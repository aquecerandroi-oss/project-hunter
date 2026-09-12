"""The ``dispersion`` clause of the eligibility envelope: band and **series**.

T3.90 / H-P18, written next to ``breadth_policy`` and on purpose in its shape:

```json
{"dispersion": {"min": "-0.05", "max": "0.00", "version": "dispersion_24h_v1"}}
```

**Three fields, not four.** ``breadth`` carries a ``window_m`` because T3.77
believed a second window would be the same series with a parameter; T3.88 had to
write ``breadth_v2`` anyway, since a different universe is a different series. This
rule applies that lesson: the horizon (24 h), the universe (the sixteen with 90 d)
and the reference market (``BTCUSDT``) all live inside the **version string**, and
there is no knob here that could re-point a pre-registered cell at a different
number.

**``version`` is mandatory and never implied.** A policy without it is refused
rather than completed with the build's default — the exact hole T3.88 closed for
``breadth``, closed here before there is a single stored row to migrate.

**The band is half-open on the top**: ``min <= value < max``. ``-0.05-0.00`` is "the
median alt between five points below the BTC and level with it"; a bar measuring
exactly ``0.00`` is refused and one measuring exactly ``-0.05`` passes, so two
adjacent bands tile the line without overlapping and without a hole.

**The bounds are signed, and that is the one thing this parser has that
``breadth_policy`` does not.** ``breadth``'s operator grammar splits the band on
``str.partition("-")``, which is correct for a quantity in ``[0, 1]`` and **wrong**
for a signed one: ``"-0.05-0.00".partition("-")`` yields ``("", "-", "0.05-0.00")``.
That is a *refusal* rather than a silent misparse (``Decimal("")`` raises and the
clause is rejected), so ``breadth`` is left exactly as it shipped — its bounds
cannot be negative anyway, and editing a frozen grammar to fix a case it forbids
would be a change with no reader. Here the band is matched by
:data:`_BAND` instead: each bound is an optional sign and a positional decimal, and
the separator is the ``-`` between them. ``-0.10--0.03`` is a legal band.

**The bounds are stored as strings.** Not decoration:
``variant.canonical_policy`` emits every number as a normalised decimal string, and
T3.59's hours rule had to keep its integers out of that path. A pair of decimal
*strings* round-trips byte for byte through both, so this rule cannot be made
unreadable by the serialisation that broke the last one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from hunter_indicators.dispersion import CURRENT_DISPERSION_VERSION, SPECS
from hunter_strategy_worker.regime_gate import PolicyError

__all__ = [
    "DISPERSION_KEY",
    "SUPPORTED_VERSIONS",
    "DispersionPolicy",
    "dispersion_clause",
    "parse_dispersion_policy",
]

DISPERSION_KEY = "dispersion"
"""The key this rule occupies in the eligibility envelope."""

SUPPORTED_VERSIONS = frozenset(SPECS)
"""The series this build can read (``dispersion_24h_v1``). A policy naming another
one is refused at parse time rather than silently served this one: a version
attributed to an experiment nobody ran is worse than an error."""

_FIELDS = frozenset({"min", "max", "version"})

_LIMIT = Decimal(1)
"""Bounds live in ``[-1, +1]``. A dispersion is a difference of two 24 h returns,
so ±1 is "the median alt a hundred points away from the reference" — far outside
anything measured (the plantão's worst reading was -0,033). A bound beyond it is
refused because it is a band nobody has evidence for, not because the arithmetic
could not hold it."""

_BAND = re.compile(r"^(?P<min>[+-]?[0-9]+(?:\.[0-9]+)?)-(?P<max>[+-]?[0-9]+(?:\.[0-9]+)?)$")
"""``<min>-<max>`` with signed bounds. Positional decimals only — the same form
``hunter_core.strategies.schema`` accepts as a number, so a bound in exponent
notation is refused here rather than reaching a ``Decimal`` that would accept it
and a stored policy that nobody can read back by eye."""


def _bound(raw: object, *, label: str) -> Decimal:
    if not isinstance(raw, str):
        raise PolicyError(
            f"{DISPERSION_KEY} policy: {label} must be a decimal *string* (got "
            f"{type(raw).__name__}); quoting it is what keeps the bound byte-identical "
            "through the canonical form"
        )
    try:
        value = Decimal(raw)
    except InvalidOperation as invalid:
        raise PolicyError(f"{DISPERSION_KEY} policy: {label} {raw!r} is not a decimal") from invalid
    if not value.is_finite() or not -_LIMIT <= value <= _LIMIT:
        raise PolicyError(f"{DISPERSION_KEY} policy: {label} {raw} is outside -1..+1")
    return value


@dataclass(frozen=True, slots=True)
class DispersionPolicy:
    """A parsed ``dispersion`` body: which series and which band."""

    minimum: Decimal
    maximum: Decimal
    """Half-open: ``minimum <= value < maximum``."""
    version: str
    """The ``market_dispersion.dispersion_version`` this band is a band *of*. Not a
    default of the gate: the horizon, the universe and the reference all live in
    this string, so a band without a series names nothing."""

    def to_body(self) -> dict[str, Any]:
        """Exactly the shape that was stored — canonical order, bounds as strings.

        ``str(Decimal("-0.05"))`` is ``"-0.05"``: a ``Decimal`` keeps the exponent
        it was built with, so the round-trip is byte-identical and a stored policy
        never drifts from the one the operator typed.
        """
        return {"max": str(self.maximum), "min": str(self.minimum), "version": self.version}

    @property
    def note(self) -> str:
        """The human copy in the lineage: ``dispersion=-0.05-0.00``.

        The series is deliberately **not** in this string, for the reason
        ``breadth_policy.note`` gives: it is the changelog line an operator reads,
        and the series is auditable where it matters — in the stored body and in
        every envelope the version writes.
        """
        return f"{DISPERSION_KEY}={self.minimum}-{self.maximum}"


def parse_dispersion_policy(body: object) -> DispersionPolicy:
    """The ``dispersion`` body of the envelope, or :class:`PolicyError`."""
    if not isinstance(body, dict):
        raise PolicyError(f"{DISPERSION_KEY} policy must be a JSON object")
    typed = cast("dict[str, Any]", body)
    unknown = sorted(set(typed) - _FIELDS)
    if unknown:
        raise PolicyError(f"{DISPERSION_KEY} policy has unknown field(s): {', '.join(unknown)}")
    missing = sorted(_FIELDS - set(typed))
    if missing:
        raise PolicyError(f"{DISPERSION_KEY} policy is missing {', '.join(missing)}")
    version = typed["version"]
    if not isinstance(version, str) or version not in SUPPORTED_VERSIONS:
        raise PolicyError(
            f"{DISPERSION_KEY} policy: version {version!r} is not a series this build reads "
            f"({', '.join(sorted(SUPPORTED_VERSIONS))})"
        )
    minimum = _bound(typed["min"], label="min")
    maximum = _bound(typed["max"], label="max")
    if minimum >= maximum:
        raise PolicyError(
            f"{DISPERSION_KEY} policy: [{minimum}, {maximum}) is empty — a gate that refuses "
            "every value is a gate someone believes in and does not have"
        )
    if minimum == -_LIMIT and maximum == _LIMIT:
        raise PolicyError(
            f"{DISPERSION_KEY} policy: [-1, 1) lets every reading through, so nothing is ever "
            "refused except an unavailable series"
        )
    return DispersionPolicy(minimum=minimum, maximum=maximum, version=version)


def dispersion_clause(rest: str) -> dict[str, Any]:
    """``"-0.05-0.00"`` -> the body to store; ``"-0.05-0.00@dispersion_24h_v1"``
    names the series explicitly. Refuses the rest.

    The operator's half of the grammar of ``infra/scripts/derive_variant.py
    --policy``. Without ``@`` the series is
    :data:`~hunter_indicators.dispersion.CURRENT_DISPERSION_VERSION` — chosen
    *here*, once, and then written into the stored body, so the version is pinned at
    derivation time and never re-resolved by a later build. It goes through
    :func:`parse_dispersion_policy` before returning, so the CLI refuses exactly
    what the worker would refuse — one validator, not two that can drift.
    """
    band, _, series = rest.strip().partition("@")
    matched = _BAND.match(band.strip())
    if matched is None:
        raise PolicyError(
            f"--policy {DISPERSION_KEY}={rest!r}: expected <min>-<max>[@<series>], e.g. "
            "-0.05-0.00 (signed bounds are allowed: -0.10--0.03)"
        )
    return parse_dispersion_policy(
        {
            "min": matched["min"],
            "max": matched["max"],
            "version": series.strip() or CURRENT_DISPERSION_VERSION,
        }
    ).to_body()
