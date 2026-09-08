# Brief T3.22 — every time on screen is Brasília time (America/Sao_Paulo); UTC becomes the detail

**Owner:** frontend-specialist (+ one API field if needed). **Reviewers afterwards:** product-designer (rendered screens), code-reviewer. **Do not commit.** **Operational rule: never a background shell; foreground commands with a timeout <= 5 min; testcontainers one file per pytest invocation, one at a time; the tree is shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only; do not touch `.env*`.** Dispatch **after** T3.18 web lands (it edits `apps/web/components/lab/**`).

## Everton's ask (2026-09-08, verbatim)
"o horario ta errado sou de sao paulo intao horario tem que ser de brasilia". Today the screens print UTC first and the local time in parentheses (`04:20:41 UTC (01:20:41 -03:00)`, `08/09 05:05 UTC`). He reads that as wrong.

## Rules (CLAUDE.md: storage and APIs stay UTC; only the display changes)
1. **One display timezone for the organization**: `America/Sao_Paulo`, defined in one place (`apps/web/lib/time.ts` or the existing formatter module — `formatUtc`, `formatLocalOffset`, `formatUtcWithOffset`, `formatWhenShort` in `apps/web/lib/format.ts` and `components/lab/lab-format.ts`). Never the viewer's browser timezone (a viewer abroad still sees Brasília, because the wallet's day is Brasília). If an organization setting for timezone already exists in the API, read it; otherwise hardcode the constant with a comment and a TODO for the org setting — do not add a migration.
2. **Primary text = Brasília**, formatted Brazilian: `08/09 02:05` (short), `08/09/2026 02:05:05` (long), with the suffix `BRT` only where ambiguity matters (tables of times keep it out of every cell and put it once in the column header: "Quando (Brasília)"). **UTC in the tooltip/`title`** and in copyable ISO form.
3. **Dates that are days** (the kill-switch day, the daily reference, "Dia (America/Sao_Paulo)") stay as they are; make the label say "Brasília" in plain Portuguese instead of the IANA name.
4. **Every screen**: Carteira (Consultado em, câmbio de abertura/atual, pico observado em, curva), Lab (Quando, Entrou, Saiu, as_of label, totals), Radar, Markets (staleness badges are ages, unchanged; the detail view's timestamps change), System (heartbeat times, last MTM, last protection, backfill), Sinais/Oportunidades detail. Grep for `UTC` and for the formatters to find them all; list every call site in the notes.
5. **Ages and relative times** ("há 12 s", "atrasado 1min") do not change (T3.16 server clock stays).
6. **Charts**: x-axis ticks in Brasília; tooltip shows Brasília and UTC.
7. **Tests**: the formatters with a fixed instant across the DST-free Brazilian year (Brazil has no DST since 2019 — say so in a comment), a midnight-crossing case (23:30 UTC = 20:30 Brasília same day; 02:30 UTC = 23:30 previous day), the header label, tooltips; snapshot-free assertions. `pnpm --filter web lint|typecheck|test`.
8. **Copy**: "Brasília" (not "São Paulo", not "BRT" in prose), "UTC" only in tooltips and the System page operator details.

## Prove
Report in Portuguese, extended format (STATUS · FILES · every call site changed · TESTS with real output · what the screen shows · CONCERNS); `.claude/state/notes-T3.22.md`.
