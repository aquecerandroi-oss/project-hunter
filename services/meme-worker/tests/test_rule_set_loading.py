"""database-architect (review of T4.91): ``lab_repo.load_active_rule_sets`` is
the only loader of the Lab tick (``lab.py``) and the wallet step
(``wallets.py``). One active row whose ``params`` do not parse — a hand edit,
a future seed — used to raise out of the list comprehension and take every
other set down with it, the real desk ``operator/5`` included. Now that row is
skipped, logged at ``error`` and counted; the others load.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hunter_meme_worker.lab_repo import load_active_rule_sets
from hunter_meme_worker.metrics import meme_rule_set_load_failed_total
from hunter_meme_worker.rule_set_loading import specs_from_rows

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

OPERATOR_5 = "01994d00-6c1a-7000-8000-000000000011"


def _failed(label: str) -> float:
    counter: Any = meme_rule_set_load_failed_total.labels(rule_set=label)
    return float(counter._value.get())


def _row(name: str, **params: Any) -> dict[str, Any]:
    from .test_proposals_flow import FLOW_PARAMS

    return {
        "id": str(uuid4()),
        "name": name,
        "version": "1",
        "kind": "research_only",
        "exp_ref": "EXP-X",
        "status": "active",
        "code_ref": "test",
        "params": {**FLOW_PARAMS, **params},
    }


@pytest.mark.unit
def test_a_row_that_does_not_parse_is_skipped_logged_and_counted() -> None:
    before = _failed("broken/1")
    rows = [
        _row("good"),
        _row("broken", entry_pullback_pct="5"),  # the switch without its window: never loads
        _row("also_good"),
    ]
    specs = specs_from_rows(rows)
    assert [s.name for s in specs] == ["good", "also_good"]
    assert _failed("broken/1") == before + 1


@pytest.mark.integration
async def test_operator_5_still_loads_beside_a_broken_active_row(db_engine: AsyncEngine) -> None:
    """Against the real table, inside a transaction rolled back at the end so
    the shared database never keeps the broken row."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(
                text(
                    "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, "
                    "  exp_ref) VALUES (:id, :name, '1', 'research_only', "
                    "  CAST(:params AS jsonb), 'test', 'EXP-X')"
                ),
                {
                    "id": str(uuid4()),
                    "name": f"broken_{uuid4().hex[:8]}",
                    "params": '{"clock": "15s", "size_sol": 0.05}',  # a float, no gate: never loads
                },
            )
            session = AsyncSession(bind=connection)
            specs = await load_active_rule_sets(session)
            await session.close()
        finally:
            await transaction.rollback()
    assert OPERATOR_5 in {s.id for s in specs}
    assert not any(s.name.startswith("broken_") for s in specs)
