"""T4.92 against a real Postgres at ``head`` — one file, one container.

What only a database can prove: ``meme_daily_ficha_queries.gather_day`` joins
``meme_live_positions`` to its proposal, rule set, token, buy/sell fills,
decision tape (``docs/DATABASE.md`` §64's ``mint = p.mint AND as_of =
p.features_end_time``) and ``meme_trades`` (the ``golpe_do_criador`` slot
rule) correctly, and that ``meme_daily_ficha_render.render_day`` turns the
result into the golden Markdown the brief describes — every one of the five
loss classes, in one seeded day.

Run alone (testcontainers):
    timeout 590 uv run pytest infra/scripts/tests/test_meme_daily_ficha_integration.py -q
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection
    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_daily_ficha_queries import gather_day  # noqa: E402
from meme_daily_ficha_render import Ficha, render_day  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
DAY = "2026-10-05"
DAY_START = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)  # 2026-10-05 00:00 BRT
LAMPORTS = Decimal(1_000_000_000)


def _alembic_config(url: str) -> Config:
    import os

    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


async def _create_database(admin_url: str, name: str) -> str:
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()
    return admin_url.rsplit("/", 1)[0] + "/" + name


@pytest.fixture(scope="module")
def ficha_db_url(postgres_container: PostgresContainer) -> str:
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_daily_ficha")
    )
    command.upgrade(_alembic_config(url), "head")
    return url


@asynccontextmanager
async def _owner(url: str) -> AsyncGenerator[AsyncConnection, None]:
    engine = create_async_engine(url, poolclass=NullPool, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            yield connection
    finally:
        await engine.dispose()


async def _rule_set_id(connection: AsyncConnection, name: str) -> str:
    value = await connection.scalar(
        text(
            "SELECT id::text FROM meme_rule_sets WHERE name = :name AND status = 'active' "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"name": name},
    )
    assert value is not None, f"seeded rule set {name!r} not found"
    return value


async def _plant_token(
    connection: AsyncConnection, mint: str, symbol: str, *, created_at: datetime
) -> None:
    await connection.execute(
        text(
            "INSERT INTO meme_tokens (mint, symbol, created_at, first_seen_source, first_seen_at, "
            "  last_seen_at, initial_real_token_reserves, progress_denominator_source, total_supply) "
            "VALUES (:mint, :symbol, :created_at, 'pumpportal_ws', :created_at, :created_at, "
            "  793100000, 'observed_virgin', 1000000000)"
        ),
        {"mint": mint, "symbol": symbol, "created_at": created_at},
    )


def _fill(
    *, fee: int, creator_fee: int, network_fee_lamports: int, ata_rent_refund: int | None = None
) -> str:
    import json

    payload: dict[str, Any] = {
        "fee": fee,
        "creator_fee": creator_fee,
        "network_fee_lamports": network_fee_lamports,
    }
    if ata_rent_refund is not None:
        payload["ata_rent_refund_lamports"] = ata_rent_refund
    return json.dumps(payload)


async def _plant_position(
    connection: AsyncConnection,
    *,
    mint: str,
    rule_set_id: str,
    entry_at: datetime,
    exit_at: datetime | None,
    cost_lamports: int,
    received_lamports: int | None,
    high_water_sol: Decimal | None,
    exit_reason: str | None,
    pnl_sol: Decimal | None,
    features_end_time: datetime | None = None,
) -> str:
    proposal_id, entry_order_id = str(uuid4()), str(uuid4())
    await connection.execute(
        text(
            "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
            "  expires_at, features_end_time, decided_by, decided_at, mode) "
            "VALUES (:id, :mint, :rule_set, 'operator', 'approved', :proposed_at, :expires_at, "
            "  :features_end_time, 'executor:auto_stage1', :proposed_at, 'live')"
        ),
        {
            "id": proposal_id,
            "mint": mint,
            "rule_set": rule_set_id,
            "proposed_at": entry_at - timedelta(seconds=5),
            "expires_at": entry_at + timedelta(seconds=90),
            "features_end_time": features_end_time,
        },
    )
    await connection.execute(
        text(
            "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, status, "
            "  tx_signature, fill, received_at) "
            "VALUES (:id, :proposal_id, 'buy', :key, 'confirmed', :sig, CAST(:fill AS jsonb), :at)"
        ),
        {
            "id": entry_order_id,
            "proposal_id": proposal_id,
            "key": f"meme:{proposal_id}",
            "sig": f"sig-buy-{uuid4().hex[:12]}",
            "fill": _fill(fee=875_000, creator_fee=350_000, network_fee_lamports=5_000),
            "at": entry_at,
        },
    )
    exit_order_id = None
    if exit_at is not None:
        exit_order_id = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, status, "
                "  tx_signature, fill, received_at) "
                "VALUES (:id, :proposal_id, 'sell', :key, 'confirmed', :sig, CAST(:fill AS jsonb), :at)"
            ),
            {
                "id": exit_order_id,
                "proposal_id": proposal_id,
                "key": f"meme:{proposal_id}:exit:1",
                "sig": f"sig-sell-{uuid4().hex[:12]}",
                "fill": _fill(
                    fee=1_015_000,
                    creator_fee=406_000,
                    network_fee_lamports=5_000,
                    ata_rent_refund=2_039_280,
                ),
                "at": exit_at,
            },
        )
    position_id = str(uuid4())
    await connection.execute(
        text(
            "INSERT INTO meme_live_positions (id, proposal_id, entry_order_id, mint, status, "
            "  entry_at, entry, tokens, sol_spent_lamports, initial_risk_sol, params, high_water_sol, "
            "  exit_order_id, exit_at, exit, sol_received_lamports, pnl_sol, r_multiple) "
            "VALUES (:id, :proposal_id, :entry_order_id, :mint, :status, :entry_at, '{}'::jsonb, "
            "  1000000000, :cost_lamports, :cost_sol, '{}'::jsonb, :high_water_sol, "
            "  :exit_order_id, :exit_at, CAST(:exit AS jsonb), :received_lamports, :pnl_sol, :r_multiple)"
        ),
        {
            "id": position_id,
            "proposal_id": proposal_id,
            "entry_order_id": entry_order_id,
            "mint": mint,
            "status": "closed" if exit_at is not None else "open",
            "entry_at": entry_at,
            "cost_lamports": cost_lamports,
            "cost_sol": Decimal(cost_lamports) / LAMPORTS,
            "high_water_sol": high_water_sol,
            "exit_order_id": exit_order_id,
            "exit_at": exit_at,
            "exit": None if exit_reason is None else f'{{"reason": "{exit_reason}"}}',
            "received_lamports": received_lamports,
            "pnl_sol": pnl_sol,
            "r_multiple": None
            if pnl_sol is None
            else pnl_sol / (Decimal(cost_lamports) / LAMPORTS),
        },
    )
    return mint


async def _plant_sellers_in_a_slot(
    connection: AsyncConnection, mint: str, *, at: datetime, slot: int, n: int
) -> None:
    for i in range(n):
        await connection.execute(
            text(
                "INSERT INTO meme_trades (block_time, signature, event_index, mint, slot, trader, "
                "  side, sol_lamports, token_amount, price, quote_mint, token_decimals, source) "
                "VALUES (:block_time, :sig, 0, :mint, :slot, :trader, 'sell', 1000000, 1000, 0.001, "
                "  'So11111111111111111111111111111111111111112', 6, 'swap_api')"
            ),
            {
                "block_time": at,
                "sig": f"dump-{mint}-{i}",
                "mint": mint,
                "slot": slot,
                "trader": f"dumper{i}",
            },
        )


async def _plant_progress_row(
    connection: AsyncConnection,
    mint: str,
    end_time: datetime,
    *,
    progress: Decimal,
    dev_share: Decimal,
) -> None:
    """Astra (T4.92 review, HIGH): ``curve_progress_pct``/``dev_share`` are
    fractions in the schema (``ck_meme_features_1m_dev_share_is_a_fraction``,
    ``curve_progress_pct`` docstring), not already a 0-100 percentage — this
    plants a real fraction so the golden test proves the ficha's own ``* 100``
    conversion, not just that a number shows up."""
    # Every other nullable metric here is NULL *with a reason* (0021/0023's own
    # biconditional CHECKs: value NULL <=> reason NOT NULL) -- a bare NULL/NULL
    # pair is refused, so a minimal row still names why each other field is absent.
    await connection.execute(
        text(
            "INSERT INTO meme_features_1m (end_time, mint, features_version, curve_progress_pct, "
            "  curve_reason, unique_buyers_reason, buy_sell_ratio_reason, top10_share_reason, "
            "  creator_sold_reason, coverage, holders_reason, dev_share, snipers_reason, "
            "  tape_reason, creator_net_seller_reason) "
            "VALUES (:end_time, :mint, 'meme_features_v3', :progress, "
            "  'not_polled', 'not_polled', 'not_polled', 'not_polled', "
            "  'not_polled', 1, 'no_holders_reader', :dev_share, 'no_holders_reader', "
            "  'no_trade_feed', 'no_trade_feed')"
        ),
        {"end_time": end_time, "mint": mint, "progress": progress, "dev_share": dev_share},
    )


async def _plant_decision_tape(connection: AsyncConnection, mint: str, as_of: datetime) -> None:
    import json

    derived = {
        "windows": {"60s": {"buys": 79, "sells": 8, "unique_buyers": 76, "net_sol": "29.5"}},
        "creation_bundle": {"sol": "3.1", "wallets": 4},
    }
    await connection.execute(
        text(
            "INSERT INTO meme_decision_tapes (mint, as_of, series, trades, trades_in_window, derived) "
            "VALUES (:mint, :as_of, 'meme_event_gate_v1', '[]'::jsonb, 0, CAST(:derived AS jsonb))"
        ),
        {"mint": mint, "as_of": as_of, "derived": json.dumps(derived)},
    )


async def _plant_paper_bet(
    connection: AsyncConnection,
    *,
    rule_set_id: str,
    mint: str,
    entry_at: datetime,
    pnl_sol: Decimal | None,
) -> None:
    proposal_id, bet_id = str(uuid4()), str(uuid4())
    await connection.execute(
        text(
            "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
            "  expires_at, features_end_time, decided_by, decided_at) "
            "VALUES (:id, :mint, :rule_set, 'rules', 'approved', :proposed_at, :expires_at, "
            "  :proposed_at, 'rules', :proposed_at)"
        ),
        {
            "id": proposal_id,
            "mint": mint,
            "rule_set": rule_set_id,
            "proposed_at": entry_at - timedelta(seconds=5),
            "expires_at": entry_at + timedelta(seconds=90),
        },
    )
    closed = pnl_sol is not None
    await connection.execute(
        text(
            "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, status, entry_at, "
            "  entry, initial_risk_sol, params, exit_at, exit, pnl_sol, r_multiple) "
            "VALUES (:id, :proposal_id, :rule_set, :mint, :status, :entry_at, "
            "  '{\"sol_spent\": \"0.07\"}'::jsonb, 0.07, '{}'::jsonb, :exit_at, "
            "  CAST(:exit AS jsonb), :pnl, :r)"
        ),
        {
            "id": bet_id,
            "proposal_id": proposal_id,
            "rule_set": rule_set_id,
            "mint": mint,
            "status": "closed" if closed else "open",
            "entry_at": entry_at,
            "exit_at": entry_at + timedelta(minutes=1) if closed else None,
            "exit": '{"reason": "target"}' if closed else None,
            "pnl": pnl_sol,
            "r": None if pnl_sol is None else pnl_sol / Decimal("0.07"),
        },
    )
    await connection.execute(
        text("UPDATE meme_proposals SET status = 'filled', bet_id = :bet WHERE id = :id"),
        {"bet": bet_id, "id": proposal_id},
    )


async def _plant_day(url: str) -> None:
    async with _owner(url) as connection:
        operator_id = await _rule_set_id(connection, "operator")
        paper_id = await _rule_set_id(connection, "meme_paper_v0")

        # 1) RIGBY: a win — target, peak above cost.
        await _plant_token(
            connection, "RIGBY_MINT", "RIGBY", created_at=DAY_START - timedelta(hours=2)
        )
        end_time = DAY_START.replace(minute=0, second=0, microsecond=0) + timedelta(
            hours=10, minutes=58
        )
        await _plant_position(
            connection,
            mint="RIGBY_MINT",
            rule_set_id=operator_id,
            entry_at=DAY_START + timedelta(hours=10, minutes=58, seconds=35),
            exit_at=DAY_START + timedelta(hours=11, minutes=1, seconds=45),
            cost_lamports=70_000_000,
            received_lamports=81_200_000,
            high_water_sol=Decimal("0.0812"),
            exit_reason="target",
            pnl_sol=Decimal("0.0112"),
            features_end_time=end_time,
        )
        await _plant_decision_tape(connection, "RIGBY_MINT", end_time)
        await _plant_progress_row(
            connection,
            "RIGBY_MINT",
            end_time,
            progress=Decimal("0.515"),  # a fraction: rendered must be "51.5 %", not "0.5 %"
            dev_share=Decimal("0.09"),  # rendered must be "9.0 %", not "0.1 %"
        )

        # 2) AIRAA: golpe_do_criador by exit reason (creator_dump).
        await _plant_token(
            connection, "AIRAA_MINT", "AIRAA", created_at=DAY_START - timedelta(hours=3)
        )
        airaa_exit = DAY_START + timedelta(hours=17, minutes=4, seconds=2)
        await _plant_position(
            connection,
            mint="AIRAA_MINT",
            rule_set_id=operator_id,
            entry_at=DAY_START + timedelta(hours=17, minutes=3, seconds=19),
            exit_at=airaa_exit,
            cost_lamports=70_000_000,
            received_lamports=15_600_000,
            high_water_sol=Decimal("0.072"),  # rose slightly, so NOT comprou_no_topo
            exit_reason="creator_dump",
            pnl_sol=Decimal("-0.0544"),
        )

        # 3) Recompra of AIRAA_MINT, 120s after its own exit above.
        await _plant_position(
            connection,
            mint="AIRAA_MINT",
            rule_set_id=operator_id,
            entry_at=airaa_exit + timedelta(seconds=120),
            exit_at=airaa_exit + timedelta(seconds=240),
            cost_lamports=70_000_000,
            received_lamports=60_000_000,
            high_water_sol=Decimal("0.075"),
            exit_reason="dead",
            pnl_sol=Decimal("-0.010"),
        )

        # 4) DUMPX: golpe_do_criador via the chain (10 distinct sellers in one slot),
        #    exit_reason is 'dead' -- proves the meme_trades join, not the exit label.
        await _plant_token(
            connection, "DUMPX_MINT", "DUMPX", created_at=DAY_START - timedelta(hours=1)
        )
        dumpx_entry = DAY_START + timedelta(hours=12)
        dumpx_exit = dumpx_entry + timedelta(seconds=90)
        await _plant_position(
            connection,
            mint="DUMPX_MINT",
            rule_set_id=operator_id,
            entry_at=dumpx_entry,
            exit_at=dumpx_exit,
            cost_lamports=70_000_000,
            received_lamports=20_000_000,
            high_water_sol=Decimal("0.073"),
            exit_reason="dead",
            pnl_sol=Decimal("-0.0450"),
        )
        await _plant_sellers_in_a_slot(
            connection, "DUMPX_MINT", at=dumpx_entry + timedelta(seconds=18), slot=449_833_635, n=10
        )

        # 5) CUSTOX: custo -- the fixed entry/exit fees this seed always plants
        #    (0.00123 + 0.001426 SOL) minus the sell's rent refund (0.00203928 SOL)
        #    round-trip to 0.00061672 SOL; a loss smaller than that is "custo".
        await _plant_token(
            connection, "CUSTOX_MINT", "CUSTOX", created_at=DAY_START - timedelta(hours=1)
        )
        await _plant_position(
            connection,
            mint="CUSTOX_MINT",
            rule_set_id=operator_id,
            entry_at=DAY_START + timedelta(hours=15),
            exit_at=DAY_START + timedelta(hours=15, minutes=1),
            cost_lamports=70_000_000,
            received_lamports=69_600_000,
            high_water_sol=Decimal("0.075"),
            exit_reason="dead",
            pnl_sol=Decimal("-0.0004"),
        )

        # 6) NORMALX: saida_normal -- an ordinary loss, larger than round-trip cost.
        await _plant_token(
            connection, "NORMALX_MINT", "NORMALX", created_at=DAY_START - timedelta(hours=1)
        )
        await _plant_position(
            connection,
            mint="NORMALX_MINT",
            rule_set_id=operator_id,
            entry_at=DAY_START + timedelta(hours=16),
            exit_at=DAY_START + timedelta(hours=16, minutes=5),
            cost_lamports=70_000_000,
            received_lamports=52_500_000,
            high_water_sol=Decimal("0.074"),
            exit_reason="trailing",
            pnl_sol=Decimal("-0.0175"),
        )

        # Paper arms: two closed (one win, one loss) and one still open, in the same day.
        await _plant_paper_bet(
            connection,
            rule_set_id=paper_id,
            mint="PAPERW_MINT",
            entry_at=DAY_START + timedelta(hours=9),
            pnl_sol=Decimal("0.02"),
        )
        await _plant_paper_bet(
            connection,
            rule_set_id=paper_id,
            mint="PAPERL_MINT",
            entry_at=DAY_START + timedelta(hours=9, minutes=30),
            pnl_sol=Decimal("-0.01"),
        )
        await _plant_paper_bet(
            connection,
            rule_set_id=paper_id,
            mint="PAPERO_MINT",
            entry_at=DAY_START + timedelta(hours=10),
            pnl_sol=None,
        )


def test_gather_day_and_render_produce_the_golden_markdown(
    ficha_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_plant_day(ficha_db_url))
    monkeypatch.setenv("DATABASE_URL", ficha_db_url)
    from hunter_core.settings import get_settings

    get_settings.cache_clear()
    try:
        data = asyncio.run(gather_day(date.fromisoformat(DAY)))
    finally:
        get_settings.cache_clear()

    assert len(data.positions) == 6
    ficha = Ficha(
        data=data, generated_at=datetime(2026, 10, 6, 3, 0, tzinfo=UTC), git_sha="testsha1"
    )
    body = render_day(ficha)

    assert "**Operações:** 6 (6 fechadas, 0 ainda abertas)" in body
    assert "**Ganhos:** 1/6 (16 %)" in body
    assert "| ganho |" in body  # RIGBY
    assert "| comprou_no_topo |" not in body  # nobody in this seed matches it
    assert "| golpe_do_criador |" in body
    assert "| recompra |" in body
    assert "| custo |" in body
    assert "| saida_normal |" in body
    assert "## A classe de perda automática" in body
    assert "Maior vazamento do dia:**" in body
    assert "## As métricas da decisão" in body
    # RIGBY: progress 0.515 and dev_share 0.09 are fractions in the DB -- the
    # ficha must show 51.5 %/9.0 %, never 0.5 %/0.1 % (Astra's HIGH finding).
    assert "| 51.5 % | 79 | 8 | 76 | 29.50 | — (sem leitura) | 9.0 % | 3.10 / 4 |" in body
    assert "Nenhuma posição real de `spot/1` neste dia." in body
    assert "| `meme_paper_v0/1` | 3 | 1 |" in body
    assert "[[09-OPERATIONS/Diario/2026-10-05|2026-10-05]]" in body
