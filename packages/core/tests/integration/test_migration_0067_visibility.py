"""``0067_meme_token_state_history`` × the H-022 export (``export_h022.sql``) — its own database.

"Known at L" is *stamped at commit no later than L*; two exports inside ``[L, L + 1 h]``
must read the same state at L. What can break that is a writer whose stamp is ``<= L``
and whose commit is not yet visible when an export takes its snapshot. The export's
first statement proves visibility (the oldest writing transaction still in flight,
read before the data snapshot) and the reading refuses an export without that proof.

Proved here, against the real schema and ``pg_stat_activity``: (1) a batch opened before
L and still open at the first export — that export is refused, the one after the commit
is accepted and reads the same state at L; (2) Astra's boundary (J round 4): a commit held
*after* its stamp (``<= L``) and *before* its visibility — the export taken in between
would read L differently, and it is the one refused; the export after the commit reads
the stamped value; (3) a writer with ``track_activities`` off (xid visible, start hidden)
refuses the export; (4) ``MEMBER`` of ``pg_read_all_stats`` without inheritance is no proof
(only ``USAGE`` is) — Astra, J round 5.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_meme_worker.repo_rows import TokenRow
from hunter_meme_worker.repo_token_sql import UPSERT_TOKEN
from infra.research.exp_m26.estado_token import (
    ExportSemProvaDeVisibilidade,
    de_registro,
    em,
    prova_de_registro,
    provar_visibilidade,
)

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

REVISION = "0067_meme_token_state_history"
T = datetime(2026, 10, 5, 12, tzinfo=UTC)
C = "01994d00-6c1a-7000-8000-00000000001f"
"""grafico_ctrl_v1/1's id: the export reads only the three EXP-M26 arms. At this revision
the arm does not exist (the seed is ``0068``), so a stand-in is planted under the id."""
_SQL = (REPO_ROOT / "infra" / "research" / "exp_m26" / "export_h022.sql").read_text("utf-8")
_STATEMENTS = [s for s in re.split(r";\s*\n", _SQL) if "SELECT" in s]
_HOLD = (
    "CREATE FUNCTION h67_hold_commit() RETURNS trigger LANGUAGE plpgsql AS "
    "$$ BEGIN PERFORM pg_sleep(2); RETURN NULL; END $$",
    "CREATE CONSTRAINT TRIGGER zzzz_h67_hold_commit AFTER UPDATE ON meme_tokens "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.mint = 'H67held') "
    "EXECUTE FUNCTION h67_hold_commit()",
)
"""Fires after the history trigger (deferred events of one row run in trigger-name order):
the commit is stamped, then held 2 s, then becomes visible."""


@pytest.fixture(scope="module")
def upgraded(container_url: str) -> Iterator[str]:
    url = asyncio.run(create_database(container_url, "hunter_migration_0067_visibility"))
    command.upgrade(alembic_config(url), REVISION)
    yield url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    async with created.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, "
                "status) VALUES (:id, 'h67_stand_in', '1', 'research_only', '{}'::jsonb, 'x', "
                "'EXP-M26', 'active')"
            ),
            {"id": C},
        )
    try:
        yield created
    finally:
        async with created.begin() as connection:
            await connection.execute(
                text("DROP TRIGGER IF EXISTS zzzz_h67_hold_commit ON meme_tokens")
            )
            await connection.execute(text("DROP FUNCTION IF EXISTS h67_hold_commit()"))
            await connection.execute(text("DELETE FROM meme_mature_opportunities"))
            await connection.execute(text("DELETE FROM meme_rule_sets WHERE id = :id"), {"id": C})
            await connection.execute(text("SET LOCAL app.meme_retention = 'on'"))
            await connection.execute(text("DELETE FROM meme_tokens WHERE mint LIKE 'H67%'"))
        await created.dispose()


def _token(mint: str, **values: Any) -> TokenRow:
    return TokenRow(
        mint=mint, first_seen_source="pumpportal_ws", first_seen_at=T, last_seen_at=T, **values
    )


async def _upsert(engine: AsyncEngine, row: TokenRow) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        await connection.execute(UPSERT_TOKEN, asdict(row))


async def _opportunity(engine: AsyncEngine, mint: str) -> None:
    """A token already completed at T + 2 h, with an opportunity of the stand-in C."""
    await _upsert(engine, _token(mint, completed_at=T + timedelta(hours=2)))
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_mature_opportunities (id, rule_set_id, mint, evaluated_at, "
                "features_end_time, features_version, code_ref, inputs, gate, coverage_version, "
                "coverage_status, coverage, proposal_refusals, no_proposal_reason, lane_since) "
                "VALUES (gen_random_uuid(), :rs, :m, :t, :t, 'v3', 'x', '{}'::jsonb, '[]'::jsonb, "
                "'v1', 'covered', '{}'::jsonb, ARRAY['creator_serial'], 'refused', :t)"
            ),
            {"rs": C, "m": mint, "t": T},
        )


async def _export(engine: AsyncEngine) -> tuple[dict[str, Any], dict[str, Any]]:
    """As ``psql`` runs the file: each statement in its own read-only transaction."""
    rows: list[dict[str, Any]] = []
    for statement in _STATEMENTS:
        async with engine.begin() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            rows += [json.loads(r[0]) for r in await connection.execute(text(statement))]
    assert {r["tipo"] for r in rows} == {"meta", "braco", "oportunidade", "estado_token"}
    ((meta,), (estado,)) = ([r for r in rows if r["tipo"] == t] for t in ("meta", "estado_token"))
    return meta, estado


def _proof(meta: dict[str, Any], leitura: datetime) -> None:
    provar_visibilidade(prova_de_registro(meta), leitura=leitura)


async def _meta(engine: AsyncEngine, role: str | None = None) -> dict[str, Any]:
    async with engine.begin() as connection:
        if role is not None:
            await connection.execute(text(f"SET LOCAL ROLE {role}"))
        return json.loads(await connection.scalar(text(_STATEMENTS[0])))


async def _clock(engine: AsyncEngine) -> datetime:
    async with engine.connect() as connection:
        return await connection.scalar(text("SELECT clock_timestamp()"))


async def test_an_export_with_a_writer_open_since_before_l_is_refused(engine: AsyncEngine) -> None:
    mint = "H67open"
    await _opportunity(engine, mint)
    async with engine.connect() as batch:
        await batch.begin()
        await batch.execute(text("SET LOCAL ROLE hunter_worker"))
        await batch.execute(UPSERT_TOKEN, asdict(_token(mint, completed_at=T)))  # before L
        leitura = await _clock(engine)
        meta_l, em_l = await _export(engine)  # the batch is still open
        await batch.commit()  # after L: stamped after L
    meta, depois = await _export(engine)
    with pytest.raises(ExportSemProvaDeVisibilidade, match="em voo"):
        _proof(meta_l, leitura)
    _proof(meta, leitura)
    assert len(em_l["historico"]) == 1 and len(depois["historico"]) == 2
    assert em(de_registro(em_l), leitura) == em(de_registro(depois), leitura)
    v = em(de_registro(depois), leitura)
    assert (v.completed_at, v.via) == (T + timedelta(hours=2), "history")


async def test_a_commit_held_between_its_stamp_and_its_visibility_refuses_the_export_between(
    engine: AsyncEngine,
) -> None:
    mint = "H67held"
    await _opportunity(engine, mint)
    async with engine.begin() as connection:
        for statement in _HOLD:
            await connection.execute(text(statement))
    async with engine.connect() as batch:
        await batch.begin()
        await batch.execute(text("SET LOCAL ROLE hunter_worker"))
        await batch.execute(UPSERT_TOKEN, asdict(_token(mint, completed_at=T)))
        committing = asyncio.create_task(batch.commit())  # stamped now, visible in ~2 s
        await asyncio.sleep(0.8)
        leitura = await _clock(engine)
        meta_between, between = await _export(engine)
        await committing
    meta, after = await _export(engine)
    stamped = [m for m in de_registro(after).historico if m.depois == T]
    assert len(stamped) == 1 and stamped[0].registrado_em <= leitura, "stamped before L"
    assert len(between["historico"]) == 1, "not yet visible to the export between"
    with pytest.raises(ExportSemProvaDeVisibilidade):
        _proof(meta_between, leitura)
    assert em(de_registro(between), leitura).completed_at == T + timedelta(hours=2)
    _proof(meta, leitura)
    assert em(de_registro(after), leitura).completed_at == T, "the accepted export reads it"


async def test_a_writer_that_hides_its_start_refuses_the_export(engine: AsyncEngine) -> None:
    """Astra (J round 5): with ``track_activities`` off a writer keeps its xid in
    ``pg_stat_activity`` but shows no ``xact_start``; ``min()`` would skip it."""
    async with engine.connect() as batch:
        await batch.execute(text("SET track_activities = off"))
        await batch.commit()
        await batch.begin()
        await batch.execute(text("SET LOCAL ROLE hunter_worker"))
        await batch.execute(UPSERT_TOKEN, asdict(_token("H67dark", completed_at=T)))
        leitura = await _clock(engine)
        meta = await _meta(engine)
        await batch.commit()
        await batch.execute(text("RESET track_activities"))
        await batch.commit()
    assert meta["escritoras_sem_inicio"] >= 1
    with pytest.raises(ExportSemProvaDeVisibilidade, match="sem início"):
        _proof(meta, leitura)


async def test_membership_without_inheritance_is_no_proof(engine: AsyncEngine) -> None:
    """Astra (J round 5): ``MEMBER`` of ``pg_read_all_stats`` without inheritance hides
    other roles' ``xact_start``; only ``USAGE`` (the effective privilege) counts."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = "
                "'h67_no_inherit') THEN CREATE ROLE h67_no_inherit NOLOGIN; END IF; END $$"
            )
        )
        await connection.execute(
            text("GRANT pg_read_all_stats TO h67_no_inherit WITH INHERIT FALSE")
        )
        await connection.execute(text("GRANT SELECT ON meme_token_state_history TO h67_no_inherit"))
    try:
        async with engine.connect() as connection:
            member = await connection.scalar(
                text("SELECT pg_has_role('h67_no_inherit', 'pg_read_all_stats', 'MEMBER')")
            )
        meta = await _meta(engine, role="h67_no_inherit")
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("DROP OWNED BY h67_no_inherit"))
            await connection.execute(text("DROP ROLE h67_no_inherit"))
    assert member is True and meta["ve_toda_atividade"] is False
    with pytest.raises(ExportSemProvaDeVisibilidade, match="atividade"):
        _proof(meta, datetime.now(UTC))
