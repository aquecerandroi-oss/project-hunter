"""Integration: a evidência de uma irmã conta **uma vez** — brief T3.18c.

- item 3 — 25 resultados replayados sob duas corridas são 25, nunca 50; cada
  braço carrega a janela dos replays dele e o bloco carrega o rótulo
  ``siblings: replay sobre <janela>`` (REPLICATION.md §3.5 item 4);
- item 11 — ``sibling_population`` é exercitada **direto**, sem passar pelo
  endpoint: a regra de evidência mora nela;
- item 13 — uma irmã promovida a viva mantém a evidência prospectiva dela.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from hunter_api.repositories.lab_replication import LabReplicationRepository
from hunter_core.domain.enums import OutcomeResult, ShadowCohort

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
PROMISING_AT = NOW - timedelta(days=60)
FIRST_DAY = NOW - timedelta(days=40)
WINDOW_FROM = NOW - timedelta(days=40)
WINDOW_TO = NOW - timedelta(days=9)


async def _parent_with_sibling(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """``(parent_id, sibling_id, market_id)`` — o pai já promissor, uma irmã."""
    strategy_id, parent_id = await fx.seed_strategy_version(
        session_factory,
        activated_at=NOW - timedelta(days=90),
        promising_at=PROMISING_AT,
        promising_by="validada",
    )
    market_id = await fx.seed_lab_market(session_factory)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=parent_id,
        market_id=market_id,
        decision_at=NOW - timedelta(days=5),
        entry_ts=NOW - timedelta(days=5) + timedelta(minutes=1),
        exit_ts=NOW - timedelta(days=5) + timedelta(hours=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1"),
    )
    _, sibling_id = await fx.seed_strategy_version(
        session_factory,
        strategy_id=strategy_id,
        version="v2",
        activated_at=NOW - timedelta(days=50),
        replication_parent_id=parent_id,
        replication_index=1,
    )
    return parent_id, sibling_id, market_id


def _specs(
    *, version_id: uuid.UUID, market_id: uuid.UUID, cohort: str, n: int, r: Decimal
) -> list[dict[str, Any]]:
    """``n`` decisões, uma por dia — a mesma sequência para qualquer coorte."""
    specs: list[dict[str, Any]] = []
    for index in range(n):
        decision_at = FIRST_DAY + timedelta(days=index)
        specs.append(
            {
                "strategy_version_id": version_id,
                "market_id": market_id,
                "decision_at": decision_at,
                "entry_ts": decision_at + timedelta(minutes=1),
                "exit_ts": decision_at + timedelta(hours=1),
                "result": OutcomeResult.TARGET if r > 0 else OutcomeResult.STOP,
                "r_multiple": r,
                "cohort": cohort,
            }
        )
    return specs


async def _replay_receipt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    version_id: uuid.UUID,
    finished_at: datetime,
) -> None:
    await fx.seed_replay_slice(
        session_factory,
        run_id=run_id,
        strategy_version_id=version_id,
        window_from=WINDOW_FROM,
        window_to=WINDOW_TO,
        markets=["labex:LABUSDT"],
        started_at=finished_at - timedelta(minutes=5),
        finished_at=finished_at,
        bars_evaluated=1000,
        signals=25,
        outcomes_resolved=25,
        outcomes_open=0,
        seconds=Decimal("30.000"),
        evaluations_by_state={"triggered": 25, "not_triggered": 900, "unavailable": 75},
    )


class TestSiblingEvidenceCountedOnce:
    async def test_twenty_five_decisions_replayed_twice_are_twenty_five(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Astra, 2026-09-08 (HIGH): dois ``run_id`` sobre a mesma janela não
        dobram a população nem aproximam a irmã da meia-régua."""
        parent_id, sibling_id, market_id = await _parent_with_sibling(session_factory)
        run_a, run_b = uuid.uuid4(), uuid.uuid4()
        for run in (run_a, run_b):
            await fx.seed_shadow_population(
                session_factory,
                _specs(
                    version_id=sibling_id,
                    market_id=market_id,
                    cohort=ShadowCohort.replay(run),
                    n=25,
                    r=Decimal("1"),
                ),
            )
            await _replay_receipt(
                session_factory,
                run_id=run,
                version_id=sibling_id,
                finished_at=NOW - timedelta(days=8),
            )

        async with session_factory() as session:
            repo = LabReplicationRepository(session)
            siblings = await repo.siblings(parent_id)
            windows = await repo.replay_windows([item.id for item in siblings], as_of=NOW)
            population = await repo.sibling_population(
                siblings[0], parent_id, as_of=NOW, replay_window=windows[sibling_id]
            )

        assert len(population.outcomes) == 25
        assert population.duplicates_dropped == 25
        assert population.evidence == "replay"
        assert population.replay_window.window_from == WINDOW_FROM
        assert population.replay_window.window_to == WINDOW_TO

    async def test_a_sibling_promoted_to_live_keeps_its_prospective_evidence(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Item 13: a coorte viva de uma irmã é o braço **e** ``prospective``,
        e ela tem precedência sobre o replay dos mesmos minutos."""
        parent_id, sibling_id, market_id = await _parent_with_sibling(session_factory)
        await fx.seed_shadow_population(
            session_factory,
            _specs(
                version_id=sibling_id,
                market_id=market_id,
                cohort=ShadowCohort.PROSPECTIVE,
                n=10,
                r=Decimal("1"),
            ),
        )
        await fx.seed_shadow_population(
            session_factory,
            _specs(
                version_id=sibling_id,
                market_id=market_id,
                cohort=ShadowCohort.replay(uuid.uuid4()),
                n=10,
                r=Decimal("-1"),
            ),
        )

        async with session_factory() as session:
            repo = LabReplicationRepository(session)
            siblings = await repo.siblings(parent_id)
            population = await repo.sibling_population(siblings[0], parent_id, as_of=NOW)

        assert population.evidence == "prospective"
        assert population.duplicates_dropped == 10
        assert [outcome.r for outcome in population.outcomes] == [Decimal("1")] * 10

    async def test_the_arm_cohort_and_prospective_are_both_live(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        parent_id, sibling_id, market_id = await _parent_with_sibling(session_factory)
        await fx.seed_shadow_population(
            session_factory,
            _specs(
                version_id=sibling_id,
                market_id=market_id,
                cohort=ShadowCohort.replication(parent_id, 1),
                n=5,
                r=Decimal("1"),
            ),
        )

        async with session_factory() as session:
            repo = LabReplicationRepository(session)
            siblings = await repo.siblings(parent_id)
            population = await repo.sibling_population(siblings[0], parent_id, as_of=NOW)

        assert population.evidence == "prospective"
        assert len(population.outcomes) == 5


class TestTheBlockSaysItRestsOnReplay:
    async def test_the_scoreboard_arm_carries_the_window_and_the_block_the_label(
        self,
        client: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        make_actor: Callable[[str], Actor],
    ) -> None:
        parent_id, sibling_id, market_id = await _parent_with_sibling(session_factory)
        run = uuid.uuid4()
        await fx.seed_shadow_population(
            session_factory,
            _specs(
                version_id=sibling_id,
                market_id=market_id,
                cohort=ShadowCohort.replay(run),
                n=25,
                r=Decimal("1"),
            ),
        )
        await _replay_receipt(
            session_factory, run_id=run, version_id=sibling_id, finished_at=NOW - timedelta(days=8)
        )
        actor = make_actor("siblings-replay-label")

        response = await client.get(
            "/api/v1/lab/shadow/scoreboard",
            params={"as_of": NOW.isoformat()},
            headers=actor.headers,
        )
        assert response.status_code == 200, response.text
        row = next(r for r in response.json()["rows"] if r["version"]["id"] == str(parent_id))
        siblings = row["replication"]["siblings"]

        assert siblings["n"] == 1
        assert siblings["label"] == (
            f"siblings: replay sobre {WINDOW_FROM:%Y-%m-%d} → {WINDOW_TO:%Y-%m-%d}"
        )
        arm = siblings["arms"][0]
        assert arm["evidence"] == "replay"
        assert arm["evaluable"] == 25
        assert arm["mature"] is False, "25 resultados não são a meia-régua de 50"
        assert arm["window_from"] is not None
        assert arm["window_to"] is not None

    async def test_a_receipt_that_finished_after_the_cut_is_not_read(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Item 7 aplicado às janelas das irmãs: ponto no tempo é ponto no
        tempo — um recibo posterior ao corte não descreve aquela leitura."""
        parent_id, sibling_id, market_id = await _parent_with_sibling(session_factory)
        run = uuid.uuid4()
        await fx.seed_shadow_population(
            session_factory,
            _specs(
                version_id=sibling_id,
                market_id=market_id,
                cohort=ShadowCohort.replay(run),
                n=5,
                r=Decimal("1"),
            ),
        )
        await _replay_receipt(
            session_factory, run_id=run, version_id=sibling_id, finished_at=NOW + timedelta(days=1)
        )

        async with session_factory() as session:
            repo = LabReplicationRepository(session)
            siblings = await repo.siblings(parent_id)
            windows = await repo.replay_windows([item.id for item in siblings], as_of=NOW)

        assert windows == {}
