"""Os quatro blocos e o veredito de replicação (`docs/plans/REPLICATION.md` §3 e §5).

Função pura: recebe as populações já carregadas e devolve o relatório completo.
Nenhum IO, nenhum relógio — quem lê o banco é
:mod:`hunter_strategy_worker.replication_stats`, e é por isso que este arquivo
pode ser testado com séries sintéticas de valor esperado conhecido.

Ordem fixa e parte do contrato — **1 → 2 → 3 → 4** — com uma nuance: os quatro
blocos são **sempre** calculados (o relatório é completo mesmo depois de uma
refutação), mas o veredito é ``refutada`` na primeira falha madura, e o motivo
nomeia o bloco. Imaturidade nunca refuta: ela adia.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hunter_indicators.replication.bootstrap import (
    BootstrapResult,
    SignTestResult,
    bootstrap_mean_ci,
    cluster_bootstrap_mean_ci,
    sign_test,
)
from hunter_indicators.replication.split import HalvesResult, split_by_market
from hunter_indicators.replication.stats import (
    MATURITY_HALF_DAYS,
    MATURITY_HALF_OUTCOMES,
    VERDICT_VALIDATED,
    Outcome,
    PopulationStats,
    after,
    scoreboard_verdict,
)

__all__ = [
    "SIBLINGS_N",
    "SIBLINGS_REQUIRED",
    "STATUS_NONE",
    "STATUS_PROMISING",
    "STATUS_REAL",
    "STATUS_REFUTED",
    "STATUS_REPLICATING",
    "Block",
    "ReplicationReport",
    "SiblingArm",
    "replication_report",
]

SIBLINGS_N = 10
"""``IRMAS_N`` — irmãs derivadas por rodada."""

SIBLINGS_REQUIRED = 7
"""``IRMAS_APROVADAS_MIN`` — maioria qualificada, não "alguma irmã sobreviveu"."""

STATUS_NONE = "none"
STATUS_PROMISING = "promissora"
STATUS_REPLICATING = "replicando"
STATUS_REAL = "real"
STATUS_REFUTED = "refutada"


@dataclass(frozen=True, slots=True)
class Block:
    """Um bloco do protocolo: passou, falhou ou ainda não tem amostra."""

    name: str
    passed: bool | None
    reason: str | None
    detail: dict[str, Any] = field(default_factory=lambda: {})

    def to_jsonable(self) -> dict[str, Any]:
        return {"passed": self.passed, "reason": self.reason, **self.detail}


@dataclass(frozen=True, slots=True)
class SiblingArm:
    """Uma irmã e a população que ela já produziu."""

    k: int
    version: str
    outcomes: Sequence[Outcome]

    def stats(self) -> PopulationStats:
        return PopulationStats.of(self.outcomes)


@dataclass(frozen=True, slots=True)
class ReplicationReport:
    """O bloco ``replication`` que o placar publica por versão (REPLICATION.md §6)."""

    status: str
    reason: str | None
    promising_at: datetime | None
    parent: PopulationStats
    parent_verdict: str
    out_of_sample: Block
    siblings: Block
    market_halves: Block
    bootstrap: Block

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "promising_at": None if self.promising_at is None else self.promising_at.isoformat(),
            "parent": {**self.parent.to_jsonable(), "verdict": self.parent_verdict},
            "out_of_sample": self.out_of_sample.to_jsonable(),
            "siblings": self.siblings.to_jsonable(),
            "market_halves": self.market_halves.to_jsonable(),
            "bootstrap": self.bootstrap.to_jsonable(),
        }


def _half_rule(stats: PopulationStats) -> bool:
    return stats.mature(outcomes=MATURITY_HALF_OUTCOMES, days=MATURITY_HALF_DAYS)


def _out_of_sample(outcomes: Sequence[Outcome], promising_at: datetime) -> Block:
    stats = PopulationStats.of(after(outcomes, promising_at))
    detail = {**stats.to_jsonable(), "mature": _half_rule(stats)}
    if not _half_rule(stats):
        missing = stats.shortfall(outcomes=MATURITY_HALF_OUTCOMES, days=MATURITY_HALF_DAYS)
        return Block("out_of_sample", None, f"imaturo: {missing}", detail)
    if not stats.positive():
        return Block("out_of_sample", False, "expectancy_nao_positiva", detail)
    return Block("out_of_sample", True, None, detail)


def _siblings(
    arms: Sequence[SiblingArm], *, required: int = SIBLINGS_REQUIRED, expected: int = SIBLINGS_N
) -> Block:
    rows: list[dict[str, Any]] = []
    positive = mature = 0
    for arm in sorted(arms, key=lambda item: item.k):
        stats = arm.stats()
        is_mature = _half_rule(stats)
        is_positive = is_mature and stats.positive()
        mature += int(is_mature)
        positive += int(is_positive)
        rows.append(
            {
                "k": arm.k,
                "version": arm.version,
                "mature": is_mature,
                "positive": is_positive,
                **stats.to_jsonable(),
            }
        )
    total = len(arms)
    detail: dict[str, Any] = {
        "n": total,
        "expected": expected,
        "required": required,
        "mature": mature,
        "positive": positive,
        "arms": rows,
    }
    if total == 0:
        return Block("siblings", None, "sem_irmas", detail)
    mature_negative = mature - positive
    if positive >= required:
        return Block("siblings", True, None, detail)
    # A maioria só é impossível quando nem todas as irmãs ainda indefinidas
    # bastariam: irmãs imaturas ainda podem virar positivas.
    if total - mature_negative < required:
        return Block("siblings", False, f"maioria_impossivel: {mature_negative} negativas", detail)
    return Block("siblings", None, f"imaturo: {positive} de {required} positivas", detail)


def _halves(outcomes: Sequence[Outcome]) -> Block:
    result: HalvesResult = split_by_market(outcomes)
    return Block("market_halves", result.passed, result.reason, result.to_jsonable())


def _bootstrap(outcomes: Sequence[Outcome], seed: int) -> Block:
    values = [outcome.r for outcome in outcomes]
    days = [outcome.day.isoformat() for outcome in outcomes]
    iid: BootstrapResult = bootstrap_mean_ci(values, seed=seed)
    clustered: BootstrapResult = cluster_bootstrap_mean_ci(values, days, seed=seed)
    signs: SignTestResult = sign_test(values)
    detail: dict[str, Any] = {
        **iid.to_jsonable(),
        "day_cluster": clustered.to_jsonable(),
        "sign_test": signs.to_jsonable(),
    }
    if not iid.ok:
        return Block("bootstrap", None, iid.refused_reason, detail)
    if iid.ci_high is not None and iid.ci_high < 0:
        return Block("bootstrap", False, "intervalo_negativo", detail)
    if not iid.excludes_zero:
        return Block("bootstrap", False, "intervalo_cruza_zero", detail)
    if not clustered.ok:
        return Block("bootstrap", None, clustered.refused_reason, detail)
    if not clustered.excludes_zero:
        return Block("bootstrap", None, "intervalo_por_dia_cruza_zero", detail)
    return Block("bootstrap", True, None, detail)


def replication_report(
    *,
    parent_outcomes: Sequence[Outcome],
    promising_at: datetime | None,
    siblings: Sequence[SiblingArm] = (),
    seed: int,
    required: int = SIBLINGS_REQUIRED,
    expected: int = SIBLINGS_N,
) -> ReplicationReport:
    """O relatório completo de uma versão pai, com o veredito do §5."""
    parent = PopulationStats.of(parent_outcomes)
    verdict = scoreboard_verdict(parent)
    empty = Block("out_of_sample", None, "sem_promising_at", {})
    if promising_at is None:
        return ReplicationReport(
            status=STATUS_NONE,
            reason="a versão nunca foi validada pela régua do placar"
            if verdict != VERDICT_VALIDATED
            else "validada, mas promising_at ainda não foi gravado",
            promising_at=None,
            parent=parent,
            parent_verdict=verdict,
            out_of_sample=empty,
            siblings=_siblings(siblings, required=required, expected=expected),
            market_halves=_halves(parent_outcomes),
            bootstrap=_bootstrap(parent_outcomes, seed),
        )
    blocks = (
        _out_of_sample(parent_outcomes, promising_at),
        _siblings(siblings, required=required, expected=expected),
        _halves(parent_outcomes),
        _bootstrap(parent_outcomes, seed),
    )
    status, reason = _status(blocks, has_siblings=bool(siblings))
    return ReplicationReport(
        status=status,
        reason=reason,
        promising_at=promising_at,
        parent=parent,
        parent_verdict=verdict,
        out_of_sample=blocks[0],
        siblings=blocks[1],
        market_halves=blocks[2],
        bootstrap=blocks[3],
    )


def _status(blocks: Sequence[Block], *, has_siblings: bool) -> tuple[str, str | None]:
    for block in blocks:
        if block.passed is False:
            return STATUS_REFUTED, f"{block.name}: {block.reason}"
    if not has_siblings:
        return STATUS_PROMISING, "irmãs ainda não foram criadas"
    pending = [block.name for block in blocks if block.passed is None]
    if pending:
        return STATUS_REPLICATING, "blocos imaturos: " + ", ".join(pending)
    return STATUS_REAL, None
