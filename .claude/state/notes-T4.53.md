# T4.53 — as quatro tabelas que faltavam nas listas de grant

`test_schema_privileges.py::test_the_grant_lists_cover_every_table_exactly_once`
compara a união das listas congeladas (uma por revisão, em `infra/migrations/ddl/`)
com o conjunto de tabelas reais do schema. Quatro tabelas existiam sem lista.
Cada uma foi classificada pelo que a própria migração **de fato** deu (`GRANT`
lido no DDL, conferido contra `docs/DATABASE.md`), não pelo que seria cômodo.

## A classificação

| Tabela | Revisão | Lista nova | Por quê |
|---|---|---|---|
| `meme_events` | `0041` | `MEME_EVENTS_APP_READ_ONLY_TABLES` (+ `MEME_EVENTS_WORKER_UPSERT_TABLES`) | `hunter_app` só tem `SELECT`; o job de casamento (`hunter_worker`) tem `SELECT`/`INSERT`/`UPDATE` — carimba `mint`, `matched_at` e `last_scanned_created_at` (§52.2). Ninguém apaga. |
| `meme_event_matches` | `0043` | `MEME_EVENT_MATCHES_APP_READ_ONLY_TABLES` (+ `..._WORKER_APPEND_TABLES`) | A forma do `market_breadth`: `hunter_app` só lê, `hunter_worker` `SELECT`/`INSERT`. O "casado uma vez fica casado" (§52.3) é a ausência do `UPDATE`, não uma promessa do escritor. |
| `meme_gate_refusals_by_mint` | `0046` | `MEME_GATE_REFUSALS_APP_READ_ONLY_TABLES` (a constante já existia no DDL, só não era unida no teste) | API só lê ("por que a moeda X não virou proposta"); o worker tem `SELECT`/`INSERT`/`DELETE` porque poda a trilha de 7 dias linha a linha, como `meme_tokens` (§54.2). |
| `meme_rule_set_param_history` | `0046` | `MEME_RULE_SET_HISTORY_OWNER_ONLY_TABLES` — **classe nova: sem grant nenhum** | §54.1 é explícito: nenhum grant a `hunter_app`/`hunter_worker`. Quem escreve é `infra/scripts/meme_rule_set.py --set-param --apply`, na mesma transação do `UPDATE` em `meme_rule_sets.params`, pela conexão do owner; quem lê é `--history`. Nenhum serviço em execução toca. |

## O que foi feito para não enfraquecer o teste

- A classe "owner-only" é uma classe declarada, não um buraco: sem ela, uma
  tabela que alguém **esqueceu** de conceder e uma tabela deliberadamente
  fechada ao operador ficam idênticas vistas de fora (o mesmo argumento que
  `replay_runs` faz sobre "política que ninguém escreveu").
- Por isso entrou junto
  `test_the_owner_only_param_history_is_reachable_by_neither_role`: afirma que
  `hunter_app`, `hunter_worker` **e** `hunter_runtime` não têm privilégio
  algum ali. O teste de cobertura só pergunta "está classificada?"; esse novo
  pergunta "classificada como o quê?".
- As listas foram declaradas nos módulos DDL da própria revisão (convenção do
  arquivo: `ddl/tables.py` está congelado como de `0001`) e as funções de
  `GRANT` passaram a iterar sobre elas — o SQL emitido é byte a byte o mesmo,
  então nenhuma migração mudou de efeito e nenhuma revisão nova foi escrita.
  Iterar sobre a lista é o que impede a lista de divergir do grant depois.

## Nenhum grant esquecido

Conferi os quatro `GRANT` contra a convenção de `docs/DATABASE.md`
(§1.1/§1.2, §52.2, §52.3, §54.1, §54.2): os quatro batem com o documentado.
Nada precisou ser "consertado" por migração e nada foi encoberto. Também não
há desvio a escrever de volta no `DATABASE.md` — as quatro seções já descrevem
exatamente estes grants, inclusive o "nenhum grant" da `meme_rule_set_param_history`.
As tabelas são todas globais (sem `organization_id`, sem RLS, §1.1), então
nenhuma regra de tenant/RLS está em jogo aqui.

## Verificação

- `uv run pytest packages/core/tests/integration/test_schema_privileges.py -q -p no:cacheprovider` → **58 passed** (185,80 s)
- `uv run pytest packages/core/tests/integration/test_migrations.py -k "0041_creates_meme_events_with_its_grants_and_fk or 0043_creates_meme_event_matches_with_its_grants_and_fks"` → **2 passed** (os grants de 0041/0043 continuam iguais depois do refactor; ambos chamam `alembic check`)
- `uv run pytest packages/core/tests/integration/test_migration_0046.py -q` → **8 passed** (inclui o teste que prova que nenhum dos dois roles alcança a `meme_rule_set_param_history`)
- `uv run ruff check` / `ruff format --check` nos 4 arquivos → limpo
