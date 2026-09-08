"""Assembling ``ScoreboardRowOut.replication`` — brief T3.18b, item 2.

Pure wiring: every statistic in the payload comes straight out of
``hunter_indicators.replication.protocol.replication_report`` (the same
pure function ``hunter_strategy_worker.replication_stats.build_report``
calls) — this module never recomputes an expectancy, a bootstrap interval or
a verdict. What it adds is D15's ``evidence`` label on each sibling arm,
stitched onto the report's own JSON after the fact rather than smuggled into
the statistics themselves.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from hunter_api.repositories.lab_replication import SEED_PATTERN, SiblingPopulation
from hunter_api.schemas.lab_replication import ReplicationBlockOut
from hunter_indicators.replication import STATUS_NONE, SiblingArm, replication_report

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_indicators.replication import Outcome

__all__ = ["build_replication_block", "resolve_seed"]


def resolve_seed(version_id: uuid.UUID, siblings: list[SiblingPopulation]) -> int:
    """The round's registered seed, read off the first sibling's changelog
    (``SEED_PATTERN``) so the bootstrap this block reports is reproducible
    across reads of the same version.

    No siblings yet (``status`` is ``none`` or ``promissora``) means no
    round was ever registered: the fallback is a seed derived from the
    version's own id, deterministic and declared here rather than borrowed
    from a value nobody wrote down (brief did not specify one — T3.18b
    concern).
    """
    for sibling in siblings:
        match = SEED_PATTERN.search(sibling.meta.changelog or "")
        if match is not None:
            return int(match.group(1))
    return int.from_bytes(version_id.bytes[:4], "big")


def build_replication_block(
    *,
    version_id: uuid.UUID,
    promising_at: datetime | None,
    parent_outcomes: list[Outcome],
    siblings: list[SiblingPopulation],
) -> ReplicationBlockOut | None:
    """``None`` when the version was never ``validada`` (``status == "none"``,
    ``promising_at`` never gravado) — the protocol has not started and a
    scoreboard row for a version that never entered it should not carry a
    block of nulls (brief T3.18b, item 2)."""
    arms = [
        SiblingArm(k=sibling.meta.k, version=sibling.meta.version, outcomes=sibling.outcomes)
        for sibling in siblings
    ]
    report = replication_report(
        parent_outcomes=parent_outcomes,
        promising_at=promising_at,
        siblings=arms,
        seed=resolve_seed(version_id, siblings),
    )
    if report.status == STATUS_NONE:
        return None

    payload = report.to_jsonable()
    evidence_by_k = {sibling.meta.k: sibling.evidence for sibling in siblings}
    _tag_evidence(payload["siblings"]["arms"], evidence_by_k)
    return ReplicationBlockOut.model_validate(payload)


def _tag_evidence(arms: list[dict[str, Any]], evidence_by_k: dict[int, str | None]) -> None:
    for arm in arms:
        arm["evidence"] = evidence_by_k.get(arm["k"])
