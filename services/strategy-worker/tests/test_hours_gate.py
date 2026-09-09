"""A janela de horas no caminho do worker, contra um Postgres real.

T3.59. A pergunta deste arquivo é a do brief: uma versão com ``hours=12-15``
(UTC) **pula** a barra que fecha às 10:00 com ``eligibility_reason =
hours_gate:10``, e decide a que fecha às 12:30 — pela mesma função que decide na
faixa viva e no replay (``decide.evaluate_slot`` -> ``build_market_context``).

O resto é o que a regra nova tem de provar junto do que já existia:

- a fronteira é a **hora**, meia-aberta: 14:45 passa, 15:00 não;
- o relógio de parede não entra no veredito — a mesma barra avaliada 2 s e 4 min
  depois do fechamento dá exatamente a mesma resposta;
- **as duas regras juntas** (a forma da ``momentum v12`` da EXP-0023): dentro da
  janela e no regime permitido decide, dentro da janela e fora do regime recusa
  por ``regime_gate:<RÓTULO>``, fora da janela recusa por ``hours_gate:HH``
  mesmo quando o regime também recusaria (precedência declarada: a hora primeiro,
  porque não lê nada);
- e a regressão da T3.52: uma versão **só** com portão de regime continua sendo
  cortada por ele e não ganha bloco de hora nenhum no envelope.

Roda: ``uv run pytest services/strategy-worker/tests/test_hours_gate.py -q``
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import AgentSignal
from hunter_core.db.session import role_session
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

MORNING = datetime(2026, 9, 5, 12, 30, tzinfo=UTC)
"""Dentro da janela pré-registrada: 12:30 UTC = 09:30 BRT."""

EARLY = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
"""A barra do brief: fecha às 10:00 UTC, fora da janela."""

LAST_INSIDE = datetime(2026, 9, 5, 14, 45, tzinfo=UTC)
FIRST_OUTSIDE = datetime(2026, 9, 5, 15, 0, tzinfo=UTC)
CUTS = (EARLY, MORNING, LAST_INSIDE, FIRST_OUTSIDE)

HOURS_ONLY: dict[str, Any] = {"hours": {"utc": [[12, 15]]}}
BOTH: dict[str, Any] = {
    "hours": {"utc": [[12, 15]]},
    "regime": {
        "allow": ["SIDEWAYS"],
        "classifier_version": "regime_hourly_v1",
        "rule": "previous_closed_hour",
        "scope": "btc",
    },
}
REGIME_ONLY: dict[str, Any] = {"regime": BOTH["regime"]}
CONFIG = ShadowConfig(eligibility_max_lag_s=300, context_minutes=1560)


def clock_at(instant: datetime) -> Any:
    return lambda: instant


def multi_series(cuts: tuple[datetime, ...]) -> list[dict[str, Any]]:
    """Uma série de 1 min contínua que dispara ``volume_anomaly_v1`` em **cada**
    corte: os cinco minutos antes de cada um levam o volume, como ``series()``
    faz para um corte só. Uma série por corte colidiria na chave da vela."""
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


async def _fixture(db_session_factory: Any, *, policy: dict[str, Any], key: str) -> dict[str, Any]:
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, MORNING)
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
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    return {"factory": db_session_factory, "version": only_version(versions, key), "market": market}


@pytest.fixture
async def gated_by_hours(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(db_session_factory, policy=HOURS_ONLY, key="volume_anomaly_hours")


@pytest.fixture
async def gated_by_both(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(db_session_factory, policy=BOTH, key="volume_anomaly_both")


@pytest.fixture
async def gated_by_regime(db_session_factory: Any) -> dict[str, Any]:
    return await _fixture(db_session_factory, policy=REGIME_ONLY, key="volume_anomaly_regime")


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


async def _allow_the_regime(fixture: dict[str, Any], *, cut: datetime, regime: str) -> None:
    """A linha horária que corta ``cut``: a **hora fechada anterior** (T3.52)."""
    async with role_session(fixture["factory"], db_role="hunter_worker") as session:
        await insert_hourly_regime(
            session, hour=cut.replace(minute=0) - timedelta(hours=1), regime=regime
        )


class TestTheWindowIsTheHourTheBarClosedIn:
    async def test_a_bar_outside_the_window_never_decides(
        self, gated_by_hours: dict[str, Any], redis_client: Any
    ) -> None:
        """O caso do brief, com o motivo que o ledger vai agrupar."""
        evaluation = await _decide(gated_by_hours, redis_client, cut=EARLY)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "hours_gate:10"
        assert await _signals(gated_by_hours["factory"]) == []

    async def test_a_bar_inside_the_window_decides_and_the_envelope_says_which_hour(
        self, gated_by_hours: dict[str, Any], redis_client: Any
    ) -> None:
        """A hora e os limites chegam ao envelope como **string**, e é assim
        mesmo: ``supporting_features`` é serializado pela forma canônica
        (``params_format = 1``), que emite todo número como string decimal
        normalizada — vale para o z-score, para o ATR e para isto. É o oposto do
        que a **coluna** ``eligibility_policy`` guarda (inteiros, senão o parser
        recusa a versão; ``test_derive_variant.py``), e as duas coisas viverem
        lado a lado é exatamente o que este par de testes fixa.
        """
        evaluation = await _decide(gated_by_hours, redis_client, cut=MORNING)
        assert evaluation.state.value == "triggered"
        provenance = (await _signals(gated_by_hours["factory"]))[0].supporting_features[
            "provenance"
        ]
        assert provenance["hours_gate"] == {
            "eligible": True,
            "hour": "12",
            "detail": "allowed",
            "policy": {"utc": [["12", "15"]]},
        }
        assert provenance["regime_gate"] is None

    async def test_the_last_bar_inside_and_the_first_bar_outside(
        self, gated_by_hours: dict[str, Any], redis_client: Any
    ) -> None:
        """Meia-aberta: 14:45 é a última barra de 15 min da janela, 15:00 já é a
        primeira de fora — e nenhuma vela nova entrou entre as duas decisões."""
        inside = await _decide(gated_by_hours, redis_client, cut=LAST_INSIDE)
        assert inside.state.value == "triggered"
        outside = await _decide(gated_by_hours, redis_client, cut=FIRST_OUTSIDE)
        assert outside.state.value == "ineligible"
        assert outside.detail["eligibility_reason"] == "hours_gate:15"

    async def test_the_wall_clock_does_not_enter_the_verdict(
        self, gated_by_hours: dict[str, Any], redis_client: Any
    ) -> None:
        """A mesma barra avaliada 2 s e 240 s depois do fechamento dá a mesma
        resposta: o veredito é função do corte, não de quando se avaliou —
        que é o que faz o replay reproduzir a faixa viva."""
        prompt = await _decide(gated_by_hours, redis_client, cut=EARLY, lag_s=2)
        late = await _decide(gated_by_hours, redis_client, cut=EARLY, lag_s=240)
        assert prompt.detail["eligibility_reason"] == late.detail["eligibility_reason"]
        assert late.detail["eligibility_reason"] == "hours_gate:10"


class TestTheTwoRulesTogether:
    async def test_inside_the_window_and_in_the_allowed_regime_it_decides(
        self, gated_by_both: dict[str, Any], redis_client: Any
    ) -> None:
        await _allow_the_regime(gated_by_both, cut=MORNING, regime="SIDEWAYS")
        evaluation = await _decide(gated_by_both, redis_client, cut=MORNING)
        assert evaluation.state.value == "triggered"
        provenance = (await _signals(gated_by_both["factory"]))[0].supporting_features["provenance"]
        assert provenance["hours_gate"]["eligible"] is True
        assert provenance["regime_gate"]["eligible"] is True
        assert provenance["regime_gate"]["label"] == "SIDEWAYS"

    async def test_inside_the_window_but_in_a_refused_regime_names_the_regime(
        self, gated_by_both: dict[str, Any], redis_client: Any
    ) -> None:
        await _allow_the_regime(gated_by_both, cut=MORNING, regime="BTC_BEAR")
        evaluation = await _decide(gated_by_both, redis_client, cut=MORNING)
        assert evaluation.state.value == "ineligible"
        assert evaluation.detail["eligibility_reason"] == "regime_gate:BTC_BEAR"

    async def test_outside_the_window_the_hour_is_the_reason_even_when_both_refuse(
        self, gated_by_both: dict[str, Any], redis_client: Any
    ) -> None:
        """Precedência declarada: a hora primeiro. Não é gosto — é que ela não
        lê nada, então recusar ali poupa a consulta indexada do regime em toda
        barra fora da janela."""
        await _allow_the_regime(gated_by_both, cut=EARLY, regime="BTC_BEAR")
        evaluation = await _decide(gated_by_both, redis_client, cut=EARLY)
        assert evaluation.detail["eligibility_reason"] == "hours_gate:10"

    async def test_outside_the_window_it_refuses_even_when_the_regime_would_allow(
        self, gated_by_both: dict[str, Any], redis_client: Any
    ) -> None:
        """As duas regras são ``AND``: cada uma só estreita."""
        await _allow_the_regime(gated_by_both, cut=EARLY, regime="SIDEWAYS")
        evaluation = await _decide(gated_by_both, redis_client, cut=EARLY)
        assert evaluation.detail["eligibility_reason"] == "hours_gate:10"


class TestTheRegimeOnlyVersionIsUntouched:
    async def test_it_decides_at_ten_in_the_morning_and_carries_no_hours_block(
        self, gated_by_regime: dict[str, Any], redis_client: Any
    ) -> None:
        """A regressão da T3.52: a versão sem regra de hora não é cortada por
        hora nenhuma, e o envelope dela não ganha um bloco inventado."""
        await _allow_the_regime(gated_by_regime, cut=EARLY, regime="SIDEWAYS")
        evaluation = await _decide(gated_by_regime, redis_client, cut=EARLY)
        assert evaluation.state.value == "triggered"
        provenance = (await _signals(gated_by_regime["factory"]))[0].supporting_features[
            "provenance"
        ]
        assert provenance["hours_gate"] is None
        assert provenance["regime_gate"]["label"] == "SIDEWAYS"

    async def test_the_regime_still_refuses_by_name(
        self, gated_by_regime: dict[str, Any], redis_client: Any
    ) -> None:
        await _allow_the_regime(gated_by_regime, cut=EARLY, regime="BTC_BEAR")
        evaluation = await _decide(gated_by_regime, redis_client, cut=EARLY)
        assert evaluation.detail["eligibility_reason"] == "regime_gate:BTC_BEAR"
