"""Contraste do braço direcional, IC por meses e permutação por pregão (desenho §6).

Por instante elegível o arnês simula **os dois lados** com a mesma geometria simétrica (B =
compra, S = venda, bp líquido). Com ``a`` = 1 para compra da IA e 0 para venda:

    d = (a − π_h)·(B − S),   D = média de d nas operações da IA,

com π_h = fração de compras da IA **no horário h** (Astra R1: com π global, uma política de
relógio ganharia da deriva por horário sem ler nada). A permutação troca os vetores de lado de
pregões inteiros dentro do mesmo mês (preserva horário e dependência intradiária).

Censura: a imputação (pessimista: lado da IA no stop + 1 tick, oposto no alvo; otimista: o
inverso) é **cenário condicionado**, não limite — um gap no minuto ausente pode custar mais que o
stop (Astra R2/R3). Por isso a censura não resolvida bloqueia CONFIRMA e REFUTA no veredito.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import cast

import numpy as np
from numpy.typing import NDArray

from infra.research.b3.ia_grafico.resposta import Lado

N_HORARIOS = 12
Matriz = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Celula:
    dia: date
    slot: int
    lado_ia: Lado | None  # None = resposta inválida
    compra_bp: float | None  # None = censurado
    venda_bp: float | None
    compra_pior_bp: float
    venda_pior_bp: float
    compra_melhor_bp: float
    venda_melhor_bp: float
    lado_mm: Lado


def _codigo(lado: Lado | None) -> int:
    return {Lado.COMPRA: 1, Lado.VENDA: 0}.get(lado, -1) if lado is not None else -1


@dataclass(frozen=True)
class Painel:
    dias: tuple[date, ...]
    a: NDArray[np.int64]
    mm: NDArray[np.int64]
    b: Matriz
    s: Matriz
    bp: Matriz
    sp: Matriz
    bm: Matriz
    sm: Matriz
    elegivel: NDArray[np.bool_]

    @classmethod
    def de_celulas(cls, celulas: Sequence[Celula]) -> Painel:
        dias = tuple(sorted({c.dia for c in celulas}))
        linha = {d: i for i, d in enumerate(dias)}
        forma = (len(dias), N_HORARIOS)
        a, mm = np.full(forma, -1, np.int64), np.full(forma, -1, np.int64)
        mats: dict[str, Matriz] = {
            k: np.full(forma, np.nan, np.float64) for k in ("b", "s", "bp", "sp", "bm", "sm")
        }
        elegivel = np.zeros(forma, np.bool_)
        for c in celulas:
            i, j = linha[c.dia], c.slot
            if elegivel[i, j]:
                raise ValueError(f"célula duplicada {c.dia} horário {j}")
            elegivel[i, j] = True
            a[i, j], mm[i, j] = _codigo(c.lado_ia), _codigo(c.lado_mm)
            for k, v in (
                ("b", c.compra_bp),
                ("s", c.venda_bp),
                ("bp", c.compra_pior_bp),
                ("sp", c.venda_pior_bp),
                ("bm", c.compra_melhor_bp),
                ("sm", c.venda_melhor_bp),
            ):
                mats[k][i, j] = np.nan if v is None else v
        return cls(
            dias,
            a,
            mm,
            mats["b"],
            mats["s"],
            mats["bp"],
            mats["sp"],
            mats["bm"],
            mats["sm"],
            elegivel,
        )

    def linhas(self, idx: NDArray[np.int64]) -> Painel:
        return Painel(
            tuple(self.dias[i] for i in cast(list[int], idx.tolist())),
            self.a[idx],
            self.mm[idx],
            self.b[idx],
            self.s[idx],
            self.bp[idx],
            self.sp[idx],
            self.bm[idx],
            self.sm[idx],
            self.elegivel[idx],
        )

    @property
    def mascara(self) -> NDArray[np.bool_]:
        return (self.a >= 0) & self.elegivel

    @property
    def n_operacoes(self) -> int:
        return int(self.mascara.sum())

    @property
    def n_censuradas(self) -> int:
        return len(self.chaves_censuradas())

    def chaves_censuradas(self) -> set[tuple[date, int]]:
        """Operações com B **ou** S ausente: D usa os dois lados (Astra R3)."""
        faltando = self.mascara & (np.isnan(self.b) | np.isnan(self.s))
        linhas, colunas = np.nonzero(faltando)
        return {(self.dias[int(i)], int(j)) for i, j in zip(linhas, colunas, strict=True)}

    def efetivos(self, a: NDArray[np.int64], *, otimista: bool = False) -> tuple[Matriz, Matriz]:
        """Censura imputada: pessimista (lado da IA no pior caso) ou otimista (no melhor)."""
        ia_b, op_b = (self.bm, self.bp) if otimista else (self.bp, self.bm)
        ia_s, op_s = (self.sm, self.sp) if otimista else (self.sp, self.sm)
        b = np.where(np.isnan(self.b), np.where(a == 1, ia_b, op_b), self.b)
        s = np.where(np.isnan(self.s), np.where(a == 0, ia_s, op_s), self.s)
        return b, s


def _d(p: Painel, a: NDArray[np.int64], *, otimista: bool = False) -> float:
    m = (a >= 0) & p.elegivel
    if not m.any():
        return float("nan")
    b, s = p.efetivos(a, otimista=otimista)
    contagem = m.sum(axis=0)
    compras = np.where(m, a, 0).sum(axis=0)
    pi = np.divide(compras, contagem, out=np.zeros(N_HORARIOS), where=contagem > 0)
    d = (a - pi[np.newaxis, :]) * (b - s)
    return float(d[m].mean())


def contraste(p: Painel, *, otimista: bool = False) -> float:
    return _d(p, p.a, otimista=otimista)


def nivel(p: Painel) -> float:
    m = p.mascara
    if not m.any():
        return float("nan")
    b, s = p.efetivos(p.a)
    return float(np.where(p.a == 1, b, s)[m].mean())


def d_media_movel(p: Painel) -> float:
    """Média de (IA − regra da média móvel) nas operações da IA; regra sem lado rende 0."""
    m = p.mascara
    if not m.any():
        return float("nan")
    b, s = p.efetivos(p.a)
    ia = np.where(p.a == 1, b, s)
    regra = np.where(p.mm == 1, b, np.where(p.mm == 0, s, 0.0))
    return float((ia - regra)[m].mean())


def _meses(p: Painel) -> list[NDArray[np.int64]]:
    grupos: dict[tuple[int, int], list[int]] = {}
    for i, d in enumerate(p.dias):
        grupos.setdefault((d.year, d.month), []).append(i)
    return [np.array(v, np.int64) for _, v in sorted(grupos.items())]


def ic_bootstrap_meses(
    p: Painel, *, reps: int, semente: int, otimista: bool = False
) -> tuple[float, float]:
    """IC 95 % percentil reamostrando meses-calendário inteiros (π_h reestimado em cada réplica)."""
    meses = _meses(p)
    rng = np.random.default_rng(semente)
    valores: list[float] = []
    for _ in range(reps):
        escolha = rng.integers(0, len(meses), size=len(meses))
        partes: list[NDArray[np.int64]] = [meses[int(k)] for k in escolha]
        sub = p.linhas(np.concatenate(partes))
        v = contraste(sub, otimista=otimista)
        if not np.isnan(v):
            valores.append(v)
    if not valores:
        return float("nan"), float("nan")
    lo, hi = np.percentile(np.array(valores), [2.5, 97.5])
    return float(lo), float(hi)


def p_permutacao(p: Painel, *, reps: int, semente: int) -> float:
    """p = (1 + nº de D permutados ≥ observado) ÷ (reps + 1).

    Só se trocam pregões do mesmo mês **com a mesma máscara de elegibilidade** (Astra R2): o vetor
    de lados do doador sempre cabe no recebedor, o total de operações se conserva e nenhuma réplica
    vira NaN. Pregão sem par admissível fica no lugar.
    """
    observado = contraste(p)
    if np.isnan(observado):
        return float("nan")
    grupos: dict[tuple[int, int, bytes], list[int]] = {}
    for i, d in enumerate(p.dias):
        grupos.setdefault((d.year, d.month, p.elegivel[i].tobytes()), []).append(i)
    blocos = [np.array(v, np.int64) for _, v in sorted(grupos.items())]
    rng = np.random.default_rng(semente)
    acima = 0
    for _ in range(reps):
        origem = np.empty(len(p.dias), np.int64)
        for linhas in blocos:
            origem[linhas] = rng.permutation(linhas)
        if _d(p, p.a[origem]) >= observado:
            acima += 1
    return (1 + acima) / (reps + 1)


def metades(p: Painel) -> tuple[float, float]:
    """D antes e depois da data mediana dos pregões com operação."""
    com = [i for i in range(len(p.dias)) if p.mascara[i].any()]
    if len(com) < 2:
        return float("nan"), float("nan")
    corte = p.dias[com[(len(com) - 1) // 2]]
    antes = np.array([i for i in com if p.dias[i] <= corte], np.int64)
    depois = np.array([i for i in com if p.dias[i] > corte], np.int64)
    return contraste(p.linhas(antes)), contraste(p.linhas(depois))
