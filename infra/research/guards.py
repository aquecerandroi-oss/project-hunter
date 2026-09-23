"""Guarda anti-antecipação reutilizável — o primitivo que o moinho empresta a todo estudo.

Duas formas da mesma regra (`docs/PIPELINE.md` §2: bar-features usam só velas `is_final`):

* **Séries** (`GuardedSeries`): cada linha tem um instante de fecho; ler uma linha que
  fecha *depois* do instante de decisão é antecipação. Portado do R68
  (`.claude/state/r68/load68.py`), onde `take` é o **único** acesso a histórico e é o que
  apanha a estratégia batoteira. **Limite conhecido** (apontado pela Astra na revisão da
  T4.87): `values` continua a ser um array público e é o chamador que passa
  `decision_idx`; quem ler `series.values[i + 1]` diretamente, ou declarar uma decisão
  futura, escapa. Em `run_hypothesis` esse buraco está fechado por construção — o
  instante de decisão vem da coluna declarada no spec, não do chamador — mas quem usar
  `GuardedSeries` à mão tem de passar por `take`.
* **Linhas de feature** (`Instants`): cada linha carrega `as_of`, `computed_at` e
  `tape_as_of`. As três condições do R69 (`.claude/state/r69/cohort.py`) são necessárias:
  o tique não pode ser posterior à decisão, a linha não pode ter sido **escrita** depois
  da decisão (preenchimento retroativo) e a fita que a alimenta não pode vir do futuro
  dela própria.

Tempo é sempre UTC *aware*; um `datetime` ingénuo é recusado com `ValueError`, porque
comparar ingénuo com aware é o modo silencioso de a guarda deixar passar tudo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np


class LookAheadError(RuntimeError):
    """Uma feature tentou usar informação posterior ao instante de decisão."""


# --------------------------------------------------------------------------- séries


def assert_causal(source_close: np.ndarray, decision_instant: np.ndarray | int, what: str) -> None:
    """Recusa qualquer fonte cujo fecho seja posterior ao instante de decisão.

    `source_close` e `decision_instant` na mesma unidade inteira (minutos ou segundos de
    época). Ler uma linha que fecha **em** `decision_instant` é legítimo — nesse instante
    ela já existe; ler uma que fecha depois é antecipação.
    """
    src = np.asarray(source_close)
    dec = np.asarray(decision_instant)
    bad = src > dec
    if bool(np.any(bad)):
        i = int(np.argmax(bad))
        raise LookAheadError(
            f"{what}: fonte fecha em {int(src.ravel()[i])} > decisão "
            f"{int(np.broadcast_to(dec, src.shape).ravel()[i])}"
        )


@dataclass(frozen=True)
class GuardedSeries:
    """Uma coluna histórica cujo único acesso passa pela guarda.

    `close_time[i]` é o instante em que a linha `i` **passa a existir**. Um preditor que
    tente ler `idx = decision_idx + 1` levanta `LookAheadError`.
    """

    name: str
    close_time: np.ndarray
    values: np.ndarray

    def __post_init__(self) -> None:
        if self.close_time.shape != self.values.shape:
            raise ValueError(f"{self.name}: close_time e values têm formas diferentes")

    def __len__(self) -> int:
        return int(self.close_time.size)

    def take(self, idx: np.ndarray, decision_idx: np.ndarray) -> np.ndarray:
        """Lê `values[idx]` como feature das decisões `decision_idx`, com guarda."""
        assert_causal(self.close_time[idx], self.close_time[decision_idx], self.name)
        return self.values[idx]


# ------------------------------------------------------------------- linhas de feature


@dataclass(frozen=True)
class Instants:
    """Os instantes de observabilidade de uma linha de feature. Tudo UTC aware."""

    as_of: datetime
    computed_at: datetime
    tape_as_of: datetime | None = None


def _aware(value: datetime, field: str, what: str) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{what}: {field} sem fuso — o tempo do moinho é sempre UTC aware")
    return value


def check_observable(
    inst: Instants, decision: datetime, what: str, *, lag: timedelta = timedelta(0)
) -> str | None:
    """Devolve o motivo da recusa, ou `None` se a linha é observável na decisão."""
    if lag < timedelta(0):
        raise ValueError(f"{what}: atraso negativo ({lag}) adiantaria o corte da guarda")
    cut = _aware(decision, "decision", what) - lag
    if _aware(inst.as_of, "as_of", what) > cut:
        return f"as_of {inst.as_of.isoformat()} > decisão-atraso {cut.isoformat()}"
    if _aware(inst.computed_at, "computed_at", what) > cut:
        return f"computed_at {inst.computed_at.isoformat()} > decisão-atraso {cut.isoformat()}"
    if inst.tape_as_of is not None and _aware(inst.tape_as_of, "tape_as_of", what) > inst.as_of:
        return f"tape_as_of {inst.tape_as_of.isoformat()} > as_of {inst.as_of.isoformat()}"
    return None


def assert_observable(
    inst: Instants, decision: datetime, what: str, *, lag: timedelta = timedelta(0)
) -> None:
    """Levanta `LookAheadError` se a linha usa informação posterior à decisão."""
    motive = check_observable(inst, decision, what, lag=lag)
    if motive is not None:
        raise LookAheadError(f"{what}: {motive}")


def observable_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    decision: str,
    as_of: str,
    computed_at: str,
    tape_as_of: str | None = None,
    lag: timedelta = timedelta(0),
    strict: bool = False,
) -> tuple[list[Mapping[str, object]], list[tuple[int, str]]]:
    """Separa as linhas observáveis das recusadas, pelas colunas de instantes indicadas.

    Com `strict=True` a primeira recusa levanta `LookAheadError` — é o modo que um
    estudo usa quando a população *deveria* ser causal por construção e uma recusa é um
    defeito do export, não um ponto a censurar.
    """
    kept: list[Mapping[str, object]] = []
    refused: list[tuple[int, str]] = []
    for i, row in enumerate(rows):
        inst = Instants(
            as_of=_as_dt(row, as_of, i),
            computed_at=_as_dt(row, computed_at, i),
            tape_as_of=None if tape_as_of is None else _opt_dt(row, tape_as_of),
        )
        motive = check_observable(inst, _as_dt(row, decision, i), f"linha {i}", lag=lag)
        if motive is None:
            kept.append(row)
        elif strict:
            raise LookAheadError(f"linha {i}: {motive}")
        else:
            refused.append((i, motive))
    return kept, refused


def _as_dt(row: Mapping[str, object], column: str, i: int) -> datetime:
    value = row.get(column)
    if not isinstance(value, datetime):
        raise ValueError(f"linha {i}: coluna {column!r} não é datetime (é {type(value).__name__})")
    return value


def _opt_dt(row: Mapping[str, object], column: str) -> datetime | None:
    value = row.get(column)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"coluna {column!r} não é datetime (é {type(value).__name__})")
    return value
