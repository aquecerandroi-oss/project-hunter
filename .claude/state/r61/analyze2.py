"""R61 v2 - snapshots (SOL, 15 s) and boards (USD, 1 min) analysed as separate series; no unit mixing."""
from __future__ import annotations
import os, sys
import numpy as np
import polars as pl

D = os.path.dirname(os.path.abspath(__file__))
FEE, SLIP, TRAIL, HOLD, DELAY = 0.0125, 0.03, 0.20, 300.0, 20.0
OUT = open(os.path.join(D, "out2.txt"), "w", encoding="utf-8")


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s); OUT.write(s + "\n")


def load(name, ts_cols):
    df = pl.read_csv(os.path.join(D, name), separator="\t", infer_schema_length=100000, null_values=[""])
    for c in ts_cols:
        df = df.with_columns(pl.col(c).str.replace(r"\+00$", "").str.to_datetime(time_unit="us", strict=False).alias(c))
    return df


def epoch(col):
    return col.cast(pl.Int64) / 1e6


ev = load("e1.tsv", ["observed_at", "mint_updated_at", "prev_obs", "prev_upd", "created_at", "completed_at", "migrated_at"])
snap = load("e2.tsv", ["observed_at"]); brd = load("e3.tsv", ["observed_at", "mint_updated_at"])
c1 = load("c1.tsv", ["created_at", "completed_at", "migrated_at"]); c2 = load("c2.tsv", ["observed_at"]); c3 = load("c3.tsv", ["observed_at", "mint_updated_at"])


def series_snap(df):
    a = df.filter(pl.col("mcap_sol").is_not_null()).select("mint", t=epoch(pl.col("observed_at")), v=pl.col("mcap_sol").cast(pl.Float64)).filter(pl.col("v") > 0).sort(["mint", "t"])
    return {m: (g["t"].to_numpy(), g["v"].to_numpy()) for (m,), g in a.group_by(["mint"], maintain_order=True)}


def series_board(df):
    a = df.filter(pl.col("market_cap_usd").is_not_null()).select("mint", t=epoch(pl.col("mint_updated_at")), v=pl.col("market_cap_usd").cast(pl.Float64)).filter(pl.col("v") > 0).unique(["mint", "t"]).sort(["mint", "t"])
    return {m: (g["t"].to_numpy(), g["v"].to_numpy()) for (m,), g in a.group_by(["mint"], maintain_order=True)}


SS_ev, SB_ev = series_snap(snap), series_board(brd)
SS_c, SB_c = series_snap(c2), series_board(c3)


def value_at(t, v, at, tol_before, tol_after):
    i = np.searchsorted(t, at, side="right") - 1
    if i >= 0 and at - t[i] <= tol_before:
        return v[i]
    j = i + 1
    if j < len(t) and t[j] - at <= tol_after:
        return v[j]
    return np.nan


def boom_start(t, v, t0, k=1.5, win=60.0):
    for i in range(len(t)):
        if t[i] < t0:
            continue
        j = np.searchsorted(t, t[i] - win, side="right") - 1
        if j >= 0 and v[i] >= k * v[j]:
            return t[i]
    return np.nan


def paper_R(t, v, t_entry):
    j = np.searchsorted(t, t_entry, side="left")
    if j >= len(t) or t[j] - t_entry > 90:
        return np.nan, "no_entry"
    pe = v[j] * (1 + SLIP); peak = v[j]; exit_v = None; why = None
    for k in range(j + 1, len(t)):
        if t[k] - t[j] > HOLD:
            exit_v, why = v[k], "time"; break
        peak = max(peak, v[k])
        if v[k] <= peak * (1 - TRAIL):
            exit_v, why = v[k], "trail"; break
    if exit_v is None:
        if t[-1] - t[j] < 60:
            return np.nan, "no_exit_data"
        exit_v, why = v[-1], "censored"
    return (exit_v * (1 - SLIP) / pe) * (1 - FEE) ** 2 - 1.0, why


def analyse(events, SS, SB):
    rows = []
    for r in events.iter_rows(named=True):
        m = r["mint"]; t_kol = r["t_kol"]; t_prev = r["t_prev"]; t_c = r["t_created"]
        if t_c is None or not np.isfinite(t_c):
            continue
        d = dict(mint=m, prev_kol=r.get("prev_kol"), kol=r.get("kol_count"), board=r.get("board"), age_kol=t_kol - t_c,
                 unc=(t_kol - t_prev) if t_prev is not None and np.isfinite(t_prev) else np.nan,
                 graduated=r.get("completed_at") is not None, holders=r.get("holders"))
        # --- snapshot series (SOL)
        if m in SS and len(SS[m][0]) >= 3:
            t, v = SS[m]
            vk = value_at(t, v, t_kol, 90, 30)
            d["s_vk"] = vk
            if np.isfinite(vk):
                ip = int(np.argmax(v)); d["s_lead_peak"] = t[ip] - t_kol; d["s_peak_over_kol"] = v[ip] / vk
                d["s_peak_before_lb"] = (t[ip] < t_prev) if np.isfinite(d["unc"]) else (t[ip] < t_kol)
                tb = boom_start(t, v, t_c); d["s_lead_boom"] = tb - t_kol
                d["s_lead_boom_opt"] = tb - t_prev if np.isfinite(d["unc"]) else np.nan
                after = np.where((t > t[ip]) & (v <= 0.5 * v[ip]))[0]; d["s_lead_crash"] = (t[after[0]] - t_kol) if len(after) else np.nan
                d["s_r1"] = value_at(t, v, t_kol + 60, 45, 30) / vk
                d["s_r5"] = value_at(t, v, t_kol + 300, 90, 60) / vk
                post = v[t >= t_kol]; d["s_rmax"] = post.max() / vk if len(post) else np.nan
                pre = v[t <= t_kol]; d["s_kol_over_prepeak"] = vk / pre.max() if len(pre) else np.nan
                d["s_R"], d["s_why"] = paper_R(t, v, t_kol + DELAY)
                if np.isfinite(d["unc"]):
                    d["s_R_opt"], d["s_why_opt"] = paper_R(t, v, t_prev + DELAY)
                    d["s_R_mid"], d["s_why_mid"] = paper_R(t, v, 0.5 * (t_prev + t_kol) + DELAY)
                d["s_cov"] = t[-1] - t_kol
        # --- board series (USD)
        if m in SB and len(SB[m][0]) >= 2:
            t, v = SB[m]
            vk = value_at(t, v, t_kol, 1, 1) if r.get("board") is not None else value_at(t, v, t_kol, 90, 90)
            d["b_vk"] = vk
            if np.isfinite(vk):
                ip = int(np.argmax(v)); d["b_lead_peak"] = t[ip] - t_kol; d["b_peak_over_kol"] = v[ip] / vk
                after = np.where((t > t[ip]) & (v <= 0.5 * v[ip]))[0]; d["b_lead_crash"] = (t[after[0]] - t_kol) if len(after) else np.nan
                tb = boom_start(t, v, t[0], 1.5, 90.0); d["b_lead_boom"] = tb - t_kol
                d["b_r1"] = value_at(t, v, t_kol + 60, 40, 40) / vk
                d["b_r5"] = value_at(t, v, t_kol + 300, 90, 90) / vk
                d["b_r15"] = value_at(t, v, t_kol + 900, 120, 120) / vk
                d["b_r60"] = value_at(t, v, t_kol + 3600, 300, 300) / vk
                post = v[t >= t_kol]; d["b_rmax"] = post.max() / vk if len(post) else np.nan
                pre = v[t <= t_kol]; d["b_kol_over_prepeak"] = vk / pre.max() if len(pre) else np.nan
                d["b_cov"] = t[-1] - t_kol; d["b_n"] = len(t)
        rows.append(d)
    return pl.DataFrame(rows, infer_schema_length=None)


def q(x, ps=(0.1, 0.25, 0.5, 0.75, 0.9)):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return "n=0" if len(x) == 0 else f"n={len(x)} " + " ".join(f"p{int(p*100)}={np.quantile(x, p):.0f}" for p in ps)


def col(df, c):
    if c not in df.columns:
        return np.array([])
    x = df[c].cast(pl.Float64, strict=False).to_numpy().astype(float)
    return x


def ratio_line(df, c):
    x = col(df, c); x = x[np.isfinite(x)]
    if len(x) == 0:
        return f"{c}: n=0"
    return f"{c}: n={len(x)} mean={x.mean():.2f} p25={np.quantile(x,.25):.2f} p50={np.quantile(x,.5):.2f} p75={np.quantile(x,.75):.2f} p90={np.quantile(x,.9):.2f} >=1.5x {(x>=1.5).mean()*100:.0f}% >=2x {(x>=2).mean()*100:.0f}% <=0.5x {(x<=0.5).mean()*100:.0f}%"


def summarize(df, title):
    P(f"\n=== {title} (n={df.height}) ===")
    P("age at sighting s:", q(col(df, 'age_kol')), "| uncertainty s:", q(col(df, 'unc')))
    lp = col(df, 's_lead_peak'); lb = col(df, 's_lead_boom'); lbo = col(df, 's_lead_boom_opt'); lc = col(df, 's_lead_crash')
    P("[15s] peak - t_kol s:", q(lp), f"| peak<=sighting {np.mean(lp[np.isfinite(lp)] <= 0)*100:.0f}% | peak before lower bound {np.nanmean(col(df,'s_peak_before_lb'))*100:.0f}%")
    fin = np.isfinite(lb)
    P("[15s] boom(+50%/60s) - t_kol s:", q(lb), f"| no boom {(~fin).mean()*100:.0f}% | of booms: after sighting {np.mean(lb[fin] > 0)*100:.0f}%, >30s after {np.mean(lb[fin] > 30)*100:.0f}%, <= 0 {np.mean(lb[fin] <= 0)*100:.0f}%")
    fo = np.isfinite(lbo)
    P("[15s] boom - t_prev (optimistic bound) s:", q(lbo), f"| of booms: >30s after lower bound {np.mean(lbo[fo] > 30)*100:.0f}%")
    P("[15s] crash(-50% of peak) - t_kol s:", q(lc), f"| no crash seen {(~np.isfinite(lc)).mean()*100:.0f}%")
    for c in ("s_r1", "s_r5", "s_rmax", "s_peak_over_kol", "s_kol_over_prepeak"):
        P("[15s]", ratio_line(df, c))
    for c, w in (("s_R", "s_why"), ("s_R_mid", "s_why_mid"), ("s_R_opt", "s_why_opt")):
        R = col(df, c); R = R[np.isfinite(R)]
        if len(R):
            P(f"[15s] paper {c} (entry +20s, fee 1.25%/leg, slip 3%, trail 20%/5min): n={len(R)} mean={R.mean():+.3f} median={np.median(R):+.3f} hit={(R>0).mean()*100:.0f}% sum={R.sum():+.1f} p90={np.quantile(R,.9):+.3f} max={R.max():+.2f} top3={np.sort(R)[-3:].sum()/max(R[R>0].sum(),1e-9)*100:.0f}% of gross gains",
              "| exits:", {k: v for k, v in zip(*df.filter(pl.col(c).is_not_nan() & pl.col(c).is_not_null()).group_by(w).len().sort(w).to_dict(as_series=False).values())} if w in df.columns else "")
    P("[15s] coverage after sighting s:", q(col(df, 's_cov')))
    bp = col(df, 'b_lead_peak'); bb = col(df, 'b_lead_boom'); bc = col(df, 'b_lead_crash')
    P("[1min boards] peak - t_kol s:", q(bp), f"| peak<=sighting {np.mean(bp[np.isfinite(bp)] <= 0)*100:.0f}% | peak > 60s after {np.mean(bp[np.isfinite(bp)] > 60)*100:.0f}%")
    fb = np.isfinite(bb)
    P("[1min boards] boom(+50%/90s) - t_kol s:", q(bb), f"| no boom {(~fb).mean()*100:.0f}% | of booms: after sighting {np.mean(bb[fb] > 0)*100:.0f}%")
    P("[1min boards] crash - t_kol s:", q(bc), f"| no crash seen {(~np.isfinite(bc)).mean()*100:.0f}%")
    for c in ("b_r1", "b_r5", "b_r15", "b_r60", "b_rmax", "b_peak_over_kol", "b_kol_over_prepeak"):
        P("[1min boards]", ratio_line(df, c))
    P("[1min boards] coverage after sighting s:", q(col(df, 'b_cov')), "| graduated share:", f"{np.nanmean(col(df,'graduated'))*100:.0f}%")


ev2 = ev.with_columns(t_kol=epoch(pl.col("mint_updated_at")), t_prev=epoch(pl.col("prev_upd")), t_created=epoch(pl.col("created_at")))
res = analyse(ev2, SS_ev, SB_ev)
summarize(res, "ALL first KOL increments")
summarize(res.filter(pl.col("prev_kol") == 0), "0 -> >=1 witnessed")
summarize(res.filter(pl.col("prev_kol") >= 1), "k -> k+1 (k>=1)")
summarize(res.filter(pl.col("kol") >= 3), "sighting with kol_count >= 3 after the jump")
summarize(res.filter(pl.col("age_kol") < 120), "sighting age < 2 min")
summarize(res.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 300)), "sighting age 2-5 min")
summarize(res.filter((pl.col("age_kol") >= 300) & (pl.col("age_kol") < 1800)), "sighting age 5-30 min")
summarize(res.filter(pl.col("age_kol") >= 1800), "sighting age >= 30 min")
summarize(res.filter(pl.col("board") != "new"), "sighting on graduating/movers/graduated")
summarize(res.filter(pl.col("board") == "new"), "sighting on new")

# --- control matched on age & mcap (snapshot series), no KOL ever
rng = np.random.default_rng(61)
c1b = c1.with_columns(t_created=epoch(pl.col("created_at")))
cidx = {r["mint"]: r for r in c1b.iter_rows(named=True)}
pool = np.array([m for m in cidx if m in SS_c and len(SS_c[m][0]) >= 3 and cidx[m]["t_created"] is not None])
used = set(); ctrl_rows = []; unmatched = 0
for r in res.filter(pl.col("s_vk").is_not_null() & pl.col("s_vk").is_not_nan()).iter_rows(named=True):
    age, vk = r["age_kol"], r["s_vk"]; ok = False
    for m in rng.permutation(pool)[:600]:
        if m in used:
            continue
        t, v = SS_c[m]; tc = cidx[m]["t_created"]
        vv = value_at(t, v, tc + age, 90, 30)
        if np.isfinite(vv) and 0.75 * vk <= vv <= 1.25 * vk:
            used.add(m); ok = True
            ctrl_rows.append(dict(mint=m, t_kol=tc + age, t_prev=np.nan, t_created=tc, prev_kol=None, kol_count=None, board=None, holders=None, completed_at=cidx[m]["completed_at"]))
            break
    unmatched += (not ok)
ctrl = pl.DataFrame(ctrl_rows, infer_schema_length=None)
resc = analyse(ctrl, SS_c, SB_c)
summarize(resc, f"CONTROL no-KOL matched on age & mcap(+-25%) — matched {ctrl.height}, unmatched {unmatched}")
summarize(resc.filter(pl.col("age_kol") < 120), "control age < 2 min")
summarize(resc.filter((pl.col("age_kol") >= 120) & (pl.col("age_kol") < 300)), "control age 2-5 min")
summarize(resc.filter(pl.col("age_kol") >= 300), "control age >= 5 min")
res.write_csv(os.path.join(D, "res2_kol.csv")); resc.write_csv(os.path.join(D, "res2_ctrl.csv"))
OUT.close()
