"""``/ws`` protocol: authenticate first, subscribe only to your own channels.

Uses ``starlette.testclient.TestClient`` specifically for its
``websocket_connect()`` — ``httpx`` (used elsewhere in this suite) has no
WebSocket support at all. Tokens are signed with the in-process FAKE keypair
and verified through the real ``StaticKeyAuthProvider``, so these exercise the
production verification path rather than a stub that trusts its input.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hunter_api.auth.clerk import StaticKeyAuthProvider
from hunter_api.auth.principal import Membership, Principal
from hunter_api.realtime import session as ws_session
from hunter_api.realtime.endpoint import RealtimeHub
from hunter_core.domain.enums import MemberStatus, OrganizationRole

from .jwt_keys import FAKE_ISSUER, generate_keypair, jwks_for, sign

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from anyio.from_thread import BlockingPortal
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI

    from hunter_api.auth.clerk import TokenClaims

pytestmark = pytest.mark.unit

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
USER = uuid.uuid4()


class _FakePubSub:
    """Just enough of ``redis.asyncio`` pub/sub for the bridge, in memory."""

    def __init__(self) -> None:
        self.channels: set[str] = set()

    async def subscribe(self, *channels: str) -> None:
        self.channels.update(channels)

    async def unsubscribe(self, *channels: str) -> None:
        self.channels.difference_update(channels)

    async def psubscribe(self, *patterns: str) -> None:
        self.channels.update(patterns)

    async def punsubscribe(self, *patterns: str) -> None:
        self.channels.difference_update(patterns)

    async def aclose(self) -> None:
        self.channels.clear()

    async def listen(self) -> AsyncIterator[dict[str, Any]]:
        # never yields: these tests drive the socket, not the Redis side
        while True:  # pragma: no cover - the dispatcher task is cancelled
            await _never()
            yield {}


async def _never() -> None:  # pragma: no cover
    import asyncio

    await asyncio.sleep(3600)


class _FakeRedis:
    def __init__(self) -> None:
        self.pubsub_instance = _FakePubSub()

    def pubsub(self) -> _FakePubSub:
        return self.pubsub_instance


class _FakeResolver:
    """Resolves any verified claim to one principal — the DB path is covered
    by the integration suite; here the subject of the test is the protocol.

    ``principal`` is writable so a test can change what the next revalidation
    round sees, which is how membership is taken away mid-connection.
    """

    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def resolve(self, claims: TokenClaims) -> Principal:
        return self.principal


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return generate_keypair()


@pytest.fixture
def principal() -> Principal:
    return Principal(
        user_id=USER,
        external_auth_id="user_FAKE_clerk_id",
        email="member@example.test",
        memberships=(
            Membership(org_id=ORG_A, role=OrganizationRole.TRADER, status=MemberStatus.ACTIVE),
        ),
    )


@pytest.fixture
def hub() -> RealtimeHub:
    """A hub over an in-memory Redis, so subscribing touches no socket."""
    return RealtimeHub(_FakeRedis())  # pyright: ignore[reportArgumentType]


@pytest.fixture
def ws_client(
    app: FastAPI, private_key: rsa.RSAPrivateKey, principal: Principal, hub: RealtimeHub
) -> Iterator[TestClient]:
    app.state.auth_provider = StaticKeyAuthProvider(jwks_for(private_key), issuer=FAKE_ISSUER)
    app.state.principal_resolver = _FakeResolver(principal)
    with TestClient(app) as client:
        # the app's own hub points at an unreachable Redis; swap in the fake
        app.state.realtime = hub
        yield client


def test_no_auth_message_closes_4401(ws_client: TestClient) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "subscribe", "channels": ["rt:radar"]}))
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4401


def test_a_bad_token_closes_4401(ws_client: TestClient) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "not-a-real-token"}))
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4401


def test_a_token_signed_by_another_key_closes_4401(ws_client: TestClient) -> None:
    other = generate_keypair()
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(other)}))
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4401


def test_a_valid_token_authenticates(ws_client: TestClient, private_key: rsa.RSAPrivateKey) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        assert json.loads(websocket.receive_text()) == {"type": "authenticated"}


def test_public_channels_are_accepted(
    ws_client: TestClient, private_key: rsa.RSAPrivateKey
) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(
            json.dumps({"type": "subscribe", "channels": ["rt:radar", "rt:market:binance:BTCUSDT"]})
        )
        reply = json.loads(websocket.receive_text())

    assert reply["type"] == "subscribed"
    assert reply["channels"] == ["rt:radar", "rt:market:binance:BTCUSDT"]


def test_own_org_channel_is_accepted(ws_client: TestClient, private_key: rsa.RSAPrivateKey) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(json.dumps({"type": "subscribe", "channels": [f"rt:org:{ORG_A}:risk"]}))
        reply = json.loads(websocket.receive_text())

    assert reply["channels"] == [f"rt:org:{ORG_A}:risk"]


def test_another_orgs_channel_is_refused(
    ws_client: TestClient, private_key: rsa.RSAPrivateKey
) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(json.dumps({"type": "subscribe", "channels": [f"rt:org:{ORG_B}:risk"]}))
        error = json.loads(websocket.receive_text())
        subscribed = json.loads(websocket.receive_text())

    assert error == {
        "type": "error",
        "code": "forbidden_channel",
        "channel": f"rt:org:{ORG_B}:risk",
    }
    # the socket stays open and the batch reports what actually landed
    assert subscribed["channels"] == []


@pytest.mark.parametrize(
    "channel",
    [
        "rt:org:*:risk",
        "rt:org:*",
        "*",
        "rt:market:*",
        "rt:org:not-a-uuid:risk",
        "internal:secrets",
        "",
    ],
)
def test_wildcards_and_junk_are_refused(
    ws_client: TestClient, private_key: rsa.RSAPrivateKey, channel: str
) -> None:
    # a wildcard would be authorized against nothing and then have Redis
    # deliver every tenant's messages down this one socket
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(json.dumps({"type": "subscribe", "channels": [channel]}))
        error = json.loads(websocket.receive_text())

    assert error["code"] == "forbidden_channel"


def test_a_published_message_reaches_a_subscriber(
    ws_client: TestClient, private_key: rsa.RSAPrivateKey, hub: RealtimeHub
) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(json.dumps({"type": "subscribe", "channels": ["rt:radar"]}))
        websocket.receive_text()

        # what the Redis bridge calls when a worker publishes on this channel.
        # The portal is how a sync test reaches the loop TestClient runs the
        # app on; starlette types it through a deprecated anyio alias, hence
        # the cast.
        portal = cast(
            "BlockingPortal | None",
            ws_client.portal,  # pyright: ignore[reportUnknownMemberType]
        )
        assert portal is not None
        portal.call(hub.dispatch, "rt:radar", b'{"score": 91}')

        delivered = json.loads(websocket.receive_text())

    assert delivered == {"channel": "rt:radar", "data": '{"score": 91}'}


def test_a_malformed_frame_closes_4400(
    ws_client: TestClient, private_key: rsa.RSAPrivateKey
) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text("not json at all")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4400


def test_an_unknown_message_type_closes_4400(
    ws_client: TestClient, private_key: rsa.RSAPrivateKey
) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(json.dumps({"type": "publish", "channel": "rt:radar"}))
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4400


def test_a_client_ping_is_answered(ws_client: TestClient, private_key: rsa.RSAPrivateKey) -> None:
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(json.dumps({"type": "ping"}))

        assert json.loads(websocket.receive_text()) == {"type": "pong"}


@pytest.fixture
def resolver(principal: Principal) -> _FakeResolver:
    return _FakeResolver(principal)


@pytest.fixture
def watched_client(
    app: FastAPI,
    private_key: rsa.RSAPrivateKey,
    resolver: _FakeResolver,
    hub: RealtimeHub,
) -> Iterator[TestClient]:
    """A client whose sockets revalidate every 50 ms instead of every minute."""
    app.state.auth_provider = StaticKeyAuthProvider(jwks_for(private_key), issuer=FAKE_ISSUER)
    app.state.principal_resolver = resolver
    with TestClient(app) as client:
        app.state.realtime = hub
        app.state.settings = app.state.settings.model_copy(
            update={"ws_revalidate_interval_s": 0.05}
        )
        yield client


def test_losing_membership_closes_the_socket_and_drops_the_org_subscription(
    watched_client: TestClient,
    private_key: rsa.RSAPrivateKey,
    resolver: _FakeResolver,
    hub: RealtimeHub,
) -> None:
    """A socket outlives the request that authorized it.

    Membership is checked once, at subscribe time, and a WebSocket then stays
    open for hours. Remove someone from an organization — or suspend them
    through the Clerk webhook — and without revalidation their open socket
    keeps receiving that organization's risk events and positions for as long
    as they leave the tab open.
    """
    channel = f"rt:org:{ORG_A}:risk"
    with watched_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(json.dumps({"type": "subscribe", "channels": [channel]}))
        assert json.loads(websocket.receive_text())["channels"] == [channel]

        resolver.principal = Principal(
            user_id=USER, external_auth_id="user_FAKE_clerk_id", memberships=()
        )

        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4403
    assert hub.manager.subscriber_count(channel) == 0


def test_a_socket_that_keeps_its_membership_stays_open(
    watched_client: TestClient, private_key: rsa.RSAPrivateKey
) -> None:
    channel = f"rt:org:{ORG_A}:risk"
    with watched_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()
        websocket.send_text(json.dumps({"type": "subscribe", "channels": [channel]}))
        websocket.receive_text()

        # several revalidation rounds later the socket is still usable
        time.sleep(0.2)
        websocket.send_text(json.dumps({"type": "ping"}))

        assert json.loads(websocket.receive_text()) == {"type": "pong"}


def test_an_idle_socket_is_closed(
    watched_client: TestClient, private_key: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A connection nobody is using still holds a slot, a Redis subscription
    and a task. The pong timeout only catches a client that stopped answering;
    this catches one that answers and does nothing else, forever.
    """
    monkeypatch.setattr(ws_session, "IDLE_TIMEOUT_SECONDS", 0.1)

    with watched_client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
        websocket.receive_text()

        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4409
