# Brief T3.26c — a variante não pode mentir sobre si mesma: guarda estrutural na ativação, faixa dos overrides, isolamento por versão no loop (revisão risk-engine-guardian de be3674a, A1–A5)

**Owner:** quant-engineer. **Reviewers afterwards:** risk-engine-guardian (re-check A1–A3), code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation, one at a time; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`; do not stop or recreate local stack containers.** Base: `main` at `3ca215e` or later. T3.18c edits `services/strategy-worker/hunter_strategy_worker/replication*.py` — disjoint from your files; check `git status` first. Your scope: `infra/scripts/{derive_variant,activate_strategy_version}.py`, `services/strategy-worker/hunter_strategy_worker/{activate_derived,consumer,catalogue,paper_line}.py`, `packages/core/hunter_core/strategies/schema.py`, `infra/scripts/obsidian_strategy_pages.py`, their tests, `docs/ACTIVATION.md`.

## Source
`.claude/state/review-T3.26-risk.md` (A1 ALTA, A2/A3 MÉDIA, A4/A5 BAIXA).

## Deliver
- **A1 (structural guard)**: in the research route of `activate_strategy_version.py`, refuse when the draft already carries non-empty `default_parameters` different from the code's canonical set (drafts from `seed.py` are empty, so no legitimate activation breaks); the `_DERIVED` regex stays only as a fast path. Test: a derived draft whose changelog was edited (lineage removed) is still refused by the research route and accepted by the derived route.
- **A2 (range validation)**: `derive_variant.py` refuses a negative value where the parent's is positive, refuses params that cannot build valid `AssumedCosts`/`Invalidation` (dry validation constructing the strategy's typed objects from the merged params), refuses declared inversions such as `atr_pct_min >= atr_pct_max` (a small per-strategy `constraints` table in `schema.py`). Tests for the probe cases in the review.
- **A3 (loop isolation)**: `consumer.py:123` — per-version try/except with a counter `shadow_version_failed_total{strategy_key,version}` and a log; other versions still evaluate and the message is acked. `catalogue.load_version_roster` orders versions numerically (v10 after v3) and paper before research so the paper line is evaluated first. Tests.
- **A4**: `activate_derived.record_event` carries `derived_from`, `params_hash`, the preserved changelog.
- **A5**: `obsidian_strategy_pages.py` — `derived_from` takes precedence over `succeeds`.
- **Docs**: `docs/ACTIVATION.md` §7 gets the derive step with the exact VPS command form (`docker exec -i hunter-api-1 python - ... < infra/scripts/derive_variant.py` until the image has it) and the warning that the image script must be at or after this commit.
- **Policy (not code)**: write in the notes the D10 gap (a derived variant of `volume_anomaly` could become its paper line without prospective evidence) for the orchestrator to put to Everton; do not change `paper_line.py` beyond a comment.

## Prove
Per-file tests with real output; `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; `.claude/state/notes-T3.26.md` section "T3.26c".
