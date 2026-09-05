"""Canonical serialisation of a parameter set — ``params_format = 1``.

SHADOW-LAB.md "Decisão conjunta" §1 and §6: the identity of a shadow signal is
``uuid5(NAMESPACE_SHADOW, canonical(strategy_version_id, market_id, params_hash,
source_bar_close, cohort))``, and ``params_hash`` is the digest of the frozen
``default_parameters``. Both are only as stable as this function: if the bytes
change, every historical id changes with them, one experiment splits into two,
and ``ON CONFLICT (id) DO NOTHING`` stops de-duplicating a redelivery.

So the format is a written contract, versioned by
``strategy_versions.params_format`` and pinned by a golden vector in
``packages/core/tests/unit/test_strategies_canonical.py``:

- object keys sorted by code point, compact separators, UTF-8;
- **numbers are emitted as their normalised decimal string** — no trailing
  zeros, no exponent — so ``Decimal("1.50")``, ``1.5`` and ``"1.5"`` are the same
  parameter set. A string is otherwise passed through verbatim: ``"1.50"`` is a
  string, not the number, and normalising every numeric-looking string would
  corrupt genuine ones (a symbol like ``"007"``);
- ``bool`` stays a JSON boolean (it is a subclass of ``int``, and collapsing it
  would make ``{"enabled": true}`` and ``{"enabled": 1}`` one experiment);
- ``datetime`` must be timezone-aware and is rendered in UTC as ISO-8601 with
  ``Z``; a naive timestamp is refused rather than assumed (CLAUDE.md: time is
  always UTC);
- ``None`` is ``null``, and a null key is **not** the same as an absent key;
- lists keep the order they were given; ``uuid.UUID`` becomes its lowercase
  hyphenated string;
- anything else — and any non-finite number — raises instead of being coerced.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

PARAMS_FORMAT = 1
"""The version of this format, mirrored by ``strategy_versions.params_format``.

A change to any rule above is a new format number and a new migration, never an
edit here: the hash of a version that is already collecting evidence must not
move.
"""

_JsonValue = str | bool | None | list[Any] | dict[str, Any]


def _decimal_string(value: Decimal) -> str:
    """``Decimal`` -> normalised string: no trailing zeros, no exponent, one zero.

    Built from ``as_tuple()`` by hand, on purpose. The obvious spelling —
    ``normalize()`` then ``quantize()`` then ``format(d, "f")`` — is **context
    dependent**: under ``decimal.getcontext().prec = 6`` it silently rounds
    ``Decimal("1.23456789")`` to ``1.23457`` (two different parameter sets then
    hash the same), and ``Decimal("1E+30").quantize(Decimal(1))`` raises
    ``InvalidOperation`` for a perfectly finite number. A canonical form that
    depends on an ambient setting is not canonical: the same parameters would
    hash differently in the worker and in a recovery job.
    """
    if not value.is_finite():
        raise ValueError(f"{value!r} is not finite; a parameter must be a finite number")
    sign, digits, exponent = value.as_tuple()
    figures = "".join(str(digit) for digit in digits)
    exponent = int(exponent)  # finite: never 'n', 'N' or 'F'
    if exponent >= 0:
        integer, fraction = figures + "0" * exponent, ""
    elif len(figures) + exponent > 0:
        integer, fraction = figures[:exponent], figures[exponent:]
    else:
        integer, fraction = "0", "0" * -(len(figures) + exponent) + figures
    integer = integer.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    magnitude = f"{integer}.{fraction}" if fraction else integer
    if magnitude == "0":  # never "-0"
        return "0"
    return f"-{magnitude}" if sign else magnitude


def _number_string(value: float | int | Decimal) -> str:
    if isinstance(value, Decimal):
        return _decimal_string(value)
    if isinstance(value, int):
        return str(value)
    if value != value or value in (float("inf"), float("-inf")):  # NaN / ±inf
        raise ValueError(f"{value!r} is not finite; a parameter must be a finite number")
    try:
        return _decimal_string(Decimal(repr(value)))
    except InvalidOperation as exc:  # pragma: no cover - repr(float) always parses
        raise ValueError(f"{value!r} cannot be represented as a decimal") from exc


def _timestamp_string(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{value!r} is naive; a canonical timestamp must be timezone-aware (UTC)")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _prepare(value: object) -> _JsonValue:
    """One value in its canonical JSON shape (see the module docstring)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, Decimal)):
        return _number_string(value)
    if isinstance(value, datetime):
        return _timestamp_string(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Mapping):
        prepared: dict[str, _JsonValue] = {}
        for key, item in cast("Mapping[object, object]", value).items():
            if not isinstance(key, str):
                raise TypeError(f"canonical objects take string keys only, got {key!r}")
            prepared[key] = _prepare(item)
        return prepared
    if isinstance(value, Sequence):
        return [_prepare(item) for item in cast("Sequence[object]", value)]
    raise TypeError(f"{type(value).__name__} cannot be canonicalised (params_format 1)")


def canonical_json(obj: object) -> bytes:
    """The canonical UTF-8 bytes of ``obj`` under ``params_format = 1``."""
    return json.dumps(
        _prepare(obj),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def params_hash(params: object) -> str:
    """SHA-256 of :func:`canonical_json`, hex — ``agent_signals.params_hash``.

    Two spellings of the same parameter set hash the same; two different
    parameter sets never do.
    """
    return hashlib.sha256(canonical_json(params)).hexdigest()
