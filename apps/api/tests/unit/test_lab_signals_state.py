"""``tracking_states_for_lab_state`` (T3.37a) — the server-side mirror of the
web's ``lab-signal-segments.ts``'s ``matchesSegment``. One fixture per state,
per the brief.
"""

from __future__ import annotations

from hunter_api.repositories.lab_common import (
    PENDING_TRACKING_STATES,
    tracking_states_for_lab_state,
)
from hunter_core.domain.enums import ShadowTrackingState


def test_closed_maps_to_terminal_only() -> None:
    assert tracking_states_for_lab_state("closed") == (ShadowTrackingState.TERMINAL,)


def test_open_maps_to_active_only() -> None:
    assert tracking_states_for_lab_state("open") == (ShadowTrackingState.ACTIVE,)


def test_pending_folds_pending_entry_no_entry_and_censored() -> None:
    assert tracking_states_for_lab_state("pending") == (
        ShadowTrackingState.PENDING_ENTRY,
        ShadowTrackingState.NO_ENTRY,
        ShadowTrackingState.CENSORED,
    )
    assert set(PENDING_TRACKING_STATES) == {
        ShadowTrackingState.PENDING_ENTRY,
        ShadowTrackingState.NO_ENTRY,
        ShadowTrackingState.CENSORED,
    }


def test_all_means_no_filter() -> None:
    assert tracking_states_for_lab_state("all") is None


def test_every_tracking_state_is_covered_by_exactly_one_non_all_segment() -> None:
    """No ``ShadowTrackingState`` member is left out or double-counted across
    ``closed``/``open``/``pending`` -- the invariant the web's totals math
    (``segmentCounts``) depends on.
    """
    seen: set[ShadowTrackingState] = set()
    for segment in ("closed", "open", "pending"):
        states = tracking_states_for_lab_state(segment)  # type: ignore[arg-type]
        assert states is not None
        assert seen.isdisjoint(states)
        seen.update(states)
    assert seen == set(ShadowTrackingState)
