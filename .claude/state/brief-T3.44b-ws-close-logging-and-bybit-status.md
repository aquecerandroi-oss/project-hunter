# Brief T3.44b — o gateway WS loga todo fechamento (4401 sem log foi o que escondeu o bug do topbar por dias) e a Bybit deixa de contar como exchange "UNAVAILABLE" enquanto não tem coletor

**Owner:** backend-specialist. **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only.** Base: `main` at `8770ff4`. Scope: `apps/api/hunter_api/realtime/endpoint.py` (+ tests), `apps/api/hunter_api/services/system_status.py` (+ tests), `infra/scripts/seed_reference.py` (exchanges), `apps/web/components/system/live-status.tsx` **read only** (say what the UI should show; the web change, if any, is a one-liner you list for the orchestrator), `docs/PIPELINE.md` §1.

## Source
`.claude/state/notes-T3.44.md`: (1) `realtime/endpoint.py:226-232` closes with `4401 "authentication required"` **without a log line** when the auth frame lacks a string token — the browser's stream died in ~1,8 s for days and nothing in the API said so; (2) `exchanges` has `bybit` with `status=active` but no worker ever ran for it, so `system_status.py:270-309` honestly reports `ws_state=unavailable` and the topbar reads "2 exchanges · UNAVAILABLE".

## Deliver
1. Every WS close initiated by the gateway logs one structured line (`ws_closed code=… reason=… client=… authenticated=bool duration_ms=…`), rate-limited per client if needed (the T3.28 buckets), plus a counter `hunter_ws_closed_total{code}`; tests for 4401 (no token / bad token), 4403, normal close.
2. Bybit: the catalogue marks it `planned` (`seed_reference.py`; `seed.py --only exchanges` is the operator's command — write it in the notes) and `system_status.py` excludes `planned` exchanges from the aggregate and lists them separately (`exchanges_planned: ["bybit"]`) so the topbar counts only exchanges with a collector; schema addition is additive (`pnpm gen:types`); tests. If `exchanges.status` has no `planned` value in its CHECK/enum, say so and brief the database-architect instead of editing migrations.
3. Notes for the web: the exact one-liner for `live-status.tsx` to read "1 exchange · CONNECTED · N mercados (bybit planejada)".

## Prove
Per-file tests with real output, `ruff`/`pyright`/`check_file_size.py`; report in Portuguese, extended format; append "T3.44b" to `.claude/state/notes-T3.44.md`.
