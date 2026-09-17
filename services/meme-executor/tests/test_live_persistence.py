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
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
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
from hunter_core.execution.meme.approval import AUTO_STAGE1_DECIDED_BY
from hunter_core.execution.meme.base58 import b58encode
from hunter_core.execution.meme.gates import MemeExecutionMode, MemeGates, SmallTestAuthorization
from hunter_core.execution.meme.journal import SigningLocked
from hunter_core.execution.meme.signer import ENV_SECRET_KEY, MemeSigner
from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_exchanges.pumpfun.tx_rpc import AccountSnapshot
from hunter_exchanges.pumpswap.decode import decode_global_config, decode_pool_account
from hunter_meme_executor.auto_approve import auto_approve_once
from hunter_meme_executor.build import decode_fills
from hunter_meme_executor.chain import (
    ChainReader,
    CurveRead,
    PoolRead,
    TokenAccountRead,
    WalletRead,
)
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.exits import exits_once
from hunter_meme_executor.heartbeat import heartbeat_fields
from hunter_meme_executor.journal_db import PostgresOrderJournal
from hunter_meme_executor.kill_switch import KillSwitchReader
from hunter_meme_executor.refusal_cooldown import refusal_cooling_mints
from hunter_meme_executor.repo import RISK_SNAPSHOT_MAX_AGE_S, TokenContext, open_positions
from hunter_meme_executor.wallet_refresh import wallet_refresh_once
from hunter_risk_meme import limits_from_env

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
PUMPSWAP_FIXTURES = (
    Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpswap"
)
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

    def get_account(self, address: str, **_: Any) -> Any:
        """Only the mint-account lookup ``pumpswap_exit._sell`` makes before a
        PumpSwap sell (T4.29a) — every mint in these tests is classic SPL."""
        return AccountSnapshot(
            address=address,
            owner=TOKEN_PROGRAM_ID,
            data_base64="",
            lamports=0,
            slot=1,
            executable=False,
        )

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
        self.migrated = False
        self.pool_read: PoolRead | None = None
        self._pumpswap_config: Any = None

    @property
    def rpc(self) -> Any:  # type: ignore[override]
        return self._fake_rpc

    def global_account(self) -> Any:
        return self._global_account_decoded

    def pumpswap_global_config(self) -> Any:
        """T4.29a: fees read live, never hardcoded — fixture is a real
        ``GlobalConfig`` read on mainnet (``t429a_rpc_globalconfig_tokens_raw.json``)."""
        if self._pumpswap_config is None:
            raw = json.loads(
                (PUMPSWAP_FIXTURES / "t429a_rpc_globalconfig_tokens_raw.json").read_text(
                    encoding="utf-8"
                )
            )
            value = raw["result"]["value"][0]
            self._pumpswap_config = decode_global_config(value["data"][0], owner=value["owner"])
        return self._pumpswap_config

    def pool(self, mint: str) -> PoolRead | None:
        """``None`` unless the scenario planted one (``pumpswap_pool_not_found``
        otherwise) — real pool bytes when it did (T4.29a)."""
        return self.pool_read

    def curve(self, mint: str) -> CurveRead | None:
        if self.migrated:
            # A migrated curve is emptied; the exit loop routes on
            # ``position.migrated`` alone, never on this read (T4.29a).
            return None
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


def _full_token_context(
    now: datetime,
    *,
    creator_sold: bool | None = False,
    dev_share: Decimal | None = None,
) -> TokenContext:
    return TokenContext(
        created_at=now - timedelta(seconds=120),
        creator=CREATOR,
        initial_real_token_reserves=793_100_000,  # tokens, as meme_tokens stores it (T4.28e)
        completed_at=None,
        migrated_at=None,
        curve_volume_1m_sol=Decimal("20"),
        features_end_time=now - timedelta(seconds=30),
        creator_sold=creator_sold,
        top10_share=Decimal("0.15"),
        bundled_share=Decimal("0.05"),
        dev_share=dev_share,
        dev_share_source=None if dev_share is None else "meme_risk_snapshots",
        dev_share_observed_at=None if dev_share is None else now - timedelta(seconds=60),
    )


@dataclass
class Harness:
    ctx: ExecutorContext
    rpc: FakeRpc
    chain: FakeChain
    redis: FakeRedis


def _small_test(max_total_sol: str = "0.25", max_trades: int = 5) -> SmallTestAuthorization:
    return SmallTestAuthorization(
        authorized_by="everton",
        max_sol_per_trade=Decimal("0.05"),
        max_total_sol=Decimal(max_total_sol),
        max_trades=max_trades,
        expires_at=date(2026, 9, 18),
        decision_note="obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md",
    )


def _gates_with(small_test: SmallTestAuthorization) -> MemeGates:
    day = date(2026, 9, 12)
    return MemeGates(
        engineering_date=day,
        engineering_evidence="notes-T4.14",
        evidence_date=day,
        evidence_evidence="EXP-M1 open",
        owner_date=day,
        signed_by="everton",
        signed_at=day,
        valid_until=date(2026, 10, 12),
        small_test=small_test,
    )


def _context(
    session_factory: async_sessionmaker[AsyncSession],
    signer: MemeSigner,
    redis: FakeRedis,
    *,
    live: bool = True,
    auto: SmallTestAuthorization | None = None,
    allow_send: bool = True,
    policy: dict[str, str] | None = None,
) -> Harness:
    """``auto`` (T4.28) arms stage 1: the written scope in the gates and the flag on.
    ``policy`` is the owner's environment — T4.28h's allowance rides on it."""
    rpc = FakeRpc(allow_send=allow_send)
    chain = FakeChain(rpc, MINT, CREATOR)
    config = ExecutorConfig(
        live=live,
        cluster="devnet",
        rpc_url="https://fake",
        limits=limits_from_env(policy or POLICY),
        system_kill_switch=KillSwitchState.ACTIVE,
        kill_file=None,
        auto_approve=auto is not None,
        small_test_max_trades=None if auto is None else auto.max_trades,
        small_test_max_total_sol=None if auto is None else auto.max_total_sol,
    )
    loop = asyncio.get_running_loop()
    written: list[dict[str, str]] = []

    async def heartbeat(mapping: dict[str, str]) -> None:
        written.append(mapping)

    ctx = ExecutorContext(
        config=config,
        mode=MemeExecutionMode(live=live, gates=None if auto is None else _gates_with(auto)),
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
    engine: AsyncEngine,
    *,
    decided_at: datetime,
    size_sol: str = "0.01",
    proposed_at: datetime | None = None,
) -> str:
    proposal_id = str(uuid4())
    proposed_at = proposed_at or decided_at - timedelta(seconds=1)
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
                "proposed": proposed_at,
                "expires": decided_at + timedelta(seconds=120),
                "decision": json.dumps(
                    {"size_sol": size_sol, "target_x": "2", "trailing_pct": "30", "max_hold_s": 900}
                ),
                "decided": decided_at,
            },
        )
    return proposal_id


async def _plant_risk_snapshot(
    engine: AsyncEngine, *, observed_at: datetime, mint: str = MINT, bundled_share: str = "0.05"
) -> None:
    """The rug read (``/in-memory-coin``, ``0023``) the worker's risk reader writes.

    T4.28g made it a **precondition** of stage 1: without a measured
    ``bundled_share`` inside ``RISK_SNAPSHOT_MAX_AGE_S`` the robot no longer opens
    the proposal at all (skip ``risk_snapshot_pending``), because opening it only
    burned the row on a ``bundled_share_unmeasurable`` a minute before the answer
    landed (measured 16/09/2026: median +103 s)."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_risk_snapshots "
                "  (observed_at, mint, received_at, source, bundled_share, raw) "
                "VALUES (:t, :mint, :t, 'pumpfun_rest', :share, '{}'::jsonb) "
                "ON CONFLICT (observed_at, mint) DO NOTHING"
            ),
            {"t": observed_at, "mint": mint, "share": Decimal(bundled_share)},
        )


async def _plant_operator_proposal(
    engine: AsyncEngine,
    *,
    proposed_at: datetime,
    size_sol: str = "0.01",
    ttl_s: int = 180,
    risk_snapshot: bool = True,
) -> str:
    """What the radar's gate writes for the desk (T4.19): a ``proposed`` row under
    the **active** ``operator`` set, ``mode = 'paper'``, nobody has decided —
    together with the rug read stage 1 now waits for (``risk_snapshot=False``
    plants the proposal without it, which is T4.28g's skip)."""
    proposal_id = str(uuid4())
    if risk_snapshot:
        await _plant_risk_snapshot(engine, observed_at=proposed_at - timedelta(seconds=20))
    async with engine.begin() as connection:
        rule_set = await connection.scalar(
            text(
                "SELECT id FROM meme_rule_sets WHERE kind = 'operator' AND status = 'active' "
                "ORDER BY version DESC LIMIT 1"
            )
        )
        assert rule_set is not None, "head must seed exactly one active operator set"
        await connection.execute(
            text(
                "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at, created_at, "
                "  creator, initial_real_token_reserves, progress_denominator_source, total_supply) "
                "VALUES (:mint, 'pumpportal_ws', :t, :t, :t, :creator, 793100000, 'observed_virgin', 1000000000) "
                "ON CONFLICT (mint) DO NOTHING"
            ),
            {"mint": MINT, "t": proposed_at - timedelta(seconds=120), "creator": CREATOR},
        )
        await connection.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, expires_at, "
                "  features_end_time, quote, reasons, suggested, decision, decided_by, decided_at, mode) "
                "VALUES (:id, :mint, :rs, 'rules', 'proposed', :proposed, :expires, :fet, '{}', "
                "  '[]', CAST(:suggested AS jsonb), NULL, NULL, NULL, 'paper')"
            ),
            {
                "id": proposal_id,
                "mint": MINT,
                "rs": rule_set,
                "proposed": proposed_at,
                "expires": proposed_at + timedelta(seconds=ttl_s),
                "fet": proposed_at - timedelta(seconds=15),
                "suggested": json.dumps(
                    {
                        "size_sol": size_sol,
                        "target_x": "3",
                        "trailing_pct": "35",
                        "max_hold_s": 1800,
                        "manual_plan": "Comprar 0,01 SOL de X ate ...",
                    }
                ),
            },
        )
    return proposal_id


async def _plant_refused_buy(
    engine: AsyncEngine,
    *,
    mint: str,
    reason: str,
    received_at: datetime,
    decided_by: str = AUTO_STAGE1_DECIDED_BY,
    side: str = "buy",
    status: str = "refused",
) -> str:
    """T4.28f — one row of what the cooldown query reads: a live proposal this
    executor (or a human) decided, plus the order the admission refused."""
    proposal_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at, created_at, "
                "  creator, initial_real_token_reserves, progress_denominator_source, total_supply) "
                "VALUES (:mint, 'pumpportal_ws', :t, :t, :t, :creator, 793100000, 'observed_virgin', 1000000000) "
                "ON CONFLICT (mint) DO NOTHING"
            ),
            {"mint": mint, "t": received_at - timedelta(seconds=120), "creator": CREATOR},
        )
        await connection.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, expires_at, "
                "  quote, reasons, suggested, decision, decided_by, decided_at, mode) "
                "VALUES (:id, :mint, :rs, 'operator', 'rejected', :proposed, :expires, '{}', "
                "  '[\"operator_manual\"]', '{}', '{}'::jsonb, :by, :decided, 'live')"
            ),
            {
                "id": proposal_id,
                "mint": mint,
                "rs": OPERATOR_RULE_SET,
                "proposed": received_at - timedelta(seconds=5),
                "expires": received_at + timedelta(seconds=120),
                "by": decided_by,
                "decided": received_at,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, status, reason, "
                "  received_at) VALUES (:id, :p, :side, :key, :status, :reason, :t)"
            ),
            {
                "id": str(uuid4()),
                "p": proposal_id,
                "side": side,
                "key": f"{side}:{proposal_id}",
                "status": status,
                "reason": reason,
                "t": received_at,
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
    import hunter_meme_executor.admission_context as admission_context_module
    import hunter_meme_executor.exits as exits_module

    async def token_context(
        _session: AsyncSession, _mint: str, *, now: datetime | None = None
    ) -> TokenContext:
        return _full_token_context(now or datetime.now(UTC))

    # T4.45: the entry loop builds its context in ``admission_context`` now (the
    # module that owns the two on-demand reads), so that is where the fake goes.
    monkeypatch.setattr(admission_context_module, "token_context", token_context)
    monkeypatch.setattr(exits_module, "token_context", token_context)
    # Each test starts from an empty ledger and an unlatched switch (owner writes):
    # an unmarked open position left by another test would refuse ``marks_incomplete``
    # — the engine doing its job, not the scenario under test.
    async with db_engine.begin() as connection:
        await connection.execute(text("DELETE FROM meme_live_positions"))
        await connection.execute(text("DELETE FROM meme_live_orders"))
        await connection.execute(
            text(
                "DELETE FROM meme_proposals WHERE mode = 'live' "
                "OR (status = 'proposed' AND mint = :mint)"
            ),
            {"mint": MINT},
        )
        # T4.28h: and the rug reads. ``_plant_operator_proposal`` plants one per
        # test (T4.28g's precondition), so a read left by the previous test is a
        # precondition nobody asked for: with Docker up,
        # ``test_stage_1_waits_for_the_rug_read_*`` passed alone and failed in the
        # suite because ``test_stage_1_opens_…`` had planted a 25 s-old
        # ``bundled_share`` for the same mint — the robot then opened the proposal
        # the test expects it to leave alone.
        await connection.execute(
            text("DELETE FROM meme_risk_snapshots WHERE mint = :mint"), {"mint": MINT}
        )
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


async def test_pickup_lag_recorded_from_proposed_at_and_published_on_heartbeat(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    """T4.52a: ``entries_once`` samples ``received_at - proposed_at`` for every
    candidate it sees for the first time; the heartbeat publishes p50/max of
    that sample — the number R55 measured as "Proposal->Received" (4.8s
    median before the wake-up in ``wake.py``)."""
    now = datetime.now(UTC)
    await _plant_proposal(db_engine, decided_at=now, proposed_at=now - timedelta(seconds=3))
    await entries_once(harness.ctx)
    assert len(harness.ctx.state.pickup_lags) == 1
    lag = harness.ctx.state.pickup_lags[0]
    assert 2.5 < lag < 4.0, lag
    hb = await heartbeat_fields(harness.ctx)
    assert float(hb["proposal_pickup_lag_s_p50"]) == pytest.approx(lag, abs=0.05)
    assert float(hb["proposal_pickup_lag_s_max"]) == pytest.approx(lag, abs=0.05)


async def test_pickup_lag_fields_are_empty_before_any_candidate_is_seen(harness: Harness) -> None:
    hb = await heartbeat_fields(harness.ctx)
    assert hb["proposal_pickup_lag_s_p50"] == ""
    assert hb["proposal_pickup_lag_s_max"] == ""


async def test_wallet_refresh_updates_the_heartbeat_with_no_candidate_at_all(
    harness: Harness,
) -> None:
    """T4.51: the desk with every position closed and no candidate in sight still
    gets a fresh balance — the defect's exact scenario (DOPEY sold, next order
    hours away)."""
    harness.chain.lamports = 672_509_616  # the chain's real answer (getBalance)
    await wallet_refresh_once(harness.ctx)
    hb = await heartbeat_fields(harness.ctx)
    assert Decimal(hb["wallet_sol_balance"]) == Decimal("0.672509616")
    assert Decimal(hb["equity_sol"]) == Decimal("0.672509616")
    assert hb["daily_loss_sol"] == "", "no order ran yet, so no day anchor exists either"
    assert Decimal(hb["wallet_balance_stale_s"]) < Decimal("2")


async def test_a_failed_wallet_refresh_never_lowers_the_published_equity(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.chain.lamports = 645_172_518
    await wallet_refresh_once(harness.ctx)
    stamp = harness.ctx.state.wallet_read_at
    errors_before = harness.ctx.state.rpc_errors

    def _boom(_pubkey: str) -> WalletRead:
        raise RuntimeError("rpc down")

    monkeypatch.setattr(harness.chain, "wallet", _boom)
    harness.chain.lamports = 0  # a refresh that trusted this would drop equity to zero
    await asyncio.sleep(0.05)
    await wallet_refresh_once(harness.ctx)
    assert harness.ctx.state.wallet_lamports == 645_172_518
    assert harness.ctx.state.wallet_read_at == stamp
    assert harness.ctx.state.rpc_errors == errors_before + 1
    hb = await heartbeat_fields(harness.ctx)
    assert Decimal(hb["wallet_sol_balance"]) == Decimal("0.645172518")
    assert float(hb["wallet_balance_stale_s"]) >= 0.05


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


async def test_a_migrated_position_sells_on_pumpswap(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.29a: the exit door ``exits.py`` used to refuse by name
    (``pumpswap_sell_not_implemented``) is real. ``position.migrated = true``
    (``decide_exit`` returns ``"migrated"`` on sight, ``hunter_risk_meme
    .exits``) routes to ``pumpswap_exit.handle_migrated_position``, which
    reads the real F5Mk pool fixture (T4.29a, mint
    ``5RFwNs16ShCeSNQY9Kf5iR5esbEMsnYm7PbWGQAwpump``), builds and "sends"
    (``FakeRpc``) a PumpSwap ``sell``, and closes the position on a fill
    priced from the payer's balance delta (no real ``SellEvent`` — none
    exists to decode; ``.claude/state/notes-T4.29a.md`` "not proven")."""
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE meme_live_positions SET migrated = true WHERE proposal_id = :p"),
            {"p": proposal_id},
        )
    restarted = _context(db_session_factory, _signer(), harness.redis)
    restarted.chain.tokens_on_chain = 10**9
    restarted.chain.migrated = True
    pools = json.loads((PUMPSWAP_FIXTURES / "t429a_rpc_pools_raw.json").read_text(encoding="utf-8"))
    pool_value = pools["result"]["value"][2]  # F5Mk, the pumpfun package's own graduated fixture
    pool = decode_pool_account(pool_value["data"][0], owner=pool_value["owner"])
    restarted.chain.pool_read = PoolRead(
        address="F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ",
        pool=pool,
        base_token_amount=964_405_811_222_437,
        quote_token_amount=751_101_815,
        slot=447586178,
        observed_at=datetime.now(UTC),
    )
    # A landed PumpSwap sell: no decodable SellEvent (none recorded — nothing
    # to fabricate), priced on the payer's own balance delta, matching this
    # exact pool's worked example (quote.py's docstring: net 18 953 lamports).
    restarted.rpc.transaction = {
        "slot": 447586200,
        "blockTime": int(datetime.now(UTC).timestamp()),
        "meta": {
            "err": None,
            "fee": 5000,
            "preBalances": [100_000_000, 0],
            "postBalances": [100_018_953, 0],
            "innerInstructions": [],
        },
        "transaction": {"signatures": ["placeholder"], "message": {"accountKeys": []}},
    }
    await exits_once(restarted.ctx)
    sells = await _rows(
        db_engine,
        "SELECT * FROM meme_live_orders WHERE proposal_id = :p AND side = 'sell'",
        p=proposal_id,
    )
    assert len(sells) == 1 and sells[0]["status"] == "confirmed", sells
    assert sells[0]["intent"]["venue"] == "pumpswap"
    closed = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert closed[0]["status"] == "closed" and closed[0]["exit"]["reason"] == "migrated"
    assert closed[0]["exit"]["venue"] == "pumpswap"
    assert closed[0]["exit"]["sell_net_lamports"] == 18_953
    assert len(restarted.rpc.sent) == 1


async def test_a_migrated_position_without_a_pool_is_blocked_by_name(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The named refusal T4.29a adds: a migrated mint whose canonical pool
    cannot be found (not yet indexed, wrong derivation, RPC lag) stays
    ``open`` with ``blocked: pumpswap_pool_not_found`` — never silently
    retried into the pre-T4.29a blanket refusal."""
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE meme_live_positions SET migrated = true WHERE proposal_id = :p"),
            {"p": proposal_id},
        )
    restarted = _context(db_session_factory, _signer(), harness.redis)
    restarted.chain.tokens_on_chain = 10**9
    restarted.chain.migrated = True
    restarted.chain.pool_read = None
    await exits_once(restarted.ctx)
    rows = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert rows[0]["status"] == "open"
    assert rows[0]["exit_intent"]["blocked"] == "pumpswap_pool_not_found"
    assert len(restarted.rpc.sent) == 0


async def test_a_creator_sale_seen_on_the_chain_sells_the_real_position(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.2h-b (``0038``): the radar's 15 s watch stamps
    ``meme_live_positions.creator_sold_seen_at``; the exit loop reads it on its
    own 5 s tick and sells ``creator_dump`` — with no ``meme_features_1m`` row
    for this mint, so the minute tape says nothing and cannot be the source.

    Before this, a real position learned of the dump only from that tape, which
    on 12/09/2026 was on average 14 minutes late.
    """
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        before = [p for p in await open_positions(session) if p.proposal_id == proposal_id]
    assert before and before[0].creator_sold_seen_at is None
    assert before[0].creator_dump_seen(None) is False, "nothing seen yet, nothing to sell on"
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET creator_sold_seen_at = now(), "
                "creator_sold_fraction = 0.6 WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    restarted = _context(db_session_factory, _signer(), harness.redis)
    restarted.chain.tokens_on_chain = 10**9
    restarted.rpc.transaction = json.loads(json.dumps(_fixture("rpc_tx_probe_raw.json")["result"]))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rebuilt = [p for p in await open_positions(session) if p.proposal_id == proposal_id]
    assert rebuilt[0].creator_sold_seen_at is not None
    assert rebuilt[0].creator_dump_seen(None) is True
    await exits_once(restarted.ctx)
    sells = await _rows(
        db_engine,
        "SELECT * FROM meme_live_orders WHERE proposal_id = :p AND side = 'sell'",
        p=proposal_id,
    )
    assert len(sells) == 1 and sells[0]["status"] == "confirmed", sells
    assert sells[0]["intent"]["exit_reason"] == "creator_dump"
    closed = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert closed[0]["status"] == "closed" and closed[0]["exit"]["reason"] == "creator_dump"
    assert closed[0]["creator_sold_fraction"] == Decimal("0.600000"), (
        "the evidence stays on the row"
    )


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


async def test_token_context_reads_the_real_schema_and_the_bundled_share_from_the_risk_read(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.28 finding: ``bundled_share`` is a column of ``meme_risk_snapshots`` (the
    ``/in-memory-coin`` read, ``0023``), never of ``meme_features_1m`` — the T4.14
    query named it on the wrong table and every test monkeypatched ``token_context``,
    so the first live candidate on the VPS would have raised ``UndefinedColumn`` and
    taken the entry loop down. Read here with no fake: absent ⇒ ``None`` (the engine
    refuses ``bundled_share_unmeasurable``), present and fresh ⇒ the value."""
    from hunter_meme_executor.repo import token_context

    now = datetime.now(UTC)
    # ``risk_snapshot=False``: this test is about the read being absent first.
    await _plant_operator_proposal(db_engine, proposed_at=now, risk_snapshot=False)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        context = await token_context(session, MINT)
    assert context.created_at is not None and context.bundled_share is None
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_risk_snapshots (observed_at, mint, received_at, source, bundled_share, raw) "
                "VALUES (:t, :mint, :t, 'pumpfun_rest', 0.123456, '{}'::jsonb)"
            ),
            {"t": now - timedelta(seconds=30), "mint": MINT},
        )
        await connection.execute(
            text(
                "INSERT INTO meme_risk_snapshots (observed_at, mint, received_at, source, bundled_share, raw) "
                "VALUES (:t, :mint, :t, 'pumpfun_rest', 0.9, '{}'::jsonb)"
            ),
            {"t": now - timedelta(hours=2), "mint": MINT},
        )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        fresh = await token_context(session, MINT)
    assert fresh.bundled_share == Decimal("0.123456"), "the newest read, not the stale one"
    async with db_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM meme_risk_snapshots WHERE mint = :mint AND observed_at >= :t"),
            {"mint": MINT, "t": now - timedelta(minutes=5)},
        )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        stale = await token_context(session, MINT)
    assert stale.bundled_share is None, "a two-hour-old read is not an input (§8)"


async def test_token_context_reads_the_dev_share_and_dates_it(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.28h: the dev share is read from the real schema (``meme_risk_snapshots.dev_share``
    and ``meme_features_1m.dev_share`` + ``holders_observed_at``/``holders_source`` — the
    columns ``0023`` added), with its instant, and a reading older than the window is no
    reading at all. Without this test the query would only be proved by the fakes, which
    is exactly how T4.14 shipped ``bundled_share`` on the wrong table."""
    from hunter_meme_executor.repo import token_context

    now = datetime.now(UTC)
    await _plant_operator_proposal(db_engine, proposed_at=now, risk_snapshot=False)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        blind = await token_context(session, MINT)
    assert (blind.dev_share, blind.dev_share_observed_at) == (None, None)
    fresh_at = now - timedelta(seconds=45)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_risk_snapshots (observed_at, mint, received_at, source, dev_share, raw) "
                "VALUES (:t, :mint, :t, 'pumpfun_rest', 0.048000, '{}'::jsonb)"
            ),
            {"t": fresh_at, "mint": MINT},
        )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        read = await token_context(session, MINT)
    assert read.dev_share == Decimal("0.048000")
    assert read.dev_share_source == "meme_risk_snapshots"
    assert read.dev_share_observed_at == fresh_at
    async with db_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM meme_risk_snapshots WHERE mint = :mint AND observed_at = :t"),
            {"mint": MINT, "t": fresh_at},
        )
        await connection.execute(
            text(
                "INSERT INTO meme_risk_snapshots (observed_at, mint, received_at, source, dev_share, raw) "
                "VALUES (:t, :mint, :t, 'pumpfun_rest', 0.048000, '{}'::jsonb)"
            ),
            {"t": now - timedelta(seconds=RISK_SNAPSHOT_MAX_AGE_S + 60), "mint": MINT},
        )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        stale = await token_context(session, MINT)
    assert stale.dev_share is None, "past the window it is not an input (§8)"


async def test_an_unknown_creator_is_admitted_only_when_the_owner_allowed_the_measured_dev_share(
    harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.28h end to end on the real ledger. Same coin, same ``creator_sold = NULL``
    (the fold's 1 m photo lands +123–441 s after creation while the entry happens at
    30–300 s, R5 16/09/2026), same measured ``dev_share`` of 5 %: **off** the buy is
    refused ``creator_flow_unknown`` and no order is sent; **on** it is admitted, sent
    and confirmed, and the admission says which of the two passes it was."""
    import hunter_meme_executor.admission_context as admission_context_module

    async def unknown_creator(
        _session: AsyncSession, _mint: str, *, now: datetime | None = None
    ) -> TokenContext:
        # T4.45: ``creator_initial_tokens`` stays ``None`` here on purpose - this
        # coin has no recorded allocation, so the chain derivation does not run
        # and the case under test is still the owner's allowance, alone.
        return _full_token_context(datetime.now(UTC), creator_sold=None, dev_share=Decimal("0.05"))

    monkeypatch.setattr(admission_context_module, "token_context", unknown_creator)

    refused_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    refused = await _rows(
        db_engine, "SELECT * FROM meme_live_orders WHERE proposal_id = :p", p=refused_id
    )
    assert len(refused) == 1 and refused[0]["status"] == "refused"
    assert refused[0]["reason"] == "creator_flow_unknown"
    assert harness.rpc.sent == [], "the default refuses and sends nothing"

    allowed = _context(
        db_session_factory,
        _signer(),
        harness.redis,
        policy={**POLICY, "MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED": "true"},
    )
    assert allowed.ctx.config.limits.creator_unknown_allowed_if_dev_measured
    approved_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(allowed.ctx)
    orders = await _rows(
        db_engine, "SELECT * FROM meme_live_orders WHERE proposal_id = :p", p=approved_id
    )
    assert len(orders) == 1 and orders[0]["status"] == "confirmed", orders
    assert orders[0]["admission"]["approved"] is True
    line = next(c for c in orders[0]["admission"]["checks"] if c["name"] == "creator_behaviour")
    assert line["state"] == "passed" and line["refusal"] is None
    assert line["message"] == "creator_unknown_dev_share_measured"
    # The canonical JSON normalises the Decimals it stores ("0.10" → "0.1").
    assert (Decimal(line["value"]), Decimal(line["limit"])) == (Decimal("0.05"), Decimal("0.10"))


async def test_the_heartbeat_publishes_the_allowance_the_owner_turned_on(
    harness: Harness, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    off = json.loads((await heartbeat_fields(harness.ctx))["policy"])
    assert off["creator_unknown_allowed_if_dev_measured"] is False
    assert off["creator_unknown_max_dev_share_pct"] == "0.10"
    on = _context(
        db_session_factory,
        _signer(),
        harness.redis,
        policy={
            **POLICY,
            "MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED": "on",
            "MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT": "0.03",
        },
    )
    published = json.loads((await heartbeat_fields(on.ctx))["policy"])
    assert published["creator_unknown_allowed_if_dev_measured"] is True
    assert published["creator_unknown_max_dev_share_pct"] == "0.03"


# ---------------------------------------------------------------- T4.28 stage 1


async def _proposal(engine: AsyncEngine, proposal_id: str) -> dict[str, Any]:
    return (
        await _rows(
            engine,
            "SELECT status, mode, decided_by, decided_at, decision FROM meme_proposals WHERE id = :p",
            p=proposal_id,
        )
    )[0]


async def test_stage_1_opens_the_operator_proposal_as_live_admits_it_and_buys(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The whole path without the click: ``proposed``/``paper`` → the executor's own
    approval (the click's statement, ``decided_by = executor:auto_stage1``,
    ``decision = suggested``) → the unchanged admission → simulate → sign → the
    fake send → confirmed order → open position — in one tick. A second tick
    writes nothing (idempotent on the proposal)."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    proposal_id = await _plant_operator_proposal(db_engine, proposed_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    proposal = await _proposal(db_engine, proposal_id)
    assert proposal["status"] == "approved" and proposal["mode"] == "live"
    assert proposal["decided_by"] == AUTO_STAGE1_DECIDED_BY
    assert proposal["decision"]["size_sol"] == "0.01"
    assert proposal["decision"]["manual_plan"].startswith("Comprar")
    assert proposal["decision"]["note"].startswith("auto_stage1")
    orders = await _rows(
        db_engine, "SELECT * FROM meme_live_orders WHERE proposal_id = :p", p=proposal_id
    )
    assert len(orders) == 1 and orders[0]["status"] == "confirmed", orders
    assert orders[0]["admission"]["approved"] is True
    assert orders[0]["admission"]["small_test"]["trades_done"] == 0
    assert orders[0]["admission"]["small_test"]["requested_clamped"] is False
    assert len(armed.rpc.sent) == 1
    positions = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert len(positions) == 1 and positions[0]["status"] == "open"
    assert positions[0]["params"]["decided_by"] == AUTO_STAGE1_DECIDED_BY
    assert armed.ctx.state.auto_approved == 1 and armed.ctx.state.auto_rejected == 0
    await entries_once(armed.ctx)
    assert len(armed.rpc.sent) == 1
    assert armed.ctx.state.auto_approved == 1
    hb = await heartbeat_fields(armed.ctx)
    assert hb["auto_approve"] == "true" and hb["auto_approved_1h"] == "1"
    assert hb["small_test_trades_done"] == "1"
    assert Decimal(hb["small_test_used_sol"]) == Decimal(
        orders[0]["fill"]["buy_total_lamports"]
    ) / (Decimal(10**9))


async def test_stage_1_rejects_by_name_what_its_own_admission_refuses(
    harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(d): the robot opened it, the 25 checks refused it (here: ``bundled_share``
    not measured) — the ``refused`` order is written **and** the proposal is
    ``rejected`` with the reason, ``decided_by`` still the robot's."""
    import hunter_meme_executor.admission_context as admission_context_module

    async def unmeasured(
        _session: AsyncSession, _mint: str, *, now: datetime | None = None
    ) -> TokenContext:
        full = _full_token_context(datetime.now(UTC))
        return replace(full, bundled_share=None)

    # T4.45: this context has no ``risk_client``, so the on-demand read cannot
    # rescue the mint - which is the point: with the endpoint out of reach the
    # refusal is exactly the one this test has always asserted.
    monkeypatch.setattr(admission_context_module, "token_context", unmeasured)
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    proposal_id = await _plant_operator_proposal(db_engine, proposed_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    proposal = await _proposal(db_engine, proposal_id)
    assert proposal["status"] == "rejected" and proposal["mode"] == "live"
    assert proposal["decided_by"] == AUTO_STAGE1_DECIDED_BY
    assert proposal["decision"]["auto_refusal"] == "bundled_share_unmeasurable"
    assert "bundled_share_unmeasurable" in proposal["decision"]["note"]
    orders = await _rows(
        db_engine,
        "SELECT status, reason FROM meme_live_orders WHERE proposal_id = :p",
        p=proposal_id,
    )
    assert orders == [{"status": "refused", "reason": "bundled_share_unmeasurable"}]
    assert armed.rpc.sent == []
    assert armed.ctx.state.auto_rejected == 1
    hb = await heartbeat_fields(armed.ctx)
    assert json.loads(hb["auto_refused_1h"]) == {"bundled_share_unmeasurable": 1}


async def test_the_cooldown_query_reads_only_this_executors_deterministic_refusals(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.28f — the SQL behind the ``recently_refused`` skip, against the real
    schema: our own buy refusals inside the window, the reason filtered in Python.
    Everything else in the table is noise it must not read."""
    now = datetime.now(UTC)
    cooling_mint = MINT
    stale_mint = "2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump"
    old_mint = "3pQ4hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump"
    click_mint = "4rT5hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump"
    sell_mint = "6uV7hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump"
    await _plant_refused_buy(
        db_engine,
        mint=cooling_mint,
        reason="progress_above_window",
        received_at=now - timedelta(seconds=30),
    )
    await _plant_refused_buy(  # reversible on the next tick — never cools
        db_engine,
        mint=stale_mint,
        reason="curve_state_stale",
        received_at=now - timedelta(seconds=30),
    )
    await _plant_refused_buy(  # deterministic, but older than the 120 s window
        db_engine,
        mint=old_mint,
        reason="progress_above_window",
        received_at=now - timedelta(seconds=200),
    )
    await _plant_refused_buy(  # a human's proposal: the robot's cooldown is its own
        db_engine,
        mint=click_mint,
        reason="progress_above_window",
        received_at=now - timedelta(seconds=30),
        decided_by="user_x",
    )
    await _plant_refused_buy(  # a refused **sale** never stops a buy
        db_engine,
        mint=sell_mint,
        reason="progress_above_window",
        received_at=now - timedelta(seconds=30),
        side="sell",
    )
    await _plant_refused_buy(  # a confirmed buy is not a refusal
        db_engine,
        mint="7wX8hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump",
        reason="progress_above_window",
        received_at=now - timedelta(seconds=30),
        status="admitted",
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        cooling = await refusal_cooling_mints(session, now=now, cooldown_s=120.0)
        disabled = await refusal_cooling_mints(session, now=now, cooldown_s=0.0)
        wide = await refusal_cooling_mints(session, now=now, cooldown_s=3600.0)

    assert cooling == frozenset({cooling_mint})
    assert disabled == frozenset(), "cooldown 0 asks the database nothing"
    assert wide == frozenset({cooling_mint, old_mint}), "the window is the only clock"


async def test_stage_1_does_not_reopen_a_mint_it_just_had_refused(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The measured loop of 16/09/2026 11:46–11:48 BRT: the desk re-proposes the
    same mint every ~20 s. With the cooldown the robot opens nothing, writes no
    order and leaves the row ``proposed`` — the heartbeat names the skip."""
    now = datetime.now(UTC)
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    await _plant_refused_buy(
        db_engine,
        mint=MINT,
        reason="progress_above_window",
        received_at=now - timedelta(seconds=30),
    )
    proposal_id = await _plant_operator_proposal(db_engine, proposed_at=now)

    opened = await auto_approve_once(armed.ctx, now=now)

    assert opened == []
    assert armed.ctx.state.auto_approved == 0
    assert armed.ctx.state.auto_skipped == {"recently_refused": 1}
    row = await _proposal(db_engine, proposal_id)
    assert row["status"] == "proposed" and row["mode"] == "paper", "left for the human"
    orders = await _rows(
        db_engine, "SELECT id FROM meme_live_orders WHERE proposal_id = :p", p=proposal_id
    )
    assert orders == [], "no RPC read, no refused row, no rejected proposal"
    hb = await heartbeat_fields(armed.ctx)
    assert json.loads(hb["auto_skipped"]) == {"recently_refused": 1}
    # Past the cooldown the same proposal is opened: the skip is a delay, not a ban.
    armed.ctx.state.auto_skipped.clear()
    later = now + timedelta(seconds=121)
    assert await auto_approve_once(armed.ctx, now=later) == []  # the row is older than 60 s now
    assert armed.ctx.state.auto_skipped == {"too_old": 1}, "not cooling any more"


async def test_stage_1_waits_for_the_rug_read_instead_of_burning_the_proposal(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.28g — the measured 103 s, closed from the executor's side.

    Before: the desk files the row, the robot opens it 3–10 s later, the admission
    refuses ``bundled_share_unmeasurable``, the proposal is ``rejected`` (gone for
    the human's click too) and a ``refused`` order is written — all for a number
    that landed a minute and a half afterwards (13 of 16 real orders on 16/09/2026).

    After: with no measured ``bundled_share`` for the mint, nothing is opened, the
    row stays ``proposed``, no order exists, and the heartbeat says
    ``risk_snapshot_pending``. When the worker's read lands, the same row is opened
    and admitted on the next tick — **the check itself never moved**."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    waiting = await _plant_operator_proposal(
        db_engine, proposed_at=datetime.now(UTC), risk_snapshot=False
    )
    await entries_once(armed.ctx)
    assert (await _proposal(db_engine, waiting))["status"] == "proposed", "still the human's"
    assert armed.ctx.state.auto_skipped == {"risk_snapshot_pending": 1}
    assert armed.ctx.state.auto_approved == 0 and armed.ctx.state.auto_rejected == 0
    assert (
        await _rows(db_engine, "SELECT id FROM meme_live_orders WHERE proposal_id = :p", p=waiting)
        == []
    ), "no order is written while the input is missing"
    assert armed.rpc.sent == []
    hb = await heartbeat_fields(armed.ctx)
    assert json.loads(hb["auto_skipped"])["risk_snapshot_pending"] == 1

    await _plant_risk_snapshot(db_engine, observed_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    opened = await _proposal(db_engine, waiting)
    assert opened["status"] == "approved" and opened["mode"] == "live"
    assert opened["decided_by"] == AUTO_STAGE1_DECIDED_BY
    assert len(armed.rpc.sent) == 1


async def test_a_stale_rug_read_is_not_a_rug_read(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """§8: stale is absent. A read older than ``RISK_SNAPSHOT_MAX_AGE_S`` is exactly
    what ``token_context`` would drop, so waiting on it (instead of opening and
    being refused) is the same decision, one step earlier."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    stale = await _plant_operator_proposal(
        db_engine, proposed_at=datetime.now(UTC), risk_snapshot=False
    )
    await _plant_risk_snapshot(
        db_engine, observed_at=datetime.now(UTC) - timedelta(seconds=RISK_SNAPSHOT_MAX_AGE_S + 60)
    )
    await entries_once(armed.ctx)
    assert (await _proposal(db_engine, stale))["status"] == "proposed"
    assert armed.ctx.state.auto_skipped == {"risk_snapshot_pending": 1}
    assert armed.rpc.sent == []


async def test_stage_1_leaves_an_old_proposal_and_a_click_proposal_alone(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Older than 60 s the robot does not decide (the human still has until the
    set's 180 s); and with the flag off nothing ``proposed`` is ever touched."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    old = await _plant_operator_proposal(
        db_engine, proposed_at=datetime.now(UTC) - timedelta(seconds=61)
    )
    await entries_once(armed.ctx)
    assert (await _proposal(db_engine, old))["status"] == "proposed"
    assert armed.ctx.state.auto_skipped == {"too_old": 1}
    assert (
        await _rows(db_engine, "SELECT id FROM meme_live_orders WHERE proposal_id = :p", p=old)
        == []
    )
    fresh = await _plant_operator_proposal(db_engine, proposed_at=datetime.now(UTC))
    await entries_once(harness.ctx)  # the click-only executor: auto_approve is False
    assert (await _proposal(db_engine, fresh))["status"] == "proposed"
    assert harness.rpc.sent == [] and harness.ctx.state.auto_approved == 0


async def test_stage_1_closes_the_tap_on_the_scope_sol_ceiling(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The recorded fill took ~1.0035 SOL from the payer (T4.8's real buy), so after
    one buy a 0,25 SOL scope is spent: the robot stops opening proposals
    (``scope_exhausted:max_total_sol``) and a click's live approval is refused
    ``small_test_scope_exhausted`` by the SOL counter, never sent."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    first = await _plant_operator_proposal(db_engine, proposed_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    assert (await _proposal(db_engine, first))["status"] == "approved"
    assert len(armed.rpc.sent) == 1
    second = await _plant_operator_proposal(db_engine, proposed_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    assert (await _proposal(db_engine, second))["status"] == "proposed"
    assert armed.ctx.state.auto_skipped == {"scope_exhausted:max_total_sol": 1}
    assert len(armed.rpc.sent) == 1
    clicked = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    orders = await _rows(
        db_engine,
        "SELECT status, reason, admission FROM meme_live_orders WHERE proposal_id = :p",
        p=clicked,
    )
    assert orders[0]["status"] == "refused" and orders[0]["reason"] == "small_test_scope_exhausted"
    assert orders[0]["admission"]["exhausted"] == "max_total_sol"
    assert orders[0]["admission"]["trades_done"] == 1
    assert len(armed.rpc.sent) == 1
    hb = await heartbeat_fields(armed.ctx)
    assert hb["small_test_exhausted"] == "max_total_sol"
    assert hb["small_test_remaining_sol"] == "0"


async def test_stage_1_clamps_the_last_buy_to_what_the_scope_has_left(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """With ~1.0035 SOL already taken and a 1,01 SOL scope, a 0,01 request is
    admitted for the remainder (~0,0065) — the scope is a ceiling, not a target.
    The first position is closed by hand in between: the SOL counter is the
    ledger of **buys sent**, not of positions still open (those the daily cap and
    ``duplicate_position`` already refuse — the engine's job, not the scope's)."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("1.01"))
    first = await _plant_operator_proposal(db_engine, proposed_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    used = (
        await _rows(db_engine, "SELECT fill FROM meme_live_orders WHERE proposal_id = :p", p=first)
    )[0]["fill"]["buy_total_lamports"]
    remaining = Decimal("1.01") - Decimal(used) / Decimal(10**9)
    assert Decimal("0") < remaining < Decimal("0.01"), remaining
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET status = 'closed', exit_at = now(), "
                'exit = \'{"reason": "sold_by_hand"}\'::jsonb, pnl_sol = 0, r_multiple = 0 '
                "WHERE proposal_id = :p"
            ),
            {"p": first},
        )
    second = await _plant_operator_proposal(db_engine, proposed_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    order = (
        await _rows(
            db_engine,
            "SELECT status, intent, admission FROM meme_live_orders WHERE proposal_id = :p",
            p=second,
        )
    )[0]
    assert order["status"] == "confirmed"
    assert order["admission"]["small_test"]["requested_clamped"] is True
    assert Decimal(order["admission"]["small_test"]["requested_cap_sol"]) == remaining
    assert Decimal(order["intent"]["sol_final"]) <= remaining
    assert order["admission"]["sizing"]["binding_constraint"] == "requested"


async def test_stage_1_with_sending_disabled_opens_admits_simulates_and_sends_nothing(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The ``sigVerify=false`` proof shape (T4.8b/T4.8c): the whole stage-1 path up
    to the simulation, then ``failed: meme_live_disabled`` before the key —
    ``rpc.sent == []``, no signature, no position; the proposal stays
    ``approved``/``live`` (a send refusal is not an admission refusal)."""
    armed = _context(
        db_session_factory, _signer(), harness.redis, auto=_small_test(), allow_send=False
    )
    proposal_id = await _plant_operator_proposal(db_engine, proposed_at=datetime.now(UTC))
    await entries_once(armed.ctx)
    proposal = await _proposal(db_engine, proposal_id)
    assert proposal["status"] == "approved" and proposal["decided_by"] == AUTO_STAGE1_DECIDED_BY
    orders = await _rows(
        db_engine,
        "SELECT status, reason, signatures, admission FROM meme_live_orders WHERE proposal_id = :p",
        p=proposal_id,
    )
    assert len(orders) == 1
    assert orders[0]["status"] == "failed" and orders[0]["reason"] == "meme_live_disabled"
    assert orders[0]["admission"]["approved"] is True
    assert orders[0]["signatures"] == []
    assert armed.rpc.sent == []
    assert (
        await _rows(
            db_engine, "SELECT id FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
        )
        == []
    )


class FakeIndexer:
    """The pump.fun indexer, answering once — or refusing. No network."""

    def __init__(self, *, answer: Any = None, raises: Exception | None = None) -> None:
        self.answer, self.raises = answer, raises
        self.calls: list[str] = []

    async def get_risk_snapshot(self, mint: str) -> Any:
        self.calls.append(mint)
        if self.raises is not None:
            raise self.raises
        return self.answer


DEV_BUY_TOKENS = Decimal("30877830.227113")
"""A real ``initialBuy`` from the live capture (line 6, mint ``HTEqdy7k…``).

The **same** number in every test that records it: ``creator_initial_tokens`` is
write-once in the database, ``meme_tokens`` is not cleaned between tests, and the
trigger refuses a second, different value - which is exactly the guarantee the
admission leans on, so the tests live with it instead of dropping the row."""


async def _record_the_dev_buy(engine: AsyncEngine) -> None:
    """What ``0048`` stores at ingest, written here as the radar would."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_tokens SET creator_initial_tokens = :tokens, "
                "  creator_initial_sol = 0.888892813 "
                "WHERE mint = :mint AND creator_initial_tokens IS DISTINCT FROM :tokens"
            ),
            {"mint": MINT, "tokens": DEV_BUY_TOKENS},
        )


def _reading(mint: str, *, observed_at: datetime, bundled_share: str | None = "0.05") -> Any:
    from hunter_exchanges.pumpfun.board_models import NormalizedRiskSnapshot

    return NormalizedRiskSnapshot(
        mint=mint,
        bundled_share=None if bundled_share is None else Decimal(bundled_share),
        dev_share=Decimal("0.04"),
        top10_share=Decimal("0.18"),
        holders=42,
        raw={"mint": mint, "bundlerOwnedPercentageV2": 5},
        observed_at=observed_at,
        received_at=observed_at,
    )


async def test_the_executors_own_rug_read_lands_as_a_row_the_admission_then_reads(
    harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """T4.45 Part A against the real schema.

    The failure it removes, measured on 16/09/2026: 36 of the 39 in-window real
    orders were refused ``bundled_share_unmeasurable`` while the radar's row for
    the same mint landed a median 103 s **later**. Here the table is empty, the
    executor reads the endpoint itself, and the row it writes is read back by the
    very query the admission uses — same table, same freshness window, only the
    ``source`` says who asked."""
    from hunter_meme_executor.repo import token_context
    from hunter_meme_executor.risk_read import ON_DEMAND_SOURCE, read_risk_snapshot_on_demand

    now = datetime.now(UTC)
    await _plant_operator_proposal(db_engine, proposed_at=now, risk_snapshot=False)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        before = await token_context(session, MINT, now=now)
    assert before.bundled_share is None, "the precondition: nothing measured yet"

    indexer = FakeIndexer(answer=_reading(MINT, observed_at=now))
    ctx = replace(harness.ctx, risk_client=cast(Any, indexer))
    assert await read_risk_snapshot_on_demand(ctx, MINT, now=now) is True
    assert indexer.calls == [MINT]

    rows = await _rows(
        db_engine,
        "SELECT source, bundled_share, dev_share, raw FROM meme_risk_snapshots WHERE mint = :mint",
        mint=MINT,
    )
    assert len(rows) == 1
    assert rows[0]["source"] == ON_DEMAND_SOURCE
    assert rows[0]["bundled_share"] == Decimal("0.05")
    assert rows[0]["raw"]["bundlerOwnedPercentageV2"] == 5, "the 65 raw fields are kept"
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        after = await token_context(session, MINT, now=now)
    assert after.bundled_share == Decimal("0.05")
    assert after.dev_share == Decimal("0.04"), "T4.28h's input rides the same row"
    assert ctx.state.risk_reads_on_demand == 1


async def test_a_failed_on_demand_read_writes_nothing_and_leaves_the_refusal_standing(
    harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Never a pass on missing data: the endpoint refusing leaves the table
    exactly as it was, so check 11 still refuses ``bundled_share_unmeasurable``."""
    from hunter_meme_executor.repo import token_context
    from hunter_meme_executor.risk_read import read_risk_snapshot_on_demand

    now = datetime.now(UTC)
    await _plant_operator_proposal(db_engine, proposed_at=now, risk_snapshot=False)
    indexer = FakeIndexer(raises=RuntimeError("429"))
    ctx = replace(harness.ctx, risk_client=cast(Any, indexer))
    assert await read_risk_snapshot_on_demand(ctx, MINT, now=now) is False
    assert (
        await _rows(db_engine, "SELECT 1 FROM meme_risk_snapshots WHERE mint = :mint", mint=MINT)
        == []
    )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        assert (await token_context(session, MINT, now=now)).bundled_share is None
    assert ctx.state.risk_reads_on_demand_failed == 1


async def test_token_context_reads_the_creators_recorded_allocation(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.45 Part B against the real schema (``0048``): the two columns the
    chain-derived creator flow compares against are read from ``meme_tokens`` by
    the query the admission already runs — no second round trip, and no fake of
    the schema (the T4.14 lesson: ``bundled_share`` shipped on the wrong table
    because only fakes had ever seen the query)."""
    from hunter_meme_executor.creator_flow import needs_chain_creator_flow
    from hunter_meme_executor.repo import token_context

    now = datetime.now(UTC)
    await _plant_operator_proposal(db_engine, proposed_at=now, risk_snapshot=False)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        unknown = await token_context(session, MINT, now=now)
    assert unknown.creator_initial_tokens is None
    assert not needs_chain_creator_flow(unknown), "no base, no derivation — the T4.28g rule"

    await _record_the_dev_buy(db_engine)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        known = await token_context(session, MINT, now=now)
    assert known.creator_initial_tokens == DEV_BUY_TOKENS
    assert known.creator_initial_sol == Decimal("0.888892813")
    assert known.creator_sold is None, "the fold has not spoken yet — the 16/09 case"
    assert needs_chain_creator_flow(known)


async def test_the_chain_answers_check_ten_when_the_fold_is_still_silent(
    harness: Harness, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end on the admission path, with the real rows and the fake chain:
    ``creator_sold`` NULL + a recorded allocation ⇒ the creator's balance decides,
    and the order's ``admission`` JSON names where the answer came from.

    Both directions are asserted, because a derivation that could only say "he
    still holds" would be worse than no derivation at all."""
    import hunter_meme_executor.admission_context as admission_context_module
    from hunter_meme_executor.admission_context import build_admission_context
    from hunter_meme_executor.repo import token_context

    # The harness fakes the context for the scenarios that are not about it; this
    # one **is** about the row, so the real query runs against the real schema.
    monkeypatch.setattr(admission_context_module, "token_context", token_context)
    now = datetime.now(UTC)
    await _plant_operator_proposal(db_engine, proposed_at=now, risk_snapshot=True)
    await _record_the_dev_buy(db_engine)
    ctx = harness.ctx
    curve = harness.chain.curve(MINT)
    assert curve is not None

    harness.chain.tokens_on_chain = int(DEV_BUY_TOKENS * 1_000_000)
    holding = await build_admission_context(ctx, MINT, curve, now=now)
    assert holding.context.creator_net_sol == Decimal(1)
    assert holding.extras["creator_flow"]["source"] == "chain_ata_vs_initial"
    assert holding.extras["creator_flow"]["balance_tokens"] == str(DEV_BUY_TOKENS)

    harness.chain.tokens_on_chain = 10_000_000  # 10 tokens: he sold 99,99 %
    dumped = await build_admission_context(ctx, MINT, curve, now=now)
    assert dumped.context.creator_net_sol == Decimal(-1)
    assert dumped.extras["creator_flow"]["net_sol"] == "-1"


async def test_stage_1_reads_the_rug_numbers_itself_instead_of_waiting_a_tick(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """T4.45 replaces T4.28g's *wait* with a *read* — end to end, in one tick.

    Same starting position as ``test_stage_1_waits_for_the_rug_read_…``: an
    ``operator`` proposal and an empty ``meme_risk_snapshots``. With the indexer
    reachable the executor reads it on the spot, persists the row, and the same
    tick opens and admits the proposal — instead of leaving it for a reader whose
    row lands a median 103 s later, by which time the proposal is the human's
    (60 s) or expired (180 s).

    The endpoint is asked **once** for the mint: the read-first path spends the
    call only on the proposal the planner would actually open."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    now = datetime.now(UTC)
    indexer = FakeIndexer(answer=_reading(MINT, observed_at=now))
    armed = replace(armed, ctx=replace(armed.ctx, risk_client=cast(Any, indexer)))
    proposal_id = await _plant_operator_proposal(db_engine, proposed_at=now, risk_snapshot=False)

    await entries_once(armed.ctx)

    opened = await _proposal(db_engine, proposal_id)
    assert opened["status"] == "approved" and opened["mode"] == "live"
    assert opened["decided_by"] == AUTO_STAGE1_DECIDED_BY
    assert armed.ctx.state.auto_skipped == {}, "nothing was waited on"
    assert indexer.calls == [MINT], "one read for one proposal"
    assert armed.ctx.state.risk_reads_on_demand == 1
    assert len(armed.rpc.sent) == 1, "the admission ran on the number that just landed"
    hb = await heartbeat_fields(armed.ctx)
    assert hb["risk_reads_on_demand"] == "1" and hb["risk_reads_on_demand_failed"] == "0"


async def test_stage_1_still_waits_when_its_own_read_fails(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The fallback T4.28g built stays exactly where it was: the read is a chance,
    never a promise. With the endpoint refusing, the proposal is **not** opened —
    no ``refused`` order, no ``rejected`` row, nothing sent — and the heartbeat
    still names ``risk_snapshot_pending``. A pass on missing data is the one
    outcome this task must never produce."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test())
    now = datetime.now(UTC)
    indexer = FakeIndexer(raises=RuntimeError("503"))
    armed = replace(armed, ctx=replace(armed.ctx, risk_client=cast(Any, indexer)))
    proposal_id = await _plant_operator_proposal(db_engine, proposed_at=now, risk_snapshot=False)

    await entries_once(armed.ctx)

    assert (await _proposal(db_engine, proposal_id))["status"] == "proposed", "still the human's"
    assert armed.ctx.state.auto_skipped == {"risk_snapshot_pending": 1}
    assert (
        await _rows(
            db_engine, "SELECT id FROM meme_live_orders WHERE proposal_id = :p", p=proposal_id
        )
        == []
    )
    assert armed.rpc.sent == []
    assert armed.ctx.state.risk_reads_on_demand_failed == 1
