"""O pacote da barra contra Postgres real: mesma decisão, um décimo das idas — T3.74g.

Irmão de `test_context_cache_engine.py` (a mesma prova para o cache de família
da T3.74b), separado dele só porque aquele arquivo já está no limite de 350
linhas do repositório. As duas metades que o brief pede estão aqui:

1. **equivalência** — cada versão devida decidida duas vezes sobre a *mesma*
   série imutável, uma pelo caminho de antes (cada versão faz as suas leituras)
   e uma pelo pacote (:mod:`hunter_strategy_worker.bar_context`), tem de
   devolver a mesma `Evaluation` e a mesma `Provenance`. A `Provenance` é
   comparada campo a campo **menos** `eligibility_observed_at`, que é o relógio
   de parede da leitura do universo e é diferente por construção em duas
   passadas diferentes — comparar esse campo seria exigir que o tempo não
   passasse entre elas;
2. **custo** — quantas idas ao banco e ao Redis uma barra faz. Contagem, não
   cronômetro: `load_candles`, `hot_state.read_tail` e `load_derivatives` são
   contados por barra, e a asserção é sobre o número (independente de máquina),
   não sobre milissegundos. Antes: uma leitura de vela por família, mais uma
   cauda e um par de derivativos **por versão**. Depois: uma de cada por barra.
"""

from __future__ import annotations

import dataclasses
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker import context as context_module
from hunter_strategy_worker.bar_context import build_bar_bundle, load_bar_bundle
from hunter_strategy_worker.catalogue import ActiveVersion
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.context import build_market_context
from hunter_strategy_worker.context_cache import build_family_readers
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    activate_version,
    ensure_partitions,
    insert_candles,
    seed_market,
    series,
)

pytestmark = pytest.mark.integration

logger = get_logger(__name__)

LATE = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
"""O fim da própria série de `builders.series` — a barra com o pico de volume."""
CONFIG = ShadowConfig(hot_state_tail=5)
SYMBOLS = ("BUNDLE0USDT", "BUNDLE1USDT")


def _version(key: str, version_id: uuid.UUID, *, version: str, atr_bars: int) -> ActiveVersion:
    params = dict(VOLUME_ANOMALY_V1.default_parameters)
    params["atr_bars"] = atr_bars
    return ActiveVersion(
        id=version_id,
        strategy_key=key,
        version=version,
        params=params,
        params_hash=params_hash(params),
        strategy=VOLUME_ANOMALY_V1,
        code_ref=None,
        purpose="research_only",
    )


@pytest.fixture
async def markets(db_session_factory: Any) -> list[Any]:
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, LATE)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM candles"))
        for symbol in SYMBOLS:
            _exchange_id, market_id = await seed_market(session, symbol=symbol, base_asset="BTC")
            await insert_candles(session, market_id, series(LATE))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = [await load_market(session, EXCHANGE, symbol) for symbol in SYMBOLS]
    assert all(row is not None for row in rows)
    return rows


@pytest.fixture
async def versions(db_session_factory: Any) -> list[ActiveVersion]:
    """Duas janelas distintas dentro da mesma família (1560 pelo piso, 1570 por
    `atr_bars = 103`) mais uma versão de outra família: é o formato em que a
    fatia do pacote pode divergir, e portanto o único em que provar não divergir
    diz alguma coisa."""
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM shadow_outbox"))
        await session.execute(text("DELETE FROM shadow_episodes"))
        await session.execute(text("DELETE FROM signal_outcomes"))
        await session.execute(text("DELETE FROM agent_signals"))
        ids = [
            (await activate_version(session, key="bundle_family", version=f"v{i}"))[1]
            for i in range(1, 4)
        ]
        lone = (await activate_version(session, key="bundle_lone", version="v1"))[1]
    return [
        _version("bundle_family", ids[0], version="v1", atr_bars=97),
        _version("bundle_family", ids[1], version="v2", atr_bars=103),
        _version("bundle_family", ids[2], version="v3", atr_bars=97),
        _version("bundle_lone", lone, version="v1", atr_bars=97),
    ]


class TestEquivalence:
    async def test_context_and_provenance_are_the_ones_the_old_reads_produced(
        self, db_session_factory: Any, redis_client: Any, markets: list[Any], versions: list[Any]
    ) -> None:
        market = markets[0]
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            bundle = await build_bar_bundle(
                session, redis_client, versions, market=market, bar_close=LATE, config=CONFIG
            )
        for version in versions:
            minutes = version.context_minutes(CONFIG)
            async with role_session(db_session_factory, db_role="hunter_worker") as session:
                old_ctx, old_prov = await build_market_context(
                    session,
                    redis_client,
                    market=market,
                    source_bar_close=LATE,
                    config=CONFIG,
                    context_minutes=minutes,
                    policy=version.eligibility_policy,
                )
                new_ctx, new_prov = await build_market_context(
                    session,
                    redis_client,
                    market=market,
                    source_bar_close=LATE,
                    config=CONFIG,
                    context_minutes=minutes,
                    policy=version.eligibility_policy,
                    bundle=bundle,
                )
            assert new_ctx == old_ctx, f"{version.strategy_key} {version.version}"
            observed = old_prov.eligibility_observed_at
            assert dataclasses.replace(new_prov, eligibility_observed_at=observed) == old_prov

    async def test_every_version_decides_byte_identically_through_the_bundle(
        self, db_session_factory: Any, redis_client: Any, markets: list[Any], versions: list[Any]
    ) -> None:
        market = markets[1]
        clock = lambda: LATE + timedelta(seconds=2)  # noqa: E731

        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            family_readers = await build_family_readers(
                session, versions, market=market, bar_close=LATE, config=CONFIG
            )
        before = [
            await evaluate_slot(
                db_session_factory,
                redis_client,
                version=version,
                market=market,
                bar_close=LATE,
                config=CONFIG,
                clock=clock,
                candles_reader=family_readers.get(version.strategy_key),
            )
            for version in versions
        ]

        bundle = await load_bar_bundle(
            db_session_factory,
            redis_client,
            versions,
            market=market,
            bar_close=LATE,
            config=CONFIG,
        )
        assert bundle is not None
        after = [
            await evaluate_slot(
                db_session_factory,
                redis_client,
                version=version,
                market=market,
                bar_close=LATE,
                config=CONFIG,
                clock=clock,
                bundle=bundle,
            )
            for version in versions
        ]

        for version, old, new in zip(versions, before, after, strict=True):
            label = f"{version.strategy_key} {version.version}"
            assert new.state == old.state, label
            assert new.reason == old.reason, label
            assert new.detail == old.detail, label
            assert new.decision == old.decision, label


class TestRoundTrips:
    async def test_one_bar_reads_the_candles_the_tail_and_the_derivatives_once(
        self,
        db_session_factory: Any,
        redis_client: Any,
        markets: list[Any],
        versions: list[Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        market = markets[0]
        clock = lambda: LATE + timedelta(seconds=2)  # noqa: E731
        counts: dict[str, int] = {}

        def counting(module: Any, name: str, key: str) -> None:
            original = getattr(module, name)

            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                counts[key] = counts.get(key, 0) + 1
                return await original(*args, **kwargs)

            monkeypatch.setattr(module, name, wrapper)

        counting(context_module, "load_candles", "candles")
        counting(context_module.hot_state, "read_tail", "tail")
        counting(context_module, "load_derivatives", "derivatives")

        async def run(*, bundle: Any) -> None:
            for version in versions:
                await evaluate_slot(
                    db_session_factory,
                    redis_client,
                    version=version,
                    market=market,
                    bar_close=LATE,
                    config=CONFIG,
                    clock=clock,
                    bundle=bundle,
                )

        counts.clear()
        await run(bundle=None)
        before = dict(counts)

        # Uma leitura de cada, por versão: quatro versões, doze idas.
        assert before == {
            "candles": len(versions),
            "tail": len(versions),
            "derivatives": len(versions),
        }

        bundle = await load_bar_bundle(
            db_session_factory,
            redis_client,
            versions,
            market=market,
            bar_close=LATE,
            config=CONFIG,
        )
        assert bundle is not None
        # O pacote já leu (uma vez cada, antes deste ``clear``); o que se conta
        # agora é o caminho por versão, e ele não lê mais nada.
        counts.clear()
        await run(bundle=bundle)
        assert counts == {}


class TestCostAgainstPostgres:
    """O mesmo trabalho com e sem o pacote, com banco e Redis reais.

    Milissegundos por avaliação medidos ponta a ponta dentro do worker
    (contexto + gates + slot + persistência), não só a CPU do `explain` do
    benchmark sem banco. Nada aqui é asserção de magnitude — o número vai para
    o log e para `.claude/state/notes-T3.74g.md`; a asserção é a de sempre:
    o caminho novo não é mais lento que o antigo. Os dois cortes são
    diferentes de propósito, para que o estado de slot de uma passada não
    apareça no tempo da outra (o mesmo cuidado de `test_context_cache_engine`).
    """

    async def test_the_bundle_is_never_slower_end_to_end(
        self, db_session_factory: Any, redis_client: Any, markets: list[Any], versions: list[Any]
    ) -> None:
        evaluations = len(markets) * len(versions)

        async def pass_over(cut: datetime, *, with_bundle: bool) -> float:
            clock = lambda: cut + timedelta(seconds=2)  # noqa: E731
            started = time.perf_counter()
            for market in markets:
                bundle = (
                    await load_bar_bundle(
                        db_session_factory,
                        redis_client,
                        versions,
                        market=market,
                        bar_close=cut,
                        config=CONFIG,
                    )
                    if with_bundle
                    else None
                )
                for version in versions:
                    await evaluate_slot(
                        db_session_factory,
                        redis_client,
                        version=version,
                        market=market,
                        bar_close=cut,
                        config=CONFIG,
                        clock=clock,
                        bundle=bundle,
                    )
            return time.perf_counter() - started

        before_s = await pass_over(LATE - timedelta(minutes=60), with_bundle=False)
        after_s = await pass_over(LATE - timedelta(minutes=30), with_bundle=True)

        assert after_s < before_s
        logger.info(
            "t374g_bundle_cost_against_postgres",
            markets=len(markets),
            versions=len(versions),
            evaluations=evaluations,
            before_s=round(before_s, 2),
            after_s=round(after_s, 2),
            before_ms_per_evaluation=round(before_s / evaluations * 1000, 1),
            after_ms_per_evaluation=round(after_s / evaluations * 1000, 1),
            speedup=round(before_s / after_s, 2),
        )
