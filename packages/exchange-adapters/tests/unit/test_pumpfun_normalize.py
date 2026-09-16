import base64
import json
from decimal import Decimal
from pathlib import Path

import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.curve import market_cap_sol
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID, decode_bonding_curve_account
from hunter_exchanges.pumpfun.mayhem_state import mayhem_pdas
from hunter_exchanges.pumpfun.normalize import (
    curve_state_from_rpc_account,
    parse_curve_state_rest,
    parse_new_token,
)
from hunter_exchanges.pumpfun.pdas import bonding_curve_address

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


def test_rest_reads_the_identity_once_from_the_same_payload() -> None:
    """T4.26: no second call — the description and the metadata uri the fixture
    already carries, with the twitter link absent (``None`` link -> ``None`` kind)."""
    raw = coin()
    state = parse_curve_state_rest(raw)
    assert state.description == "lets go up to the flowwww"
    assert state.uri == "https://ipfs.io/ipfs/QmTz5YyX9hFNCcX7T1t3ZUNNdo2dx4YhNU1CpmfUFXkWba"
    assert state.twitter is None
    assert state.twitter_kind is None
    assert state.twitter_post_id is None


def test_rest_classifies_a_post_link_and_truncates_a_long_description() -> None:
    raw = coin()
    raw["twitter"] = "https://x.com/CoachPatNFT/status/2098618936124375364"
    raw["website"] = "https://coachpat.example"
    raw["telegram"] = "t.me/coachpat"
    raw["description"] = "a" * 2500
    state = parse_curve_state_rest(raw)
    assert state.twitter_kind == "post"
    assert state.twitter_post_id == 2098618936124375364
    assert state.website == "https://coachpat.example"
    assert state.telegram == "t.me/coachpat"
    assert len(state.description or "") == 2000
    assert (state.description or "").endswith("truncated]")


def test_creation_has_observation_and_mayhem() -> None:
    raw = json.loads((FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text().splitlines()[4])
    event = parse_new_token(raw)
    assert event.mayhem_enabled is False
    assert event.observed_at == event.received_at
    assert market_cap_sol(Decimal(30), Decimal(1073000000), Decimal(1000000000)) == (
        Decimal(30) / Decimal(1073000000) * Decimal(1000000000)
    )
    assert event.bonding_curve == raw["bondingCurveKey"]
    assert event.bonding_curve_raw is None, "a correct frame has nothing to keep as evidence"


def test_a_mayhem_create_frame_carrying_the_shared_sol_vault_is_never_trusted() -> None:
    """R36/T4.39: a real captured Mayhem ``create`` frame
    (``pumpportal_ws_capture_raw.jsonl`` line 8, mint ``CGuNLUVmr…``) carries
    the Mayhem program's shared sol-vault in ``bondingCurveKey`` instead of the
    coin's own curve. ``bonding_curve`` must be the derived PDA; the frame's
    lie is kept only in ``bonding_curve_raw``."""
    raw = json.loads(
        (FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text().splitlines()[7],
        parse_float=Decimal,
    )
    assert raw["mint"] == "CGuNLUVmrers2FwnLjjVr9Tv8B726caZbRkY116Apump"
    assert raw["bondingCurveKey"] == mayhem_pdas().sol_vault
    event = parse_new_token(raw)
    assert event.bonding_curve == bonding_curve_address(raw["mint"])
    assert event.bonding_curve != mayhem_pdas().sol_vault
    assert event.bonding_curve_raw == mayhem_pdas().sol_vault


def test_a_mayhem_create_frame_with_a_correct_curve_keeps_no_raw_evidence() -> None:
    """43/100 diverge, 57/100 do not (R36): a Mayhem coin whose frame already
    carries the right PDA leaves ``bonding_curve_raw`` at ``None``."""
    raw = json.loads(
        (FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text().splitlines()[5],
        parse_float=Decimal,
    )
    assert raw["is_mayhem_mode"] is True
    event = parse_new_token(raw)
    assert event.bonding_curve == raw["bondingCurveKey"] == bonding_curve_address(raw["mint"])
    assert event.bonding_curve_raw is None


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
