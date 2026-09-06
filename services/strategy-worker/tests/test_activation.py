"""The audited activation — ``infra/scripts/activate_strategy_version.py``.

The first activation is irreversible (DATABASE.md §16.1), so every check has to
happen *before* it and every failure has to be a refusal, not a warning.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.strategies.registry import DEFAULT_REGISTRY
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.code_ref import PACKAGE, version_code_ref

from .builders import activate_version, registry_for, seed_market

REPO_ROOT = Path(__file__).resolve().parents[3]


def _script() -> Any:
    """Import the ops script by path (``infra/scripts`` is not a package)."""
    path = REPO_ROOT / "infra" / "scripts" / "activate_strategy_version.py"
    spec = importlib.util.spec_from_file_location("activate_strategy_version", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["activate_strategy_version"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestParameterValidation:
    def test_the_frozen_defaults_validate_against_their_own_schema(self) -> None:
        import json

        from hunter_core.strategies.canonical import canonical_json

        for strategy in DEFAULT_REGISTRY.all():
            schema: dict[str, Any] = json.loads(canonical_json(dict(strategy.parameters_schema)))
            params: dict[str, Any] = json.loads(canonical_json(dict(strategy.default_parameters)))
            assert validate_parameters(schema, params).ok, strategy.key

    def test_a_missing_parameter_is_an_error(self) -> None:
        schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}}
        report = validate_parameters(schema, {})
        assert not report.ok
        assert "required" in report.errors[0]

    def test_an_undeclared_parameter_is_an_error(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {},
        }
        assert not validate_parameters(schema, {"sneaky": "1"}).ok

    def test_a_value_that_breaks_the_pattern_is_an_error(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "required": ["a"],
            "properties": {"a": {"type": ["string", "number"], "pattern": r"^-?[0-9]+$"}},
        }
        assert not validate_parameters(schema, {"a": "1.5"}).ok
        assert validate_parameters(schema, {"a": "15"}).ok

    def test_an_unsupported_keyword_is_refused_rather_than_ignored(self) -> None:
        """Silently skipping a constraint would report a version as validated
        when it was not checked."""
        schema = {"type": "object", "properties": {"a": {"type": "string", "minLength": 2}}}
        report = validate_parameters(schema, {"a": "x"})
        assert not report.ok
        assert "does not check" in report.errors[0]


@pytest.mark.integration
class TestActivationScript:
    async def test_it_refuses_when_the_migration_is_missing(self, db_session_factory: Any) -> None:
        script = _script()

        async def no_migration(_conn: Any) -> bool:
            return False

        script._migration_applied = no_migration
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="0002_shadow_lab is not applied"):
                await script.activate(session, "volume_anomaly", "v1", "test", dry_run=True)

    async def test_it_refuses_a_version_this_build_has_no_code_for(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await session.execute(
                text(
                    "INSERT INTO strategies (id, key, name) VALUES "
                    "(gen_random_uuid(), 'no_such_strategy', 'x') ON CONFLICT DO NOTHING"
                )
            )
            await session.execute(
                text(
                    "INSERT INTO strategy_versions (id, strategy_id, version, status) "
                    "SELECT gen_random_uuid(), id, 'v9', 'draft' FROM strategies "
                    "WHERE key = 'no_such_strategy' ON CONFLICT DO NOTHING"
                )
            )
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="no code registered"):
                await script.activate(session, "no_such_strategy", "v9", "test", dry_run=True)

    async def test_it_refuses_an_unknown_version(self, db_session_factory: Any) -> None:
        script = _script()
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="no strategy_version"):
                await script.activate(session, "momentum", "v404", "test", dry_run=True)

    async def test_a_dry_run_writes_nothing_and_names_the_code_ref(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="dry_run_volume", active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            message = await script.activate(
                session,
                "dry_run_volume",
                "v1",
                "test",
                dry_run=True,
                registry=registry_for("dry_run_volume"),
            )
        assert message.startswith("would activate")
        assert PACKAGE in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            activated = await session.scalar(
                text(
                    "SELECT activated_at FROM strategy_versions v JOIN strategies s "
                    "ON s.id = v.strategy_id WHERE s.key = 'dry_run_volume'"
                )
            )
        assert activated is None

    async def test_activation_writes_the_definitive_code_ref_and_an_audit_event(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="real_volume", active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            message = await script.activate(
                session,
                "real_volume",
                "v1",
                "S2 proof",
                dry_run=False,
                registry=registry_for("real_volume"),
            )
        assert message.startswith("activated")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            row = (
                await session.execute(
                    text(
                        "SELECT v.code_ref, v.status, v.activated_at, v.changelog, "
                        "v.params_format, v.default_parameters FROM strategy_versions v "
                        "JOIN strategies s ON s.id = v.strategy_id WHERE s.key = 'real_volume'"
                    )
                )
            ).one()
            events = await session.scalar(
                text(
                    "SELECT count(*) FROM system_events WHERE event = 'strategy_version_activated'"
                )
            )
        assert row.code_ref == version_code_ref("volume_anomaly_v1")
        assert row.status == "active"
        assert row.activated_at is not None
        assert row.changelog == "S2 proof"
        assert row.params_format == 1
        assert row.default_parameters["volume_mult"] == "4"
        assert events >= 1

    async def test_reactivating_the_same_frozen_version_is_a_no_op(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key="idempotent_volume", active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            await script.activate(
                session,
                "idempotent_volume",
                "v1",
                "first",
                dry_run=False,
                registry=registry_for("idempotent_volume"),
            )
        async with db_session_factory() as session, session.begin():
            message = await script.activate(
                session,
                "idempotent_volume",
                "v1",
                "second",
                dry_run=False,
                registry=registry_for("idempotent_volume"),
            )
        assert "already activated" in message

    async def test_it_refuses_to_repoint_a_frozen_version_at_other_code(
        self, db_session_factory: Any
    ) -> None:
        """A version already collecting evidence is never re-pointed: that is a
        new version, not an update (DATABASE.md §16.1)."""
        script = _script()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session, key="frozen_volume", active=True, code_ref="hunter_core.strategies@old"
            )
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="never re-pointed"):
                await script.activate(
                    session,
                    "frozen_volume",
                    "v1",
                    "test",
                    dry_run=False,
                    registry=registry_for("frozen_volume"),
                )
