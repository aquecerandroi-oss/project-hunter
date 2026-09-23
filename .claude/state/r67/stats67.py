"""R67 - estatistica fora de amostra (baldes + bootstrap de cluster de mint + permutacao por dia)."""
import random

random.seed(67)
B = 10_000


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def median(xs):
    if not xs:
        return float("nan")
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def pct(xs, q):
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def cluster_boot_diff(rows, key, lo_fn, val, n=B):
    """IC 95 % da diferenca de medias (lo - hi) reamostrando CLUSTERS inteiros (mints)."""
    groups = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    ks = list(groups)
    if len(ks) < 3:
        return (float("nan"), float("nan"), float("nan"), len(ks))
    diffs = []
    for _ in range(n):
        samp = []
        for _ in range(len(ks)):
            samp += groups[ks[random.randrange(len(ks))]]
        a = [r[val] for r in samp if lo_fn(r)]
        b = [r[val] for r in samp if not lo_fn(r)]
        if a and b:
            diffs.append(mean(a) - mean(b))
    if len(diffs) < 100:
        return (float("nan"), float("nan"), float("nan"), len(ks))
    diffs.sort()
    return (diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs))],
            sum(1 for d in diffs if d <= 0) / len(diffs), len(ks))


def perm_p_strat(rows, lo_fn, val, strat="day", n=B):
    """p bilateral por permutacao dos rotulos DENTRO de cada dia (preserva o efeito de dia)."""
    obs = _diff(rows, lo_fn, val)
    if obs != obs:
        return float("nan")
    blocks = {}
    for r in rows:
        blocks.setdefault(r[strat], []).append((1 if lo_fn(r) else 0, r[val]))
    hits = 0
    for _ in range(n):
        a, b = [], []
        for _, items in blocks.items():
            labs = [x[0] for x in items]
            random.shuffle(labs)
            for lab, (_, v) in zip(labs, items):
                (a if lab else b).append(v)
        if a and b and abs(mean(a) - mean(b)) >= abs(obs) - 1e-15:
            hits += 1
    return (hits + 1) / (n + 1)


def _diff(rows, lo_fn, val):
    a = [r[val] for r in rows if lo_fn(r)]
    b = [r[val] for r in rows if not lo_fn(r)]
    if not a or not b:
        return float("nan")
    return mean(a) - mean(b)


def bucket_table(rows, var, edges, val="ret"):
    """Baldes por limiares `edges` sobre `var`; devolve linhas (rotulo, n, hit%, media, mediana)."""
    out = []
    bounds = [(-1e18, edges[0])] + [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)] + [(edges[-1], 1e18)]
    for lo, hi in bounds:
        sel = [r for r in rows if r[var] is not None and lo < r[var] <= hi]
        if not sel:
            continue
        hs = [r["hit15"] for r in sel if r["hit15"] is not None]
        out.append(dict(
            lab="%s-%s" % ("" if lo < -1e17 else "%g" % lo, "inf" if hi > 1e17 else "%g" % hi),
            n=len(sel), hit=100.0 * mean(hs) if hs else float("nan"),
            m=mean([r[val] for r in sel]), med=median([r[val] for r in sel]),
            hold=median([r["hold_s"] for r in sel if r["hold_s"] is not None]),
        ))
    return out


def terciles(rows, var):
    xs = sorted(r[var] for r in rows if r[var] is not None)
    if len(xs) < 6:
        return None
    return (xs[len(xs) // 3], xs[2 * len(xs) // 3])


def rolling_pct_cut(rows, q, days=3):
    """Percentil movel de `buys_1m` das decisoes dos `days` dias ANTERIORES (nunca do proprio dia)."""
    by_day = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r["buys_1m"])
    ds = sorted(by_day)
    cuts = {}
    for i, d in enumerate(ds):
        hist = []
        for j in range(max(0, i - days), i):
            hist += [x for x in by_day[ds[j]] if x is not None]
        cuts[d] = pct(hist, q) if len(hist) >= 20 else None
    return cuts
