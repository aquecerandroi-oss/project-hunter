"""T4.11 — what the desk payload gains for a bet that held through the
migration: ``mark_source``/``mark_stale_s`` on the bet, the switches on the
params, ``dead`` in the exit vocabulary, and the manual buy filed under the
active ``operator`` set (``operator/2`` since ``0029``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast, get_args

from hunter_api.repositories.meme_desk import OPERATOR_RULE_SET
from hunter_api.repositories.meme_desk_marks import MARK_COLUMNS_0029, with_marks_0029
from hunter_api.repositories.meme_desk_rows import BetRow, bet_from_mapping
from hunter_api.repositories.meme_desk_tables import meme_paper_bets
from hunter_api.schemas.meme_desk import ExitReason, MarkSource
from hunter_api.schemas.meme_tests import EXIT_REASON_PT
from hunter_api.services.meme_desk_out import params_from_json

from .test_meme_desk_service import _bet, _rule_set  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

NOW = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)


def _closed_on_the_pool(**overrides: Any) -> BetRow:
    rule_set = _rule_set()
    base: dict[str, Any] = {
        "mark_source": "pool_tape",
        "mark_stale_s": 930,
        "params": {
            "size_sol": "0.02",
            "target_x": "10",
            "trailing_pct": "50",
            "max_hold_s": 7200,
            "exit_on_migration": False,
            "trailing_arm_x": "3",
        },
    }
    base.update(overrides)
    return _bet(rule_set, uuid.uuid4(), **base)


def test_the_bet_payload_carries_the_marks_source_and_staleness() -> None:
    from hunter_api.services.meme_desk_out import _bet_out  # pyright: ignore[reportPrivateUsage]

    out = _bet_out(_closed_on_the_pool())
    assert out.mark_source == "pool_tape" and out.mark_stale_s == 930
    assert out.params.exit_on_migration is False and out.params.trailing_arm_x == Decimal(3)
    frozen = _bet_out(_bet(_rule_set(), uuid.uuid4()))
    assert frozen.mark_source is None and frozen.mark_stale_s is None
    assert frozen.params.exit_on_migration is None and frozen.params.trailing_arm_x is None


def test_a_row_mapped_without_the_columns_says_nothing_never_curve() -> None:
    mapping: dict[str, Any] = {
        "id": uuid.uuid4(),
        "proposal_id": uuid.uuid4(),
        "rule_set_id": uuid.uuid4(),
        "mint": "MINT",
        "mode": "paper",
        "status": "open",
        "entry_at": NOW - timedelta(minutes=2),
        "entry": {},
        "initial_risk_sol": Decimal("0.02"),
        "params": {},
        "exit_at": None,
        "exit": None,
        "pnl_sol": None,
        "r_multiple": None,
        "mark_sol": None,
        "mark_at": None,
        "high_water_x": None,
        "sol_usd_at_entry": None,
        "sol_usd_at_exit": None,
    }
    row = bet_from_mapping(mapping)  # type: ignore[arg-type]
    assert row.mark_source is None and row.mark_stale_s is None and row.leg == "single"
    with_columns = bet_from_mapping({**mapping, "mark_source": "curve", "mark_stale_s": 0})  # type: ignore[arg-type]
    assert with_columns.mark_source == "curve" and with_columns.mark_stale_s == 0


def test_the_params_read_the_switches_tolerantly() -> None:
    params = params_from_json({"size_sol": "0.05", "exit_on_migration": "no", "trailing_arm_x": 3})
    assert params.exit_on_migration is None, "a string is not a switch"
    assert params.trailing_arm_x == Decimal(3)
    assert params_from_json(None).exit_on_migration is None


def test_dead_is_in_the_exit_vocabulary_and_the_mark_sources_are_two() -> None:
    assert "dead" in get_args(ExitReason)
    assert EXIT_REASON_PT["dead"] == "morta", "the tests record and its CSV print the word"
    assert set(get_args(MarkSource)) == {"curve", "pool_tape"}
    assert OPERATOR_RULE_SET == ("operator", "2"), "0029 retired operator/1"


# ---- the desk on a database still at 0028 ------------------------------------------------


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class _Session:
    """Answers the ``0029`` probe with ``columns`` and the read with ``rows``,
    and records what was asked — the database is the only thing faked."""

    def __init__(self, columns: int, rows: list[dict[str, Any]]) -> None:
        self.columns = columns
        self.rows = rows
        self.asked: list[str] = []

    async def scalar(self, _statement: Any) -> int:
        self.asked.append("probe")
        return self.columns

    async def execute(self, _statement: Any) -> _Result:
        self.asked.append("read")
        return _Result(self.rows)


def test_the_shared_bet_table_does_not_declare_the_0029_columns() -> None:
    """``select(meme_paper_bets)`` — the desk's and T4.13's read — must keep
    working on a database still at ``0028``: the two columns are read apart."""
    declared = set(meme_paper_bets.c.keys())
    assert not declared & set(MARK_COLUMNS_0029), declared & set(MARK_COLUMNS_0029)
    assert {"leg", "parent_bet_id", "mark_sol"} <= declared


async def test_below_0029_no_mark_column_is_read_and_the_rows_say_nothing() -> None:
    bet = _bet(_rule_set(), uuid.uuid4())
    session = _Session(columns=0, rows=[])
    out = await with_marks_0029(cast("AsyncSession", session), {bet.id: bet})
    assert session.asked == ["probe"], "never a read of a column the database does not have"
    assert out[bet.id] is bet
    assert out[bet.id].mark_source is None and out[bet.id].mark_stale_s is None


async def test_at_0029_the_marks_are_folded_in_by_id_and_nothing_is_invented() -> None:
    bet = _bet(_rule_set(), uuid.uuid4())
    stranger = uuid.uuid4()
    session = _Session(
        columns=2,
        rows=[
            {"id": bet.id, "mark_source": "pool_tape", "mark_stale_s": 930},
            {"id": stranger, "mark_source": "curve", "mark_stale_s": None},
        ],
    )
    out = await with_marks_0029(cast("AsyncSession", session), {bet.id: bet})
    assert session.asked == ["probe", "read"]
    assert out[bet.id].mark_source == "pool_tape" and out[bet.id].mark_stale_s == 930
    assert out[bet.id].id == bet.id and out[bet.id].params == bet.params, "the rest is the row"
    assert stranger not in out, "a row nobody asked for is not a desk row"


async def test_nothing_to_read_asks_the_database_nothing() -> None:
    session = _Session(columns=2, rows=[])
    assert await with_marks_0029(cast("AsyncSession", session), {}) == {}
    assert session.asked == []
