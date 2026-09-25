# R79 — H-017 (EXP-M24) julgamento. cd .claude/state/r79 && PYTHONPATH=C:/dev/project-hunter uv run --project C:/dev/project-hunter python h017_run.py
from collections import Counter, defaultdict
from datetime import timedelta

import numpy as np

from h017 import classify_decision, control, load, pair_rows
from h019 import ts

B, SEED = 10_000, 17
BRT = timedelta(hours=-3)


def boot_mean(v: np.ndarray, seed: int = SEED) -> tuple[float, float, float]:
    """Média e IC 95 % por bootstrap de mint (uma decisão por mint → linhas)."""
    rng = np.random.default_rng(seed)
    m = v[rng.integers(0, v.size, (B, v.size))].mean(1)
    return float(v.mean()), *np.percentile(m, [2.5, 97.5]).tolist()


def label(n: int, d: tuple[float, float, float], vs0: tuple[float, float, float]) -> str:
    if n < 150:
        return f"LIMITE DE DADO ({n} < 150 decisões resolvidas emparelhadas)"
    if d[2] < 0.01:
        return "REFUTA (IC sup de D < +1 pp)"
    if vs0[0] <= 0:
        return "REFUTA (não bate 'não comprar nada')"
    if d[0] >= 0.02 and d[1] > 0 and vs0[1] > 0:
        return "CONFIRMA"
    return "NÃO CONFIRMA"


def show(tag: str, pairs: list[dict]) -> None:
    if not pairs:
        print(f"   {tag}: 0 pares")
        return
    ra = np.array([p["ra"] for p in pairs])
    rc = np.array([p["rc"] for p in pairs])
    d, a, c = boot_mean(ra - rc), boot_mean(ra), boot_mean(rc)
    print(f"   {tag}: n {len(pairs)} | braço {a[0]:+.4f} [{a[1]:+.4f}, {a[2]:+.4f}] | op5 {c[0]:+.4f} [{c[1]:+.4f}, {c[2]:+.4f}]"
          f" | D {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}] | braço melhor em {int((ra > rc).sum())}, pior {int((ra < rc).sum())}"
          f" | Σ SOL braço−op5 = {sum(float(p['arm_pnl'] or 0) for p in pairs) - sum(float(p['op_pnl']) for p in pairs):+.4f}")


def main() -> None:
    rows = load()
    pairs, why = pair_rows(rows)
    print(f"## Armações (1.ª por mint): {len(rows)} | classes {dict(Counter(classify_decision(r)[0] for r in rows))}")
    print(f"   emparelháveis: {len(pairs)} | sem controle resolvido: {why['no_control']} |"
          f" status da proposta op5: {dict(Counter(r['op_prop_status'] or 'sem proposta' for r in rows))}")
    ra = np.array([p["ra"] for p in pairs])
    rc = np.array([p["rc"] for p in pairs])
    d, vs0 = boot_mean(ra - rc), boot_mean(ra)
    print(f"\n## PRIMÁRIA (a) braço − op5 emparelhado: D {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}] (bootstrap por mint {B})")
    print(f"   (b) braço contra 'não comprar nada' nos pares: {vs0[0]:+.4f} [{vs0[1]:+.4f}, {vs0[2]:+.4f}]")
    print(f"   → {label(len(pairs), d, vs0)}")
    print(f"   composição: {dict(Counter(p['cls'] for p in pairs))}")
    show("todos os pares", pairs)
    byday: dict[str, list] = defaultdict(list)
    bybrt: dict[str, list] = defaultdict(list)
    for p in pairs:
        byday[p["t0"][:10]].append(p)
        bybrt[(ts(p["t0"]) + BRT).date().isoformat()].append(p)
    for k in sorted(byday):
        show(f"dia UTC {k}", byday[k])
    for k in sorted(bybrt):
        show(f"dia BRT {k}", bybrt[k])
    print("\n   pares, um a um:")
    for p in sorted(pairs, key=lambda p: p["t0"]):
        print(f"     {p['t0'][:19]} {p['symbol'][:12]:12} {p['cls']:11} braço {p['ra']:+.4f} ({p['arm_exit'] or '-'}) op5 {p['rc']:+.4f} ({p['op_exit']})")
    # descritivo: todas as decisões resolvidas do braço, sem exigir controle
    allr = [(r, *classify_decision(r)) for r in rows]
    res = [(r, c, v) for r, c, v in allr if v is not None]
    v = np.array([x for _, _, x in res])
    m = boot_mean(v)
    print(f"\n## DESCRITIVO (b) em todas as decisões resolvidas do braço: n {len(res)} | média {m[0]:+.4f} [{m[1]:+.4f}, {m[2]:+.4f}]"
          f" | Σ SOL {sum(float(r['arm_pnl'] or 0) for r, _, _ in res):+.4f} | classes {dict(Counter(c for _, c, _ in res))}")
    for grp, cond in (("op5 aceitou (filled)", lambda r: r["op_prop_status"] == "filled"),
                      ("op5 recusou/expirou", lambda r: r["op_prop_status"] != "filled")):
        sub = np.array([x for r, _, x in res if cond(r)])
        if sub.size:
            s = boot_mean(sub)
            print(f"   {grp}: n {sub.size} | média {s[0]:+.4f} [{s[1]:+.4f}, {s[2]:+.4f}]")
    for k in ("2026-09-24", "2026-09-25"):
        sub = np.array([x for r, _, x in res if r["t0"].startswith(k)])
        s = boot_mean(sub)
        print(f"   dia UTC {k}: n {sub.size} | média {s[0]:+.4f} [{s[1]:+.4f}, {s[2]:+.4f}]")
    # papel × real no mesmo op5 (fidelidade), nos pares com posição real fechada
    fr = [(float(r["real_pnl"]) / float(r["real_size"]), control(r)) for r in rows
          if r["real_status"] == "closed" and r["real_pnl"] and control(r) is not None]
    if fr:
        diff = np.array([a - b for a, b in fr])
        s = boot_mean(diff)
        print(f"\n## Fidelidade op5 real − op5 papel (mesma proposta): n {len(fr)} | {s[0]:+.4f} [{s[1]:+.4f}, {s[2]:+.4f}]")
    # decomposição de D: não-entradas × entradas na MESMA foto do op5 × entradas em foto diferente
    parts: dict[str, list[float]] = defaultdict(list)
    for p in pairs:
        if p["cls"] != "entered":
            k = "não entrou (0 − op5)"
        elif ts(p["arm_entry_at"]) == ts(p["op_entry_at"]):
            k = "entrou na mesma foto do op5"
        else:
            k = "entrou em foto posterior"
        parts[k].append(p["ra"] - p["rc"])
    print(f"\n## Decomposição de D (soma das diferenças ÷ {len(pairs)} pares):")
    for k, v in parts.items():
        print(f"   {k}: n {len(v)} | contribuição {sum(v) / len(pairs):+.4f} | média no grupo {np.mean(v):+.4f}")
    big = max(pairs, key=lambda p: abs(p["ra"] - p["rc"]))
    rest = np.array([p["ra"] - p["rc"] for p in pairs if p is not big])
    s = boot_mean(rest)
    print(f"   sem o maior par ({big['symbol']}, {big['ra'] - big['rc']:+.4f}): D {s[0]:+.4f} [{s[1]:+.4f}, {s[2]:+.4f}] (n {rest.size})")
    kills = Counter(next((i.split("@")[0] for i in r["outcomes"].split(" | ") if i.startswith("pullback_")), "")
                    for r in rows if classify_decision(r)[0] in ("killed", "censored"))
    print(f"   motivos de morte/censura no braço (todas as armações): {dict(kills)}")
    per_day = Counter(p["t0"][:10] for p in pairs)
    print(f"\n## Ritmo: pares por dia UTC {dict(per_day)}; horas da coorte {(ts(rows[-1]['t0']) - ts(rows[0]['t0'])).total_seconds() / 3600:.1f}")


if __name__ == "__main__":
    main()
