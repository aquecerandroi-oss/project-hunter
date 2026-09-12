"""T4.8b — the program-identity check: at boot, ``program_upgraded`` is a named refusal
in live mode and a logged, heartbeat-visible state in inert mode; at runtime the
deploy slot alone flips the state. No signer is involved in any branch."""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_core.execution.meme.gates import MemeLiveTradingRefused
from hunter_exchanges.pumpfun.program_identity import (
    EXPECTED_PUMP_PROGRAM,
    UPGRADE_MESSAGE,
    pump_idl_account_address,
    pump_programdata_address,
)
from hunter_meme_executor.context import ExecutorContext, ExecutorState
from hunter_meme_executor.program_check import check_program_at_boot, program_check_once

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@dataclass
class FakeRpc:
    deploy_slot: int = EXPECTED_PUMP_PROGRAM.last_deploy_slot
    down: bool = False
    calls: list[str] = field(default_factory=lambda: list[str]())

    def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append(method)
        if self.down:
            raise RuntimeError("rpc down")
        if params[0] == pump_idl_account_address():
            return _fixture("t48b_rpc_idl_account_raw.json")["result"]
        if params[0] == pump_programdata_address():
            result = _fixture("t48b_rpc_programdata_raw.json")["result"]
            header = struct.pack("<IQ", 3, self.deploy_slot) + b"\x01" + b"\x00" * 32
            value = {**result["value"], "data": [base64.b64encode(header).decode(), "base64"]}
            return {**result, "value": value}
        raise AssertionError(params[0])

    def send_transaction(self, *_: Any, **__: Any) -> str:
        raise AssertionError("never")


@dataclass
class FakeChain:
    rpc: FakeRpc


@dataclass
class FakeConfig:
    live: bool


@dataclass
class FakeContext:
    config: FakeConfig
    chain: FakeChain
    state: ExecutorState = field(default_factory=ExecutorState)


def _ctx(*, live: bool, deploy_slot: int | None = None, down: bool = False) -> FakeContext:
    rpc = FakeRpc(down=down)
    if deploy_slot is not None:
        rpc.deploy_slot = deploy_slot
    return FakeContext(FakeConfig(live=live), FakeChain(rpc))


async def test_boot_with_the_program_the_fixtures_were_captured_from_passes() -> None:
    ctx = _ctx(live=True)
    await check_program_at_boot(cast(ExecutorContext, ctx))
    assert ctx.state.program_divergence is None
    assert ctx.state.program_idl_hash == EXPECTED_PUMP_PROGRAM.idl_sha256
    assert ctx.state.program_last_deploy_slot == EXPECTED_PUMP_PROGRAM.last_deploy_slot
    assert ctx.chain.rpc.calls == ["getAccountInfo", "getAccountInfo"]


async def test_boot_live_on_an_upgraded_program_is_refused_by_name_and_signs_nothing() -> None:
    ctx = _ctx(live=True, deploy_slot=EXPECTED_PUMP_PROGRAM.last_deploy_slot + 1)
    with pytest.raises(MemeLiveTradingRefused) as info:
        await check_program_at_boot(cast(ExecutorContext, ctx))
    assert info.value.reason == "program_upgraded"
    assert UPGRADE_MESSAGE in str(info.value) and "last_deploy_slot" in str(info.value)
    assert ctx.state.program_divergence is not None
    assert "sendTransaction" not in ctx.chain.rpc.calls
    assert set(ctx.chain.rpc.calls) == {"getAccountInfo"}


async def test_boot_live_with_the_identity_unreadable_fails_closed() -> None:
    ctx = _ctx(live=True, down=True)
    with pytest.raises(MemeLiveTradingRefused) as info:
        await check_program_at_boot(cast(ExecutorContext, ctx))
    assert info.value.reason == "program_identity_unreadable"


async def test_boot_inert_on_an_upgraded_program_keeps_running_and_says_so() -> None:
    ctx = _ctx(live=False, deploy_slot=1)
    await check_program_at_boot(cast(ExecutorContext, ctx))  # no raise: nothing to sign with
    assert (
        ctx.state.program_divergence is not None and UPGRADE_MESSAGE in ctx.state.program_divergence
    )
    unreadable = _ctx(live=False, down=True)
    await check_program_at_boot(cast(ExecutorContext, unreadable))
    assert unreadable.state.program_divergence is None and unreadable.state.rpc_errors == 1


async def test_the_runtime_check_reads_the_deploy_slot_only_and_flips_the_state() -> None:
    ctx = _ctx(live=True)
    await program_check_once(cast(ExecutorContext, ctx))
    assert ctx.chain.rpc.calls == ["getAccountInfo"] and ctx.state.program_divergence is None
    ctx.chain.rpc.deploy_slot = EXPECTED_PUMP_PROGRAM.last_deploy_slot + 7
    await program_check_once(cast(ExecutorContext, ctx))
    assert ctx.state.program_divergence is not None
    assert (
        f"last_deploy_slot {EXPECTED_PUMP_PROGRAM.last_deploy_slot + 7}"
        in ctx.state.program_divergence
    )
    assert ctx.state.program_last_deploy_slot == EXPECTED_PUMP_PROGRAM.last_deploy_slot + 7
    ctx.chain.rpc.down = True
    await program_check_once(cast(ExecutorContext, ctx))
    assert ctx.state.rpc_errors == 1 and ctx.state.program_divergence is not None, "never cleared"
