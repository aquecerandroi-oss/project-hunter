"""``session_orb_v1`` — brief T3.33c, EXP-0010.

Every expected number here is exact and written by hand, and the series is built
so that the Wilder recursion has nothing to smooth: **every** bar before the
breakout has ``true_range = 1`` (a flat bar of half-range 0.5 whose previous
close sits in the middle), so the ATR is exactly ``1`` — seed included — and the
breakout bar is chosen with ``TR = 1`` as well (it opens and bottoms at 100 and
closes at 101), so the last smoothing step lands on ``1`` again.

The clock is the subject of this version, so the series is anchored on a real
UTC wall clock instead of the shared ``ORIGIN``: the reference bar closes at
**2026-01-02 14:15Z**, five 15-minute bars after the declared ``us`` open of
13:00Z. The 97-bar window (``rvol_window + 1``) reaches back to 2026-01-01
14:00Z, which is 1455 minutes — the whole budget of §8 of the brief.

Geometry, by hand: ``range_high = 100.5``, ``range_low = 99.5`` (the four bars of
13:00-14:00), ``close = 101``, ``risk = 1.5``, ``range_risk_atr = 1.5``,
``stop = 99.5``, ``target1 = 101 + 2 x 1.5 = 104``, ``target2 = 107``.

Run: ``uv run pytest packages/core/tests/unit/strategies/test_session_orb_v1.py -q``
"""

from __future__ import annotations

import ast
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import hunter_core.strategies.session_orb_v1 as session_module
from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import (
    Decision,
    EvaluationState,
    StrategyContext,
    build_context,
)
from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.session_orb_v1 import (
    SESSION_ORB_V1,
    _session_open,  # pyright: ignore[reportPrivateUsage]  # the brief names it
)

from .conftest import EXCHANGE, SYMBOL, BarSpec, D, flat, series

pytestmark = pytest.mark.unit

PARAMS: Mapping[str, Any] = SESSION_ORB_V1.default_parameters

PREVIOUS = 96
"""``rvol_window`` bars before the breakout bar — the longest lookback."""
RANGE_BARS = 4
CUT = datetime(2026, 1, 2, 14, 15, tzinfo=UTC)
"""Close of the reference bar: five bars after the declared ``us`` open."""
SESSION_OPEN = datetime(2026, 1, 2, 13, 0, tzinfo=UTC)
BARS_SINCE_OPEN = 5
ORIGIN = CUT - timedelta(minutes=15 * (PREVIOUS + 1))  # 2026-01-01 14:00Z

BASE_CLOSE = D("100")
HALF = D("0.5")
"""Half-range of every bar of the series: ``TR = 1`` with a flat previous close."""
ATR = D("1")
RANGE_HIGH = D("100.75")
RANGE_LOW = D("99.75")
"""The opening range is deliberately **not** the range of the other bars (100.5 /
99.5): a rule that read "the last four bars" instead of "the four bars of the
session" would land on those, and the anchoring test below would not exist."""
REFERENCE = D("101")
RISK = D("1.25")
RANGE_RISK_ATR = D("1.25")
TARGET1 = D("103.5")
TARGET2 = D("106")
CUT_LATE = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
"""Eight bars after the open: here the opening range and "the last four bars"
are different bars, and only one of the two answers is the contract."""
BASE_VOLUME = D("100")
SIGNAL_VOLUME = D("150")
SIGNAL_RISE = D("1")
"""The breakout bar closes one point above the base, so its own true range is 1
too and the ATR stays exactly 1 through the last smoothing step."""


def orb_range_bar(base_close: Decimal = BASE_CLOSE, volume: Decimal = BASE_VOLUME) -> BarSpec:
    """One bar of the opening range: ``TR = 1`` against a previous close of
    ``base_close`` (``high - low`` dominates), and it opens and closes there, so
    it prints a range of ``+0.75 / -0.25`` without moving the ATR."""
    return BarSpec(base_close, base_close + D("0.75"), base_close - D("0.25"), base_close, volume)


def orb_bar(
    base_close: Decimal = BASE_CLOSE,
    rise: Decimal = SIGNAL_RISE,
    volume: Decimal = SIGNAL_VOLUME,
) -> BarSpec:
    """Opens and bottoms at the base close, closes ``rise`` above it (``TR = rise``)."""
    return BarSpec(base_close, base_close + rise, base_close, base_close + rise, volume)


def build_series(
    *,
    signal: BarSpec | None = None,
    base_close: Decimal = BASE_CLOSE,
    half: Decimal = HALF,
    opening_half: Decimal | None = None,
    volume: Decimal = BASE_VOLUME,
    previous: int = PREVIOUS,
    cut: datetime = CUT,
) -> list[NormalizedCandle]:
    """``previous`` flat bars plus the breakout bar, ending exactly at ``cut``.

    The four bars of the opening range are placed **from the session open**, not
    from the end of the series, so moving ``cut`` moves the rest of the session
    and not the range. ``opening_half`` replaces them with a symmetric flat bar
    (``0`` degenerates the range, ``0.05`` makes it narrower than 1 ATR), which
    is how the availability and ``range_geometry`` branches are reached without
    touching the rest of the ATR history.
    """
    specs = [flat(base_close, half, volume) for _ in range(previous)]
    first = previous + 1 - int((cut - SESSION_OPEN) // timedelta(minutes=15))
    for index in range(first, first + RANGE_BARS):
        specs[index] = (
            orb_range_bar(base_close, volume)
            if opening_half is None
            else flat(base_close, opening_half, volume)
        )
    specs.append(signal if signal is not None else orb_bar(base_close))
    origin = cut - timedelta(minutes=15 * (previous + 1))
    return series(specs, timeframe=Timeframe.M15, origin=origin)


def context(**kwargs: object) -> StrategyContext:
    candles = kwargs.pop("candles", None) or build_series()
    cut = kwargs.pop("cut", None) or CUT
    return build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=cut, **kwargs)  # pyright: ignore[reportArgumentType]


def variant(**overrides: object) -> Mapping[str, Any]:
    return {**PARAMS, **overrides}


# --------------------------------------------------------------------------- 1. it fires


def test_it_signals_on_the_break_of_the_opening_range() -> None:
    decision = SESSION_ORB_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.direction is TradeDirection.LONG
    assert decision.reference_price == REFERENCE
    assert decision.stop == RANGE_LOW
    assert decision.target1 == TARGET1
    assert decision.targets_informational == (TARGET2,)
    assert decision.horizon_s == 14400
    assert decision.confidence == D("0.5")


def test_the_stop_is_the_structure_and_the_target_is_two_r_of_it() -> None:
    """The stop is a datum (the low of the opening range), so the target has to
    be in R: 2 R nominal at the reference, never 2 ATR."""
    decision = SESSION_ORB_V1.evaluate(context(), PARAMS)

    assert decision is not None
    risk = decision.reference_price - decision.stop
    assert risk == RISK
    assert decision.stop == RANGE_LOW
    assert decision.target1 - decision.reference_price == 2 * risk
    assert decision.targets_informational[0] - decision.reference_price == 4 * risk


def test_the_range_is_the_one_of_the_session_open_not_the_last_four_bars() -> None:
    """Eight bars after the open: the four bars of the opening range (13:00-14:00,
    range ``100.75 / 99.75``) are no longer the four bars before the breakout
    (range ``100.5 / 99.5``). A rule anchored on the end of the window would stop
    at 99.5 and risk 1.5; this one stops at 99.75 and risks 1.25."""
    decision = SESSION_ORB_V1.evaluate(
        context(candles=build_series(cut=CUT_LATE), cut=CUT_LATE), PARAMS
    )

    assert decision is not None
    values = {feature.name: feature.value for feature in decision.supporting_features.features}
    assert values["bars_since_open"] == 8
    assert values["range_high"] == RANGE_HIGH
    assert values["range_low"] == RANGE_LOW
    assert decision.stop == RANGE_LOW == D("99.75")
    assert decision.reference_price - decision.stop == RISK


def test_there_is_no_invalidation_because_the_structure_is_the_stop() -> None:
    """A ``close_below`` rule would sit either above the stop (a second, tighter
    stop nobody declared) or below it (dead code). Design decision, not evidence
    that removing an invalidation helps (KB-0006)."""
    decision = SESSION_ORB_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.invalidations == ()


def test_the_envelope_carries_every_number_the_decision_used() -> None:
    decision = SESSION_ORB_V1.evaluate(context(), PARAMS)

    assert decision is not None
    envelope = decision.supporting_features
    assert envelope.observation_ts == CUT
    assert envelope.strategy_key == "session_orb_v1"
    assert envelope.strategy_version == "v1"
    assert envelope.timeframe == "15m"
    values = {feature.name: feature.value for feature in envelope.features}
    assert values["session"] == "us"
    assert values["session_model"] == "declared_utc_sessions_v1"
    assert values["bars_since_open"] == BARS_SINCE_OPEN
    assert values["range_high"] == RANGE_HIGH
    assert values["range_low"] == RANGE_LOW
    assert values["range_risk_atr"] == RANGE_RISK_ATR
    assert values["open_15m"] == BASE_CLOSE
    assert values["high_15m"] == REFERENCE
    assert values["low_15m"] == BASE_CLOSE
    assert values["volume_15m"] == SIGNAL_VOLUME
    assert values["close_15m"] == REFERENCE
    assert values["relative_volume_15m"] == D("1.5")
    assert values["volume_median_15m"] == BASE_VOLUME
    assert values["atr_pct_15m"] == ATR / REFERENCE
    stamps = {feature.name: feature.source_ts for feature in envelope.features}
    assert stamps["session_open"] == SESSION_OPEN
    assert stamps["close_15m"] == CUT
    assert stamps["open_15m"] == CUT - timedelta(minutes=15)
    windows = {feature.name: feature.window for feature in envelope.features}
    assert windows["range_high"] == windows["range_low"] == RANGE_BARS
    assert windows["relative_volume_15m"] == 96
    assert windows["atr_pct_15m"] == 97
    assert envelope.atr is not None
    assert envelope.atr.value == ATR
    assert envelope.atr.seed == ATR
    assert envelope.atr.period == 14
    assert envelope.atr.method == "wilder_v1"
    assert envelope.atr.origin == "rolling_window_v1"
    assert envelope.atr.timeframe == "15m"
    assert envelope.atr.bars_used == 97
    assert envelope.atr.window_start == ORIGIN
    assert envelope.atr.window_end == CUT
    assert envelope.atr.seed_anchor == ORIGIN + timedelta(minutes=15 * 14)
    assert envelope.assumed_costs == AssumedCosts(
        spread_bps=D("2"), slippage_bps=D("5"), fee_bps=D("4"), max_entry_delay_s=120
    )
    assert envelope.confidence_method == "constant_uncalibrated_v1"
    assert envelope.purpose == "research_only"


def test_the_reason_names_the_session_and_is_deterministic() -> None:
    first = SESSION_ORB_V1.explain(context(), PARAMS)
    second = SESSION_ORB_V1.explain(context(), PARAMS)

    assert first.state is EvaluationState.TRIGGERED
    assert first.reason == "signal"
    assert first.decision is not None and second.decision is not None
    assert first.decision.reason == second.decision.reason
    assert first.decision.reason == (
        "Session ORB 15m: sessão us (abertura 13:00Z), fechamento 101 acima da máxima "
        "100.75 da faixa das 4 primeiras barras, 5 barras após a abertura; "
        "stop na mínima da faixa (99.75), risco 1.25 ATR, volume relativo 1.50x "
        "da mediana de 96 barras, ATR% 0.99%"
    )


# ------------------------------------------------------- 2. the session boundary table


@pytest.mark.parametrize(
    ("hour", "minute", "session", "open_hour"),
    [
        (0, 0, "asia", 0),
        (6, 45, "asia", 0),
        (7, 0, "europe", 7),
        (12, 45, "europe", 7),
        (13, 0, "us", 13),
        (23, 45, "us", 13),
    ],
)
def test_the_session_of_a_cut_is_the_latest_open_at_or_before_it(
    hour: int, minute: int, session: str, open_hour: int
) -> None:
    """The 00:00 case is in the table on purpose: the asia open is also the day
    boundary, so the bar that closes at midnight belongs to the **new** day's
    asia session with zero bars since the open."""
    cut = datetime(2026, 1, 2, hour, minute, tzinfo=UTC)

    resolved = _session_open(cut, (0, 7, 13))

    assert resolved == (session, datetime(2026, 1, 2, open_hour, 0, tzinfo=UTC))


def test_a_day_whose_first_session_opens_later_is_uncovered_and_says_so() -> None:
    """Not reachable with the frozen defaults (asia opens at 00:00), and declared
    rather than assumed away: it is a state of the convention, not an error."""
    cut = datetime(2026, 1, 2, 2, 0, tzinfo=UTC)

    assert _session_open(cut, (5, 7, 13)) is None

    evaluation = SESSION_ORB_V1.explain(context(cut=cut), variant(session_asia_open_h=5))
    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "no_session_open"


# --------------------------------------------------------------------------- 3. not triggered


@pytest.mark.parametrize(
    ("cut", "bars_since_open"),
    [(datetime(2026, 1, 2, 13, 45, tzinfo=UTC), 3), (datetime(2026, 1, 2, 14, 0, tzinfo=UTC), 4)],
    ids=["three_bars_in", "exactly_range_bars"],
)
def test_a_cut_inside_the_opening_range_is_not_a_signal(
    cut: datetime, bars_since_open: int
) -> None:
    """``bars_since_open <= range_bars``: the range is still being printed. It is
    NOT_TRIGGERED — an observably false condition — so the market may re-arm."""
    evaluation = SESSION_ORB_V1.explain(context(cut=cut), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "inside_opening_range"
    assert evaluation.detail == {
        "session": "us",
        "session_open": "2026-01-02T13:00:00Z",
        "bars_since_open": str(bars_since_open),
    }


def test_a_break_five_hours_after_the_open_is_outside_the_session_window() -> None:
    cut = datetime(2026, 1, 2, 18, 15, tzinfo=UTC)  # 21 bars after 13:00Z

    evaluation = SESSION_ORB_V1.explain(context(cut=cut), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == "outside_session_window"
    assert evaluation.detail["bars_since_open"] == "21"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"signal": orb_bar(rise=D("0.3"))}, "no_range_break"),
        ({"signal": orb_bar(volume=D("100"))}, "rvol_low"),
        ({"base_close": D("1000")}, "atr_out_of_range"),
        ({"base_close": D("15")}, "atr_out_of_range"),
    ],
    ids=["no_range_break", "rvol_low", "atr_too_low", "atr_too_high"],
)
def test_the_branches_that_do_not_trigger(kwargs: dict[str, Any], reason: str) -> None:
    evaluation = SESSION_ORB_V1.explain(context(candles=build_series(**kwargs)), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == reason
    assert evaluation.decision is None


def test_no_range_break_reports_the_level_it_had_to_clear() -> None:
    evaluation = SESSION_ORB_V1.explain(
        context(candles=build_series(signal=orb_bar(rise=D("0.3")))), PARAMS
    )

    assert evaluation.detail == {"close_15m": "100.3", "range_high": "100.75"}


def test_a_close_exactly_at_the_range_high_is_not_a_break() -> None:
    """``close > range_high``, strictly: touching the level is not clearing it."""
    evaluation = SESSION_ORB_V1.explain(
        context(candles=build_series(signal=orb_bar(rise=D("0.75")))), PARAMS
    )

    assert evaluation.reason == "no_range_break"
    assert evaluation.detail == {"close_15m": "100.75", "range_high": "100.75"}


def test_relative_volume_exactly_at_the_floor_still_fires() -> None:
    """``rvol_min`` is inclusive: 1.3 belongs to the triggered side."""
    at_the_floor = build_series(signal=orb_bar(volume=D("130")))
    just_below = build_series(signal=orb_bar(volume=D("129.9")))

    assert SESSION_ORB_V1.explain(context(candles=at_the_floor), PARAMS).state is (
        EvaluationState.TRIGGERED
    )
    assert SESSION_ORB_V1.explain(context(candles=just_below), PARAMS).reason == "rvol_low"


def test_an_ineligible_market_is_never_evaluated() -> None:
    evaluation = SESSION_ORB_V1.explain(
        context(eligible=False, eligibility_reason="not_monitored"), PARAMS
    )

    assert evaluation.state is EvaluationState.INELIGIBLE
    assert evaluation.reason == "ineligible"
    assert evaluation.detail == {"eligibility_reason": "not_monitored"}


# --------------------------------------------------------------------------- 4. unavailable


def test_a_short_history_is_warmup_not_a_false_condition() -> None:
    """41 bars against a 97-bar window: the history does not reach back far
    enough, which is warm-up — a hole *inside* a reachable window is a gap."""
    evaluation = SESSION_ORB_V1.explain(context(candles=build_series(previous=40)), PARAMS)

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "warmup"


def test_one_missing_minute_in_the_middle_makes_the_window_a_gap() -> None:
    candles = build_series()
    missing = candles[len(candles) // 2].open_time
    holed = [candle for candle in candles if candle.open_time != missing]

    evaluation = SESSION_ORB_V1.explain(context(candles=holed), PARAMS)

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "gap"
    assert evaluation.detail["missing_minute"] == missing.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("atr_bars", [200, 15], ids=["window_too_long", "indicator_warmup"])
def test_the_atr_reports_its_own_warmup(atr_bars: int) -> None:
    """Two different holes with one name: the ATR window does not reach back far
    enough, or it does and Wilder has not released a reading yet."""
    evaluation = SESSION_ORB_V1.explain(context(), variant(atr_bars=atr_bars))

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "atr_warmup"


def test_an_opening_range_with_no_width_is_not_a_range() -> None:
    """Four bars that printed a single price: ``range_high == range_low`` would
    make ``range_risk_atr`` a measure of nothing."""
    flat_open = build_series(opening_half=D("0"))

    evaluation = SESSION_ORB_V1.explain(context(candles=flat_open), PARAMS)

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "degenerate_range"
    assert evaluation.detail["session"] == "us"


def test_a_baseline_without_volume_makes_relative_volume_unavailable() -> None:
    evaluation = SESSION_ORB_V1.explain(
        context(candles=build_series(volume=D("0"), signal=orb_bar(volume=D("0")))), PARAMS
    )

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "rvol_unavailable"
    assert evaluation.detail == {"rvol_window": "96"}


# --------------------------------------------------------------------------- 5. rejected


def test_a_range_narrower_than_one_atr_is_refused_not_ignored() -> None:
    """The break happened and the decision was refused: REJECTED, never
    NOT_TRIGGERED, so the market cannot re-arm on it. Below 1 ATR of risk the
    20 bps of assumed cost eat the trade before the market has an opinion
    (75 % break-even at a 0.4 ATR range — notes-T3.33 §4)."""
    narrow = build_series(opening_half=D("0.05"), signal=orb_bar(rise=D("0.1")))

    evaluation = SESSION_ORB_V1.explain(context(candles=narrow), PARAMS)

    assert evaluation.state is EvaluationState.REJECTED
    assert evaluation.reason == "range_geometry"
    assert evaluation.detail["range_low"] == "99.95"
    assert evaluation.detail["close_15m"] == "100.1"
    assert Decimal(evaluation.detail["range_risk_atr"]) < D("1")


def test_a_range_wider_than_the_ceiling_is_refused_too() -> None:
    """``TR = 15`` on the breakout bar: the ATR lands on exactly 2, the risk is
    ``115 - 99.75 = 15.25`` and the ratio is exactly 7.625, far above 2.5."""
    wide = build_series(signal=orb_bar(rise=D("15")))

    evaluation = SESSION_ORB_V1.explain(context(candles=wide), PARAMS)

    assert evaluation.state is EvaluationState.REJECTED
    assert evaluation.reason == "range_geometry"
    assert evaluation.detail["range_risk_atr"] == "7.625"


def test_a_geometry_that_does_not_close_is_rejected() -> None:
    evaluation = SESSION_ORB_V1.explain(context(), variant(target_r=D("0")))

    assert evaluation.state is EvaluationState.REJECTED
    assert evaluation.reason == "geometry"
    assert evaluation.decision is None
    assert evaluation.detail == {
        "stop": "99.75",
        "reference_price": "101",
        "target1": "101",
    }


def test_the_range_guard_is_checked_before_the_geometry() -> None:
    """Both guards fail on the same bar; the order of reasons is the contract."""
    wide = build_series(signal=orb_bar(rise=D("15")))

    evaluation = SESSION_ORB_V1.explain(context(candles=wide), variant(target_r=D("0")))

    assert evaluation.reason == "range_geometry"


# ------------------------------------------------------------- 6/7. purity and the clock


def test_evaluate_is_a_pure_function_of_the_context() -> None:
    ctx = context()

    assert SESSION_ORB_V1.evaluate(ctx, PARAMS) == SESSION_ORB_V1.evaluate(ctx, PARAMS)
    assert SESSION_ORB_V1.evaluate(ctx, PARAMS) == SESSION_ORB_V1.evaluate(context(), PARAMS)


class _PoisonedClock:
    """Anything a clock could be asked for, refused by name."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"session_orb_v1 read the clock: datetime.{name}")


def test_moving_the_system_clock_a_day_forward_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The session comes from ``ctx.source_bar_close``, never from the process.
    The module's own ``datetime`` symbol is replaced by an object that raises on
    every attribute, so a future ``datetime.now()`` in this module fails here."""
    ctx = context()
    baseline = SESSION_ORB_V1.evaluate(ctx, PARAMS)

    shifted = time.time() + 86400
    monkeypatch.setattr(time, "time", lambda: shifted)
    monkeypatch.setattr(session_module, "datetime", _PoisonedClock())

    assert baseline is not None
    assert SESSION_ORB_V1.evaluate(ctx, PARAMS) == baseline
    assert SESSION_ORB_V1.evaluate(context(), PARAMS) == baseline


def _module_tree() -> ast.Module:
    return ast.parse(Path(session_module.__file__).read_text(encoding="utf-8"))


def test_the_module_imports_no_clock_and_no_io() -> None:
    imported: set[str] = set()
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    assert imported == {
        "__future__",
        "collections.abc",
        "datetime",
        "decimal",
        "typing",
        "hunter_core.domain.enums",
        "hunter_core.domain.market",
        "hunter_core.strategies.aggregate",
        "hunter_core.strategies.base",
        "hunter_core.strategies.envelope",
        "hunter_core.strategies.indicators",
        "hunter_core.strategies.numeric",
        "hunter_core.strategies.schema",
    }


def test_the_module_calls_nothing_that_reads_a_clock_or_the_world() -> None:
    """An AST scan, not a substring scan: the docstring is allowed to *name*
    ``datetime.now`` while the code may never call it."""
    called: set[str] = set()
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Attribute):
            called.add(target.attr)
        elif isinstance(target, ast.Name):
            called.add(target.id)

    assert called.isdisjoint(
        {"now", "utcnow", "today", "time", "monotonic", "open", "eval", "exec", "input"}
    )


# --------------------------------------------------------------------------- 8. bootstrap


def test_bootstrap_equals_continuous_execution() -> None:
    """The worker bootstraps from Postgres with one window and then grows the
    context bar by bar; both paths must agree on the reference close, and no
    earlier bar of this series may fire."""
    candles = build_series()
    bootstrap = SESSION_ORB_V1.evaluate(context(candles=candles), PARAMS)

    grown: list[NormalizedCandle] = []
    decisions: list[Decision | None] = []
    for index in range(PREVIOUS + 1):
        grown.extend(candles[index * 15 : (index + 1) * 15])
        cut = ORIGIN + timedelta(minutes=15 * (index + 1))
        decisions.append(SESSION_ORB_V1.evaluate(context(candles=list(grown), cut=cut), PARAMS))

    assert bootstrap is not None
    assert decisions[-1] == bootstrap
    assert [decision for decision in decisions[:-1] if decision is not None] == []


# --------------------------------------------------------------- 9. digest isolation


def test_the_live_versions_digests_did_not_move() -> None:
    """Brief §2: adding this module cannot re-freeze the versions already
    activated on the VPS — including the ``paper`` line."""
    from hunter_strategy_worker.code_ref import version_code_ref

    assert version_code_ref("momentum_v1") == (
        "hunter_core.strategies.momentum_v1@sha256:"
        "ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"
    )
    assert version_code_ref("volume_anomaly_v1") == (
        "hunter_core.strategies.volume_anomaly_v1@sha256:"
        "9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22"
    )


def test_this_version_closes_over_the_siblings_it_imports_and_no_others() -> None:
    from hunter_strategy_worker.code_ref import module_closure

    closure = module_closure("session_orb_v1")

    assert "constraints" not in closure
    assert "momentum_v1" not in closure and "volume_anomaly_v1" not in closure
    assert "breakout_v1" not in closure and "mean_reversion_v1" not in closure
    assert {"aggregate", "base", "indicators", "numeric", "schema"} <= set(closure)


# ----------------------------------------------------- 11. window and cost budgets


def test_the_longest_window_fits_the_shadow_context() -> None:
    """``SHADOW_CONTEXT_MINUTES = 1560`` is a worker-wide knob shared by every
    version; a version that needed more would cost coverage for all of them."""
    signal_bars = max(PARAMS["session_window_bars"], PARAMS["rvol_window"] + 1)
    session_span = (PARAMS["session_window_bars"] + 1) * 15
    atr_minutes = PARAMS["atr_bars"] * 15

    assert signal_bars == 97
    assert signal_bars * 15 == 1455
    assert atr_minutes == 1455
    assert session_span == 315
    assert max(signal_bars * 15, atr_minutes, session_span) <= 1560
    # non-overlap of the three declared sessions, and the budget above
    assert PARAMS["session_window_bars"] <= 24
    assert PARAMS["range_bars"] < PARAMS["session_window_bars"]


def test_the_toll_of_this_geometry_has_a_declared_ceiling() -> None:
    """T3.32 / KB-0076: ``custo_R x risco%`` is arithmetic, not statistics —
    20 bps round trip divided by the distance to the stop. The floors frozen here
    (``range_risk_atr_min = 1`` and ``atr_pct_min = 0.006``) cap the toll at
    1/3 R, against the 0.6152 R measured on the ``volume_anomaly v2`` replay."""
    round_trip = (
        PARAMS["assumed_spread_bps"] + 2 * PARAMS["slippage_bps"] + 2 * PARAMS["fee_bps"]
    ) / D("10000")
    worst_risk_pct = PARAMS["range_risk_atr_min"] * PARAMS["atr_pct_min"]

    assert round_trip == D("0.002")
    assert worst_risk_pct == D("0.006")
    assert round_trip / worst_risk_pct <= D("0.3334")


def test_the_widest_stop_this_version_can_take_is_under_the_review_ceiling() -> None:
    """C5 of the review gate wants ``stop_loss_pct <= 0.15``; here the stop is a
    datum, so the ceiling is the product of the two frozen maxima."""
    assert PARAMS["atr_pct_max"] * PARAMS["range_risk_atr_max"] == D("0.125")


def test_the_declared_identity_is_the_registry_key() -> None:
    assert SESSION_ORB_V1.key == "session_orb_v1"
    assert SESSION_ORB_V1.version == "v1"
    assert SESSION_ORB_V1.timeframe is Timeframe.M15
    assert set(PARAMS) == set(SESSION_ORB_V1.parameters_schema["required"])
