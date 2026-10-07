"""lab-cost-sweep — extras: (a) os 10 sinais reais da spot/1 × o desfecho-sombra do mesmo sinal no Lab;
(b) aritmética de poder para uma coorte futura (EP agrupado por dia escalado pelo nº de dias)."""
import csv, gzip, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import sweep
rows = {r["signal_id"]: r for r in csv.DictReader(gzip.open(HERE / "cache/out.csv.gz", "rt", encoding="utf-8"))}
spot = list(csv.DictReader(open(HERE / "cache/spot.csv", encoding="utf-8")))
print("(a) spot/1 real × sombra do Lab no MESMO sinal (mean_reversion v14 perp):")
pairs = []
for p in spot:
    r = rows.get(p["signal_id"])
    if r is None:
        print("  sem sombra:", p["signal_id"]); continue
    t = sweep.Trade.from_row(r)
    pairs.append((float(p["r_multiple"]), t.r_lab, t.gross_r, t.scenario_r(fee_bp=5, slip_bp=0, with_funding=True)))
    print(f"  {p['market_symbol']:9s} {p['entry_at'][:16]} real {float(p['r_multiple']):+.3f} | sombra R_lab {t.r_lab:+.3f} "
          f"G {t.gross_r:+.3f} | {t.result}")
a = np.array(pairs)
print(f"  médias (n={len(a)}): real {a[:,0].mean():+.3f} · sombra R_lab {a[:,1].mean():+.3f} · sombra G {a[:,2].mean():+.3f} "
      f"· sombra taker5 {a[:,3].mean():+.3f} · real − sombra G {(a[:,0]-a[:,2]).mean():+.3f} R")

print("\n(b) poder de REJEITAR média = 0 quando a média verdadeira é +efeito (não de provar média > efeito); aproximação "
      "normal, bilateral 5 %, 80 % (z 1,96 + 0,84); EP agrupado por dia desta coorte escalado por 1/√dias; 'dias' = dias "
      "COM trades elegíveis, mesma frequência/variância/dependência; SEM paradas intermediárias — referência "
      "condicional, potencialmente otimista (Astra, must-fix 5):")
trades = [sweep.Trade.from_row(r) for r in rows.values()]
for key in (("mean_reversion", "v10"), ("mean_reversion", "v7"), ("mean_reversion", "v14"), ("momentum", "v3")):
    ts = [t for t in trades if (t.strategy, t.version) == key and t.cohort == "prospective" and t.mt == "perpetual"
          and t.funding is not None]
    r = np.array([t.scenario_r(fee_bp=5, slip_bp=0, with_funding=True) for t in ts])
    days = sorted({t.day for t in ts})
    by = np.array([r[[i for i, t in enumerate(ts) if t.day == d]].sum() for d in days])
    cnt = np.array([sum(1 for t in ts if t.day == d) for d in days])
    m = r.mean()
    # EP agrupado (linearização da razão Σr/Σn por dia)
    resid = by - m * cnt
    se = float(np.sqrt(len(days) / (len(days) - 1) * np.sum(resid ** 2)) / cnt.sum())
    sd = float(r.std(ddof=1))
    for eff in (0.03, 0.05, 0.10):
        need = len(days) * (se * 2.8 / eff) ** 2
        print(f"  {key[0]} {key[1]}: n {len(ts)}, {len(days)} dias, média taker5 {m:+.3f}, EP dia {se:.3f}, dp/trade {sd:.2f} "
              f"→ efeito {eff:+.2f} R pede ≈ {need:.0f} dias (≈ {need * len(ts) / len(days):.0f} trades)")
