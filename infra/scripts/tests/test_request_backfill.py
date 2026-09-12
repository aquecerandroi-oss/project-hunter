"""Unit tests for ``infra/scripts/request_backfill.py`` — the window arithmetic.

No database: everything that can silently deliver a quarter of what was asked
for is pure. The collector truncates a request wider than seven days *to its
most recent seven days* and says so only in its own log, so the whole value of
this script is that it never sends one — which is a property of
:func:`chunks_for` and of nothing else.

Run:
    uv run pytest infra/scripts/tests/test_request_backfill.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SCRIPTS_DIR / "request_backfill.py"

NOW = datetime(2026, 9, 8, 12, 37, 41, 123456, tzinfo=UTC)
MARKET = UUID("11111111-1111-7111-8111-111111111111")


def _load_module() -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("hunter_infra_request_backfill_ut", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered *before* execution: the script's dataclasses are declared under
    # ``from __future__ import annotations``, and ``dataclasses`` resolves a
    # string annotation through ``sys.modules[cls.__module__]``. A module loaded
    # by path that is not registered makes that lookup return ``None``.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_window_reaches_one_bar_past_the_days_asked_for() -> None:
    """The first hourly return of the window needs the close before it."""
    module = _load_module()
    start, end = module.window_for(NOW, 31)

    assert end == datetime(2026, 9, 8, 12, 35, tzinfo=UTC)  # floored, minus the grace
    assert end - start == timedelta(days=31, hours=1)


def test_no_request_is_ever_wider_than_the_collector_ceiling() -> None:
    """Seven days is policy on the other side: a wider window loses its old end."""
    module = _load_module()
    target = module.Target(market_id=MARKET, symbol="BTCUSDT")
    start, end = module.window_for(NOW, 31)

    chunks = module.chunks_for(target, start, end)

    assert all(chunk.minutes <= module.MAX_REQUEST_MINUTES for chunk in chunks)
    assert sum(chunk.minutes for chunk in chunks) == int((end - start).total_seconds() // 60)
    # Contiguous, newest first, no overlap and no hole between them.
    assert chunks[0].gap_end == end
    assert chunks[-1].gap_start == start
    for newer, older in zip(chunks, chunks[1:], strict=False):
        assert newer.gap_start == older.gap_end
    assert len(chunks) == 5  # 31 d + 1 h over a 7 d ceiling


def test_the_identity_of_a_request_is_its_window() -> None:
    """Asking twice is one gap: the same window is the same ``event_id``."""
    module = _load_module()
    target = module.Target(market_id=MARKET, symbol="BTCUSDT")
    start, end = module.window_for(NOW, 31)
    chunks = module.chunks_for(target, start, end)

    first = module.envelope_for(chunks[0], "binance")
    again = module.envelope_for(chunks[0], "binance")
    neighbour = module.envelope_for(chunks[1], "binance")

    assert first.event_id == again.event_id
    assert first.event_id != neighbour.event_id
    assert first.type == "market.backfill.requested"
    assert first.key == "binance:BTCUSDT"
    assert first.payload["timeframe"] == "1m"
    assert first.payload["gap_start"] == chunks[0].gap_start.isoformat()
    assert first.payload["gap_end"] == chunks[0].gap_end.isoformat()
    assert first.payload["reason"] == "beta_history"


def test_the_event_id_matches_the_one_the_scanner_would_publish() -> None:
    """Same stream, same parts: a scanner request and this one are one gap.

    The point of the assertion is that this script is not a second producer of
    a look-alike event — it is the same producer of the same event, so the
    collector's ``hunter:processed:{group}`` guard and the ``ingestion_gaps``
    de-duplication behave identically for both.
    """
    from hunter_core.events.outbox import event_id_for
    from hunter_core.events.streams import Streams

    module = _load_module()
    target = module.Target(market_id=MARKET, symbol="BTCUSDT")
    chunk = module.chunks_for(target, *module.window_for(NOW, 7))[0]

    assert module.envelope_for(chunk, "binance").event_id == event_id_for(
        Streams.MARKET_BACKFILL_REQUESTED, MARKET, chunk.gap_start, chunk.gap_end
    )


# ---- --kind funding (T3.7c) -------------------------------------------------


def test_the_funding_window_has_no_bar_or_settled_grace() -> None:
    """Unlike ``window_for`` (candles), funding has no per-minute anchor bar
    and no settled-grace clamp -- the collector's own ``normalize_window``
    clamps the tail when the request is actually served."""
    module = _load_module()

    start, end = module.funding_window_for(NOW, 31)

    assert end == NOW.replace(second=0, microsecond=0)
    assert end - start == timedelta(days=31)


def test_a_funding_window_wider_than_the_ceiling_is_clamped_to_its_recent_end() -> None:
    module = _load_module()
    import backfill_funding

    start, end = module.funding_window_for(NOW, 400)

    assert end - start == timedelta(days=backfill_funding.MAX_REQUEST_DAYS)


def test_one_funding_request_is_published_per_market_not_per_seven_days() -> None:
    module = _load_module()
    start, end = module.funding_window_for(NOW, 31)
    targets = [
        module.Target(market_id=MARKET, symbol="BTCUSDT"),
        module.Target(market_id=UUID("22222222-2222-7222-8222-222222222222"), symbol="ETHUSDT"),
    ]
    chunks = [module.Chunk(target=t, gap_start=start, gap_end=end) for t in targets]

    envelopes = module.funding_envelopes_for(chunks, "binance", producer="test")

    assert len(envelopes) == 2
    assert {e.payload["symbol"] for e in envelopes} == {"BTCUSDT", "ETHUSDT"}
    assert all(e.payload["kind"] == "funding" for e in envelopes)
    assert all("timeframe" not in e.payload for e in envelopes)


def test_a_funding_requests_identity_never_collides_with_a_candles_request() -> None:
    """Same market, same nominal window: the literal ``"funding"`` folded into
    the funding event's id keeps the two kinds from ever sharing an identity,
    which would let ``ON CONFLICT (event_id) DO NOTHING`` silently drop one."""
    module = _load_module()
    target = module.Target(market_id=MARKET, symbol="BTCUSDT")
    start, end = module.funding_window_for(NOW, 31)
    candle_chunk = module.Chunk(target=target, gap_start=start, gap_end=end)
    funding_chunk = module.Chunk(target=target, gap_start=start, gap_end=end)

    candles_envelope = module.envelope_for(candle_chunk, "binance")
    (funding_envelope,) = module.funding_envelopes_for([funding_chunk], "binance", producer="test")

    assert candles_envelope.event_id != funding_envelope.event_id


def test_a_rerun_of_the_same_funding_window_is_one_gap() -> None:
    module = _load_module()
    target = module.Target(market_id=MARKET, symbol="BTCUSDT")
    start, end = module.funding_window_for(NOW, 31)
    chunk = module.Chunk(target=target, gap_start=start, gap_end=end)

    first = module.funding_envelopes_for([chunk], "binance", producer="test")[0]
    again = module.funding_envelopes_for([chunk], "binance", producer="test")[0]

    assert first.event_id == again.event_id
