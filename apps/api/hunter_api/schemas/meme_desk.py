"""``/api/v1/orgs/{org_id}/meme/{desk,proposals,bets}`` — the operator desk
(T4.7). Contract: ``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` §Rotas.

Every SOL amount, multiple and percentage is ``Decimal`` in and out: request
bodies refuse a JSON float at the door (``DecimalIn``, the same rule
``schemas/orders.py`` applies) and responses serialize as plain strings
(``DecimalStr``). JSONB the loop writes (``quote``/``entry``/``exit``) is
read into typed *optional* fields by ``services/meme_desk_out.py`` — a key
the loop did not write is ``None`` here, never a fabricated ``0``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from hunter_api.schemas.common import StrictModel
from hunter_api.schemas.meme import DecimalStr
from hunter_api.schemas.meme_wallets import RealObservedOut
from hunter_api.schemas.orders import DecimalIn

MEME_DESK_LABEL = (
    "PAPEL — nenhuma transação real; a chave e a flag ao vivo não existem neste processo"
)
"""Contract §Tela: the permanent label, carried in every payload of this
router (same convention as ``MEME_LABEL``/``LAB_LABEL``)."""

MAX_NOTE_LENGTH = 500
MIN_MINT_LENGTH = 32
MAX_MINT_LENGTH = 64

ProposalStatus = Literal["proposed", "approved", "rejected", "expired", "filled", "unfilled"]
ProposalMode = Literal["paper", "live"]
ProposalOrigin = Literal["rules", "operator"]
RuleSetKind = Literal["research_only", "operator"]
BetStatus = Literal["open", "closed"]
CommandKind = Literal["sell_now", "cancel"]
ExitReason = Literal[
    "target",
    "trailing",
    "time_stop",
    "migrated",
    "creator_dump",
    "sell_now",
    "rug_no_snapshot",
    "max_loss",
    "line_broken",
    "dead",
]
"""The contract's seven, plus ``max_loss`` (the loop has written it since T4.6,
Emendas 1), ``line_broken`` (``0026``, T4.10: the market cap closed below the
support line for two snapshots in a row — EXP-M2's own invalidation) and
``dead`` (``0029``, T4.11: the pool's tape silent for 15 min with the mark at
or below half the cost — the desk's "morta")."""

BetLeg = Literal["probe", "scale", "single"]
"""``meme_paper_bets.leg`` (``0026``, T4.10 — the brief's contract): ``probe``
is the desk's "semi-comprado (sonda)", ``scale`` its "escalado (perna 2)" (a
separate bet that names its ``parent_bet_id``), ``single`` every other bet."""

MarkSource = Literal["curve", "pool_tape"]
"""``meme_paper_bets.mark_source`` (``0029``, T4.11): ``curve`` = "marcada pela
curva", ``pool_tape`` = "marcada pela pool (fita)" — a bet that held through
the migration is priced by the PumpSwap pool's last trade."""

OutcomeQuality = Literal["measured", "indeterminate"]
"""``meme_paper_bets.outcome_quality`` (``0030``, T4.16): ``measured`` =
"medido", ``indeterminate`` = "indeterminado (sem fotografia)" — a close the
instrument could not price, left out of every sum and counted apart."""


class DeskParamsIn(StrictModel):
    """The four parameters the operator decides (contract §Tela: ``size_sol``,
    ``alvo (×)``, ``trailing (%)``, ``espera máx (s)``), plus a note.
    Bounds mirror ``hunter_indicators.meme.rules.ExitRules``: a target below
    1× is not a target and a trailing outside (0, 100) is not a percentage."""

    size_sol: DecimalIn = Field(gt=0)
    target_x: DecimalIn = Field(gt=1)
    trailing_pct: DecimalIn = Field(gt=0, lt=100)
    max_hold_s: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)
    mode: ProposalMode = "paper"
    """T4.14 — ``live`` files the proposal for the real executor **and** the paper
    loop (shadow). Refused ``meme_live_disabled`` unless the API's
    ``ENABLE_MEME_LIVE_TRADING`` is on; the desk shows "Aprovar (REAL)" only then."""


class ApproveProposalIn(DeskParamsIn):
    """``POST /proposals/{id}/approve``."""


class RejectProposalIn(StrictModel):
    """``POST /proposals/{id}/reject``."""

    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)


class ManualProposalIn(DeskParamsIn):
    """``POST /proposals/manual`` — the operator pasted a mint."""

    mint: str = Field(min_length=MIN_MINT_LENGTH, max_length=MAX_MINT_LENGTH)


class DeskParamsOut(BaseModel):
    """``suggested``/``decision``/``params`` as the loop or the API wrote
    them; a missing key is ``None`` (contract: the operator may change any of
    the four, and the loop applies the set's ceilings on top)."""

    size_sol: DecimalStr | None
    target_x: DecimalStr | None
    trailing_pct: DecimalStr | None
    max_hold_s: int | None
    note: str | None = None
    exit_on_migration: bool | None = None
    """``0029`` (T4.11): ``False`` = the set holds through the migration (the
    moonshot arms, ``operator/2``); ``None`` = the key is absent, which for
    every set frozen before means "sells on migration"."""
    trailing_arm_x: DecimalStr | None = None
    """The trailing rule is armed only once the peak reaches this multiple
    ("trailing 50 % só depois de 3×"); ``None`` = armed from the entry."""


class QuoteOut(BaseModel):
    """The snapshot a proposal was priced on (``meme_proposals.quote``).
    Keys are the ones the manual path writes and the desk reads (contract
    "Emendas", T4.7); ``reason`` names why price fields are absent."""

    observed_at: datetime | None
    source: str | None
    mcap_sol: DecimalStr | None
    curve_progress_pct: DecimalStr | None
    price_sol_per_token: DecimalStr | None
    size_sol: DecimalStr | None
    fee_pct: DecimalStr | None
    fee_sol: DecimalStr | None
    cost_sol: DecimalStr | None
    tokens: DecimalStr | None
    reason: str | None = None


class TokenIdentityOut(BaseModel):
    mint: str
    name: str | None
    symbol: str | None
    creator: str | None
    created_at: datetime | None
    mayhem_enabled: bool | None
    mayhem_state: str | None
    completed_at: datetime | None
    migrated_at: datetime | None


class RuleSetOut(BaseModel):
    id: uuid.UUID
    name: str
    version: str
    kind: RuleSetKind | str
    max_sol_per_bet: DecimalStr | None


class BetOut(BaseModel):
    """``meme_paper_bets`` as the desk shows it: live mark, PnL, R, the hold
    deadline (``entry_at + params.max_hold_s``) and, once closed, the exit
    reason. Every ``None`` is a value the loop has not written."""

    id: uuid.UUID
    status: BetStatus | str
    mode: str
    entry_at: datetime
    sol_spent: DecimalStr | None
    fee_sol: DecimalStr | None
    tokens: DecimalStr | None
    initial_risk_sol: DecimalStr
    params: DeskParamsOut
    hold_deadline_at: datetime | None
    mark_sol: DecimalStr | None
    mark_at: datetime | None
    high_water_x: DecimalStr | None
    pnl_sol: DecimalStr | None
    r_multiple: DecimalStr | None
    unrealized_pnl_sol: DecimalStr | None
    """``mark_sol - entry.sol_spent`` while ``open`` (what a sell at the last
    snapshot would have netted, before the loop books it); ``None`` once
    closed or until the loop writes a mark. Computed here in ``Decimal``,
    never in the browser."""

    unrealized_r: DecimalStr | None
    exit_at: datetime | None
    exit_reason: ExitReason | str | None
    sol_received: DecimalStr | None
    sol_usd_at_entry: DecimalStr | None
    sol_usd_at_exit: DecimalStr | None
    leg: BetLeg | str = "single"
    """``0026``: the desk shows ``probe`` as "semi-comprado (sonda)" and
    ``scale`` as "escalado (perna 2)"; a row written before the column existed
    is ``single``, which is what it was."""
    parent_bet_id: uuid.UUID | None = None
    """The probe a ``scale`` leg rides on; ``None`` for every other leg."""
    mark_source: MarkSource | str | None = None
    """``0029``: what priced ``mark_sol`` — ``curve`` or ``pool_tape``; ``None``
    until the loop writes a mark (or on a row older than the column)."""
    mark_stale_s: int | None = None
    """Seconds the pool's tape had been silent at the last mark ("marca
    envelhecida há Ns"); ``None`` while the position is priced on the curve."""
    outcome_quality: OutcomeQuality | str | None = None
    outcome_quality_reason: str | None = None
    """``0030`` (T4.16): ``indeterminate`` with its reason when the close priced
    nothing; ``None`` on a row older than the column."""
    decision_to_fill_s: int | None = None
    """``entry.decision_to_fill_s``: seconds between the decision and the fill
    photograph — the latency the brief asks to be shown per bet."""


class DeskRowOut(BaseModel):
    """One line of ``GET /desk``: the proposal, its token, its rule set and —
    once filled — its bet."""

    id: uuid.UUID
    mint: str
    origin: ProposalOrigin | str
    status: ProposalStatus | str
    proposed_at: datetime
    expires_at: datetime
    features_end_time: datetime | None
    quote: QuoteOut
    reasons: list[Any]
    suggested: DeskParamsOut
    decision: DeskParamsOut | None
    decided_by: str | None
    decided_at: datetime | None
    refusal: str | None
    token: TokenIdentityOut | None
    rule_set: RuleSetOut | None
    bet: BetOut | None
    manual_plan: str | None = None
    """T4.19: ``suggested.manual_plan`` as the loop wrote it at proposal time
    for an ``operator`` proposal — "Comprar 0,05 SOL de X até HH:MM:SS
    (proposta expira). Vender até HH:MM (30 min) — antes disso …", every
    number from the set's params, hours in Brasília; ``None`` on a research
    proposal or a row older than the plan. Never composed here."""


class RuleSetBalanceOut(BaseModel):
    """Paper balance of one active rule set, in SOL. ``balance_sol`` is
    ``wallet_max_sol + realized_total_sol - open_sol``; ``None`` with
    ``balance_reason`` when the set's ``params`` carry no ``wallet_max_sol``."""

    rule_set: RuleSetOut
    wallet_max_sol: DecimalStr | None
    daily_loss_cap_sol: DecimalStr | None
    open_sol: DecimalStr
    open_bets: int
    realized_today_sol: DecimalStr
    closed_today: int
    realized_total_sol: DecimalStr
    balance_sol: DecimalStr | None
    balance_reason: Literal["wallet_max_sol_missing"] | None = None


class SolUsdQuoteOut(BaseModel):
    rate: DecimalStr
    observed_at: datetime
    source: str | None


class DeskSummaryOut(BaseModel):
    rule_sets: list[RuleSetBalanceOut]
    day_pnl_sol: DecimalStr
    sol_usd: SolUsdQuoteOut | None
    sol_usd_reason: Literal["no_observed_quote"] | None = None


class DeskListOut(BaseModel):
    label: str = MEME_DESK_LABEL
    server_now: datetime
    summary: DeskSummaryOut
    items: list[DeskRowOut]
    next_cursor: str | None = None
    real_observed: RealObservedOut | None = None
    """T4.12: the observed wallets' **real** fills and positions, labelled
    "REAL — observado na cadeia, não executado por este sistema"; ``None``
    only when the router did not read them."""


class CommandOut(BaseModel):
    """``meme_operator_commands`` as filed: the loop applies it on the next
    snapshot (``applied_at``/``result`` stay ``None`` until then)."""

    label: str = MEME_DESK_LABEL
    id: uuid.UUID
    command: CommandKind | str
    bet_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    issued_by: str
    issued_at: datetime
    applied_at: datetime | None
    result: dict[str, Any] | None


class ProposalOut(BaseModel):
    label: str = MEME_DESK_LABEL
    row: DeskRowOut


__all__ = [
    "MEME_DESK_LABEL",
    "ApproveProposalIn",
    "BetLeg",
    "BetOut",
    "BetStatus",
    "CommandKind",
    "CommandOut",
    "DeskListOut",
    "DeskParamsIn",
    "DeskParamsOut",
    "DeskRowOut",
    "DeskSummaryOut",
    "ExitReason",
    "ManualProposalIn",
    "MarkSource",
    "OutcomeQuality",
    "ProposalOrigin",
    "ProposalOut",
    "ProposalStatus",
    "QuoteOut",
    "RejectProposalIn",
    "RuleSetBalanceOut",
    "RuleSetKind",
    "RuleSetOut",
    "SolUsdQuoteOut",
    "TokenIdentityOut",
]
