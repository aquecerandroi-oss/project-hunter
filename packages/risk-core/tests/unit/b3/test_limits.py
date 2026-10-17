"""§9: limits are data, validated on edit with named refusals ``limits_invalid:<campo>``;
JSON numbers are refused (every number is a decimal string); floats never construct;
the house rules (30 s approval, one open position) are not editable."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from hunter_risk_b3 import LimitsInvalid, initial_limits, parse_limits, parse_limits_json

pytestmark = pytest.mark.unit


def _profile(**update: object) -> dict[str, object]:
    data = initial_limits("v1").model_dump(mode="json")
    data.update(update)
    return data


def test_initial_values_are_the_contract_table() -> None:
    lim = initial_limits("v1")
    assert lim.daily_loss_limit_brl == Decimal("9000")
    assert lim.alloc_per_trade_brl == Decimal("1000")
    assert lim.max_loss_per_trade_brl == Decimal("250")
    assert (lim.max_contracts_per_order, lim.max_contracts_per_position) == (1, 1)
    assert lim.max_trades_per_day == 1
    assert lim.symbol_roots == ("WIN",)
    assert (lim.flatten_at_local, lim.rico_flatten_local) == (None, None)  # D6: no entries
    assert lim.approval_ttl_s == 30
    assert lim.max_open_positions == 1
    assert lim.equity_floor_brl is None
    assert lim.warning_fraction == Decimal("0.5")
    assert (lim.min_stop_ticks, lim.max_stop_ticks) == (10, 400)


def test_round_trip_through_json_strings() -> None:
    raw = json.dumps(_profile())
    assert parse_limits_json(raw) == initial_limits("v1")


def test_json_numbers_are_refused_with_the_field_name() -> None:
    data = _profile()
    data["daily_loss_limit_brl"] = "__NUM__"
    raw = json.dumps(data).replace('"__NUM__"', "9000")
    with pytest.raises(LimitsInvalid) as err:
        parse_limits_json(raw)
    assert err.value.reason == "limits_invalid:daily_loss_limit_brl"


def test_float_is_refused_at_construction() -> None:
    with pytest.raises(LimitsInvalid) as err:
        parse_limits(_profile(daily_loss_limit_brl=9000.0))
    assert err.value.reason.startswith("limits_invalid:")


@pytest.mark.parametrize(
    ("update", "field"),
    [
        ({"max_contracts_per_order": "2", "max_contracts_per_position": "1"}, "max_contracts_per_order"),
        ({"max_loss_per_trade_brl": "9001"}, "max_loss_per_trade_brl"),
        ({"min_stop_ticks": "400"}, "min_stop_ticks"),
        ({"warning_fraction": "0"}, "warning_fraction"),
        ({"margin_use_max_pct": "1.01"}, "margin_use_max_pct"),
        ({"flatten_at_local": "16:55:00", "rico_flatten_local": "17:10:00"}, "flatten_at_local"),
        ({"approval_ttl_s": "31"}, "approval_ttl_s"),
        ({"max_open_positions": "2"}, "max_open_positions"),
        ({"daily_loss_limit_brl": "-1"}, "daily_loss_limit_brl"),
        ({"sltp_record_api_ms": "600"}, "sltp_record_api_ms"),
        ({"surprise": "1"}, "surprise"),
    ],
)  # fmt: skip
def test_named_refusals(update: dict[str, object], field: str) -> None:
    with pytest.raises(LimitsInvalid) as err:
        parse_limits(_profile(**update))
    assert err.value.reason == f"limits_invalid:{field}"


def test_flatten_one_side_only_is_accepted_as_unset() -> None:
    lim = parse_limits(_profile(flatten_at_local="16:50:00"))
    assert lim.rico_flatten_local is None
