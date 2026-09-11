"""``backfill_breadth.py`` over ninety days of ``breadth_v2`` — the readiness proof.

T3.88, item 2 of the brief. The tool has never been run anywhere, and the number
that decides whether EXP-0027 is measurable is not an opinion: it is "how many
minutes would this fold, and would they be usable". This file measures it against
a real Postgres with synthetic candles, in the tool's own default mode (dry-run,
which writes nothing), and prints what it measured so the task can report it
instead of estimating it.

**The shape of the fixture is the shape of the VPS.** Sixteen monitored
perpetuals, each with one 1-minute candle ninety days before the cut (which is
what puts them in ``breadth_v2``'s universe -- ``hunter_core.universe``) and dense
1-minute candles over the days the report covers. The remaining ~184 markets of
production are represented by four monitored perpetuals **without** old history:
they are candidates the rule must exclude, and if it stopped excluding them the
universe would be twenty and the coverage floor would be 16.

**Why three days and not ninety.** Ninety days of the real universe is
90 x 1440 x 16 = 2 073 600 candle rows; seeding that in a test would measure the
seeding. Three days is 69 120 rows, the per-day cost is what the fold is linear
in (one statement and one fold per day -- ``CHUNK_MINUTES``), and the test prints
the measured per-day figure next to the 90-day extrapolation. The extrapolation is
labelled as such, here and in the task's notes.

Run:
    uv run pytest infra/scripts/tests/test_backfill_breadth_plan.py -q -s
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models._partitions import (  # pyright: ignore[reportPrivateUsage]
    create_partition_sql,
)

if TYPE_CHECKING:
    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = Path(__file__).resolve().parents[1]

EXCHANGE = "binance"
HISTORIC = 16
"""Markets with ninety days of 1m history -- ``breadth_v2``'s universe, the number
measured on the VPS 2026-09-10."""
YOUNG = 4
"""Monitored perpetuals without it, standing in for production's other ~184."""
DAYS = 3
"""Days of dense candles, and the window the report is asked for."""
MINUTES_PER_DAY = 1_440
FLOOR_MARKETS = 13
"""``ceil(0.80 x 16)`` -- how many of the sixteen must be dense for a minute to be
usable. Written out because it is the number the report prints."""

CUT = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
"""Today's UTC midnight, and the **only** clock this test admits: the tool reads
``utcnow()`` and the fixture patches it to this instant, so ``[cut - 3d, cut)`` is
exactly three *complete* UTC days. With a wall-clock cut the first and last days of
the window would be partial, fewer than ``--dense`` minutes, and the report's "days
above the floor" would depend on the hour the suite happened to run -- a test whose
expected value moves with the clock measures the clock."""


def _load(name: str) -> ModuleType:
    """Load ``infra/scripts/<name>.py`` the way running it as a script would."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_t388", SCRIPTS_DIR / f"{name}.py"
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


async def _seed(url: str, *, cut: datetime) -> None:
    """Sixteen markets with ninety days of history, four without, dense candles.

    Everything is written with server-side ``generate_series``: 69 120 candles
    through Python would measure the driver, and this test exists to measure the
    fold.

    The partitions of the three months before the cut are created here because
    ``0001`` only creates 2026-09 through 2026-12 while production's daily
    partition job (and ``candles_1m``'s own 90-day retention, DATABASE.md §1.3)
    means the month ninety days back **does** exist there. Creating them is
    fidelity to production, not a convenience.
    """
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    old = cut - timedelta(days=90)
    try:
        async with engine.begin() as conn:
            for back in range(4):
                month = (cut - timedelta(days=31 * back)).replace(day=1)
                await conn.execute(
                    text(create_partition_sql("candles_1m", month.year, month.month))
                )
                await conn.execute(text(create_partition_sql("candles_1m", old.year, old.month)))
            exchange_id = await conn.scalar(
                text(
                    "INSERT INTO exchanges (id, code, name) VALUES (:id, :code, :code) "
                    "ON CONFLICT (code) DO UPDATE SET name = excluded.name RETURNING id"
                ),
                {"id": uuid.uuid4(), "code": EXCHANGE},
            )
            quote_id = await conn.scalar(
                text(
                    "INSERT INTO assets (id, symbol) VALUES (:id, 'USDT') "
                    "ON CONFLICT (symbol) DO UPDATE SET symbol = 'USDT' RETURNING id"
                ),
                {"id": uuid.uuid4()},
            )
            for index in range(HISTORIC + YOUNG):
                symbol = f"T{index:02d}USDT"
                base_id = await conn.scalar(
                    text("INSERT INTO assets (id, symbol) VALUES (:id, :symbol) RETURNING id"),
                    {"id": uuid.uuid4(), "symbol": f"T{index:02d}"},
                )
                market_id = await conn.scalar(
                    text(
                        "INSERT INTO markets (id, exchange_id, symbol, market_type, "
                        "  base_asset_id, quote_asset_id, is_monitored, status) "
                        "VALUES (:id, :exchange_id, :symbol, 'perpetual', :base, :quote, "
                        "  true, 'active') RETURNING id"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "exchange_id": exchange_id,
                        "symbol": symbol,
                        "base": base_id,
                        "quote": quote_id,
                    },
                )
                if index < HISTORIC:
                    await conn.execute(
                        text(
                            "INSERT INTO candles (market_id, timeframe, open_time, open, high, "
                            "  low, close, volume, is_final) VALUES (:market_id, '1m', :open_time, "
                            "  100, 100, 100, 100, 1, true)"
                        ),
                        {"market_id": market_id, "open_time": old},
                    )
                # Dense candles for the report's window. Alternating direction so
                # the fold has something to count: even markets fall, odd rise.
                await conn.execute(
                    text(
                        "INSERT INTO candles (market_id, timeframe, open_time, open, high, low, "
                        "  close, volume, is_final) "
                        "SELECT :market_id, '1m', minute, 100, 101, 99, "
                        "  CASE WHEN :falling THEN 100 - extract(epoch from (minute - :start))"
                        "       / 86400.0 ELSE 100 + extract(epoch from (minute - :start))"
                        "       / 86400.0 END, 1, true "
                        "  FROM generate_series(:start, :end, interval '1 minute') AS minute"
                    ),
                    {
                        "market_id": market_id,
                        "falling": index % 2 == 0,
                        "start": cut - timedelta(days=DAYS) - timedelta(minutes=10),
                        "end": cut,
                    },
                )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def plan_db_url(postgres_container: PostgresContainer) -> str:
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_breadth_plan")
    )
    command.upgrade(_alembic_config(url), "head")
    asyncio.run(_seed(url, cut=CUT))
    return url


@pytest.fixture
def script(plan_db_url: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The tool, pointed at the container through the settings it really reads."""
    monkeypatch.setenv("DATABASE_URL", plan_db_url)
    from hunter_core.settings import get_settings

    get_settings.cache_clear()
    module = _load("backfill_breadth")
    monkeypatch.setattr(module, "utcnow", lambda: CUT, raising=True)
    return module


def _args(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "exchange": EXCHANGE,
        "series": "breadth_v2",
        "days": DAYS,
        "dense": 1_200,
        "plan": True,
        "apply": False,
        "include_unusable": False,
        "reason": None,
    }
    return argparse.Namespace(**(base | overrides))


class TestOEnsaioDeNoventaDias:
    async def test_o_dry_run_dobra_o_universo_de_dezesseis_e_nao_grava_nada(
        self, script: ModuleType, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """O modo padrão do brief: relatório + ``--plan``, sem uma linha escrita.

        Três dias densos dos 16 mercados com 90 dias de histórico. O que este teste
        fixa, e é o item 2 do brief: (i) o universo é 16, não 20 — os quatro sem
        histórico são candidatos que a regra exclui; (ii) todos os dias do relatório
        passam o piso de 80 %, que é a diferença exata entre ``breadth_v2`` e a
        ``breadth_v1`` que reprovava 87 de 91 dias; (iii) todo minuto dobrado sai
        ``usable``; (iv) nada é gravado. O custo medido por dia é impresso para a
        extrapolação de 90 dias viver na nota da tarefa como medida, não como palpite.
        """
        started = time.monotonic()
        code = await script._run(_args())  # pyright: ignore[reportPrivateUsage]
        elapsed = time.monotonic() - started
        out = capsys.readouterr().out

        assert code == 0
        assert f"universo agora: {HISTORIC} perpétuas" in out
        assert f"-> {FLOOR_MARKETS} mercados densos por minuto" in out
        assert "série: breadth_v2  universo: monitored_perpetual_min_history_90d" in out
        assert "[dry-run] nada foi gravado" in out
        assert "insufficient_coverage" not in out
        # Every day of the window cleared the floor, which is the claim T3.88 makes.
        assert f"dias que passariam o piso de cobertura: {DAYS} de {DAYS}" in out
        assert f"minutos sem linha na janela: {DAYS * MINUTES_PER_DAY}" in out
        minutes = DAYS * MINUTES_PER_DAY
        per_day = elapsed / DAYS
        print("")
        print(f"[T3.88] minutos dobrados em {DAYS} dias: ~{minutes}")
        print(f"[T3.88] duração medida: {elapsed:.1f} s ({per_day:.1f} s/dia)")
        print(f"[T3.88] extrapolação para 90 dias (129 600 min): {per_day * 90 / 60:.1f} min")

    async def test_gravar_exige_motivo_e_o_relatorio_vem_antes(
        self, script: ModuleType, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--apply`` sem ``--reason`` é recusado **antes** de abrir o banco: a
        linha de ``audit_logs`` é parte do write, não um enfeite dele."""
        code = await script._run(  # pyright: ignore[reportPrivateUsage]
            _args(apply=True, plan=False)
        )
        assert code == 1
        assert "RECUSADO: --apply exige --reason" in capsys.readouterr().err

    async def test_a_serie_v1_sobre_o_mesmo_banco_reprova_todos_os_dias(
        self, script: ModuleType, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A prova de que a mudança é o universo e não o piso: ``--series
        breadth_v1`` vê 20 mercados monitorados, precisa de 16 densos e tem 20 — os
        quatro jovens também são densos nesta janela, então v1 **passa** aqui. O que
        muda é o denominador, e é por isso que na VPS (16 densos de 200) v1
        reprovava: o teste que pode ser escrito localmente é o de que as duas séries
        leem universos de tamanhos diferentes, com o mesmo piso.
        """
        code = await script._run(  # pyright: ignore[reportPrivateUsage]
            _args(series="breadth_v1")
        )
        out = capsys.readouterr().out
        assert code == 0
        assert f"universo agora: {HISTORIC + YOUNG} perpétuas" in out
        assert "série: breadth_v1  universo: monitored_perpetual" in out
        assert "-> 16 mercados densos por minuto" in out


class TestOApplyDeUmDia:
    """``--apply`` sobre um dia, porque a taxa de escrita é o custo real na VPS.

    Fica na última classe do arquivo de propósito: é a única que escreve, e as
    leituras acima contam os minutos **sem linha** — rodar esta antes mudaria o
    número que elas medem. Uma dependência de ordem declarada é melhor que um
    banco por teste com uma migração inteira cada.
    """

    async def test_grava_um_dia_de_breadth_v2_com_uma_linha_de_auditoria(
        self, script: ModuleType, plan_db_url: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        started = time.monotonic()
        code = await script._run(  # pyright: ignore[reportPrivateUsage]
            _args(days=1, plan=False, apply=True, reason="T3.88 ensaio de prontidão")
        )
        elapsed = time.monotonic() - started
        out = capsys.readouterr().out
        assert code == 0
        assert f"linhas gravadas: {MINUTES_PER_DAY}" in out
        assert "audit_logs: uma linha market_breadth.backfill gravada" in out

        engine = create_async_engine(plan_db_url, connect_args={"statement_cache_size": 0})
        try:
            async with engine.connect() as conn:
                rows = await conn.scalar(
                    text("SELECT count(*) FROM market_breadth WHERE breadth_version = 'breadth_v2'")
                )
                usable = await conn.scalar(
                    text("SELECT count(*) FROM market_breadth WHERE usable AND value IS NOT NULL")
                )
                universe = await conn.scalar(
                    text("SELECT DISTINCT universe_size FROM market_breadth")
                )
                rule = await conn.scalar(
                    text("SELECT DISTINCT inputs->>'universe_rule' FROM market_breadth")
                )
                audits = await conn.scalar(
                    text("SELECT count(*) FROM audit_logs WHERE action = 'market_breadth.backfill'")
                )
        finally:
            await engine.dispose()

        assert rows == MINUTES_PER_DAY
        assert usable == MINUTES_PER_DAY
        assert universe == HISTORIC
        assert rule == "monitored_perpetual_min_history_90d"
        assert audits == 1
        per_minute = elapsed / MINUTES_PER_DAY
        print("")
        print(f"[T3.88] --apply de 1 dia: {MINUTES_PER_DAY} linhas em {elapsed:.1f} s")
        print(
            f"[T3.88] extrapolação de --apply para 129 600 min: {per_minute * 129_600 / 60:.1f} min"
        )
