"""T3.84 passo 3 -- a leitura da coorte de 90 d da `mean_reversion_m5 v1` (EXP-0028).

Entrada: o CSV de `infra/scripts/sql/research/2026-09-11-t384-q03-dump-decisoes-m5.sql`
(a coorte `replay:92c8d080-...` e o controle pre-declarado `mean_reversion v1`,
coorte `replay:fa005985-...` da EXP-0025 -- que **nao** foi re-rodado).

O bootstrap e o mesmo modulo das EXP-0025/0026 (`.claude/state/exp-drafts/t362b/blocos90.py`),
com a **mesma semente 20260910** e as mesmas 20 000 reamostragens: trocar qualquer
um dos dois tornaria os IC incomparaveis com as duas paginas que esta compara.
Bloco = o **dia inteiro** (KB-0010): decisoes do mesmo dia em mercados
correlacionados dividem regime e choque.

Nada aqui e dinheiro persistido, entao nada aqui e `Decimal` (a fronteira
`Decimal` fica no banco, PIPELINE §9). NumPy sobre janelas em memoria; sem pandas.

    uv run python .claude/state/exp-drafts/t384/analise.py \
        .claude/state/exp-drafts/t384/decisoes-m5-e-mae.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "t362b"))

from blocos90 import delta_pareado_por_dia, ic_media, profit_factor  # noqa: E402

FILHA = "mean_reversion_m5 v1"
MAE = "mean_reversion v1"
# Os 16 elegiveis da regra T3.82, na ordem da pagina. Dois deles (BNB, BTC) nao
# produziram nenhuma decisao a 5 min: o leave-one-market-out deles e a populacao
# inteira, e isso e dito em voz alta em vez de ser omitido da tabela.
UNIVERSO = (
    "ARBUSDT BNBUSDT BTCUSDT DASHUSDT DOGEUSDT ETHUSDT LINKUSDT NEARUSDT "
    "PROMUSDT SAHARAUSDT SOLUSDT SUIUSDT TAOUSDT UNIUSDT XRPUSDT ZECUSDT"
).split()


def carregar(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def recorte(linhas: list[dict[str, str]], versao: str) -> tuple[list[str], np.ndarray, np.ndarray, list[str], np.ndarray]:
    """dias, r_exf, r_bruto, mercados, atr_pct de uma versao -- na ordem do dump."""
    sel = [r for r in linhas if r["versao"] == versao]
    dias = [r["dia"] for r in sel]
    r_exf = np.array([float(r["r_exf"]) for r in sel], dtype=float)
    r_bruto = np.array([float(r["r_bruto"]) for r in sel], dtype=float)
    mercados = [r["mercado"] for r in sel]
    atr = np.array([float(r["atr_pct"]) for r in sel], dtype=float)
    return dias, r_exf, r_bruto, mercados, atr


def linha_ic(rotulo: str, dias: list[str], valores: np.ndarray) -> str:
    iv = ic_media(dias, valores)
    pf = profit_factor(valores)
    sinal = "acima de zero" if iv.ic95[0] > 0 else ("abaixo de zero" if iv.ic95[1] < 0 else "cruza zero")
    return (
        f"{rotulo:<34} n={iv.n:>4} dias={iv.dias:>3} media={iv.media:+.4f} "
        f"IC95=[{iv.ic95[0]:+.4f}; {iv.ic95[1]:+.4f}] ({sinal})  PF={pf:.4f}"
    )


def main(argv: list[str]) -> int:
    caminho = Path(argv[1]) if len(argv) > 1 else Path("decisoes-m5-e-mae.csv")
    linhas = carregar(caminho)

    print("=" * 108)
    print("T3.84 / EXP-0028 -- leitura da coorte replay:92c8d080-6009-4a59-9868-31282b1bd493")
    print("bootstrap: blocos de DIA, 20 000 reamostragens, semente 20260910 (as mesmas das EXP-0025/0026)")
    print("=" * 108)

    dados = {v: recorte(linhas, v) for v in (FILHA, MAE)}

    print("\n-- 1. REGRA DE SUCESSO No 1 -- expectativa ex-funding em 90 d com IC de blocos de dia")
    for v in (FILHA, MAE):
        dias, r_exf, _, _, _ = dados[v]
        print(linha_ic(f"{v} | r_ex_funding", dias, r_exf))
    print("\n-- expectativa BRUTA (a clausula de K3: bruta < 0 com >= 100 desfechos e >= 30 dias)")
    for v in (FILHA, MAE):
        dias, _, r_bruto, _, _ = dados[v]
        print(linha_ic(f"{v} | r_bruto", dias, r_bruto))

    print("\n-- 2. REGRA No 2 -- PF por janela de 30 d (precisa de PF > 1 em >= 2 de 3)")
    for v in (FILHA, MAE):
        dias, r_exf, r_bruto, _, _ = dados[v]
        sel = [r for r in linhas if r["versao"] == v]
        for janela in ("J1", "J2", "J3"):
            masc = np.array([r["janela"] == janela for r in sel], dtype=bool)
            if not masc.any():
                print(f"{v} | {janela}: nenhuma decisao")
                continue
            dj = [d for d, m in zip(dias, masc, strict=True) if m]
            print(linha_ic(f"{v} | {janela} | r_ex_funding", dj, r_exf[masc]))

    print("\n-- 3. REGRA No 3 -- leave-one-market-out (16 reajustes, um por mercado do universo)")
    for v in (FILHA, MAE):
        dias, r_exf, _, mercados, _ = dados[v]
        print(f"   [{v}]")
        for fora in UNIVERSO:
            masc = np.array([m != fora for m in mercados], dtype=bool)
            if masc.all():
                nota = "  (mercado sem decisao: a populacao nao muda)"
            else:
                nota = ""
            dj = [d for d, m in zip(dias, masc, strict=True) if m]
            print("   " + linha_ic(f"sem {fora}", dj, r_exf[masc]) + nota)

    print("\n-- 4. filha contra a mae, Delta PAREADO POR DIA (as duas dividem o calendario de 90 d)")
    dias_j = [r["dia"] for r in linhas if r["versao"] in (FILHA, MAE)]
    val_j = np.array([float(r["r_exf"]) for r in linhas if r["versao"] in (FILHA, MAE)], dtype=float)
    eh_filha = np.array([r["versao"] == FILHA for r in linhas if r["versao"] in (FILHA, MAE)], dtype=bool)
    d = delta_pareado_por_dia(dias_j, val_j, eh_filha)
    print(
        f"   filha n={d.n_a} media={d.media_a:+.4f} | mae n={d.n_b} media={d.media_b:+.4f} | "
        f"Delta={d.delta:+.4f} IC95=[{d.ic95[0]:+.4f}; {d.ic95[1]:+.4f}] "
        f"(reamostragens validas {d.reamostragens_validas})"
    )

    print("\n-- 5. DE ONDE VEM A PIORA: custo medido vs vantagem bruta (identidade, nao modelo)")
    print("   custo medio por decisao em R = media(r_bruto) - media(r_ex_funding), exato por construcao")
    for v in (FILHA, MAE):
        _, r_exf, r_bruto, _, atr = dados[v]
        custo = float(r_bruto.mean() - r_exf.mean())
        pedagio_ident = float(np.median(0.0020 / atr))
        print(
            f"   {v:<22} bruta={r_bruto.mean():+.4f}  liquida={r_exf.mean():+.4f}  "
            f"custo={custo:.4f} R   |  KB-0076 0,0020/ATR% p50 = {pedagio_ident:.4f} R  "
            f"(ATR% p50 = {100*float(np.median(atr)):.4f} %)"
        )
    cf = float(dados[FILHA][2].mean() - dados[FILHA][1].mean())
    cm = float(dados[MAE][2].mean() - dados[MAE][1].mean())
    gf, gm = float(dados[FILHA][2].mean()), float(dados[MAE][2].mean())
    piora = (dados[FILHA][1].mean() - dados[MAE][1].mean())
    print(
        f"   Delta liquida (filha - mae) = {piora:+.4f} R  =  Delta bruta {gf - gm:+.4f} R  "
        f"-  Delta custo {cf - cm:+.4f} R"
    )
    total = abs(gf - gm) + abs(cf - cm)
    print(
        f"   fracao da piora explicada pela vantagem BRUTA = {100*abs(gf-gm)/total:.1f} %"
        f" | pelo CUSTO = {100*abs(cf-cm)/total:.1f} %"
    )

    print("\n-- 6. as duas metades de C5 (banda de risco do paper_v1 [0,3 %; 3 %])")
    for v in (FILHA, MAE):
        sel = [r for r in linhas if r["versao"] == v]
        risco = np.array([float(r["risco_pct"]) for r in sel], dtype=float)
        print(
            f"   {v:<22} n={risco.size:>4} p50={100*float(np.median(risco)):.4f} % "
            f"abaixo de 0,3 % = {int((risco < 0.003).sum())} ({100*float((risco < 0.003).mean()):.2f} %) "
            f"acima de 3 % = {int((risco > 0.03).sum())} ({100*float((risco > 0.03).mean()):.2f} %)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
