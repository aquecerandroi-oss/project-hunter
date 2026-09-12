"""``dispersion_24h``'s per-minute producer, against a real Postgres and Redis.

T3.90 / H-P18. The question of this file is the one ``test_breadth_job.py`` asks
for the amplitude: not "does the arithmetic work" — that is
``packages/indicators/tests/unit/test_dispersion_series.py``, where every number is
worked out by hand — but "does :func:`run_dispersion_once` write the row the gate
then reads", with the universe, the reference, the coverage floor, the idempotency
and the lock all resolved against a database instead of a fake.

Every expected number below is a literal, for the same reason: a test that asked
the function under review what it thinks the answer is would pass no matter what
the arithmetic did.

Each test seeds its own exchange (``binance-<tag>``), the same isolation
``test_breadth_job.py``/``test_regime_job.py`` use: the producer's reads all join
through ``exchanges.code``, so two tests never share a universe.

Run: ``uv run pytest services/scanner-worker/tests/test_dispersion_job.py -q``
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
from hunter_indicators.dispersion import REFERENCE_SYMBOL, current_spec, endpoint_open_times
from hunter_scanner_worker.dispersion import claim_minute
from hunter_scanner_worker.dispersion_job import minutes_due, run_dispersion_once

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

pytestmark = pytest.mark.integration

MINUTE = timedelta(minutes=1)
SPEC = current_spec()

CUT = datetime(2026, 12, 10, 12, 6, tzinfo=UTC)
"""The closed minute every test folds. Chosen so that all three instants that
matter fall inside partitions ``0001`` creates (2026-09 … 2026-12): the two
endpoints (2026-12-09 12:05 and 2026-12-10 12:05) and the history anchor
``CUT - 90 days`` = 2026-09-11 12:06 — the same reasoning
``test_breadth_job.py::V2_CUT`` states, since this series' universe is the same
one."""

OLD, NEW = endpoint_open_times(CUT, SPEC.horizon_minutes)
"""The two ``open_time``s the reading needs, resolved with the same function the
job imports, so a change to the pair's shape moves both sides of every test here."""

NINETY_DAYS_BEFORE_CUT = CUT - timedelta(days=SPEC.min_history_days)
"""The oldest candle that still qualifies a market for the universe (``<=``, the
inclusive boundary ``hunter_core.universe.has_min_history`` states)."""


async def _upsert_asset(session: Any, symbol: str) -> Any:
    """A copy of ``db_helpers._upsert_asset`` — that one is private to its module,
    and duplicating four lines beats importing another module's underscore-named
    helper (``reportPrivateUsage``). Same choice ``test_breadth_job.py`` made."""
    stmt = (
        pg_insert(Asset)
        .values(symbol=symbol)
        .on_conflict_do_update(index_elements=["symbol"], set_={"symbol": symbol})
        .returning(Asset.id)
    )
    return await session.scalar(stmt)


async def _upsert_exchange(session: Any, code: str) -> Any:
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
) -> UUID:
    async with role_session(factory, db_role="hunter_worker") as session:
        exchange_id = await _upsert_exchange(session, exchange)
        base_id = await _upsert_asset(session, "X")
        quote_id = await _upsert_asset(session, "USDT")
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
    written ``is_final = true``; everything else is written still printing — the
    shape a look-ahead bug turns into a complete pair."""
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


async def _member(
    factory: Any,
    exchange: str,
    symbol: str,
    *,
    old: str | None,
    new: str | None,
    history: bool = True,
    anchor: datetime | None = None,
) -> UUID:
    """One market of the series' universe: the history anchor that makes it
    eligible, plus whichever endpoint closes it is supposed to have.

    ``history=False`` seeds the anchor **one minute inside** the 90-day boundary, so
    the market is a monitored active perpetual with candles that the universe rule
    still refuses — the one difference the rule is about.
    """
    market_id = await _seed_market(factory, exchange, symbol)
    at = anchor or (NINETY_DAYS_BEFORE_CUT if history else NINETY_DAYS_BEFORE_CUT + MINUTE)
    closes = {at: Decimal("100")}
    if old is not None:
        closes[OLD] = Decimal(old)
    if new is not None:
        closes[NEW] = Decimal(new)
    await _seed_candles(factory, market_id, closes)
    return market_id


async def _row(factory: Any, exchange: str, *, end_time: datetime) -> Any:
    async with role_session(factory, db_role="hunter_worker") as session:
        return (
            await session.execute(
                text(
                    "SELECT d.* FROM market_dispersion d "
                    "  JOIN exchanges e ON e.id = d.exchange_id "
                    " WHERE e.code = :exchange AND d.end_time = :end_time"
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
                        "SELECT d.* FROM market_dispersion d "
                        "  JOIN exchanges e ON e.id = d.exchange_id "
                        " WHERE e.code = :exchange ORDER BY d.end_time"
                    ),
                    {"exchange": exchange},
                )
            ).all()
        )


async def _fold(factory: Any, exchange: str, *, back: int = 0) -> Any:
    """One pass, with membership judged at the cut itself: a test must not depend
    on the wall clock of the machine running it (the ``universe_as_of`` seam the
    backfill uses for the same reason)."""
    return await run_dispersion_once(
        factory, exchange=exchange, cut=CUT, back=back, spec=SPEC, universe_as_of=CUT
    )


class TestADiscordanciaDoPlantao:
    """Item 1 do brief: o número de 10/09, gravado com as quatro colunas."""

    async def test_a_leitura_grava_o_btc_a_mediana_a_dispersao_e_a_fracao(
        self, db_session_factory: Any
    ) -> None:
        """BTC -1,50 % (100 -> 98,5) e cinco alts entre -4,6 % e -5,0 %: mediana
        -4,80 %, dispersão **-0,033000**, todas as cinco abaixo do BTC."""
        exchange = "binance-plantao"
        await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old="100", new="98.5")
        for symbol, new in (
            ("AUSDT", "95.0"),
            ("BUSDT", "95.1"),
            ("CUSDT", "95.2"),
            ("DUSDT", "95.3"),
            ("EUSDT", "95.4"),
        ):
            await _member(db_session_factory, exchange, symbol, old="100", new=new)

        run = await _fold(db_session_factory, exchange)

        assert run.universe_size == 6
        assert run.reference_found is True
        assert run.written == 1
        assert run.outcomes["usable"] == 1
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.dispersion_version == "dispersion_24h_v1"
        assert row.horizon_minutes == 1_440
        assert row.universe_size == 6
        assert row.covered == 6
        assert row.alts_covered == 5
        assert row.alts_below_btc == 5
        assert row.btc_r24h == Decimal("-0.015000")
        assert row.median_alt_r24h == Decimal("-0.048000")
        assert row.dispersion == Decimal("-0.033000")
        assert row.share_below_btc == Decimal("1.0000")
        assert row.coverage == Decimal("1.0000")
        assert row.usable is True
        assert row.reason is None
        assert row.inputs["reference_symbol"] == REFERENCE_SYMBOL
        assert row.inputs["universe_rule"] == "monitored_perpetual_min_history_90d"
        # ``inputs`` passes through ``canonical_json`` (``params_format = 1``), which
        # emits every number as a normalised decimal **string** -- the same shape
        # ``market_breadth.inputs`` carries. Asserted as stored, not as wished for.
        assert row.inputs["horizon_minutes"] == "1440"
        assert row.inputs["min_coverage"] == "0.8"  # canonical form normalises 0.80
        assert row.inputs["universe_as_of"] == "2026-12-10T12:06:00Z"


class TestOUniversoDaSerie:
    """Item 1 do brief: a série dobra o universo sombra, e só ele."""

    async def test_um_mercado_sem_noventa_dias_fica_fora_e_nao_move_a_mediana(
        self, db_session_factory: Any
    ) -> None:
        """``YOUNG`` tem vela **um minuto depois** da fronteira dos 90 dias e cai
        -50 %: se entrasse, o universo iria a 4, a mediana de -0,020000 para
        -0,035000 e a dispersão de -0,010000 para -0,025000."""
        exchange = "binance-universe"
        await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old="100", new="99")
        await _member(db_session_factory, exchange, "AUSDT", old="100", new="98")
        await _member(db_session_factory, exchange, "BUSDT", old="100", new="98")
        await _member(db_session_factory, exchange, "YOUNGUSDT", old="100", new="50", history=False)

        run = await _fold(db_session_factory, exchange)

        assert run.universe_size == 3
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.universe_size == 3
        assert row.covered == 3
        assert row.median_alt_r24h == Decimal("-0.020000")
        assert row.dispersion == Decimal("-0.010000")

    async def test_um_mercado_spot_nao_entra_no_universo(self, db_session_factory: Any) -> None:
        """O mesmo par em spot cairia -50 %; ele não é perpétuo, então não existe
        para esta série (a mesma cláusula de ``hunter_core.universe``)."""
        exchange = "binance-spot"
        await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old="100", new="99")
        await _member(db_session_factory, exchange, "AUSDT", old="100", new="98")
        spot = await _seed_market(
            db_session_factory, exchange, "SPOTUSDT", market_type=MarketType.SPOT
        )
        await _seed_candles(
            db_session_factory,
            spot,
            {NINETY_DAYS_BEFORE_CUT: Decimal("100"), OLD: Decimal("100"), NEW: Decimal("50")},
        )

        run = await _fold(db_session_factory, exchange)

        assert run.universe_size == 2
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.median_alt_r24h == Decimal("-0.020000")


class TestAReferencia:
    """Sem BTC não há o que medir contra, e isso é uma linha, não um buraco."""

    async def test_sem_o_btc_no_universo_a_linha_sai_btc_missing(
        self, db_session_factory: Any
    ) -> None:
        """Quatro alts com cobertura perfeita e nenhum BTC: a cobertura **não** é o
        problema, e a palavra gravada diz qual é."""
        exchange = "binance-nobtc"
        for symbol in ("AUSDT", "BUSDT", "CUSDT", "DUSDT"):
            await _member(db_session_factory, exchange, symbol, old="100", new="98")

        run = await _fold(db_session_factory, exchange)

        assert run.reference_found is False
        assert run.outcomes["btc_missing"] == 1
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.coverage == Decimal("1.0000")
        assert row.usable is False
        assert row.reason == "btc_missing"
        assert row.dispersion is None
        assert row.btc_r24h is None
        assert row.median_alt_r24h is None
        assert row.share_below_btc is None
        assert row.alts_below_btc == 0

    async def test_o_btc_sem_uma_das_pontas_tambem_sai_btc_missing(
        self, db_session_factory: Any
    ) -> None:
        """O BTC está no universo e perdeu o fechamento de 24 h atrás."""
        exchange = "binance-btcgap"
        await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old=None, new="99")
        for symbol in ("AUSDT", "BUSDT", "CUSDT"):
            await _member(db_session_factory, exchange, symbol, old="100", new="98")

        run = await _fold(db_session_factory, exchange)

        assert run.reference_found is True  # it *is* in the universe
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.covered == 3
        assert row.reason == "btc_missing"


class TestCoberturaInsuficiente:
    """Item 4 do brief: abaixo do piso, a linha existe e diz por quê."""

    async def test_cobertura_abaixo_do_piso_grava_linha_sem_valor(
        self, db_session_factory: Any
    ) -> None:
        """Cinco de dez respondem (50 %, abaixo dos 80 %) — o BTC entre eles, para
        que a recusa seja a cobertura e não a referência."""
        exchange = "binance-lowcov"
        await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old="100", new="99")
        for symbol in ("AUSDT", "BUSDT", "CUSDT", "DUSDT"):
            await _member(db_session_factory, exchange, symbol, old="100", new="98")
        for index in range(5):
            await _member(db_session_factory, exchange, f"M{index}USDT", old=None, new=None)

        run = await _fold(db_session_factory, exchange)

        assert run.universe_size == 10
        assert run.outcomes["insufficient_coverage"] == 1
        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.covered == 5
        assert row.coverage == Decimal("0.5000")
        assert row.usable is False
        assert row.reason == "insufficient_coverage"
        assert row.dispersion is None

    async def test_exatamente_no_piso_a_leitura_vale(self, db_session_factory: Any) -> None:
        """4 de 5 = 0,8000, exatamente o piso: ``>=``, não ``>``."""
        exchange = "binance-floor"
        await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old="100", new="99")
        for symbol in ("AUSDT", "BUSDT", "CUSDT"):
            await _member(db_session_factory, exchange, symbol, old="100", new="97")
        await _member(db_session_factory, exchange, "MUTEUSDT", old=None, new=None)

        await _fold(db_session_factory, exchange)

        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert row.coverage == Decimal("0.8000")
        assert row.usable is True
        assert row.dispersion == Decimal("-0.020000")


class TestIdempotencia:
    """Item 4 do brief: a segunda passagem do mesmo minuto não escreve nada."""

    async def test_a_segunda_passagem_nao_insere_e_a_linha_fica_byte_a_byte_igual(
        self, db_session_factory: Any
    ) -> None:
        exchange = "binance-idem"
        await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old="100", new="99")
        for symbol in ("AUSDT", "BUSDT", "CUSDT"):
            await _member(db_session_factory, exchange, symbol, old="100", new="98")

        first = await _fold(db_session_factory, exchange)
        before = await _row(db_session_factory, exchange, end_time=CUT)
        assert before is not None
        second = await _fold(db_session_factory, exchange)
        after = await _row(db_session_factory, exchange, end_time=CUT)

        assert (first.due, first.written) == (1, 1)
        assert (second.due, second.written) == (0, 0)
        assert len(await _rows(db_session_factory, exchange)) == 1
        assert dict(after._mapping) == dict(before._mapping)  # not one column moved


class TestOLimiteDoMinutosDue:
    """A janela de ``back`` é exata, e um off-by-one faria isto falhar. Puro."""

    def test_o_corte_entra_sempre_que_nao_tem_linha_e_a_ponta_e_exata(self) -> None:
        due = minutes_due(CUT, back=5, known={CUT - 3 * MINUTE})
        assert due == [
            CUT - 5 * MINUTE,
            CUT - 4 * MINUTE,
            CUT - 2 * MINUTE,
            CUT - MINUTE,
            CUT,
        ]
        assert (CUT - 6 * MINUTE) not in due

    def test_um_minuto_ja_conhecido_no_proprio_corte_nao_e_devido_de_novo(self) -> None:
        assert minutes_due(CUT, back=0, known={CUT}) == []


class TestNaoAntecipacaoNoCaminhoDoProdutor:
    """Item 4 do brief, pela via real do banco e não só pela função pura."""

    async def test_uma_vela_um_minuto_atrasada_e_uma_fora_da_ponta_nao_entram(
        self, db_session_factory: Any
    ) -> None:
        """Três velas existem no banco e **nenhuma** delas pode contar: a que
        **abre no corte** (fecha um minuto depois dele) valendo 1, a que abre um
        minuto **depois** da ponta velha (``OLD + 1min``) valendo 1 e a que abre um
        minuto **antes** dela valendo 10 000. Se qualquer uma entrasse, a dispersão
        deixaria de ser -0,030000. A quarta armadilha é ``UNFINAL``: um mercado cuja
        vela da ponta nova ainda está imprimindo não é contado — e ele cairia -90 %
        se fosse, levando a mediana das alts de -0,040000 para -0,050000."""
        exchange = "binance-lookahead"
        poisoned = [
            await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old="100", new="99"),
            await _member(db_session_factory, exchange, "AUSDT", old="100", new="98"),
            await _member(db_session_factory, exchange, "BUSDT", old="100", new="96"),
            await _member(db_session_factory, exchange, "CUSDT", old="100", new="94"),
        ]
        for market_id in poisoned:
            await _seed_candles(
                db_session_factory,
                market_id,
                {
                    CUT: Decimal("1"),
                    OLD + MINUTE: Decimal("1"),
                    OLD - MINUTE: Decimal("10000"),
                },
            )
        unfinal = await _seed_market(db_session_factory, exchange, "UNFINALUSDT")
        await _seed_candles(
            db_session_factory,
            unfinal,
            {NINETY_DAYS_BEFORE_CUT: Decimal("100"), OLD: Decimal("100"), NEW: Decimal("10")},
            final={NINETY_DAYS_BEFORE_CUT, OLD},
        )

        run = await _fold(db_session_factory, exchange)

        row = await _row(db_session_factory, exchange, end_time=CUT)
        assert row is not None
        assert run.universe_size == 5
        assert row.covered == 4  # UNFINAL is not counted
        assert row.coverage == Decimal("0.8000")  # exactly the floor: the row is usable
        assert row.alts_covered == 3
        assert row.btc_r24h == Decimal("-0.010000")
        assert row.median_alt_r24h == Decimal("-0.040000")
        assert row.dispersion == Decimal("-0.030000")
        assert row.share_below_btc == Decimal("1.0000")
        assert row.usable is True

    async def test_virar_o_bit_de_final_da_ponta_nova_e_o_que_faz_o_minuto_existir(
        self, db_session_factory: Any
    ) -> None:
        """A mesma semente, duas vezes: com a vela da ponta nova do BTC ainda
        imprimindo não há leitura (``btc_missing``); com ela final, há. É o que
        prova que a leitura é função de ``is_final`` e não do relógio."""
        printing = "binance-printing"
        btc = await _seed_market(db_session_factory, printing, REFERENCE_SYMBOL)
        await _seed_candles(
            db_session_factory,
            btc,
            {NINETY_DAYS_BEFORE_CUT: Decimal("100"), OLD: Decimal("100"), NEW: Decimal("99")},
            final={NINETY_DAYS_BEFORE_CUT, OLD},
        )
        for symbol in ("AUSDT", "BUSDT", "CUSDT"):
            await _member(db_session_factory, printing, symbol, old="100", new="98")

        await _fold(db_session_factory, printing)
        row = await _row(db_session_factory, printing, end_time=CUT)
        assert row is not None
        assert row.reason == "btc_missing"

        final = "binance-final"
        await _member(db_session_factory, final, REFERENCE_SYMBOL, old="100", new="99")
        for symbol in ("AUSDT", "BUSDT", "CUSDT"):
            await _member(db_session_factory, final, symbol, old="100", new="98")

        await _fold(db_session_factory, final)
        healthy = await _row(db_session_factory, final, end_time=CUT)
        assert healthy is not None
        assert healthy.usable is True
        assert healthy.dispersion == Decimal("-0.010000")


class TestATrancaDoRedis:
    """Item 4 do brief: dois produtores concorrentes do mesmo minuto."""

    async def test_dois_produtores_do_mesmo_minuto_escrevem_uma_linha_so(
        self, db_session_factory: Any, redis_client: redis_asyncio.Redis
    ) -> None:
        """A forma de ``test_breadth_job.py``: o ganho de ``claim_minute`` é quem
        chega a chamar o fold; quem perde nunca chama e devolve o rótulo que
        ``dispersion_loop`` usaria para pular."""
        exchange = "binance-lock"
        await _member(db_session_factory, exchange, REFERENCE_SYMBOL, old="100", new="99")
        await _member(db_session_factory, exchange, "AUSDT", old="100", new="98")

        async def producer() -> str:
            if not await claim_minute(redis_client, exchange, CUT):
                return "skipped"
            await _fold(db_session_factory, exchange)
            return "ran"

        outcomes = await asyncio.gather(producer(), producer())

        assert sorted(outcomes) == ["ran", "skipped"]
        assert len(await _rows(db_session_factory, exchange)) == 1
        # The claim is not released: the same cut is refused until the TTL, a later
        # cut is a fresh key.
        assert await claim_minute(redis_client, exchange, CUT) is False
        assert await claim_minute(redis_client, exchange, CUT + MINUTE) is True
