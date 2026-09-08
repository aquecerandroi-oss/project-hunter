# Brief T3.18d — um veredito, uma função: `compute_verdict` passa a chamar `profit_factor_passes`/`scoreboard_verdict` do pacote puro; teste do placar com R nulo após o portão

**Owner:** backend-specialist. **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers.** Base: `main` at `2df9f67`. Scope: `apps/api/hunter_api/services/lab_scoreboard_metrics.py`, `lab_scoreboard.py`, `apps/api/tests/unit/**`, `apps/api/tests/integration/test_lab_scoreboard_api.py`, `packages/indicators/hunter_indicators/replication/stats.py` (read; extend only if a helper is missing).

## Source
Review of T3.18c (`c8c9dc6`): "Duplicação remanescente do veredito — `lab_scoreboard_metrics.py:51-81` (`compute_verdict`) and `replication/stats.py:230-243` (`scoreboard_verdict`/`profit_factor_passes`) implement the same rule in two packages; agreement is by test vigilance, not by construction" and "falta um teste que semeie explicitamente uma linha terminal, horizonte vencido, `r_multiple IS NULL` e prove que ela não conta nem para `evaluable` nem para `maturity.days` no placar isoladamente".

## Deliver
1. `compute_verdict` delegates to the pure package (`hunter_indicators.replication.stats.scoreboard_verdict` or a shared helper you extract there), keeping the API's output shape and reasons byte-identical (assert with the existing tests; add a parametrised test over the borderline cases: PF null with `sem_perdas`, PF exactly 1, only losses, mature vs immature).
2. Integration test in `test_lab_scoreboard_api.py`: a seeded terminal outcome past its horizon with `r_multiple IS NULL` (funding not resolvable) is excluded from `evaluable` and from `maturity.days`.
3. Notes: `.claude/state/notes-T3.18.md` section "T3.18d".

## Prove
Per-file tests with real output, `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format.
