"""T4.73c — the treasury reads of ``treasury_db`` see treasury rows only.

Astra's finding on T4.73b (``.claude/state/astra-review-review-T4.73b-send-path.md``):
since ``0056`` the generic spot swaps of ``infra/scripts/meme_spot_swap.py``
live in the same ``meme_treasury_swaps`` table, with ``input_mint`` /
``output_mint`` set (the ``0056`` CHECK makes the pair all-or-nothing; the
USDC->SOL treasury never sets it). Their ``sol_out_*`` are **token atoms**
— 10 402 273 WIF for a 0.02 SOL buy — not SOL. Without a mint filter:

* ``sol_inflow_since`` (read every reconcile tick by ``treasury_inflow_once``,
  even with the treasury off) adds 10.4 M "SOL" of inflow, and
  ``daily_loss_sol = day_start + inflow - equity`` goes negative for good —
  ``MEME_DAILY_LOSS_CAP_SOL`` never trips;
* ``submitted_swaps`` hands a stuck spot row to ``treasury_reconcile``,
  which marks it ``confirmed`` with ``max(0, sol_now - sol_before) = 0``;
* ``usdc_committed_last_24h`` counts the 0.02 SOL input as USDC spend.

The real proof — rows in a migrated Postgres — is
``test_treasury_db.py::test_a_spot_swap_row_is_neither_inflow_nor_spend_nor_picked_by_the_reconcile``.
This module pins the contract without Docker, the way ``test_treasury_inflow``
fakes the session: every one of the three statements the reader sends must
carry the ``input_mint IS NULL`` predicate, and the ``0056`` CHECK is what
makes that single column enough to name the whole pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_meme_executor import treasury_db

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)
TREASURY_ONLY = "input_mint IS NULL"


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Rows:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


@dataclass
class FakeSession:
    """Records the SQL text of every read, answers whatever the test set."""

    scalar_value: Any = Decimal("0.079")
    rows: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    statements: list[str] = field(default_factory=lambda: list[str]())

    async def scalar(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        self.statements.append(str(statement))
        return self.scalar_value

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Rows:
        self.statements.append(str(statement))
        return _Rows(self.rows)


def _only(session: FakeSession) -> str:
    assert len(session.statements) == 1, "one bounded read, not more"
    return session.statements[0]


async def test_sol_inflow_reads_treasury_rows_only() -> None:
    session = FakeSession()
    got = await treasury_db.sol_inflow_since(cast(Any, session), since=NOW)
    assert got == Decimal("0.079")
    sql = _only(session)
    assert TREASURY_ONLY in sql, sql
    assert "status IN ('submitted', 'confirmed')" in sql, "the T4.60 status rule is kept"


async def test_usdc_committed_reads_treasury_rows_only() -> None:
    session = FakeSession(scalar_value=Decimal("17"))
    got = await treasury_db.usdc_committed_last_24h(cast(Any, session), now=NOW)
    assert got == Decimal("17")
    sql = _only(session)
    assert TREASURY_ONLY in sql, sql
    assert "status IN ('submitted', 'confirmed')" in sql, "the T4.54b fix C rule is kept"


async def test_submitted_swaps_hands_the_reconcile_treasury_rows_only() -> None:
    session = FakeSession(
        rows=[
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "signature": "9" * 88,
                "requested_at": NOW,
                "wallet_sol_before": Decimal("0.2"),
            }
        ]
    )
    pending = await treasury_db.submitted_swaps(cast(Any, session))
    assert [row.signature for row in pending] == ["9" * 88]
    sql = _only(session)
    assert TREASURY_ONLY in sql, sql
    assert "status = 'submitted'" in sql and "signature IS NOT NULL" in sql
