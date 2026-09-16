"""KB-0110 - simulacao das saidas S0..S4 na serie de 15 s (12-16/09/2026).

Entradas e serie vem de infra/scripts/sql/research/2026-09-16-r20-q0{1,2}-*.sql
(dump |-separado). Nada aqui toca o banco: e uma funcao pura sobre os dois dumps.

Convencoes (KB-0099 r4-q05, reusadas sem mudanca):
  base   = mcap observado na barra de 1 min de entrada (fill pessimista)
  taxa   = 1,75 % por perna  -> multiplo liquido = (saida/base) * 0.9825**2
  R      = (multiplo liquido - 1) / 0.5     (unidade de risco = o piso de -50 %)
  pico   = max(base, mcaps ate a foto ANTERIOR) -- causal, nunca olha a propria foto
  stop   = preenchido no mcap OBSERVADO da foto, nao no nivel
E20 = a foto corrente esta <= 80 % do pico corrente (KB-0108 §3).
"""
import sys, math, random
from collections import defaultdict

FEE = 0.9825 ** 2
random.seed(20260916)


def load(entradas_path, serie_path):
    ent = {}
    for ln in open(entradas_path, encoding="utf-8"):
        dia, mint, sym, snip, t_in, base = ln.rstrip("\n").split("|")
        ent[mint] = dict(dia=dia, mint=mint, sym=sym, snipers=int(snip), t_in=t_in,
                         base=float(base), serie=[])
    for ln in open(serie_path, encoding="utf-8"):
        dia, mint, base, dt, mcap, sells, buys = ln.rstrip("\n").split("|")
        if mint not in ent:
            continue
        s = None if sells == "" else float(sells)
        b = None if buys == "" else float(buys)
        ratio = (s / b) if (s is not None and b) else None
        ent[mint]["serie"].append((int(float(dt)), float(mcap), ratio))
    for e in ent.values():
        e["serie"].sort()
    return ent


def simulate(e, variant):
    """Retorna (r, motivo, tempo_s). Pura: so le e['base'] e e['serie']."""
    base = e["base"]
    serie = e["serie"]
    if not serie:
        return None
    peak = base  # pico ate a foto anterior (inclui a entrada)
    for dt, mcap, ratio in serie:
        # 1) alvo 3x tem prioridade (ordem do r4-q05)
        if mcap >= 3.0 * base:
            return ((3.0 * base / base) * FEE - 1) / 0.5, "alvo_3x", dt
        # 2) piso -50 % e trailing 35 % apos 1,5x (S0, presente em todas menos S4 acima de 1,5x)
        if variant == "S4" and peak >= 1.5 * base:
            nivel = 0.5 * base            # o trailing 35 % sai; fica so o piso
        elif peak >= 1.5 * base:
            nivel = max(0.65 * peak, 0.5 * base)
        else:
            nivel = 0.5 * base
        hit_s0 = mcap <= nivel
        # 3) E20 conforme a variante
        e20 = mcap <= 0.80 * peak
        if variant == "S0":
            armado = False
        elif variant == "S1":
            armado = True
        elif variant == "S2":
            armado = peak >= 1.30 * base
        elif variant == "S3":
            armado = ratio is not None and ratio > 0.6
        elif variant == "S4":
            armado = peak >= 1.50 * base
        hit_e20 = e20 and armado
        if hit_s0 or hit_e20:
            motivo = "e20" if (hit_e20 and not hit_s0) else ("stop" if hit_s0 and not hit_e20 else "stop+e20")
            return ((mcap / base) * FEE - 1) / 0.5, motivo, dt
        if mcap > peak:
            peak = mcap
    dt, mcap, _ = serie[-1]
    return ((mcap / base) * FEE - 1) / 0.5, "tempo", dt


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] if lo == hi else xs[lo] * (hi - k) + xs[hi] * (k - lo)


def boot_ci(by_day, n=10000):
    dias = list(by_day)
    out = []
    for _ in range(n):
        amostra = [r for d in (random.choice(dias) for _ in dias) for r in by_day[d]]
        if amostra:
            out.append(sum(amostra) / len(amostra))
    return pct(out, 0.025), pct(out, 0.975)


def main(ent_p, ser_p):
    ent = load(ent_p, ser_p)
    variants = ["S0", "S1", "S2", "S3", "S4"]
    res = {v: {} for v in variants}
    sem_serie = [m for m, e in ent.items() if not e["serie"]]
    for v in variants:
        for m, e in ent.items():
            r = simulate(e, v)
            if r:
                res[v][m] = r
    print(f"entradas={len(ent)}  sem serie de 15 s={len(sem_serie)}  com serie={len(res['S0'])}")
    print()
    hdr = ("var", "n", "R medio", "R mediano", "R total", ">=+2R", "<=-0.5R",
           "tempo med (s)", "saidas E20", "IC95 do R medio")
    print("|" + "|".join(hdr) + "|")
    for v in variants:
        rs = [x[0] for x in res[v].values()]
        by_day = defaultdict(list)
        for m, x in res[v].items():
            by_day[ent[m]["dia"]].append(x[0])
        lo, hi = boot_ci(by_day)
        n = len(rs)
        ne20 = sum(1 for x in res[v].values() if "e20" in x[1])
        print("|%s|%d|%+.3f|%+.3f|%+.1f|%.1f%%|%.1f%%|%.0f|%d (%.1f%%)|[%+.2f; %+.2f]|" % (
            v, n, sum(rs) / n, pct(rs, 0.5), sum(rs),
            100 * sum(1 for r in rs if r >= 2) / n,
            100 * sum(1 for r in rs if r <= -0.5) / n,
            sum(x[2] for x in res[v].values()) / n,
            ne20, 100 * ne20 / n, lo, hi))
    print()
    print("motivos de saida por variante")
    for v in variants:
        c = defaultdict(int)
        for x in res[v].values():
            c[x[1]] += 1
        print(v, dict(sorted(c.items(), key=lambda kv: -kv[1])))
    print()
    print("cauda: 10 melhores de S0 sob cada variante")
    top = sorted(res["S0"].items(), key=lambda kv: -kv[1][0])[:10]
    print("|moeda|dia|" + "|".join(variants) + "|")
    for m, x in top:
        print("|%s|%s|" % (ent[m]["sym"], ent[m]["dia"][5:]) +
              "|".join("%+.2f" % res[v][m][0] for v in variants) + "|")
    print("|**soma top-10 de S0**||" + "|".join(
        "%+.2f" % sum(res[v][m][0] for m, _ in top) for v in variants) + "|")
    print()
    print("R total por dia")
    print("|dia|n|" + "|".join(variants) + "|")
    for d in sorted({e["dia"] for e in ent.values()}):
        ms = [m for m in res["S0"] if ent[m]["dia"] == d]
        print("|%s|%d|" % (d, len(ms)) + "|".join(
            "%+.2f" % sum(res[v][m][0] for m in ms) for v in variants) + "|")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
