"""``/api/v1/orgs/{org_id}/meme/tests`` — the complete record of every test
on the desk (T4.13, brief ``.claude/state/brief-T4.13-registro-de-testes-na-mesa.md``).

One row per paper bet of a Brasília day — closed **and** open (the open ones
with the current mark as a provisional exit) — with every field already
derived here in ``Decimal``: entry and exit photographs, duration, PnL in SOL
and in US$ at the quotes the loop observed, R, the rule set and leg, and what
the Lab's gate said in the minute that motivated the proposal
(``lab_context``, read from ``meme_features_1m``). The observed wallet's REAL
positions (T4.12, ``meme_wallet_positions``) ride along as ``real_items`` when
that table exists.

The exit reason keeps the contract's closed vocabulary (``ExitReason``) and
carries its Portuguese label next to it (``EXIT_REASON_PT``), so the CSV and
the screen say the same words; a reason outside the vocabulary is shown as
``motivo não previsto``, never invented and never dropped.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Final, Literal

from pydantic import BaseModel

from hunter_api.schemas.meme import DecimalStr
from hunter_api.schemas.meme_desk import BetLeg, BetStatus, ExitReason

MEME_TESTS_LABEL = "Registro de testes — papel e REAL observado lado a lado; nada aqui executa"
"""Carried on every payload of this router (the ``MEME_DESK_LABEL`` convention)."""

REAL_OBSERVED_LABEL = "REAL — observado na cadeia, não executado por este sistema"
"""Brief T4.12 §3: the words a REAL row is labelled with, verbatim."""

EXIT_REASON_PT: Final[dict[str, str]] = {
    "target": "alvo atingido",
    "trailing": "trailing disparou",
    "time_stop": "espera máxima",
    "migrated": "curva migrou",
    "creator_dump": "criador vendeu",
    "sell_now": "vender agora (operador)",
    "rug_no_snapshot": "rug — sem fotografia",
    "max_loss": "perda máxima (piso)",
    "line_broken": "linha rompida",
    "dead": "morta",
}
"""``ExitReason`` → Portuguese, the same words ``components/meme-desk/labels.ts``
prints (DESIGN-5: no raw enum on screen; the CSV is a screen too).
``tests/unit/test_meme_tests_service.py`` asserts every ``ExitReason`` member
has an entry."""

PROVISIONAL_EXIT_LABEL = "aberta — marca atual (saída provisória)"
UNKNOWN_EXIT_LABEL = "motivo não previsto"
NO_EXIT_LABEL = "saída sem motivo registrado"

OUTCOME_QUALITY_PT: Final[dict[str, str]] = {
    "measured": "medido",
    "indeterminate": "indeterminado (sem fotografia)",
}
"""``meme_paper_bets.outcome_quality`` (``0030``, T4.16) → Portuguese, the
brief's own words: an ``indeterminate`` close is left out of every sum and
counted apart. A row read from a database below ``0030`` has no quality and
no label — never a fabricated "medido"."""
UNKNOWN_QUALITY_LABEL = "qualidade não registrada"

TestKind = Literal["paper", "real_observed"]
WalletsSource = Literal["observada", "não observada", "leitura indisponível"]
"""Brief: when ``meme_wallet_positions`` (T4.12) does not exist the payload
says ``"não observada"``; a table that exists but could not be read (a column
the reader did not expect) is ``"leitura indisponível"`` — never an empty
list that pretends there is nothing to show."""

PnlUsdBasis = Literal["exit_quote", "entry_quote_provisional"]
PnlUsdReason = Literal["no_exit_quote", "no_entry_quote", "no_pnl"]
LabContextReason = Literal["manual_no_minute", "no_features_row"]


class TestEntryOut(BaseModel):
    """The fill photograph (``meme_paper_bets.entry``): every ``None`` is a key
    the loop did not write."""

    at: datetime
    price_sol_per_token: DecimalStr | None
    """Marginal price of the curve *before* the buy (``marginal_price_before_sol``)."""
    average_price_sol: DecimalStr | None
    mcap_sol: DecimalStr | None
    sol_spent: DecimalStr | None
    tokens: DecimalStr | None
    fee_sol: DecimalStr | None
    fee_pct: DecimalStr | None
    fill_delay_s: int | None
    """``decision_to_fill_s``: seconds between the decision and the fill photograph."""
    fill_delay_snapshots: int | None
    source: str | None


class TestExitOut(BaseModel):
    """The sale photograph, or — while the bet is open — the last mark standing
    in as a provisional exit (``provisional = True``)."""

    at: datetime | None
    provisional: bool
    price_sol_per_token: DecimalStr | None
    """Marginal price *after* the sale (``marginal_price_after_sol``)."""
    mcap_sol: DecimalStr | None
    sol_received: DecimalStr | None
    fee_sol: DecimalStr | None
    reason: ExitReason | str | None
    reason_label: str
    trigger: str | None
    pending_reason: str | None
    """``rug_no_snapshot``: the rule that was waiting for a photograph that never came."""


class LabContextOut(BaseModel):
    """What the gate read in the minute that motivated the proposal
    (``meme_features_1m`` at ``features_end_time``)."""

    features_end_time: datetime | None
    features_version: str | None
    reason: LabContextReason | None
    gate_reasons: list[Any]
    """``meme_proposals.reasons`` — the features/rules that fired (or ``operator_manual``)."""
    line_drawn: bool | None
    line_reason: str | None
    support_line_sol: DecimalStr | None
    distance_to_support_pct: DecimalStr | None
    higher_lows: bool | None
    breakout_15m: bool | None
    hype_score: DecimalStr | None
    hype_reason: str | None
    creator_sold: bool | None
    creator_sold_reason: str | None
    curve_progress_pct: DecimalStr | None
    progress_reason: str | None
    age_minutes: int | None
    unique_buyers: int | None
    mcap_sol: DecimalStr | None


class TestRuleSetOut(BaseModel):
    name: str | None
    version: str | None
    kind: str | None
    label: str
    """``name/version`` for a paper bet, ``wallet:<8 chars>`` for a REAL row."""


class TestRowOut(BaseModel):
    id: str
    kind: TestKind
    kind_label: str
    bet_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    mint: str
    token_name: str | None
    token_symbol: str | None
    status: BetStatus | str
    rule_set: TestRuleSetOut
    leg: BetLeg | str
    parent_bet_id: uuid.UUID | None
    origin: str | None
    decided_by: str | None
    entry: TestEntryOut
    exit: TestExitOut
    duration_s: int | None
    pnl_sol: DecimalStr | None
    pnl_usd: DecimalStr | None
    pnl_usd_basis: PnlUsdBasis | None
    pnl_usd_reason: PnlUsdReason | None
    r_multiple: DecimalStr | None
    sol_usd_at_entry: DecimalStr | None
    sol_usd_at_exit: DecimalStr | None
    sol_usd_source: str | None
    lab_context: LabContextOut
    wallet: str | None
    mark_source: str | None
    outcome_quality: str | None = None
    outcome_quality_label: str | None = None
    outcome_quality_reason: str | None = None
    """``0030`` (T4.16): ``measured`` | ``indeterminate`` and its Portuguese
    label; ``None`` on a row older than the column (or a REAL row)."""


class TestsTotalsOut(BaseModel):
    """The day's totals over **every** row of the filter, not only the page.
    Since T4.16 ``wins``/``losses``/``pnl_sol``/``pnl_usd``/``r_sum`` count
    **measured** closes only; ``indeterminate`` counts the rest apart."""

    bets: int
    closed: int
    open: int
    wins: int
    losses: int
    indeterminate: int = 0
    """Closes the instrument could not price ("indeterminado (sem fotografia)")."""
    pnl_sol: DecimalStr
    """Realized: measured closed bets only."""
    provisional_pnl_sol: DecimalStr
    """Open bets at their last mark — what a sell at that photograph would net."""
    pnl_usd: DecimalStr | None
    unpriced_usd: int
    r_sum: DecimalStr
    real_rows: int


class TestsSourcesOut(BaseModel):
    wallets: WalletsSource
    features_version: str


class TestsListOut(BaseModel):
    label: str = MEME_TESTS_LABEL
    server_now: datetime
    day: date
    day_start: datetime
    day_end: datetime
    rule_set: str | None
    rule_sets: list[str]
    """Names with at least one bet on the day — the filter's pills."""
    totals: TestsTotalsOut
    sources: TestsSourcesOut
    items: list[TestRowOut]
    real_items: list[TestRowOut]
    next_cursor: str | None = None


class TestCurvePointOut(BaseModel):
    observed_at: datetime
    source: str
    mcap_sol: DecimalStr | None
    complete: bool


class TestDetailOut(BaseModel):
    label: str = MEME_TESTS_LABEL
    server_now: datetime
    row: TestRowOut
    curve: list[TestCurvePointOut]
    curve_from: datetime
    curve_to: datetime


__all__ = [
    "EXIT_REASON_PT",
    "MEME_TESTS_LABEL",
    "NO_EXIT_LABEL",
    "OUTCOME_QUALITY_PT",
    "PROVISIONAL_EXIT_LABEL",
    "REAL_OBSERVED_LABEL",
    "UNKNOWN_EXIT_LABEL",
    "UNKNOWN_QUALITY_LABEL",
    "LabContextOut",
    "LabContextReason",
    "PnlUsdBasis",
    "PnlUsdReason",
    "TestCurvePointOut",
    "TestDetailOut",
    "TestEntryOut",
    "TestExitOut",
    "TestKind",
    "TestRowOut",
    "TestRuleSetOut",
    "TestsListOut",
    "TestsSourcesOut",
    "TestsTotalsOut",
    "WalletsSource",
]
