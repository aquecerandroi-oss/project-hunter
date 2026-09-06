"""Activating a ``strategy_version`` — the audited half of the ops script.

SHADOW-LAB.md §1: the **first activation** freezes everything that determines
the experiment, and ``0002_shadow_lab``'s trigger enforces that from then on
(DATABASE.md §16.1). So everything has to be right *before* ``activated_at`` is
set — after it, ``code_ref``, ``parameters_schema``, ``default_parameters`` and
``params_format`` can never be corrected, only superseded by a new version.

Four prerequisites, each a refusal and never a warning:

1. ``0002_shadow_lab`` is applied — without it there is nowhere to record the
   evidence, and nothing to enforce the freeze;
2. this build carries the code for ``(key, version)``;
3. the definitive ``code_ref`` — the per-version digest of
   :mod:`hunter_strategy_worker.code_ref` (the strategy's module plus the
   calculators it imports) — is computed and written in the same statement that
   activates;
4. ``default_parameters`` validate against ``parameters_schema``.

The parameter validator is deliberately small and local: the schemas this
project writes (``hunter_core.strategies.schema``) use exactly ``type``,
``pattern``, ``enum``, ``required`` and ``additionalProperties``, and adding a
dependency to check five keywords would be a worse trade than 40 lines that
refuse anything they do not understand.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

_SUPPORTED_KEYWORDS = frozenset(
    {
        "$schema",
        "type",
        "additionalProperties",
        "required",
        "properties",
        "pattern",
        "enum",
        "description",
    }
)

__all__ = [
    "ValidationReport",
    "validate_parameters",
]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Why a parameter set does or does not match its frozen schema."""

    errors: list[str] = field(default_factory=lambda: [])

    @property
    def ok(self) -> bool:
        return not self.errors


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    if expected == "null":
        return value is None
    return False


def _check_field(name: str, value: Any, rule: Mapping[str, Any], errors: list[str]) -> None:
    unknown = set(rule) - _SUPPORTED_KEYWORDS
    if unknown:
        errors.append(
            f"{name}: schema uses keywords this validator does not check: {sorted(unknown)}"
        )
        return
    expected = rule.get("type")
    if expected is not None:
        allowed = [expected] if isinstance(expected, str) else list(expected)
        if not any(_type_ok(value, option) for option in allowed):
            errors.append(f"{name}: expected type {allowed}, got {type(value).__name__}")
            return
    pattern = rule.get("pattern")
    if pattern is not None and isinstance(value, str) and re.fullmatch(pattern, value) is None:
        errors.append(f"{name}: {value!r} does not match {pattern}")
    choices = rule.get("enum")
    if choices is not None and value not in choices:
        errors.append(f"{name}: {value!r} is not one of {choices}")


def validate_parameters(schema: Mapping[str, Any], params: Mapping[str, Any]) -> ValidationReport:
    """Check ``params`` against ``schema``. Empty errors means it validated."""
    errors: list[str] = []
    if schema.get("type") not in (None, "object"):
        return ValidationReport([f"schema type {schema.get('type')!r} is not supported"])
    properties: Mapping[str, Any] = schema.get("properties") or {}
    required: Sequence[str] = schema.get("required") or []
    for name in required:
        if name not in params:
            errors.append(f"{name}: required parameter is missing")
    if schema.get("additionalProperties") is False:
        for name in params:
            if name not in properties:
                errors.append(f"{name}: not declared by the frozen schema")
    for name, rule in properties.items():
        if name in params:
            _check_field(name, params[name], rule, errors)
    return ValidationReport(errors)
