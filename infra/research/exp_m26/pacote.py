"""A secundária: D_pacote = média de H − L por par completo, sob observação conjunta L+C+H.

**Par** (uma decisão comum por mint desde o seed; §2.2, §4; revisão do J):

- a unidade é o mint com linha de R1 em L ou H, **ou** com proposta de L/H sem linha em
  R1 (órfã): esta é par ausente por instrumento, nunca reconstruída;
- ordem: `fidelity` ≠ `faithful` → exclusão substantiva (E, fora do denominador) → perna
  sem registro → `features_end_time` diferente → perna sem proposta (I) ou sem fill (F) →
  foto de fill diferente (`observed_at`, `source`) → estados das pernas;
- as duas avaliáveis = **completo**; preenchidas na mesma foto com ao menos uma perna sem
  desfecho precificável = estressável (`H_C`, `L_C`, `ambos_C`); o resto é ausente sem
  estresse (não se atribui custo de posição a uma compra que não aconteceu).

**Inferência:** IC por mint (pares) e por blocos de 6 h (`evaluated_at` da decisão); p por
bootstrap em blocos **centrado sob a nula** (diferenças − média), bilateral. Não testável —
ausentes > 20 % das comuns, < 100 completos ou < 10 blocos com pares — continua na família
com p = 1.

**Estresse:** H ausente → perda integral de H, L observado; L ausente → p90 observado dos L
completos, H observado; ambos → p10 observado das diferenças completas e nível de H em perda
integral. Quantis recalculados em cada réplica sobre os completos da réplica.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from infra.research.exp_m26.classes import bloco_de, censura_da_aposta, exclusao
from infra.research.exp_m26.constantes import (
    FIDEDIGNA,
    MIN_BLOCOS_PARES,
    MIN_PARES,
    P_NAO_TESTAVEL,
    QUANTIL_DIFERENCA_AMBOS,
    QUANTIL_L_AUSENTE,
    TETO_PARES_AUSENTES,
)
from infra.research.exp_m26.estimador import intervalo, replicas
from infra.research.exp_m26.modelo import Oportunidade

_TOL = 1e-12
_KIND = {"completo": 0, "H_C": 1, "L_C": 2, "ambos_C": 3}


@dataclass(frozen=True)
class Par:
    mint: str
    bloco: str | None
    estado: str
    detalhe: str
    y_h: float | None = None
    y_l: float | None = None
    perda_h: float | None = None


def _perna(o: Oportunidade) -> tuple[str, str]:
    if o.proposal_id is None:
        return "I", f"sem_proposta:{o.no_proposal_reason}"
    if o.aposta is None:
        return "F", f"sem_fill:{o.proposal_status}"
    c = censura_da_aposta(o.aposta)
    return ("C", c) if c is not None else ("A", "avaliavel")


def parear(mint: str, perna_l: Oportunidade | None, perna_h: Oportunidade | None) -> Par:
    presentes = [(n, o) for n, o in (("L", perna_l), ("H", perna_h)) if o is not None]
    bloco = bloco_de(min(o.evaluated_at for _, o in presentes)) if presentes else None
    for nome, o in presentes:
        if o.fidelity != FIDEDIGNA:
            return Par(mint, bloco, "ausente", f"{nome}:fidelity:{o.fidelity}")
    for _, o in presentes:
        if exclusao(o) is not None:
            return Par(mint, bloco, "E", str(exclusao(o)))
    if perna_l is None or perna_h is None:
        return Par(mint, bloco, "ausente", "sem_registro_" + ("L" if perna_l is None else "H"))
    if perna_l.features_end_time != perna_h.features_end_time:
        return Par(mint, bloco, "ausente", "minuto_diferente")
    (el, dl), (eh, dh) = _perna(perna_l), _perna(perna_h)
    for nome, e, d in (("L", el, dl), ("H", eh, dh)):
        if e in ("I", "F"):
            return Par(mint, bloco, "ausente", f"{nome}:{e}:{d}")
    assert perna_l.aposta is not None and perna_h.aposta is not None
    if (perna_l.aposta.fill_observed_at, perna_l.aposta.fill_source) != (
        perna_h.aposta.fill_observed_at,
        perna_h.aposta.fill_source,
    ):
        return Par(mint, bloco, "ausente", "foto_de_fill")
    estado = {("A", "A"): "completo", ("C", "A"): "H_C", ("A", "C"): "L_C"}.get((eh, el), "ambos_C")
    return Par(
        mint,
        bloco,
        estado,
        f"H:{dh}|L:{dl}",
        y_h=perna_h.aposta.retorno() if eh == "A" else None,
        y_l=perna_l.aposta.retorno() if el == "A" else None,
        perda_h=perna_h.aposta.perda_integral(),
    )


def _arrays(pares: Sequence[Par]) -> dict[str, np.ndarray]:
    def col(xs: list[float | None]) -> np.ndarray:
        return np.array([math.nan if x is None else x for x in xs], dtype=np.float64)

    return {
        "kind": np.array([_KIND[p.estado] for p in pares], dtype=np.int64),
        "yh": col([p.y_h for p in pares]),
        "yl": col([p.y_l for p in pares]),
        "perda": col([p.perda_h for p in pares]),
        "bloco": np.array([str(p.bloco) for p in pares], dtype=object),
        "mint": np.array([p.mint for p in pares], dtype=object),
    }


def _estresse(a: dict[str, np.ndarray], idx: np.ndarray) -> tuple[float, float]:
    """(média das diferenças estressadas, nível de H estressado) na réplica `idx`."""
    k = a["kind"][idx]
    comp = idx[k == 0]
    if comp.size == 0:
        return math.nan, math.nan
    yh, yl, perda = a["yh"][idx], a["yl"][idx], a["perda"][idx]
    p90_l = float(np.quantile(a["yl"][comp], QUANTIL_L_AUSENTE))
    p10_d = float(np.quantile(a["yh"][comp] - a["yl"][comp], QUANTIL_DIFERENCA_AMBOS))
    d = np.select([k == 0, k == 1, k == 2], [yh - yl, perda - yl, yh - p90_l], p10_d)
    h = np.select([k == 0, k == 1, k == 2], [yh, perda, yh], perda)
    return float(d.mean()), float(h.mean())


def secundaria(pares: Sequence[Par], *, reps: int, seed: int) -> dict[str, Any]:
    comuns = [p for p in pares if p.estado != "E"]
    comp = [p for p in comuns if p.estado == "completo"]
    stress = [p for p in comuns if p.estado in _KIND]
    n = len(comuns)
    taxa = (n - len(comp)) / n if n else math.nan
    blocos = len({p.bloco for p in comp})
    motivo: str | None = None
    if not n or taxa > TETO_PARES_AUSENTES:
        motivo = f"instrumento: pares ausentes {taxa:.3f} das {n} decisões comuns"
    elif len(comp) < MIN_PARES:
        motivo = f"amostra: {len(comp)} pares completos < {MIN_PARES}"
    elif blocos < MIN_BLOCOS_PARES:
        motivo = f"amostra: {blocos} blocos com pares < {MIN_BLOCOS_PARES}"
    out: dict[str, Any] = {
        "comuns": n,
        "excluidos_E": len(pares) - n,
        "completos": len(comp),
        "taxa_ausentes": taxa,
        "blocos": blocos,
        "ausentes_por_motivo": _contagem([p.detalhe for p in comuns if p.estado == "ausente"]),
        "testavel": motivo is None,
        "motivo_nao_testavel": motivo,
        "d": math.nan,
        "nivel_h": math.nan,
        "p": P_NAO_TESTAVEL,
    }
    if not comp:
        return out
    a = _arrays(comp)
    d = a["yh"] - a["yl"]
    out["d"], out["nivel_h"] = float(d.mean()), float(a["yh"].mean())
    out["ic_mint"] = intervalo(
        replicas(a["mint"], lambda i: float(d[i].mean()), reps=reps, seed=seed)
    )
    out["ic_blocos"] = intervalo(
        replicas(a["bloco"], lambda i: float(d[i].mean()), reps=reps, seed=seed)
    )
    if motivo is None:
        centrado = d - d.mean()
        t = replicas(a["bloco"], lambda i: float(centrado[i].mean()), reps=reps, seed=seed)
        out["p"] = (int(np.sum(np.abs(t) >= abs(out["d"]) - _TOL)) + 1) / (reps + 1)
    s = _arrays(stress)
    full = np.arange(len(stress))
    d_s, h_s = _estresse(s, full)
    out["estresse"] = {
        "n": len(stress),
        "d": d_s,
        "nivel_h": h_s,
        "ic_mint": intervalo(
            replicas(s["mint"], lambda i: _estresse(s, i)[0], reps=reps, seed=seed)
        ),
        "ic_blocos": intervalo(
            replicas(s["bloco"], lambda i: _estresse(s, i)[0], reps=reps, seed=seed)
        ),
    }
    return out


def _contagem(xs: Sequence[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items()))
