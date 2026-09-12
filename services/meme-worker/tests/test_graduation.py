"""The four completion signals, their reducer, the fill threshold and the
denominator source — pure (T4.2d).

What the plantão measured (run 5, 12/09 05:51 BRT): of 140 coins the REST said
were ``complete``, 77 had ``real_sol_reserves = 0`` and 72 were not on the
site's ``graduated`` board. Astra's must-fixes: keep the four indicators
separate, and a zero reserve classifies nothing. So ``completed_at`` is the
earliest of the four, **except** that a REST ``complete = true`` whose photo
carried no SOL does not count on its own.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hunter_meme_worker.graduation import (
    GLOBAL_PARAMS,
    OBSERVED_VIRGIN,
    POOL_SOURCE_TRENCHES,
    CompletionSignals,
    GlobalParamsStore,
    curve_signals,
    denominator_for,
    earliest_completion,
    fill_threshold_sol,
)

from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_exchanges.pumpfun.quote import GlobalParams

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)
PARAMS = GlobalParams(
    slot=354155511,
    signature="x",
    initial_virtual_token_reserves=1073000000000000,
    initial_virtual_sol_reserves=30000000000,
    initial_real_token_reserves=793100000000000,
    token_total_supply=1000000000000000,
    fee_basis_points=95,
    timestamp=1752856476446,
)


def _state(
    *,
    real_sol: str = "0",
    real_token: str = "793100000",  # noqa: S107 — a reserve, not a secret
    complete: bool = False,
    mayhem_state: str | None = None,
    mayhem_enabled: bool | None = None,
    observed_at: datetime = T0,
) -> NormalizedCurveState:
    return NormalizedCurveState(
        mint="MINT",
        virtual_sol_reserves=Decimal("30"),
        virtual_token_reserves=Decimal("1073000000"),
        real_sol_reserves=Decimal(real_sol),
        real_token_reserves=Decimal(real_token),
        total_supply=Decimal("1000000000"),
        complete=complete,
        market_cap_sol=Decimal("27.96"),
        source="pumpfun_rest",
        observed_at=observed_at,
        received_at=observed_at,
        mayhem_state=mayhem_state,
        mayhem_enabled=mayhem_enabled,
    )


# ------------------------------------------------------------------ reducer
def test_the_earliest_of_the_four_signals_is_the_completion() -> None:
    signals = CompletionSignals(
        rest_complete_seen_at=T0 + timedelta(minutes=3),
        curve_filled_seen_at=T0 + timedelta(minutes=2),
        graduated_board_seen_at=T0 + timedelta(minutes=1),
        pool_created_at=T0,
        pool_created_source=POOL_SOURCE_TRENCHES,
    )
    assert earliest_completion(signals) == T0


def test_no_signal_is_no_completion() -> None:
    assert earliest_completion(CompletionSignals()) is None


def test_a_rest_complete_with_a_zero_reserve_classifies_nothing_on_its_own() -> None:
    """Astra, must-fix 2: 77/140 "complete" coins had ``real_sol_reserves = 0``
    (47 Mayhem, mcap median US$ 9,57) — and so did 31 real graduations whose
    reserve had already left for the pool. The photo is recorded as a signal;
    it is not, alone, a completion."""
    alone = CompletionSignals(rest_complete_seen_at=T0, rest_reserve_is_zero=True)
    assert earliest_completion(alone) is None
    with_sol = CompletionSignals(rest_complete_seen_at=T0, rest_reserve_is_zero=False)
    assert earliest_completion(with_sol) == T0
    corroborated = CompletionSignals(
        rest_complete_seen_at=T0,
        rest_reserve_is_zero=True,
        pool_created_at=T0 + timedelta(seconds=30),
        pool_created_source=POOL_SOURCE_TRENCHES,
    )
    assert earliest_completion(corroborated) == T0 + timedelta(seconds=30), (
        "the zero-reserve photo does not even lend its instant: the pool is the evidence"
    )


# ------------------------------------------------------- the curve's signals
def test_the_fill_threshold_is_derived_from_the_record_never_typed() -> None:
    assert fill_threshold_sol(PARAMS) == Decimal("85.005359057")


def test_a_curve_at_the_threshold_is_filled_and_a_complete_photo_is_rest_complete() -> None:
    filled = curve_signals(_state(real_sol="85.005359057", real_token="0"), PARAMS)
    assert filled.curve_filled_seen_at == T0 and filled.rest_complete_seen_at is None
    complete = curve_signals(_state(real_sol="0", real_token="0", complete=True), PARAMS)
    assert complete.rest_complete_seen_at == T0 and complete.rest_reserve_is_zero
    assert complete.curve_filled_seen_at is None
    both = curve_signals(_state(real_sol="85.1", real_token="0", complete=True), PARAMS)
    assert both.rest_complete_seen_at == T0 and both.curve_filled_seen_at == T0
    assert not both.rest_reserve_is_zero


def test_without_the_record_nothing_is_called_filled() -> None:
    """No threshold, no claim: ``curve_filled_seen_at`` stays unset rather than
    comparing against a number typed from a blog."""
    signals = curve_signals(_state(real_sol="85.1", real_token="0"), None)
    assert signals.curve_filled_seen_at is None


# ----------------------------------------------------------- the denominator
def test_a_virgin_curve_gives_the_observed_denominator() -> None:
    result = denominator_for(_state(real_sol="0", real_token="793100000"), PARAMS)
    assert (result.value, result.source) == (Decimal("793100000"), OBSERVED_VIRGIN)
    mayhem_virgin = denominator_for(
        _state(real_sol="0", real_token="822644036.902123", mayhem_state="active"), PARAMS
    )
    assert (mayhem_virgin.value, mayhem_virgin.source) == (
        Decimal("822644036.902123"),
        OBSERVED_VIRGIN,
    ), "a Mayhem curve observed before its first buy has its own, observed, initial"


def test_a_curve_discovered_after_the_first_buy_takes_the_records_denominator() -> None:
    """The production finding (06:04 BRT): 117/123 gate rows were
    ``progress_unknown`` because the denominator was only ever written from a
    virgin photo. A standard curve seen mid-life gets the record's initial."""
    result = denominator_for(_state(real_sol="12.5", real_token="600000000"), PARAMS)
    assert (result.value, result.source) == (Decimal("793100000"), GLOBAL_PARAMS)
    done = denominator_for(_state(real_sol="85.1", real_token="0", complete=True), PARAMS)
    assert (done.value, done.source) == (Decimal("793100000"), GLOBAL_PARAMS)


def test_a_mayhem_curve_never_takes_the_records_denominator() -> None:
    """The extra 1 B: a Mayhem coin's agent mints a billion tokens on top and
    ``set_mayhem_virtual_params`` moves the curve's reserves (RISK_ENGINE_MEME
    §8.3). The by-mint fixture of T4.1 (``2sduGq…``, ``mayhem_state = paused``)
    holds 822,6 M real tokens — more than the record's 793,1 M initial. The
    record describes the standard curve, not this one: unknown, said so."""
    by_state = denominator_for(
        _state(real_sol="0.000000001", real_token="822644036.902123", mayhem_state="paused"),
        PARAMS,
    )
    assert (by_state.value, by_state.source) == (None, None)
    by_flag = denominator_for(
        _state(real_sol="0.27", real_token="779556997.686755", mayhem_enabled=True), PARAMS
    )
    assert (by_flag.value, by_flag.source) == (None, None)


def test_a_curve_holding_more_than_the_records_initial_is_not_the_records_curve() -> None:
    result = denominator_for(_state(real_sol="0.5", real_token="822644036.902123"), PARAMS)
    assert (result.value, result.source) == (None, None)


def test_without_the_record_a_bought_curve_stays_unknown() -> None:
    result = denominator_for(_state(real_sol="12.5", real_token="600000000"), None)
    assert (result.value, result.source) == (None, None)


# ------------------------------------------------------------------ the store
class _Source:
    def __init__(self, records: dict[int, GlobalParams] | None = None) -> None:
        self.calls: list[int] = []
        self.records = records or {}
        self.fail = False

    async def get_global_params(self, created_at_ms: int) -> GlobalParams:
        self.calls.append(created_at_ms)
        if self.fail:
            raise RuntimeError("boom")
        for since in sorted(self.records, reverse=True):
            if created_at_ms >= since:
                return self.records[since]
        return PARAMS


async def test_the_store_reads_once_per_refresh_and_serves_every_coin_created_since() -> None:
    source = _Source()
    store = GlobalParamsStore(source, refresh_s=3600)
    created = datetime(2026, 9, 12, 7, 0, tzinfo=UTC)
    assert await store.resolve(created, now=T0) is PARAMS
    assert await store.resolve(created + timedelta(minutes=5), now=T0 + timedelta(minutes=1))
    assert await store.resolve(None, now=T0 + timedelta(minutes=2)) is PARAMS
    assert len(source.calls) == 1, "one read per refresh window, charged to the curve budget"
    assert await store.resolve(created, now=T0 + timedelta(hours=2))
    assert len(source.calls) == 2


async def test_a_coin_created_before_the_records_instant_gets_its_own_record() -> None:
    older = GlobalParams(
        slot=1,
        signature="old",
        initial_virtual_token_reserves=1073000000000000,
        initial_virtual_sol_reserves=30000000000,
        initial_real_token_reserves=793100000000000,
        token_total_supply=1000000000000000,
        fee_basis_points=100,
        timestamp=1700000000000,
    )
    newer = GlobalParams(
        slot=2,
        signature="new",
        initial_virtual_token_reserves=1073000000000000,
        initial_virtual_sol_reserves=30000000000,
        initial_real_token_reserves=793100000000000,
        token_total_supply=1000000000000000,
        fee_basis_points=95,
        timestamp=int(T0.timestamp() * 1000) - 60_000,
    )
    source = _Source({1700000000000: older, newer.timestamp: newer})
    store = GlobalParamsStore(source, refresh_s=3600)
    assert (await store.resolve(T0, now=T0)) is newer
    before = T0 - timedelta(minutes=5)
    assert (await store.resolve(before, now=T0)) is older
    assert (await store.resolve(before, now=T0)) is older
    assert len(source.calls) == 2, "the older record is remembered too"


async def test_a_failed_read_is_counted_and_never_becomes_a_guess() -> None:
    source = _Source()
    source.fail = True
    store = GlobalParamsStore(source, refresh_s=3600)
    assert await store.resolve(T0, now=T0) is None
    assert store.errors == 1 and store.last_error == "RuntimeError"
    source.fail = False
    assert await store.resolve(T0, now=T0 + timedelta(seconds=1)) is PARAMS, (
        "a failure does not start the refresh window"
    )
