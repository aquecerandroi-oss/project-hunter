"""O veredito da H-042 na ordem pré-registrada, a futilidade e o relatório em Markdown.

Três rótulos e só três (``docs/RESEARCH.md``). NaN nunca passa numa cláusula; falta de
potência nunca vira REFUTA; CONFIRMA = candidato a braço de papel, nunca dinheiro real.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from infra.research.b3.ia_grafico.protocolo import MRE_BP, VERSAO_PROMPT
from infra.research.b3.ia_grafico.render import VERSAO as VERSAO_GRAFICO

MIN_OPERACOES, MIN_MESES = 600, 12
MIN_HOLDOUT_OPERACOES, MIN_HOLDOUT_MESES = 150, 3
TETO_FRACAO = 0.05


@dataclass(frozen=True, slots=True)
class Resumo:
    n_chamadas: int
    n_invalidas: int
    n_instantes: int
    n_operacoes: int
    n_censuradas: int
    n_sem_preco_entrada: int
    n_meses: int
    d: float
    ic: tuple[float, float]
    p: float
    nivel_direcional: float
    nivel_completo: float
    metades: tuple[float, float]
    patamar: tuple[float, float]
    d_mm: float
    holdout_operacoes: int
    holdout_meses: int
    holdout_nivel_completo: float | None
    holdout_d: float | None
    ic_otimista: tuple[float, float]
    holdout_n_chamadas: int
    holdout_n_invalidas: int
    holdout_n_censuradas: int
    holdout_n_sem_preco_entrada: int


@dataclass(frozen=True, slots=True)
class Veredito:
    rotulo: str
    motivo: str
    clausulas: tuple[tuple[str, bool, str], ...]


def _positivo(v: float | None) -> bool:
    return v is not None and not math.isnan(v) and v > 0


def _limite(r: Resumo) -> list[str]:
    falhas: list[str] = []
    if r.n_operacoes < MIN_OPERACOES:
        falhas.append(f"{r.n_operacoes} operações (< {MIN_OPERACOES})")
    if r.n_chamadas and r.n_invalidas > TETO_FRACAO * r.n_chamadas:
        falhas.append(f"{r.n_invalidas} inválidas em {r.n_chamadas} chamadas (> 5 %)")
    if r.n_censuradas > TETO_FRACAO * max(r.n_operacoes, 1):
        falhas.append(f"censura de {r.n_censuradas} operações (> 5 %)")
    if r.n_sem_preco_entrada > TETO_FRACAO * max(r.n_operacoes, 1):
        falhas.append(f"{r.n_sem_preco_entrada} sem preço na entrada (> 5 %)")
    if r.n_meses < MIN_MESES:
        falhas.append(f"{r.n_meses} meses (< {MIN_MESES})")
    return falhas


def _holdout_instrumento_ok(r: Resumo) -> bool:
    return (
        r.holdout_operacoes >= MIN_HOLDOUT_OPERACOES
        and r.holdout_meses >= MIN_HOLDOUT_MESES
        and r.holdout_n_invalidas <= TETO_FRACAO * max(r.holdout_n_chamadas, 1)
        and r.holdout_n_sem_preco_entrada <= TETO_FRACAO * max(r.holdout_operacoes, 1)
    )


def julgar(r: Resumo) -> Veredito:
    """Ordem: LIMITE → CONFIRMA → REFUTA → NÃO CONFIRMA.

    Censura não resolvida bloqueia o CONFIRMA (em P ou H) e também o REFUTA (em P): nenhuma
    imputação é limite, porque um gap no minuto ausente pode custar mais que o stop (Astra R2/R3).
    As imputações pessimista (``ic``) e otimista (``ic_otimista``) são sensibilidades publicadas.
    """
    lo, hi = r.ic
    holdout_ok = _holdout_instrumento_ok(r)
    clausulas = (
        (f"D ≥ MRE ({MRE_BP} bp)", not math.isnan(r.d) and r.d >= MRE_BP, f"{r.d:.2f}"),
        ("IC 95 % inferior > 0", _positivo(lo), f"[{lo:.2f}; {hi:.2f}]"),
        ("permutação p < 0,05", not math.isnan(r.p) and r.p < 0.05, f"{r.p:.4f}"),
        (
            "nível do braço direcional > 0",
            _positivo(r.nivel_direcional),
            f"{r.nivel_direcional:.2f}",
        ),
        (
            "nível da estratégia completa > 0",
            _positivo(r.nivel_completo),
            f"{r.nivel_completo:.2f}",
        ),
        ("D > 0 nas duas metades", all(map(_positivo, r.metades)), str(r.metades)),
        ("patamar: D > 0 com saída em 45 e 75 min", all(map(_positivo, r.patamar)), str(r.patamar)),
        ("IA − média móvel > 0", _positivo(r.d_mm), f"{r.d_mm:.2f}"),
        (
            "holdout pós-corte suficiente, com instrumento ok, nível completo > 0 e D > 0",
            holdout_ok and _positivo(r.holdout_nivel_completo) and _positivo(r.holdout_d),
            f"{r.holdout_operacoes} op., {r.holdout_meses} meses, "
            f"nível {r.holdout_nivel_completo}, D {r.holdout_d}",
        ),
        (
            "nenhuma censura não resolvida (P e H)",
            r.n_censuradas == 0 and r.holdout_n_censuradas == 0,
            f"P {r.n_censuradas}, H {r.holdout_n_censuradas}",
        ),
    )
    falhas = _limite(r)
    if falhas:
        return Veredito("NÃO CONFIRMA", "limite de dado: " + "; ".join(falhas), clausulas)
    if all(ok for _, ok, _ in clausulas):
        return Veredito("CONFIRMA", "todas as cláusulas", clausulas)
    if r.n_censuradas:
        motivo = f"instrumento: {r.n_censuradas} operações com censura não resolvida no primário"
        return Veredito("NÃO CONFIRMA", motivo, clausulas)
    if not math.isnan(hi) and hi < MRE_BP:
        return Veredito("REFUTA", f"limite superior do IC {hi:.2f} < MRE {MRE_BP}", clausulas)
    reprovadas = [nome for nome, ok, _ in clausulas if not ok]
    return Veredito("NÃO CONFIRMA", "falhou: " + "; ".join(reprovadas), clausulas)


def futilidade(*, nivel_completo: float, n_operacoes: int) -> str:
    """Consulta única nos primeiros 500 instantes da ordem sorteada (parada operacional)."""
    if n_operacoes == 0 or math.isnan(nivel_completo):
        return "parar: instrumento"
    return "parar sem rótulo" if nivel_completo <= 0 else "seguir"


def relatorio(r: Resumo, *, diagnosticos: Mapping[str, object]) -> str:
    v = julgar(r)
    linhas = [
        "# H-042 — IA que lê o gráfico do WIN: relatório",
        "",
        f"**Veredito: {v.rotulo}** — {v.motivo}",
        "",
        f"Gráfico `{VERSAO_GRAFICO}` · pedido `{VERSAO_PROMPT}` · MRE {MRE_BP} bp por operação.",
        "",
        "| cláusula | passa | valor |",
        "|---|---|---|",
        *(f"| {nome} | {'sim' if ok else 'não'} | {valor} |" for nome, ok, valor in v.clausulas),
        "",
        "## Contagens",
        "",
        *(f"- {k}: {val}" for k, val in asdict(r).items() if k.startswith(("n_", "holdout_"))),
        "",
        "## Diagnósticos (publicados, não decidem)",
        "",
        *(f"- {k}: {val}" for k, val in diagnosticos.items()),
        "",
        "## Suposições declaradas",
        "",
        "- aproximação OHLC de 1 min, rotulada aproximação, nunca execução observada;",
        "- 1 tick (5 pts) adverso por perna, pelo lado, em toda perna; R$ 0,256 por perna (1,28 pt);",
        "- entrada a mercado em t + 1 min; censura não resolvida bloqueia CONFIRMA e REFUTA "
        "(as imputações são só sensibilidade);",
        "- bp contra o fechamento de referência de cada instante; IR fora da métrica.",
    ]
    return "\n".join(linhas) + "\n"
