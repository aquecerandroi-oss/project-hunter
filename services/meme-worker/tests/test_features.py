"""The per-minute fold: every absence has a reason, and no absence becomes a zero.

The case that shaped the schema is here twice, because it is the one that would
have cost a real number: a mint whose snapshot landed but whose denominator was
never observed has a **known market cap** and an **unknown progress**. With one
shared reason column that row was unrepresentable and the collector would have had
to throw the market cap away; with two it is written as it happened
(``.claude/state/notes-T4.2.md`` §contrato amendment 1).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from hunter_meme_worker.features import (
    DENOMINATOR_UNKNOWN,
    NO_HOLDERS_READER,
    NO_TRADE_FEED,
    NOT_POLLED,
    RATE_LIMITED,
    REASON_VOCABULARY,
    CurveObservation,
    MinuteInputs,
    age_minutes,
    build_row,
    curve_progress_pct,
)

from hunter_exchanges.pumpfun import normalize

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
MINUTE = datetime(2026, 9, 12, 5, 30, tzinfo=UTC)
INITIAL = Decimal("793100000")


def _rest_observation() -> CurveObservation:
    """The real ``frontend-api-v3`` response of T4.1, through the real normalizer."""
    raw = json.loads(
        (FIXTURES / "frontend_api_v3_coin_by_mint_response_raw.json").read_text(),
        parse_float=Decimal,
    )
    state = normalize.parse_curve_state_rest(raw)
    return CurveObservation(
        observed_at=state.observed_at,
        source=state.source,
        real_token_reserves=state.real_token_reserves,
        mcap_sol=state.market_cap_sol,
        complete=state.complete,
    )


def _inputs(**kw: object) -> MinuteInputs:
    defaults: dict[str, object] = {
        "mint": "MINT",
        "end_time": MINUTE,
        "created_at": MINUTE - timedelta(minutes=7),
        "initial_real_token_reserves": INITIAL,
        "snapshot": None,
    }
    defaults.update(kw)
    return MinuteInputs(**defaults)  # type: ignore[arg-type]


def test_progress_is_one_minus_the_remaining_share_of_the_observed_denominator() -> None:
    assert curve_progress_pct(Decimal("793100000"), INITIAL) == Decimal("0")
    assert curve_progress_pct(Decimal("396550000"), INITIAL) == Decimal("0.500000")
    assert curve_progress_pct(Decimal("0"), INITIAL) == Decimal("1.000000")


def test_an_unobserved_or_zero_denominator_yields_no_progress_instead_of_a_guess() -> None:
    """The 793,1 M constant every blog quotes is not a fallback (plan §3)."""
    assert curve_progress_pct(Decimal("10"), None) is None
    assert curve_progress_pct(Decimal("10"), Decimal("0")) is None


def test_progress_outside_zero_and_one_is_stored_as_observed_not_clamped() -> None:
    """§15.8: a strange feed number must stay visible, not become a plausible one."""
    progress = curve_progress_pct(Decimal("900000000"), INITIAL)
    assert progress is not None and progress < 0


def test_a_minute_with_no_observation_is_all_nulls_with_reasons_and_zero_coverage() -> None:
    row = build_row(_inputs(absence_reason=NOT_POLLED))
    assert row.coverage == Decimal(0)
    assert (row.mcap_sol, row.curve_reason) == (None, NOT_POLLED)
    assert (row.curve_progress_pct, row.progress_reason) == (None, NOT_POLLED)
    assert (row.unique_buyers, row.unique_buyers_reason) == (None, NO_TRADE_FEED)
    assert (row.buy_sell_ratio, row.buy_sell_ratio_reason) == (None, NO_TRADE_FEED)
    assert (row.top10_share, row.top10_share_reason) == (None, NO_HOLDERS_READER)
    assert (row.creator_sold, row.creator_sold_reason) == (None, NO_HOLDERS_READER)
    assert row.snapshot_observed_at is None and row.snapshot_source is None
    assert row.age_minutes == 7


def test_a_rate_limited_minute_says_rate_limited_and_not_not_polled() -> None:
    """The two are different operator problems and the API renders them apart."""
    row = build_row(_inputs(absence_reason=RATE_LIMITED))
    assert row.curve_reason == RATE_LIMITED
    assert row.progress_reason == RATE_LIMITED


def test_a_real_rest_reading_folds_into_a_covered_minute() -> None:
    observation = _rest_observation()
    row = build_row(_inputs(snapshot=observation))
    assert row.coverage == Decimal(1)
    assert row.curve_reason is None
    assert row.progress_reason is None
    assert row.mcap_sol is not None and row.mcap_sol > 0
    assert row.snapshot_source == "pumpfun_rest"
    assert row.snapshot_observed_at == observation.observed_at
    assert row.curve_progress_pct == curve_progress_pct(observation.real_token_reserves, INITIAL)


def test_a_known_market_cap_survives_an_unknown_denominator() -> None:
    """The amendment's whole point: two absences, two causes, two reasons."""
    observation = _rest_observation()
    row = build_row(_inputs(snapshot=observation, initial_real_token_reserves=None))
    assert row.mcap_sol is not None, "a real market cap was thrown away"
    assert row.curve_reason is None
    assert row.curve_progress_pct is None
    assert row.progress_reason == DENOMINATOR_UNKNOWN


def test_the_four_trade_and_holder_columns_are_null_in_every_row_this_slice_writes() -> None:
    """Astra's MUST-FIX 1, as a test: no feed is never "nobody bought"."""
    for snapshot in (None, _rest_observation()):
        row = build_row(_inputs(snapshot=snapshot))
        assert row.unique_buyers is None and row.unique_buyers_reason == NO_TRADE_FEED
        assert row.buy_sell_ratio is None and row.buy_sell_ratio_reason == NO_TRADE_FEED
        assert row.top10_share is None and row.top10_share_reason == NO_HOLDERS_READER
        assert row.creator_sold is None and row.creator_sold_reason == NO_HOLDERS_READER


def test_every_reason_a_row_can_carry_is_in_the_frozen_vocabulary() -> None:
    """T4.3 renders these and only these; a seventh reason is a decision."""
    rows = [
        build_row(_inputs()),
        build_row(_inputs(snapshot=_rest_observation())),
        build_row(_inputs(snapshot=_rest_observation(), initial_real_token_reserves=None)),
        build_row(_inputs(absence_reason=RATE_LIMITED)),
    ]
    reasons = {
        reason
        for row in rows
        for reason in (
            row.curve_reason,
            row.progress_reason,
            row.unique_buyers_reason,
            row.buy_sell_ratio_reason,
            row.top10_share_reason,
            row.creator_sold_reason,
        )
        if reason is not None
    }
    assert reasons <= REASON_VOCABULARY


def test_an_unobserved_or_future_creation_time_leaves_the_age_unknown() -> None:
    """A negative age is a clock disagreeing with itself, and the CHECK would refuse it."""
    assert age_minutes(MINUTE, None) is None
    assert age_minutes(MINUTE, MINUTE + timedelta(minutes=1)) is None
    assert age_minutes(MINUTE, MINUTE) == 0
    assert build_row(_inputs(created_at=None)).age_minutes is None


def test_a_snapshot_the_database_could_not_price_is_covered_but_capless() -> None:
    """A zero virtual reserve makes the generated column NULL (§15.8): the
    observation happened and the number does not exist, which is two facts."""
    observation = CurveObservation(
        observed_at=MINUTE,
        source="pumpfun_rest",
        real_token_reserves=Decimal("100"),
        mcap_sol=None,
        complete=False,
    )
    row = build_row(_inputs(snapshot=observation))
    assert row.coverage == Decimal(1)
    assert row.mcap_sol is None and row.curve_reason == "insufficient_coverage"
    assert row.curve_progress_pct is not None, "progress does not need a market cap"
    assert row.progress_reason is None
