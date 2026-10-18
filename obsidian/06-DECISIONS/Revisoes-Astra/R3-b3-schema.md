---
tags: [revisao-astra, b3, mt5, rico, robo, banco, schema, rls, migracao, mercado-tradicional]
date: 2026-10-17
updated: 2026-10-17
status: registro
owner: database-architect
decided_on: 2026-10-17
by: database-architect + astra
tarefa: "R3 do desenho docs/design/robo-b3-mt5.md §9 — schema b3_* (migração 0071_b3_robot) contra o contrato congelado docs/RISK_ENGINE_B3.md v1.0"
veredito: "4 chamadas. Desenho: 6 must-fix (serialização do claim, contrato de auditoria, dados duráveis faltando, proposed→expired, FKs compostas, encadeamento) — 5 absorvidos antes do DDL, o 6.º é do orquestrador. Diff r1: 6 must-fix (slot de posição fechada, reversão, saída sem intenção durável, evidência P4 NULL, conta nas FKs, encadeamento) — 5 corrigidos com teste. Diff r2: os 5 fechados; 2 novos no CHECK decisão × colunas (instantes não comparados; NULL passava) — corrigidos com teste. Rodada 3: os 2 fechados, nenhum must-fix novo. Pendente: encadeamento 0070/0071 (orquestrador)"
---

# Revisão da Astra — schema do robô B3 (R3, `0071_b3_robot`)

**Pedido:** desenhar e revisar o schema `b3_*` que a API (R4) e o serviço (R5) vão usar — perfis versionados, grades,
feriados, contratos, custos, armamento/autoridade, kill switch do robô, propostas, intenções, ordens, negócios,
posições, SLTP, reconciliações — com RLS forçada, auditoria e as máquinas de estado do contrato no banco. Fontes brutas:
`.claude/state/astra-review-R3-b3-schema-design.md`, `.claude/state/astra-review-R3-b3-schema.md`,
`.claude/state/astra-review-R3-b3-schema-r2.md`, `.claude/state/astra-review-R3-b3-schema-r3.md`. Documento normativo: `docs/DATABASE.md` §74.

**Notas lidas antes e o que mudaram:** [[00-HOME]] (toda entrada é proposta → risco → execução; mesas distintas);
[[Revisoes-Astra/R0a-risk-engine-b3|R0a-risk-engine-b3]] (incerteza atravessa instâncias → slot e intenção `unknown`
ficam no banco e nenhuma concessão os limpa; saída é obrigação durável → `b3_exit_intents` imutável);
[[Dialogos/robo-b3-mt5]] (um só remetente → autoridade de uma linha por conta, *fencing token*);
[[Revisoes-Astra/R1-hunter-risk-b3|R1-hunter-risk-b3]] (os nomes do `RiskDecision` e do `RobotOpsState` que o banco
persiste); [[KB-0149-o-que-a-mesa-real-ensinou]] (custo com fonte e data → `b3_fee_schedules` exige fonte e data da
fonte). Nenhuma estratégia mudou nesta tarefa.

## Chamada 1 — desenho (antes do DDL)

Concordou com: uma linha de autoridade por conta, coluna gerada para `client_order_id`, reusar `kill_switch_state` em
vez de criar `b3_kill_state` ("mesmo enum do SPOT"; um enum por conceito). Must-fix absorvidos:

1. **Claim sem serialização** (lê a autoridade A, outra transação revoga e concede B, a primeira commita): a linha da
   conta (`b3_robot_accounts`) virou a trava estável; concessão, revogação, armamento, troca de limites/grade e o claim
   a disputam, e o claim lê `clock_timestamp()` **depois** da trava (o `now()` de quem esperou é velho).
2. **Auditoria**: uma linha de `audit_logs` por entidade tocada, `entity_type` = tabela, nunca em `SAVEPOINT`.
3. **Dados duráveis faltando**: âncora do dia (`b3_session_anchors`), recibo de ingestão por `event_id`
   (`b3_robot_events`), batimento **por instância** (o da nova não apaga o da anterior) e o **conjunto** de travas do
   kill switch (a virada do pregão solta `daily_loss_limit` sem soltar `broker_reject_breaker`).
4. **`proposed → expired`** quando a instância morre (§6.1).
5. FKs compostas em toda a cadeia.
6. Encadeamento 0070/0071 — fica com o orquestrador.

**Divergência registrada:** ela sugeriu permitir inteiros JSON no perfil; mantive o contrato §9 ("número JSON
recusado").

## Chamada 2 — o diff, rodada 1

Seis must-fix, cinco corrigidos, cada um com teste:

1. `closed` congelava também o slot — mas P3/P4 liberam e `journal_lost` marca o slot de uma posição já fechada →
   `closed` congela tudo **menos** `sltp_slot`.
2. `exit_reason` imutável recusava a reversão do §4.2 → só muda para `reversal`; o prazo continua o da intenção.
3. Uma posição podia ir a `exiting` sem a intenção durável e depois voltar a `protected` → de `exiting`/`exit_overdue`
   só se vai a elas, `closed` ou `unattributed`, e um gatilho adiado exige `b3_exit_intents` no COMMIT.
4. `CHECK` com `length(btrim(x)) > 0` sobre coluna anulável aceita `NULL` (evidência P4 vazia liberava o slot) →
   `IS NOT NULL` explícito.
5. Duas contas da mesma organização passam pela mesma RLS: SLTP→época, ordem→intenção e intenção/autoridade→pin agora
   incluem `account_hash` na chave.
6. Encadeamento — orquestrador.

Nice-to-have aceitos: o teste de isolamento passou a ter dado nas 24 tabelas (antes provava contra tabela vazia); o
teste de downgrade cria a própria linha; um teste de claim esperando uma revogação (perde com `authority_mismatch`). A
ordem de travas para a R4 (todo escritor trava sistema → organização → conta antes do DML) ficou escrita na §74.8.

## Chamada 3 — rodada 2

Os cinco fechados. Dois novos, no `CHECK` que amarra o `RiskDecision` do R1 às colunas: os instantes não eram
comparados (uma primeira gravação atrasada podia re-datar a aprovação) e uma chave ausente dava `NULL`, que passa num
`CHECK` → comparo `as_of`/`approved_at`/`expires_at` e a expressão inteira é `IS TRUE`; três testes negativos (preço
diferente, re-datação, `sizing` ausente).

## Chamada 4 — rodada 3

Os dois achados fechados ("nenhum must-fix novo no escopo revisado"); continua só o encadeamento. Nice-to-have não
feito: um negativo com `sizing.n_final = null` isolando o `IS TRUE` (o caso "sem `sizing`" já passa por ele).

## O que a base aprendeu

1. **Um `CHECK` passa com `NULL`.** Toda condição sobre coluna anulável ou chave JSON opcional precisa de `IS NOT NULL`
   ou de `(…) IS TRUE` — "texto não vazio" não recusa a ausência.
2. **Fechar a posição não termina a requisição.** Estado da posição e slot SLTP são fatos com provas diferentes; o
   terminal de um não congela o outro.
3. **A conta é parte da identidade, não só a organização.** RLS isola tenants; dentro de um tenant, quem impede misturar
   contas é a chave composta.
4. **Gatilho que trava outra linha cria ordem de travas.** Um `BEFORE ROW` dispara com a própria tupla já travada; se ele
   trava a conta, todo escritor tem de travar a conta antes, explicitamente.
5. **A guarda de downgrade precisa enxergar as linhas.** Com `FORCE ROW LEVEL SECURITY`, um dono que não é superusuário
   conta zero; a `0071` faz `NO FORCE` antes de contar. **Hipótese não verificada:** as guardas da `0006` não fazem — a
   Astra confirmou o risco por leitura; falta a prova com dono comum.

**Pendências:** encadeamento da semente retida `0070` sobre a `0071` e `HEAD_REVISION` de `test_migrations.py` no
commit (orquestrador); prova da guarda da `0006` com dono comum.
