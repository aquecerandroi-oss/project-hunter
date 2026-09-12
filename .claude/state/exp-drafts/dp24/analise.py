"""D-P24 — le os dois CSV e imprime a decomposicao do Delta(240-80) por motivo
REAL de saida.

Secoes:
  §0  cobertura, e a checagem cruzada das DUAS implementacoes (SQL x Python)
  §1  o Delta agregado — a reproducao do numero do D-P23 a partir de outro dump
  §2  A TABELA: decomposicao por motivo de saida, em ATR da propria decisao
  §3  a mesma tabela em % do preco de entrada
  §4  time-stop CONTRA stop: os dois grupos que a pergunta separa
  §5  excursoes de CLOSES por grupo — colunas AUXILIARES, nunca a medida
  §6  sensibilidade: tirar um dia, tirar um mercado (o Delta agregado e de um dia so?)

Uso: uv run --with numpy python analise.py dp24-decisoes.csv dp24-caminho.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import decomp  # noqa: E402,F401  (poe `t362b` e `dp23` no path — reuso declarado)
from blocos90 import delta_pareado_por_dia, ic_media  # noqa: E402
from curva import ic_mediana_blocos  # noqa: E402
from decomp import (  # noqa: E402
    MOTIVOS,
    Vela,
    contribuicao_decil,
    decompoe,
    delta_por_decisao,
    divide_delta,
    mfe_mae_closes,
    ret_atr,
    ret_pct,
)

REAMOSTRAGENS = 20_000
SEED = 20260910
H_CURTO, H_LONGO = 80, 240
HORIZONTE = 240


# --------------------------------------------------------------------- IO


def carrega_csv(caminho: Path, primeira_coluna: str) -> list[dict[str, str]]:
    """Le a saida crua do psql (`\\pset format unaligned`), sem pandas."""
    linhas: list[dict[str, str]] = []
    cab: list[str] | None = None
    for cru in caminho.read_text(encoding="utf-8").splitlines():
        if cab is None:
            if cru.startswith(primeira_coluna + ","):
                cab = cru.split(",")
            continue
        if cru.startswith("(") and cru.rstrip().endswith("rows)"):
            break
        if not cru.strip() or cru.strip() in {"BEGIN", "SET", "COMMIT"}:
            continue
        partes = cru.split(",")
        if len(partes) != len(cab):
            raise SystemExit(f"linha com {len(partes)} campos, esperado {len(cab)}: {cru!r}")
        linhas.append(dict(zip(cab, partes, strict=True)))
    if cab is None:
        raise SystemExit(f"cabecalho comecando em {primeira_coluna!r} nao encontrado")
    return linhas


def _f(txt: str) -> float:
    return float("nan") if txt == "" else float(txt)


# ------------------------------------------------------------- formatacao


def _n(x: float, casas: int = 4) -> str:
    return "      —" if np.isnan(x) else f"{x:+.{casas}f}"


def tabela(titulo: str, grupos, total, *, casas: int = 4) -> None:
    print()
    print(titulo)
    print(
        f"{'motivo':<13}{'n':>5}{'dias':>6}{'media':>10}{'mediana':>10}"
        f"{'IC95 media':>22}{'contrib':>10}{'IC95 contrib':>22}{'%>0':>7}"
    )
    for g in list(MOTIVOS) + ["todos"]:
        r = total if g == "todos" else grupos[g]
        ic_m = f"[{_n(r.ic_media[0], casas)}; {_n(r.ic_media[1], casas)}]"
        ic_c = f"[{_n(r.ic_contribuicao[0], casas)}; {_n(r.ic_contribuicao[1], casas)}]"
        pos = "     —" if np.isnan(r.frac_pos) else f"{100 * r.frac_pos:5.1f}%"
        print(
            f"{r.motivo:<13}{r.n:>5}{r.dias:>6}{_n(r.media, casas):>10}"
            f"{_n(r.mediana, casas):>10}{ic_m:>22}{_n(r.contribuicao, casas):>10}"
            f"{ic_c:>22}{pos:>7}"
        )
    soma = sum(grupos[g].contribuicao for g in MOTIVOS)
    print(
        f"{'IDENTIDADE':<13} soma das contribuicoes = {soma:+.6f}   "
        f"media total = {total.media:+.6f}   erro = {abs(soma - total.media):.2e}"
    )


def tabela_decis(titulo: str, grupos, total, *, casas: int = 4) -> None:
    print()
    print(titulo)
    print(
        f"{'motivo':<13}{'n':>5}{'decil':>7}{'contrib':>10}{'decil sup':>11}"
        f"{'decil inf':>11}{'sup/contrib':>13}{'mediana':>10}{'IC95 mediana':>22}"
    )
    for g in list(MOTIVOS) + ["todos"]:
        r = total if g == "todos" else grupos[g]
        k = 0 if r.n == 0 else int(np.ceil(r.n / 10))
        razao = (
            "      —"
            if r.n == 0 or abs(r.contribuicao) < 1e-12
            else f"{r.contrib_decil_sup / r.contribuicao:+7.2f}x"
        )
        ic_md = f"[{_n(r.ic_mediana[0], casas)}; {_n(r.ic_mediana[1], casas)}]"
        print(
            f"{r.motivo:<13}{r.n:>5}{k:>7}{_n(r.contribuicao, casas):>10}"
            f"{_n(r.contrib_decil_sup, casas):>11}{_n(r.contrib_decil_inf, casas):>11}"
            f"{razao:>13}{_n(r.mediana, casas):>10}{ic_md:>22}"
        )


# ------------------------------------------------------------------ main


def main(csv_decisoes: Path, csv_caminho: Path) -> None:
    dec = {d["decisao"]: d for d in carrega_csv(csv_decisoes, "decisao")}
    print(f"decisoes lidas: {len(dec)}")

    velas: dict[str, list[Vela]] = {d: [] for d in dec}
    for linha in carrega_csv(csv_caminho, "decisao"):
        velas[linha["decisao"]].append(
            Vela(minuto=int(linha["m"]), close=float(linha["fechamento"]), is_final=True)
        )
    print(f"minutos lidos: {sum(len(v) for v in velas.values())}")

    # ---------------------------------------------------------------- §0
    print("\n" + "=" * 78)
    print("§0 COBERTURA E CHECAGEM CRUZADA — duas implementacoes da mesma definicao")
    print("=" * 78)
    completos = sum(1 for d in dec if len(velas[d]) == HORIZONTE)
    print(f"decisoes com os {HORIZONTE} minutos `is_final` completos: {completos}/{len(dec)}")
    faltando = {d: HORIZONTE - len(velas[d]) for d in dec if len(velas[d]) != HORIZONTE}
    print(f"decisoes com buraco no caminho: {len(faltando)}  {faltando if faltando else ''}")

    difs = {k: 0.0 for k in ("ret80", "ret240", "mfe80", "mae80", "mfe240", "mae240",
                             "antes_max", "antes_min", "depois_max", "depois_min")}
    ncomp = {"antes": 0, "depois": 0}
    for d, linha in dec.items():
        eo, atr = float(linha["entry_open"]), float(linha["atr"])
        m_saida = int(linha["m_saida"])
        por_minuto = {v.minuto: v for v in velas[d]}
        p80, p240 = por_minuto.get(H_CURTO), por_minuto.get(H_LONGO)
        if p80 is None or p240 is None:
            raise SystemExit(f"{d}: falta endpoint no caminho — a cobertura mentiu")
        difs["ret80"] = max(
            difs["ret80"],
            abs(ret_atr(entry_open=eo, preco=p80.close, atr=atr) - _f(linha["ret80_atr"])),
        )
        difs["ret240"] = max(
            difs["ret240"],
            abs(ret_atr(entry_open=eo, preco=p240.close, atr=atr) - _f(linha["ret240_atr"])),
        )
        for rotulo, ini, fim, cmax, cmin in (
            ("80", 1, H_CURTO, "max_close_80", "min_close_80"),
            ("240", 1, HORIZONTE, "max_close_240", "min_close_240"),
        ):
            ex = mfe_mae_closes(velas[d], entry_open=eo, atr=atr, ini=ini, fim=fim)
            difs[f"mfe{rotulo}"] = max(
                difs[f"mfe{rotulo}"],
                abs(ex.mfe - ret_atr(entry_open=eo, preco=_f(linha[cmax]), atr=atr)),
            )
            difs[f"mae{rotulo}"] = max(
                difs[f"mae{rotulo}"],
                abs(ex.mae - ret_atr(entry_open=eo, preco=_f(linha[cmin]), atr=atr)),
            )
        antes = mfe_mae_closes(velas[d], entry_open=eo, atr=atr, ini=1, fim=m_saida)
        depois = mfe_mae_closes(
            velas[d], entry_open=eo, atr=atr, ini=m_saida + 1, fim=HORIZONTE
        )
        ncomp["antes"] += int(antes.n == int(linha["n_antes"]))
        ncomp["depois"] += int(depois.n == int(linha["n_depois"]))
        if antes.n:
            difs["antes_max"] = max(
                difs["antes_max"],
                abs(antes.mfe - ret_atr(entry_open=eo, preco=_f(linha["max_close_antes"]), atr=atr)),
            )
            difs["antes_min"] = max(
                difs["antes_min"],
                abs(antes.mae - ret_atr(entry_open=eo, preco=_f(linha["min_close_antes"]), atr=atr)),
            )
        if depois.n:
            difs["depois_max"] = max(
                difs["depois_max"],
                abs(depois.mfe - ret_atr(entry_open=eo, preco=_f(linha["max_close_depois"]), atr=atr)),
            )
            difs["depois_min"] = max(
                difs["depois_min"],
                abs(depois.mae - ret_atr(entry_open=eo, preco=_f(linha["min_close_depois"]), atr=atr)),
            )
    print("maior divergencia absoluta SQL x Python (em ATR), por coluna:")
    for k, v in difs.items():
        print(f"   {k:<12} {v:.3e}")
    print(f"n_antes conferido em {ncomp['antes']}/{len(dec)} decisoes; "
          f"n_depois em {ncomp['depois']}/{len(dec)}")

    # --------------------------------------------------- populacao do Delta
    pontos_atr: dict[str, dict[int, float]] = {}
    pontos_pct: dict[str, dict[int, float]] = {}
    for d, linha in dec.items():
        eo, atr = float(linha["entry_open"]), float(linha["atr"])
        por_minuto = {v.minuto: v.close for v in velas[d]}
        pontos_atr[d] = {
            h: ret_atr(entry_open=eo, preco=por_minuto[h], atr=atr) for h in (H_CURTO, H_LONGO)
        }
        pontos_pct[d] = {
            h: ret_pct(entry_open=eo, preco=por_minuto[h]) for h in (H_CURTO, H_LONGO)
        }
    par_atr = delta_por_decisao(pontos_atr, h_longo=H_LONGO, h_curto=H_CURTO)
    par_pct = delta_por_decisao(pontos_pct, h_longo=H_LONGO, h_curto=H_CURTO)
    ordem = sorted(par_atr.deltas)
    dias = [dec[d]["dia"] for d in ordem]
    motivos = [dec[d]["motivo"] for d in ordem]
    mercados = [dec[d]["mercado"] for d in ordem]
    v_atr = np.array([par_atr.deltas[d] for d in ordem])
    v_pct = np.array([par_pct.deltas[d] for d in ordem])

    print("\n" + "=" * 78)
    print("§1 O DELTA AGREGADO — a reproducao do numero do D-P23, de outro dump")
    print("=" * 78)
    print(f"pares com os DOIS pontos: {len(ordem)}   "
          f"so +80: {len(par_atr.so_curto)}   so +240: {len(par_atr.so_longo)}")
    for rotulo, v in (("ATR", v_atr), ("% do preco", v_pct)):
        im = ic_media(dias, v, reamostragens=REAMOSTRAGENS, seed=SEED)
        imd = ic_mediana_blocos(dias, v, reamostragens=REAMOSTRAGENS, seed=SEED)
        print(
            f"  D(240-80) em {rotulo:<11} media {im.media:+.4f} "
            f"IC95 [{im.ic95[0]:+.4f}; {im.ic95[1]:+.4f}]   "
            f"mediana {imd.media:+.4f} IC95 [{imd.ic95[0]:+.4f}; {imd.ic95[1]:+.4f}]   "
            f"{100 * (v > 0).mean():.1f}% dos pares com D > 0   dias {im.dias}"
        )

    # ---------------------------------------------------------------- §2/§3
    print("\n" + "=" * 78)
    print("§2 A TABELA — decomposicao do D(240-80) pelo MOTIVO REAL DE SAIDA (ATR)")
    print("=" * 78)
    g_atr, t_atr = decompoe(dias, motivos, v_atr, reamostragens=REAMOSTRAGENS, seed=SEED)
    tabela("  em ATR da propria decisao (long-only, bruto a partir do open da entrada)",
           g_atr, t_atr)
    tabela_decis("  decis (MUST-FIX 3: 'cauda' e leitura a CONFIRMAR, nao achado)",
                 g_atr, t_atr)

    print("\n" + "=" * 78)
    print("§3 A MESMA TABELA EM % DO PRECO DE ENTRADA")
    print("=" * 78)
    g_pct, t_pct = decompoe(dias, motivos, v_pct, reamostragens=REAMOSTRAGENS, seed=SEED)
    tabela("  em pontos percentuais do preco de entrada", g_pct, t_pct, casas=4)
    tabela_decis("  decis, em % do preco", g_pct, t_pct)

    print("\n  ATR% por grupo (o denominador NAO e o mesmo entre grupos):")
    print(f"{'motivo':<13}{'n':>5}{'atr% p50':>10}{'atr% media':>12}")
    for g in MOTIVOS:
        sel = [float(dec[d]["atr_pct"]) for d in ordem if dec[d]["motivo"] == g]
        if not sel:
            print(f"{g:<13}{0:>5}{'—':>10}{'—':>12}")
            continue
        a = np.array(sel)
        print(f"{g:<13}{a.size:>5}{np.percentile(a, 50):>10.4f}{a.mean():>12.4f}")

    # ---------------------------------------------------------------- §4
    print("\n" + "=" * 78)
    print("§4 TIME-STOP CONTRA STOP — a pergunta do brief, isolada")
    print("=" * 78)
    par = [i for i, m in enumerate(motivos) if m in ("time-stop", "stop")]
    dias_p = [dias[i] for i in par]
    mot_p = [motivos[i] for i in par]
    print(f"populacao restrita: {len(par)} decisoes "
          f"({mot_p.count('time-stop')} time-stop + {mot_p.count('stop')} stop), "
          f"{len(set(dias_p))} dias")
    for rotulo, v in (("ATR", v_atr), ("% do preco", v_pct)):
        vp = v[par]
        g_r, t_r = decompoe(
            dias_p, mot_p, vp,
            grupos=("stop", "time-stop"),
            reamostragens=REAMOSTRAGENS, seed=SEED,
        )
        print(f"\n  --- em {rotulo} (contribuicoes recompoem a media DESTA populacao, N={len(par)})")
        print(
            f"{'motivo':<13}{'n':>5}{'dias':>6}{'media':>10}{'mediana':>10}"
            f"{'IC95 media':>22}{'contrib':>10}{'%>0':>8}{'decil sup':>11}"
        )
        for g in ("stop", "time-stop", "todos"):
            r = t_r if g == "todos" else g_r[g]
            ic_m = f"[{_n(r.ic_media[0])}; {_n(r.ic_media[1])}]"
            pos = "     —" if np.isnan(r.frac_pos) else f"{100 * r.frac_pos:5.1f}%"
            print(
                f"{r.motivo:<13}{r.n:>5}{r.dias:>6}{_n(r.media):>10}{_n(r.mediana):>10}"
                f"{ic_m:>22}{_n(r.contribuicao):>10}{pos:>8}{_n(r.contrib_decil_sup):>11}"
            )
        mascara = np.array([m == "time-stop" for m in mot_p], dtype=bool)
        d2 = delta_pareado_por_dia(
            dias_p, vp, mascara, reamostragens=REAMOSTRAGENS, seed=SEED
        )
        print(
            f"  contraste time-stop - stop = {d2.delta:+.4f} "
            f"IC95 [{d2.ic95[0]:+.4f}; {d2.ic95[1]:+.4f}]  "
            f"(pareado por DIA, {d2.reamostragens_validas}/{REAMOSTRAGENS} reamostragens com os dois lados)"
        )

    # ---------------------------------------------------------------- §4b
    print("\n" + "=" * 78)
    print("§4b O MESMO DELTA PARTIDO EM 'DENTRO DA POSICAO' E 'DEPOIS DA SAIDA REAL'")
    print("=" * 78)
    print("  D_i = [ret(c) - ret(80)] + [ret(240) - ret(c)],  c = clamp(m_saida, 80, 240)")
    print("  a esquerda: o trecho que a posicao de verdade atravessou (dinheiro que ela")
    print("  poderia ter guardado); a direita: o trecho depois da saida (dinheiro que ela")
    print("  nao podia tocar). A identidade e exata por telescopagem.")
    print("  O corte e o FECHAMENTO que cai em `exit_ts`, nao o `exit_price` sintetico —")
    print("  nada aqui e o resultado realizado da operacao (esse e o r_multiple, EXP-0025).")
    for rotulo, unidade in (("ATR", "atr"), ("% do preco", "pct")):
        emp, dep = [], []
        for d in ordem:
            eo, atr = float(dec[d]["entry_open"]), float(dec[d]["atr"])
            pm = {v.minuto: v.close for v in velas[d]}
            rets = (
                {m: ret_atr(entry_open=eo, preco=c, atr=atr) for m, c in pm.items()}
                if unidade == "atr"
                else {m: ret_pct(entry_open=eo, preco=c) for m, c in pm.items()}
            )
            a, b = divide_delta(
                rets, m_saida=int(dec[d]["m_saida"]), h_curto=H_CURTO, h_longo=H_LONGO
            )
            emp.append(a)
            dep.append(b)
        v_emp, v_dep = np.array(emp), np.array(dep)
        v_tot = v_atr if unidade == "atr" else v_pct
        erro = float(np.abs(v_emp + v_dep - v_tot).max())
        g_e, t_e = decompoe(dias, motivos, v_emp, reamostragens=REAMOSTRAGENS, seed=SEED)
        g_d, t_d = decompoe(dias, motivos, v_dep, reamostragens=REAMOSTRAGENS, seed=SEED)
        print(f"\n  --- em {rotulo}   (maior erro da identidade por decisao: {erro:.2e})")
        print(
            f"{'motivo':<13}{'n':>5}{'contrib dentro':>16}{'IC95 dentro':>22}"
            f"{'contrib depois':>16}{'IC95 depois':>22}{'soma':>10}"
        )
        for g in list(MOTIVOS) + ["todos"]:
            re_, rd = (t_e, t_d) if g == "todos" else (g_e[g], g_d[g])
            ic_e = f"[{_n(re_.ic_contribuicao[0])}; {_n(re_.ic_contribuicao[1])}]"
            ic_d = f"[{_n(rd.ic_contribuicao[0])}; {_n(rd.ic_contribuicao[1])}]"
            print(
                f"{g:<13}{re_.n:>5}{_n(re_.contribuicao):>16}{ic_e:>22}"
                f"{_n(rd.contribuicao):>16}{ic_d:>22}"
                f"{_n(re_.contribuicao + rd.contribuicao):>10}"
            )
        n_so_depois = sum(1 for d in ordem if int(dec[d]["m_saida"]) <= H_CURTO)
        n_so_dentro = sum(1 for d in ordem if int(dec[d]["m_saida"]) >= H_LONGO)
        print(
            f"  decisoes cujo trecho 80->240 e INTEIRAMENTE depois da saida: {n_so_depois} "
            f"({100 * n_so_depois / len(ordem):.1f}%); inteiramente dentro da posicao: "
            f"{n_so_dentro} ({100 * n_so_dentro / len(ordem):.1f}%); partido: "
            f"{len(ordem) - n_so_depois - n_so_dentro}"
        )

    # ---------------------------------------------------------------- §5
    print("\n" + "=" * 78)
    print("§5 EXCURSOES DE CLOSES — COLUNAS AUXILIARES (nao decompoem o Delta)")
    print("=" * 78)
    print("  MFE/MAE = maximo/minimo do RETORNO DE FECHAMENTO na janela, com sinal")
    print("  (OHLC nao revela ordem intrabar; nada aqui e 'o maximo que a posicao viu')")
    print()
    print(
        f"{'motivo':<13}{'n':>5}{'mfe80':>9}{'mae80':>9}{'mfe240':>9}{'mae240':>9}"
        f"{'m_saida':>9}{'mfe antes':>11}{'mae antes':>11}{'n>0 dep':>9}"
        f"{'mfe depois':>12}{'mae depois':>12}"
    )
    for g in list(MOTIVOS) + ["todos"]:
        sel = [d for d in ordem if g == "todos" or dec[d]["motivo"] == g]
        if not sel:
            print(f"{g:<13}{0:>5}" + "        —" * 4 + "        —" + "          —" * 2
                  + "        —" + "           —" * 2)
            continue
        col: dict[str, list[float]] = {k: [] for k in
                                       ("mfe80", "mae80", "mfe240", "mae240",
                                        "mfe_a", "mae_a", "mfe_d", "mae_d")}
        m_saidas, com_depois = [], 0
        for d in sel:
            eo, atr = float(dec[d]["entry_open"]), float(dec[d]["atr"])
            ms = int(dec[d]["m_saida"])
            m_saidas.append(ms)
            e80 = mfe_mae_closes(velas[d], entry_open=eo, atr=atr, ini=1, fim=H_CURTO)
            e240 = mfe_mae_closes(velas[d], entry_open=eo, atr=atr, ini=1, fim=HORIZONTE)
            ea = mfe_mae_closes(velas[d], entry_open=eo, atr=atr, ini=1, fim=ms)
            ed = mfe_mae_closes(velas[d], entry_open=eo, atr=atr, ini=ms + 1, fim=HORIZONTE)
            col["mfe80"].append(e80.mfe); col["mae80"].append(e80.mae)
            col["mfe240"].append(e240.mfe); col["mae240"].append(e240.mae)
            col["mfe_a"].append(ea.mfe); col["mae_a"].append(ea.mae)
            if ed.n:
                com_depois += 1
                col["mfe_d"].append(ed.mfe); col["mae_d"].append(ed.mae)

        def md(chave: str) -> str:
            a = np.array(col[chave], dtype=float)
            a = a[~np.isnan(a)]
            return "        —" if a.size == 0 else f"{np.percentile(a, 50):+9.4f}"

        print(
            f"{g:<13}{len(sel):>5}{md('mfe80')}{md('mae80')}{md('mfe240')}{md('mae240')}"
            f"{int(np.percentile(m_saidas, 50)):>9}{md('mfe_a'):>11}{md('mae_a'):>11}"
            f"{com_depois:>9}{md('mfe_d'):>12}{md('mae_d'):>12}"
        )
    print("  (medianas; `m_saida` e o minuto em que a vela da saida fecha, contado da entrada)")

    # ---------------------------------------------------------------- §6
    print("\n" + "=" * 78)
    print("§6 SENSIBILIDADE — o Delta agregado e a historia de um dia? de um mercado?")
    print("=" * 78)
    for rotulo, chaves in (("dia", dias), ("mercado", mercados)):
        base = float(v_atr.mean())
        pior_nome, pior_valor = None, base
        for alvo in sorted(set(chaves)):
            mascara = np.array([c != alvo for c in chaves], dtype=bool)
            if mascara.sum() == 0:
                continue
            m = float(v_atr[mascara].mean())
            if abs(m - base) > abs(pior_valor - base):
                pior_nome, pior_valor = alvo, m
        print(
            f"  tirando um {rotulo} de cada vez ({len(set(chaves))} {rotulo}s): "
            f"a media vai de {base:+.4f} para, no extremo, {pior_valor:+.4f} "
            f"(sem {pior_nome}) — variacao {pior_valor - base:+.4f}"
        )
    ordenado = np.sort(v_atr)
    k = int(np.ceil(v_atr.size / 10))
    print(
        f"  decil superior ({k} de {v_atr.size}) contribui {ordenado[-k:].sum() / v_atr.size:+.4f} "
        f"de {v_atr.mean():+.4f}; decil inferior {ordenado[:k].sum() / v_atr.size:+.4f}; "
        f"os {v_atr.size - 2 * k} do meio {ordenado[k:-k].sum() / v_atr.size:+.4f}"
    )
    print(
        f"  contribuicao do decil superior por grupo (ATR): "
        + "  ".join(
            f"{g}={contribuicao_decil(v_atr[np.array([m == g for m in motivos])], n_total=v_atr.size, alto=True):+.4f}"
            for g in MOTIVOS
            if any(m == g for m in motivos)
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
