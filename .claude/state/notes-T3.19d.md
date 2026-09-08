# Notas T3.19d — `0013_replay_runs`: o recibo de um replay vira evidência durável

Base: `main` em `79379ef`. **Nada commitado.** Caminhos tocados (só os meus):
`infra/migrations/{versions/0013_replay_runs.py,ddl/replay_runs.py}`,
`packages/core/hunter_core/db/models/{replay_runs.py,__init__.py}`,
`packages/core/hunter_core/domain/enums.py`,
`packages/core/tests/integration/{test_migrations.py,test_schema_privileges.py}`,
`services/strategy-worker/hunter_strategy_worker/replay/ledger.py`,
`services/strategy-worker/tests/{test_replay_engine.py,test_replay_contract.py}`,
`docs/DATABASE.md` (§25 novo, §1.3 e §17.6 emendados).
Nada em `apps/**`, `services/execution-worker/**`, `obsidian/**`, `docs/DESIGN.md`, `.env*`.

Origem: `.claude/state/brief-T3.19b-db-replay-runs.md` (o quant escreveu o brief em vez da
migração, porque o brief da T3.19b o proibia de escrevê-la).

---

## 1. A decisão central: uma linha por **fatia**, e ela vem do grant

O brief deixou a escolha entre (a) uma linha por fatia e (b) uma linha por corrida acumulada por
`UPSERT`. Escolhi (a), e a razão que fecha não é a que o brief dá:

- **(b) exigiria `UPDATE` na própria tabela.** O único escritor é o strategy-worker, e a regra de
  `audit_logs`/`risk_events`/`kill_switch_transitions` desde a `0001` é que quem escreve evidência
  não a reescreve. A forma da tabela é **consequência do grant**, não preferência de modelagem;
- a fatia é a unidade que de fato acontece: a prova da T3.19b rodou 31 dias em **onze comandos** sob
  a mesma coorte. Somar fatias reconstrói a corrida; separar uma corrida em fatias não.

`id` é `uuid7` (§1), `run_id` é coluna, e `UNIQUE (run_id, window_from, window_to)` torna repetir uma
fatia idempotente — a mesma propriedade que a identidade `uuid5` dos sinais dá do outro lado. O
escritor usa `ON CONFLICT DO NOTHING` (nunca `DO UPDATE`, que o grant recusaria).

## 2. A tabela, em uma frase por decisão

| Decisão | Por quê |
|---|---|
| global, sem `organization_id`, sem RLS | pesquisa sombra é global (§1.1), como `agent_signals`, `signal_outcomes` e `shadow_episodes`. A ausência é **asserida** por teste (`test_replay_runs_is_global_and_carries_no_tenant_column` lê `pg_policy` e `information_schema.columns`), porque "não precisa de política" e "alguém esqueceu" são indistinguíveis de fora |
| sem partição, sem retenção | dezenas de linhas/dia; apagar por idade apagaria a contagem de tentativas que o protocolo de replicação existe para manter (`Registro de Tentativas`). Registrado no §1.3 em vez de deixado como lacuna |
| `seconds numeric(12,3)` | é **duração** que vira **taxa** num relatório (`bars/seconds`) — nem dinheiro (`28,10`) nem fração (`9,6`). Acréscimo declarado às convenções do §1, no espírito do §15.7 (funding) e do §18.6 (β). O escritor liga o parâmetro como **string** e converte no SQL |
| CHECK de coorte = `^replay:<uuid>$` | é a **interseção** que o brief pediu, escrita **uma vez**. Duas expressões que precisam concordar são duas que podem divergir. Provado por teste que é o segundo ramo de `SHADOW_COHORT_PATTERN` caractere a caractere |
| CHECK `cohort = 'replay:' \|\| run_id::text` | o rótulo e o `run_id` não podem discordar. A redundância é deliberada e incapaz de derivar |
| mais seis CHECKs | janela semiaberta, `finished_at >= started_at`, contadores não negativos, `outcomes_resolved <= signals`, `cardinality(markets) > 0`, `workers >= 1`, `jsonb_typeof(evaluations_by_state) = 'object'`. Nenhum recusa linha que `replay/run.py` produza hoje |
| FK `ON DELETE CASCADE` para `strategy_versions` | como `shadow_episodes`. Uma versão apagável é `draft` (a trigger de congelamento recusa o resto), e um recibo de um experimento cujo instrumento sumiu não explica nada |

Índices: PK, `uq_replay_runs_slice` (que também é o índice de `run_id`) e
`ix_replay_runs_version_window (strategy_version_id, window_from)` — a pergunta do placar e o índice
que o §1 exige da FK.

## 3. Grants — papel × tabela

| Papel | `replay_runs` |
|---|---|
| `hunter_app` | `SELECT` |
| `hunter_worker` | `SELECT`, `INSERT` — **nunca `UPDATE`, nunca `DELETE`** |
| dono / `DATABASE_URL_MIGRATIONS` | tudo |

Exatamente a forma de `fx_observations` (§18.9). Provado **como o papel**, não perguntado ao
catálogo: o `INSERT` passa, o `UPDATE` e o `DELETE` batem em *permission denied*, e o `INSERT` do
`hunter_app` também. As duas listas congeladas (`REPLAY_APP_READ_ONLY_TABLES`,
`REPLAY_WORKER_APPEND_TABLES`) entram na união de
`test_the_grant_lists_cover_every_table_exactly_once` — a partição exata do schema do §15.6 continua
exata.

## 4. `ledger.py`: o terceiro ramo, e uma sonda que o brief não pediu

`record_slice()` é novo; `record_run()` o chama **antes** do `INSERT` em `system_events`, na mesma
transação do chamador (um evento publicado que nenhuma linha gravada explica é a discordância que a
outbox existe para impedir). O JSONL continua fora da transação. Os três ramos continuam.

**A sonda.** `record_slice` pergunta `to_regclass('public.replay_runs')` antes de escrever. Não é
zelo: um statement contra relação inexistente **aborta a transação inteira**, e um banco ainda na
`0012` perderia junto a metade `system_events` do recibo — meia hora de corrida relatando **nada**
por causa de uma ordem de deploy. Faltando a tabela, o log sai em `error` nomeando a revisão (nunca
em silêncio) e os outros dois ramos gravam. É a forma que o §17.2 dá à sonda de lock do scanner.
Custo: um round trip por fatia, nunca por barra. Testado sem banco
(`test_a_database_still_at_0012_keeps_the_other_two_branches`: a sonda roda, o `INSERT` não).

## 5. Verificação (saída real está no relatório)

- `alembic upgrade head` em banco limpo (Postgres 16 descartável meu, porta 15434, removido ao fim):
  0001 → 0013, sem erro;
- `alembic check`: `No new upgrade operations detected.` — antes e depois do round trip;
- `alembic downgrade -1 && upgrade head` da `0013`: passa, e `check` continua limpo;
- guarda de downgrade com um recibo gravado: recusa com contagem e instrução, e
  `alembic_version` continua em `0013_replay_runs` (não commitou);
- isolamento RLS org A × org B: `hunter_app` com `app.current_org = A` vê 1 carteira (a de A) e
  **zero** de B; com `= B`, vê a de B. `replay_runs`: `relrowsecurity = f`, 0 políticas — global por
  contrato (§1.1), não por esquecimento;
- suítes: `test_migrations.py` 94, `test_schema_privileges.py` 42, `test_schema_rls.py` 17,
  `test_schema_seed_and_partitions.py` 24, `test_schema_shadow.py` + `test_schema_constraints.py` 66,
  `test_replay_engine.py` 13, `test_replay_lookahead.py` 6, `test_replay_contract.py` 32, unitários
  de `packages/core` 714 e de `services/strategy-worker` 191. **Tudo verde.**

## 6. Duas correções em testes existentes que a `0013` obrigou

`0012` deixou de ser o head, então dois testes que faziam `downgrade -1` esperando rodar o downgrade
da `0012` passavam a rodar o da `0013`. Os dois descem primeiro até `REPLICATION_REVISION`, no mesmo
padrão que os testes da `0010`/`0011` já usavam quando a `0011`/`0012` chegou por cima
(`test_0012_refuses_to_downgrade_while_a_replication_is_on_record`,
`test_0012_reverses_on_a_populated_database_and_gives_0010s_trigger_back`). O primeiro ganhou também
um `upgrade head` no `finally`, que ele não tinha e que a mudança de head tornou necessário.

A fixture `replay_db` de `test_replay_engine.py` passou a limpar `replay_runs` **como o dono** — o
`hunter_worker` não pode apagar, que é o ponto da tabela e não um incômodo do teste.

## 7. Concerns

1. **O stack local está na `0012`, não na `0013`.** Verificado agora (`select version_num from
   alembic_version` no `docker-postgres-1`): `0012_replication`. **Não apliquei** — é banco
   compartilhado e outro agente o usa. Efeito real: um replay rodado contra o stack local hoje grava
   `system_events` + JSONL e **não** grava o recibo durável, logando
   `replay_run_table_missing` em `error`. Quem opera o stack roda
   `uv run alembic -c infra/migrations/alembic.ini upgrade head` (ou recria o serviço `migrate`);
   a `0013` é `CREATE TABLE` + dois `GRANT`, não toma trava em relação existente e não abre janela.
2. **Três contadores são da coorte, não da fatia.** `count_population` conta as linhas da coorte
   inteira, sem filtro de janela, então `signals`/`outcomes_resolved`/`outcomes_open` são **total
   corrente** enquanto `bars_evaluated`/`seconds`/`errors` são da fatia. Somar os três multiplica a
   população; o número da corrida é o da última fatia. **Declarei em vez de corrigir**: mudar o
   número mudaria o que a prova da T3.19b relatou (o mesmo JSON já está em `system_events` com esse
   significado). Está no docstring do modelo, no §25.2 e aqui. Se alguém quiser o delta por fatia, é
   mudança do lado do quant (filtrar `agent_signals.emitted_at` pela janela), com um nome de coluna
   novo — nunca reinterpretando estes.
3. **Nada lê a tabela ainda.** O grant de `SELECT` do `hunter_app` existe e o índice do placar
   existe; o handler da T3.18 **não** foi ligado (é `apps/**`, fora do meu escopo). Enquanto isso, a
   tabela acumula evidência que ninguém consulta — o que é o estado certo, mas vale dizer que a
   pergunta do brief ("quantas operações simuladas esta versão acumulou?") ainda não tem rota.
4. **A `0013` não cobre o passado.** Toda corrida de replay anterior a esta migração — inclusive as
   onze fatias da prova da T3.19b — só existe em `system_events` (que expira) e nos JSONL que
   sobraram. Não há backfill honesto: o `system_events` do stack local ainda tem as linhas dentro dos
   30 dias e alguém *poderia* transcrevê-las, mas isso seria escrever recibo por reconstrução, e a
   prova rodou num banco descartável que já não existe. Fica declarado: a série começa aqui.
5. **`cardinality(markets) > 0` é o único CHECK que depende de comportamento do chamador.**
   `replay/run.py` recusa uma corrida sem mercado (`no market matched the selection`) antes de chegar
   ao recibo, então o CHECK só torna a recusa durável. Se um caminho futuro quiser registrar uma
   corrida que não visitou nada, ele precisa de migração — o que é a intenção.
6. **`pyright` do repo inteiro reporta 179 erros**, todos em
   `services/execution-worker/tests/**` e `apps/api/tests/unit/test_admission_adapter.py` — trabalho
   em voo de outro agente, nenhum nos meus arquivos (verificado por filtro de caminho). `ruff format
   --check` também acusa 4 arquivos, todos em `obsidian/**`. Nenhum dos dois é meu e nenhum é
   regressão desta tarefa.
7. **A sonda `to_regclass` custa um round trip por fatia.** Numa máquina onde o round trip é 45 ms
   (Docker Desktop no Windows, medido pela T3.19b) isso é ruído contra uma fatia de minutos, mas é
   uma escolha e não um acidente: o alternativo (falhar alto) perde a metade `system_events` do
   recibo junto, e o alternativo mais elegante (`SAVEPOINT`) traz a armadilha de `xmin`/subtransação
   que o §18.7 registra — desnecessária aqui, mas um precedente que eu não quis abrir.

## 8. O que revisar depois de mim

- **code-reviewer:** `ledger.py` (o terceiro ramo e a sonda) e a fixture `replay_db`, que agora
  limpa `replay_runs` como o dono.
- **quant (T3.19b):** o concern 2 — se o delta por fatia importa para o placar, o nome novo e o
  filtro são dele.
- **Sexta-feira / operador do stack:** o concern 1 (`upgrade head` no stack local).
- **T3.18 (placar):** a consulta está pronta e indexada:
  `SELECT ... FROM replay_runs WHERE strategy_version_id = :v ORDER BY window_from DESC`.
