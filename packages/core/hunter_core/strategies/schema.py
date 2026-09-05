"""JSON Schema fragments for ``strategy_versions.parameters_schema``.

The schema describes **both** shapes a parameter set legitimately takes: the
typed in-memory form (``Decimal``/``int``) and the canonical wire form of
``params_format = 1``, where every number is a normalised string. Both hash to
the same ``params_hash``, and ``param_decimal``/``param_int`` read either — so a
schema that only allowed ``type: number`` would reject exactly what a round-trip
through JSONB produces (Astra, S1 design review, point 9).

Deliberate limitation, stated rather than hidden: these fragments constrain
*shape and presence*, not ranges. JSON Schema's ``minimum``/``maximum`` do not
apply to the string form, and inventing bounds that only bite in one of the two
representations would be worse than none. v0 only ever runs
``default_parameters``; validating operator-supplied overrides is M4's job, when
agents may actually override them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DECIMAL_PARAM: Mapping[str, Any] = {
    "type": ["string", "number"],
    "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
}
"""A decimal threshold: ``Decimal("1.5")`` or its canonical string ``"1.5"``."""

INTEGER_PARAM: Mapping[str, Any] = {
    "type": ["string", "integer"],
    "pattern": r"^-?[0-9]+$",
}
"""A whole number (window length, seconds), typed or as its canonical string."""

TIMEFRAME_PARAM: Mapping[str, Any] = {"type": "string", "enum": ["1m", "5m", "15m", "1h"]}
"""A timeframe, spelled exactly as ``hunter_core.domain.enums.Timeframe``."""


def schema_of(fields: Mapping[str, tuple[Mapping[str, Any], str]]) -> Mapping[str, Any]:
    """A closed object schema: every field required, nothing else accepted.

    ``additionalProperties: false`` and a complete ``required`` list are what make
    a frozen version verifiable — a parameter set with an extra key, or missing
    one, is a different experiment and must not validate.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": sorted(fields),
        "properties": {
            name: {**fragment, "description": description}
            for name, (fragment, description) in fields.items()
        },
    }
