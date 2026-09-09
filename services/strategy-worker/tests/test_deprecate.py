"""``--deprecate`` — T3.39: the audited way to retire a version whose successor
is a parameter variant (or that has none at all), which ``--supersede``
structurally refuses ("already frozen against this code").

Mirrors ``test_supersede.py``: the script loaded by path, a real Postgres with
every migration applied, one frozen row per scenario so tests stay independent
of file order.

Run: ``uv run pytest services/strategy-worker/tests/test_deprecate.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import uuid7
from hunter_strategy_worker.catalogue import load_version_roster

from .builders import activate_version, seed_market, seed_paper_exposure, seed_shadow_exposure

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]


def _script() -> Any:
    path = REPO_ROOT / "infra" / "scripts" / "activate_strategy_version.py"
    spec = importlib.util.spec_from_file_location("activate_strategy_version_deprecate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["activate_strategy_version_deprecate"] = module
    spec.loader.exec_module(module)
    return module


async def _row(session: Any, key: str) -> Any:
    return (
        await session.execute(
            text(
                "SELECT v.id, v.status, v.deprecated_at, v.changelog FROM strategy_versions v "
                "JOIN strategies s ON s.id = v.strategy_id "
                "WHERE s.key = :key AND v.version = 'v1'"
            ),
            {"key": key},
        )
    ).one()


class TestDeprecateResearchOnly:
    async def test_it_deprecates_an_active_research_only_version(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_research")
        async with db_session_factory() as session, session.begin():
            message = await script.deprecate(
                session, "deprecate_research", "v1", "K1: 0 decisões", dry_run=False
            )
        assert "deprecated deprecate_research v1" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            row = await _row(session, "deprecate_research")
        assert row.status == "deprecated"
        assert row.deprecated_at is not None
        assert "K1" in (row.changelog or "")

    async def test_a_dry_run_writes_nothing(self, db_session_factory: Any) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_dry")
        async with db_session_factory() as session, session.begin():
            message = await script.deprecate(session, "deprecate_dry", "v1", "why", dry_run=True)
        assert message.startswith("would deprecate")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            row = await _row(session, "deprecate_dry")
        assert row.status == "active"
        assert row.deprecated_at is None

    async def test_it_refuses_a_version_that_is_not_active(self, db_session_factory: Any) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_draft", active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="not active"):
                await script.deprecate(session, "deprecate_draft", "v1", "why", dry_run=True)

    async def test_it_refuses_a_version_already_deprecated(self, db_session_factory: Any) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_twice")
        async with db_session_factory() as session, session.begin():
            await script.deprecate(session, "deprecate_twice", "v1", "first", dry_run=False)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="not active"):
                await script.deprecate(session, "deprecate_twice", "v1", "second", dry_run=True)

    async def test_it_records_the_successor_named_by_the_operator(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_successor", version="v1")
            await activate_version(session, key="deprecate_successor", version="v2")
        async with db_session_factory() as session, session.begin():
            message = await script.deprecate(
                session,
                "deprecate_successor",
                "v1",
                "K1: descartar; sucedida por parâmetro",
                dry_run=False,
                successor="v2",
            )
        assert "successor=deprecate_successor v2" in message

    async def test_it_records_params_format_in_the_audit_event(
        self, db_session_factory: Any
    ) -> None:
        """BAIXA-11: the ``system_events`` row names the frozen ``params_format``
        too, the same way it already names ``code_ref`` and ``params_hash``."""
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_audit_format")
        async with db_session_factory() as session, session.begin():
            await script.deprecate(session, "deprecate_audit_format", "v1", "K1", dry_run=False)
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            message = await session.scalar(
                text(
                    "SELECT message FROM system_events WHERE event = 'strategy_version_deprecated' "
                    "AND message LIKE 'deprecate_audit_format%' ORDER BY created_at DESC LIMIT 1"
                )
            )
        assert message is not None
        assert "params_format=1" in message

    async def test_it_refuses_an_unknown_successor(self, db_session_factory: Any) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_bad_successor")
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="does not exist"):
                await script.deprecate(
                    session,
                    "deprecate_bad_successor",
                    "v1",
                    "why",
                    dry_run=True,
                    successor="v9",
                )

    async def test_the_roster_drops_the_deprecated_version_at_the_next_reload(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_roster")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            roster = await load_version_roster(session)
        assert "deprecate_roster" in {v.strategy_key for v in roster.versions}
        async with db_session_factory() as session, session.begin():
            await script.deprecate(session, "deprecate_roster", "v1", "K1", dry_run=False)
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            roster = await load_version_roster(session)
        assert "deprecate_roster" not in {v.strategy_key for v in roster.versions}


class TestDeprecatePreservesLineage:
    """T3.47c (found by T3.47b, CONCERN 3): a derived variant's analysable
    lineage (``derive_variant.py``'s ``derived_from=v<n> | overrides=...``,
    read back by ``infra/scripts/obsidian_strategy_pages.py``) lives only in
    ``changelog`` — a plain ``changelog = :verdict`` overwrite would erase it."""

    async def test_it_appends_to_an_existing_lineage_prefix_instead_of_erasing_it(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        lineage = (
            "variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089 "
            "| params_hash=aaaaaaaaaaaa | KB-0008: piso de custo"
        )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            _strategy_id, version_id = await activate_version(session, key="deprecate_lineage")
        async with db_session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE strategy_versions SET changelog = :changelog WHERE id = :id"),
                {"changelog": lineage, "id": version_id},
            )
        async with db_session_factory() as session, session.begin():
            message = await script.deprecate(
                session, "deprecate_lineage", "v1", "K1: 0 decisões", dry_run=False
            )
        assert "deprecated deprecate_lineage v1" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            row = await _row(session, "deprecate_lineage")
        assert row.changelog is not None
        assert row.changelog.startswith(lineage)
        assert "\n[deprecated " in row.changelog
        assert row.changelog.endswith("K1: 0 decisões")


class TestDeprecateLive:
    async def test_it_refuses_a_live_version_even_with_force_paper(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_live", purpose="live")
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="purpose 'live'"):
                await script.deprecate(
                    session,
                    "deprecate_live",
                    "v1",
                    "why",
                    dry_run=True,
                    force_paper=True,
                )


class TestDeprecatePaperLine:
    async def test_it_refuses_a_paper_version_without_force_paper(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_paper_noforce", purpose="paper")
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="--force-paper"):
                await script.deprecate(
                    session, "deprecate_paper_noforce", "v1", "why", dry_run=True
                )

    async def test_it_refuses_a_paper_version_with_open_position_even_with_force_paper(
        self, db_session_factory: Any
    ) -> None:
        """ALTA-1 (T3.39b review): seeded the way production actually links a
        position to an agent — ``metadata->>'proposal_id' -> orders ->
        trade_proposals -> agents`` — never through ``positions.agent_id``,
        which the execution worker's ``INSERT`` never writes."""
        script = _script()
        org = uuid7()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            _exchange_id, market_id = await seed_market(session)
            _strategy_id, version_id = await activate_version(
                session, key="deprecate_paper_open", purpose="paper"
            )
            await seed_paper_exposure(session, org=org, version_id=version_id, market_id=market_id)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="skin in the game"):
                await script.deprecate(
                    session,
                    "deprecate_paper_open",
                    "v1",
                    "why",
                    dry_run=True,
                    force_paper=True,
                )

    async def test_it_refuses_a_paper_version_with_an_open_shadow_slot(
        self, db_session_factory: Any
    ) -> None:
        """BAIXA-7: the other half of the guard — no wallet exposure at all, only
        a ``shadow_episodes`` slot still tracking an entry."""
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            _exchange_id, market_id = await seed_market(session)
            _strategy_id, version_id = await activate_version(
                session, key="deprecate_paper_shadow", purpose="paper"
            )
            await seed_shadow_exposure(session, version_id=version_id, market_id=market_id)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="shadow slot"):
                await script.deprecate(
                    session,
                    "deprecate_paper_shadow",
                    "v1",
                    "why",
                    dry_run=True,
                    force_paper=True,
                )

    async def test_it_deprecates_a_paper_version_with_force_paper_and_no_open_positions(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="deprecate_paper_clean", purpose="paper")
        async with db_session_factory() as session, session.begin():
            message = await script.deprecate(
                session,
                "deprecate_paper_clean",
                "v1",
                "wallet retired",
                dry_run=False,
                force_paper=True,
            )
        assert "deprecated deprecate_paper_clean v1" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            row = await _row(session, "deprecate_paper_clean")
        assert row.status == "deprecated"
