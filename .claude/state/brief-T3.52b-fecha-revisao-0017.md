# Brief T3.52b — fecha as ressalvas R2/R4/R5 da revisão do arquiteto sobre a migração 0017 (R1/R3 já aplicadas pelo orquestrador)

**Owner:** the T3.52 quant-engineer (or database-architect). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers max 2 files, one per invocation; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; VPS read-only.** Base: the uncommitted T3.52 tree (read `.claude/state/notes-T3.52.md` and the review text below).

## Ressalvas (database-architect, review of 0017)
- **R2** — the privilege proof is catalog-only (`has_column_privilege`); extend `packages/core/tests/integration/test_schema_privileges.py` (the parametrized "UPDATE as hunter_worker is refused" test, ~lines 985-1019) with `("eligibility_policy", "'{}'::jsonb")` so the column is proven closed AS THE ROLE, not by absence of a grant list; cite it in `docs/DATABASE.md` §29.4.
- **R4** — `classifier_version` in the policy has no closed list (`regime_gate.py:~167`): a typo makes the version enter the roster and refuse every bar as `regime_gate:unknown/no_row` — fail-closed but silent. Fix at write time in `infra/scripts/derive_variant.py`: refuse `--policy` unless at least one `market_regimes` row exists for that (scope, classifier_version) pair (read-only query through the owner DSN the script already has); message names the pair; test in `services/strategy-worker/tests/test_derive_variant.py`. Correct `notes-T3.52.md:38` (it claims a closed list).
- **R5** — `test_migrations.py` (~3127 and ~3256-3272): assert the frozen column list against `_FROZEN_COLUMNS_0017` / `_FROZEN_COLUMNS_0012` exactly (11 vs 10 names), not substrings, and include `replication_index` in the reverted-body assertion.
- **R6 (nit)** — leave as is (`agents.py` at 350 lines), note it.

## Prove
`uv run pytest packages/core/tests/integration/test_schema_privileges.py -q -k eligibility` and `... test_migrations.py -q -k "0017 or 0012"` (two invocations), `services/strategy-worker/tests/test_derive_variant.py -q`; `ruff`/`pyright`; report in Portuguese with exact file list; append "## T3.52b" to `.claude/state/notes-T3.52.md`.
