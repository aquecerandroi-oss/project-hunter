"""O que a leitura recebe: a oportunidade gravada no tique (R1) e a sua aposta de papel.

Dinheiro chega em `Decimal` (a fronteira) e só vira `float` dentro do estimador. Tempo é
sempre UTC aware. A aposta é vista **como estava no instante da leitura** (`na_leitura`):
nada que o laço gravou depois entra no veredito.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Aposta:
    """`meme_paper_bets` de uma proposta, com a foto de fill e a foto de venda."""

    entry_at: datetime
    fill_observed_at: datetime
    fill_source: str
    sol_spent: Decimal
    size_sol: Decimal
    status: str
    exit_at: datetime | None
    exit_reason: str | None
    pnl_sol: Decimal | None
    outcome_quality: str
    sale_observed_at: datetime | None
    sale_complete: bool | None
    token_completed_at: datetime | None
    token_migrated_at: datetime | None
    high_water_x: Decimal | None
    fee_buy_sol: Decimal | None
    fee_sell_sol: Decimal | None
    curve_proceeds_sol: Decimal | None
    token_estado_via: str = "history"  # noqa: S105 - a label, not a secret
    """Como `token_completed_at`/`token_migrated_at` são conhecidos em L
    (`estado_token.VIAS`); a carga deixa `nao_resolvido` até a leitura resolver."""

    def retorno(self) -> float | None:
        """`pnl_sol / size_sol` (H-022, desfecho), ou ausente."""
        if self.pnl_sol is None:
            return None
        return float(self.pnl_sol / self.size_sol)

    def perda_integral(self) -> float:
        """−`sol_spent`/`size_sol`: a taxa de compra já está dentro de `sol_spent`."""
        return float(-self.sol_spent / self.size_sol)


@dataclass(frozen=True)
class Oportunidade:
    """Uma linha de `meme_mature_opportunities` (1.ª por conjunto e mint) e o que veio dela."""

    rule_set_id: str
    mint: str
    evaluated_at: datetime
    features_end_time: datetime
    features_computed_at: datetime | None
    fidelity: str
    coverage_status: str
    line_reason: str | None
    higher_lows: bool | None
    breakout_15m: bool | None
    distance_to_support_pct: Decimal | None
    mcap_slope_15m: Decimal | None
    curve_progress_pct: Decimal | None
    proposal_refusals: tuple[str, ...]
    no_proposal_reason: str | None
    proposal_id: str | None
    proposal_status: str | None
    proposal_refusal: str | None
    aposta: Aposta | None
    prior_other_bet: bool
    """Aposta de outro conjunto neste mint aberta antes de `features_end_time` (§2.2)."""


def na_leitura(aposta: Aposta | None, leitura: datetime) -> Aposta | None:
    """A aposta como estava em `leitura`: fill depois = sem fill; saída depois = aberta."""
    if aposta is None or aposta.entry_at > leitura:
        return None
    if aposta.exit_at is None or aposta.exit_at <= leitura:
        return aposta
    return replace(
        aposta,
        status="open",
        exit_at=None,
        exit_reason=None,
        pnl_sol=None,
        outcome_quality="measured",
        sale_observed_at=None,
        sale_complete=None,
        fee_sell_sol=None,
        curve_proceeds_sol=None,
    )
