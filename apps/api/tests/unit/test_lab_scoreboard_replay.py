"""Unit tests: ``ScoreboardRowOut.replay`` block builder — briefs T3.18b
(item 1) e T3.18c (item 9: massa medida em **decisões**, não em barras).

No IO, no Postgres: ``OutcomeRow``/``ReplayRunsSummary`` are built by hand.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_api.repositories.lab_scoreboard import ReplayRunsSummary, ReplayRunWindow
from hunter_api.repositories.lab_summary import OutcomeRow
from hunter_api.schemas.lab_scoreboard import RateWithCountsOut
from hunter_api.services.lab_scoreboard_replay import (
    NO_STATES_REASON,
    build_replay_block,
    decisions_simulated,
)
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
EMPTY_RUNS = ReplayRunsSummary(
    runs=0,
    bars_evaluated=0,
    evaluations_by_state={},
    window_from=None,
    window_to=None,
    windows=[],
)

STATES = {
    "triggered": 3,
    "not_triggered": 297,
    "rejected": 100,
    "unavailable": 80,
    "ineligible": 20,
}
"""500 barras varridas, 400 delas com decisão registrada (D14)."""


def _runs(
    *,
    runs: int,
    bars: int,
    window_from: datetime | None,
    window_to: datetime | None,
    states: dict[str, int] | None = None,
) -> ReplayRunsSummary:
    windows = (
        []
        if window_from is None or window_to is None
        else [ReplayRunWindow(run_id=uuid.uuid4(), window_from=window_from, window_to=window_to)]
    )
    return ReplayRunsSummary(
        runs=runs,
        bars_evaluated=bars,
        evaluations_by_state=STATES if states is None else states,
        window_from=window_from,
        window_to=window_to,
        windows=windows,
    )


def _evaluable_row(
    *,
    decision_at: datetime,
    exit_ts: datetime,
    r_multiple: Decimal,
    market_id: uuid.UUID | None = None,
    horizon_s: int = 3600,
) -> OutcomeRow:
    entry_bar_open = decision_at + timedelta(minutes=1)
    return OutcomeRow(
        tracking_state=ShadowTrackingState.TERMINAL,
        result=OutcomeResult.TARGET if r_multiple > 0 else OutcomeResult.STOP,
        no_entry_reason=None,
        censored_reason=None,
        entry_ts=entry_bar_open,
        exit_ts=exit_ts,
        r_multiple=r_multiple,
        meta={"entry_plan": {"entry_bar_open": entry_bar_open.isoformat()}, "horizon_s": horizon_s},
        market_id=market_id or uuid.uuid4(),
        decision_at=decision_at,
    )


class TestNullWhenThereIsNoEvidence:
    def test_zero_runs_and_zero_rows_is_none(self) -> None:
        assert build_replay_block(rows=[], runs=EMPTY_RUNS, as_of=AS_OF) is None

    def test_a_receipted_run_with_zero_outcomes_is_not_none(self) -> None:
        """A run happened (the D14 mass counter is non-zero) even though it
        produced no closed operation yet — still evidence, never null."""
        runs = _runs(runs=1, bars=500, window_from=AS_OF - timedelta(days=1), window_to=AS_OF)
        block = build_replay_block(rows=[], runs=runs, as_of=AS_OF)
        assert block is not None
        assert block.runs == 1
        assert block.bars_evaluated == 500
        assert block.decisions_simulated == 400
        assert block.operations_closed == 0
        assert block.expectancy_r.value is None
        assert block.expectancy_r.reason == "no_sample"
        assert block.profit_factor.value is None
        assert block.profit_factor.reason == "no_sample"
        assert block.net_profit_rate.value is None
        assert block.net_profit_rate.reason == "no_sample"
        assert block.label == "replay — não conta para o veredito"


class TestOperationsClosedIsTheSameEvaluableGateAsProspective:
    def test_a_recent_row_not_yet_matured_by_horizon_does_not_count(self) -> None:
        decision_at = AS_OF - timedelta(minutes=30)
        row = _evaluable_row(
            decision_at=decision_at,
            exit_ts=decision_at + timedelta(minutes=25),
            r_multiple=Decimal("-1"),
            horizon_s=4 * 3600,
        )
        runs = _runs(runs=1, bars=10, window_from=AS_OF, window_to=AS_OF)

        block = build_replay_block(rows=[row], runs=runs, as_of=AS_OF)

        assert block is not None
        assert block.operations_closed == 0

    def test_a_matured_row_counts_and_feeds_the_rates(self) -> None:
        decision_at = AS_OF - timedelta(hours=6)
        rows = [
            _evaluable_row(
                decision_at=decision_at,
                exit_ts=decision_at + timedelta(hours=1),
                r_multiple=Decimal("2"),
            ),
            _evaluable_row(
                decision_at=decision_at,
                exit_ts=decision_at + timedelta(hours=2),
                r_multiple=Decimal("-1"),
            ),
        ]
        runs = _runs(runs=2, bars=1000, window_from=decision_at, window_to=AS_OF)

        block = build_replay_block(rows=rows, runs=runs, as_of=AS_OF)

        assert block is not None
        assert block.runs == 2
        assert block.bars_evaluated == 1000
        assert block.decisions_simulated == 400
        assert block.operations_closed == 2
        assert block.expectancy_r.value == Decimal("0.5000")
        assert block.net_profit_rate == _expected_rate(numerator=1, denominator=2)
        assert block.distinct_days == 1
        assert block.window_from == decision_at
        assert block.window_to == AS_OF


def _expected_rate(*, numerator: int, denominator: int) -> RateWithCountsOut:
    value = None if denominator == 0 else Decimal(numerator) / Decimal(denominator)
    return RateWithCountsOut(
        value=None if value is None else value.quantize(Decimal("0.0001")),
        reason=None,
        numerator=numerator,
        denominator=denominator,
    )


class TestMassIsCountedInDecisions:
    """T3.18c, item 9 (D14): a meta de 500 mil por dia é medida contra barras
    **com decisão registrada**, não contra barras varridas."""

    def test_unavailable_and_ineligible_bars_are_not_decisions(self) -> None:
        decided, reason = decisions_simulated(STATES)
        assert (decided, reason) == (400, None)

    def test_the_block_publishes_the_whole_map_so_the_numerator_is_checkable(self) -> None:
        runs = _runs(runs=1, bars=500, window_from=AS_OF - timedelta(days=1), window_to=AS_OF)
        block = build_replay_block(rows=[], runs=runs, as_of=AS_OF)
        assert block is not None
        assert block.evaluations_by_state == STATES
        assert sum(block.evaluations_by_state.values()) == block.bars_evaluated
        assert block.decisions_simulated_reason is None

    def test_receipts_without_the_state_map_answer_null_with_a_reason(self) -> None:
        """Zero inventado seria pior que o silêncio: um recibo antigo não sabe
        quantas barras viraram decisão, e dizer 0 afirmaria que nenhuma virou."""
        runs = _runs(
            runs=1,
            bars=500,
            window_from=AS_OF - timedelta(days=1),
            window_to=AS_OF,
            states={},
        )
        block = build_replay_block(rows=[], runs=runs, as_of=AS_OF)
        assert block is not None
        assert block.bars_evaluated == 500
        assert block.decisions_simulated is None
        assert block.decisions_simulated_reason == NO_STATES_REASON
