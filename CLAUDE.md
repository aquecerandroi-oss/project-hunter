# PROJECT HUNTER

> Project memory for Claude Code. Short and high-signal. Workflow adapted from the
> vibe-coding-toolkit (https://github.com/soumatheusgomes/vibe-coding-toolkit).
> Human-facing docs are in Portuguese under `docs/`; agent-facing instructions are in English.

**Status:** architecture phase done, committed. Milestone 0 not started. Current milestone lives in `.claude/state/milestone.json`.

## Behavioral guidelines

1. **Think before coding** — state assumptions explicitly. If multiple interpretations exist, present them instead of picking silently. Say so when a simpler approach exists. If something is genuinely unclear, stop and ask.
2. **Simplicity first** — minimum code that solves the problem. No speculative features, no abstractions for single-use code, no unrequested configurability, no error handling for impossible scenarios. Before writing new code: does it need to exist? does the codebase already have it? does the stdlib/framework/an installed dependency solve it?
3. **Surgical changes** — touch only what the request requires. Match existing style. Don't refactor, reformat, or "improve" adjacent code that wasn't part of the request.
4. **Goal-driven execution** — turn tasks into verifiable goals ("fix the bug" becomes "write a test that reproduces it, then make it pass"). For multi-step work, state a brief plan with a verify check per step, then loop until every step is verified. Never claim "done" or "tests pass" without running the command in the same turn and reading its output.
5. **Orchestrator, not implementer** — the main session plans, decides, coordinates and commits; it does not implement. Delegable implementation and analysis goes to a specialist subagent (table below), dispatched in parallel waves when task scopes don't conflict. Rule: `@.claude/rules/parallel-subagent-driven-development.md`.
6. **Brainstorm → plan → implement → review.** Classify every request as *spike* (answer, no permanent code), *bounded* (≤ 3 files inside an existing flow: two-sentence design in chat, approval, implement) or *architectural* (new subsystem or interface change: design doc in `docs/`, explicit approval, then a plan in `docs/plans/`). When in doubt, pick the heavier path. Never downgrade mid-task.

## Hard rules of this product (from the spec; non-negotiable)

- **No agent executes orders.** Every entry goes AGENT → PROPOSAL → RISK ENGINE → EXECUTION. Exit orders (stop, target, manual close, kill switch) are always allowed.
- **No live trading** until Phase 4. `LiveExecutionAdapter` raises `LiveTradingDisabled`. Do not build UI for it.
- **No fake anything in production:** no permanent mock data, no inert buttons, no fake charts, no invented PnL, no "coming soon" pages in the nav. Mocks/fixtures live only in tests and are labeled.
- **No local state:** no SQLite, no JSON state files, no browser-only state, no cron on a dev box. Postgres + Redis only.
- **Secrets never reach the frontend, the repo, or logs.** `.env*` files are never written by agents (hook-enforced).
- **Money is `Decimal` / `NUMERIC(28,10)`.** Never `float` for price, qty, PnL, fees. Time is always UTC.
- **Tenant isolation is double:** tenant-scoped repositories in code AND Row Level Security in Postgres. Every tenant table has `organization_id`.
- **Every meaningful mutation is audited** (`audit_logs`, append-only) — risk, exchange, agent, kill switch, orders.
- **Explainable:** every score/signal/decision persists its decomposition/checks at decision time.

## Stack

TypeScript · Next.js 15 (App Router) + React 19 + Tailwind 4 + shadcn/ui · pnpm + Turborepo
Python 3.12 · FastAPI + Pydantic v2 + SQLAlchemy 2 (async) + Alembic · NumPy/Polars · uv workspace
PostgreSQL 16 (Neon) · Redis 7 (Streams + pub/sub) · Clerk (auth) · Docker · GitHub Actions · Sentry · PostHog

## Canonical commands (created in Milestone 0 — until then they do not exist)

Always use exactly these; never guess alternatives.

- **Install:** `pnpm install` and `uv sync --all-packages` (the root is a virtual uv project; without `--all-packages` the `hunter_*` members are not installed)
- **Lint:** `pnpm lint` (fast ESLint tier) · `uv run ruff check .` · `uv run ruff format --check .`
- **Lint (slow tier, CI only):** `pnpm lint:types` · `uv run ruff check --config packages/config/ruff.strict.toml .`
- **Typecheck:** `pnpm typecheck` · `uv run pyright`
- **Test:** `pnpm test` · `uv run pytest`
- **Build:** `pnpm build` · `docker compose -f infra/docker/docker-compose.yml build`
- **Run/Dev:** `docker compose -f infra/docker/docker-compose.yml up` (postgres, redis, api, worker `all`, web)
- **Migrations:** `uv run alembic -c infra/migrations/alembic.ini upgrade head` · `... check` · `... revision --autogenerate -m "<msg>"`
- **Generate TS types from OpenAPI:** `pnpm gen:types`
- **File-size gate (Python):** `python infra/scripts/check_file_size.py`
- **ESLint rule self-check:** `node packages/config/eslint/verify.mjs packages/config/eslint/eslint-rules/index.cjs`

## Read these first (in this order) before any design or implementation work

1. `docs/ARCHITECTURE.md` — stack, topology, services, module interfaces, monorepo tree
2. `docs/PIPELINE.md` — Market → Features → Anomaly → Regime → Opportunity → Agent → Risk → Execution
3. `docs/DATABASE.md` — schema, RLS, partitioning, retention
4. `docs/RISK_ENGINE.md` — checks, sizing, kill switch
5. `docs/ROADMAP.md` + `docs/plans/M<n>.md` — current milestone scope and wave plan
6. `docs/SPEC_REVIEW.md` — why the decisions above were taken
7. `docs/WORKFLOW.md` — how work is planned, dispatched, reviewed, committed and reported

## Specialist agent routing table

Dispatch the specialist whose row matches; never a generic agent for delegable work. Definitions in `.claude/agents/`. Pick the model tier per dispatch (mechanical → haiku, implementation/integration → sonnet, architecture/risk/security judgment → opus); never inherit silently.

| Agent | When to use | Default model |
|---|---|---|
| `sexta-feira` | Everton's personal agent and product owner: takes requests in Portuguese, saves files/folders, keeps long-term memory in the Obsidian vault (MCP-only), writes specs/briefs, dispatches the whole roster (including the opus specialists), enforces the workflow, reports in §77 format. Entry point for a human steering the product. | opus |
| `backend-specialist` | FastAPI routers/services, SQLAlchemy repositories, workers (`services/*`), Redis Streams consumers/producers, Pydantic schemas. | sonnet |
| `frontend-specialist` | Next.js App Router pages, shadcn/ui components, Tailwind theme, TanStack Table/Query, realtime hooks, nav-registry. | sonnet |
| `database-architect` | Schema changes, Alembic migrations, RLS policies, partitions/retention, indexes, query plans. Reviews any migration. | opus |
| `exchange-integration-specialist` | `hunter_exchanges`: Binance/Bybit REST+WS adapters, normalization, reconnection/gap recovery, rate limiting, recorded fixtures. | sonnet |
| `quant-engineer` | `hunter_indicators`: features, anomaly detectors, regime classifier, opportunity scorer, strategies; backtest engine; anti-look-ahead. | opus |
| `risk-engine-guardian` | Anything under `packages/risk-core`, `hunter_core.execution`, `services/execution-worker`, kill switch, sizing. Mandatory reviewer for changes there. | opus |
| `security-reviewer` | Auth, RBAC, tenant isolation, secrets, webhooks, headers, dependency CVEs. Mandatory reviewer before merging anything touching those. | opus |
| `code-reviewer` | General review of any diff: bugs, error handling, test coverage, spec conformance. One per task after each wave. | sonnet |
| `test-engineer` | Unit/integration/property tests (pytest, Vitest), fixtures, testcontainers; Playwright E2E for critical flows. | sonnet |
| `devops-engineer` | Dockerfiles, docker-compose, GitHub Actions, Railway/Vercel/Neon config, health checks, observability wiring. | sonnet |
| `explorer-agent` | Read-only mapping of the codebase or a dependency's API before planning. Never edits. | haiku |
| `documentation-writer` | `docs/*.md` (Portuguese), READMEs, runbooks, ADRs in `docs/decisions/`. | sonnet |

## Conventions

- **Python:** ruff (config in `packages/config/ruff.toml`), pyright strict, `async` everywhere in IO paths, `structlog` (never `print`), `Decimal` for money, `hunter_*` package prefix, one module ≤ 350 lines (`infra/scripts/check_file_size.py`), tests next to code in `tests/` folders, pytest markers `unit`, `integration`, `live` (live = hits real exchange, never in CI).
- **TypeScript:** ESLint flat config from `packages/config/eslint` (`quality/max-lines` 350 = error, `quality/no-direct-console` → `@/lib/logger`, `components/**` must not import `@/lib/server/**`), Prettier for formatting, Server Components by default, `"use client"` only where needed, tables virtualized ≥ 200 rows.
- **Naming:** DB snake_case; Python snake_case; TS camelCase; enums mirrored 1:1 between Postgres, Pydantic and TS (generated).
- **Tests are TDD:** write the failing test first, see it fail for the right reason, implement the minimum, see it pass, refactor. No production code without a test that failed first.
- **Commits:** conventional commits (`feat|fix|test|chore|docs|perf|refactor(scope): message`), one commit per task, made by the orchestrator only, HEAD captured fresh before each commit. Trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **New lint rules are born as `warn`** with the violation count written next to them; promoted to `error` only at zero. Never raise the 350-line budget to make a file pass.
- **Milestone report (§77 of the spec), mandatory at the end of each milestone:** COMPLETED · FILES CREATED · FILES MODIFIED · DATABASE CHANGES · TESTS CREATED · TEST RESULTS (real output) · KNOWN ISSUES · NEXT MILESTONE.

## Memory

@.claude/memory/INSTRUCTIONS.md
