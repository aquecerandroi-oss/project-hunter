"""What the engine cannot check for itself: the market row, and an unmeasurable wallet.

Two seams between the durable side and the pure core:

- ``market_id`` is a foreign key and ``MarketIdentity`` is what the engine
  compares. Nothing in the schema ties them together, so a proposal could name
  the BTC row while handing the engine the SOL book — both internally
  consistent, and the order goes to the wrong market (RISK_ENGINE.md §1);
- when ``PortfolioState`` cannot be built at all, there is no ``evaluate`` to
  call and there still has to be an answer. The contract's answer is a
  *rejection with its reason recorded*, not silence (RISK_ENGINE.md §5:
  "entradas novas bloqueadas, proteções preservadas").
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.enums import MarketType
from hunter_risk.decision import RiskCheck, RiskDecision, check, unavailable
from hunter_risk.evaluate import ENTRY_CHECKS
from hunter_risk.inputs import MarketIdentity
from hunter_risk.kill_switch import blocks_entries

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.admission.sources import ProposalRequest
    from hunter_core.risk.scopes import EffectiveKillSwitch
    from hunter_risk.limits import RiskLimits

__all__ = ["MarketMismatch", "unmeasured_decision", "verify_market"]


class MarketMismatch(ValueError):
    """``market_id`` and the identity handed to the engine name different markets."""


async def verify_market(session: AsyncSession, request: ProposalRequest) -> None:
    """The ``markets`` row and the identity the engine will compare have to agree.

    Without this the row says BTC and the engine sizes against the SOL book:
    both are internally consistent and the order goes to the wrong market
    (RISK_ENGINE.md §1, "a identidade viaja com cada insumo").
    """
    row = (
        await session.execute(
            text(
                "SELECT x.code AS exchange, m.symbol, m.market_type::text AS market_type, "
                "ba.symbol AS base_asset, qa.symbol AS quote_asset FROM markets m "
                "JOIN exchanges x ON x.id = m.exchange_id "
                "LEFT JOIN assets ba ON ba.id = m.base_asset_id "
                "LEFT JOIN assets qa ON qa.id = m.quote_asset_id WHERE m.id = :market"
            ),
            {"market": request.market_id},
        )
    ).one_or_none()
    if row is None:
        raise MarketMismatch(f"market {request.market_id} does not exist")
    if row.base_asset is None or row.quote_asset is None:
        raise MarketMismatch(
            f"market {request.market_id} has no base or quote asset; it cannot be named"
        )
    stored = MarketIdentity(
        exchange=row.exchange,
        symbol=row.symbol,
        market_type=MarketType(row.market_type),
        base_asset=row.base_asset,
        quote_asset=row.quote_asset,
    )
    if stored != request.market:
        raise MarketMismatch(
            f"market {request.market_id} is {stored.exchange}:{stored.symbol} "
            f"({stored.market_type}) but the proposal names {request.market.exchange}:"
            f"{request.market.symbol} ({request.market.market_type})"
        )


def unmeasured_decision(
    request: ProposalRequest,
    *,
    proposal_id: uuid.UUID,
    limits: RiskLimits,
    scopes: EffectiveKillSwitch,
    beta_validated: bool,
    reasons: tuple[str, ...],
) -> RiskDecision:
    """The decision when the wallet itself could not be measured.

    ``PortfolioState`` cannot be built without the day's reference, and the
    contract's answer to that is "entradas novas bloqueadas, proteções
    preservadas" (RISK_ENGINE.md §5) — a *rejection*, recorded with its reason,
    not an exception that leaves no trace of a request that asked for capital.

    Every check of ``ENTRY_CHECKS`` is present, in order, as ``unavailable``
    with the missing input named. The one exception is ``kill_switch``: the
    durable latches were read under the lock, and when they already block
    entries that is a *measured* failure, not an unknown. Anything else would
    need the wallet, and re-deriving those checks here would be a second
    implementation of the engine's rules, which is how two answers to the same
    question start to disagree.
    """
    detail = "estado da carteira indisponivel: " + ", ".join(reasons)
    blocked = blocks_entries(scopes.effective)
    checks: list[RiskCheck] = []
    for name in ENTRY_CHECKS:
        if name == "kill_switch" and blocked:
            checks.append(
                check(
                    name,
                    ok=False,
                    message=(
                        f"kill switch efetivo {scopes.effective} (sistema {scopes.system}, "
                        f"organizacao {scopes.organization}, carteira {scopes.portfolio})"
                    ),
                )
            )
        else:
            checks.append(unavailable(name, detail))
    return RiskDecision(
        approved=False,
        kind="entry",
        proposal_id=proposal_id,
        portfolio_id=request.portfolio_id,
        market=request.market,
        limits_profile=limits.profile,
        effective_kill_switch=scopes.effective,
        cancel_pending=blocked,
        shadow_only=not beta_validated,
        checks=tuple(checks),
        sizing=None,
    )
