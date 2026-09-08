"""A costura da passada de estresse: plano do cenário → walker de produção.

T3.36, sem banco. O que estes testes provam é a única coisa que o módulo de
estresse acrescenta ao caminho já provado do EXP-0004: **como um cenário vira
um `TrackingPlan`**. O que acontece depois é `walker.walk`, que a T3.19b já
prova, e é de propósito que ele é chamado aqui sem nenhum invólucro — um
cenário que precisasse de uma regra de saída própria estaria medindo a
diferença entre duas implementações.

A série é sintética e rotulada como tal, com uma barra desenhada para cada
cenário: a que só o stop apertado alcança, a que só o alvo curto alcança, a que
o alvo da base alcança e a que só o alvo longo alcança.

Números conferidos à mão (custo de 6 bps por lado na entrada e na saída, taxa
de 4 bps fora do preço), não copiados da saída do código:

    P_entry = 100 x 1,0006 = 100,0600      P_exit = 103 x 0,9994 = 102,9382
    R_base  = (102,9382 - 100,06 - 0,0004x100,06 - 0,0004x102,9382) / 2,06
            = 1,357767...
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import MarketStatus, OutcomeResult, ShadowTrackingState
from hunter_core.strategies.envelope import AssumedCosts
from hunter_indicators.replay.stress import BASE, scenario
from hunter_strategy_worker.pricing import r_net
from hunter_strategy_worker.replay.load import ReplayCase, StoredOutcome, VersionRow
from hunter_strategy_worker.replay.stress import _delayed, _plan_for
from hunter_strategy_worker.repo import MarketRow
from hunter_strategy_worker.walker import Bar, Progress, TrackingPlan, walk

pytestmark = pytest.mark.unit

ENTRY_OPEN = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=120
)
"""A hipótese congelada do Lab (SHADOW-LAB.md §3) — dado de teste."""

PLAN = TrackingPlan(
    entry_bar_open=ENTRY_OPEN,
    stop=Decimal(98),
    target1=Decimal(103),
    horizon_s=4 * 3600,
    costs=COSTS,
    reference_price=Decimal(100),
    invalidation_level=None,
    invalidation_timeframe=None,
)

BARS = (
    Bar(ENTRY_OPEN, Decimal(100), Decimal("100.5"), Decimal("99.95"), Decimal("100.4")),
    Bar(
        ENTRY_OPEN + MINUTE, Decimal("100.4"), Decimal("102.4"), Decimal("98.45"), Decimal("102.3")
    ),
    Bar(
        ENTRY_OPEN + 2 * MINUTE,
        Decimal("102.3"),
        Decimal("103.2"),
        Decimal("102.2"),
        Decimal("103.1"),
    ),
    Bar(
        ENTRY_OPEN + 3 * MINUTE,
        Decimal("103.1"),
        Decimal("104.0"),
        Decimal("103.0"),
        Decimal("103.9"),
    ),
)
"""Barra 1 desce a 98,45 (só o stop apertado alcança) e sobe a 102,4 (só o alvo
curto alcança); a barra 2 toca 103 (o alvo da base); a barra 3 toca 104 (só o
alvo longo)."""


def case() -> ReplayCase:
    """Uma entrada congelada mínima — só o que o estresse lê dela."""
    return ReplayCase(
        signal_id=uuid.uuid5(uuid.NAMESPACE_URL, "stress-test"),
        version=VersionRow(
            id=uuid.uuid4(),
            strategy_key="momentum",
            version="v2",
            params_hash="deadbeef",
            params_format=1,
            code_ref="test",
            activated_at=ENTRY_OPEN,
        ),
        market=MarketRow(
            id=uuid.uuid4(),
            symbol="AAAUSDT",
            exchange="binance",
            is_monitored=True,
            status=MarketStatus.ACTIVE,
        ),
        source_bar_close=ENTRY_OPEN - MINUTE,
        plan=PLAN,
        targets=(Decimal(103),),
        atr0=Decimal(2),
        stored=StoredOutcome(
            tracking_state=ShadowTrackingState.TERMINAL,
            result=OutcomeResult.TARGET,
            virtual_entry=Decimal("100.06"),
            entry_ts=ENTRY_OPEN,
            exit_price=Decimal("102.9382"),
            exit_ts=ENTRY_OPEN + 2 * MINUTE,
            r_multiple=Decimal("1.357767"),
            r_ex_funding=Decimal("1.357767"),
            funding_reason=None,
            no_entry_reason=None,
            progress=Progress.start(),
        ),
    )


def fold(plan: TrackingPlan, bars: tuple[Bar, ...] = BARS) -> Progress:
    return walk(plan, Progress.start(), list(bars))


BASE_ENTRY = Decimal("100.0600")


def test_the_base_arm_reproduces_the_frozen_geometry_and_target() -> None:
    progress = fold(PLAN)
    assert progress.entry == BASE_ENTRY
    assert progress.result is OutcomeResult.TARGET
    assert progress.exit_base == Decimal(103)
    assert progress.exit_bar_open == ENTRY_OPEN + 2 * MINUTE
    value = r_net(
        entry=BASE_ENTRY,
        exit_=Decimal("102.9382"),
        stop=PLAN.stop,
        costs=COSTS,
        funding_per_unit=Decimal(0),
    )
    assert value.quantize(Decimal("0.000001")) == Decimal("1.357767")


def test_doubling_the_costs_moves_the_entry_and_costs_r() -> None:
    """Mesma barra de entrada, mesmo alvo: o que muda é o preço dos dois lados."""
    plan = _plan_for(case(), scenario("custos_x2"), BASE_ENTRY)
    assert plan.entry_bar_open == PLAN.entry_bar_open
    assert (plan.stop, plan.target1) == (PLAN.stop, PLAN.target1)
    progress = fold(plan)
    assert progress.entry == Decimal("100.1200")
    assert progress.result is OutcomeResult.TARGET
    value = r_net(
        entry=Decimal("100.1200"),
        exit_=Decimal("102.8764"),
        stop=plan.stop,
        costs=plan.costs,
        funding_per_unit=Decimal(0),
    )
    assert value.quantize(Decimal("0.000001")) == Decimal("1.223586")
    assert value < Decimal("1.357767"), "custo dobrado nunca melhora um resultado"


def test_a_tighter_stop_turns_the_same_trade_into_a_loss() -> None:
    """98,515 = 100,06 − 0,75 x 2,06 — a mínima de 98,45 da barra 1 alcança."""
    plan = _plan_for(case(), scenario("stop_x0.75"), BASE_ENTRY)
    assert plan.stop == Decimal("98.515000")
    progress = fold(plan)
    assert progress.result is OutcomeResult.STOP
    assert progress.exit_base == plan.stop
    assert progress.exit_bar_open == ENTRY_OPEN + MINUTE


def test_a_wider_stop_keeps_the_target_and_only_widens_the_risk() -> None:
    plan = _plan_for(case(), scenario("stop_x1.25"), BASE_ENTRY)
    assert plan.stop == Decimal("97.485000")
    progress = fold(plan)
    assert progress.result is OutcomeResult.TARGET
    assert progress.exit_bar_open == ENTRY_OPEN + 2 * MINUTE


def test_a_nearer_target_is_reached_one_bar_earlier() -> None:
    plan = _plan_for(case(), scenario("alvo_x0.75"), BASE_ENTRY)
    assert plan.target1 == Decimal("102.265000")
    progress = fold(plan)
    assert progress.result is OutcomeResult.TARGET
    assert progress.exit_bar_open == ENTRY_OPEN + MINUTE


def test_a_farther_target_needs_one_more_bar() -> None:
    plan = _plan_for(case(), scenario("alvo_x1.25"), BASE_ENTRY)
    assert plan.target1 == Decimal("103.735000")
    progress = fold(plan)
    assert progress.result is OutcomeResult.TARGET
    assert progress.exit_bar_open == ENTRY_OPEN + 3 * MINUTE


def test_the_entry_delay_moves_the_bar_and_the_horizon_together() -> None:
    """O único cenário que não é reprecificação: a entrada é outra barra."""
    spec = scenario("entrada_mais_1_barra")
    delayed = _delayed(case(), spec)
    assert delayed.plan.entry_bar_open == ENTRY_OPEN + MINUTE
    assert delayed.plan.horizon_open == PLAN.horizon_open + MINUTE
    progress = fold(_plan_for(case(), spec, BASE_ENTRY), BARS[1:])
    assert progress.entry == Decimal("100.46024")
    assert progress.result is OutcomeResult.TARGET
    value = r_net(
        entry=Decimal("100.46024"),
        exit_=Decimal("102.9382"),
        stop=PLAN.stop,
        costs=COSTS,
        funding_per_unit=Decimal(0),
    )
    assert value.quantize(Decimal("0.000001")) == Decimal("0.974133")


def test_no_scenario_touches_what_the_record_froze() -> None:
    """Custos, stop e alvo mudam; a barra de entrada, o horizonte e a
    invalidação da base não — e o registro congelado nunca é reescrito."""
    original = case()
    for spec in (scenario(BASE), scenario("custos_x2"), scenario("alvo_x1.25")):
        plan = _plan_for(original, spec, BASE_ENTRY)
        assert plan.entry_bar_open == PLAN.entry_bar_open
        assert plan.horizon_s == PLAN.horizon_s
        assert plan.invalidation_level == PLAN.invalidation_level
        assert plan.reference_price == PLAN.reference_price
    assert original.plan == PLAN


def test_a_candle_after_the_exit_cannot_change_a_stressed_outcome() -> None:
    """Anti-look-ahead do lado do desfecho: o que vem depois da saída não entra.

    A barra 3 (que sobe a 104) é acrescentada e depois **alterada**; o braço da
    base sai no alvo da barra 2 nos dois casos, com o mesmo preço e o mesmo
    instante. É a contrapartida, no desfecho, da regra que a decisão já obedece
    (contexto cortado em ``source_bar_close``, só velas ``is_final``).
    """
    tampered = (
        *BARS[:3],
        Bar(
            ENTRY_OPEN + 3 * MINUTE,
            Decimal("103.1"),
            Decimal("999.0"),
            Decimal("1.0"),
            Decimal("500.0"),
        ),
    )
    assert fold(PLAN, BARS) == fold(PLAN, tampered)
