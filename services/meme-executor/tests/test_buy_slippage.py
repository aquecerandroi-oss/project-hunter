"""T4.59 — the buy's tolerance from the environment (``MEME_BUY_MAX_SLIPPAGE_PCT``,
per cent, ``(0, 20]``), reaching ``build_buy`` as ``max_slippage_bps`` on the entries
path, published in the heartbeat's ``policy``; and the network fee a buy that landed
with ``6002 TooMuchSolRequired`` paid, written to the order's ``fill`` so the wallet
panel counts it."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import SubmitResult
from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_exchanges.pumpfun.quote import BuyQuote
from hunter_meme_executor import send_path
from hunter_meme_executor.build import decode_fills
from hunter_meme_executor.chain import CurveRead
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.heartbeat import policy_fields
from hunter_meme_executor.priority_fee import PriorityFeeChoice
from hunter_meme_executor.send_path import (
    build_entry_buy,
    failed_onchain_fill,
    record_failed_onchain_fee,
    record_send_result,
)
from hunter_meme_executor.send_tuning import ENV_BUY_MAX_SLIPPAGE_PCT, SendTuning
from hunter_risk_meme import MEME_PAPER_V0

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
USER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
BLOCKHASH = "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ"
SIGNATURE = "5" * 87
ERR_6002 = {"InstructionError": [3, {"Custom": 6002}]}


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _global_account() -> Any:
    g = _fixture("rpc_global_account_raw.json")["result"]["value"]
    return decode_global_account(g["data"][0], owner=g["owner"])


def _curve_read() -> CurveRead:
    """The same curve ``test_send_tuning`` rebuilds from the recorded buy."""
    (fill,) = decode_fills(_fixture("rpc_tx_buy_raw.json")["result"])
    e = fill.event
    account = BondingCurveAccount(
        virtual_token_reserves=e.virtual_token_reserves + e.token_amount,
        virtual_sol_reserves=e.virtual_sol_reserves - e.sol_amount,
        real_token_reserves=e.real_token_reserves + e.token_amount,
        real_sol_reserves=1,
        token_total_supply=1_000_000_000_000_000,
        complete=False,
        creator=e.creator,
        is_mayhem_mode=False,
        is_cashback_coin=True,
        quote_mint="11111111111111111111111111111111",
    )
    return CurveRead(e.mint, account, TOKEN_2022, 446_378_553, datetime(2026, 9, 12, tzinfo=UTC))


def _config(env: dict[str, str]) -> ExecutorConfig:
    return ExecutorConfig(
        live=True,
        cluster="mainnet",
        rpc_url="https://rpc.example",
        limits=MEME_PAPER_V0,
        system_kill_switch=KillSwitchState.ACTIVE,
        kill_file=None,
        send=SendTuning.from_env(env),
    )


# ------------------------------------------------------------------ parser
def test_absent_is_the_profiles_one_per_cent() -> None:
    tuning = SendTuning.from_env({})
    assert tuning.buy_max_slippage_pct == Decimal(1)
    assert tuning.buy_slippage_bps() == 100 == int(MEME_PAPER_V0.max_slippage_pct * 10_000)


@pytest.mark.parametrize(("raw", "bps"), [("3", 300), ("0.5", 50), ("20", 2_000), (" 2.5 ", 250)])
def test_a_valid_value_is_read_in_per_cent(raw: str, bps: int) -> None:
    tuning = SendTuning.from_env({ENV_BUY_MAX_SLIPPAGE_PCT: raw})
    assert tuning.buy_slippage_bps() == bps
    # the exit tolerances are untouched by the buy's knob
    assert tuning.exit_slippage_bps("time_stop") == 500
    assert tuning.exit_slippage_bps("rug_signal") == 1_500


@pytest.mark.parametrize("raw", ["0", "-1", "20.01", "25", "50", "one", "1e", ""])
def test_out_of_range_or_nonsense_falls_back_to_the_default(raw: str) -> None:
    tuning = SendTuning.from_env({ENV_BUY_MAX_SLIPPAGE_PCT: raw})
    assert tuning.buy_max_slippage_pct == Decimal(1)
    assert tuning.buy_slippage_bps() == 100


def test_the_buy_ceiling_is_tighter_than_the_exits() -> None:
    # 30 % is a legal exit tolerance and an illegal buy tolerance
    both = SendTuning.from_env({ENV_BUY_MAX_SLIPPAGE_PCT: "30", "MEME_EXIT_MAX_SLIPPAGE_PCT": "30"})
    assert both.exit_max_slippage_pct == Decimal(30)
    assert both.buy_max_slippage_pct == Decimal(1)


# ------------------------------------------------------------ buy plumbing
def test_build_entry_buy_hands_the_configured_bps_to_build_buy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def recorder(read: Any, global_account: Any, **kwargs: Any) -> Any:
        seen.update(kwargs, read=read, global_account=global_account)
        return "built"

    monkeypatch.setattr(send_path, "build_buy", recorder)
    cfg = _config({ENV_BUY_MAX_SLIPPAGE_PCT: "3"})
    read, global_account = object(), object()
    fee = PriorityFeeChoice.static(150_000)
    out = build_entry_buy(
        cfg,
        cast(Any, read),
        cast(Any, global_account),
        user=USER,
        budget_sol=Decimal("0.28"),
        fee=fee,
        blockhash=BLOCKHASH,
        last_valid_block_height=150,
        creates_ata=True,
    )
    assert out == "built"
    assert seen["max_slippage_bps"] == 300
    assert seen["read"] is read and seen["global_account"] is global_account
    assert seen["user"] == USER
    assert seen["budget_sol"] == Decimal("0.28")
    assert seen["compute_unit_limit"] == cfg.compute_unit_limit
    assert seen["compute_unit_price_micro_lamports"] == 150_000
    assert seen["blockhash"] == BLOCKHASH
    assert seen["last_valid_block_height"] == 150
    assert seen["creates_ata"] is True


def test_the_default_config_still_builds_the_buy_at_one_per_cent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def recorder(*_: Any, **kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(send_path, "build_buy", recorder)
    build_entry_buy(
        _config({}),
        cast(Any, object()),
        cast(Any, object()),
        user=USER,
        budget_sol=Decimal("0.28"),
        fee=PriorityFeeChoice.static(100_000),
        blockhash=BLOCKHASH,
        last_valid_block_height=1,
        creates_ata=False,
    )
    assert seen["max_slippage_bps"] == 100


def test_a_real_buy_built_at_three_per_cent_carries_it_in_the_intent() -> None:
    def built_with(pct: str) -> Any:
        return build_entry_buy(
            _config({ENV_BUY_MAX_SLIPPAGE_PCT: pct}),
            _curve_read(),
            _global_account(),
            user=USER,
            budget_sol=Decimal("0.05"),
            fee=PriorityFeeChoice.static(100_000),
            blockhash=BLOCKHASH,
            last_valid_block_height=150,
            creates_ata=True,
        )

    three, one = built_with("3"), built_with("1")
    assert isinstance(three.quote, BuyQuote) and isinstance(one.quote, BuyQuote)
    assert three.quote.max_slippage_bps == 300 and one.quote.max_slippage_bps == 100
    # same budget, same tokens: the tolerance only widens the instruction's ceiling
    assert three.quote.token_amount == one.quote.token_amount
    assert three.quote.total_cost == one.quote.total_cost
    assert three.intent.sol_limit == three.quote.max_sol_cost > one.quote.max_sol_cost
    assert three.intent_json()["max_slippage_bps"] == 300
    assert three.verify(three.message) is not None


# --------------------------------------------------------------- heartbeat
def test_the_policy_blob_publishes_the_buy_tolerance() -> None:
    default = json.loads(json.dumps(policy_fields(MEME_PAPER_V0)))
    assert default["buy_max_slippage_pct"] == "1"
    tuned = policy_fields(MEME_PAPER_V0, SendTuning.from_env({ENV_BUY_MAX_SLIPPAGE_PCT: "2.5"}))
    assert tuned["buy_max_slippage_pct"] == "2.5"
    # T4.58's window and the five are still there
    assert tuned["curve_progress_max_pct"] == "0.50"
    assert tuned["max_open_positions"] == 3


# ----------------------------------------------------- fee of a failed buy
def _failed_tx(fee: int, err: Any = ERR_6002) -> dict[str, Any]:
    return {"slot": 370_000_001, "meta": {"err": err, "fee": fee}, "transaction": {}}


def test_a_landed_and_failed_transaction_yields_its_paid_fee_as_fill() -> None:
    fill = failed_onchain_fill(
        _failed_tx(105_000), signature=SIGNATURE, reason="onchain_error:{'Custom': 6002}"
    )
    assert fill == {
        "failed_onchain": True,
        "network_fee_lamports": 105_000,
        "err": ERR_6002,
        "reason": "onchain_error:{'Custom': 6002}",
        "signature": SIGNATURE,
        "slot": 370_000_001,
    }
    json.dumps(fill)


def test_a_transaction_without_an_error_or_unreadable_is_not_a_failed_fill() -> None:
    assert failed_onchain_fill(None, signature=SIGNATURE, reason="onchain_error:x") is None
    assert failed_onchain_fill({}, signature=SIGNATURE, reason="onchain_error:x") is None
    landed = {"meta": {"err": None, "fee": 5_000}}
    assert failed_onchain_fill(landed, signature=SIGNATURE, reason="onchain_error:x") is None
    bad_fee = {"meta": {"err": ERR_6002, "fee": "lots"}}
    assert failed_onchain_fill(bad_fee, signature=SIGNATURE, reason="onchain_error:x") is None


@dataclass
class _Rpc:
    transaction: dict[str, Any] | None = None
    raise_on_read: bool = False
    asked: list[str] = field(default_factory=lambda: list[str]())

    def get_transaction(self, signature: str, **_: Any) -> dict[str, Any] | None:
        self.asked.append(signature)
        if self.raise_on_read:
            raise ConnectionError("rpc down")
        return self.transaction


@dataclass
class _Session:
    executed: list[tuple[str, dict[str, Any]]] = field(default_factory=lambda: list[Any]())

    async def execute(self, statement: Any, params: dict[str, Any]) -> None:
        self.executed.append((str(statement), params))


class _Sessions:
    """Stands in for ``role_session``: one fake session, no database."""

    def __init__(self) -> None:
        self.session = _Session()

    def __call__(self, *_: Any, **__: Any) -> _Sessions:
        return self

    async def __aenter__(self) -> _Session:
        return self.session

    async def __aexit__(self, *_: Any) -> None:
        return None


def _ctx(rpc: _Rpc) -> Any:
    state = SimpleNamespace(resends_total=0, resend_errors_total=0, last_resends=0)
    return SimpleNamespace(chain=SimpleNamespace(rpc=rpc), state=state, session_factory=None)


def _run(ctx: Any, result: SubmitResult, monkeypatch: pytest.MonkeyPatch) -> _Session:
    sessions = _Sessions()
    monkeypatch.setattr(send_path, "role_session", sessions)
    asyncio.run(record_send_result(ctx, "meme:pid", result))
    return sessions.session


def test_a_buy_that_failed_on_chain_records_the_fee_it_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _Rpc(_failed_tx(105_000))
    result = SubmitResult(
        "pid", SubmitState.FAILED, "onchain_error:{'Custom': 6002}", SIGNATURE, None, resends=2
    )
    session = _run(_ctx(rpc), result, monkeypatch)
    assert rpc.asked == [SIGNATURE]
    stats, fill_write = session.executed
    assert "intent = intent ||" in stats[0]
    assert json.loads(stats[1]["patch"]) == {"resends": 2, "resend_errors": 0}
    assert "SET fill = " in fill_write[0]
    assert "status = 'failed' AND fill IS NULL" in fill_write[0]
    assert fill_write[1]["key"] == "meme:pid"
    written = json.loads(fill_write[1]["fill"])
    assert written["network_fee_lamports"] == 105_000
    assert written["failed_onchain"] is True
    assert written["signature"] == SIGNATURE


@pytest.mark.parametrize(
    "result",
    [
        # a simulation failure never reached the chain: nothing was paid
        SubmitResult("pid", SubmitState.FAILED, "simulation_failed:6002", None, None),
        SubmitResult("pid", SubmitState.FAILED, "preflight_failed:RpcError", SIGNATURE, None),
        SubmitResult("pid", SubmitState.FAILED, "blockhash_expired_never_landed", SIGNATURE, None),
        SubmitResult("pid", SubmitState.SUBMITTED_UNCONFIRMED, "not_found_yet", SIGNATURE, None),
        SubmitResult("pid", SubmitState.CONFIRMED, "trade_event", SIGNATURE, {"x": 1}),
    ],
)
def test_only_a_landed_failure_is_charged(
    result: SubmitResult, monkeypatch: pytest.MonkeyPatch
) -> None:
    rpc = _Rpc(_failed_tx(105_000))
    session = _run(_ctx(rpc), result, monkeypatch)
    assert rpc.asked == []
    assert len(session.executed) == 1 and "intent = intent ||" in session.executed[0][0]


def test_an_unreadable_transaction_leaves_the_refusal_standing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = _Rpc(raise_on_read=True)
    result = SubmitResult(
        "pid", SubmitState.FAILED, "onchain_error:{'Custom': 6002}", SIGNATURE, None
    )
    session = _run(_ctx(rpc), result, monkeypatch)
    assert rpc.asked == [SIGNATURE]
    assert len(session.executed) == 1  # the stats still land; no fill was invented


def test_a_replayed_result_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = _Rpc(_failed_tx(105_000))
    result = SubmitResult(
        "pid", SubmitState.FAILED, "onchain_error:{'Custom': 6002}", SIGNATURE, None, replayed=True
    )
    session = _run(_ctx(rpc), result, monkeypatch)
    assert rpc.asked == [] and session.executed == []


def test_a_reconcile_that_lands_on_an_error_records_the_fee_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main.reconcile_once`` / ``exits._reconcile_sell`` settle a row that timed out
    unconfirmed; when the chain answers ``err``, the fee was paid all the same."""
    rpc = _Rpc(_failed_tx(7_000))
    sessions = _Sessions()
    monkeypatch.setattr(send_path, "role_session", sessions)
    result = SubmitResult(
        "pid", SubmitState.FAILED, "onchain_error:{'Custom': 6002}", SIGNATURE, None
    )
    asyncio.run(record_failed_onchain_fee(_ctx(rpc), "meme:pid:exit:1", result))
    (write,) = sessions.session.executed
    assert "SET fill = " in write[0] and write[1]["key"] == "meme:pid:exit:1"
    assert json.loads(write[1]["fill"])["network_fee_lamports"] == 7_000
    # a reconcile with nothing to settle writes nothing
    asyncio.run(record_failed_onchain_fee(_ctx(rpc), "meme:pid:exit:1", None))
    assert len(sessions.session.executed) == 1
