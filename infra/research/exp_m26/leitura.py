"""`ler_h022(entrada)` — a leitura única da H-022, pura (§4).

0. As linhas entram em ordem canônica (braço, mint): a ordem física do export nunca muda um
   sorteio. A guarda anti-antecipação corre nas linhas dos três braços antes de qualquer conta.
1. T0 = seed + 48 h; mints do piloto (qualquer linha de R1 ou proposta de qualquer braço
   antes de T0) saem de tudo, para sempre.
2. Corte pelas inscrições elegíveis de C (sem desfecho); leitura L = corte + 2 h. **O export
   é o retrato em L**: o seu instante (`exportado_em`, o único relógio da leitura) tem de
   cair em [L, L + 1 h] — um export posterior pode trazer o que só chegou depois de L
   (fechamento processado tarde com `exit_at` antigo). As apostas são vistas como estavam
   em L, e o `completed_at`/`migrated_at` do token é o **conhecido em L** — a última
   mudança do histórico só de acréscimo com `recorded_at <= L` (`estado_token`, `0067`),
   nunca a linha corrente — e o export tem de provar que toda mudança carimbada até L
   estava visível nele (`provar_visibilidade`), senão é recusado.
3. Primária em C: classes, motivo único, denominadores, estimador estratificado, dois IC,
   permutação, robustez e estresse. Secundária H − L. Holm sobre os dois p. Rótulos.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any

from infra.research.exp_m26 import censura, estado_token, pacote, robustez
from infra.research.exp_m26.calendario import Corte, corte, t0_de
from infra.research.exp_m26.classes import Registro, registrar, verificar_relogio
from infra.research.exp_m26.constantes import (
    BRACOS,
    DIAGNOSTICO_CENSURA,
    JANELA_EXPORTACAO,
    MIN_ESTRATOS,
    MIN_FALSE,
    MIN_TRUE,
    MRE,
    P_NAO_TESTAVEL,
    RENT_SOL,
    REPS,
    RULE_SET_C,
    RULE_SET_H,
    RULE_SET_L,
    SEMENTE,
)
from infra.research.exp_m26.contabil import pnl_alternativo
from infra.research.exp_m26.estado_token import EstadoToken, ProvaDeVisibilidade
from infra.research.exp_m26.estimador import (
    Intervalo,
    estimar,
    ic_blocos,
    ic_mint,
    p_permutacao,
    unidades,
)
from infra.research.exp_m26.modelo import Oportunidade, na_leitura
from infra.research.exp_m26.veredito import decidir, denominadores, falhas_de_instrumento, holm


class ExportForaDaJanela(RuntimeError):
    """O export não foi tirado em [L, L + 1 h]: não é o retrato da leitura."""


@dataclass(frozen=True)
class Entrada:
    seed: datetime
    exportado_em: datetime
    """`now()` da transação do export — o instante do retrato."""
    oportunidades: tuple[Oportunidade, ...]
    """As linhas de R1 dos três braços, todas desde o seed."""
    propostas: tuple[tuple[str, str, datetime], ...]
    """`(rule_set_id, mint, 1.ª proposed_at)` de cada braço e mint — acha órfãs e piloto."""
    aposentadorias: Mapping[str, datetime | None]
    """`retired_at` dos três braços; a primeira antes do corte é a parada pela guarda."""
    estados: Mapping[str, EstadoToken]
    """O histórico de `completed_at`/`migrated_at` de cada mint com oportunidade."""
    prova: ProvaDeVisibilidade = ProvaDeVisibilidade()
    """A linha 'meta' do export: a prova de que tudo carimbado até L estava visível nele."""


def _em_l(o: Oportunidade, e: Entrada, leitura: datetime) -> Oportunidade:
    """A aposta como estava em L, com o estado do token conhecido em L."""
    a = na_leitura(o.aposta, leitura)
    if a is None:
        return replace(o, aposta=None)
    if o.mint not in e.estados:
        raise ValueError(f"export sem estado_token para {o.mint}")
    s = estado_token.em(e.estados[o.mint], leitura)
    return replace(
        o,
        aposta=replace(
            a,
            token_completed_at=s.completed_at,
            token_migrated_at=s.migrated_at,
            token_estado_via=s.via,
        ),
    )


def _iv(i: Intervalo) -> dict[str, Any]:
    return {**asdict(i), "finito": i.finito}


def _limpo(x: Any) -> Any:
    if isinstance(x, Intervalo):
        return _iv(x)
    if isinstance(x, dict):
        return {k: _limpo(v) for k, v in x.items()}  # type: ignore[misc]
    if isinstance(x, list | tuple):
        return [_limpo(v) for v in x]  # type: ignore[misc]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _piloto(e: Entrada, t0: datetime) -> set[str]:
    mints = {o.mint for o in e.oportunidades if o.evaluated_at < t0}
    return mints | {m for _, m, t in e.propostas if t < t0}


def _parada(e: Entrada) -> datetime | None:
    vistas = [t for rs, t in e.aposentadorias.items() if rs in BRACOS and t is not None]
    return min(vistas) if vistas else None


def _inscrita(o: Oportunidade) -> str | None:
    """A classe que conta para as metas do corte (não E, não U), sem olhar a aposta."""
    r = registrar(replace(o, aposta=None))
    return None if r.motivo in ("E", "U") else r.classe


def _primaria(regs: list[Registro], den: dict[str, Any], parada: bool, reps: int) -> dict[str, Any]:
    u, mints = censura.unidades_primarias(regs, estresse=False)
    est = estimar(u)
    bloqueios: list[tuple[str, str]] = []
    if parada:
        bloqueios.append(("instrumento", "coleta parada pela guarda (§6.8)"))
    bloqueios += [("instrumento", f) for f in falhas_de_instrumento(den)]
    if est.n_true < MIN_TRUE or est.n_false < MIN_FALSE:
        bloqueios.append(
            (
                "limite_de_dado",
                f"{est.n_true} true / {est.n_false} false avaliáveis "
                f"nos estratos com os dois grupos (mínimo {MIN_TRUE}/{MIN_FALSE})",
            )
        )
    if est.estratos < MIN_ESTRATOS:
        bloqueios.append(
            ("amostra", f"{est.estratos} estratos com os dois grupos < {MIN_ESTRATOS}")
        )
    im = ic_mint(u, mints, reps=reps, seed=SEMENTE)
    ib = ic_blocos(u, reps=reps, seed=SEMENTE)
    testavel = not bloqueios and im.finito and ib.finito
    p = p_permutacao(u, reps=reps, seed=SEMENTE) if testavel else P_NAO_TESTAVEL
    us, ms = censura.unidades_primarias(regs, estresse=True)
    es = estimar(us)
    estresse = {
        "d": es.d,
        "media_true": es.media_true,
        "ic_mint": ic_mint(us, ms, reps=reps, seed=SEMENTE),
        "ic_blocos": ic_blocos(us, reps=reps, seed=SEMENTE),
    }
    return {
        "d": est.d,
        "estratos": est.estratos,
        "n_true": est.n_true,
        "n_false": est.n_false,
        "media_true": est.media_true,
        "ic_mint": im,
        "ic_blocos": ib,
        "p": p,
        "testavel": testavel,
        "bloqueios": bloqueios,
        "estresse": estresse,
        "planalto": robustez.planalto(regs),
        "tercis": robustez.tercis(regs),
        "identidade": robustez.identidade(regs),
        "diagnosticos": {
            "d_true_c_a_menos_050": censura.diagnostico(regs, DIAGNOSTICO_CENSURA).d,
            "inversao_d0": censura.inversao(regs, 0.0),
            "inversao_mre": censura.inversao(regs, MRE),
            "grade_2d": censura.grade(regs),
        },
    }


def _condicoes_primaria(p: dict[str, Any], p_ok: bool) -> list[tuple[bool, str]]:
    s = p["estresse"]
    s_ok = (
        s["ic_mint"].finito
        and s["ic_blocos"].finito
        and min(s["ic_mint"].lo, s["ic_blocos"].lo) > 0
        and s["media_true"] > 0
    )
    return [
        (p["d"] >= MRE, f"D_linha {p['d']:+.4f} < MRE {MRE}"),
        (p_ok, f"p {p['p']:.4f} não sobrevive a Holm"),
        (p["media_true"] > 0, f"true não é lucrativo em nível ({p['media_true']:+.4f})"),
        (p["planalto"]["ok"], "planalto 0,10/0,25/0,50 falhou"),
        (p["tercis"]["ok"], "sinal em < 2 tercis avaliáveis de progresso"),
        (p["identidade"]["ok"], "cláusula de identidade (mcap_slope_15m) disparou ou sem dado"),
        (bool(s_ok), "não sobrevive ao estresse de censura (true C em perda integral)"),
    ]


def _condicoes_secundaria(s: dict[str, Any], p_ok: bool) -> list[tuple[bool, str]]:
    st = s.get("estresse", {})
    st_ok = (
        bool(st)
        and st["ic_mint"].finito
        and st["ic_blocos"].finito
        and (min(st["ic_mint"].lo, st["ic_blocos"].lo) > 0 and st["nivel_h"] > 0)
    )
    return [
        (s["d"] >= MRE, f"D_pacote {s['d']:+.4f} < MRE {MRE}"),
        (p_ok, f"p {s['p']:.4f} não sobrevive a Holm"),
        (s["nivel_h"] > 0, f"H não é lucrativo em nível ({s['nivel_h']:+.4f})"),
        (st_ok, "não sobrevive ao estresse dos três casos de par incompleto"),
    ]


def _pares(
    e: Entrada, ok: set[str], janela: tuple[datetime, datetime], leitura: datetime
) -> list[pacote.Par]:
    por: dict[str, dict[str, Oportunidade]] = {RULE_SET_L: {}, RULE_SET_H: {}}
    for o in e.oportunidades:
        if o.rule_set_id in por and o.mint in ok:
            por[o.rule_set_id][o.mint] = _em_l(o, e, leitura)
    inicio: dict[str, datetime] = {}
    for rs, m, t in e.propostas:
        if rs in por and m in ok and m not in por[rs]:
            inicio[m] = min(t, inicio.get(m, t))
    for rs in por:
        for m, o in por[rs].items():
            inicio[m] = min(o.evaluated_at, inicio.get(m, o.evaluated_at))
    return [
        pacote.parear(m, por[RULE_SET_L].get(m), por[RULE_SET_H].get(m))
        for m, t in sorted(inicio.items())
        if janela[0] <= t < janela[1]
    ]


def _contabil(regs: Sequence[Registro]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for rent in RENT_SOL:
        ys: list[float | None] = []
        base = [r for r in regs if r.motivo == "A" and r.classe in ("true", "false")]
        for r in base:
            alt = None if r.o.aposta is None else pnl_alternativo(r.o.aposta, rent)
            ys.append(None if alt is None else float(alt / r.o.aposta.size_sol))  # type: ignore[union-attr]
        u = unidades([r.bloco for r in base], [r.classe == "true" for r in base], ys)
        out[f"d_rent_{rent}"] = estimar(u).d
    return out


def ler_h022(e: Entrada, *, reps: int = REPS) -> dict[str, Any]:
    e = replace(
        e,
        oportunidades=tuple(sorted(e.oportunidades, key=lambda o: (o.rule_set_id, o.mint))),
        propostas=tuple(sorted(e.propostas)),
    )
    for o in e.oportunidades:
        verificar_relogio(o)
    t0 = t0_de(e.seed)
    piloto = _piloto(e, t0)
    c_ops = [o for o in e.oportunidades if o.rule_set_id == RULE_SET_C and o.mint not in piloto]
    inscricoes = [(o.evaluated_at, k) for o in c_ops if (k := _inscrita(o)) is not None]
    parada = _parada(e)
    c: Corte = corte(t0, inscricoes, parada=parada, agora=e.exportado_em)
    if e.exportado_em > c.leitura + JANELA_EXPORTACAO:
        raise ExportForaDaJanela(
            f"export em {e.exportado_em.isoformat()}, leitura em {c.leitura.isoformat()}: "
            f"fora da janela de {JANELA_EXPORTACAO}"
        )
    estado_token.provar_visibilidade(e.prova, leitura=c.leitura)
    janela = (t0, c.instante)
    regs = [
        registrar(_em_l(o, e, c.leitura)) for o in c_ops if janela[0] <= o.evaluated_at < janela[1]
    ]
    com_r1 = {(o.rule_set_id, o.mint) for o in e.oportunidades}
    orfas_c = {
        m
        for rs, m, t in e.propostas
        if rs == RULE_SET_C
        and (rs, m) not in com_r1
        and m not in piloto
        and janela[0] <= t < janela[1]
    }
    den = denominadores(regs, orfas_c=len(orfas_c))
    parou = c.motivo == "parada_guarda"
    prim = _primaria(regs, den, parou, reps)
    todos = {o.mint for o in e.oportunidades} | {m for _, m, _ in e.propostas}
    sec = pacote.secundaria(_pares(e, todos - piloto, janela, c.leitura), reps=reps, seed=SEMENTE)
    p2 = sec["p"] if sec["testavel"] and not parou else P_NAO_TESTAVEL
    ok1, ok2 = holm(prim["p"], p2)
    prim["rotulo_final"] = decidir(
        prim["bloqueios"], prim["ic_mint"], prim["ic_blocos"], _condicoes_primaria(prim, ok1)
    )
    bloq2 = [("instrumento", "coleta parada pela guarda (§6.8)")] if parou else []
    if sec["motivo_nao_testavel"]:
        bloq2.append((sec["motivo_nao_testavel"].split(":")[0], sec["motivo_nao_testavel"]))
    vazio = Intervalo(math.nan, math.nan, 1.0, 0)
    sec_r = decidir(
        bloq2,
        sec.get("ic_mint", vazio),
        sec.get("ic_blocos", vazio),
        _condicoes_secundaria(sec, ok2),
    )
    motivos = {f"{r.motivo}:{r.detalhe}": 0 for r in regs}
    for r in regs:
        motivos[f"{r.motivo}:{r.detalhe}"] += 1
    rel = {
        "hipotese": "H-022",
        "seed": e.seed.isoformat(),
        "t0": t0.isoformat(),
        "corte": {"instante": c.instante.isoformat(), "motivo": c.motivo},
        "leitura": c.leitura.isoformat(),
        "exportado_em": e.exportado_em.isoformat(),
        "funil": {
            "mints_do_piloto": len(piloto),
            "c_inscritas": len(regs),
            "motivos": dict(sorted(motivos.items())),
            "estado_token_via": dict(
                sorted(Counter(r.o.aposta.token_estado_via for r in regs if r.o.aposta).items())
            ),
        },
        "denominadores": den,
        "primaria": {
            **{k: v for k, v in prim.items() if k != "rotulo_final"},
            **prim["rotulo_final"],
        },
        "secundaria": {**sec, **sec_r, "p_na_familia": p2},
        "holm": {"p": [prim["p"], p2], "sobrevive": [ok1, ok2]},
        "descritivos": {**robustez.sensibilidades(regs), **_contabil(regs)},
        "rotulo_h022": prim["rotulo_final"]["rotulo"],
    }
    return _limpo(rel)


__all__ = ["Entrada", "ExportForaDaJanela", "ler_h022"]
