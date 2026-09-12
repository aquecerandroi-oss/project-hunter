"""A dispersão BTC × alts no caminho do worker, contra um Postgres real.

T3.90 / H-P18. A pergunta deste arquivo é a do brief: uma versão com portão
``dispersion -0,05-0,00`` **pula** a barra em que a dispersão é -0,08 com
``eligibility_reason = dispersion_gate:-0.08``, e decide a barra em que ela é
-0,03 — pela mesma função que decide na faixa viva e no replay
(``decide.evaluate_slot`` -> ``build_market_context``).

O -0,08 não é um número escolhido a esmo: é a ordem de grandeza da discordância
que o plantão mediu em 10/09 (mediana das alts -4,80 % contra o BTC -1,50 %, isto
é -0,033) levada ao dobro, a região que o braço A da EXP-0029 pré-registra
(``[-0,10; -0,03)``) e que a faixa do brief deixa **fora**.

O resto é o que a regra nova tem de provar junto do que já existia:

- a âncora é **exata**: a linha vale para o minuto que ela nomeia e para nenhum
  outro, então um produtor atrasado emudece a versão (``dispersion_unavailable``)
  em vez de deixá-la decidir com o valor de quinze minutos atrás;
- uma linha que o produtor marcou inutilizável (cobertura abaixo do piso, ou o BTC
  sem retorno de 24 h) recusa com a mesma palavra, e o motivo **dele** viaja no
  envelope;
- o relógio de parede não entra no veredito;
- a precedência declarada: hora, regime, amplitude, dispersão — a dispersão por
  último, para que uma versão com as regras antigas reporte exatamente o que
  reportava antes desta tarefa existir;
- e a regressão da T3.52/T3.59/T3.77: uma versão sem regra de dispersão não ganha
  bloco nenhum no envelope.

Roda: ``uv run pytest services/strategy-worker/tests/test_dispersion_gate.py -q``
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
from hunter_indicators.dispersion import CURRENT_DISPERSION_VERSION, HORIZON_MINUTES
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

DISCORD = datetime(2026, 9, 10, 22, 15, tzinfo=UTC)
"""A barra de 15 min cuja linha carrega a discordância forte: dispersão -0,08.

O corte é o fechamento da barra e não um minuto qualquer porque o produtor escreve
**todo minuto**, mas quem decide são barras de 15 min: a linha que um portão
realmente lê é sempre a do fechamento da barra."""

MILD = datetime(2026, 9, 10, 22, 30, tzinfo=UTC)
"""Dentro da faixa do brief: dispersão -0,03 (a do plantão de 10/09)."""

SILENT = datetime(2026, 9, 10, 22, 45, tzinfo=UTC)
"""Sem linha nenhuma: o produtor não rodou este minuto."""

BLIND = datetime(2026, 9, 10, 23, 0, tzinfo=UTC)
"""Com linha, mas o produtor não tinha o BTC para medir contra."""

CUTS = (DISCORD, MILD, SILENT, BLIND)

BAND: dict[str, Any] = {
    "dispersion": {"min": "-0.05", "max": "0.00", "version": CURRENT_DISPERSION_VERSION}
}
"""A faixa do brief, nomeando a série: a política carrega ``dispersion_24h_v1``, e é
essa série que o portão procura."""
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


async def insert_dispersion(
    session: Any,
    *,
    end_time: datetime,
    dispersion: str | None,
    btc: str = "-0.015000",
    median: str | None = None,
    covered: int = 16,
    universe_size: int = 16,
    alts_below: int = 15,
    reason: str | None = None,
    version: str = CURRENT_DISPERSION_VERSION,
) -> uuid.UUID:
    """Uma linha de ``market_dispersion`` exatamente como o produtor do scanner a
    escreve — ``end_time``-ancorada, imutável, na série que ``version`` nomear.

    A mediana é derivada de ``btc + dispersion`` para que a CHECK da ``0020``
    (``dispersion = median_alt_r24h - btc_r24h``) valha: um teste que semeasse os
    três números livremente estaria semeando uma linha que a produção não pode ter.

    Escrita como ``hunter_worker``, o único papel com ``INSERT`` nesta tabela
    (``0020``); um teste que a semeasse como dono estaria provando uma permissão que
    a produção não tem.
    """
    usable = dispersion is not None
    reference = Decimal(btc) if usable else None
    value = Decimal(dispersion) if dispersion is not None else None
    middle = (
        Decimal(median)
        if median is not None
        else (None if value is None or reference is None else reference + value)
    )
    row_id = uuid7()
    exchange_id = await session.scalar(
        text("SELECT id FROM exchanges WHERE code = :code"), {"code": EXCHANGE}
    )
    await session.execute(
        text(
            "INSERT INTO market_dispersion (id, exchange_id, end_time, dispersion_version, "
            "  horizon_minutes, universe_size, covered, alts_covered, alts_below_btc, btc_r24h, "
            "  median_alt_r24h, dispersion, share_below_btc, coverage, usable, reason) "
            "VALUES (:id, :exchange_id, :end_time, :version, :horizon, :universe_size, :covered, "
            "  :alts_covered, :alts_below, :btc, :median, :dispersion, :share, :coverage, "
            "  :usable, :reason)"
        ),
        {
            "id": row_id,
            "exchange_id": exchange_id,
            "end_time": end_time,
            "version": version,
            "horizon": HORIZON_MINUTES,
            "universe_size": universe_size,
            "covered": covered,
            "alts_covered": covered - 1,
            "alts_below": alts_below if usable else 0,
            "btc": reference,
            "median": middle,
            "dispersion": value,
            "share": (None if not usable else Decimal(alts_below) / Decimal(max(covered - 1, 1))),
            "coverage": Decimal(covered) / Decimal(universe_size),
            "usable": usable,
            "reason": reason,
        },
    )
    return row_id


async def _fixture(db_session_factory: Any, *, policy: dict[str, Any], key: str) -> dict[str, Any]:
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, DISCORD)
        # Como **dono**, e não como ``hunter_worker``: a ``0020`` não dá DELETE
        # nesta tabela a nenhum dos dois papéis de aplicação, e um teste que
        # limpasse a série como o worker estaria provando uma permissão que a
        # produção não tem.
        await owner.execute(text("DELETE FROM market_dispersion"))
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
        await insert_dispersion(session, end_time=DISCORD, dispersion="-0.080000")
        await insert_dispersion(session, end_time=MILD, dispersion="-0.033000", alts_below=12)
        await insert_dispersion(
            session, end_time=BLIND, dispersion=None, covered=15, reason="btc_missing"
        )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    return {"factory": db_session_factory, "version": only_version(versions, key), "market": market}


@pytest.fixture
async def gated_by_dispersion(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(db_session_factory, policy=BAND, key="volume_anomaly_dispersion")


@pytest.fixture
async def gated_by_hours_and_dispersion(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(
        db_session_factory, policy=HOURS_AND_BAND, key="volume_anomaly_hours_dispersion"
    )


@pytest.fixture
async def gated_by_regime(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(
        db_session_factory, policy=REGIME_ONLY, key="volume_anomaly_no_dispersion"
    )


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


class TestADiscordanciaForte:
    async def test_a_barra_com_dispersao_de_menos_oito_e_pulada(
        self, gated_by_dispersion: dict[str, Any], redis_client: Any
    ) -> None:
        """O caso do brief, com o motivo que o ledger vai agrupar."""
        evaluation = await _decide(gated_by_dispersion, redis_client, cut=DISCORD)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "dispersion_gate:-0.08"
        assert await _signals(gated_by_dispersion["factory"]) == []

    async def test_a_barra_dentro_da_faixa_decide_e_o_envelope_diz_qual_valor(
        self, gated_by_dispersion: dict[str, Any], redis_client: Any
    ) -> None:
        """O valor e os limites chegam ao envelope como **string**: é a forma
        canônica (``params_format = 1``) e é assim que a prova de "esta decisão leu
        esta linha" fica auditável."""
        evaluation = await _decide(gated_by_dispersion, redis_client, cut=MILD)
        assert evaluation.state.value == "triggered"
        provenance = (await _signals(gated_by_dispersion["factory"]))[0].supporting_features[
            "provenance"
        ]
        gate = provenance["dispersion_gate"]
        assert gate["eligible"] is True
        assert gate["detail"] == "allowed"
        assert gate["value"] == "-0.033000"
        assert gate["end_time"] == MILD.isoformat()
        assert gate["policy"] == {
            "max": "0.00",
            "min": "-0.05",
            "version": "dispersion_24h_v1",
        }
        assert provenance["hours_gate"] is None
        assert provenance["regime_gate"] is None
        assert provenance["breadth_gate"] is None

    async def test_o_relogio_de_parede_nao_entra_no_veredito(
        self, gated_by_dispersion: dict[str, Any], redis_client: Any
    ) -> None:
        prompt = await _decide(gated_by_dispersion, redis_client, cut=DISCORD, lag_s=2)
        late = await _decide(gated_by_dispersion, redis_client, cut=DISCORD, lag_s=240)
        assert prompt.detail["eligibility_reason"] == late.detail["eligibility_reason"]
        assert late.detail["eligibility_reason"] == "dispersion_gate:-0.08"


class TestQuandoASerieNaoResponde:
    async def test_sem_linha_para_o_minuto_a_versao_emudece(
        self, gated_by_dispersion: dict[str, Any], redis_client: Any
    ) -> None:
        """Falha fechada, e sem tolerância: a linha das 22:30 existe e vale -0,033,
        e ela **não** cobre a barra das 22:45. Uma âncora aproximada deixaria a
        versão decidir com o valor de quinze minutos atrás."""
        evaluation = await _decide(gated_by_dispersion, redis_client, cut=SILENT)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "dispersion_unavailable"

    async def test_uma_linha_sem_o_btc_recusa_com_a_mesma_palavra_e_diz_qual_foi(
        self, gated_by_dispersion: dict[str, Any], redis_client: Any
    ) -> None:
        """ "Ninguém produziu este minuto" e "o produtor não tinha referência"
        recusam igual e se distinguem pelo ``detail`` e pelo ``series_reason``,
        nunca por uma segunda gramática de motivo."""
        evaluation = await _decide(gated_by_dispersion, redis_client, cut=BLIND)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "dispersion_unavailable"


class TestAsRegrasJuntas:
    async def test_fora_da_janela_a_hora_e_o_motivo_mesmo_com_a_dispersao_recusando(
        self, gated_by_hours_and_dispersion: dict[str, Any], redis_client: Any
    ) -> None:
        """Precedência declarada: a hora primeiro, porque não lê nada. 22:15 está
        fora de ``12-15`` **e** tem dispersão -0,08 — e o motivo é a hora."""
        evaluation = await _decide(gated_by_hours_and_dispersion, redis_client, cut=DISCORD)
        assert evaluation.detail["eligibility_reason"] == "hours_gate:22"

    async def test_fora_da_janela_recusa_mesmo_quando_a_dispersao_liberaria(
        self, gated_by_hours_and_dispersion: dict[str, Any], redis_client: Any
    ) -> None:
        """``AND``: cada regra só estreita."""
        evaluation = await _decide(gated_by_hours_and_dispersion, redis_client, cut=MILD)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "hours_gate:22"


class TestAVersaoSemDispersaoNaoMuda:
    async def test_ela_decide_no_minuto_da_discordancia_e_nao_ganha_bloco_nenhum(
        self, gated_by_regime: dict[str, Any], redis_client: Any
    ) -> None:
        """A regressão: acrescentar uma quarta regra ao build não pode cortar nem
        carimbar uma versão que não a declarou."""
        async with role_session(gated_by_regime["factory"], db_role="hunter_worker") as session:
            await insert_hourly_regime(
                session, hour=DISCORD.replace(minute=0) - timedelta(hours=1), regime="SIDEWAYS"
            )
        evaluation = await _decide(gated_by_regime, redis_client, cut=DISCORD)
        assert evaluation.state.value == "triggered"
        provenance = (await _signals(gated_by_regime["factory"]))[0].supporting_features[
            "provenance"
        ]
        assert provenance["dispersion_gate"] is None
        assert provenance["regime_gate"]["label"] == "SIDEWAYS"


class TestAIdentidadeGravadaEExata:
    async def test_a_linha_carrega_a_identidade_que_a_check_da_0020_exige(
        self, gated_by_dispersion: dict[str, Any], redis_client: Any
    ) -> None:
        """Não é sobre o portão: é a prova de que a linha que o portão leu é uma
        linha que a produção pode ter. ``dispersion = median_alt_r24h - btc_r24h``
        é CHECK no banco, então uma semente incoerente não entraria — e o que o
        portão lê é a coluna ``dispersion``, nunca uma recomposição dela."""
        async with role_session(gated_by_dispersion["factory"], db_role="hunter_worker") as session:
            row = (
                await session.execute(
                    text(
                        "SELECT btc_r24h, median_alt_r24h, dispersion, share_below_btc "
                        "  FROM market_dispersion WHERE end_time = :cut"
                    ),
                    {"cut": MILD},
                )
            ).one()
        assert row.dispersion == row.median_alt_r24h - row.btc_r24h == Decimal("-0.033000")
        assert row.btc_r24h == Decimal("-0.015000")
        assert row.median_alt_r24h == Decimal("-0.048000")  # o número do plantão de 10/09
        assert row.share_below_btc == Decimal("0.800000")  # 12 de 15 alts abaixo do BTC
