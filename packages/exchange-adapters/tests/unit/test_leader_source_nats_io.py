"""Copy-trade pilot (H-037): the IO seams of the NATS source — the home-page read and the socket options."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
import pytest

from hunter_exchanges.pumpfun import leader_source_nats_io as module
from hunter_exchanges.pumpfun.leader_source_nats_io import default_connect, default_fetch_config
from hunter_exchanges.pumpfun.leader_source_nats_wire import NatsAuthError, NatsRefused

pytestmark = pytest.mark.unit

PAGE = (
    '..."configs":{"CORE":{"servers":"wss://core.nats.invalid","user":"subscriber",'
    '"pass":"TEST-ONLY-NOT-A-REAL-PASSWORD"}}...'
)


def transport(
    status: int, body: str = "", headers: dict[str, str] | None = None
) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, text=body, headers=headers))


async def test_a_good_page_yields_the_credential_and_it_never_appears_in_str() -> None:
    cfg = await default_fetch_config(transport=transport(200, PAGE))
    assert cfg.user == "subscriber" and "TEST-ONLY" not in str(cfg) + repr(cfg)


@pytest.mark.parametrize("status", [401, 403, 418, 429, 500, 502, 503, 504, 520])
async def test_a_block_or_a_server_error_on_the_page_is_a_refusal_not_a_plain_error(
    status: int,
) -> None:
    with pytest.raises(NatsRefused) as err:
        await default_fetch_config(transport=transport(status))
    assert err.value.status == status and err.value.retry_after_s is None


async def test_retry_after_is_honoured_when_the_page_says_so() -> None:
    with pytest.raises(NatsRefused) as err:
        await default_fetch_config(transport=transport(503, headers={"Retry-After": "120"}))
    assert err.value.retry_after_s == 120.0


@pytest.mark.parametrize("value", ["soon", "-5", "nan", "inf"])
async def test_an_unreadable_retry_after_is_ignored_not_trusted(value: str) -> None:
    with pytest.raises(NatsRefused) as err:
        await default_fetch_config(transport=transport(429, headers={"Retry-After": value}))
    assert err.value.retry_after_s is None


async def test_an_absurd_retry_after_is_capped() -> None:
    with pytest.raises(NatsRefused) as err:
        await default_fetch_config(transport=transport(429, headers={"Retry-After": "99999999"}))
    assert err.value.retry_after_s == module.RETRY_AFTER_MAX_S


async def test_a_page_without_the_credential_is_an_auth_error() -> None:
    with pytest.raises(NatsAuthError):
        await default_fetch_config(transport=transport(200, "<html>nothing</html>"))


async def test_other_client_errors_are_plain_connection_errors() -> None:
    with pytest.raises(ConnectionError):
        await default_fetch_config(transport=transport(404))


def test_the_socket_has_a_finite_receive_queue_and_a_message_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import websockets

    seen: dict[str, Any] = {}

    def fake_connect(url: str, **kwargs: Any) -> object:
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(websockets, "connect", fake_connect)
    default_connect("wss://core.nats.invalid")
    assert (
        isinstance(seen["max_queue"], int) and 0 < seen["max_queue"] <= 1024
    )  # backpressure restored
    assert 0 < seen["max_size"] <= 8 * 1024 * 1024


NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


async def test_retry_after_given_as_a_date_is_honoured() -> None:
    when = format_datetime(NOW + timedelta(seconds=7200), usegmt=True)
    with pytest.raises(NatsRefused) as err:
        await default_fetch_config(
            transport=transport(429, headers={"Retry-After": when}), now=lambda: NOW
        )
    assert err.value.retry_after_s == 7200.0  # two hours: the page asked, the page gets it


async def test_a_past_date_or_garbage_is_ignored() -> None:
    past = format_datetime(NOW - timedelta(seconds=60), usegmt=True)
    for value in (past, "Not a date at all"):
        with pytest.raises(NatsRefused) as err:
            await default_fetch_config(
                transport=transport(429, headers={"Retry-After": value}), now=lambda: NOW
            )
        assert err.value.retry_after_s is None
