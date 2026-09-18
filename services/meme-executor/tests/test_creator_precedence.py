"""T4.56 — any source that saw the creator sell wins; the tape's ``false`` only
fills the chain's silence; a chain sighting is remembered per mint.

The measurement (R56 §1 and §3.2, ``.claude/state/notes-R56.md``): COVER,
17/09/2026. The creator sold 200 M tokens (20,1 SOL) at 19:46:28 BRT. At 19:46:56
the executor read his ATA (balance 0 against a recorded allocation) and refused
``creator_net_seller``. At 19:47:20 — 23 s later — the desk re-proposed the
same mint; ``meme_features_1m.creator_sold`` said ``false`` (the sale reached the
tape 37,7 s late), the tape had precedence (``admission.creator_net_sol``), the
chain was not asked (``needs_chain_creator_flow``), and the coin was bought.
Real loss −0,08 R.

Three holes, three tests each way:

1. **precedence** — ``resolve_creator_flow``: sold by *any* source ⇒ sold;
2. **cooldown** — ``creator_net_seller`` cools its mint (a creator who sold does
   not un-sell in 120 s);
3. **memory** — a chain sighting is kept for 30 min so a later tape ``false``
   never re-opens the mint, even without a second RPC read.

No network and no database: the rows are faked, the chain reader is a fake
whose balance the test sets, and ``build_admission_context`` runs as it does in
``entries.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pytest

from hunter_meme_executor import admission_context
from hunter_meme_executor.admission import context_from
from hunter_meme_executor.admission_context import build_admission_context
from hunter_meme_executor.chain import TokenAccountRead
from hunter_meme_executor.context import ExecutorState
from hunter_meme_executor.creator_flow import (
    CHAIN_FLOW_SOURCE,
    CREATOR_SOLD_MEMORY_MAX_MINTS,
    CREATOR_SOLD_MEMORY_TTL_S,
    MEMORY_FLOW_SOURCE,
    TAPE_FLOW_SOURCE,
    CreatorSoldMemory,
    creator_flow_from_chain,
    resolve_creator_flow,
)
from hunter_meme_executor.refusal_cooldown import DETERMINISTIC_REFUSALS, cooling_mints_of
from hunter_meme_executor.repo import TokenContext
from hunter_risk_meme.checks import REFUSAL_NAMES

if TYPE_CHECKING:
    from hunter_meme_executor.chain import CurveRead
    from hunter_meme_executor.context import ExecutorContext

pytestmark = pytest.mark.unit

# COVER's clock, in UTC (19:46:56 BRT = 22:46:56Z; the buy landed at 22:47:20Z).
T0 = datetime(2026, 9, 17, 22, 46, 56, tzinfo=UTC)
T1 = T0 + timedelta(seconds=23)
MINT = "CoverCoverCoverCoverCoverCoverCoverCoverpump"
CREATOR = "CEC8SGJea2R4gUrL9C3cCJDa9ChhLie2NmCSFZfwD2hD"
INITIAL = Decimal("200000000")
SUBUNITS = 1_000_000


def _token(creator_sold: bool | None, **overrides: object) -> TokenContext:
    values: dict[str, object] = {
        "created_at": T0 - timedelta(seconds=150),
        "creator": CREATOR,
        "initial_real_token_reserves": 793_100_000,
        "completed_at": None,
        "migrated_at": None,
        "curve_volume_1m_sol": Decimal("4.2"),
        "features_end_time": T0 - timedelta(seconds=20),
        "creator_sold": creator_sold,
        "top10_share": Decimal("0.2"),
        "bundled_share": Decimal("0.05"),
        "creator_initial_tokens": INITIAL,
        "creator_initial_sol": Decimal("5.5"),
    }
    values.update(overrides)
    return TokenContext(**values)  # type: ignore[arg-type]


def _chain(balance_tokens: Decimal, *, at: datetime = T0):
    return creator_flow_from_chain(
        initial_tokens=INITIAL,
        balance_subunits=int(balance_tokens * SUBUNITS),
        tolerance_pct=Decimal("0.02"),
        observed_at=at,
    )


class TestPrecedenceIsFailClosedBothWays:
    """``resolve_creator_flow`` is pure: (tape, chain, memory) → (net_sol, who decided)."""

    def test_cover_the_chain_says_sold_and_the_tape_still_says_false(self) -> None:
        verdict = resolve_creator_flow(tape_sold=False, flow=_chain(Decimal(0)), remembered_at=None)
        assert verdict.net_sol == Decimal(-1)
        assert verdict.decided_by == CHAIN_FLOW_SOURCE == "chain_ata_vs_initial"

    def test_the_reverse_the_tape_saw_the_sale_and_the_chain_is_absent(self) -> None:
        verdict = resolve_creator_flow(tape_sold=True, flow=None, remembered_at=None)
        assert verdict.net_sol == Decimal(-1)
        assert verdict.decided_by == TAPE_FLOW_SOURCE

    def test_a_chain_read_that_says_holding_never_overrides_a_tape_true(self) -> None:
        """He sold and bought back more (the tape's ``creator_sold`` is *any*
        sell): the balance is above the base, the trade still happened."""
        verdict = resolve_creator_flow(tape_sold=True, flow=_chain(INITIAL * 2), remembered_at=None)
        assert verdict.net_sol == Decimal(-1)
        assert verdict.decided_by == TAPE_FLOW_SOURCE

    def test_the_happy_path_both_say_no(self) -> None:
        verdict = resolve_creator_flow(tape_sold=False, flow=_chain(INITIAL), remembered_at=None)
        assert verdict.net_sol == Decimal(1)
        assert verdict.decided_by == TAPE_FLOW_SOURCE
        assert verdict.chain_net_sol == Decimal(1), "the agreeing read is on record"

    def test_the_tape_fills_in_only_when_the_chain_is_absent(self) -> None:
        """A failed or skipped read leaves ``flow = None``; the tape's ``false``
        is then the only answer and the engine sees ``+1`` — exactly the T4.45
        behaviour, now reached only through the chain's silence."""
        verdict = resolve_creator_flow(tape_sold=False, flow=None, remembered_at=None)
        assert verdict.net_sol == Decimal(1)
        assert verdict.decided_by == TAPE_FLOW_SOURCE

    def test_the_chain_alone_still_answers_the_silent_tape(self) -> None:
        """T4.45's own case is unchanged: tape NULL, chain speaks."""
        holding = resolve_creator_flow(tape_sold=None, flow=_chain(INITIAL), remembered_at=None)
        dumped = resolve_creator_flow(tape_sold=None, flow=_chain(Decimal(0)), remembered_at=None)
        assert (holding.net_sol, holding.decided_by) == (Decimal(1), CHAIN_FLOW_SOURCE)
        assert (dumped.net_sol, dumped.decided_by) == (Decimal(-1), CHAIN_FLOW_SOURCE)

    def test_nothing_spoke_is_still_unknown(self) -> None:
        verdict = resolve_creator_flow(tape_sold=None, flow=None, remembered_at=None)
        assert verdict.net_sol is None and verdict.decided_by is None

    def test_a_remembered_sighting_beats_a_later_tape_false(self) -> None:
        verdict = resolve_creator_flow(tape_sold=False, flow=None, remembered_at=T0)
        assert verdict.net_sol == Decimal(-1)
        assert verdict.decided_by == MEMORY_FLOW_SOURCE

    def test_the_json_names_every_source_and_the_decision(self) -> None:
        payload = resolve_creator_flow(
            tape_sold=False, flow=_chain(Decimal(0)), remembered_at=T0
        ).as_json()
        assert payload == {
            "net_sol": "-1",
            "decided_by": CHAIN_FLOW_SOURCE,
            "tape_creator_sold": "false",
            "chain_net_sol": "-1",
            "remembered_sold_at": T0.isoformat(),
        }

    def test_context_from_carries_the_same_rule_into_the_engine(self) -> None:
        """``admission.creator_net_sol`` delegates: the engine's check 10 sees
        the verdict, not the tape."""
        cover = context_from(
            MINT,
            _token(False),
            participation_used_sol=Decimal(0),
            now=T1,
            creator_flow=_chain(Decimal(0)),
        )
        assert cover.creator_net_sol == Decimal(-1)
        remembered = context_from(
            MINT,
            _token(False),
            participation_used_sol=Decimal(0),
            now=T1,
            creator_sold_remembered_at=T0,
        )
        assert remembered.creator_net_sol == Decimal(-1)
        fine = context_from(MINT, _token(False), participation_used_sol=Decimal(0), now=T1)
        assert fine.creator_net_sol == Decimal(1)


class TestTheCooldown:
    def test_a_creator_who_sold_cools_his_mint(self) -> None:
        """The desk re-proposes every ~20 s; a creator who sold ≥ 98 % of his
        allocation does not un-sell in 120 s. Retrying is one refused order and
        one rejected proposal per pass — COVER's 23 s."""
        assert "creator_net_seller" in REFUSAL_NAMES
        assert "creator_net_seller" in DETERMINISTIC_REFUSALS
        assert cooling_mints_of([(MINT, "creator_net_seller")]) == frozenset({MINT})

    def test_an_unknown_flow_does_not_cool(self) -> None:
        """``creator_flow_unknown`` is data availability: the next tick's chain
        read (T4.45) or the fold's row can resolve it, so the retry is worth its
        RPC call."""
        assert "creator_flow_unknown" in REFUSAL_NAMES
        assert "creator_flow_unknown" not in DETERMINISTIC_REFUSALS
        assert cooling_mints_of([(MINT, "creator_flow_unknown")]) == frozenset()


class TestTheMemory:
    def test_a_sighting_is_kept_and_read_back(self) -> None:
        memory = CreatorSoldMemory()
        memory.remember(MINT, T0)
        assert memory.seen_at(MINT, now=T1) == T0
        assert memory.seen_at("other", now=T1) is None

    def test_the_first_sighting_is_the_one_kept(self) -> None:
        """ "Seen on chain at <ts>" is the instant the desk learned it; a later
        read confirming the same fact does not move the stamp."""
        memory = CreatorSoldMemory()
        memory.remember(MINT, T0)
        memory.remember(MINT, T1)
        assert memory.seen_at(MINT, now=T1) == T0

    def test_a_sighting_expires_after_the_ttl(self) -> None:
        memory = CreatorSoldMemory()
        memory.remember(MINT, T0)
        inside = T0 + timedelta(seconds=CREATOR_SOLD_MEMORY_TTL_S)
        outside = inside + timedelta(seconds=1)
        assert CREATOR_SOLD_MEMORY_TTL_S == 30 * 60
        assert memory.seen_at(MINT, now=inside) == T0
        assert memory.seen_at(MINT, now=outside) is None
        assert len(memory) == 0, "evicted, not merely hidden"

    def test_the_dict_is_bounded_and_evicts_the_oldest(self) -> None:
        memory = CreatorSoldMemory(max_mints=3)
        for i in range(5):
            memory.remember(f"mint{i}", T0 + timedelta(seconds=i))
        assert len(memory) == 3
        assert memory.seen_at("mint0", now=T1) is None
        assert memory.seen_at("mint1", now=T1) is None
        assert memory.seen_at("mint4", now=T1) == T0 + timedelta(seconds=4)
        assert CREATOR_SOLD_MEMORY_MAX_MINTS >= 1024

    def test_the_executor_state_owns_one(self) -> None:
        assert isinstance(ExecutorState().creator_sold_on_chain, CreatorSoldMemory)


# --- COVER end to end through ``build_admission_context`` -------------------


class FakeChainReader:
    """The creator's ATA as the test sets it; ``None`` balance = the read fails."""

    def __init__(self) -> None:
        self.balance_subunits: int | None = 0
        self.calls = 0

    def token_account(self, owner: str, mint: str, token_program: str) -> TokenAccountRead:
        self.calls += 1
        assert owner == CREATOR and mint == MINT
        if self.balance_subunits is None:
            raise ConnectionError("rpc down")
        return TokenAccountRead(exists=self.balance_subunits > 0, amount=self.balance_subunits)


@dataclass
class FakeConfig:
    risk_read_timeout_s: float = 1.0
    creator_sell_tolerance_pct: Decimal = Decimal("0.02")


@dataclass
class FakeContext:
    chain: FakeChainReader = field(default_factory=FakeChainReader)
    config: FakeConfig = field(default_factory=FakeConfig)
    state: ExecutorState = field(default_factory=ExecutorState)
    session_factory: Any = None


@dataclass
class FakeCurve:
    token_program: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The rows ``build_admission_context`` reads, faked at the module seam."""
    rows: dict[str, Any] = {"token": _token(None)}

    @asynccontextmanager
    async def fake_role_session(*args: Any, **kwargs: Any) -> AsyncGenerator[None]:
        yield None

    async def fake_token_context(session: Any, mint: str, *, now: datetime) -> TokenContext:
        return cast("TokenContext", rows["token"])

    async def none_list(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def zero(*args: Any, **kwargs: Any) -> Decimal:
        return Decimal(0)

    async def no_read(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(admission_context, "role_session", fake_role_session)
    monkeypatch.setattr(admission_context, "token_context", fake_token_context)
    monkeypatch.setattr(admission_context, "open_positions", none_list)
    monkeypatch.setattr(admission_context, "pending_attempts", none_list)
    monkeypatch.setattr(admission_context, "participation_used_sol", zero)
    monkeypatch.setattr(admission_context, "read_risk_snapshot_on_demand", no_read)
    return rows


async def _build(ctx: FakeContext, *, now: datetime):
    return await build_admission_context(
        cast("ExecutorContext", ctx), MINT, cast("CurveRead", FakeCurve()), now=now
    )


class TestCoverEndToEnd:
    @pytest.mark.asyncio
    async def test_cover_refused_at_t0_stays_refused_at_t0_plus_23s(
        self, rows: dict[str, Any]
    ) -> None:
        ctx = FakeContext()
        # 19:46:56 BRT — fold silent, chain: balance 0 against 200 M recorded.
        rows["token"] = _token(None)
        ctx.chain.balance_subunits = 0
        first = await _build(ctx, now=T0)
        assert first.context.creator_net_sol == Decimal(-1)
        assert first.extras["creator_flow"]["source"] == CHAIN_FLOW_SOURCE
        assert first.extras["creator_verdict"]["decided_by"] == CHAIN_FLOW_SOURCE
        assert ctx.chain.calls == 1

        # 19:47:20 BRT — the fold now says ``false`` (the sale reached the tape
        # 37,7 s late). Before T4.56: tape wins, no read, +1, bought.
        rows["token"] = _token(False)
        second = await _build(ctx, now=T1)
        assert second.context.creator_net_sol == Decimal(-1)
        verdict = second.extras["creator_verdict"]
        assert verdict["decided_by"] == MEMORY_FLOW_SOURCE
        assert verdict["remembered_sold_at"] == T0.isoformat()
        assert verdict["tape_creator_sold"] == "false"
        assert ctx.chain.calls == 1, "the memory settles it without a second RPC read"

    @pytest.mark.asyncio
    async def test_cover_in_a_fresh_process_the_chain_is_asked_despite_the_tape(
        self, rows: dict[str, Any]
    ) -> None:
        """No memory (restart between the two ticks): the tape's ``false`` no
        longer silences the read, and the read refuses by name."""
        ctx = FakeContext()
        rows["token"] = _token(False)
        ctx.chain.balance_subunits = 0
        built = await _build(ctx, now=T1)
        assert ctx.chain.calls == 1
        assert built.context.creator_net_sol == Decimal(-1)
        assert built.extras["creator_verdict"]["decided_by"] == CHAIN_FLOW_SOURCE
        assert built.extras["creator_flow"]["net_sol"] == "-1"
        assert ctx.state.creator_sold_on_chain.seen_at(MINT, now=T1) == T1

    @pytest.mark.asyncio
    async def test_the_tape_true_refuses_without_a_read(self, rows: dict[str, Any]) -> None:
        ctx = FakeContext()
        rows["token"] = _token(True)
        ctx.chain.balance_subunits = int(INITIAL) * SUBUNITS
        built = await _build(ctx, now=T1)
        assert ctx.chain.calls == 0
        assert built.context.creator_net_sol == Decimal(-1)
        assert built.extras["creator_verdict"]["decided_by"] == TAPE_FLOW_SOURCE
        assert "creator_flow" not in built.extras

    @pytest.mark.asyncio
    async def test_the_happy_path_both_say_no(self, rows: dict[str, Any]) -> None:
        ctx = FakeContext()
        rows["token"] = _token(False)
        ctx.chain.balance_subunits = int(INITIAL) * SUBUNITS
        built = await _build(ctx, now=T1)
        assert ctx.chain.calls == 1
        assert built.context.creator_net_sol == Decimal(1)
        verdict = built.extras["creator_verdict"]
        assert verdict["net_sol"] == "1"
        assert verdict["chain_net_sol"] == "1"
        assert built.extras["creator_flow"]["source"] == CHAIN_FLOW_SOURCE
        assert len(ctx.state.creator_sold_on_chain) == 0, "nothing to remember"

    @pytest.mark.asyncio
    async def test_a_failed_read_leaves_the_tape_to_fill_in(self, rows: dict[str, Any]) -> None:
        ctx = FakeContext()
        rows["token"] = _token(False)
        ctx.chain.balance_subunits = None
        built = await _build(ctx, now=T1)
        assert built.context.creator_net_sol == Decimal(1)
        assert built.extras["creator_flow"] == {
            "source": CHAIN_FLOW_SOURCE,
            "read_failed": "ConnectionError",
        }
        assert built.extras["creator_verdict"]["decided_by"] == TAPE_FLOW_SOURCE
        assert built.extras["creator_verdict"]["chain_net_sol"] == ""

    @pytest.mark.asyncio
    async def test_a_hanging_read_is_bounded_by_the_deadline(self, rows: dict[str, Any]) -> None:
        ctx = FakeContext(config=FakeConfig(risk_read_timeout_s=0.05))

        def hang(*args: Any, **kwargs: Any) -> TokenAccountRead:
            import time

            time.sleep(0.3)
            return TokenAccountRead(exists=True, amount=0)

        ctx.chain.token_account = hang  # type: ignore[method-assign]
        rows["token"] = _token(None)
        started = asyncio.get_running_loop().time()
        built = await _build(ctx, now=T1)
        assert asyncio.get_running_loop().time() - started < 0.25
        assert built.context.creator_net_sol is None, "timeout is silence, never a pass"
        assert built.extras["creator_flow"]["read_failed"] == "timeout"
