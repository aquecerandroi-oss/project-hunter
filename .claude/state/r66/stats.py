"""R66 Q4 - o que separa vencedoras de perdedoras DEPOIS da graduacao, e a validacao
do board contra a fita do pool.

Metodo herdado do R65, com os ajustes que a Astra pediu:
- ha UMA entrada por mint, logo o bootstrap por cluster de mint degenera; o cluster que
  importa aqui e o DIA (8 dias) - reamostro dias inteiros.
- a permutacao e ESTRATIFICADA POR DIA (embaralho o desfecho dentro do dia), para um p
  pequeno nao poder ser so "esta feature identifica uma hora boa".
- Benjamini-Hochberg a 10 % sobre a familia inteira de contrastes desta analise.
- so entram variaveis observaveis NO INSTANTE DA ENTRADA (a 1a leitura do board pos
  graduacao) ou antes dele (idade da curva). Nada de leitura posterior.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
from decimal import Decimal
from pathlib import Path

from load import HERE, entry_point, load_board, load_tokens, ts
from metrics import pct
from sim import RULES, simulate

random.seed(20260922)
ITERS = 10_000

FEATURES = (
    ("mcap_sol", "market cap na entrada (SOL)"),
    ("volume_sol", "volume acumulado da curva (SOL)"),
    ("volume_5m_sol", "volume 5 min (SOL)"),
    ("txs", "transacoes"),
    ("buys", "compras"),
    ("sells", "vendas"),
    ("sell_ratio", "vendas / compras"),
    ("holders", "holders"),
    ("participants", "participantes"),
    ("top10", "top-10 share"),
    ("dev_share", "dev share"),
    ("snipers", "snipers"),
    ("kol", "KOLs"),
    ("age_to_grad_s", "idade da criacao ate a graduacao (s)"),
)


def xval(series: dict[str, list[dict]], out: list[str]) -> None:
    """O market cap do board bate com preco da fita x supply? (so onde ha as duas coisas)"""
    tape: dict[str, list[tuple]] = {}
    with open(HERE / "amm.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            price = Decimal(r["price"]) if r["price"] else None
            if not price or price <= 0:
                continue
            tape.setdefault(r["mint"], []).append((ts(r["block_time"]), price))
    pairs = []
    for mint, obs in series.items():
        t = tape.get(mint)
        if not t:
            continue
        e = entry_point(obs)
        if e is None:
            continue
        near = [(abs((bt - e["observed_at"]).total_seconds()), p) for bt, p in t]
        gap, price = min(near, key=lambda x: x[0])
        if gap > 30:
            continue
        fdv_tape = price * Decimal(1_000_000_000)
        pairs.append((float(e["mcap_sol"]), float(fdv_tape)))
    out.append("== R66 - validacao do board contra a fita do pool (pump_amm) ==")
    if not pairs:
        out.append("sem sobreposicao")
        return
    ratios = [b / t for b, t in pairs if t > 0]
    out.append(
        f"mints com fita a <= 30 s da 1a leitura do board: {len(pairs)}\n"
        f"razao (market cap do board) / (preco da fita x 1e9 supply): "
        f"p10 {pct(ratios,0.1):.3f} | mediana {pct(ratios,0.5):.3f} | p90 {pct(ratios,0.9):.3f}\n"
        f"dentro de +-10 %: {100*sum(1 for r in ratios if 0.9<=r<=1.1)/len(ratios):.1f} %"
    )


def build_rows(series: dict[str, list[dict]], tokens: dict[str, dict]) -> list[dict]:
    rule = RULES[0]
    rows = []
    for mint, obs in series.items():
        e = entry_point(obs)
        if e is None:
            continue
        r = simulate(obs, e, rule, True)
        if r is None or r["censored"]:  # censurada nao tem desfecho observavel
            continue
        tok = tokens.get(mint, {})
        age = None
        if tok.get("created_at") and tok.get("migrated_at"):
            age = (tok["migrated_at"] - tok["created_at"]).total_seconds()
        row = dict(
            mint=mint, day=str(r["day"]), pnl=float(r["pnl"]), target=r["reason"] == "target",
            mcap_sol=float(e["mcap_sol"]),
            volume_sol=float(e["volume_sol"]) if e["volume_sol"] is not None else None,
            volume_5m_sol=float(e["volume_5m_sol"]) if e["volume_5m_sol"] is not None else None,
            txs=e["txs"], buys=e["buys"], sells=e["sells"],
            sell_ratio=(e["sells"] / e["buys"]) if (e["buys"] or 0) > 0 else None,
            holders=e["holders"], participants=e["participants"],
            top10=float(e["top10"]) if e["top10"] is not None else None,
            dev_share=float(e["dev_share"]) if e["dev_share"] is not None else None,
            snipers=e["snipers"], kol=e["kol"], age_to_grad_s=age,
        )
        rows.append(row)
    return rows


def perm_p(rows: list[dict], key: str, lo: float, hi: float) -> tuple[float, float, int, int]:
    """Diferenca de PnL medio entre o terco de cima e o de baixo, p por permutacao
    estratificada por dia."""
    top = [r for r in rows if r[key] is not None and r[key] >= hi]
    bot = [r for r in rows if r[key] is not None and r[key] <= lo]
    if len(top) < 30 or len(bot) < 30:
        return float("nan"), float("nan"), len(bot), len(top)
    obs = statistics.mean(r["pnl"] for r in top) - statistics.mean(r["pnl"] for r in bot)
    pool = top + bot
    by_day: dict[str, list[dict]] = {}
    for r in pool:
        by_day.setdefault(r["day"], []).append(r)
    n_top_by_day = {d: sum(1 for r in v if r in top) for d, v in by_day.items()}
    hits = 0
    for _ in range(ITERS):
        t_sum, t_n, b_sum, b_n = 0.0, 0, 0.0, 0
        for d, v in by_day.items():
            pnls = [r["pnl"] for r in v]
            random.shuffle(pnls)
            k = n_top_by_day[d]
            t_sum += sum(pnls[:k]); t_n += k
            b_sum += sum(pnls[k:]); b_n += len(pnls) - k
        if t_n and b_n and abs(t_sum / t_n - b_sum / b_n) >= abs(obs):
            hits += 1
    return obs, (hits + 1) / (ITERS + 1), len(bot), len(top)


def day_bootstrap(rows: list[dict], key: str, lo: float, hi: float) -> tuple[float, float]:
    days = sorted({r["day"] for r in rows})
    by_day = {d: [r for r in rows if r["day"] == d] for d in days}
    diffs = []
    for _ in range(2000):
        sample = [r for d in random.choices(days, k=len(days)) for r in by_day[d]]
        top = [r["pnl"] for r in sample if r[key] is not None and r[key] >= hi]
        bot = [r["pnl"] for r in sample if r[key] is not None and r[key] <= lo]
        if len(top) < 10 or len(bot) < 10:
            continue
        diffs.append(statistics.mean(top) - statistics.mean(bot))
    if not diffs:
        return float("nan"), float("nan")
    diffs.sort()
    return diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs))]


def main() -> None:
    tokens = load_tokens()
    series = load_board(tokens)
    out: list[str] = []
    xval(series, out)
    out.append("")

    rows = build_rows(series, tokens)
    out.append(f"== R66 Q4 - selecao: {len(rows)} entradas, desfecho = PnL da regra da mesa "
               f"(1,15x / trail 10 % / 300 s, rent devolvido) ==")
    out.append(f"PnL medio global: {statistics.mean(r['pnl'] for r in rows):+.6f} SOL | "
               f"taxa de alvo: {100*sum(r['target'] for r in rows)/len(rows):.1f} %")
    out.append("")
    out.append(f"{'variavel':<38} {'n baixo':>7} {'n alto':>7} {'PnL baixo':>10} {'PnL alto':>10} "
               f"{'dif':>10} {'IC95 dia':>22} {'p perm':>8}")

    results = []
    for key, label in FEATURES:
        vals = [r[key] for r in rows if r[key] is not None]
        if len(vals) < 200:
            out.append(f"{label:<38} (sem dados: n={len(vals)})")
            continue
        lo, hi = pct([float(v) for v in vals], 1 / 3), pct([float(v) for v in vals], 2 / 3)
        if lo == hi:
            out.append(f"{label:<38} (sem variancia util: tercos iguais)")
            continue
        diff, p, nb, nt = perm_p(rows, key, lo, hi)
        ci = day_bootstrap(rows, key, lo, hi)
        bot = statistics.mean(r["pnl"] for r in rows if r[key] is not None and r[key] <= lo)
        top = statistics.mean(r["pnl"] for r in rows if r[key] is not None and r[key] >= hi)
        out.append(f"{label:<38} {nb:>7} {nt:>7} {bot:>10.6f} {top:>10.6f} {diff:>10.6f} "
                   f"[{ci[0]:+.6f},{ci[1]:+.6f}] {p:>8.4f}")
        results.append((label, p))

    out.append("")
    out.append("== Benjamini-Hochberg, FDR 10 %, sobre os contrastes acima ==")
    ok = [(lbl, p) for lbl, p in results if p == p]
    ok.sort(key=lambda x: x[1])
    m = len(ok)
    survivors = []
    for i, (lbl, p) in enumerate(ok, start=1):
        thr = 0.10 * i / m
        out.append(f"  {i:>2}. {lbl:<38} p={p:.4f}  limiar BH={thr:.4f}  "
                   f"{'SOBREVIVE' if p <= thr else '-'}")
        if p <= thr:
            survivors.append(lbl)
    out.append(f"sobreviventes: {survivors if survivors else 'NENHUM'}")

    text = "\n".join(out)
    print(text)
    Path(HERE / "stats.txt").write_text(text + "\n", encoding="utf-8")
    json.dump(rows, open(HERE / "rows.json", "w"))


if __name__ == "__main__":
    main()
