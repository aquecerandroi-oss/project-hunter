"""R90 / H-033 — corrida real pelo pré-registro (04:51:02Z) e pela emenda (05:15:31Z), sobre a lista congelada (05:18:27Z).

cd .claude/state/r90 && PYTHONPATH=C:/dev/project-hunter uv run --no-sync --project C:/dev/project-hunter python run90.py > h033.txt
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter

import numpy as np
from analysis90 import analyze, label, render
from data90 import CACHE, attach_outcomes, check_join, units
from freeze90 import build, complete
from stats90 import global_label, holm

FROZEN = "e597cabf49f9a8e7beee21535dd218e2c3d9065b34264f70a4c086af658dd4dd"
POST_R86 = "2026-10-01T03:06:15+00:00"


def main() -> None:
    body = (CACHE / "eligible.csv").read_bytes()
    assert hashlib.sha256(body).hexdigest() == FROZEN, "eligible.csv não é a lista congelada às 05:18:27Z"
    print("# R90 / H-033 — OI relativo à mediana semanal como estado dos sinais de continuação do Lab")
    print("ANÁLISE RETROSPECTIVA PRÉ-ESPECIFICADA (emenda, item 7) — condicionada à folga de 15 min (emenda, item 1)")
    print("sha256 eligible.csv:", FROZEN)
    with (CACHE / "eligible.csv").open(encoding="utf-8") as fh:
        elig = {r["signal_id"] for r in csv.DictReader(fh)}
    rows = build(15)
    attach_outcomes(rows)
    check_join(rows, elig)
    with (CACHE / "out.csv").open(encoding="utf-8") as fh:
        out = list(csv.DictReader(fh))
    ids = [r["signal_id"] for r in out]
    print(f"desfechos lidos em {out[0]['read_at']} | linhas {len(out)} | signal_id únicos {len(set(ids))}")
    div = Counter()
    for r in rows:
        if r["signal_id"] in elig:
            div["elegível_sem_R_agora" if r["r"] is None else "ok"] += 1
        elif not r["has_r"] and r["r"] is not None:
            div["nulo_no_cego_com_R_agora"] += 1
    print("divergência de disponibilidade de R_net (cego × agora):", dict(div))

    pop = [r for r in rows if r["signal_id"] in elig and r["r"] is not None]
    by = {s: units([r for r in pop if r["strategy"] == s]) for s in ("momentum", "volume_anomaly")}
    res = {s: analyze(us) for s, us in by.items()}
    ph = holm([res["momentum"]["p_raw"], res["volume_anomaly"]["p_raw"]])
    slack = {s: tuple(_slack_beta(s, lag) for lag in (30, 60)) for s in by}  # emenda item 1: entra no CONFIRMA
    labels = {}
    for (s, r), p in zip(res.items(), ph, strict=True):
        lab = label(r, p, slack=slack[s])  # type: ignore[arg-type]
        print(f"\nβ_x nas folgas 30/60 (condição do CONFIRMA) para {s}: {slack[s]}")
        labels[s] = lab.label  # type: ignore[attr-defined]
        print("\n".join(render(s, r, lab, p)))
        print("versões nas unidades:", dict(Counter(v for u in by[s] for v in u["versions"])))
    print(f"\n### RÓTULO H-033 (regra global da emenda): {global_label(list(labels.values()))} — por estratégia {labels}")

    print("\n## Sensibilidades pré-registradas da momentum (não decidem o rótulo; folgas 30/60 entram no CONFIRMA)")
    mom = [r for r in pop if r["strategy"] == "momentum"]
    for lag in (30, 60):
        rl = build(lag)
        attach_outcomes(rl)
        sub = [r for r in rl if r["strategy"] == "momentum" and complete(r) and r["r"] is not None]
        _summ(f"folga {lag} min (população completa)", units(sub))
        _summ(f"folga {lag} min ∩ elegíveis da folga 15", units([r for r in sub if r["signal_id"] in elig]))
    for name, sub in (
        ("leitura corrente provada (despacho ≤ obs)", units([r for r in mom if r["verified"]])),
        ("janela inteira provada", units([r for r in mom if r["window_proven"]])),
        ("sem velas tardias na janela de 24 h", units([r for r in mom if not r["late_candles"]])),
        ("r_ex_funding (mesmas linhas)", units([dict(r, r=r["r_ex"]) for r in mom if r["r_ex"] is not None])),
        ("pós-R86 (emitidas depois de 01/10 03:06:15Z)", units([r for r in mom if r["t"].isoformat() > POST_R86])),
        ("pré-R86", units([r for r in mom if r["t"].isoformat() <= POST_R86])),
    ):
        _summ(name, sub)
    sec = units([dict(r, x=-r["oi_vol"]) for r in mom if r["oi_vol"] is not None])
    _summ("SECUNDÁRIA oi_vol (x = −oi_vol, mesmo modelo; grupos por oi_vol, não pela primária)",
          sec, groups=("oi_vol<0", "oi_vol≥0"))

    print("\n## Descritivo (reversão, sem rótulo)")
    for s in ("mean_reversion", "mean_reversion_h1"):
        _summ(s, units([r for r in pop if r["strategy"] == s]))


def _slack_beta(strategy: str, lag: int) -> float:
    rl = build(lag)
    attach_outcomes(rl)
    us = units([r for r in rl if r["strategy"] == strategy and complete(r) and r["r"] is not None])
    r = analyze(us, reps=2000, robust=False)
    return float(r.get("beta", float("nan")))


def _summ(name: str, us: list[dict], groups: tuple[str, str] = ("oi_rel7d<0", "≥0")) -> None:
    r = analyze(us, reps=2000, robust=False)
    if "beta" not in r:
        y = [u["r"] for u in us]
        print(f"- {name}: n {r['n']} dias {r['days']} ({groups[0]} {r['n_pos']}, {groups[1]} {r['n_neg']}) — abaixo do"
              f" piso, sem ajuste | média R {np.mean(y) if y else float('nan'):+.4f}")
        return
    print(f"- {name}: n {r['n']} dias {r['days']} | β_x {r['beta']:+.4f} IC dia [{r['lo']:+.4f}, {r['hi']:+.4f}]"
          f" IC mercado [{r['lo_m']:+.4f}, {r['hi_m']:+.4f}] | nível {groups[0]} {r['level_pos']:+.4f} (n {r['n_pos']})"
          f" · {groups[1]} {r['level_neg']:+.4f} (n {r['n_neg']})")


if __name__ == "__main__":
    main()
