"""T4.74-4 — the fakes of the ``spot/1`` money path (no network, no key, no
Postgres), shared by ``test_spot_money_path.py`` and ``test_spot_entries.py``:
a chain, an RPC, a Jupiter, a kill switch, a signer and a repository that
record the order of what happened (``FakeChain``/``FakeRpc``/``FakeJupiter``/
``FakeKill``/``FakeSigner`` in the shape of ``test_treasury_tick.py``). The
transaction bytes come from ``spot_tx_fixtures.py``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_exchanges.jupiter import JupiterQuote, JupiterSwapTransaction
from hunter_exchanges.jupiter.versioned_tx import VersionedMessage
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_exchanges.pumpfun.tx_rpc import SimulationResult
from hunter_meme_executor import spot_send
from hunter_meme_executor.chain import TokenAccountRead, WalletRead
from hunter_meme_executor.context import ExecutorState
from hunter_meme_executor.spot_alt import ALT_PROGRAM_ID
from hunter_meme_executor.treasury_rules import JUP_PROGRAM_ID

from .spot_tx_fixtures import (
    ATA_RENT,
    ORDER,
    OUT,
    SIG_BYTES,
    SIGNATURE,
    TICKET,
    WALLET,
    WIF,
    WSOL,
    as_swap,
    buy_message,
    quote,
)


# ---------------------------------------------------------------------------- fakes
def accounts_after(lamports: int, atoms: int) -> tuple[dict[str, Any], ...]:
    token = {"data": {"parsed": {"info": {"tokenAmount": {"amount": str(atoms)}}}}}
    return ({"lamports": lamports}, token)


def simulation(accounts: tuple[Any, ...] | None, *, ok: bool = True) -> SimulationResult:
    return SimulationResult(
        ok=ok,
        err=None if ok else {"InstructionError": [3, "Custom"]},
        logs=(),
        units_consumed=90_000,
        slot=1,
        return_data=None,
        accounts=() if accounts is None else accounts,
    )


@dataclass
class FakeRpc:
    log: list[str]
    simulation: SimulationResult
    statuses: list[dict[str, Any] | None] = field(default_factory=lambda: [_confirmed()])
    send_error: Exception | None = None
    simulate_error: Exception | None = None
    sent: list[bytes] = field(default_factory=lambda: list[bytes]())
    simulated_accounts: tuple[str, ...] | None = None
    status_calls: int = 0
    transaction: dict[str, Any] | None = None
    """What ``getTransaction`` serves for ``SIGNATURE``; ``None`` = not indexed yet."""
    transaction_error: Exception | None = None
    block_height: int = 0
    """T4.74-5: what ``getBlockHeight`` answers the reconcile."""
    lookup_tables: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    """T4.81: ``table address -> base64 account data`` for ``getMultipleAccounts``."""
    lookup_table_owner: str = ALT_PROGRAM_ID
    call_error: Exception | None = None

    def call(self, method: str, params: list[Any]) -> Any:
        """The read-only JSON-RPC door — only the lookup-table read uses it."""
        assert method == "getMultipleAccounts"
        self.log.append("get_multiple_accounts")
        if self.call_error is not None:
            raise self.call_error
        value = [
            None
            if address not in self.lookup_tables
            else {
                "data": [self.lookup_tables[address], "base64"],
                "owner": self.lookup_table_owner,
                "lamports": 1_000_000,
                "executable": False,
            }
            for address in params[0]
        ]
        return {"context": {"slot": 1}, "value": value}

    def get_block_height(self, *, commitment: str = "confirmed") -> int:
        self.log.append("get_block_height")
        return self.block_height

    def get_transaction(self, signature: str, *, commitment: str = "confirmed") -> Any:
        assert signature == SIGNATURE
        self.log.append("get_transaction")
        if self.transaction_error is not None:
            raise self.transaction_error
        return self.transaction

    def simulate_transaction(
        self, raw: bytes, *, sig_verify: bool = False, accounts: tuple[str, ...] = ()
    ) -> SimulationResult:
        self.log.append("simulate")
        self.simulated_accounts = tuple(accounts)
        if self.simulate_error is not None:
            raise self.simulate_error
        return self.simulation

    def send_transaction(self, tx: bytes, *, max_retries: int = 0) -> str:
        self.log.append("send")
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(tx)
        return SIGNATURE

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        assert signatures == [SIGNATURE]
        self.status_calls += 1
        return [self.statuses[min(self.status_calls - 1, len(self.statuses) - 1)]]


def _confirmed() -> dict[str, Any]:
    return {"confirmationStatus": "confirmed", "err": None}


def tx_meta(
    *,
    wallet_pre: int,
    wallet_post: int,
    token_pre: int | None,
    token_post: int | None,
    mint: str = WIF,
    fee: int = 5_000,
    err: Any = None,
    payer: str = WALLET,
) -> dict[str, Any]:
    """A ``getTransaction`` (``encoding=json``) result: the fee payer first in
    ``accountKeys``; a token account absent from ``preTokenBalances`` and present
    in ``postTokenBalances`` is one the transaction created."""

    def entry(amount: int) -> dict[str, Any]:
        return {
            "accountIndex": 4,
            "mint": mint,
            "owner": WALLET,
            "uiTokenAmount": {"amount": str(amount), "decimals": 6},
        }

    return {
        "slot": 1,
        "transaction": {"message": {"accountKeys": [payer, JUP_PROGRAM_ID], "instructions": []}},
        "meta": {
            "err": err,
            "fee": fee,
            "preBalances": [wallet_pre, 0],
            "postBalances": [wallet_post, 0],
            "preTokenBalances": [] if token_pre is None else [entry(token_pre)],
            "postTokenBalances": [] if token_post is None else [entry(token_post)],
        },
    }


@dataclass
class FakeChain:
    rpc: FakeRpc
    lamports: int
    token: TokenAccountRead
    reads: int = 0
    lamports_after_first_read: int | None = None
    """What the wallet shows from the second read on (an inflow that landed meanwhile)."""

    def wallet(self, pubkey: str) -> WalletRead:
        self.reads += 1
        read = WalletRead(pubkey, self.lamports, 1, datetime.now(UTC))
        if self.lamports_after_first_read is not None:
            self.lamports = self.lamports_after_first_read
        return read

    def token_account(self, owner: str, mint: str, token_program: str) -> TokenAccountRead:
        assert mint == WIF and token_program == TOKEN_PROGRAM_ID
        return self.token


@dataclass
class FakeJupiter:
    quote_reply: JupiterQuote
    swap_reply: JupiterSwapTransaction
    swap_calls: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    quote_calls: int = 0

    def quote(self, **kwargs: Any) -> JupiterQuote:
        self.quote_calls += 1
        return self.quote_reply

    def swap(self, **kwargs: Any) -> JupiterSwapTransaction:
        self.swap_calls.append(kwargs)
        return self.swap_reply


@dataclass
class FakeKill:
    effective: KillSwitchState = KillSwitchState.ACTIVE
    flip_on_refresh: KillSwitchState | None = None
    refreshes: int = 0

    @property
    def blocks_entries(self) -> bool:
        return self.effective in (KillSwitchState.TRADING_DISABLED, KillSwitchState.EMERGENCY)

    async def refresh(self) -> None:
        self.refreshes += 1
        if self.flip_on_refresh is not None:
            self.effective = self.flip_on_refresh

    def describe(self) -> dict[str, str]:
        return {"kill_switch": self.effective.value}


@dataclass
class FakeSigner:
    log: list[str]
    pubkey: str = WALLET
    signed: list[bytes] = field(default_factory=lambda: list[bytes]())

    def sign(self, message: bytes) -> bytes:
        self.log.append("sign")
        self.signed.append(message)
        return SIG_BYTES


@dataclass
class FakeConfig:
    confirm_timeout_s: float = 3.0


@dataclass
class FakeContext:
    config: FakeConfig
    chain: FakeChain
    signer: FakeSigner | None
    kill: FakeKill
    treasury_client: FakeJupiter
    session_factory: Any = None
    state: ExecutorState = field(default_factory=ExecutorState)


@dataclass
class Db:
    log: list[str]
    rows: list[tuple[str, dict[str, Any]]] = field(
        default_factory=lambda: list[tuple[str, dict[str, Any]]]()
    )
    submitted_ok: bool = True
    expected_order_id: str | None = ORDER

    def statuses(self) -> list[str]:
        return [s for s, _ in self.rows]


class _Session:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


def wire_db(monkeypatch: pytest.MonkeyPatch, db: Db) -> None:
    async def mark(status: str, order_id: str, **kw: Any) -> bool:
        assert db.expected_order_id is None or order_id == db.expected_order_id
        db.log.append(status)
        db.rows.append((status, kw))
        return db.submitted_ok if status == "submitted" else True

    async def simulated(_s: Any, order_id: str, **kw: Any) -> bool:
        return await mark("simulated", order_id, **kw)

    async def submitted(_s: Any, order_id: str, **kw: Any) -> bool:
        return await mark("submitted", order_id, **kw)

    async def confirmed(_s: Any, order_id: str, **kw: Any) -> bool:
        return await mark("confirmed", order_id, **kw)

    async def failed(_s: Any, order_id: str, **kw: Any) -> bool:
        return await mark("failed", order_id, **kw)

    async def refused(_s: Any, order_id: str, **kw: Any) -> bool:
        return await mark("refused", order_id, **kw)

    def session(*_a: Any, **_k: Any) -> _Session:
        return _Session()

    monkeypatch.setattr(spot_send, "role_session", session)
    monkeypatch.setattr(spot_send.spot_repo, "mark_simulated", simulated)
    monkeypatch.setattr(spot_send.spot_repo, "mark_submitted", submitted)
    monkeypatch.setattr(spot_send.spot_repo, "mark_confirmed", confirmed)
    monkeypatch.setattr(spot_send.spot_repo, "mark_failed", failed)
    monkeypatch.setattr(spot_send.spot_repo, "mark_refused", refused)
    monkeypatch.setattr(spot_send, "CONFIRM_INTERVAL_S", 0.0)


@dataclass
class Rig:
    ctx: FakeContext
    db: Db
    log: list[str]

    @property
    def signer(self) -> FakeSigner:
        assert self.ctx.signer is not None
        return self.ctx.signer


def buy_rig(
    monkeypatch: pytest.MonkeyPatch,
    *,
    message: VersionedMessage | None = None,
    sim: SimulationResult | None = None,
    token_after: int = OUT,
    wallet_after: int | None = None,
) -> Rig:
    """A SOL -> WIF buy of the ticket: the wallet before, the simulated post-state
    and the transaction's own meta (fee 5 000 + priority 50 + the WIF ATA's rent)."""
    log: list[str] = []
    before = 500_000_000
    after = before - TICKET - ATA_RENT - 5_050 if wallet_after is None else wallet_after
    rpc = FakeRpc(log, sim or simulation(accounts_after(after, OUT)))
    rpc.transaction = tx_meta(
        wallet_pre=before, wallet_post=after, token_pre=None, token_post=token_after
    )
    chain = FakeChain(rpc, before, TokenAccountRead(exists=False, amount=0))
    jupiter = FakeJupiter(
        quote(input_mint=WSOL, output_mint=WIF, amount=TICKET, out=OUT),
        as_swap(message or buy_message()),
    )
    ctx = FakeContext(FakeConfig(), chain, FakeSigner(log), FakeKill(), jupiter)
    db = Db(log)
    wire_db(monkeypatch, db)
    return Rig(ctx, db, log)


async def run_buy(rig: Rig, *, cap: int = 100_000) -> spot_send.LegResult:
    return await spot_send.spot_leg(
        cast(Any, rig.ctx),
        order_id=ORDER,
        input_mint=WSOL,
        output_mint=WIF,
        amount_atoms=TICKET,
        slippage_bps=50,
        max_priority_fee_lamports=cap,
    )
