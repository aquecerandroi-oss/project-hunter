"""I1 (EXP-M26): pure tests of the mature-retention rule — no IO, no clock of
its own. See ``docs/design/exp-m26-grafico-moedas-maduras.md`` §1.6 and
``obsidian/11-KNOWLEDGE/KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta.md``
for why this budget exists at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_meme_worker.tracker_mature import (
    MATURE_MAX_AGE_S,
    MATURE_MCAP_FRESHNESS_S,
    MATURE_MIN_AGE_S,
    is_mature_eligible,
    mature_report,
    select_mature,
)
from hunter_meme_worker.tracker_types import TrackedMint

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _mature(
    mint: str,
    *,
    age_s: int = 3600,
    mcap_sol: Decimal | None = Decimal(30),
    mcap_age_s: int | None = 10,
    **kw: Any,
) -> TrackedMint:
    created = NOW - timedelta(seconds=age_s)
    observed = None if mcap_age_s is None else NOW - timedelta(seconds=mcap_age_s)
    return TrackedMint(
        mint=mint,
        first_seen_at=created,
        created_at=created,
        mcap_sol=mcap_sol,
        mcap_observed_at=observed,
        **kw,
    )


def test_eligible_inside_the_5_to_120_minute_window() -> None:
    assert is_mature_eligible(_mature("m", age_s=MATURE_MIN_AGE_S), NOW)
    assert is_mature_eligible(_mature("m", age_s=MATURE_MAX_AGE_S), NOW)
    assert is_mature_eligible(_mature("m", age_s=3600), NOW)


def test_ineligible_younger_than_5_minutes_or_older_than_120() -> None:
    assert not is_mature_eligible(_mature("young", age_s=MATURE_MIN_AGE_S - 1), NOW)
    assert not is_mature_eligible(_mature("old", age_s=MATURE_MAX_AGE_S + 1), NOW)


def test_ineligible_without_a_known_creation_time() -> None:
    tracked = TrackedMint(
        mint="ageless", first_seen_at=NOW, mcap_sol=Decimal(30), mcap_observed_at=NOW
    )
    assert not is_mature_eligible(tracked, NOW)


def test_ineligible_when_finished() -> None:
    assert not is_mature_eligible(_mature("done", complete=True), NOW)
    assert not is_mature_eligible(_mature("gone", migrated=True), NOW)


def test_ineligible_with_an_active_mayhem_agent() -> None:
    assert not is_mature_eligible(_mature("m1", mayhem_state="active"), NOW)
    assert not is_mature_eligible(_mature("m2", mayhem_state="paused"), NOW)


def test_a_completed_mayhem_agent_does_not_exclude_it() -> None:
    assert is_mature_eligible(_mature("m", mayhem_state="completed"), NOW)


def test_ineligible_with_an_unsupported_quote() -> None:
    assert not is_mature_eligible(_mature("usdc", quote_unsupported=True), NOW)


def test_ineligible_without_any_mcap_reading() -> None:
    assert not is_mature_eligible(_mature("m", mcap_sol=None, mcap_age_s=None), NOW)


def test_ineligible_with_a_stale_mcap_reading() -> None:
    assert not is_mature_eligible(_mature("stale", mcap_age_s=MATURE_MCAP_FRESHNESS_S + 1), NOW)


def test_a_reading_exactly_at_the_freshness_ceiling_still_counts() -> None:
    assert is_mature_eligible(_mature("edge", mcap_age_s=MATURE_MCAP_FRESHNESS_S), NOW)


def test_select_mature_orders_by_mcap_sol_descending() -> None:
    small = _mature("small", mcap_sol=Decimal(5))
    big = _mature("big", mcap_sol=Decimal(50))
    mid = _mature("mid", mcap_sol=Decimal(20))
    assert select_mature([small, big, mid], NOW, 3) == ("big", "mid", "small")


def test_select_mature_ties_break_by_mint() -> None:
    a = _mature("bbb", mcap_sol=Decimal(10))
    b = _mature("aaa", mcap_sol=Decimal(10))
    assert select_mature([a, b], NOW, 2) == ("aaa", "bbb")


def test_select_mature_respects_the_k_limit() -> None:
    coins = [_mature(f"m{i}", mcap_sol=Decimal(i)) for i in range(10)]
    kept = select_mature(coins, NOW, 3)
    assert len(kept) == 3
    assert kept == ("m9", "m8", "m7")


def test_select_mature_k_zero_or_negative_keeps_nothing() -> None:
    coins = [_mature("m", mcap_sol=Decimal(30))]
    assert select_mature(coins, NOW, 0) == ()
    assert select_mature(coins, NOW, -1) == ()


def test_select_mature_ignores_ineligible_candidates() -> None:
    eligible = _mature("keep", mcap_sol=Decimal(30))
    young = _mature("young", age_s=10, mcap_sol=Decimal(1000))
    finished = _mature("done", complete=True, mcap_sol=Decimal(1000))
    assert select_mature([eligible, young, finished], NOW, 5) == ("keep",)


def test_select_mature_is_causal_a_later_arriving_reading_does_not_move_the_choice() -> None:
    """The proof the design's §1.6 asks for: what has not yet arrived at ``now``
    cannot outrank what has, however large it will turn out to be."""
    already_arrived = _mature("early", mcap_sol=Decimal(40), mcap_age_s=5)
    not_yet_arrived = _mature("late", mcap_sol=Decimal(1000), mcap_age_s=None)
    assert select_mature([already_arrived, not_yet_arrived], NOW, 1) == ("early",)
    # Once the late reading has actually arrived (and is fresh), it may win.
    arrived_now = _mature("late", mcap_sol=Decimal(1000), mcap_age_s=1)
    assert select_mature([already_arrived, arrived_now], NOW, 1) == ("late",)


def test_mature_report_separates_kept_ranked_out_and_stale() -> None:
    kept = _mature("kept", mcap_sol=Decimal(50))
    ranked_out = _mature("ranked_out", mcap_sol=Decimal(10))
    stale = _mature("stale", mcap_sol=Decimal(1000), mcap_age_s=MATURE_MCAP_FRESHNESS_S + 1)
    report = mature_report([kept, ranked_out, stale], NOW, 1)
    assert report.kept == ("kept",)
    assert report.ranked_out == ("ranked_out",)
    assert report.stale_mcap == ("stale",)
    assert set(report.eligible) == {"kept", "ranked_out"}
