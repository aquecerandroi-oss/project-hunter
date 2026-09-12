# pyright: reportPrivateUsage=false
"""T4.12 against a real Postgres at ``head`` — one file, one container.

What only a database can prove: the wallet loop appends the real captured
buy (``AsRQ…``, ``rpc_tx_buy_raw.json``) and the real captured sell
(``sssss…``, ``rpc_tx_probe_raw.json``) to ``meme_wallet_trades`` as
``hunter_worker``, skips the signature the node reports failed, keeps a
signature the node cannot serve as ``unknown`` by name, **dedupes by
signature** on a second pass, writes the ``lab_context`` of the buy from the
minute the Lab folded (every active gate's verdict by name, the minute's
``hype_score``/``line_reason``), folds the positions (an open one marked by
the later curve snapshot, a sell with no observed buy left unmatched),
re-marks by the tape when it is newer, and puts the wallet on
``meme_lab_scoreboard_v1`` as ``wallet:<8>`` / ``real_observed`` readable by
``hunter_app``.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.rpc_wallet import SignatureInfo
from hunter_indicators.meme.curve import CurveReserves, quote_sell
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.features import FEATURES_VERSION
from hunter_meme_worker.repo import insert_snapshot, upsert_token
from hunter_meme_worker.repo_rows import SnapshotRow, TokenRow
from hunter_meme_worker.sources import SourcesState
from hunter_meme_worker.tracker import MintTracker
from hunter_meme_worker.wallets import wallets_once
from hunter_meme_worker.wallets_state import WalletsWatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
APP = "hunter_app"
FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
BUYER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
SELLER = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
BUY_AT = datetime.fromtimestamp(1789197249, tz=UTC)
SELL_AT = datetime.fromtimestamp(1789198468, tz=UTC)
MINUTE = BUY_AT.replace(second=0, microsecond=0)
# The reserves the buy event reports after the fill (lamports / token units).
RESERVES_1 = (Decimal("37.786957611"), Decimal("851881256.808384"))
RESERVES_2 = (Decimal("36.903292683"), Decimal("872279913.273338"))
TOKENS_BOUGHT = Decimal("22628881.309131")

_REASON_COLUMNS = (
    "progress_reason, curve_reason, unique_buyers_reason, buy_sell_ratio_reason, "
    "top10_share_reason, creator_sold_reason, holders_reason, dev_share_reason, "
    "snipers_reason, tape_reason, creator_net_seller_reason"
)
_REASON_VALUES = (
    "'not_polled', 'not_polled', 'no_trade_feed', 'no_trade_feed', 'no_holders_reader', "
    "'no_trade_feed', 'no_holders_reader', 'no_holders_reader', 'no_holders_reader', "
    "'no_trade_feed', 'no_trade_feed'"
)
_A_V3_ROW = text(
    "INSERT INTO meme_features_1m (end_time, mint, features_version, coverage, "  # noqa: S608
    f"  {_REASON_COLUMNS}, snapshot_observed_at, snapshot_source, line_points, line_reason, "
    "  high_15m_sol, low_15m_sol, hype_score) "
    f"VALUES (:end_time, :mint, :version, 1, {_REASON_VALUES}, :observed_at, 'pumpfun_rest', "
    "  15, 'flat', 56, 36, 0.7)"
)


def _tx(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text())["result"])


class FakeChain:
    """Two coroutines and no socket — a legitimate ``WalletChainSource``."""

    def __init__(self, pages: dict[str, list[SignatureInfo]], txs: dict[str, Any]) -> None:
        self.pages, self.txs = pages, txs
        self.calls: list[tuple[str, str]] = []

    async def get_signatures_for_address(
        self, address: str, *, until: str | None = None, limit: int = 100
    ) -> list[SignatureInfo]:
        self.calls.append(("sigs", address))
        out: list[SignatureInfo] = []
        for info in self.pages.get(address, []):
            if info.signature == until:
                break
            out.append(info)
        return out[:limit]

    async def get_transaction(self, signature: str) -> dict[str, Any] | None:
        self.calls.append(("tx", signature))
        return self.txs.get(signature)


def _chain() -> FakeChain:
    return FakeChain(
        pages={
            BUYER: [
                SignatureInfo("BUYSIG", 446369982, BUY_AT, False),
                SignatureInfo("FAILSIG", 446369980, BUY_AT, True),
            ],
            SELLER: [
                SignatureInfo("SELLSIG", 446373814, SELL_AT, False),
                SignatureInfo("GHOST", 446373800, None, False),
            ],
        },
        txs={"BUYSIG": _tx("rpc_tx_buy_raw.json"), "SELLSIG": _tx("rpc_tx_probe_raw.json")},
    )


def _snapshot(at: datetime, reserves: tuple[Decimal, Decimal]) -> SnapshotRow:
    sol, tokens = reserves
    return SnapshotRow(
        observed_at=at,
        mint=MINT,
        source="pumpfun_rest",
        virtual_sol_reserves=sol,
        virtual_token_reserves=tokens,
        real_sol_reserves=sol - Decimal(30),
        real_token_reserves=tokens - Decimal("279900000"),
        total_supply=Decimal(1_000_000_000),
        complete=False,
    )


async def _plant(factory: async_sessionmaker[AsyncSession]) -> None:
    async with role_session(factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            TokenRow(
                mint=MINT,
                first_seen_source="pumpportal_ws",
                first_seen_at=BUY_AT - timedelta(minutes=2),
                last_seen_at=BUY_AT,
                created_at=BUY_AT - timedelta(minutes=2),
                initial_real_token_reserves=Decimal("793100000"),
                progress_denominator_source="observed_virgin",
                total_supply=Decimal(1_000_000_000),
            ),
        )
        await insert_snapshot(session, _snapshot(MINUTE - timedelta(seconds=30), RESERVES_1))
        await insert_snapshot(session, _snapshot(BUY_AT + timedelta(seconds=60), RESERVES_2))
        await session.execute(
            _A_V3_ROW,
            {
                "end_time": MINUTE,
                "mint": MINT,
                "version": FEATURES_VERSION,
                "observed_at": MINUTE - timedelta(seconds=30),
            },
        )


def _context(factory: async_sessionmaker[AsyncSession], chain: FakeChain) -> RadarContext:
    sources = SourcesState()
    return RadarContext(
        config=MemeConfig(enabled=True, watch_wallets=(BUYER, SELLER)),
        session_factory=factory,
        tracker=MintTracker(window_minutes=60, cap=10, young_minutes=30),
        state=RadarState(),
        events=cast(Any, None),
        curves=cast(Any, None),
        chain=cast(Any, None),
        sources=sources,
        wallets=WalletsWatcher(
            chain, wallets=(BUYER, SELLER), features_version=FEATURES_VERSION, sources=sources
        ),
    )


async def _rows(factory: async_sessionmaker[AsyncSession], sql: str, **params: Any) -> list[Any]:
    async with role_session(factory, db_role=APP) as session:
        return list((await session.execute(text(sql), params)).mappings().all())


async def test_the_loop_appends_real_fills_dedupes_by_signature_and_derives_the_positions(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _plant(db_session_factory)
    chain = _chain()
    ctx = _context(db_session_factory, chain)
    watcher = ctx.wallets
    assert watcher is not None

    report = await wallets_once(ctx)
    assert (report.wallets, report.fills, report.unknown, report.failed) == (2, 2, 1, 1)
    assert report.calls == 5 and report.errors == 0 and report.positions == 2
    assert chain.calls.count(("tx", "FAILSIG")) == 0  # a failed signature is never fetched

    trades = await _rows(
        db_session_factory,
        "SELECT * FROM meme_wallet_trades ORDER BY block_time NULLS LAST, signature",
    )
    assert [t["signature"] for t in trades] == ["BUYSIG", "SELLSIG", "GHOST"]
    buy, sell, ghost = trades
    assert (buy["side"], buy["venue"], buy["decode"], buy["mint"]) == (
        "buy",
        "curve",
        "trade_event",
        MINT,
    )
    assert buy["sol_lamports"] == 977_777_777 and buy["fee_lamports"] == 12_310_723
    assert buy["token_amount"] == TOKENS_BOUGHT and buy["block_time"] == BUY_AT
    assert buy["hype_score"] == Decimal("0.7") and buy["line_reason"] == "flat"
    context = buy["lab_context"]
    assert context["minute"] == MINUTE.isoformat() and context["reason"] is None
    verdict = context["rule_sets"]["meme_paper_v0/1"]
    assert verdict["accepted"] is False and "creator_net_seller_unknown" in verdict["refusals"]
    active = await _rows(
        db_session_factory,
        "SELECT name || '/' || version AS label FROM meme_rule_sets WHERE status = 'active'",
    )
    assert set(context["rule_sets"]) == {str(r["label"]) for r in active}  # every active set spoke
    assert "meme_paper_v0/1" in context["rule_sets"]  # the 0022 seed is still active
    assert sell["side"] == "sell" and sell["lab_context"] is None
    assert sell["sol_lamports"] == 724_716_993 and sell["fee_lamports"] == 9_158_963
    assert (ghost["side"], ghost["decode"], ghost["block_time"]) == ("unknown", "none", None)
    assert ghost["raw"]["reason"] == "transaction_not_found" and ghost["slot"] == 446373800

    positions = {
        p["wallet"]: p
        for p in await _rows(db_session_factory, "SELECT * FROM meme_wallet_positions")
    }
    opened, orphan = positions[BUYER], positions[SELLER]
    assert opened["status"] == "open" and opened["tokens_held"] == TOKENS_BOUGHT
    assert opened["sol_spent"] == Decimal("0.9900885") and opened["buys"] == 1
    assert opened["first_buy_at"] == BUY_AT and opened["mark_source"] == "curve_snapshot"
    reserves = CurveReserves(
        virtual_sol_reserves=RESERVES_2[0], virtual_token_reserves=RESERVES_2[1]
    )
    expected_mark = quote_sell(reserves, TOKENS_BOUGHT, Decimal("1.25")).net_sol
    assert opened["mark_sol"] == expected_mark.quantize(Decimal("1.0000000000"))
    assert opened["unrealized_pnl_sol"] == opened["mark_sol"] - opened["open_cost_sol"]
    assert opened["r_multiple"] is not None and opened["mark_at"] == BUY_AT + timedelta(seconds=60)
    assert orphan["status"] == "closed" and orphan["tokens_held"] == 0
    assert orphan["unmatched_sell_tokens"] == Decimal("16800146.527261")
    assert orphan["sol_received"] == Decimal("0.71555803") and orphan["realized_pnl_sol"] == 0
    assert orphan["buys"] == 0 and orphan["first_buy_at"] is None
    assert orphan["mark_reason"] == "closed" and orphan["r_multiple"] is None

    board = await _rows(
        db_session_factory,
        "SELECT * FROM meme_lab_scoreboard_v1 WHERE kind = 'real_observed' ORDER BY name",
    )
    assert [b["name"] for b in board] == ["wallet:AsRQHoHx"]  # no first buy, no board row
    assert (board[0]["bets"], board[0]["closed"], board[0]["pnl_usd"]) == (1, 0, None)
    assert board[0]["version"] == "1" and board[0]["rule_set_status"] == "active"

    fields = watcher.heartbeat_fields(SELL_AT + timedelta(seconds=1))
    assert fields["wallets_watched"] == "2" and fields["wallets_positions_open"] == "1"
    assert fields["wallets_last_trade_at"] == SELL_AT.isoformat()

    # Second pass with the cursors forgotten: every signature comes back from the
    # node and none is written twice — dedupe is the schema's, not the process's.
    watcher.cursors.clear()
    watcher.cursors[BUYER] = None
    again = await wallets_once(ctx)
    assert (again.fills, again.unknown, again.known) == (0, 0, 1)
    count = await _rows(db_session_factory, "SELECT count(*) AS n FROM meme_wallet_trades")
    assert count[0]["n"] == 3

    # A tape print newer than the snapshot re-marks the open position by the tape
    # (the ``0021`` columns of ``meme_trades``, written directly: this test must
    # not depend on the tape puller's row shape).
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await session.execute(
            text(
                "INSERT INTO meme_trades (block_time, signature, event_index, mint, slot, "
                "  received_at, trader, side, sol_lamports, token_amount, price, quote_mint, "
                "  token_decimals, source) "
                "VALUES (:block_time, 'TAPE', 0, :mint, 446370000, :received_at, 'someone', "
                "  'buy', 1000000, 20000, 0.00000005, '11111111111111111111111111111111', 6, "
                "  'swap_api')"
            ),
            {
                "block_time": BUY_AT + timedelta(seconds=120),
                "mint": MINT,
                "received_at": BUY_AT + timedelta(seconds=121),
            },
        )
    await wallets_once(ctx)
    (marked,) = await _rows(
        db_session_factory, "SELECT * FROM meme_wallet_positions WHERE wallet = :w", w=BUYER
    )
    assert marked["mark_source"] == "tape" and marked["mark_at"] == BUY_AT + timedelta(seconds=120)
    assert marked["mark_sol"] == (TOKENS_BOUGHT * Decimal("0.00000005")).quantize(
        Decimal("1.0000000000")
    )


async def test_an_rpc_failure_is_counted_and_never_raised_and_the_app_role_only_reads(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    class Broken(FakeChain):
        async def get_signatures_for_address(
            self, address: str, *, until: str | None = None, limit: int = 100
        ) -> list[SignatureInfo]:
            raise RuntimeError("rpc down")

    ctx = _context(db_session_factory, Broken({}, {}))
    report = await wallets_once(ctx)
    assert report.errors == 2 and report.fills == 0
    assert ctx.sources is not None
    assert ctx.sources["solana_rpc"].last_error == "RuntimeError"
    async with role_session(db_session_factory, db_role=APP) as session:
        with pytest.raises(Exception, match="permission denied"):
            await session.execute(
                text("DELETE FROM meme_wallet_trades WHERE wallet = :w"), {"w": BUYER}
            )
