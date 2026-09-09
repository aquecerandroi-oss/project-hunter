"""T3.54 — bootstrap de blocos por dia para um contraste **transversal**.

Aqui a variante de 1 h **não decide as mesmas barras** do pai de 15 m (o piso de
ATR% morde de forma diferente numa grade e noutra), então não existe par decisão
a decisão e o estimando é a diferença de médias entre duas populações. O bloco
continua sendo o **dia**, porque decisões do mesmo dia em quatro mercados
correlacionados compartilham choque (KB-0010) — e os dias reamostrados são os
mesmos para as duas populações, senão o contraste misturaria dias diferentes.

Não é código de produção: mora em ``.claude/state/exp-drafts/``. NumPy sobre
janelas em memória; nada de ``Decimal`` porque nada disto é dinheiro persistido.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict

import numpy as np

CSV = "C:/dev/project-hunter/.claude/state/exp-drafts/t354/decisoes.csv"
RESAMPLES = 10_000
SEED = 20260909


def load() -> dict[str, dict[str, list[float]]]:
    """``versao -> dia -> [r_net]``."""
    out: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with open(CSV, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out[row["versao"]][row["dia_utc"]].append(float(row["r_net"]))
    return out


def bootstrap(
    a: dict[str, list[float]], b: dict[str, list[float]]
) -> tuple[float, float, tuple[float, float], int, int]:
    """Média(a) − média(b) e IC 95 % percentil, reamostrando **dias** em comum."""
    days = sorted(set(a) | set(b))
    rng = np.random.default_rng(SEED)
    index = np.arange(len(days))
    flat_a = np.concatenate([np.array(a.get(d, []), dtype=float) for d in days])
    flat_b = np.concatenate([np.array(b.get(d, []), dtype=float) for d in days])
    samples = np.empty(RESAMPLES, dtype=float)
    valid = 0
    for i in range(RESAMPLES):
        chosen = rng.choice(index, size=len(days), replace=True)
        pa = np.concatenate([np.array(a.get(days[j], []), dtype=float) for j in chosen])
        pb = np.concatenate([np.array(b.get(days[j], []), dtype=float) for j in chosen])
        if pa.size == 0 or pb.size == 0:
            samples[i] = np.nan
            continue
        samples[i] = pa.mean() - pb.mean()
        valid += 1
    finite = samples[np.isfinite(samples)]
    return (
        float(flat_a.mean()),
        float(flat_b.mean()),
        (float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))),
        valid,
        len(days),
    )


def main() -> None:
    data = load()
    pairs = [
        ("mean_reversion v10", "mean_reversion v6"),
        ("momentum v10", "momentum v8"),
    ]
    print(f"reamostragens={RESAMPLES} seed={SEED} bloco=dia UTC")
    print()
    for variant, parent in pairs:
        if variant not in data or parent not in data:
            print(f"{variant} vs {parent}: populacao ausente")
            continue
        mv, mp, ci, valid, days = bootstrap(data[variant], data[parent])
        nv = sum(len(v) for v in data[variant].values())
        npar = sum(len(v) for v in data[parent].values())
        sign = "sim" if ci[0] > 0 or ci[1] < 0 else "NAO"
        print(f"{variant}  n={nv}  media={mv:+.4f} R")
        print(f"{parent}   n={npar}  media={mp:+.4f} R")
        print(
            f"  delta = {mv - mp:+.4f} R   IC95% [{ci[0]:+.4f}; {ci[1]:+.4f}]   "
            f"dias={days}  reamostragens validas={valid}  distingue de zero: {sign}"
        )
        print()
    print("soma de R por versao (o que a coorte inteira rendeu):")
    for versao in sorted(data):
        total = sum(sum(v) for v in data[versao].values())
        n = sum(len(v) for v in data[versao].values())
        print(f"  {versao:<22} n={n:>4}  soma={total:+8.2f} R  media={total / n:+.4f} R")


if __name__ == "__main__":
    main()
    sys.exit(0)
