"""R85 — do que `collect` juntou ao relatório: contrastes, IC, Holm, cláusulas, vereditos, sensibilidades e diagnósticos."""

from __future__ import annotations

from collections import Counter

import numpy as np
from collect85 import HOLDS, MAIN, Arm, Collected
from geom85 import BANDS
from stats85 import SEED, arm_verdict, boot_d, coverage, day_sums, holm, mbb_idx, summarize
from study85 import TOLS, Contrast, contrast

MRE = 0.01
BLOCK, BLOCK_STRUCT = 28, 120
BOUNDS = ("opt", "pes")


def arm_contrast(arm: Arm, ctrl: dict, hold: int = 10) -> Contrast:
    return contrast(arm.events[hold], ctrl[hold], arm.coins[hold])


def stats(c: Contrast, n_days: int, idx: np.ndarray, width: int = BLOCK) -> list[dict]:
    out = []
    for x, lvl in ((c.opt, c.lvl_opt), (c.pes, c.lvl_pes)):
        s, n = day_sums(c.days, x, n_days)
        r = summarize(s, n, idx) if n.sum() else {"d": float("nan"), "lo": float("nan"), "hi": float("nan"), "p": 1.0, "dropped": 0}
        r.update(level=float(np.mean(lvl)) if lvl.size else float("nan"), n=int(c.days.size), cov=coverage(c.days, width))
        out.append(r)
    return out


def split_ok(c: Contrast, split_dd: int) -> tuple[bool, list[str]]:
    txt, ok = [], True
    for name, x in zip(BOUNDS, (c.opt, c.pes), strict=True):
        pre, post = x[c.days < split_dd], x[c.days >= split_dd]
        mp = float(pre.mean()) if pre.size else float("nan")
        mq = float(post.mean()) if post.size else float("nan")
        ok &= pre.size > 0 and post.size > 0 and mp > 0 and mq > 0
        txt.append(f"{name}: antes de 2022 {mp * 100:+.3f} p.p. (n {pre.size}) · depois {mq * 100:+.3f} (n {post.size})")
    return ok, txt


def point(c: Contrast) -> tuple[float, float]:
    return (float(c.opt.mean()) if c.opt.size else float("nan"), float(c.pes.mean()) if c.pes.size else float("nan"))


def k6(c: Contrast) -> tuple[bool, str]:
    if not c.coins:
        return False, "sem eventos"
    top, n = Counter(c.coins).most_common(1)[0]
    return n / len(c.coins) >= 0.6, f"maior moeda {top} {n}/{len(c.coins)} = {n / len(c.coins) * 100:.1f} %"


def per_coin(c: Contrast) -> str:
    if not c.coins:
        return "—"
    coins = np.array(c.coins)
    total = c.opt.sum()
    contrib = sorted(((float(c.opt[coins == k].sum() / c.opt.size), k, int((coins == k).sum())) for k in set(c.coins)), reverse=True)
    loo = [float(c.opt[coins != k].mean()) for k in set(c.coins) if (coins != k).any()]
    top3 = ", ".join(f"{k} {v * 100:+.3f} p.p. (n {m})" for v, k, m in contrib[:3])
    bot = ", ".join(f"{k} {v * 100:+.3f} (n {m})" for v, k, m in contrib[-2:])
    return (f"{len(set(c.coins))} moedas; maiores contribuições ao D otimista: {top3}; menores: {bot}; "
            f"D sem cada moeda de {min(loo) * 100:+.3f} a {max(loo) * 100:+.3f} p.p. (soma {total * 100:+.2f})")


def fmt(s: dict, hp: float | None = None) -> str:
    h = f", Holm {hp:.4f}" if hp is not None else ""
    return (f"D {s['d'] * 100:+.3f} p.p. [{s['lo'] * 100:+.3f}; {s['hi'] * 100:+.3f}], p {s['p']:.4f}{h}, nível "
            f"{s['level'] * 100:+.3f} %, n {s['n']}, cobertura {s['cov']}")


def coin_cluster(c: Contrast, reps: int = 10_000, seed: int = SEED) -> tuple[float, float]:
    coins = sorted(set(c.coins))
    idx = {k: np.flatnonzero(np.array(c.coins) == k) for k in coins}
    s = np.array([c.opt[idx[k]].sum() for k in coins])
    n = np.array([idx[k].size for k in coins])
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(coins), size=(reps, len(coins)))
    d = s[pick].sum(1) / n[pick].sum(1)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return float(lo), float(hi)


def paired_spec(cs: list[Contrast], n_days: int, idx: np.ndarray) -> tuple[float, float, float]:
    """D(principal) − média de D nas 4 faixas vizinhas, com os mesmos índices de bloco (otimista)."""
    nums, dens = [], []
    for c in cs:
        s, n = day_sums(c.days, c.opt, n_days)
        nums.append(np.concatenate([s[idx[k : k + 1000]].sum(1) for k in range(0, idx.shape[0], 1000)]))
        dens.append(np.concatenate([n[idx[k : k + 1000]].sum(1) for k in range(0, idx.shape[0], 1000)]))
    ok = np.all(np.array(dens) > 0, axis=0)
    ds = [nu[ok] / de[ok] for nu, de in zip(nums, dens, strict=True)]
    main = ds[MAIN]
    neigh = np.mean([ds[b] for b in range(len(cs)) if b != MAIN], axis=0)
    est = point(cs[MAIN])[0] - float(np.mean([point(cs[b])[0] for b in range(len(cs)) if b != MAIN]))
    lo, hi = np.percentile(main - neigh, [2.5, 97.5])
    return est, float(lo), float(hi)


def struct_contrast(col: Collected) -> tuple[Contrast, Contrast]:
    ev, ctrl = [], {}
    for k, (_dd, o, p_, _, _) in enumerate(col.struct):
        if col.struct_ctrl.get(k):
            ev.append((k, o, p_))
            ctrl[k] = col.struct_ctrl[k]
    c = contrast(ev, ctrl, [col.struct[k][4] for k, _, _ in ev])
    days = np.array([col.struct[k][0] for k, _, _ in ev], dtype=np.int64)
    c.days = days  # contraste por evento, datado pelo dia do sinal
    pairs = [(s, f) for s, f in zip(col.struct, col.fixed_same_entry, strict=True) if f is not None]
    same = Contrast(np.array([s[0] for s, _ in pairs], dtype=np.int64), np.array([s[1] - f[0] for s, f in pairs]),
                    np.array([s[2] - f[1] for s, f in pairs]), np.array([s[1] for s, _ in pairs]),
                    np.array([s[2] for s, _ in pairs]), [s[4] for s, _ in pairs], len(col.struct) - len(pairs))
    return c, same


def report(col: Collected) -> tuple[str, dict[str, str]]:
    nd = col.n_days
    idx = mbb_idx(nd, BLOCK)
    out = [f"dias de sinal {nd}; contagens {dict(sorted(col.counts.items()))}",
           f"atraso de venda (H=10) além de e+10: {Counter(col.delays).most_common(6)}"]
    verdicts: dict[str, str] = {}
    # ---------------- H-025
    fc = [arm_contrast(a, col.fib_ctrl) for a in col.fib]
    sc, same = struct_contrast(col)
    st_main = stats(fc[MAIN], nd, idx)
    st_struct = stats(sc, nd, mbb_idx(nd, BLOCK_STRUCT), BLOCK_STRUCT)
    hol = [holm([st_main[b]["p"], st_struct[b]["p"]]) for b in range(2)]
    out.append("\n## H-025 — Fibonacci 50–61,8 %")
    out.append(f"eventos sem controle no dia: {fc[MAIN].dropped_no_control}; estrutural sem controle: {len(col.struct) - sc.days.size}")
    for b, name in enumerate(BOUNDS):
        out.append(f"primária [{name}]: {fmt(st_main[b], hol[b][0])}")
    for b, (lo_b, hi_b) in enumerate(BANDS):
        po, pp = point(fc[b])
        out.append(f"faixa [{lo_b:.2f}; {hi_b:.3f}]: D {po * 100:+.3f} / {pp * 100:+.3f} p.p., n {fc[b].days.size}")
    plateau = all(v > 0 for b in (1, 3) for v in point(fc[b]))
    sp_ok, sp_txt = split_ok(fc[MAIN], col.split_dd)
    out += [f"patamar (0,45 e 0,55 > 0 nos dois limites): {plateau}", *sp_txt, f"corte ok: {sp_ok}"]
    k6_main, k6_txt = k6(fc[MAIN])
    out += [f"K6 (diagnóstico): {k6_txt}", f"por moeda: {per_coin(fc[MAIN])}"]
    verdicts["H-025 primária"] = arm_verdict(st_main, [hol[0][0], hol[1][0]], MRE, plateau, sp_ok, False)
    for b, name in enumerate(BOUNDS):
        out.append(f"estrutural [{name}] (bloco 120 d): {fmt(st_struct[b], hol[b][1])}")
    for blk in (60, 180):  # sensibilidade registrada na emenda (4), não decide
        s_b = stats(sc, nd, mbb_idx(nd, blk), blk)[0]
        out.append(f"estrutural bloco {blk} d (otimista, não decide): [{s_b['lo'] * 100:+.3f}; {s_b['hi'] * 100:+.3f}], p {s_b['p']:.4f}")
    out.append(f"réplicas descartadas por ΣN* = 0: primária {st_main[0]['dropped']}, estrutural {st_struct[0]['dropped']}")
    sp2, sp2_txt = split_ok(sc, col.split_dd)
    out += sp2_txt
    verdicts["H-025 estrutural"] = arm_verdict(st_struct, [hol[0][1], hol[1][1]], MRE, True, sp2, False, min_cover=15)
    so, spp = point(same)
    out.append(f"descritivo: mesmas entradas, estrutural − fixa 10 d: {so * 100:+.3f} / {spp * 100:+.3f} p.p. (n {same.days.size}; sem saída fixa {same.dropped_no_control}); "
               f"m mediano {int(np.median([s[3] for s in col.struct])) if col.struct else 0} d")
    est, lo, hi = paired_spec(fc, nd, idx)
    out.append(f"especificidade de Fibonacci (principal − média das 4 vizinhas, otimista): {est * 100:+.3f} p.p. [{lo * 100:+.3f}; {hi * 100:+.3f}]"
               f" → {'especial' if lo > 0 else 'não especial'}")
    out.append(f"verdito H-025: primária {verdicts['H-025 primária']} · estrutural {verdicts['H-025 estrutural']}")
    # ---------------- H-026
    out.append("\n## H-026 — LTA diária (tolerância 0,25 decide; 0,15/0,35 = patamar)")
    ct = {t: {k: arm_contrast(col.lta[t][k], col.lta_ctrl[t]) for k in ("A", "B")} for t in TOLS}
    st = {k: stats(ct[0.25][k], nd, idx) for k in ("A", "B")}
    hol26 = [holm([st["A"][b]["p"], st["B"][b]["p"]]) for b in range(2)]
    for j, k in enumerate(("A", "B")):
        c = ct[0.25][k]
        out.append(f"-- braço {k}: eventos sem controle {c.dropped_no_control}")
        for b, name in enumerate(BOUNDS):
            out.append(f"   [{name}]: {fmt(st[k][b], hol26[b][j])}")
        pl = all(v > 0 for t in (0.15, 0.35) for v in point(ct[t][k]))
        out.append("   patamar: " + " · ".join(f"tol {t}: {point(ct[t][k])[0] * 100:+.3f}/{point(ct[t][k])[1] * 100:+.3f} (n {ct[t][k].days.size})" for t in TOLS) + f" → {pl}")
        spk, spk_txt = split_ok(c, col.split_dd)
        k6b, k6t = k6(c)
        out += [f"   {x}" for x in spk_txt] + [f"   K6: {k6t} → {k6b}", f"   por moeda: {per_coin(c)}"]
        verdicts[f"H-026 {k}"] = arm_verdict(st[k], [hol26[0][j], hol26[1][j]], MRE, pl, spk, k6b)
    out.append(f"veredito H-026: A {verdicts['H-026 A']} · B {verdicts['H-026 B']}")
    # ---------------- sensibilidade (não decide)
    out.append("\n## Sensibilidade (não decide)")
    arms = {"H-025": (col.fib[MAIN], col.fib_ctrl), "H-026 A": (col.lta[0.25]["A"], col.lta_ctrl[0.25]),
            "H-026 B": (col.lta[0.25]["B"], col.lta_ctrl[0.25])}
    for name, (arm, ctrl) in arms.items():
        for h in (5, 20):
            c = arm_contrast(arm, ctrl, h)
            po, pp = point(c)
            out.append(f"{name} H={h}: D {po * 100:+.3f} / {pp * 100:+.3f} p.p. (n {c.days.size})")
        c10 = arm_contrast(arm, ctrl)
        for blk in (1, 14, 56):
            s = stats(c10, nd, mbb_idx(nd, blk))[0]
            out.append(f"{name} bloco {blk} d (otimista): [{s['lo'] * 100:+.3f}; {s['hi'] * 100:+.3f}], p {s['p']:.4f}")
        if c10.coins:
            lo, hi = coin_cluster(c10)
            out.append(f"{name} cluster por moeda (otimista): [{lo * 100:+.3f}; {hi * 100:+.3f}]")
    return "\n".join(out), verdicts


__all__ = ["HOLDS", "report", "boot_d"]
