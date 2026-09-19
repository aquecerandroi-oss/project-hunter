import os, numpy as np, polars as pl
D = os.path.dirname(os.path.abspath(__file__))
res = pl.read_csv(os.path.join(D, "res2_kol.csv"), infer_schema_length=None)
rng = np.random.default_rng(7)
def ci(df, c, title):
    x = df[c].cast(pl.Float64, strict=False).to_numpy().astype(float); x = x[np.isfinite(x)]
    bs = np.array([rng.choice(x, len(x)).mean() for _ in range(3000)])
    srt = np.sort(x)
    print(f"{title} {c}: n={len(x)} mean={x.mean():+.3f} CI95=[{np.quantile(bs,.025):+.3f},{np.quantile(bs,.975):+.3f}] hit={(x>0).mean()*100:.0f}% median={np.median(x):+.3f} w/o top3={srt[:-3].mean():+.3f} top3 share of gross={srt[-3:].sum()/srt[srt>0].sum()*100:.0f}%")
for lo, hi, t in ((120, 300, "age 2-5"), (300, 1800, "age 5-30"), (120, 1800, "age 2-30")):
    sub = res.filter((pl.col("age_kol") >= lo) & (pl.col("age_kol") < hi))
    for c in ("s_R", "s_R_mid", "s_R_opt"):
        ci(sub, c, t)
sub = res.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 1800) & (pl.col("s_kol_over_prepeak") >= 0.95))
for c in ("s_R", "s_R_mid", "s_R_opt"): ci(sub, c, "age 2-30 at pre-peak")
sub = res.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 1800) & (pl.col("holders") >= 30))
for c in ("s_R", "s_R_mid", "s_R_opt"): ci(sub, c, "age 2-30 holders>=30")
# per-day stability for age 2-30
ev = pl.read_csv(os.path.join(D, "e1.tsv"), separator="\t", infer_schema_length=None).select("mint", "observed_at")
sub = res.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 1800)).join(ev, on="mint").with_columns(day=pl.col("observed_at").str.slice(0, 10))
for (d,), g in sub.group_by(["day"], maintain_order=True):
    for c in ("s_R", "s_R_mid"): ci(g, c, f"age 2-30 day {d}")
