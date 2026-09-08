"""A passada de estresse ponta a ponta contra um Postgres de verdade — T3.36.

O que os testes puros não podem provar: que a coorte é encontrada pelo envelope
da decisão, que a sessão é a de leitura, que a série sai do banco, que a
liquidação de produção fecha as contas e que a **linha base reproduz o que o
Lab gravou**. Essa última é a que sustenta a tabela inteira: se a base
reprecificada não bate com o `r_multiple` persistido, nenhuma outra linha
significa nada (é a mesma regra do passo 1 do EXP-0004,
``replay/reproduce.py``).

A coorte é montada aqui do mesmo jeito que a T3.19b monta a dela — um replay de
verdade do ``volume_anomaly_v1`` congelado sobre uma série sintética rotulada —,
porque uma coorte escrita à mão provaria a aritmética contra si mesma.

Estatística de tabela (leave-one-out, metades, os cinco vereditos) é provada
sobre livro-razão sintético em
``packages/indicators/tests/unit/test_replay_stress.py``: com um mercado e um
dia, as duas funções devolvem lista vazia — e o teste cobra exatamente isso.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import SignalOutcome
from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowCohort
from hunter_core.domain.types import utcnow
from hunter_indicators.replay.stress import BASE
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.replay.load import read_only_session
from hunter_strategy_worker.replay.simulate import ReplayWindow, drain_cohort, replay_market
from hunter_strategy_worker.replay.stress import cohort_cases, run_stress
from hunter_strategy_worker.replay.stress_report import append_jsonl
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    MINUTE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    insert_funding_rate,
    isolate_catalogue,
    only_version,
    seed_market,
)

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
HISTORY_MINUTES = 1620
WINDOW = ReplayWindow(CUT - timedelta(minutes=60), CUT)
TRIGGER_BAR = CUT - timedelta(minutes=60)
RUN_ID = uuid.UUID("bbbbbbbb-cccc-4ddd-8eee-ffffffffffff")
COHORT = ShadowCohort.replay(RUN_ID)
CONFIG = ShadowConfig(cohort=COHORT, eligibility_max_lag_s=300, context_minutes=1560)


def series() -> list[dict[str, Any]]:
    """A mesma série da T3.19b: uma anomalia de volume e uma alta serena.

    Rotulada como dado de teste. A alta é gentil de propósito — um salto direto
    através do alvo daria ``no_entry: geometry`` e não provaria nada sobre
    saídas.
    """
    rows: list[dict[str, Any]] = []
    for index in range(HISTORY_MINUTES):
        open_time = CUT - MINUTE * (HISTORY_MINUTES - index)
        spike = TRIGGER_BAR - MINUTE * 5 <= open_time < TRIGGER_BAR
        if open_time >= TRIGGER_BAR:
            step = int((open_time - TRIGGER_BAR).total_seconds() // 60)
            base = Decimal("100.3") + Decimal("0.2") * step
            rows.append(
                {
                    "open_time": open_time,
                    "open": base,
                    "high": base + Decimal("0.3"),
                    "low": base - Decimal("0.1"),
                    "close": base + Decimal("0.2"),
                    "volume": Decimal("12"),
                }
            )
            continue
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
    return rows


@pytest.fixture
async def stress_db(db_session_factory: Any) -> dict[str, Any]:
    """Uma coorte de replay real, produzida pelo caminho vivo de avaliação."""
    key = f"replay_stress_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        for table in ("shadow_outbox", "shadow_episodes", "signal_outcomes", "agent_signals"):
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
        await session.execute(text("DELETE FROM candles"))
        await session.execute(text("DELETE FROM funding_rates"))
        _exchange_id, market_id = await seed_market(session)
        await activate_version(session, key=key)
        await insert_candles(session, market_id, series())
        for hours in range(0, 73, 8):
            await insert_funding_rate(
                session,
                market_id,
                funding_time=CUT - timedelta(hours=72 - hours),
                rate=Decimal("0.0001"),
                mark_price=Decimal("100"),
            )
    async with db_session_factory() as owner, owner.begin():
        await isolate_catalogue(owner, keep=key)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    await replay_market(
        db_session_factory,
        version=only_version(versions, key),
        market=market,
        window=WINDOW,
        config=CONFIG,
    )
    await drain_cohort(db_session_factory, cohort=COHORT, config=CONFIG)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        outcome = (await session.execute(select(SignalOutcome))).scalar_one()
    assert outcome.r_multiple is not None, "sem R gravado não há o que reprecificar"
    return {"factory": db_session_factory, "recorded": outcome}


@pytest.mark.integration
class TestTheStressPassReadsTheCohort:
    async def test_the_cohort_is_found_by_the_envelope_of_the_decision(
        self, stress_db: dict[str, Any]
    ) -> None:
        async with read_only_session(stress_db["factory"]) as session:
            cases = await cohort_cases(session, cohort=COHORT, as_of=utcnow())
        assert len(cases) == 1
        assert cases[0].signal_id == stress_db["recorded"].signal_id
        assert cases[0].market.symbol == SYMBOL

    async def test_another_cohort_finds_nothing(self, stress_db: dict[str, Any]) -> None:
        """A coorte é o isolamento: nenhuma linha vaza de uma corrida para outra."""
        async with read_only_session(stress_db["factory"]) as session:
            cases = await cohort_cases(
                session, cohort=ShadowCohort.replay(uuid.uuid4()), as_of=utcnow()
            )
        assert cases == []

    async def test_the_session_of_the_pass_cannot_write(self, stress_db: dict[str, Any]) -> None:
        """``READ ONLY`` é do Postgres, não da revisão de código."""
        with pytest.raises(Exception, match="read-only"):
            async with read_only_session(stress_db["factory"]) as session:
                await session.execute(text("DELETE FROM agent_signals"))


@pytest.mark.integration
class TestTheTable:
    async def test_the_base_row_reproduces_what_the_lab_recorded(
        self, stress_db: dict[str, Any]
    ) -> None:
        """A asserção que sustenta a tabela inteira."""
        run = await run_stress(stress_db["factory"], cohort=COHORT, as_of=utcnow())
        base = next(row for row in run.rows if row.key == BASE)
        assert base.n == 1
        recorded = Decimal(str(stress_db["recorded"].r_multiple))
        assert base.expectancy_r is not None
        assert base.expectancy_r.quantize(Decimal("0.0000000001")) == recorded
        assert base.dropped == {}

    async def test_doubling_the_costs_can_only_cost(self, stress_db: dict[str, Any]) -> None:
        run = await run_stress(stress_db["factory"], cohort=COHORT, as_of=utcnow())
        rows = {row.key: row for row in run.rows}
        base, doubled = rows[BASE].expectancy_r, rows["custos_x2"].expectancy_r
        assert base is not None and doubled is not None
        assert doubled < base
        delta = run.deltas["custos_x2"]
        assert delta.n_pairs == 1
        assert delta.estimate is not None and delta.estimate < 0
        assert delta.ci_reason == "single_block", "um dia só não tem intervalo honesto"

    async def test_every_declared_scenario_produces_a_row(self, stress_db: dict[str, Any]) -> None:
        run = await run_stress(stress_db["factory"], cohort=COHORT, as_of=utcnow())
        keys = [row.key for row in run.rows]
        assert keys == [
            BASE,
            "custos_x2",
            "stop_x0.75",
            "stop_x1.25",
            "alvo_x0.75",
            "alvo_x1.25",
            "entrada_mais_1_barra",
        ], "um mercado e um dia: sem linhas de leave-one-out nem de metade"
        assert run.markets == (f"{EXCHANGE}:{SYMBOL}",)
        assert run.cases == 1

    async def test_the_delayed_entry_enters_one_minute_later(
        self, stress_db: dict[str, Any]
    ) -> None:
        """O cenário que não é reprecificação: outra barra, outro preço."""
        run = await run_stress(stress_db["factory"], cohort=COHORT, as_of=utcnow())
        rows = {row.key: row for row in run.rows}
        delayed = rows["entrada_mais_1_barra"]
        assert delayed.n == 1
        assert delayed.expectancy_r != rows[BASE].expectancy_r

    async def test_a_sample_of_one_never_gets_a_robustness_verdict(
        self, stress_db: dict[str, Any]
    ) -> None:
        run = await run_stress(stress_db["factory"], cohort=COHORT, as_of=utcnow())
        assert run.verdict.verdict == "amostra_insuficiente"
        assert run.verdict.reasons == ("1 desfechos avaliáveis de 30",)
        assert not run.verdict.robust


@pytest.mark.integration
class TestTheReceipt:
    async def test_the_receipt_is_appended_and_readable(
        self, stress_db: dict[str, Any], tmp_path: Path
    ) -> None:
        """Vai para um JSONL porque ``replay_runs`` não representa esta linha:
        ``CHECK (cohort = 'replay:' || run_id::text)`` e nenhuma coluna
        ``kind`` (brief para a database-architect em
        ``.claude/state/brief-T3.36-db-replay-runs-kind.md``)."""
        run = await run_stress(stress_db["factory"], cohort=COHORT, as_of=utcnow())
        ledger = tmp_path / "stress.jsonl"
        append_jsonl(ledger, run)
        append_jsonl(ledger, run)
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2, "acrescenta, nunca reescreve"
        payload = json.loads(lines[0])
        assert payload["cohort"] == COHORT
        assert payload["stress_version"] == 1
        assert payload["partial"] is False
        assert payload["input_digest"]
        assert [row["key"] for row in payload["rows"]][0] == BASE
        assert payload["verdict"] == "amostra_insuficiente"

    async def test_the_rendered_table_names_its_population(self, stress_db: dict[str, Any]) -> None:
        run = await run_stress(stress_db["factory"], cohort=COHORT, as_of=utcnow())
        table = run.render()
        assert COHORT in table
        assert "1 entradas congeladas" in table
        assert "| `custos_x2` |" in table
        assert "**Veredito:** amostra_insuficiente" in table

    async def test_a_limited_pass_is_labelled_partial(self, stress_db: dict[str, Any]) -> None:
        run = await run_stress(stress_db["factory"], cohort=COHORT, as_of=utcnow(), limit=1)
        assert run.partial is True
        assert "TABELA PARCIAL" in run.render()
