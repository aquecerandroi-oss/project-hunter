# Brief T3.46b — três detectores do Radar produzem zero sem motivo declarado (`ORDERBOOK_IMBALANCE`, `OPEN_INTEREST_SPIKE`, `TRADE_VELOCITY_SPIKE`): silêncio sem motivo é defeito; ou produzem, ou aparecem em `detectors_disarmed` com a razão

**Owner:** quant-engineer (owns `services/scanner-worker`). **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation (max 2 files in this task); the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only (`docker logs`, heartbeat `redis-cli hgetall hb:scanner:*`, SQL in `repeatable read read only`).** Base: `main` at HEAD (scanner on the VPS = `7e9d59c`). Scope: `services/scanner-worker/hunter_scanner_worker/**` (detectors, health/heartbeat `detectors_disarmed`), `packages/indicators/hunter_indicators/anomalies/**` if the detector logic lives there, tests, `docs/PIPELINE.md` §3 (one paragraph), `.claude/state/notes-T3.46b.md`.

## Facts (T3.46, `.claude/state/notes-T3.46.md`)
```
detectors_disarmed = CROSS_EXCHANGE_DIVERGENCE:single_exchange_until_m1b=200, FUNDING_ANOMALY:funding_unavailable=200, LIQUIDATION_CLUSTER:feature_not_implemented=200
rows 31 d: VOLUME_SPIKE 580 | MOMENTUM_SHIFT 335 | PRICE_ACCELERATION 331 | VOLATILITY_EXPANSION 48 | ORDERBOOK_IMBALANCE 0 | OPEN_INTEREST_SPIKE 0 | TRADE_VELOCITY_SPIKE 0 | SOCIAL_SPIKE 0 | WHALE_ACTIVITY 0
```
`SOCIAL_SPIKE`/`WHALE_ACTIVITY` have no feature by design (say so in the heartbeat too, `feature_not_implemented`). The three named ones have features in the pipeline (order book, OI, trade velocity — check `docs/PIPELINE.md` §2–3 and the feature calculators) but never emit.

## Deliver
1. **Diagnosis with evidence** per detector: is the feature computed (sample the last hour of `feature_snapshots`/heartbeat fields on the VPS, read-only), is the detector wired, what threshold/baseline gate blocks it (e.g. baselines under construction, `sample_size` gate, a unit mismatch, a missing `NormalizedTrade` stream on spot). Paste numbers.
2. **Fix**: either the detector emits on real data (prove with a testcontainer test on a realistic series and, after the orchestrator deploys, a count on the VPS) or the heartbeat declares the reason in `detectors_disarmed` (`baselines_under_construction`, `feature_unavailable_on_spot`, `no_orderbook_stream`…) — never silent. The Radar coverage strip (T3.46c) already renders "silencioso sem motivo" vs "desarmado: motivo"; after this task no detector may be in the first class.
3. Also the `markets.is_monitored = 217` vs heartbeat `markets = 200` divergence (T3.46 concern 7): find the 17 and say why (planned exchange? eligibility? cap?). One paragraph, fix only if it is a one-liner.

## Prove
Tests (per file), `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; `.claude/state/notes-T3.46b.md`. Times in Brasília (UTC−3) with UTC as detail.
