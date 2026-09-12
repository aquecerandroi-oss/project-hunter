---
task_categories:
- tabular-classification
- tabular-regression
- time-series-forecasting
tags:
- solana
- cryptocurrency
- memecoin
- defi
- pump.fun
- blockchain
- finance
- fraud-detection
size_categories:
- 10M<n<100M
pretty_name: PumpFun Launch-to-Graduation Corpus
license: mit
---

# PumpFun Launch-to-Graduation Corpus (Jun–Jul 2026)

**798,430 pump.fun token launches. 33.58 million trades. 26.9 million bonding
-curve snapshots. Every graduation outcome labeled. Tracked continuously,
second by second, for 39 uninterrupted days.**

> ⚠️ **This dataset has documented, quantified data-quality issues — several
> are not optional to handle correctly.** Full detail, root causes, and
> exact handling instructions: **[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md)**.
> Read it before you write a single query.

## What This Dataset Actually Is

Most public pump.fun data is either a live feed with no history, or a
post-graduation price scrape that starts *after* the interesting part is
already over. This corpus is different: it captures the **entire lifecycle**
of a memecoin launch — from the moment a token appears on the bonding curve,
through every trade, every 15-second state snapshot, all the way to
graduation (or quiet abandonment) and, for graduated tokens, everything that
happens to price and liquidity in the days after.

It was collected continuously via websocket and on-chain RPC polling across
a fixed **39-day window (June 5 – July 14, 2026)** — not a sample, not a
curated set of "notable" launches, but every token that appeared on the
platform during that window, whether it graduated in ten seconds or never
traded again after minute one.

**Six linked tables, joined on `mint` and `wallet`, let you move between
token-level, trade-level, and wallet-level analysis without leaving the
dataset:**

| Table | Rows | Grain |
|---|---:|---|
| `tokens.parquet` | 798,430 | 1 row per token — launch parameters, creator history, holder concentration, graduation status |
| `trades.parquet` | 33,581,765 | 1 row per trade — buy/sell, price, bonding-curve state, wallet |
| `snapshots.parquet` | 26,934,864 | 1 row per token per polling interval, pre-graduation — bonding-curve depletion, buy pressure, trade velocity |
| `postgard_snapshots.parquet` | 1,392,133 | 1 row per graduated token per polling interval, post-graduation — DEX price, liquidity, volume |
| `postgard_outcomes.parquet` | 5,669 | 1 row per graduated token — labeled outcome (`major_pump`, `minor_pump`, `sustained`, `pump_dump`, `dead`), peak price/mcap, 24h/48h liquidity survival |
| `wallet_stats.parquet` | 1,016,374 | 1 row per wallet — first/last seen, activity summary *(see known-issues note)* |
| `migrations.parquet` | 5,701 | 1 row per graduation event |

**5,689 tokens graduated** across the window (0.71% of all launches) — and
the graduation rate itself is a rich signal, climbing roughly **900x** over
the 39 days as the platform's usage grew, giving you a genuine
non-stationary time series to model, not a static snapshot.

## What You Can Build With This

- **Rug-risk and fraud detection** — holder concentration, creator history,
  and bonding-curve dynamics, joined against confirmed outcome labels
  (`rug_detected`, `outcome_label`).
- **Launch-time success prediction** — every token's first seconds of
  bonding-curve activity, at 15-second granularity, paired with what
  actually happened.
- **Memecoin market microstructure research** — buy pressure, wallet
  concentration, trade intensity, and curve-depletion velocity, all
  computed at the trade level, not just aggregated daily bars.
- **Creator and wallet behavior studies** — every wallet's full trade
  history across the corpus, cross-referenced against which tokens they
  created vs. traded.
- **Regime and non-stationarity research** — a real 39-day window with
  multiple confirmed, dated platform-level shifts baked in (see
  `KNOWN_ISSUES.md`), useful precisely *because* it isn't artificially
  stationary.

## Why This, Not Just On-Chain Data Directly

Raw Solana on-chain data is technically public to anyone with RPC access —
what isn't public is the work of turning 33 million individual transactions
into a clean, joined, labeled research corpus. That work is the actual
value here:

1. **Bonding-curve-phase granularity**, not just post-graduation trading —
   most public feeds start coverage after graduation, missing the entire
   phase where most of the interesting launch-time signal lives.
2. **Labeled graduation outcomes**, computed and validated, not a raw price
   history you have to label yourself.
3. **A fully quantified data-quality audit** — every contamination source
   below was found by directly querying this exact corpus, with exact row
   counts, root causes (where determinable), and a documented handling
   rule. Most public datasets don't tell you what's wrong with them; this
   one does, in detail.

## Quickstart

`quickstart.py` loads the corpus, applies the core data-quality filters,
and computes one example metric (graduation rate by creator experience
tier). Requires only `duckdb`.

```bash
pip install duckdb
python quickstart.py --data-dir /path/to/parquet/files
```

## Files In This Release

- `tokens.parquet` — the corrected token table (mayhem-mode supply bug
  fixed, unfixable suspect rows flagged via `top10_pct_suspect`).
- `trades.parquet`, `snapshots.parquet`, `postgard_snapshots.parquet`,
  `postgard_outcomes.parquet`, `wallet_stats.parquet`, `migrations.parquet`
  — as collected.
- `KNOWN_ISSUES.md` — full data-quality reference, read this first.
- `quickstart.py` — runnable example.

*(A live-state table, `live_token_stats.parquet`, reflects only the
platform's current moment and is not included — it has no meaning as
historical data.)*

## Licensing & Provenance

- Collected via websocket + on-chain RPC polling of Solana, plus
  concentration/holder data from a third-party API. 
- No PII beyond public, pseudonymous on-chain wallet addresses and
  user-submitted token names/symbols. 
- **License**: CC BY 4.0. You are free to use, share, and
  dapt this dataset for any purpose, including commercially, as long as you give appropriate credit — cite this dataset
  (see Citation below) and indicate if changes were made.

---

## Research Built On This Dataset

Three papers are in progress using this corpus, covering distinct research
questions — links and citations will be added as each is finalized:

1. **Rug-risk clustering & survival analysis** — a validated, temporally
   -stable cluster of graduated tokens at elevated rug risk (holder
   concentration + creator history), plus a Cox survival model of
   time-to-rug.
2. **Launch-time graduation prediction** — an ensemble model predicting
   graduation from the first 0–10 minutes of bonding-curve activity,
   evaluated across 100 purged/embargoed cross-validation folds.
3. **Creator economics & memecoin market behavior** — wallet-level evidence
   on who actually profits on pump.fun, graduation-speed effects, and how
   creator experience shapes launch design.

*Citations pending — check back or reach out for preprints.*

## Looking For Higher-Quality, Continuously-Updated Data?

Everything documented in `KNOWN_ISSUES.md` above — the regime breaks, the
`wallet_stats.parquet` staleness, the bounded curve-depletion overshoot —
reflects the real, honest limitations of a fixed 39-day research snapshot.

A **live, daily-refreshed version of this exact dataset format** is in
development — same schema, same six tables, continuously updated rather
than frozen at a point in time, with the issues above resolved at the
source rather than documented after the fact: no stale wallet snapshots,
consistent supply handling across token types from day one, and ongoing
collection-uptime monitoring instead of a one-off outage discovered in
hindsight. **This will be a paid service**, aimed at teams that need
current, production-grade pump.fun data rather than a fixed historical
research corpus. Details TBD — reach out for early access.

## Citation

```
Slink Dev (slink21taken). PumpFun Launch Corpus. 2026.
Research papers will be released later on.
```