# T4.28g — parar de recusar entradas reais por dado que chega segundos depois

**Data:** 2026-09-16. **Escopo:** worker (leitor de risco) + executor (auto-approve).
**Nenhum limite, nenhum check e nenhuma janela de frescor foram alterados.**

## 1. As medições em que me apoiei (não refiz nenhuma)

Fonte: `obsidian/03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa.md` (R5, 16 ordens
reais do dia, 11:46–15:33 BRT, consultas em `infra/scripts/sql/research/2026-09-16-r5-q0{1..4}-*.sql`).

| medição | valor |
|---|---|
| ordens recusadas `bundled_share_unmeasurable` | 13 / 16 (6 de 7 mints) |
| ordens recusadas `creator_flow_unknown` | 7 / 16 (4 de 7 mints) |
| `meme_risk_snapshots` do mint × 1ª ordem | mediana **+103 s** (6 de 7 mints depois da ordem) |
| `creator_sold` não-nulo × 1ª ordem | mediana **+15 s** |
| mesa → executor | 3–10 s (média 6 s) |
| admissão estimada sobre 48 mints propostos em 24 h | 8 % (4/48); sem o bundled, 19 % (9/48) |

Cadências que li no código (não medidas na VPS nesta tarefa): `risk_cycle_s = 60`,
`risk_min_interval_s = 300` (`services/meme-worker/hunter_meme_worker/config.py`),
`AUTO_APPROVE_MAX_AGE_S = 60` e `RISK_SNAPSHOT_MAX_AGE_S = 600`.

## 2. O que mudou

### 2.1 Worker — o leitor de risco cobre quem está para ser julgado

`repo_tape.pending_operator_mints` era `status = 'proposed'` apenas. **A causa real** é que o
executor move a linha para `approved` 3–10 s depois (`hunter_core.execution.meme.approval.
DECIDE_PROPOSAL`), e a partir do tique seguinte do leitor o mint já não estava no conjunto.

Agora três ramos `UNION`, cada um com igualdade na coluna líder de um índice e a janela de 600 s na
segunda (`pending_mints_sql()`, `PENDING_PROPOSAL_STATUSES`, `LIVE_ORDER_PENDING_STATUSES`,
`PENDING_LOOKBACK_S`):

| ramo | índice (`docs/DATABASE.md`) |
|---|---|
| `p.status = 'proposed' AND p.proposed_at >= :since AND p.expires_at > :now` | `ix_meme_proposals_status_proposed_at` |
| `p.status = 'approved' AND p.proposed_at >= :since` | o mesmo |
| `o.status IN ('admitted','simulated','submitted_unconfirmed') AND o.received_at >= :since` | `ix_meme_live_orders_status_received_at`, depois PK de `meme_proposals` |

**Correção ao brief:** ele pedia `('proposed','suggested')`. **`suggested` não é um status** —
`PROPOSAL_STATUSES` é `('proposed','approved','rejected','expired','filled','unfilled')`; o
`decision = suggested` da §3.5 nomeia o *payload* que o robô copia do conjunto. Um `WHERE` com
`'suggested'` casaria zero linhas para sempre, em silêncio. Provado por
`test_there_is_no_suggested_status_to_cover`.

**Throttle:** verifiquei `RiskReader.due` — `mint not in self.last_read` vem **primeiro**, então a
primeira leitura de um mint nunca é adiada. Não precisou de isenção; precisou de teste
(`TestFirstReadIsNotDeferred`, 4 casos) e de docstring, para que uma otimização futura do tipo
"N leituras por tique" não reintroduza o atraso.

### 2.2 Executor — `risk_snapshot_pending`

`plan_auto_approvals` ganhou `snapshot_mints: frozenset[str] | None`; `auto_approve_once` mede com
`risk_snapshot.mints_with_snapshot` (uma query, `mint = ANY(:mints)` + `observed_at >= :since`,
`bundled_share IS NOT NULL` no predicado; sem candidatos, **nenhuma query**). Sem `bundled_share`
medido e fresco (600 s — a janela da própria admissão, `SNAPSHOT_MAX_AGE_S is RISK_SNAPSHOT_MAX_AGE_S`)
o robô **não abre** a proposta: fica `proposed`, nenhuma ordem existe, o heartbeat mostra o nome.

`None` = "o chamador não mediu" (comportamento pré-T4.28g). `auto_approve_once` sempre mede.

A condição de idade do brief é **redundante e por isso não foi escrita**: `too_old` é avaliado antes,
logo tudo que chega ao novo skip já tem < 60 s. Provado por
`test_a_proposal_too_old_is_the_humans_not_a_pending_snapshot`.

### 2.3 O que **não** foi feito: fluxo do criador pela cadeia

O brief pedia derivar `creator_net_sol` lendo a ATA do criador e comparando com "a alocação inicial
conhecida de `meme_tokens`". **Essa coluna não existe** e nenhuma outra tabela guarda a alocação do
criador na criação:

- `meme_tokens`: `creator`, `initial_real_token_reserves` (denominador da curva, de todo mundo),
  `total_supply`. Nada do criador.
- `meme_features_1m/15s.dev_share`, `meme_risk_snapshots.dev_share`, `meme_boards.dev_share`: todos
  são o `devHoldingsPercent` do indexador (`indexer_rest.py:191`) — a fração **corrente** do supply,
  observada quando a leitura acontece, cuja primeira amostra chegou +114 a +419 s depois da criação
  (mediana 290 s) nos 7 mints de hoje.
- `meme_paper_bets/meme_live_positions.creator_sold_seen_at`: o *creator watch* do worker, que por
  doutrina exige **duas** leituras e a primeira **queda** (`creator_watch.py`: "a restart starts
  blind and waits for two readings, it never invents a previous balance"). Só produz o lado
  "vendeu"; nunca o lado "segura".

**Cenário de falha concreto se a derivação fosse escrita como pedida** (por que eu não a escrevi):
moeda criada às 14:00:00, dev buy de 30 M tokens; o criador larga tudo às 14:00:20. A primeira
leitura `/in-memory-coin` do mint (que a mudança 2.1 antecipa, mas ainda assim é posterior) chega às
14:01:00 e grava `dev_share = 0`. O executor decide às 14:02:00, lê a ATA do criador pela cadeia e
encontra 0 tokens; `0 ≥ 0` ⇒ `creator_net_sol = +1` ⇒ **`creator_behaviour` PASSA** numa moeda que o
criador já rugou. É exatamente o dump que o check 10 existe para barrar, e a §4 é explícita:
"insumo que não existe não vira zero". Também tentei uma versão conservadora (base =
`initial_real_token_reserves − real_token_reserves` da foto mais antiga): ela só consegue produzir
**mais recusas**, nunca a admissão que a tarefa quer, e o caso "criador dumpou tudo, ninguém mais
comprou" ainda passa com `0 ≥ 0`.

**Os dois caminhos sãos, para quem retomar:** (a) persistir a alocação do criador no instante da
criação (o radar já decodifica o `TradeEvent`; a compra do dev vem na transação de `create`), e aí a
comparação pela ATA fica exata e barata; (b) fechar a cobertura da fita — `creator_sold` já é exato
quando `covered_since <= created_at`, e o atraso medido (+123 a +441 s) é do orçamento do
`swap-api` (16 pulls/min sobre ~130 mints, `tape_budget.py`), não do mercado. (b) é o irmão exato da
mudança 2.1 e vale medir antes de escrever.

## 3. O que está provado e o que não está

**Provado (sem Docker nesta máquina — as metades Postgres ficam `skipped`):**
- 10 testes unitários no worker (`test_risk_candidates.py`): os statuses, a ausência de `suggested`,
  as três janelas, a forma index-friendly, e as 4 do throttle/primeira leitura.
- 9 testes unitários no executor (`test_auto_approve.py::TestRiskSnapshotPending`), incluindo a
  ordenação contra `too_old`/`mint_busy`/`recently_refused` e "sem candidatos, sem query".
- 360 passed / 101 skipped em `services/meme-executor/tests services/meme-worker/tests`.

**Não provado nesta tarefa (Docker indisponível — `docker info` falhou):**
- os 7 testes Postgres novos do worker (`test_risk_candidates_persistence.py`) e os 2 novos do
  executor (`test_live_persistence.py::test_stage_1_waits_for_the_rug_read_*`,
  `test_a_stale_rug_read_is_not_a_rug_read`) **nunca correram**. O SQL novo é sintaticamente válido
  (gerado e inspecionado) mas **não foi executado contra Postgres**; `EXPLAIN` foi raciocinado
  contra os índices declarados, não medido.
- `_plant_operator_proposal` passou a plantar um `meme_risk_snapshots` por padrão (a nova
  pré-condição do estágio 1). Se algum teste Postzgres do executor depender de a leitura **não**
  existir e eu não tiver visto, ele quebra — rodar a suíte com Docker antes de subir.
- O ganho estimado (admissão de 8 % → ~19 % dos mints propostos) é do estudo R5, **não** uma medição
  desta mudança.

## 4. Corrida que fica declarada

Pior caso: o leitor roda a cada 60 s e o robô desiste da proposta aos 60 s (`too_old`). Uma proposta
filed logo depois de um tique do leitor pode envelhecer para o humano exatamente quando a leitura
chega. Não inventei um tique mais rápido nem afrouxei `AUTO_APPROVE_MAX_AGE_S`: as duas são decisão
do dono. Se a mesa continuar repropondo o mesmo mint a cada ~20 s (medido em 16/09), a proposta
seguinte já encontra a leitura pronta — é o caminho esperado, e `risk_snapshot_pending` no heartbeat
é como se mede se ele funciona.
