"""What a *runnable* strategy version is, and in which order the roster runs them.

Split from :mod:`.catalogue` for the 350-line budget, along the seam the module
docstring there already draws: this is the value object — a database row already
bound to the code that implements it — and that is the machinery that produces
one (reading the catalogue, resolving the code, refusing every disagreement).
Both names are re-exported from ``catalogue`` so no caller had to move.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hunter_core.domain.enums import ShadowCohort, Timeframe
from hunter_strategy_worker.context_budget import context_minutes_for

if TYPE_CHECKING:
    from hunter_core.strategies.base import Strategy
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.regime_gate import EligibilityPolicy

__all__ = ["VERSION_RE", "ActiveVersion", "VersionRoster", "roster_order"]

VERSION_RE = re.compile(r"^v(\d+)$")
_PURPOSE_PAPER = "paper"
_UNNUMBERED = 1 << 30
"""``paper`` sorts before research, and a label this build cannot read as
``v<n>`` sorts after every numbered one instead of at a position invented for
it. The label is spelled out here for the same reason ``catalogue._PURPOSE_LIVE``
is: this package names its own frozen strings."""


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
    purpose: str
    """Copied from ``strategy_versions.purpose`` — the envelope carries this,
    never a literal the worker crava (T3.15, D10). Never ``"live"``: a row
    naming it is refused before it becomes an :class:`ActiveVersion` at all."""

    eligibility_policy: EligibilityPolicy | None = None
    """``strategy_versions.eligibility_policy``, already parsed
    (``0017_eligibility_policy``, T3.52). ``None`` is no gate — which is every
    version activated before this column existed.

    Parsed once, here, and not at every bar: the policy is frozen with the row,
    so re-reading it per evaluation would be re-deciding a settled question
    thousands of times a day. A policy this build cannot parse never becomes an
    :class:`ActiveVersion` at all (``catalogue.load_version_roster`` refuses it
    with ``policy_unreadable``), which is the same fail-closed rule ``code_ref``
    already follows: a decision taken under a gate the process misread would be
    attributed to a version it does not implement.
    """

    replication_parent_id: uuid.UUID | None = None
    replication_index: int | None = None
    """``strategy_versions.replication_parent_id``/``replication_index``
    (``0012_replication``): whose replication sibling this version is, and which
    arm of it. ``None`` for every ordinary version — which is every version that
    is not a sibling.

    They are read here, and nowhere else, because :meth:`cohort` is the only
    thing the worker does with them: the catalogue is where a database row
    becomes something the run can label.
    """

    @property
    def timeframe(self) -> Timeframe:
        """Bars of this timeframe — and only these — are evaluated for entries."""
        return self.strategy.timeframe

    def context_minutes(self, config: ShadowConfig) -> int:
        """How much 1m history *this* version loads behind every bar (T3.54b).

        Derived from the frozen row — the decision grid plus the parameters that
        size its longest lookback — and then clamped between
        ``SHADOW_CONTEXT_MINUTES`` (floor) and ``SHADOW_CONTEXT_MAX_MINUTES``
        (ceiling): :mod:`hunter_strategy_worker.context_budget`.

        A method and not a field because it is a pure function of two things the
        object already holds and one the caller has: computing it at roster load
        would freeze it against a config the evaluation might not be running
        with (a replay builds its own :class:`ShadowConfig`), and the arithmetic
        is a handful of integer operations — far below one candle read.

        It cannot raise here: the catalogue refuses a version whose windows this
        build cannot size before it ever becomes an :class:`ActiveVersion`.
        """
        return context_minutes_for(self.strategy, self.params, config)

    def cohort(self, process_cohort: str) -> str:
        """The cohort this version's decisions are stamped with.

        A replication sibling stamps ``replication:<parent>:<k>``
        (REPLICATION.md §4.4, DATABASE.md §24) instead of the process default,
        which is what lets a consumer refuse its signals **by name**: the
        execution bridge admits ``prospective`` and refuses everything else with
        ``cohort_not_live`` (T3.15e). Before ``0012_replication`` the label was
        unrepresentable and a sibling emitted as ``prospective`` — the one
        cohort the bridge admits — leaving only ``purpose`` and the absence of
        an ``agents`` row between a research sibling and the wallet.

        **A replay keeps its own run label**, sibling or not. Cohorts separate
        populations *of the same version*, and a replay of a sibling is not the
        sibling's reserved forward evaluation (SHADOW-LAB.md §1); collapsing the
        two would also put a replay into the slot
        ``uq_shadow_episodes_slot`` reserves for the forward run.
        """
        if self.replication_parent_id is None or self.replication_index is None:
            return process_cohort
        if process_cohort != ShadowCohort.PROSPECTIVE:
            return process_cohort
        return ShadowCohort.replication(self.replication_parent_id, self.replication_index)


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


def roster_order(version: ActiveVersion) -> tuple[str, int, int, str]:
    """Sort key: strategy, then ``paper`` before research, then version *numerically*.

    Two bugs in one ``ORDER BY`` before this existed (review T3.26-risk, A3).
    SQL ordered ``version`` as text, so ``v10`` came before ``v3``; and nothing
    said the ``paper`` line — the only version whose decisions can reach a
    wallet — should be evaluated before the research variants beside it. The
    order is not cosmetic: ``consumer.handle_candle`` walks this list in order.
    """
    number = VERSION_RE.fullmatch(version.version)
    rank = 0 if version.purpose == _PURPOSE_PAPER else 1
    numeric = int(number.group(1)) if number else _UNNUMBERED
    return (version.strategy_key, rank, numeric, version.version)
