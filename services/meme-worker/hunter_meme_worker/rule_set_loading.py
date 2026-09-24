"""One active ``meme_rule_sets`` row that does not parse must never take the
others down (database-architect, review of T4.91) — split from
:mod:`hunter_meme_worker.lab_repo` for the 350-line budget.

``lab_repo.load_active_rule_sets`` is the only loader of the Lab tick and the
wallet step; before this, one bad document (a hand edit, a future seed)
raised out of its list comprehension and the real desk ``operator/5`` stopped
with it. Now the row is skipped, logged at ``error`` with the worker's own
exception, and counted (``hunter_meme_rule_set_load_failed_total``). A
skipped set proposes nothing and its open bets are not marked until it is
fixed — the error says so; ``meme_rule_set.py --validate`` names the fix.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from hunter_core.logging import get_logger
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.metrics import meme_rule_set_load_failed_total

logger = get_logger(__name__)

__all__ = ["specs_from_rows"]


def specs_from_rows(rows: Iterable[Mapping[Any, Any]]) -> list[RuleSetSpec]:
    """Every row that parses, in order; the others skipped, logged, counted."""
    specs: list[RuleSetSpec] = []
    for r in rows:
        label = f"{r['name']}/{r['version']}"
        try:
            specs.append(
                RuleSetSpec.from_params(
                    id=str(r["id"]),
                    name=str(r["name"]),
                    version=str(r["version"]),
                    kind=str(r["kind"]),
                    exp_ref=r["exp_ref"],
                    status=str(r["status"]),
                    code_ref=str(r["code_ref"]),
                    params=r["params"],
                )
            )
        except Exception as exc:  # the worker's own error, verbatim - never the whole tick
            meme_rule_set_load_failed_total.labels(rule_set=label).inc()
            logger.error(
                "meme_rule_set_load_failed",
                rule_set=label,
                rule_set_id=str(r["id"]),
                error_type=type(exc).__name__,
                error=str(exc),
                fix="uv run python infra/scripts/meme_rule_set.py --validate " + label,
            )
    return specs
