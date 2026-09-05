---
tags: [changelog, historico]
updated: 2026-09-05
---

# Changelog

Uma entrada por commit (`git log --date=short --format='%h %ad %s'`), agrupado por dia, mais novo primeiro. Todo o histórico até agora é do Milestone 0 (fundação) — ver `docs/plans/M0.md` para as ondas T01–T13 e [[Resolved Bugs]] para o detalhe das correções de segurança/qualidade citadas aqui.

## 2026-09-05

- `97c36ff` feat(exchanges): Binance USDS-M public REST + WS adapter — duas rotas (`/public` e `/market`), assinaturas incrementais (`update_subscriptions` diff-only com ACK e catch-up), funding realizado paginado, fila limitada que nunca descarta kline final, rate limit por tentativa com gate de IP (T1.2 + T1.2b). 189 testes offline + 3 live (dado real nas duas rotas). Revisado por `code-reviewer`, revisão cruzada do `exchange-integration-specialist` e Astra adversarial; 16 achados corrigidos. Ver [[Exchange Adapters]] e [[WebSockets]].
- `a522bf1` docs(m1): DECISÃO CONJUNTA Claude⇄Astra — acceptance checklist for T1.2/T1.3/T1.4/T1.6
- `c58d4d1` docs(m1): joint Claude⇄Astra decision folded into the plan (recovery, liquidation identity ON CONFLICT (id, ts), supervision, per-component stalenes
- `becf1d9` docs(m1): Binance WS routes and @depth20 per official notice; Claude⇄Astra dialogue rounds 1–2 with concrete contracts (recovery, liquidation dedu
- `dd93d99` chore(rules): point the Astra rule at infra/scripts/astra.sh and the dialogue mode
- `606d5b6` chore(astra): single channel script (ask / run / dialogue / show) and Astra's second opinion recorded in the M1 plan
- `d76a0cf` feat(ops): market-worker compose service (restart unless-stopped, /ready healthcheck); entrypoint dispatches worker roles honestly (T1.6a, implemented
- `3399a19` chore(claude-md): fix guideline numbering
- `8df57ff` chore(agents): Astra second-opinion rule for every agent; Sexta-feira review protocol
- `3c31ef0` fix(docker): web image copies packages/shared-types (build was failing); sexta-feira: Astra runs unsandboxed by owner authorization
- `560c94c` fix(test): e2e workspace exposes 'e2e' instead of 'test' so 'pnpm test' no longer runs Playwright
- `4b24204` docs(m0): closure — DEPLOYMENT env table, README quickstart, CLAUDE.md commands verified, ROADMAP, milestone state, §77 report
- `f71059e` feat(exchanges): ExchangeAdapter protocol, stream channels and error types (M1 base)
- `415cc83` feat(core): normalized market domain types (T1.1)
- `c24a7b6` docs(obsidian): project knowledge base (32 pages, ADR 0003) and M1 wave plan
- `f153315` docs(audit): CURRENT_STATE.md — full repo audit at end of M0; ADR 0003 obsidian/ knowledge base

- `744fdf8` test(api): T11 integration suite — isolation, RBAC matrix, mutations, webhook, rate limits, websocket, auth edge cases
- `541ef78` fix(web): nav registry is plain data (segment + icon key) so the server layout can pass it to the client sidebar
- `b2e48b5` fix(dev): setup_env.ps1 parenthesizes each .env line (comma binds tighter than + in PowerShell, so all vars were joined into one line)

## 2026-09-04

- `4e7e878` fix(dev): setup_env.ps1 extracts the right key from NAME=value or multi-line pastes; prints lengths
- `330f861` chore(agents): record Astra (Codex) verified login and Windows shim note
- `ccc9139` chore(agents): Sexta-feira delegates execution to Astra via OpenAI Codex CLI (workspace-write sandbox, no commits, reviewed like any implementer)
- `4df500f` chore(dev): setup_env.ps1 optionally records OPENAI_API_KEY for the Astra second opinion
- `e18d1d7` feat(agents): Sexta-feira can ask GPT-6 Astra for a second opinion (infra/scripts/ask_astra.py, key from local .env, data not decisions)
- `336de92` docs(adr): 0002 provider-agnostic LLM layer with Anthropic and OpenAI GPT-6 Astra (Phase 2); env placeholders
- `43ee7c3` fix(dev): setup_env.ps1 ASCII-only so PowerShell 5.1 parses it
- `9a212b6` chore(dev): setup_env.ps1 creates the local .env from hidden prompts (keys never pass through agents or chat)
- `76b7cfd` chore(memory): obsidian-mcp v2 server for the vault (.mcp.json); vault initialized
- `a39ffde` chore(agents): Sexta-feira, Everton's personal agent; Obsidian vault (PARA structure, templates) as tier-two memory with MCP-only hook
- `e6a564a` chore(agents): product-owner agent for Everton (PT-BR entry point with authority over the full roster)
- `8e4d00d` docs(web): e2e script description
- `8fad06f` test(e2e): send browser navigation headers so the fake-key handshake assertion sees the 307
- `0b73fa4` test(e2e): assert the fake-key sign-in handshake without following the redirect
- `99c41bf` chore(state): repo moved to C:\dev\project-hunter; wave 5
- `7e90e81` test(e2e): playwright setup, public/api-health specs, clerk-gated signup+onboarding spec, CI e2e job (M0 T12)
- `8a454f4` fix(api): streaming body cap, JWKS max staleness, per-principal and WS limits, two-phase webhook claims (T06 re-review)
- `f48da11` fix(web): keep the dev-only /_design preview outside the Clerk middleware matcher
- `936b4b1` feat(web): accept-invite page, onboarding gating and step-jump guard, density pre-hydration (T09 review)
- `94b26a4` fix(api): auth/tenancy hardening from security review (T06 fixes)
- `c76c705` chore(dev): preview launch config for the web app
- `da557b5` feat(web): gold/green/black/white identity applied (DESIGN-1)
- `1bae973` feat(web): onboarding wizard, dashboard/system/settings pages, typed api client, generated OpenAPI types (M0 T09)
- `be82830` docs(design): gold/green/black/white identity, tokens and usage rules
- `ea24864` test(core): create app/worker roles in the shared container fixture; typed helpers for schema tests; nosec on constant-table SQL
- `137cb0d` chore(state): wave 4 started
- `5c5e412` feat(api): clerk auth, principal with JIT provisioning, RBAC (404 cross-tenant), tenant/user/bootstrap sessions with SET LOCAL ROLE, org/workspace/member/invitation/audit routers, clerk webhook, sql audit sink, websocket auth (M0 T06)
- `720102f` fix(db): users co-member policy read-only; organizations no DELETE for app role; explicit role check; real seed counts (T04 re-review)
- `907ebc2` chore(state): compose verified end to end; T06 in progress
- `12bf174` style: ruff format
- `1a15013` fix(docker): drop unused noqa in healthcheck (ruff RUF100)
- `c28c1bc` fix(db): schema hardening from cross-review (T04 fixes, 0001 amended in place, never deployed)
- `9c81634` fix(test): resolve per-member tests packages as namespace packages so a single pytest run works (CI python-test)
- `46993a0` fix(docker): loopback comment passes forbidden-patterns; HEALTH_PORT default 8001; DEPLOYMENT.md describes the real entrypoint (T07 review)
- `34da662` chore(docker): api/workers image with role entrypoint, web standalone image, dev and test compose (M0 T07)
- `a900926` test(api): redis bridge exposes is_running; pyright strict clean
- `c6eb407` fix(api): validation errors never echo input; /ready timeouts; proxy IP trust model; /metrics token gate; bounded request id (T05 review CRITICAL/HIGH/MEDIUM)
- `ba4ebe0` chore(state): T04 cross-review blocked, T04-fixes and T07 dispatched
- `149c542` fix(api): single-dispatcher redis bridge routed by message channel; broadcast evicts dead connections (T05 review HIGH/MEDIUM)
- `4988645` fix(web): decimal-safe money formatting, jittered ws backoff, accessible planned nav items (T08 review)
- `a9da9ea` test(core): narrow formatter type in logging test (pyright strict clean)
- `7d25f8a` chore: gitleaks allowlist for historical fixture literal; milestone state after rate-limit pause
- `4035cd4` test(core): mark fixture db password as FAKE per gitleaks allowlist convention
- `154ecea` feat(db): initial schema, RLS, partitions, roles, seeds and partition script (M0 T04)
- `9b7afe8` ci(security): value-based gitleaks allowlist, db-uri password rule, SHA-pinned actions, path-segment exemptions (T10 review)
- `4c107f7` fix: wave-2 review follow-ups
- `8db248a` feat(api): app factory, problem+json errors, middleware, health/ready/metrics, realtime classes (M0 T05)
- `b0f6012` feat(web): next.js 15 scaffold, dark-first theme, nav registry, clerk auth pages and app shell (M0 T08)
- `ca3cab3` test(core): runtime shutdown cleanup, /ready db-down branch, audit on exception, token-checked lock release (T03 review)
- `f7bcef7` ci: pipeline with lint, tests, migrations, security scans, forbidden patterns and gate (M0 T10)
- `e9f2091` chore(state): M0 wave 2 dispatched
- `88c2dd7` feat(core): settings, logging, db base/session, redis, events, runtime, audit, observability (M0 T03)
- `61c47e0` docs(workflow): eslint self-check command is the package test script (T02 review nit)
- `5b4cae8` chore(config): shared lint/type presets (M0 T02)
- `cd1c2d3` fix(repo): canonical install uses uv sync --all-packages (virtual root)
- `6652c5a` chore(repo): monorepo workspaces, tooling and python package skeletons (M0 T01)
- `a8d48a9` docs(plan): M0 approved; T02/T03 depend on T01, scope adjustments recorded
- `f925517` chore: toolchain complete — docker verified with hello-world, no blockers
- `a8e6764` chore: record docker desktop installed but blocked by missing WSL
- `06d9562` chore: record toolchain state (pnpm, uv, python 3.12 installed; docker pending)
- `b3fd8d4` chore: record verified hooks and eslint self-check after Node install
- `41ab588` chore: adopt vibe-coding-toolkit workflow (CLAUDE.md, agents, hooks, rules, memory, quality gates, M0 wave plan)
- `cbb36b1` docs: arquitetura, revisão da especificação, schema, pipeline, MVP e roadmap (pré-M0)

## Relacionadas

[[Resolved Bugs]] · [[System Overview]]

## Fontes

`git log --date=short --format='%h %ad %s'` (repositório `C:\dev\project-hunter`, capturado em 2026-09-05)
