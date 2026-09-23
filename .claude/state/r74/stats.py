"""R74 — estatistica do contraste emparelhado e a regra de decisao congelada da H-011.

`boot_ci` e `perm_p` sao o MESMO estimador do `r72/run.py` (reamostra mints inteiros com
reposicao; troca de sinal emparelhada), so vetorizados em NumPy para caber no tempo. Floats
aqui e so estatistica; dinheiro fica em lamports/Decimal no motor.
"""

from __future__ import annotations

import numpy as np

MRE = 0.05     # +0,05 por SOL arriscado (previsao da H-011)
REFUT = 0.01   # refutacao (a): nenhum IC inferior acima de +0,01
REPS = 10_000
SEED = 74


def boot_ci(diffs, mints, reps=REPS, seed=SEED):
    by: dict[str, list[float]] = {}
    for d, m in zip(diffs, mints):
        by.setdefault(m, []).append(float(d))
    sums = np.array([sum(v) for v in by.values()])
    cnts = np.array([len(v) for v in by.values()], dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(reps, len(sums)))
    means = np.sort(sums[idx].sum(axis=1) / cnts[idx].sum(axis=1))
    return float(means[int(0.025 * reps)]), float(means[int(0.975 * reps)])


def perm_p(diffs, mints=None, reps=REPS, seed=SEED):
    """Troca de sinal por CLUSTER de mint (Astra, pre-corrida: a unidade da permutacao tem de
    ser a mesma do bootstrap). Sem `mints`, cada diferenca e o seu proprio cluster."""
    mints = mints if mints is not None else list(range(len(diffs)))
    by: dict = {}
    for d, m in zip(diffs, mints):
        by[m] = by.get(m, 0.0) + float(d)
    v = np.array(list(by.values()))
    n = len(diffs)
    obs = abs(v.sum() / n)
    rng = np.random.default_rng(seed + 1)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(reps, len(v)))
    hits = int((np.abs((signs * v).sum(axis=1) / n) >= obs - 1e-15).sum())
    return (hits + 1) / (reps + 1)


def holm(pvals: dict) -> dict:
    """Holm-Bonferroni sobre a familia principal (as politicas != controlo)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for k, (name, p) in enumerate(items):
        run = max(run, min(1.0, (m - k) * p))
        out[name] = run
    return out


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 1.0)
    ph = k / n
    den = 1 + z * z / n
    mid = (ph + z * z / (2 * n)) / den
    half = z * ((ph * (1 - ph) / n + z * z / (4 * n * n)) ** 0.5) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def _neighbours(order, name):
    k = order.index(name)
    return [order[j] for j in (k - 1, k + 1) if 0 <= j < len(order)]


def verdict(base, lat5, targets, pops, control):
    """Regra congelada ANTES de correr (ver notes-R74 §2). `base`/`lat5`: {politica: celula}.

    Devolve (rotulo, motivos). Refutacao tem precedencia sobre confirmacao.
    """
    why = []
    grid = [n for n in targets + pops if n != control]
    # refutacao (a): nenhum IC inferior acima de +0,01 em toda a grade (alvos + repiques)
    ref_a = all(base[n]["lo"] <= REFUT for n in grid)
    if ref_a:
        why.append("(a) nenhum IC inferior > +0,01 (maior = %+.4f)" % max(base[n]["lo"] for n in grid))
    # refutacao (b): melhor ALVO (maior D entre multiplos) na borda da grade
    edge = (targets[0], targets[-1])
    best_t = max(targets, key=lambda n: (base[n]["D"], n not in edge))  # empate -> interior
    ref_b = best_t in edge
    if ref_b:
        why.append("(b) melhor alvo %s (D %+.4f) na borda da grade" % (best_t, base[best_t]["D"]))
    # refutacao (c): o ganho da MESMA politica, escolhida a 1,6 s, desaparece a 5 s (D <= 0).
    # D > 0 com IC a atravessar zero a 5 s e evidencia insuficiente, nao desaparecimento (Astra).
    best = max(grid, key=lambda n: (base[n]["D"], n not in edge))
    ref_c = base[best]["D"] > 0 and lat5[best]["D"] <= 0
    if ref_c:
        why.append("(c) %s: D %+.4f a 1,6 s vira %+.4f a 5 s" % (best, base[best]["D"], lat5[best]["D"]))
    why.append("melhor da grade a 1,6 s: %s D %+.4f IC [%+.4f, %+.4f] -> a 5 s D %+.4f IC [%+.4f, %+.4f]"
               % (best, base[best]["D"], base[best]["lo"], base[best]["hi"],
                  lat5[best]["D"], lat5[best]["lo"], lat5[best]["hi"]))
    conf = []
    for fam in (targets, pops):
        for n in fam:
            if n == control:
                continue
            c = base[n]
            plateau = any(base[m]["D"] > 0 for m in _neighbours(fam, n) if m != control)
            if c["D"] >= MRE and c["lo"] > 0 and plateau and lat5[n]["D"] > 0:
                conf.append(n)
    if conf:
        why.append("cumprem a previsao (D >= +0,05, IC inf > 0, patamar, D > 0 a 5 s): %s" % ", ".join(conf))
    if ref_a or ref_b or ref_c:
        return "REFUTA", why
    if conf:
        return "CONFIRMA", why
    why.append("nenhuma celula cumpre D >= MRE, IC inferior > 0 e patamar")
    return "NAO CONFIRMA", why
