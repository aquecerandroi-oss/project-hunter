"""``breadth_5m``'s per-minute producer, against a real Postgres and a real Redis.

T3.77b — the HIGH finding of the code review on the uncommitted T3.77 producer:
``breadth.py``/``breadth_job.py``/``breadth_repo.py`` had no test of their own.
``services/strategy-worker/tests/test_breadth_gate.py`` inserts ``market_breadth``
rows by hand and proves the *gate*; nothing proved that :func:`run_breadth_once`
itself writes the row the gate then reads. This file is that proof, on the same
doctrine ``test_beta_job.py``/``test_regime_job.py`` already state: the point is
the row and the lock, which no fake session can stand in for.

Every expected number below is worked out by hand rather than taken from
:func:`hunter_indicators.breadth.compute_breadth` at test time — a test that
asks the function under review what it thinks the answer is would pass no
matter what the arithmetic did. ``packages/indicators/tests/unit/
test_breadth_series.py`` is the arithmetic's own proof and is not repeated here.

Each test seeds its own exchange (``binance-<tag>``), the same isolation
``test_regime_job.py``'s ``_universe`` uses: the producer's three queries all
join through ``exchanges.code``, so two tests never share a universe.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from sqlalchemy import insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.market_data import Candle
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketStatus, MarketType, Timeframe
from hunter_indicators.breadth import WINDOW_MINUTES, window_open_times
from hunter_scanner_worker.breadth import claim_minute
from hunter_scanner_worker.breadth_job import minutes_due, run_breadth_once

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

pytestmark = pytest.mark.integration

MINUTE = timedelta(minutes=1)
CUT = datetime(2026, 9, 10, 12, 6, tzinfo=UTC)
"""The closed minute every test folds. Arbitrary, except that it is a minute
whose six candles ``window_open_times`` names all fall on 2026-09-10."""

WINDOW = window_open_times(CUT, WINDOW_MINUTES)
"""The six ``open_time``s the reading needs, oldest first: ``CUT-6min`` through
``CUT-1min``. Computed with the same function the job imports, so a change to
the window's shape moves both sides of every test here together."""


async def _upsert_asset(session: Any, symbol: str) -> Any:
    """A copy of ``db_helpers._upsert_asset`` — that one is private to its
    module, and duplicating four lines here beats importing another module's
    underscore-named helper (``reportPrivateUsage``)."""
    stmt = (
        pg_insert(Asset)
        .values(symbol=symbol)
        .on_conflict_do_update(index_elements=["symbol"], set_={"symbol": symbol})
        .returning(Asset.id)
    )
    return await session.scalar(stmt)


async def _upsert_exchange(session: Any, code: str) -> Any:
    """A copy of ``db_helpers._upsert_exchange``, for the same reason."""
    stmt = (
        pg_insert(Exchange)
        .values(code=code, name=code)
        .on_conflict_do_update(index_elements=["code"], set_={"code": code})
        .returning(Exchange.id)
    )
    return await session.scalar(stmt)


async def _seed_market(
    factory: Any,
    exchange: str,
    symbol: str,
    *,
    market_type: MarketType = MarketType.PERPETUAL,
    is_monitored: bool = True,
    status: MarketStatus = MarketStatus.ACTIVE,
    base: str = "X",
    quote: str = "USDT",
) -> UUID:
    """Same shape as ``db_helpers.seed_market``, with the two knobs that module
    has no reason to offer and this file needs: ``market_type`` (T3.73's spot
    exclusion) and ``is_monitored`` (the whole of the producer's universe
    query). ``db_helpers.seed_market`` always monitors a perpetual; a breadth
    test has to be able to seed the opposite of both."""
    async with role_session(factory, db_role="hunter_worker") as session:
        exchange_id = await _upsert_exchange(session, exchange)
        base_id = await _upsert_asset(session, base)
        quote_id = await _upsert_asset(session, quote)
        market = Market(
            exchange_id=exchange_id,
            symbol=symbol,
            market_type=market_type,
            base_asset_id=base_id,
            quote_asset_id=quote_id,
            is_monitored=is_monitored,
            status=status,
        )
        session.add(market)
        await session.flush()
        return market.id


async def _seed_candles(
    factory: Any,
    market_id: UUID,
    closes: dict[datetime, Decimal],
    *,
    final: set[datetime] | None = None,
) -> None:
    """One 1m candle per ``(open_time, close)``. ``final`` names the open times
    written ``is_final = true``; everything else in ``closes`` is written still
    printing — the same shape a look-ahead bug turns into a complete window."""
    rows = [
        {
            "market_id": market_id,
            "timeframe": Timeframe.M1,
            "open_time": open_time,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": Decimal("1"),
            "is_final": final is None or open_time in final,
        }
        for open_time, close in closes.items()
    ]
    async with role_session(factory, db_role="hunter_worker") as session:
        await session.execute(insert(Candle), rows)


def _full_window(
    *, first: Decimal, last: Decimal, mid: Decimal | None = None
) -> dict[datetime, Decimal]:
    """The six closes ``compute_breadth`` needs. Only ``WINDOW[0]`` (``first``)
    and ``WINDOW[-1]`` (``last``) decide falling/rising; the middle four hold
    whatever ``mid`` is (default: ``first``, so a flat market that only moves at
    the very end is the default shape)."""
    body = mid if mid is not None else first
    return {
        WINDOW[0]: first,
        WINDOW[1]: body,
        WINDOW[2]: body,
        WINDOW[3]: body,
        WINDOW[4]: body,
        WINDOW[5]: last,
    }


async def _row(factory: Any, exchange: str, *, end_time: datetime) -> Any:
    async with role_session(factory, db_role="hunter_worker") as session:
        return (
            await session.execute(
                text(
                    "SELECT mb.* FROM market_breadth mb JOIN exchanges e ON e.id = mb.exchange_id "
                    "WHERE e.code = :exchange AND mb.end_time = :end_time"
                ),
                {"exchange": exchange, "end_time": end_time},
            )
        ).one_or_none()


async def _rows(factory: Any, exchange: str) -> list[Any]:
    async with role_session(factory, db_role="hunter_worker") as session:
        return list(
            (
                await session.execute(
                    text(
                        "SELECT mb.* FROM market_breadth mb JOIN exchanges e ON e.id = mb.exchange_id "
                        "WHERE e.code = :exchange ORDER BY mb.end_time"
                    ),
                    {"exchange": exchange},
                )
            ).all()
        )


class TestAFracaoExata:
    """Item 1 do brief: a fração exata, e quem falta uma vela não conta."""

    async def test_a_leitura_grava_a_fracao_exata_e_exclui_quem_falta_uma_vela(
        self, db_session_factory: Any
    ) -> None:
        """Dez mercados monitorados. Seis caem, dois sobem — oito cobertos — e
        dois ficariam de fora da conta se contassem: um sem uma das seis velas
        (``HOLED``) e um com a sexta vela ainda imprimindo (``UNFINAL``). Os dois
        cairiam se entrassem (``first=100``, ``last`` bem abaixo), então a prova
        não é só "o número bate" — é "excluí-los mudou o numerador, não só o
        denominador". A cobertura resultante, 8/10, é o mesmo piso exato que
        ``test_breadth_series.py::test_exatamente_no_piso_a_leitura_vale`` fixa.
        """
        exchange = "binance-exact"
        falling_ids = [
            await _seed_market(db_session_factory, exchange, f"F{i}USDT") for i in range(6)
        ]
        rising_ids = [
            await _seed_market(db_session_factory, exchange, f"R{i}USDT") for i in range(2)
        ]
        holed_id = await _seed_market(db_session_factory, exchange, "HOLEDUSDT")
        unfinal_id = await _seed_market(db_session_factory, exchange, "UNFINALUSDT")

        for market_id in falling_ids:
            await _seed_candles(
                db_session_factory,
                market_id,
                _full_window(first=Decimal("100"), last=Decimal("99")),
            )
        for market_id in rising_ids:
            await _seed_candles(
                db_session_factory,
                market_id,
                _full_window(first=Decimal("100"), last=Decimal("101")),
            )
        holed = _full_window(first=Decimal("100"), last=Decimal("50"))
        del holed[WINDOW[3]]  # would fall hard if it were counted
        await _seed_candles(db_session_factory, holed_id, holed)
        await _seed_candles(
            db_session_factory,
            unfinal_id,
            _full_window(first=Decimal("100"), last=Decimal("10")),  # would fall hardest of all
            final=set(WINDOW[:-1]),  # every candle final except the one the window ends on
        )

        run = await run_breadth_once(db_session_factory, exchange=exchange, cut=CUT, back=0)

        assert run.universe_size == 10
        assert run.written == 1
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.universe_size == 10
        assert row.covered == 8
        assert row.falling == 6
        assert row.value == Decimal("0.7500")
        assert str(row.value) == "0.750000"  # numeric(9,6)
        assert row.coverage == Decimal("0.8000")
        assert str(row.coverage) == "0.800000"
        assert row.usable is True
        assert row.reason is None


class TestCoberturaInsuficiente:
    """Item 2 do brief: abaixo do piso, a linha existe e diz por quê."""

    async def test_cobertura_abaixo_do_piso_grava_linha_inutilizavel_sem_valor(
        self, db_session_factory: Any
    ) -> None:
        """Cinco de dez respondem (50 %, abaixo dos 80 %): a linha grava
        ``usable = false``, ``reason = 'insufficient_coverage'`` e ``value =
        NULL`` — exatamente o contrato que ``test_breadth_gate.py`` semeou à mão
        (``BLIND``) e nunca provou que o produtor produz."""
        exchange = "binance-lowcov"
        covered_ids = [
            await _seed_market(db_session_factory, exchange, f"C{i}USDT") for i in range(5)
        ]
        for _ in range(5):
            await _seed_market(db_session_factory, exchange, f"B{_}USDT")  # never gets a candle
        for market_id in covered_ids:
            await _seed_candles(
                db_session_factory,
                market_id,
                _full_window(first=Decimal("100"), last=Decimal("90")),
            )

        run = await run_breadth_once(db_session_factory, exchange=exchange, cut=CUT, back=0)

        assert run.universe_size == 10
        assert run.outcomes["insufficient_coverage"] == 1
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.universe_size == 10
        assert row.covered == 5
        assert row.coverage == Decimal("0.5000")
        assert row.value is None
        assert row.usable is False
        assert row.reason == "insufficient_coverage"


class TestIdempotencia:
    """Item 3 do brief: a segunda passagem do mesmo minuto não escreve nada."""

    async def test_a_segunda_passagem_nao_insere_e_a_linha_fica_byte_a_byte_igual(
        self, db_session_factory: Any
    ) -> None:
        exchange = "binance-idem"
        ids = [await _seed_market(db_session_factory, exchange, f"M{i}USDT") for i in range(4)]
        for index, market_id in enumerate(ids):
            last = Decimal("90") if index < 2 else Decimal("110")
            await _seed_candles(
                db_session_factory, market_id, _full_window(first=Decimal("100"), last=last)
            )

        first = await run_breadth_once(db_session_factory, exchange=exchange, cut=CUT, back=0)
        assert first.due == 1
        assert first.written == 1
        before = await _row(db_session_factory, exchange, end_time=CUT)
        assert before is not None

        second = await run_breadth_once(db_session_factory, exchange=exchange, cut=CUT, back=0)
        after = await _row(db_session_factory, exchange, end_time=CUT)

        assert second.due == 0  # minutes_due already excludes the known minute
        assert second.written == 0
        rows = await _rows(db_session_factory, exchange)
        assert len(rows) == 1
        assert dict(after._mapping) == dict(before._mapping)  # not one column moved


class TestOLimiteDoMinutosDue:
    """Item 4 do brief, metade pura: ``minutes_due`` sozinha, sem banco."""

    def test_a_janela_de_back_e_exata_e_um_off_by_one_faria_este_teste_falhar(self) -> None:
        """Último minuto persistido em ``T-3``, ``back=5``: os minutos devidos
        são ``[T-5, T-4, T-2, T-1, T]`` — ``T-3`` sai por já ter linha, e nem um
        minuto a mais nem a menos nas duas pontas. ``T-6`` (um passo além de
        ``back``) nunca aparece, e ``T`` (o próprio corte) aparece sempre que
        não tem linha — a mesma garantia que a docstring da função declara."""
        cut = CUT
        back = 5
        known = {cut - 3 * MINUTE}

        due = minutes_due(cut, back=back, known=known)

        assert due == [
            cut - 5 * MINUTE,
            cut - 4 * MINUTE,
            cut - 2 * MINUTE,
            cut - 1 * MINUTE,
            cut,
        ]
        assert (cut - back * MINUTE) in due
        assert (cut - (back + 1) * MINUTE) not in due
        assert cut in due

    def test_um_minuto_ja_conhecido_no_proprio_corte_nao_e_devido_de_novo(self) -> None:
        """O caso que a T3.77b existe para fechar: ``known`` contém o próprio
        ``cut`` — o minuto não reaparece, por mais que ``back`` seja zero."""
        due = minutes_due(CUT, back=0, known={CUT})
        assert due == []


class TestNaoAntecipacaoNoCaminhoDoProdutor:
    """Item 4 do brief, a outra metade: a mesma garantia, através do fetch real
    (``window_closes``/``_fold_chunk``), não só da função pura já provada em
    ``packages/indicators``."""

    async def test_uma_vela_que_abre_no_corte_e_uma_mais_velha_que_a_janela_nao_entram(
        self, db_session_factory: Any
    ) -> None:
        """``POISONED`` sobe de verdade (``first=100``, ``last=101``, dentro da
        janela). Duas velas extras existem no banco e não deveriam contar: uma
        que **abre exatamente no corte** (fecha depois dele — ``open_time + 1min
        > CUT``) valendo 1 (quedaço, se entrasse), e uma **um minuto mais velha
        que a janela** (``WINDOW[0] - 1min``) valendo 100000 (alta absurda, se
        entrasse). Se qualquer uma delas entrasse na leitura pela via real do
        banco, ``CLEAN`` deixaria de ser a única contando e o valor mudaria."""
        exchange = "binance-lookahead"
        poisoned_id = await _seed_market(db_session_factory, exchange, "POISONEDUSDT")
        clean_id = await _seed_market(db_session_factory, exchange, "CLEANUSDT")

        rising = _full_window(first=Decimal("100"), last=Decimal("101"))
        await _seed_candles(db_session_factory, poisoned_id, rising)
        await _seed_candles(db_session_factory, poisoned_id, {CUT: Decimal("1")})
        await _seed_candles(
            db_session_factory, poisoned_id, {WINDOW[0] - MINUTE: Decimal("100000")}
        )
        await _seed_candles(db_session_factory, clean_id, rising)

        await run_breadth_once(db_session_factory, exchange=exchange, cut=CUT, back=0)

        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.universe_size == 2
        assert row.covered == 2
        assert row.falling == 0
        assert row.value == Decimal("0.0000")


class TestOTrancaDoRedis:
    """Item 5 do brief: dois produtores concorrentes do mesmo minuto."""

    async def test_dois_produtores_do_mesmo_minuto_escrevem_uma_linha_so(
        self, db_session_factory: Any, redis_client: redis_asyncio.Redis
    ) -> None:
        """A mesma forma que ``test_regime_job.py::
        test_two_producers_of_the_same_cut_write_one_row_per_hour`` prova para a
        hora: o ganho de ``claim_minute`` é quem chega a chamar
        ``run_breadth_once``; quem perde nunca chama e devolve o rótulo que o
        chamador real (``breadth_loop``) usaria para pular."""
        exchange = "binance-lock"
        market_id = await _seed_market(db_session_factory, exchange, "LUSDT")
        await _seed_candles(
            db_session_factory, market_id, _full_window(first=Decimal("100"), last=Decimal("90"))
        )

        async def producer() -> str:
            if not await claim_minute(redis_client, exchange, CUT):
                return "skipped"
            await run_breadth_once(db_session_factory, exchange=exchange, cut=CUT, back=0)
            return "ran"

        outcomes = await asyncio.gather(producer(), producer())

        assert sorted(outcomes) == ["ran", "skipped"]
        rows = await _rows(db_session_factory, exchange)
        assert len(rows) == 1
        # The claim is not released: the same cut is refused until the TTL, a
        # later cut is a fresh key.
        assert await claim_minute(redis_client, exchange, CUT) is False
        assert await claim_minute(redis_client, exchange, CUT + MINUTE) is True


class TestUniversoSomentePerpetuo:
    """Item 6 do brief: T3.73 — mercados spot ficam de fora."""

    async def test_um_mercado_spot_nao_entra_no_universo_nem_na_conta(
        self, db_session_factory: Any
    ) -> None:
        """Quatro perpétuas sobem (não caem). Um mercado spot do mesmo par cai
        forte — se contasse, o universo passaria de 4 para 5 e o valor de
        ``0.0000`` para ``0.2000``."""
        exchange = "binance-spot"
        perp_ids = [await _seed_market(db_session_factory, exchange, f"P{i}USDT") for i in range(4)]
        spot_id = await _seed_market(
            db_session_factory, exchange, "SPOTUSDT", market_type=MarketType.SPOT
        )
        for market_id in perp_ids:
            await _seed_candles(
                db_session_factory,
                market_id,
                _full_window(first=Decimal("100"), last=Decimal("101")),
            )
        await _seed_candles(
            db_session_factory, spot_id, _full_window(first=Decimal("100"), last=Decimal("1"))
        )

        run = await run_breadth_once(db_session_factory, exchange=exchange, cut=CUT, back=0)

        assert run.universe_size == 4
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.universe_size == 4
        assert row.covered == 4
        assert row.falling == 0
        assert row.value == Decimal("0.0000")
