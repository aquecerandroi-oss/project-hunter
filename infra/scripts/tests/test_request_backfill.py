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
