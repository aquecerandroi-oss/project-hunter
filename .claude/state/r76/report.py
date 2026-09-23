"""R76 — relatório completo (report.md) a partir de rows.json. Números reais, nada inventado."""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as R  # noqa: E402

from infra.research.stats import adjust_family  # noqa: E402

HERE = R.HERE
CAPS = (0.05, 0.10, 0.15, 0.20, 0.30)
CCAPS = (0.0, 0.05, 0.10)
FOCUS = ("SIMFTR", "CITIZEN", "WAVECOREE", "RHOS")
PROXIES = ("p_buyers", "p_holders", "p_holders_frac", "p_cv", "p_drip_frac", "p_bundle", "p_bundle_sol",
           "p_single_nosell_frac")


def pct(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def cobertura(pop, elig) -> list[str]:
    out = ["## 1. População e cobertura", "",
           "| recorte | mints | com fita desde o nascimento (R73) | compradoras pré-decisão | resolvidas antes da decisão | cobertura agregada | mediana por mint | mints ≥ 60 % |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for lab, sub in (("uma por mint (todas)", pop), ("reais", [r for r in pop if r["lane"] == "live"]),
                     ("papel", [r for r in pop if r["lane"] == "paper"]), ("**elegíveis**", elig)):
        nb = sum(r["n_buyers"] for r in sub)
        nr = sum(r["n_resolved"] for r in sub)
        cov = [r["coverage"] for r in sub if r["coverage"] is not None]
        out.append(f"| {lab} | {len(sub)} | {sum(r['eligible'] for r in sub)} | {nb} | {nr} | {pct(nr / nb if nb else None)}"
                   f" | {pct(statistics.median(cov) if cov else None)} | {sum(c >= 0.6 for c in cov)} de {len(cov)} |")
    cens = Counter(str(r["censor"]) for r in elig)
    amb = sum(r["ambiguous"] for r in elig)
    out += ["", f"Desfecho nas elegíveis: {dict(cens)} (`None` = resolvido). Compradoras no mesmo segundo da decisão "
            f"(ambíguas, contadas): {amb} de {sum(r['n_buyers'] for r in elig)}."]
    return out


def distrib(elig, allrows) -> list[str]:
    v = [r["pct"] for r in elig if r["pct"] is not None]
    out = ["## 2. A variável", "",
           f"`rede_financiadora_pct` nas {len(v)} elegíveis: zeros {sum(x == 0 for x in v)} "
           f"({sum(x == 0 for x in v) / len(v):.1%}); quantis 1/3 {np.quantile(v, 1 / 3):.4f}, mediana "
           f"{np.median(v):.4f}, 2/3 {np.quantile(v, 2 / 3):.4f}, p90 {np.quantile(v, 0.9):.4f}, máx {max(v):.4f}.",
           "", "| caso | via | fita nasce/reconcilia | compradoras | resolvidas | maior grupo | rede (congelada) | rede ÷ todas | s1 | s2 | criador | despejo (máx. vendedoras/slot) | PnL realizado |",
           "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|"]
    for sym in FOCUS:
        for r in [x for x in allrows if x["symbol"] == sym and x["group"] == "live_all"][:1]:
            out.append(f"| {sym} | {r['lane']} | {r['nasce']}/{r['reconcilia']} | {r['n_buyers']} | {r['n_resolved']} | "
                       f"{r['max_group']} | {pct(r['pct'])} | {pct(r['pct_all'])} | {pct(r['s1_pct'])} | {pct(r['s2_pct'])} | "
                       f"{pct(r['creator_pct'])} | {r['dump']} ({r['dump_sellers']}) | {r['pnl_sol']} |")
    return out


def tercis(elig) -> tuple[list[str], dict]:
    head = ["| recorte | n | baixo / alto | cortes | média baixo / alto | D (baixo − alto) | IC 95 % (mint) | despejo baixo vs alto |",
            "|---|---:|---:|---|---|---:|---|---|"]
    main = R.contrast(elig, "pct", "sim_ret", R.SEED)  # cortes = tercis da elegível inteira (291)
    rows = [R.fmt(main, "**principal** (simulador, censura 60 s)")]
    for lab, sub, var, out, seed in (
        ("sem censura por buraco", elig, "pct", "sim_ret_nc", 1),
        ("censura ≤ 30 s", [r for r in elig if (r.get("gap_to_landing_s") or 1e9) <= 30], "pct", "sim_ret", 2),
        ("s1 (exclui desconhecidos)", elig, "s1_pct", "sim_ret", 3),
        ("s2 (só identidade)", elig, "s2_pct", "sim_ret", 4),
        ("maior grupo ÷ todas", elig, "pct_all", "sim_ret", 5),
        ("só reais", [r for r in elig if r["lane"] == "live"], "pct", "sim_ret", 6),
        ("só reais, PnL realizado", [r for r in elig if r["lane"] == "live"], "pct", "real_ret", 7),
        ("só papel", [r for r in elig if r["lane"] == "paper"], "pct", "sim_ret", 8),
        ("cobertura por mint ≥ 60 %", [r for r in elig if (r["coverage"] or 0) >= 0.6], "pct", "sim_ret", 9),
    ):
        rows.append(R.fmt(R.contrast(sub, var, out, R.SEED + seed, cut=R.cuts(elig, var)), lab))
    return ["## 3. Tercis (D = baixo − alto; previsão D ≥ +0,05)", ""] + head + rows, main


def despejo(main) -> list[str]:
    if "D" not in main:
        return ["## 4. Despejo coordenado", "", "Sem contraste identificável."]
    (kl, nl), (kh, nh) = main["dump_lo"], main["dump_hi"]
    (bl, _), (bh, _) = main["big_lo"], main["big_hi"]
    ratio = (kh / nh) / (kl / nl) if kl else float("inf") if kh else float("nan")
    return ["## 4. Despejo coordenado (≥ 10 vendedoras distintas num slot, até 300 s da entrada)", "",
            "| tercil | n | despejo coordenado [Wilson] | perda ≥ 50 % |", "|---|---:|---|---:|",
            f"| baixo | {nl} | {R.wilson(kl, nl)} | {bl} |", f"| alto | {nh} | {R.wilson(kh, nh)} | {bh} |", "",
            f"Razão alto ÷ baixo = **{ratio:.2f}×** (a previsão pede ≥ 2×). Diferença de taxas (alto − baixo) "
            f"{kh / nh - kl / nl:+.3f}, IC 95 % bootstrap por mint [{main['dump_diff_ci'][0]:+.3f}, {main['dump_diff_ci'][1]:+.3f}]."]


def by_day(elig) -> list[str]:
    out = ["", "Por dia (D e n; descritivo):", ""]
    for d in sorted({r["dia"] for r in elig}):
        c = R.contrast([r for r in elig if r["dia"] == d], "pct", "sim_ret", R.SEED + 50, cut=R.cuts(elig, "pct"))
        out.append(f"- {d}: n = {c['n']}" + (f", D = {c['D']:+.4f} [{c['ci'][0]:+.4f}, {c['ci'][1]:+.4f}]" if "D" in c
                                                 else f" ({c.get('note')})"))
    return out


def contrafactual(live) -> list[str]:
    total = sum(Decimal(r["pnl_sol"]) for r in live)
    wins = [r for r in live if Decimal(r["pnl_sol"]) > 0]
    worst = sorted(live, key=lambda r: Decimal(r["pnl_sol"]))[:6]
    out = ["## 7. Contrafactual nas 95 decisões reais (cada uma no seu instante; PnL realizado)", "",
           f"Base: {len(live)} posições, {len(wins)} vencedoras, PnL **{total:+.4f} SOL**. As 6 piores: "
           + ", ".join(f"`{r['symbol']}` {Decimal(r['pnl_sol']):+.4f} (rede {pct(r['pct'])}, fita nasce {r['nasce']})"
                       for r in worst) + ".", "",
           "| regra | bloqueia | das 6 piores | vencedoras mortas | Δ PnL |", "|---|---:|---|---|---:|"]
    for var, caps, lab in (("pct", CAPS, "rede >"), ("creator_pct", CCAPS, "criador >")):
        for c in caps:
            blk = [r for r in live if r[var] is not None and r[var] > c]
            dead = [r["symbol"] for r in blk if Decimal(r["pnl_sol"]) > 0]
            w6 = [r["symbol"] for r in worst if r in blk]
            d = -sum(Decimal(r["pnl_sol"]) for r in blk)
            out.append(f"| {lab} {c:.0%} | {len(blk)} | {len(w6)} {w6} | {len(dead)} de {len(wins)} "
                       f"({len(dead) / len(wins):.0%}) {dead} | {d:+.4f} |")
    unk = sum(1 for r in live if r["pct"] is None)
    return out + ["", f"Sem valor (nenhuma compradora resolvida): {unk}. Sem fita desde o nascimento: "
                      f"{sum(not r['eligible'] for r in live)} de {len(live)} (valores dessas são exploratórios)."]


def _rank(x) -> np.ndarray:
    """Postos médios (empates recebem a média dos postos — há muitos zeros)."""
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[order] = np.arange(1, len(x) + 1)
    for v in np.unique(x):
        m = x == v
        r[m] = r[m].mean()
    return r


def spearman(a, b) -> float:
    return float(np.corrcoef(_rank(a), _rank(b))[0, 1])


def auc(score, label) -> float:
    s, y = np.asarray(score, float), np.asarray(label, bool)
    if y.all() or not y.any():
        return float("nan")
    pos, neg = s[y], s[~y]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def proxy(elig) -> list[str]:
    ok = [r for r in elig if r["pct"] is not None]
    hi_cut = np.quantile([r["pct"] for r in ok], 2 / 3)
    out = ["## 8. Proxy barato ao vivo (descritivo, fora do veredito)", "",
           f"n = {len(ok)} elegíveis. Alvo 1: tercil alto de rede (> {hi_cut:.4f}). Alvo 2: despejo coordenado.", "",
           "| proxy | mediana | Spearman com rede | AUC tercil alto de rede | AUC despejo | AUC perda ≥ 50 % (sim) |",
           "|---|---:|---:|---:|---:|---:|"]
    for p in PROXIES:
        sub = [r for r in ok if r.get(p) is not None]
        x = [float(r[p]) for r in sub]
        rs = [r for r in sub if r.get("sim_ret") is not None]
        out.append(f"| `{p}` | {statistics.median(x):.3f} | {spearman(x, [r['pct'] for r in sub]):+.3f} | "
                   f"{auc(x, [r['pct'] > hi_cut for r in sub]):.3f} | {auc(x, [bool(r['dump']) for r in sub]):.3f} | "
                   f"{auc([float(r[p]) for r in rs], [r['sim_ret'] <= -0.5 for r in rs]):.3f} |")
    x = [r["pct"] for r in ok]
    rs = [r for r in ok if r.get("sim_ret") is not None]
    out.append(f"| (a própria rede) | {statistics.median(x):.3f} | 1 | — | {auc(x, [bool(r['dump']) for r in ok]):.3f} | "
               f"{auc([r['pct'] for r in rs], [r['sim_ret'] <= -0.5 for r in rs]):.3f} |")
    return out


def main() -> None:
    rows = json.loads((HERE / "rows.json").read_text(encoding="utf-8"))
    for r in rows:
        r["sim_ret_nc"] = r["sim_ret"]
        if r.get("censor") not in (None, "None"):
            r["sim_ret"] = None
    pop = [r for r in rows if r["group"] == "pop"]
    live = [r for r in rows if r["group"] == "live_all"]
    elig = [r for r in pop if r["eligible"]]
    parts = cobertura(pop, elig) + [""] + distrib(elig, rows) + [""]
    t, main = tercis(elig)
    parts += t + by_day(elig) + [""] + despejo(main) + ["", "## 5. Moinho — primária e secundária", ""]
    txt1, p1 = R.moinho(elig, "pct", "H-014 primária — rede_financiadora_pct (baixo × alto)", R.SEED)
    parts += [txt1, ""]
    try:
        txt2, p2 = R.moinho(elig, "creator_pct", "H-014 secundária — financiado_pelo_criador_pct", R.SEED + 1)
        parts += [txt2, ""]
    except (ValueError, ZeroDivisionError) as e:  # tercis degenerados
        p2 = None
        parts += [f"Secundária: moinho não corre ({type(e).__name__}: {e}).", ""]
    ps = [p for p in (p1, p2) if p is not None]
    fam = adjust_family(ps)
    parts += [f"Holm na família {{primária, secundária}}: p brutos {[round(p, 4) for p in ps]} → {fam}", "",
              "## 6. Patamar (população elegível inteira, direção low)", ""] + R.plateau(elig, "pct") + [""]
    parts += contrafactual(live) + [""] + proxy(elig)
    txt = "\n".join(str(x) for x in parts)
    (HERE / "report.md").write_text(txt, encoding="utf-8")
    sys.stdout.buffer.write(txt.encode("utf-8"))


if __name__ == "__main__":
    main()
