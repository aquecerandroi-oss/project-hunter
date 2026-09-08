# Brief T3.43 — o Lab ganha regime: um produtor horário de `market_regimes` (tendência do BTC, volatilidade realizada, amplitude do universo, funding médio) para que toda avaliação possa ser cortada por contexto

**Owner:** quant-engineer (indicator + scanner job). **Reviewers afterwards:** code-reviewer; Astra on the definitions. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only.** Base: `main` at `7b0edeb`. Scope: `packages/indicators/hunter_indicators/regime/**` (new), `services/scanner-worker/hunter_scanner_worker/regime*.py` (new job next to `beta_job.py`), `packages/core/hunter_core/db/models/market_regimes.py` (read; if a column is missing → brief for database-architect, no migration here), tests, `docs/PIPELINE.md` §2.

## Why
Every evaluation today lacks the regime split (Astra's C4, T3.32 "não é BTC", T3.33e/g "market_regimes tem 1 linha"). The crypto-regime model in `.claude/skills/` references (6 components) is the inspiration; we use only data we have: BTC 1 h closes (trend structure: price vs SMA50/SMA200 of hours, slope), realised vol percentile (24 h), breadth (% of monitored markets above their 24 h SMA and with positive 24 h return), average funding across the β universe, drawdown from 30-day high.

## Deliver
1. `hunter_indicators.regime`: pure functions over Decimal series producing a `RegimeSnapshot(ts, trend: up|down|flat, vol_regime: low|normal|high, breadth_pct, funding_avg, drawdown_pct, score_0_100)` with declared thresholds (no magic numbers without a comment), no look-ahead (only closed hours), unit tests with synthetic series.
2. Scanner job `regime_job.py` hourly (same scheduling as `beta_job.py`): writes one `market_regimes` row per hour for the exchange (idempotent on `(exchange, ts)`), backfills the last 31 days on first run from stored candles/funding (so the replay evaluations can be cut by regime), heartbeat field `regime_last_ts`.
3. `replay.stress` and the research SQL get a regime join: `infra/scripts/sql/research/2026-09-09-regime-split.sql` that splits any cohort's outcomes by `trend × vol_regime` — run it read-only on the VPS **after** the job has backfilled (the orchestrator deploys; you paste the query and, if the deploy happens during your task, the result).
4. Tests: indicator units; job integration (testcontainers) with seeded candles → rows; idempotency; backfill window.
5. `docs/PIPELINE.md` §2 (what regime is, thresholds, how to read).

## Prove
Per-file tests with real output, `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; `.claude/state/notes-T3.43.md`.
