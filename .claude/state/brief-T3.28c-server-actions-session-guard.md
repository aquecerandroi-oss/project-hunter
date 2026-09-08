# Brief T3.28c — Server Actions públicas não podem gastar o balde interno da API sem sessão (security-reviewer, T3.28a achado 1, MEDIUM)

**Owner:** frontend-specialist. **Reviewers afterwards:** security-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`; do not stop or recreate local stack containers.** Base: `main` at `3ca215e` or later. In flight elsewhere: T3.24b (`apps/web/components/lab/**`, `app/(app)/[orgSlug]/lab/**`, `lib/api/lab.ts`), T3.28b (`app/**/layout.tsx`, `app/global-error.tsx`, `components/shell/**`) — do not edit those. Your scope: `apps/web/lib/api/{organizations,workspaces,members,invitations}-actions.ts` (and any other `*-actions.ts` without a session guard), `apps/web/lib/server/session.ts` (read; add a helper next to it), `apps/web/tests/actions-*.test.ts`, `docs/SECURITY.md` §5 (one line).

## Finding
`organizations-actions.ts:24`, `workspaces-actions.ts:29`, `members-actions.ts`, `invitations-actions.ts` call `apiFetch` without `getServerSession()`; `/` is public in `middleware.ts`, so an unauthenticated POST carrying a `Next-Action` id reaches the API (answered 401) but is charged to the web peer's bucket (6 000/min after T3.28a): an unauthenticated caller can exhaust the site's SSR budget. The correct pattern already exists in `markets-actions.ts:44-46`.

## Deliver
1. Every Server Action checks the session first and returns the same typed error the markets actions return when there is none (no fetch, no API call).
2. A shared helper `requireSession()` in `lib/server/` used by all actions (keep `markets-actions.ts` behaviour identical).
3. Tests: each action with no session → no `apiFetch` call (mock) and the typed error; with session → unchanged.
4. `docs/SECURITY.md` §5: "Server Actions verificam a sessão antes de qualquer chamada à API".

## Prove
`pnpm --filter web lint|typecheck|test` with real output; report in Portuguese, extended format; `.claude/state/notes-T3.28c.md`.
