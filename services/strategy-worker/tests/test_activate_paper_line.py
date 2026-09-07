"""``--paper-line`` — the paper coorte is derived from a frozen research version
and nothing is activated (T3.15, D10).

Runs against the migrated schema on the owner connection, exactly the way the
ops script runs (``DATABASE_URL_MIGRATIONS``): ``0010_strategy_purpose`` revoked
``purpose`` from every application role, so the owner is the only role that can
write the label at all.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.strategies.envelope import PURPOSE_PAPER, PURPOSE_RESEARCH_ONLY

from .builders import activate_version, registry_for, seed_market

REPO_ROOT = Path(__file__).resolve().parents[3]


def _script() -> Any:
    path = REPO_ROOT / "infra" / "scripts" / "activate_strategy_version.py"
    spec = importlib.util.spec_from_file_location("activate_strategy_version_paper", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["activate_strategy_version_paper"] = module
    spec.loader.exec_module(module)
    return module


async def _rows(session: Any, key: str) -> list[Any]:
    return list(
        (
            await session.execute(
                text(
                    "SELECT v.version, v.status, v.purpose, v.activated_at, v.code_ref, "
                    "v.default_parameters, v.parameters_schema, v.params_format, v.changelog "
                    "FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id "
                    "WHERE s.key = :key ORDER BY v.version"
                ),
                {"key": key},
            )
        ).all()
    )


@pytest.mark.integration
class TestPaperLine:
    async def test_a_dry_run_names_the_line_and_writes_nothing(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "paper_line_dry"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            message = await script.paper_line(
                session, key, "v1", "D10 dry run", dry_run=True, registry=registry_for(key)
            )
        assert message.startswith(f"would derive {key} v2 (purpose paper, draft, not activated)")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            rows = await _rows(session, key)
        assert [r.version for r in rows] == ["v1"]

    async def test_the_paper_line_copies_the_frozen_content_and_activates_nothing(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "paper_line_real"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            message = await script.paper_line(
                session, key, "v1", "D10: momentum paper", dry_run=False, registry=registry_for(key)
            )
        assert message.startswith(f"derived {key} v2 (purpose paper, draft, not activated)")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            source, paper = await _rows(session, key)
            events = (
                (
                    await session.execute(
                        text(
                            "SELECT event FROM system_events WHERE component = "
                            "'activate_strategy_version' AND message LIKE :like"
                        ),
                        {"like": f"{key} v2 derived from v1%"},
                    )
                )
                .scalars()
                .all()
            )
        # The source is untouched: still research_only, still active, still frozen.
        assert source.version == "v1"
        assert source.purpose == PURPOSE_RESEARCH_ONLY
        assert source.status == "active"
        assert source.activated_at is not None
        # The paper line is a draft with the label, the same content, no activation.
        assert paper.version == "v2"
        assert paper.purpose == PURPOSE_PAPER
        assert paper.status == "draft"
        assert paper.activated_at is None
        assert paper.default_parameters == source.default_parameters
        assert paper.parameters_schema == source.parameters_schema
        assert paper.params_format == source.params_format
        assert paper.code_ref == source.code_ref
        assert paper.changelog.startswith("paper line of v1 (D10, T3.15)")
        assert events == ["strategy_version_paper_line_derived"]

    async def test_one_paper_line_per_strategy(self, db_session_factory: Any) -> None:
        script = _script()
        key = "paper_line_twice"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            await script.paper_line(
                session, key, "v1", "first", dry_run=False, registry=registry_for(key)
            )
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="already has a paper line"):
                await script.paper_line(
                    session, key, "v1", "second", dry_run=False, registry=registry_for(key)
                )

    async def test_it_refuses_a_version_that_was_never_frozen(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "paper_line_draft_source"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key, active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="never activated"):
                await script.paper_line(
                    session, key, "v1", "x", dry_run=True, registry=registry_for(key)
                )

    async def test_it_refuses_to_derive_from_anything_but_research_only(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "paper_line_from_paper"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
        # ``purpose`` cannot be named by hunter_worker (0010): the owner writes it.
        async with db_session_factory() as session, session.begin():
            await activate_version(session, key=key, purpose=PURPOSE_PAPER)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="research_only"):
                await script.paper_line(
                    session, key, "v1", "x", dry_run=True, registry=registry_for(key)
                )

    async def test_the_paper_line_can_later_be_activated_and_live_never(
        self, db_session_factory: Any
    ) -> None:
        """Activating the derived line is a separate run — and resolves the code
        through the frozen ``code_ref``, since ``v2`` has no registry entry."""
        script = _script()
        key = "paper_line_then_activate"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            await script.paper_line(
                session, key, "v1", "derive", dry_run=False, registry=registry_for(key)
            )
        async with db_session_factory() as session, session.begin():
            message = await script.activate(
                session, key, "v2", "activate paper", dry_run=True, registry=registry_for(key)
            )
        assert message.startswith(f"would activate {key} v2 (purpose paper)")
        # A live-labelled row is refused by name, whatever else is true about it.
        live_key = "paper_line_live_refused"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
        async with db_session_factory() as session, session.begin():
            await activate_version(session, key=live_key, active=False, purpose="live")
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="live é Fase 4"):
                await script.activate(
                    session, live_key, "v1", "x", dry_run=True, registry=registry_for(live_key)
                )
