"""Uma versão que levanta não leva a barra inteira junto (revisão T3.26-risk, A3).

``handle_candle`` percorria ``due`` sem ``try``: a primeira versão que levantasse
— exatamente a forma que uma variante mal derivada toma, com parâmetros
congelados que ``param_int``/``AssumedCosts`` recusam a cada barra — abortava o
laço, então **nenhuma** versão depois dela era avaliada e a mensagem nunca era
confirmada. O ``run_consumer`` já tratava isso como "mensagem ilegível" e seguia,
mas a barra ficava sem ack e voltava para sempre, e a linha ``paper`` (agora a
primeira da lista, ``test_roster_order.py``) parava em silêncio.

Sem Docker: ``evaluate_slot``, ``load_market`` e a sessão são substituídos, porque
o que está sob teste é o laço, não o banco.

Run: ``uv run pytest services/strategy-worker/tests/test_consumer_isolation.py -q``
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire
from hunter_core.strategies.base import EvaluationState
from hunter_core.strategies.envelope import PURPOSE_PAPER, PURPOSE_RESEARCH_ONLY
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker import consumer as consumer_mod
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth, handle_candle
from hunter_strategy_worker.roster import ActiveVersion

pytestmark = pytest.mark.unit

BAR_CLOSE = datetime(2026, 9, 8, 12, 5, tzinfo=UTC)
"""Um fechamento de 5m — o timeframe do ``volume_anomaly_v1``, que é a estratégia
que todas as versões falsas abaixo carregam."""


def _version(version: str, *, purpose: str = PURPOSE_RESEARCH_ONLY) -> ActiveVersion:
    return ActiveVersion(
        id=uuid.uuid4(),
        strategy_key="momentum",
        version=version,
        params={"volume_mult": "4"},
        params_hash="0" * 64,
        strategy=VOLUME_ANOMALY_V1,
        code_ref=None,
        purpose=purpose,
    )


class _Evaluation:
    state = EvaluationState.NOT_TRIGGERED


def _payload(*, is_final: bool = True) -> dict[str, Any]:
    """The wire shape ``market.candles.closed`` actually carries — produced by
    ``to_wire`` from a real ``NormalizedCandle``, not hand-typed, so a field the
    model renames does not turn this file into a test of nothing."""
    return to_wire(
        NormalizedCandle(
            exchange="binance",
            symbol="BTCUSDT",
            market_type=MarketType.PERPETUAL,
            timeframe=Timeframe.M1,
            open_time=BAR_CLOSE - timedelta(minutes=1),
            close_time=BAR_CLOSE,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            volume=Decimal("10"),
            is_final=is_final,
        )
    )


class _Versions:
    def __init__(self, versions: list[ActiveVersion]) -> None:
        self._versions = versions

    async def get(self, _factory: Any) -> list[ActiveVersion]:
        return list(self._versions)


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """``handle_candle`` sem banco: mercado fixo e sessão de mentira."""
    evaluated: list[str] = []

    @asynccontextmanager
    async def _session(*_args: Any, **_kwargs: Any) -> AsyncGenerator[object]:
        yield object()

    async def _load_market(*_args: Any, **_kwargs: Any) -> Any:
        return object()

    async def _evaluate(*_args: Any, version: ActiveVersion, **_kwargs: Any) -> Any:
        evaluated.append(version.version)
        if version.version == "v10":
            raise ValueError("lookback_closes must be a whole number, got '-20.5'")
        return _Evaluation()

    async def _no_family_cache(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        # T3.74b: this suite is about per-*version* isolation, not the family
        # cache (covered by ``test_context_cache.py``) — the fake ``factory``
        # here (``object()``) has nothing for a real ``role_session`` to open.
        return {}

    monkeypatch.setattr(consumer_mod, "role_session", _session)
    monkeypatch.setattr(consumer_mod, "load_market", _load_market)
    monkeypatch.setattr(consumer_mod, "evaluate_slot", _evaluate)
    monkeypatch.setattr(consumer_mod, "load_family_readers", _no_family_cache)

    def _due(versions: list[ActiveVersion], _bar: datetime) -> list[ActiveVersion]:
        return versions

    monkeypatch.setattr(consumer_mod, "versions_for_bar", _due)
    return evaluated


async def _run(
    versions: list[ActiveVersion], health: ConsumerHealth, payload: dict[str, Any] | None = None
) -> None:
    await handle_candle(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        payload=_payload() if payload is None else payload,
        versions=_Versions(versions),  # type: ignore[arg-type]
        config=ShadowConfig(),
        health=health,
        # BAR_CLOSE is a fixed past date; without this the real clock (T3.74c's
        # new bar-level backlog valve, ShadowConfig.late_delay_backlog_max_s)
        # would see this bar as ~2 years late and skip it before the loop this
        # suite actually tests ever runs.
        clock=lambda: BAR_CLOSE + timedelta(seconds=2),
    )


class TestOneVersionFailing:
    async def test_the_versions_after_it_are_still_evaluated(self, wired: list[str]) -> None:
        health = ConsumerHealth()
        await _run([_version("v10"), _version("v3", purpose=PURPOSE_PAPER), _version("v4")], health)
        assert wired == ["v10", "v3", "v4"]
        assert health.evaluated_bars == 2

    async def test_the_bar_is_still_processed_so_the_message_can_be_acked(
        self, wired: list[str]
    ) -> None:
        """``handle_candle`` volta normalmente: é o retorno sem exceção que faz
        ``run_consumer`` chamar ``ack``. Levantar aqui deixaria a mensagem para
        sempre pendente no grupo."""
        health = ConsumerHealth()
        await _run([_version("v10")], health)  # a única versão da barra falha
        assert wired == ["v10"]
        assert health.errors == 1

    async def test_the_failure_is_counted_by_strategy_and_version(self, wired: list[str]) -> None:
        before = _failed_count("momentum", "v10")
        await _run([_version("v10"), _version("v4")], health := ConsumerHealth())
        assert _failed_count("momentum", "v10") == before + 1
        assert _failed_count("momentum", "v4") == 0
        assert health.errors == 1

    async def test_a_healthy_roster_counts_nothing(self, wired: list[str]) -> None:
        health = ConsumerHealth()
        await _run([_version("v3", purpose=PURPOSE_PAPER), _version("v4")], health)
        assert health.errors == 0
        assert health.evaluated_bars == 2
        assert _failed_count("momentum", "v3") == 0


def _failed_count(strategy_key: str, version: str) -> float:
    from hunter_core.observability import registry

    value = registry.get_sample_value(
        "hunter_shadow_version_failed_total",
        {"strategy_key": strategy_key, "version": version},
    )
    return 0.0 if value is None else value


async def test_a_non_final_candle_never_reaches_the_loop(wired: list[str]) -> None:
    """Continua valendo o contrato de sempre (sem look-ahead): uma vela que ainda
    não fechou não é avaliada por versão nenhuma, quebrada ou não."""
    health = ConsumerHealth()
    await _run([_version("v4")], health, payload=_payload(is_final=False))
    assert wired == []
    assert health.evaluated_bars == 0


class TestRedisTimeoutIsNotACodeBug:
    """T3.83: a ``redis.exceptions.TimeoutError`` mid-evaluation is a transient
    infra failure, not a broken version — swallowing it the same way as a
    ``ValueError`` (Astra's T3.26 fix) would silently drop a decision for that
    market/version forever, since the message still gets acked either way. It
    must instead propagate out of ``handle_candle`` so the whole bar is left
    un-acked and redelivered once Redis recovers (idempotent per the module's
    own docstring: the slot barrier has already moved past a version that did
    commit)."""

    async def test_it_propagates_instead_of_being_swallowed(
        self, wired: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from redis.exceptions import TimeoutError as RedisTimeoutError

        async def _evaluate(*_args: Any, version: ActiveVersion, **_kwargs: Any) -> Any:
            wired.append(version.version)
            if version.version == "v10":
                raise RedisTimeoutError("Timeout reading from redis:6379")
            return _Evaluation()

        monkeypatch.setattr(consumer_mod, "evaluate_slot", _evaluate)
        health = ConsumerHealth()
        with pytest.raises(RedisTimeoutError):
            await _run([_version("v10"), _version("v4")], health)
        # the version after the timeout never ran this attempt — it will on
        # the redelivery the un-acked message now gets.
        assert wired == ["v10"]

    async def test_it_is_not_counted_as_a_version_failure(
        self, wired: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from redis.exceptions import TimeoutError as RedisTimeoutError

        async def _evaluate(*_args: Any, version: ActiveVersion, **_kwargs: Any) -> Any:
            raise RedisTimeoutError("Timeout reading from redis:6379")

        monkeypatch.setattr(consumer_mod, "evaluate_slot", _evaluate)
        before = _failed_count("momentum", "v10")
        with pytest.raises(RedisTimeoutError):
            await _run([_version("v10")], ConsumerHealth())
        assert _failed_count("momentum", "v10") == before

    async def test_it_is_counted_as_a_redis_timeout(
        self, wired: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from redis.exceptions import TimeoutError as RedisTimeoutError

        from hunter_core.observability import registry

        async def _evaluate(*_args: Any, version: ActiveVersion, **_kwargs: Any) -> Any:
            raise RedisTimeoutError("Timeout reading from redis:6379")

        monkeypatch.setattr(consumer_mod, "evaluate_slot", _evaluate)
        before = registry.get_sample_value(
            "hunter_shadow_redis_timeouts_total", {"stage": "version_evaluate"}
        )
        with pytest.raises(RedisTimeoutError):
            await _run([_version("v10")], ConsumerHealth())
        after = registry.get_sample_value(
            "hunter_shadow_redis_timeouts_total", {"stage": "version_evaluate"}
        )
        assert (after or 0.0) == (before or 0.0) + 1
