"""R86 / H-027 — corrida real pelo protocolo pré-registrado (02:56Z) e pela emenda (03:02Z).

cd .claude/state/r86 && PYTHONPATH=C:/dev/project-hunter uv run --no-sync --project C:/dev/project-hunter python run86.py > h027.txt
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter

import numpy as np
from analysis86 import analyze, label, render
from data86 import CACHE, attach_outcomes, check_join, feature_rows, guard_window, load_daily, units
from stats86 import global_label, holm

POST_R83 = "2026-09-28T01:58:45+00:00"
FROZEN = "f6fb22012cccf5b11744d72f75af5421c34c9682e9f1b78239fdbbe2ef2a2436"


def main() -> None:
    body = (CACHE / "eligible.csv").read_bytes()
    assert hashlib.sha256(body).hexdigest() == FROZEN, "eligible.csv não é a lista congelada às 03:04:58Z"
    print("# R86 / H-027 — tendência diária (razao_mm20d) como estado dos sinais de continuação do Lab")
    print("ANÁLISE RETROSPECTIVA PRÉ-ESPECIFICADA (emenda 03:02Z, item 5) — não é a validação em coorte futura da C1")
    print("sha256 eligible.csv:", hashlib.sha256(body).hexdigest())
    with (CACHE / "eligible.csv").open(encoding="utf-8") as fh:
        elig = {r["signal_id"] for r in csv.DictReader(fh)}
    rows, _ = feature_rows(load_daily())
    kept, _ = guard_window(rows)
    attach_outcomes(kept)
    check_join(kept, elig)
    with (CACHE / "out.csv").open(encoding="utf-8") as fh:
        out = list(csv.DictReader(fh))
    ids = [r["signal_id"] for r in out]
    print(f"desfechos lidos em {out[0]['read_at']} | linhas {len(out)} | signal_id únicos {len(set(ids))}")
    div = Counter()
    for r in kept:
        if r["signal_id"] in elig:
            div["elegível_sem_R_agora" if r["r"] is None else "ok"] += 1
        elif r["has_r"] is False and r["r"] is not None:
            div["nulo_no_cego_com_R_agora"] += 1
    print("divergência de disponibilidade de R_net (cego × agora):", dict(div))

    pop = [r for r in kept if r["signal_id"] in elig and r["r"] is not None]
    by = {s: units([r for r in pop if r["strategy"] == s]) for s in ("momentum", "volume_anomaly")}
    res = {s: analyze(us) for s, us in by.items()}
    ph = holm([res["momentum"]["p_raw"], res["volume_anomaly"]["p_raw"]])
    labels = {}
    for (s, r), p in zip(res.items(), ph, strict=True):
        lab = label(r, p)
        labels[s] = lab.label  # type: ignore[attr-defined]
        print("\n".join(render(s, r, lab, p)))
        print("versões nas unidades:", dict(Counter(v for u in by[s] for v in u["versions"])))
    print(f"\n### RÓTULO H-027 (regra global da emenda): {global_label(list(labels.values()))} — por estratégia {labels}")

    # Sensibilidades (descritivas, não mudam o rótulo) — momentum
    print("\n## Sensibilidades da momentum (não decidem)")
    mom = [r for r in pop if r["strategy"] == "momentum"]
    for name, sub in (
        ("só momentum v3 (paper)", units([r for r in mom if r["version"] == "v3"])),
        ("r_ex_funding (mesmas linhas)", units([dict(r, r=r["r_ex"]) for r in mom if r["r_ex"] is not None])),
        ("pós-R83 (emitidas depois de 28/09 01:58:45Z)", units([r for r in mom if r["t"].isoformat() > POST_R83])),
        ("pré-R83", units([r for r in mom if r["t"].isoformat() <= POST_R83])),
    ):
        _summ(name, sub)
    ng = [dict(r, razao=r["razao_noguard"]) for r in kept if r["strategy"] == "momentum" and r["r"] is not None
          and r["razao_noguard"] is not None and r["d_low"] is not None and r["ret4h"] is not None
          and r["atr_pct"] is not None]
    _summ("sem a guarda de chegada dos 20 dias", units(ng))

    # spot/1 — mean_reversion v14, só descritivo
    v14 = units([r for r in pop if r["strategy"] == "mean_reversion_v14"])
    pos = [u["r"] for u in v14 if u["razao"] > 0]
    neg = [u["r"] for u in v14 if u["razao"] <= 0]
    print("\n## spot/1 — sinais mean_reversion v14 (descritivo, sem rótulo; reversão, não continuação)")
    print(f"unidades {len(v14)} | razão>0 {len(pos)}: média R_net {np.mean(pos):+.4f} | razão≤0 {len(neg)}: "
          f"média {np.mean(neg) if neg else float('nan'):+.4f} | todos {np.mean([u['r'] for u in v14]):+.4f}")


def _summ(name: str, us: list[dict]) -> None:
    r = analyze(us, reps=2000)
    if "beta" not in r:
        print(f"- {name}: n {r['n']} dias {r['days']} (razão>0 {r['n_pos']}, ≤0 {r['n_neg']}) — abaixo do piso, sem ajuste")
        return
    print(f"- {name}: n {r['n']} dias {r['days']} | β_razao {r['beta']:+.4f} IC dia [{r['lo']:+.4f}, {r['hi']:+.4f}]"
          f" IC mercado [{r['lo_m']:+.4f}, {r['hi_m']:+.4f}] | nível razão>0 {r['level_pos']:+.4f} · ≤0 {r['level_neg']:+.4f}")


if __name__ == "__main__":
    main()
