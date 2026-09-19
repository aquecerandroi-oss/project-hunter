import os, numpy as np, polars as pl
D = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(D, "analyze2.py"), encoding="utf-8").read()
exec(src.split("ev = load(")[0])
exec(src.split("c1 = load(")[1].split(chr(10), 1)[1].split("ev2 = ev.with_columns")[0].replace("SS_ev, SB_ev = series_snap(snap), series_board(brd)", "").replace("SS_c, SB_c = series_snap(c2), series_board(c3)", ""))
res = pl.read_csv(os.path.join(D, "res2_kol.csv"), infer_schema_length=None)
ev = load("e1.tsv", ["created_at"]).select("mint", "has_tw", "has_tg", "has_ws", "twitter_kind")
res = res.join(ev, on="mint", how="left")
def short(df, title):
    R = col(df, "s_R"); R = R[np.isfinite(R)]; Ro = col(df, "s_R_opt"); Ro = Ro[np.isfinite(Ro)]
    lb = col(df, "s_lead_boom"); fin = np.isfinite(lb); kp = col(df, "s_kol_over_prepeak"); kp = kp[np.isfinite(kp)]
    r5 = col(df, "s_r5"); r5 = r5[np.isfinite(r5)]; rmax = col(df, "s_rmax"); rmax = rmax[np.isfinite(rmax)]
    lp = col(df, "s_lead_peak"); lp = lp[np.isfinite(lp)]
    P(f"{title}: n={df.height} | boom {fin.mean()*100:.0f}% (of which >30s after {np.mean(lb[fin]>30)*100:.0f}%) | peak<=sighting {np.mean(lp<=0)*100:.0f}% | already -20% from pre-peak {np.mean(kp<=0.8)*100:.0f}% | r5 p50 {np.median(r5):.2f} | rmax>=2x {np.mean(rmax>=2)*100:.0f}% | R mean {R.mean():+.3f} hit {(R>0).mean()*100:.0f}% (n={len(R)}) | R_opt mean {Ro.mean():+.3f} hit {(Ro>0).mean()*100:.0f}% | grad {np.nanmean(col(df,'graduated'))*100:.0f}%")
short(res, "ALL")
short(res.filter(pl.col("has_tw") == True), "has twitter")
short(res.filter(pl.col("has_tw") == False), "no twitter")
short(res.filter(pl.col("twitter_kind") == "profile"), "twitter profile")
short(res.filter(pl.col("twitter_kind") == "post"), "twitter post")
short(res.filter(pl.col("has_tg") == True), "has telegram")
for lo, hi in ((0, 10), (10, 30), (30, 100), (100, 10**6)):
    short(res.filter((pl.col("holders") >= lo) & (pl.col("holders") < hi)), f"holders at sighting [{lo},{hi})")
for lo, hi in ((0, 40), (40, 60), (60, 100), (100, 300), (300, 10**9)):
    short(res.filter((pl.col("s_vk") >= lo) & (pl.col("s_vk") < hi)), f"mcap SOL at sighting [{lo},{hi})")
short(res.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 1800) & (pl.col("s_kol_over_prepeak") >= 0.95)), "age 2-30 min AND at pre-peak (not fallen)")
short(res.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 1800) & (pl.col("has_tw") == True)), "age 2-30 min AND has twitter")
short(res.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 1800) & (pl.col("kol") >= 2)), "age 2-30 min AND kol>=2 after jump")
# R by hour-of-day (UTC) for age 2-5 min group, to see stability
sub = res.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 300))
P("age 2-5 min R by tercile of s_vk:", [ (float(np.nanmean(col(g,'s_R'))), g.height) for g in [sub.filter(pl.col('s_vk')<50), sub.filter((pl.col('s_vk')>=50)&(pl.col('s_vk')<100)), sub.filter(pl.col('s_vk')>=100)]])
# bootstrap CI of mean R for age 2-5 min
R = col(sub, "s_R"); R = R[np.isfinite(R)]; rng = np.random.default_rng(1)
bs = np.array([rng.choice(R, len(R)).mean() for _ in range(2000)])
P(f"age 2-5 min: R mean {R.mean():+.3f}, bootstrap 95% CI [{np.quantile(bs,.025):+.3f}, {np.quantile(bs,.975):+.3f}], n={len(R)}")
Ro = col(sub, "s_R_opt"); Ro = Ro[np.isfinite(Ro)]
bs = np.array([rng.choice(Ro, len(Ro)).mean() for _ in range(2000)])
P(f"age 2-5 min: R_opt mean {Ro.mean():+.3f}, bootstrap 95% CI [{np.quantile(bs,.025):+.3f}, {np.quantile(bs,.975):+.3f}], n={len(Ro)}; without top 5: {np.sort(Ro)[:-5].mean():+.3f}")
OUT.close()
