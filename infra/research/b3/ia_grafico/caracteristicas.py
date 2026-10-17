"""Características do caminho decisório inteiro em painéis SINTÉTICOS (Astra R2/R3, must-fix 3).

Desenho efetivo: pregões inteiros sorteados por mês, máscaras de elegibilidade variáveis, "none"
dependente do passado (volatilidade do dia), correlação dentro do dia, respostas inválidas,
censura, braço completo **distinto** do direcional (geometria própria e limites sem fill) e a regra
da média móvel concorrendo com lado sorteado. Cada repetição passa pela **futilidade** (primeiros 42
pregões de uma ordem sorteada) antes da consulta final; as paradas são contadas à parte dos três
rótulos. Serve para publicar frequências; nunca para escolher parâmetros. Nada aqui é dado de mercado.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, timedelta
from statistics import fmean

import numpy as np

from infra.research.b3.ia_grafico.analise import resumir
from infra.research.b3.ia_grafico.estatistica import Celula
from infra.research.b3.ia_grafico.pipeline import Avaliacao
from infra.research.b3.ia_grafico.resposta import Lado
from infra.research.b3.ia_grafico.veredito import futilidade, julgar

CUSTO_BP = 1.3  # ≈ 2 ticks + 2,56 pts sobre ~120 000 pts, por operação (escala do WIN)
PREGOES_FUTILIDADE = 42
ROTULOS = ("CONFIRMA", "NÃO CONFIRMA", "REFUTA", "PARADA (futilidade)", "PARADA (instrumento)")


@dataclass(frozen=True, slots=True)
class Cenario:
    efeito_bp: float
    meses: int = 24
    pregoes_por_mes: int = 7
    inicio: date = date(2023, 1, 2)
    sigma_bp: float = 30.0
    peso_dia: float = 0.5
    frac_inelegivel: float = 0.03
    frac_none: float = 0.30
    frac_invalida: float = 0.01
    frac_censura: float = 0.0
    frac_sem_fill: float = 0.10


@dataclass(frozen=True, slots=True)
class Sintetico:
    avaliacao: Avaliacao
    dias_completo: tuple[date, ...]
    n_invalidas: int


def _dias(c: Cenario) -> list[date]:
    dias: list[date] = []
    ano, mes = c.inicio.year, c.inicio.month
    for _ in range(c.meses):
        dias += [date(ano, mes, 1 + 27 * k // c.pregoes_por_mes) for k in range(c.pregoes_por_mes)]
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return dias


def painel_sintetico(c: Cenario, semente: int, *, escala: float = 1.0) -> Sintetico:
    """``escala`` estica o movimento (horizontes de 45/75 min) mantendo os mesmos sorteios."""
    rng = np.random.default_rng(semente)
    e_abs = c.sigma_bp * math.exp(0.3**2 / 2) * math.sqrt(2 / math.pi)
    acerto = min(max(0.5 + c.efeito_bp / (2 * e_abs), 0.0), 1.0)
    melhor, pior = 2 * c.sigma_bp, -2 * c.sigma_bp
    celulas: list[Celula] = []
    completo: list[float] = []
    dias_completo: list[date] = []
    censuradas_completo = invalidas = 0
    for dia in _dias(c):
        choque, vol = rng.normal(), float(np.exp(rng.normal(0, 0.3)))
        for slot in range(12):
            u = rng.random(7)
            ruido, geometria = rng.normal(), rng.uniform(0.6, 1.4)
            mov = escala * c.sigma_bp * vol
            mov *= c.peso_dia * choque + math.sqrt(1 - c.peso_dia**2) * ruido
            if u[0] < c.frac_inelegivel:
                continue
            b, s = mov - CUSTO_BP, -mov - CUSTO_BP
            mm = Lado.COMPRA if u[5] < 0.5 else Lado.VENDA
            if u[1] < c.frac_invalida:
                invalidas += 1
                celulas.append(Celula(dia, slot, None, b, s, pior, pior, melhor, melhor, mm))
                continue
            if u[2] < c.frac_none * (1.5 if vol > 1 else 0.5):
                celulas.append(Celula(dia, slot, Lado.NENHUM, b, s, pior, pior, melhor, melhor, mm))
                completo.append(0.0)
                dias_completo.append(dia)
                continue
            lado = Lado.COMPRA if (b > s) == (u[3] < acerto) else Lado.VENDA
            censurada = u[4] < c.frac_censura
            bb: float | None = b
            ss: float | None = s
            if censurada:
                bb, ss = (None, s) if u[6] < 0.5 else (b, None)
            celulas.append(Celula(dia, slot, lado, bb, ss, pior, pior, melhor, melhor, mm))
            if censurada:
                censuradas_completo += 1
                completo.append(pior)
            elif u[6] < c.frac_sem_fill:
                completo.append(0.0)
            else:
                completo.append((b if lado is Lado.COMPRA else s) * geometria - 0.3)
            dias_completo.append(dia)
    av = Avaliacao(celulas, completo, 0, censuradas_completo, 0)
    return Sintetico(av, tuple(dias_completo), invalidas)


def _parada(s: Sintetico, semente: int) -> str | None:
    dias = sorted(set(s.dias_completo))
    ordem = np.random.default_rng(semente).permutation(len(dias))
    primeiros = {dias[int(i)] for i in ordem[:PREGOES_FUTILIDADE]}
    pares = zip(s.avaliacao.completo_bp, s.dias_completo, strict=True)
    valores = [v for v, d in pares if d in primeiros]
    n_op = sum(
        1
        for c in s.avaliacao.celulas
        if c.dia in primeiros and c.lado_ia is not None and c.lado_ia is not Lado.NENHUM
    )
    decisao = futilidade(nivel_completo=fmean(valores) if valores else math.nan, n_operacoes=n_op)
    if decisao == "seguir":
        return None
    return "PARADA (instrumento)" if decisao.startswith("parar:") else "PARADA (futilidade)"


def operar(c: Cenario, *, repeticoes: int, reps: int, holdout_meses: int = 4) -> Counter[str]:
    contagem: Counter[str] = Counter()
    fim_p = _dias(c)[-1]
    h_inicio = date(fim_p.year + (fim_p.month == 12), fim_p.month % 12 + 1, 1) + timedelta(days=31)
    ch = replace(c, meses=holdout_meses, pregoes_por_mes=20, inicio=h_inicio.replace(day=1))
    for r in range(repeticoes):
        prim = painel_sintetico(c, r)
        parada = _parada(prim, 42042 + r)
        if parada is not None:
            contagem[parada] += 1
            continue
        hold = painel_sintetico(ch, 1_000_000 + r)
        resumo = resumir(
            primario=prim.avaliacao,
            patamar45=painel_sintetico(c, r, escala=math.sqrt(45 / 60)).avaliacao,
            patamar75=painel_sintetico(c, r, escala=math.sqrt(75 / 60)).avaliacao,
            holdout=hold.avaliacao,
            n_chamadas=len(prim.avaliacao.celulas),
            n_invalidas=prim.n_invalidas,
            holdout_n_chamadas=len(hold.avaliacao.celulas),
            holdout_n_invalidas=hold.n_invalidas,
            reps=reps,
            semente=r,
        )
        contagem[julgar(resumo).rotulo] += 1
    return contagem
