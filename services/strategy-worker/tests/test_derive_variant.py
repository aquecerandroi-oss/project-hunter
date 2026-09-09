"""``infra/scripts/derive_variant.py`` — a research variant is a **new version**
with one parameter overridden, born ``draft`` and activated separately (T3.26).

Runs against the migrated schema on the owner connection, exactly the way the
ops script runs (``DATABASE_URL_MIGRATIONS``): ``0011_strategy_activation_owner``
revoked ``INSERT`` on ``strategy_versions`` from every application role, so the
owner is the only one that can write a version row at all. Same pattern as
``test_activate_paper_line.py``, and deliberately the same fixtures: the parent
is a real frozen contract (``volume_anomaly_v1``'s schema and parameters), so
what is validated is the genuine ``parameters_schema``, not a hand-made one.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.envelope import PURPOSE_PAPER, PURPOSE_RESEARCH_ONLY

from .builders import activate_version, insert_hourly_regime, registry_for, seed_market

REPO_ROOT = Path(__file__).resolve().parents[3]


def _module(name: str, filename: str) -> Any:
    path = REPO_ROOT / "infra" / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _script() -> Any:
    return _module("derive_variant_integration", "derive_variant.py")


def _activation_script() -> Any:
    return _module("activate_for_variant", "activate_strategy_version.py")


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


async def _events(session: Any, like: str) -> list[str]:
    return list(
        (
            await session.execute(
                text(
                    "SELECT event FROM system_events WHERE component = "
                    "'activate_strategy_version' AND message LIKE :like ORDER BY created_at"
                ),
                {"like": like},
            )
        )
        .scalars()
        .all()
    )


GATE_SIDEWAYS: dict[str, Any] = {
    "regime": {
        "allow": ["SIDEWAYS"],
        "classifier_version": "regime_hourly_v1",
        "rule": "previous_closed_hour",
        "scope": "btc",
    }
}
"""O portão da T3.52 na forma canônica em que a coluna o guarda."""

SERIES_HOUR = datetime(2026, 9, 8, 14, tzinfo=UTC)
"""Uma hora fechada da série da T3.43 (``btc``/``regime_hourly_v1``). Existe
porque ``--policy`` só é aceito quando o par ``(scope, classifier_version)`` tem
série: um teste que não a semeasse estaria testando a recusa, não a derivação."""

GATE_GLOBAL: dict[str, Any] = {
    "regime": {
        "allow": ["SIDEWAYS"],
        "classifier_version": "regime_hourly_v1",
        "rule": "previous_closed_hour",
        "scope": "global",
    }
}
"""Um portão gramaticalmente válido e **sem série nenhuma** por trás: o escopo
``global`` nunca recebeu linha da passada horária. É o caso da R4."""

OVERRIDE = {"volume_mult": "5.5"}
"""One parameter, explicitly. ``volume_mult`` is the frozen contract's own
``DECIMAL_PARAM`` — the same shape ``atr_pct_min`` has in ``momentum_v1``, which
is the variant this task actually derives in production (KB-0008)."""


@pytest.mark.integration
class TestDeriveVariant:
    async def test_a_dry_run_names_the_variant_and_writes_nothing(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "variant_dry"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            message = await script.derive_variant(
                session,
                key,
                "v1",
                "dry run",
                overrides=dict(OVERRIDE),
                dry_run=True,
                registry=registry_for(key),
            )
        assert message.startswith(f"derivaria {key} v2 de v1 (purpose research_only, draft")
        assert "volume_mult 4 -> 5.5" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            assert [r.version for r in await _rows(session, key)] == ["v1"]
            assert await _events(session, f"{key} v2%") == []

    async def test_the_variant_copies_everything_but_the_override(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "variant_real"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            message = await script.derive_variant(
                session,
                key,
                "v1",
                "KB-0008: piso de custo",
                overrides=dict(OVERRIDE),
                dry_run=False,
                registry=registry_for(key),
            )
        assert message.startswith(f"derivada {key} v2 de v1 (purpose research_only, draft")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            parent, variant = await _rows(session, key)
            events = await _events(session, f"{key} v2 derived from v1%")
        # The parent is untouched: still active, still frozen, still its own value.
        assert parent.status == "active"
        assert parent.activated_at is not None
        assert parent.default_parameters["volume_mult"] == "4"
        # The variant is a draft that nothing has activated.
        assert variant.version == "v2"
        assert variant.status == "draft"
        assert variant.activated_at is None
        assert variant.purpose == PURPOSE_RESEARCH_ONLY
        assert variant.code_ref == parent.code_ref
        assert variant.params_format == parent.params_format
        assert variant.parameters_schema == parent.parameters_schema
        # Exactly one parameter moved, and it moved to the canonical form.
        assert variant.default_parameters["volume_mult"] == "5.5"
        assert {k: v for k, v in variant.default_parameters.items() if k != "volume_mult"} == {
            k: v for k, v in parent.default_parameters.items() if k != "volume_mult"
        }
        assert params_hash(dict(variant.default_parameters)) != params_hash(
            dict(parent.default_parameters)
        )
        # The lineage is in the changelog, in the frozen spelling.
        assert variant.changelog.startswith(
            "variante de v1 | derived_from=v1 | overrides=volume_mult=5.5 | params_hash="
        )
        assert variant.changelog.endswith(" | KB-0008: piso de custo")
        assert events == ["strategy_version_variant_derived"]

    async def test_it_refuses_a_parameter_the_frozen_schema_does_not_declare(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "variant_unknown_param"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="não declara esse parâmetro"):
                await script.derive_variant(
                    session,
                    key,
                    "v1",
                    "x",
                    overrides={"invalidation_closes": "2"},
                    dry_run=True,
                    registry=registry_for(key),
                )

    async def test_it_refuses_a_value_the_frozen_schema_rejects(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "variant_bad_value"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="não validam contra o schema"):
                await script.derive_variant(
                    session,
                    key,
                    "v1",
                    "x",
                    overrides={"atr_timeframe": "30m"},
                    dry_run=True,
                    registry=registry_for(key),
                )

    async def test_it_refuses_a_variant_that_is_the_parent(self, db_session_factory: Any) -> None:
        """``4`` and ``4.0`` are the same parameter set (``params_format = 1``):
        deriving it would be the same experiment counted twice."""
        script = _script()
        key = "variant_no_move"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="nenhum parâmetro se moveu"):
                await script.derive_variant(
                    session,
                    key,
                    "v1",
                    "x",
                    overrides={"volume_mult": "4.0"},
                    dry_run=True,
                    registry=registry_for(key),
                )

    async def test_it_refuses_the_same_variant_twice(self, db_session_factory: Any) -> None:
        script = _script()
        key = "variant_twice"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            await script.derive_variant(
                session,
                key,
                "v1",
                "first",
                overrides=dict(OVERRIDE),
                dry_run=False,
                registry=registry_for(key),
            )
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="mesmo experimento contado duas vezes"):
                await script.derive_variant(
                    session,
                    key,
                    "v1",
                    "second",
                    overrides=dict(OVERRIDE),
                    dry_run=False,
                    registry=registry_for(key),
                )

    async def test_it_refuses_a_parent_that_was_never_frozen(self, db_session_factory: Any) -> None:
        script = _script()
        key = "variant_draft_parent"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key, active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="nunca foi ativada"):
                await script.derive_variant(
                    session,
                    key,
                    "v1",
                    "x",
                    overrides=dict(OVERRIDE),
                    dry_run=True,
                    registry=registry_for(key),
                )

    async def test_it_refuses_a_parent_that_may_reach_a_wallet(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "variant_from_paper"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
        async with db_session_factory() as session, session.begin():
            await activate_version(session, key=key, purpose=PURPOSE_PAPER)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="research_only"):
                await script.derive_variant(
                    session,
                    key,
                    "v1",
                    "x",
                    overrides=dict(OVERRIDE),
                    dry_run=True,
                    registry=registry_for(key),
                )

    async def test_it_refuses_a_parent_frozen_against_other_code(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "variant_drifted"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session,
                key=key,
                code_ref="hunter_core.strategies.volume_anomaly_v1@sha256:" + "0" * 64,
            )
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="uma variante roda exatamente o código"):
                await script.derive_variant(
                    session,
                    key,
                    "v1",
                    "x",
                    overrides=dict(OVERRIDE),
                    dry_run=True,
                    registry=registry_for(key),
                )


@pytest.mark.integration
class TestActivatingTheVariant:
    async def test_activation_keeps_the_override_and_the_lineage(
        self, db_session_factory: Any
    ) -> None:
        """The whole point of the ``_DERIVED`` branch in the ops script: the
        plain research path would rewrite ``default_parameters`` from today's
        code and freeze the parent's value into the variant."""
        derive, activate = _script(), _activation_script()
        key = "variant_then_activate"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            await derive.derive_variant(
                session,
                key,
                "v1",
                "KB-0008: piso de custo",
                overrides=dict(OVERRIDE),
                dry_run=False,
                registry=registry_for(key),
            )
        async with db_session_factory() as session, session.begin():
            message = await activate.activate(
                session,
                key,
                "v2",
                "T3.26: coorte de pesquisa aberta",
                dry_run=False,
                registry=registry_for(key),
            )
        assert message.startswith(f"activated {key} v2 (purpose research_only)")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            parent, variant = await _rows(session, key)
        assert variant.status == "active"
        assert variant.activated_at is not None
        assert variant.default_parameters["volume_mult"] == "5.5"
        assert parent.default_parameters["volume_mult"] == "4"
        assert variant.changelog.startswith("variante de v1 | derived_from=v1 |")
        assert variant.changelog.endswith(" | T3.26: coorte de pesquisa aberta")

    async def test_a_dry_run_activation_writes_nothing(self, db_session_factory: Any) -> None:
        derive, activate = _script(), _activation_script()
        key = "variant_activate_dry"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            await derive.derive_variant(
                session,
                key,
                "v1",
                "x",
                overrides=dict(OVERRIDE),
                dry_run=False,
                registry=registry_for(key),
            )
        async with db_session_factory() as session, session.begin():
            message = await activate.activate(
                session, key, "v2", "x", dry_run=True, registry=registry_for(key)
            )
        assert message.startswith(f"would activate {key} v2 (purpose research_only)")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            _, variant = await _rows(session, key)
        assert variant.status == "draft"
        assert variant.activated_at is None

    async def test_a_variant_that_only_moves_the_gate_is_a_variant(
        self, db_session_factory: Any
    ) -> None:
        """T3.52: o portão é conteúdo da versão sem ser parâmetro dela, então uma
        variante sem ``--set`` é legítima — e nasce com o **mesmo**
        ``params_hash`` do pai, de propósito."""
        script = _script()
        key = "variant_gate_only"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
            await insert_hourly_regime(session, hour=SERIES_HOUR)
        async with db_session_factory() as session, session.begin():
            message = await script.derive_variant(
                session,
                key,
                "v1",
                "T3.52: só decide em lateral",
                overrides={},
                dry_run=False,
                policy="regime=btc:SIDEWAYS",
                registry=registry_for(key),
            )
        assert "policy -> btc:SIDEWAYS" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            parent, variant = await _rows(session, key)
            gate = (
                await session.execute(
                    text(
                        "SELECT eligibility_policy FROM strategy_versions v "
                        "JOIN strategies s ON s.id = v.strategy_id "
                        "WHERE s.key = :key AND v.version = 'v2'"
                    ),
                    {"key": key},
                )
            ).scalar_one()
        assert variant.status == "draft"
        assert variant.activated_at is None
        assert variant.default_parameters == parent.default_parameters
        assert params_hash(dict(variant.default_parameters)) == params_hash(
            dict(parent.default_parameters)
        )
        assert gate == {
            "regime": {
                "allow": ["SIDEWAYS"],
                "classifier_version": "regime_hourly_v1",
                "rule": "previous_closed_hour",
                "scope": "btc",
            }
        }
        assert variant.changelog.startswith(
            "variante de v1 | derived_from=v1 | overrides= | params_hash="
        )
        assert "| policy=btc:SIDEWAYS |" in variant.changelog

    async def test_the_child_inherits_the_parents_gate_and_the_twin_check_sees_it(
        self, db_session_factory: Any
    ) -> None:
        """Sem ``--policy`` a variante herda o portão — e uma segunda variante
        com o mesmo conjunto **e** o mesmo portão é recusada como duplicata,
        enquanto a mesma com portão diferente é outro experimento."""
        derive = _script()
        key = "variant_gate_inherit"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key, policy=GATE_SIDEWAYS)
            await insert_hourly_regime(session, hour=SERIES_HOUR)
        async with db_session_factory() as session, session.begin():
            await derive.derive_variant(
                session,
                key,
                "v1",
                "herda o portão",
                overrides=dict(OVERRIDE),
                dry_run=False,
                registry=registry_for(key),
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            inherited = (
                await session.execute(
                    text(
                        "SELECT eligibility_policy FROM strategy_versions v "
                        "JOIN strategies s ON s.id = v.strategy_id "
                        "WHERE s.key = :key AND v.version = 'v2'"
                    ),
                    {"key": key},
                )
            ).scalar_one()
        assert inherited == GATE_SIDEWAYS
        with pytest.raises(derive.Refused, match="mesmo experimento contado duas vezes"):
            async with db_session_factory() as session, session.begin():
                await derive.derive_variant(
                    session,
                    key,
                    "v1",
                    "de novo",
                    overrides=dict(OVERRIDE),
                    dry_run=True,
                    registry=registry_for(key),
                )
        async with db_session_factory() as session, session.begin():
            message = await derive.derive_variant(
                session,
                key,
                "v1",
                "mesmo conjunto, outro portão",
                overrides=dict(OVERRIDE),
                dry_run=True,
                policy="regime=btc:BTC_BULL",
                registry=registry_for(key),
            )
        assert "policy -> btc:BTC_BULL" in message

    async def test_it_refuses_a_gate_it_cannot_honour_before_writing_anything(
        self, db_session_factory: Any
    ) -> None:
        """O mesmo validador do worker: rótulo que não é ``MarketRegime``,
        ``UNKNOWN`` (aquecimento do classificador) e ``none`` sem portão do pai."""
        script = _script()
        key = "variant_gate_refused"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        for argument, message in (
            ("regime=btc:LATERAL", "is not a MarketRegime label"),
            ("regime=btc:UNKNOWN", "UNKNOWN cannot be allowed"),
            ("sessao=btc:SIDEWAYS", "expected regime="),
            ("none", "não há o que remover"),
        ):
            with pytest.raises(script.Refused, match=message):
                async with db_session_factory() as session, session.begin():
                    await script.derive_variant(
                        session,
                        key,
                        "v1",
                        "recusa",
                        overrides={},
                        dry_run=True,
                        policy=argument,
                        registry=registry_for(key),
                    )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            assert [r.version for r in await _rows(session, key)] == ["v1"]

    async def test_it_refuses_a_gate_whose_pair_has_no_series_in_market_regimes(
        self, db_session_factory: Any
    ) -> None:
        """R4 da revisão do arquiteto: ``classifier_version`` não tem lista
        fechada — nem pode ter, o nome vem do produtor (T3.43) —, então o par
        ``(scope, classifier_version)`` é conferido contra ``market_regimes``
        na hora de escrever. Sem isso a versão entraria no roster e recusaria
        **toda** barra por ``regime_gate:unknown``/``no_row``: fecha, como deve,
        mas em silêncio, e o operador só descobriria pela ausência de sinais.
        A recusa nomeia o par, e vem antes de qualquer escrita — inclusive num
        ``--dry-run``, que é onde o operador espera ouvir isso.
        """
        script = _script()
        key = "variant_gate_no_series"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
            await insert_hourly_regime(session, hour=SERIES_HOUR)
            absent = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM market_regimes WHERE scope = 'global' "
                        "AND classifier_version = 'regime_hourly_v1'"
                    )
                )
            ).scalar_one()
        assert absent == 0, "premissa do teste: esse par nunca foi escrito"
        with pytest.raises(
            script.Refused, match="scope=global, classifier_version=regime_hourly_v1"
        ):
            async with db_session_factory() as session, session.begin():
                await script.derive_variant(
                    session,
                    key,
                    "v1",
                    "escopo sem série",
                    overrides=dict(OVERRIDE),
                    dry_run=True,
                    policy="regime=global:SIDEWAYS",
                    registry=registry_for(key),
                )
        async with db_session_factory() as session, session.begin():
            message = await script.derive_variant(
                session,
                key,
                "v1",
                "escopo com série",
                overrides=dict(OVERRIDE),
                dry_run=True,
                policy="regime=btc:SIDEWAYS",
                registry=registry_for(key),
            )
        assert "policy -> btc:SIDEWAYS" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            assert [r.version for r in await _rows(session, key)] == ["v1"]

    async def test_an_inherited_gate_is_not_re_checked_against_the_series(
        self, db_session_factory: Any
    ) -> None:
        """O outro lado da R4, e o limite dela: a checagem é de **escrita**, não
        de leitura. Um portão herdado já passou por ela quando foi escrito, e
        re-conferi-lo faria uma variante de ``--set`` — que não fala de portão
        nenhum — ser recusada porque a série do produtor foi podada. Quem cobra
        a série ausente em tempo de decisão é o próprio portão
        (``regime_gate:unknown``/``no_row``), que é o lugar certo.
        """
        script = _script()
        key = "variant_gate_inherited_no_series"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key, policy=GATE_GLOBAL)
        async with db_session_factory() as session, session.begin():
            message = await script.derive_variant(
                session,
                key,
                "v1",
                "só o parâmetro se move; o portão vem junto",
                overrides=dict(OVERRIDE),
                dry_run=False,
                registry=registry_for(key),
            )
        assert "volume_mult" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            inherited = (
                await session.execute(
                    text(
                        "SELECT eligibility_policy FROM strategy_versions v "
                        "JOIN strategies s ON s.id = v.strategy_id "
                        "WHERE s.key = :key AND v.version = 'v2'"
                    ),
                    {"key": key},
                )
            ).scalar_one()
        assert inherited == GATE_GLOBAL
