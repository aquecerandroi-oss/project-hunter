---
tags: [trading, risco, m3]
updated: 2026-09-08
status: implementado e rodando na VPS — o execution-worker roda o ciclo inteiro e reporta em hb:execution:paper; a ponte sinal → admissão continua desligada e o aceite operacional da autonomia (T3.29) tem cinco itens não medidos
owner: sexta-feira
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

## Status — atualizado no plantão da manhã de 2026-09-07 (11:10Z)

**A frase que governava esta página deixou de ser verdade.** Até a madrugada de hoje ela dizia
"nenhum worker chama `evaluate`". Agora chama: o **`execution-worker` existe** (T3.5, `7ecafd2`;
revisão do guardião em `7091a16`; correções em `12edda3`) e roda o ciclo inteiro — admissão de
pedido arquivado decidido **na própria linha**, ciclo de ordem aplicando o `ExecutionReport` **por
fill numa transação só** (ordem, fills, posição com taxa em ativo base descontada, trade, caixa,
consumo de participação, reserva consumida e as **intenções de stop e alvo criadas ali dentro**, de
modo que nunca existe posição sem proteção durável), ciclo de proteção sob a trava sistema →
organização → carteira, marcação a mercado **antes** do kill switch, expiração de reserva,
recuperação após restart, heartbeat e `/ready` com sete verificações. Idempotente por
`execution_key`; nada em memória é fonte da verdade.

**A prova, de ponta a ponta, 30 minutos no stack local (06:57–07:27Z, saída 0):** ordem manual
aprovada com quantidade 18,518 e limite ativo `risk_per_trade` → fill a 100,01 com taxa 0,018518 em
ativo base → posição 18,499482 com stop 97,5 → salto sintético para 95,00 → **primeira saída
degradada** (ordem escrita, sem fill inventado) → segunda tentativa 18,499 @ 95,00 com deslize de
256,41 bps → caixa 19.903,662415 + pó 0,04579 = patrimônio **19.903,708205, idêntico no heartbeat e
no último ponto da curva** → `trades.pnl = −96,28938018` = bruto −92,679990 menos custos 3,60939018
**contados uma vez só** → 30 pontos de 1 min, **0 exceções**.

**A ponte sinal → admissão existe e está desligada** (T3.14, `12edda3`), e há duas travas
independentes: `ENABLE_PAPER_AUTONOMY=false` por padrão — e com ela falsa a ponte **nem cria o grupo
de consumo** —, e, mesmo se ligada, **todo sinal do Lab hoje é `research_only`**, propósito que a
ponte recusa. Nada é admitido até que exista uma `strategy_version` ativada com propósito de paper,
e essa ativação é **decisão do Everton**, num ato auditado.

**O que falta agora, e é uma lista curta e nomeada:**

| Tarefa | O que entrega | Estado |
|---|---|---|
| **T3.5c** | Assentamento do pó (vender o resíduo quando passar do mínimo); `kill_switch.changed` também na retomada pela API; fechar o dedupe com a suíte de integração | **em voo** |
| **T3.0c / T3.0d** | Ingestão spot no `market-worker` (T3.0c, **em voo**) e os quatro itens da revisão da T3.0b (T3.0d) — entre eles o **bloqueante**: o `event_id` do candle não inclui `market_type`, e com spot ligado o segundo candle do mesmo minuto é descartado em silêncio | **em voo / a fazer** |
| **T3.9b** | As verificações restantes das nove da diretiva (V1/V2/V3 e §11 já feitas em `eccb648`) — **o portão do milestone** | a fazer |
| **T3.10** | Runbook de ativação (a ordem: versão com propósito de paper → linha `agents` habilitada → bandeira) e os quatro itens da revisão da T3.14 | a fazer |
| **Deploy na VPS** | Um comando (`MARKET_SHARDS=4 bash infra/vps/compose.sh update`), mas recria a rede e aplica `0008` + `0009` num banco com a carteira permanente. **Não antes da T3.9** | pendente |

*(A leitura abaixo é do plantão de 04:50Z e fica preservada — a tabela "o que existe" continua
válida e ganhou as linhas do execution-worker.)*

## Status — leitura de 2026-09-07 04:50Z (preservada)

**Todas as peças existem, nenhuma roda sozinha ainda.** Entre 2026-09-06 e 2026-09-07 o M3 saiu de
"núcleo puro sem integração" para "carteira aberta em produção, motor completo e nenhum processo que
o acione". O que falta é o **`execution-worker` (T3.5)** — é ele que transforma um conjunto de
funções corretas num sistema que decide. *(Superado às 11:10Z: o worker existe e foi provado.)*

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
| **`execution-worker` (T3.5 + T3.5b)** | `services/execution-worker` (25 módulos, nenhum acima de 350 linhas) | **implementado e provado** (`7ecafd2`, `12edda3`) — prova de 30 min com saída 0, dois bloqueios do guardião fechados |
| Modelo de papéis no banco (T3.1c/T3.1d) — `0007` + `0008` | `infra/migrations` | **implementado** (`2688ef1`, `c1f8c5f`): a API perde escrita em `orders`/`fills`/`positions`/`trades`, a carteira nasce auditada, o motivo do kill switch não se reescreve sem transição |
| Geometria do pedido e o pó como coluna (T3.1e) — `0009` | `infra/migrations` | **implementado** (`70acb6f`): `trade_proposals.request_payload`, `positions.is_residual` |
| Heartbeat e runbook do worker (T3.13) | `apps/api`, `docs/DEPLOYMENT.md` | **implementado** (`7557368`) — onze campos reais em `/system/workers`, nenhum inventado |
| Tela `/system` mostrando o worker | `apps/web` | **implementada** (`509e4d8`) — nulo é "indisponível", nunca zero |
| Ponte sinal → admissão (T3.14) | `services/execution-worker` | **implementada e desligada** (`12edda3`) — `ENABLE_PAPER_AUTONOMY=false` e todo sinal do Lab é `research_only` |
| Verificações V1/V2/V3 e §11 da diretiva (T3.9a) | `tests/integration/paper` | **implementadas** (`eccb648`) — todo número lido de volta do banco; três divergências registradas como `xfail` estrito, sem ajustar número |

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

**Sete itens em [[Open Bugs]] eram condições escritas destas tarefas** (revisão adversarial de
`.claude/state/review-T3.1b-T3.6-T3.12.md`). **Na manhã de 2026-09-07, três caíram** — admissão do
lado da API (`7ecafd2` + `70acb6f`), `kill_switch.changed` (`7ecafd2`, com a metade da retomada ainda
aberta) e o escopo antigo nos docs (`2ee79c1`) —, o dedupe está corrigido no código e **em
observação** até a T3.5c aterrissar, e o **teto do pico sem `resolution='1m'` foi reconfirmado
aberto**: nem a `0008` nem a `0009` o levaram. Doze itens novos entraram, e os quatro da revisão da
T3.14 são **condições para ligar a autonomia**, não defeitos do que roda.

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
> foram provados. ~~**O que continua verdadeiro é a frase que importa: nenhum worker chama
> `evaluate`.**~~ **Superado de novo em 2026-09-07 às 11:10Z: o `execution-worker` existe, chama
> `evaluate` e foi provado por 30 minutos com saída 0.** A lista atual do que falta está na tabela do
> Status no topo da página (T3.5c, T3.0c/T3.0d, T3.9b, T3.10 e o deploy na VPS).

Continua valendo a regra de ouro (`CLAUDE.md`): **nenhum agente executa ordens** — todo caminho de
entrada é AGENTE → PROPOSTA → RISK ENGINE → EXECUÇÃO —, e o `risk-engine-guardian` (opus) é revisor
obrigatório de qualquer diff nesses caminhos. Contrato normativo: `docs/RISK_ENGINE.md` **v2.1**.

## Pré-requisitos efetivos da autonomia paper — atualizado em 2026-09-08 (revisão da Astra)

**Sinal paper não é execução paper.** A linha `momentum v3` com `purpose = paper` está ativa desde
**02:57 de Brasília de 2026-09-08** e já emitiu **154 sinais**; a carteira registrou **0 propostas, 0
posições, 0 trades**, porque a ponte está desligada. Medir sinais **não** mede o Risk Engine em
serviço: enquanto a chave estiver `false`, `evaluate` nunca é chamado por um sinal do Lab, e a metade
da hipótese que passa pela carteira continua sem contrafactual ([[EXP-0005-momentum-paper]]).

A revisão [[2026-09-08-shadow-lab-pronto]] derrubou a ideia de que faltavam **quatro** condições:
são **sete**, e a maioria está **não medida**. A tabela completa, com o estado e o arquivo:linha de
cada uma, está em [[Execution Engine]]; o aceite é o brief
`.claude/state/brief-T3.29-autonomy-acceptance-run.md`. Em resumo, o que toca este motor:

- **Admissão** — o vínculo em `agents` precisa existir **habilitado** para a versão e a carteira
  certas; ativar a `strategy_version` não basta (**não medido**).
- **MTM antes do kill switch** — hoje o check `mtm_fresh` prova que **houve escrita**, não que o
  preço é atual: fita parada com snapshot renovado deixa o kill switch avaliando patrimônio velho
  com o painel verde. O aceite passa a exigir `mark_quality` (**não medido**).
- **Proteção** — `pending_degraded` registra a intenção, e a posição segue exposta; falta a prova de
  recuperação após restart, sem venda duplicada (**não medido**).
- **β indisponível em 100% dos mercados** — enquanto o BTC (a referência) não tiver 20 dias
  contíguos, o check `correlation` recusa por `beta_unavailable` e nenhuma proposta passaria de
  qualquer forma. Ver [[Open Bugs]].

**Nada disto é defeito comprovado em produção** — é cenário nomeado que ninguém verificou, e é por
isso que `ENABLE_PAPER_AUTONOMY` continua `false`. Ligar é decisão do Everton, depois de todas as
linhas verdes.

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

**A trava agora sobrevive ao reinício** (`9a0ac45`): `evaluate_and_persist` compara a avaliação pura com a trava gravada e escreve a transição auditada (de, para, motivo, evidência, ator) **na mesma transação** que muda `portfolios.kill_switch_state` e `portfolio_risk_state`. O AVISO só sai na virada do dia em `America/Sao_Paulo` e só com os **dois** gatilhos eliminados; o BLOQUEADO **nunca** sai sozinho; a retomada é recusada enquanto a avaliação automática ainda bloqueia e **não** redefine pico nem perdas. Um `UPDATE` cru da trava é recusado pelo banco.

**Atualizado em 2026-09-07 (manhã) — as duas pendências desta seção mudaram de estado.** A retomada
pela API **passou a exigir OWNER** (`2688ef1`, T3.1c aplicada), e o `kill_switch.changed`
**passou a ser publicado pelo `execution-worker`** (`7ecafd2`), que relê a trava a cada 10 s e dentro
de cada transação de efeito — o que destravou isso foi a `0007` dar ao papel do motor `INSERT` em
`outbox_events`. **Fica a metade menor:** a retomada pela API ainda **não** publica
(`routers/risk.py:180` chama `resume()` sem `publish=True`), então a tela pode mostrar BLOQUEADO por
mais um ciclo de poll depois de o Everton destravar. Está em [[Open Bugs]] como MEDIUM, dono T3.5c.
Na VPS hoje: `kill_switch_state = ACTIVE`, **0** transições registradas.

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

[[Execution Engine]] · [[Agents Overview]] · [[Portfolio]] · [[Paper Trading]] · [[Strategy Backlog]] · [[Architecture Decisions]] (regra "nenhum agente executa") · [[Changelog]] · [[Open Bugs]] · [[Dialogos/M3]] · [[2026-09-08-shadow-lab-pronto]] · [[EXP-0005-momentum-paper]]

## Fontes

`docs/RISK_ENGINE.md` (**v2.2**), `docs/PIPELINE.md` §7 e §1c, `docs/DATABASE.md` §18, `CLAUDE.md` ("Hard rules"), `docs/ROADMAP.md` e `docs/plans/M3.md` (Milestone 3), `.claude/state/notes-T3.2-risk-core.md`, `.claude/state/review-T3.2-risk-core.md`, `.claude/state/review-T3.1-security.md`, `.claude/state/review-T3.3-T3.4.md`, `.claude/state/review-T3.1b-T3.6-T3.12.md`, `.claude/state/decisions-M3-delegated-2026-09-06.md`, `.claude/state/brief-T3.1c-grants-roles.md`, `.claude/state/brief-T3.5-execution-worker.md`
