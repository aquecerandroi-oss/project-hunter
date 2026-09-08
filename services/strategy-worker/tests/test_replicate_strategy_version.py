"""``replicate_strategy_version.py`` — as irmãs de uma versão promissora (T3.19).

Roda contra o schema migrado na conexão do **dono**, como o script roda
(``DATABASE_URL_MIGRATIONS``): ``0011`` revogou ``INSERT`` em
``strategy_versions`` de todo papel de aplicação e ``purpose`` só o dono escreve.
O padrão é o de ``test_activate_paper_line.py``.

O que estes testes garantem, além do caminho feliz: um pai não promissor é
**recusado**, uma segunda replicação do mesmo pai é **recusada**, o pai nunca é
tocado, e as irmãs — que rodam como qualquer versão de pesquisa ativa — são
recusadas pela ponte de execução pelo nome do ``purpose``, antes de qualquer
consulta de carteira.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowCohort, TradeDirection
from hunter_core.strategies.envelope import PURPOSE_PAPER, PURPOSE_RESEARCH_ONLY
from hunter_strategy_worker.activation_db import Refused
from hunter_strategy_worker.catalogue import load_version_roster
from hunter_strategy_worker.replication_stats import (
    arm_label,
    build_report,
    load_sibling_rows,
)

from .builders import activate_version, registry_for

REPO_ROOT = Path(__file__).resolve().parents[3]

EXCHANGE = "replication"
HALF_A = ("BTCUSDT", "LINKUSDT", "TONUSDT")
HALF_B = ("ETHUSDT", "SOLUSDT", "XRPUSDT")
SYMBOLS = HALF_A + HALF_B
"""Metades reais de ``market_half`` sobre a chave ``<exchange>:<symbol>`` que o
bloco 3 usa — três mercados de cada lado, o mínimo que ele exige. A corretora é
fixa porque ela entra no hash; um prefixo por teste moveria as metades."""

WINNER = [Decimal("1"), Decimal("1"), Decimal("1"), Decimal("-0.5"), Decimal("-0.5")]
"""Expectancy 0,4 R e PF 3 — o pai fica ``validada`` na régua do placar."""

LOSER = [Decimal("-1"), Decimal("-1"), Decimal("-1"), Decimal("0.5"), Decimal("0.5")]
"""Expectancy −0,4 R e PF 1/3 — ``reprovada``, e madura o bastante para isso."""

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _script() -> Any:
    path = REPO_ROOT / "infra" / "scripts" / "replicate_strategy_version.py"
    spec = importlib.util.spec_from_file_location("replicate_strategy_version_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["replicate_strategy_version_test"] = module
    spec.loader.exec_module(module)
    return module


async def _seed_markets(session: Any) -> list[uuid.UUID]:
    exchange_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO exchanges (id, code, name, status) VALUES (:id, :code, :name, 'active') "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {"id": exchange_id, "code": EXCHANGE, "name": "Test"},
    )
    exchange_id = await session.scalar(
        text("SELECT id FROM exchanges WHERE code = :code"), {"code": EXCHANGE}
    )
    ids: list[uuid.UUID] = []
    for symbol in SYMBOLS:
        market_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, status, "
                "is_monitored, monitor_rank, volume_24h_usd, last_seen_at) "
                "VALUES (:id, :exchange_id, :symbol, 'perpetual', 'active', true, 1, 1000000, "
                "now()) ON CONFLICT (exchange_id, symbol, market_type) DO NOTHING"
            ),
            {"id": market_id, "exchange_id": exchange_id, "symbol": symbol},
        )
        ids.append(
            await session.scalar(
                text(
                    "SELECT id FROM markets WHERE exchange_id = :exchange_id AND symbol = :symbol "
                    "AND market_type = 'perpetual'"
                ),
                {"exchange_id": exchange_id, "symbol": symbol},
            )
        )
    return ids


async def _seed_outcomes(
    session: Any,
    version_id: uuid.UUID,
    markets: list[uuid.UUID],
    *,
    days: int,
    per_day: int,
    values: list[Decimal] = WINNER,
    start: datetime = START,
    cohort: str = ShadowCohort.PROSPECTIVE,
) -> int:
    """``days × per_day`` resultados **avaliáveis pela régua do placar**.

    Avaliável tem uma definição só (T3.18c, item 2), e ela exige mais que
    ``terminal`` com R conhecido: coorte declarada no envelope, ``exit_ts`` e
    horizonte transcorrido (``entry_plan.entry_bar_open + horizon_s``). Uma
    fixture que escrevesse menos que isso estaria testando uma população que o
    worker nunca produz.
    """
    rows: list[dict[str, Any]] = []
    index = 0
    for day in range(days):
        for slot in range(per_day):
            emitted = start + timedelta(days=day, minutes=slot * 7)
            entry_bar_open = emitted + timedelta(minutes=1)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "version": version_id,
                    "market": markets[index % len(markets)],
                    "emitted": emitted,
                    "exit_ts": emitted + timedelta(hours=1),
                    "r": values[index % len(values)],
                    "envelope": json.dumps(
                        {
                            "cohort": cohort,
                            "decision_at": emitted.isoformat(),
                            "observation_ts": (emitted - timedelta(seconds=5)).isoformat(),
                            "purpose": PURPOSE_RESEARCH_ONLY,
                        }
                    ),
                    "meta": json.dumps(
                        {
                            "cohort": cohort,
                            "horizon_s": 14400,
                            "entry_plan": {"entry_bar_open": entry_bar_open.isoformat()},
                        }
                    ),
                }
            )
            index += 1
    await session.execute(
        text(
            "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, "
            "direction, confidence, emitted_at, supporting_features) "
            "VALUES (:id, :version, :market, 'test', 'long', 0.5, :emitted, "
            "CAST(:envelope AS jsonb))"
        ),
        rows,
    )
    await session.execute(
        text(
            "INSERT INTO signal_outcomes (signal_id, result, tracking_state, r_multiple, "
            "exit_ts, meta) "
            "VALUES (:id, 'target', 'terminal', :r, :exit_ts, CAST(:meta AS jsonb))"
        ),
        rows,
    )
    return len(rows)


async def _versions(session: Any, key: str) -> list[Any]:
    return list(
        (
            await session.execute(
                text(
                    "SELECT v.id, v.version, v.status, v.purpose, v.activated_at, v.code_ref, "
                    "v.default_parameters, v.parameters_schema, v.params_format, "
                    "v.changelog, v.promising_at, v.promising_by, "
                    "v.replication_parent_id, v.replication_index "
                    "FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id "
                    "WHERE s.key = :key ORDER BY length(v.version), v.version"
                ),
                {"key": key},
            )
        ).all()
    )


async def _events(session: Any, version_id: uuid.UUID) -> list[Any]:
    return list(
        (
            await session.execute(
                text(
                    "SELECT event, level::text AS level, data FROM system_events "
                    "WHERE component = 'replicate_strategy_version' "
                    "AND data ->> 'strategy_version_id' = :id ORDER BY created_at"
                ),
                {"id": str(version_id)},
            )
        ).all()
    )


@pytest.mark.integration
class TestReplicate:
    async def test_it_refuses_a_parent_the_scoreboard_has_not_validated(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "replication_not_promising"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="não é promissora"):
                await script.replicate(
                    session, key, "v1", "x", dry_run=True, seed=1, registry=registry_for(key)
                )

    async def test_force_research_replicates_anyway_and_is_audited_as_a_warning(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "replication_forced"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            message = await script.replicate(
                session,
                key,
                "v1",
                "x",
                dry_run=False,
                siblings=3,
                seed=5,
                force_research="experimento manual do Everton",
                registry=registry_for(key),
            )
        assert "[FORÇADO]" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            rows = await _versions(session, key)
            events = await _events(session, rows[0].id)
        assert [row.version for row in rows] == ["v1", "v2", "v3", "v4"]
        # Forçado não é promissor: nenhum ``promising_at`` foi inventado.
        assert [event.event for event in events] == ["strategy_version_replicated"]
        assert events[0].level == "warning"
        assert events[0].data["forced"] is True

    async def test_a_positive_replay_never_makes_a_refuted_parent_promising(
        self, db_session_factory: Any
    ) -> None:
        """T3.18c, item 1 (Astra, HIGH): a CLI não é enganável por replay.

        Cenário: prospectivo **maduro e negativo** (200 resultados, 40 dias,
        expectancy −0,4 R) — ``reprovada`` sem ambiguidade — e um replay
        histórico grande e positivo (200 resultados, 40 dias, +0,4 R) sob
        ``replay:<uuid>``. Antes, a consulta do worker não filtrava coorte: as
        duas populações somavam expectancy zero... e, com um replay maior,
        viravam ``validada``, a rodada era aceita sem ``--force-research`` e
        ``promising_at`` — o marco de onde o bloco 1 conta — nascia de
        evidência histórica.
        """
        script = _script()
        key = "replication_replay_leak"
        run = uuid.uuid4()
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            markets = await _seed_markets(session)
            _, version_id = await activate_version(session, key=key)
            await _seed_outcomes(session, version_id, markets, days=40, per_day=5, values=LOSER)
            await _seed_outcomes(
                session,
                version_id,
                markets,
                days=40,
                per_day=5,
                values=WINNER,
                start=START + timedelta(days=100),
                cohort=ShadowCohort.replay(run),
            )
        async with db_session_factory() as session, session.begin():
            report = await build_report(await session.connection(), version_id, seed=1)
            assert report.parent.evaluable == 200, "só o prospectivo entra na conta do pai"
            assert report.parent.expectancy_r == Decimal("-0.4000")
            assert report.parent_verdict == "reprovada"
            with pytest.raises(script.Refused, match="não é promissora"):
                await script.replicate(
                    session, key, "v1", "x", dry_run=False, seed=1, registry=registry_for(key)
                )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            rows = await _versions(session, key)
        assert [row.version for row in rows] == ["v1"], "nenhuma irmã foi derivada"
        assert rows[0].promising_at is None, "nenhum carimbo nasceu de replay"

    async def test_an_immature_prospective_population_is_not_promising_either(
        self, db_session_factory: Any
    ) -> None:
        """O outro lado do mesmo portão: 100 resultados em 20 dias de saída não
        são 30 dias, e imaturidade é ``inconclusivo``, nunca ``validada``."""
        script = _script()
        key = "replication_immature"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            markets = await _seed_markets(session)
            _, version_id = await activate_version(session, key=key)
            await _seed_outcomes(session, version_id, markets, days=20, per_day=5)
        async with db_session_factory() as session, session.begin():
            report = await build_report(await session.connection(), version_id, seed=1)
            assert (report.parent.evaluable, report.parent.days) == (100, 20)
            assert report.parent_verdict == "inconclusivo"
            with pytest.raises(script.Refused, match="não é promissora"):
                await script.replicate(
                    session, key, "v1", "x", dry_run=True, seed=1, registry=registry_for(key)
                )

    async def test_a_dry_run_names_the_siblings_and_writes_nothing(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "replication_dry"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            markets = await _seed_markets(session)
            _, version_id = await activate_version(session, key=key)
            await _seed_outcomes(session, version_id, markets, days=40, per_day=5)
        async with db_session_factory() as session, session.begin():
            message = await script.replicate(
                session, key, "v1", "dry", dry_run=True, seed=99, registry=registry_for(key)
            )
        assert "derivaria 10 irmãs" in message
        assert arm_label(version_id, 1) in message
        assert "volume_mult" in message  # o contrato congelado do fixture é volume_anomaly_v1
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            assert [row.version for row in await _versions(session, key)] == ["v1"]
            assert await _events(session, version_id) == []

    async def test_it_derives_ten_research_siblings_and_never_touches_the_parent(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "replication_real"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            markets = await _seed_markets(session)
            _, version_id = await activate_version(session, key=key)
            await _seed_outcomes(session, version_id, markets, days=40, per_day=5)
        async with db_session_factory() as session, session.begin():
            message = await script.replicate(
                session,
                key,
                "v1",
                "T3.19",
                dry_run=False,
                seed=20260908,
                registry=registry_for(key),
            )
        assert message.startswith("criadas 10 irmãs")
        assert "nada foi ativado para a carteira" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            rows = await _versions(session, key)
            events = await _events(session, version_id)
            siblings = await load_sibling_rows(await session.connection(), version_id)
        parent, *derived = rows
        assert len(derived) == 10
        assert parent.version == "v1"
        assert parent.purpose == PURPOSE_RESEARCH_ONLY
        assert parent.changelog is None or "replication:" not in parent.changelog
        hashes = {json.dumps(row.default_parameters, sort_keys=True) for row in rows}
        assert len(hashes) == 11, "cada irmã tem o seu próprio conjunto de parâmetros"
        for index, row in enumerate(derived, start=1):
            assert row.status == "active"
            assert row.purpose == PURPOSE_RESEARCH_ONLY
            assert row.activated_at is not None
            assert row.code_ref == parent.code_ref
            assert row.parameters_schema == parent.parameters_schema
            assert row.params_format == parent.params_format
            assert row.changelog.startswith(arm_label(version_id, index))
            assert "promising_at=" in row.changelog
            assert "seed=20260908" in row.changelog
            # 0012_replication: a linhagem é coluna, não uma frase do changelog
            assert row.replication_parent_id == version_id
            assert row.replication_index == index
            # e a irmã não é ela própria promissora — o carimbo é do pai
            assert row.promising_at is None
        # O pai é tocado numa coluna só, e é a razão da 0012 (DATABASE.md §24).
        assert parent.promising_at is not None
        assert parent.promising_by == "replicate_strategy_version:validada"
        assert parent.replication_parent_id is None and parent.replication_index is None
        assert [event.event for event in events] == [
            "strategy_version_promising",
            "strategy_version_replicated",
        ]
        assert events[1].data["parent_verdict"] == "validada"
        assert events[1].data["purpose"] == PURPOSE_RESEARCH_ONLY
        assert [row.k for row in siblings] == list(range(1, 11))

    async def test_a_second_replication_of_the_same_parent_is_refused(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "replication_twice"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            markets = await _seed_markets(session)
            _, version_id = await activate_version(session, key=key)
            await _seed_outcomes(session, version_id, markets, days=40, per_day=5)
        async with db_session_factory() as session, session.begin():
            await script.replicate(
                session,
                key,
                "v1",
                "first",
                dry_run=False,
                siblings=2,
                seed=1,
                registry=registry_for(key),
            )
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="já tem 2 irmãs"):
                await script.replicate(
                    session,
                    key,
                    "v1",
                    "second",
                    dry_run=False,
                    siblings=2,
                    seed=2,
                    registry=registry_for(key),
                )

    async def test_it_refuses_a_paper_line_and_a_version_that_was_never_frozen(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        draft_key = "replication_draft"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await activate_version(session, key=draft_key, active=False, code_ref=None)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="nunca foi ativada"):
                await script.replicate(
                    session,
                    draft_key,
                    "v1",
                    "x",
                    dry_run=True,
                    seed=1,
                    registry=registry_for(draft_key),
                )
        paper_key = "replication_paper"
        async with db_session_factory() as session, session.begin():
            await activate_version(session, key=paper_key, purpose=PURPOSE_PAPER)
        async with db_session_factory() as session, session.begin():
            with pytest.raises(script.Refused, match="nunca é multiplicada por dez"):
                await script.replicate(
                    session,
                    paper_key,
                    "v1",
                    "x",
                    dry_run=True,
                    seed=1,
                    registry=registry_for(paper_key),
                )

    async def test_the_report_prints_the_four_blocks_without_writing(
        self, db_session_factory: Any
    ) -> None:
        script = _script()
        key = "replication_report"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            markets = await _seed_markets(session)
            _, version_id = await activate_version(session, key=key)
            await _seed_outcomes(session, version_id, markets, days=40, per_day=5)
        async with db_session_factory() as session, session.begin():
            message = await script.report(session, key, "v1", seed=7)
        assert "veredito: none" in message
        assert "pai: validada — 200 resultados avaliáveis, 40 dias, 6 mercados" in message
        assert "market_halves: passou" in message
        assert "bootstrap: passou" in message
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            assert await _events(session, version_id) == []

    async def test_the_siblings_run_like_any_research_version_and_never_reach_the_wallet(
        self, db_session_factory: Any
    ) -> None:
        """Item 4 do brief: as irmãs rodam como qualquer versão de pesquisa ativa,
        e a ponte as recusa pelo ``purpose`` antes de qualquer consulta de carteira.

        Desde a ``0012_replication`` (T3.19c) o rótulo ``replication:<pai>:<k>``
        **é** a coorte do banco e a coorte que a irmã carimba, então a terceira
        barreira deixa de ser hipotética: a ponte recusa por ``purpose`` e, se
        alguém rotulasse a irmã de ``paper``, recusaria de novo pela coorte.
        """
        pytest.importorskip("hunter_execution_worker")
        from hunter_execution_worker.bridge_repo import ShadowSignal
        from hunter_execution_worker.bridge_screen import screen_signal
        from hunter_execution_worker.wallet import WalletRef

        def _signal(version_purpose: str, cohort: str, sibling_id: uuid.UUID) -> ShadowSignal:
            return ShadowSignal(
                signal_id=uuid.uuid4(),
                strategy_version_id=sibling_id,
                perp_market_id=markets[0],
                exchange_id=uuid.uuid4(),
                base_asset_id=None,
                quote_asset_id=None,
                direction=TradeDirection.LONG,
                entry_ref=Decimal("100"),
                stop=Decimal("99"),
                target=Decimal("102"),
                assumed_costs=None,
                source_bar_close=START,
                emitted_at=START,
                purpose=version_purpose,
                envelope_purpose=version_purpose,
                cohort=cohort,
                version_active=True,
            )

        script = _script()
        key = "replication_roster"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            markets = await _seed_markets(session)
            _, version_id = await activate_version(session, key=key)
            await _seed_outcomes(session, version_id, markets, days=40, per_day=5)
        async with db_session_factory() as session, session.begin():
            await script.replicate(
                session,
                key,
                "v1",
                "roster",
                dry_run=False,
                siblings=3,
                seed=3,
                registry=registry_for(key),
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            roster = await load_version_roster(session)
            siblings = await load_sibling_rows(await session.connection(), version_id)
        running = {version.id: version for version in roster.versions}
        wallet = WalletRef(organization_id=uuid.uuid4(), portfolio_id=uuid.uuid4())
        assert siblings, "as irmãs foram criadas"
        for sibling in siblings:
            version = running.get(sibling.id)
            assert version is not None, f"{sibling.version} devia rodar como versão ativa"
            assert version.purpose == PURPOSE_RESEARCH_ONLY
            assert version.params_hash != running[version_id].params_hash
            # Barreira 1: a ponte recusa pelo nome do purpose, antes de
            # qualquer consulta (por isso ``session = None`` basta).
            screened = await screen_signal(
                None,  # type: ignore[arg-type]
                wallet=wallet,
                signal=_signal(version.purpose, ShadowCohort.PROSPECTIVE, sibling.id),
                now=START,
            )
            assert screened.refused == "research_only"
            # Barreira 2 (T3.15e): mesmo que uma irmã fosse rotulada ``paper`` por
            # engano, o filtro de coorte da ponte recusa o rótulo do braço.
            labelled = await screen_signal(
                None,  # type: ignore[arg-type]
                wallet=wallet,
                signal=_signal(PURPOSE_PAPER, arm_label(version_id, sibling.k), sibling.id),
                now=START,
            )
            assert labelled.refused == "cohort_not_live"
            # T3.19c: a pendência da REPLICATION.md §4.4 está fechada. O rótulo
            # do braço é uma coorte que o banco aceita (0012_replication) **e**
            # a coorte que esta irmã de fato carimba — a recusa acima deixa de
            # ser hipotética e passa a descrever o sinal que ela emite.
            assert ShadowCohort.is_valid(arm_label(version_id, sibling.k)) is True
            assert version.cohort(ShadowCohort.PROSPECTIVE) == arm_label(version_id, sibling.k)
        # E o pai, que não é irmã de ninguém, continua carimbando prospective.
        assert running[version_id].cohort(ShadowCohort.PROSPECTIVE) == ShadowCohort.PROSPECTIVE


@pytest.mark.integration
class TestMarkPromising:
    """``promising_at`` é escrito por um lugar só (brief T3.19c, entrega 3).

    O carimbo decide onde o bloco 1 do protocolo começa a contar
    (REPLICATION.md §1.6): dois escritores seriam duas datas, e a mais recente
    ganharia sem que ninguém visse a outra sumir.
    """

    async def test_it_stamps_once_and_never_moves_the_stamp(self, db_session_factory: Any) -> None:
        from hunter_strategy_worker.replication import mark_promising

        key = "replication_mark"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            _, version_id = await activate_version(session, key=key)
        async with db_session_factory() as session, session.begin():
            first = await mark_promising(
                await session.connection(), version_id, "scoreboard:validada"
            )
        async with db_session_factory() as session, session.begin():
            again = await mark_promising(
                await session.connection(), version_id, "outra fonte qualquer"
            )
        assert again == first, "um carimbo existente nunca se move"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            rows = await _versions(session, key)
            events = await _events(session, version_id)
        assert rows[0].promising_at is not None
        # A segunda chamada não reescreveu a atribuição da primeira.
        assert rows[0].promising_by == "scoreboard:validada"
        # ...nem duplicou a auditoria: um evento por marcação de fato feita.
        assert [event.event for event in events] == ["strategy_version_promising"]
        assert events[0].data["promising_by"] == "scoreboard:validada"
        assert events[0].data["promising_at"] == first.isoformat()

    async def test_it_refuses_an_attribution_the_check_would_refuse(
        self, db_session_factory: Any
    ) -> None:
        """Recusa, nunca truncamento: o CHECK aceita 1..64 caracteres, e cortar
        um rótulo de 200 inventaria uma atribuição que ninguém escreveu."""
        from hunter_strategy_worker.replication import PROMISING_BY_MAX, mark_promising

        key = "replication_mark_bad"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            _, version_id = await activate_version(session, key=key)
        for source in ("", "   ", "x" * (PROMISING_BY_MAX + 1)):
            async with db_session_factory() as session, session.begin():
                with pytest.raises(Refused, match="promising_by"):
                    await mark_promising(await session.connection(), version_id, source)
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            assert (await _versions(session, key))[0].promising_at is None
