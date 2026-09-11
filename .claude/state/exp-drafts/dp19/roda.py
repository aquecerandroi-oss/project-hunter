"""D-P19 — a manivela: lê os dumps da VPS e escreve as tabelas em `Decimal`.

Rascunho de pesquisa (fora de produção). Todo o IO está aqui; a aritmética está
em `meta_em_dinheiro.py`, que é puro e tem tabela de testes.

Entradas (dumps somente-leitura da VPS, ver `infra/scripts/sql/research/2026-09-11-dp19-*.sql`):
  volume_1m.csv.gz     q01 — quote_volume de cada minuto, 30 dias, 16 perpétuos + gêmeos SPOT
  stops_e_apostas.csv  q04 — d_stop por mercado e apostas únicas da família

Saídas (neste mesmo diretório):
  volume_por_hora.csv        distribuição do volume do minuto por hora de Brasília
  teto_por_mercado_hora.csv  notional do teto de participação e o R em BRL, por hora
  resumo_por_mercado.csv     o dia inteiro por mercado, nas 3 participações e 2 escalas
  teto_por_hora.csv          capacidade do universo por hora x giro observado naquela hora
  cenarios.csv               o agregado: teto e esperado de BRL/dia, e o que falta para 9.000
  o_que_falta.csv            a inversão da meta contra o teto das vagas (5 x 4 h = 30/dia)
  impacto_na_meta.csv        impacto raiz-quadrada no tamanho que a meta pediria (SENSIBILIDADE)

Uso: uv run python .claude/state/exp-drafts/dp19/roda.py
"""

from __future__ import annotations

import csv
import gzip
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from meta_em_dinheiro import (
    CUSTO_RT_LAB,
    PARTICIPACOES,
    Cenario,
    brl,
    caps_do_motor,
    impacto_raiz_quadrada,
    percentil_nearest_rank,
    referencias_de_volume,
    valor_de_1r_usdt,
)

from hunter_risk.limits import PAPER_V1

AQUI = Path(__file__).parent

# --- constantes do corte, todas declaradas (nenhuma é limite do motor) -------
CAMBIO = Decimal("5.1198")  # fx_observations USDTBRL, 2026-09-11 05:05:35 BRT (q00 §3)
META_BRL_DIA = Decimal("9000")  # ApiSettings.daily_goal_brl (T3.78)
DIAS_DA_FAMILIA = Decimal(3)  # 08, 09 e 10/09 BRT — os dias com coorte prospectiva (q03)
ESCALAS_BRL = (Decimal("100000"), Decimal("400000"))  # as escalas da T3.60
K_IMPACTO = (Decimal("0.1"), Decimal("0.3"), Decimal("1.0"))  # SENSIBILIDADE, não medição
OS_16 = (
    "ARBUSDT BNBUSDT BTCUSDT DASHUSDT DOGEUSDT ETHUSDT LINKUSDT NEARUSDT "
    "PROMUSDT SAHARAUSDT SOLUSDT SUIUSDT TAOUSDT UNIUSDT XRPUSDT ZECUSDT"
).split()
PISO_LIQUIDEZ_USD_24H = Decimal("50000000")  # PAPER_V1.min_liquidity_usd_24h, só para rotular
HORIZONTE_S = Decimal("14400")  # meta.horizon_s da família: 4 h por posição
PAPER_V1_MAX_VAGAS = PAPER_V1.max_concurrent_positions
PAPER_V1_MAX_MOEDA = PAPER_V1.max_asset_exposure_pct


def _hora_brt(minuto_epoch: int) -> int:
    """Brasília é UTC-3 o ano todo desde 2019 (sem horário de verão)."""
    return ((minuto_epoch - 180) // 60) % 24


def le_volumes() -> dict[tuple[str, str], list[tuple[int, Decimal]]]:
    series: dict[tuple[str, str], list[tuple[int, Decimal]]] = defaultdict(list)
    with gzip.open(AQUI / "volume_1m.csv.gz", "rt", encoding="utf-8", newline="") as fh:
        for linha in csv.DictReader(fh):
            minuto = int(
                datetime.strptime(linha["open_time_utc"], "%Y-%m-%dT%H:%M:%S")
                .replace(tzinfo=UTC)
                .timestamp()
                // 60
            )
            series[(linha["symbol"], linha["tipo"])].append(
                (minuto, Decimal(linha["quote_volume"]))
            )
    for chave in series:
        series[chave].sort()
    return dict(series)


def le_stops() -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, str]]:
    por_mercado: dict[tuple[str, str], dict[str, str]] = {}
    familia: dict[str, str] = {}
    with (AQUI / "stops_e_apostas.csv").open(encoding="utf-8", newline="") as fh:
        for linha in csv.DictReader(fh):
            if linha["escopo"] == "FAMILIA":
                familia = linha
            else:
                por_mercado[(linha["symbol"], linha["tipo"])] = linha
    return por_mercado, familia


def d_stop_de(
    chave: tuple[str, str], stops: dict[tuple[str, str], dict[str, str]], familia: dict[str, str]
) -> tuple[Decimal, str, int]:
    """`d_stop` medido no mercado quando existe; senão a mediana da família,
    sempre rotulado — nunca um número sem procedência."""
    linha = stops.get(chave)
    if linha and linha["d_stop_p50"] and int(linha["n_desfechos"]) > 0:
        return Decimal(linha["d_stop_p50"]), "medido_no_mercado", int(linha["n_desfechos"])
    perp = stops.get((chave[0], "perpetual"))
    if perp and perp["d_stop_p50"] and int(perp["n_desfechos"]) > 0:
        return Decimal(perp["d_stop_p50"]), "medido_no_perpetuo_gemeo", int(perp["n_desfechos"])
    return Decimal(familia["d_stop_p50"]), "mediana_da_familia", 0


def main() -> None:
    series = le_volumes()
    stops, familia = le_stops()
    refs_por_chave: dict[tuple[str, str], list[tuple[int, Decimal]]] = {}
    for chave, serie in series.items():
        refs_por_chave[chave] = referencias_de_volume(serie, janela=30)

    # ---------------------------------------------- A. volume por hora ------
    por_hora_qv: dict[tuple[str, str, int], list[Decimal]] = defaultdict(list)
    por_hora_ref: dict[tuple[str, str, int], list[Decimal]] = defaultdict(list)
    for chave, serie in series.items():
        for minuto, qv in serie:
            por_hora_qv[(*chave, _hora_brt(minuto))].append(qv)
    for chave, refs in refs_por_chave.items():
        for minuto, ref in refs:
            por_hora_ref[(*chave, _hora_brt(minuto))].append(ref)

    q = (Decimal("0.10"), Decimal("0.50"), Decimal("0.90"))
    with (AQUI / "volume_por_hora.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            "symbol tipo hora_brt n_min qv_p10 qv_p50 qv_p90 n_ref ref_p10 ref_p50 ref_p90".split()
        )
        for (symbol, tipo, hora), qvs in sorted(por_hora_qv.items()):
            refs = por_hora_ref.get((symbol, tipo, hora), [])
            linha = [symbol, tipo, hora, len(qvs)]
            linha += [f"{percentil_nearest_rank(qvs, p):.2f}" for p in q]
            linha.append(len(refs))
            linha += [f"{percentil_nearest_rank(refs, p):.2f}" if refs else "" for p in q]
            w.writerow(linha)

    # ------------------------------- B. teto e 1 R por mercado x hora -------
    equity_usdt = {e: e / CAMBIO for e in ESCALAS_BRL}
    with (AQUI / "teto_por_mercado_hora.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            "symbol tipo hora_brt participacao d_stop fonte_d_stop ref_p10 ref_p50 ref_p90 "
            "notional_p10 notional_p50 notional_p90 r_brl_p10 r_brl_p50 r_brl_p90".split()
        )
        for (symbol, tipo, hora), refs in sorted(por_hora_ref.items()):
            if not refs:
                continue
            d_stop, fonte, _ = d_stop_de((symbol, tipo), stops, familia)
            rp = [percentil_nearest_rank(refs, p) for p in q]
            for part in PARTICIPACOES:
                notionais = [r * part for r in rp]
                rbrl = [brl(valor_de_1r_usdt(n, d_stop), CAMBIO) for n in notionais]
                w.writerow(
                    [symbol, tipo, hora, part, f"{d_stop:.8f}", fonte]
                    + [f"{v:.2f}" for v in rp]
                    + [f"{v:.2f}" for v in notionais]
                    + [f"{v:.2f}" for v in rbrl]
                )

    # ------------------------------------ C. resumo por mercado (dia) -------
    linhas_resumo = []
    for chave in sorted(refs_por_chave):
        symbol, tipo = chave
        refs = [r for _, r in refs_por_chave[chave]]
        if not refs:
            continue
        serie = series[chave]
        minutos = len(serie)
        adv = sum((qv for _, qv in serie), Decimal(0)) / (Decimal(minutos) / Decimal(1440))
        d_stop, fonte, n_desf = d_stop_de(chave, stops, familia)
        linha_apostas = stops.get(chave)
        apostas = Decimal(linha_apostas["apostas_unicas"]) if linha_apostas else Decimal(0)
        r_medio = (
            Decimal(linha_apostas["r_medio"])
            if linha_apostas and linha_apostas["r_medio"]
            else Decimal(familia["r_medio"])
        )
        fonte_r = "medido_no_mercado" if (linha_apostas and linha_apostas["r_medio"]) else "familia"
        apostas_dia = apostas / DIAS_DA_FAMILIA
        # D1 (docs/RISK_ENGINE.md §1): o perpétuo decide, o SPOT executa. Para a
        # linha SPOT o giro e o R são os do gêmeo perpétuo; só o volume (e logo o
        # teto de participação) é o do SPOT, que é onde a carteira compraria.
        linha_perp = stops.get((symbol, "perpetual"))
        apostas_dia_sinal = (
            Decimal(linha_perp["apostas_unicas"]) / DIAS_DA_FAMILIA
            if tipo == "spot" and linha_perp
            else apostas_dia
        )
        r_medio_sinal = (
            Decimal(linha_perp["r_medio"])
            if tipo == "spot" and linha_perp and linha_perp["r_medio"]
            else r_medio
        )
        ref_p50 = percentil_nearest_rank(refs, Decimal("0.50"))
        for part in PARTICIPACOES:
            for escala_brl, eq_usdt in equity_usdt.items():
                caps = caps_do_motor(
                    equity_usdt=eq_usdt,
                    d_stop=d_stop,
                    referencia_volume=ref_p50,
                    participacao=part,
                )
                r_brl = brl(valor_de_1r_usdt(caps.notional, d_stop), CAMBIO)
                cen = Cenario(
                    nome=f"{symbol}:{tipo}",
                    apostas_por_dia=apostas_dia,
                    valor_1r_brl=r_brl,
                    r_por_aposta=r_medio,
                )
                cen_sinal = Cenario(
                    nome=f"{symbol}:{tipo}:sinal_do_perp",
                    apostas_por_dia=apostas_dia_sinal,
                    valor_1r_brl=r_brl,
                    r_por_aposta=r_medio_sinal,
                )
                impactos = [impacto_raiz_quadrada(caps.notional, adv, k) for k in K_IMPACTO]
                linhas_resumo.append(
                    [
                        symbol,
                        tipo,
                        symbol in OS_16,
                        part,
                        escala_brl,
                        f"{ref_p50:.2f}",
                        f"{adv:.2f}",
                        adv >= PISO_LIQUIDEZ_USD_24H,
                        f"{d_stop:.8f}",
                        fonte,
                        n_desf,
                        f"{caps.notional:.2f}",
                        caps.binding,
                        f"{caps.valores['risk_per_trade']:.2f}",
                        f"{caps.valores['market_participation']:.2f}",
                        f"{caps.valores['asset_exposure']:.2f}",
                        f"{r_brl:.2f}",
                        f"{apostas_dia:.4f}",
                        f"{r_medio:.4f}",
                        fonte_r,
                        f"{cen.teto_brl_dia:.2f}",
                        f"{cen.esperado_brl_dia:.2f}",
                        f"{apostas_dia_sinal:.4f}",
                        f"{r_medio_sinal:.4f}",
                        f"{cen_sinal.teto_brl_dia:.2f}",
                        f"{cen_sinal.esperado_brl_dia:.2f}",
                    ]
                    + [f"{i * 10000:.2f}" for i in impactos]
                )
    with (AQUI / "resumo_por_mercado.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            "symbol tipo nos_16 participacao equity_brl ref_p50_usdt adv_usdt passa_piso_50m "
            "d_stop fonte_d_stop n_desfechos notional_usdt binding cap_risk cap_participacao "
            "cap_moeda r_brl apostas_dia r_medio fonte_r teto_brl_dia esperado_brl_dia "
            "apostas_dia_sinal r_medio_sinal teto_brl_dia_sinal esperado_brl_dia_sinal "
            "impacto_raiz_bps_k0_1 impacto_raiz_bps_k0_3 impacto_raiz_bps_k1_0".split()
        )
        w.writerows(linhas_resumo)

    # ----------------------------------------------- D. cenários -----------
    idx = {nome: i for i, nome in enumerate(
        "symbol tipo nos_16 participacao equity_brl ref_p50_usdt adv_usdt passa_piso_50m "
        "d_stop fonte_d_stop n_desfechos notional_usdt binding cap_risk cap_participacao "
        "cap_moeda r_brl apostas_dia r_medio fonte_r teto_brl_dia esperado_brl_dia "
        "apostas_dia_sinal r_medio_sinal teto_brl_dia_sinal esperado_brl_dia_sinal".split()
    )}
    universos = (
        ("16_perpetuos", lambda lin: lin[idx["tipo"]] == "perpetual" and lin[idx["nos_16"]], False),
        ("16_spot", lambda lin: lin[idx["tipo"]] == "spot" and lin[idx["nos_16"]], False),
        (
            "16_spot_executando_sinal_do_perp",
            lambda lin: lin[idx["tipo"]] == "spot" and lin[idx["nos_16"]],
            True,
        ),
    )
    with (AQUI / "cenarios.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            "universo participacao equity_brl mercados apostas_dia teto_brl_dia esperado_brl_dia "
            "r_brl_mediano falta_para_9000 r_brl_necessario_por_aposta "
            "notional_necessario_usdt volume_do_minuto_necessario_usdt "
            "equity_necessario_brl_teto_moeda mercados_com_esse_minuto".split()
        )
        for universo, filtro, usa_sinal in universos:
            for part in PARTICIPACOES:
                for escala in ESCALAS_BRL:
                    sel = [
                        lin
                        for lin in linhas_resumo
                        if filtro(lin)
                        and lin[idx["participacao"]] == part
                        and lin[idx["equity_brl"]] == escala
                    ]
                    if not sel:
                        continue
                    suf = "_sinal" if usa_sinal else ""
                    apostas = sum(Decimal(lin[idx["apostas_dia" + suf]]) for lin in sel)
                    teto = sum(Decimal(lin[idx["teto_brl_dia" + suf]]) for lin in sel)
                    esperado = sum(Decimal(lin[idx["esperado_brl_dia" + suf]]) for lin in sel)
                    r_mediano = percentil_nearest_rank(
                        [Decimal(lin[idx["r_brl"]]) for lin in sel], Decimal("0.50")
                    )
                    # a inversão: quanto 1 R teria de valer para a meta sair no
                    # TETO (toda aposta fechando +1 R), e o que isso exige do
                    # mercado e do patrimônio.
                    d_stop_mediano = percentil_nearest_rank(
                        [Decimal(lin[idx["d_stop"]]) for lin in sel], Decimal("0.50")
                    )
                    if apostas > 0:
                        r_nec = META_BRL_DIA / apostas
                        notional_nec = r_nec / (CAMBIO * d_stop_mediano)
                        minuto_nec = notional_nec / part
                        equity_nec = notional_nec * CAMBIO / Decimal("0.10")  # max_asset_exposure_pct
                        com_minuto = sum(
                            1 for lin in sel if Decimal(lin[idx["ref_p50_usdt"]]) >= minuto_nec
                        )
                    else:
                        r_nec = notional_nec = minuto_nec = equity_nec = Decimal(0)
                        com_minuto = 0
                    w.writerow(
                        [
                            universo,
                            part,
                            escala,
                            len(sel),
                            f"{apostas:.4f}",
                            f"{teto:.2f}",
                            f"{esperado:.2f}",
                            f"{r_mediano:.2f}",
                            f"{META_BRL_DIA - teto:.2f}",
                            f"{r_nec:.2f}",
                            f"{notional_nec:.2f}",
                            f"{minuto_nec:.2f}",
                            f"{equity_nec:.2f}",
                            com_minuto,
                        ]
                    )

    # ------------------------------------------ E. capacidade por hora -----
    apostas_hora: dict[int, dict[str, str]] = {}
    caminho_horas = AQUI / "apostas_por_hora.csv"
    if caminho_horas.exists():
        with caminho_horas.open(encoding="utf-8", newline="") as fh:
            for linha in csv.DictReader(fh):
                if linha["escopo"] == "os_16":
                    apostas_hora[int(linha["hora_brt"])] = linha
    with (AQUI / "teto_por_hora.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            "hora_brt tipo participacao equity_brl mercados soma_1r_brl mediana_1r_brl "
            "apostas_dia_nessa_hora r_medio_nessa_hora n_apostas teto_brl_hora "
            "esperado_brl_hora".split()
        )
        for tipo in ("perpetual", "spot"):
            for hora in range(24):
                for part in PARTICIPACOES:
                    for escala_brl, eq_usdt in equity_usdt.items():
                        valores_1r = []
                        for symbol in OS_16:
                            refs = por_hora_ref.get((symbol, tipo, hora))
                            if not refs:
                                continue
                            d_stop, _, _ = d_stop_de((symbol, tipo), stops, familia)
                            caps = caps_do_motor(
                                equity_usdt=eq_usdt,
                                d_stop=d_stop,
                                referencia_volume=percentil_nearest_rank(refs, Decimal("0.50")),
                                participacao=part,
                            )
                            valores_1r.append(brl(valor_de_1r_usdt(caps.notional, d_stop), CAMBIO))
                        if not valores_1r:
                            continue
                        linha_h = apostas_hora.get(hora)
                        n_apostas = int(linha_h["apostas_unicas"]) if linha_h else 0
                        apostas_dia_h = Decimal(n_apostas) / DIAS_DA_FAMILIA
                        r_h = (
                            Decimal(linha_h["r_medio"])
                            if linha_h and linha_h["r_medio"]
                            else Decimal(familia["r_medio"])
                        )
                        mediana_1r = percentil_nearest_rank(valores_1r, Decimal("0.50"))
                        cen = Cenario(
                            nome=f"hora {hora}",
                            apostas_por_dia=apostas_dia_h,
                            valor_1r_brl=mediana_1r,
                            r_por_aposta=r_h,
                        )
                        w.writerow(
                            [
                                hora,
                                tipo,
                                part,
                                escala_brl,
                                len(valores_1r),
                                f"{sum(valores_1r):.2f}",
                                f"{mediana_1r:.2f}",
                                f"{apostas_dia_h:.4f}",
                                f"{r_h:.4f}",
                                n_apostas,
                                f"{cen.teto_brl_dia:.2f}",
                                f"{cen.esperado_brl_dia:.2f}",
                            ]
                        )

    # ------------------------------------- F. o teto absoluto do universo ---
    # Uma aposta em CADA um dos 16, em CADA hora, TODAS fechando +1 R: o teto
    # aritmético do universo executável. Não é cenário — é o limite superior.
    with (AQUI / "teto_por_hora.csv").open(encoding="utf-8", newline="") as fh:
        horas = list(csv.DictReader(fh))
    print(f"custo de ida e volta do Lab (do motor): {CUSTO_RT_LAB}")
    print(f"cambio USDTBRL: {CAMBIO}   meta: R$ {META_BRL_DIA}/dia")
    print(f"series lidas: {len(series)}   minutos: {sum(len(s) for s in series.values())}")
    print(f"linhas de resumo: {len(linhas_resumo)}")
    print("\n-- teto ABSURDO (384 apostas/dia, 16 mercados x 24 h, todas +1 R) --")
    for tipo in ("perpetual", "spot"):
        for part in PARTICIPACOES:
            for escala in ESCALAS_BRL:
                sel = [
                    h
                    for h in horas
                    if h["tipo"] == tipo
                    and Decimal(h["participacao"]) == part
                    and Decimal(h["equity_brl"]) == escala
                ]
                if not sel:
                    continue
                total = sum(Decimal(h["soma_1r_brl"]) for h in sel)
                apostas = sum(int(h["mercados"]) for h in sel)
                print(
                    f"{tipo:10s} part={part} equity=R${escala:>8} "
                    f"apostas={apostas:4d}  teto=R$ {total:>12,.2f}/dia"
                )
    # ------------------- G. o teto que as VAGAS impõem, e a inversão --------
    # max_concurrent_positions = 5 e horizonte de 4 h (meta.horizon_s = 14400)
    # => no máximo 5 x (24/4) = 30 entradas por dia, qualquer que seja o número
    # de sinais. É o teto estrutural do perfil, não uma hipótese.
    vagas = Decimal(PAPER_V1_MAX_VAGAS)
    giros = Decimal(24 * 3600) / HORIZONTE_S
    entradas_max_dia = vagas * giros
    print(
        f"\n-- teto das VAGAS: {vagas} x {giros} giros de {HORIZONTE_S}s = "
        f"{entradas_max_dia} entradas/dia --"
    )
    with (AQUI / "o_que_falta.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            "tipo participacao r_medio_hipotetico entradas_dia r_brl_necessario "
            "notional_necessario_usdt volume_do_minuto_necessario_usdt "
            "equity_necessario_brl mercados_com_esse_minuto".split()
        )
        d_stop_fam = Decimal(familia["d_stop_p50"])
        for tipo in ("perpetual", "spot"):
            refs_p50 = {}
            for symbol in OS_16:
                refs = [r for _, r in refs_por_chave.get((symbol, tipo), [])]
                if refs:
                    refs_p50[symbol] = percentil_nearest_rank(refs, Decimal("0.50"))
            for part in PARTICIPACOES:
                for r_hip in (Decimal("0.05"), Decimal("0.10"), Decimal("0.20"), Decimal("0.40"), Decimal("1.00")):
                    r_nec = META_BRL_DIA / (entradas_max_dia * r_hip)
                    notional_nec = r_nec / (CAMBIO * d_stop_fam)
                    minuto_nec = notional_nec / part
                    equity_nec = notional_nec * CAMBIO / PAPER_V1_MAX_MOEDA
                    com = sum(1 for v in refs_p50.values() if v >= minuto_nec)
                    w.writerow(
                        [
                            tipo,
                            part,
                            r_hip,
                            entradas_max_dia,
                            f"{r_nec:.2f}",
                            f"{notional_nec:.2f}",
                            f"{minuto_nec:.2f}",
                            f"{equity_nec:.2f}",
                            com,
                        ]
                    )
                    if tipo == "perpetual" and part == Decimal("0.01"):
                        print(
                            f"  R medio +{r_hip}: 1R=R$ {r_nec:>9,.2f}  "
                            f"notional={notional_nec:>10,.0f} USDT  "
                            f"minuto>={minuto_nec:>12,.0f} USDT ({com}/16 tem)  "
                            f"patrimonio>=R$ {equity_nec:>12,.0f}"
                        )

    # ---- H. impacto raiz-quadrada NO TAMANHO QUE A META PEDIRIA (sensibilidade)
    # `k` não é nosso e o autor não publica o calibrado (Astra: não importar como
    # verdade). Grade declarada, coluna rotulada, nada entra em limite.
    alvo = META_BRL_DIA / (entradas_max_dia * Decimal("0.20")) / (CAMBIO * d_stop_fam)
    with (AQUI / "impacto_na_meta.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            "symbol tipo notional_alvo_usdt adv_usdt impacto_bps_k0_1 impacto_bps_k0_3 "
            "impacto_bps_k1_0 custo_do_lab_bps max_slippage_pct_bps".split()
        )
        for tipo in ("perpetual", "spot"):
            for symbol in OS_16:
                serie = series.get((symbol, tipo))
                if not serie:
                    continue
                adv = sum((qv for _, qv in serie), Decimal(0)) / (
                    Decimal(len(serie)) / Decimal(1440)
                )
                w.writerow(
                    [symbol, tipo, f"{alvo:.2f}", f"{adv:.2f}"]
                    + [
                        f"{impacto_raiz_quadrada(alvo, adv, k) * 10000:.2f}"
                        for k in K_IMPACTO
                    ]
                    + [f"{CUSTO_RT_LAB * 10000:.2f}", f"{PAPER_V1.max_slippage_pct * 10000:.2f}"]
                )

    print("\n-- o dia real medido (16 perpetuos, participacao 1%, R$100 mil) --")
    with (AQUI / "cenarios.csv").open(encoding="utf-8", newline="") as fh:
        for linha in csv.DictReader(fh):
            if linha["participacao"] == "0.01" and linha["equity_brl"] == "100000":
                print(
                    f"{linha['universo']:34s} apostas/dia={linha['apostas_dia']:>7} "
                    f"teto=R$ {linha['teto_brl_dia']:>9} esperado=R$ {linha['esperado_brl_dia']:>9} "
                    f"1R mediano=R$ {linha['r_brl_mediano']:>7}"
                )


if __name__ == "__main__":
    main()
