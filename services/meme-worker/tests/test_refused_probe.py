"""T4.85 / EXP-M23 — the sampler and the anti-look-ahead guard of
``refused_probe_v0/1``, pure and without a database.

What these tests hold frozen (``obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md``
plus its Emenda 1 of 23/09/2026): the two strata and their four rates, the
seed, that a mint is drawn once, that a mint admitted anywhere in the same
tick is out, that **every** refusal reason is recorded (not only the first),
and that a bet does not move when a later candle or a retroactively written
row arrives — the R69 invariance test (`.claude/state/r69/test_cohort.py`)
carried over to the probe.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_worker.refused_probe import (
    EXPERIMENT,
    FROZEN_SEED,
    PROBE_CLOCK,
    RATE_A_BASE,
    RATE_A_RARE,
    RATE_B_BASE,
    RATE_B_RARE,
    STRATUM_MULTIPLE,
    STRATUM_NEAR_MISS,
    RefusedRow,
    criteria_refusals,
    inclusion_probability,
    is_sampled,
    pick_probes,
    probe_reason_block,
    stratum_of,
    uniform01,
)

pytestmark = pytest.mark.unit

TICK = datetime(2026, 9, 23, 16, 20, tzinfo=UTC)
"""The tick's ``now``; every row below is stamped relative to it."""

MINT_IN = "Mint7111111111111111111111111111111111111111"
"""Frozen draw 0,0838 — inside stratum A's 10 %, outside B's 0,1 %."""
MINT_RARE = "Mint0111111111111111111111111111111111111111"
"""Frozen draw 0,4396 — outside A's 10 %, inside A's oversampled 50 %."""
MINT_OUT = "Mint5111111111111111111111111111111111111111"
"""Frozen draw 0,9251 — outside every one of the four rates."""
MINT_DEEP = "Mint2978111111111111111111111111111111111111"
"""Frozen draw 0,000131 — inside even stratum B's 0,1 %."""

COMMON = "snipers_above_max"
COMMON_2 = "progress_above_max"
RARE = "dev_share_above_max"
"""A name absent from the pre-registration's own census of 41 905 refusals —
therefore under 30 mints/week, therefore oversampled."""


def _row(
    mint: str,
    *,
    refusals: tuple[str, ...] = (COMMON,),
    as_of: datetime | None = None,
    computed_at: datetime | None = None,
    tape_as_of: datetime | None = None,
    snapshot_observed_at: datetime | None = None,
) -> RefusedRow:
    at = TICK - timedelta(seconds=15) if as_of is None else as_of
    return RefusedRow(
        mint=mint,
        as_of=at,
        refusals=refusals,
        refused_by="operator/6",
        computed_at=at if computed_at is None else computed_at,
        tape_as_of=at if tape_as_of is None else tape_as_of,
        snapshot_observed_at=at if snapshot_observed_at is None else snapshot_observed_at,
    )


# --- the two strata and the four frozen rates -------------------------------


def test_the_four_rates_are_the_ones_emenda_1_froze() -> None:
    assert (RATE_A_BASE, RATE_A_RARE) == (Decimal("0.10"), Decimal("0.50"))
    assert (RATE_B_BASE, RATE_B_RARE) == (Decimal("0.001"), Decimal("0.005"))


def test_exactly_one_criterion_is_stratum_a_and_two_is_stratum_b() -> None:
    assert stratum_of((COMMON,)) == STRATUM_NEAR_MISS
    assert stratum_of((COMMON, COMMON_2)) == STRATUM_MULTIPLE
    assert stratum_of(()) is None


def test_a_rare_reason_oversamples_its_own_stratum() -> None:
    assert inclusion_probability((COMMON,)) == RATE_A_BASE
    assert inclusion_probability((RARE,)) == RATE_A_RARE
    assert inclusion_probability((COMMON, COMMON_2)) == RATE_B_BASE
    assert inclusion_probability((COMMON, RARE)) == RATE_B_RARE


def test_a_structural_skip_is_not_a_criterion() -> None:
    """``already_open`` fires before the gate reads a criterion and
    ``no_snapshot_for_quote`` fires after the gate has already passed — neither is a
    refusal by the desk, so neither puts a mint in the population."""
    assert criteria_refusals(("already_open",)) == ()
    assert criteria_refusals(("no_snapshot_for_quote",)) == ()
    assert criteria_refusals(("already_open", COMMON)) == (COMMON,)
    assert stratum_of(criteria_refusals(("already_open",))) is None


def test_all_reasons_are_kept_sorted_and_deduplicated() -> None:
    assert criteria_refusals((COMMON, COMMON_2, COMMON_2)) == (COMMON_2, COMMON)
    assert COMMON_2 < COMMON, "sorted, so the row reads the same however the tick built it"


# --- the sampler ------------------------------------------------------------


def test_the_draw_is_frozen_under_the_frozen_seed() -> None:
    assert FROZEN_SEED == "EXP-M23/refused_probe_v0/1"
    assert uniform01(MINT_IN).quantize(Decimal("0.000001")) == Decimal("0.083816")
    assert uniform01(MINT_OUT).quantize(Decimal("0.000001")) == Decimal("0.925056")


def test_the_draw_does_not_move_between_calls() -> None:
    assert uniform01(MINT_IN) == uniform01(MINT_IN)


def test_a_different_seed_is_a_different_experiment() -> None:
    assert uniform01(MINT_IN, seed="outra-semente") != uniform01(MINT_IN)


def test_the_draw_decides_against_the_probability_of_its_own_stratum() -> None:
    assert is_sampled(MINT_IN, RATE_A_BASE)
    assert not is_sampled(MINT_IN, RATE_B_BASE)
    assert not is_sampled(MINT_RARE, RATE_A_BASE)
    assert is_sampled(MINT_RARE, RATE_A_RARE)
    assert is_sampled(MINT_DEEP, RATE_B_BASE)
    assert not is_sampled(MINT_OUT, RATE_A_RARE)


def test_the_rate_holds_over_a_large_frozen_population() -> None:
    """Not a property of one mint: over 20 000 mints the share drawn at 10 %
    is 10 % ± 1 pp — the sampler is random, not merely deterministic."""
    mints = [f"Sample{i}".ljust(44, "1") for i in range(20_000)]
    drawn = sum(1 for mint in mints if is_sampled(mint, RATE_A_BASE))
    assert 1_900 <= drawn <= 2_100


# --- the population ---------------------------------------------------------


def test_a_mint_admitted_by_any_arm_in_the_same_tick_is_out() -> None:
    rows = [_row(MINT_IN)]
    assert [p.row.mint for p in pick_probes(rows, admitted={}, now=TICK)] == [MINT_IN]
    same_instant = {MINT_IN: TICK - timedelta(seconds=15)}
    assert pick_probes(rows, admitted=same_instant, now=TICK) == []


def test_an_admission_after_the_refusal_does_not_erase_the_refusal() -> None:
    """Cancelling a bet decided at t because an arm admitted the mint at
    t + 15 s is the same look-ahead the guard exists to forbid — and it would
    make the population depend on how the backlog happened to be batched (a
    tick that saw both instants would drop the mint, two ticks would not)."""
    rows = [_row(MINT_IN, as_of=TICK - timedelta(seconds=30))]
    later = {MINT_IN: TICK - timedelta(seconds=15)}
    assert [p.row.mint for p in pick_probes(rows, admitted=later, now=TICK)] == [MINT_IN]
    assert pick_probes(rows, admitted=later, now=TICK) == pick_probes(rows, admitted={}, now=TICK)


def test_a_mint_already_drawn_never_enters_again() -> None:
    rows = [_row(MINT_IN)]
    assert pick_probes(rows, admitted={}, now=TICK, drawn=frozenset({MINT_IN})) == []


def test_a_mint_with_no_criterion_refusal_is_not_population() -> None:
    rows = [_row(MINT_IN, refusals=("already_open",))]
    assert pick_probes(rows, admitted={}, now=TICK) == []


def test_a_row_with_no_snapshot_cannot_be_quoted_and_is_not_an_opportunity() -> None:
    rows = [RefusedRow(mint=MINT_IN, as_of=TICK, refusals=(COMMON,), refused_by="operator/6")]
    assert pick_probes(rows, admitted={}, now=TICK) == []


def test_the_pick_records_every_reason_the_stratum_and_the_probability() -> None:
    rows = [_row(MINT_DEEP, refusals=(COMMON_2, COMMON))]
    (pick,) = pick_probes(rows, admitted={}, now=TICK)
    assert pick.stratum == STRATUM_MULTIPLE
    assert pick.probability == RATE_B_BASE
    block = probe_reason_block(pick)
    assert block["refusals"] == [COMMON_2, COMMON]
    assert block["stratum"] == STRATUM_MULTIPLE
    assert block["inclusion_probability"] == "0.001"
    assert block["sampler_seed"] == FROZEN_SEED
    assert block["experiment"] == EXPERIMENT
    assert block["refused_by"] == "operator/6"
    assert block["as_of"] == pick.row.as_of.isoformat()


def test_two_operator_sets_refusing_the_same_instant_merge_their_reasons() -> None:
    rows = [
        _row(MINT_DEEP, refusals=(COMMON,)),
        _row(MINT_DEEP, refusals=(COMMON_2,)),
    ]
    (pick,) = pick_probes(rows, admitted={}, now=TICK)
    assert pick.row.refusals == (COMMON_2, COMMON)
    assert pick.stratum == STRATUM_MULTIPLE


# --- the anti-look-ahead guard (R69's invariance test, carried over) --------


def test_a_later_row_does_not_change_the_pick() -> None:
    """The bet must not move when the next 15-second candle arrives."""
    first = _row(MINT_IN, as_of=TICK - timedelta(seconds=45))
    before = pick_probes([first], admitted={}, now=TICK)
    later = _row(MINT_IN, as_of=TICK - timedelta(seconds=15), refusals=(COMMON, COMMON_2))
    after = pick_probes([first, later], admitted={}, now=TICK)
    assert before == after


def test_a_row_from_the_future_of_the_tick_is_rejected() -> None:
    future = _row(MINT_IN, as_of=TICK + timedelta(seconds=15))
    assert pick_probes([future], admitted={}, now=TICK) == []


def test_a_row_written_after_the_tick_is_rejected() -> None:
    """``as_of`` inside the window but ``computed_at`` after it: a retroactive
    fill would put in the bet a number nobody could read at the refusal."""
    retro = _row(MINT_IN, computed_at=TICK + timedelta(seconds=1))
    assert pick_probes([retro], admitted={}, now=TICK) == []


def test_tape_from_the_future_of_its_own_row_is_rejected() -> None:
    ahead = _row(MINT_IN, tape_as_of=TICK - timedelta(seconds=1))
    assert ahead.tape_as_of is not None and ahead.tape_as_of > ahead.as_of
    assert pick_probes([ahead], admitted={}, now=TICK) == []


def test_the_snapshot_of_the_pick_is_not_from_the_future_of_its_row() -> None:
    ahead = _row(MINT_IN, snapshot_observed_at=TICK - timedelta(seconds=1))
    assert pick_probes([ahead], admitted={}, now=TICK) == []


def test_the_pick_is_the_earliest_eligible_opportunity() -> None:
    early = _row(MINT_IN, as_of=TICK - timedelta(seconds=45))
    late = _row(MINT_IN, as_of=TICK - timedelta(seconds=15))
    (pick,) = pick_probes([late, early], admitted={}, now=TICK)
    assert pick.row.as_of == early.as_of


def test_the_order_of_the_rows_does_not_change_the_result() -> None:
    rows = [_row(MINT_IN), _row(MINT_DEEP), _row(MINT_OUT)]
    assert pick_probes(rows, admitted={}, now=TICK) == pick_probes(
        list(reversed(rows)), admitted={}, now=TICK
    )


def test_the_probe_clock_is_its_own() -> None:
    assert PROBE_CLOCK == "refused"
    assert PROBE_CLOCK not in {"1m", "15s", "event"}


def test_the_pick_does_not_depend_on_how_the_backlog_was_batched() -> None:
    """Astra's finding nº 3: the "tick" is a processing batch, so a rule that
    looked across the whole batch would give a mint one answer when the worker
    kept up and another when it caught up on two instants at once."""
    early = _row(MINT_IN, as_of=TICK - timedelta(seconds=30))
    late_admission = {MINT_IN: TICK - timedelta(seconds=15)}
    one_batch = pick_probes([early], admitted=late_admission, now=TICK)
    two_batches = pick_probes([early], admitted={}, now=TICK)
    assert one_batch == two_batches
    assert [p.row.as_of for p in one_batch] == [early.as_of]
