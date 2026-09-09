# Brief T3.46f — a T3.46d fechou a corrida do lado do carimbo e o livro continua "após o corte" em ~89 % (178/200 mercados) — o resíduo é a ORDEM DE LEITURA do scanner: ele lê `covered_until` primeiro e o livro depois; um livro que atualiza 5–10×/s quase sempre já andou. Ler o snapshot primeiro e o corte depois (ou reler o corte após o snapshot) fecha o resíduo sem tolerância e sem antecipação

**Owner:** quant-engineer (owns `services/scanner-worker` and `hunter_indicators.features`). **Reviewer afterwards:** code-reviewer with the same two hats as T3.46d (code + non-anticipation). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation (max 2); the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only (Redis `hgetall`/`hget`, SQL in `repeatable read read only`, `docker logs`).** Base: `main` at HEAD (VPS market-workers = `2b7cef9` with T3.46d; scanner = `09b8fa6`). Scope: `services/scanner-worker/hunter_scanner_worker/**` (the per-market evaluation read path: hot state / coverage read), `packages/indicators/hunter_indicators/features/{context.py,hotstate.py}` only if the read helper lives there, tests, `docs/PIPELINE.md` §2 (one paragraph), `.claude/state/notes-T3.46f.md`.

## Evidence after the T3.46d deploy (scanner heartbeat, 2026-09-08 22:5x BRT)
```
ANTES  (market-workers antigos): ORDERBOOK_IMBALANCE:feature_after_cut=134  (de 134 avaliados)
DEPOIS (2b7cef9, +1..+3 min):     feature_after_cut=178/174/184 · baseline_absent=4 · baselines_under_construction=18/22/12  (de 200)
```
`covered_until` now equals the ts of the last accepted event (`observe_proof`, stamped by the 100 ms housekeeping loop). The scanner still reads the cut first and the book second; a liquid perp's book advances between the two reads, so `book.ts > as_of` most of the time. Reading the book snapshot first and the cut second inverts the race: the cut (proof of everything accepted, book included) is then ≥ the snapshot ts with high probability, and anything still ahead is refused as today.

## Deliver
1. **Read the current read path** and paste it: where `as_of`/`covered_until` is read, where the book/ticker/tape snapshots are read, in which order, and whether the features are computed against `as_of` (they must stay so).
2. **Fix by ordering, not tolerance**: take the hot-state snapshots first, then read `covered_until` and use it as `as_of` (or re-read it after the snapshots and take the later value); every snapshot with `ts > as_of` keeps being refused exactly as today (`MarketContext.__post_init__`/`decode_book` untouched). Write the non-anticipation argument: `as_of` is still a published proof of accepted data, read AFTER the data it is compared with, so no snapshot can be newer than the cut except by a genuine race, which is refused; `source_bar_close` is minute-aligned and unaffected.
3. Tests: unit test of the read order with a fake hot state whose book advances between reads (today: `after_cut`; after: accepted); one testcontainer test on the scanner evaluation path if one exists for hot-state reads.
4. After the orchestrator deploys the scanner: the heartbeat `ORDERBOOK_IMBALANCE:feature_after_cut` count must fall from ~178/200 to < 10/200 within 5 minutes — paste before/after; and the `spread_pct`/`orderbook_imbalance_20` availability from `feature_snapshots` over 30 min (read-only SQL).

## Prove
Tests per file, `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; `.claude/state/notes-T3.46f.md`. Times in Brasília (UTC−3) with UTC as detail.
