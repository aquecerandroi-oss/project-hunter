# Brief T3.46g — os últimos ~43 pontos do "livro após o corte" moram no market-worker: (a) o carimbo de cobertura sai do laço de housekeeping (fase livre de 250 ms contra o `coalesce_loop` que grava o livro) e passa a ser escrito no MESMO pipeline do `flush_ticks`, depois das escritas de livro; (b) o scanner lê o `until` do shard dono do símbolo (`mkt:binance:coverage:shards`, já existe) em vez do `min` global dos 4 shards (dispersão p50 283 ms, p90 727 ms)

**Owner:** exchange-integration-specialist for (a) + quant-engineer for (b) — ONE agent (exchange-integration-specialist) does both, because (b) is a read-side change of 10–20 lines in `services/scanner-worker/hunter_scanner_worker/coverage.py` (`read_coverage`/`refreshed_cut`, T3.46f) and the two must be measured together. **Reviewer afterwards:** code-reviewer (code + non-anticipation). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation (max 3 in this task); the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only.** Base: `main` at HEAD **after the orchestrator commits T3.46f** (read `git log -1 -- services/scanner-worker/hunter_scanner_worker/context.py` to confirm; if T3.46f is still uncommitted in the tree, build on the tree state and say so). Scope: `services/market-worker/hunter_market_worker/{streaming.py, coalesce.py (or wherever flush_ticks/book writes live), coverage.py (350/350 — free lines before adding)}`, `services/scanner-worker/hunter_scanner_worker/coverage.py` (+ `context.py` only if the signature must change), tests in both services, `docs/PIPELINE.md` §1–2 (one paragraph), `.claude/state/notes-T3.46g.md`.

## Facts (T3.46f, `.claude/state/notes-T3.46f.md` §2, VPS 23:10–23:41 BRT)
```
after_cut with cut read right before the book:  43.2 % (OLD order) / 42.6 % (NEW order)   ← the residue this brief closes
BTC: after_cut vs global min = 53.9 %  vs own shard = 25.7 %     ETH: 51.3 % vs 21.3 %
shard dispersion of `until`: p50 283 ms, p90 727 ms
coalesce_loop writes the book every 250 ms; housekeeping stamps every 0.25 s (COVERAGE_STAMP_S) — no causal order between them
```

## Deliver
1. **(a) Stamp after the writes**: in the same coalescing/flush pipeline that writes the book/ticker/trades for a cycle, append the coverage stamp (`covered_until` = proof of the events just written, per T3.46d `observe_proof`) so that a reader who sees the book also sees a cut ≥ its ts. Keep the housekeeping stamp as the fallback for quiet shards (no events → the margin-based stamp keeps the clock honest). Prove with the T3.46e-style integration test: after one flush, `covered_until` in Redis ≥ the book ts written in that flush, always.
2. **(b) Owning shard's `until`**: the scanner's refreshed cut for a symbol uses the `until` of the shard that owns that symbol (the mapping is already published in `mkt:binance:coverage:shards`); the global `min` remains the default for anything not mapped and for the top-of-cycle read. Non-anticipation argument: a shard's `until` is that shard's own proof; a symbol never reads a cut from data it does not have. Tests: symbol on a lagging shard keeps the lagging cut; symbol on a fresh shard gets the fresh cut; unmapped symbol → global min.
3. Measure before/after on the VPS after the orchestrator deploys (heartbeat `ORDERBOOK_IMBALANCE:feature_after_cut` and the 30-min SQL of `pct_ok` for `orderbook_imbalance_20`/`spread_pct`); the target is `after_cut` < 10/200 and `pct_ok` > 80 %.

## Prove
Tests per file, `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; `.claude/state/notes-T3.46g.md`. Times in Brasília (UTC−3) with UTC as detail.

## Reserva da revisão da T3.46f (obrigatória para (b))
Antes de ler o `until` do shard dono, provar que o mapeamento símbolo→shard usado pelo scanner é sempre correto e atualizado (fonte única publicada pelo coletor, com versão/timestamp; símbolo migrado ou rebalanceado cai para o `min` global). Ler a prova do shard errado seria antecipação de verdade (prova de outro fluxo justificando dado deste). Teste explícito desse caso.
