"""T4.28g — which mints the rug-risk reader must cover, and when it may defer.

**Measured (R5, 16/09/2026, ``obsidian/03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa.md``):**
13 of the day's 16 real orders were refused ``bundled_share_unmeasurable`` and the
mint's ``meme_risk_snapshots`` row landed a median **103 s after** the executor had
already decided. The cause was not the market: ``_PENDING_OPERATOR`` (T4.28b) only
selected operator rows still ``status = 'proposed'``, and the stage-1 executor moves
a row to ``approved`` 3–10 s after it is filed (``hunter_core.execution.meme.approval.
DECIDE_PROPOSAL``) and then to ``rejected``. From the reader's next 60 s tick on, the
mint had vanished from the candidate set — the reader stopped asking about exactly the
coins the executor was about to judge.

Nothing here loosens a check: the reader reads *more mints, sooner*; the 25 checks of
``docs/RISK_ENGINE_MEME.md`` §4 and every limit are untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_core.db.models.meme_lab import PROPOSAL_STATUSES
from hunter_core.db.models.meme_live import LIVE_ORDER_STATUSES
from hunter_meme_worker.repo_tape import (
    LIVE_ORDER_PENDING_STATUSES,
    PENDING_LOOKBACK_S,
    PENDING_PROPOSAL_STATUSES,
    pending_mints_sql,
)
from hunter_meme_worker.risk import RiskReader

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 16, 14, 0, tzinfo=UTC)


class TestCandidateStatuses:
    def test_an_approved_operator_proposal_is_still_a_candidate(self) -> None:
        """The whole finding: ``approved`` is the state the stage-1 executor puts the
        row in *before* it admits the buy. A reader that only sees ``proposed`` has a
        3–10 s window on a 60 s tick — it loses the race by construction."""
        assert PENDING_PROPOSAL_STATUSES == ("proposed", "approved")

    def test_there_is_no_suggested_status_to_cover(self) -> None:
        """``decision = suggested`` in ``docs/RISK_ENGINE_MEME.md`` §3.5 names the
        *payload* the robot copies from the rule set, not a row state. ``suggested``
        is not in the CHECK's vocabulary, and a query naming it would match nothing
        for ever — silently."""
        assert "suggested" not in PROPOSAL_STATUSES
        assert set(PENDING_PROPOSAL_STATUSES) <= set(PROPOSAL_STATUSES)

    def test_the_live_order_states_covered_are_the_pre_fill_ones(self) -> None:
        """``meme_live_orders`` before a fill: admitted → simulated →
        submitted_unconfirmed. A settled row (``confirmed``/``refused``/``failed``)
        is not a decision waiting on a rug read."""
        assert LIVE_ORDER_PENDING_STATUSES == (
            "admitted",
            "simulated",
            "submitted_unconfirmed",
        )
        assert set(LIVE_ORDER_PENDING_STATUSES) <= set(LIVE_ORDER_STATUSES)
        assert not set(LIVE_ORDER_PENDING_STATUSES) & {"confirmed", "refused", "failed"}


class TestQueryIsBounded:
    """The post-incident rule (``docs/DATABASE.md`` §26.4): a new per-tick query
    carries a time window and rides an index, or it is not merged."""

    def test_every_branch_carries_the_ten_minute_window(self) -> None:
        sql = pending_mints_sql()
        assert PENDING_LOOKBACK_S == 600
        assert sql.count("p.proposed_at >= :since") == len(PENDING_PROPOSAL_STATUSES)
        assert sql.count("o.received_at >= :since") == 1

    def test_each_branch_filters_one_status_so_it_rides_its_index(self) -> None:
        """``ix_meme_proposals_status_proposed_at`` is ``(status, proposed_at)`` and
        ``ix_meme_live_orders_status_received_at`` is ``(status, received_at)``: one
        equality on the leading column per branch, the window on the second."""
        sql = pending_mints_sql()
        for status in PENDING_PROPOSAL_STATUSES:
            assert f"p.status = '{status}'" in sql
        assert "o.status IN ('admitted', 'simulated', 'submitted_unconfirmed')" in sql
        assert " UNION " in sql

    def test_a_proposal_still_awaiting_a_click_must_not_be_expired(self) -> None:
        """A ``proposed`` row past ``expires_at`` is dead to the desk and to the
        robot; reading its rug numbers would spend the budget on nothing."""
        sql = pending_mints_sql()
        assert "p.expires_at > :now" in sql


class TestFirstReadIsNotDeferred:
    """The reader's own throttle (1 read/mint/``risk_min_interval_s``, 300 s) must
    not push the *first* read of a mint to a later tick — that would hand back the
    103 s the query above just removed."""

    def _reader(self) -> RiskReader:
        return RiskReader(client=None, min_interval_s=300)  # type: ignore[arg-type]

    def test_a_mint_seen_for_the_first_time_is_due_on_this_tick(self) -> None:
        reader = self._reader()
        assert reader.due({"NEWMINT"}, T0) == ["NEWMINT"]

    def test_a_mint_read_thirty_seconds_ago_still_waits(self) -> None:
        reader = self._reader()
        reader.last_read["SEEN"] = T0
        assert reader.due({"SEEN"}, T0 + timedelta(seconds=30)) == []

    def test_a_throttled_mint_never_hides_a_first_read(self) -> None:
        """The failure this guards: a per-mint throttle implemented as "one read per
        tick" or "skip the tick if anything is cooling" would defer the brand-new
        operator mint behind a coin read 30 s ago."""
        reader = self._reader()
        reader.last_read["SEEN"] = T0
        assert reader.due({"SEEN", "NEWMINT"}, T0 + timedelta(seconds=30)) == ["NEWMINT"]

    def test_after_the_interval_the_mint_is_due_again(self) -> None:
        reader = self._reader()
        reader.last_read["SEEN"] = T0
        assert reader.due({"SEEN"}, T0 + timedelta(seconds=300)) == ["SEEN"]
