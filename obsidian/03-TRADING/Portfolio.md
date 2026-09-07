---
tags: [trading, portfolio, carteira, m3]
updated: 2026-09-07
status: aberta em produção e parada de propósito — o execution-worker existe e foi provado no local; na VPS ainda não; a ponte de sinais está desligada
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

## Atualização do plantão da manhã de 2026-09-07 (11:10Z) — a carteira ganhou quem a faça andar

Dois dos três "não faz" do parágrafo acima caíram, e o terceiro caiu por inteiro:

- **O `execution-worker` existe** (T3.5, `7ecafd2`; correções do guardião em `12edda3`) e foi
  **provado no stack local por 30 minutos, com saída 0**: ordem manual aprovada → fill a 100,01 com
  taxa em ativo base → posição com stop 97,5 → salto para 95,00 → primeira saída **degradada** (ordem
  escrita, **sem fill inventado**) → segunda tentativa a 95,00 com deslize de 256,41 bps → caixa
  19.903,662415 + pó 0,04579 = patrimônio **19.903,708205, idêntico no heartbeat e no último ponto da
  curva** → `trades.pnl = −96,28938018`, custos contados **uma vez só** → 30 pontos de 1 min, **0
  exceções**.
- **A admissão pelo lado da API não vira mais 500:** a API agora só **arquiva um pedido pendente**
  (sem decisão, sem lugar na fila, sem reserva, sem digest — o motor recomputa), e quem decide é o
  worker, na própria linha do pedido (`7ecafd2` + `0009_paper_geometry`, `70acb6f`).
- **A ponte sinal → admissão existe e está desligada** (T3.14, `12edda3`), com **duas travas
  independentes**: `ENABLE_PAPER_AUTONOMY=false` (e com ela falsa a ponte nem cria o grupo de
  consumo) e, mesmo se ligada, **todo sinal do Lab hoje é `research_only`** — propósito que a ponte
  recusa. Nada é admitido até existir uma `strategy_version` ativada com propósito de paper, e essa
  ativação é **decisão do Everton**.

**O pó agora tem nome.** Uma compra spot paga a taxa no próprio ativo, e a migalha que sobra depois
da venda **não é posição**: não segura vaga, não conta exposição e não bloqueia uma segunda ordem na
moeda (antes bloqueava — reproduzido 4 h depois do stop). Mas ela **continua visível e valorizada** no
patrimônio, marcada como pó (`positions.is_residual`, `0009`). **O assentamento — vender o pó quando
ele passar do mínimo — ainda não existe**, e está em [[Open Bugs]].

**Na VPS, nada disto está no ar ainda.** A VPS roda a era do `2688ef1` (`0007`, 4 shards, coletor de
câmbio, carteira aberta). O deploy é **um comando só**
(`MARKET_SHARDS=4 bash infra/vps/compose.sh update`), mas ele **recria a rede** e **aplica `0008` e
`0009`** num banco que tem a carteira permanente do Everton — e o `execution-worker` **não deve subir
lá antes das nove verificações da T3.9**. Fica pendente, com ordem escrita.

**O que falta, nomeado:** **T3.5c** (assentamento do pó; `kill_switch.changed` também na retomada
pela API; fechar o dedupe com a suíte de integração) · **T3.0c/T3.0d** (ingestão spot e os itens da
revisão da T3.0b, um deles bloqueante: o `event_id` do candle sem `market_type` descarta o segundo
candle do minuto em silêncio) · **T3.9b** (as verificações restantes — V1/V2/V3 e §11 já estão feitas
em `eccb648`) · **T3.10** (runbook de ativação e os quatro itens da revisão da T3.14) · **o deploy**.

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

*(Tabela atualizada no plantão da manhã de 2026-09-07 — a coluna "Estado" mudou em cinco das seis
linhas.)*

| Tarefa | O que entrega | Estado |
|---|---|---|
| **T3.5 — `execution-worker`** | Ciclo de admissão, ciclo de ordem aplicando o `ExecutionReport` por fill, ciclo de proteção, MTM antes do kill switch, expiração de reserva sob a mesma trava, recuperação após restart | **implementado e provado** (`7ecafd2` + `12edda3`): 30 min no local, saída 0, dois bloqueios do guardião fechados |
| **T3.1c/T3.1d/T3.1e — papéis e geometria** | Worker decide e grava estado de risco; API pede, lê e autoriza; retomada exige **OWNER**; a API perde escrita nas tabelas de execução; o pedido carrega a própria geometria | **implementado** (`2688ef1`, `c1f8c5f`, `70acb6f`) |
| **T3.0b/T3.0c — integração SPOT** | `market_type` nos eventos e nas chaves do Redis; ingestão spot no `market-worker`; hold durável | T3.0b **implementada** (`cefad8c`); **T3.0c em voo**; T3.0d com quatro itens, um deles bloqueante |
| **T3.13 — integração operacional** | Papel no `RoleRegistry`, compose e Dockerfile do worker, prontidão, métricas, visibilidade de atraso | **implementado** (`7557368`) + tela `/system` (`509e4d8`) |
| **T3.14 — ponte shadow → admissão** | Uma proposta por ciclo, atrás de `ENABLE_PAPER_AUTONOMY=false` | **implementada e desligada** (`12edda3`); quatro condições escritas antes de ligar; nunca em produção antes da T3.9 |
| **T3.9 — as nove verificações** | O portão do milestone | V1/V2/V3 e §11 **feitas** (`eccb648`); o resto é **T3.9b**, a fazer |
| **T3.5c · T3.10 · deploy** | Assentamento do pó e `kill_switch.changed` na retomada (T3.5c, **em voo**); runbook de ativação (T3.10); e o deploy único na VPS, que recria a rede e aplica `0008`+`0009` | a fazer / pendente |

## D10 — qual versão de estratégia vai alimentar a carteira (delegada em 2026-09-07)

Everton, 2026-09-07: **"sexta feira pode decider esses 4"**. Esta é a primeira das quatro, e é a que
decide de onde virá a primeira entrada não manual da carteira. Registro completo em
`.claude/state/decisions-delegated-2026-09-07.md`; ver também [[Strategies]], [[Paper Trading]],
[[EXP-0001-momentum-v1]], [[EXP-0002-volume-anomaly-v1]] e [[Dialogos/M3]].

**Decisão: `momentum`**, e **não** virando o propósito de uma versão existente. A coorte de paper
nasce como uma **linha nova e congelada** em `strategy_versions`, com `purpose = paper`, parâmetros
copiados bit a bit da versão de momentum ativa na VPS e `code_ref` recalculado. A coorte
`research_only` continua **ativa e intocada** ao lado — o que dá de graça a comparação que interessa:
o mesmo gatilho medido pelas barras (hipotético) e medido pela carteira (com os custos do simulador).

**O achado que mudou a pergunta.** O rótulo `paper` **não existe no código**: o `strategy-worker` só
sabe escrever `research_only` (cravado em `record.py:198,229`), a ponte e a admissão só aceitam
`"live"` (`bridge_screen.py:156`, `admission/sources.py:259`), e `strategy_versions` **não tem coluna
`purpose`**. Falta exatamente um rótulo entre o produtor e o consumidor — e ele é coluna, migração,
envelope e portão, não uma linha de banco. Decidido junto: o rótulo admissível para carteira
`type=paper` passa a ser **`paper`**, e `live` fica **recusado por nome** até a Fase 4. Vira a
**T3.15**.

**Por que momentum, com o dado** (leitura datada da VPS, `as_of = 2026-09-06T13:00:00Z`):

| | `momentum v1` | `volume_anomaly v1` |
|---|---|---|
| Emitidos / entradas | 208 / 208 | 459 / 443 |
| Recusas por **geometria** (o que a ponte revalida) | **0** | **16** |
| Avaliáveis / dias distintos | 105 / **1** | 352 / **1** |
| Expectancy líquida hipotética | **−0,2102 R** | **−0,2304 R** |

Zero recusas de geometria em 208, e momentum não carrega a janela de **288 barras de 5 min
contíguas** que deixa o volume_anomaly refém de um único minuto ausente por ~24 h — que é justamente
o defeito que este sistema tem hoje (63.793 avaliações `unavailable` no `hb:strategy:shadow`).

**Não é escolha de desempenho, e ninguém deve ler assim.** As duas têm expectancy negativa e **1 dia
distinto** contra o limiar editorial de 100 outcomes **e** 30 dias — inconclusivas, as duas. A coorte
de paper existe para provar o **caminho** (sinal → ponte → admissão → Risk Engine → fill paper →
ledger → proteção), não para ganhar dinheiro.

**Nada foi ativado.** A ativação exige as sete condições da D10 — T3.9b verde, T3.14b e T3.15
revisadas, spot ligado na VPS depois da T3.0d, β válido, `EXP-0005` aberto **antes** do primeiro
sinal, e o parecer da Astra — e é ato manual, auditado em `system_events`, anunciado ao Everton
antes. `ENABLE_PAPER_AUTONOMY` continua `false`.

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
