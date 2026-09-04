# MVP — definição exata

MVP = Milestones 0 a 5 concluídos e validados (`ROADMAP.md`). Sem dinheiro real. Sem live trading.

## 1. Escopo

### Entra

| Área | Conteúdo |
|---|---|
| Auth | Cadastro, login, logout, reset de senha, confirmação de e-mail, sessões (Clerk) |
| Tenancy | Organização criada no onboarding; 1 workspace padrão; membros com RBAC (OWNER, ADMIN, TRADER, ANALYST, VIEWER); convites por e-mail |
| Onboarding | 6 passos do §10 (exchanges = preferência de monitoramento) |
| Market data | Binance USDS-M e Bybit Linear, perpétuos USDT, top 200 por volume em cada; ticker, trades, book 25, candles 1m, funding, mark, OI, liquidações; recovery REST |
| Feature Engine | Conjunto v1 (`PIPELINE.md` §2) com registro de features |
| Anomaly Engine | 8 tipos v1 |
| Regime | v0: BTC_BULL, BTC_BEAR, SIDEWAYS + HIGH/LOW_VOLATILITY |
| Opportunity | Score 0–100 com decomposição, pesos configuráveis (global), status |
| Agentes | `momentum_v1`, `volume_anomaly_v1`; framework de estratégias; sinais globais; agentes por portfolio |
| Risk Engine | Limites do §31, kill switch em 3 escopos, sizing, checks registrados |
| Execução | Paper com fees, spread, slippage do book, latência, partial fills; stops e alvos gerenciados; MTM 1 s |
| Portfolio | Múltiplos portfolios paper por workspace; equity, cash, exposição, PnL, drawdown |
| Rotas | `/dashboard`, `/radar`, `/markets/[exchange]/[symbol]`, `/opportunities`, `/portfolio`, `/trades`, `/trades/[id]`, `/agents`, `/agents/[id]`, `/risk`, `/analytics` (básico), `/system`, `/settings/{profile,organization,members,security,risk,notifications,appearance}` |
| Realtime | WS para preços, radar, oportunidades, posições, PnL, risk events, sinais |
| Analytics básica | Equity curve, PnL por período, estatísticas por agente e por mercado |
| Audit | Todas as mutações relevantes; `/settings/security` mostra o log da org |
| System | `/system` com workers, Redis, Postgres, conexões WS, latência por exchange, último dado, erros |
| Observabilidade | Sentry, logs JSON, `/health`, `/ready`, `/metrics`, heartbeats |
| CI | lint, typecheck, testes, build, validação de migração, security checks |

### Não entra (com destino)

| Item | Milestone / Fase |
|---|---|
| Shadow portfolios na UI (shadow de sistema em `signal_outcomes` **entra**, mas sem UI própria) | M6 |
| Agent Arena, Backtests, versionamento de estratégia na UI | M6 |
| Agentes breakout, order flow, mean reversion, derivatives, ensemble | Fase 2 |
| Regime v1 (RISK_ON/OFF, ALT_EXPANSION, PANIC, LIQUIDITY_CONTRACTION) | Fase 2 |
| Alertas com regras e canais externos | Fase 2 (in-app simples de risk events **entra** no M5) |
| Intelligence, LLM, narrativa, social, on-chain | Fase 2/3 |
| Exchange connections com chaves | Fase 3 (schema no M0) |
| Billing/Stripe | Fase 3 (schema no M0) |
| API pública com api_keys | Fase 2 |
| Live trading | Fase 4 |
| Parâmetros customizados de agente por org | Fase 2 |
| Light theme polish, i18n | Fase 2 |

## 2. Critérios de sucesso (§63) mapeados

| Critério | Como se verifica | Milestone |
|---|---|---|
| Usuário cria conta | E2E Playwright `signup.spec` | M0 |
| Onboarding funciona | E2E `onboarding.spec` cria org, workspace, portfolio paper, risk profile | M0 (org) + M3 (portfolio) |
| Dashboard funciona | Cards lidos de dados reais; teste de integração de `/dashboard/summary` | M5 |
| Market data realtime | `/system` mostra último dado < 5 s; teste de integração com fixtures gravadas | M1 |
| Scanner monitora ativos | `radar:scores` com N mercados; `/radar` lista | M2 |
| Anomalias aparecem | `anomalies` com linhas nas últimas 24 h em ambiente rodando; teste unitário com séries sintéticas | M2 |
| Opportunity Score funciona | Decomposição visível no Explanation Panel; teste unitário de pesos | M2 |
| Agentes geram sinais | `agent_signals` gerados; teste unitário com cenário determinístico | M4 |
| Risk Engine aceita/rejeita | Tabela de casos; `trade_proposals.risk_decision.checks` visível na UI | M4 |
| Paper Wallet executa | `orders`/`fills`/`positions` criados; teste de execução com book sintético | M3 + M4 |
| PnL calculado | Reconciliação: `equity = cash + Σ posições` sempre; teste de propriedade | M3 |
| Trade history registrado | `/trades` e `/trades/[id]` com snapshot | M3 |
| Dashboard atualiza | WS entrega `positions.updated` em < 1 s; E2E observa mudança | M5 |
| Nenhum dado depende de arquivo local | `grep` no CI proíbe `sqlite`, `open(` para escrita fora de testes, e `.json` de estado; `docker-compose` só com Postgres e Redis | M0 |

## 3. Regras que valem para todo o MVP

- Nenhum mock em produção. Fixtures gravadas de exchange só em `packages/exchange-adapters/hunter_exchanges/testing/` e em testes.
- Toda tela lista a origem dos dados (feature e versão) no Explanation Panel ou tooltip.
- Um item de navegação só aparece quando sua rota está implementada.
- Live trading: interface existe, `ENABLE_LIVE_TRADING=false`, e a UI não mostra a opção.

## 4. Dimensionamento inicial

| Parâmetro | Valor padrão | Env |
|---|---|---|
| Mercados monitorados por exchange | 200 | `MARKET_UNIVERSE_SIZE` |
| Profundidade de book | 25 | `BOOK_DEPTH` |
| Coalescência de ticks | 250 ms | `TICK_COALESCE_MS` |
| Throttle de features por símbolo | 1 s | `FEATURE_THROTTLE_MS` |
| Throttle de radar para o browser | 1 s | `RADAR_PUSH_MS` |
| Retenção 1m candles | 90 d | `RETENTION_CANDLES_1M_DAYS` |
