"""The eight arms over labelled synthetic series, with the real walker.

Every scenario is a hand-built 1-minute series with known expected exits, and
every policy gets both readings the brief asks for: a series where it **differs**
from the base and a series where it **coincides** with it.

No database and no clock: the fold is pure, so the exit rules can be pinned
exactly. The settlement (funding, ``R_net``) is exercised against Postgres in
``test_replay_reproduce.py``.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_core.domain.enums import (
    MarketStatus,
    OutcomeResult,
    ShadowTrackingState,
    Timeframe,
)
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.envelope import AssumedCosts
from hunter_indicators.replay.policies import POLICIES, policy
from hunter_strategy_worker.replay.arms import ArmNotBuildable, build_arm
from hunter_strategy_worker.replay.contrast import run_contrasts
from hunter_strategy_worker.replay.engine import ArmOutcome, fold_arm, replay_case
from hunter_strategy_worker.replay.load import ReplayCase, StoredOutcome, VersionRow
from hunter_strategy_worker.replay.reproduce import audit_case
from hunter_strategy_worker.replay.series import Series
from hunter_strategy_worker.repo import MarketRow
from hunter_strategy_worker.walker import Bar, Progress, TrackingPlan

pytestmark = pytest.mark.unit

MINUTE = timedelta(minutes=1)
HISTORY_START = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)
ENTRY = datetime(2026, 9, 5, 12, 1, tzinfo=UTC)
HORIZON = datetime(2026, 9, 5, 12, 31, tzinfo=UTC)

COSTS = AssumedCosts(
    spread_bps=Decimal("2"),
    slippage_bps=Decimal("5"),
    fee_bps=Decimal("4"),
    max_entry_delay_s=120,
)
STOP = Decimal("99")
TARGET1 = Decimal("101")
TARGET2 = Decimal("103")
TARGET3 = Decimal("104.5")
REFERENCE = Decimal("100")
ATR0 = Decimal("2")
INVALIDATION = Decimal("99.5")
"""INV-E moves it to ``99.5 - 0.25 * 2 = 99``."""


def _candle(open_time: datetime, o: str, h: str, low: str, c: str) -> NormalizedCandle:
    return NormalizedCandle(
        exchange="binance",
        symbol="TESTUSDT",
        timeframe=Timeframe.M1,
        open_time=open_time,
        close_time=open_time + MINUTE,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("10"),
        quote_volume=Decimal("1000"),
        trade_count=10,
        taker_buy_volume=Decimal("5"),
        is_final=True,
        received_at=open_time + MINUTE,
    )


def _history(close: str) -> list[NormalizedCandle]:
    """Quiet minutes from 09:00 to 12:00 — the channel's own window lives here."""
    minutes = int((ENTRY - MINUTE - HISTORY_START).total_seconds() // 60) + 1
    return [_candle(HISTORY_START + MINUTE * i, close, close, close, close) for i in range(minutes)]


def _flat(open_time: datetime, price: str) -> NormalizedCandle:
    return _candle(open_time, price, price, price, price)


def _series(history_close: str, window: list[NormalizedCandle]) -> Series:
    candles = [*_history(history_close), *window]
    bars = tuple(
        Bar(open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close)
        for c in window
    )
    return Series(candles=tuple(candles), bars=bars, truncated=None)


def _window(prices: dict[int, tuple[str, str, str, str]], default: str) -> list[NormalizedCandle]:
    """The 31 minutes 12:01..12:31; ``prices`` overrides individual minutes."""
    out: list[NormalizedCandle] = []
    minute = ENTRY
    index = 0
    while minute <= HORIZON:
        override = prices.get(index)
        if override is None:
            out.append(_flat(minute, default))
        else:
            out.append(_candle(minute, *override))
        minute += MINUTE
        index += 1
    return out


def _case(stored_state: ShadowTrackingState = ShadowTrackingState.TERMINAL) -> ReplayCase:
    plan = TrackingPlan(
        entry_bar_open=ENTRY,
        stop=STOP,
        target1=TARGET1,
        horizon_s=1800,
        costs=COSTS,
        reference_price=REFERENCE,
        invalidation_level=INVALIDATION,
        invalidation_timeframe=Timeframe.M15,
    )
    return ReplayCase(
        signal_id=uuid.UUID(int=1),
        version=VersionRow(
            id=uuid.UUID(int=2),
            strategy_key="momentum",
            version="v1",
            params_hash="hash",
            params_format=1,
            code_ref="ref",
            activated_at=None,
        ),
        market=MarketRow(
            id=uuid.UUID(int=3),
            symbol="TESTUSDT",
            exchange="binance",
            is_monitored=True,
            status=MarketStatus.ACTIVE,
        ),
        source_bar_close=ENTRY - MINUTE,
        plan=plan,
        targets=(TARGET1, TARGET2, TARGET3),
        atr0=ATR0,
        stored=StoredOutcome(
            tracking_state=stored_state,
            result=OutcomeResult.OPEN,
            virtual_entry=None,
            entry_ts=None,
            exit_price=None,
            exit_ts=None,
            r_multiple=None,
            r_ex_funding=None,
            funding_reason=None,
            no_entry_reason=("geometry" if stored_state is ShadowTrackingState.NO_ENTRY else None),
            progress=Progress.start(),
        ),
    )


# --- the four labelled series -------------------------------------------------

INVALIDATION_SERIES = _series(
    "100",
    _window(
        {
            0: ("100", "100.1", "99.9", "100"),  # 12:01 entry bar
            13: ("99.6", "99.6", "99.35", "99.4"),  # 12:14 closes the 12:15 bar below 99.5
            14: ("99.45", "99.6", "99.4", "99.5"),  # 12:15 open pays a pending invalidation
            18: ("100.5", "101.2", "100.4", "101"),  # 12:19 touches target1
        },
        "100.2",
    ),
)
"""Base invalidates at 12:15; the arms that keep going reach target1 at 12:19."""

TARGET_SERIES = _series(
    "100",
    _window({9: ("100.6", "101.2", "100.5", "101")}, "100.6"),
)
"""Target1 is touched at 12:10; nothing else ever triggers."""

CHANNEL_SERIES = _series(
    "100",
    _window({13: ("99.95", "100", "99.9", "99.9")}, "100.05"),
)
"""The 15m close at 12:15 (99.9) is below the ten previous 15m closes (100) and
still above the invalidation level (99.5)."""

QUIET_SERIES = _series("100", _window({}, "100"))
"""Nothing triggers at all: every policy expires at the horizon open."""


def _fold(policy_key: str, series: Series, case: ReplayCase | None = None) -> Progress:
    spec = build_arm(case or _case(), policy(policy_key))
    progress, _trigger, unavailable, _folded = fold_arm(spec, series)
    assert unavailable is None
    return progress


def _exit(progress: Progress) -> tuple[str, str, str]:
    assert progress.exit_ts is not None
    assert progress.exit_base is not None
    return progress.result.value, progress.exit_ts.isoformat(), format(progress.exit_base, "f")


# --- differs / coincides, policy by policy ------------------------------------


def test_base_invalidates_at_the_next_open_after_the_close_below() -> None:
    assert _exit(_fold("base", INVALIDATION_SERIES)) == (
        "invalidated",
        "2026-09-05T12:15:00+00:00",
        "99.45",
    )


@pytest.mark.parametrize("key", ["INV-B", "INV-C", "INV-E"])
def test_the_three_invalidation_arms_differ_from_the_base(key: str) -> None:
    """One close below the level: ``INV-B`` ignores it, ``INV-C`` needs a second
    one, ``INV-E``'s level is 0.5 lower — so all three stay in and take
    target1."""
    assert _exit(_fold(key, INVALIDATION_SERIES)) == (
        "target",
        "2026-09-05T12:20:00+00:00",
        "101",
    )


@pytest.mark.parametrize("key", ["INV-B", "INV-C", "INV-E"])
def test_the_three_invalidation_arms_coincide_with_the_base_when_nothing_breaks(
    key: str,
) -> None:
    assert _exit(_fold(key, TARGET_SERIES)) == _exit(_fold("base", TARGET_SERIES))


@pytest.mark.parametrize("key", ["TGT-3", "TGT-4.5", "EXIT-NOTGT"])
def test_the_target_arms_differ_from_the_base_when_the_base_takes_target1(key: str) -> None:
    assert _exit(_fold("base", TARGET_SERIES))[0] == "target"
    assert _exit(_fold(key, TARGET_SERIES)) == (
        "expired",
        "2026-09-05T12:31:00+00:00",
        "100.6",
    )


@pytest.mark.parametrize("key", ["TGT-3", "TGT-4.5", "EXIT-NOTGT", "EXIT-CHAN"])
def test_the_target_arms_coincide_with_the_base_when_the_invalidation_fires_first(
    key: str,
) -> None:
    """A farther target changes nothing about a trade that ends on its
    invalidation — which is why ``EXIT-CHAN`` must keep that invalidation."""
    assert _exit(_fold(key, INVALIDATION_SERIES)) == _exit(_fold("base", INVALIDATION_SERIES))


def test_the_channel_arm_exits_on_the_close_below_the_ten_previous_closes() -> None:
    chan = _fold("EXIT-CHAN", CHANNEL_SERIES)
    notgt = _fold("EXIT-NOTGT", CHANNEL_SERIES)
    assert _exit(chan) == ("invalidated", "2026-09-05T12:15:00+00:00", "100.05")
    assert _exit(notgt) == ("expired", "2026-09-05T12:31:00+00:00", "100.05")


def test_every_policy_coincides_with_the_base_when_nothing_triggers() -> None:
    baseline = _exit(_fold("base", QUIET_SERIES))
    assert baseline == ("expired", "2026-09-05T12:31:00+00:00", "100")
    for key in POLICIES:
        assert _exit(_fold(key, QUIET_SERIES)) == baseline


def test_the_channel_needs_its_whole_window_and_says_so() -> None:
    """Without ten previous 15m closes the rule has no answer: unresolved, never
    "did not fire"."""
    short = replace(CHANNEL_SERIES, candles=CHANNEL_SERIES.candles[-40:])
    spec = build_arm(_case(), policy("EXIT-CHAN"))
    _progress, _trigger, unavailable, _folded = fold_arm(spec, short)
    assert unavailable == "channel_window_unavailable"


def test_a_candle_after_the_exit_cannot_change_the_outcome() -> None:
    """No look-ahead: the fold stops at the exit, so rewriting later minutes —
    a backfill, a corrected candle — leaves a finished tracking untouched."""
    before = _fold("base", INVALIDATION_SERIES)
    tampered = list(INVALIDATION_SERIES.bars)
    for index in range(20, len(tampered)):
        tampered[index] = replace(
            tampered[index], high=Decimal("500"), low=Decimal("1"), close=Decimal("500")
        )
    after = _fold("base", replace(INVALIDATION_SERIES, bars=tuple(tampered)))
    assert before == after


# --- pairing ------------------------------------------------------------------


def _refused_case() -> ReplayCase:
    """A stored ``no_entry: geometry`` whose geometry really is impossible: the
    entry bar opens at 100, the synthetic fill is 100.06 and target1 is 100."""
    case = _case(ShadowTrackingState.NO_ENTRY)
    return replace(case, plan=replace(case.plan, target1=Decimal("100")))


async def test_no_arm_enters_where_the_base_refused_the_entry() -> None:
    """The admission is frozen at the base — a farther target must not admit a
    trade the base rejected (Strategy Backlog, "ressalva de pareamento")."""
    case = _refused_case()
    outcomes = await replay_case(
        cast("Any", None),
        case,
        policies=[policy(key) for key in POLICIES],
        series=QUIET_SERIES,
    )
    assert len(outcomes) == len(POLICIES)
    assert outcomes["base"].inherited is False, "the base re-derives its own refusal"
    for key, outcome in outcomes.items():
        assert outcome.tracking_state is ShadowTrackingState.NO_ENTRY
        assert outcome.reason == "geometry"
        assert outcome.r_net is None
        assert outcome.inherited is (key != "base")


async def test_a_late_refusal_is_inherited_because_no_candle_can_re_derive_it() -> None:
    case = replace(
        _case(ShadowTrackingState.NO_ENTRY),
        stored=replace(_case(ShadowTrackingState.NO_ENTRY).stored, no_entry_reason="late:delay"),
    )
    outcomes = await replay_case(
        cast("Any", None),
        case,
        policies=[policy("base")],
        series=QUIET_SERIES,
    )
    assert outcomes["base"].inherited is True
    assert outcomes["base"].reason == "late:delay"


async def test_a_stored_geometry_refusal_is_audited_not_copied() -> None:
    """Astra, R1 diff review, must-fix 2: if the record says "geometry" and the
    replay disagrees, the audit has to say so instead of confirming the record
    against itself."""
    case = _case(ShadowTrackingState.NO_ENTRY)  # geometry is actually fine here
    truncated = replace(QUIET_SERIES, bars=QUIET_SERIES.bars[:3], truncated="immature")
    outcomes = await replay_case(
        cast("Any", None), case, policies=[policy("base")], series=truncated
    )
    verdict, divergences = audit_case(case, outcomes["base"])
    assert verdict == "diverged"
    assert [d.field for d in divergences] == ["tracking_state", "no_entry_reason"]


def test_an_arm_the_record_cannot_support_is_refused_not_downgraded() -> None:
    case = replace(_case(), targets=(TARGET1,), atr0=None)
    with pytest.raises(ArmNotBuildable, match="target2_missing"):
        build_arm(case, policy("TGT-3"))
    with pytest.raises(ArmNotBuildable, match="atr0_missing"):
        build_arm(case, policy("INV-E"))


def test_the_no_target_sentinel_is_declared_and_checked() -> None:
    spec = build_arm(_case(), policy("EXIT-NOTGT"))
    assert spec.sentinel == Decimal("100000000.0000000000")
    assert spec.plan.target1 == spec.sentinel
    assert spec.plan.invalidation_level == INVALIDATION


def test_inv_e_lowers_the_level_by_a_quarter_atr_and_inv_c_replaces_the_native_rule() -> None:
    inv_e = build_arm(_case(), policy("INV-E"))
    assert inv_e.plan.invalidation_level == Decimal("99.0000000000")
    inv_c = build_arm(_case(), policy("INV-C"))
    assert inv_c.plan.invalidation_level is None
    assert inv_c.consecutive is not None
    assert inv_c.consecutive.level == INVALIDATION


# --- the audit's own gaps -----------------------------------------------------


async def test_a_terminal_record_that_replays_as_no_entry_is_a_divergence() -> None:
    """Astra, R1 fixes review: filing it as "unresolved" would take it out of the
    gate's denominator, and a replay that refuses every entry would score 1.0."""
    case = _case(ShadowTrackingState.TERMINAL)
    refused = replace(case, plan=replace(case.plan, target1=Decimal("100")))
    outcomes = await replay_case(
        cast("Any", None), refused, policies=[policy("base")], series=QUIET_SERIES
    )
    verdict, divergences = audit_case(refused, outcomes["base"])
    assert verdict == "diverged"
    assert [d.field for d in divergences] == ["tracking_state", "no_entry_reason"]


def _arm(policy_key: str, *, r_net: str | None, matured: bool) -> ArmOutcome:
    return ArmOutcome(
        signal_id=uuid.UUID(int=9),
        policy_key=policy_key,
        tracking_state=(
            ShadowTrackingState.TERMINAL if r_net is not None else ShadowTrackingState.ACTIVE
        ),
        result=OutcomeResult.TARGET if r_net is not None else None,
        reason=None if r_net is not None else "immature",
        entry=Decimal("100"),
        entry_ts=ENTRY,
        exit_base=None,
        exit_price=None,
        exit_ts=None,
        exit_at_open=None,
        exit_bar_open=None,
        r_net=None if r_net is None else Decimal(r_net),
        r_ex_funding=None if r_net is None else Decimal(r_net),
        funding_reason=None,
        trigger=None,
        bars_folded=1,
        matured=matured,
    )


def test_an_immature_horizon_is_dropped_before_the_pairing() -> None:
    """The common horizon cut comes first: pairing on "both resolved" would keep
    the fast exits and drop the slow ones (Astra, R1 fixes review)."""
    outcomes = {
        uuid.UUID(int=9): {
            "base": _arm("base", r_net="1", matured=False),
            "INV-B": _arm("INV-B", r_net="2", matured=False),
        }
    }
    rows = run_contrasts(cast("Any", outcomes), seed=1, resamples=10)
    inv_b = next(row for row in rows if row.spec.treatment == "INV-B")
    assert inv_b.net.n_pairs == 0
    assert inv_b.dropped == {"immature_horizon": 1}
