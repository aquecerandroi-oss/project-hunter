# Brief T3.44e — o "tempo real interrompido" do topbar tem causa medida: o servidor fecha por ociosidade (4409, 15 min) todo socket passivo, e o topbar é passivo — a aba visível passa a mandar um `ping` de cliente (que o servidor conta como atividade) a cada 5 min

**Owner:** frontend-specialist. **Reviewer afterwards:** code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; no testcontainers; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard blocks); add exact files only; do not touch `.env*`; do not stop or recreate local stack containers; VPS read-only. Build on the uncommitted T3.44d diff in `apps/web/lib/ws.ts` / `lib/realtime-health.ts` / `components/system/live-status.tsx` (read `git diff` first; do not undo it).** Base: `main` at `9ff2d47`. Scope: `apps/web/lib/ws.ts`, `apps/web/lib/realtime-health.ts`, `apps/web/tests/ws.test.ts`, docs line in `docs/PIPELINE.md` or `docs/ARCHITECTURE.md` where the WS protocol is described (one paragraph), `.claude/state/notes-T3.44d.md` (append "T3.44e").

## Evidence (VPS `hunter-api-1`, last 60 min at 2026-09-08 23:06Z)
```
      3 "code": 1001
      1 "code": 1005
     10 "code": 4409   ← {"reason": "idle timeout", "client": "187.101.9.196", "authenticated": true, "duration_ms": 905013 / 963519}
```
Server side (`apps/api/hunter_api/realtime/session.py:43` `IDLE_TIMEOUT_SECONDS = 15*60`; `endpoint.py:241-249`): a server `ping`→client `pong` deliberately does **not** count as activity; a client-initiated frame (`ping`, `subscribe`, `unsubscribe`) calls `session.mark_frame()` and resets the idle clock. The topbar socket only receives, so it dies every 15 min by design and the client reconnects with backoff — that is the "tempo real do navegador interrompido" Everton sees. The server policy is right for abandoned tabs; the client must say "someone is looking".

## Deliver
1. `RealtimeClient`: while `document.visibilityState === "visible"` and the socket is open and authenticated, send `{"type":"ping"}` every `KEEPALIVE_MS = 5 * 60_000` (jitter ±10 s); pause while hidden (a hidden tab should time out — intended); send one immediately on `visibilitychange` to visible if the last activity is older than 5 min; clear the timer on close. The server answers `pong`; ignore it (no double handling with T3.44d's pong logic — the server pong is `{"type":"pong"}`, distinct from the server `ping`).
2. `deriveConnectionHealth`: a 4409 close followed by a successful reconnect inside the grace stays "ao vivo"; the tooltip names the reason "encerrado por ociosidade (15 min)" when it was the last close.
3. Tests: fake timers — visible tab sends a ping at 5 min, hidden tab sends none, visibility flip sends one, timer cleared on close; no double pong.
4. Proof after the orchestrator deploys: VPS `ws_closed` code histogram for 60 min with the page open in Everton's browser (read-only `docker logs`) — 4409 count must drop to zero for visible tabs; paste before/after.

## Prove
`pnpm --filter web lint|typecheck|test`; report in Portuguese, extended format; exact file list.
