"""T4.8f guardian F1/F6: ``signing_block`` is not only a pure function — both entry paths call it
at the signature boundary. A program-identity block that appears **after** the admission (while
the loop awaited the RPC/database) must leave a refusal row, record the reason, and never reach
the submitter.

The entry path of ``entries.handle_candidate`` is driven through every await with stubs for the
admission machinery (this test is about the wiring, not the maths: ``test_admission*`` own that);
the launch path reuses the rig of ``test_launch_entries.py`` (model: its kill-switch twin).
"""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

import hunter_meme_executor.entries as entries
import hunter_meme_executor.launch_entries as le
from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.journal import SubmitState
from hunter_meme_executor.context import ExecutorState
from hunter_risk_meme import MemeKillSwitchInputs

from .test_launch_entries import Db, FakeContext, FakeKill, FakeSubmitter, _config, _fresh_candidate
from .test_launch_entries import _wire as _wire_launch

pytestmark = pytest.mark.unit

BLOCKS = [
    ("program_divergence", "pumpswap last_deploy_slot 9 != 8", "program_upgraded_before_signing"),
    (
        "program_unreadable",
        "3 consecutive program identity reads failed",
        "program_identity_unreadable_before_signing",
    ),
]


@dataclass
class _BlockAppearsOnRefresh:
    """A kill-switch double whose re-read (the one right before signing) is the moment the
    runtime tick finds the program block — the interleaving the guardian asked to prove."""

    state: ExecutorState
    field_name: str
    detail: str
    effective: Any = field(default_factory=lambda: SimpleNamespace(value="ACTIVE"))
    blocks_entries: bool = False
    refreshes: int = 0

    async def refresh(self) -> None:
        self.refreshes += 1
        if self.refreshes >= 2:  # the loop's own top-of-step read passed clean
            setattr(self.state, self.field_name, self.detail)

    def inputs(self) -> MemeKillSwitchInputs:
        return MemeKillSwitchInputs(system=KillSwitchState.ACTIVE)

    async def latch(self, _reason: str) -> bool:
        return True

    def describe(self) -> dict[str, str]:
        return {}


# -- launch path --------------------------------------------------------------------------


@pytest.mark.parametrize(("field_name", "detail", "reason"), BLOCKS)
async def test_a_program_block_after_the_launch_admission_refuses_the_row_and_signs_nothing(
    monkeypatch: pytest.MonkeyPatch, field_name: str, detail: str, reason: str
) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire_launch(monkeypatch, db, submitter)
    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        le.logger, "warning", lambda event, **kw: logged.append({"event": event, **kw})
    )
    ctx = FakeContext(config=_config())
    ctx.kill = _BlockAppearsOnRefresh(ctx.state, field_name, detail)  # type: ignore[assignment]
    await ctx.kill.refresh()  # the loop's own top-of-step read: still clean
    await le.handle_launch_candidate(ctx, db.candidates[0], now=datetime.now(UTC))  # type: ignore[arg-type]
    assert len(db.orders) == 1 and db.orders[0]["status"] == "admitted"
    assert db.refused_admitted == [reason]
    assert submitter.calls == [] and db.positions == []
    assert ctx.launch.refusals == {reason: 1} and ctx.state.refusals == {reason: 1}
    # F6: the late refusal keeps the block's detail, like the entry path
    late = [entry for entry in logged if entry.get("reason") == reason]
    assert late and late[0]["detail"] == detail


async def test_a_clean_desk_still_signs_on_the_launch_path(monkeypatch: pytest.MonkeyPatch) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire_launch(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config(), kill=FakeKill())
    await le.handle_launch_candidate(ctx, db.candidates[0], now=datetime.now(UTC))  # type: ignore[arg-type]
    assert db.refused_admitted == [] and len(submitter.calls) == 1


# -- entry path ---------------------------------------------------------------------------


@dataclass
class EntryRig:
    refused_admitted: list[str] = field(default_factory=lambda: list[str]())
    rejected_if_auto: list[str] = field(default_factory=lambda: list[str]())
    submitted: list[Any] = field(default_factory=lambda: list[Any]())
    inserted: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())


class _Session:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _entry_rig(monkeypatch: pytest.MonkeyPatch) -> EntryRig:
    rig = EntryRig()
    fee = SimpleNamespace(fee_sol=lambda _limit: Decimal("0.0001"), as_json=lambda _limit: {})

    async def lane_scope(*_a: Any, **_k: Any) -> None:
        return None

    async def priority_fee_for(*_a: Any, **_k: Any) -> Any:
        return fee

    def read_entry(*_a: Any, **_k: Any) -> Any:
        wallet = SimpleNamespace(lamports=300_000_000, observed_at=datetime.now(UTC))
        return SimpleNamespace(wallet=wallet, curve=object(), creates_ata=False)

    async def build_admission_context(*_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(positions=[], pending=[], recent_losses={}, context=None, extras={})

    async def ensure_anchor(*_a: Any, **_k: Any) -> object:
        return object()

    async def conviction_for(*_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(input=None, as_json=lambda: {})

    async def admission_holdings(*_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(unrecognized=(), as_json=lambda: {})

    def admit(*_a: Any, **_k: Any) -> Any:
        sizing = SimpleNamespace(sol_final=Decimal("0.01"))
        return SimpleNamespace(
            checks=(), approved=True, sizing=sizing, first_refusal=None, to_jsonable=lambda: {}
        )

    def build_entry_buy(*_a: Any, **_k: Any) -> Any:
        return SimpleNamespace(intent=SimpleNamespace(sol_limit=10_000_000), intent_json=lambda: {})

    async def claim_scope(*_a: Any, **_k: Any) -> None:
        return None

    async def insert_order(_session: Any, **row: Any) -> str:
        rig.inserted.append(row)
        return "order-1"

    async def refuse_admitted_order(_session: Any, _key: str, *, reason: str, now: Any) -> bool:
        rig.refused_admitted.append(reason)
        return True

    async def reject_if_auto(_ctx: Any, _session: Any, _cand: Any, reason: str, **_k: Any) -> None:
        rig.rejected_if_auto.append(reason)

    async def submit_entry_buy(*args: Any, **_k: Any) -> None:
        rig.submitted.append(args)

    for name, value in {
        "lane_scope": lane_scope,
        "scope_refusal": lambda *_a, **_k: None,
        "requested_sol_of": lambda *_a, **_k: Decimal("0.01"),
        "priority_fee_for": priority_fee_for,
        "read_entry": read_entry,
        "build_admission_context": build_admission_context,
        "ensure_anchor": ensure_anchor,
        "fee_bps": lambda *_a, **_k: SimpleNamespace(total=125),
        "buy_reserve_sol": lambda *_a, **_k: Decimal(0),
        "proposal_from": lambda *_a, **_k: object(),
        "wallet_from": lambda *_a, **_k: object(),
        "curve_from": lambda *_a, **_k: object(),
        "AdmissionInputs": lambda **_k: object(),
        "conviction_for": conviction_for,
        "admission_holdings": admission_holdings,
        "admit": admit,
        "build_entry_buy": build_entry_buy,
        "claim_scope": claim_scope,
        "insert_order": insert_order,
        "role_session": lambda *_a, **_k: _Session(),
        "refuse_admitted_order": refuse_admitted_order,
        "reject_if_auto": reject_if_auto,
        "submit_entry_buy": submit_entry_buy,
    }.items():
        monkeypatch.setattr(entries, name, value)
    return rig


def _entry_ctx(kill: Any, state: ExecutorState) -> Any:
    return SimpleNamespace(
        config=SimpleNamespace(
            approval_ttl_s=3600,
            limits=SimpleNamespace(min_trade_sol=Decimal("0.01")),
            send=SimpleNamespace(buy_slippage_bps=lambda: 100),
            compute_unit_limit=150_000,
        ),
        mode=SimpleNamespace(live=True),
        signer=SimpleNamespace(pubkey="Wallet111"),
        state=state,
        chain=SimpleNamespace(global_account=lambda: object(), blockhash=lambda: ("hash", 150)),
        treasury_inflow=SimpleNamespace(inflow_sol=Decimal(0), describe=lambda: {}),
        kill=kill,
        session_factory=None,
    )


def _candidate() -> Any:
    return SimpleNamespace(
        id="01994d00-6c1a-7000-8000-000000000301",
        mint="5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump",
        decided_at=datetime.now(UTC),
        decision=None,
    )


@pytest.mark.parametrize(("field_name", "detail", "reason"), BLOCKS)
async def test_a_program_block_after_the_entry_admission_refuses_the_row_and_signs_nothing(
    monkeypatch: pytest.MonkeyPatch, field_name: str, detail: str, reason: str
) -> None:
    rig = _entry_rig(monkeypatch)
    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        entries.logger, "warning", lambda event, **kw: logged.append({"event": event, **kw})
    )
    state = ExecutorState(program_identity_verified=True)
    ctx = _entry_ctx(_BlockAppearsOnRefresh(state, field_name, detail), state)
    await ctx.kill.refresh()  # the loop's own top-of-step read: clean
    await entries.handle_candidate(ctx, _candidate(), now=datetime.now(UTC))
    assert len(rig.inserted) == 1 and rig.inserted[0]["status"] == "admitted"
    assert rig.refused_admitted == [reason] and rig.rejected_if_auto == [reason]
    assert rig.submitted == [], "nothing reaches the submitter"
    assert state.refusals == {reason: 1}
    assert any(e.get("reason") == reason and e.get("detail") == detail for e in logged)


async def test_a_clean_desk_reaches_the_submitter_on_the_entry_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _entry_rig(monkeypatch)
    state = ExecutorState(program_identity_verified=True)
    ctx = _entry_ctx(
        SimpleNamespace(
            effective=SimpleNamespace(value="ACTIVE"),
            blocks_entries=False,
            refresh=_async_noop,
            inputs=lambda: None,
        ),
        state,
    )
    await entries.handle_candidate(ctx, _candidate(), now=datetime.now(UTC))
    assert rig.refused_admitted == [] and len(rig.submitted) == 1


async def _async_noop() -> None:
    return None


# -- the gate handed to the submitter: after the simulation, right before signing --------------


async def test_the_launch_entry_hands_the_submitter_a_gate_that_reads_the_state_as_it_is_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hunter_meme_executor.launch_submit as lsub

    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire_launch(monkeypatch, db, submitter)
    captured: list[dict[str, Any]] = []

    def make_submitter(**kwargs: Any) -> FakeSubmitter:
        captured.append(kwargs)
        return submitter

    monkeypatch.setattr(lsub, "MemeSubmitter", make_submitter)
    ctx = FakeContext(config=_config())
    await le.handle_launch_candidate(ctx, db.candidates[0], now=datetime.now(UTC))  # type: ignore[arg-type]
    (kwargs,) = captured
    gate = kwargs["pre_sign_gate"]
    assert gate() is None  # a clean desk
    ctx.state.program_divergence = "pumpswap last_deploy_slot 9 != 8"  # found while simulating
    assert gate() == "program_upgraded_before_signing"
    ctx.state.program_divergence = None
    ctx.kill.effective = KillSwitchState.TRADING_DISABLED
    assert gate() == "kill_switch_blocked_before_signing"


async def test_the_desk_entry_hands_the_submitter_the_same_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hunter_meme_executor.entry_submit as esub

    captured: list[dict[str, Any]] = []

    class CapturingSubmitter:
        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

        def submit(self, _approval: Any) -> Any:
            return SimpleNamespace(
                state=SubmitState.FAILED, reason="stopped", signature=None, fill=None
            )

    async def record_send_result(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(esub, "MemeSubmitter", CapturingSubmitter)
    monkeypatch.setattr(esub, "submit_policy", lambda *_a, **_k: None)
    monkeypatch.setattr(esub, "record_send_result", record_send_result)
    state = ExecutorState(program_identity_verified=True)
    ctx = _entry_ctx(
        SimpleNamespace(blocks_entries=False, effective=SimpleNamespace(value="ACTIVE")), state
    )
    ctx.config.limits.reservation_ttl_s = 5
    ctx.journal = object()
    ctx.chain.rpc = object()
    built: Any = SimpleNamespace(verify=lambda _m: None, message=b"", last_valid_block_height=150)
    await esub.submit_entry_buy(ctx, _candidate(), built, "key", "order-1", datetime.now(UTC))
    gate = captured[0]["pre_sign_gate"]
    assert gate() is None
    state.program_unreadable = "3 consecutive program identity reads failed"
    assert gate() == "program_identity_unreadable_before_signing"


@pytest.mark.parametrize(
    "module",
    ["exits.py", "pumpswap_exit.py", "exit_settle.py", "pumpswap_settle.py", "spot_exits.py"],
)
def test_no_exit_builds_its_submitter_with_the_gate(module: str) -> None:
    """Exits are never gated by the program identity (the §9.2 simulation is their guard)."""
    from pathlib import Path

    source = (Path(entries.__file__).parent / module).read_text(encoding="utf-8")
    assert "pre_sign_gate" not in source and "pre_sign_reason" not in source
