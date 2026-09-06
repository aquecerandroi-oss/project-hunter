"""Signal identity and the tracking-slot state machine (the pure halves).

SHADOW-LAB.md §6 (identity, ``decision_at`` deliberately outside the hash) and
§4 (one tracking per slot; re-arm only after a bar where the condition was
observably false *after* the previous tracking ended).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from hunter_core.domain.enums import ShadowCohort
from hunter_core.strategies.base import EvaluationState
from hunter_strategy_worker.episodes import SlotState, next_slot
from hunter_strategy_worker.identity import NAMESPACE_SHADOW, signal_id

pytestmark = pytest.mark.unit

VERSION = uuid.UUID("11111111-1111-5111-8111-111111111111")
MARKET = uuid.UUID("22222222-2222-5222-8222-222222222222")
BAR = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
HASH = "a" * 64


def _id(**overrides: object) -> uuid.UUID:
    kwargs: dict[str, object] = {
        "strategy_version_id": VERSION,
        "market_id": MARKET,
        "params_hash": HASH,
        "source_bar_close": BAR,
        "cohort": ShadowCohort.PROSPECTIVE,
    }
    kwargs.update(overrides)
    return signal_id(**kwargs)  # type: ignore[arg-type]


class TestSignalIdentity:
    def test_the_same_observation_always_gets_the_same_id(self) -> None:
        assert _id() == _id()
        assert _id().version == 5

    def test_the_namespace_is_pinned(self) -> None:
        """Changing it would renumber every historical signal (SHADOW-LAB.md §6)."""
        assert NAMESPACE_SHADOW == uuid.UUID("0f9d2a3c-5b7e-5c41-9f3a-8d6c1e2b4a70")

    def test_the_id_is_stable_across_processes(self) -> None:
        """Golden vector. If this changes, every historical signal id changed
        with it and one experiment silently became two (SHADOW-LAB.md §6)."""
        assert str(_id()) == "7507473c-df13-520e-83ee-2b3ea76f2df3"

    def test_a_different_bar_is_a_different_signal(self) -> None:
        assert _id(source_bar_close=BAR + timedelta(minutes=15)) != _id()

    def test_a_different_parameter_set_is_a_different_signal(self) -> None:
        assert _id(params_hash="b" * 64) != _id()

    def test_a_replay_never_collides_with_the_prospective_cohort(self) -> None:
        run = uuid.UUID("33333333-3333-5333-8333-333333333333")
        assert _id(cohort=ShadowCohort.replay(run)) != _id()

    def test_two_replay_runs_have_their_own_identities(self) -> None:
        first = uuid.UUID("33333333-3333-5333-8333-333333333333")
        second = uuid.UUID("44444444-4444-5444-8444-444444444444")
        assert _id(cohort=ShadowCohort.replay(first)) != _id(cohort=ShadowCohort.replay(second))

    def test_an_equivalent_spelling_of_the_bar_hashes_the_same(self) -> None:
        """Canonical form: the same instant in another offset is the same bar."""
        other = BAR.astimezone(timezone(timedelta(hours=-3)))
        assert other.isoformat() != BAR.isoformat()
        assert _id(source_bar_close=other) == _id()

    def test_a_naive_bar_close_is_refused(self) -> None:
        with pytest.raises(ValueError, match="tz-aware|naive"):
            _id(source_bar_close=datetime(2026, 9, 5, 12, 0))  # noqa: DTZ001


class TestSlotStateMachine:
    def test_an_armed_idle_slot_decides_on_a_trigger(self) -> None:
        after = next_slot(SlotState(armed=True, tracking_open=False), EvaluationState.TRIGGERED)
        assert after.decide is True
        assert after.armed is False

    def test_a_disarmed_slot_never_decides(self) -> None:
        after = next_slot(SlotState(armed=False, tracking_open=False), EvaluationState.TRIGGERED)
        assert after.decide is False
        assert after.armed is False

    def test_a_slot_already_tracking_never_takes_a_second_entry(self) -> None:
        after = next_slot(SlotState(armed=True, tracking_open=True), EvaluationState.TRIGGERED)
        assert after.decide is False

    def test_only_a_false_condition_rearms(self) -> None:
        after = next_slot(
            SlotState(armed=False, tracking_open=False), EvaluationState.NOT_TRIGGERED
        )
        assert after.armed is True

    def test_a_false_condition_while_still_tracking_does_not_rearm(self) -> None:
        after = next_slot(SlotState(armed=False, tracking_open=True), EvaluationState.NOT_TRIGGERED)
        assert after.armed is False

    @pytest.mark.parametrize("state", [EvaluationState.UNAVAILABLE, EvaluationState.INELIGIBLE])
    def test_a_bar_that_could_not_be_evaluated_proves_nothing(self, state: EvaluationState) -> None:
        """Missing data never re-arms (SHADOW-LAB.md §4)."""
        after = next_slot(SlotState(armed=False, tracking_open=False), state)
        assert after.armed is False
        assert after.decide is False
        assert after.advance_checkpoint is False

    def test_a_rejected_geometry_is_not_a_false_condition(self) -> None:
        after = next_slot(SlotState(armed=False, tracking_open=False), EvaluationState.REJECTED)
        assert after.armed is False
        assert after.decide is False
        assert after.advance_checkpoint is True

    def test_an_evaluated_bar_advances_the_checkpoint(self) -> None:
        after = next_slot(SlotState(armed=True, tracking_open=False), EvaluationState.NOT_TRIGGERED)
        assert after.advance_checkpoint is True
