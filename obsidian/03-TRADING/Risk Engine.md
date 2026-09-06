---
tags: [trading, risco, m3]
updated: 2026-09-06
status: parcial — núcleo implementado (T3.2/T3.2b), sem integração
---

# Risk Engine

> **Atualizado em 2026-09-06 — leia isto antes do resto da página.** A diretiva do Everton (ADR 0005,
> [[Dialogos/M3]]) trouxe o Risk Engine para o **Milestone 3** e substituiu o contrato: vale
> `docs/RISK_ENGINE.md` **v2**, com o perfil `paper_v1` (0,25 % por operação com custos dentro, 1 %
> agregado, 1 % de participação do minuto, 40 % total, 10 % por moeda, 5 posições, β-BTC 0,5×, kill
> switch 1 %/4 % e 2 %/8 % com o dia em `America/Sao_Paulo`, SPOT sem alavancagem, piso de 50 M). Os
> presets Conservative/Balanced/Aggressive descritos abaixo **continuam existindo e não são o perfil
> da carteira** — e a medição da rodada 8 mostrou que neles o `risk_per_trade_pct` nunca chegava a
> atuar. Plano: `docs/plans/M3.md`. Ver [[Portfolio]], [[Paper Trading]], [[Execution Engine]],
> [[Strategy Backlog]].

**Atualização de 2026-09-06 (T3.2b).** O núcleo puro (`packages/risk-core`) implementa hoje as
invariantes que a v2 já prometia e uma revisão adversarial (`bf4924b` → `5f86028`, 204 testes) provou
faltarem: `entry_ref` confrontado com o preço observado (banda `max_entry_deviation_pct = 0,5 %`),
sizing pelo pior entre `entry_ref` e o preço observado (`sizing_price`), idade máxima do volume
aplicada (`max_volume_age_s = 120 s`), caixa líquido das reservas pendentes (`available_cash`), e
`evaluate_exit` provado funcionando sem `PortfolioState` (restart após a meia-noite de São Paulo). O
contrato normativo passa a ser **`docs/RISK_ENGINE.md` v2.1**; nenhum limite do Everton mudou. Decisão
registrada em `docs/decisions/0005-carteira-virtual-e-risk-engine-paper-v1.md`.

## Status

**Núcleo implementado, nada integrado — Milestone 3 em andamento** (o Risk Engine era do M4 até
2026-09-06; ADR 0005 o trouxe para o M3).

**O que existe hoje, no commit `bf4924b` → `5f86028` (2026-09-06):** `packages/risk-core`
(`hunter_risk`) é um pacote **puro** — onze módulos, sem IO, sem rede, sem banco e **sem relógio**
(o instante é `portfolio.as_of`), com `Decimal` em toda linha; o modelo **recusa `float` na
construção**. Estão implementados e testados (**204 testes**):

| Peça | Estado |
|---|---|
| `RiskLimits` com o preset `PAPER_V1` congelado e validação de coerência | implementado |
| `PortfolioState` (posições abertas, reservas pendentes, exposição por ativo e por β-BTC, início do dia em `America/Sao_Paulo` validado contra o `as_of`, pico monotônico) | implementado |
| Kill switch — `assess` / `most_restrictive` / `entry_size_multiplier` / `resume` com autorização casada, ordenação por dicionário | implementado (núcleo puro) |
| Sizing como **mínimo de nove tetos**, com `binding_constraint` e dois contrafactuais, arredondamento sempre para baixo | implementado |
| `evaluate` (checks em ordem, todos registrados mesmo depois da primeira reprovação) e `evaluate_exit` (provado sem `PortfolioState`) | implementado |
| `beta_v1` — β contra o BTC com validade e motivos de invalidade (`da2fb49`, T3.7) | implementado, **sem tabela** (`market_betas` é proposta, não migração) |

**As invariantes que a revisão adversarial provou faltarem estão fechadas** (`5f86028`, contrato
v2.1 em `faabe3d`): perda do dia derivada do patrimônio e não de campos opcionais; `entry_ref`
confrontado com o preço observado dentro de ±0,5 %; sizing pelo pior entre referência e preço
observado; idade máxima do volume aplicada (120 s); caixa líquido das reservas pendentes; `resume()`
recusado enquanto os gatilhos automáticos mordem. Cada uma tem o cenário numérico que a motivou
escrito no contrato.

**O que ainda não existe — e é por isso que o motor não decide nada em produção hoje:** nenhum
worker chama `evaluate`, não há carteira virtual persistida, não há proposta, não há execução, e o
kill switch **durável** (a trava, a transição auditada, a autenticação) é da T3.6 — sem ela, um
`assess` volta sozinho para `ACTIVE` no ciclo seguinte. Faltam **T3.3 a T3.14** do plano
(`docs/plans/M3.md`): contabilidade da carteira e reconciliação diária (T3.3), repositórios e
persistência da decisão (T3.4/T3.5), kill switch durável (T3.6), β persistido e recalculado (T3.8),
telas (T3.9–T3.11), e a ponte sinal → proposta atrás de `ENABLE_PAPER_AUTONOMY=false` (T3.14).

Continua valendo a regra de ouro (`CLAUDE.md`): **nenhum agente executa ordens** — todo caminho de
entrada é AGENTE → PROPOSTA → RISK ENGINE → EXECUÇÃO —, e o `risk-engine-guardian` (opus) é revisor
obrigatório de qualquer diff nesses caminhos. Contrato normativo: `docs/RISK_ENGINE.md` **v2.1**.

## Contrato (implementado como função pura em `packages/risk-core`)

`evaluate(proposal, portfolio_state, limits, market_liquidity, kill_switch) -> RiskDecision`. Função **pura e determinística** — sem IO, sem chamada de rede ou banco — testável com tabelas de casos e reutilizável no backtest (M6). LLM não tem acesso ao Risk Engine nem aos limites.

## Limites planejados (por preset de `risk_profiles.limits`)

| Chave | Conservative | Balanced | Aggressive |
|---|---|---|---|
| `max_position_pct` | 0.02 | 0.05 | 0.10 |
| `risk_per_trade_pct` | 0.0025 | 0.005 | 0.01 |
| `max_total_exposure_pct` | 0.30 | 0.60 | 1.00 |
| `max_daily_loss_pct` | 0.01 | 0.02 | 0.04 |
| `max_drawdown_pct` | 0.05 | 0.10 | 0.20 |
| `max_concurrent_positions` | 3 | 6 | 12 |
| `max_leverage` | 1 | 2 | 3 |

Tabela completa (13 chaves) em `docs/RISK_ENGINE.md` §2.

## Checks (20, em ordem, todos registrados mesmo após o primeiro reprovado — implementados em `hunter_risk.evaluate` desde `bf4924b`)

`kill_switch` → `portfolio_status` → `data_quality` → `signal_validity` → `stop_distance` → `daily_loss` → `drawdown` → `concurrent_positions` → `duplicate_position` → `liquidity` → `spread` → `sizing` → `position_size` → `total_exposure` → `asset_exposure` → `exchange_exposure` → `correlation` → `slippage_estimate` → `leverage` → `cash`.

## Kill switch (núcleo implementado, 3 escopos; a trava durável e a transição auditada são da T3.6)

Sistema, organização, portfolio; estado efetivo = mais restritivo entre os três (`ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY`). `WARNING` reduz tamanho pela metade; `TRADING_DISABLED`/`EMERGENCY` bloqueiam toda entrada nova; saídas (stop, alvo, fechamento manual) são sempre permitidas. `SYSTEM_KILL_SWITCH=ACTIVE` já existe em `.env.example` como flag de sistema, acionável sem redeploy — mas hoje não há nenhum worker lendo esse valor para agir sobre ele.

## Testes

**Feitos — 204 no núcleo** (`bf4924b` + `5f86028`): tabela de casos por check (cada um aprovando e
reprovando isoladamente), kill switch por escopo, propriedades sobre o sizing, e **cada cenário
numérico da revisão adversarial virado em teste** (a carteira em 19 500 contra abertura de 20 000, o
`entry_ref` de 100 com o mercado a 110, o volume de 45 minutos, o caixa 500 com 400 reservados).
Mutação usada como controle: arredondar para cima → 20 falhas; multiplicador do AVISO = 1 → 8
falhas. **Faltam:** o pipeline de integração candle → sinal → proposta → fill paper (depende de
T3.3–T3.5) e os testes da trava durável (T3.6).

## Relacionadas

[[Execution Engine]] · [[Agents Overview]] · [[Portfolio]] · [[Paper Trading]] · [[Strategy Backlog]] · [[Architecture Decisions]] (regra "nenhum agente executa") · [[Changelog]] · [[Open Bugs]] · [[Dialogos/M3]]

## Fontes

`docs/RISK_ENGINE.md` (v2.1), `docs/PIPELINE.md` §7, `CLAUDE.md` ("Hard rules"), `docs/ROADMAP.md` e `docs/plans/M3.md` (Milestone 3), `.claude/state/notes-T3.2-risk-core.md`, `.claude/state/review-T3.2-risk-core.md`
