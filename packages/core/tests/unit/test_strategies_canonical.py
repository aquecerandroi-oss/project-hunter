"""Canonical serialisation ``params_format = 1`` — SHADOW-LAB.md "Decisão conjunta" §1.

The point of this format is that two spellings of the same parameter set produce
the same bytes, and therefore the same ``params_hash`` and the same deterministic
``agent_signals.id``. A signal identity that changed because someone wrote
``1.50`` instead of ``1.5`` would silently split one experiment into two.

Equally important is what must *not* collapse: a hash that ignored the
difference between two genuinely different parameter sets would merge two
experiments into one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from hunter_core.strategies.canonical import PARAMS_FORMAT, canonical_json, params_hash

pytestmark = pytest.mark.unit


def test_params_format_is_one() -> None:
    assert PARAMS_FORMAT == 1


@pytest.mark.parametrize(
    "equivalent",
    [
        ({"a": Decimal("1.50")}, {"a": "1.5"}, {"a": 1.5}),
        ({"a": Decimal("100")}, {"a": "100"}, {"a": 100}),
        ({"a": Decimal("0.30")}, {"a": "0.3"}, {"a": 0.3}),
        ({"a": Decimal("-0.0")}, {"a": "0"}, {"a": 0}),
    ],
)
def test_equivalent_number_spellings_share_one_canonical_form(
    equivalent: tuple[dict[str, object], ...],
) -> None:
    """A number is canonicalised to its normalised decimal string: no trailing
    zeros, no exponent — so ``Decimal("1.50")``, ``"1.5"`` and ``1.5`` are one
    parameter set, not three experiments."""
    forms = {canonical_json(candidate) for candidate in equivalent}
    assert len(forms) == 1, f"spellings disagree: {[canonical_json(c) for c in equivalent]}"
    hashes = {params_hash(candidate) for candidate in equivalent}
    assert len(hashes) == 1


def test_key_order_does_not_change_the_canonical_form() -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_utc_offset_and_z_are_the_same_instant() -> None:
    with_offset = datetime(2026, 1, 1, tzinfo=timezone(timedelta(0)))
    assert canonical_json({"t": with_offset}) == b'{"t":"2026-01-01T00:00:00Z"}'


def test_a_non_utc_offset_is_normalised_to_utc() -> None:
    sao_paulo = datetime(2026, 1, 1, 21, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert canonical_json({"t": sao_paulo}) == canonical_json(
        {"t": datetime(2026, 1, 2, tzinfo=UTC)}
    )


def test_a_naive_datetime_is_refused() -> None:
    """UTC is not a default here: a naive timestamp is an unanswered question."""
    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_json({"t": datetime(2026, 1, 1)})  # noqa: DTZ001


def test_none_is_null_and_missing_is_not_the_same_as_null() -> None:
    assert canonical_json({"a": None}) == b'{"a":null}'
    assert canonical_json({"a": None}) != canonical_json({})


def test_list_order_is_preserved() -> None:
    assert canonical_json({"a": [2, 1]}) != canonical_json({"a": [1, 2]})
    assert canonical_json({"a": [2, 1]}) == b'{"a":["2","1"]}'


def test_booleans_stay_json_booleans() -> None:
    """``True`` is not ``1``: bool is a subclass of int, and collapsing it would
    make ``{"enabled": True}`` and ``{"enabled": 1}`` the same experiment."""
    assert canonical_json({"a": True}) == b'{"a":true}'
    assert canonical_json({"a": True}) != canonical_json({"a": 1})


def test_uuid_is_canonicalised_lowercase() -> None:
    run = uuid.UUID("0199e4a0-1c3d-7a11-8f0a-2b3c4d5e6f70")
    assert canonical_json({"run_id": run}) == canonical_json({"run_id": str(run)})
    assert canonical_json({"run_id": uuid.UUID(str(run).upper())}) == canonical_json(
        {"run_id": run}
    )


def test_nested_mappings_and_sequences_are_canonicalised_too() -> None:
    assert canonical_json({"a": {"b": Decimal("2.0"), "c": (Decimal("1.10"),)}}) == canonical_json(
        {"a": {"c": ["1.1"], "b": 2}}
    )


def test_different_parameter_sets_never_collide() -> None:
    assert params_hash({"a": 1}) != params_hash({"a": 2})
    assert params_hash({"a": 1}) != params_hash({"b": 1})
    assert params_hash({"a": "1"}) != params_hash({"a": "01"})


def test_non_finite_numbers_are_refused() -> None:
    for bad in (float("nan"), float("inf"), Decimal("NaN")):
        with pytest.raises(ValueError, match="finite"):
            canonical_json({"a": bad})


def test_an_unsupported_type_is_refused_instead_of_stringified() -> None:
    with pytest.raises(TypeError, match="cannot be canonicalised"):
        canonical_json({"a": object()})


def test_non_string_keys_are_refused() -> None:
    with pytest.raises(TypeError, match="string keys"):
        canonical_json({1: "a"})


def test_the_canonical_form_does_not_depend_on_the_decimal_context() -> None:
    """Found by Astra's review of this diff.

    ``normalize()``/``quantize()`` obey ``decimal.getcontext().prec``: under a
    precision of 6 the first spelling below rounded to ``1.23457``, so a worker
    and a recovery job with different contexts produced different
    ``params_hash`` values for the same version — and two parameter sets that
    differ in the ninth digit collided.
    """
    params = {"a": Decimal("1.23456789")}
    with localcontext() as context:
        context.prec = 6
        assert canonical_json(params) == b'{"a":"1.23456789"}'
        assert params_hash({"a": Decimal("1.234567891")}) != params_hash(
            {"a": Decimal("1.234567892")}
        )
    assert canonical_json(params) == b'{"a":"1.23456789"}'


def test_a_large_exponent_is_still_written_in_full() -> None:
    """``Decimal("1E+30")`` is finite; ``quantize`` raised ``InvalidOperation`` on it."""
    assert canonical_json({"a": Decimal("1E+30")}) == b'{"a":"1' + b"0" * 30 + b'"}'
    assert canonical_json({"a": Decimal("1E-12")}) == b'{"a":"0.000000000001"}'


def test_the_hash_is_pinned_so_the_format_cannot_drift_silently() -> None:
    """A golden vector: changing the canonical form changes every historical
    signal id, so it has to be a deliberate ``params_format`` bump."""
    params = {
        "atr_period": 14,
        "atr_multiple": Decimal("1.50"),
        "anchor": datetime(2026, 1, 1, tzinfo=UTC),
        "timeframes": ["15m", "1m"],
        "enabled": True,
        "unset": None,
    }
    assert canonical_json(params) == (
        b'{"anchor":"2026-01-01T00:00:00Z","atr_multiple":"1.5","atr_period":"14",'
        b'"enabled":true,"timeframes":["15m","1m"],"unset":null}'
    )
    assert params_hash(params) == (
        "3be7678182d4a8fdfc4d9f062c493721f62bcf91eb5fba781cbdbb0139f77aa3"
    )
