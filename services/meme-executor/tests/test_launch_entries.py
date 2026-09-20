"""T4.67b, pure (no Docker): the launch loop against fakes — ``off``/``paper``
never query a launch proposal, ``on`` without the live flag is inert, a stale
proposal is refused before any chain read, a blocking kill switch refuses by
name, the happy path writes **one** admitted order with ``admission.profile =
launch`` (every skipped check recorded) in the same transaction as the claim,
signs with the cached blockhash, opens the position with ``params.lane =
launch`` and the launch exits, and records ``proposal_to_submit_ms``; a claim
that lost writes nothing; a switch that moves between the admission and the
signature refuses the admitted row."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import hunter_meme_executor.launch_entries as le
from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import SubmitResult
from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_meme_executor.build import decode_fills
from hunter_meme_executor.chain import CurveRead, WalletRead
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.context import ExecutorState
from hunter_meme_executor.event_exits_stats import EventExitsStats
from hunter_meme_executor.kill_switch import DayAnchor
from hunter_meme_executor.launch_config import LaunchConfig
from hunter_meme_executor.launch_stats import LaunchStats
from hunter_meme_executor.priority_fee import PriorityFeeChoice
from hunter_meme_executor.send_tuning import SendTuning
from hunter_risk_meme import MemeKillSwitchInputs, limits_from_env

from .test_launch_admission import CREATOR, LIMITS, MINT, POLICY, WALLET, _candidate

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
NOW = datetime(2026, 9, 19, 15, 0, 1, tzinfo=UTC)
DAY_START = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)


@dataclass
class FakeRpc:
    allow_send: bool = True


@dataclass
class FakeChain:
    real_sol: int = 500_000_000
    reads: list[tuple[str, str | None]] = field(
        default_factory=lambda: list[tuple[str, str | None]]()
    )
    blockhash_fetches: int = 0
    rpc: FakeRpc = field(default_factory=FakeRpc)

    def __post_init__(self) -> None:
        raw = json.loads((FIXTURES / "rpc_global_account_raw.json").read_text())["result"]["value"]
        self._global = decode_global_account(raw["data"][0], owner=raw["owner"])

    def global_account(self) -> Any:
        return self._global

    def curve(self, mint: str, *, commitment: str | None = None) -> CurveRead:
        self.reads.append(("curve", commitment))
        sold = 13_000_000_000_000 * self.real_sol // 500_000_000
        account = BondingCurveAccount(
            virtual_token_reserves=self._global.initial_virtual_token_reserves - sold,
            virtual_sol_reserves=self._global.initial_virtual_sol_reserves + self.real_sol,
            real_token_reserves=self._global.initial_real_token_reserves - sold,
            real_sol_reserves=self.real_sol,
            token_total_supply=self._global.token_total_supply,
            complete=False,
            creator=CREATOR,
            is_mayhem_mode=False,
            is_cashback_coin=False,
            quote_mint="11111111111111111111111111111111",
        )
        return CurveRead(
            mint, account, TOKEN_PROGRAM_ID, 1, datetime.now(UTC), commitment or "confirmed"
        )

    def wallet(self, pubkey: str) -> WalletRead:
        self.reads.append(("wallet", None))
        return WalletRead(pubkey, 300_000_000, 1, datetime.now(UTC))

    def blockhash(self) -> tuple[str, int]:
        self.blockhash_fetches += 1
        return "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ", 150


@dataclass
class FakeKill:
    effective: KillSwitchState = KillSwitchState.ACTIVE
    flip_on_refresh: bool = False
    refreshes: int = 0
    latched: list[str] = field(default_factory=lambda: list[str]())
    anchor: DayAnchor | None = None

    @property
    def blocks_entries(self) -> bool:
        return self.effective in (KillSwitchState.TRADING_DISABLED, KillSwitchState.EMERGENCY)

    async def refresh(self) -> None:
        self.refreshes += 1
        if self.flip_on_refresh:
            self.effective = KillSwitchState.TRADING_DISABLED

    def inputs(self) -> MemeKillSwitchInputs:
        return MemeKillSwitchInputs(system=self.effective)

    def describe(self) -> dict[str, str]:
        return {"kill_switch": self.effective.value}

    async def latch(self, reason: str) -> bool:
        self.latched.append(reason)
        return True


@dataclass
class FakeInflow:
    inflow_sol: Decimal | None = Decimal(0)

    def describe(self) -> dict[str, str]:
        return {
            "treasury_inflow_today_sol": "" if self.inflow_sol is None else str(self.inflow_sol)
        }


@dataclass
class FakeSigner:
    pubkey: str = WALLET


@dataclass
class FakeMode:
    live: bool = True
    gates: Any = None


@dataclass
class FakeContext:
    config: ExecutorConfig
    chain: FakeChain = field(default_factory=FakeChain)
    signer: FakeSigner | None = field(default_factory=FakeSigner)
    kill: FakeKill = field(default_factory=FakeKill)
    mode: FakeMode = field(default_factory=FakeMode)
    session_factory: Any = None
    journal: Any = None
    state: ExecutorState = field(default_factory=ExecutorState)
    launch: LaunchStats = field(default_factory=LaunchStats)
    event_exits: EventExitsStats = field(default_factory=EventExitsStats)
    treasury_inflow: FakeInflow = field(default_factory=FakeInflow)
    priority_fees: Any = None
    event_exits_wake: Any = field(default_factory=lambda: _Flag())


class _Flag:
    def __init__(self) -> None:
        self.set_calls = 0

    def set(self) -> None:
        self.set_calls += 1


class _Session:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


@dataclass
class Db:
    candidates: list[Any] = field(default_factory=lambda: list[Any]())
    orders: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    positions: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    claims: list[str] = field(default_factory=lambda: list[str]())
    claim_ok: bool = True
    refused_admitted: list[str] = field(default_factory=lambda: list[str]())
    queried: int = 0
    submitted_at: datetime | None = None


@dataclass
class FakeSubmitter:
    """Signs nothing: returns the fixture's real buy as a confirmed fill."""

    calls: list[Any] = field(default_factory=lambda: list[Any]())
    state: SubmitState = SubmitState.CONFIRMED

    def submit(self, approval: Any) -> SubmitResult:
        self.calls.append(approval)
        tx = json.loads((FIXTURES / "rpc_tx_buy_raw.json").read_text())["result"]
        fill = decode_fills(tx)[0] if self.state is SubmitState.CONFIRMED else None
        return SubmitResult(approval.proposal_id, self.state, "ok", "sig", fill)


def _config(mode: str = "on", *, live: bool = True) -> ExecutorConfig:
    return ExecutorConfig(
        live=live,
        cluster="devnet",
        rpc_url="https://fake",
        limits=limits_from_env(POLICY),
        system_kill_switch=KillSwitchState.ACTIVE,
        kill_file=None,
        send=SendTuning(),
        launch=LaunchConfig(mode=mode),  # type: ignore[arg-type]
    )


def _wire(monkeypatch: pytest.MonkeyPatch, db: Db, submitter: FakeSubmitter) -> None:
    async def launch_candidates(_session: Any, *, now: Any) -> list[Any]:
        db.queried += 1
        return list(db.candidates)

    async def claim(_session: Any, proposal_id: str, *, now: Any) -> bool:
        db.claims.append(proposal_id)
        return db.claim_ok

    async def insert_order(_session: Any, **row: Any) -> str | None:
        db.orders.append(row)
        return f"order-{len(db.orders)}"

    async def insert_position(_session: Any, **row: Any) -> str | None:
        db.positions.append(row)
        return "pos-1"

    async def refuse_admitted_order(_session: Any, key: str, *, reason: str, now: Any) -> bool:
        db.refused_admitted.append(reason)
        return True

    async def nothing(_session: Any, *_a: Any, **_k: Any) -> list[Any]:
        return []

    async def zero(_session: Any, *_a: Any, **_k: Any) -> Decimal:
        return Decimal(0)

    async def token_context(_session: Any, *_a: Any, **_k: Any) -> Any:
        raise RuntimeError("no row yet")

    async def ensure_anchor(ctx: Any, now: Any, equity: Decimal) -> DayAnchor | None:
        if ctx.treasury_inflow.inflow_sol is None:
            return None
        return DayAnchor(DAY_START, Decimal("0.3"), Decimal("0.3"), now)

    async def priority_fee_for(_ctx: Any, _addresses: Any) -> PriorityFeeChoice:
        return PriorityFeeChoice.static(100_000)

    async def record_send_result(_ctx: Any, _key: str, _result: Any) -> None:
        return None

    async def buy_submitted_at(_session: Any, _key: str) -> datetime | None:
        return db.submitted_at

    def session(*_a: Any, **_k: Any) -> _Session:
        return _Session()

    monkeypatch.setattr(le, "role_session", session)
    monkeypatch.setattr(le, "launch_candidates", launch_candidates)
    monkeypatch.setattr(le, "claim_launch_proposal", claim)
    monkeypatch.setattr(le, "insert_order", insert_order)
    monkeypatch.setattr(le, "insert_position", insert_position)
    monkeypatch.setattr(le, "refuse_admitted_order", refuse_admitted_order)
    monkeypatch.setattr(le, "brake_positions", nothing)  # T4.74: one brake
    monkeypatch.setattr(le, "pending_attempts", nothing)
    monkeypatch.setattr(le, "spot_pending_intents", nothing)  # T4.74: one brake
    monkeypatch.setattr(le, "participation_used_sol", zero)
    monkeypatch.setattr(le, "token_context", token_context)
    monkeypatch.setattr(le, "ensure_anchor", ensure_anchor)
    monkeypatch.setattr(le, "priority_fee_for", priority_fee_for)
    monkeypatch.setattr(le, "record_send_result", record_send_result)
    monkeypatch.setattr(le, "buy_submitted_at", buy_submitted_at)

    def make_submitter(**_k: Any) -> FakeSubmitter:
        return submitter

    monkeypatch.setattr(le, "MemeSubmitter", make_submitter)


def _fresh_candidate(age_s: float = 0.6) -> Any:
    proposed = datetime.now(UTC) - timedelta(seconds=age_s)
    c = _candidate(
        reasons=[
            {
                "series": "meme_launch_lane_v1",
                "created_at": (proposed - timedelta(milliseconds=300)).isoformat(),
            }
        ]
    )
    from dataclasses import replace

    return replace(c, candidate=replace(c.candidate, proposed_at=proposed, decided_at=proposed))


# ---- the flag ------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["off", "paper"])
async def test_off_and_paper_never_query_a_launch_proposal(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config(mode))
    assert le.launch_inert_reason(ctx) == f"lane_{mode}"  # type: ignore[arg-type]
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert db.queried == 0 and db.orders == [] and db.claims == []
    assert ctx.chain.blockhash_fetches == 0 and ctx.kill.refreshes == 0


async def test_on_without_the_live_flag_is_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config("on", live=False), signer=None, mode=FakeMode(live=False))
    assert le.launch_inert_reason(ctx) == "meme_live_disabled"  # type: ignore[arg-type]
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert db.queried == 0 and db.orders == []


# ---- refusals before any chain read -------------------------------------------------------


async def test_a_stale_proposal_is_refused_by_name_without_a_chain_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_fresh_candidate(age_s=5.5)]), FakeSubmitter()
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config())
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert ctx.chain.reads == [] and submitter.calls == []
    assert len(db.orders) == 1 and db.orders[0]["status"] == "refused"
    assert db.orders[0]["reason"] == "launch_proposal_stale"
    assert db.claims == [db.orders[0]["proposal_id"]], "refused rows are claimed too"
    assert ctx.launch.refusals == {"launch_proposal_stale": 1}


async def test_a_blocking_kill_switch_refuses_by_name_without_a_chain_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config(), kill=FakeKill(effective=KillSwitchState.EMERGENCY))
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert ctx.chain.reads == [] and db.orders[0]["reason"] == "kill_switch_blocked"


# ---- the happy path ------------------------------------------------------------------------


async def test_a_launch_proposal_becomes_one_buy_with_the_launch_profile_and_a_launch_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    db.submitted_at = datetime.now(UTC) + timedelta(milliseconds=400)
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config())
    ctx.launch.blockhash.refresh(ctx.chain, now=datetime.now(UTC))  # type: ignore[arg-type]
    before = ctx.chain.blockhash_fetches
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert ("curve", "processed") in ctx.chain.reads, "the quote is read processed"
    assert ctx.chain.blockhash_fetches == before, "signed with the cached blockhash, no fetch"
    assert len(db.orders) == 1 and db.orders[0]["status"] == "admitted"
    admission = db.orders[0]["admission"]
    assert admission["profile"] == "launch" and admission["approved"] is True
    states = {c["name"]: c["state"] for c in admission["checks"]}
    assert states["creator_behaviour"] == "skipped" and states["conviction"] == "skipped"
    assert states["bundled_share"] == "skipped" and states["top10_share"] == "skipped"
    assert admission["launch"]["skipped_reads"]["creator_ata"]
    assert admission["launch"]["quote_commitment"] == "processed"
    assert admission["launch"]["token_row_present"] is False
    intent = db.orders[0]["intent"]
    assert intent["lane"] == "launch" and intent["max_slippage_bps"] == 1000
    assert intent["priority_fee"]["micro_lamports"] == 1_000_000
    assert intent["priority_fee"]["source"] == "launch_floor"
    assert Decimal(intent["sol_final"]) == Decimal("0.01")
    assert db.claims == [db.orders[0]["proposal_id"]]
    assert len(submitter.calls) == 1 and ctx.kill.refreshes >= 2, "re-read before signing"
    assert len(db.positions) == 1
    params = db.positions[0]["params"]
    assert params["lane"] == "launch" and params["time_stop_s"] == 6
    assert params["max_drawdown_from_peak_pct"] == "20" and params["exit_on_first_third_party_sell"]
    assert ctx.launch.buys_total == 1 and ctx.event_exits_wake.set_calls == 1
    assert len(ctx.launch.submit_latencies_ms) == 1 and ctx.launch.submit_latencies_ms[0] > 0


async def test_a_claim_that_lost_writes_no_order_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()], claim_ok=False), FakeSubmitter()
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config())
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert db.orders == [] and submitter.calls == [] and ctx.launch.claim_lost_total == 1


async def test_a_switch_that_moves_between_admission_and_signature_refuses_the_admitted_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config(), kill=FakeKill(flip_on_refresh=True))
    ctx.kill.flip_on_refresh = False
    await ctx.kill.refresh()  # the loop's own top-of-step read: still ACTIVE
    ctx.kill.flip_on_refresh = True
    await le.handle_launch_candidate(ctx, db.candidates[0], now=datetime.now(UTC))  # type: ignore[arg-type]
    assert len(db.orders) == 1 and db.orders[0]["status"] == "admitted"
    assert db.refused_admitted == ["kill_switch_blocked_before_signing"]
    assert submitter.calls == [] and db.positions == []
    assert ctx.launch.refusals == {"kill_switch_blocked_before_signing": 1}


async def test_the_launch_cap_refuses_the_third_launch_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from .test_launch_admission import _launch_position

    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire(monkeypatch, db, submitter)

    async def two_open(_session: Any, *_a: Any, **_k: Any) -> list[Any]:
        return [_launch_position(1), _launch_position(2)]

    monkeypatch.setattr(le, "brake_positions", two_open)
    ctx = FakeContext(config=_config())
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert (
        db.orders[0]["status"] == "refused" and db.orders[0]["reason"] == "launch_max_open_reached"
    )
    assert submitter.calls == []


async def test_an_unreadable_treasury_inflow_refuses_day_anchor_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_fresh_candidate()]), FakeSubmitter()
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config(), treasury_inflow=FakeInflow(inflow_sol=None))
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert db.orders[0]["reason"] == "day_anchor_unavailable" and submitter.calls == []


def test_limits_used_by_these_tests_have_the_live_floor_above_the_ticket() -> None:
    assert LIMITS.min_trade_sol == Decimal("0.02") and MINT
