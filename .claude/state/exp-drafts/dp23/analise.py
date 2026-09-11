"""D-P23 — le o CSV do q01 e imprime a curva, a cobertura e os Delta pareados.

Secoes:
  §0  cobertura por coorte e por horizonte (declarada, nunca suposta)
  §0b checagem cruzada: o `ret_atr` do SQL contra o `ret_atr` do Python
  §1  a curva da mae (`mean_reversion v1`, 542 decisoes, h = 5..240)
  §2  o Delta pareado por decisao contra +80 min, com IC de blocos de dia
  §3  a curva da irma de 5 min (`mean_reversion_m5 v1`, 373 decisoes, h = 5..80)
  §4  a curva da mae RESTRITA aos mesmos mercados/dias da irma (so comparacao)

Uso: uv run --with numpy python analise.py <csv>
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from curva import (  # noqa: E402
    curva_por_horizonte,
    delta_pareado_por_decisao,
    diferencas_pareadas,
    ic_mediana_blocos,
    ret_atr,
)

MAE = "replay:fa005985-0b55-4820-904c-8ada589e441c"
IRMA = "replay:92c8d080-6009-4a59-9868-31282b1bd493"
H_MAE = (5, 10, 15, 30, 60, 80, 120, 180, 240)
H_IRMA = (5, 10, 15, 30, 60, 80)
REAMOSTRAGENS = 20_000
SEED = 20260910


def carrega(caminho: Path) -> list[dict[str, str]]:
    linhas: list[dict[str, str]] = []
    cab: list[str] | None = None
    for cru in caminho.read_text(encoding="utf-8").splitlines():
        if cab is None:
            if cru.startswith("coorte,versao,"):
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
        raise SystemExit("cabecalho nao encontrado")
    return linhas


def _f(txt: str) -> float:
    return float("nan") if txt == "" else float(txt)


def tabela_curva(titulo, tuplas, horizontes):
    print()
    print(titulo)
    print(
        f"{'h(min)':>7} {'n':>5} {'media':>9} {'mediana':>9} {'p25':>9} "
        f"{'p75':>9} {'%>0':>7} {'zeros':>6}"
    )
    curva = curva_por_horizonte([(d, h, r) for d, _dia, h, r in tuplas], horizontes=horizontes)
    for h in horizontes:
        r = curva[h]
        print(
            f"{h:>7} {r.n:>5} {r.media:>+9.4f} {r.mediana:>+9.4f} {r.p25:>+9.4f} "
            f"{r.p75:>+9.4f} {100 * r.frac_pos:>6.1f}% {r.zeros:>6}"
        )
    return curva


def tabela_delta(titulo, tuplas, horizontes, base):
    print()
    print(titulo)
    rotulo = f"D(h-{base})"
    print(
        f"{rotulo:>12} {'n':>5} {'dias':>5} {'media':>9} {'mediana':>9} "
        f"{'IC95 inf':>10} {'IC95 sup':>10} {'exclui 0':>9}"
    )
    for h in horizontes:
        if h == base:
            continue
        d = delta_pareado_por_decisao(
            tuplas, h_longo=h, h_curto=base, reamostragens=REAMOSTRAGENS, seed=SEED
        )
        exclui = "sim" if (d.ic95[0] > 0 or d.ic95[1] < 0) else "nao"
        print(
            f"{h:>12} {d.n:>5} {d.dias:>5} {d.media:>+9.4f} {d.mediana:>+9.4f} "
            f"{d.ic95[0]:>+10.4f} {d.ic95[1]:>+10.4f} {exclui:>9}"
        )


def delta_240_80(rotulo, tuplas) -> None:
    """O Delta do brief com os DOIS estimadores, na mesma populacao pareada."""
    d = delta_pareado_por_decisao(
        tuplas, h_longo=240, h_curto=80, reamostragens=REAMOSTRAGENS, seed=SEED
    )
    dias_d, diffs = diferencas_pareadas(tuplas, h_longo=240, h_curto=80)
    med = ic_mediana_blocos(dias_d, diffs, reamostragens=REAMOSTRAGENS, seed=SEED)
    print()
    print(f"{rotulo}: n = {d.n} pares em {d.dias} dias")
    print(f"   media   D(240-80) = {d.media:+.4f}  IC95 [{d.ic95[0]:+.4f}; {d.ic95[1]:+.4f}]")
    print(f"   mediana D(240-80) = {med.media:+.4f}  IC95 [{med.ic95[0]:+.4f}; {med.ic95[1]:+.4f}]")
    print(f"   fracao de pares com D > 0: {100.0 * float((diffs > 0).mean()):.1f} %")


def main() -> None:
    caminho = Path(sys.argv[1])
    linhas = carrega(caminho)
    print(f"D-P23 — {len(linhas)} linhas de {caminho.name}")
    print(f"bootstrap: blocos de DIA (UTC), {REAMOSTRAGENS} reamostragens, semente {SEED}")
    print("percentis por interpolacao linear; %>0 conta positivos ESTRITOS")

    print()
    print("== §0b CHECAGEM CRUZADA: ret_atr do SQL vs ret_atr do Python ==")
    maior = 0.0
    conferidas = 0
    for ln in linhas:
        if ln["ret_atr"] == "":
            continue
        py = ret_atr(
            entry_open=float(ln["entry_open"]), preco=float(ln["preco"]), atr=float(ln["atr"])
        )
        maior = max(maior, abs(py - float(ln["ret_atr"])))
        conferidas += 1
    print(f"{conferidas} pontos conferidos; maior divergencia absoluta = {maior:.3e}")
    print("(o SQL arredonda em 8 casas; divergencia acima de 1e-8 seria defeito)")

    por_coorte: dict[str, list] = {MAE: [], IRMA: []}
    recorte_par: list = []
    recorte_largo: list = []
    dias_de: dict[str, str] = {}
    mercados: dict[str, set] = {MAE: set(), IRMA: set()}
    decisoes: dict[str, set] = {MAE: set(), IRMA: set()}
    direcoes: set = set()
    for ln in linhas:
        t = (ln["decisao"], ln["dia"], int(ln["horizonte_min"]), _f(ln["ret_atr"]))
        por_coorte[ln["coorte"]].append(t)
        dias_de[ln["decisao"]] = ln["dia"]
        mercados[ln["coorte"]].add(ln["mercado"])
        decisoes[ln["coorte"]].add(ln["decisao"])
        direcoes.add(ln["direcao"])
        if ln["coorte"] == MAE:
            if ln["no_recorte_par"] == "t":
                recorte_par.append(t)
            if ln["no_recorte_mercado_dia"] == "t":
                recorte_largo.append(t)

    print()
    print("== §0 COBERTURA ==")
    print(f"direcoes presentes: {sorted(direcoes)} (long-only e pre-condicao do metodo)")
    for coorte, rot, hs in (
        (MAE, "mae  mean_reversion v1", H_MAE),
        (IRMA, "irma mean_reversion_m5 v1", H_IRMA),
    ):
        tu = por_coorte[coorte]
        n_dec = len(decisoes[coorte])
        n_dias = len({dias_de[d] for d, _dia, _h, _r in tu})
        print()
        print(f"{rot}: {n_dec} decisoes, {len(mercados[coorte])} mercados, {n_dias} dias")
        for h in hs:
            vals = [r for _d, _dia, hh, r in tu if hh == h]
            pres = sum(1 for v in vals if not np.isnan(v))
            print(f"   +{h:>3} min: {pres:>4}/{n_dec} endpoints ({100.0 * pres / n_dec:6.2f} %)")

    print()
    print("== §1 A CURVA DA MAE (542 decisoes, bruta, em ATR da propria decisao) ==")
    curva_mae = tabela_curva("mean_reversion v1 — 16 mercados, 83 dias", por_coorte[MAE], H_MAE)

    print()
    print("== §2 DELTA PAREADO POR DECISAO CONTRA +80 min (IC de blocos de dia) ==")
    tabela_delta("mean_reversion v1", por_coorte[MAE], H_MAE, 80)
    print()
    print("O numero do brief, isolado:")
    d = delta_pareado_por_decisao(
        por_coorte[MAE], h_longo=240, h_curto=80, reamostragens=REAMOSTRAGENS, seed=SEED
    )
    print(
        f"   D(240 - 80) = {d.media:+.4f} ATR   IC95 [{d.ic95[0]:+.4f}; {d.ic95[1]:+.4f}]   "
        f"n = {d.n} pares em {d.dias} dias   mediana {d.mediana:+.4f}"
    )
    print(f"   decisoes com so o ponto de +80: {d.n_so_curto}; com so o de +240: {d.n_so_longo}")
    dias_d, diffs = diferencas_pareadas(por_coorte[MAE], h_longo=240, h_curto=80)
    med = ic_mediana_blocos(dias_d, diffs, reamostragens=REAMOSTRAGENS, seed=SEED)
    print(
        f"   mediana do MESMO Delta = {med.media:+.4f} ATR   "
        f"IC95 [{med.ic95[0]:+.4f}; {med.ic95[1]:+.4f}]   n = {med.n} em {med.dias} dias"
    )
    print(
        f"   fracao de pares com Delta > 0: {100.0 * float((diffs > 0).mean()):.1f} % "
        f"(a media e a mediana divergindo mede quanto da acumulacao esta na cauda)"
    )
    r80, r240 = curva_mae[80], curva_mae[240]
    print()
    print(
        f"   razao descritiva curva(80)/curva(240) = {r80.media / r240.media:.4f} "
        f"({r80.media:+.4f} / {r240.media:+.4f})"
    )
    print(
        "   (so descritiva; nao decide nada — a regra pre-registrada exige denominador "
        "separado de zero, e o veredito e do Delta pareado com IC)"
    )

    print()
    print("== §3 A CURVA DA IRMA DE 5 min (373 decisoes, h = 5..80, o horizonte dela) ==")
    tabela_curva("mean_reversion_m5 v1 — 14 mercados, 72 dias", por_coorte[IRMA], H_IRMA)
    tabela_delta("mean_reversion_m5 v1 — Delta pareado contra +80", por_coorte[IRMA], H_IRMA, 80)

    # --- §5 a mesma curva numa UNIDADE COMUM -------------------------------
    # O ATR da mae e de 15 min e o da irma e de 5 min (EXP-0028: ATR% p50
    # 0,5585 % contra 0,2714 %), entao "+0,20 ATR" nas duas NAO e o mesmo
    # movimento de preco. Esta secao repete as duas curvas em % do preco de
    # entrada -- a unica unidade que as duas coortes dividem. Ela nao substitui a
    # unidade do brief; ela impede a leitura errada dela.
    pct: dict[str, list] = {MAE: [], IRMA: []}
    for ln in linhas:
        if ln["preco"] == "":
            continue
        base = float(ln["entry_open"])
        r = 100.0 * (float(ln["preco"]) - base) / base
        pct[ln["coorte"]].append((ln["decisao"], ln["dia"], int(ln["horizonte_min"]), r))
    print()
    print("== §5 AS DUAS CURVAS NUMA UNIDADE COMUM: % DO PRECO DE ENTRADA ==")
    print("(o ATR da mae e 15 m e o da irma e 5 m -- '+0,20 ATR' nas duas nao e o")
    print(" mesmo movimento; esta secao existe so para impedir essa leitura)")
    tabela_curva("mae  mean_reversion v1 — % do preco de entrada", pct[MAE], H_MAE)
    tabela_curva("irma mean_reversion_m5 v1 — % do preco de entrada", pct[IRMA], H_IRMA)

    print()
    print("== §4 A MAE RESTRITA AOS MESMOS MERCADOS/DIAS DA IRMA (so comparacao) ==")
    n_par = len({d for d, _dia, _h, _r in recorte_par})
    n_largo = len({d for d, _dia, _h, _r in recorte_largo})
    print(f"recorte estrito (mesmo par mercado x dia): {n_par} decisoes")
    tabela_curva("mae | par (mercado, dia) da irma", recorte_par, H_MAE)
    delta_240_80("mae | par (mercado, dia) da irma", recorte_par)
    print()
    print(f"recorte largo (mesmos mercados E mesmos dias, sem exigir o par): {n_largo} decisoes")
    tabela_curva("mae | mercado in irma AND dia in irma", recorte_largo, H_MAE)
    delta_240_80("mae | mercado in irma AND dia in irma", recorte_largo)


if __name__ == "__main__":
    main()
