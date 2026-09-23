"""T4.54b — the treasury tick around its pure rules, with fakes for the
database, the chain and Jupiter: fix D (flag off = pure no-op; a failure
inside never escapes), fix E (a target above the wallet ceiling is refused
by name before any quote), fix B (a quote that drifts from the request is
refused before the builder), fix C (the reconcile settles ``submitted`` rows
from ``getSignatureStatuses``) and the simulated-balance parser."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from structlog.testing import capture_logs

from hunter_exchanges.jupiter import JupiterQuote
from hunter_meme_executor import treasury, treasury_reconcile
from hunter_meme_executor.chain import TokenAccountRead, WalletRead
from hunter_meme_executor.context import ExecutorContext, ExecutorState
from hunter_meme_executor.treasury_db import SubmittedSwap
from hunter_meme_executor.treasury_send import simulated_balances

pytestmark = pytest.mark.unit

PUBKEY = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL = "So11111111111111111111111111111111111111112"


class _NeverOpened:
    """A session factory that proves nothing touched the database."""

    def __call__(self) -> Any:
        raise AssertionError("a session was opened with the treasury disabled")


@dataclass
class FakeRpc:
    statuses: list[dict[str, Any] | None] = field(
        default_factory=lambda: list[dict[str, Any] | None]()
    )
    calls: list[str] = field(default_factory=lambda: list[str]())
    tx: dict[str, Any] | None = None
    tx_error: Exception | None = None

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        self.calls.append("statuses")
        return self.statuses

    def get_transaction(self, signature: str) -> dict[str, Any] | None:
        self.calls.append("transaction")
        if self.tx_error is not None:
            raise self.tx_error
        return self.tx


@dataclass
class FakeChain:
    rpc: FakeRpc = field(default_factory=FakeRpc)
    lamports: int = 680_000_000
    usdc_atoms: int = 21_330_000
    calls: list[str] = field(default_factory=lambda: list[str]())

    def wallet(self, pubkey: str) -> WalletRead:
        self.calls.append("wallet")
        return WalletRead(pubkey, self.lamports, 1, datetime.now(UTC))

    def token_account(self, owner: str, mint: str, token_program: str) -> TokenAccountRead:
        self.calls.append("token_account")
        return TokenAccountRead(exists=True, amount=self.usdc_atoms)


@dataclass
class FakeLimits:
    wallet_max_sol: Decimal = Decimal("0.72")
    max_sol_per_trade: Decimal = Decimal("0.02")


@dataclass
class FakeConfig:
    treasury_enabled: bool = True
    live: bool = True
    treasury_sol_floor: Decimal = Decimal("0.70")
    treasury_sol_target: Decimal = Decimal("0.60")
    treasury_max_usdc_per_swap: Decimal = Decimal("25")
    treasury_max_usdc_per_day: Decimal = Decimal("50")
    treasury_max_slippage_bps: int = 50
    treasury_min_interval_s: float = 600.0
    confirm_timeout_s: float = 30.0
    limits: FakeLimits = field(default_factory=FakeLimits)


@dataclass
class FakeKill:
    blocks_entries: bool = False


@dataclass
class FakeSigner:
    pubkey: str = PUBKEY


@dataclass
class FakeJupiter:
    quotes: dict[int, JupiterQuote] = field(default_factory=lambda: dict[int, JupiterQuote]())
    calls: list[int] = field(default_factory=lambda: list[int]())

    def quote(self, *, input_mint: str, output_mint: str, amount: int, slippage_bps: int) -> Any:
        self.calls.append(amount)
        return self.quotes[amount]


@dataclass
class FakeContext:
    config: FakeConfig
    chain: FakeChain
    signer: FakeSigner | None
    kill: FakeKill
    session_factory: Any
    treasury_client: FakeJupiter
    state: ExecutorState = field(default_factory=ExecutorState)


def _ctx(**config: Any) -> FakeContext:
    ctx = FakeContext(
        config=FakeConfig(**config),
        chain=FakeChain(),
        signer=FakeSigner(),
        kill=FakeKill(),
        session_factory=_NeverOpened(),
        treasury_client=FakeJupiter(),
    )
    ctx.state.wallet_lamports = 680_000_000
    return ctx


def _quote(amount: int, out: int, **overrides: Any) -> JupiterQuote:
    base: dict[str, Any] = {
        "input_mint": USDC,
        "output_mint": WSOL,
        "in_amount": Decimal(amount),
        "out_amount": Decimal(out),
        "other_amount_threshold": Decimal(out * 9950 // 10_000),
        "price_impact_pct": Decimal(0),
        "slippage_bps": 50,
        "route_labels": ("HumidiFi",),
        "raw": {},
    }
    base.update(overrides)
    return JupiterQuote(**base)


def _fake_db(monkeypatch: pytest.MonkeyPatch, ctx: FakeContext) -> None:
    """The two reads ``_tick`` makes, and no reconcile work, without Postgres."""

    class _Session:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_exc: object) -> None:
            return None

    def fake_session(_factory: Any, *, db_role: str) -> _Session:
        return _Session()

    async def last_attempt_at(_session: Any) -> None:
        return None

    async def usdc_committed_last_24h(_session: Any, *, now: datetime) -> Decimal:
        return Decimal(0)

    async def submitted_swaps(_session: Any) -> list[SubmittedSwap]:
        return []

    monkeypatch.setattr(treasury, "role_session", fake_session)
    monkeypatch.setattr(treasury_reconcile, "role_session", fake_session)
    monkeypatch.setattr(treasury.treasury_db, "last_attempt_at", last_attempt_at)
    monkeypatch.setattr(treasury.treasury_db, "usdc_committed_last_24h", usdc_committed_last_24h)
    monkeypatch.setattr(treasury_reconcile.treasury_db, "submitted_swaps", submitted_swaps)


# ------------------------------------------------------------------ fix D
async def test_with_the_flag_off_the_tick_opens_no_session_and_makes_no_call() -> None:
    ctx = _ctx(treasury_enabled=False)
    await treasury.treasury_once(cast(ExecutorContext, ctx))
    assert ctx.chain.calls == [] and ctx.chain.rpc.calls == [] and ctx.treasury_client.calls == []
    assert ctx.state.treasury_last_attempt_reason == "disabled"
    assert ctx.state.rpc_errors == 0


async def test_a_failure_inside_the_tick_is_logged_and_counted_never_raised() -> None:
    ctx = _ctx()  # enabled, live, signer: the first DB access explodes
    await treasury.treasury_once(cast(ExecutorContext, ctx))
    assert ctx.state.rpc_errors == 1
    assert ctx.state.treasury_last_attempt_reason == "tick_failed:AssertionError"


async def test_without_live_or_signer_nothing_is_read_at_all() -> None:
    ctx = _ctx(live=False)
    await treasury.treasury_once(cast(ExecutorContext, ctx))
    assert ctx.state.treasury_last_attempt_reason == "live_disabled"
    ctx = _ctx()
    ctx.signer = None
    await treasury.treasury_once(cast(ExecutorContext, ctx))
    assert ctx.state.treasury_last_attempt_reason == "no_signer"


# ------------------------------------------------------------------ fix E
async def test_a_target_above_the_wallet_ceiling_is_refused_before_any_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _ctx(treasury_sol_target=Decimal("1.0"))  # cap is 0.72 - 0.02 = 0.70
    _fake_db(monkeypatch, ctx)
    await treasury.treasury_once(cast(ExecutorContext, ctx))
    assert ctx.state.treasury_last_attempt_reason == "target_above_wallet_max"
    assert ctx.treasury_client.calls == [], "no quote for a target the gate could never accept"
    assert ctx.chain.calls == [], "not even the USDC balance was read"


async def test_the_size_is_capped_by_the_effective_target_not_the_configured_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # wallet 0.68, target 0.70 (== cap): needs 0.02 SOL ≈ 2.11 USDC at 9.4876e-3 SOL/USDC
    ctx = _ctx(treasury_sol_target=Decimal("0.70"))
    _fake_db(monkeypatch, ctx)
    ctx.treasury_client.quotes[21_330_000] = _quote(21_330_000, 202_360_000)
    sent: list[int] = []

    async def fake_attempt(_ctx: Any, *, usdc_atoms: int, quote: Any, wallet_sol: Decimal) -> None:
        sent.append(usdc_atoms)

    monkeypatch.setattr(treasury, "attempt_swap", fake_attempt)
    ctx.treasury_client.quotes[2_108_125] = _quote(2_108_125, 20_000_000)
    await treasury.treasury_once(cast(ExecutorContext, ctx))
    assert sent == [2_108_125]
    assert ctx.treasury_client.calls == [21_330_000, 2_108_125]


# ------------------------------------------------------------------ fix B
async def test_a_quote_for_another_amount_is_refused_before_the_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _ctx(treasury_sol_target=Decimal("0.70"))
    _fake_db(monkeypatch, ctx)
    # Jupiter answers the 21.33 USDC ask with a quote for the whole 2 133 USDC
    ctx.treasury_client.quotes[21_330_000] = _quote(2_133_000_000, 20_236_000_000)
    called = False

    async def fake_attempt(*_a: Any, **_k: Any) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(treasury, "attempt_swap", fake_attempt)
    await treasury.treasury_once(cast(ExecutorContext, ctx))
    assert ctx.state.treasury_last_attempt_reason == "quote_mismatch:in_amount"
    assert called is False


# ------------------------------------------------------------------ fix C
def _submitted(age_s: float, sol_before: str = "0.68") -> SubmittedSwap:
    return SubmittedSwap(
        id=uuid.uuid4(),
        signature="9" * 88,
        requested_at=datetime.now(UTC) - timedelta(seconds=age_s),
        wallet_sol_before=Decimal(sol_before),
    )


def _tx(sol_delta: int, *, payer: str = PUBKEY) -> dict[str, Any]:
    """T4.84 — a ``getTransaction`` answer whose ``meta`` says what **this
    signature** did to the fee payer's lamports; never the wallet's live
    balance, which the spot lane moves between the send and the reconcile."""
    pre = 680_000_000
    return {
        "meta": {
            "err": None,
            "fee": 5_000,
            "preBalances": [pre, 1],
            "postBalances": [pre + sol_delta, 1],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
        "transaction": {"message": {"accountKeys": [payer, "11111111111111111111111111111111"]}},
        "blockTime": 1_758_000_000,
    }


Outcome = tuple[str, Decimal | None, Decimal | None]


def _wire_reconcile(
    monkeypatch: pytest.MonkeyPatch, ctx: FakeContext, row: SubmittedSwap
) -> list[Outcome]:
    outcomes: list[Outcome] = []

    async def submitted_swaps(_session: Any) -> list[SubmittedSwap]:
        return [row]

    async def mark_confirmed(
        _session: Any, swap_id: uuid.UUID, *, sol_out_filled: Decimal, wallet_sol_after: Decimal
    ) -> None:
        assert swap_id == row.id
        outcomes.append(("confirmed", sol_out_filled, wallet_sol_after))

    async def mark_failed(_session: Any, swap_id: uuid.UUID) -> None:
        assert swap_id == row.id
        outcomes.append(("failed", None, None))

    monkeypatch.setattr(treasury_reconcile.treasury_db, "submitted_swaps", submitted_swaps)
    monkeypatch.setattr(treasury_reconcile.treasury_db, "mark_confirmed", mark_confirmed)
    monkeypatch.setattr(treasury_reconcile.treasury_db, "mark_failed", mark_failed)
    return outcomes


@pytest.mark.parametrize(
    "status,age_s,expected",
    [
        ({"confirmationStatus": "finalized", "err": None}, 45.0, "confirmed"),
        ({"confirmationStatus": "processed", "err": None}, 45.0, "pending"),
        (
            {"confirmationStatus": "confirmed", "err": {"InstructionError": [3, "Custom"]}},
            45,
            "failed",
        ),
        (None, 45.0, "pending"),
        (None, 200.0, "failed"),
    ],
)
async def test_the_reconcile_settles_a_submitted_row_from_the_chain(
    monkeypatch: pytest.MonkeyPatch, status: dict[str, Any] | None, age_s: float, expected: str
) -> None:
    ctx = _ctx()
    _fake_db(monkeypatch, ctx)
    row = _submitted(age_s)
    ctx.chain.rpc.statuses = [status]
    ctx.chain.rpc.tx = _tx(9_400_000)
    outcomes = _wire_reconcile(monkeypatch, ctx, row)
    await treasury_reconcile.reconcile_once(cast(ExecutorContext, ctx))
    if expected == "pending":
        assert outcomes == []
    elif expected == "failed":
        assert outcomes == [("failed", None, None)]
    else:
        assert outcomes == [("confirmed", Decimal("0.0094"), Decimal("0.6894"))]
        assert ctx.state.treasury_last_swap_at is not None


async def test_the_fill_comes_from_this_signature_not_from_the_live_wallet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wallet is shared with the spot lane: a live re-read would book
    someone else's SOL (or someone else's spend) as this swap's fill, and that
    number feeds the daily-loss brake (§16.3)."""
    ctx = _ctx()
    _fake_db(monkeypatch, ctx)
    row = _submitted(45.0)
    ctx.chain.rpc.statuses = [{"confirmationStatus": "finalized", "err": None}]
    ctx.chain.rpc.tx = _tx(9_400_000)
    ctx.chain.lamports = 120_000_000  # the spot lane spent meanwhile
    outcomes = _wire_reconcile(monkeypatch, ctx, row)
    await treasury_reconcile.reconcile_once(cast(ExecutorContext, ctx))
    assert outcomes == [("confirmed", Decimal("0.0094"), Decimal("0.6894"))]
    assert "wallet" not in ctx.chain.calls


@pytest.mark.parametrize("failure", ["not_served", "rpc_error"], ids=["not-served", "rpc-error"])
async def test_a_landed_swap_whose_meta_is_unreadable_stays_submitted(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Confirmed by status but not yet served (or the RPC failed): the row is
    left ``submitted`` for the next tick — never a fill of zero, never
    ``failed``, and it keeps counting against the daily cap."""
    ctx = _ctx()
    _fake_db(monkeypatch, ctx)
    row = _submitted(45.0)
    ctx.chain.rpc.statuses = [{"confirmationStatus": "finalized", "err": None}]
    if failure == "rpc_error":
        ctx.chain.rpc.tx_error = TimeoutError("rpc down")
    outcomes = _wire_reconcile(monkeypatch, ctx, row)
    await treasury_reconcile.reconcile_once(cast(ExecutorContext, ctx))
    assert outcomes == []
    assert ctx.state.rpc_errors == (1 if failure == "rpc_error" else 0)


@pytest.mark.parametrize("answer", [[], [None, None]], ids=["short", "long"])
async def test_an_answer_that_does_not_match_the_signatures_condemns_nobody(
    monkeypatch: pytest.MonkeyPatch, answer: list[dict[str, Any] | None]
) -> None:
    """Astra, review of this diff: an RPC that answers fewer entries than
    signatures asked about says **nothing** about the ones it left out. Padding
    them with ``None`` made a row older than 180 s ``failed`` on no evidence —
    and a swap that really landed would then leave the daily cap and the
    inflow. An explicit ``null`` is still evidence (test above); a missing
    entry is not."""
    ctx = _ctx()
    _fake_db(monkeypatch, ctx)
    row = _submitted(200.0)
    ctx.chain.rpc.statuses = answer
    outcomes = _wire_reconcile(monkeypatch, ctx, row)
    await treasury_reconcile.reconcile_once(cast(ExecutorContext, ctx))
    assert outcomes == []
    assert ctx.state.rpc_errors == 1


async def test_a_landed_swap_that_took_sol_away_is_left_for_a_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A USDC -> SOL swap cannot land with the wallet poorer: booking it as a
    fill of zero would understate the treasury inflow the daily-loss brake
    subtracts. The row stays ``submitted`` (counted at its quoted size)."""
    ctx = _ctx()
    _fake_db(monkeypatch, ctx)
    row = _submitted(45.0)
    ctx.chain.rpc.statuses = [{"confirmationStatus": "finalized", "err": None}]
    ctx.chain.rpc.tx = _tx(-5_000)
    outcomes = _wire_reconcile(monkeypatch, ctx, row)
    await treasury_reconcile.reconcile_once(cast(ExecutorContext, ctx))
    assert outcomes == []


@pytest.mark.parametrize(
    ("status", "age_s", "reason"),
    [
        (None, 200.0, "failed:blockhash_expired_never_landed"),
        (
            {"confirmationStatus": "confirmed", "err": {"InstructionError": [3, "Custom"]}},
            45.0,
            "failed:on_chain_error",
        ),
    ],
    ids=["expired", "on-chain-error"],
)
async def test_a_reconciled_failure_says_which_failure_it_was(
    monkeypatch: pytest.MonkeyPatch, status: dict[str, Any] | None, age_s: float, reason: str
) -> None:
    """A swap that never landed and a swap the chain rejected are different
    accidents, and the log of the reconcile names which one it settled (the
    tick's own last-attempt field is rewritten a few lines later, by design —
    ``treasury._tick`` always ends with its own reason)."""
    ctx = _ctx()
    _fake_db(monkeypatch, ctx)
    row = _submitted(age_s)
    ctx.chain.rpc.statuses = [status]
    outcomes = _wire_reconcile(monkeypatch, ctx, row)
    with capture_logs() as logs:
        await treasury_reconcile.reconcile_once(cast(ExecutorContext, ctx))
    assert outcomes == [("failed", None, None)]
    settled = [entry for entry in logs if entry["event"] == "meme_treasury_reconciled"]
    assert [(entry["state"], entry["reason"]) for entry in settled] == [("failed", reason)]


# --------------------------------------------------- simulated balances
def test_simulated_balances_reads_the_json_parsed_pair() -> None:
    wallet = {"lamports": 689_380_000, "owner": "11111111111111111111111111111111"}
    usdc = {
        "lamports": 2_039_280,
        "data": {
            "parsed": {"info": {"tokenAmount": {"amount": "20330000"}}},
            "program": "spl-token",
        },
    }
    assert simulated_balances([wallet, usdc]) == (689_380_000, 20_330_000)


@pytest.mark.parametrize(
    "accounts",
    [
        [],
        [None, None],
        [{"lamports": 1}, None],
        [{"lamports": 1}, {"data": ["", "base64"]}],
        [{"lamports": 1}, {"data": {"parsed": {"info": {}}}}],
    ],
)
def test_simulated_balances_refuses_anything_it_cannot_read(accounts: list[Any]) -> None:
    assert simulated_balances(accounts) is None
