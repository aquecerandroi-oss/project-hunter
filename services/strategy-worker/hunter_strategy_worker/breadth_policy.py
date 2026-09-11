"""The ``breadth`` clause of the eligibility envelope: band, window and **series**.

T3.77 wrote this next to the gate; T3.88 split it out, because the rule grew a
third field and the gate was at 319 of the repo's 350 lines. The split is the one
``gate_policy`` already argues for: a *rule* and the *envelope* are different
things, and so are "what the version declared" and "what the row says".

```json
{"breadth": {"window_m": 5, "min": "0.10", "max": "0.60", "version": "breadth_v2"}}
```

**Why ``version`` is stored and not implied.** Until T3.88 the gate read
``market_breadth`` with ``breadth_version = BREADTH_VERSION``, a module constant —
so the series a version was measured against was a property of *the build that
happened to be running*, not of the experiment. Then ``breadth_v2`` appeared (a
different universe: the 16 markets with 90 days of history instead of ~200
monitored perpetuals) and that implicitness became a way to silently re-point a
pre-registered cell at a different series between two deploys. Now the version
names the series it means, the stored policy carries it, the envelope's provenance
block publishes it, and a build that does not know that series **refuses at parse
time** instead of serving the nearest one.

**The band is half-open on the top**: ``min <= value < max``. ``0.10-0.60`` is
"between a tenth and three fifths of the universe falling"; a bar measuring
exactly ``0.60`` is refused and one measuring exactly ``0.10`` passes, so two
adjacent bands tile the line without overlapping and without a hole.

**The bounds are stored as strings.** That is not decoration:
``variant.canonical_policy`` emits every number as a normalised decimal string,
and T3.59's hours rule had to keep its integers out of that path
(``variant.stored_policy``'s docstring). A pair of decimal *strings* round-trips
byte for byte through both, so this rule cannot be made unreadable by the
serialisation that broke the last one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from hunter_indicators.breadth import CURRENT_BREADTH_VERSION, SPECS, WINDOW_MINUTES
from hunter_strategy_worker.regime_gate import PolicyError

__all__ = [
    "BREADTH_KEY",
    "SUPPORTED_VERSIONS",
    "SUPPORTED_WINDOWS",
    "BreadthPolicy",
    "breadth_clause",
    "parse_breadth_policy",
]

BREADTH_KEY = "breadth"
"""The key this rule occupies in the eligibility envelope."""

SUPPORTED_WINDOWS = frozenset({WINDOW_MINUTES})
"""The windows this build's producer actually writes. A policy asking for another
one is refused at parse time rather than silently served the 5-minute series: the
version would be attributed to an experiment nobody ran."""

SUPPORTED_VERSIONS = frozenset(SPECS)
"""The series this build can read (``breadth_v1``, ``breadth_v2``). Same doctrine
as :data:`SUPPORTED_WINDOWS`, and the same refusal."""

_FIELDS = frozenset({"window_m", "min", "max", "version"})
_ZERO = Decimal(0)
_ONE = Decimal(1)


def _bound(raw: object, *, label: str) -> Decimal:
    if not isinstance(raw, str):
        raise PolicyError(
            f"{BREADTH_KEY} policy: {label} must be a decimal *string* (got "
            f"{type(raw).__name__}); quoting it is what keeps the bound byte-identical "
            "through the canonical form"
        )
    try:
        value = Decimal(raw)
    except InvalidOperation as invalid:
        raise PolicyError(f"{BREADTH_KEY} policy: {label} {raw!r} is not a decimal") from invalid
    if not value.is_finite() or not _ZERO <= value <= _ONE:
        raise PolicyError(f"{BREADTH_KEY} policy: {label} {raw} is outside 0-1")
    return value


@dataclass(frozen=True, slots=True)
class BreadthPolicy:
    """A parsed ``breadth`` body: which series, which window, which band."""

    window_m: int
    minimum: Decimal
    maximum: Decimal
    """Half-open: ``minimum <= value < maximum``."""
    version: str
    """The ``market_breadth.breadth_version`` this band is a band *of*. Not a
    default of the gate: two series with different universes produce different
    numbers for the same minute, so a band without a series names nothing."""

    def to_body(self) -> dict[str, Any]:
        """Exactly the shape that was stored — canonical order, bounds as strings.

        ``str(Decimal("0.10"))`` is ``"0.10"``: a ``Decimal`` keeps the exponent
        it was built with, so the round-trip is byte-identical and a stored
        policy never drifts from the one the operator typed.
        """
        return {
            "max": str(self.maximum),
            "min": str(self.minimum),
            "version": self.version,
            "window_m": self.window_m,
        }

    @property
    def note(self) -> str:
        """The human copy that travels in the lineage: ``breadth=0.10-0.60``.

        The series is deliberately **not** in this string. It is the changelog
        line an operator reads in a version's lineage, T3.77 shipped it in that
        shape, and a version derived before T3.88 must keep reading the same note
        it read then; the series is auditable where it matters, in the stored body
        and in every envelope the version writes.
        """
        return f"{BREADTH_KEY}={self.minimum}-{self.maximum}"


def parse_breadth_policy(body: object) -> BreadthPolicy:
    """The ``breadth`` body of the envelope, or :class:`PolicyError`."""
    if not isinstance(body, dict):
        raise PolicyError(f"{BREADTH_KEY} policy must be a JSON object")
    typed = cast("dict[str, Any]", body)
    unknown = sorted(set(typed) - _FIELDS)
    if unknown:
        raise PolicyError(f"{BREADTH_KEY} policy has unknown field(s): {', '.join(unknown)}")
    missing = sorted(_FIELDS - set(typed))
    if missing:
        raise PolicyError(f"{BREADTH_KEY} policy is missing {', '.join(missing)}")
    window = typed["window_m"]
    if isinstance(window, bool) or not isinstance(window, int):
        raise PolicyError(f"{BREADTH_KEY} policy: window_m {window!r} is not an integer")
    if window not in SUPPORTED_WINDOWS:
        raise PolicyError(
            f"{BREADTH_KEY} policy: window_m {window} is not a window this build computes "
            f"({', '.join(str(known) for known in sorted(SUPPORTED_WINDOWS))})"
        )
    version = typed["version"]
    if not isinstance(version, str) or version not in SUPPORTED_VERSIONS:
        raise PolicyError(
            f"{BREADTH_KEY} policy: version {version!r} is not a series this build reads "
            f"({', '.join(sorted(SUPPORTED_VERSIONS))})"
        )
    minimum = _bound(typed["min"], label="min")
    maximum = _bound(typed["max"], label="max")
    if minimum >= maximum:
        raise PolicyError(
            f"{BREADTH_KEY} policy: [{minimum}, {maximum}) is empty — a gate that refuses "
            "every value is a gate someone believes in and does not have"
        )
    if minimum == _ZERO and maximum == _ONE:
        raise PolicyError(
            f"{BREADTH_KEY} policy: [0, 1) lets every reading through, so nothing is ever "
            "refused except an unavailable series"
        )
    return BreadthPolicy(window_m=window, minimum=minimum, maximum=maximum, version=version)


def breadth_clause(rest: str) -> dict[str, Any]:
    """``"0.10-0.60"`` -> the body to store; ``"0.10-0.60@breadth_v1"`` names the
    series explicitly. Refuses the rest.

    The operator's half of the grammar of ``infra/scripts/derive_variant.py
    --policy``. Without ``@`` the series is
    :data:`~hunter_indicators.breadth.CURRENT_BREADTH_VERSION` — chosen *here*,
    once, and then written into the stored body, so the version is pinned at
    derivation time and never re-resolved by a later build. It goes through
    :func:`parse_breadth_policy` before returning, so the CLI refuses exactly what
    the worker would refuse — one validator, not two that can drift.
    """
    band, _, series = rest.strip().partition("@")
    low, dash, high = band.strip().partition("-")
    if not dash:
        raise PolicyError(
            f"--policy {BREADTH_KEY}={rest!r}: expected <min>-<max>[@<series>], e.g. 0.10-0.60"
        )
    return parse_breadth_policy(
        {
            "window_m": WINDOW_MINUTES,
            "min": low.strip(),
            "max": high.strip(),
            "version": series.strip() or CURRENT_BREADTH_VERSION,
        }
    ).to_body()
