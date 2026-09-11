"""A amplitude do universo no caminho do worker, contra um Postgres real.

T3.77 / H-P8. A pergunta deste arquivo é a do brief: uma versão com portão
``breadth 0,10-0,60`` **pula** a barra em que a amplitude é 0,97 com
``eligibility_reason = breadth_gate:0.97``, e decide a barra em que ela é 0,35 —
pela mesma função que decide na faixa viva e no replay
(``decide.evaluate_slot`` -> ``build_market_context``).

O 0,97 não é um número escolhido: é o minuto do KB-0083, 2026-09-09 22:08Z, em
que 194 das 200 perpétuas monitoradas caíram juntas e 15 das 39 apostas da pior
hora da família morreram.

O resto é o que a regra nova tem de provar junto do que já existia:

- a âncora é **exata**: a linha vale para o minuto que ela nomeia e para nenhum
  outro, então um produtor atrasado emudece a versão (``breadth_unavailable``) em
  vez de deixá-la decidir com o valor de três minutos atrás;
- uma linha que o produtor marcou inutilizável (cobertura abaixo do piso) recusa
  com a mesma palavra, e o motivo **dele** viaja no envelope;
- o relógio de parede não entra no veredito — a mesma barra avaliada 2 s e 4 min
  depois do fechamento dá a mesma resposta;
- a precedência declarada: hora primeiro, regime depois, amplitude por último —
  escolhida para que uma versão com as duas regras antigas reporte exatamente o
  que reportava antes desta tarefa existir;
- e a regressão da T3.52/T3.59: uma versão sem regra de amplitude não ganha bloco
  nenhum no envelope.

Roda: ``uv run pytest services/strategy-worker/tests/test_breadth_gate.py -q``
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import AgentSignal
from hunter_core.db.session import role_session
from hunter_core.domain.types import uuid7
from hunter_indicators.breadth import BREADTH_V1, CURRENT_BREADTH_VERSION, WINDOW_MINUTES
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    MINUTE,
    SERIES_MINUTES,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    insert_hourly_regime,
    isolate_catalogue,
    only_version,
    seed_market,
)

pytestmark = pytest.mark.integration

STORM = datetime(2026, 9, 9, 22, 15, tzinfo=UTC)
"""A primeira barra de 15 min que fecha depois do estouro de 22:08Z do KB-0083.

O corte é 22:15 e não 22:08 por um motivo que vale registrar: o produtor escreve
**todo minuto**, mas quem decide são barras de 15 min, então a linha que um
portão realmente lê é sempre a do fechamento da barra. A amplitude 0,97 medida às
22:08 é a que essa barra carrega."""

CALM = datetime(2026, 9, 9, 22, 30, tzinfo=UTC)
"""Dentro da faixa pré-registrada: amplitude 0,35."""

SILENT = datetime(2026, 9, 9, 22, 45, tzinfo=UTC)
"""Sem linha nenhuma: o produtor não rodou este minuto."""

BLIND = datetime(2026, 9, 9, 23, 0, tzinfo=UTC)
"""Com linha, mas o produtor não enxergou o universo."""

CUTS = (STORM, CALM, SILENT, BLIND)

BAND: dict[str, Any] = {
    "breadth": {
        "window_m": WINDOW_MINUTES,
        "min": "0.10",
        "max": "0.60",
        "version": CURRENT_BREADTH_VERSION,
    }
}
"""A faixa pré-registrada da EXP-0027, agora **nomeando a série** (T3.88): a
política carrega ``breadth_v2``, e é essa série que o portão procura. Uma linha de
``breadth_v1`` no mesmo minuto não responde por ela — é o que
``TestASerieEParteDaChave`` prova."""
HOURS_AND_BAND: dict[str, Any] = {"hours": {"utc": [[12, 15]]}, **BAND}
REGIME_ONLY: dict[str, Any] = {
    "regime": {
        "allow": ["SIDEWAYS"],
        "classifier_version": "regime_hourly_v1",
        "rule": "previous_closed_hour",
        "scope": "btc",
    }
}
CONFIG = ShadowConfig(eligibility_max_lag_s=300, context_minutes=1560)


def clock_at(instant: datetime) -> Any:
    return lambda: instant


def multi_series(cuts: tuple[datetime, ...]) -> list[dict[str, Any]]:
    """Série de 1 min contínua que dispara ``volume_anomaly_v1`` em cada corte."""
    spikes = {cut - MINUTE * step for cut in cuts for step in range(1, 6)}
    rows: list[dict[str, Any]] = []
    open_time = min(cuts) - MINUTE * SERIES_MINUTES
    while open_time < max(cuts):
        spike = open_time in spikes
        rows.append(
            {
                "open_time": open_time,
                "open": Decimal("100"),
                "high": Decimal("100.4") if spike else Decimal("100.2"),
                "low": Decimal("100.0") if spike else Decimal("99.8"),
                "close": Decimal("100.3") if spike else Decimal("100"),
                "volume": Decimal("60") if spike else Decimal("10"),
            }
        )
        open_time += MINUTE
    return rows


async def insert_breadth(
    session: Any,
    *,
    end_time: datetime,
    value: str | None,
    covered: int = 200,
    universe_size: int = 200,
    falling: int = 194,
    reason: str | None = None,
    version: str = CURRENT_BREADTH_VERSION,
) -> uuid.UUID:
    """Uma linha de ``market_breadth`` exatamente como o produtor do scanner a
    escreve — ``end_time``-ancorada, imutável, na série que ``version`` nomear
    (padrão: a atual, ``breadth_v2``).

    As contagens padrão são as do minuto do KB-0083 (194 de 200) porque é esse o
    fato que motivou a regra; o portão lê **só o ``value``** e nunca interpreta
    ``covered``/``universe_size``, então elas são proveniência semeada à mão, não
    uma afirmação sobre o universo de 16. Quem prova que a série escolhida importa
    é ``TestASerieEParteDaChave``, com as contagens do universo de v2.

    Escrita como ``hunter_worker``, que é o único papel com ``INSERT`` nesta
    tabela (``0019``); um teste que a semeasse como dono estaria provando uma
    permissão que a produção não tem.
    """
    row_id = uuid7()
    exchange_id = await session.scalar(
        text("SELECT id FROM exchanges WHERE code = :code"), {"code": EXCHANGE}
    )
    await session.execute(
        text(
            "INSERT INTO market_breadth (id, exchange_id, end_time, window_minutes, "
            "  breadth_version, universe_size, covered, falling, value, coverage, usable, reason) "
            "VALUES (:id, :exchange_id, :end_time, :window, :version, :universe_size, :covered, "
            "  :falling, :value, :coverage, :usable, :reason)"
        ),
        {
            "id": row_id,
            "exchange_id": exchange_id,
            "end_time": end_time,
            "window": WINDOW_MINUTES,
            "version": version,
            "universe_size": universe_size,
            "covered": covered,
            "falling": falling if value is not None else 0,
            "value": None if value is None else Decimal(value),
            "coverage": Decimal(covered) / Decimal(universe_size),
            "usable": value is not None,
            "reason": reason,
        },
    )
    return row_id


async def _fixture(db_session_factory: Any, *, policy: dict[str, Any], key: str) -> dict[str, Any]:
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, STORM)
        # Como **dono**, e não como ``hunter_worker``: a ``0019`` não dá DELETE
        # nesta tabela a nenhum dos dois papéis de aplicação, e um teste que
        # limpasse a série como o worker estaria provando uma permissão que a
        # produção não tem.
        await owner.execute(text("DELETE FROM market_breadth"))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
        await session.execute(text("DELETE FROM market_regimes"))
        _exchange_id, market_id = await seed_market(session)
        _strategy_id, _version_id = await activate_version(session, key=key, policy=policy)
        await isolate_catalogue(session, keep=key)
        await insert_candles(session, market_id, multi_series(CUTS))
        await insert_breadth(session, end_time=STORM, value="0.9700")
        await insert_breadth(session, end_time=CALM, value="0.3500", falling=70)
        await insert_breadth(
            session,
            end_time=BLIND,
            value=None,
            covered=40,
            reason="insufficient_coverage",
        )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    return {"factory": db_session_factory, "version": only_version(versions, key), "market": market}


@pytest.fixture
async def gated_by_breadth(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(db_session_factory, policy=BAND, key="volume_anomaly_breadth")


@pytest.fixture
async def gated_by_hours_and_breadth(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(
        db_session_factory, policy=HOURS_AND_BAND, key="volume_anomaly_hours_breadth"
    )


@pytest.fixture
async def gated_by_regime(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(db_session_factory, policy=REGIME_ONLY, key="volume_anomaly_no_breadth")


async def _decide(
    fixture: dict[str, Any], redis_client: Any, *, cut: datetime, lag_s: int = 2
) -> Any:
    return await evaluate_slot(
        fixture["factory"],
        redis_client,
        version=fixture["version"],
        market=fixture["market"],
        bar_close=cut,
        config=CONFIG,
        clock=clock_at(cut + timedelta(seconds=lag_s)),
    )


async def _signals(factory: Any) -> list[AgentSignal]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return list((await session.execute(select(AgentSignal))).scalars())


class TestOMinutoDoKb0083:
    async def test_a_barra_com_amplitude_de_noventa_e_sete_e_pulada(
        self, gated_by_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        """O caso do brief, com o motivo que o ledger vai agrupar."""
        evaluation = await _decide(gated_by_breadth, redis_client, cut=STORM)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "breadth_gate:0.97"
        assert await _signals(gated_by_breadth["factory"]) == []

    async def test_a_barra_dentro_da_faixa_decide_e_o_envelope_diz_qual_valor(
        self, gated_by_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        """O valor e os limites chegam ao envelope como **string**, e é assim
        mesmo: ``supporting_features`` passa pela forma canônica
        (``params_format = 1``). É o oposto do que a **coluna**
        ``eligibility_policy`` guarda para ``window_m`` (inteiro), e as duas
        coisas viverem lado a lado é o que este par de testes fixa."""
        evaluation = await _decide(gated_by_breadth, redis_client, cut=CALM)
        assert evaluation.state.value == "triggered"
        provenance = (await _signals(gated_by_breadth["factory"]))[0].supporting_features[
            "provenance"
        ]
        gate = provenance["breadth_gate"]
        assert gate["eligible"] is True
        assert gate["detail"] == "allowed"
        assert gate["value"] == "0.350000"
        assert gate["end_time"] == CALM.isoformat()
        assert gate["policy"] == {
            "max": "0.60",
            "min": "0.10",
            "version": "breadth_v2",
            "window_m": "5",
        }
        assert provenance["hours_gate"] is None
        assert provenance["regime_gate"] is None

    async def test_o_relogio_de_parede_nao_entra_no_veredito(
        self, gated_by_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        prompt = await _decide(gated_by_breadth, redis_client, cut=STORM, lag_s=2)
        late = await _decide(gated_by_breadth, redis_client, cut=STORM, lag_s=240)
        assert prompt.detail["eligibility_reason"] == late.detail["eligibility_reason"]
        assert late.detail["eligibility_reason"] == "breadth_gate:0.97"


class TestQuandoASerieNaoResponde:
    async def test_sem_linha_para_o_minuto_a_versao_emudece(
        self, gated_by_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        """Falha fechada, e sem tolerância: a linha das 22:30 existe e vale 0,35,
        e ela **não** cobre a barra das 22:45. Uma âncora aproximada deixaria a
        versão decidir com o valor de quinze minutos atrás."""
        evaluation = await _decide(gated_by_breadth, redis_client, cut=SILENT)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "breadth_unavailable"

    async def test_uma_linha_inutilizavel_recusa_com_a_mesma_palavra(
        self, gated_by_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        """ "Ninguém produziu este minuto" e "o produtor não enxergou o universo"
        recusam igual e se distinguem pelo ``detail``, nunca por uma segunda
        gramática de motivo."""
        evaluation = await _decide(gated_by_breadth, redis_client, cut=BLIND)
        assert evaluation.detail["eligibility_reason"] == "breadth_unavailable"


class TestAsRegrasJuntas:
    async def test_fora_da_janela_a_hora_e_o_motivo_mesmo_com_a_amplitude_recusando(
        self, gated_by_hours_and_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        """Precedência declarada: a hora primeiro, porque não lê nada. 22:15 está
        fora de ``12-15`` **e** tem amplitude 0,97 — e o motivo é a hora."""
        evaluation = await _decide(gated_by_hours_and_breadth, redis_client, cut=STORM)
        assert evaluation.detail["eligibility_reason"] == "hours_gate:22"

    async def test_fora_da_janela_recusa_mesmo_quando_a_amplitude_liberaria(
        self, gated_by_hours_and_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        """``AND``: cada regra só estreita."""
        evaluation = await _decide(gated_by_hours_and_breadth, redis_client, cut=CALM)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "hours_gate:22"


class TestAVersaoSemAmplitudeNaoMuda:
    async def test_ela_decide_no_minuto_da_tempestade_e_nao_ganha_bloco_nenhum(
        self, gated_by_regime: dict[str, Any], redis_client: Any
    ) -> None:
        """A regressão: acrescentar uma terceira regra ao build não pode cortar
        nem carimbar uma versão que não a declarou."""
        async with role_session(gated_by_regime["factory"], db_role="hunter_worker") as session:
            await insert_hourly_regime(
                session, hour=STORM.replace(minute=0) - timedelta(hours=1), regime="SIDEWAYS"
            )
        evaluation = await _decide(gated_by_regime, redis_client, cut=STORM)
        assert evaluation.state.value == "triggered"
        provenance = (await _signals(gated_by_regime["factory"]))[0].supporting_features[
            "provenance"
        ]
        assert provenance["breadth_gate"] is None
        assert provenance["regime_gate"]["label"] == "SIDEWAYS"


class TestASerieEParteDaChave:
    """T3.88: a política nomeia a série, e uma linha da outra série não responde
    por ela — nem para liberar, nem para recusar."""

    async def test_a_linha_de_v1_no_mesmo_minuto_nao_libera_uma_versao_presa_a_v2(
        self, gated_by_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        """O minuto ``SILENT`` não tem linha de ``breadth_v2``. Escrever uma de
        ``breadth_v1`` ali — **dentro** da faixa, 5 de 16 caindo — não faz a versão
        decidir: ela continua muda com ``breadth_unavailable``.

        É a prova de que a série é parte da chave e não um detalhe do build. Antes
        da T3.88 o portão lia ``breadth_version = BREADTH_VERSION``, uma constante
        de módulo: a mesma linha teria liberado a barra, e a célula pré-registrada
        da EXP-0027 teria sido medida contra um universo de 200 mercados sem que
        nada no envelope dissesse isso.
        """
        async with role_session(gated_by_breadth["factory"], db_role="hunter_worker") as session:
            await insert_breadth(
                session,
                end_time=SILENT,
                value="0.3125",
                covered=16,
                universe_size=16,
                falling=5,
                version=BREADTH_V1,
            )

        evaluation = await _decide(gated_by_breadth, redis_client, cut=SILENT)

        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "breadth_unavailable"
        assert await _signals(gated_by_breadth["factory"]) == []

    async def test_as_duas_series_coexistem_no_mesmo_minuto_com_valores_diferentes(
        self, gated_by_breadth: dict[str, Any], redis_client: Any
    ) -> None:
        """O minuto ``CALM`` já tem ``breadth_v2 = 0,3500``. Uma linha de
        ``breadth_v1`` com 0,9700 no **mesmo** minuto entra sem colidir (a chave
        única inclui ``breadth_version``) e a versão presa a v2 decide como antes:
        duas leituras honestas do mesmo minuto, duas séries, nenhuma reescrita.
        """
        async with role_session(gated_by_breadth["factory"], db_role="hunter_worker") as session:
            await insert_breadth(session, end_time=CALM, value="0.9700", version=BREADTH_V1)
            rows = list(
                (
                    await session.execute(
                        text(
                            "SELECT breadth_version, value FROM market_breadth "
                            " WHERE end_time = :cut ORDER BY breadth_version"
                        ),
                        {"cut": CALM},
                    )
                ).all()
            )

        assert [(row.breadth_version, str(row.value)) for row in rows] == [
            ("breadth_v1", "0.970000"),
            ("breadth_v2", "0.350000"),
        ]
        evaluation = await _decide(gated_by_breadth, redis_client, cut=CALM)
        assert evaluation.state.value == "triggered"
