"""A manivela da T3.60: roda o simulador e imprime as tabelas da nota.

Uso: `uv run python .claude/state/exp-drafts/t360/roda.py`

Nada aqui decide nada — só chama `carteira.simular` com as configurações do
brief e formata. Os limites saem sempre de `RiskLimits.model_validate` sobre o
`PAPER_V1`; nenhum limiar é redigitado neste arquivo.
"""

from __future__ import annotations

import csv
import itertools
import os
import statistics
import sys
from collections.abc import Sequence
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "t342-blocos"))

from blocos import Decisao, contraste_por_piso
from carteira import (
    CAMBIO_BRL,
    EQUITY_100K,
    Config,
    Resultado,
    deduplicar,
    ler_populacao,
    simular,
)

AQUI = os.path.dirname(os.path.abspath(__file__))
POP = os.path.join(AQUI, "populacao.csv")

RISCOS = (Decimal("0.0025"), Decimal("0.005"), Decimal("0.01"))
AGREGADOS = (Decimal("0.01"), Decimal("0.02"), Decimal("0.04"))
VAGAS = (5, 10, 20)
CAPITAIS = {"R$100k": EQUITY_100K, "R$400k": EQUITY_100K * 4}


def brl(usdt: Decimal) -> Decimal:
    return usdt * CAMBIO_BRL


def q(valores: Sequence[Decimal], p: float) -> Decimal:
    if not valores:
        return Decimal(0)
    ordenados = sorted(valores)
    idx = min(len(ordenados) - 1, max(0, int(round(p * (len(ordenados) - 1)))))
    return ordenados[idx]


def linha(*celulas: object) -> str:
    return " | ".join(str(c) for c in celulas)


def resumo(res: Resultado, dias: int) -> dict[str, object]:
    r_dia = list(res.r_por_dia.values())
    dd_usdt, dd_pct = res.drawdown_maximo()
    usdt_por_r = [f.usdt_por_r for f in res.fechadas]
    return {
        "candidatas": len(res.registros),
        "aprovadas": len(res.aprovadas),
        "fechadas": len(res.fechadas),
        "ops_dia": Decimal(len(res.fechadas)) / Decimal(max(1, dias)),
        "r_total": res.r_total,
        "r_dia_medio": (res.r_total / Decimal(max(1, dias))),
        "r_p10": q(r_dia, 0.10),
        "r_p50": q(r_dia, 0.50),
        "r_p90": q(r_dia, 0.90),
        "pior_dia": min(r_dia) if r_dia else Decimal(0),
        "usdt_por_r_p50": q(usdt_por_r, 0.50),
        "pnl_usdt": res.pnl_total,
        "dd_usdt": dd_usdt,
        "dd_pct": dd_pct,
        "latch": res.latch_em,
        "recusas": res.recusas_por_motivo,
        "limitantes": res.limitantes,
    }


def main() -> None:
    pop = ler_populacao(POP)
    prospectiva = [s for s in pop if s.coorte == "prospective"]
    replay = [s for s in pop if s.coorte == "replay"]
    hoje = [s for s in prospectiva if s.dia_br == "2026-09-09"]

    print("=" * 100)
    print("T3.60 — a familia mean_reversion como UMA carteira sob o motor real")
    print("=" * 100)

    # ------------------------------------------------------------------ #
    print("\n== 1. populacao e o pooling ==")
    for nome, grupo in (("prospectiva", prospectiva), ("replay", replay), ("hoje 09/09", hoje)):
        unicos, creditos = deduplicar(grupo)
        dias = len({s.dia_br for s in grupo})
        print(
            linha(
                f"{nome:<12}",
                f"n={len(grupo):>4}",
                f"apostas={len(unicos):>4}",
                f"pooling={len(grupo) / max(1, len(unicos)):>5.2f}x",
                f"dias={dias:>2}",
                f"mercados={len({s.symbol for s in grupo}):>3}",
                f"versoes={len({s.versao for s in grupo}):>2}",
                f"R_bruto_soma={sum((s.r_net for s in grupo), Decimal(0)):>8.2f}",
                f"R_unico_soma={sum((s.r_net for s in unicos), Decimal(0)):>8.2f}",
            )
        )
        if nome == "hoje 09/09":
            print("   creditos do dedupe (quem levou a aposta):", dict(sorted(creditos.items())))

    # ------------------------------------------------------------------ #
    print("\n== 2. quantos sinais o motor recusa ANTES de qualquer limite de carteira ==")
    print("   (checks de admissao que so dependem do proprio sinal/mercado)")
    for nome, grupo in (("prospectiva", prospectiva), ("replay", replay)):
        unicos, _ = deduplicar(grupo)
        fora_banda = [s for s in unicos if not (Decimal("0.003") <= s.risco_pct <= Decimal("0.03"))]
        sem_janela = [s for s in unicos if s.barras_30 < 30]
        fina = [s for s in unicos if (s.vol_24h or Decimal(0)) < Decimal(50_000_000)]
        print(
            linha(
                f"{nome:<12}",
                f"apostas={len(unicos):>4}",
                f"stop fora de [0,3%;3%]={len(fora_banda):>4} ({100 * len(fora_banda) / max(1, len(unicos)):.1f}%)",
                f"vol24h<50M={len(fina):>4} ({100 * len(fina) / max(1, len(unicos)):.1f}%)",
                f"janela 30min incompleta={len(sem_janela):>3}",
            )
        )

    # ------------------------------------------------------------------ #
    print("\n== 3. varredura de configuracoes (populacao prospectiva 08-09/09) ==")
    print(
        linha(
            "risco%",
            "agreg%",
            "vagas",
            "cand",
            "aprov",
            "ops/dia",
            "R/dia",
            "R p10",
            "R p50",
            "R p90",
            "pior dia R",
            "USDT/R p50",
            "PnL USDT",
            "DD USDT",
            "DD%",
            "travou",
        )
    )
    dias_p = len({s.dia_br for s in prospectiva})
    linhas_csv: list[dict[str, object]] = []
    for risco, agregado, vagas in itertools.product(RISCOS, AGREGADOS, VAGAS):
        cfg = Config(
            risk_per_trade_pct=risco,
            max_aggregate_planned_risk_pct=agregado,
            max_concurrent_positions=vagas,
        )
        res = simular(prospectiva, cfg)
        r = resumo(res, dias_p)
        print(
            linha(
                f"{risco * 100:>5.2f}",
                f"{agregado * 100:>5.1f}",
                f"{vagas:>5}",
                f"{r['candidatas']:>4}",
                f"{r['aprovadas']:>5}",
                f"{r['ops_dia']:>7.1f}",
                f"{r['r_dia_medio']:>+7.2f}",
                f"{r['r_p10']:>+6.2f}",
                f"{r['r_p50']:>+6.2f}",
                f"{r['r_p90']:>+6.2f}",
                f"{r['pior_dia']:>+10.2f}",
                f"{r['usdt_por_r_p50']:>10.2f}",
                f"{r['pnl_usdt']:>+8.2f}",
                f"{r['dd_usdt']:>7.2f}",
                f"{r['dd_pct'] * 100:>5.2f}",
                "sim" if r["latch"] else "nao",
            )
        )
        linhas_csv.append(
            {
                "coorte": "prospectiva",
                "risco_pct": str(risco),
                "agregado_pct": str(agregado),
                "vagas": vagas,
                **{k: str(v) for k, v in r.items() if k not in ("recusas", "limitantes")},
                "recusas": ";".join(f"{k}={v}" for k, v in r["recusas"].items()),  # type: ignore[union-attr]
                "limitantes": ";".join(f"{k}={v}" for k, v in r["limitantes"].items()),  # type: ignore[union-attr]
            }
        )

    # ------------------------------------------------------------------ #
    print("\n== 4. a mesma varredura no replay de 31 dias (massa, NAO veredito) ==")
    dias_r = len({s.dia_br for s in replay})
    print(
        linha(
            "risco%",
            "agreg%",
            "vagas",
            "aprov",
            "ops/dia",
            "R/dia",
            "pior dia R",
            "USDT/R p50",
            "DD%",
            "travou",
        )
    )
    for risco, agregado, vagas in itertools.product(RISCOS, AGREGADOS, VAGAS):
        cfg = Config(
            risk_per_trade_pct=risco,
            max_aggregate_planned_risk_pct=agregado,
            max_concurrent_positions=vagas,
        )
        res = simular(replay, cfg)
        r = resumo(res, dias_r)
        print(
            linha(
                f"{risco * 100:>5.2f}",
                f"{agregado * 100:>5.1f}",
                f"{vagas:>5}",
                f"{r['aprovadas']:>5}",
                f"{r['ops_dia']:>7.1f}",
                f"{r['r_dia_medio']:>+7.2f}",
                f"{r['pior_dia']:>+10.2f}",
                f"{r['usdt_por_r_p50']:>10.2f}",
                f"{r['dd_pct'] * 100:>5.2f}",
                "sim" if r["latch"] else "nao",
            )
        )
        linhas_csv.append(
            {
                "coorte": "replay",
                "risco_pct": str(risco),
                "agregado_pct": str(agregado),
                "vagas": vagas,
                **{k: str(v) for k, v in r.items() if k not in ("recusas", "limitantes")},
                "recusas": ";".join(f"{k}={v}" for k, v in r["recusas"].items()),  # type: ignore[union-attr]
                "limitantes": ";".join(f"{k}={v}" for k, v in r["limitantes"].items()),  # type: ignore[union-attr]
            }
        )

    with open(os.path.join(AQUI, "configuracoes.csv"), "w", newline="", encoding="utf-8") as fh:
        escritor = csv.DictWriter(fh, fieldnames=list(linhas_csv[0].keys()))
        escritor.writeheader()
        escritor.writerows(linhas_csv)

    # ------------------------------------------------------------------ #
    print("\n== 5. onde as entradas morrem, e qual teto decide o tamanho (paper_v1 puro) ==")
    for nome, grupo, dias in (("prospectiva", prospectiva, dias_p), ("replay", replay, dias_r)):
        res = simular(grupo, Config())
        r = resumo(res, dias)
        total = r["candidatas"]
        print(f"-- {nome}: {total} apostas candidatas, {r['aprovadas']} aprovadas")
        for motivo, n in r["recusas"].items():  # type: ignore[union-attr]
            print(f"     recusa {motivo:<24} {n:>4}  ({100 * n / max(1, int(str(total))):.1f}%)")
        for teto, n in r["limitantes"].items():  # type: ignore[union-attr]
            print(f"     limitante {teto:<21} {n:>4}")

    # ------------------------------------------------------------------ #
    print("\n== 6. hoje (09/09), hora a hora, no perfil paper_v1 ==")
    res_hoje = simular(hoje, Config())
    por_hora: dict[int, list[Decimal]] = {}
    for f in res_hoje.fechadas:
        por_hora.setdefault(f.sinal.hora_br, []).append(f.r_net)
    print(linha("hora BRT", "ops", "R", "R medio"))
    for h in sorted(por_hora):
        vals = por_hora[h]
        print(
            linha(
                f"{h:>8}",
                f"{len(vals):>3}",
                f"{sum(vals, Decimal(0)):>+7.2f}",
                f"{sum(vals, Decimal(0)) / len(vals):>+7.3f}",
            )
        )
    print(
        linha(
            "TOTAL",
            f"{len(res_hoje.fechadas)} ops",
            f"{res_hoje.r_total:+.2f} R",
            f"PnL {res_hoje.pnl_total:+.2f} USDT = R$ {brl(res_hoje.pnl_total):+.2f}",
            f"USDT/R mediano {q([f.usdt_por_r for f in res_hoje.fechadas], 0.5):.2f}",
        )
    )

    # ------------------------------------------------------------------ #
    print("\n== 7. a tabela do dinheiro: R$/dia = R unicos/dia x valor de 1 R ==")
    print(
        "   (a) o ROTULO: 1 R = risk_per_trade_pct x patrimonio / (1 + custo_R) — o que o numero promete"
    )
    print("   (b) o REAL: 1 R = notional aprovado x distancia do stop — o que o motor entrega")
    base = simular(prospectiva, Config())
    r_unicos_dia = base.r_total / Decimal(max(1, dias_p))
    print(f"   R unicos/dia medido (perfil paper_v1, prospectiva): {r_unicos_dia:+.2f} R/dia")
    print(
        linha(
            "capital",
            "risco%",
            "1R rotulo R$ (p50)",
            "1R real R$ (p50)",
            "R$/dia rotulo",
            "R$/dia real (PnL medido)",
            "quanto do rotulo sobra",
        )
    )
    for cap_nome, equity in CAPITAIS.items():
        for risco in RISCOS:
            cfg = Config(risk_per_trade_pct=risco, equity_inicial=equity)
            res = simular(prospectiva, cfg)
            # o "rotulo" e o teto `risk_per_trade` que o PROPRIO motor calculou,
            # antes de perder para outro teto — nao uma conta feita aqui.
            rotulos = [
                r.notional_rotulo * r.sinal.risco_pct
                for r in res.aprovadas
                if r.notional_rotulo is not None
            ]
            reais = [f.usdt_por_r for f in res.fechadas]
            rotulo_usdt = q(rotulos, 0.5)
            real_usdt = q(reais, 0.5)
            r_dia = res.r_total / Decimal(max(1, dias_p))
            pnl_dia = res.pnl_total / Decimal(max(1, dias_p))
            print(
                linha(
                    f"{cap_nome:>7}",
                    f"{risco * 100:>5.2f}",
                    f"{brl(rotulo_usdt):>18.2f}",
                    f"{brl(real_usdt):>16.2f}",
                    f"{brl(rotulo_usdt) * r_dia:>13.2f}",
                    f"{brl(pnl_dia):>24.2f}",
                    f"{100 * real_usdt / rotulo_usdt if rotulo_usdt else 0:>21.2f}%",
                )
            )

    # ------------------------------------------------------------------ #
    print("\n== 8. quanto R$/dia cada configuracao entrega (prospectiva, capital R$100k) ==")
    print(
        linha("risco%", "agreg%", "vagas", "ops/dia", "R/dia", "R$/dia", "R$ pior dia", "R$ DD max")
    )
    for risco, agregado, vagas in itertools.product(RISCOS, AGREGADOS, VAGAS):
        cfg = Config(
            risk_per_trade_pct=risco,
            max_aggregate_planned_risk_pct=agregado,
            max_concurrent_positions=vagas,
        )
        res = simular(prospectiva, cfg)
        r = resumo(res, dias_p)
        usdt_r = r["usdt_por_r_p50"]
        print(
            linha(
                f"{risco * 100:>5.2f}",
                f"{agregado * 100:>5.1f}",
                f"{vagas:>5}",
                f"{r['ops_dia']:>7.1f}",
                f"{r['r_dia_medio']:>+7.2f}",
                f"{brl(res.pnl_total) / Decimal(max(1, dias_p)):>+9.2f}",
                f"{brl(Decimal(str(r['pior_dia'])) * Decimal(str(usdt_r))):>+11.2f}",
                f"{brl(Decimal(str(r['dd_usdt']))):>9.2f}",
            )
        )

    # ------------------------------------------------------------------ #
    print("\n== 9. roster: qual subconjunto das versoes entrega mais R unico/dia ==")
    versoes = sorted({s.versao for s in prospectiva}, key=lambda v: int(v.split("v")[-1]))
    escolhidas: list[str] = []
    restantes = list(versoes)
    print(
        linha("passo", "versao adicionada", "apostas", "R unico total", "R/dia", "ganho do passo")
    )
    anterior = Decimal(0)
    while restantes:
        melhor: tuple[Decimal, str, int] | None = None
        for v in restantes:
            teste = frozenset([*escolhidas, v])
            unicos, _ = deduplicar([s for s in prospectiva if s.versao in teste])
            total = sum((s.r_net for s in unicos), Decimal(0))
            if melhor is None or total > melhor[0]:
                melhor = (total, v, len(unicos))
        assert melhor is not None
        total, v, n = melhor
        escolhidas.append(v)
        restantes.remove(v)
        print(
            linha(
                f"{len(escolhidas):>5}",
                f"{v:<18}",
                f"{n:>7}",
                f"{total:>+13.2f}",
                f"{total / Decimal(max(1, dias_p)):>+7.2f}",
                f"{total - anterior:>+14.2f}",
            )
        )
        anterior = total

    print("\n   -- o roster passado pelo motor (perfil paper_v1), por tamanho de roster --")
    print(
        linha(
            "roster",
            "versoes",
            "aprovadas",
            "R/dia",
            "R$/dia",
            "IC95 do delta vs familia (bloco=dia)",
        )
    )
    unicos_familia, _ = deduplicar(prospectiva)
    for k in range(1, len(versoes) + 1):
        roster = frozenset(escolhidas[:k])
        res = simular(prospectiva, Config(roster=roster))
        decisoes = [
            Decisao(dia=s.dia_br, atr_pct=1.0 if s.versao in roster else 0.0, r_net=float(s.r_net))
            for s in unicos_familia
        ]
        c = contraste_por_piso(decisoes, 0.5, reamostragens=2000)
        print(
            linha(
                f"{k:>6}",
                f"{len(roster):>7}",
                f"{len(res.aprovadas):>9}",
                f"{res.r_total / Decimal(max(1, dias_p)):>+7.2f}",
                f"{brl(res.pnl_total) / Decimal(max(1, dias_p)):>+9.2f}",
                f"delta {c.delta:+.4f} R/decisao IC95 [{c.ic95[0]:+.4f}; {c.ic95[1]:+.4f}] n={c.n_variante}",
            )
        )

    # ------------------------------------------------------------------ #
    print("\n== 10. estresse: marca no pior ponto (MAE) em vez de marca a custo ==")
    for marca in ("custo", "mae"):
        res = simular(prospectiva, Config(marca=marca))  # type: ignore[arg-type]
        dd_usdt, dd_pct = res.drawdown_maximo()
        print(
            linha(
                f"marca={marca:<6}",
                f"aprovadas={len(res.aprovadas):>4}",
                f"R/dia={res.r_total / Decimal(max(1, dias_p)):>+7.2f}",
                f"DD={dd_pct * 100:>5.2f}%",
                f"travou={'sim ' + str(res.latch_em) if res.latch_em else 'nao'}",
            )
        )

    # ------------------------------------------------------------------ #
    print("\n== 11. quando o kill switch travaria, e quanto custa o dia ruim ==")
    for nome, grupo, dias in (("prospectiva", prospectiva, dias_p), ("replay", replay, dias_r)):
        for risco in RISCOS:
            cfg = Config(risk_per_trade_pct=risco, marca="mae")
            res = simular(grupo, cfg)
            r_dia = list(res.r_por_dia.values())
            pior = min(r_dia) if r_dia else Decimal(0)
            usdt_r = q([f.usdt_por_r for f in res.fechadas], 0.5)
            print(
                linha(
                    f"{nome:<12}",
                    f"risco {risco * 100:>5.2f}%",
                    f"dias={dias:>2}",
                    f"pior dia {pior:>+7.2f} R = R$ {brl(pior * usdt_r):>+9.2f}",
                    f"perda diaria maxima medida {100 * abs(min(Decimal(0), pior)) * usdt_r / EQUITY_100K:>5.3f}% do patrimonio",
                    f"travou={'sim' if res.latch_em else 'nao'}",
                )
            )

    # ------------------------------------------------------------------ #
    print("\n== 12. a pergunta do Everton: o que R$ 9.000/dia exigiria ==")
    base = simular(prospectiva, Config())
    r_dia = base.r_total / Decimal(max(1, dias_p))
    usdt_r = q([f.usdt_por_r for f in base.fechadas], 0.5)
    stop_p50 = q([f.sinal.risco_pct for f in base.fechadas], 0.5)
    notional_p50 = q([f.notional for f in base.aprovadas], 0.5)
    meta_brl = Decimal(9000)
    meta_usdt = meta_brl / CAMBIO_BRL
    print(
        f"   medido hoje: {r_dia:+.2f} R unicos/dia, 1 R = {usdt_r:.2f} USDT (R$ {brl(usdt_r):.2f})"
    )
    print(
        f"                notional aprovado mediano {notional_p50:.2f} USDT, stop mediano {stop_p50 * 100:.3f}%"
    )
    print(f"   PnL medido: R$ {brl(base.pnl_total / Decimal(max(1, dias_p))):.2f}/dia")
    if r_dia > 0:
        preciso_usdt_r = meta_usdt / r_dia
        preciso_notional = preciso_usdt_r / stop_p50
        print(
            f"   (a) mesma taxa de R/dia -> 1 R teria de valer {preciso_usdt_r:.2f} USDT (R$ {brl(preciso_usdt_r):.2f})"
        )
        print(
            f"       = notional de {preciso_notional:.0f} USDT por operacao ({preciso_notional / notional_p50:.0f}x o de hoje)"
        )
        print(
            f"       teto por moeda (10%) exige patrimonio de {preciso_notional * 10:.0f} USDT = R$ {brl(preciso_notional * 10):,.0f}"
        )
        print(
            f"       teto de participacao (1% do minuto) exige um minuto de {preciso_notional * 100:.0f} USDT"
        )
        print(
            f"       = ~{preciso_notional * 100 * 1440 / Decimal(1_000_000_000):.1f} bi USDT/24h de volume no par"
        )
        print(
            f"   (b) mesmo tamanho de hoje -> seriam {meta_usdt / usdt_r:.0f} R unicos/dia (hoje: {r_dia:.2f})"
        )
        print(
            f"       = {meta_usdt / usdt_r / max(r_dia, Decimal('0.01')):.0f}x o fluxo de R da familia inteira"
        )

    print("\n== 13. quantos mercados do universo passam o piso de liquidez de 50 M/24h ==")
    for nome, grupo in (("prospectiva", prospectiva), ("replay", replay)):
        unicos, _ = deduplicar(grupo)
        por_mercado: dict[str, Decimal] = {}
        for s in unicos:
            por_mercado[s.symbol] = max(
                por_mercado.get(s.symbol, Decimal(0)), s.vol_24h or Decimal(0)
            )
        passam = [m for m, v in por_mercado.items() if v >= Decimal(50_000_000)]
        vols = sorted(por_mercado.values())
        print(
            linha(
                f"{nome:<12}",
                f"mercados={len(por_mercado):>3}",
                f"passam 50M={len(passam):>3} ({100 * len(passam) / max(1, len(por_mercado)):.1f}%)",
                f"vol24h p50={statistics.median(vols) / Decimal(1_000_000):.1f}M",
                f"p90={q(vols, 0.9) / Decimal(1_000_000):.1f}M",
            )
        )


if __name__ == "__main__":
    main()
