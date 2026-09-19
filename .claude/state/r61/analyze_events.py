"""R61 part 2 - meme_event_matches: does matched_at lead the peak? Outcome after the match."""
import os, sys
import numpy as np
import polars as pl
sys.argv = [sys.argv[0]]
D = os.path.dirname(os.path.abspath(__file__))
# reuse helpers from analyze2 without re-running it: exec only the function defs
src = open(os.path.join(D, "analyze2.py"), encoding="utf-8").read()
defs = src.split("ev = load(")[0]  # everything before data loading
exec(defs)
tail = src.split("c1 = load(")[1].split(chr(10), 1)[1].split("ev2 = ev.with_columns")[0].replace("SS_ev, SB_ev = series_snap(snap), series_board(brd)", "").replace("SS_c, SB_c = series_snap(c2), series_board(c3)", "")
exec(tail)  # value_at, boom_start, paper_R, analyse, q, col, ratio_line, summarize

m1 = load("m1.tsv", ["matched_at", "event_at", "created_at", "completed_at"])
m2 = load("m2.tsv", ["observed_at"]); m3 = load("m3.tsv", ["observed_at", "mint_updated_at"])
SS, SB = series_snap(m2), series_board(m3)
P("\n##### EVENT MATCHES #####")
P("matches (distinct mints):", m1.height, "| by kind:", m1.group_by("match_kind").len().to_dict(as_series=False))
P("by event kind/confidence:", m1.group_by(["kind", "confidence"]).len().sort("len", descending=True).to_dict(as_series=False))
m1 = m1.with_columns(t_kol=epoch(pl.col("matched_at")), t_prev=epoch(pl.col("matched_at")), t_created=epoch(pl.col("created_at")), t_event=epoch(pl.col("event_at")))
lag = (m1["t_kol"] - m1["t_created"]).to_numpy(); ev_lead = (m1["t_created"] - m1["t_event"]).to_numpy() / 3600
P("matched_at - created_at s:", q(lag), "| created_at - event.observed_at h:", q(ev_lead))
P("share with any KOL on boards:", f"{(m1['max_kol'].fill_null(0) > 0).mean()*100:.0f}%", "| graduated:", f"{m1['completed_at'].is_not_null().mean()*100:.1f}%")
m1 = m1.with_columns(pl.lit(None).alias("prev_kol"), pl.lit(None).alias("kol_count"), pl.lit(None).alias("board"), pl.lit(None).alias("holders"))
res = analyse(m1, SS, SB)
res = res.join(m1.select("mint", "match_kind", "kind", "confidence", "symbol_hint"), on="mint", how="left")
summarize(res, "ALL event matches (t_sig = matched_at)")
summarize(res.filter(pl.col("match_kind") == "buy"), "match_kind = buy")
summarize(res.filter(pl.col("match_kind") == "avoid"), "match_kind = avoid")
summarize(res.filter((pl.col("match_kind") == "buy") & (pl.col("age_kol") < 120)), "buy, matched at age < 2 min")
summarize(res.filter((pl.col("match_kind") == "buy") & (pl.col("age_kol") >= 120)), "buy, matched at age >= 2 min")
for sh in ("PAID", "ARC", "STOCKS", "GROK", "SEC"):
    sub = res.filter(pl.col("symbol_hint") == sh)
    if sub.height >= 20:
        summarize(sub, f"symbol_hint = {sh}")
res.write_csv(os.path.join(D, "res_events.csv"))
OUT.close()
