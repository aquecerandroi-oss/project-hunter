"""O estimador estratificado da H-022 e a sua reamostragem (§3, §4; aceites da rodada 5).

`D = Σ_s w_s (ȳ_true,s − ȳ_false,s) / Σ_s w_s`, com `w_s = n_true,s · n_false,s / n_s`, só
nos estratos que têm os dois grupos. Uma população e uma estatística para D, IC, p, MRE e
mínimos: todos passam por `estimar`.

Cada unidade carrega `conta` (entra no n do estrato) e `valor` (entra na média; `NaN` =
sem valor). É isso que deixa o estresse de censura usar o mesmo estimador: o `false`
censurado conta no peso mas a média do estrato continua a dos observados, **recalculada
em cada réplica** (§4, regras do estresse).

Reamostragem (J):

- **por mint**: sorteia mints com reposição, cada um com todas as suas unidades;
- **por blocos de 6 h**: sorteia blocos com reposição. O estrato é o próprio bloco, então
  um bloco sorteado duas vezes é um estrato com o dobro dos n (o mesmo que peso 2);
- nas réplicas os estratos são refeitos: só entram os que têm os dois grupos; réplica sem
  nenhum é inválida; mais de 1 % de inválidas (ou < 100 válidas) = IC não finito;
- IC = percentis 2,5 e 97,5 das réplicas válidas (`numpy.percentile`, linear);
- p = permutação de `grupo` dentro do estrato, bilateral: `(1 + #{|D*| ≥ |D|}) / (reps + 1)`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from infra.research.exp_m26.constantes import MAX_REPLICAS_INVALIDAS, MIN_REPLICAS_VALIDAS

_TOL = 1e-12


@dataclass(frozen=True)
class Unidades:
    estrato: np.ndarray
    grupo: np.ndarray
    conta: np.ndarray
    valor: np.ndarray

    @property
    def n(self) -> int:
        return int(self.grupo.size)


def _codigos(values: Sequence[object]) -> np.ndarray:
    if not len(values):
        return np.zeros(0, dtype=np.int64)
    _, inv = np.unique(np.asarray([str(v) for v in values], dtype=object), return_inverse=True)
    return inv.astype(np.int64)


def unidades(
    estrato: Sequence[object],
    grupo: Sequence[bool],
    valor: Sequence[float | None],
    conta: Sequence[bool] | None = None,
) -> Unidades:
    n = len(grupo)
    if not (len(estrato) == len(valor) == n and (conta is None or len(conta) == n)):
        raise ValueError("estrato, grupo, valor e conta com tamanhos diferentes")
    return Unidades(
        estrato=_codigos(estrato),
        grupo=np.asarray(grupo, dtype=bool),
        conta=np.ones(n) if conta is None else np.asarray(conta, dtype=np.float64),
        valor=np.asarray([math.nan if v is None else float(v) for v in valor], dtype=np.float64),
    )


@dataclass(frozen=True)
class Estimativa:
    d: float
    estratos: int
    n_true: int
    n_false: int
    media_true: float


def _estimar(
    u: Unidades, grupo: np.ndarray, idx: np.ndarray | None
) -> tuple[float, int, float, float, float]:
    s = u.estrato if idx is None else u.estrato[idx]
    g = grupo if idx is None else grupo[idx]
    c = u.conta if idx is None else u.conta[idx]
    v = u.valor if idx is None else u.valor[idx]
    has = ~np.isnan(v)
    v0 = np.where(has, v, 0.0)
    k = int(u.estrato.max()) + 1 if u.n else 0

    def soma(mask: np.ndarray, w: np.ndarray) -> np.ndarray:
        return np.bincount(s[mask], weights=w[mask], minlength=k)

    nt, nf = soma(g, c), soma(~g, c)
    syt, syf = soma(g, v0), soma(~g, v0)
    hyt, hyf = soma(g, has.astype(np.float64)), soma(~g, has.astype(np.float64))
    ok = (nt > 0) & (nf > 0) & (hyt > 0) & (hyf > 0)
    if not ok.any():
        return math.nan, 0, 0.0, 0.0, math.nan
    w = nt[ok] * nf[ok] / (nt[ok] + nf[ok])
    diff = syt[ok] / hyt[ok] - syf[ok] / hyf[ok]
    d = float(np.sum(w * diff) / np.sum(w))
    level = float(syt[ok].sum() / hyt[ok].sum())
    return d, int(ok.sum()), float(nt[ok].sum()), float(nf[ok].sum()), level


def estimar(u: Unidades) -> Estimativa:
    d, k, nt, nf, level = _estimar(u, u.grupo, None)
    return Estimativa(d, k, round(nt), round(nf), level)


# ----------------------------------------------------------------------- intervalos


@dataclass(frozen=True)
class Intervalo:
    lo: float
    hi: float
    invalidas: float
    validas: int

    @property
    def finito(self) -> bool:
        return (
            math.isfinite(self.lo)
            and math.isfinite(self.hi)
            and self.invalidas <= MAX_REPLICAS_INVALIDAS
            and self.validas >= MIN_REPLICAS_VALIDAS
        )


def intervalo(replicas: np.ndarray) -> Intervalo:
    total = int(replicas.size)
    ok = replicas[np.isfinite(replicas)]
    invalid = 1.0 if total == 0 else float((total - ok.size) / total)
    if ok.size == 0:
        return Intervalo(math.nan, math.nan, invalid, 0)
    lo, hi = np.percentile(ok, [2.5, 97.5])
    return Intervalo(float(lo), float(hi), invalid, int(ok.size))


class Reamostrador:
    """Sorteia grupos inteiros (mints ou blocos) e devolve os índices das unidades."""

    def __init__(self, grupos: Sequence[object] | np.ndarray) -> None:
        if isinstance(grupos, np.ndarray) and grupos.dtype.kind in "iu":
            codes: np.ndarray = grupos
        else:
            codes = _codigos(list(grupos))
        self.order = np.argsort(codes, kind="stable")
        self.sizes = np.bincount(codes) if codes.size else np.zeros(0, dtype=np.int64)
        self.starts = np.cumsum(self.sizes) - self.sizes
        self.k = int(self.sizes.size)

    def indices(self, rng: np.random.Generator) -> np.ndarray:
        draw = rng.integers(0, self.k, size=self.k)
        sz = self.sizes[draw]
        offs = np.repeat(np.cumsum(sz) - sz, sz)
        return self.order[np.repeat(self.starts[draw], sz) + np.arange(int(sz.sum())) - offs]


def replicas(
    grupos: Sequence[object] | np.ndarray,
    estatistica: Callable[[np.ndarray], float],
    *,
    reps: int,
    seed: int,
) -> np.ndarray:
    """`estatistica(idx)` em `reps` réplicas de grupos inteiros; `NaN` = réplica inválida."""
    sampler = Reamostrador(grupos)
    if sampler.k == 0:
        return np.full(reps, math.nan)
    rng = np.random.default_rng(seed)
    return np.array([estatistica(sampler.indices(rng)) for _ in range(reps)])


def ic_mint(u: Unidades, mints: Sequence[object], *, reps: int, seed: int) -> Intervalo:
    return intervalo(
        replicas(mints, lambda idx: _estimar(u, u.grupo, idx)[0], reps=reps, seed=seed)
    )


def ic_blocos(u: Unidades, *, reps: int, seed: int) -> Intervalo:
    return intervalo(
        replicas(u.estrato, lambda idx: _estimar(u, u.grupo, idx)[0], reps=reps, seed=seed)
    )


def p_permutacao(u: Unidades, *, reps: int, seed: int) -> float:
    """p bilateral da permutação de `grupo` dentro do estrato (permutabilidade condicional
    ao estrato: suposição declarada, §4). `NaN` se D não é finito."""
    obs = _estimar(u, u.grupo, None)[0]
    if not math.isfinite(obs):
        return math.nan
    base = np.argsort(u.estrato, kind="stable")
    rotulos = u.grupo[base]
    rng = np.random.default_rng(seed)
    hits = 0
    novo = np.empty_like(u.grupo)
    for _ in range(reps):
        perm = np.lexsort((rng.random(u.n), u.estrato))
        novo[perm] = rotulos
        d = _estimar(u, novo, None)[0]
        hits += int(math.isfinite(d) and abs(d) >= abs(obs) - _TOL)
    return (hits + 1) / (reps + 1)
