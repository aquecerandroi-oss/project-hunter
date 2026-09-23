"""R69 — coorte viva num instante e percentil dentro dela.

Funcao pura e testavel: recebe linhas cruas e devolve a coorte observavel em `t`.
A guarda anti-antecipacao vive aqui e é o que o teste prova.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

WINDOW = timedelta(seconds=120)


@dataclass(frozen=True)
class Row:
    """Uma linha de `meme_features_15s`."""

    mint: str
    as_of: datetime
    computed_at: datetime
    tape_as_of: datetime | None
    values: dict[str, Decimal | None]


def live_cohort(
    rows: list[Row], t: datetime, *, window: timedelta = WINDOW, lag: timedelta = timedelta(0)
) -> dict[str, Row]:
    """A linha mais recente por mint observavel em `t`.

    Guarda anti-antecipacao (as tres condicoes sao necessarias):
      1. `as_of <= t - lag`   — o tique nao pode ser posterior a decisao;
      2. `computed_at <= t - lag` — a linha nao pode ter sido ESCRITA depois da decisao;
      3. `tape_as_of <= as_of` — a fita que alimenta a linha nao pode vir do futuro dela.
    `as_of > t - window` mantem so quem ainda estava a ser observado.
    """
    cut = t - lag
    best: dict[str, Row] = {}
    for r in rows:
        if r.as_of > cut or r.computed_at > cut:
            continue
        if r.as_of <= t - window:
            continue
        if r.tape_as_of is not None and r.tape_as_of > r.as_of:
            continue
        cur = best.get(r.mint)
        if cur is None or r.as_of > cur.as_of:
            best[r.mint] = r
    return best


def percentile(cohort: dict[str, Row], subject: str, var: str) -> Decimal | None:
    """Percentil do sujeito dentro da coorte, com o sujeito FORA da referencia.

    Empates contam meio. Devolve None se o sujeito nao tem valor ou a referencia e vazia.
    """
    me = cohort.get(subject)
    if me is None:
        return None
    mine = me.values.get(var)
    if mine is None:
        return None
    lower = 0
    ties = 0
    total = 0
    for mint, r in cohort.items():
        if mint == subject:
            continue
        v = r.values.get(var)
        if v is None:
            continue
        total += 1
        if v < mine:
            lower += 1
        elif v == mine:
            ties += 1
    if total == 0:
        return None
    return (Decimal(lower) + Decimal(ties) / 2) / Decimal(total)
