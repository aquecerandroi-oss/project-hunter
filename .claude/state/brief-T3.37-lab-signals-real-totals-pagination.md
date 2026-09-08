# Brief T3.37 — the Lab signals table shows the real totals and pages through everything (Everton, 2026-09-08: "se tiver 2 mil operações tem que paginar mas mostrar as 2 mil"; "essa parte do Lab sem nenhum BO")

**Owners:** T3.37a backend-specialist (API), T3.37b frontend-specialist (web) — two agents, one contract, this brief. **Reviewers afterwards:** code-reviewer (both), product-designer (screen). **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation, one at a time; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`; do not stop or recreate local stack containers.** Base: `main` at `953d371`. In flight: T3.18c (`apps/api/hunter_api/{repositories,services,schemas,routers}/lab_replication.py`, `lab_scoreboard*.py`, `lab_curve.py` — **T3.37a must not edit those**; signals live in `lab_signals*.py`/`lab.py`), T3.31 (`apps/web/components/lab/lab-curve-chart.tsx`, `components/markets/candles-chart.tsx`, `components/portfolio/portfolio-equity-chart.tsx` — **T3.37b must not edit those**).

## Measured (VPS, 2026-09-08 15:20 Brasília, Everton's screenshot)
Tabs read "Concluídas (131) · Abertas (67) · Pendentes/sem entrada (2) · Todas (200)". Those are counts **within the 200 rows the page loaded**, not the dataset: the Lab has thousands of signals (momentum v1 alone 929 evaluable). Clicking "Concluídas" filters the 200 loaded rows client-side, so a user never sees concluded operations beyond the newest 200 signals. "Load more" appends but the counters stay wrong.

## Contract (T3.37a implements, T3.37b consumes)
`GET /api/v1/lab/shadow/signals` keeps its filters (`cohort`, `version`, `window`) and gains:
- `state=closed|open|pending|all` (default `all`) — server-side segment filter with the **same definitions as the web's `lab-signal-segments.ts`** (closed = terminal outcome with R known; open = entered, tracking; pending = no entry / waiting / censored-not-evaluable — read the web file and mirror it in SQL; write the mapping in the notes);
- `page_size` (50 | 100 | 200 | 500, default 200) and `cursor` (opaque, keyset on `(emitted_at DESC, id DESC)`) — never OFFSET on large sets;
- response: `items`, `next_cursor`, and **`totals: {closed, open, pending, all}` computed over the whole filtered dataset (cohort/version/window applied, state not applied)** so the tabs show real numbers; plus `page: {from, to}` (1-based positions in the current state's ordering) so the web can print "1–200 de 2 135".
- Indexes: check `EXPLAIN` for the totals query on the VPS-sized table (`agent_signals` + outcomes); if a partial index is needed, write the brief for database-architect (do not edit migrations). Unit + integration tests (testcontainers): totals independent of page, cursor stability under new inserts, state filter definitions (one fixture per state).
- `pnpm gen:types` regenerated.

## Web (T3.37b)
- `lab-segment-tabs.tsx` shows `totals.*` (real), `aria-live` on change; tabs change `state` in the URL (`?state=closed`) and refetch server-side — no client-side filtering of a partial page.
- Pager below the table: "1–200 de 2 135 · página 1" with "Próxima"/"Anterior" (cursor stack in URL or state), page-size select (50/100/200/500), and the existing "Carregar mais" removed or turned into "Próxima". Keyboard reachable; loading and error states with `SectionUnavailable`.
- Totals card ("Resultado das operações desta página (200)") gets an explicit scope switch: **"desta página" | "de todas as concluídas"** — the second uses the summary endpoint for the same filters (it exists: `/lab/shadow/summary`), never a client sum of a page. Copy: D16/D17/D19.
- Tests: tabs render totals from a fixture; clicking a tab changes the query, not the array; pager math; scope switch.
- Screen proof: `bash .claude/state/tmp/run-design-audit.sh -g "lab"` after the orchestrator rebuilds `docker-web-1` (ask), plus a capture of "Concluídas" showing a count > 200 on the VPS is the orchestrator's job after deploy.

## Prove
Per-file tests with real output; `ruff`/`pyright`/`check_file_size.py` (api); `pnpm --filter web lint|typecheck|test` (web); reports in Portuguese, extended format; `.claude/state/notes-T3.37.md` (both append their section).
