"""T3.69 — the persisted ``paper_v1`` profile, and the wallet that points at it.

Two halves, one database, one container (the brief's rule: one testcontainer
file at a time):

1. **Proof of equality.** Against a database that mirrors the VPS of
   2026-09-10 (``risk_profiles`` holding four rows — the three system presets
   plus one organization's copy — and **no** ``paper_v1``), ``seed.py --only
   risk_profiles --dry-run`` prints the row it would insert and writes nothing;
   writing it stores the limits as JSON **strings** (never numbers), and the
   stored row round-trips to ``hunter_risk.limits.PAPER_V1`` field by field.
   A row that has diverged stops the seed instead of being overwritten.
2. **The link.** ``infra/scripts/link_portfolio_risk_profile.py`` — refusals
   first (no preset row, wrong portfolio type, unknown id, a diverged profile,
   a wallet already pointing elsewhere), then the write, its single
   ``audit_logs`` row, and its idempotent replay.

Run:
    uv run pytest infra/scripts/tests/test_link_portfolio_risk_profile.py -q
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_risk.limits import PAPER_V1, RiskLimits

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine
    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = Path(__file__).resolve().parents[1]

ORG_ID = uuid.UUID("01a07a1e-0000-7000-8000-00000000000a")
WORKSPACE_ID = uuid.UUID("01a07a1e-0000-7000-8000-00000000000b")
WALLET_ID = uuid.UUID("01a07a1e-0000-7000-8000-00000000000c")
SHADOW_ID = uuid.UUID("01a07a1e-0000-7000-8000-00000000000d")
OTHER_PROFILE_ID = uuid.UUID("01a07a1e-0000-7000-8000-00000000000e")


def _load(name: str) -> ModuleType:
    """Load ``infra/scripts/<name>.py`` the way running it as a script would."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_t369", SCRIPTS_DIR / f"{name}.py"
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
def link_db_url(postgres_container: PostgresContainer) -> str:
    """A database of its own, migrated to head, then made to look like the VPS."""
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_link_risk_profile")
    )
    command.upgrade(_alembic_config(url), "head")
    asyncio.run(_mirror_the_vps(url))
    return url


async def _mirror_the_vps(url: str) -> None:
    """The VPS state measured 2026-09-10 00:40 BRT: four profiles, no ``paper_v1``.

    Three system presets written by ``seed_risk_profiles`` itself (never a
    literal here), one organization-scoped copy of ``balanced`` — the fourth row
    an organization gets at sign-up (``services/organizations.py`` →
    ``copy_preset_for_org``) — and the principal paper wallet with
    ``risk_profile_id`` NULL, which is exactly what the wallet on the VPS shows.
    """
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    seed = _load("seed")
    try:
        async with engine.begin() as conn:
            await seed.seed_risk_profiles(conn)
            await conn.execute(
                text("INSERT INTO organizations (id, slug, name) VALUES (:id, 'ever', 'ever')"),
                {"id": ORG_ID},
            )
            await conn.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, objective) "
                    "VALUES (:id, :org, 'principal', 'paper_trading')"
                ),
                {"id": WORKSPACE_ID, "org": ORG_ID},
            )
            await conn.execute(
                text(
                    "INSERT INTO risk_profiles (id, organization_id, name, preset, limits) "
                    "SELECT :id, :org, name, preset, limits FROM risk_profiles "
                    "WHERE organization_id IS NULL AND preset = 'balanced'"
                ),
                {"id": OTHER_PROFILE_ID, "org": ORG_ID},
            )
            for portfolio_id, name, kind in (
                (WALLET_ID, "Carteira paper principal", "paper"),
                (SHADOW_ID, "Sombra", "shadow"),
            ):
                await conn.execute(
                    text(
                        "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                        "initial_capital) VALUES (:id, :org, :ws, :name, :type, 20000)"
                    ),
                    {
                        "id": portfolio_id,
                        "org": ORG_ID,
                        "ws": WORKSPACE_ID,
                        "name": name,
                        "type": kind,
                    },
                )
    finally:
        await engine.dispose()


@pytest.fixture
def engine(link_db_url: str) -> AsyncEngine:
    return create_async_engine(link_db_url, connect_args={"statement_cache_size": 0})


@pytest.fixture
def cli(link_db_url: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", link_db_url)
    return _load("seed_cli")


@pytest.fixture
def script(link_db_url: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", link_db_url)
    return _load("link_portfolio_risk_profile")


def _args(
    *,
    portfolio: uuid.UUID = WALLET_ID,
    preset: str = "paper_v1",
    yes: bool = False,
    replace: bool = False,
    actor: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        portfolio=portfolio, preset=preset, dry_run=not yes, yes=yes, replace=replace, actor=actor
    )


async def _stored_limits(engine: AsyncEngine) -> dict[str, Any] | None:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text(
                "SELECT limits FROM risk_profiles "
                "WHERE organization_id IS NULL AND preset = 'paper_v1'"
            )
        )
    return dict(value) if value is not None else None


async def _paper_profile_id(engine: AsyncEngine) -> uuid.UUID | None:
    async with engine.connect() as conn:
        return await conn.scalar(
            text(
                "SELECT id FROM risk_profiles WHERE organization_id IS NULL AND preset = 'paper_v1'"
            )
        )


async def _linked_profile(engine: AsyncEngine, portfolio_id: uuid.UUID = WALLET_ID) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(
            text("SELECT risk_profile_id FROM portfolios WHERE id = :id"), {"id": portfolio_id}
        )


async def _set_link(engine: AsyncEngine, value: uuid.UUID | None) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE portfolios SET risk_profile_id = :value WHERE id = :id"),
            {"value": value, "id": WALLET_ID},
        )


async def _audit_rows(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT organization_id, actor_type, action, entity_type, entity_id, before, "
                "after, metadata FROM audit_logs WHERE entity_id = :id AND action = :action "
                "ORDER BY created_at"
            ),
            {"id": WALLET_ID, "action": "portfolio.risk_profile_linked"},
        )
        return list(result.mappings())


async def _ensure_paper_preset(cli: ModuleType) -> None:
    """Seed ``paper_v1`` if it is not there — the seed's own writer, idempotent."""
    await cli.seed_with_report(only="risk_profiles", yes=True)


async def _delete_paper_preset(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM risk_profiles WHERE organization_id IS NULL AND preset = 'paper_v1'")
        )


# --------------------------------------------------------------------------
# 1. The seeded row is the engine's object, not a copy of it
# --------------------------------------------------------------------------


class TestTheSeedOnTheVpsState:
    async def test_the_state_this_module_starts_from_is_the_vps_one(
        self, engine: AsyncEngine
    ) -> None:
        """Four profiles, none of them ``paper_v1`` — the measurement of the brief."""
        async with engine.connect() as conn:
            total = await conn.scalar(text("SELECT count(*) FROM risk_profiles"))
            paper = await conn.scalar(
                text("SELECT count(*) FROM risk_profiles WHERE preset = 'paper_v1'")
            )
        assert (total, paper) == (4, 0)

    async def test_a_dry_run_shows_the_row_it_would_insert_and_writes_nothing(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await _delete_paper_preset(engine)
        counts, diff = await cli.seed_with_report(only="risk_profiles", dry_run=True)
        assert set(counts) == {"risk_profiles"}
        new_lines = [line for line in diff if line.startswith("risk_profiles.paper_v1: NEW")]
        assert new_lines, diff
        # The preview names the wallet's profile and its ceilings, as strings.
        assert "'preset': 'paper_v1'" in new_lines[0]
        assert "'risk_per_trade_pct': '0.0025'" in new_lines[0]
        assert await _stored_limits(engine) is None, "a dry run wrote the row"

    async def test_writing_it_stores_json_strings_never_numbers(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await _ensure_paper_preset(cli)
        stored = await _stored_limits(engine)
        assert stored is not None
        fractions = [
            name for name, field in RiskLimits.model_fields.items() if field.annotation is Decimal
        ]
        assert fractions, "RiskLimits stopped carrying Decimal fields"
        for name in fractions:
            assert isinstance(stored[name], str), f"{name} was stored as {type(stored[name])}"
        assert isinstance(stored["max_concurrent_positions"], int)
        assert isinstance(stored["participation_window_s"], int)

    async def test_the_stored_row_round_trips_to_paper_v1_field_by_field(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """``risk_profiles.limits`` is the engine's object, read back out of Postgres.

        The existing ``test_the_seeded_paper_profile_has_exactly_one_source``
        compares the *shipped* constant with the engine's; this one compares
        what a real jsonb column gave back after a real seed — the artefact the
        VPS will actually hold.
        """
        await _ensure_paper_preset(cli)
        stored = await _stored_limits(engine)
        assert stored is not None
        parsed = RiskLimits.model_validate(stored)
        for name in RiskLimits.model_fields:
            assert getattr(parsed, name) == getattr(PAPER_V1, name), name
        assert parsed == PAPER_V1
        assert json.dumps(stored, sort_keys=True) == json.dumps(
            PAPER_V1.model_dump(mode="json"), sort_keys=True
        )
        # And the directive's own numbers survived the trip.
        assert parsed.risk_per_trade_pct == Decimal("0.0025")
        assert parsed.max_total_exposure_pct == Decimal("0.40")
        assert parsed.max_concurrent_positions == 5
        assert parsed.day_timezone == "America/Sao_Paulo"

    async def test_a_diverged_row_stops_the_seed_instead_of_being_overwritten(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """The seed's own guard. Everton's limits are never rewritten by a deploy."""
        await _ensure_paper_preset(cli)
        drifted = dict(PAPER_V1.model_dump(mode="json"))
        drifted["risk_per_trade_pct"] = "0.0100"
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE risk_profiles SET limits = CAST(:limits AS jsonb) "
                    "WHERE organization_id IS NULL AND preset = 'paper_v1'"
                ),
                {"limits": json.dumps(drifted)},
            )
        try:
            with pytest.raises(SystemExit, match="risk_per_trade_pct"):
                await cli.seed_with_report(only="risk_profiles", yes=True)
            with pytest.raises(SystemExit, match="never changed without being presented"):
                await cli.seed_with_report(only="risk_profiles")
            assert (await _stored_limits(engine) or {})["risk_per_trade_pct"] == "0.0100"
        finally:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE risk_profiles SET limits = CAST(:limits AS jsonb) "
                        "WHERE organization_id IS NULL AND preset = 'paper_v1'"
                    ),
                    {"limits": json.dumps(PAPER_V1.model_dump(mode="json"))},
                )


# --------------------------------------------------------------------------
# 2. link_portfolio_risk_profile.py — the refusals, then the write
# --------------------------------------------------------------------------


class TestTheLinkRefuses:
    async def test_without_the_preset_row_it_refuses_and_points_at_the_seed(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        await _set_link(engine, None)
        await _delete_paper_preset(engine)
        try:
            assert await script.run(_args(yes=True)) == 1
            printed = capsys.readouterr().out
            assert "REFUSED" in printed
            assert "seed.py --only risk_profiles" in printed
            assert await _linked_profile(engine) is None
            assert await _audit_rows(engine) == []
        finally:
            await _ensure_paper_preset(cli)

    async def test_an_unknown_portfolio_is_refused(
        self, script: ModuleType, cli: ModuleType, capsys: Any
    ) -> None:
        await _ensure_paper_preset(cli)
        assert await script.run(_args(portfolio=uuid.uuid4(), yes=True)) == 1
        assert "no portfolio" in capsys.readouterr().out

    async def test_a_portfolio_that_is_not_the_paper_wallet_is_refused(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        await _ensure_paper_preset(cli)
        assert await script.run(_args(portfolio=SHADOW_ID, yes=True)) == 1
        assert "type=shadow" in capsys.readouterr().out
        assert await _linked_profile(engine, SHADOW_ID) is None

    async def test_a_diverged_profile_row_is_never_linked(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        """A wallet linked to a row that is not ``PAPER_V1`` would be a limit
        change made by nobody — the exact thing RISK_ENGINE.md §2 forbids."""
        await _ensure_paper_preset(cli)
        await _set_link(engine, None)
        drifted = dict(PAPER_V1.model_dump(mode="json"))
        drifted["max_total_exposure_pct"] = "0.90"
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE risk_profiles SET limits = CAST(:limits AS jsonb) "
                    "WHERE organization_id IS NULL AND preset = 'paper_v1'"
                ),
                {"limits": json.dumps(drifted)},
            )
        try:
            assert await script.run(_args(yes=True)) == 1
            printed = capsys.readouterr().out
            assert "differ from hunter_risk.limits.PAPER_V1" in printed
            assert "max_total_exposure_pct" in printed
            assert await _linked_profile(engine) is None
            assert await _audit_rows(engine) == []
        finally:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE risk_profiles SET limits = CAST(:limits AS jsonb) "
                        "WHERE organization_id IS NULL AND preset = 'paper_v1'"
                    ),
                    {"limits": json.dumps(PAPER_V1.model_dump(mode="json"))},
                )

    async def test_a_wallet_pointing_elsewhere_needs_replace(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        await _ensure_paper_preset(cli)
        await _set_link(engine, OTHER_PROFILE_ID)
        try:
            assert await script.run(_args(yes=True)) == 1
            assert "--replace" in capsys.readouterr().out
            assert await _linked_profile(engine) == OTHER_PROFILE_ID
        finally:
            await _set_link(engine, None)

    async def test_dry_run_and_yes_together_are_a_usage_error(
        self, script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "link_portfolio_risk_profile.py",
                "--portfolio",
                str(WALLET_ID),
                "--preset",
                "paper_v1",
                "--dry-run",
                "--yes",
            ],
        )
        with pytest.raises(SystemExit) as exit_info:
            script.main()
        assert exit_info.value.code == 2


class TestTheLinkWrites:
    async def test_the_preview_prints_before_and_after_and_writes_nothing(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        await _ensure_paper_preset(cli)
        await _set_link(engine, None)
        assert await script.run(_args()) == 0
        printed = capsys.readouterr().out
        profile_id = await _paper_profile_id(engine)
        assert "before: risk_profile_id = None" in printed
        assert f"after:  risk_profile_id = {profile_id}" in printed
        assert "would link" in printed
        assert "nothing written" in printed
        assert await _linked_profile(engine) is None
        assert await _audit_rows(engine) == []

    async def test_yes_links_the_wallet_and_writes_one_audit_row(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        await _ensure_paper_preset(cli)
        await _set_link(engine, None)
        profile_id = await _paper_profile_id(engine)
        before_rows = len(await _audit_rows(engine))

        assert await script.run(_args(yes=True, actor="operator@example.com")) == 0
        printed = capsys.readouterr().out
        assert "linked" in printed
        assert await _linked_profile(engine) == profile_id

        rows = await _audit_rows(engine)
        assert len(rows) == before_rows + 1
        row = rows[-1]
        assert row["organization_id"] == ORG_ID
        assert row["actor_type"] == "system"
        assert row["entity_type"] == "portfolio"
        assert row["before"] == {"risk_profile_id": None}
        assert row["after"] == {"risk_profile_id": str(profile_id), "preset": "paper_v1"}
        assert row["metadata"]["actor_input"] == "operator@example.com"
        assert row["metadata"]["replaced"] is False

    async def test_running_it_again_changes_nothing_and_adds_no_second_audit_row(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        """Replaying an operator act is a no-op, not a second write."""
        await _ensure_paper_preset(cli)
        profile_id = await _paper_profile_id(engine)
        await _set_link(engine, profile_id)
        before_rows = len(await _audit_rows(engine))

        assert await script.run(_args(yes=True)) == 0
        assert "already points at paper_v1" in capsys.readouterr().out
        assert await _linked_profile(engine) == profile_id
        assert len(await _audit_rows(engine)) == before_rows

    async def test_replace_moves_a_wallet_and_records_what_it_replaced(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        await _ensure_paper_preset(cli)
        await _set_link(engine, OTHER_PROFILE_ID)
        profile_id = await _paper_profile_id(engine)
        before_rows = len(await _audit_rows(engine))

        assert await script.run(_args(yes=True, replace=True)) == 0
        assert f"before: risk_profile_id = {OTHER_PROFILE_ID}" in capsys.readouterr().out
        assert await _linked_profile(engine) == profile_id

        rows = await _audit_rows(engine)
        assert len(rows) == before_rows + 1
        assert rows[-1]["before"] == {"risk_profile_id": str(OTHER_PROFILE_ID)}
        assert rows[-1]["metadata"]["replaced"] is True

    async def test_the_linked_row_is_what_the_api_would_read_back(
        self, script: ModuleType, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """The point of the whole task: after the link, the wallet's profile is
        readable through ``portfolios.risk_profile_id`` and it *is* ``PAPER_V1``
        — the path ``apps/api/hunter_api/services/risk_limits.py`` takes when the
        column is set (``source='risk_profile'`` instead of ``engine_default``).
        """
        await _ensure_paper_preset(cli)
        await _set_link(engine, None)
        assert await script.run(_args(yes=True)) == 0
        async with engine.connect() as conn:
            limits = await conn.scalar(
                text(
                    "SELECT rp.limits FROM portfolios p JOIN risk_profiles rp "
                    "ON rp.id = p.risk_profile_id WHERE p.id = :id"
                ),
                {"id": WALLET_ID},
            )
        assert limits is not None
        assert RiskLimits.model_validate(dict(limits)) == PAPER_V1
