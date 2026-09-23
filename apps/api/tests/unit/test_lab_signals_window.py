"""T4.82: ``emitted_from``/``emitted_to`` on ``GET /lab/shadow/signals``.

Without a time cut the confluence screen would have to page the market's whole
history to find fifteen minutes (design §7a item 2). The window is half-open
``[emitted_from, emitted_to)``, the same shape the candles take, and it cuts on
``agent_signals.emitted_at`` — the column ``0014_lab_signals_indexes`` can
actually serve (``lab_common.DECISION_AT``), never the ``decision_at`` copy
inside ``supporting_features``, which is a text cast and therefore unindexable.

Compiled SQL only; no database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql

from hunter_api.repositories.lab_signals import emitted_window_filters

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 23, 14, 45, tzinfo=UTC)


def _sql(emitted_from: datetime | None, emitted_to: datetime | None) -> list[str]:
    return [
        str(clause.compile(dialect=postgresql.dialect()))
        for clause in emitted_window_filters(emitted_from=emitted_from, emitted_to=emitted_to)
    ]


def test_no_bounds_adds_no_filter_at_all() -> None:
    """Backward compatible: the listing without a window is the one that
    shipped before T4.82, totals included."""
    assert _sql(None, None) == []


def test_emitted_from_is_inclusive() -> None:
    (clause,) = _sql(NOW - timedelta(minutes=15), None)
    assert "agent_signals.emitted_at >=" in clause


def test_emitted_to_is_exclusive() -> None:
    (clause,) = _sql(None, NOW)
    assert "agent_signals.emitted_at <" in clause
    assert "agent_signals.emitted_at <=" not in clause, "half-open, like the candles window"


def test_both_bounds_produce_two_filters_on_the_indexed_column() -> None:
    clauses = _sql(NOW - timedelta(minutes=15), NOW + timedelta(minutes=15))
    assert len(clauses) == 2
    assert all("agent_signals.emitted_at" in clause for clause in clauses)
    assert not any("supporting_features" in clause for clause in clauses), (
        "never the text-cast copy of decision_at — it cannot be indexed"
    )
