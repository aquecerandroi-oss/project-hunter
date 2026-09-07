---
tags: [trading, risco, m3]
updated: 2026-09-07
status: parcial — núcleo, schema, ledger, simulador, kill switch durável e admissão implementados; falta o worker que faz tudo isso rodar (T3.5)
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

## Status — atualizado no plantão de 2026-09-07 04:50Z

**Todas as peças existem, nenhuma roda sozinha ainda.** Entre 2026-09-06 e 2026-09-07 o M3 saiu de
"núcleo puro sem integração" para "carteira aberta em produção, motor completo e nenhum processo que
o acione". O que falta é o **`execution-worker` (T3.5)** — é ele que transforma um conjunto de
funções corretas num sistema que decide.

### O que existe hoje, com o commit e a prova

| Peça | Onde | Estado |
|---|---|---|
| Núcleo puro `hunter_risk` — 20 checks, sizing como mínimo de nove tetos, kill switch, β | `packages/risk-core` | **implementado** (`bf4924b` → `5f86028`, 204 testes) |
| Contrato normativo | `docs/RISK_ENGINE.md` **v2.2** | `faabe3d` (v2.1) → `8c53b30` (v2.2): o perfil do banco é **literalmente** `PAPER_V1` serializado, ida e volta provada |
| Schema da carteira — `0006_paper_wallet` | `infra/migrations` | **implementado e aplicado na VPS** (`11faba8`, corrigido em `296f3c1`); `alembic_version = 0006_paper_wallet` |
| Ledger, abertura com âncora de câmbio, `PortfolioState` | `hunter_core.portfolio` | **implementado** (`8a6a69f`, `d23b7bd`) |
| Simulador de execução paper | `hunter_core.execution` | **implementado** (`edd5d7e`, `ec78727`) |
| Kill switch **durável** com transição auditada | `hunter_core.risk` + API | **implementado** (`9a0ac45`) |
| Serviço de admissão único (proposta → decisão → reserva → auditoria → outbox, atômicos) | `hunter_core.admission` | **implementado** (`ae2657d`) |
| β contra o BTC (`beta_v1`, T3.7) | `packages/indicators` | implementado como pacote puro (`da2fb49`); `market_betas` existe no banco e está **vazia** (0 linhas na VPS) |
| Adaptador SPOT da Binance (T3.0a) | `packages/exchange-adapters` | **implementado, lado do adaptador só** (`078d6ef`) |
| Coletor de câmbio USDTBRL (T3.11a) | `services/market-worker` | **implementado e no ar na VPS** (`09eb6de`) — uma observação por minuto no shard 0 |
| API de leitura da carteira (T3.8a) + tela (T3.8b) | `apps/api`, `apps/web` | **implementadas** (`9a0ac45`, `817f129`, `096d8c5`) |

**Três invariantes que valem repetir porque foram provadas contra o banco, não contra um mock:** um
`UPDATE` cru do kill switch é **recusado pelo Postgres**; a trava exige que a **última** transição do
escopo case com o movimento **e** tenha sido escrita pela transação corrente (`xmin =
pg_current_xact_id()`), de modo que uma transição antiga ou forjada não destrava nada; e a carteira
principal é única **por organização**, então um workspace novo não compra outros R$100.000.

### O que falta — e é isto que impede o motor de decidir qualquer coisa hoje

| Tarefa | O que é | Por que trava |
|---|---|---|
| **T3.5 — `execution-worker`** | O processo que junta tudo: ciclo de admissão, ciclo de ordem aplicando o `ExecutionReport` por fill, ciclo de proteção, marcação a mercado **antes** do kill switch, expiração de reserva sob a mesma trava, recuperação após restart, heartbeat e readiness | **Nenhum processo chama `evaluate` hoje.** Sem ele, admissão, ledger, simulador e kill switch são bibliotecas corretas que ninguém executa. Brief em `6c60653` + as cinco condições em `3519107` |
| **T3.1c — modelo de papéis (grants sobre a `0006`)** | Worker decide e grava estado de risco; API pede, lê e autoriza pessoas; retomada exige **OWNER** | Enquanto não entrar, a admissão do lado da API roda como `hunter_app` e o `kill_switch.changed` não pode ser publicado. É pré-requisito da T3.5 |
| **T3.0b/T3.0c — integração SPOT** | `market_type` nos modelos de evento, nas chaves do Redis e nos leitores de hot state; ingestão spot no `market-worker`; hold durável de posições e intenções | Declarado como bloqueio pela própria T3.0a: spot e perpétuo de `BTCUSDT` dividiriam a mesma chave. **Sem preço spot ao vivo a carteira não pode operar** (decisão D1) |
| **T3.13 — integração operacional** | Papel no `RoleRegistry`, compose e Dockerfile do `execution-worker`, prontidão, métricas, visibilidade do atraso de proteção/MTM/outbox | Sem ela o worker existe no repositório e não sobe na VPS. **Nenhuma ativação de produção nesta tarefa** |
| **T3.14 — ponte shadow → admissão** | Consome `shadow.signals.emitted`, aplica elegibilidade, ordena pela D3 e submete **uma** proposta por ciclo | Atrás de `ENABLE_PAPER_AUTONOMY=false`, e **mesmo ligada nunca em produção antes do aceite da T3.9**. O M3 **não** declara modo autônomo |
| **T3.9 — as nove verificações da diretiva** | Tamanho/exposição/risco agregado; redução em AVISO; bloqueio sem desligar proteções; ordens simultâneas e fills duplicados; reconciliação; dado atrasado e reinício; mínimos da exchange; execução pior que o stop; ausência de fill fabricado | É o portão. Espec executável em `a88daac`, com seis decisões pendentes escritas |

**Sete itens em [[Open Bugs]] são condições escritas destas tarefas**, cinco deles da revisão
adversarial de `.claude/state/review-T3.1b-T3.6-T3.12.md`: dedupe casando pedido não decidido,
admissão do lado da API, teto do pico sem `resolution='1m'`, `docs/` com o escopo antigo da carteira
principal, e `kill_switch.changed` nunca publicado.

### Decisões tomadas pela Sexta-feira em nome do Everton (reversíveis por ele)

- **D1/D2/D3** (`.claude/state/decisions-M3-delegated-2026-09-06.md`): spot para executar e perpétuo
  para decidir, com basis por fill; participação de 1 % do minuto medida **no venue de execução**,
  com revisão marcada após 14 dias de paper; escolha entre sinais elegíveis por score do Radar →
  custo estimado em R → chegada mais antiga.
- **Modelo de papéis** (`.claude/state/brief-T3.1c-grants-roles.md`): **o worker decide e grava
  estado de risco; a API pede, lê e autoriza pessoas; a retomada do kill switch exige OWNER** — a
  diretiva diz "retomar somente com minha autorização", e TRADER não basta.

*(Contexto histórico preservado — o Risk Engine era do M4 até 2026-09-06; a ADR 0005 o trouxe para o
M3.)*

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

> **Superado em 2026-09-07 — mantido para registro.** O parágrafo desta seção dizia, em 2026-09-06,
> que "não há carteira virtual persistida, não há proposta, não há execução, e o kill switch durável
> é da T3.6". Nada disso vale mais: a `0006` está aplicada na VPS, a carteira do Everton está aberta
> (19.333,0111164813 USDT), o ledger, o simulador, o kill switch durável e a admissão existem e
> foram provados. **O que continua verdadeiro é a frase que importa: nenhum worker chama `evaluate`.**
> A lista atual do que falta está na tabela do Status acima (T3.5, T3.1c, T3.0b/T3.0c, T3.13, T3.14,
> T3.9).

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

## Kill switch — **durável desde `9a0ac45` (T3.6)**, 3 escopos

Sistema, organização, portfolio; estado efetivo = mais restritivo entre os três (`ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY`). `WARNING` reduz tamanho pela metade; `TRADING_DISABLED`/`EMERGENCY` bloqueiam toda entrada nova; saídas (stop, alvo, fechamento manual) são sempre permitidas. `SYSTEM_KILL_SWITCH=ACTIVE` já existe em `.env.example` como flag de sistema, acionável sem redeploy — mas hoje não há nenhum worker lendo esse valor para agir sobre ele.

**A trava agora sobrevive ao reinício** (`9a0ac45`): `evaluate_and_persist` compara a avaliação pura com a trava gravada e escreve a transição auditada (de, para, motivo, evidência, ator) **na mesma transação** que muda `portfolios.kill_switch_state` e `portfolio_risk_state`. O AVISO só sai na virada do dia em `America/Sao_Paulo` e só com os **dois** gatilhos eliminados; o BLOQUEADO **nunca** sai sozinho; a retomada é recusada enquanto a avaliação automática ainda bloqueia e **não** redefine pico nem perdas. Um `UPDATE` cru da trava é recusado pelo banco. **Duas coisas ainda faltam:** a transição **não publica `kill_switch.changed`** (o contrato exige reação < 1 s — [[Open Bugs]]), e a retomada pela API ainda exige TRADER, não OWNER (decidido na T3.1c, ainda não aplicado). Na VPS hoje: `kill_switch_state = ACTIVE`, **0** transições registradas.

## Testes

**Feitos — 204 no núcleo** (`bf4924b` + `5f86028`): tabela de casos por check (cada um aprovando e
reprovando isoladamente), kill switch por escopo, propriedades sobre o sizing, e **cada cenário
numérico da revisão adversarial virado em teste** (a carteira em 19 500 contra abertura de 20 000, o
`entry_ref` de 100 com o mercado a 110, o volume de 45 minutos, o caixa 500 com 400 reservados).
Mutação usada como controle: arredondar para cima → 20 falhas; multiplicador do AVISO = 1 → 8
falhas.

**Acrescentado em 2026-09-07:** os testes da trava durável **existem** (T3.6, `9a0ac45`: −1 % →
AVISO → −2 % → BLOQUEADO → recuperação no mesmo dia continua BLOQUEADO → retomada recusada e depois
aceita com o pico intacto; reinício encontra a mesma trava; duas avaliações concorrentes escrevem
uma transição), e com eles os do ledger (65 unit + 34 de integração), do simulador (132 unit) e da
admissão (17 + 10 + 6 de integração). **Falta:** o pipeline de integração candle → sinal → proposta →
fill paper, que depende da **T3.5**, e as **nove verificações da T3.9** — o portão do milestone.

## Relacionadas

[[Execution Engine]] · [[Agents Overview]] · [[Portfolio]] · [[Paper Trading]] · [[Strategy Backlog]] · [[Architecture Decisions]] (regra "nenhum agente executa") · [[Changelog]] · [[Open Bugs]] · [[Dialogos/M3]]

## Fontes

`docs/RISK_ENGINE.md` (**v2.2**), `docs/PIPELINE.md` §7 e §1c, `docs/DATABASE.md` §18, `CLAUDE.md` ("Hard rules"), `docs/ROADMAP.md` e `docs/plans/M3.md` (Milestone 3), `.claude/state/notes-T3.2-risk-core.md`, `.claude/state/review-T3.2-risk-core.md`, `.claude/state/review-T3.1-security.md`, `.claude/state/review-T3.3-T3.4.md`, `.claude/state/review-T3.1b-T3.6-T3.12.md`, `.claude/state/decisions-M3-delegated-2026-09-06.md`, `.claude/state/brief-T3.1c-grants-roles.md`, `.claude/state/brief-T3.5-execution-worker.md`
