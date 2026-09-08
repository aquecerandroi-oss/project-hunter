# Brief T3.44d — o tempo real do topbar: a evidência da VPS diz que é o CLIENTE que fecha (1005, autenticado, 3,5 s e 101 s); achar o que fecha no navegador e deixar o status honesto e estável

**Owner:** frontend-specialist. **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; no testcontainers; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only (`docker logs`).** Base: `main` at `2e39774` (deployed on the VPS). Scope: `apps/web/hooks/useRealtime.ts`, `apps/web/lib/realtime/**` (the client), `apps/web/components/system/live-status.tsx`, `apps/web/components/**/topbar*`, tests (Vitest), Playwright check.

## Evidence (VPS `hunter-api-1`, T3.44b logging, 2026-09-08)
```
{"code": 1005, "reason": "client disconnected", "client": "187.101.9.196", "authenticated": true, "duration_ms": 3515,   "timestamp": "2026-09-08T22:17:08Z"}
{"code": 1005, "reason": "client disconnected", "client": "187.101.9.196", "authenticated": true, "duration_ms": 101773, "timestamp": "2026-09-08T22:18:51Z"}
```
The server accepted and authenticated both sockets; the browser closed them without a status code. Candidates to test, in order: (1) the Clerk token refresh (~60–100 s) tears the client down and reconnects — during the gap the topbar shows "tempo real do navegador interrompido" and may never return to "ao vivo" if the status is not re-derived from the new socket (T3.44 fixed a token race; check what remains); (2) route navigation unmounts the provider (a per-page provider instead of a layout-level one); (3) React strict-mode double effect in dev only (not the VPS case); (4) idle/visibility handling.

## Deliver
1. Diagnosis with proof: read the client, reproduce locally with Playwright (Clerk test user; `waitUntil: "load"`, never `networkidle`) logging every `close` with its trigger (stack or a named reason the client passes), over ≥ 3 minutes; paste the log.
2. Fix: the socket survives a token refresh (re-auth in band if the protocol allows, otherwise reconnect without dropping to "interrompido" unless the reconnect fails past a threshold); the status is derived from the live socket, with `since` and the last close reason in the tooltip (D16/D17 copy, Brasília time); the provider lives at the layout level so route changes do not close it. Tests for the state machine.
3. Proof after the orchestrator deploys: Playwright against `https://169.58.116.99` for 5 minutes with the status sampled every 15 s (all "ao vivo" or the exact reasons), and the VPS `ws_closed` count in that window (read-only `docker logs`).

## Prove
`pnpm --filter web lint|typecheck|test`, the Playwright log; report in Portuguese, extended format; `.claude/state/notes-T3.44d.md`.
