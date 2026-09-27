"""O rótulo da H-022 (§3 refutação, §4 "Rótulos"): precedência, denominadores, Holm e a
regra de concordância dos dois IC — a mesma lógica para os dois contrastes.

Ordem congelada: parada pela guarda → instrumento (tetos de `desconhecida`, sem proposta,
união das falhas) → limite de dado / amostra → IC não finito → CONFIRMA (toda a previsão e
`min(L_mint, L_blocos) > 0`) → REFUTA (`max(U_mint, U_blocos) < MRE`) → NÃO CONFIRMA.
Um IC não finito (inclusive > 1 % de réplicas inválidas) impede CONFIRMA **e** REFUTA.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from infra.research.exp_m26.classes import Registro
from infra.research.exp_m26.constantes import (
    ALPHA,
    MRE,
    TETO_DESCONHECIDA,
    TETO_FALHA,
    TETO_SEM_PROPOSTA,
)
from infra.research.exp_m26.estimador import Intervalo
from infra.research.stats import adjust_family
from infra.research.verdict import CONFIRMA, NAO_CONFIRMA, REFUTA

_GRUPOS = ("true", "false")


def concordancia(ic_mint: Intervalo, ic_blocos: Intervalo) -> tuple[bool, bool]:
    """`(os dois inferiores > 0, os dois superiores < MRE)` — nunca pela largura."""
    confirma = min(ic_mint.lo, ic_blocos.lo) > 0
    refuta = max(ic_mint.hi, ic_blocos.hi) < MRE
    return confirma, refuta


def holm(p_primaria: float, p_secundaria: float) -> tuple[bool, bool]:
    fam = adjust_family([p_primaria, p_secundaria], alpha=ALPHA)
    return fam.holm_survives[0], fam.holm_survives[1]


def denominadores(regs: Sequence[Registro], *, orfas_c: int) -> dict[str, Any]:
    """A equação congelada por classe: N_bruto = E + N_elegivel; N_elegivel = I+F+C+A.
    `desconhecida`: U / (N_elegivel_true + N_elegivel_false + U), U sem os E, com as
    propostas de C sem linha em R1 (`orfas_c`, classe incognoscível)."""
    out: dict[str, Any] = {}
    for g in _GRUPOS:
        cont = {m: sum(1 for r in regs if r.classe == g and r.motivo == m) for m in "EIFCA"}
        eleg = cont["I"] + cont["F"] + cont["C"] + cont["A"]
        out[g] = {
            **cont,
            "N_bruto": cont["E"] + eleg,
            "N_elegivel": eleg,
            "taxa_I": cont["I"] / eleg if eleg else None,
            "taxa_falha": (cont["I"] + cont["F"] + cont["C"]) / eleg if eleg else None,
        }
    u = sum(1 for r in regs if r.motivo == "U") + orfas_c
    base = out["true"]["N_elegivel"] + out["false"]["N_elegivel"] + u
    out["U"] = u
    out["orfas_c"] = orfas_c
    out["E_desconhecida"] = sum(1 for r in regs if r.motivo == "E" and r.classe == "desconhecida")
    out["taxa_U"] = u / base if base else None
    out["out_of_range"] = sum(1 for r in regs if r.detalhe_classe == "out_of_range")
    out["flat"] = sum(1 for r in regs if r.detalhe_classe == "flat")
    return out


def falhas_de_instrumento(den: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if den["taxa_U"] is None:
        out.append("sem oportunidade inscrita: taxa de desconhecida não estimável")
    elif den["taxa_U"] > TETO_DESCONHECIDA:
        out.append(f"desconhecida {den['taxa_U']:.3f} > {TETO_DESCONHECIDA}")
    for g in _GRUPOS:
        d = den[g]
        if d["N_elegivel"] == 0:
            out.append(f"nenhuma oportunidade {g} elegível: tetos não estimáveis")
            continue
        if d["taxa_I"] > TETO_SEM_PROPOSTA:
            out.append(
                f"sem_proposta por instrumento em {g} {d['taxa_I']:.3f} > {TETO_SEM_PROPOSTA}"
            )
        if d["taxa_falha"] > TETO_FALHA:
            out.append(f"falha (I+F+C) em {g} {d['taxa_falha']:.3f} > {TETO_FALHA}")
    return out


def decidir(
    bloqueios: Sequence[tuple[str, str]],
    ic_mint: Intervalo,
    ic_blocos: Intervalo,
    condicoes: Sequence[tuple[bool, str]],
) -> dict[str, Any]:
    """`bloqueios` = `(categoria, motivo)` já na ordem da precedência; `condicoes` = o
    resto da previsão (MRE, Holm, nível, planalto, tercis, identidade, estresse)."""
    if bloqueios:
        return {
            "rotulo": NAO_CONFIRMA,
            "categoria": bloqueios[0][0],
            "motivos": [m for _, m in bloqueios],
        }
    if not (ic_mint.finito and ic_blocos.finito):
        return {
            "rotulo": NAO_CONFIRMA,
            "categoria": "ic_nao_finito",
            "motivos": [f"IC por mint {ic_mint} / por blocos {ic_blocos}: sem inferência"],
        }
    confirma_ic, refuta_ic = concordancia(ic_mint, ic_blocos)
    falhas = [txt for ok, txt in condicoes if not ok]
    if not confirma_ic:
        falhas.append(f"min(L_mint, L_blocos) = {min(ic_mint.lo, ic_blocos.lo):+.4f} não é > 0")
    if not falhas:
        return {"rotulo": CONFIRMA, "categoria": "previsao", "motivos": []}
    if refuta_ic:
        return {
            "rotulo": REFUTA,
            "categoria": "previsao",
            "motivos": [
                f"max(U_mint, U_blocos) = {max(ic_mint.hi, ic_blocos.hi):+.4f} < MRE {MRE}: "
                "refuta um efeito desse tamanho, não qualquer efeito"
            ],
        }
    return {"rotulo": NAO_CONFIRMA, "categoria": "previsao", "motivos": falhas}
