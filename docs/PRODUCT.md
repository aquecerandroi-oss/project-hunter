# Produto

## 1. Tese
Encontrar situações com **assimetria + anomalia + contexto + liquidez + controle de risco**, explicar por que, e provar com histórico (paper e shadow) antes de qualquer dinheiro real.

## 2. Modelo de tenancy
`USER → ORGANIZATION → WORKSPACE → PORTFOLIOS → AGENTS`. Um usuário pode pertencer a várias organizações. Todo dado financeiro tem `organization_id`.

## 3. Onboarding
1. Criar workspace (nome; a organização é criada junto com slug derivado).
2. Objetivo: Explore, Paper Trading, Research, Automated Trading (afeta presets e itens de navegação destacados).
3. Capital virtual (valor padrão 10 000 USDT).
4. Perfil de risco: Conservative, Balanced, Aggressive, Custom (preset copiado para um `risk_profile` da org).
5. Exchanges monitoradas (preferência de filtro).
6. Entrar no dashboard. No M3, o passo 3 passa a criar o primeiro portfolio paper.

## 4. Navegação (registro único, com milestone de disponibilidade)

| Item | Rota | Disponível a partir de |
|---|---|---|
| Dashboard | `/dashboard` | M0 (shell), M5 (completo) |
| Radar | `/radar` | M2 |
| Markets | `/markets` | M1 |
| Opportunities | `/opportunities` | M2 |
| Portfolio | `/portfolio` | M3 |
| Trades | `/trades` | M3 |
| Agents | `/agents` | M4 |
| Agent Arena | `/arena` | M6 |
| Strategies | `/strategies` | M6 |
| Backtests | `/backtests` | M6 |
| Analytics | `/analytics` | M5 |
| Intelligence | `/intelligence` | Fase 2 |
| Risk Center | `/risk` | M4 |
| Exchanges | `/exchanges` | Fase 3 |
| Alerts | `/alerts` | Fase 2 |
| System | `/system` | M0 |
| Settings | `/settings/*` | M0 (profile, organization, members, security, appearance); M4 (risk defaults); M5 (notifications); Fase 2 (api); Fase 3 (billing) |

## 5. Planos e entitlements (schema no M0, cobrança na Fase 3)

| Entitlement | FREE | PRO | QUANT | ENTERPRISE |
|---|---|---|---|---|
| `max_agents` | 2 | 8 | 30 | ilimitado |
| `max_exchanges` | 2 | 4 | 8 | ilimitado |
| `max_portfolios` | 1 | 5 | 20 | ilimitado |
| `market_history_days` | 30 | 180 | 730 | ilimitado |
| `backtesting` | não | sim | sim | sim |
| `advanced_intelligence` | não | não | sim | sim |
| `custom_agent_params` | não | sim | sim | sim |
| `live_trading` | não | não | sim (Fase 4) | sim (Fase 4) |
| `api_access` | não | sim | sim | sim |

Feature flags de sistema (`ENABLE_*`) são independentes e sempre prevalecem quando desligadas.

## 6. Eventos de product analytics (PostHog)

`user_signed_up`, `workspace_created`, `portfolio_created`, `agent_enabled`, `agent_paused`, `backtest_started`, `opportunity_viewed`, `market_viewed`, `exchange_connected`, `paper_trade_executed`, `manual_paper_order_placed`, `risk_profile_changed`, `live_mode_requested`, `kill_switch_used`, `alert_rule_created`.

Propriedades permitidas: ids (org, workspace, agent, strategy_version), plano, papel, exchange, símbolo, regime, faixa de score. **Nunca**: valores de PnL, capital, chaves, e-mails de terceiros.

## 7. Design

Dark-first; densidade de informação alta; tipografia tabular para números; cores semânticas fixas (long/short, pnl positivo/negativo, severidade); estados vazios honestos ("Nenhuma anomalia nas últimas 24 h") em vez de placeholders. Componentes shadcn/ui customizados em `apps/web/components/ui`. Mobile: overview, posições, PnL, alertas, kill switch.

## 8. Explicabilidade

Toda oportunidade, sinal, proposta e trade mostra:
- componentes e contribuições (Opportunity),
- features de suporte com nome e versão (Signal),
- checks com valor e limite (Risk),
- fills com preço, slippage e fee (Execution),
- snapshot de features na entrada e saída (Trade),
- e, quando existir, "shadow performance deste setup nos últimos 90 dias" a partir de `signal_outcomes`.
