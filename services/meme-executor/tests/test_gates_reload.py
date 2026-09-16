"""T4.28d — ``meme_gates.json`` re-read at runtime, on mtime change only.

Measured on 2026-09-16 (11:3x BRT): the owner widened
``small_test_authorization.scope.max_total_sol`` from 0,25 to 0,72 on the VPS and
``hb:meme:executor`` kept publishing ``wallet_max_sol 0.25`` until
``docker restart hunter-meme-executor-1`` — a restart of the one process that
holds the signing key and the in-flight state. The kill-switch file is already
re-read every tick (``kill_switch.py``); the gates now follow the same pattern.

Four cases, one per branch, all pure (``tmp_path`` files, a fixed clock, a fake
kill switch — no Postgres, no Redis, no chain, no key):

a. the mtime did not move ⇒ nothing is parsed and nothing is swapped;
b. a valid edit ⇒ the effective policy is recomposed from the **owner's env
   policy** (never from the already-tightened one) and swapped atomically, the
   heartbeat shows the new scope, and no counter is touched;
c. an invalid edit ⇒ the kill switch is latched ``gates_invalid:<reason>``, the
   previous policy stays in memory for reporting, and the loop keeps ticking
   (a second tick over a still-broken file returns normally). T4.28f: a
   **parse** failure (half-written file, missing file) gets one tick of grace —
   it latches on the second failing tick, never on the first; a **semantic**
   refusal (expired, gate C off, the scope gone while armed) is a complete file
   saying no and latches immediately;
d. a scope that shrank **below what was already spent** ⇒ ``remaining_sol``
   clamps at 0 and ``exhausted`` is ``max_total_sol`` — the existing refusal
   (``small_test_scope_exhausted``) — instead of a negative number or a raise.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.gates import MemeExecutionMode, load_gates
from hunter_meme_executor.config import ExecutorConfig, effective_limits
from hunter_meme_executor.context import ExecutorContext, ExecutorState
from hunter_meme_executor.gates_reload import (
    GATES_LATCH_PREFIX,
    gates_reload_once,
    prime_gates,
)
from hunter_meme_executor.heartbeat import gates_fields
from hunter_meme_executor.kill_switch import KillSwitchReader
from hunter_meme_executor.scope import scope_use
from hunter_risk_meme import MemeLimits, limits_from_env

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 16, 14, 35, tzinfo=UTC)
TODAY = date(2026, 9, 16)
ENV_POLICY = {
    # The owner's five numbers (docs/ACTIVATION.md §9b item 1) — the base the
    # written scope is a ceiling on top of.
    "MEME_WALLET_MAX_SOL": "2.0",
    "MEME_MAX_SOL_PER_TRADE": "0.08",
    "MEME_DAILY_LOSS_CAP_SOL": "0.15",
    "MEME_MAX_OPEN_POSITIONS": "2",
    "MEME_COOLDOWN_S": "60",
}


def _doc(*, max_total_sol: str = "0.25", max_sol_per_trade: str = "0.05") -> dict[str, Any]:
    return {
        "schema": "hunter.meme_gates/v1",
        "gate_a_engineering": {"passed": False, "date": "2026-09-12", "evidence": "notes-T4.14"},
        "gate_b_evidence": {"passed": False, "date": "2026-09-12", "evidence": "EXP-M1 open"},
        "gate_c_owner": {"enabled": True, "date": "2026-09-12"},
        "small_test_authorization": {
            "authorized_by": "everton",
            "scope": {
                "max_sol_per_trade": max_sol_per_trade,
                "max_total_sol": max_total_sol,
                "max_trades": 5,
            },
            "expires_at": "2026-09-18",
            "decision_note": "obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md",
        },
        "signed_by": "everton",
        "signed_at": "2026-09-12",
        "valid_until": "2026-09-18",
    }


def _write(path: Path, payload: object, *, mtime_ns: int | None = None) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    if mtime_ns is not None:  # the owner's editor rewrote the bytes, not the clock
        os.utime(path, ns=(mtime_ns, mtime_ns))


@dataclass(slots=True)
class FakeKill:
    """Only what the reload touches: the memory latch and the durable one."""

    local_latch_reason: str | None = None
    latched: list[str] = field(default_factory=lambda: list[str]())
    raises: bool = False

    async def latch(self, reason: str, *, event: str = "") -> bool:
        if self.raises:
            raise RuntimeError("postgres is down")
        self.latched.append(f"{reason}|{event}")
        return True


def _config(gates_file: Path, *, auto_approve: bool = True) -> ExecutorConfig:
    env_limits = limits_from_env(ENV_POLICY)
    gates = load_gates(gates_file, today=TODAY)
    return ExecutorConfig(
        live=True,
        cluster="mainnet",
        rpc_url="https://rpc.example",
        limits=effective_limits(env_limits, gates.small_test),
        system_kill_switch=KillSwitchState.ACTIVE,
        kill_file=None,
        small_test_max_trades=None if gates.small_test is None else gates.small_test.max_trades,
        small_test_max_total_sol=(
            None if gates.small_test is None else gates.small_test.max_total_sol
        ),
        auto_approve=auto_approve,
        gates_file=str(gates_file),
        env_limits=env_limits,
    )


def _context(gates_file: Path, *, auto_approve: bool = True) -> tuple[ExecutorContext, FakeKill]:
    config = _config(gates_file, auto_approve=auto_approve)
    kill = FakeKill()
    ctx = ExecutorContext(
        config=config,
        mode=MemeExecutionMode(live=True, gates=load_gates(gates_file, today=TODAY)),
        signer=cast(Any, None),
        session_factory=cast(Any, None),
        chain=cast(Any, None),
        journal=cast(Any, None),
        kill=cast(KillSwitchReader, kill),
        heartbeat=cast(Any, None),
        loop=cast(Any, None),
        state=ExecutorState(),
    )
    prime_gates(ctx, now=NOW)
    return ctx, kill


def _scope_of(ctx: ExecutorContext) -> Any:
    gates = ctx.mode.gates
    assert gates is not None and gates.small_test is not None
    return gates.small_test


class TestBoot:
    def test_the_boot_policy_is_the_min_of_the_env_and_the_written_scope(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, _ = _context(path)
        limits = ctx.config.limits
        assert limits.wallet_max_sol == Decimal("0.25"), "the written scope is the tighter one"
        assert limits.max_sol_per_trade == Decimal("0.05")
        assert limits.profile.endswith("+small_test")
        assert ctx.state.gates_mtime is not None, "the boot primes the mtime it already read"
        assert ctx.state.gates_reloaded_at is None, "nothing was reloaded yet"


class TestUnchanged:
    async def test_the_mtime_did_not_move_so_nothing_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        mtime_ns = path.stat().st_mtime_ns
        # Bytes the parser would refuse, under the *same* mtime: if the reload
        # parsed on every tick this case would latch. It must only stat.
        _write(path, "{ not json at all", mtime_ns=mtime_ns)
        outcome = await gates_reload_once(ctx, now=NOW)
        assert outcome.reloaded is False and outcome.refusal is None
        assert ctx.config.limits.wallet_max_sol == Decimal("0.25")
        assert kill.latched == [] and kill.local_latch_reason is None
        assert ctx.state.gates_reloaded_at is None


class TestValidChange:
    async def test_a_widened_scope_is_swapped_in_without_a_restart(self, tmp_path: Path) -> None:
        """The 11:3x BRT case: 0,25 → 0,72 with the process untouched."""
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        ctx.state.entries_confirmed, ctx.state.auto_approved = 2, 2
        before = ctx.config.limits
        _write(path, _doc(max_total_sol="0.72"), mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)

        outcome = await gates_reload_once(ctx, now=NOW)

        assert outcome.reloaded is True and outcome.refusal is None
        assert _scope_of(ctx).max_total_sol == Decimal("0.72")
        assert ctx.config.small_test_max_total_sol == Decimal("0.72")
        # Recomposed from the owner's env policy (2.0), not from the 0,25 the
        # previous composition had already pinned — a min() over the tightened
        # value would keep 0,25 forever.
        assert before.wallet_max_sol == Decimal("0.25")
        assert ctx.config.limits.wallet_max_sol == Decimal("0.72")
        assert ctx.config.limits.max_sol_per_trade == Decimal("0.05"), "per-trade unchanged"
        assert kill.latched == [] and kill.local_latch_reason is None
        # Counters are not reset by a reload: the in-memory ones are untouched and
        # the scope's two (trades done, SOL used) are read from the ledger.
        assert (ctx.state.entries_confirmed, ctx.state.auto_approved) == (2, 2)

    async def test_the_heartbeat_publishes_the_new_scope_and_when_it_was_reloaded(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, _ = _context(path)
        assert gates_fields(ctx)["gates_reloaded_at"] == ""
        _write(path, _doc(max_total_sol="0.72"), mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)
        await gates_reload_once(ctx, now=NOW)

        fields = gates_fields(ctx)
        published = json.loads(fields["gates"])
        assert published["small_test"]["max_total_sol"] == "0.72"
        assert fields["gates_reloaded_at"] == NOW.isoformat()
        assert (
            fields["gates_mtime"]
            == datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
        )
        assert fields["gates_reload_error"] == ""
        # What the desk reads as "x/0,72 SOL" comes from the swapped scope.
        use = scope_use(
            _scope_of(ctx), trades_done=2, used_sol=Decimal("0.20"), requested_sol=Decimal("0.05")
        )
        assert use.remaining_sol == Decimal("0.52") and use.exhausted is None


class TestInvalidChange:
    @pytest.mark.parametrize(
        ("payload", "reason"),
        [
            (_doc() | {"valid_until": "2026-09-15"}, "gates_expired"),
            (
                _doc() | {"gate_c_owner": {"enabled": False, "date": "2026-09-12"}},
                "gate_c_owner_not_enabled",
            ),
        ],
    )
    async def test_a_semantically_invalid_edit_latches_on_the_first_tick(
        self, tmp_path: Path, payload: object, reason: str
    ) -> None:
        """A file that parses and says no is complete: there is nothing to wait
        for, so it latches at once (no grace — T4.28f)."""
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        _write(path, payload, mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)

        outcome = await gates_reload_once(ctx, now=NOW)

        assert outcome.reloaded is False and outcome.deferred is None
        assert outcome.refusal == f"{GATES_LATCH_PREFIX}{reason}"
        assert kill.local_latch_reason == outcome.refusal
        assert kill.latched and kill.latched[0].startswith(f"{GATES_LATCH_PREFIX}{reason}|")
        # The previous policy stays in memory — for the heartbeat to report, not
        # to trade on: the latch blocks entries.
        assert ctx.config.limits.wallet_max_sol == Decimal("0.25")
        assert _scope_of(ctx).max_total_sol == Decimal("0.25")
        assert gates_fields(ctx)["gates_reload_error"] == reason

    async def test_a_file_that_stopped_parsing_latches_on_the_second_tick(
        self, tmp_path: Path
    ) -> None:
        """T4.28f — ``nano`` rewrites the file in place: a tick can stat+read a
        half-written one. The first parse failure is **deferred** (named in the
        heartbeat), the second latches; the policy in force never changes."""
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        _write(path, "{ truncated", mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)

        first = await gates_reload_once(ctx, now=NOW)

        assert first.deferred == "gates_file_invalid"
        assert first.refusal is None and first.reloaded is False
        assert kill.latched == [] and kill.local_latch_reason is None, "still trading"
        assert ctx.state.gates_invalid is None
        assert gates_fields(ctx)["gates_reload_error"] == "deferred:gates_file_invalid"

        # Same mtime, still broken: the grace is over even though nothing moved.
        second = await gates_reload_once(ctx, now=NOW)

        assert second.refusal == f"{GATES_LATCH_PREFIX}gates_file_invalid"
        assert second.deferred is None
        assert kill.local_latch_reason == second.refusal
        assert kill.latched and kill.latched[0].startswith(
            f"{GATES_LATCH_PREFIX}gates_file_invalid|"
        )
        assert ctx.config.limits.wallet_max_sol == Decimal("0.25")
        assert gates_fields(ctx)["gates_reload_error"] == "gates_file_invalid"

    async def test_a_second_broken_write_latches_too(self, tmp_path: Path) -> None:
        """A new mtime that also fails is the second tick: two different broken
        bytes in a row are not a race, they are a broken file."""
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        _write(path, "{ truncated", mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)
        assert (await gates_reload_once(ctx, now=NOW)).deferred == "gates_file_invalid"
        _write(path, "{ also broken", mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)

        outcome = await gates_reload_once(ctx, now=NOW)

        assert outcome.refusal == f"{GATES_LATCH_PREFIX}gates_file_invalid"
        assert kill.local_latch_reason == outcome.refusal

    async def test_a_half_written_file_that_becomes_valid_is_just_a_reload(
        self, tmp_path: Path
    ) -> None:
        """The case the grace exists for: the tick read the middle of the owner's
        ``nano`` write. The next tick reads the whole file — no latch, the new
        policy applies, and nothing is left in the heartbeat."""
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        half = json.dumps(_doc(max_total_sol="0.72"))[:120]
        _write(path, half, mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)
        assert (await gates_reload_once(ctx, now=NOW)).deferred == "gates_file_invalid"

        _write(path, _doc(max_total_sol="0.72"), mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)
        outcome = await gates_reload_once(ctx, now=NOW)

        assert outcome.reloaded is True
        assert outcome.refusal is None and outcome.deferred is None
        assert kill.latched == [] and kill.local_latch_reason is None
        assert ctx.config.limits.wallet_max_sol == Decimal("0.72")
        assert _scope_of(ctx).max_total_sol == Decimal("0.72")
        fields = gates_fields(ctx)
        assert fields["gates_reload_error"] == "", "no error left behind"
        assert fields["gates_reloaded_at"] == NOW.isoformat()

    async def test_the_file_being_deleted_is_an_invalid_edit_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        """A missing file is a parse failure too (``mv`` in flight): deferred once,
        latched on the second tick, and then said only once."""
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        path.unlink()
        assert (await gates_reload_once(ctx, now=NOW)).deferred == "gates_file_missing"
        assert kill.local_latch_reason is None

        outcome = await gates_reload_once(ctx, now=NOW)
        assert outcome.refusal == f"{GATES_LATCH_PREFIX}gates_file_missing"
        assert kill.local_latch_reason == outcome.refusal
        assert ctx.config.limits.wallet_max_sol == Decimal("0.25")
        # Still gone on the next tick: already latched, already logged.
        assert (await gates_reload_once(ctx, now=NOW)).refusal == outcome.refusal
        assert len(kill.latched) == 1, "one line, not one every 10 s"

    async def test_a_file_that_came_back_before_the_second_tick_never_latches(
        self, tmp_path: Path
    ) -> None:
        """``mv new old`` seen mid-flight: gone on one tick, whole on the next."""
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        path.unlink()
        assert (await gates_reload_once(ctx, now=NOW)).deferred == "gates_file_missing"
        _write(path, _doc(max_total_sol="0.72"))

        outcome = await gates_reload_once(ctx, now=NOW)

        assert outcome.reloaded is True and kill.latched == []
        assert ctx.config.limits.wallet_max_sol == Decimal("0.72")
        assert gates_fields(ctx)["gates_reload_error"] == ""

    async def test_dropping_the_written_scope_while_the_robot_is_armed_is_refused(
        self, tmp_path: Path
    ) -> None:
        """``MEME_LIVE_AUTO_APPROVE`` on without a small test is the boot's
        ``auto_approve_needs_small_test``; it cannot become true at runtime."""
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path, auto_approve=True)
        widened = _doc()
        del widened["small_test_authorization"]
        widened["gate_a_engineering"] = {
            "passed": True,
            "date": "2026-09-12",
            "evidence": "notes-T4.14",
        }
        widened["gate_b_evidence"] = {"passed": True, "date": "2026-09-12", "evidence": "EXP-M1"}
        _write(path, widened, mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)

        outcome = await gates_reload_once(ctx, now=NOW)

        assert outcome.deferred is None, "a complete file saying no latches at once"
        assert outcome.refusal == f"{GATES_LATCH_PREFIX}auto_approve_needs_small_test"
        assert kill.local_latch_reason == outcome.refusal
        assert _scope_of(ctx).max_total_sol == Decimal("0.25"), "the old scope is kept"

    async def test_a_latch_postgres_refuses_still_stops_this_process(self, tmp_path: Path) -> None:
        path = tmp_path / "meme_gates.json"
        _write(path, _doc())
        ctx, kill = _context(path)
        kill.raises = True
        _write(path, "{ truncated", mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)

        assert (await gates_reload_once(ctx, now=NOW)).deferred == "gates_file_invalid"
        outcome = await gates_reload_once(ctx, now=NOW)

        assert outcome.refusal == f"{GATES_LATCH_PREFIX}gates_file_invalid"
        assert kill.local_latch_reason == outcome.refusal, "the memory latch does not need the DB"
        assert ctx.state.gates_invalid == "gates_file_invalid"


class TestShrunkScope:
    async def test_a_scope_shrunk_below_what_was_spent_exhausts_instead_of_raising(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "meme_gates.json"
        _write(path, _doc(max_total_sol="0.25"))
        ctx, kill = _context(path)
        _write(path, _doc(max_total_sol="0.05"), mtime_ns=path.stat().st_mtime_ns + 1_000_000_000)

        outcome = await gates_reload_once(ctx, now=NOW)

        assert outcome.reloaded is True and kill.local_latch_reason is None
        assert ctx.config.limits.wallet_max_sol == Decimal("0.05")
        # 0,18 SOL already spent against a scope that is now 0,05.
        use = scope_use(
            _scope_of(ctx), trades_done=2, used_sol=Decimal("0.18"), requested_sol=Decimal("0.02")
        )
        assert use.remaining_sol == Decimal(0), "clamped at zero, never negative"
        assert use.exhausted == "max_total_sol"
        assert use.requested_cap_sol == Decimal(0)
        # The refusal the admission already uses (entries.handle_candidate).
        assert json.loads(json.dumps(use.as_json()))["exhausted"] == "max_total_sol"


class TestKillSwitchMemoryLatch:
    def test_the_memory_latch_blocks_entries_and_is_reported(self) -> None:
        reader = KillSwitchReader(
            redis=cast(Any, None),
            session_factory=cast(Any, None),
            system=KillSwitchState.ACTIVE,
            kill_file=None,
        )
        assert reader.blocks_entries is False
        reader.local_latch_reason = "gates_invalid:gates_expired"
        assert reader.effective is KillSwitchState.TRADING_DISABLED
        assert reader.blocks_entries is True
        described = reader.describe()
        assert described["kill_switch_latched"] == "true"
        assert described["kill_switch_latch_reason"] == "gates_invalid:gates_expired"

    def test_a_refresh_that_reads_an_unlatched_row_does_not_clear_it(self) -> None:
        """``refresh`` rebuilds ``latched`` from the row; the memory latch is this
        process's own decision and a row it could not write must not erase it."""
        reader = KillSwitchReader(
            redis=cast(Any, None),
            session_factory=cast(Any, None),
            system=KillSwitchState.ACTIVE,
            kill_file=None,
            local_latch_reason="gates_invalid:gates_file_invalid",
        )
        reader.latched = False  # what a successful refresh over an unlatched row leaves
        assert reader.blocks_entries is True


def test_effective_limits_is_the_only_place_the_ceiling_arithmetic_lives(
    tmp_path: Path,
) -> None:
    """Boot and reload compose the same way — one function, no duplicated min()."""
    path = tmp_path / "meme_gates.json"
    _write(path, _doc(max_total_sol="0.72", max_sol_per_trade="0.05"))
    base: MemeLimits = limits_from_env(ENV_POLICY)
    gates = load_gates(path, today=TODAY)
    composed = effective_limits(base, gates.small_test)
    assert composed.wallet_max_sol == Decimal("0.72")
    assert composed.max_sol_per_trade == Decimal("0.05")
    assert composed.max_exposure_per_mint_sol == Decimal("0.05")
    assert effective_limits(base, None) == base, "no written scope, no ceiling"
