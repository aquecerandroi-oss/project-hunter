"""T3.14b review item 1 — a refused candidate is named once per (signal, reason).

Unit, no database and no Docker: :func:`report_refusal` is a pure function of a
signal, a reason and the ``reported`` map, so the once-per-row doctrine
``admission_cycle.report_unreadable`` already proved for a manual request is
proved here the same way, for the bridge's own 1 s loop
(:mod:`hunter_execution_worker.bridge_screen`).

The bridge's own durable queue (``bridge_repo.pending_signals``) re-reads a
still-eligible signal for up to 240 s (twice the 120 s entry window), so
without this dedupe a single refused signal wrote one log line and one counter
increment a second for the whole time it stayed in the lookback — up to 240 of
each (review-T3.14.md item 1).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from hunter_core.domain.enums import TradeDirection
from hunter_execution_worker.bridge_repo import ShadowSignal
from hunter_execution_worker.bridge_screen import report_refusal

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def _signal(signal_id: uuid.UUID | None = None) -> ShadowSignal:
    return ShadowSignal(
        signal_id=signal_id or uuid.uuid4(),
        strategy_version_id=uuid.uuid4(),
        perp_market_id=uuid.uuid4(),
        exchange_id=uuid.uuid4(),
        base_asset_id=uuid.uuid4(),
        quote_asset_id=uuid.uuid4(),
        direction=TradeDirection.LONG,
        entry_ref=Decimal(100),
        stop=Decimal("97.5"),
        target=Decimal(105),
        assumed_costs=None,
        source_bar_close=NOW,
        emitted_at=NOW,
        purpose="paper",
        envelope_purpose="paper",
        cohort="prospective",
        version_active=True,
    )


def _refusal_lines(logs: object) -> list[dict[str, object]]:
    return [line for line in logs if line.get("event") == "bridge_candidate_refused"]  # type: ignore[union-attr]


class TestARefusalIsNamedOncePerSignalAndReason:
    def test_two_hundred_and_forty_passes_over_the_same_refusal_write_one_line(self) -> None:
        signal = _signal()
        reported: dict[uuid.UUID, str] = {}

        with capture_logs() as logs:
            results = [
                report_refusal(signal, "beta_unavailable", reported=reported) for _ in range(240)
            ]

        assert results == [True] + [False] * 239
        lines = _refusal_lines(logs)
        assert len(lines) == 1
        assert lines[0]["signal_id"] == str(signal.signal_id)
        assert lines[0]["reason"] == "beta_unavailable"

    def test_a_different_reason_for_the_same_signal_is_named_again(self) -> None:
        """A transition — not the level — is what is worth a new line."""
        signal = _signal()
        reported: dict[uuid.UUID, str] = {}

        with capture_logs() as logs:
            report_refusal(signal, "beta_unavailable", reported=reported)
            report_refusal(signal, "beta_unavailable", reported=reported)
            report_refusal(signal, "duplicate_position", reported=reported)
            report_refusal(signal, "duplicate_position", reported=reported)

        reasons = [line["reason"] for line in _refusal_lines(logs)]
        assert reasons == ["beta_unavailable", "duplicate_position"]

    def test_two_signals_are_named_independently(self) -> None:
        first, second = _signal(), _signal()
        reported: dict[uuid.UUID, str] = {}

        with capture_logs() as logs:
            report_refusal(first, "beta_unavailable", reported=reported)
            report_refusal(second, "beta_unavailable", reported=reported)
            report_refusal(first, "beta_unavailable", reported=reported)
            report_refusal(second, "beta_unavailable", reported=reported)

        named = [line["signal_id"] for line in _refusal_lines(logs)]
        assert named == [str(first.signal_id), str(second.signal_id)]

    def test_a_forgotten_signal_is_named_again(self) -> None:
        """``bridge._rank`` prunes ``reported`` to what ``pending_signals`` still
        returns, so a signal that left the lookback and came back (a fresh
        window, a redelivery) is not silenced by a stale entry — same doctrine
        as ``report_unreadable``'s pruning."""
        signal = _signal()
        reported: dict[uuid.UUID, str] = {signal.signal_id: "beta_unavailable"}
        del reported[signal.signal_id]  # what pruning does once it is no longer pending

        with capture_logs() as logs:
            report_refusal(signal, "beta_unavailable", reported=reported)

        assert len(_refusal_lines(logs)) == 1

    def test_without_a_map_every_call_names_and_counts(self) -> None:
        signal = _signal()

        with capture_logs() as logs:
            report_refusal(signal, "beta_unavailable")
            report_refusal(signal, "beta_unavailable")

        assert len(_refusal_lines(logs)) == 2
