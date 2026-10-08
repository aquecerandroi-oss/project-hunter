"""The program-identity check: at boot, ``program_upgraded`` is a named refusal
in live mode and a logged, heartbeat-visible state in inert mode; at runtime the
deploy slot alone flips the state. No signer is involved in any branch.

Fixtures refreshed to T4.8g (2026-10-08 deploy, slot 454596459, read 2026-10-08) —
``EXPECTED_PUMP_PROGRAM`` moved from T4.8f's values. That deploy left the IDL account untouched
(a fourth time), so only the deploy slot separates them."""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.program_identity import (
    EXPECTED_PUMP_PROGRAM,
    UPGRADE_MESSAGE,
    pump_idl_account_address,
    pump_programdata_address,
)
from hunter_exchanges.pumpfun.program_watch import WATCHED_PROGRAMS, programdata_address
from hunter_meme_executor.context import ExecutorContext, ExecutorState
from hunter_meme_executor.program_check import check_program_at_boot, program_check_once

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _header_value(label: str, slot: int) -> dict[str, Any]:
    """The recorded ``ProgramData`` header of ``label`` (t48g), with its deploy slot replaced."""
    value = _fixture(f"t48g_rpc_programdata_{label}_raw.json")["result"]["value"]
    header = struct.pack("<IQ", 3, slot) + b"\x01" + b"\x00" * 32
    return {**value, "data": [base64.b64encode(header).decode(), "base64"]}


@dataclass
class FakeRpc:
    deploy_slot: int = EXPECTED_PUMP_PROGRAM.last_deploy_slot
    pumpswap_slot: int = WATCHED_PROGRAMS[0].last_deploy_slot
    fees_slot: int = WATCHED_PROGRAMS[1].last_deploy_slot
    down: bool = False
    multiple_down: bool = False
    identity_down: bool = False
    calls: list[str] = field(default_factory=lambda: list[str]())

    def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append(method)
        if (
            self.down
            or (self.multiple_down and method == "getMultipleAccounts")
            or (self.identity_down and method == "getAccountInfo")
        ):
            raise RuntimeError("rpc down")
        if method == "getMultipleAccounts":  # T4.8f: the runtime detector, all programs at once
            slots = {
                pump_programdata_address(): ("pump", self.deploy_slot),
                programdata_address(WATCHED_PROGRAMS[0].program_id): (
                    "pumpswap",
                    self.pumpswap_slot,
                ),
                programdata_address(WATCHED_PROGRAMS[1].program_id): ("pump_fees", self.fees_slot),
            }
            values = [_header_value(*slots[a]) for a in params[0]]
            return {"context": {"slot": 454629051}, "value": values}
        if params[0] == pump_idl_account_address():
            return _fixture("t48g_rpc_idl_account_raw.json")["result"]
        if params[0] == pump_programdata_address():
            result = _fixture("t48g_rpc_programdata_pump_raw.json")["result"]
            header = struct.pack("<IQ", 3, self.deploy_slot) + b"\x01" + b"\x00" * 32
            value = {**result["value"], "data": [base64.b64encode(header).decode(), "base64"]}
            return {**result, "value": value}
        raise AssertionError(params[0])

    def send_transaction(self, *_: Any, **__: Any) -> str:
        raise AssertionError("never")

    def close(self) -> None:
        return None


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
    assert ctx.state.program_identity_verified is True and ctx.state.program_block is None
    assert ctx.chain.rpc.calls == ["getAccountInfo", "getAccountInfo", "getMultipleAccounts"]


async def test_boot_live_on_an_upgraded_program_boots_exits_only_and_signs_nothing() -> None:
    """T4.8f F3: the process stays up (exits and reconciliation must keep running with a
    position open) — only entries are refused, by name."""
    ctx = _ctx(live=True, deploy_slot=EXPECTED_PUMP_PROGRAM.last_deploy_slot + 1)
    await check_program_at_boot(cast(ExecutorContext, ctx))  # no raise
    assert ctx.state.program_divergence is not None
    assert UPGRADE_MESSAGE in ctx.state.program_divergence
    assert "last_deploy_slot" in ctx.state.program_divergence
    assert ctx.state.program_identity_verified is False
    assert ctx.state.program_block is not None and ctx.state.program_block[0] == "program_upgraded"
    assert "sendTransaction" not in ctx.chain.rpc.calls
    assert set(ctx.chain.rpc.calls) <= {"getAccountInfo", "getMultipleAccounts"}


async def test_boot_live_with_the_identity_unreadable_boots_exits_only() -> None:
    """Unknown is not "unchanged": nothing marks the identity verified, so entries stay refused
    (``program_identity_unverified``) — but the process lives to run the exits."""
    ctx = _ctx(live=True, down=True)
    await check_program_at_boot(cast(ExecutorContext, ctx))  # no raise
    assert ctx.state.program_identity_verified is False and ctx.state.program_divergence is None
    assert ctx.state.rpc_errors == 1
    assert ctx.state.program_block is not None
    assert ctx.state.program_block[0] == "program_identity_unverified"


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
    await check_program_at_boot(cast(ExecutorContext, ctx))  # verified: ticks are slots-only now
    ctx.chain.rpc.calls.clear()
    await program_check_once(cast(ExecutorContext, ctx))
    assert ctx.chain.rpc.calls == ["getMultipleAccounts"], "one call for all three programs"
    assert ctx.state.program_divergence is None
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
