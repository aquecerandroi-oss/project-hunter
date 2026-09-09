"""T3.66 / EXP-0024 — a medição: validação, os dois controles e os dois testes.

Ordem dos atos, e ela importa:

1. **validar** — recaminhar o plano *da própria decisão* com `walker.walk` e exigir
   que `result` e `r_ex_funding` batam com o que `signal_outcomes` persistiu. Se não
   bater, nada abaixo pode ser lido (critério congelado no EXP-0024);
2. **C1** — o contrarian lag-1 na **mesma** barra;
3. **C2** — a mesma regra em até `K = 20` barras sorteadas, pareadas por
   (mercado, hora UTC), sorteio determinístico por md5;
4. **testar** — bootstrap por blocos de dia e Holm.

Manivela: ``uv run python .claude/state/exp-drafts/t366/rodar.py``
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from blocos import Estimativa, holm, media_por_blocos  # noqa: E402
from controle import (  # noqa: E402
    BARRA,
    CUSTOS,
    MINUTO,
    Serie,
    plano_do_controle,
    r_sem_funding,
    sinal,
    utc,
)
from hunter_strategy_worker.progress import Progress, TrackingPlan  # noqa: E402
from hunter_strategy_worker.walker import walk  # noqa: E402

RAIZ = Path(__file__).resolve().parent
DECISOES = RAIZ / "decisoes.csv"
VELAS = RAIZ / "velas.csv.gz"
K = 20
BLOCO_MIN = 30
"""Minutos por leva de velas. ``walk`` é um fold resumível, então caminhar em levas
de 30 min evita construir 241 ``Bar`` (quatro ``Decimal`` cada) para um stop que
disparou no quinto minuto — mesmo resultado, uma fração do custo."""


# --------------------------------------------------------------------- dados


def carregar_velas() -> dict[str, Serie]:
    series: dict[str, Serie] = defaultdict(Serie)
    with gzip.open(VELAS, "rt", encoding="utf-8", newline="") as fh:
        for linha in csv.DictReader(fh):
            series[linha["market_id"]].adicionar(
                utc(linha["t"]),
                float(linha["open"]),
                float(linha["high"]),
                float(linha["low"]),
                float(linha["close"]),
            )
    return dict(series)


@dataclass(frozen=True)
class Decisao:
    signal_id: str
    versao: str
    coorte: str
    market_id: str
    symbol: str
    bar: datetime
    entrada: datetime
    dia_br: str
    hora_utc: int
    stop: Decimal
    alvo1: Decimal
    p_entry: Decimal
    risco: Decimal
    motivo: str
    r_exf: float
    r_net: float
    horizonte_s: int

    @property
    def risco_pct(self) -> Decimal:
        return self.risco / self.p_entry

    @property
    def tr(self) -> Decimal:
        return (self.alvo1 - self.p_entry) / self.risco


def carregar_decisoes() -> list[Decisao]:
    with DECISOES.open(newline="", encoding="utf-8") as fh:
        return [
            Decisao(
                signal_id=l["signal_id"],
                versao=l["versao"],
                coorte=l["coorte"],
                market_id=l["market_id"],
                symbol=l["symbol"],
                bar=utc(l["bar_utc"]),
                entrada=utc(l["entrada_utc"]),
                dia_br=l["dia_br"],
                hora_utc=int(l["hora_utc"]),
                stop=Decimal(l["stop"]),
                alvo1=Decimal(l["alvo1"]),
                p_entry=Decimal(l["p_entry"]),
                risco=Decimal(l["risco"]),
                motivo=l["motivo"],
                r_exf=float(l["r_exf"]),
                r_net=float(l["r_net"]),
                horizonte_s=int(l["horizonte_s"]),
            )
            for l in csv.DictReader(fh)
        ]


# ------------------------------------------------------------------ caminhar


def caminhar_em_levas(serie: Serie, plano: TrackingPlan) -> Progress | None:
    """Caminha até terminar. ``None`` = buraco antes do fim (**censurado**)."""
    total = plano.horizon_s // 60 + 1
    progresso = Progress.start()
    inicio = plano.entry_bar_open
    andados = 0
    while andados < total and not progresso.finished:
        levar = min(BLOCO_MIN, total - andados)
        velas = serie.janela(inicio + timedelta(minutes=andados), levar)
        if velas is None:
            return None
        progresso = walk(plano, progresso, velas)  # fold resumivel: a leva seguinte continua de onde parou
        andados += levar
    return progresso if progresso.finished else None


def plano_da_decisao(d: Decisao) -> TrackingPlan:
    return TrackingPlan(
        entry_bar_open=d.entrada,
        stop=d.stop,
        target1=d.alvo1,
        horizon_s=d.horizonte_s,
        costs=CUSTOS,
    )


# ------------------------------------------------------------------ controles


def grade_de_baixas(serie: Serie) -> dict[int, list[datetime]]:
    """Por hora UTC, os fechamentos de 15 min cujo **próprio balde fechou em baixa**.

    A grade é a do ``date_bin('15 min', ..., 'epoch')``: fechamentos em ``:00``,
    ``:15``, ``:30`` e ``:45``.
    """
    minutos = serie.minutos()
    if not minutos:
        return {}
    inicio, fim = min(minutos), max(minutos)
    primeiro = inicio + BARRA - timedelta(minutes=inicio.minute % 15) if inicio.minute % 15 else inicio + BARRA
    grade: dict[int, list[datetime]] = defaultdict(list)
    t = primeiro
    while t <= fim:
        balde = serie.balde15(t)
        if balde is not None and sinal(balde) == -1:
            grade[t.hour].append(t)
        t += BARRA
    return dict(grade)


def sorteio(d: Decisao, candidatas: list[datetime]) -> list[datetime]:
    """Ordem pseudo-aleatória **determinística e reproduzível** (md5), congelada no EXP-0024."""
    return sorted(
        candidatas,
        key=lambda b: hashlib.md5(
            f"{d.signal_id}{d.market_id}{b.isoformat()}".encode()
        ).hexdigest(),
    )


# --------------------------------------------------------------------- saída


def linha(nome: str, e: Estimativa) -> str:
    return (
        f"{nome:<34} n {e.n:>4} | dias {e.dias:>2} | ponto {e.ponto:+.4f} | "
        f"IC95 [{e.ic95[0]:+.4f}; {e.ic95[1]:+.4f}] | p {e.p_bicaudal:.4f}"
    )


def main() -> None:  # noqa: C901
    print("carregando velas…", flush=True)
    series = carregar_velas()
    decisoes = carregar_decisoes()
    print(f"mercados {len(series)} | velas {sum(len(s) for s in series.values())} | decisões {len(decisoes)}")

    grades = {mid: grade_de_baixas(s) for mid, s in series.items()}

    validadas: list[tuple[Decisao, float]] = []
    divergencias: list[str] = []
    sem_velas = 0
    max_dr = 0.0
    print("validando a população (recaminhando o plano da própria decisão)…", flush=True)
    for d in decisoes:
        serie = series.get(d.market_id)
        if serie is None:
            sem_velas += 1
            continue
        prog = caminhar_em_levas(serie, plano_da_decisao(d))
        if prog is None or prog.exit_base is None:
            sem_velas += 1
            continue
        r = r_sem_funding(plano_da_decisao(d), prog)
        assert r is not None
        dr = abs(float(r) - d.r_exf)
        max_dr = max(max_dr, dr)
        if prog.result.value != d.motivo or dr > 1e-6:
            divergencias.append(
                f"{d.signal_id} {d.symbol} {d.versao}: motivo {prog.result.value}!={d.motivo} "
                f"R {float(r):+.6f} vs {d.r_exf:+.6f}"
            )
        validadas.append((d, float(r)))

    print(f"validação: {len(validadas)} recaminhadas | sem velas/censuradas {sem_velas} | "
          f"divergências {len(divergencias)} | max |ΔR| {max_dr:.3e}")
    for x in divergencias[:20]:
        print("   DIVERGE", x)

    print("controles…", flush=True)
    saida: list[dict[str, object]] = []
    for d, _ in validadas:
        serie = series[d.market_id]
        balde = serie.balde15(d.bar)
        s = None if balde is None else sinal(balde)

        # ---- C1: mesma barra, entrada na convenção da regra (barra + 1 min)
        r_c1: float | None = 0.0
        if s == -1:
            plano1 = plano_do_controle(
                entrada=d.bar + MINUTO,
                abertura=Decimal(repr(serie.vela(d.bar + MINUTO)[0]))
                if serie.vela(d.bar + MINUTO)
                else Decimal(0),
                risco_pct=d.risco_pct,
                tr=d.tr,
                horizonte_s=d.horizonte_s,
            )
            prog1 = (
                caminhar_em_levas(serie, plano1) if serie.vela(d.bar + MINUTO) is not None else None
            )
            r1 = None if prog1 is None else r_sem_funding(plano1, prog1)
            r_c1 = None if r1 is None else float(r1)

        # ---- C2: a mesma regra em até K barras pareadas por (mercado, hora UTC)
        candidatas = [b for b in grades[d.market_id].get(d.hora_utc, []) if b != d.bar]
        rs: list[float] = []
        for b in sorteio(d, candidatas):
            if len(rs) >= K:
                break
            abertura = serie.vela(b + MINUTO)
            if abertura is None:
                continue
            plano2 = plano_do_controle(
                entrada=b + MINUTO,
                abertura=Decimal(repr(abertura[0])),
                risco_pct=d.risco_pct,
                tr=d.tr,
                horizonte_s=d.horizonte_s,
            )
            prog2 = caminhar_em_levas(serie, plano2)
            if prog2 is None:
                continue
            r2 = r_sem_funding(plano2, prog2)
            if r2 is not None:
                rs.append(float(r2))

        saida.append(
            {
                "signal_id": d.signal_id,
                "versao": d.versao,
                "coorte": d.coorte,
                "symbol": d.symbol,
                "dia_br": d.dia_br,
                "bar_utc": d.bar.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "hora_utc": d.hora_utc,
                "sinal": "" if s is None else s,
                "motivo": d.motivo,
                "r_exf": f"{d.r_exf:.6f}",
                "r_net": f"{d.r_net:.6f}",
                "r_c1": "" if r_c1 is None else f"{r_c1:.6f}",
                "n_c2": len(rs),
                "r_c2": "" if not rs else f"{sum(rs) / len(rs):.6f}",
                "risco_pct": f"{float(d.risco_pct):.6f}",
            }
        )

    destino = RAIZ / "pareado.csv"
    with destino.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(saida[0].keys()))
        w.writeheader()
        w.writerows(saida)
    print(f"escrito {destino} ({len(saida)} linhas)")

    # ------------------------------------------------------------- os testes
    recortes: dict[str, list[dict[str, object]]] = {"AGREGADO": saida}
    for v in ("v1", "v2", "v6", "v10"):
        recortes[v] = [x for x in saida if x["versao"] == v]

    print()
    for nome, linhas in recortes.items():
        if not linhas:
            continue
        com_sinal = [x for x in linhas if x["sinal"] != ""]
        baixas = [x for x in com_sinal if x["sinal"] == -1]
        dojis = [x for x in com_sinal if x["sinal"] == 0]
        obs_a = [
            (str(x["dia_br"]), float(x["r_exf"]) - float(x["r_c1"]))
            for x in linhas
            if x["r_c1"] != ""
        ]
        obs_b = [(str(x["dia_br"]), float(x["r_exf"])) for x in linhas]
        obs_b_net = [(str(x["dia_br"]), float(x["r_net"])) for x in linhas]
        obs_c2 = [
            (str(x["dia_br"]), float(x["r_exf"]) - float(x["r_c2"]))
            for x in linhas
            if x["r_c2"] != ""
        ]
        ea = media_por_blocos(obs_a)
        eb = media_por_blocos(obs_b)
        eb_net = media_por_blocos(obs_b_net)
        ec = media_por_blocos(obs_c2)
        ajust2 = holm({"a_incremental_C1": ea.p_bicaudal, "b_liquido_20bps": eb.p_bicaudal})
        ajust3 = holm(
            {
                "a_incremental_C1": ea.p_bicaudal,
                "b_liquido_20bps": eb.p_bicaudal,
                "c_incremental_C2": ec.p_bicaudal,
            }
        )
        conc = len(baixas) / len(com_sinal) if com_sinal else float("nan")
        r_c2_medio = (
            sum(float(x["r_c2"]) for x in linhas if x["r_c2"] != "")
            / max(1, len([x for x in linhas if x["r_c2"] != ""]))
        )
        print(f"=== {nome} ===")
        print(
            f"  decisões {len(linhas)} | com balde de 15 m {len(com_sinal)} | "
            f"baixa {len(baixas)} ({conc:.1%}) | doji {len(dojis)} | "
            f"alta {len(com_sinal) - len(baixas) - len(dojis)}"
        )
        print(f"  pool C2: média de sorteios usados {sum(int(x['n_c2']) for x in linhas)/len(linhas):.1f} | R médio do controle {r_c2_medio:+.4f}")
        print("  " + linha("(a) Δ1 = R − C1 (mesma barra)", ea))
        print("  " + linha("(b) expectancy r_ex_funding", eb))
        print("  " + linha("    [2ª leitura] r_net c/ funding", eb_net))
        print("  " + linha("(c) Δ2 = R − C2 (barras pareadas)", ec))
        print(f"  Holm (família de 2): {', '.join(f'{k}={v:.4f}' for k, v in ajust2.items())}")
        print(f"  Holm (sensibilidade, 3): {', '.join(f'{k}={v:.4f}' for k, v in ajust3.items())}")
        print()


if __name__ == "__main__":
    main()
