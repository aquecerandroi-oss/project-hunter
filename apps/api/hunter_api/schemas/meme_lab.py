"""``GET /api/v1/orgs/{org_id}/meme/lab`` — the Lab's scoreboard per rule set per
Brasília day, the distance to the goal, and the sources (T4.6, contract
``.claude/state/contrato-T4.6-T4.7-mesa-meme.md``).

Every money/ratio field is ``DecimalStr`` (never a float over the wire) and
every "no value" is ``None`` **with a reason**, the ``lab_common.py``
discipline. Two labels ride on every payload: this is **paper** (no key, no
live flag exist in the process that wrote these rows) and the goal block is
**arithmetic about the target**, never a forecast
(``obsidian/06-DECISIONS/2026-09-12-meta-7m-e-lab-meme.md`` §2).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr

__all__ = [
    "MEME_LAB_LABEL",
    "MEME_LAB_GOAL_LABEL",
    "DayScoreOut",
    "GoalOut",
    "MemeLabOut",
    "NullableDecimalOut",
    "RuleSetBoardOut",
    "RuleSetCeilingsOut",
    "SolUsdOut",
    "SourcesOut",
    "WalletOut",
]

MEME_LAB_LABEL = (
    "PAPEL — nenhuma transação real; a chave e a flag ao vivo não existem neste processo"
)
"""The contract's permanent label, in the payload itself."""

MEME_LAB_GOAL_LABEL = "meta — conta sobre o alvo declarado, nunca previsão de retorno"
"""The decision note's own rule: the goal block answers what the target
*requires*, never what the Lab will deliver."""

LabStatus = Literal[
    "alive", "stalled", "never", "disabled", "heartbeat_missing", "redis_unavailable"
]


class NullableDecimalOut(BaseModel):
    """A number that is ``null`` with a reason instead of a zero."""

    value: DecimalStr | None
    reason: str | None = None


class SolUsdOut(BaseModel):
    """An observed SOL/USD quote — the number never travels without its source."""

    price_usd: DecimalStr
    source: str
    observed_at: datetime
    origin: Literal["worker_heartbeat", "last_bet"]


class RuleSetCeilingsOut(BaseModel):
    size_sol: DecimalStr
    target_x: DecimalStr
    trailing_pct: DecimalStr
    max_hold_s: int
    wallet_max_sol: DecimalStr
    max_sol_per_bet: DecimalStr
    daily_loss_cap_sol: DecimalStr


class WalletOut(BaseModel):
    """Derived from ``meme_paper_bets`` alone: ``balance = wallet_max + Σ closed
    pnl − Σ open stake``; ``equity = balance + Σ open marks``."""

    balance_sol: DecimalStr
    open_positions: int
    open_exposure_sol: DecimalStr
    open_marks_sol: DecimalStr
    equity_sol: DecimalStr
    realized_total_sol: DecimalStr
    realized_today_sol: DecimalStr


class DayScoreOut(BaseModel):
    """One row of ``meme_lab_scoreboard_v1``: one rule set, one Brasília day of entry."""

    day: date
    bets: int
    closed: int
    wins: int
    win_rate: NullableDecimalOut
    pnl_sol: NullableDecimalOut
    pnl_usd: NullableDecimalOut
    unpriced_usd: int
    r_sum: NullableDecimalOut
    avg_r: NullableDecimalOut
    max_drawdown_sol: NullableDecimalOut
    rugs: int


class RuleSetBoardOut(BaseModel):
    id: uuid.UUID
    name: str
    version: str
    kind: Literal["research_only", "operator"]
    exp_ref: str | None
    status: Literal["active", "retired"]
    code_ref: str
    ceilings: RuleSetCeilingsOut
    wallet: WalletOut
    today: DayScoreOut | None
    today_reason: str | None = None
    """``no_bets_today`` when ``today`` is ``None``."""
    days: list[DayScoreOut]
    """Newest first, at most ``days_limit`` of them (a bounded window, not a
    paginated list — the scoreboard is one screen)."""


class GoalOut(BaseModel):
    label: str = MEME_LAB_GOAL_LABEL
    target_usd: DecimalStr
    horizon_days: int
    clock_start: date
    clock_start_source: str
    days_elapsed: int
    days_remaining: int
    capital_sol: DecimalStr
    capital_usd: NullableDecimalOut
    sol_usd: SolUsdOut | None
    sol_usd_reason: str | None = None
    required_daily_return: NullableDecimalOut
    """``(target / capital) ^ (1 / days_remaining) − 1``, recomputed from the
    capital of *now* and the days still left — never the day-0 table."""
    measured_daily_return: NullableDecimalOut
    """``pnl_today / (equity_now − pnl_today)`` over closed bets of the day."""
    pnl_today_sol: DecimalStr


class SourcesOut(BaseModel):
    """§Semântica 5: a stopped loop must be visible, not silent."""

    heartbeat_key: str
    heartbeat_ts: datetime | None
    heartbeat_age_s: int | None
    lab_enabled: bool | None
    lab_last_tick_at: datetime | None
    lab_tick_age_s: int | None
    lab_status: LabStatus
    lab_alive: bool
    stalled_after_s: int
    tick_minute: datetime | None
    rule_sets_active: int | None
    rows_evaluated: int | None
    gate_refusals: dict[str, dict[str, int]]
    proposals_total: int | None
    fills_total: int | None
    unfilled_total: int | None
    closes_total: int | None
    bets_open: int | None
    sol_usd_error: str | None


class MemeLabOut(BaseModel):
    label: str = MEME_LAB_LABEL
    as_of: datetime
    day: date
    """Today in Brasília — the day the scoreboard and the caps are counted in."""
    days_limit: int
    rule_sets: list[RuleSetBoardOut]
    goal: GoalOut
    sources: SourcesOut
