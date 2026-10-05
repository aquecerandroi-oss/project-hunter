"""T4.8f guardian F3 — the executor **boots exits-only** when the program identity is divergent,
unreadable or unverified, instead of dying.

Before: ``check_program_at_boot`` raised ``MemeLiveTradingRefused`` in live mode and the process
ended before ``main`` created a single loop — with a position open, its exits and its
reconciliation did not exist either ("saídas nunca travadas" held only after a *healthy* boot).
Now the boot records the state (``program_divergence`` sticky, ``program_identity_verified``
born ``False``), logs ``meme_executor_boot_exits_only`` at ERROR and goes on: every loop that
sells or reconciles (meme exits, launch exits, spot/1 exits, reconcile, kill switch, heartbeat)
runs; entries are refused by name. Only a COMPLETE compatible read (identity + deploy slots) in
``program_check_once`` verifies the identity; a slots-only read never clears an unvalidated IDL.
"""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import hunter_meme_executor.main as main
import hunter_meme_executor.program_check as program_check
from hunter_exchanges.pumpfun.program_identity import EXPECTED_PUMP_PROGRAM
from hunter_meme_executor.context import (
    ExecutorContext,
    ExecutorState,
    heartbeat_program_fields,
    program_mode_text,
)
from hunter_meme_executor.program_check import check_program_at_boot, program_check_once

from .test_program_check import FakeContext, _ctx

pytestmark = pytest.mark.unit

PACKAGE = Path(__file__).resolve().parents[1] / "hunter_meme_executor"
EXPECTED_SLOT = EXPECTED_PUMP_PROGRAM.last_deploy_slot


def _as(ctx: FakeContext) -> ExecutorContext:
    return cast(ExecutorContext, ctx)


def test_the_identity_is_born_unverified_and_that_is_a_block() -> None:
    state = ExecutorState()
    assert state.program_identity_verified is False
    assert (
        state.program_block is not None and state.program_block[0] == "program_identity_unverified"
    )


async def test_only_a_complete_compatible_read_verifies_and_a_slots_only_read_never_does() -> None:
    ctx = _ctx(live=True)
    ctx.chain.rpc.down = True
    await check_program_at_boot(_as(ctx))  # unreadable boot
    assert ctx.state.program_identity_verified is False
    # the node answers the slots again but NOT the IDL/identity reads: not enough
    ctx.chain.rpc.down = False
    ctx.chain.rpc.identity_down = True
    for _ in range(3):
        await program_check_once(_as(ctx))
    assert ctx.state.program_identity_verified is False
    assert ctx.state.program_block is not None  # the complete read failed 3x: named unreadable
    assert ctx.state.program_block[0] == "program_identity_unreadable"
    # the complete read (identity + slots) works: verified, entries may flow again
    ctx.chain.rpc.identity_down = False
    ctx.chain.rpc.calls.clear()
    await program_check_once(_as(ctx))
    assert ctx.chain.rpc.calls == ["getAccountInfo", "getAccountInfo", "getMultipleAccounts"]
    assert ctx.state.program_identity_verified is True and ctx.state.program_block is None
    # and once verified the ticks go back to the single cheap call
    ctx.chain.rpc.calls.clear()
    await program_check_once(_as(ctx))
    assert ctx.chain.rpc.calls == ["getMultipleAccounts"]


async def test_a_divergence_found_at_boot_is_sticky_even_when_the_slots_come_back() -> None:
    ctx = _ctx(live=True)
    ctx.chain.rpc.pumpswap_slot += 1
    await check_program_at_boot(_as(ctx))
    assert ctx.state.program_block is not None and ctx.state.program_block[0] == "program_upgraded"
    ctx.chain.rpc.pumpswap_slot -= 1  # the chain matches again (a rollback?) — still not trusted
    for _ in range(3):
        await program_check_once(_as(ctx))
    assert ctx.state.program_block is not None and ctx.state.program_block[0] == "program_upgraded"
    assert ctx.state.program_identity_verified is False


async def test_the_boot_logs_the_exits_only_decision_at_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        program_check.logger, "error", lambda event, **kw: logged.append((event, kw))
    )
    divergent = _ctx(live=True)
    divergent.chain.rpc.deploy_slot += 1
    await check_program_at_boot(_as(divergent))
    unreadable = _ctx(live=True, down=True)
    await check_program_at_boot(_as(unreadable))
    events = [(e, kw.get("reason")) for e, kw in logged if e == "meme_executor_boot_exits_only"]
    assert events == [
        ("meme_executor_boot_exits_only", "program_upgraded"),
        ("meme_executor_boot_exits_only", "program_identity_unreadable"),
    ]


def test_the_status_and_the_heartbeat_say_exits_only() -> None:
    state = ExecutorState()
    assert "exits-only" in program_mode_text(state)
    fields = heartbeat_program_fields(state)
    assert fields["program_mode"] == "exits_only"
    assert fields["program_block"] == "program_identity_unverified"
    state.program_identity_verified = True
    assert program_mode_text(state) == "normal"
    assert heartbeat_program_fields(state) == {
        "program_mode": "normal",
        "program_block": "",
        "program_block_detail": "",
        "program_divergence": "",
    }
    state.program_divergence = "pumpswap last_deploy_slot 9 != 8"
    assert heartbeat_program_fields(state)["program_block"] == "program_upgraded"
    assert heartbeat_program_fields(state)["program_divergence"].startswith("pumpswap")


# -- the process does not die and the exit loops run ---------------------------------------------


def _runtime_stubs(monkeypatch: pytest.MonkeyPatch, ctx: FakeContext) -> list[str]:
    """Everything ``run_meme_executor`` touches that is not the boot decision, stubbed; ``forever``
    records the loops the ``TaskGroup`` would have run and returns at once."""
    loops: list[str] = []
    config = SimpleNamespace(
        live=True,
        cluster="mainnet",
        limits=SimpleNamespace(profile="paper_v0"),
        approval_ttl_s=60,
        auto_close_on_emergency=False,
        small_test_max_trades=None,
        small_test_max_total_sol=None,
        auto_approve=False,
        auto_approve_max_per_hour=0,
        event_exits=SimpleNamespace(enabled=False),
        launch=SimpleNamespace(mode="on", enabled=True),
        spot=SimpleNamespace(enabled=True, mark_s=5, as_json=lambda _limits: {"mode": "on"}),
        loop_s=1.0,
        mark_s=5.0,
        kill_switch_poll_s=10.0,
        reconcile_s=30.0,
    )
    ctx.config = config  # type: ignore[assignment]
    ctx.wake_event = asyncio.Event()  # type: ignore[attr-defined]
    ctx.risk_client = None  # type: ignore[attr-defined]
    signer = SimpleNamespace(pubkey="Wallet111")
    ctx.signer = signer  # type: ignore[attr-defined]
    ctx.kill = SimpleNamespace(legible=True, effective=SimpleNamespace(value="ACTIVE"))  # type: ignore[attr-defined]

    async def refresh() -> None:
        return None

    ctx.kill.refresh = refresh  # type: ignore[attr-defined]

    async def fake_forever(name: str, _interval: float, _step: Any, _ctx: Any, **_k: Any) -> None:
        loops.append(name)

    class FakeListener:
        def __init__(self, *_a: Any) -> None:
            pass

        async def run(self) -> None:
            return None

    monkeypatch.setattr(main, "process_environment", lambda: {})
    monkeypatch.setattr(
        main, "boot", lambda *_a, **_k: (config, SimpleNamespace(live=True), signer)
    )
    monkeypatch.setattr(main, "build_context", lambda *_a, **_k: ctx)
    monkeypatch.setattr(main, "prime_gates", lambda _ctx: None)
    monkeypatch.setattr(main, "event_exits_client", lambda _cfg: None)
    monkeypatch.setattr(main, "ProposalWakeListener", FakeListener)
    monkeypatch.setattr(main, "forever", fake_forever)
    monkeypatch.setattr(main, "spot_exits_active", lambda _spot: True)
    return loops


EXIT_SIDE_LOOPS = {"exits", "reconcile", "launch_exits", "spot_exits", "kill_switch", "heartbeat"}


@pytest.mark.parametrize("cause", ["divergent", "unreadable"])
async def test_the_process_boots_and_every_exit_side_loop_runs(
    monkeypatch: pytest.MonkeyPatch, cause: str
) -> None:
    ctx = _ctx(live=True, down=cause == "unreadable")
    if cause == "divergent":
        ctx.chain.rpc.deploy_slot += 1
    loops = _runtime_stubs(monkeypatch, ctx)
    runtime = SimpleNamespace(
        settings=SimpleNamespace(system_kill_switch=None),
        readiness_checks=[],
        status_details={},
        redis=None,
    )
    await main.run_meme_executor(cast(Any, runtime))  # must NOT raise MemeLiveTradingRefused
    assert EXIT_SIDE_LOOPS <= set(loops), sorted(loops)
    assert "spot_entries" in loops and "entries" in loops  # spot/1 has its own gates
    block = ctx.state.program_block
    assert block is not None
    assert block[0] == (
        "program_upgraded" if cause == "divergent" else "program_identity_unverified"
    )
    assert "exits-only" in runtime.status_details["program_identity"]()


# -- the exit side never looks at the program state ------------------------------------------


EXIT_SIDE_MODULES = [
    "exits.py",
    "exit_settle.py",
    "exit_common.py",
    "pumpswap_exit.py",
    "pumpswap_settle.py",
    "launch_exits.py",
    "spot_exits.py",
    "spot_reconcile.py",
    "event_exits.py",
    "event_exits_eval.py",
    "event_exits_watch.py",
    "event_exits_runtime.py",
]
FORBIDDEN = re.compile(
    r"program_block|program_divergence|program_unreadable|program_identity_verified"
)


@pytest.mark.parametrize("module", EXIT_SIDE_MODULES)
def test_no_exit_side_module_reads_the_program_state(module: str) -> None:
    """Exits are never gated by the program identity: they keep the §9.2 simulation, the only
    thing that knows whether the cluster still accepts our sell."""
    assert not FORBIDDEN.search((PACKAGE / module).read_text(encoding="utf-8")), module


def test_main_reconcile_does_not_read_it_either() -> None:
    source = (PACKAGE / "main.py").read_text(encoding="utf-8")
    reconcile = source[
        source.index("async def reconcile_once") : source.index("async def kill_switch_once")
    ]
    assert not FORBIDDEN.search(reconcile)


# -- Astra (T4.8f round 3): a divergence seen in a PARTIAL read is not forgotten ----------------


async def test_a_boot_divergence_is_kept_even_when_the_watched_read_then_fails() -> None:
    """The pump identity answered and diverged; the other programs' read failed. The divergence
    already observed must be recorded at once — a later clean read must not wash it away."""
    ctx = _ctx(live=True, deploy_slot=EXPECTED_SLOT + 1)
    ctx.chain.rpc.multiple_down = True
    await check_program_at_boot(_as(ctx))
    assert ctx.state.program_divergence is not None, "observed, so recorded"
    assert ctx.state.program_identity_verified is False
    ctx.chain.rpc.multiple_down = False
    ctx.chain.rpc.deploy_slot = EXPECTED_SLOT  # the chain "matches" again
    for _ in range(3):
        await program_check_once(_as(ctx))
    assert ctx.state.program_block is not None and ctx.state.program_block[0] == "program_upgraded"
    assert ctx.state.program_identity_verified is False


async def test_a_runtime_full_read_keeps_a_divergence_seen_before_its_slots_read_fails() -> None:
    ctx = _ctx(live=True, down=True)
    await check_program_at_boot(_as(ctx))  # unreadable boot: unverified, no divergence yet
    ctx.chain.rpc.down = False
    ctx.chain.rpc.deploy_slot = EXPECTED_SLOT + 5  # the identity read will see this
    ctx.chain.rpc.multiple_down = True  # ...and the slots read fails right after
    await program_check_once(_as(ctx))
    assert ctx.state.program_divergence is not None
    ctx.chain.rpc.multiple_down = False
    ctx.chain.rpc.deploy_slot = EXPECTED_SLOT
    await program_check_once(_as(ctx))
    assert ctx.state.program_block is not None and ctx.state.program_block[0] == "program_upgraded"


def test_the_exits_only_text_says_which_entries_it_blocks_and_that_spot_is_independent() -> None:
    text = program_mode_text(ExecutorState())
    assert "pump/launch entries blocked" in text and "spot/1 independent" in text
