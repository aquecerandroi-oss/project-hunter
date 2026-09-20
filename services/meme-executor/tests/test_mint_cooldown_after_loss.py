"""T4.78 — the executor's side of check 28 (``mint_cooldown_after_loss``): the
losses are read from ``meme_live_positions`` (one bounded query, losses only),
reach the engine as ``MemeWalletState.recent_losses`` through
``build_admission_context`` → ``wallet_from``, the refusal is counted by base
name on the heartbeat (``refusals.mint_cooldown_after_loss``), the window is
published in the ``policy`` block, and the stage-1 robot does not re-open a
mint the engine just refused for this reason (``refusal_cooldown``).

No Docker: the rows are faked at the module seams the other unit tests use.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_meme_executor import admission_context, entries
from hunter_meme_executor.admission import wallet_from
from hunter_meme_executor.admission_context import build_admission_context
from hunter_meme_executor.chain import WalletRead
from hunter_meme_executor.context import ExecutorState
from hunter_meme_executor.heartbeat import policy_fields
from hunter_meme_executor.kill_switch import DayAnchor
from hunter_meme_executor.refusal_cooldown import (
    SHORT_COOLDOWNS,
    cooling_mints_by_window,
    cooling_mints_of,
)
from hunter_meme_executor.repo import Candidate, TokenContext
from hunter_meme_executor.repo_positions import recent_losses
from hunter_risk_meme import MEME_PAPER_V0, MINT_COOLDOWN_AFTER_LOSS, MemeLimits, limits_from_env

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 19, 17, 28, 40, tzinfo=UTC)  # Musepaid's operator/5 re-entry
LOST_AT = datetime(2026, 9, 19, 17, 28, 15, tzinfo=UTC)  # operator/6's exit, 25 s earlier
DAY_START = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)
MINT = "MusepaidMusepaidMusepaidMusepaidMusepaidpump"
OTHER = "NarkyNarkyNarkyNarkyNarkyNarkyNarkyNarkypump"
POLICY = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.02",
    "MEME_DAILY_LOSS_CAP_SOL": "0.05",
    "MEME_MAX_OPEN_POSITIONS": "2",
    "MEME_COOLDOWN_S": "1800",
}


# ---- the query -----------------------------------------------------------------------


class FakeSession:
    """Records the statement and its parameters; answers the scalar it was given."""

    def __init__(self, stamp: datetime | None) -> None:
        self.stamp = stamp
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any]) -> FakeSession:
        self.calls.append((str(statement), params))
        return self

    def scalar(self) -> datetime | None:
        return self.stamp


class TestTheQuery:
    async def test_the_newest_losing_close_of_the_candidate_s_mint_inside_the_window(
        self,
    ) -> None:
        """Per mint, never a global "last N losing mints": Astra (review T4.78) —
        with 51 losing mints in the window a global read bounded to 50 could
        omit exactly the candidate, and an empty map reads as "no loss"."""
        session = FakeSession(LOST_AT)
        losses = await recent_losses(cast("Any", session), MINT, now=NOW, cooldown_s=300)
        assert losses == {MINT: LOST_AT}
        sql, params = session.calls[0]
        assert "mint = :mint" in sql and "status = 'closed'" in sql and "pnl_sol < 0" in sql
        assert "exit_at >= :since" in sql and "max(exit_at)" in sql, "the newest loss only"
        assert "LIMIT" not in sql, "keyed by the mint: nothing to truncate"
        assert params == {"mint": MINT, "since": NOW - timedelta(seconds=300)}

    async def test_no_losing_close_is_an_empty_map(self) -> None:
        assert (
            await recent_losses(cast("Any", FakeSession(None)), MINT, now=NOW, cooldown_s=300) == {}
        )

    async def test_zero_runs_no_query(self) -> None:
        session = FakeSession(LOST_AT)
        assert await recent_losses(cast("Any", session), MINT, now=NOW, cooldown_s=0) == {}
        assert session.calls == []


# ---- the input reaches the engine ------------------------------------------------------


def _token() -> TokenContext:
    values: dict[str, object] = {
        "created_at": NOW - timedelta(seconds=150),
        "creator": "CEC8SGJea2R4gUrL9C3cCJDa9ChhLie2NmCSFZfwD2hD",
        "initial_real_token_reserves": 793_100_000,
        "completed_at": None,
        "migrated_at": None,
        "curve_volume_1m_sol": Decimal("4.2"),
        "features_end_time": NOW - timedelta(seconds=20),
        "creator_sold": False,
        "top10_share": Decimal("0.2"),
        "bundled_share": Decimal("0.05"),
        "creator_initial_tokens": None,
        "creator_initial_sol": None,
    }
    return TokenContext(**values)  # type: ignore[arg-type]


@dataclass
class FakeConfig:
    limits: MemeLimits = MEME_PAPER_V0
    risk_read_timeout_s: float = 1.0
    creator_sell_tolerance_pct: Decimal = Decimal("0.02")


@dataclass
class FakeContext:
    config: FakeConfig = field(default_factory=FakeConfig)
    state: ExecutorState = field(default_factory=ExecutorState)
    chain: Any = None
    session_factory: Any = None


@dataclass
class FakeCurve:
    token_program: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


@pytest.fixture
def seams(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {"losses": {MINT: LOST_AT}, "cooldown_calls": []}

    @asynccontextmanager
    async def fake_role_session(*_a: Any, **_k: Any) -> AsyncGenerator[None]:
        yield None

    async def fake_token_context(_s: Any, _mint: str, *, now: datetime) -> TokenContext:
        return _token()

    async def none_list(*_a: Any, **_k: Any) -> list[Any]:
        return []

    async def zero(*_a: Any, **_k: Any) -> Decimal:
        return Decimal(0)

    async def no_read(*_a: Any, **_k: Any) -> bool:
        return False

    async def fake_recent_losses(
        _s: Any, mint: str, *, now: datetime, cooldown_s: int
    ) -> dict[str, datetime]:
        seen["cooldown_calls"].append(cooldown_s)
        seen["mints_asked"] = [*seen.get("mints_asked", []), mint]
        return {} if cooldown_s <= 0 else {m: t for m, t in seen["losses"].items() if m == mint}

    monkeypatch.setattr(admission_context, "role_session", fake_role_session)
    monkeypatch.setattr(admission_context, "token_context", fake_token_context)
    monkeypatch.setattr(admission_context, "brake_positions", none_list)
    monkeypatch.setattr(admission_context, "pending_attempts", none_list)
    monkeypatch.setattr(admission_context, "spot_pending_intents", none_list)
    monkeypatch.setattr(admission_context, "participation_used_sol", zero)
    monkeypatch.setattr(admission_context, "read_risk_snapshot_on_demand", no_read)
    monkeypatch.setattr(admission_context, "recent_losses", fake_recent_losses)
    return seen


def _wallet(losses: dict[str, datetime]):
    anchor = DayAnchor(DAY_START, Decimal("0.3"), Decimal("0.3"), NOW)
    return wallet_from(
        wallet_id="wallet",
        now=NOW,
        balance=WalletRead(pubkey="wallet", lamports=300_000_000, slot=1, observed_at=NOW),
        positions=[],
        pending=[],
        anchor=anchor,
        limits=MEME_PAPER_V0,
        recent_losses=losses,
    )


class TestTheInputReachesTheEngine:
    async def test_the_admission_context_carries_the_losses_read_with_the_limits_window(
        self, seams: dict[str, Any]
    ) -> None:
        ctx = FakeContext()
        built = await build_admission_context(
            cast("Any", ctx), MINT, cast("Any", FakeCurve()), now=NOW
        )
        assert built.recent_losses == {MINT: LOST_AT}
        assert seams["cooldown_calls"] == [300], "the window is the limits' own"
        assert seams["mints_asked"] == [MINT], "asked for the candidate's mint"

    async def test_a_disabled_window_hands_the_engine_nothing(self, seams: dict[str, Any]) -> None:
        limits = MEME_PAPER_V0.model_validate(
            {**MEME_PAPER_V0.model_dump(), "mint_cooldown_after_loss_s": 0}
        )
        ctx = FakeContext(config=FakeConfig(limits=limits))
        built = await build_admission_context(
            cast("Any", ctx), MINT, cast("Any", FakeCurve()), now=NOW
        )
        assert built.recent_losses == {} and seams["cooldown_calls"] == [0]

    def test_wallet_from_puts_them_on_the_wallet_state(self) -> None:
        wallet = _wallet({MINT: LOST_AT})
        assert wallet.recent_losses == {MINT: LOST_AT}
        assert wallet.age_s(LOST_AT) == Decimal(25)
        assert _wallet({}).recent_losses == {}

    def test_a_loss_on_mint_a_leaves_mint_b_alone_and_a_sell_never_reads_it(self) -> None:
        """The engine's own cases are in ``packages/risk-core``; here only the
        wiring: ``recent_losses`` is keyed by mint, and no exit path calls
        ``wallet_from`` with it (``exits.py`` never builds an entry wallet)."""
        wallet = _wallet({OTHER: LOST_AT})
        assert MINT not in wallet.recent_losses and OTHER in wallet.recent_losses


# ---- the refusal is counted and the window published -------------------------------------


def _candidate() -> Candidate:
    return Candidate(
        id="01994d00-6c1a-7000-8000-000000000101",
        mint=MINT,
        decision={"size_sol": "0.02"},
        decided_at=NOW,
        decided_by="executor:auto_stage1",
        status="approved",
        proposed_at=NOW - timedelta(seconds=2),
    )


class TestTheCounterAndTheHeartbeat:
    def test_record_refusal_counts_by_base_name(self) -> None:
        state = ExecutorState()
        state.record_refusal("mint_cooldown_after_loss:275")
        state.record_refusal("mint_cooldown_after_loss:113")
        state.record_refusal("build_failed:KeyError")
        state.record_refusal("duplicate_position")
        assert state.refusals == {
            "mint_cooldown_after_loss": 2,
            "build_failed": 1,
            "duplicate_position": 1,
        }
        assert state.entries_refused == 4
        assert state.last_refusal == "duplicate_position"

    async def test_the_desk_refusal_path_feeds_the_counter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``entries._refuse``: the refused row is written and the counter moves —
        with the reason the engine produced, seconds and all."""
        written: list[dict[str, Any]] = []

        @asynccontextmanager
        async def fake_role_session(*_a: Any, **_k: Any) -> AsyncGenerator[None]:
            yield None

        async def insert_order(_s: Any, **kw: Any) -> str:
            written.append(kw)
            return "order"

        async def reject_if_auto(*_a: Any, **_k: Any) -> None:
            return None

        monkeypatch.setattr(entries, "role_session", fake_role_session)
        monkeypatch.setattr(entries, "insert_order", insert_order)
        monkeypatch.setattr(entries, "reject_if_auto", reject_if_auto)
        ctx = FakeContext()
        await entries._refuse(  # pyright: ignore[reportPrivateUsage]
            cast("Any", ctx), _candidate(), "mint_cooldown_after_loss:275", {"checks": []}
        )
        assert written[0]["status"] == "refused"
        assert written[0]["reason"] == "mint_cooldown_after_loss:275"
        assert ctx.state.refusals == {"mint_cooldown_after_loss": 1}
        assert ctx.state.last_refusal == "mint_cooldown_after_loss:275"

    def test_the_policy_block_publishes_the_window(self) -> None:
        assert policy_fields(MEME_PAPER_V0)["mint_cooldown_after_loss_s"] == 300
        live = limits_from_env({**POLICY, "MEME_MINT_COOLDOWN_AFTER_LOSS_S": "0"})
        assert policy_fields(live)["mint_cooldown_after_loss_s"] == 0
        json.dumps(policy_fields(live))


# ---- the stage-1 robot does not re-open a cooling mint ---------------------------------------


class TestTheRobotWaits:
    def test_the_reason_with_its_seconds_cools_the_mint_by_base_name(self) -> None:
        rows = [(MINT, "mint_cooldown_after_loss:240", NOW - timedelta(seconds=30))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset({MINT})
        assert SHORT_COOLDOWNS[MINT_COOLDOWN_AFTER_LOSS] == 300.0

    def test_capped_by_the_owner_s_cooldown_like_every_short_one(self) -> None:
        rows = [(MINT, "mint_cooldown_after_loss:240", NOW - timedelta(seconds=121))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset()

    def test_the_announced_remainder_is_the_wait_never_the_ceiling(self) -> None:
        """Astra (review T4.78): loss at t=0, refusal at t=290 with ``:10``, owner's
        cooldown 120 s — the engine frees the mint at t=300; the robot must not
        hold it until t=410."""
        refused_at = NOW - timedelta(seconds=11)  # ``:10`` announced 11 s ago
        rows = [(MINT, "mint_cooldown_after_loss:10", refused_at)]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset()
        rows = [(MINT, "mint_cooldown_after_loss:10", NOW - timedelta(seconds=9))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset({MINT})

    def test_a_reason_without_a_readable_remainder_uses_the_ceiling(self) -> None:
        rows = [(MINT, "mint_cooldown_after_loss", NOW - timedelta(seconds=100))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset({MINT})
        rows = [(MINT, "mint_cooldown_after_loss:soon", NOW - timedelta(seconds=100))]
        assert cooling_mints_by_window(rows, now=NOW, cooldown_s=120.0) == frozenset({MINT})

    def test_it_is_not_a_deterministic_refusal_the_clock_clears_it(self) -> None:
        """``cooling_mints_of`` is the deterministic set only — this one waits
        by its own window, never by the owner's alone."""
        assert cooling_mints_of([(MINT, "mint_cooldown_after_loss:240")]) == frozenset()
