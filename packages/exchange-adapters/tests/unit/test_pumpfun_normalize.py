import base64
import json
from decimal import Decimal
from pathlib import Path

import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.curve import market_cap_sol
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID, decode_bonding_curve_account
from hunter_exchanges.pumpfun.normalize import (
    curve_state_from_rpc_account,
    parse_curve_state_rest,
    parse_new_token,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def coin() -> dict[str, object]:
    return json.loads((FIXTURES / "frontend_api_v3_coin_by_mint_response_raw.json").read_text())


def test_rest_preserves_mayhem_and_units() -> None:
    raw = coin()
    state = parse_curve_state_rest(raw)
    assert state.mayhem_state == "paused"
    assert state.mayhem_mode == "manual"
    assert state.virtual_sol_reserves == Decimal("3.082705753")
    assert state.observed_at == state.received_at


def test_creation_has_observation_and_mayhem() -> None:
    raw = json.loads((FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text().splitlines()[4])
    event = parse_new_token(raw)
    assert event.mayhem_enabled is False
    assert event.observed_at == event.received_at
    assert market_cap_sol(Decimal(30), Decimal(1073000000), Decimal(1000000000)) == (
        Decimal(30) / Decimal(1073000000) * Decimal(1000000000)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("complete", "false"),
        ("virtual_sol_reserves", 1.5),
        ("virtual_token_reserves", 0),
        ("quote_mint", "USDC"),
    ],
)
def test_reject_invalid_rest(field: str, value: object) -> None:
    raw = coin()
    raw[field] = value
    with pytest.raises(MalformedMessage):
        parse_curve_state_rest(raw)


@pytest.mark.parametrize("offset", [0, 48, 81, 82])
def test_decoder_checks_type_and_booleans(offset: int) -> None:
    raw = json.loads((FIXTURES / "rpc_get_account_info_bonding_curve_raw.json").read_text())
    data = bytearray(base64.b64decode(raw["result"]["value"]["data"][0]))
    data[offset] = 7
    with pytest.raises(MalformedMessage):
        decode_bonding_curve_account(base64.b64encode(data).decode(), owner=PUMP_PROGRAM_ID)


def test_new_live_account_fixture() -> None:
    raw = json.loads((FIXTURES / "rpc_a41_raw.json").read_text())["result"]["value"]
    account = decode_bonding_curve_account(raw["data"][0], owner=raw["owner"])
    coin_raw = json.loads((FIXTURES / "coin_a41_raw.json").read_text())
    state = curve_state_from_rpc_account(coin_raw["mint"], account)
    rest = parse_curve_state_rest(coin_raw)
    assert state.total_supply == rest.total_supply
    assert account.creator == coin_raw["creator"]
    assert state.virtual_sol_reserves == Decimal(account.virtual_sol_reserves) / Decimal(10**9)
    # Reads are not atomic; reserves must not be asserted equal across providers.


@pytest.mark.parametrize("field", ["mint", "signature", "traderPublicKey"])
def test_creation_rejects_null_identity(field: str) -> None:
    raw = json.loads((FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text().splitlines()[4])
    raw[field] = None
    with pytest.raises(MalformedMessage):
        parse_new_token(raw)
