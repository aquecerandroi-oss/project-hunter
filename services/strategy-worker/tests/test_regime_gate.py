"""O portão de regime contra um Postgres real — a regra de corte, e o que ela recusa.

T3.52. A pergunta que este arquivo responde é uma só, e é de **não-antecipação**:
uma decisão das 15:30 é cortada pela linha horária ``[14:00, 15:00)`` — a última
hora **fechada** antes do corte —, nunca pela ``[15:00, 16:00)``, que contém o
corte. Os dois casos são testados nos dois sentidos: a linha da hora anterior
libera enquanto a da hora corrente recusaria, e a da hora anterior recusa
enquanto a da hora corrente liberaria. Um portão que lesse a linha errada
passaria no primeiro e falharia no segundo.

O resto é o vocabulário do portão: ``UNKNOWN`` do classificador, série ausente,
linha velha demais, escopo ``btc`` valendo para um mercado que não é BTC, e a
versão **sem** política, que não é cortada por nada.

Roda: ``uv run pytest services/strategy-worker/tests/test_regime_gate.py -q``
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import AgentSignal
from hunter_core.db.session import role_session
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.regime_gate import DEFAULT_CLASSIFIER, RULE_PREVIOUS_CLOSED_HOUR
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    insert_hourly_regime,
    isolate_catalogue,
    only_version,
    seed_market,
    series,
)

pytestmark = pytest.mark.integration

CUT = datetime(2026, 9, 5, 15, 30, tzinfo=UTC)
"""A decisão do brief: 15:30, dentro da hora ``[15:00, 16:00)``."""

PREVIOUS_HOUR = datetime(2026, 9, 5, 14, 0, tzinfo=UTC)
CURRENT_HOUR = datetime(2026, 9, 5, 15, 0, tzinfo=UTC)
CONFIG = ShadowConfig(eligibility_max_lag_s=300, context_minutes=1560)
SIDEWAYS_ONLY: dict[str, Any] = {
    "regime": {
        "allow": ["SIDEWAYS"],
        "classifier_version": DEFAULT_CLASSIFIER,
        "rule": RULE_PREVIOUS_CLOSED_HOUR,
        "scope": "btc",
    }
}
OTHER_SYMBOL = "ETHUSDT"


def clock_at(instant: datetime) -> Any:
    return lambda: instant


async def _fixture(db_session_factory: Any, *, policy: dict[str, Any] | None) -> dict[str, Any]:
    """Um mercado, uma ``volume_anomaly_v1`` ativada (com ou sem portão) e uma
    série que dispara — a receita de ``test_regime_stamp.py``, mais o segundo
    mercado que prova o escopo."""
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        await session.execute(text("DELETE FROM candles"))
        await session.execute(text("DELETE FROM market_regimes"))
        _exchange_id, market_id = await seed_market(session)
        _exchange_id, other_id = await seed_market(session, symbol=OTHER_SYMBOL, base_asset="ETH")
        # The version is *inserted* with its policy: 0017's trigger freezes the
        # column on an activated row, which is the property under test elsewhere.
        version_key = "volume_anomaly" if policy is None else "volume_anomaly_gated"
        _strategy_id, version_id = await activate_version(session, key=version_key, policy=policy)
        await isolate_catalogue(session, keep=version_key)
        await insert_candles(session, market_id, series(CUT))
        await insert_candles(session, other_id, series(CUT))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
        other = await load_market(session, EXCHANGE, OTHER_SYMBOL)
    assert market is not None
    assert other is not None
    return {
        "factory": db_session_factory,
        "version": only_version(versions, version_key),
        "market": market,
        "other": other,
        "version_id": version_id,
    }


@pytest.fixture
async def gated(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(db_session_factory, policy=SIDEWAYS_ONLY)


@pytest.fixture
async def ungated(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(db_session_factory, policy=None)


async def _decide(fixture: dict[str, Any], redis_client: Any, *, market_key: str = "market") -> Any:
    return await evaluate_slot(
        fixture["factory"],
        redis_client,
        version=fixture["version"],
        market=fixture[market_key],
        bar_close=CUT,
        config=CONFIG,
        clock=clock_at(CUT + timedelta(seconds=2)),
    )


async def _signals(factory: Any) -> list[AgentSignal]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return list((await session.execute(select(AgentSignal))).scalars())


class TestTheCutIsThePreviousClosedHour:
    async def test_a_decision_at_1530_is_gated_by_the_1400_row(
        self, gated: dict[str, Any], redis_client: Any
    ) -> None:
        """A hora fechada anterior libera; a hora que **contém** o corte diria
        o contrário e não é lida. O id gravado no envelope é o da linha usada."""
        async with role_session(gated["factory"], db_role="hunter_worker") as session:
            previous = await insert_hourly_regime(session, hour=PREVIOUS_HOUR, regime="SIDEWAYS")
            await insert_hourly_regime(session, hour=CURRENT_HOUR, regime="BTC_BEAR")
        evaluation = await _decide(gated, redis_client)
        assert evaluation.state.value == "triggered"
        signal = (await _signals(gated["factory"]))[0]
        gate = signal.supporting_features["provenance"]["regime_gate"]
        assert gate["row_id"] == str(previous)
        assert gate["hour_start"] == PREVIOUS_HOUR.isoformat()
        assert gate["hour_end"] == CURRENT_HOUR.isoformat()
        assert (gate["label"], gate["detail"], gate["eligible"]) == ("SIDEWAYS", "allowed", True)

    async def test_the_hour_containing_the_cut_cannot_rescue_a_refusal(
        self, gated: dict[str, Any], redis_client: Any
    ) -> None:
        """O outro sentido, que é o que prova a não-antecipação: se o portão
        lesse a linha da hora corrente, esta decisão passaria."""
        async with role_session(gated["factory"], db_role="hunter_worker") as session:
            await insert_hourly_regime(session, hour=PREVIOUS_HOUR, regime="BTC_BEAR")
            await insert_hourly_regime(session, hour=CURRENT_HOUR, regime="SIDEWAYS")
        evaluation = await _decide(gated, redis_client)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "regime_gate:BTC_BEAR"
        assert await _signals(gated["factory"]) == []

    async def test_an_hour_that_has_not_closed_yet_does_not_exist_for_the_gate(
        self, gated: dict[str, Any], redis_client: Any
    ) -> None:
        """Só a hora corrente na série: nenhuma linha fechou até o corte, então
        o portão responde ``unknown`` — e não a linha que está aberta sobre ele."""
        async with role_session(gated["factory"], db_role="hunter_worker") as session:
            await insert_hourly_regime(session, hour=CURRENT_HOUR, regime="SIDEWAYS")
        evaluation = await _decide(gated, redis_client)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "regime_gate:unknown"


class TestWhatTheGateRefuses:
    async def test_the_classifiers_unknown_refuses(
        self, gated: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(gated["factory"], db_role="hunter_worker") as session:
            await insert_hourly_regime(session, hour=PREVIOUS_HOUR, regime="UNKNOWN")
        evaluation = await _decide(gated, redis_client)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "regime_gate:unknown"

    async def test_an_empty_series_refuses(self, gated: dict[str, Any], redis_client: Any) -> None:
        """27 % dos 31 dias saem ``unknown`` hoje e o resto da série pode
        simplesmente não existir: as duas coisas recusam, honestamente."""
        evaluation = await _decide(gated, redis_client)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "regime_gate:unknown"

    async def test_a_row_from_another_scope_is_not_this_series(
        self, gated: dict[str, Any], redis_client: Any
    ) -> None:
        """``regime_v0`` escreve em ``scope = global`` com intervalos abertos; o
        portão lê ``btc``/``regime_hourly_v1`` e nada mais (PIPELINE §4b item 2)."""
        async with role_session(gated["factory"], db_role="hunter_worker") as session:
            await session.execute(
                text(
                    "INSERT INTO market_regimes (id, scope, regime, start_time, end_time) "
                    "VALUES (gen_random_uuid(), 'global', 'SIDEWAYS', :start, :end)"
                ),
                {"start": PREVIOUS_HOUR, "end": CURRENT_HOUR},
            )
        evaluation = await _decide(gated, redis_client)
        assert evaluation.detail["eligibility_reason"] == "regime_gate:unknown"

    async def test_a_stale_row_stops_the_version_instead_of_aging_with_it(
        self, gated: dict[str, Any], redis_client: Any
    ) -> None:
        async with role_session(gated["factory"], db_role="hunter_worker") as session:
            await insert_hourly_regime(
                session, hour=PREVIOUS_HOUR - timedelta(hours=4), regime="SIDEWAYS"
            )
        evaluation = await _decide(gated, redis_client)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "regime_gate:unknown"


class TestScopeAndAbsence:
    async def test_the_btc_scope_gates_a_market_that_is_not_btc(
        self, gated: dict[str, Any], redis_client: Any
    ) -> None:
        """O escopo é o contexto do mercado inteiro, não o do símbolo: a mesma
        linha de ``btc`` decide sobre ETHUSDT, que não tem linha nenhuma."""
        async with role_session(gated["factory"], db_role="hunter_worker") as session:
            await insert_hourly_regime(session, hour=PREVIOUS_HOUR, regime="BTC_BEAR")
        evaluation = await _decide(gated, redis_client, market_key="other")
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "regime_gate:BTC_BEAR"

    async def test_a_version_without_a_policy_is_not_gated_at_all(
        self, ungated: dict[str, Any], redis_client: Any
    ) -> None:
        """Toda versão anterior à ``0017`` tem ``NULL``: decide como decidia, e o
        envelope não ganha um bloco de portão inventado."""
        async with role_session(ungated["factory"], db_role="hunter_worker") as session:
            await insert_hourly_regime(session, hour=PREVIOUS_HOUR, regime="BTC_BEAR")
        evaluation = await _decide(ungated, redis_client)
        assert evaluation.state.value == "triggered"
        signal = (await _signals(ungated["factory"]))[0]
        assert signal.supporting_features["provenance"]["regime_gate"] is None
