"""The regime gate: may *this version* decide in the context of *this bar*?

T3.52. The hourly regime series (``market_regimes`` with ``scope = 'btc'`` and
``classifier_version = 'regime_hourly_v1'``, written by the scanner's T3.43 job)
has existed since 2026-09-08 and nothing that decides has ever read it. This
module is the reader, and it lives **outside** the frozen closure
(``hunter_core.strategies.{aggregate,base,canonical,envelope,indicators,numeric,schema}``):
touching any of those would move every activated version's ``code_ref`` digest
and the worker would refuse the whole catalogue. The hook that already exists is
``StrategyContext.eligible``/``eligibility_reason`` — every strategy opens its
``explain`` with ``if not ctx.eligible`` and answers ``INELIGIBLE``, a state that
neither decides, nor re-arms the slot, nor spends the barrier
(``episodes.py``). So the gate is a decision of the **context builder**, not of
the strategy: no strategy code changes, no digest changes.

**The policy is per version and frozen with it** (``strategy_versions.eligibility_policy``,
``0017_eligibility_policy``, DATABASE.md §29). ``NULL`` means "no gate", which is
what every version written before this task honestly is.

**The cut, and why it is the *previous* closed hour.** A snapshot of the hour
``ts`` is decided with candles that were already final at ``ts`` and the row it
writes spans ``[ts, ts + 1h)`` (PIPELINE §4b item 1), so using the row that
*contains* the cut would not, by itself, be look-ahead. The rule here is
stricter — **the newest closed row with ``end_time <= source_bar_close``** — and
it is stricter on purpose:

- it stays true if the labelling convention of the series ever changes, or if a
  second classifier ever writes into the same scope. The gate is on the reading
  side and must not depend on a property of the writing side;
- it does not depend on the producer's latency: the row containing 15:02 is
  written by the hourly pass just after 15:00, and a decision at 15:02 taken
  while that pass is still running would find nothing and be refused. A gate
  that flips with a job's schedule is a lottery, not a gate;
- the replay reads the same rule over the same table, so a historical decision
  and a live one are cut identically.

Declared cost: the context is 61 to 119 minutes old (the row ``[14:00, 15:00)``
was decided with data up to 14:00 and gates every decision between 15:00 and
16:00). Changing that is a **new** ``rule`` label in the policy — the parser
refuses a label it does not know — never a silent edit here.

**Staleness fails closed.** Under this rule a healthy series is always less than
an hour old at the cut; :data:`MAX_STALENESS` (2 h) is the ceiling past which a
row stops being context and starts being an assumption. Beyond it the gate
answers ``regime_gate:unknown`` with ``detail = "stale"`` — the hourly producer
having died is exactly when a version must **not** keep deciding on last
Tuesday's regime.

**Everything unreadable is refused, never ignored**: an unknown key, an unknown
scope, an unknown rule, a label that is not a ``MarketRegime``, an empty
``allow``, ``UNKNOWN`` inside ``allow`` (a version deciding during the
classifier's warm-up would be deciding without context and calling it context).
``load_version_roster`` refuses to run a version whose policy does not parse.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from hunter_core.db.models.analysis import MarketRegimeRow
from hunter_core.domain.enums import MarketRegime, RegimeScope
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "DEFAULT_CLASSIFIER",
    "DEFAULT_SCOPE",
    "MAX_STALENESS",
    "POLICY_KEY",
    "REASON_PREFIX",
    "RULE_PREVIOUS_CLOSED_HOUR",
    "EligibilityPolicy",
    "PolicyError",
    "RegimeGate",
    "evaluate_gate",
    "load_gate",
    "parse_policy",
    "policy_argument",
]

POLICY_KEY = "regime"
"""The only policy this build understands. A second gate (session, beta,
breadth) is a second key, and an unknown key is refused — the envelope is a map
of policies precisely so that adding one is not editing this one."""

DEFAULT_SCOPE = RegimeScope.BTC.value
DEFAULT_CLASSIFIER = "regime_hourly_v1"
RULE_PREVIOUS_CLOSED_HOUR = "previous_closed_hour"
REASON_PREFIX = "regime_gate"
UNKNOWN = "unknown"
"""The reason word for "no usable label", covering both the classifier's own
``UNKNOWN`` row and no row at all. The two are told apart by
:attr:`RegimeGate.detail`, never by inventing a second reason grammar."""

MAX_STALENESS = timedelta(hours=2)
"""How old the chosen row may be, measured ``cut - end_time``. Under
:data:`RULE_PREVIOUS_CLOSED_HOUR` a complete series is always under one hour
old; two hours is one full hour of slack for the producer and nothing more."""

_SCOPES = frozenset(scope.value for scope in RegimeScope)
_RULES = frozenset({RULE_PREVIOUS_CLOSED_HOUR})
_LABELS = frozenset(regime.value for regime in MarketRegime)
_POLICY_FIELDS = frozenset({"scope", "classifier_version", "rule", "allow"})


class PolicyError(ValueError):
    """The stored policy is not one this build can honour. Nothing is guessed."""


@dataclass(frozen=True, slots=True)
class EligibilityPolicy:
    """A parsed ``strategy_versions.eligibility_policy``. Immutable, like the row."""

    scope: str
    classifier_version: str
    rule: str
    allow: tuple[str, ...]

    def to_jsonable(self) -> dict[str, Any]:
        """Exactly the shape that was stored — the canonical order, sorted labels."""
        return {
            POLICY_KEY: {
                "allow": list(self.allow),
                "classifier_version": self.classifier_version,
                "rule": self.rule,
                "scope": self.scope,
            }
        }


def parse_policy(raw: object | None) -> EligibilityPolicy | None:
    """``None`` for "no gate"; a policy; or :class:`PolicyError`. Never a default.

    Typed ``object`` and not ``dict``: what arrives is whatever JSONB holds, and
    a column someone put a list or a string into must be *refused*, not assumed.

    An empty object (``{}``) is refused rather than read as "no gate": a row
    someone wrote a policy into and emptied by accident must not be silently
    promoted to "decides everywhere".
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PolicyError(f"eligibility_policy must be a JSON object, got {type(raw).__name__}")
    stored = cast("dict[str, Any]", raw)
    unknown_keys = sorted(set(stored) - {POLICY_KEY})
    if unknown_keys:
        raise PolicyError(f"eligibility_policy has unknown key(s): {', '.join(unknown_keys)}")
    if POLICY_KEY not in stored:
        raise PolicyError(f"eligibility_policy has no {POLICY_KEY!r} policy and is not NULL")
    body: object = stored[POLICY_KEY]
    if not isinstance(body, dict):
        raise PolicyError(f"{POLICY_KEY} policy must be a JSON object")
    typed = cast("dict[str, Any]", body)
    unknown_fields = sorted(set(typed) - _POLICY_FIELDS)
    if unknown_fields:
        raise PolicyError(f"{POLICY_KEY} policy has unknown field(s): {', '.join(unknown_fields)}")
    scope = str(typed.get("scope", DEFAULT_SCOPE)).lower()
    if scope not in _SCOPES:
        raise PolicyError(f"{POLICY_KEY} policy scope {scope!r} is not a RegimeScope")
    classifier = str(typed.get("classifier_version", DEFAULT_CLASSIFIER))
    rule = str(typed.get("rule", RULE_PREVIOUS_CLOSED_HOUR))
    if rule not in _RULES:
        raise PolicyError(f"{POLICY_KEY} policy rule {rule!r} is not a rule this build knows")
    return EligibilityPolicy(
        scope=scope,
        classifier_version=classifier,
        rule=rule,
        allow=_parse_allow(typed.get("allow")),
    )


def _parse_allow(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise PolicyError(f"{POLICY_KEY} policy needs a non-empty 'allow' list of regime labels")
    labels: list[str] = []
    for entry in cast("list[object]", raw):
        label = str(entry)
        if label not in _LABELS:
            raise PolicyError(f"{label!r} is not a MarketRegime label")
        if label == MarketRegime.UNKNOWN.value:
            raise PolicyError(
                "UNKNOWN cannot be allowed: it is the classifier's warm-up state, and a "
                "version deciding in it would be deciding with no context and calling it context"
            )
        if label in labels:
            raise PolicyError(f"{label!r} appears twice in 'allow'")
        labels.append(label)
    return tuple(sorted(labels))


def policy_argument(argument: str) -> dict[str, Any]:
    """``"regime=BTC:SIDEWAYS,BTC_BULL"`` -> the JSON to store. Refuses the rest.

    The operator's grammar for ``infra/scripts/derive_variant.py --policy``:
    ``<key>=<scope>:<LABEL>[,<LABEL>...]``. It goes through :func:`parse_policy`
    before being returned, so the CLI refuses exactly what the worker would
    refuse — one validator, not two that can drift.
    """
    key, separator, rest = argument.partition("=")
    if not separator or key.strip() != POLICY_KEY:
        raise PolicyError(f"--policy {argument!r}: expected {POLICY_KEY}=<scope>:<LABEL>[,<LABEL>]")
    scope, colon, labels = rest.partition(":")
    if not colon:
        raise PolicyError(f"--policy {argument!r}: missing ':' between scope and labels")
    parsed = parse_policy(
        {
            POLICY_KEY: {
                "scope": scope.strip().lower(),
                "classifier_version": DEFAULT_CLASSIFIER,
                "rule": RULE_PREVIOUS_CLOSED_HOUR,
                "allow": [label.strip() for label in labels.split(",") if label.strip()],
            }
        }
    )
    if parsed is None:  # pragma: no cover - parse_policy only answers None for None
        raise PolicyError(f"--policy {argument!r} produced no policy")
    return parsed.to_jsonable()


@dataclass(frozen=True, slots=True)
class RegimeGate:
    """The verdict for one (policy, cut): what was read, and what it decided."""

    eligible: bool
    label: str | None
    """The regime label of the row used, or ``None`` when no row was usable."""
    row_id: uuid.UUID | None
    hour_start: datetime | None
    hour_end: datetime | None
    detail: str
    """``allowed`` | ``refused`` | ``no_row`` | ``stale`` | ``classifier_warmup``."""
    policy: EligibilityPolicy

    @property
    def reason(self) -> str:
        """``regime_gate:<LABEL>`` on a refusal by label, ``regime_gate:unknown``
        when no label was usable (no row, stale row, or the classifier's own
        ``UNKNOWN``). ``None`` is never a reason: a refusal always says why."""
        if self.label is None or self.label == MarketRegime.UNKNOWN.value:
            return f"{REASON_PREFIX}:{UNKNOWN}"
        return f"{REASON_PREFIX}:{self.label}"

    def to_jsonable(self) -> dict[str, Any]:
        """What the envelope's provenance block carries — the row that gated it."""
        return {
            "eligible": self.eligible,
            "label": self.label,
            "row_id": None if self.row_id is None else str(self.row_id),
            "hour_start": None if self.hour_start is None else self.hour_start.isoformat(),
            "hour_end": None if self.hour_end is None else self.hour_end.isoformat(),
            "detail": self.detail,
            "policy": self.policy.to_jsonable()[POLICY_KEY],
        }


@dataclass(frozen=True, slots=True)
class RegimeRow:
    """The four fields of a ``market_regimes`` row this gate looks at."""

    id: uuid.UUID
    regime: str
    start_time: datetime
    end_time: datetime | None


def evaluate_gate(policy: EligibilityPolicy, row: RegimeRow | None, cut: datetime) -> RegimeGate:
    """The verdict — pure, so the replay and a test decide it the same way."""
    if row is None:
        return RegimeGate(False, None, None, None, None, "no_row", policy)
    end = None if row.end_time is None else ensure_utc(row.end_time)
    if end is None or ensure_utc(cut) - end > MAX_STALENESS:
        return RegimeGate(False, None, row.id, ensure_utc(row.start_time), end, "stale", policy)
    if row.regime == MarketRegime.UNKNOWN.value:
        return RegimeGate(
            False, row.regime, row.id, ensure_utc(row.start_time), end, "classifier_warmup", policy
        )
    allowed = row.regime in policy.allow
    return RegimeGate(
        allowed,
        row.regime,
        row.id,
        ensure_utc(row.start_time),
        end,
        "allowed" if allowed else "refused",
        policy,
    )


async def load_gate(
    session: AsyncSession, policy: EligibilityPolicy, *, cut: datetime
) -> RegimeGate:
    """Read the gating row for ``cut`` and decide.

    The read lives here rather than in :mod:`hunter_strategy_worker.repo` for two
    reasons: the 350-line budget that already split ``repo``/``tracking_repo``,
    and the fact that this query is meaningless without the rule it implements —
    ``end_time <= cut`` **is** :data:`RULE_PREVIOUS_CLOSED_HOUR`, and separating
    them would let one move without the other.

    ``ORDER BY start_time DESC`` rather than ``end_time``: for closed hourly rows
    the two orders agree, and it is ``ix_market_regimes_scope_start`` that makes
    this a backward index scan over a handful of rows instead of a sort.

    The query has **no** staleness predicate on purpose: an old row still comes
    back and :func:`evaluate_gate` calls it ``stale``. Filtering it in SQL would
    make the same fact arrive as ``no_row``, and "the producer died" and "this
    series never existed" are different operator problems.
    """
    cut_utc = ensure_utc(cut)
    found = (
        await session.execute(
            select(
                MarketRegimeRow.id,
                MarketRegimeRow.regime,
                MarketRegimeRow.start_time,
                MarketRegimeRow.end_time,
            )
            .where(
                MarketRegimeRow.scope == RegimeScope(policy.scope),
                MarketRegimeRow.classifier_version == policy.classifier_version,
                MarketRegimeRow.end_time.is_not(None),
                MarketRegimeRow.end_time <= cut_utc,
            )
            .order_by(MarketRegimeRow.start_time.desc())
            .limit(1)
        )
    ).first()
    row = (
        None
        if found is None
        else RegimeRow(
            id=found.id,
            regime=MarketRegime(found.regime).value,
            start_time=found.start_time,
            end_time=found.end_time,
        )
    )
    return evaluate_gate(policy, row, cut_utc)
