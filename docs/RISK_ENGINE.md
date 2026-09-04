# Risk Engine

Função pura e determinística: `evaluate(proposal, portfolio_state, limits, market_liquidity, kill_switch) -> RiskDecision`. Nenhuma ordem é criada sem uma `RiskDecision.approved = true` persistida em `trade_proposals`.

## 1. Entradas

```
TradeProposal      agent, portfolio, market, direction, signal (entry_zone, stop, targets), requested_risk_pct
PortfolioState     cash, equity, peak_equity, exposure_notional, open_positions[], daily_realized_pnl,
                   daily_unrealized_pnl, drawdown_pct, exposure_by_asset{}, exposure_by_exchange{}
RiskLimits         (do risk_profile do portfolio, com defaults da org e do sistema)
MarketLiquidity    quote_volume_24h, spread_pct, book_depth_usd_top25, data_quality, last_price, mark_price
KillSwitchState    system, organization, portfolio  → efetivo = mais restritivo
MarketRegime       regime atual (v0) — usado só para ajuste de tamanho, nunca para aprovar
```

## 2. Limites (chaves de `risk_profiles.limits`)

| Chave | Conservative | Balanced | Aggressive | Descrição |
|---|---|---|---|---|
| `max_position_pct` | 0.02 | 0.05 | 0.10 | Notional de uma posição / equity |
| `risk_per_trade_pct` | 0.0025 | 0.005 | 0.01 | Perda no stop / equity (base do sizing) |
| `max_total_exposure_pct` | 0.30 | 0.60 | 1.00 | Σ notional / equity |
| `max_daily_loss_pct` | 0.01 | 0.02 | 0.04 | Perda realizada + não realizada do dia |
| `max_drawdown_pct` | 0.05 | 0.10 | 0.20 | Do pico de equity; ao atingir, portfolio vai a `TRADING_DISABLED` |
| `max_concurrent_positions` | 3 | 6 | 12 | |
| `max_asset_exposure_pct` | 0.05 | 0.10 | 0.20 | Por base asset, somando exchanges |
| `max_exchange_exposure_pct` | 0.50 | 0.70 | 1.00 | |
| `min_liquidity_usd_24h` | 50M | 20M | 5M | Volume 24h do mercado |
| `max_spread_pct` | 0.0005 | 0.001 | 0.002 | No momento da proposta e da execução |
| `max_slippage_pct` | 0.001 | 0.002 | 0.005 | Estimado pelo walk do book |
| `max_leverage` | 1 | 2 | 3 | Paper respeita como se fosse margem |
| `max_correlated_positions` | 2 | 4 | 8 | Posições com beta > 0.8 na mesma direção |
| `min_stop_distance_pct` | 0.003 | 0.002 | 0.001 | Evita stops dentro do ruído |
| `max_stop_distance_pct` | 0.03 | 0.05 | 0.08 | Evita sizing minúsculo por stop absurdo |
| `auto_close_on_emergency` | false | false | false | Se `EMERGENCY`, fechar posições automaticamente |
| `regime_size_multiplier` | {BTC_BEAR long: 0.5, HIGH_VOL: 0.7} | idem | {HIGH_VOL: 0.85} | Multiplicador de tamanho por regime |

Limites são validados na edição (`max_position_pct ≤ max_total_exposure_pct`, etc.). Edição gera `audit_logs` com before/after e `risk_events` tipo `limits_changed`.

## 3. Checks (ordem de avaliação)

Todos os checks avaliáveis são registrados em `risk_decision.checks[]` como `{name, passed, value, limit, message}`, mesmo após o primeiro reprovado, para que o Explanation Panel mostre o quadro inteiro.

| # | Check | Reprova quando |
|---|---|---|
| 1 | `kill_switch` | efetivo ∈ {TRADING_DISABLED, EMERGENCY} |
| 2 | `portfolio_status` | portfolio não `active` ou agente não `enabled` |
| 3 | `data_quality` | market data `degraded` ou último preço > 10 s |
| 4 | `signal_validity` | sinal expirado/invalidado; stop no lado errado; entry fora de ±0,5 % do preço atual |
| 5 | `stop_distance` | fora de `[min_stop_distance_pct, max_stop_distance_pct]` |
| 6 | `daily_loss` | perda do dia ≥ `max_daily_loss_pct` |
| 7 | `drawdown` | drawdown ≥ `max_drawdown_pct` (também aciona `TRADING_DISABLED` no portfolio) |
| 8 | `concurrent_positions` | abertas ≥ `max_concurrent_positions` |
| 9 | `duplicate_position` | já existe posição aberta no mesmo mercado e direção neste portfolio |
| 10 | `liquidity` | `quote_volume_24h` < `min_liquidity_usd_24h` |
| 11 | `spread` | `spread_pct` > `max_spread_pct` |
| 12 | `sizing` | tamanho calculado < `min_notional` do mercado |
| 13 | `position_size` | notional > `max_position_pct × equity` (após sizing, deve passar por construção; registrado) |
| 14 | `total_exposure` | exposição + notional > `max_total_exposure_pct × equity` |
| 15 | `asset_exposure` | por base asset |
| 16 | `exchange_exposure` | por exchange |
| 17 | `correlation` | posições correlacionadas na mesma direção ≥ `max_correlated_positions` |
| 18 | `slippage_estimate` | walk do book para o tamanho > `max_slippage_pct` |
| 19 | `leverage` | notional / cash disponível > `max_leverage` |
| 20 | `cash` | margem necessária > cash disponível |

## 4. Sizing

```
risk_usdt        = equity × risk_per_trade_pct × regime_multiplier × ks_multiplier
stop_distance    = |entry_ref − stop| / entry_ref
qty_by_risk      = risk_usdt / (entry_ref × stop_distance)
qty_by_position  = (max_position_pct × equity) / entry_ref
qty_by_exposure  = ((max_total_exposure_pct × equity) − exposure_notional) / entry_ref
qty_by_asset     = ((max_asset_exposure_pct × equity) − exposure_by_asset[base]) / entry_ref
qty_by_exchange  = idem por exchange
qty_by_cash      = (cash_available × max_leverage) / entry_ref
qty              = floor_to_step(min(todos), step_size)
```

`ks_multiplier` = 1.0 em `ACTIVE`, 0.5 em `WARNING`. `entry_ref` = meio da `entry_zone` ou último preço se dentro da zona. A decisão registra cada limitante e qual venceu (`sizing.binding_constraint`), para a frase "Risk Engine permite posição máxima de 1,2 %".

## 5. Kill switch

Escopos: **sistema**, **organização**, **portfolio**. Estado efetivo = máximo pela ordem `ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY`.

| Estado | Entradas | Saídas | Gestão de posições | Quem aciona |
|---|---|---|---|---|
| `ACTIVE` | permitidas | normais | normal | — |
| `WARNING` | permitidas com tamanho × 0.5 | normais | normal | automático (perda do dia ≥ 70 % do limite; drawdown ≥ 70 %); manual |
| `TRADING_DISABLED` | bloqueadas | permitidas (stops, alvos, manual) | normal | automático (limite de perda/drawdown atingido; dado degradado > 5 min em posição); manual |
| `EMERGENCY` | bloqueadas | permitidas; fechamento automático **somente** se `auto_close_on_emergency` | só saídas | manual (OWNER/ADMIN ou operador) |

Transições automáticas para cima são imediatas. Transições para baixo são sempre manuais e auditadas (`kill_switch_transitions`), exceto `WARNING → ACTIVE` que pode ser automática no início do próximo dia UTC se as condições sumiram. Cada transição publica `kill_switch.changed`; strategy e execution workers reagem em < 1 s. Workers também releem o estado do Redis a cada 10 s (defesa contra evento perdido).

## 6. Risk events

Tipos v1: `limits_changed`, `proposal_rejected`, `daily_loss_warning`, `daily_loss_limit`, `drawdown_warning`, `drawdown_limit`, `exposure_limit`, `data_degraded_in_position`, `kill_switch_changed`, `stop_slippage_excess` (fill de stop com slippage > 2× o esperado), `position_stale_price`. Severidade `info | warning | critical`. `critical` gera notificação in-app aos OWNER/ADMIN e evento no Sentry.

## 7. Garantias

- Nenhum caminho de código cria `orders` sem `proposal_id` com `risk_decision.approved = true`, exceto ordens de **saída** (stop, alvo, fechamento manual, kill switch), que são sempre permitidas.
- Ordem manual paper (M3) também gera uma `trade_proposal` (agent_id nulo, `actor=user`) e passa pelos mesmos checks.
- O Risk Engine nunca chama rede nem banco: tudo que precisa é passado como argumento, o que o torna testável com tabelas de casos e reutilizável no backtest.
- LLM não tem acesso ao Risk Engine nem aos limites.
