"""As condições de robustez da previsão (§3) e as sensibilidades descritivas.

- **Planalto:** o sinal de D repete com teto de distância 0,10, 0,25 e 0,50 na definição de
  `true` (classes e estratos refeitos; D indefinido não satisfaz).
- **Tercis de `curve_progress_pct`:** cortes por posto sobre as oportunidades elegíveis de
  classe conhecida (sem desfecho; desempate pelo mint); um tercil é avaliável com ≥ 20
  avaliáveis por grupo **nos estratos com os dois grupos dentro do tercil**; satisfaz com
  ≥ 2 tercis avaliáveis de D > 0.
- **Identidade:** na população comum (avaliáveis dos estratos válidos da primária, sem os
  slopes ausentes, só nos blocos que têm os dois grupos **nas duas divisões**), D_slope
  (`mcap_slope_15m > 0` contra ≤ 0) e D_linha são refeitos com o mesmo estimador; dispara se
  D_slope ≥ D_linha comparável. Slope ausente > 20 % ou D indefinido não satisfaz (Astra,
  revisão do J).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from infra.research.exp_m26.classes import Registro, classe_linha
from infra.research.exp_m26.constantes import (
    MIN_POR_GRUPO_TERCIL,
    MIN_TERCIS_COM_SINAL,
    TETO_SLOPE_AUSENTE,
    TETOS_PLANALTO,
)
from infra.research.exp_m26.estimador import estimar, unidades

_CONHECIDAS = ("true", "false")


def _avaliaveis(regs: Sequence[Registro]) -> list[Registro]:
    return [r for r in regs if r.motivo == "A" and r.classe in _CONHECIDAS]


def _d(regs: Sequence[Registro], grupo: Callable[[Registro], bool]) -> Any:
    return estimar(unidades([r.bloco for r in regs], [grupo(r) for r in regs], [r.y for r in regs]))


def planalto(regs: Sequence[Registro]) -> dict[str, Any]:
    base = _avaliaveis(regs)
    out: dict[str, Any] = {}
    for teto in TETOS_PLANALTO:
        pares = [(r, classe_linha(r.o, teto)[0]) for r in base]
        pares = [(r, c) for r, c in pares if c in _CONHECIDAS]
        u = unidades(
            [r.bloco for r, _ in pares], [c == "true" for _, c in pares], [r.y for r, _ in pares]
        )
        out[str(teto)] = estimar(u).d
    out["ok"] = all(math.isfinite(out[str(t)]) and out[str(t)] > 0 for t in TETOS_PLANALTO)
    return out


def tercis(regs: Sequence[Registro]) -> dict[str, Any]:
    pop = [
        r
        for r in regs
        if r.motivo not in ("E", "U")
        and r.classe in _CONHECIDAS
        and r.o.curve_progress_pct is not None
    ]
    pop.sort(key=lambda r: (r.o.curve_progress_pct, r.o.mint))
    n = len(pop)
    grupos: list[list[Registro]] = [[], [], []]
    for i, r in enumerate(pop):
        grupos[min(2, 3 * i // n)].append(r)
    linhas: list[dict[str, Any]] = []
    for g in grupos:
        e = _d(_avaliaveis(g), lambda r: r.classe == "true")
        ok = e.n_true >= MIN_POR_GRUPO_TERCIL and e.n_false >= MIN_POR_GRUPO_TERCIL
        avaliavel = ok and math.isfinite(e.d)
        linhas.append(
            {
                "n": len(g),
                "n_true": e.n_true,
                "n_false": e.n_false,
                "d": e.d,
                "avaliavel": avaliavel,
            }
        )
    positivos = sum(1 for t in linhas if t["avaliavel"] and t["d"] > 0)
    return {"tercis": linhas, "positivos": positivos, "ok": positivos >= MIN_TERCIS_COM_SINAL}


def _nos_estratos_validos(regs: Sequence[Registro]) -> list[Registro]:
    base = _avaliaveis(regs)
    por_bloco: dict[str, set[str]] = {}
    for r in base:
        por_bloco.setdefault(r.bloco, set()).add(r.classe)
    return [r for r in base if por_bloco[r.bloco] == set(_CONHECIDAS)]


def identidade(regs: Sequence[Registro]) -> dict[str, Any]:
    pop = _nos_estratos_validos(regs)
    ausentes = sum(1 for r in pop if r.o.mcap_slope_15m is None)
    frac = ausentes / len(pop) if pop else math.nan
    comum = [r for r in pop if r.o.mcap_slope_15m is not None]

    def sobe(r: Registro) -> bool:
        return bool(r.o.mcap_slope_15m is not None and r.o.mcap_slope_15m > 0)

    def com_os_dois(grupo: Callable[[Registro], bool]) -> set[str]:
        lados: dict[str, set[bool]] = {}
        for r in comum:
            lados.setdefault(r.bloco, set()).add(grupo(r))
        return {b for b, s in lados.items() if len(s) == 2}

    suporte = com_os_dois(lambda r: r.classe == "true") & com_os_dois(sobe)
    comum = [r for r in comum if r.bloco in suporte]
    d_linha = _d(comum, lambda r: r.classe == "true").d
    d_slope = _d(comum, sobe).d
    ok = (
        math.isfinite(frac)
        and frac <= TETO_SLOPE_AUSENTE
        and math.isfinite(d_linha)
        and math.isfinite(d_slope)
        and d_slope < d_linha
    )
    return {"ausentes": frac, "d_linha_comparavel": d_linha, "d_slope": d_slope, "ok": ok}


# ------------------------------------------------------------------ descritivos


def sensibilidades(regs: Sequence[Registro]) -> dict[str, Any]:
    """Descritivo, nunca rótulo: `false` só traçável, covariável das apostas anteriores,
    `comprou_no_topo` (pico ≤ custo) por classe e o D global sem estratos."""
    base = _avaliaveis(regs)
    tracavel = [r for r in base if r.classe == "true" or r.detalhe_classe == "tracada"]
    out: dict[str, Any] = {
        "d_false_so_tracavel": _d(tracavel, lambda r: r.classe == "true").d,
        "d_sem_aposta_anterior": _d(
            [r for r in base if not r.o.prior_other_bet], lambda r: r.classe == "true"
        ).d,
        "d_com_aposta_anterior": _d(
            [r for r in base if r.o.prior_other_bet], lambda r: r.classe == "true"
        ).d,
    }
    for c in _CONHECIDAS:
        grupo = [r for r in base if r.classe == c]
        ys = [r.y for r in grupo if r.y is not None]
        out[f"media_global_{c}"] = sum(ys) / len(ys) if ys else math.nan
        topo = [r for r in grupo if r.o.aposta is not None and r.o.aposta.high_water_x is not None]
        hits = sum(
            1
            for r in topo
            if r.o.aposta and r.o.aposta.high_water_x and r.o.aposta.high_water_x <= 1
        )
        out[f"comprou_no_topo_{c}"] = hits / len(topo) if topo else math.nan
    out["d_global"] = out["media_global_true"] - out["media_global_false"]
    t, f = out["comprou_no_topo_true"], out["comprou_no_topo_false"]
    out["comprou_no_topo_razao_ok"] = bool(math.isfinite(t) and math.isfinite(f) and t <= 0.75 * f)
    return out
