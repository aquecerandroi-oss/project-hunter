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

> **Corrigido em 2026-09-06 (ADR 0005).** A carteira do dono no M3 não segue os passos 3 e 4: ela é **uma só, permanente, aberta com R$100.000 convertidos em USDT** ao câmbio registrado na abertura, com o perfil `paper_v1` (não `conservative`/`balanced`/`aggressive`), sem aporte e sem reset. O fluxo de onboarding acima continua descrevendo o produto para outros usuários; a carteira principal de um workspace é única por escopo e não pode ser recriada para recomeçar.

## 4. Navegação (registro único, com milestone de disponibilidade e estado real)

**Estado real**, além do milestone nominal, porque o M3 antecipou dado (schema, API) de páginas que
o roadmap original só previa mais adiante (T3.25, `.claude/state/brief-T3.25-pages-with-real-data.md`,
2026-09-08): "implementada" (tela renderiza dado real em produção/VPS), "dado real, tela pendente"
(API e schema existem, a tela ainda mostra "Planejado"), "planejada" (nem dado nem tela).

| Item | Rota | Milestone nominal | Estado real (2026-09-08) |
|---|---|---|---|
| Dashboard | `/dashboard` | M0 (shell), M5 (completo) | implementada (shell) |
| Radar | `/radar` | M2 | implementada — score com teto de 25/100 por evidência insuficiente, ver `docs/reports/M2.md` |
| Markets | `/markets` | M1 | implementada |
| Opportunities | `/opportunities` | M2 | implementada |
| Portfolio | `/portfolio` | M3 | implementada — dado real na VPS (carteira `ever`, USDT/BRL, kill switch) |
| Lab (Shadow Lab) | `/lab` | fora do roadmap original (S2–S4) | implementada — placar, curva de R acumulado, tabela em dinheiro (T3.16–T3.18) |
| Trades | `/trades` | M3 | dado real (API de posições/ordens/trades da carteira, T3.8a), tela reaproveitando o formato da carteira dispatada na T3.25 (Parte B, não executada ainda) |
| Strategies | `/strategies` | M6 | dado real (catálogo com propósito/veredito/linhagem desde `0010`–`0012`), tela e endpoint próprio despachados na T3.25 (não executados) |
| Backtests (replay) | `/backtests` | M6 | dado real (`replay_runs`, `0013`, **ainda não aplicada em nenhum stack** — ver `docs/reports/M3.md`), tela despachada na T3.25 (não executada) |
| Risk Center | `/risk` | M4 | dado real (`RiskLimits`/`portfolio_risk_state` já existem e são a fonte única, `docs/RISK_ENGINE.md` §2), endpoint numérico e tela despachados na T3.25 (não executados) |
| Agents | `/agents` | M4 | planejada — a ponte sinal→proposta existe (T3.14) mas não há nenhuma linha em `agents`; ver `docs/ROADMAP.md` M4 |
| Agent Arena | `/arena` | M6 | planejada |
| Analytics | `/analytics` | M5 | planejada |
| Intelligence | `/intelligence` | Fase 2 | planejada |
| Exchanges | `/exchanges` | Fase 3 | planejada |
| Alerts | `/alerts` | Fase 2 | planejada |
| System | `/system` | M0 | implementada — inclui heartbeat do execution-worker e do coletor spot dedicado desde o M3 |
| Settings | `/settings/*` | M0 (profile, organization, members, security, appearance); M4 (risk defaults); M5 (notifications); Fase 2 (api); Fase 3 (billing) | implementada (M0); demais planejadas |

### 4.1 Lab, replay e replicação — o que o usuário vê antes de qualquer coisa virar dinheiro

A tela `/lab` mostra o Shadow Lab: um placar por versão de estratégia (veredito
inconclusiva/validada/reprovada pela régua de 100 resultados e 30 dias, `docs/plans/SHADOW-LAB.md`
§9), a curva de resultado simulado acumulado e a tabela de sinais em termos de dinheiro (entrou,
saiu, variação, resultado simulado pela régua de 0,25 % da própria carteira paper). Nada ali é
carteira: todo sinal do Lab nasce `research_only` e a ponte de execução recusa esse rótulo pelo
nome antes de qualquer outra checagem (`docs/PIPELINE.md` §7). Duas camadas de evidência adicional,
sem tela própria ainda (T3.25 despacha os endpoints, não as telas):

- **Replay histórico** — a mesma decisão do caminho vivo rodada sobre velas já persistidas, para
  acumular evidência sem esperar o calendário passar. Rótulo `replay` sempre visível ao lado do
  número; nunca conta para a régua de maturidade. Detalhe: `docs/PIPELINE.md` §6c.
- **Replicação** — quando uma versão fica `validada`, o protocolo cria dez "irmãs" de parâmetro e
  testa se o resultado sobrevive a variação, metade de mercado e reamostragem. Veredito
  `real`/`refutada`/`replicando`; nunca ativa, deprecia ou reparametriza nada sozinho — só o
  Everton, pelo script de ativação auditado. Detalhe: `docs/plans/REPLICATION.md`.

### 4.2 Meta diária

Everton fixou (2026-09-10) um lucro mínimo diário de R$9.000 para o Lab. `GET
/api/v1/orgs/{org_id}/lab/daily-goal` (T3.78) responde, todo dia, com dado real, o quanto falta e
por quê: `unique_r` (a família inteira como uma carteira, uma aposta por `(mercado, barra)` — a
mesma dedupe da T3.60) contra `pooled_r` (a soma bruta de todas as versões, o "barulho" que a T3.60
mediu em 3–4×); e o valor de **1 R** em duas réguas lado a lado — o `label_brl` do onboarding
(0,25 % × R$100.000 = R$250) e o `real_brl_p10/p50/p90`, calculado dos volumes de 1 minuto reais dos
mercados apostados sob o teto de participação (`hunter_risk.limits.PAPER_V1`), que é a régua que
paga a conta. A tela ainda não existe (T3.78 entrega só a API); o schema congelado está em
`.claude/state/notes-T3.78.md`.

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
