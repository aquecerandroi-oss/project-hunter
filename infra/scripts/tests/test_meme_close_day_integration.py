"""T4.15 against a real Postgres at ``head`` — one file, one container.

What only a database can prove: ``0031`` creates ``meme_lab_ticks`` with the
grants as the roles (``hunter_worker`` appends, ``hunter_app`` reads, nobody
deletes); one ``lab_tick`` of the real loop writes exactly one row with the
gate's refusals by name; and ``meme_close_day.py --apply`` over a day of
planted bets writes the diary with the lessons, the ``M-L`` rows, the dated
EXP evaluation, the index line and the batch proposal into a **copy** of the
vault that ``obsidian_lint.py`` then reads as clean — and refuses to close the
same day twice.

Run alone (testcontainers):
    timeout 590 uv run pytest infra/scripts/tests/test_meme_close_day_integration.py -q
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import shutil
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from hunter_core.db.session import create_engine, create_session_factory, role_session
from hunter_core.settings import Settings, get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection
    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
RESEARCH_ID = "01994d00-6c1a-7000-8000-000000000001"
DAY = "2026-10-05"
NOW = datetime(2026, 10, 5, 12, 10, 30, tzinfo=UTC)
"""09:10:30 BRT of the planted day, inside the 2026-10 partitions."""
FIRST_ENTRY = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _load_script(name: str) -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_it", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
def close_db_url(postgres_container: PostgresContainer) -> str:
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_meme_close")
    )
    command.upgrade(_alembic_config(url), "head")
    return url


@asynccontextmanager
async def _owner(url: str) -> AsyncGenerator[AsyncConnection, None]:
    """One owner transaction on an engine of its own — never a pool shared across
    ``asyncio.run`` calls (a connection outlives its loop and the proactor dies)."""
    engine = create_async_engine(url, poolclass=NullPool, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            yield connection
    finally:
        await engine.dispose()


async def _plant_day(url: str) -> None:
    """32 closed bets of the seeded EXP-M1 set over six Brasília hours: 12 same-slot
    clones of one serial creator that died at −1 R, 20 others at +0.3/−0.2; two
    operator proposals (one rejected after 45 s, one expired)."""
    operator_id = None
    async with _owner(url) as connection:
        operator_id = await connection.scalar(
            text(
                "SELECT id::text FROM meme_rule_sets WHERE name = 'operator' AND status = 'active' "
                "ORDER BY version DESC LIMIT 1"
            )
        )
        for i in range(32):
            same_slot = i < 12
            mint = f"CLOSE_{i:02d}_{uuid4().hex[:6]}"
            entry_at = FIRST_ENTRY + timedelta(hours=i % 6, minutes=i)
            # The serial creator minted its 12 clones inside one 12-minute window
            # before the first entry (``creator_prior_1h`` = i); the others 100 s
            # before their own entry.
            created_at = (
                FIRST_ENTRY - timedelta(minutes=30) + timedelta(minutes=i)
                if same_slot
                else entry_at - timedelta(seconds=100)
            )
            r = Decimal("-1") if same_slot else (Decimal("0.3") if i % 2 == 0 else Decimal("-0.2"))
            reason = "dead" if same_slot else ("target" if i % 2 == 0 else "trailing")
            await connection.execute(
                text(
                    "INSERT INTO meme_tokens (mint, symbol, creator, created_at, pool_created_at, "
                    "  pool_created_source, first_seen_source, first_seen_at, last_seen_at) "
                    "VALUES (:mint, :symbol, :creator, :created_at, :pool_at, :pool_source, "
                    "  'pumpportal_ws', :created_at, :created_at)"
                ),
                {
                    "mint": mint,
                    "symbol": "CLONE" if same_slot else f"SYM{i}",
                    "creator": "CREATOR_SERIAL" if same_slot else f"creator_{i}",
                    "created_at": created_at,
                    "pool_at": created_at if same_slot else None,
                    "pool_source": "pumpportal_ws" if same_slot else None,
                },
            )
            proposal_id, bet_id = str(uuid4()), str(uuid4())
            await connection.execute(
                text(
                    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                    "  expires_at, quote, reasons, suggested, decision, decided_by, decided_at) "
                    "VALUES (:id, :mint, :rule_set, 'operator', 'approved', :proposed_at, :expires_at, "
                    "  '{\"curve_progress_pct\": \"7\"}'::jsonb, '[]'::jsonb, '{}'::jsonb, "
                    "  '{}'::jsonb, 'rules', :proposed_at)"
                ),
                {
                    "id": proposal_id,
                    "mint": mint,
                    "rule_set": RESEARCH_ID,
                    "proposed_at": entry_at - timedelta(seconds=30),
                    "expires_at": entry_at + timedelta(seconds=90),
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, status, entry_at, "
                    "  entry, initial_risk_sol, params, exit_at, exit, pnl_sol, r_multiple) "
                    "VALUES (:id, :proposal_id, :rule_set, :mint, 'closed', :entry_at, "
                    '  \'{"sol_spent": "0.05", "tokens": "1000"}\'::jsonb, 0.05, \'{}\'::jsonb, '
                    "  :exit_at, CAST(:exit AS jsonb), :pnl, :r)"
                ),
                {
                    "id": bet_id,
                    "proposal_id": proposal_id,
                    "rule_set": RESEARCH_ID,
                    "mint": mint,
                    "entry_at": entry_at,
                    "exit_at": entry_at + timedelta(minutes=5),
                    "exit": f'{{"reason": "{reason}"}}',
                    "pnl": r * Decimal("0.05"),
                    "r": r,
                },
            )
            await connection.execute(
                text("UPDATE meme_proposals SET status = 'filled', bet_id = :bet WHERE id = :id"),
                {"bet": bet_id, "id": proposal_id},
            )
        for status, decided in (("rejected", 45), ("expired", None)):
            proposed_at = FIRST_ENTRY + timedelta(hours=2)
            await connection.execute(
                text(
                    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                    "  expires_at, features_end_time, decision, decided_by, decided_at) "
                    "VALUES (:id, :mint, :rule_set, 'rules', :status, :proposed_at, :expires_at, "
                    "  :minute, CAST(:decision AS jsonb), :by, :decided_at)"
                ),
                {
                    "id": str(uuid4()),
                    "mint": f"OPER_{status}",
                    "rule_set": operator_id,
                    "status": status,
                    "proposed_at": proposed_at,
                    "expires_at": proposed_at + timedelta(seconds=120),
                    "minute": proposed_at,
                    "decision": "{}" if decided else None,
                    "by": "user_test" if decided else None,
                    "decided_at": proposed_at + timedelta(seconds=decided) if decided else None,
                },
            )


async def _plant_gate_minute(url: str, mint: str) -> None:
    """One folded ``meme_features_1m`` row on the last closed minute before ``NOW``,
    so the real gate has something to refuse (``creator_net_seller_unknown``)."""
    from hunter_meme_worker.features import CurveObservation, MinuteInputs, build_row
    from hunter_meme_worker.repo import insert_features

    closed = NOW.replace(second=0, microsecond=0) - timedelta(minutes=1)
    observation = CurveObservation(
        observed_at=closed - timedelta(seconds=20),
        source="pumpfun_rest",
        real_token_reserves=Decimal("666100000"),
        mcap_sol=Decimal("35.94"),
        complete=False,
    )
    row = build_row(
        MinuteInputs(
            mint=mint,
            end_time=closed,
            created_at=closed - timedelta(seconds=120),
            initial_real_token_reserves=Decimal("793100000"),
            snapshot=observation,
        )
    )
    engine = create_engine(Settings(database_url=SecretStr(url)))
    try:
        async with role_session(create_session_factory(engine), db_role="hunter_worker") as session:
            await insert_features(session, [row])
    finally:
        await engine.dispose()


async def _tick(url: str) -> Any:
    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.lab import LabContext, LabState, lab_tick

    engine = create_engine(Settings(database_url=SecretStr(url)))
    try:
        ctx = LabContext(
            config=MemeConfig(enabled=True, lab_enabled=True),
            session_factory=create_session_factory(engine),
            state=LabState(),
            quotes=None,
            heartbeat=None,
        )
        first = await lab_tick(ctx, now=NOW)
        refusals = {name: dict(reasons) for name, reasons in ctx.state.refusals.items()}
        second = await lab_tick(ctx, now=NOW)  # the same instant again: nothing twice
        return first, second, refusals
    finally:
        await engine.dispose()


async def _as(url: str, role: str, sql: str, **params: Any) -> Any:
    engine = create_engine(Settings(database_url=SecretStr(url)))
    try:
        async with role_session(create_session_factory(engine), db_role=role) as session:
            return (await session.execute(text(sql), params)).mappings().all()
    finally:
        await engine.dispose()


def test_one_tick_of_the_real_loop_writes_one_row_with_the_refusals_and_the_grants_hold(
    close_db_url: str,
) -> None:
    mint = f"GATE_{uuid4().hex[:8]}"
    asyncio.run(_plant_token(close_db_url, mint))
    asyncio.run(_plant_gate_minute(close_db_url, mint))
    first, second, refusals = asyncio.run(_tick(close_db_url))
    assert first.rows_evaluated >= 1 and "meme_paper_v0" in refusals
    assert all(
        isinstance(count, int) and count >= 1
        for reasons in refusals.values()
        for count in reasons.values()
    )
    rows = asyncio.run(
        _as(
            close_db_url, "hunter_app", "SELECT * FROM meme_lab_ticks WHERE ticked_at = :at", at=NOW
        )
    )
    assert len(rows) == 1, "the same instant ticked twice writes one row"
    row = rows[0]
    assert row["rows_evaluated"] == first.rows_evaluated and row["rule_sets_active"] >= 1
    assert row["refusals"] == refusals, "the row is the heartbeat's dictionary, frozen"
    assert second.rows_evaluated == 0, "the minute is not read twice by the same process"
    with pytest.raises(DBAPIError, match="permission denied"):
        asyncio.run(
            _as(
                close_db_url,
                "hunter_app",
                "INSERT INTO meme_lab_ticks (ticked_at, minutes_evaluated, rows_evaluated, "
                "rule_sets_active, proposals, expired, cancelled, fills, unfilled, closes, bets_open) "
                "VALUES (now(), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) RETURNING ticked_at",
            )
        )
    with pytest.raises(DBAPIError, match="permission denied"):
        asyncio.run(
            _as(close_db_url, "hunter_worker", "DELETE FROM meme_lab_ticks RETURNING ticked_at")
        )


async def _plant_token(url: str, mint: str) -> None:
    async with _owner(url) as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_tokens (mint, created_at, first_seen_source, first_seen_at, "
                "  last_seen_at, initial_real_token_reserves, progress_denominator_source, total_supply) "
                "VALUES (:mint, :at, 'pumpportal_ws', :at, :at, 793100000, 'observed_virgin', 1000000000)"
            ),
            {"mint": mint, "at": NOW - timedelta(minutes=3)},
        )


def test_apply_closes_the_day_into_a_copy_of_the_vault_that_lints_clean_and_refuses_twice(
    close_db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_plant_day(close_db_url))
    monkeypatch.setenv("DATABASE_URL", close_db_url)
    get_settings.cache_clear()
    vault = tmp_path / "obsidian"
    shutil.copytree(REPO_ROOT / "obsidian", vault)
    state = tmp_path / "state"
    state.mkdir()
    exp_page = next(vault.glob("05-EXPERIMENTS/EXP-M1-*.md"))
    exp_before = exp_page.read_text(encoding="utf-8")
    module = _load_script("meme_close_day")
    args = argparse.Namespace(
        day=DAY, apply=True, allow_empty=False, vault_root=str(vault), state_dir=str(state)
    )
    try:
        assert asyncio.run(module._run(args)) == 0  # type: ignore[reportPrivateUsage]
    finally:
        get_settings.cache_clear()

    diary = (vault / "09-OPERATIONS" / "Diario-Meme" / f"{DAY}.md").read_text(encoding="utf-8")
    assert "## 6. O que o Lab aprendeu" in diary and "(a preencher" not in diary
    assert "Apostas fechadas do dia: n = 32" in diary
    assert "| `meme_paper_v0/1` | dead | 12 |" in diary
    assert "| todos | mesmo slot (pool ≤ 1 s após a criação) | 12 |" in diary
    assert "criador em série (≥ 2 moedas na hora anterior) | 10 |" in diary
    assert "amanhã o lote propõe um braço irmão que exclui mesmo slot" in diary
    assert "1 ticks entre 09:10:30 e 09:10:30 BRT" in diary
    assert "- Recusas de `" in diary or "nenhuma recusa registrada nos ticks do dia" in diary
    assert (
        "propostas pelo laço 2 (conjunto `operator`): aprovadas 0, rejeitadas 1, expiradas sem aval 1"
        in diary
    )
    assert "mediana 45 s" in diary
    assert "- **EXP-M1** (`meme_paper_v0/1`): hoje n = 32" in diary
    inbox = (vault / "00-INBOX" / "Hipoteses-do-plantao.md").read_text(encoding="utf-8")
    assert f"fechamento diário T4.15, dia {DAY}" in inbox and "**M-L1**" in inbox
    assert "`same_slot` ∈ mesmo slot" in inbox
    exp_after = exp_page.read_text(encoding="utf-8")
    assert f"### Avaliação de {DAY} — fechamento diário (T4.15)" in exp_after
    assert exp_after.startswith(exp_before.split("## Variantes tentadas")[0].rstrip("\n"))
    readme = (vault / "09-OPERATIONS" / "Diario-Meme" / "README.md").read_text(encoding="utf-8")
    assert f"[[09-OPERATIONS/Diario-Meme/{DAY}|{DAY}]] — 32 apostas fechadas" in readme
    lote = (state / "lote-meme-2026-10-06.md").read_text(encoding="utf-8")
    assert "manter (n 32/100, dias 1/30)" in lote and "`same_slot`" in lote

    from obsidian_lint import lint
    from obsidian_lint_rules import Note, check_exp_rewrite

    report, code = lint(vault, "text", True)
    assert code == 0, report
    findings, checked = check_exp_rewrite(
        Note(f"05-EXPERIMENTS/{exp_page.name}", exp_page, exp_after), lambda _path: exp_before
    )
    assert checked and findings == [], "the evaluation was appended, nothing rewritten"

    monkeypatch.setenv("DATABASE_URL", close_db_url)
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit) as refused:
            asyncio.run(module._run(args))  # type: ignore[reportPrivateUsage]
    finally:
        get_settings.cache_clear()
    assert refused.value.code == 2
