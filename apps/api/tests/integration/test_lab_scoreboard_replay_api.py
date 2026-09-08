"""Integration tests: ``ScoreboardRowOut.replay`` — brief T3.18b, item 1 (D14/D15).

Proves the block is populated from ``replay:<uuid>`` cohorts and
``replay_runs`` receipts, and — the brief's explicit assertion — that a
version whose replay is positive and whose prospective is negative still
gets its verdict and maturity from prospective alone.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from hunter_core.domain.enums import OutcomeResult

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


async def _row(client: httpx.AsyncClient, actor: Actor, version_id: uuid.UUID) -> dict[str, Any]:
    response = await client.get(
        "/api/v1/lab/shadow/scoreboard", params={"as_of": NOW.isoformat()}, headers=actor.headers
    )
    assert response.status_code == 200, response.text
    return next(r for r in response.json()["rows"] if r["version"]["id"] == str(version_id))


async def test_no_replay_evidence_is_null(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=1),
        exit_ts=NOW - timedelta(minutes=30),
        entry_ts=NOW - timedelta(minutes=59),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1"),
    )
    actor = make_actor("replay-block-null")

    row = await _row(client, actor, version_id)

    assert row["replay"] is None


async def test_replay_positive_and_prospective_negative_never_swap_the_verdict(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """The brief's own assertion (item 1): a version whose ``replay`` block is
    positive and whose prospective population is negative keeps its verdict
    and maturity computed on prospective alone."""
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=2)
    )
    market_id = await fx.seed_lab_market(session_factory)

    # prospective: a single mature loss -> immature (verdict "inconclusivo"),
    # but if it ever counted, strictly negative expectancy.
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=6),
        exit_ts=NOW - timedelta(hours=5),
        entry_ts=NOW - timedelta(hours=6) + timedelta(minutes=1),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1"),
        cohort="prospective",
    )

    # replay: several winners under one receipted run.
    run_id = uuid.uuid4()
    decision_at = NOW - timedelta(days=10)
    for i in range(3):
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=decision_at + timedelta(minutes=i),
            exit_ts=decision_at + timedelta(hours=1, minutes=i),
            entry_ts=decision_at + timedelta(minutes=i + 1),
            result=OutcomeResult.TARGET,
            r_multiple=Decimal("2"),
            cohort=f"replay:{run_id}",
        )
    await fx.seed_replay_slice(
        session_factory,
        run_id=run_id,
        strategy_version_id=version_id,
        window_from=decision_at - timedelta(hours=1),
        window_to=NOW - timedelta(days=9),
        markets=["labex:LABUSDT"],
        started_at=decision_at,
        finished_at=decision_at + timedelta(minutes=5),
        bars_evaluated=288,
        signals=3,
        outcomes_resolved=3,
        outcomes_open=0,
        seconds=Decimal("12.500"),
        evaluations_by_state={"triggered": 3, "not_triggered": 197, "unavailable": 88},
    )
    actor = make_actor("replay-verdict-isolation")

    row = await _row(client, actor, version_id)

    # verdict/maturity: prospective only, one immature loss.
    assert row["evaluable"] == 1
    assert row["maturity"]["mature"] is False
    assert row["verdict"] == "inconclusivo"

    # replay block: positive, separate, labelled, never touching the above.
    replay = row["replay"]
    assert replay is not None
    assert replay["runs"] == 1
    assert replay["bars_evaluated"] == 288
    # D14, T3.18c item 9: massa é barra **com decisão registrada**; as 88 em
    # warm-up/gap não são decisões e não entram na meta de 500 mil por dia.
    assert replay["decisions_simulated"] == 200
    assert replay["evaluations_by_state"] == {
        "triggered": 3,
        "not_triggered": 197,
        "unavailable": 88,
    }
    assert replay["operations_closed"] == 3
    assert replay["expectancy_r"]["value"] == "2"
    assert replay["net_profit_rate"] == {
        "value": "1",
        "reason": None,
        "numerator": 3,
        "denominator": 3,
    }
    assert replay["label"] == "replay — não conta para o veredito"
    assert replay["window_from"] is not None
    assert replay["window_to"] is not None


async def test_a_receipt_that_finished_after_the_cut_is_not_counted(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """T3.18c, item 7: ``replay_runs`` também respeita ``as_of``.

    Uma leitura datada de ontem não pode mostrar a massa de uma corrida que só
    terminou hoje — isso descreveria trabalho que, naquele instante, não tinha
    acontecido.
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=30)
    )
    market_id = await fx.seed_lab_market(session_factory)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(days=20),
        entry_ts=NOW - timedelta(days=20) + timedelta(minutes=1),
        exit_ts=NOW - timedelta(days=20) + timedelta(hours=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1"),
    )
    run_id = uuid.uuid4()
    await fx.seed_replay_slice(
        session_factory,
        run_id=run_id,
        strategy_version_id=version_id,
        window_from=NOW - timedelta(days=31),
        window_to=NOW - timedelta(days=1),
        markets=["labex:LABUSDT"],
        started_at=NOW + timedelta(hours=1),
        finished_at=NOW + timedelta(hours=2),
        bars_evaluated=1000,
        signals=0,
        outcomes_resolved=0,
        outcomes_open=0,
        seconds=Decimal("60.000"),
        evaluations_by_state={"triggered": 0, "not_triggered": 1000},
    )
    actor = make_actor("replay-runs-as-of")

    row = await _row(client, actor, version_id)

    assert row["replay"] is None, "nenhum recibo dentro do corte, nenhuma linha de replay"


async def test_a_mature_reproved_prospective_is_not_rescued_by_a_large_positive_replay(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """T3.18c, item 11: o teste-prova com uma população **madura e negativa**.

    O teste anterior usava um prospectivo imaturo, que sairia ``inconclusivo``
    de qualquer jeito — ele não distinguia "o replay não contamina" de "não
    havia amostra". Aqui o prospectivo é ``reprovada`` (100 perdas em 100 dias)
    e o replay é grande e positivo: o veredito, a maturidade e o ``parent`` da
    replicação continuam negativos, e o bloco de replay continua positivo ao
    lado, rotulado.
    """
    first_day = NOW - timedelta(days=110)
    _, version_id = await fx.seed_strategy_version(
        session_factory,
        activated_at=NOW - timedelta(days=200),
        promising_at=NOW - timedelta(days=150),
        promising_by="validada",
    )
    market_id = await fx.seed_lab_market(session_factory)
    run_id = uuid.uuid4()
    specs: list[dict[str, Any]] = []
    for index in range(100):
        decision_at = first_day + timedelta(days=index)
        for cohort, r_multiple in (
            ("prospective", Decimal("-1")),
            (f"replay:{run_id}", Decimal("2")),
        ):
            specs.append(
                {
                    "strategy_version_id": version_id,
                    "market_id": market_id,
                    "decision_at": decision_at,
                    "entry_ts": decision_at + timedelta(minutes=1),
                    "exit_ts": decision_at + timedelta(hours=1),
                    "result": OutcomeResult.STOP if r_multiple < 0 else OutcomeResult.TARGET,
                    "r_multiple": r_multiple,
                    "cohort": cohort,
                }
            )
    await fx.seed_shadow_population(session_factory, specs)
    await fx.seed_replay_slice(
        session_factory,
        run_id=run_id,
        strategy_version_id=version_id,
        window_from=first_day,
        window_to=NOW - timedelta(days=9),
        markets=["labex:LABUSDT"],
        started_at=NOW - timedelta(hours=3),
        finished_at=NOW - timedelta(hours=2),
        bars_evaluated=10_000,
        signals=100,
        outcomes_resolved=100,
        outcomes_open=0,
        seconds=Decimal("200.000"),
        evaluations_by_state={"triggered": 100, "not_triggered": 8_900, "unavailable": 1_000},
    )
    actor = make_actor("replay-does-not-rescue")

    row = await _row(client, actor, version_id)

    assert row["evaluable"] == 100
    assert row["maturity"]["mature"] is True
    assert row["verdict"] == "reprovada"
    assert row["replication"]["parent"]["verdict"] == "reprovada"
    assert row["replication"]["parent"]["evaluable"] == 100
    assert row["replication"]["parent"]["expectancy_r"] == "-1"
    assert row["replay"]["operations_closed"] == 100
    assert row["replay"]["expectancy_r"]["value"] == "2"
    assert row["replay"]["decisions_simulated"] == 9_000
