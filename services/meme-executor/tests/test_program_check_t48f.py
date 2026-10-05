"""T4.8f: the guard's scope — PumpSwap and the fee program next to the pump program — and what
an unreadable or unverified identity means (Astra, 05/10: "a boot approved, an upgrade later and
the identity read unavailable: the detector closes nothing out of ignorance").

Rule (guardian F3): the executor never refuses to **boot** on the program identity — a position
open at that moment needs its exits and its reconciliation. It boots *exits-only*: entries are
refused by name while the identity is **diverged** (sticky, ``program_upgraded``), **unreadable
for 3 consecutive ticks** (``program_identity_unreadable``, cleared by the next good read) or
**not yet verified** (``program_identity_unverified``, born so; cleared only by a COMPLETE
compatible read). Exits are never gated by any of them — they keep the §9.2 simulation.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

import hunter_meme_executor.entries as entries
from hunter_exchanges.pumpfun.program_watch import WATCHED_PROGRAMS
from hunter_meme_executor.context import ExecutorContext, ExecutorState
from hunter_meme_executor.program_check import (
    PROGRAM_READ_FAILURES_MAX,
    check_program_at_boot,
    program_check_once,
)

from .test_program_check import FakeConfig, FakeContext, _ctx

pytestmark = pytest.mark.unit

PUMPSWAP, FEES = WATCHED_PROGRAMS


def _as(ctx: FakeContext) -> ExecutorContext:
    return cast(ExecutorContext, ctx)


async def _booted(**kwargs: Any) -> FakeContext:
    """A desk whose boot read was complete and compatible: verified, ticks are slots-only."""
    ctx = _ctx(live=True, **kwargs)
    await check_program_at_boot(_as(ctx))
    assert ctx.state.program_identity_verified is True
    ctx.chain.rpc.calls.clear()
    return ctx


# -- scope: the boot never dies, entries are refused by name ----------------------------------


async def test_boot_live_with_an_upgraded_pumpswap_boots_exits_only() -> None:
    ctx = _ctx(live=True)
    ctx.chain.rpc.pumpswap_slot = PUMPSWAP.last_deploy_slot + 1
    await check_program_at_boot(_as(ctx))  # no raise
    detail = ctx.state.program_divergence or ""
    assert "pumpswap" in detail and str(PUMPSWAP.last_deploy_slot + 1) in detail
    assert ctx.state.program_block == ("program_upgraded", detail)
    assert ctx.state.program_identity_verified is False


async def test_boot_live_with_an_upgraded_fee_program_boots_exits_only() -> None:
    ctx = _ctx(live=True)
    ctx.chain.rpc.fees_slot = FEES.last_deploy_slot + 9
    await check_program_at_boot(_as(ctx))
    assert "pump_fees" in (ctx.state.program_divergence or "")
    assert ctx.state.program_block is not None and ctx.state.program_block[0] == "program_upgraded"


async def test_boot_live_with_the_watched_programs_unreadable_boots_exits_only_unverified() -> None:
    """The pump identity read fine; the other two did not: the read is not complete, so the
    identity is NOT verified (never "assume unchanged") — and the process still lives."""
    ctx = _ctx(live=True)
    ctx.chain.rpc.multiple_down = True
    await check_program_at_boot(_as(ctx))
    assert ctx.state.program_identity_verified is False
    assert ctx.state.program_block is not None
    assert ctx.state.program_block[0] == "program_identity_unverified"


async def test_boot_inert_keeps_running_and_says_which_program_moved() -> None:
    ctx = _ctx(live=False)
    ctx.chain.rpc.pumpswap_slot = 1
    await check_program_at_boot(_as(ctx))
    assert ctx.state.program_divergence is not None and "pumpswap" in ctx.state.program_divergence


async def test_the_runtime_check_names_every_program_that_moved() -> None:
    ctx = await _booted()
    await program_check_once(_as(ctx))
    assert ctx.state.program_divergence is None and ctx.state.program_block is None
    ctx.chain.rpc.pumpswap_slot += 1
    ctx.chain.rpc.fees_slot += 1
    await program_check_once(_as(ctx))
    detail = ctx.state.program_divergence or ""
    assert "pumpswap" in detail and "pump_fees" in detail and "pump" in detail
    assert ctx.state.program_block == ("program_upgraded", detail)


async def test_a_pump_only_upgrade_is_still_named_as_before() -> None:
    ctx = await _booted()
    ctx.chain.rpc.deploy_slot += 3
    await program_check_once(_as(ctx))
    assert ctx.state.program_divergence is not None
    assert "pumpswap" not in ctx.state.program_divergence


# -- an unreadable identity at runtime --------------------------------------------------------


async def test_repeated_read_failures_refuse_entries_and_a_good_read_clears_it() -> None:
    ctx = await _booted()
    ctx.chain.rpc.down = True
    for _ in range(PROGRAM_READ_FAILURES_MAX - 1):
        await program_check_once(_as(ctx))
        assert ctx.state.program_block is None, "one bad tick is not a reason to stop buying"
    await program_check_once(_as(ctx))
    block = ctx.state.program_block
    assert block is not None and block[0] == "program_identity_unreadable"
    assert str(PROGRAM_READ_FAILURES_MAX) in block[1]
    assert ctx.state.program_divergence is None, "unreadable is not an upgrade"
    ctx.chain.rpc.down = False
    await program_check_once(_as(ctx))
    assert ctx.state.program_block is None and ctx.state.program_read_failures == 0


async def test_a_divergence_outranks_an_unreadable_identity_and_is_never_cleared_by_a_good_read() -> (
    None
):
    ctx = await _booted()
    ctx.chain.rpc.pumpswap_slot += 1
    await program_check_once(_as(ctx))
    ctx.chain.rpc.down = True
    for _ in range(PROGRAM_READ_FAILURES_MAX):
        await program_check_once(_as(ctx))
    assert ctx.state.program_block is not None and ctx.state.program_block[0] == "program_upgraded"
    ctx.chain.rpc.down = False
    await program_check_once(_as(ctx))
    assert ctx.state.program_block is not None and ctx.state.program_block[0] == "program_upgraded"


async def test_the_heartbeat_fields_exist_on_the_state() -> None:
    state = ExecutorState()
    assert state.program_read_failures == 0 and state.program_unreadable is None


async def test_entries_are_refused_by_the_name_of_the_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``entries.handle_candidate`` reads ``program_block`` — the name follows the cause."""
    seen: list[tuple[str, dict[str, object]]] = []

    async def refuse(_ctx: Any, _candidate: Any, reason: str, admission: dict[str, object]) -> None:
        seen.append((reason, admission))

    monkeypatch.setattr(entries, "_refuse", refuse)
    for cause, expected in (
        ("unreadable", "program_identity_unreadable"),
        ("diverged", "program_upgraded"),
        ("unverified", "program_identity_unverified"),
    ):
        state = ExecutorState()
        if cause == "unreadable":
            state.program_identity_verified = True
            state.program_unreadable = "3 consecutive reads failed"
        elif cause == "diverged":
            state.program_divergence = "pumpswap last_deploy_slot 1 != 2"
        ctx = FakeContext(FakeConfig(live=True), cast(Any, None), state)
        ctx.config.approval_ttl_s = 3600  # type: ignore[attr-defined]
        ctx.signer = object()  # type: ignore[attr-defined]
        ctx.mode = type("Mode", (), {"live": True})()  # type: ignore[attr-defined]
        candidate = type("Candidate", (), {"decided_at": datetime.now(UTC), "id": "p"})()
        await entries.handle_candidate(_as(ctx), cast(Any, candidate), now=datetime.now(UTC))
        assert seen[-1][0] == expected, seen
