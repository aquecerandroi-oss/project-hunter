"""``/ws`` end to end, against the real application — ARCHITECTURE.md §5.2,
SECURITY.md §1/§5.

``tests/unit/test_ws_endpoint.py`` and ``test_ws_manager.py`` cover the
protocol against a bare, hand-assembled app; this file runs the same close
codes through ``create_app`` — real Postgres-backed membership, real Redis —
so a membership revoked through the real HTTP mutation actually reaches a
live socket, not a synthetic ``Principal`` swapped in by a fake resolver.

Everything here — HTTP setup (creating organizations, inviting and removing
members) *and* the WebSocket itself — goes through one
``starlette.testclient.TestClient``, entered once per test as its context
manager. That is deliberate, not merely convenient: ``TestClient.__enter__``
runs the ASGI lifespan (building the engine, the session factory, the Redis
client) on its own worker thread and its own event loop, and asyncpg's
connections are bound to the loop that created them. Driving HTTP through a
*second* client (``httpx.AsyncClient`` on the pytest-asyncio loop, the pattern
the rest of this suite uses) while the WebSocket runs through ``TestClient``'s
loop was tried and fails at runtime with ``RuntimeError: ... attached to a
different loop`` the moment a handler reachable from both tries to reuse a
pooled connection. One client, one loop, one pool.

``TestClient``'s HTTP verbs (``.get``/``.post``/``.delete``) resolve to a
cascade of ``Unknown`` types under pyright strict (``apps/api/tests/conftest.py``
documents why: its ``httpx``-backed sync wrapper). ``_Http`` below is a
``Protocol`` naming just the shapes this file calls, and casting the client to
it once gives every call site a concrete, fully-typed ``httpx.Response`` — the
same trick without a type-ignore comment at every call.

``ws_revalidate_interval_s`` and (via monkeypatch, since it is a module
constant rather than a setting) ``IDLE_TIMEOUT_SECONDS`` are both shortened so
these tests run in well under a second instead of a minute-plus.

Each ``TestClient`` below is given its own ``client=`` address (a distinct
one in the ``TEST-NET-3`` documentation range, RFC 5737) rather than
``TestClient``'s default ``("testclient", 50000)``. The ``/ws`` handshake
limit's Redis window (``realtime.endpoint._handshake_allowed``, sharing
``middleware.rate_limit``'s bucket implementation) is keyed on nothing but
the peer address and a ``ws`` scope — never on which application or settings
opened the socket — so every ``TestClient()`` left at the library default
would spend down one shared budget: ``test_rate_limits.py``'s handshake-limit
test tightens that budget to 2 for its own custom app, and without a
dedicated address here, whichever suite of tests happens to run its
handshakes first exhausts it for the other, closing sockets with 4429
instead of the codes each test actually means to exercise.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from typing import TYPE_CHECKING, Protocol, cast

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hunter_api.auth.clerk_api import UserProfile
from hunter_api.auth.principal import PrincipalResolver
from hunter_api.realtime import session as ws_session
from hunter_core.domain.enums import OrganizationRole

from ..unit.jwt_keys import sign
from .conftest import Actor, build_custom_app

if TYPE_CHECKING:
    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI

    from hunter_api.auth.clerk_api import StaticProfileSource

pytestmark = pytest.mark.integration


def _rebind_resolver(app: FastAPI) -> None:
    """The lifespan (just run by ``TestClient.__enter__``) built a resolver
    against the real Clerk profile source; swap it for this test's static one
    before any socket or request tries to authenticate.
    """
    app.state.principal_resolver = PrincipalResolver(app.state.session_factory, app.state.profiles)


class _Http(Protocol):
    """The handful of ``TestClient`` methods this file calls, fully typed."""

    def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response: ...

    def post(
        self, url: str, *, json: dict[str, str] | None = None, headers: dict[str, str]
    ) -> httpx.Response: ...

    def delete(self, url: str, *, headers: dict[str, str]) -> httpx.Response: ...


def _actor(signing_key: rsa.RSAPrivateKey, profiles: StaticProfileSource, name: str) -> Actor:
    subject = f"user_FAKE_{name}"
    email = f"{name}@example.test"
    profiles.add(UserProfile(external_auth_id=subject, email=email, display_name=name.title()))
    return Actor(signing_key, subject, email)


def _create_org(client: _Http, actor: Actor, name: str) -> Actor:
    response = client.post("/api/v1/orgs", json={"name": name}, headers=actor.headers)
    assert response.status_code == 201, response.text
    body = response.json()
    actor.org_id = uuid.UUID(body["id"])
    actor.workspace_id = uuid.UUID(body["workspace_id"])
    me = client.get("/api/v1/me", headers=actor.headers)
    actor.user_id = uuid.UUID(me.json()["user"]["id"])
    return actor


def _join(
    client: _Http,
    owner: Actor,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
    name: str,
    role: OrganizationRole,
) -> Actor:
    joiner = _actor(signing_key, profiles, name)
    created = client.post(
        f"/api/v1/orgs/{owner.org_id}/invitations",
        json={"email": joiner.email, "role": role.value},
        headers=owner.headers,
    )
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    accepted = client.post(f"/api/v1/invitations/{token}/accept", headers=joiner.headers)
    assert accepted.status_code == 200, accepted.text
    me = client.get("/api/v1/me", headers=joiner.headers)
    joiner.user_id = uuid.UUID(me.json()["user"]["id"])
    joiner.org_id = owner.org_id
    return joiner


def test_a_member_removed_mid_connection_is_closed_4403_within_the_revalidation_interval(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
        ws_revalidate_interval_s=0.1,
    )

    with TestClient(app, client=("203.0.113.11", 44444)) as raw_client:
        _rebind_resolver(app)
        client = cast("_Http", raw_client)
        owner = _create_org(client, _actor(signing_key, profiles, "ws-revoke-owner"), "WS Revoke")
        member = _join(
            client, owner, signing_key, profiles, "ws-revoke-member", OrganizationRole.TRADER
        )
        channel = f"rt:org:{owner.org_id}:risk"

        with raw_client.websocket_connect("/ws") as websocket:
            websocket.send_text(
                json.dumps({"type": "auth", "token": sign(signing_key, subject=member.subject)})
            )
            assert json.loads(websocket.receive_text()) == {"type": "authenticated"}
            websocket.send_text(json.dumps({"type": "subscribe", "channels": [channel]}))
            assert json.loads(websocket.receive_text()) == {
                "type": "subscribed",
                "channels": [channel],
            }

            removed = client.delete(
                f"/api/v1/orgs/{owner.org_id}/members/{member.user_id}", headers=owner.headers
            )
            assert removed.status_code == 204

            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_text()

    assert exc_info.value.code == 4403


def test_a_pong_only_client_is_closed_4409_after_the_idle_window(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client that keeps answering pings but never sends a real frame is not
    the pong-timeout's job (``session.mark_frame`` is deliberately *not*
    called for a ``pong``) — it is the idle watchdog's, sharing the same
    revalidation loop.
    """
    monkeypatch.setattr(ws_session, "IDLE_TIMEOUT_SECONDS", 0.3)
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
        ws_revalidate_interval_s=0.1,
    )
    subject = "user_FAKE_ws_idle"
    profiles.add(UserProfile(external_auth_id=subject, email="ws-idle@example.test"))

    with TestClient(app, client=("203.0.113.12", 44444)) as client:
        _rebind_resolver(app)
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(
                json.dumps({"type": "auth", "token": sign(signing_key, subject=subject)})
            )
            assert json.loads(websocket.receive_text()) == {"type": "authenticated"}
            websocket.send_text(json.dumps({"type": "pong"}))

            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_text()

    assert exc_info.value.code == 4409


def test_subscribing_to_another_orgs_channel_is_an_error_frame_not_a_close(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    """``endpoint._subscribe`` refuses one bad channel name in a batch without
    dropping the connection — a working socket must survive a client asking
    for something it may not have.
    """
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
    )

    with TestClient(app, client=("203.0.113.13", 44444)) as raw_client:
        _rebind_resolver(app)
        client = cast("_Http", raw_client)
        member = _create_org(client, _actor(signing_key, profiles, "ws-chan-a"), "WS Channels A")
        other = _create_org(client, _actor(signing_key, profiles, "ws-chan-b"), "WS Channels B")
        forbidden_channel = f"rt:org:{other.org_id}:risk"

        with raw_client.websocket_connect("/ws") as websocket:
            websocket.send_text(
                json.dumps({"type": "auth", "token": sign(signing_key, subject=member.subject)})
            )
            assert json.loads(websocket.receive_text()) == {"type": "authenticated"}

            websocket.send_text(json.dumps({"type": "subscribe", "channels": [forbidden_channel]}))
            error = json.loads(websocket.receive_text())
            assert error == {
                "type": "error",
                "code": "forbidden_channel",
                "channel": forbidden_channel,
            }
            # one "error" per rejected channel, then always one "subscribed"
            # naming what actually got through — empty here, since nothing did
            assert json.loads(websocket.receive_text()) == {"type": "subscribed", "channels": []}

            # the socket is still alive: an unauthorized channel is refused
            # individually, not treated as a protocol violation
            websocket.send_text(json.dumps({"type": "ping"}))
            assert json.loads(websocket.receive_text()) == {"type": "pong"}


def test_the_sixth_connection_for_one_principal_is_4429(
    api_database_url: str,
    redis_url: str,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> None:
    """The default ``ws_max_connections_per_principal`` is 5 (``settings.py``);
    this is the property, not a shortened stand-in for it.
    """
    app = build_custom_app(
        database_url=api_database_url,
        redis_url=redis_url,
        signing_key=signing_key,
        profiles=profiles,
    )
    subject = "user_FAKE_ws_conn_cap"
    profiles.add(UserProfile(external_auth_id=subject, email="ws-conn-cap@example.test"))
    token = sign(signing_key, subject=subject)

    with (
        TestClient(app, client=("203.0.113.14", 44444)) as client,
        contextlib.ExitStack() as open_sockets,
    ):
        _rebind_resolver(app)
        for _ in range(5):
            websocket = open_sockets.enter_context(client.websocket_connect("/ws"))
            websocket.send_text(json.dumps({"type": "auth", "token": token}))
            assert json.loads(websocket.receive_text()) == {"type": "authenticated"}

        sixth = open_sockets.enter_context(client.websocket_connect("/ws"))
        sixth.send_text(json.dumps({"type": "auth", "token": token}))

        with pytest.raises(WebSocketDisconnect) as exc_info:
            sixth.receive_text()

    assert exc_info.value.code == 4429
