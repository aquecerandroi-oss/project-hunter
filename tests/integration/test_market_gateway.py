"""T1.7 item 1 (closing Astra's second-opinion gap): ``rt:market:*`` and
``rt:system`` frames delivered through the REAL WebSocket gateway
(``apps/api/hunter_api/realtime/endpoint.py``), not just observed on the
underlying Redis pub/sub channel the way ``test_market_pipeline.py`` does.

Follows ``apps/api/tests/integration/test_websocket.py``'s own recipe
(``TestClient``, its own thread/loop, real auth/subscribe protocol) since
that is the established, working pattern for this gateway in this repo; the
worker-side publish happens inside a single, self-contained ``asyncio.run()``
call with its own engine/Redis client (a *separate* event loop is fine here
because Redis pub/sub is a network protocol, not a shared Python object --
unlike asyncpg connections, which are loop-bound).
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hunter_api.app import create_app
from hunter_api.auth.clerk import StaticKeyAuthProvider
from hunter_api.auth.principal import PrincipalResolver
from hunter_core.db.session import create_engine, create_session_factory
from hunter_core.redis import create_redis
from hunter_core.settings import Settings
from hunter_exchanges.testing.fake_adapter import FakeExchangeAdapter
from hunter_market_worker import hot_state
from hunter_market_worker.heartbeat import HeartbeatState, run_heartbeat
from hunter_market_worker.ingest import AcceptedEvents, TickCoalescer, flush_ticks, handle_event
from hunter_market_worker.persist import PersistQueues
from hunter_market_worker.universe import MonitoredUniverse

from . import pipeline_builders as b
from .conftest import FAKE_ISSUER, WEB_ORIGIN, jwks_for, sign

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI

    from hunter_api.auth.clerk_api import StaticProfileSource
    from hunter_api.settings import ApiSettings

pytestmark = pytest.mark.integration

EXCHANGE = b.EXCHANGE
SYMBOL = "GATEWAYUSDT"
PRODUCER = "market-worker@gateway-it:1"


class _FakeRuntime:
    def __init__(self, redis: object) -> None:
        self.redis = redis
        self.instance = EXCHANGE

    def mark_success(self) -> None:
        return None

    def mark_error(self) -> None:
        return None


async def _publish_a_tick_and_one_heartbeat(database_url: str, redis_url: str) -> None:
    """Everything here is self-contained: its own engine, its own Redis
    client, its own event loop (``asyncio.run`` below) -- nothing crosses
    into the ``TestClient``'s loop except over the wire, via Redis itself."""
    settings = Settings(database_url=SecretStr(database_url), redis_url=SecretStr(redis_url))
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis = create_redis(settings)
    try:
        queues, coalescer, accepted = PersistQueues(), TickCoalescer(), AcceptedEvents()
        ticker = b.ticker(SYMBOL, "42")
        assert await handle_event(
            ticker, redis, PRODUCER, queues, coalescer, accepted, hot_state.TradeMemory()
        )
        await flush_ticks(coalescer, redis, PRODUCER)

        adapter = FakeExchangeAdapter(
            code=EXCHANGE, markets=[b.market(SYMBOL, "GATEWAY")], connection_states=("connected",)
        )
        universe = MonitoredUniverse()
        universe.set([SYMBOL])
        state = HeartbeatState()
        hb_task = asyncio.create_task(
            run_heartbeat(cast(Any, _FakeRuntime(redis)), adapter, universe, state, session_factory)
        )
        await asyncio.sleep(
            0.3
        )  # one heartbeat tick is enough; it publishes on the first iteration
        hb_task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await hb_task
    finally:
        await redis.aclose()
        await engine.dispose()


def test_gateway_delivers_rt_market_and_rt_system_frames(
    api_settings: ApiSettings,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
    pipeline_db_url: str,
    pipeline_redis_url: str,
) -> None:
    app: FastAPI = create_app(api_settings)
    app.state.auth_provider = StaticKeyAuthProvider(
        jwks_for(signing_key), issuer=FAKE_ISSUER, allowed_azp=api_settings.cors_allowed_origins
    )
    app.state.profiles = profiles
    from hunter_api.auth.clerk_api import UserProfile

    profiles.add(UserProfile(external_auth_id="user_FAKE_gateway", email="gateway@example.test"))

    channel = f"rt:market:{EXCHANGE}:{SYMBOL}"
    with TestClient(app, client=("203.0.113.77", 55123)) as raw_client:
        app.state.principal_resolver = PrincipalResolver(
            app.state.session_factory, app.state.profiles
        )
        token = sign(signing_key, subject="user_FAKE_gateway", azp=WEB_ORIGIN)
        with raw_client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({"type": "auth", "token": token}))
            assert json.loads(websocket.receive_text()) == {"type": "authenticated"}
            websocket.send_text(
                json.dumps({"type": "subscribe", "channels": [channel, "rt:system"]})
            )
            subscribed = json.loads(websocket.receive_text())
            assert subscribed["type"] == "subscribed"
            assert set(subscribed["channels"]) == {channel, "rt:system"}

            asyncio.run(_publish_a_tick_and_one_heartbeat(pipeline_db_url, pipeline_redis_url))

            received: dict[str, dict[str, Any]] = {}
            for _ in range(10):
                if {channel, "rt:system"} <= received.keys():
                    break
                frame = json.loads(websocket.receive_text())
                if frame.get("type") == "ping":
                    websocket.send_text(json.dumps({"type": "pong"}))
                    continue
                if "channel" in frame:
                    received[frame["channel"]] = frame

    assert channel in received, "rt:market frame never arrived through the gateway"
    assert "rt:system" in received, "rt:system frame never arrived through the gateway"
    market_payload = json.loads(received[channel]["data"])
    assert market_payload["symbol"] == SYMBOL
    assert market_payload["price"] == "42"
    system_payload = json.loads(received["rt:system"]["data"])
    assert system_payload["type"] == "market_status"
    assert system_payload["exchange"] == EXCHANGE
