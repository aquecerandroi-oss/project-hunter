# Brief T3.46d — o livro de ofertas chega "do futuro": 97,7 % das leituras de `orderbook_imbalance_20` e `spread_pct` são recusadas por `after_cut` (o snapshot do livro carrega o relógio da exchange e fica +2 a +400 ms à frente de `covered_until`) — Liquidity e Order Flow do score nunca têm dado, e a baseline do livro nunca matura

**Owner:** exchange-integration-specialist (owns `services/market-worker` and coverage). **Reviewer afterwards:** code-reviewer + quant-engineer (a one-paragraph opinion on the non-anticipation argument). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation (max 2); the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only (Redis `hgetall`, SQL in `repeatable read read only`, `docker logs`).** Base: `main` at HEAD. Scope: `services/market-worker/hunter_market_worker/**` (coverage / `covered_until` stamping, order-book snapshot writer), `packages/indicators/hunter_indicators/features/**` only if a declared tolerance is the chosen fix, tests, `docs/PIPELINE.md` §1/§2 (one paragraph), `.claude/state/notes-T3.46d.md`.

## Facts (T3.46b, `.claude/state/notes-T3.46b.md` §1 and the SQL under `infra/scripts/sql/research/2026-09-09-t346b-*.sql`)
- `orderbook_imbalance_20` = `unavailable` in 11 721 of 12 002 reads in one hour (97,7 %), always `after_cut`; 8 paired reads show the book stamp ahead of the cut by +2 … +400 ms in 6 of 8.
- Consequence: baseline `sample_size` max 63 vs gate 120 → 0 of 8 480 buckets usable; `ORDERBOOK_IMBALANCE` can never emit; `spread_pct` falls with it; the score's *Liquidity* and *Order Flow* components are empty → plausibly part of why the opportunity score never passed 38 (T3.46).
- The refusal itself is correct (using a book newer than the cut would be anticipation).

## Deliver
1. **Measure first** (read-only, VPS): the distribution of `book_ts − covered_until` over ≥ 1 000 cycles for 5 markets (p50/p90/p99, sign); where each stamp comes from (exchange event time vs local receive time vs coalescing-cycle time); paste.
2. **Choose and implement one of the two fixes, with the non-anticipation argument written down**: (a) stamp `covered_until` after the book write in the same coalescing cycle, so the book that is visible at the cut is the one the cut declares; or (b) a declared tolerance for book features (like the ATR checkpoint already has), bounded (e.g. ≤ 500 ms) and recorded in the feature envelope as `tolerance_ms`, never silently. State why the chosen one cannot let a strategy see data from after its decision bar (`source_bar_close` is minute-aligned; the book is intra-minute).
3. Tests: the race reproduced in a unit test (book stamped 150 ms after the cut → today refused; after the fix, accepted under the declared rule) and one testcontainer test on the coverage path.
4. After the orchestrator deploys: the `unavailable/after_cut` ratio for `orderbook_imbalance_20` over one hour must fall from 97,7 % to < 5 % — the proof; paste before/after.

## Prove
Tests per file, `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; `.claude/state/notes-T3.46d.md`. Times in Brasília (UTC−3) with UTC as detail.
