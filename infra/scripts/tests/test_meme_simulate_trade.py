"""``infra/scripts/meme_simulate_trade.py`` — the simulate path must never send.

The script exists so the owner can simulate a **sell on a holder-rewards curve**
on the VPS (T4.29c). Two things are worth a test rather than a habit:

1. the simulate path never reaches ``sendTransaction`` — proved dynamically (a fake
   RPC that explodes if asked to send, plus the recorded method list) *and*
   statically (no ``.send_transaction(...)`` call anywhere in the module's AST);
2. ``--simulate-only`` is mandatory, so a future copy-paste cannot drop it.

Run:
    uv run pytest infra/scripts/tests/test_meme_simulate_trade.py -q
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "packages/exchange-adapters/tests/fixtures/pumpfun"

from meme_simulate_trade import (  # noqa: E402  (path surgery must come first)
    SimulateOnlyRpc,
    SimulateOnlyViolation,
    SimulationArgs,
    parse_args,
    run_simulation,
    unsigned_transaction,
)

from hunter_exchanges.pumpfun.fee_config import fee_config_address  # noqa: E402
from hunter_exchanges.pumpfun.global_state import GLOBAL_ACCOUNT_ADDRESS  # noqa: E402
from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    TOKEN_2022_PROGRAM_ID,
    associated_token_address,
)
from hunter_exchanges.pumpfun.tx import bonding_curve_address  # noqa: E402
from hunter_exchanges.pumpfun.tx_rpc import AccountSnapshot, SimulationResult  # noqa: E402

HR_MINT = "7qSzmCMq9tGr2GiAiMrRQJh6esWcJrHhtChojPPqpump"
"""The coin T4.8c confirmed ``is_holder_reward = true`` on-chain (and whose *buy*
it simulated on mainnet); its curve account is the fixture below."""
USER = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"  # the robot wallet, public address
BLOCKHASH = "7Pptc9XnKLPqD1mUEPfDbYbYpbHGJsWEnV6vRHqZCMQ4"
HELD = 106_137_438_640


def _value(name: str) -> dict[str, Any]:
    raw = cast("dict[str, Any]", json.loads((FIXTURES / name).read_text(encoding="utf-8")))
    return dict(cast("dict[str, Any]", cast("dict[str, Any]", raw["result"])["value"]))


class FakeRpc:
    """Serves the four accounts the path reads, from real mainnet fixtures. Raises
    the moment anything tries to send."""

    allow_send = False

    def __init__(self) -> None:
        self.methods: list[str] = []
        curve = _value("t48c_rpc_bonding_curve_hr_raw.json")
        self.accounts: dict[str, dict[str, Any]] = {
            bonding_curve_address(HR_MINT): curve,
            GLOBAL_ACCOUNT_ADDRESS: _value("rpc_global_account_raw.json"),
            fee_config_address(): _value("rpc_fee_config_raw.json"),
            HR_MINT: {"owner": TOKEN_2022_PROGRAM_ID, "data": ["", "base64"], "lamports": 1},
        }
        self.accounts[
            associated_token_address(USER, HR_MINT, token_program=TOKEN_2022_PROGRAM_ID)
        ] = {"owner": TOKEN_2022_PROGRAM_ID, "data": ["", "base64"], "lamports": 2_039_280}

    def get_account(self, address: str, *, commitment: str = "confirmed") -> Any:
        self.methods.append(f"getAccountInfo:{address}")
        account = self.accounts.get(address)
        if account is None:
            return None
        return AccountSnapshot(
            address=address,
            owner=str(account["owner"]),
            data_base64=str(account["data"][0]),
            lamports=int(account["lamports"]),
            slot=447_228_373,
            executable=False,
        )

    def call(self, method: str, params: list[Any]) -> Any:
        self.methods.append(method)
        if method == "getTokenAccountBalance":
            return {"context": {"slot": 1}, "value": {"amount": str(HELD), "decimals": 6}}
        if method == "sendTransaction":
            raise AssertionError("the fake RPC was asked to send a transaction")
        raise AssertionError(f"unexpected RPC method {method}")

    def get_latest_blockhash(self, *, commitment: str = "confirmed") -> tuple[str, int]:
        self.methods.append("getLatestBlockhash")
        return BLOCKHASH, 425_380_780

    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = False, replace_blockhash: bool = False
    ) -> SimulationResult:
        self.methods.append("simulateTransaction")
        assert transaction[:65] == b"\x01" + b"\x00" * 64, "the simulated tx must be unsigned"
        assert (sig_verify, replace_blockhash) == (False, True)
        return SimulationResult(
            ok=True,
            err=None,
            logs=("Program log: Instruction: Sell",),
            units_consumed=62_037,
            slot=447_228_400,
            return_data=None,
        )

    def send_transaction(self, *_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("the fake RPC was asked to send a transaction")


def _sell_args() -> SimulationArgs:
    return SimulationArgs(mint=HR_MINT, user=USER, side="sell", token_amount=HELD)


def test_sell_on_a_holder_rewards_curve_builds_verifies_and_only_simulates() -> None:
    fake = FakeRpc()
    record = run_simulation(SimulateOnlyRpc(fake, throttle_s=0), _sell_args())
    assert record["curve"]["is_holder_reward"] is True
    assert record["side"] == "sell"
    assert record["verified"] is True
    assert record["simulation"]["ok"] is True
    assert record["intent"]["token_amount"] == HELD
    assert record["intent"]["blockhash"] == BLOCKHASH
    assert record["send_transaction_calls"] == 0
    assert "sendTransaction" not in fake.methods
    assert fake.methods.count("simulateTransaction") == 1


def test_the_fee_config_account_is_read_on_the_way() -> None:
    fake = FakeRpc()
    record = run_simulation(SimulateOnlyRpc(fake, throttle_s=0), _sell_args())
    assert record["fee_config"]["address"] == fee_config_address()
    assert record["fee_config"]["fee_tiers"] == [
        {"threshold": 0, "fees": {"lp_fee_bps": 0, "protocol_fee_bps": 95, "creator_fee_bps": 30}}
    ]


def test_a_missing_fee_config_account_logs_the_unavailable_event(capsys: Any) -> None:
    fake = FakeRpc()
    del fake.accounts[fee_config_address()]
    record = run_simulation(SimulateOnlyRpc(fake, throttle_s=0), _sell_args())
    assert record["fee_config"]["event"] == "meme_fee_config_unavailable"
    assert "meme_fee_config_unavailable" in capsys.readouterr().out
    assert record["simulation"]["ok"] is True  # the fallback constant keeps the sell quotable


def test_the_wrapper_refuses_every_road_to_a_send() -> None:
    rpc = SimulateOnlyRpc(FakeRpc(), throttle_s=0)
    with pytest.raises(SimulateOnlyViolation):
        rpc.send_transaction(b"\x00")
    with pytest.raises(SimulateOnlyViolation):
        rpc.call("sendTransaction", [])
    assert rpc.allow_send is False


def test_the_wrapper_refuses_an_inner_client_that_can_send() -> None:
    class Sender(FakeRpc):
        allow_send = True

    with pytest.raises(SimulateOnlyViolation, match="allow_send=True"):
        SimulateOnlyRpc(Sender())


def test_run_simulation_refuses_an_unwrapped_client() -> None:
    with pytest.raises(SimulateOnlyViolation, match="cannot vouch for"):
        run_simulation(cast("SimulateOnlyRpc", FakeRpc()), _sell_args())


def test_the_module_contains_no_call_to_send_transaction() -> None:
    """Static proof for the next editor: no ``x.send_transaction(...)`` call, and no
    ``sendTransaction`` string outside the two refusals."""
    source = (SCRIPTS_DIR / "meme_simulate_trade.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"send_transaction", "send"}
    ]
    assert calls == []
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "sendTransaction"
    ]
    assert len(literals) == 1  # the one comparison that refuses it


def test_simulate_only_is_mandatory() -> None:
    argv = ["--sell", "--mint", HR_MINT, "--user", USER]
    with pytest.raises(SystemExit) as excinfo:
        parse_args(argv)
    assert excinfo.value.code == 2
    args, parsed = parse_args(["--simulate-only", *argv])
    assert (args.side, args.mint, args.user) == ("sell", HR_MINT, USER)
    assert parsed.simulate_only is True


def test_unsigned_transaction_framing_matches_the_submitter() -> None:
    assert unsigned_transaction(b"msg") == b"\x01" + b"\x00" * 64 + b"msg"
