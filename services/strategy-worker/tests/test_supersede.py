"""``--supersede`` — MUST-FIX 1(c).

The versions already frozen in the local database carry the superseded
tree-wide ``code_ref``, and ``0002_shadow_lab``'s trigger will never let it be
corrected (DATABASE.md §16.1). Rewriting those rows is not an option and would
not be honest if it were: what changed is how the code is identified, and a
version's identity is exactly what the freeze protects. The only honest move is
a successor row — same frozen experiment, new digest — with the retirement of
the old one in the *same* transaction.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.code_ref import version_code_ref

from .builders import activate_version, registry_for, seed_market

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]


def _script() -> Any:
    path = REPO_ROOT / "infra" / "scripts" / "activate_strategy_version.py"
    spec = importlib.util.spec_from_file_location("activate_strategy_version", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["activate_strategy_version"] = module
    spec.loader.exec_module(module)
    return module


async def _frozen(session: Any, key: str, code_ref: str) -> None:
    await seed_market(session)
    await activate_version(session, key=key, active=True, code_ref=code_ref)


class TestSupersede:
    async def test_it_deprecates_the_frozen_row_and_activates_its_successor(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await _frozen(session, "supersede_volume", "hunter_core.strategies@sha256:" + "0" * 64)
        async with db_session_factory() as session, session.begin():
            message = await script.supersede(
                session,
                "supersede_volume",
                "v1",
                "digest per version (MUST-FIX 1)",
                dry_run=False,
                registry=registry_for("supersede_volume"),
            )
        assert "superseded" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT v.version, v.status, v.code_ref, v.changelog, v.params_format, "
                        "v.default_parameters, v.parameters_schema, v.activated_at, "
                        "v.deprecated_at FROM strategy_versions v JOIN strategies s "
                        "ON s.id = v.strategy_id WHERE s.key = 'supersede_volume' "
                        "ORDER BY v.version"
                    )
                )
            ).all()
        assert [r.version for r in rows] == ["v1", "v2"]
        old, new = rows
        assert old.status == "deprecated"
        assert old.deprecated_at is not None
        assert "digest per version" in (old.changelog or "")
        assert old.code_ref == "hunter_core.strategies@sha256:" + "0" * 64
        assert new.status == "active"
        assert new.activated_at is not None
        assert new.code_ref == version_code_ref("volume_anomaly_v1")
        # the experiment is copied from the frozen row, never recomputed from code
        assert new.default_parameters == old.default_parameters
        assert new.parameters_schema == old.parameters_schema
        assert new.params_format == old.params_format

    async def test_the_successor_is_runnable_by_the_module_its_code_ref_names(
        self, db_session_factory: Any
    ) -> None:
        """A ``v2`` row has no ``(key, version)`` in the registry; the frozen
        ``code_ref`` names the module, and that is what binds it to code."""
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await _frozen(
                session, "supersede_runnable", "hunter_core.strategies@sha256:" + "1" * 64
            )
        async with db_session_factory() as session, session.begin():
            await script.supersede(
                session,
                "supersede_runnable",
                "v1",
                "digest per version",
                dry_run=False,
                registry=registry_for("supersede_runnable"),
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            versions = await load_active_versions(session)
        successor = [v for v in versions if v.strategy_key == "supersede_runnable"]
        assert len(successor) == 1
        assert successor[0].version == "v2"

    async def test_a_successor_can_itself_be_superseded(self, db_session_factory: Any) -> None:
        """Astra, S2 fixes diff review (HIGH b): the *second* change of code has
        to work too. ``v2`` has no ``(key, version)`` in the registry, so the
        script must find its code the same way the worker does — through the
        module its frozen ``code_ref`` names."""
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session,
                key="supersede_twice",
                version="v2",
                active=True,
                code_ref="hunter_core.strategies.volume_anomaly_v1@sha256:" + "4" * 64,
            )
        script = _script()
        async with db_session_factory() as session, session.begin():
            message = await script.supersede(
                session,
                "supersede_twice",
                "v2",
                "second change of code",
                dry_run=False,
                registry=registry_for("supersede_twice"),
            )
        assert "with v3" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT v.version, v.status, v.code_ref FROM strategy_versions v "
                        "JOIN strategies s ON s.id = v.strategy_id "
                        "WHERE s.key = 'supersede_twice' ORDER BY v.version"
                    )
                )
            ).all()
        assert [(r.version, r.status) for r in rows] == [("v2", "deprecated"), ("v3", "active")]
        assert rows[1].code_ref == version_code_ref("volume_anomaly_v1")

    async def test_a_dry_run_writes_nothing(self, db_session_factory: Any) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await _frozen(session, "supersede_dry", "hunter_core.strategies@sha256:" + "2" * 64)
        async with db_session_factory() as session, session.begin():
            message = await script.supersede(
                session,
                "supersede_dry",
                "v1",
                "why",
                dry_run=True,
                registry=registry_for("supersede_dry"),
            )
        assert message.startswith("would supersede")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            count = await session.scalar(
                text(
                    "SELECT count(*) FROM strategy_versions v JOIN strategies s "
                    "ON s.id = v.strategy_id WHERE s.key = 'supersede_dry'"
                )
            )
        assert count == 1

    async def test_it_refuses_when_the_digest_already_matches(
        self, db_session_factory: Any
    ) -> None:
        """Superseding a version already frozen against this exact code would
        split one experiment in two for nothing."""
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await _frozen(session, "supersede_current", version_code_ref("volume_anomaly_v1"))
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="already frozen against this code"):
                await script.supersede(
                    session,
                    "supersede_current",
                    "v1",
                    "why",
                    dry_run=True,
                    registry=registry_for("supersede_current"),
                )

    async def test_it_refuses_a_version_that_was_never_activated(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="supersede_draft", active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="was never activated"):
                await script.supersede(
                    session,
                    "supersede_draft",
                    "v1",
                    "why",
                    dry_run=True,
                    registry=registry_for("supersede_draft"),
                )

    async def test_a_failure_before_the_commit_leaves_nothing_half_done(
        self, db_session_factory: Any
    ) -> None:
        """Astra: one transaction, or an operator finds the old version retired
        and no successor collecting anything."""
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await _frozen(session, "supersede_atomic", "hunter_core.strategies@sha256:" + "3" * 64)
        with pytest.raises(RuntimeError, match="injected"):
            async with db_session_factory() as session, session.begin():
                await script.supersede(
                    session,
                    "supersede_atomic",
                    "v1",
                    "why",
                    dry_run=False,
                    registry=registry_for("supersede_atomic"),
                )
                raise RuntimeError("injected before the commit")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT v.version, v.status FROM strategy_versions v JOIN strategies s "
                        "ON s.id = v.strategy_id WHERE s.key = 'supersede_atomic'"
                    )
                )
            ).all()
        assert [(r.version, r.status) for r in rows] == [("v1", "active")]
