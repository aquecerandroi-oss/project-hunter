"""O recibo da passada de estresse: a tabela, os Δ pareados e o JSONL.

Separado de :mod:`hunter_strategy_worker.replay.stress` pela mesma costura que
separa ``report.py`` de ``engine.py`` no EXP-0004: lá se decide *o que
aconteceu*, aqui se decide *como isso é publicado*. Nada aqui lê banco.

O recibo vai para um JSONL e **não** para ``replay_runs``: aquela tabela tem
``CHECK (cohort = 'replay:' || run_id::text)``, não tem coluna ``kind`` e o
papel ``hunter_worker`` só pode ``SELECT``/``INSERT`` nela — uma linha de
estresse não é representável hoje. O pedido de coluna está em
``.claude/state/brief-T3.36-db-replay-runs-kind.md``; migração é da
database-architect.

O Δ vs base é **pareado por sinal** e o intervalo vem de reamostrar **dias**
inteiros (``hunter_indicators.replay.stats``), não sinais: mercados simultâneos
são dependentes e rótulos de três barreiras se sobrepõem no tempo
(REPLICATION.md §3.4, [[KB-0051]]). Ele diz *de quanto* o cenário moveu o
resultado; o veredito continua sendo sobre o **sinal** da expectancy, que é a
pergunta do brief.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from hunter_core.domain.types import ensure_utc
from hunter_indicators.replay.stats import ContrastResult, Pair, contrast
from hunter_indicators.replay.stress import BASE, REWALK_SCENARIOS, STRESS_VERSION
from hunter_indicators.replay.stress_table import StressOutcome, StressRow, StressVerdict

__all__ = ["StressRun", "append_jsonl", "deltas"]


@dataclass(frozen=True, slots=True)
class StressRun:
    """A passada inteira: as linhas, os Δ pareados, o veredito e a cobertura."""

    cohort: str
    as_of: datetime
    generated_at: datetime
    versions: tuple[str, ...]
    markets: tuple[str, ...]
    rows: tuple[StressRow, ...]
    deltas: Mapping[str, ContrastResult]
    verdict: StressVerdict
    cases: int
    input_digest: str
    seed: int
    resamples: int
    limit: int | None
    seconds: float

    @property
    def partial(self) -> bool:
        """``--limit`` produz uma tabela **parcial**; ela nunca é publicada como
        a leitura da coorte."""
        return self.limit is not None

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "stress_version": STRESS_VERSION,
            "cohort": self.cohort,
            "as_of": ensure_utc(self.as_of).isoformat(),
            "generated_at": ensure_utc(self.generated_at).isoformat(),
            "versions": list(self.versions),
            "markets": list(self.markets),
            "cases": self.cases,
            "partial": self.partial,
            "limit": self.limit,
            "seed": self.seed,
            "resamples": self.resamples,
            "input_digest": self.input_digest,
            "seconds": round(self.seconds, 3),
            "verdict": self.verdict.verdict,
            "reasons": list(self.verdict.reasons),
            "rows": [_row_json(row, self.deltas.get(row.key)) for row in self.rows],
        }

    def render(self) -> str:
        """A tabela como ela vai para o relatório e para o EXP."""
        head = (
            f"coorte {self.cohort} · as_of {ensure_utc(self.as_of).isoformat()} · "
            f"{self.cases} entradas congeladas · {len(self.markets)} mercados"
            + (" · TABELA PARCIAL (--limit)" if self.partial else "")
        )
        lines = [
            head,
            "",
            "| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ | descartes |",
            "|---|---|---:|---:|---:|---:|---|---|",
        ]
        lines.extend(_render_row(row, self.deltas.get(row.key)) for row in self.rows)
        lines.append("")
        lines.append(f"**Veredito:** {self.verdict.verdict}")
        lines.extend(f"- {reason}" for reason in self.verdict.reasons)
        return "\n".join(lines)


def _num(value: Decimal | None, places: str = "0.0001") -> str:
    return "—" if value is None else format(value.quantize(Decimal(places)), "f")


def _row_json(row: StressRow, delta: ContrastResult | None) -> dict[str, Any]:
    metrics = row.metrics
    return {
        "key": row.key,
        "family": row.family.value,
        "kind": row.kind.value,
        "total": row.total,
        "n": row.n,
        "targets": metrics.targets,
        "stops": metrics.stops,
        "expectancy_r": None if metrics.expectancy_r is None else format(metrics.expectancy_r, "f"),
        "profit_factor": (
            None if metrics.profit_factor is None else format(metrics.profit_factor, "f")
        ),
        "profit_factor_reason": metrics.profit_factor_reason,
        "sum_r": None if metrics.sum_r is None else format(metrics.sum_r, "f"),
        "dropped": dict(row.dropped),
        "delta_vs_base": None
        if delta is None or delta.estimate is None
        else {
            "estimate": format(delta.estimate, "f"),
            "pairs": delta.n_pairs,
            "blocks": delta.blocks,
            "ci_low": delta.ci_low,
            "ci_high": delta.ci_high,
            "ci_reason": delta.ci_reason,
        },
    }


def _render_row(row: StressRow, delta: ContrastResult | None) -> str:
    pf = _num(row.profit_factor)
    if row.profit_factor is None and row.metrics.profit_factor_reason:
        pf = f"nulo ({row.metrics.profit_factor_reason})"
    if delta is None or delta.estimate is None:
        change, interval = "—", "—"
    else:
        change = _num(delta.estimate)
        interval = (
            f"[{delta.ci_low:+.4f}, {delta.ci_high:+.4f}]"
            if delta.ci_low is not None and delta.ci_high is not None
            else f"nulo ({delta.ci_reason})"
        )
    dropped = ", ".join(f"{k}={v}" for k, v in row.dropped.items()) or "—"
    return (
        f"| `{row.key}` | {row.kind.value} | {row.n} | {_num(row.expectancy_r)} | {pf} | "
        f"{change} | {interval} | {dropped} |"
    )


def deltas(
    outcomes: Sequence[Mapping[str, StressOutcome]], *, seed: int, resamples: int
) -> dict[str, ContrastResult]:
    """Δ pareado por sinal, com o intervalo por blocos de dia da REPLICATION §3.4."""
    results: dict[str, ContrastResult] = {}
    for spec in REWALK_SCENARIOS:
        if spec.key == BASE:
            continue
        pairs = [
            Pair(
                # O bloco é o dia UTC da entrada — o mesmo rótulo que
                # ``stats.blocks_of`` produz a partir de um instante. Aqui ele
                # já é uma data (``StressOutcome.entry_day``), então
                # reconstruir um ``datetime`` para reformatá-lo só criaria a
                # chance de um instante ingênuo.
                block=base.entry_day.isoformat(),
                delta=(arm.r_net or Decimal(0)) - (base.r_net or Decimal(0)),
            )
            for case in outcomes
            for base, arm in [(case[BASE], case.get(spec.key))]
            if arm is not None and base.evaluable and arm.evaluable and base.entry_day is not None
        ]
        results[spec.key] = contrast(spec.key, pairs, seed=seed, resamples=resamples)
    return results


def append_jsonl(path: Path, run: StressRun) -> None:
    """Acrescenta o recibo. Nunca reescreve: um livro-razão editável não é um."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run.to_jsonable(), ensure_ascii=False) + "\n")
