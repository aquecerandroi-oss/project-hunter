"""Integration: **um contrato só** entre placar e replicação — brief T3.18c.

O que se prova aqui, contra Postgres de verdade:

- item 2 — ``replication.parent.evaluable == row.evaluable`` e
  ``parent.verdict == row.verdict``, inclusive nos dois extremos do profit
  factor (só perdas, nenhuma perda);
- item 5 — a mesma população volta na mesma ordem, e o bootstrap com a mesma
  semente devolve o mesmo intervalo;
- item 6 — a semente vem do evento da rodada, com a proveniência declarada;
- item 8 — sem ``promising_at`` o bloco é ``null``, e ``?include=`` escolhe o
  que é calculado.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.domain.enums import OutcomeResult

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
PROMISING_AT = NOW - timedelta(days=120)
FIRST_DAY = NOW - timedelta(days=100)


async def _row(
    client: httpx.AsyncClient,
    actor: Actor,
    version_id: uuid.UUID,
    *,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    query = {"as_of": NOW.isoformat(), **(params or {})}
    response = await client.get(
        "/api/v1/lab/shadow/scoreboard", params=query, headers=actor.headers
    )
    assert response.status_code == 200, response.text
    return next(r for r in response.json()["rows"] if r["version"]["id"] == str(version_id))


def _population(
    *, version_id: uuid.UUID, market_id: uuid.UUID, values: list[Decimal]
) -> list[dict[str, Any]]:
    """Um resultado por dia, cem dias: cem avaliáveis e cem dias de saída."""
    specs: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        decision_at = FIRST_DAY + timedelta(days=index)
        specs.append(
            {
                "strategy_version_id": version_id,
                "market_id": market_id,
                "decision_at": decision_at,
                "entry_ts": decision_at + timedelta(minutes=1),
                "exit_ts": decision_at + timedelta(hours=1),
                "result": OutcomeResult.TARGET if value > 0 else OutcomeResult.STOP,
                "r_multiple": value,
            }
        )
    return specs


async def _mature_version(
    session_factory: async_sessionmaker[AsyncSession], values: list[Decimal]
) -> uuid.UUID:
    _, version_id = await fx.seed_strategy_version(
        session_factory,
        activated_at=NOW - timedelta(days=200),
        promising_at=PROMISING_AT,
        promising_by="validada",
    )
    market_id = await fx.seed_lab_market(session_factory)
    await fx.seed_shadow_population(
        session_factory, _population(version_id=version_id, market_id=market_id, values=values)
    )
    return version_id


class TestOneDefinitionOfEvaluable:
    """Astra, 2026-09-08 (HIGH e MEDIUM): o mesmo JSON não pode publicar dois
    vereditos sobre a mesma evidência."""

    async def test_a_mixed_population_agrees_on_population_and_verdict(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        # 75 × +1 e 25 × −0,5 -> expectancy 0,625 e PF 6: validada dos dois lados.
        values = [Decimal("1")] * 75 + [Decimal("-0.5")] * 25
        version_id = await _mature_version(session_factory, values)

        row = await _row(client, make_actor("contract-mixed"), version_id)
        parent = row["replication"]["parent"]

        assert row["evaluable"] == parent["evaluable"] == 100
        assert row["maturity"]["days"] == parent["days"] == 100
        assert row["verdict"] == parent["verdict"] == "validada"
        assert row["expectancy_r"]["value"] == parent["expectancy_r"] == "0.625"
        assert row["profit_factor"]["value"] == parent["profit_factor"] == "6"

    async def test_a_population_with_no_losses_is_validada_on_both_sides(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        """O caso que divergia: PF nulo por ``sem_perdas`` conta como > 1."""
        version_id = await _mature_version(session_factory, [Decimal("1")] * 100)

        row = await _row(client, make_actor("contract-no-losses"), version_id)
        parent = row["replication"]["parent"]

        assert row["verdict"] == parent["verdict"] == "validada"
        assert row["profit_factor"]["value"] is None
        assert parent["profit_factor"] is None
        assert row["profit_factor"]["reason"] == "no_losses"
        assert parent["profit_factor_reason"] == "sem_perdas"

    async def test_a_population_with_no_wins_reports_profit_factor_zero_on_both_sides(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        """O outro extremo: 0 / |perdas| é zero **com motivo nulo**, nunca
        ``sem_ganhos`` — era a segunda metade da divergência."""
        version_id = await _mature_version(session_factory, [Decimal("-1")] * 100)

        row = await _row(client, make_actor("contract-no-wins"), version_id)
        parent = row["replication"]["parent"]

        assert row["verdict"] == parent["verdict"] == "reprovada"
        assert row["profit_factor"]["value"] == parent["profit_factor"] == "0"
        assert row["profit_factor"]["reason"] is None
        assert parent["profit_factor_reason"] is None

    async def test_an_open_horizon_is_excluded_from_both_counts(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        """O portão de horizonte, que a replicação não aplicava: um desfecho
        rápido cujo horizonte ainda não fechou não conta em lugar nenhum."""
        version_id = await _mature_version(session_factory, [Decimal("1")] * 100)
        market_id = await fx.seed_lab_market(session_factory)
        just_resolved = NOW - timedelta(minutes=30)
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=just_resolved,
            entry_ts=just_resolved + timedelta(minutes=1),
            exit_ts=just_resolved + timedelta(minutes=10),
            result=OutcomeResult.STOP,
            r_multiple=Decimal("-3"),
            horizon_s=4 * 3600,
        )

        row = await _row(client, make_actor("contract-horizon"), version_id)
        parent = row["replication"]["parent"]

        assert row["emitted"] == 101
        assert row["evaluable"] == parent["evaluable"] == 100
        assert parent["expectancy_r"] == "1"


class TestSeedProvenance:
    async def test_without_a_registered_round_the_seed_is_declared_derived(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        version_id = await _mature_version(session_factory, [Decimal("1")] * 100)

        row = await _row(client, make_actor("seed-derived"), version_id)
        bootstrap = row["replication"]["bootstrap"]

        assert bootstrap["seed"] == int.from_bytes(version_id.bytes[:4], "big")
        assert bootstrap["seed_source"] == "derivada_do_id"
        assert bootstrap["day_cluster"]["seed_source"] == "derivada_do_id"

    async def test_the_rounds_event_is_where_the_seed_comes_from(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        """Do **evento**, não do ``changelog``: o CLI grava a semente num campo
        próprio no mesmo commit que criou as irmãs (T3.18c, item 6)."""
        version_id = await _mature_version(session_factory, [Decimal("1")] * 100)
        await _record_replication_event(session_factory, version_id, seed=20260908)

        row = await _row(client, make_actor("seed-registered"), version_id)
        bootstrap = row["replication"]["bootstrap"]

        assert bootstrap["seed"] == 20260908
        assert bootstrap["seed_source"] == "registrada"


class TestDeterministicOrderAndReproducibility:
    async def test_ties_in_emitted_at_never_move_the_interval(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        """T3.18c, item 5: o replay produz empates de ``emitted_at`` por
        construção, e o bootstrap reamostra por índice — sem ``id`` no
        ``ORDER BY``, duas leituras iguais medem intervalos diferentes."""
        _, version_id = await fx.seed_strategy_version(
            session_factory,
            activated_at=NOW - timedelta(days=200),
            promising_at=PROMISING_AT,
            promising_by="validada",
        )
        market_id = await fx.seed_lab_market(session_factory)
        specs: list[dict[str, Any]] = []
        for day in range(40):
            decision_at = FIRST_DAY + timedelta(days=day)
            for index, value in enumerate((Decimal("1"), Decimal("-0.4"))):
                specs.append(
                    {
                        "strategy_version_id": version_id,
                        "market_id": market_id,
                        # o mesmo instante para os dois: empate por construção
                        "decision_at": decision_at,
                        "entry_ts": decision_at + timedelta(minutes=1),
                        "exit_ts": decision_at + timedelta(hours=1 + index),
                        "result": OutcomeResult.TARGET if value > 0 else OutcomeResult.STOP,
                        "r_multiple": value,
                    }
                )
        await fx.seed_shadow_population(session_factory, specs)
        actor = make_actor("deterministic-order")

        first = await _row(client, actor, version_id)
        second = await _row(client, actor, version_id)

        assert first["replication"]["bootstrap"]["n"] == 80
        assert first["replication"]["bootstrap"] == second["replication"]["bootstrap"]
        assert first["replication"]["parent"] == second["replication"]["parent"]


class TestCheapNullAndInclude:
    async def test_a_version_without_promising_at_carries_a_null_block(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        _, version_id = await fx.seed_strategy_version(
            session_factory, activated_at=NOW - timedelta(days=200)
        )
        market_id = await fx.seed_lab_market(session_factory)
        await fx.seed_shadow_population(
            session_factory,
            _population(version_id=version_id, market_id=market_id, values=[Decimal("1")] * 100),
        )

        row = await _row(client, make_actor("cheap-null"), version_id)

        assert row["verdict"] == "validada"
        assert row["replication"] is None

    async def test_include_selects_which_blocks_are_computed(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        version_id = await _mature_version(session_factory, [Decimal("1")] * 100)
        actor = make_actor("include-param")

        both = await _row(client, actor, version_id)
        only_replay = await _row(client, actor, version_id, params={"include": "replay"})

        assert both["replication"] is not None
        assert only_replay["replication"] is None
        assert only_replay["verdict"] == both["verdict"]

    async def test_an_unknown_include_is_422(
        self, client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
    ) -> None:
        response = await client.get(
            "/api/v1/lab/shadow/scoreboard",
            params={"include": "replay,carteira"},
            headers=make_actor("include-invalid").headers,
        )
        assert response.status_code == 422, response.text
        assert response.json()["type"].endswith("invalid-include")


async def _record_replication_event(
    session_factory: async_sessionmaker[AsyncSession], version_id: uuid.UUID, *, seed: int
) -> None:
    """A linha que ``hunter_strategy_worker.replication`` escreve ao replicar."""
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO system_events (id, created_at, level, component, event, message, "
                "data) VALUES (gen_random_uuid(), now(), 'info', "
                "'replicate_strategy_version', 'strategy_version_replicated', 'test', "
                "CAST(:data AS jsonb))"
            ),
            {
                "data": json.dumps(
                    {"strategy_version_id": str(version_id), "seed": seed, "forced": False}
                )
            },
        )
        await session.commit()
