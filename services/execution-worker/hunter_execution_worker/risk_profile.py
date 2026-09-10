"""The wallet's own risk profile, resolved before anything is admitted — T3.69b.

``docs/RISK_ENGINE.md`` §2 calls ``risk_profiles.limits`` of the ``paper_v1``
row "the object of the engine, not a copy of it", and
``portfolios.risk_profile_id`` is how a wallet names it. Until T3.69b the engine
never read it: :func:`hunter_core.admission.service.admit` takes
``limits: RiskLimits = PAPER_V1`` and this worker never passed the argument, so
the row was the **declared** source and the code constant the **applied** one.
This module makes the row the applied one, and refuses to admit at all when it
cannot be trusted.

**Fail closed, with the constant still the guard.** Four outcomes, three of them
refusals that write nothing (no proposal, no reservation, no order — protections
are untouched, as regra 3 of the directive requires):

- :data:`MISSING` — the wallet has no linked profile, or the link dangles. The
  constant is *not* used as a fallback: that would be exactly the silent
  substitution this task closes, and the operator has two commands to run
  (``docs/ACTIVATION.md`` §8b);
- :data:`INVALID` — the stored JSON does not validate into
  :class:`~hunter_risk.limits.RiskLimits`. ``extra="forbid"`` and
  ``RiskModel._refuse_float`` are what catch a hand-edited row (a fraction
  re-typed as a JSON number is ``Decimal(0.0025)``, not ``Decimal("0.0025")``);
- :data:`DIVERGED` — it validates but differs from
  :data:`~hunter_risk.limits.PAPER_V1` field by field. A silently edited row
  must never move a ceiling, so the divergence is an **operator error**
  surfaced in ``hb:execution:paper`` and in the log, never a new limit;
- :data:`LINKED` — the row *is* the constant, and the limits handed to ``admit``
  are the ones read back from the row.

Nothing here decides anything about a proposal: it reads one row and validates
it. The refusal is applied by :func:`hunter_execution_worker.admission_cycle.decide_requests`,
which resolves for itself when a caller hands it nothing — so no path can admit
without having answered this question.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.logging import get_logger
from hunter_risk.limits import RiskLimits, diverged_fields

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.wallet import WalletRef

__all__ = [
    "DIVERGED",
    "INVALID",
    "LINKED",
    "MISSING",
    "ResolvedLimits",
    "RiskProfileGate",
    "resolve_limits",
    "wallet_limits",
]

logger = get_logger(__name__)

MISSING = "risk_profile_missing"
INVALID = "risk_profile_invalid"
DIVERGED = "risk_profile_diverged"
LINKED = "risk_profile_linked"

_WALLET_PROFILE_SQL = text(
    "SELECT rp.id AS profile_id, rp.preset::text AS preset, rp.limits AS limits "
    "FROM portfolios p LEFT JOIN risk_profiles rp ON rp.id = p.risk_profile_id "
    "WHERE p.id = :portfolio AND p.organization_id = :organization"
)
"""One row, by primary key, both halves of the tenant identity in the predicate.

A ``LEFT JOIN``: a wallet with ``risk_profile_id`` NULL — and a link pointing at
a row this connection cannot see — must come back as a wallet with no profile,
not as no wallet at all.
"""


@dataclass(frozen=True, slots=True)
class ResolvedLimits:
    """What the wallet's profile turned out to be, and the limits to apply."""

    state: str
    """:data:`LINKED` or one of the three refusals — the name the heartbeat,
    the log and the deferral all use, so an operator greps one word."""

    limits: RiskLimits | None = None
    """The object read back from the row. ``None`` on every refusal: there is no
    "degraded" set of limits, because a ceiling nobody decided is not a ceiling."""

    preset: str | None = None
    detail: str = ""
    """The fields that diverged, or the validation error — what to fix."""

    @property
    def usable(self) -> bool:
        return self.limits is not None


def resolve_limits(
    *, profile_id: uuid.UUID | None, preset: str | None, stored: object
) -> ResolvedLimits:
    """Turn one ``(risk_profile_id, preset, limits)`` triple into limits or a refusal.

    Pure: no session, no clock. ``stored`` is the ``jsonb`` as the driver hands
    it back (a mapping), and every failure mode is a named state rather than an
    exception, because the caller's job is to admit nothing and say why.
    """
    if profile_id is None or stored is None:
        return ResolvedLimits(state=MISSING, preset=preset)
    try:
        limits = RiskLimits.model_validate(stored)
    except Exception as invalid:
        return ResolvedLimits(state=INVALID, preset=preset, detail=str(invalid))
    diverged = diverged_fields(limits)
    if diverged:
        return ResolvedLimits(state=DIVERGED, preset=preset, detail=", ".join(diverged))
    return ResolvedLimits(state=LINKED, limits=limits, preset=preset)


async def wallet_limits(session: AsyncSession, *, wallet: WalletRef) -> ResolvedLimits:
    """The limits this wallet's linked profile carries — one indexed row read."""
    row = (
        await session.execute(
            _WALLET_PROFILE_SQL,
            {"portfolio": wallet.portfolio_id, "organization": wallet.organization_id},
        )
    ).first()
    if row is None:
        return ResolvedLimits(state=MISSING, detail="no such wallet for this organization")
    return resolve_limits(profile_id=row.profile_id, preset=row.preset, stored=row.limits)


class RiskProfileGate:
    """The same resolution, with the log written on the **transition** only.

    The admission loop runs once a second: naming an unlinked wallet on every
    pass writes 86.400 identical lines a day and buries everything else, which
    is the doctrine :func:`hunter_execution_worker.admission_cycle.report_unreadable`
    already applies to a request without geometry. State is per process and
    losable — after a restart the current state is named once more, which is
    correct: a new process has said nothing yet.
    """

    def __init__(self) -> None:
        self._named: dict[uuid.UUID, str] = {}

    async def resolve(self, session: AsyncSession, *, wallet: WalletRef) -> ResolvedLimits:
        resolved = await wallet_limits(session, wallet=wallet)
        if self._named.get(wallet.portfolio_id) == resolved.state:
            return resolved
        self._named[wallet.portfolio_id] = resolved.state
        if resolved.usable:
            logger.info(
                "risk_profile_resolved",
                portfolio_id=str(wallet.portfolio_id),
                reason=resolved.state,
                preset=resolved.preset,
            )
        else:
            logger.warning(
                "admission_refused_no_risk_profile",
                portfolio_id=str(wallet.portfolio_id),
                reason=resolved.state,
                preset=resolved.preset,
                detail=resolved.detail,
            )
        return resolved
