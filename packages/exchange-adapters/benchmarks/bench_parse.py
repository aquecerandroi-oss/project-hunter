"""Micro-benchmark for ``hunter_exchanges.binance.streams.parse_stream_message``.

T1.6b-A: not a pytest test (no ``test_`` prefix, so it is never collected —
``pyproject.toml``'s ``testpaths`` includes ``packages`` but pytest only
matches ``test_*.py``/``*_test.py``). Run directly:

    uv run python packages/exchange-adapters/benchmarks/bench_parse.py

Replays the real recorded WS fixtures N times per channel through
``parse_stream_message`` (the same dispatcher ``ws.py::_handle_raw_message``
calls per frame) and reports events/s and microseconds/event — the "before"
and "after" numbers the T1.6b-A brief requires as a deliverable, run once
against stashed ``HEAD`` and once against the change.

``print``, not ``structlog``, is deliberate here: this is a throwaway CLI
tool, not library code (CLAUDE.md's "no print in library code" scopes to
``hunter_*`` packages' importable modules) — every call is `# noqa: T201`.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from hunter_exchanges.binance import streams

FIXTURES = (Path(__file__).parents[1] / "hunter_exchanges" / "testing" / "fixtures").resolve()

LAST_PRICE = Decimal("79500")


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# (label, stream name, fixture file, iteration count)
_CASES: list[tuple[str, str, str, int]] = [
    ("aggTrade", "btcusdt@aggTrade", "ws_agg_trade.json", 200_000),
    ("bookTicker", "btcusdt@bookTicker", "ws_book_ticker.json", 200_000),
    # Bare "depth20" (no cadence suffix) on purpose: it resolves to
    # StreamChannel.BOOK on both the pre-A5 and post-A5 code (A5 only changes
    # which cadence *stream_name()* builds for a live subscription, not what
    # channel_for_stream_name() accepts on the read side) — so this same
    # benchmark script is valid unmodified for the "before" and "after" runs.
    ("depth20", "btcusdt@depth20", "ws_depth20.json", 20_000),
    ("kline_1m", "btcusdt@kline_1m", "ws_kline_1m.json", 50_000),
    ("markPrice", "btcusdt@markPrice@1s", "ws_mark_price.json", 50_000),
    ("forceOrder", "btcusdt@forceOrder", "ws_force_order.json", 50_000),
]

#: Roughly proportional to real per-symbol traffic (T1.6b profile: bookTicker
#: and aggTrade dominate, depth20 is now half as frequent at 500ms cadence,
#: kline/markPrice/forceOrder are comparatively rare) — one "tick" of the mix
#: below is replayed ``_MIX_REPEATS`` times for a stable combined number.
_MIX_WEIGHTS: dict[str, int] = {
    "aggTrade": 10,
    "bookTicker": 10,
    "depth20": 2,
    "kline_1m": 1,
    "markPrice": 1,
    "forceOrder": 1,
}
_MIX_REPEATS = 20_000


def _run_channel(label: str, stream_name: str, fixture: str, n: int) -> tuple[float, float]:
    raw = _load(fixture)
    channel = streams.channel_for_stream_name(stream_name)
    assert channel is not None, f"{stream_name!r} did not resolve to a channel"
    start = time.perf_counter()
    for _ in range(n):
        streams.parse_stream_message(stream_name, raw, last_price=LAST_PRICE)
    elapsed = time.perf_counter() - start
    events_per_s = n / elapsed
    us_per_event = elapsed * 1_000_000 / n
    print(  # noqa: T201
        f"{label:>12}  {n:>8} iters  {elapsed:8.4f}s  {events_per_s:14,.0f} events/s  "
        f"{us_per_event:8.3f} us/event"
    )
    return events_per_s, us_per_event


def _run_mix() -> None:
    loaded = {label: (_load(fixture), stream_name) for label, stream_name, fixture, _ in _CASES}
    sequence: list[tuple[str, dict[str, Any]]] = []
    for label, weight in _MIX_WEIGHTS.items():
        raw, stream_name = loaded[label]
        sequence.extend([(stream_name, raw)] * weight)
    total = len(sequence) * _MIX_REPEATS
    start = time.perf_counter()
    for _ in range(_MIX_REPEATS):
        for stream_name, raw in sequence:
            streams.parse_stream_message(stream_name, raw, last_price=LAST_PRICE)
    elapsed = time.perf_counter() - start
    events_per_s = total / elapsed
    us_per_event = elapsed * 1_000_000 / total
    print("-" * 80)  # noqa: T201
    print(  # noqa: T201
        f"{'mix':>12}  {total:>8} iters  {elapsed:8.4f}s  {events_per_s:14,.0f} events/s  "
        f"{us_per_event:8.3f} us/event  (weights={_MIX_WEIGHTS})"
    )


def main() -> None:
    print(  # noqa: T201
        f"{'channel':>12}  {'iters':>8}         {'wall':>8}  {'throughput':>14}  {'latency':>8}"
    )
    for label, stream_name, fixture, n in _CASES:
        _run_channel(label, stream_name, fixture, n)
    _run_mix()


if __name__ == "__main__":
    main()
