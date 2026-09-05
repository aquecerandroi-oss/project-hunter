"""``/ws`` protocol: authenticate first, subscribe only to your own channels.

Uses ``starlette.testclient.TestClient`` specifically for its
``websocket_connect()`` — ``httpx`` (used elsewhere in this suite) has no
WebSocket support at all. Tokens are signed with the in-process FAKE keypair
and verified through the real ``StaticKeyAuthProvider``, so these exercise the
production verification path rather than a stub that trusts its input.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import defaultdict
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hunter_api.auth.clerk import AuthUnavailableError, StaticKeyAuthProvider, TokenClaims
from hunter_api.auth.principal import Membership, Principal
from hunter_api.realtime import session as ws_session
from hunter_api.realtime.endpoint import (
    RealtimeHub,
    _serve,  # pyright: ignore[reportPrivateUsage]
)
from hunter_api.realtime.session import WsSession, watch_session
from hunter_core.domain.enums import MemberStatus, OrganizationRole

from .jwt_keys import FAKE_ISSUER, generate_keypair, jwks_for, sign

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from anyio.from_thread import BlockingPortal
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI, WebSocket

    from hunter_api.settings import ApiSettings

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


class _WindowRedis:
    """In-memory sorted sets — the four commands the sliding window uses.

    Every fixture below installs one. The suite's ``app.state.redis`` points at
    an unreachable address on purpose, and the handshake limit is the first
    thing ``/ws`` does, so without this each connect pays a TCP timeout before
    failing open.
    """

    def __init__(self) -> None:
        self._sets: dict[str, dict[str, float]] = defaultdict(dict)

    async def zremrangebyscore(self, name: str, min_: float, max_: float) -> None:
        self._sets[name] = {
            member: score
            for member, score in self._sets[name].items()
            if not (min_ <= score <= max_)
        }

    async def zadd(self, name: str, mapping: dict[str, float]) -> None:
        self._sets[name].update(mapping)

    async def zcard(self, name: str) -> int:
        return len(self._sets[name])

    async def expire(self, name: str, seconds: int) -> bool:
        return True

    def keys(self) -> list[str]:
        return list(self._sets)


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
        # the app's own hub points at an unreachable Redis; swap in the fakes
        app.state.realtime = hub
        app.state.redis = _WindowRedis()
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
        app.state.redis = _WindowRedis()
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


# ---- idle: a pong is not activity ----------------------------------------
#
# Driven directly against ``_serve`` and ``watch_session`` with a fake clock,
# rather than through a socket: the question is whether one specific frame
# type resets the idle timer, and a wall-clock test of that is a race with the
# watchdog it is trying to observe.


class _Clock:
    """Stands in for the ``time`` module inside ``realtime.session``."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _ScriptedSocket:
    """A live socket, reduced to what the receive loop and watchdog touch:
    a fixed list of inbound frames, whatever was written back, and the close
    code the server chose.
    """

    def __init__(self, app: FastAPI, frames: list[str]) -> None:
        self.app = app
        self.state = SimpleNamespace(pong_pending=False)
        self._frames = list(frames)
        self.sent: list[str] = []
        self.closed_with: int | None = None

    async def receive_text(self) -> str:
        if not self._frames:
            raise WebSocketDisconnect(1000)
        return self._frames.pop(0)

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = code


def _session(principal: Principal) -> WsSession:
    return WsSession(principal, TokenClaims(subject="user_FAKE_clerk_id"))


@pytest.fixture
def idle_app(
    app: FastAPI,
    api_settings: ApiSettings,
    principal: Principal,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    """The app the watchdog reads its interval and resolver off.

    Populated by hand rather than by the lifespan: nothing here opens a socket,
    so there is no ``TestClient`` to run one.
    """
    app.state.settings = api_settings.model_copy(update={"ws_revalidate_interval_s": 0.01})
    app.state.principal_resolver = _FakeResolver(principal)
    monkeypatch.setattr(ws_session, "IDLE_TIMEOUT_SECONDS", 300)
    return app


async def test_a_pong_only_client_is_closed_as_idle(
    idle_app: FastAPI, principal: Principal, hub: RealtimeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Answering the heartbeat is not using the connection.

    The pong is the server's own ping coming back, and a browser answers it
    whether or not anybody is looking at the tab. Count it as activity and the
    idle timeout can only ever fire for a client that has *also* stopped
    answering — which is what the 4408 pong timeout already covers — so every
    abandoned tab holds a slot, a Redis subscription and two tasks for as long
    as it is left open.
    """
    clock = _Clock()
    monkeypatch.setattr(ws_session, "time", clock)
    session = _session(principal)
    socket = _ScriptedSocket(idle_app, [json.dumps({"type": "pong"})] * 5)

    await _serve(cast("WebSocket", socket), session, hub)
    clock.advance(301)
    await watch_session(cast("WebSocket", socket), session, hub)

    assert socket.closed_with == 4409


async def test_a_client_sending_real_frames_is_not_idle(
    idle_app: FastAPI, principal: Principal, hub: RealtimeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the rule: a frame that is not a pong does reset the
    clock, well past the point a pong-only client would have been closed."""
    clock = _Clock()
    monkeypatch.setattr(ws_session, "time", clock)
    session = _session(principal)
    socket = _ScriptedSocket(
        idle_app, [json.dumps({"type": "subscribe", "channels": ["rt:radar"]})]
    )

    clock.advance(299)
    await _serve(cast("WebSocket", socket), session, hub)
    clock.advance(299)
    watchdog = asyncio.ensure_future(watch_session(cast("WebSocket", socket), session, hub))
    await asyncio.sleep(0.05)  # several revalidation rounds at 10 ms
    watchdog.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watchdog

    assert socket.closed_with is None


# ---- the handshake limit and the connection cap ---------------------------


def _bounded_client(
    app: FastAPI,
    private_key: rsa.RSAPrivateKey,
    principal: Principal,
    hub: RealtimeHub,
    **limits: int,
) -> Iterator[TestClient]:
    app.state.auth_provider = StaticKeyAuthProvider(jwks_for(private_key), issuer=FAKE_ISSUER)
    app.state.principal_resolver = _FakeResolver(principal)
    with TestClient(app) as client:
        app.state.realtime = hub
        app.state.redis = _WindowRedis()
        app.state.settings = app.state.settings.model_copy(update=limits)
        yield client


@pytest.fixture
def handshake_limited_client(
    app: FastAPI, private_key: rsa.RSAPrivateKey, principal: Principal, hub: RealtimeHub
) -> Iterator[TestClient]:
    """Two handshakes a minute, no meaningful connection cap."""
    yield from _bounded_client(
        app,
        private_key,
        principal,
        hub,
        ws_handshakes_per_minute=2,
        ws_max_connections_per_principal=50,
    )


@pytest.fixture
def connection_capped_client(
    app: FastAPI, private_key: rsa.RSAPrivateKey, principal: Principal, hub: RealtimeHub
) -> Iterator[TestClient]:
    """Two live connections per principal, no meaningful handshake limit."""
    yield from _bounded_client(
        app,
        private_key,
        principal,
        hub,
        ws_handshakes_per_minute=1000,
        ws_max_connections_per_principal=2,
    )


def test_the_handshake_is_rate_limited_before_it_is_accepted(
    handshake_limited_client: TestClient, private_key: rsa.RSAPrivateKey
) -> None:
    """Opening a socket is cheaper for the client than it is for us.

    Every accepted connection costs a task, a slot in the fan-out and five
    seconds of patience waiting for the auth frame — and none of that requires
    a token, so without a limit on the handshake itself an unauthenticated
    caller opens them as fast as the network allows. The check runs before
    ``accept()``, so a refused handshake costs a header parse.
    """
    for _ in range(2):
        with handshake_limited_client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
            assert json.loads(websocket.receive_text()) == {"type": "authenticated"}

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        handshake_limited_client.websocket_connect("/ws"),
    ):
        pass  # pragma: no cover - the handshake never completes

    assert exc_info.value.code == 4429


def test_a_principal_cannot_hold_more_than_the_connection_cap(
    connection_capped_client: TestClient, private_key: rsa.RSAPrivateKey
) -> None:
    """The handshake limit is per address; this one is per account.

    One signed-in user opening a socket per tab, per device and per reconnect
    loop is a slow leak of tasks and Redis subscriptions that no address limit
    catches once the connections are spread out in time.
    """
    with contextlib.ExitStack() as open_sockets:
        for _ in range(2):
            websocket = open_sockets.enter_context(
                connection_capped_client.websocket_connect("/ws")
            )
            websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
            assert json.loads(websocket.receive_text()) == {"type": "authenticated"}

        third = open_sockets.enter_context(connection_capped_client.websocket_connect("/ws"))
        third.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))

        with pytest.raises(WebSocketDisconnect) as exc_info:
            third.receive_text()

    assert exc_info.value.code == 4429


def test_a_closed_connection_gives_its_slot_back(
    connection_capped_client: TestClient, private_key: rsa.RSAPrivateKey, hub: RealtimeHub
) -> None:
    """A cap that only ever counts up is a cap that locks an account out."""
    for _ in range(4):
        with connection_capped_client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
            assert json.loads(websocket.receive_text()) == {"type": "authenticated"}

    assert hub.manager.connection_count(str(USER)) == 0


# ---- 4503: the credential was never judged --------------------------------


class _UnavailableAuthProvider:
    """Clerk's JWKS is unreachable — no verdict on the token, either way."""

    async def verify(self, token: str) -> TokenClaims:
        raise AuthUnavailableError


def test_an_unreachable_jwks_closes_4503_not_4401(
    app: FastAPI, hub: RealtimeHub, private_key: rsa.RSAPrivateKey, principal: Principal
) -> None:
    """4401 tells the browser its session is dead and sends the user back to
    Clerk to sign in again — through the provider that is the thing currently
    unavailable. The token was never judged, so no answer about it is honest;
    4503 says what is true and the client can retry.
    """
    app.state.auth_provider = _UnavailableAuthProvider()
    app.state.principal_resolver = _FakeResolver(principal)
    with TestClient(app) as client:
        app.state.realtime = hub
        app.state.redis = _WindowRedis()
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({"type": "auth", "token": sign(private_key)}))
            with pytest.raises(WebSocketDisconnect) as exc_info:
                websocket.receive_text()

    assert exc_info.value.code == 4503


# --- MEDIUM (security review of the T1.6b proof, 2026-09-05) --------------
# `RealtimeHub._intervals` and the throttle's `_last_emit` are keyed by the
# client-supplied channel name. They were never pruned, and a live socket has
# no per-message rate limit, so a subscribe/unsubscribe loop on fresh names
# grew both dicts for the lifetime of the process. Measured before the fix:
# 5000 cycles left `manager.channels()` at 0 and 5000 entries behind.
@pytest.mark.asyncio
async def test_per_channel_state_dies_with_the_last_subscriber(hub: RealtimeHub) -> None:
    socket = cast("WebSocket", object())
    for index in range(200):
        channel = f"rt:market:binance:BTC{index}USDT"
        await hub.subscribe(socket, channel)
        await hub.unsubscribe(socket, channel)

    assert hub.manager.channels() == []
    assert hub._intervals == {}
    assert hub._throttle._last_emit == {}


@pytest.mark.asyncio
async def test_detaching_a_socket_also_drops_its_channel_state(hub: RealtimeHub) -> None:
    socket = cast("WebSocket", object())
    for index in range(50):
        await hub.subscribe(socket, f"rt:market:binance:ETH{index}USDT")

    await hub.detach(socket)

    assert hub._intervals == {}
    assert hub._throttle._last_emit == {}


@pytest.mark.asyncio
async def test_state_survives_while_another_subscriber_is_still_there(
    hub: RealtimeHub,
) -> None:
    first, second = cast("WebSocket", object()), cast("WebSocket", object())
    channel = "rt:market:binance:BTCUSDT"
    await hub.subscribe(first, channel)
    await hub.subscribe(second, channel)

    await hub.unsubscribe(first, channel)

    assert hub._intervals[channel] > 0, "the surviving subscriber still needs its throttle"
