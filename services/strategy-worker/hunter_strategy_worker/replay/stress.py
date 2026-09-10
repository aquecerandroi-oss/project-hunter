"""A passada de estresse sobre uma coorte de replay — T3.36.

    uv run python -m hunter_strategy_worker.replay.stress \
        --cohort replay:<uuid> [--as-of ISO] [--ledger stress.jsonl] [--limit N]

    uv run python -m hunter_strategy_worker.replay.run --stress replay:<uuid> ...

O replay já respondeu "o que teria acontecido". Esta passada responde "o que
teria acontecido se o mundo fosse pior", e é o passo do funil que vem **depois**
do replay e antes do prospectivo (``docs/plans/SHADOW-LAB.md``, funil de
validação).

**As entradas são congeladas.** Nada aqui chama a estratégia: os sinais da
coorte já existem, com a barra de entrada, os níveis e o envelope que foram
gravados. O que muda é o desfecho — os mesmos minutos folheados de novo com
custo dobrado, stop mais curto ou mais longo, alvo mais perto ou mais longe. O
único cenário em que reprecificar é impossível é o **atraso de entrada**: mover
a entrada uma barra à frente muda a barra, e o desfecho tem de ser recaminhado
do zero (o brief pede que isso seja dito, não escondido). Os dois últimos
blocos — deixar um mercado de fora e cortar a janela ao meio — não recalculam
nada: reagregam os desfechos da base.

**Não existe um segundo modelo de saída.** Cada braço é o walker de produção
(:func:`hunter_strategy_worker.walker.walk`) e a liquidação de produção
(:func:`hunter_strategy_worker.settle.settle`), montados pelo mesmo
:func:`~hunter_strategy_worker.replay.engine.replay_arm` do EXP-0004. Um cenário
com regra de saída própria estaria medindo a diferença entre duas
implementações, não entre dois mundos.

**A passada não escreve no Lab.** A sessão é ``READ ONLY`` no Postgres
(:func:`~hunter_strategy_worker.replay.load.read_only_session`), e o recibo sai
num JSONL ao lado da coorte: ``replay_runs`` (``0013_replay_runs``) tem
``CHECK (cohort = 'replay:' || run_id)`` e nenhuma coluna ``kind``, então uma
linha de estresse não é representável lá hoje. O pedido de coluna está em
``.claude/state/brief-T3.36-db-replay-runs-kind.md``; migração é da
database-architect, nunca desta passada.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.db.session import create_engine, create_session_factory
from hunter_core.domain.enums import ShadowTrackingState
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_core.settings import Settings
from hunter_indicators.replay.policies import BASE as BASE_POLICY
from hunter_indicators.replay.policies import policy
from hunter_indicators.replay.stress import (
    BASE,
    REWALK_SCENARIOS,
    StressKind,
    StressScenario,
    stressed_costs,
    stressed_levels,
)
from hunter_indicators.replay.stress_table import (
    StressOutcome,
    aggregate,
    halves,
    leave_one_out,
    stress_verdict,
)
from hunter_strategy_worker.pricing import entry_price
from hunter_strategy_worker.replay.arms import ArmSpec
from hunter_strategy_worker.replay.engine import replay_arm
from hunter_strategy_worker.replay.load import (
    ReplayCase,
    input_digest,
    load_cases,
    load_manifest,
    read_only_session,
)
from hunter_strategy_worker.replay.series import load_series
from hunter_strategy_worker.replay.stress_report import StressRun, append_jsonl, deltas

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_strategy_worker.replay.engine import ArmOutcome
    from hunter_strategy_worker.walker import TrackingPlan

logger = get_logger(__name__)

__all__ = ["cohort_cases", "main", "run_cli", "run_stress", "stress_case"]

MINUTE = timedelta(minutes=1)
_INDETERMINATE_SCHEDULE = "funding_schedule_unknown"
"""Vocabulário congelado de ``hunter_strategy_worker.funding``; ver
:class:`~hunter_indicators.replay.stress.StressAxis` para por que só ele cai."""
DEFAULT_SEED = 20260908
DEFAULT_RESAMPLES = 1000
"""``BOOTSTRAP_REAMOSTRAS`` da REPLICATION.md §3.4 — a mesma máquina, o mesmo
número de reamostras, para que o Δ desta tabela seja lido com a mesma régua."""

_COHORT_INDEX = text(
    "SELECT a.id AS signal_id, s.key AS strategy_key "
    "FROM agent_signals a "
    "JOIN strategy_versions v ON v.id = a.strategy_version_id "
    "JOIN strategies s ON s.id = v.strategy_id "
    "WHERE a.supporting_features->>'cohort' = :cohort"
)
"""A coorte vive no envelope imutável da decisão, que é onde ``count_population``
já a lê (``replay/simulate.py``): a linha de ``replay_runs`` diz que a corrida
existiu, não quais sinais ela produziu."""


async def cohort_cases(session: AsyncSession, *, cohort: str, as_of: datetime) -> list[ReplayCase]:
    """As entradas congeladas de ``cohort``, ordenadas por ``signal_id``."""
    rows = (await session.execute(_COHORT_INDEX, {"cohort": cohort})).all()
    if not rows:
        return []
    signal_ids = {row.signal_id for row in rows}
    keys = sorted({str(row.strategy_key) for row in rows})
    versions = await load_manifest(session, keys=keys)
    cases = await load_cases(session, versions=versions, as_of=as_of)
    return [case for case in cases if case.signal_id in signal_ids]


def _plan_for(case: ReplayCase, spec: StressScenario, entry: Decimal) -> TrackingPlan:
    """O plano do cenário: custos, níveis e barra de entrada, nada mais."""
    costs = stressed_costs(case.plan.costs, spec)
    stop, target1 = stressed_levels(
        entry=entry, stop=case.plan.stop, target1=case.plan.target1, spec=spec
    )
    return replace(
        case.plan,
        costs=costs,
        stop=stop,
        target1=target1,
        entry_bar_open=case.plan.entry_bar_open + MINUTE * spec.entry_delay_bars,
    )


def _as_outcome(case: ReplayCase, arm: ArmOutcome, *, dropped: str | None = None) -> StressOutcome:
    """Um braço já folheado, no vocabulário da tabela de estresse.

    Precedência intocada — não resolvido, horizonte imaturo — e só então o
    funding. **T3.75:** ``funding_schedule_unknown`` deixa de ser descarte e
    passa a ser medido em ``r_ex_funding``; todo outro motivo continua descarte,
    nomeado pelo prefixo, porque ali a dúvida é sobre *aquela* operação.
    """
    reason = dropped
    if reason is None and arm.tracking_state is not ShadowTrackingState.TERMINAL:
        reason = (arm.reason or "nao_resolvido").split(":", 1)[0]
    if reason is None and not arm.matured:
        reason = "horizonte_imaturo"
    indeterminate = arm.r_net is None and arm.funding_reason == _INDETERMINATE_SCHEDULE
    fallback = indeterminate and arm.r_ex_funding is not None
    if reason is None and arm.r_net is None and not fallback:
        reason = (arm.funding_reason or "funding_indeterminado").split(":", 1)[0]
    return StressOutcome(
        signal_id=str(case.signal_id),
        market=f"{case.market.exchange}:{case.market.symbol}",
        entry_day=ensure_utc(case.plan.entry_bar_open).date(),
        result=None if arm.result is None else arm.result.value,
        r_net=arm.r_net,
        dropped=reason,
        r_ex_funding=arm.r_ex_funding,
        funding_indeterminate=indeterminate,
    )


def _refused(case: ReplayCase, reason: str) -> StressOutcome:
    return StressOutcome(
        signal_id=str(case.signal_id),
        market=f"{case.market.exchange}:{case.market.symbol}",
        entry_day=ensure_utc(case.plan.entry_bar_open).date(),
        result=None,
        r_net=None,
        dropped=reason,
    )


async def stress_case(
    session: AsyncSession,
    case: ReplayCase,
    *,
    as_of: datetime,
    specs: Sequence[StressScenario] = REWALK_SCENARIOS,
) -> dict[str, StressOutcome]:
    """Todos os cenários de reprecificação sobre uma entrada congelada.

    A admissão é da base, como no EXP-0004: se a base não entrou, não resolveu
    ou não amadureceu até ``as_of``, **nenhum** cenário conta aquele sinal —
    caso contrário um cenário mais rápido ficaria com as operações curtas e a
    tabela compararia populações diferentes.
    """
    outcomes: dict[str, StressOutcome] = {}
    series = await load_series(session, case, as_of=as_of)
    if not series.bars:
        reason = (series.truncated or "sem_barra_de_entrada").split(":", 1)[0]
        return {spec.key: _refused(case, reason) for spec in specs}
    entry = entry_price(series.bars[0].open, case.plan.costs)
    base_spec = next(spec for spec in specs if spec.key == BASE)
    base_arm = await replay_arm(
        session, case, ArmSpec(policy=policy(BASE_POLICY), plan=case.plan), series
    )
    outcomes[BASE] = _as_outcome(case, base_arm)
    if outcomes[BASE].dropped is not None:
        refusal = f"fora_da_base:{outcomes[BASE].dropped}"
        for spec in specs:
            if spec.key != base_spec.key:
                outcomes[spec.key] = _refused(case, refusal)
        return outcomes
    for spec in specs:
        if spec.key == BASE:
            continue
        arm_series = series
        if not spec.repriced:
            delayed = _delayed(case, spec)
            arm_series = await load_series(session, delayed, as_of=as_of)
            if not arm_series.bars:
                outcomes[spec.key] = _refused(
                    case, (arm_series.truncated or "sem_barra_de_entrada").split(":", 1)[0]
                )
                continue
        arm = await replay_arm(
            session,
            case,
            ArmSpec(policy=policy(BASE_POLICY), plan=_plan_for(case, spec, entry)),
            arm_series,
        )
        outcomes[spec.key] = _as_outcome(case, arm)
    return outcomes


def _delayed(case: ReplayCase, spec: StressScenario) -> ReplayCase:
    """A mesma entrada com a barra adiada — o horizonte anda junto com ela."""
    plan = replace(
        case.plan, entry_bar_open=case.plan.entry_bar_open + MINUTE * spec.entry_delay_bars
    )
    return replace(case, plan=plan)


async def run_stress(
    factory: async_sessionmaker[AsyncSession],
    *,
    cohort: str,
    as_of: datetime,
    seed: int = DEFAULT_SEED,
    resamples: int = DEFAULT_RESAMPLES,
    limit: int | None = None,
) -> StressRun:
    """A passada inteira sobre uma coorte. Lê; não escreve."""
    started = utcnow()
    async with read_only_session(factory) as session:
        cases = await cohort_cases(session, cohort=cohort, as_of=as_of)
        if limit is not None:
            cases = cases[:limit]
        per_case: list[Mapping[str, StressOutcome]] = []
        for index, case in enumerate(cases, start=1):
            per_case.append(await stress_case(session, case, as_of=as_of))
            if index % 25 == 0:
                logger.info("stress_progress", cohort=cohort, done=index, total=len(cases))
        digest = input_digest(cases)
    rows = [
        aggregate(
            spec.key,
            [case[spec.key] for case in per_case if spec.key in case],
            family=spec.family,
            kind=StressKind.REWALK,
        )
        for spec in REWALK_SCENARIOS
    ]
    base_outcomes = [case[BASE] for case in per_case if BASE in case]
    rows.extend(leave_one_out(base_outcomes))
    rows.extend(halves(base_outcomes))
    return StressRun(
        cohort=cohort,
        as_of=as_of,
        generated_at=utcnow(),
        versions=tuple(sorted({case.version.label for case in cases})),
        markets=tuple(sorted({o.market for o in base_outcomes})),
        rows=tuple(rows),
        deltas=deltas(per_case, seed=seed, resamples=resamples),
        verdict=stress_verdict(rows),
        cases=len(cases),
        input_digest=digest,
        seed=seed,
        resamples=resamples,
        limit=limit,
        seconds=(utcnow() - started).total_seconds(),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hunter_strategy_worker.replay.stress", description=__doc__
    )
    parser.add_argument("--cohort", required=True, help="replay:<uuid>")
    parser.add_argument("--as-of", default=None, help="corte de dados (UTC); padrão: agora")
    parser.add_argument("--ledger", default=None, help="JSONL onde o recibo é acrescentado")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument(
        "--limit", type=int, default=None, help="só para medir tempo; marca parcial"
    )
    parser.add_argument("--json", action="store_true", help="imprime o recibo em vez da tabela")
    return parser


async def run_cli(argv: list[str] | None = None) -> int:
    """A passada inteira a partir da linha de comando, já dentro de um loop."""
    args = _parser().parse_args(argv)
    cohort = str(args.cohort)
    uuid.UUID(cohort.split(":", 1)[-1])
    as_of = ensure_utc(datetime.fromisoformat(str(args.as_of))) if args.as_of else utcnow()
    engine = create_engine(Settings())
    try:
        run = await run_stress(
            create_session_factory(engine),
            cohort=cohort,
            as_of=as_of,
            seed=int(args.seed),
            resamples=int(args.resamples),
            limit=None if args.limit is None else int(args.limit),
        )
    finally:
        await engine.dispose()
    if args.ledger:
        append_jsonl(Path(str(args.ledger)), run)
    sys.stdout.write(
        (json.dumps(run.to_jsonable(), ensure_ascii=False) if args.json else run.render()) + "\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada de linha de comando; ``replay.run --stress`` chama
    :func:`run_cli` diretamente, porque já está dentro de um loop."""
    return asyncio.run(run_cli(argv))


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
