"""``history_v2``: the sparse sampling the 27/09 disk decision authorized.

``docs/design/retencao-e-disco-2026-09-27.md`` §3/§6 step 3(a): a preserved sample
every ``interval`` (300 s by default) **or** when ``status``/``stage`` changes —
the two things the Radar filters on — and nothing else. Every other ``history_v1``
trigger (score delta, direction, regime, versions, eligibility, quality) stops
writing a row on its own; the row that *is* written still carries the whole
envelope, so each preserved sample stays recomputable.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import OpportunityStage, OpportunityStatus, TradeDirection
from hunter_indicators.opportunity import (
    HISTORY_POLICY_V2,
    HISTORY_POLICY_VERSION,
    HistoryMark,
    should_record_history,
    sparse_history_policy,
)
from hunter_indicators.opportunity.history import (
    REASON_FIRST,
    REASON_INTERVAL,
    REASON_STAGE,
    REASON_STALE,
    REASON_STATUS,
)
from packages.indicators.tests.scoring import OBSERVED_AT

SECOND = timedelta(seconds=1)
VERSIONS = {"scorer": "opportunity_v1", "weights": "v2"}
V2 = sparse_history_policy(timedelta(seconds=300))


def mark(seconds: int = 0, score: str = "50", **kwargs: Any) -> HistoryMark:
    base = HistoryMark(
        ts=OBSERVED_AT + seconds * SECOND,
        score=Decimal(score),
        status=OpportunityStatus.WATCHING,
        stage=OpportunityStage.NONE,
        direction=TradeDirection.LONG,
        stage_direction=TradeDirection.NEUTRAL,
        regime="bull/normal",
        quality="liquidity:1:1/1",
        eligible=True,
        versions=VERSIONS,
    )
    return replace(base, **kwargs)


def test_the_policy_is_versioned_apart_from_v1() -> None:
    assert V2.version == HISTORY_POLICY_V2 == "history_v2"
    assert HISTORY_POLICY_VERSION == "history_v1"
    assert V2.interval == timedelta(seconds=300)


def test_the_first_sample_is_still_kept() -> None:
    verdict = should_record_history(None, mark(), V2)
    assert verdict.record is True
    assert verdict.reasons == (REASON_FIRST,)
    assert verdict.policy_version == "history_v2"


def test_299_seconds_write_nothing_and_300_write_the_heartbeat() -> None:
    assert should_record_history(mark(0), mark(299, "70"), V2).record is False
    verdict = should_record_history(mark(0), mark(300, "70"), V2)
    assert verdict.reasons == (REASON_INTERVAL,)


@pytest.mark.parametrize(
    "change",
    [
        {"score": "90"},
        {"direction": TradeDirection.SHORT},
        {"stage_direction": TradeDirection.SHORT},
        {"regime": "bear/high"},
        {"versions": {**VERSIONS, "weights": "v3"}},
        {"eligible": False},
        {"quality": "liquidity:0:0/1"},
    ],
    ids=["score", "direction", "stage_direction", "regime", "versions", "eligible", "quality"],
)
def test_the_triggers_v2_drops_write_no_row_inside_the_interval(change: dict[str, Any]) -> None:
    verdict = should_record_history(mark(0), mark(60, **change), V2)
    assert verdict.record is False
    assert verdict.reasons == ()


def test_a_status_change_is_still_a_row_inside_the_interval() -> None:
    """The HOT excursion between two heartbeats (WATCHING -> HOT -> WATCHING in
    three minutes) would vanish under a hard five-minute cap (Astra, 27/09)."""
    verdict = should_record_history(mark(0), mark(60, status=OpportunityStatus.HOT), V2)
    assert verdict.reasons == (REASON_STATUS,)


def test_a_stage_change_is_still_a_row_inside_the_interval() -> None:
    verdict = should_record_history(mark(0), mark(60, stage=OpportunityStage.EARLY), V2)
    assert verdict.reasons == (REASON_STAGE,)


def test_a_status_change_after_the_interval_reports_both_reasons() -> None:
    verdict = should_record_history(mark(0), mark(301, status=OpportunityStatus.HOT), V2)
    assert verdict.reasons == (REASON_STATUS, REASON_INTERVAL)


def test_a_redelivered_or_older_sample_still_writes_nothing() -> None:
    assert should_record_history(mark(10), mark(10), V2).reasons == (REASON_STALE,)
    assert should_record_history(mark(400), mark(10), V2).reasons == (REASON_STALE,)


@pytest.mark.parametrize("seconds", [0, -5])
def test_a_non_positive_interval_is_refused(seconds: int) -> None:
    with pytest.raises(ValueError, match="interval"):
        sparse_history_policy(timedelta(seconds=seconds))


def test_the_verdict_carries_the_interval_that_judged_it() -> None:
    """Quant review F2: a sparse row says under which heartbeat it was kept."""
    assert should_record_history(mark(0), mark(300), V2).interval_s == 300
    assert should_record_history(None, mark(), V2).interval_s == 300
    assert should_record_history(mark(0), mark(60), V2).as_wire()["interval_s"] == 300
