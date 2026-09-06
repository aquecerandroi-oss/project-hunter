"""Which strategy versions exist, and which of them *this build can run*.

The catalogue (``strategies`` × ``strategy_versions``) is what the Shadow Lab
was told to evaluate; the registry (``hunter_core.strategies.registry``) is what
this binary carries; and ``code_ref`` is the frozen claim about which code
produced a version's decisions. This module is where the three meet, and it
refuses whenever they disagree — a signal attributed to code that did not
produce it is worse than no signal at all.

Split from :mod:`.repo` (which stays market data: markets, candles, funding)
for the 350-line budget, and along the right seam: this is *what to run*, that
is *what to run it on*.

Reads go through ``role_session(..., db_role="hunter_worker")`` at the call
sites. Nothing here is tenant data — shadow research is global (DATABASE.md
§1.1), so there is no ``organization_id`` and no ``app.current_org`` to set.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from hunter_core.db.models.agents import Strategy as StrategyRow
from hunter_core.db.models.agents import StrategyVersion
from hunter_core.domain.enums import StrategyVersionStatus, Timeframe
from hunter_core.logging import get_logger
from hunter_core.strategies.canonical import params_hash as compute_params_hash
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_strategy_worker.code_ref import (
    code_ref_module,
    is_code_ref,
    strategy_module,
    version_code_ref,
)
from hunter_strategy_worker.metrics import (
    shadow_versions_active,
    shadow_versions_runnable,
    shadow_versions_unrunnable,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.strategies.base import Strategy

logger = get_logger(__name__)

REJECTIONS = ("code_ref_mismatch", "code_ref_not_frozen", "no_code", "no_parameters")
"""Every way an ``active`` row can fail to become a runnable version. Declared up
front so the gauge publishes a zero for a reason that stopped happening instead
of leaving the last count standing."""

__all__ = [
    "ActiveVersion",
    "REJECTIONS",
    "VersionRoster",
    "code_ref_matches",
    "load_active_versions",
    "load_version_roster",
    "registry_key",
    "resolve_strategy",
]


def registry_key(strategy_key: str, version: str) -> str:
    """``("momentum", "v1") -> "momentum_v1"`` — how a DB row finds its code.

    The catalogue splits what the code joins: ``strategies.key`` is the family
    and ``strategy_versions.version`` is the version, while
    ``hunter_core.strategies`` registers ``momentum_v1``/``v1``. Deriving the
    lookup keeps the two in step without a hand-written map that could drift.
    """
    return f"{strategy_key}_{version}"


@dataclass(frozen=True, slots=True)
class ActiveVersion:
    """One activated ``strategy_version`` bound to the code that implements it."""

    id: uuid.UUID
    strategy_key: str
    version: str
    params: dict[str, Any]
    params_hash: str
    strategy: Strategy
    code_ref: str | None

    @property
    def timeframe(self) -> Timeframe:
        """Bars of this timeframe — and only these — are evaluated for entries."""
        return self.strategy.timeframe


@dataclass(frozen=True, slots=True)
class VersionRoster:
    """What the catalogue says versus what this build can actually run."""

    versions: list[ActiveVersion]
    active_rows: int
    rejected: dict[str, int]

    @property
    def blind(self) -> bool:
        """``active`` rows exist and not one of them can be evaluated here.

        The condition ``main.py`` already treats as fatal for a missing
        migration, arriving later: the worker consumes bars, drops every one of
        them and reports itself healthy. ``/ready`` must say so
        (risk-engine-guardian, S2 review, MUST-FIX 1(b)).
        """
        return self.active_rows > 0 and not self.versions


def code_ref_matches(stored: str | None, running: str, key: str) -> str | None:
    """``None`` when this process runs the code the version was frozen with.

    Otherwise the rejection reason, for the counters. The activation script
    checks the digest once, which does not protect an ordinary restart onto a
    new image: activate v1 with digest A, change a calculator keeping the same
    key, restart, and the worker would evaluate B while recording provenance A —
    an experiment silently measuring different code (Astra, S2 diff review,
    must-fix 6). A mismatch skips the version instead: no signal is better than a
    signal attributed to code that did not produce it.

    A ``code_ref`` that is not a digest at all (the seed's placeholder, or
    ``NULL``) is not evidence either way; it is logged and the version is
    skipped, because the ops script is what writes the definitive one.
    """
    if stored is not None and stored == running:
        return None
    if not is_code_ref(stored):
        logger.warning("shadow_version_code_ref_not_frozen", strategy=key, code_ref=stored)
        return "code_ref_not_frozen"
    logger.error("shadow_version_code_ref_mismatch", strategy=key, frozen=stored, running=running)
    return "code_ref_mismatch"


def resolve_strategy(
    strategy_key: str,
    version: str,
    stored_ref: str | None,
    registry: StrategyRegistry = DEFAULT_REGISTRY,
) -> Strategy | None:
    """The code behind one catalogue row, or ``None`` with the reason logged.

    **The frozen ``code_ref`` decides when it names a module.** That is the whole
    point of freezing it: the row said, once and irrevocably, which module
    produced its decisions. The registry's ``(strategies.key, version)`` lookup
    is the fallback for a row that has no such claim yet — a draft about to be
    activated for the first time, or one still carrying the superseded
    tree-wide spelling.

    Ordering it this way is what makes a *superseded* row work at all: ``v2``'s
    code is still ``momentum_v1``, and no ``momentum_v2`` will ever be
    registered for it. It also removes a trap Astra found (S2 fixes diff review,
    HIGH b): if someone later writes a genuine ``momentum_v2`` class, a
    registry-first resolution would suddenly find *two* answers for the running
    ``momentum``/``v2`` row and refuse it, killing a live experiment.

    The named module still has to belong to the *family* this build knows for
    that ``strategies.key``: if the registry carries any ``<key>_*`` strategy,
    the module must be one of theirs, so ``momentum``/``v7`` pointed at
    ``volume_anomaly_v1`` is refused instead of quietly running another
    strategy's code (Astra: "uma linha momentum poderia executar volume"). A key
    this build knows nothing about has no family to contradict.
    """
    key = registry_key(strategy_key, version)
    module = code_ref_module(stored_ref)
    if module is not None:
        by_module = {strategy_module(s): s for s in registry.all()}.get(module)
        if by_module is None:
            logger.warning("shadow_version_module_not_built", strategy=key, module=module)
            return None
        family = {
            strategy_module(s) for s in registry.all() if s.key.startswith(f"{strategy_key}_")
        }
        if family and module not in family:
            logger.error(
                "shadow_version_code_module_foreign",
                strategy=key,
                code_ref_module=module,
                family=sorted(family),
            )
            return None
        # debug, not info: the roster is reloaded on every readiness poll, and a
        # line per version per poll would bury the events that matter.
        # ``VersionCache`` already logs the roster whenever it *changes*.
        logger.debug("shadow_version_bound_by_code_ref", strategy=key, module=module)
        return by_module
    try:
        return registry.get(key, version)
    except KeyError:
        logger.warning("shadow_version_without_code", strategy=key, version=version)
        return None


async def load_version_roster(session: AsyncSession) -> VersionRoster:
    """Every ``active`` version, split into runnable and refused with reasons.

    A row whose code this build does not carry is skipped and counted: this
    binary cannot honestly run an experiment whose code it does not have, and
    guessing "the closest version" is how a run gets attributed to the wrong
    frozen parameters (``hunter_core.strategies.registry``).
    """
    rows = (
        await session.execute(
            select(
                StrategyVersion.id,
                StrategyVersion.version,
                StrategyVersion.default_parameters,
                StrategyVersion.code_ref,
                StrategyRow.key,
            )
            .join(StrategyRow, StrategyRow.id == StrategyVersion.strategy_id)
            .where(
                StrategyVersion.status == StrategyVersionStatus.ACTIVE,
                StrategyVersion.activated_at.is_not(None),
            )
            .order_by(StrategyRow.key, StrategyVersion.version)
        )
    ).all()
    versions: list[ActiveVersion] = []
    rejected: dict[str, int] = {}

    def refuse(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for row in rows:
        key = registry_key(row.key, row.version)
        strategy = resolve_strategy(row.key, row.version, row.code_ref)
        if strategy is None:
            refuse("no_code")
            continue
        mismatch = code_ref_matches(row.code_ref, version_code_ref(strategy_module(strategy)), key)
        if mismatch is not None:
            refuse(mismatch)
            continue
        params = dict(row.default_parameters or {})
        if not params:
            logger.warning("shadow_version_without_parameters", strategy=key)
            refuse("no_parameters")
            continue
        versions.append(
            ActiveVersion(
                id=row.id,
                strategy_key=row.key,
                version=row.version,
                params=params,
                params_hash=compute_params_hash(params),
                strategy=strategy,
                code_ref=row.code_ref,
            )
        )
    roster = VersionRoster(versions=versions, active_rows=len(rows), rejected=rejected)
    _publish_roster(roster)
    return roster


def _publish_roster(roster: VersionRoster) -> None:
    """Counts on the shared registry, so a partly dead roster is visible even
    when ``/ready`` stays green because one version still runs."""
    shadow_versions_active.set(roster.active_rows)
    shadow_versions_runnable.set(len(roster.versions))
    for reason in REJECTIONS:
        shadow_versions_unrunnable.labels(reason=reason).set(roster.rejected.get(reason, 0))
    if roster.blind:
        logger.error("shadow_no_runnable_version", active=roster.active_rows, **roster.rejected)


async def load_active_versions(session: AsyncSession) -> list[ActiveVersion]:
    """The runnable half of :func:`load_version_roster`."""
    return (await load_version_roster(session)).versions
