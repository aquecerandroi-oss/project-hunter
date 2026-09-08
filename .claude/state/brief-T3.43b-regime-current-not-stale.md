# Brief T3.43b — a linha horária de regime (sempre fechada por construção) não pode aparecer como "stale" no tile "Regime atual"; o tile mostra a hora e o score

**Owner:** frontend-specialist (web tile) + the API repository read (`apps/api/hunter_api/repositories/regime*.py`, `services/*regime*`). **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers.** Base: `main` at `f7aed39`. Scope: `apps/api/hunter_api/{repositories,services,schemas,routers}/*regime*`, `apps/web/components/**/regime*`, `apps/web/app/(app)/[orgSlug]/{dashboard,system}/**` (only the tile), tests.

## Source
`.claude/state/notes-T3.43.md` concern 1: `RegimeRepository.current_per_scope` returns the latest row per scope and `is_stale = end_time is not None or not scanner_alive`. Hourly rows from T3.43 are closed (`end_time` set) by construction, so after the scanner deploys the tile "Regime atual" would show `BTC · <rótulo>` with a permanent `stale` badge — honest but reads as a defect. The hourly row also carries the decomposition (score 0–100, components, confidence) that the tile does not show yet.

## Deliver
1. API: `is_stale` for hourly rows = `now − end_time > 2 h` **or** scanner heartbeat `regime_last_ts` older than 2 h; the response gains `as_of` (the hour), `score`, `confidence`, `components` (name, normalized, weight, contribution), `identity` (`regime_hourly_v1…`), additive; `pnpm gen:types`. Unit + one integration test.
2. Web tile: "Regime atual — BTC · ALTA/BAIXA/LATERAL (score 62/100 · confiança 0,8) · hora 15:00 Brasília · atualizado há 12 min"; hover/expand shows the five components with their contribution; `stale` badge only per the new rule; D16/D17/D19 copy. Tests with the real hourly row shape as fixture.
3. Screen proof after the orchestrator rebuilds (`bash .claude/state/tmp/run-design-audit.sh -g "screens 1440 dark"` — dashboard).

## Prove
`pnpm --filter web lint|typecheck|test`, api tests per file, `ruff`/`pyright`; report in Portuguese, extended format; `.claude/state/notes-T3.43b.md`.
