"""T4.25 contra um Postgres de verdade em ``head`` — um arquivo, um contêiner.

O que só um banco prova: que a exportação roda como ``hunter_app`` (a leitura
que a VPS faz), que ela lê as colunas de linha da ``meme_features_v3``, a série
de 15 s e as fotografias **só dentro da janela da aposta** e só do mint dela, e
que as notas escritas a partir daquele JSONL deixam uma cópia do vault limpa no
``obsidian_lint.py``.

Rodar sozinho (testcontainers):
    timeout 590 uv run pytest infra/scripts/tests/test_meme_render_bets_integration.py -q
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
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

from hunter_core.settings import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection
    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

DAY = "2026-10-05"
ENTRY = datetime(2026, 10, 5, 12, 0, 35, tzinfo=UTC)
"""09:00:35 BRT de um dia dentro das partições iniciais de 2026-10."""
EXIT = ENTRY + timedelta(minutes=6)
MINUTE = ENTRY.replace(second=0)
MINT = "RENDERmint1111111111111111111111111111pump"
OTHER = "OTHERmint22222222222222222222222222222pump"
RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000425"
PLAN = "Comprar 0,05 SOL de WIF até 09:03:00 (proposta expira)."
PARAMS: dict[str, Any] = {
    "size_sol": "0.05",
    "target_x": "3",
    "trailing_pct": "35",
    "max_hold_s": 1800,
    "max_loss_pct": "50",
    "exit_on_line_break": True,
    "clock": "15s",
}
REASONS = {
    "progress_reason": "denominator_unknown",
    "unique_buyers_reason": "no_trade_feed",
    "buy_sell_ratio_reason": "no_trade_feed",
    "top10_share_reason": "no_holders_reader",
    "creator_sold_reason": "no_trade_feed",
    "holders_reason": "no_holders_reader",
    "dev_share_reason": "no_holders_reader",
    "snipers_reason": "no_trade_feed",
    "tape_reason": "no_trade_feed",
    "creator_net_seller_reason": "no_trade_feed",
    "hype_reason": "no_tape_no_board",
}
"""Todo valor ausente carrega o motivo que o CHECK bicondicional exige — a
fixture não pode mentir dizendo zero onde ninguém mediu."""


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


def _alembic_config(url: str) -> Config:
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


@pytest.fixture(scope="module")
def render_db_url(postgres_container: PostgresContainer) -> str:
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_meme_render")
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


_MINUTE_SQL = text(
    "INSERT INTO meme_features_1m (end_time, mint, features_version, coverage, mcap_sol, "
    "  progress_reason, unique_buyers_reason, buy_sell_ratio_reason, top10_share_reason, "
    "  creator_sold_reason, holders_reason, dev_share_reason, snipers_reason, tape_reason, "
    "  creator_net_seller_reason, hype_reason, line_points, support_line_sol, "
    "  support_line_slope, higher_lows, distance_to_support_pct, high_15m_sol, low_15m_sol, "
    "  breakout_15m, line_reason) "
    "VALUES (:end_time, :mint, 'meme_features_v3', 1, :mcap, :progress_reason, "
    "  :unique_buyers_reason, :buy_sell_ratio_reason, :top10_share_reason, :creator_sold_reason, "
    "  :holders_reason, :dev_share_reason, :snipers_reason, :tape_reason, "
    "  :creator_net_seller_reason, :hype_reason, :points, :support, :slope, :higher, :distance, "
    "  :high, :low, :breakout, :line_reason)"
)
_FAST_SQL = text(
    "INSERT INTO meme_features_15s (as_of, mint, features_version, snapshots_120s, age_s, "
    "  snapshot_observed_at, snapshot_source, mcap_sol, window_reason, progress_reason, "
    "  holders_reason, tape_reason, creator_net_seller_reason, dev_share_reason, snipers_reason) "
    "VALUES (:as_of, :mint, 'meme_features_15s_v1', 8, 240, :as_of, 'pumpfun_rest', :mcap, "
    "  'too_few_points', 'denominator_unknown', 'no_holders_reader', 'no_trade_feed', "
    "  'no_trade_feed', 'no_holders_reader', 'no_trade_feed')"
)
_SNAP_SQL = text(
    "INSERT INTO meme_curve_snapshots (observed_at, mint, source, received_at, "
    "  virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, real_token_reserves, "
    "  total_supply, complete) "
    "VALUES (:at, :mint, 'pumpfun_rest', :at, :vsol, 1000000000, 10, 700000000, 1000000000, false)"
)


async def _line_minute(
    connection: AsyncConnection, *, end_time: datetime, mint: str, mcap: str, **line: Any
) -> None:
    await connection.execute(
        _MINUTE_SQL, {"end_time": end_time, "mint": mint, "mcap": mcap, **REASONS, **line}
    )


TRACED: dict[str, Any] = {
    "points": 7,
    "support": "104",
    "slope": "2",
    "higher": True,
    "distance": "0.05",
    "high": "121",
    "low": "95",
    "breakout": True,
    "line_reason": None,
}
UNTRACEABLE: dict[str, Any] = {
    "points": 2,
    "support": None,
    "slope": None,
    "higher": None,
    "distance": None,
    "high": None,
    "low": None,
    "breakout": None,
    "line_reason": "too_few_points",
}


async def _plant(url: str) -> str:
    """Uma aposta medida e uma indeterminada, com fita dentro e fora da janela."""
    bet_id = str(uuid4())
    async with _owner(url) as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "VALUES (:id, 'flow_v2', '9', 'research_only', CAST(:params AS jsonb), "
                "  'hunter_indicators.meme.rules@sha256:test', 'EXP-M5')"
            ),
            {"id": RULE_SET_ID, "params": json.dumps(PARAMS)},
        )
        for mint, symbol in ((MINT, "WIF"), (OTHER, "BONK")):
            await connection.execute(
                text(
                    "INSERT INTO meme_tokens (mint, symbol, creator, created_at, "
                    "  first_seen_source, first_seen_at, last_seen_at) "
                    "VALUES (:mint, :symbol, 'creator-1', :at, 'pumpportal_ws', :at, :at)"
                ),
                {"mint": mint, "symbol": symbol, "at": ENTRY - timedelta(minutes=9)},
            )
        # Dentro da janela: dois minutos do mint da aposta (um com linha, um sem)
        # e um minuto do **outro** mint no mesmo instante.
        await _line_minute(
            connection, end_time=MINUTE - timedelta(minutes=1), mint=MINT, mcap="115", **TRACED
        )
        await _line_minute(connection, end_time=MINUTE, mint=MINT, mcap="120.5", **TRACED)
        await _line_minute(connection, end_time=MINUTE, mint=OTHER, mcap="999", **UNTRACEABLE)
        # Fora da janela (30 min antes da entrada): não pode ser exportado.
        await _line_minute(
            connection, end_time=MINUTE - timedelta(minutes=30), mint=MINT, mcap="42", **TRACED
        )
        for i in range(4):
            await connection.execute(
                _FAST_SQL,
                {"as_of": ENTRY + timedelta(seconds=15 * i), "mint": MINT, "mcap": str(120 + i)},
            )
        for i in range(3):
            await connection.execute(
                _SNAP_SQL, {"at": ENTRY + timedelta(minutes=i), "mint": MINT, "vsol": 30 + i}
            )
        await connection.execute(
            _SNAP_SQL,
            {"at": ENTRY - timedelta(minutes=30), "mint": MINT, "vsol": 12},
        )
        await _plant_bet(connection, bet_id, "a", "measured", "line_broken", "-0.0403")
        await _plant_bet(connection, str(uuid4()), "b", "indeterminate", "rug_no_snapshot", "-1")
    return bet_id


@pytest.fixture(scope="module")
def planted(render_db_url: str) -> str:
    """As duas apostas, plantadas uma vez para os três testes deste arquivo."""
    return asyncio.run(_plant(render_db_url))


async def _plant_bet(
    connection: AsyncConnection, bet_id: str, suffix: str, quality: str, reason: str, r: str
) -> None:
    proposal_id = str(uuid4())
    await connection.execute(
        text(
            "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
            "  expires_at, features_end_time, suggested, decision, decided_by, decided_at) "
            "VALUES (:id, :mint, :rule_set, 'rules', 'approved', :proposed_at, :expires_at, "
            "  :minute, CAST(:suggested AS jsonb), '{}'::jsonb, 'rules', :proposed_at)"
        ),
        {
            "id": proposal_id,
            "mint": MINT,
            "rule_set": RULE_SET_ID,
            "proposed_at": ENTRY - timedelta(seconds=20),
            "expires_at": ENTRY + timedelta(minutes=2),
            # Um índice único cobre (conjunto, mint, minuto) para `rules`: a
            # segunda aposta do mesmo mint nasce de outro minuto, como no laço.
            "minute": MINUTE if suffix == "a" else MINUTE + timedelta(minutes=30),
            "suggested": json.dumps({"manual_plan": PLAN}),
        },
    )
    entry_payload = '{"snapshot": {"mcap_sol": "120.5"}, "sol_spent": "0.05", "tokens": "1000"}'
    exit_payload = (
        f'{{"reason": "{reason}", "snapshot": {{"mcap_sol": "104.25"}}}}'
        if quality == "measured"
        else f'{{"reason": "{reason}", "snapshot": null}}'
    )
    await connection.execute(
        text(
            "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, status, entry_at, "
            "  entry, initial_risk_sol, params, exit_at, exit, pnl_sol, r_multiple, high_water_x, "
            "  creator_sold_seen_at, creator_sold_fraction, outcome_quality, "
            "  outcome_quality_reason, outcome_quality_at) "
            "VALUES (:id, :proposal, :rule_set, :mint, 'closed', :entry_at, "
            "  CAST(:entry AS jsonb), 0.05, CAST(:params AS jsonb), :exit_at, "
            "  CAST(:exit AS jsonb), :pnl, :r, 1.08, :creator_at, :creator_share, :quality, "
            "  :q_reason, :q_at)"
        ),
        {
            "id": bet_id,
            "proposal": proposal_id,
            "rule_set": RULE_SET_ID,
            "mint": MINT,
            "entry_at": ENTRY if suffix == "a" else ENTRY + timedelta(minutes=30),
            "entry": entry_payload,
            "params": json.dumps(PARAMS),
            "exit_at": EXIT if suffix == "a" else EXIT + timedelta(minutes=30),
            "exit": exit_payload,
            "pnl": Decimal(r) * Decimal("0.05"),
            "r": Decimal(r),
            "creator_at": ENTRY + timedelta(minutes=3) if suffix == "a" else None,
            "creator_share": Decimal("0.83") if suffix == "a" else None,
            "quality": quality,
            "q_reason": None if quality == "measured" else "no_snapshot_in_window",
            "q_at": None if quality == "measured" else EXIT,
        },
    )
    await connection.execute(
        text("UPDATE meme_proposals SET status = 'filled', bet_id = :bet WHERE id = :id"),
        {"bet": bet_id, "id": proposal_id},
    )


def _export(url: str, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> list[dict[str, Any]]:
    from meme_render_bets_query import gather_day

    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        return asyncio.run(gather_day(date.fromisoformat(DAY), **kwargs))
    finally:
        get_settings.cache_clear()


def test_the_export_reads_as_hunter_app_only_the_window_and_only_this_mint(
    render_db_url: str, planted: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = _export(render_db_url, monkeypatch)
    assert planted, "a aposta medida foi plantada"

    assert len(records) == 1, "a indeterminada fica de fora por padrão"
    row = records[0]
    assert row["rule_set"] == "flow_v2/9" and row["symbol"] == "WIF"
    assert row["exp_ref"] == "EXP-M5" and row["manual_plan"] == PLAN
    assert row["entry_mcap_sol"] == "120.5" and row["exit_mcap_sol"] == "104.25"
    assert row["exit_reason"] == "line_broken"
    assert Decimal(row["r_multiple"]) == Decimal("-0.0403")
    assert Decimal(row["high_water_x"]) == Decimal("1.08")
    assert row["creator_sold_seen_at"].startswith("2026-10-05T12:03:35")
    assert row["outcome_quality"] == "measured"

    minutes = row["features_1m"]
    assert len(minutes) == 2, "só os minutos do mint dentro da janela"
    assert {m["end_time"] for m in minutes} == {
        (MINUTE - timedelta(minutes=1)).isoformat(),
        MINUTE.isoformat(),
    }
    assert Decimal(minutes[-1]["support_line_sol"]) == Decimal("104")
    assert Decimal(minutes[-1]["support_line_slope"]) == Decimal("2")
    assert minutes[-1]["breakout_15m"] is True and minutes[-1]["higher_lows"] is True
    assert minutes[-1]["line_reason"] is None
    assert Decimal(minutes[-1]["high_15m_sol"]) == Decimal("121")

    assert len(row["features_15s"]) == 4
    assert Decimal(row["features_15s"][0][1]) == Decimal("120")
    # mcap gerado pelo banco: 30/1e9 × 1e9 = 30 SOL, e a foto de 30 min antes
    # está fora da janela.
    assert len(row["snapshots"]) == 3
    assert Decimal(row["snapshots"][0][2]) == Decimal("30")
    assert row["snapshots"][0][1] == "pumpfun_rest"


def test_the_indeterminate_close_comes_back_labelled_when_it_is_asked_for(
    render_db_url: str, planted: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert planted
    records = _export(render_db_url, monkeypatch, with_indeterminate=True)
    assert len(records) == 2
    bad = [r for r in records if r["outcome_quality"] == "indeterminate"]
    assert len(bad) == 1
    assert bad[0]["exit_reason"] == "rug_no_snapshot"
    assert bad[0]["exit_mcap_sol"] is None, "sem fotografia não há preço de saída"
    assert bad[0]["outcome_quality_reason"] == "no_snapshot_in_window"
    assert _export(render_db_url, monkeypatch, rule_set="flow_v2/0") == []


def test_the_notes_leave_a_copy_of_the_vault_clean_in_the_linter(
    render_db_url: str, planted: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import meme_render_bets_notes as notes_mod
    from meme_render_bets_model import parse_bet

    assert planted

    records = _export(render_db_url, monkeypatch, with_indeterminate=True)
    vault = tmp_path / "obsidian"
    shutil.copytree(REPO_ROOT / "obsidian", vault)
    monkeypatch.setattr(notes_mod, "VAULT", vault)
    monkeypatch.setattr(notes_mod, "SETS_DIR", vault / "03-TRADING" / "Meme" / "Apostas-tracadas")
    monkeypatch.setattr(notes_mod, "DIARY_DIR", vault / "09-OPERATIONS" / "Diario-Meme")
    monkeypatch.setattr(notes_mod, "ATTACH", vault / "attachments" / "meme")
    monkeypatch.setattr(notes_mod, "MEME_README", vault / "03-TRADING" / "Meme" / "README.md")

    written = notes_mod.write_notes([parse_bet(r) for r in records])
    assert (vault / "03-TRADING" / "Meme" / "Apostas-tracadas" / "flow_v2-9.md") in written
    page = (vault / "03-TRADING" / "Meme" / "Apostas-tracadas" / "flow_v2-9.md").read_text(
        encoding="utf-8"
    )
    assert "[[EXP-M5-fluxo-e-holders]]" in page and f"## Dia {DAY}" in page

    from obsidian_lint import lint

    report, code = lint(vault, "text", True)
    assert code == 0, report
