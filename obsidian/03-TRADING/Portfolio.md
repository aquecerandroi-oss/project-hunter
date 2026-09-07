---
tags: [trading, portfolio, carteira, m3]
updated: 2026-09-07
status: implementado e aberto em produção — parado por falta do execution-worker (T3.5)
---

# Portfolio — a carteira paper permanente

## Status — atualizado no plantão de 2026-09-07 04:50Z

**A carteira existe de verdade.** Aberta na VPS às **2026-09-07T04:27:24.716469Z** pelo script
auditado `infra/scripts/open_paper_wallet.py`. Não é maquete, não é seed de teste: é a carteira
permanente da diretiva do Everton, com a taxa de câmbio que a converteu gravada e **imutável**.

| | Valor medido na VPS (somente leitura, 04:34Z) |
|---|---|
| `portfolio_id` | `01a07a1e-f6ae-7366-a7fe-ab3d9c83d488` |
| Nome / tipo | "Carteira paper principal" · `type=paper` · `status=active` · `is_arena=false` |
| Organização | `ever` (a do Everton) |
| Capital de origem | **R$ 100.000,0000000000** |
| Creditado | **19.333,0111164813 USDT** |
| Taxa da âncora | **5,1725** |
| Observação de câmbio usada | `01a07a1e-f670-7e58-aa71-b17b25e86efe` · par `USDTBRL` · fonte `binance.spot.ticker` · `observed_at 04:27:21.992Z` |
| Resíduo de conversão | **0,0000000005 BRL** — a fração que o `floor_10dp_v1` descartou, registrada e não evaporada |
| Âncora | **imutável**, uma linha, `anchored_at 04:27:24.716469Z` |
| Kill switch | `ACTIVE` · **0** transições registradas |
| Posições / β | **0** posições · **0** revisões em `market_betas` |
| Pontos de patrimônio | **1** (o da abertura) |
| Migração aplicada | `alembic_version = 0006_paper_wallet` |

O coletor de câmbio (T3.11a, `09eb6de`) está no ar: `fx_observations` foi de **2** para **3** linhas
entre 04:33Z e 04:34Z, todas `USDTBRL` a `5,1725`, uma por minuto, gravadas apenas pelo shard 0 do
`market-worker`.

**O que a carteira NÃO faz hoje, e é importante dizer:** ela não opera. Não existe
`execution-worker` (T3.5), a ponte sinal → proposta é do M4 (T3.14, atrás de
`ENABLE_PAPER_AUTONOMY=false`), e a admissão pelo lado da API vira erro 500 assim que os grants da
T3.1c entrarem — está em [[Open Bugs]]. A carteira está **parada, correta e visível**, e é exatamente
isso que ela deveria estar hoje.

## O que o Everton vê na tela

`/[org]/portfolio` (T3.8b, `817f129`; BRL na convenção brasileira em `096d8c5`): patrimônio em USDT e
em BRL, caixa, reservas, exposição e o `as_of` de cada leitura; a decomposição que a diretiva pediu —
**operacional** (a carteira ganhou ou perdeu operando) contra **cambial** (o dólar mexeu); cartão de
risco com o dia de negociação e o fuso, patrimônio de abertura, pico, perda do dia e drawdown, onde
nulo aparece como **"indisponível"** e nunca como `0 %`; kill switch efetivo com os três escopos, o
motivo e a última transição com evidência; curva de patrimônio com alternância USDT/BRL, e os pontos
sem BRL ficam como **buraco visível**, não interpolados; e tabelas de posições, ordens e trades com
estado vazio honesto. Sem carteira principal, a página **explica o comando do operador** em vez de
oferecer um botão que finja abrir uma.

## A contabilidade, em uma linha cada

- **Atribuição sobre o patrimônio, não sobre o caixa:** operacional `(E − E0)·F0`, cambial
  `E·(Ft − F0)`, identidade `total = E·Ft − E0·F0`.
- **Sem aporte e sem reset.** Uma varredura de AST sobre `packages/`, `apps/` e `services/` prova que
  não existe rota nenhuma — a diretiva virou teste (`8a6a69f`).
- **Capital fixo em R$100.000.** `open_paper_wallet` recusa qualquer outro valor sem um override
  explícito de teste, e o AST prova que nenhum módulo de produção o usa (`d23b7bd`).
- **Uma carteira principal por organização** (`296f3c1`, decisão D7). Antes era por workspace, e um
  workspace novo comprava outros R$100.000 — furo achado pelo `security-reviewer` e fechado no banco.
- **Banda de plausibilidade no câmbio:** `[1, 100]` para USDTBRL, mais uma comparação opcional com a
  última observação aceita (20 % em 600 s, com causalidade). `0,54321` é recusado; `5,4321` passa.
  A abertura é irreversível, então um erro de escala do coletor não pode nascer permanente
  (`d23b7bd`).
- **Long-only.** `mark_positions` recusa qualquer linha que não seja comprada — spot, sem
  alavancagem.

## O que falta para a carteira andar

| Tarefa | O que entrega | Estado |
|---|---|---|
| **T3.5 — `execution-worker`** | Ciclo de admissão, ciclo de ordem aplicando o `ExecutionReport` por fill, ciclo de proteção, MTM antes do kill switch, expiração de reserva sob a mesma trava, recuperação após restart | brief pronto (`6c60653` + 5 condições em `3519107`), **não implementado** |
| **T3.1c — grants e papéis** | Worker decide e grava estado de risco; API pede, lê e autoriza; retomada exige **OWNER** | decidido, **não aplicado** |
| **T3.0b/T3.0c — integração SPOT** | `market_type` nos eventos e nas chaves do Redis; ingestão spot no `market-worker`; hold durável | bloqueio declarado pela T3.0a, **não implementado** |
| **T3.13 — integração operacional** | Papel no `RoleRegistry`, compose e Dockerfile do worker, prontidão, métricas, visibilidade de atraso | **não implementado** |
| **T3.14 — ponte shadow → admissão** | Uma proposta por ciclo, atrás de `ENABLE_PAPER_AUTONOMY=false` | **não implementado**; nunca em produção antes da T3.9 |
| **T3.9 — as nove verificações** | O portão do milestone | espec executável em `a88daac`, **não executada** |

## Modelo (schema aplicado — `0006_paper_wallet`)

`portfolios`: `organization_id`, `workspace_id`, `name`, `type` (`paper|shadow|live`),
`base_currency` (USDT), `initial_capital`, `risk_profile_id`, `exchange_connection_id` (null no MVP),
`execution_config`, `status`, `kill_switch_state`, `is_arena`. Isolado por RLS como qualquer tabela
de tenant. Acrescentadas pela `0006`: `portfolio_currency_anchor` (imutável, uma por carteira),
`fx_observations` (global, imutável, **nunca apagada** nem em teardown de tenant), `market_betas`
(revisões imutáveis), `portfolio_risk_state` (referência diária em `America/Sao_Paulo` e pico
durável), `portfolio_exit_intents` (a intenção de proteção, distinta da tentativa),
`participation_consumptions`, `kill_switch_transitions` (com evidência, sem FK em cascata para o
tenant — a trilha sobrevive), e `portfolio_equity_snapshots` particionada por resolução.

Tenancy: `USER → ORGANIZATION → WORKSPACE → PORTFOLIOS → AGENTS`.

## Relacionadas

[[Risk Engine]] · [[Paper Trading]] · [[Execution Engine]] · [[System Overview]] · [[Open Bugs]] ·
[[Changelog]] · [[Diario/2026-09-07]] · [[Dialogos/M3]] · [[Architecture Decisions]]

## Fontes

`docs/RISK_ENGINE.md` (v2.2) · `docs/DATABASE.md` §7 e §18 · `docs/PRODUCT.md` §2 e §4 ·
`docs/plans/M3.md` · `docs/decisions/0005-carteira-virtual-e-risk-engine-paper-v1.md` ·
`.claude/state/decisions-M3-delegated-2026-09-06.md` · `.claude/state/brief-T3.1c-grants-roles.md` ·
medição direta na VPS em 2026-09-07 04:27–04:40Z (somente leitura)
