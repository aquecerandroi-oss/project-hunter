"""The eligibility envelope: *all* the gates a version declares, read as one.

``strategy_versions.eligibility_policy`` (``0017_eligibility_policy``,
DATABASE.md §29) was always a **map of policies with one policy inside** — the
T3.52 note says so in as many words, and the parser refused an unknown key
precisely so that adding a second gate would not be editing the first one.
T3.59 adds that second gate (:mod:`hunter_strategy_worker.hours_gate`), and this
module is the seam it was designed for:

```json
{"regime": {"scope": "btc", "allow": ["BTC_BULL"], ...},
 "hours":  {"utc": [[12, 15]]}}
```

T3.77 adds the third (:mod:`hunter_strategy_worker.breadth_gate`), the share of
the monitored universe falling in the five minutes before the bar closed:

```json
{"regime": {"scope": "btc", "allow": ["BTC_BULL"], ...},
 "hours":  {"utc": [[12, 15]]},
 "breadth": {"window_m": 5, "min": "0.10", "max": "0.60"}}
```

**Every declared rule must pass.** They are ``AND``, never ``OR``: each rule
narrows, and a version that declares three gates is asking to decide in the
intersection. The order they are evaluated in is not arbitrary either — the
hours gate first, because it reads nothing (no query, no clock) and refusing
there saves the other two their indexed reads on every bar outside the window;
the regime gate second and the breadth gate **last**, which is a deliberately
conservative choice: appending the new rule at the end means a version carrying
only ``regime`` and ``hours`` reports byte for byte the reason it reported before
T3.77 existed, so no already-measured ``ineligible`` histogram changes shape
because a third rule was added to the build. The consequence, worth saying for
the same reason, is that a bar failing *several* rules is reported by the first
one in that order.

**Why this lives outside** :mod:`hunter_strategy_worker.regime_gate`: that
module is at 300+ of the 350 lines the repo allows, and — the real reason — it
is one *rule*. The envelope is not a rule; it is what decides which rules exist,
and a rule that had to know about its siblings could not be added without
touching them.

Fail-closed everywhere, as before: an unknown key, an empty object, a body that
is not an object, anything a rule's own parser refuses. ``NULL`` — every version
written before ``0017`` — is the one honest "no gate".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from hunter_strategy_worker.breadth_gate import (
    BREADTH_KEY,
    BreadthPolicy,
    breadth_clause,
    parse_breadth_policy,
)
from hunter_strategy_worker.hours_gate import (
    HOURS_KEY,
    HoursPolicy,
    hours_clause,
    parse_hours_policy,
)
from hunter_strategy_worker.regime_gate import (
    POLICY_KEY as REGIME_KEY,
)
from hunter_strategy_worker.regime_gate import (
    EligibilityPolicy,
    PolicyError,
    parse_regime_policy,
    regime_clause,
)

__all__ = [
    "BREADTH_KEY",
    "HOURS_KEY",
    "NONE_CLAUSE",
    "REGIME_KEY",
    "BreadthPolicy",
    "EligibilityPolicy",
    "GatePolicy",
    "HoursPolicy",
    "PolicyError",
    "parse_policy",
    "policy_argument",
    "policy_clauses",
]
"""``EligibilityPolicy``/``HoursPolicy``/``PolicyError`` are re-exported: the
envelope is the public face of the gates, so a caller that needs one rule's type
should not have to know which module the rule happens to live in."""

NONE_CLAUSE = "none"
"""The value that **removes** one rule (``--policy regime=none,hours=12-15``),
spelled out for the same reason ``--policy none`` removes all of them: dropping
a gate is a sentence the operator writes, never the absence of one."""

_KEYS = (REGIME_KEY, HOURS_KEY, BREADTH_KEY)
_CLAUSE_PARSERS: dict[str, Callable[[str], dict[str, Any]]] = {
    REGIME_KEY: regime_clause,
    HOURS_KEY: hours_clause,
    BREADTH_KEY: breadth_clause,
}


@dataclass(frozen=True, slots=True)
class GatePolicy:
    """Every rule a version declares, already parsed. At least one is not ``None``."""

    regime: EligibilityPolicy | None = None
    """The hourly-regime rule (T3.52), or ``None`` when the version declares none."""
    hours: HoursPolicy | None = None
    """The hour-of-day rule (T3.59), or ``None`` when the version declares none."""
    breadth: BreadthPolicy | None = None
    """The universe-amplitude rule (T3.77), or ``None`` when none is declared."""

    def to_jsonable(self) -> dict[str, Any]:
        """Exactly the shape that was stored, rule by rule."""
        stored: dict[str, Any] = {}
        if self.regime is not None:
            stored[REGIME_KEY] = self.regime.to_body()
        if self.hours is not None:
            stored[HOURS_KEY] = self.hours.to_body()
        if self.breadth is not None:
            stored[BREADTH_KEY] = self.breadth.to_body()
        return stored


def parse_policy(raw: object | None) -> GatePolicy | None:
    """``None`` for "no gate"; a parsed envelope; or :class:`PolicyError`.

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
    unknown_keys = sorted(set(stored) - set(_KEYS))
    if unknown_keys:
        raise PolicyError(f"eligibility_policy has unknown key(s): {', '.join(unknown_keys)}")
    if not stored:
        raise PolicyError(
            "eligibility_policy has no policy in it and is not NULL: expected one or "
            f"more of {', '.join(sorted(_KEYS))}"
        )
    return GatePolicy(
        regime=parse_regime_policy(stored[REGIME_KEY]) if REGIME_KEY in stored else None,
        hours=parse_hours_policy(stored[HOURS_KEY]) if HOURS_KEY in stored else None,
        breadth=parse_breadth_policy(stored[BREADTH_KEY]) if BREADTH_KEY in stored else None,
    )


def policy_clauses(argument: str) -> dict[str, str]:
    """``"regime=btc:SIDEWAYS,BTC_BULL,hours=12-15"`` -> one string per rule.

    The separator between rules is a comma, and a comma is *also* what separates
    regime labels — so the split is on the only thing that tells them apart: a
    fragment carrying ``=`` opens a new rule, a fragment without one continues
    the rule before it. No rule key and no label contains ``=``, which is what
    makes this unambiguous rather than clever.
    """
    clauses: dict[str, str] = {}
    current: str | None = None
    for fragment in argument.split(","):
        if "=" in fragment:
            key, _, rest = fragment.partition("=")
            key = key.strip()
            if key not in _CLAUSE_PARSERS:
                raise PolicyError(
                    f"--policy {argument!r}: {key!r} is not a gate this build knows "
                    f"({', '.join(sorted(_CLAUSE_PARSERS))})"
                )
            if key in clauses:
                raise PolicyError(f"--policy {argument!r}: {key} appears twice")
            clauses[key] = rest.strip()
            current = key
        elif current is None:
            raise PolicyError(
                f"--policy {argument!r}: expected <gate>=<value>[,<gate>=<value>], "
                f"one of {', '.join(sorted(_CLAUSE_PARSERS))}"
            )
        else:
            clauses[current] = f"{clauses[current]},{fragment.strip()}"
    if not clauses:
        raise PolicyError(f"--policy {argument!r}: no gate named")
    return clauses


def policy_argument(argument: str) -> dict[str, Any] | None:
    """The operator's ``--policy`` string -> the JSON to store, or ``None``.

    Every clause goes through the rule's own parser — the same function the
    worker uses to read the column back — so the CLI refuses exactly what the
    worker would refuse. ``<gate>=none`` drops that one rule; when nothing is
    left the answer is ``None``, which is "no gate at all".
    """
    stored: dict[str, Any] = {}
    for key, rest in policy_clauses(argument).items():
        if rest.lower() == NONE_CLAUSE:
            continue
        stored[key] = _CLAUSE_PARSERS[key](rest)
    return stored or None
