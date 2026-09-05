# Roadmap — Milestones 0 a 6 e fases seguintes

Cada milestone tem: escopo, entregáveis, testes e critério de saída. Um milestone só fecha quando lint, typecheck, testes e build passam e a documentação foi atualizada. Commit lógico por milestone (ou por sub-entrega quando grande).

Formato de fechamento (§77): COMPLETED · FILES CREATED · FILES MODIFIED · DATABASE CHANGES · TESTS CREATED · TEST RESULTS · KNOWN ISSUES · NEXT MILESTONE.

---

## Milestone 0 — Fundação

**Status: entregue em 2026-09-05.** Relatório de fechamento (§77): `docs/reports/M0.md`.

**Objetivo:** monorepo funcional, deployável, com auth real, organizações, dashboard shell, migrações, CI.

**Plano de execução em ondas:** `docs/plans/M0.md` (13 tarefas, 6 ondas). **Pré-requisitos de máquina** (Node 22, pnpm, uv, Docker) listados lá; em 2026-09-04 nenhum estava instalado.

**Escopo**
- Monorepo: pnpm + Turborepo; `uv` workspace; `packages/config` com presets de lint/tsconfig/ruff/pyright.
- `apps/web`: Next.js, Tailwind, shadcn/ui, tema dark-first com tokens, layout de app (sidebar via `nav-registry`, topbar, seletor de organização), páginas de auth do Clerk, onboarding passos 1–6 (passos 3–5 salvam preferências; portfolio real só no M3, então o passo 3 grava `default_initial_capital` no workspace), `/dashboard` shell com cards de sistema reais (estado dos workers, contagem de mercados = 0 até o M1) e sem números financeiros inventados.
- `apps/api`: FastAPI, `Settings`, verificação JWT Clerk, webhook Clerk (`user.created/updated/deleted`) para `users`, RBAC, tenant context + RLS, routers `orgs`, `workspaces`, `members`, `invitations`, `me`, `system`, `audit`; middleware de request id, security headers, rate limit (Redis), CORS; erros RFC 9457; OpenAPI organizado por tags.
- `packages/core`: models SQLAlchemy de **todas** as tabelas do `DATABASE.md` (para o schema nascer inteiro), sessão async, RLS helper, Redis client, envelopes de evento, logging estruturado, runtime de worker (`HUNTER_ROLE`, heartbeat, `/health`), audit helper.
- `infra/migrations`: migração inicial com enums, tabelas, partições iniciais, políticas RLS, roles `hunter_app` e `hunter_worker`, seeds (exchanges, strategies, strategy_versions v1 como `draft`, plan_entitlements, feature_flags, risk profile presets).
- `infra/docker`: Dockerfile único para api/workers, Dockerfile web, `docker-compose.yml` (postgres, redis, api, worker `all`, web).
- `.github/workflows/ci.yml`: lint, typecheck, pytest, vitest, build, `alembic upgrade head` + `alembic check` contra Postgres de serviço, `pip-audit`, `pnpm audit`, geração de tipos com verificação de diff.
- `packages/shared-types`: geração a partir do OpenAPI.
- Sentry e PostHog inicializados atrás de env (sem chave = desligado).

**Testes:** unitários de RBAC e tenant context; integração de auth (JWT válido/inválido/expirado), isolamento entre duas orgs (RLS), webhook Clerk; E2E `signup`, `onboarding`.

**Saída:** `docker compose up` sobe tudo; usuário cria conta, faz onboarding, vê dashboard shell; CI verde; deploy manual em Railway + Vercel documentado e testado uma vez.

---

## Milestone 1 — Market data

**Escopo**
- `hunter_exchanges`: `ExchangeAdapter`, `BinanceAdapter` (USDS-M) e `BybitAdapter` (Linear): REST público (markets, candles, ticker, book, funding, OI) e WS (trades, bookTicker, depth, kline, markPrice, liquidations). Rate limiter por exchange em Redis. Fixtures gravadas para testes.
- Normalização: modelos `Normalized*` em `hunter_core.domain`.
- `market-worker`: universo, assinaturas, hot state Redis, candles e snapshots no Postgres, recovery e `ingestion_gaps`, heartbeat.
- API: `GET /markets`, `GET /markets/{exchange}/{symbol}` (hot state), `GET /markets/{...}/candles`, `GET /markets/{...}/book`; WS `rt:market:*`.
- Web: `/markets` (lista real, busca), `/markets/[exchange]/[symbol]` com gráfico de candles (lightweight-charts), book, trades, funding e OI. `/system` mostra latência, último dado, conexões WS por exchange. Dashboard passa a mostrar "mercados monitorados".

**Testes:** adapters contra fixtures (parse, normalização, edge cases de símbolos); gap detection e recovery; integração market-worker → Redis → API; contrato WS.

**Saída:** dados ao vivo das duas exchanges no navegador; gaps recuperados automaticamente após derrubar a rede em teste.

---

## Milestone 2 — Inteligência de mercado

**Escopo**
- `hunter_indicators`: registro de features, conjunto v1, detectores de anomalia v1, regime v0, Opportunity Engine com pesos em `opportunity_weights`.
- `scanner-worker`: runners com as cadências de `PIPELINE.md`; persistência; publicação.
- API: `/radar` (lista paginada e filtrada server-side: score, status, exchange, anomalia, regime, volatilidade), `/opportunities`, `/opportunities/{id}` (decomposição, histórico, anomalias, timeline), `/anomalies`, `/regime`.
- Web: `/radar` (tabela virtualizada realtime, filtros do §13), `/opportunities` com **Explanation Panel** determinístico (componentes, pesos, contribuições, anomalias, features), timeline no Market Detail (§14), regime no dashboard.

**Testes:** cada feature com série sintética e valor esperado; anti-look-ahead (feature não muda quando um candle não-final muda); detectores com spikes injetados; regime com histerese; scorer com pesos e decomposição que soma o score; integração scanner → Redis → API.

**Saída:** Radar ao vivo com centenas de mercados; anomalias reais nas últimas 24 h; oportunidade explicada sem texto de LLM.

---

## Milestone 3 — Paper trading

**Escopo**
- `hunter_core.execution`: `ExecutionAdapter`, `PaperExecutionAdapter` (walk do book, partial fills, slippage, fees, latência), `ShadowExecutionAdapter`, `LiveExecutionAdapter` (stub que levanta `LiveTradingDisabled`).
- `execution-worker`: gestão de ordens, posições, stops/alvos, MTM, trades, equity snapshots, recuperação após restart.
- Portfolios: CRUD, risk profile por portfolio, onboarding cria o primeiro portfolio paper com o capital escolhido.
- **Ordem manual paper** (TRADER+) em Market Detail para exercitar o motor antes dos agentes existirem. Passa pelo Risk Engine básico (limites de tamanho, exposição, spread) mesmo antes do M4 completar o engine.
- API: portfolios, positions, orders, trades, equity; WS `rt:org:*:portfolio:*`.
- Web: `/portfolio` (lista, detalhe, equity curve, posições), `/trades`, `/trades/[id]` com snapshot e gráfico de entrada/saída.

**Testes:** fills contra books sintéticos (book raso → partial), invariante `equity = cash + Σ pos`, PnL com fees e slippage, stop e alvo parciais, restart do worker com posições abertas, idempotência (mesma proposta duas vezes = uma ordem).

**Saída:** usuário abre e fecha posição paper manual; PnL, fees e slippage corretos; histórico completo.

---

## Milestone 4 — Agentes e Risk Engine

**Escopo**
- Framework `Strategy`; `momentum_v1` e `volume_anomaly_v1` ativados; `strategy-worker` gerando sinais globais.
- `hunter_risk`: `RiskEngine` completo (todos os checks de `RISK_ENGINE.md`), sizing, kill switch em 3 escopos com transições auditadas.
- Proposal builder, `trade_proposals`, fluxo AGENT → PROPOSAL → RISK → PAPER EXECUTION de ponta a ponta.
- API: agents CRUD (enable/pause/disable, alocação, filtros), signals, proposals (com decisão e checks), risk (limites, estado, eventos, kill switch).
- Web: `/agents`, `/agents/[id]` (métricas básicas; estatísticas completas no M5), `/risk` (Risk Center com limites editáveis, exposição, kill switch), propostas rejeitadas visíveis com motivo, status `IN_POSITION` e `BLOCKED_BY_RISK` no Radar.

**Testes:** estratégias com cenários determinísticos (gera sinal / não gera); tabela de casos do Risk Engine (cada check aprovando e reprovando); kill switch por escopo; pipeline de integração: candle sintético → sinal → proposta → fill paper; E2E `enable agent`, `change risk`, `kill switch`.

**Saída:** agentes operando paper sem intervenção; toda decisão explicável na UI.

---

## Milestone 5 — Analytics, auditoria, sistema (fecha o MVP)

**Escopo**
- `analytics-worker`: `agent_stats`, `signal_outcomes` (shadow de sistema), agregações de equity, retenção e partições.
- Dashboard completo (§12) com dados reais; PnL hoje/7d/30d; best/worst agent; top opportunity; most active market; recent trades; risk events.
- `/analytics` básico: por agente, estratégia, mercado, regime, exchange, hora, volatilidade, score, confiança, holding time.
- `/settings/security` com audit log da organização; audit em todas as mutações.
- `/system` completo (§45), heartbeats, fila (lag por stream), erros.
- Notificações in-app de risk events e kill switch.
- Mobile: overview, posições, PnL, kill switch.

**Testes:** estatísticas com trades sintéticos (win rate, PF, expectancy, Sharpe, Sortino, drawdown); audit em cada endpoint mutante (teste parametrizado); E2E `view opportunity`, `paper trade`, dashboard atualizando via WS.

**Saída:** todos os critérios de `MVP.md` §2 verdes.

---

## Milestone 6 — Shadow, Arena, Backtest, versionamento

**Escopo**
- Shadow portfolios na UI; comparação shadow vs paper.
- Agent Arena: organização de sistema, um portfolio `is_arena` por strategy_version ativa, ranking por retorno ajustado a risco (Sortino, drawdown, consistência, expectancy, PF), `/arena`.
- Backtest Engine: replay de candles do Postgres com o mesmo `Strategy`, `RiskEngine` e `PaperExecutionAdapter` (mesmo código que o realtime; sem look-ahead por construção), validação train/validation/oos e walk-forward, alertas de overfitting (diferença de performance entre segmentos) e leakage (teste de embaralhamento). `/backtests`.
- Versionamento na UI: `/strategies` com versões, changelog, ativação por OWNER; agente escolhe versão; versão antiga nunca some.
- Meta Engine v0: recomendação de pesos e alocação (só recomenda; OWNER aprova; histórico).

**Testes:** backtest reproduzível (mesma entrada, mesma saída); backtest de estratégia "cheat" com look-ahead deliberado é detectado; ranking da arena com portfolios sintéticos.

---

## Fase 2 (após M6)
Agentes breakout, order flow, mean reversion, derivatives, ensemble; Regime v1; Alertas com regras e canais (e-mail via Resend, Telegram, Discord); Intelligence v1 (news, listings, announcements) com LLM para classificação; analytics avançada; API pública com `api_keys`; parâmetros customizados por org.

## Fase 3
On-chain, whales, narrativa e social; Learning Engine (importância de features, falsos positivos, degradação); alocação automática dentro de limites; otimização de portfolio; OKX, Coinbase, Hyperliquid, Kraken; exchange connections com validação de permissões (withdraw rejeitado); Stripe.

## Fase 4 — Live trading (somente após validação)
Checklist de segurança, testnet/sandbox, reconciliação local × exchange, controles de emergência, testes de execução, ativação explícita por OWNER com confirmação, `ENABLE_LIVE_TRADING` por org via entitlement. Sem exceções.
