"""A costura do eixo: `ArmOutcome` → `StressOutcome` → recibo — T3.75.

O par puro deste arquivo é `packages/indicators/tests/unit/test_replay_stress_axis.py`,
que prova a aritmética. Aqui se prova a **tradução**: quais motivos do
`settle()` viram queda de eixo, quais continuam descarte, e que o recibo diz o
eixo em vez de publicar uma expectancy silenciosamente medida noutra régua.

Sem banco: `_as_outcome` é uma função sobre um `ArmOutcome` já folheado, e
`StressRun.render()`/`to_jsonable()` não leem nada.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_core.domain.enums import MarketStatus, OutcomeResult, ShadowTrackingState
from hunter_core.strategies.envelope import AssumedCosts
from hunter_indicators.replay.stats import ContrastResult
from hunter_indicators.replay.stress import (
    BASE,
    REWALK_SCENARIOS,
    StressAxis,
    StressFamily,
    StressKind,
)
from hunter_indicators.replay.stress_table import StressOutcome, aggregate, stress_verdict
from hunter_strategy_worker.replay.engine import ArmOutcome
from hunter_strategy_worker.replay.load import ReplayCase, StoredOutcome, VersionRow
from hunter_strategy_worker.replay.stress import _as_outcome  # pyright: ignore[reportPrivateUsage]
from hunter_strategy_worker.replay.stress_report import StressRun, deltas
from hunter_strategy_worker.repo import MarketRow
from hunter_strategy_worker.walker import Progress, TrackingPlan

# ``_as_outcome`` é privada de propósito (o módulo publica a passada, não a
# costura); testá-la pela API pública exigiria banco e esconderia justamente a
# precedência de motivos que estes casos existem para fixar.
pytestmark = pytest.mark.unit

ENTRY_OPEN = datetime(2026, 6, 12, 8, 0, tzinfo=UTC)
COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=120
)


def case() -> ReplayCase:
    """A entrada congelada mínima que `_as_outcome` lê — dado de teste."""
    return ReplayCase(
        signal_id=uuid.uuid5(uuid.NAMESPACE_URL, "t375-axis"),
        version=VersionRow(
            id=uuid.uuid4(),
            strategy_key="mean_reversion",
            version="v10",
            params_hash="deadbeef",
            params_format=1,
            code_ref="test",
            activated_at=ENTRY_OPEN,
        ),
        market=MarketRow(
            id=uuid.uuid4(),
            symbol="ETHUSDT",
            exchange="binance",
            is_monitored=True,
            status=MarketStatus.ACTIVE,
        ),
        source_bar_close=ENTRY_OPEN,
        plan=TrackingPlan(
            entry_bar_open=ENTRY_OPEN,
            stop=Decimal(98),
            target1=Decimal(103),
            horizon_s=4 * 3600,
            costs=COSTS,
            reference_price=Decimal(100),
            invalidation_level=None,
            invalidation_timeframe=None,
        ),
        targets=(Decimal(103),),
        atr0=Decimal(2),
        stored=StoredOutcome(
            tracking_state=ShadowTrackingState.TERMINAL,
            result=OutcomeResult.TARGET,
            virtual_entry=Decimal("100.06"),
            entry_ts=ENTRY_OPEN,
            exit_price=Decimal("102.9382"),
            exit_ts=ENTRY_OPEN,
            r_multiple=None,
            r_ex_funding=Decimal("1.357767"),
            funding_reason="funding_schedule_unknown",
            no_entry_reason=None,
            progress=Progress.start(),
        ),
    )


def arm(
    *,
    r_net: str | None,
    r_ex_funding: str | None,
    funding_reason: str | None,
    state: ShadowTrackingState = ShadowTrackingState.TERMINAL,
    matured: bool = True,
) -> ArmOutcome:
    """Um braço já folheado — só os campos que `_as_outcome` consulta."""
    return ArmOutcome(
        signal_id=uuid.uuid5(uuid.NAMESPACE_URL, "t375-arm"),
        policy_key=BASE,
        tracking_state=state,
        result=OutcomeResult.TARGET,
        reason=None,
        entry=Decimal("100.06"),
        entry_ts=ENTRY_OPEN,
        exit_base=Decimal(103),
        exit_price=Decimal("102.9382"),
        exit_ts=ENTRY_OPEN,
        exit_at_open=True,
        exit_bar_open=ENTRY_OPEN,
        r_net=None if r_net is None else Decimal(r_net),
        r_ex_funding=None if r_ex_funding is None else Decimal(r_ex_funding),
        funding_reason=funding_reason,
        trigger=None,
        bars_folded=3,
        matured=matured,
    )


# ---- a tradução do motivo ---------------------------------------------------


def test_schedule_unknown_becomes_a_measured_row_on_r_ex_funding() -> None:
    """As 498 linhas da `v10` (T3.62b §3): entram na conta, no eixo declarado."""
    outcome = _as_outcome(
        case(),
        arm(r_net=None, r_ex_funding="1.357767", funding_reason="funding_schedule_unknown"),
    )

    assert outcome.dropped is None
    assert outcome.axis is StressAxis.R_EX_FUNDING
    assert outcome.r == Decimal("1.357767")


def test_an_ambiguous_exit_is_dropped_by_its_own_name_never_swapped_for_an_axis() -> None:
    """Ali a dúvida é da operação: o assentamento pode ou não ter sido pago."""
    outcome = _as_outcome(
        case(),
        arm(r_net=None, r_ex_funding="1.357767", funding_reason="funding_ambiguous_exit"),
    )

    assert outcome.dropped == "funding_ambiguous_exit"
    assert outcome.evaluable is False


def test_a_missing_settlement_keeps_its_prefix_and_stays_a_drop() -> None:
    """`funding_missing:<instante>` é truncado no prefixo, como todo descarte."""
    outcome = _as_outcome(
        case(),
        arm(
            r_net=None,
            r_ex_funding="1.0",
            funding_reason="funding_missing:2026-06-13T00:00:00+00:00",
        ),
    )

    assert outcome.dropped == "funding_missing"


def test_a_resolved_r_net_never_touches_the_fallback() -> None:
    outcome = _as_outcome(
        case(), arm(r_net="0.500000", r_ex_funding="0.501100", funding_reason=None)
    )

    assert outcome.axis is StressAxis.R_NET
    assert outcome.r == Decimal("0.500000")


def test_the_admission_reasons_still_win_over_the_axis() -> None:
    """Precedência intocada: não resolvido e horizonte imaturo vêm antes.

    Um braço que nem terminou não é "funding indeterminado", e um cuja janela
    não fechou até `as_of` continua fora da população pareada.
    """
    unresolved = _as_outcome(
        case(),
        arm(
            r_net=None,
            r_ex_funding="1.0",
            funding_reason="funding_schedule_unknown",
            state=ShadowTrackingState.ACTIVE,
        ),
    )
    immature = _as_outcome(
        case(),
        arm(
            r_net=None,
            r_ex_funding="1.0",
            funding_reason="funding_schedule_unknown",
            matured=False,
        ),
    )

    assert unresolved.dropped == "nao_resolvido"
    assert immature.dropped == "horizonte_imaturo"


def test_an_indeterminate_arm_without_r_ex_funding_is_named_not_silently_zero() -> None:
    outcome = _as_outcome(
        case(),
        arm(r_net=None, r_ex_funding=None, funding_reason="funding_schedule_unknown"),
    )

    assert outcome.dropped == "funding_schedule_unknown"
    assert outcome.evaluable is False


# ---- o recibo ---------------------------------------------------------------


def run_for(outcomes: list[StressOutcome]) -> StressRun:
    """Um recibo mínimo com uma linha `base` — o resto é rótulo de teste."""
    rows = (aggregate(BASE, outcomes, family=StressFamily.BASE, kind=StressKind.REWALK),)
    return StressRun(
        cohort="replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3",
        as_of=ENTRY_OPEN,
        generated_at=ENTRY_OPEN,
        versions=("mean_reversion v10",),
        markets=("binance:ETHUSDT",),
        rows=rows,
        deltas={},
        verdict=stress_verdict(list(rows)),
        cases=len(outcomes),
        input_digest="sha256:test",
        seed=1,
        resamples=10,
        limit=None,
        seconds=0.5,
    )


def blind(index: int, r: str) -> StressOutcome:
    return StressOutcome(
        signal_id=f"b{index}",
        market="binance:ETHUSDT",
        entry_day=ENTRY_OPEN.date(),
        result="target",
        r_net=None,
        r_ex_funding=Decimal(r),
        funding_indeterminate=True,
    )


def priced(index: int, r: str) -> StressOutcome:
    return StressOutcome(
        signal_id=f"p{index}",
        market="binance:ETHUSDT",
        entry_day=ENTRY_OPEN.date(),
        result="target",
        r_net=Decimal(r),
    )


def test_the_receipt_names_the_axis_and_the_count_it_rests_on() -> None:
    """A frase que o brief exige: `axis: r_ex_funding, funding_indeterminado: N`."""
    run = run_for([priced(1, "0.2"), blind(1, "0.1"), blind(2, "0.3")])

    rendered = run.render()
    payload = run.to_jsonable()

    assert "axis: r_ex_funding, funding_indeterminado: 2" in rendered
    assert payload["axis"] == "r_ex_funding"
    assert payload["funding_indeterminado"] == 2
    assert payload["rows"][0]["axis"] == "r_ex_funding"
    assert payload["rows"][0]["axis_r_ex_funding"] == 2


def test_a_receipt_with_no_fallback_declares_r_net_and_says_nothing_more() -> None:
    run = run_for([priced(1, "0.2"), priced(2, "-0.1")])

    assert "axis: r_net" in run.render()
    assert "funding_indeterminado" not in run.render()
    assert run.to_jsonable()["axis"] == "r_net"
    assert run.to_jsonable()["funding_indeterminado"] == 0


def test_the_paired_delta_uses_each_members_own_axis_instead_of_dropping_it() -> None:
    """Δ pareado por sinal sobre `r`, não sobre `r_net`.

    Conferido à mão: o cenário devolve 0,30 e a base 0,10 no mesmo sinal, os
    dois em `r_ex_funding` → Δ = +0,20 num único bloco de dia.
    """
    base = blind(1, "0.10")
    armed = blind(1, "0.30")
    key = next(spec.key for spec in REWALK_SCENARIOS if spec.key != BASE)

    result = deltas([{BASE: base, key: armed}], seed=1, resamples=64)[key]

    assert isinstance(result, ContrastResult)
    assert result.n_pairs == 1
    assert result.estimate == Decimal("0.20")
