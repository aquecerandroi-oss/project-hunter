"""A rota de pesquisa não reescreve o conteúdo de uma linha derivada (A1/A4).

``activate()`` reconhecia uma linha derivada por dois sinais **que a coluna
``changelog`` carrega** — e ``changelog`` não é congelada pela trigger da
``0002``. A revisão risk-engine-guardian de ``be3674a`` (A1, ALTA) mostrou duas
formas de perder esses sinais:

- a imagem da VPS anterior a ``be3674a`` só escrevia ``paper line of``, então
  derivar com o script de hoje (``docker exec ... < derive_variant.py``) e ativar
  com o script *da imagem* caía na rota de pesquisa;
- um ``UPDATE`` manual no ``changelog`` apaga a linhagem.

Nos dois casos a rota de pesquisa reescrevia ``default_parameters`` a partir do
código de hoje e congelava o experimento **errado** sob o número da variante,
imprimindo ``activated`` como se nada tivesse acontecido. A trava agora é
estrutural: um rascunho que já tem conjunto próprio nunca é reescrito.

A4 no mesmo arquivo porque é a mesma corrida: o evento de ativação passa a
carregar de quem a linha veio, qual conjunto exatamente foi congelado e o
``changelog`` como ficou.

Roda contra o schema migrado na conexão do dono, como ``test_derive_variant.py``.

Run: ``uv run pytest services/strategy-worker/tests/test_activate_derived_guard.py -q``
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import uuid7
from hunter_core.strategies.canonical import canonical_json, params_hash
from hunter_core.strategies.envelope import PURPOSE_PAPER, PURPOSE_RESEARCH_ONLY
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker.activate_derived import activate_derived
from hunter_strategy_worker.activation_db import load_row

from .builders import activate_version, registry_for, seed_market

REPO_ROOT = Path(__file__).resolve().parents[3]

OVERRIDE = {"volume_mult": "5.5"}


def _module(name: str, filename: str) -> Any:
    path = REPO_ROOT / "infra" / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _derive() -> Any:
    return _module("derive_variant_guard", "derive_variant.py")


def _activate() -> Any:
    return _module("activate_guard", "activate_strategy_version.py")


async def _row(session: Any, key: str, version: str) -> Any:
    return (
        await session.execute(
            text(
                "SELECT v.version, v.status, v.purpose, v.activated_at, v.default_parameters, "
                "v.changelog FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id "
                "WHERE s.key = :key AND v.version = :version"
            ),
            {"key": key, "version": version},
        )
    ).first()


async def _messages(session: Any, like: str) -> list[str]:
    return list(
        (
            await session.execute(
                text(
                    "SELECT message FROM system_events WHERE component = "
                    "'activate_strategy_version' AND event = 'strategy_version_activated' "
                    "AND message LIKE :like ORDER BY created_at"
                ),
                {"like": like},
            )
        )
        .scalars()
        .all()
    )


async def _erase_lineage(session: Any, key: str, version: str) -> None:
    """O ``UPDATE`` manual que a revisão descreve: a linhagem some do changelog.

    Legítimo no banco — ``changelog`` não está entre as colunas que a trigger da
    ``0002`` congela, e a linha ainda é um rascunho.
    """
    await session.execute(
        text(
            "UPDATE strategy_versions v SET changelog = 'ajuste de nota do operador' "
            "FROM strategies s WHERE s.id = v.strategy_id AND s.key = :key AND v.version = :version"
        ),
        {"key": key, "version": version},
    )


async def _seed_style_draft(session: Any, key: str) -> uuid.UUID:
    """Um rascunho como ``seed.py`` escreve: sem ``default_parameters``.

    É o caso que a trava **não** pode quebrar — é assim que toda primeira
    ativação de pesquisa começa.
    """
    strategy_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO strategies (id, key, name) VALUES (:id, :key, :name) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"id": strategy_id, "key": key, "name": key},
    )
    strategy_id = await session.scalar(
        text("SELECT id FROM strategies WHERE key = :key"), {"key": key}
    )
    await session.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version, status, code_ref) "
            "VALUES (:id, :strategy_id, 'v1', 'draft', :code_ref)"
        ),
        {
            "id": uuid7(),
            "strategy_id": strategy_id,
            "code_ref": f"hunter_indicators.strategies.{key}_v1",
        },
    )
    return strategy_id


@pytest.mark.integration
class TestTheStructuralGuard:
    async def test_a_variant_whose_lineage_was_erased_is_still_refused(
        self, db_session_factory: Any
    ) -> None:
        """O caso exato da A1: sem a frase no ``changelog``, a rota de pesquisa
        reescreveria ``volume_mult`` de 5.5 para 4 e ninguém saberia."""
        derive, activate = _derive(), _activate()
        key = "guard_erased_lineage"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            await derive.derive_variant(
                session,
                key,
                "v1",
                "KB-0008",
                overrides=dict(OVERRIDE),
                dry_run=False,
                registry=registry_for(key),
            )
            await _erase_lineage(session, key, "v2")
        async with db_session_factory() as session, session.begin():
            with pytest.raises(
                activate.Refused, match="already carries its own default_parameters"
            ):
                await activate.activate(
                    session, key, "v2", "T3.26c", dry_run=False, registry=registry_for(key)
                )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            variant = await _row(session, key, "v2")
        assert variant.status == "draft"
        assert variant.activated_at is None
        assert variant.default_parameters["volume_mult"] == "5.5"

    async def test_a_dry_run_is_refused_too_so_the_operator_learns_first(
        self, db_session_factory: Any
    ) -> None:
        derive, activate = _derive(), _activate()
        key = "guard_erased_dry"
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
            await _erase_lineage(session, key, "v2")
        async with db_session_factory() as session, session.begin():
            with pytest.raises(activate.Refused, match="freeze the wrong experiment"):
                await activate.activate(
                    session, key, "v2", "x", dry_run=True, registry=registry_for(key)
                )

    async def test_the_derived_route_still_accepts_the_very_same_row(
        self, db_session_factory: Any
    ) -> None:
        """A recusa não é um beco sem saída: a rota derivada — que é a correta —
        ativa a mesma linha preservando o conteúdo dela."""
        derive = _derive()
        key = "guard_derived_route"
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
            await _erase_lineage(session, key, "v2")
        async with db_session_factory() as session, session.begin():
            row = await load_row(session, key, "v2")
            message = await activate_derived(
                session,
                key,
                "v2",
                "T3.26c: ativada pela rota derivada",
                row,
                code_ref=row.code_ref,
                dry_run=False,
            )
        assert message.startswith(f"activated {key} v2 (purpose {PURPOSE_RESEARCH_ONLY})")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            variant = await _row(session, key, "v2")
        assert variant.status == "active"
        assert variant.default_parameters["volume_mult"] == "5.5"

    async def test_a_seed_draft_with_no_parameters_still_activates(
        self, db_session_factory: Any
    ) -> None:
        """A trava só morde um conjunto próprio: a primeira ativação de pesquisa,
        que é o caso normal, continua escrevendo os parâmetros do código."""
        activate = _activate()
        key = "guard_seed_draft"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
        async with db_session_factory() as session, session.begin():
            await _seed_style_draft(session, key)
        async with db_session_factory() as session, session.begin():
            message = await activate.activate(
                session, key, "v1", "primeira ativação", dry_run=False, registry=registry_for(key)
            )
        assert message.startswith(f"activated {key} v1 (purpose {PURPOSE_RESEARCH_ONLY})")
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            row = await _row(session, key, "v1")
        assert row.default_parameters == json.loads(
            canonical_json(dict(VOLUME_ANOMALY_V1.default_parameters))
        )

    async def test_a_draft_carrying_exactly_the_codes_own_set_is_not_refused(
        self, db_session_factory: Any
    ) -> None:
        """Reescrever o que já está lá não apaga experimento nenhum: o que a
        trava compara é o ``params_hash``, não a presença."""
        activate = _activate()
        key = "guard_same_params"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key, active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            message = await activate.activate(
                session, key, "v1", "mesma coisa", dry_run=False, registry=registry_for(key)
            )
        assert message.startswith(f"activated {key} v1")


@pytest.mark.integration
class TestTheActivationEvent:
    async def test_it_names_the_parent_the_params_hash_and_the_kept_changelog(
        self, db_session_factory: Any
    ) -> None:
        derive, activate = _derive(), _activate()
        key = "event_variant"
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
            await activate.activate(
                session, key, "v2", "coorte aberta", dry_run=False, registry=registry_for(key)
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            variant = await _row(session, key, "v2")
            (message,) = await _messages(session, f"{key} v2 %")
        expected = params_hash(dict(variant.default_parameters))
        assert "derived_from=v1" in message
        assert f"params_hash={expected}" in message
        assert "variante de v1 | derived_from=v1 | overrides=volume_mult=5.5" in message
        assert "coorte aberta" in message

    async def test_a_paper_line_activation_names_its_source_too(
        self, db_session_factory: Any
    ) -> None:
        activate = _activate()
        key = "event_paper_line"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            await activate.paper_line(
                session, key, "v1", "D10", dry_run=False, registry=registry_for(key)
            )
        async with db_session_factory() as session, session.begin():
            await activate.activate(
                session, key, "v2", "D10 cumprida", dry_run=False, registry=registry_for(key)
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            paper = await _row(session, key, "v2")
            (message,) = await _messages(session, f"{key} v2 %")
        assert paper.purpose == PURPOSE_PAPER
        assert "derived_from=v1" in message
        assert f"params_hash={params_hash(dict(paper.default_parameters))}" in message
