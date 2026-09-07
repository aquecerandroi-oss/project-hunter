"""Opening the paper wallet — the one act that ever credits cash.

The directive's first paragraph: start with R$100.000 of fictional money, and if
the engine operates in USDT, *convert the equivalent at the opening and record
the rate and its source*. Nothing here invents that rate: the caller hands in an
FX observation that is already persisted (T3.11 collects it), this module
decides whether it may open a wallet, and refuses when it may not — "fonte
inválida não abre".

**One transaction, six writes.** DATABASE.md §18.2 states plainly what the
schema cannot prove: that the wallet, the credit, the anchor, the lock row, the
first point of the equity curve and the audit entry were born in the same
commit. This function is that proof — it is the single write path, it never
commits (the caller's ``tenant_session`` owns the unit of work), and the order
is the one the anchor's trigger requires: the lock row exists before the anchor,
because ``SELECT ... FOR UPDATE`` on a row that does not exist serialises
nothing.

**There is no second opening.** A principal paper wallet is one per
organization for ever (D7; the index moved off ``workspace_id`` in T3.1b's
security review of ``0006`` — a workspace is a grouping, not the permanence
guarantee D7 asks for). A concurrent second attempt loses on
``uq_portfolios_principal_paper`` and is reported as :class:`WalletAlreadyOpen`,
not as a database error the caller has to interpret.

**Nothing in this package can add money afterwards.** The anchor is immutable by
trigger, ``portfolios.initial_capital`` is frozen once anchored, and no other
function in ``hunter_core.portfolio`` writes either — there is no deposit route
and no reset (directive §1), which ``test_no_funding_route.py`` asserts against
the source itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError

from hunter_core.audit import AuditEvent, SqlAuditSink
from hunter_core.db.models.fx import FxObservation
from hunter_core.db.repositories.equity import EquitySnapshotRepository
from hunter_core.db.repositories.portfolio import PRINCIPAL_PAPER_SCOPE, PortfolioRepository
from hunter_core.domain.types import ensure_utc, utcnow, uuid7
from hunter_core.logging import get_logger
from hunter_core.portfolio.attribution import (
    OPERATING_CURRENCY,
    ORIGIN_CURRENCY,
    OpeningConversion,
    convert_opening,
)
from hunter_core.portfolio.fx_policy import (
    PAPER_FX_POLICY as PAPER_FX_POLICY,  # re-exported: callers import the policy from here too
)
from hunter_core.portfolio.fx_policy import (
    FxObservationRejected as FxObservationRejected,  # re-exported for the same reason
)
from hunter_core.portfolio.fx_policy import FxPolicy, validate_fx_observation
from hunter_core.portfolio.opening_scope import (
    ScopeViolation as ScopeViolation,  # re-exported: callers import it from here too
)
from hunter_core.portfolio.opening_scope import verify_scope as _verify_scope
from hunter_risk.exposure import SAO_PAULO, sao_paulo_day_start_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

DEFAULT_CAPITAL_BRL = Decimal("100000")
"""R$100.000 — the directive's number, in the currency it was written in."""

DEFAULT_WALLET_NAME = "Carteira paper principal"

_ZERO = Decimal(0)
_PRINCIPAL_INDEX = "uq_portfolios_principal_paper"


class WalletAlreadyOpen(Exception):
    """This organization already has its principal paper wallet (D7)."""


class OpeningResult(BaseModel):
    """What the opening wrote, for the caller to report and audit."""

    model_config = ConfigDict(frozen=True)

    portfolio_id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    conversion: OpeningConversion
    fx_observation_id: uuid.UUID
    opened_at: datetime
    trading_day_start_utc: datetime


async def open_paper_wallet(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    workspace_id: uuid.UUID,
    fx: FxObservation,
    as_of: datetime | None = None,
    capital_brl: Decimal = DEFAULT_CAPITAL_BRL,
    name: str = DEFAULT_WALLET_NAME,
    fx_policy: FxPolicy = PAPER_FX_POLICY,
    risk_profile_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    actor_id: str = "system",
    verify_scope: bool = True,
    _testing_capital_override: bool = False,
) -> OpeningResult:
    """Open the principal paper wallet of ``organization_id``, once, atomically.

    Raises :class:`FxObservationRejected` before writing anything when the rate
    may not open a wallet, and :class:`WalletAlreadyOpen` when the organization
    already has one — including a paused, archived or soft-deleted one, because
    those are the same substitution the directive forbids when it forbids a
    reset.

    ``capital_brl`` **must be** :data:`DEFAULT_CAPITAL_BRL`: the directive's §1
    fixes the paper wallet's opening capital at R$100.000, and a parameter that
    silently accepted anything else would be a second, code-level way to change
    a number the product intentionally hard-codes. It exists at all only so a
    test that means to exercise the conversion arithmetic at a different
    capital can, by also passing ``_testing_capital_override=True`` — a name
    deliberately awkward to type, so it is never reached from production code
    by accident (``test_no_funding_route.py`` scans the repository for it).

    ``verify_scope`` (default ``True``) re-reads every row this call writes and
    refuses to return — raising :class:`ScopeViolation` instead — if any of
    them landed under a different ``organization_id`` than the one given here
    (security review of ``open_paper_wallet.py``, S3b: the role this function
    always runs as, ``hunter_worker``, has ``BYPASSRLS``, so nothing in
    Postgres itself would catch that on its own). Pass ``False`` only where a
    caller already re-verifies scope some other way; every production call
    site (the script, and T3.14's future API route) keeps the default.
    """
    if capital_brl != DEFAULT_CAPITAL_BRL and not _testing_capital_override:
        raise ValueError(
            f"capital_brl must be {DEFAULT_CAPITAL_BRL} (directive §1 fixes the paper "
            f"wallet's opening capital); got {capital_brl}. Only a test that means to "
            "exercise a different capital passes _testing_capital_override=True."
        )
    moment = ensure_utc(as_of) if as_of is not None else utcnow()
    validate_fx_observation(fx, as_of=moment, policy=fx_policy)
    conversion = convert_opening(capital_brl, fx.rate)

    portfolios = PortfolioRepository(session, organization_id)
    await portfolios.require_tenant_context()
    if await portfolios.principal_paper_id() is not None:
        raise WalletAlreadyOpen(
            f"{PRINCIPAL_PAPER_SCOPE} {organization_id} already has its principal paper "
            "wallet; there is no second opening, because a second wallet is the reset the "
            "directive forbids"
        )

    portfolio_id = uuid7()
    day_start = sao_paulo_day_start_utc(moment)
    try:
        await portfolios.create_wallet(
            portfolio_id=portfolio_id,
            workspace_id=workspace_id,
            name=name,
            base_currency=OPERATING_CURRENCY,
            initial_capital=conversion.credited_amount,
            risk_profile_id=risk_profile_id,
            created_by=created_by,
        )
    except IntegrityError as exc:  # a concurrent opening won the unique index
        if _PRINCIPAL_INDEX not in str(exc.orig):
            raise
        raise WalletAlreadyOpen(
            f"{PRINCIPAL_PAPER_SCOPE} {organization_id} got its principal paper wallet from "
            "a concurrent opening; this one is rolled back whole"
        ) from exc

    await portfolios.create_risk_state(
        portfolio_id=portfolio_id,
        equity=conversion.credited_amount,
        as_of=moment,
        trading_day=day_start.astimezone(SAO_PAULO).date(),
        trading_day_start_utc=day_start,
    )
    await portfolios.create_anchor(
        portfolio_id=portfolio_id,
        origin_currency=ORIGIN_CURRENCY,
        origin_amount=conversion.origin_amount,
        operating_currency=OPERATING_CURRENCY,
        credited_amount=conversion.credited_amount,
        fx_observation_id=fx.id,
        rate=conversion.rate,
        conversion_residual=conversion.conversion_residual,
        rounding_policy=conversion.rounding_policy,
        anchored_at=moment,
    )
    await EquitySnapshotRepository(session, organization_id).record(
        portfolio_id=portfolio_id,
        ts=moment,
        cash=conversion.credited_amount,
        equity=conversion.credited_amount,
        exposure_notional=_ZERO,
        exposure_pct=_ZERO,
        unrealized_pnl=_ZERO,
        realized_pnl_cum=_ZERO,
        peak_equity=conversion.credited_amount,
        drawdown_pct=_ZERO,
        open_positions=0,
        fx_observation_id=fx.id,
    )
    await SqlAuditSink(session).record(
        AuditEvent(
            actor_type="system",
            actor_id=actor_id,
            organization_id=organization_id,
            action="portfolio.opened",
            entity_type="portfolio",
            entity_id=str(portfolio_id),
            after=conversion.model_dump(mode="json"),
            metadata={
                "workspace_id": str(workspace_id),
                "fx_observation_id": str(fx.id),
                "fx_source": fx.source,
                "fx_pair": fx.pair,
                "fx_observed_at": ensure_utc(fx.observed_at).isoformat(),
                "fx_available_at": ensure_utc(fx.available_at).isoformat(),
                "fx_availability_max_age_s": fx_policy.availability_max_age_s,
                "fx_observation_max_age_s": fx_policy.observation_max_age_s,
                "trading_day_start_utc": day_start.isoformat(),
            },
            ts=moment,
        )
    )
    log.info(
        "paper_wallet_opened",
        portfolio_id=str(portfolio_id),
        organization_id=str(organization_id),
        workspace_id=str(workspace_id),
        credited=str(conversion.credited_amount),
        origin_amount=str(conversion.origin_amount),
        rate=str(conversion.rate),
        rounding_policy=conversion.rounding_policy,
        fx_observation_id=str(fx.id),
    )
    if verify_scope:
        await _verify_scope(
            session,
            organization_id=organization_id,
            portfolio_id=portfolio_id,
            fx_observation_id=fx.id,
        )
    return OpeningResult(
        portfolio_id=portfolio_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        conversion=conversion,
        fx_observation_id=fx.id,
        opened_at=moment,
        trading_day_start_utc=day_start,
    )
