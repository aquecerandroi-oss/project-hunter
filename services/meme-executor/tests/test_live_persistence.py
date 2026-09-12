"""The executor against a real Postgres at ``head`` (``0028_meme_live``) — one container,
no network: the chain is a fake fed by T4.8's recorded mainnet fixtures.

Proved here and nowhere else: a live approval becomes an admitted order, a
signature recorded **before** the send, a confirmed fill and an open position;
a second pass writes nothing (idempotent on the proposal); a redelivered stream
event finds its row (idempotent on the signature); a restarted process rebuilds
the position and sells it on ``sell_now``; an approval older than the TTL is
refused ``approval_expired`` and never sent; the kill switch read from Redis
blocks entries and the daily latch persists across readers; the grants as the
roles; two sessions never sign the same key (VM8/VM9's Postgres halves).
"""

from __future__ import annotations

import asyncio
import json
import random
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from hunter_core.db.session import role_session
from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.base58 import b58encode
from hunter_core.execution.meme.gates import MemeExecutionMode
from hunter_core.execution.meme.journal import SigningLocked
from hunter_core.execution.meme.signer import ENV_SECRET_KEY, MemeSigner
from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_meme_executor.build import decode_fills
from hunter_meme_executor.chain import ChainReader, CurveRead, TokenAccountRead, WalletRead
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.exits import exits_once
from hunter_meme_executor.journal_db import PostgresOrderJournal
from hunter_meme_executor.kill_switch import KillSwitchReader
from hunter_meme_executor.repo import TokenContext, open_positions
from hunter_risk_meme import limits_from_env

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
OPERATOR_RULE_SET = "01994d00-6c1a-7000-8000-000000000002"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
POLICY = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.02",
    "MEME_DAILY_LOSS_CAP_SOL": "0.1",
    "MEME_MAX_OPEN_POSITIONS": "3",
    "MEME_COOLDOWN_S": "3600",
}


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class _Sim:
    ok = True
    err: Any = None


@dataclass
class FakeRpc:
    """Scripted RPC: simulate ok, send returns the signature, confirmed on first poll."""

    allow_send: bool = True
    sent: list[bytes] = field(default_factory=lambda: list[bytes]())
    transaction: dict[str, Any] = field(
        default_factory=lambda: _fixture("rpc_tx_buy_raw.json")["result"]
    )

    def simulate_transaction(self, transaction: bytes, **_: Any) -> _Sim:
        return _Sim()

    def send_transaction(self, transaction: bytes, *, max_retries: int = 0) -> str:
        self.sent.append(transaction)
        return b58encode(transaction[1:65])

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        return [{"confirmationStatus": "confirmed", "err": None} for _ in signatures]

    def get_transaction(self, signature: str, **_: Any) -> dict[str, Any] | None:
        tx = json.loads(json.dumps(self.transaction))
        tx["transaction"]["signatures"] = [signature]
        return tx

    def get_block_height(self, **_: Any) -> int:
        return 100

    def close(self) -> None:
        return None


class FakeChain(ChainReader):
    def __init__(self, rpc: FakeRpc, mint: str, creator: str) -> None:
        self._fake_rpc = rpc
        self._mint = mint
        self._creator = creator
        g = _fixture("rpc_global_account_raw.json")["result"]["value"]
        self._global_account_decoded = decode_global_account(g["data"][0], owner=g["owner"])
        self.lamports = 300_000_000
        self.tokens_on_chain = 0
        self.complete = False

    @property
    def rpc(self) -> Any:  # type: ignore[override]
        return self._fake_rpc

    def global_account(self) -> Any:
        return self._global_account_decoded

    def curve(self, mint: str) -> CurveRead | None:
        account = BondingCurveAccount(
            virtual_token_reserves=900_000_000_000_000,
            virtual_sol_reserves=36_400_000_000,
            real_token_reserves=793_100_000_000_000 * 8 // 10,
            real_sol_reserves=6_400_000_000,
            token_total_supply=1_000_000_000_000_000,
            complete=self.complete,
            creator=self._creator,
            is_mayhem_mode=False,
            is_cashback_coin=False,
            quote_mint="11111111111111111111111111111111",
        )
        return CurveRead(mint, account, TOKEN_2022, 1, datetime.now(UTC))

    def wallet(self, pubkey: str) -> WalletRead:
        return WalletRead(pubkey, self.lamports, 1, datetime.now(UTC))

    def token_account(self, owner: str, mint: str, token_program: str) -> TokenAccountRead:
        return TokenAccountRead(exists=self.tokens_on_chain > 0, amount=self.tokens_on_chain)

    def blockhash(self) -> tuple[str, int]:
        return "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ", 150


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)


def _signer() -> MemeSigner:
    seed = random.Random(20260914).randbytes(32)
    pub = (
        Ed25519PrivateKey.from_private_bytes(seed)
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    return MemeSigner.from_environment({ENV_SECRET_KEY: b58encode(seed + pub)})


MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
CREATOR = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"


def _full_token_context(now: datetime) -> TokenContext:
    return TokenContext(
        created_at=now - timedelta(seconds=120),
        creator=CREATOR,
        initial_real_token_reserves=793_100_000_000_000,
        completed_at=None,
        migrated_at=None,
        curve_volume_1m_sol=Decimal("20"),
        features_end_time=now - timedelta(seconds=30),
        creator_sold=False,
        top10_share=Decimal("0.15"),
        bundled_share=Decimal("0.05"),
    )


@dataclass
class Harness:
    ctx: ExecutorContext
    rpc: FakeRpc
    chain: FakeChain
    redis: FakeRedis


def _context(
    session_factory: async_sessionmaker[AsyncSession],
    signer: MemeSigner,
    redis: FakeRedis,
    *,
    live: bool = True,
) -> Harness:
    rpc = FakeRpc()
    chain = FakeChain(rpc, MINT, CREATOR)
    config = ExecutorConfig(
        live=live,
        cluster="devnet",
        rpc_url="https://fake",
        limits=limits_from_env(POLICY),
        system_kill_switch=KillSwitchState.ACTIVE,
        kill_file=None,
    )
    loop = asyncio.get_running_loop()
    written: list[dict[str, str]] = []

    async def heartbeat(mapping: dict[str, str]) -> None:
        written.append(mapping)

    ctx = ExecutorContext(
        config=config,
        mode=MemeExecutionMode(live=live, gates=None),
        signer=signer,
        session_factory=session_factory,
        chain=chain,
        journal=PostgresOrderJournal(session_factory, loop),
        kill=KillSwitchReader(
            redis=cast(Any, redis),
            session_factory=session_factory,
            system=KillSwitchState.ACTIVE,
            kill_file=None,
        ),  # type: ignore[arg-type]
        heartbeat=heartbeat,
        loop=loop,
    )
    return Harness(ctx, rpc, chain, redis)


async def _plant_proposal(
    engine: AsyncEngine, *, decided_at: datetime, size_sol: str = "0.01"
) -> str:
    proposal_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at, created_at, "
                "  creator, initial_real_token_reserves, progress_denominator_source, total_supply) "
                "VALUES (:mint, 'pumpportal_ws', :t, :t, :t, :creator, 793100000, 'observed_virgin', 1000000000) "
                "ON CONFLICT (mint) DO NOTHING"
            ),
            {"mint": MINT, "t": decided_at - timedelta(seconds=120), "creator": CREATOR},
        )
        await connection.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, expires_at, "
                "  quote, reasons, suggested, decision, decided_by, decided_at, mode) "
                "VALUES (:id, :mint, :rs, 'operator', 'approved', :proposed, :expires, '{}', "
                "  '[\"operator_manual\"]', '{}', CAST(:decision AS jsonb), 'user_x', :decided, 'live')"
            ),
            {
                "id": proposal_id,
                "mint": MINT,
                "rs": OPERATOR_RULE_SET,
                "proposed": decided_at - timedelta(seconds=1),
                "expires": decided_at + timedelta(seconds=120),
                "decision": json.dumps(
                    {"size_sol": size_sol, "target_x": "2", "trailing_pct": "30", "max_hold_s": 900}
                ),
                "decided": decided_at,
            },
        )
    return proposal_id


async def _rows(engine: AsyncEngine, sql: str, **params: Any) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        return [dict(r) for r in (await connection.execute(text(sql), params)).mappings()]


@pytest_asyncio.fixture
async def harness(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Harness]:
    import hunter_meme_executor.entries as entries_module
    import hunter_meme_executor.exits as exits_module

    async def token_context(_session: AsyncSession, _mint: str) -> TokenContext:
        return _full_token_context(datetime.now(UTC))

    monkeypatch.setattr(entries_module, "token_context", token_context)
    monkeypatch.setattr(exits_module, "token_context", token_context)
    # Each test starts from an empty ledger and an unlatched switch (owner writes):
    # an unmarked open position left by another test would refuse ``marks_incomplete``
    # — the engine doing its job, not the scenario under test.
    async with db_engine.begin() as connection:
        await connection.execute(text("DELETE FROM meme_live_positions"))
        await connection.execute(text("DELETE FROM meme_live_orders"))
        await connection.execute(text("DELETE FROM meme_proposals WHERE mode = 'live'"))
        await connection.execute(
            text(
                "UPDATE meme_live_kill_switch SET state = 'ACTIVE', reason = NULL, latched_at = NULL, "
                "released_at = NULL, released_by = NULL WHERE scope = 'wallet'"
            )
        )
    redis = FakeRedis()
    yield _context(db_session_factory, _signer(), redis)


async def test_a_live_approval_becomes_a_confirmed_order_and_an_open_position(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    orders = await _rows(
        db_engine, "SELECT * FROM meme_live_orders WHERE proposal_id = :p", p=proposal_id
    )
    assert len(orders) == 1 and orders[0]["status"] == "confirmed", orders
    assert orders[0]["client_order_id"] == f"meme:{proposal_id}"
    assert orders[0]["tx_signature"] and orders[0]["signatures"] == [orders[0]["tx_signature"]]
    assert orders[0]["admission"]["approved"] is True
    assert orders[0]["admission"]["sizing"]["binding_constraint"] == "requested"
    assert orders[0]["fill"]["token_amount"] > 0
    assert orders[0]["signing_at"] is None, "the signing lock is released after the attempt"
    assert len(harness.rpc.sent) == 1
    positions = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert len(positions) == 1 and positions[0]["status"] == "open"
    assert positions[0]["tokens"] == orders[0]["fill"]["token_amount"]
    assert Decimal(positions[0]["initial_risk_sol"]) == Decimal(
        positions[0]["sol_spent_lamports"]
    ) / Decimal(10**9)

    # Idempotent on the proposal: a second pass writes nothing and sends nothing.
    await entries_once(harness.ctx)
    assert (
        len(
            await _rows(
                db_engine, "SELECT id FROM meme_live_orders WHERE proposal_id = :p", p=proposal_id
            )
        )
        == 1
    )
    assert len(harness.rpc.sent) == 1

    # Idempotent on the signature: a redelivered stream event finds the row, creates nothing.
    from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy

    submitter = MemeSubmitter(
        rpc=harness.rpc,
        signer=None,
        journal=harness.ctx.journal,
        verify=lambda _r: None,
        decode_fill=decode_fills,
        policy=SubmitPolicy(allow_send=False, cluster="devnet"),
        now=lambda: datetime.now(UTC),
    )
    replay = await asyncio.to_thread(
        submitter.on_stream_event,
        orders[0]["tx_signature"],
        harness.rpc.get_transaction(orders[0]["tx_signature"]) or {},
    )
    assert replay is not None and replay.replayed
    assert len(await _rows(db_engine, "SELECT id FROM meme_live_orders")) >= 1
    assert (
        await _rows(
            db_engine,
            "SELECT count(*) AS n FROM meme_live_orders WHERE tx_signature = :s",
            s=orders[0]["tx_signature"],
        )
    )[0]["n"] == 1


async def test_a_restarted_executor_rebuilds_the_position_and_sells_it_on_sell_now(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET sell_requested_at = now(), sell_requested_by = 'everton' WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    # "Restart": a fresh context over the same rows, with the chain holding the tokens.
    restarted = _context(db_session_factory, _signer(), harness.redis)
    restarted.chain.tokens_on_chain = 10**9
    sell_tx = json.loads(json.dumps(_fixture("rpc_tx_probe_raw.json")["result"]))
    restarted.rpc.transaction = sell_tx
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rebuilt = await open_positions(session)
    assert [p.proposal_id for p in rebuilt if p.proposal_id == proposal_id]
    await exits_once(restarted.ctx)
    sells = await _rows(
        db_engine,
        "SELECT * FROM meme_live_orders WHERE proposal_id = :p AND side = 'sell'",
        p=proposal_id,
    )
    assert len(sells) == 1 and sells[0]["status"] == "confirmed", sells
    assert sells[0]["client_order_id"] == f"meme:{proposal_id}:exit:1"
    closed = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert closed[0]["status"] == "closed" and closed[0]["exit"]["reason"] == "sell_now"
    assert closed[0]["pnl_sol"] is not None and closed[0]["r_multiple"] is not None
    assert len(restarted.rpc.sent) == 1


async def test_an_approval_older_than_the_ttl_is_refused_and_never_sent(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    proposal_id = await _plant_proposal(
        db_engine, decided_at=datetime.now(UTC) - timedelta(seconds=60)
    )
    await entries_once(harness.ctx)
    orders = await _rows(
        db_engine,
        "SELECT status, reason FROM meme_live_orders WHERE proposal_id = :p",
        p=proposal_id,
    )
    assert orders == [{"status": "refused", "reason": "approval_expired"}]
    assert harness.rpc.sent == []


async def test_a_program_upgrade_detected_at_runtime_refuses_every_entry_by_name(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    """T4.8b: once the deploy slot moved, the approval is refused ``program_upgraded``
    before any chain read, nothing built, nothing signed, nothing sent."""
    harness.ctx.state.program_divergence = "last_deploy_slot 1 != 446462760 (programa mudou)"
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    orders = await _rows(
        db_engine,
        "SELECT status, reason, admission FROM meme_live_orders WHERE proposal_id = :p",
        p=proposal_id,
    )
    assert len(orders) == 1 and orders[0]["status"] == "refused"
    assert orders[0]["reason"] == "program_upgraded"
    assert "programa mudou" in orders[0]["admission"]["detail"]
    assert harness.rpc.sent == []


async def test_the_kill_switch_from_redis_blocks_and_the_daily_latch_persists(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    harness.redis.values["meme:kill"] = "TRADING_DISABLED"
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    orders = await _rows(
        db_engine,
        "SELECT status, reason, admission FROM meme_live_orders WHERE proposal_id = :p",
        p=proposal_id,
    )
    assert orders[0]["status"] == "refused" and orders[0]["reason"] == "kill_switch_blocked"
    assert len(orders[0]["admission"]["checks"]) == 25, (
        "every check recorded after the first refusal"
    )
    assert harness.rpc.sent == []
    assert await harness.ctx.kill.latch("daily_loss_cap_reached")
    fresh = KillSwitchReader(
        redis=cast(Any, FakeRedis()),
        session_factory=db_session_factory,
        system=KillSwitchState.ACTIVE,
        kill_file=None,
    )  # type: ignore[arg-type]
    await fresh.refresh()
    assert fresh.latched and fresh.effective is KillSwitchState.TRADING_DISABLED
    assert fresh.inputs().daily_loss_latched


async def test_the_app_role_may_ask_for_a_sale_and_nothing_else(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    async with db_engine.connect() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_app"))
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET sell_requested_at = now(), sell_requested_by = 'u' WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
        with pytest.raises(ProgrammingError, match="permission denied"):
            await connection.execute(
                text("UPDATE meme_live_positions SET status = 'closed' WHERE proposal_id = :p"),
                {"p": proposal_id},
            )
        await connection.rollback()
    async with db_engine.connect() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_app"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            await connection.execute(
                text("UPDATE meme_live_orders SET status = 'failed' WHERE proposal_id = :p"),
                {"p": proposal_id},
            )
        await connection.rollback()
    async with db_engine.connect() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_app"))
        await connection.execute(
            text("UPDATE meme_proposals SET mode = 'paper' WHERE id = :p"), {"p": proposal_id}
        )
        await connection.rollback()


async def test_two_sessions_never_sign_the_same_key(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    key = f"meme:{proposal_id}"
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, status, admitted_at) "
                "VALUES (:id, :p, 'buy', :k, 'admitted', now())"
            ),
            {"id": str(uuid4()), "p": proposal_id, "k": key},
        )
    journal = harness.ctx.journal
    outcomes: list[str] = []
    gate = threading.Barrier(2)

    def session() -> None:
        gate.wait(5)
        try:
            journal.begin_signing(key)
            outcomes.append("locked")
        except SigningLocked:
            outcomes.append("refused")

    await asyncio.gather(asyncio.to_thread(session), asyncio.to_thread(session))
    assert sorted(outcomes) == ["locked", "refused"]
    await asyncio.to_thread(journal.release_signing, key)
    row = await _rows(
        db_engine, "SELECT signing_at FROM meme_live_orders WHERE client_order_id = :k", k=key
    )
    assert row[0]["signing_at"] is None


async def test_a_kill_switch_that_moves_between_admission_and_signing_refuses_and_sends_nothing(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    """§7/§9.5 — an approval is not a safe-conduct: the switch is re-read after the
    admitted row exists and before the key is touched; a switch that moved in
    between leaves ``refused:kill_switch_blocked_before_signing`` and no send."""
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    reads = {"n": 0}
    original = harness.redis.get

    async def flipping(key: str) -> str | None:
        reads["n"] += 1
        # 1st read: the top of the pass (ACTIVE); 2nd: the re-read before signing.
        return "TRADING_DISABLED" if reads["n"] >= 2 else await original(key)

    harness.redis.get = flipping  # type: ignore[method-assign]
    await entries_once(harness.ctx)
    orders = await _rows(
        db_engine,
        "SELECT status, reason, admission, signatures FROM meme_live_orders WHERE proposal_id = :p",
        p=proposal_id,
    )
    assert len(orders) == 1
    assert orders[0]["status"] == "refused"
    assert orders[0]["reason"] == "kill_switch_blocked_before_signing"
    assert orders[0]["admission"]["approved"] is True, "admitted first, refused by the re-read"
    assert orders[0]["signatures"] == []
    assert harness.rpc.sent == []
    assert reads["n"] == 2


async def test_the_daily_latch_can_bite_again_after_the_owner_released_it(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The owner's manual release (``docs/DEPLOYMENT.md`` section 3.7) leaves ``latched_at``
    set and ``released_at`` filled; the next day's cap must still latch — a release is
    not a permanent exemption."""
    assert await harness.ctx.kill.latch("daily_loss_cap_reached")
    assert not await harness.ctx.kill.latch("daily_loss_cap_reached"), "idempotent while latched"
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_kill_switch SET state = 'ACTIVE', released_at = now(), "
                "released_by = 'everton', reason = NULL WHERE scope = 'wallet'"
            )
        )
    fresh = KillSwitchReader(
        redis=cast(Any, FakeRedis()),
        session_factory=db_session_factory,
        system=KillSwitchState.ACTIVE,
        kill_file=None,
    )  # type: ignore[arg-type]
    await fresh.refresh()
    assert not fresh.latched and fresh.effective is KillSwitchState.ACTIVE
    assert await fresh.latch("daily_loss_cap_reached"), "latchable again after the release"
    await fresh.refresh()
    assert fresh.latched and fresh.effective is KillSwitchState.TRADING_DISABLED
    row = await _rows(
        db_engine,
        "SELECT released_at, released_by FROM meme_live_kill_switch WHERE scope = 'wallet'",
    )
    assert row[0]["released_at"] is None and row[0]["released_by"] is None
