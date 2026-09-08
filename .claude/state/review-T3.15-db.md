# Revisão database-architect — T3.15 / `0010_strategy_purpose` (commit `6b837ac`)

**Escopo:** só leitura. Nada foi executado (o brief proíbe suítes com
testcontainers e Bash em background; `alembic upgrade/check/downgrade` exigem
Postgres real). A revisão é estática sobre o código, o diff e o corpo dos testes;
a saída real citada em `.claude/state/notes-T3.15.md` §"Saída real" **não foi
reproduzida por mim** — ver "Depois", item D8.

Arquivos revisados: `infra/migrations/versions/0010_strategy_purpose.py`,
`infra/migrations/ddl/strategy_purpose.py`, `infra/migrations/ddl/shadow.py`,
`infra/migrations/ddl/tables.py`, `infra/migrations/ddl/grants.py`,
`infra/migrations/env.py`, `packages/core/hunter_core/db/models/agents.py`,
`packages/core/hunter_core/db/base.py`,
`packages/core/tests/integration/test_migrations.py` (1825–2045),
`packages/core/tests/integration/test_schema_privileges.py` (324–380, 695–815),
`services/strategy-worker/hunter_strategy_worker/{catalogue,paper_line,activation_db,replay/load}.py`,
`services/execution-worker/hunter_execution_worker/bridge_repo.py`,
`infra/scripts/{activate_strategy_version.py,seed.py}`, `docs/DATABASE.md`
(§15.6, §16.1, §17.6, §17.7, §22).

## Bloqueantes

Nenhum. Os seis pontos investigados fecham:

1. **Substituição da trigger** (`infra/migrations/ddl/strategy_purpose.py:143-162`).
   Nenhuma outra dependência cai junto: `shadow_freeze_strategy_version` só é
   referenciada pelas duas triggers de `strategy_versions`
   (`strategy_versions_freeze_update` / `_delete`), ambas dropadas antes do
   `DROP FUNCTION` (linhas 148-150). Não há view, grant explícito de `EXECUTE`
   nem outra trigger apontando para a função — o grep em todo o repo devolve só
   `ddl/shadow.py`, `ddl/strategy_purpose.py` e dois testes. Como o `DROP
   FUNCTION` é **sem `CASCADE`**, uma dependência esquecida falharia alto em vez
   de sumir em silêncio — é o comportamento certo.
   **O downgrade devolve exatamente a trigger da `0002`:** comparei os dois
   construtores de SQL linha a linha (`ddl/shadow.py:65-95` × `ddl/strategy_purpose.py:86-118`);
   o único caractere diferente é `_FROZEN_COLUMNS` × `_FROZEN_COLUMNS_0010` no
   `for`. E `restore_shadow_freeze()` (`strategy_purpose.py:164-174`) não repete
   corpo nenhum: chama `ddl.shadow.drop_strategy_version_freeze()` +
   `create_strategy_version_freeze()`, então o que volta é literalmente o objeto
   da `0002`. `test_migrations.py:2016` confere isso pelo `pg_proc`.

2. **Estreitamento de grants** (`strategy_purpose.py:196-217`). Nenhuma consulta
   real do worker escreve `strategy_versions`. As únicas escritas em produção são
   `infra/scripts/activate_strategy_version.py:158,248,266` e
   `services/strategy-worker/hunter_strategy_worker/paper_line.py:109`, e as
   quatro rodam na conexão de dono (`activate_strategy_version.py:281-292`:
   `DATABASE_URL_MIGRATIONS`, `create_async_engine(..., statement_cache_size=0)`,
   direta, nunca no pooler). Pelo papel `hunter_worker` só há leitura:
   `catalogue.py:230-242`, `replay/load.py:147-166`, `metrics.py:82`,
   `bridge_repo.py:98` — todas `SELECT`, e `SELECT` não foi tocado.
   `WORKER_COLUMNS_EXCEPT_PURPOSE` (`strategy_purpose.py:176-190`) tem 12 nomes =
   exatamente as 13 colunas do modelo (`agents.py:67-108`) menos `purpose`;
   nenhuma coluna ficou de fora por engano.
   `seed.py:162-174` insere pelo ORM sem nomear `purpose` (usa o `DEFAULT`) e o
   `ON CONFLICT DO UPDATE` só mexe em `code_ref` com `WHERE activated_at IS NULL`
   — não toca `purpose` e não colide com linha `paper` (a derivada nasce
   `v<max+1>` ≥ `v2`, `activation_db.py:96-110`; o seed só semeia `v1`).
   Um `INSERT` sem lista de colunas (`INSERT INTO strategy_versions VALUES (...)`)
   passaria a exigir privilégio em **todas** as colunas e seria negado — não
   existe nenhum no repo, mas fica registrado como a única forma de quebrar isto.
   O `downgrade` (`:211-217`) revoga o grant por coluna e reconcede `INSERT,
   UPDATE` de tabela; `DELETE` nunca foi revogado, então o estado pós-downgrade é
   idêntico ao da `0001` (`ddl/grants.py:76`).

3. **CHECK, default e nomes.** `text` + CHECK em vez de `CREATE TYPE` é o padrão
   do repo para rótulo cuja lista pode crescer (§15.6/§21) e evita o `ALTER TYPE
   ... ADD VALUE`, que não roda dentro de transação — coerente.
   **A convenção de nomes bate:** `hunter_core/db/base.py:24` define
   `"ck": "ck_%(table_name)s_%(constraint_name)s"`, então o
   `CheckConstraint(..., name="purpose_is_a_known_label")` de `agents.py:78-80`
   materializa como `ck_strategy_versions_purpose_is_a_known_label` — exatamente
   o nome que `strategy_purpose.py:57` cria. (Vale notar que isso **não** é o que
   protege o `alembic check`: o Alembic não compara CHECK constraints; o nome
   igual importa para paridade real de DDL, não para o portão.)
   `compare_server_default` **não** está ligado em `env.py:116-127` (só
   `compare_type=True`), e a coluna é `Text`/`text` NOT NULL nos dois lados — não
   há origem de drift. `test_alembic_check_reports_no_drift`
   (`test_migrations.py:600`) cobre o portão, e o round trip da `0010` termina em
   `command.check(config)` (`test_migrations.py:2044`).

4. **Guarda de downgrade.** `refuse_a_downgrade_that_would_lose_a_purpose()`
   (`strategy_purpose.py:232-244`) é a **primeira** chamada do `downgrade()`
   (`0010_strategy_purpose.py:64-69`), o `RAISE` aborta a transação e o
   `alembic_version` não avança — asserido em `test_migrations.py:2005-2010`.
   Quanto à linha `paper` **ativada**: ela nunca chega ao `DROP COLUMN`, porque a
   guarda recusa antes. E mesmo a linha `research_only` **ativada** (congelada)
   passa: `ALTER TABLE ... DROP COLUMN` é DDL e **não dispara trigger de linha**
   `BEFORE UPDATE/DELETE`; além disso `restore_shadow_freeze()` roda antes do
   `drop_purpose_column()`, então a função já não cita `purpose` quando a coluna
   some. Na prática o teste de round trip (`test_migrations.py:2016`) roda num
   banco module-scoped que **contém** a linha ativada deixada por
   `test_0010_freezes_purpose_after_activation` (`:1948`) — mas isso é ordem de
   definição no arquivo, não asserção (ver D5).

5. **Limites de nome, partições e RLS.** `0010_strategy_purpose` = **21**
   caracteres (`alembic_version.version_num` é `VARCHAR(32)`, §17.6 — o teto que
   derrubou a `0005`); `ck_strategy_versions_purpose_is_a_known_label` = **45**
   (< 63). Nenhum índice novo. `strategy_versions` não é particionada e nenhuma
   partição é tocada. **RLS: `strategy_versions` não tem RLS e não deve ter** —
   é tabela global de catálogo, sem `organization_id` (`docs/DATABASE.md:761`
   a classifica em `APP_READ_ONLY_TABLES`; não aparece em `TENANT_TABLES` nem em
   `ddl/policies.py`). Portanto a coluna nova **não** precisa de policy, e o
   isolamento entre orgs não muda nada com esta revisão.

6. **Implantação com dados.** `ALTER TABLE ... ADD COLUMN purpose text NOT NULL
   DEFAULT 'research_only'` (`strategy_purpose.py:128-131`) **não reescreve a
   tabela** no PG16: o default é não-volátil (literal), então o valor vai para
   `pg_attribute.attmissingval` e o comando é O(1) — comportamento desde o PG11.
   O `ADD CONSTRAINT ... CHECK` (`:132-135`) **não** é `NOT VALID`, então faz
   varredura completa sob `ACCESS EXCLUSIVE` — irrelevante aqui:
   `strategy_versions` tem uma linha por estratégia semeada (ordem de dezenas).
   Não há `LOCK TABLE` explícito, nem `CREATE INDEX` sem `CONCURRENTLY`, nem
   `VACUUM`/`REINDEX`. Nada nesta revisão quebra sob pooler de transação (sem
   prepared statement de sessão, sem `LISTEN/NOTIFY`, sem advisory lock de
   sessão) — e ela roda pela conexão direta de migração de qualquer forma.
   A ressalva de fila de trava está em A3.

## Antes do deploy

**A1. `docs/DATABASE.md` §16.1 ficou desatualizada e é a seção que um leitor
consulta para saber o que a ativação congela.**
`docs/DATABASE.md:864-869` enumera as colunas congeladas — `strategy_id`,
`version`, `code_ref`, `parameters_schema`, `default_parameters`,
`params_format`, `activated_at` — **sem `purpose`**, que a `0010` acrescentou.
§22.2 (`:3573-3585`) descreve a ampliação, mas §16.1 continua afirmando a lista
antiga como se fosse completa.
*Cenário:* na T3.15b/T3.16 alguém lê §16.1, conclui que `purpose` é mutável, e
escreve um caminho de "promover a versão de pesquisa para paper com um UPDATE".
Só descobre a trigger em runtime, na VPS, com a transação abortada.
*Correção:* em §16.1, acrescentar `purpose` à enumeração com a marca de origem
(por exemplo "... `activated_at` e `purpose` — esta desde a `0010`, §22.2") e uma
frase dizendo que a lista viva mora em
`ddl/strategy_purpose.py:_FROZEN_COLUMNS_0010`, não mais em `ddl/shadow.py`.

**A2. A tabela de classes de grant de §17.6 passou a mentir sobre uma tabela.**
`docs/DATABASE.md:1545` diz que `WORKER_WRITE_TABLES` dá a `hunter_worker`
`SELECT/INSERT/UPDATE/DELETE`. Desde a `0010`, `strategy_versions` — que está em
`WORKER_WRITE_TABLES` (`ddl/tables.py:143`) — tem `INSERT`/`UPDATE` **por
coluna** e não de tabela. §22.3 documenta o caso, mas §17.6 é a seção que
descreve as classes, e o teste de partição
(`test_the_grant_lists_cover_every_table_exactly_once`,
`test_schema_privileges.py:324`) só compara **tabelas**, nunca colunas — então
nada no repo detecta a divergência entre a tabela de §17.6 e o banco.
*Cenário:* um revisor futuro confere §17.6 contra
`has_table_privilege('hunter_worker','strategy_versions','INSERT')`, recebe
`false`, e "conserta" com um `GRANT INSERT ON strategy_versions TO
hunter_worker` — que reabre a escrita de `purpose` inteira, porque a ACL de
coluna é a **união** com a de tabela (exatamente o que
`strategy_purpose.py:29-44` mediu).
*Correção:* nota de rodapé na linha de `WORKER_WRITE_TABLES` em §17.6 apontando
para §22.3 e dizendo explicitamente: "exceto `strategy_versions`, cujos
`INSERT`/`UPDATE` são por coluna desde a `0010` — nunca reconceda no nível de
tabela".

**A3. §15.6 ainda diz "nenhuma revisão até a `0005`" sobre trava de migração, e o
deploy da VPS roda `migrate` com os workers de pé.**
`docs/DATABASE.md:792-803` decide, com razão, não pôr `lock_timeout` em `env.py`
até a primeira revisão que precise de trava longa em tabela quente, mas a
justificativa enumera só `0001`–`0005`. A `0010` toma `ACCESS EXCLUSIVE` em
`strategy_versions` (ADD COLUMN, ADD CONSTRAINT, DROP/CREATE TRIGGER — tudo numa
transação só, `env.py` não usa `transaction_per_migration`), e
`docs/DEPLOYMENT.md:394,428-430` mostra que na VPS a migração é um
`docker compose run --rm migrate` **com `api`/`market-worker`/`strategy-worker`
rodando** (`restart: unless-stopped`, `DEPLOYMENT.md:83`).
*Cenário concreto:* o strategy-worker está no meio de um `load_active_versions`
(`catalogue.py:298`) quando o `ALTER TABLE` pede `ACCESS EXCLUSIVE`; o pedido
entra na fila e **todo leitor novo de `strategy_versions` fica atrás dele** —
inclusive a API. O dano é limitado (as consultas são curtas e o
`statement_timeout` de 15 s do §1.2a corta o leitor), mas o pior caso é ~15 s de
`strategy_versions` inacessível para leitura, e nada no repo hoje impede isso.
*Correção (escolher uma, e registrar):* (a) `op.execute("SET LOCAL lock_timeout =
'3s'")` como primeira linha do `upgrade()` de `0010_strategy_purpose.py`, no
mesmo espírito de `create_partitions.py:113` — a revisão é reexecutável no run
seguinte; ou (b) parar o `strategy-worker` durante o `run --rm migrate`. Em
qualquer caso, atualizar o bullet de §15.6 para cobrir `0006`–`0010` em vez de
parar na `0005`.

**A4. A garantia "quem escreve é o script de ativação" vale para a coluna
`purpose`, não para a ativação — e §22 não diz isso.**
A `0010` tira do `hunter_worker` a capacidade de *nomear* `purpose`, mas ele
mantém `UPDATE (status, activated_at)` (`strategy_purpose.py:176-190`) e o
`DELETE` de tabela da `0001` (`ddl/grants.py:76`, nunca revogado). A trigger de
congelamento só dispara `WHEN (OLD.activated_at IS NOT NULL)`.
*Cenário concreto:* o script cria a linha paper com `--paper-line` (`draft`,
`activated_at NULL`, `paper_line.py:107-124`). Enquanto ela está `draft`, o papel
`hunter_worker` — credencial que vive em todo container de worker — pode rodar
`UPDATE strategy_versions SET status='active', activated_at=now() WHERE id=...`
e **ativar a coorte paper sem passar pelo script auditado e sem linha em
`system_events`**; ou apagá-la com `DELETE` (a guarda de DELETE também só vale
para linha ativada). Com a T3.15b, uma coorte paper ativa é admitida pela ponte.
Isso é **pré-existente desde a `0001`**, não foi introduzido pela `0010`, e o
alcance é a carteira paper, não a live — por isso não bloqueia. Mas a `0010` é
justamente a revisão que promete "escrita só pelo script", e a promessa é mais
estreita do que soa.
*Correção:* escrever a limitação em §22.3, logo abaixo da tabela papel × coluna:
"`hunter_worker` continua com `UPDATE (status, activated_at)` e `DELETE` de
tabela, então **ativar** ou **apagar** uma linha `paper` ainda em `draft` não
exige a conexão de dono; o que a `0010` garante é que o rótulo não pode ser
escrito nem alterado por ele." Se a intenção era fechar isso também, é uma `0011`
(tirar `activated_at`/`status` da lista de colunas e o `DELETE` de tabela), com o
custo de conferir quem depende deles — `builders.py:206-214,469-476` e
`test_version_roster.py:158-179` dependem.

## Depois

**D1. `WORKER_COLUMNS_EXCEPT_PURPOSE` é uma lista congelada sem teste que a
prenda ao banco** (`infra/migrations/ddl/strategy_purpose.py:176-190`).
Como `strategy_versions` já não tem `INSERT`/`UPDATE` de tabela, **toda coluna
futura nasce sem privilégio de escrita para `hunter_worker`** (o Postgres não
propaga grant de coluna para colunas novas). O único teste do lado positivo
verifica uma coluna só (`changelog`, `test_schema_privileges.py:795-810`).
*Cenário:* a `0011` acrescenta `strategy_versions.retired_reason`; meses depois
alguém faz o worker escrevê-la e leva `permission denied for column
retired_reason` em produção, sem nada no CI ter avisado.
*Correção:* um teste em `test_schema_privileges.py` que leia as colunas vivas do
`information_schema.columns` e asserte
`set(colunas) - {"purpose"} == set(WORKER_COLUMNS_EXCEPT_PURPOSE)`, falhando na
adição da coluna e não no primeiro `INSERT`.

**D2. `paper_line.py:109` gera o PK com `gen_random_uuid()` (UUID v4), não UUID v7.**
O contrato do schema é "UUID v7 gerado na aplicação"; `seed.py` respeita
(`seed.py:163`, `uuid7()`). O padrão veio de
`infra/scripts/activate_strategy_version.py:248` (`--supersede`, pré-existente),
mas a T3.15 acrescentou **uma segunda ocorrência**.
*Cenário:* `strategy_versions` deixa de ter id ordenado no tempo justamente nas
linhas mais novas; qualquer diagnóstico que ordene por id (ou que conte com
localidade de inserção no índice) passa a ver as linhas derivadas fora de ordem.
*Correção:* passar `uuid7()` do Python como bind param nos dois lugares
(`paper_line.py:109-124` e `activate_strategy_version.py:248-262`) e, se a
divergência for para ficar, registrá-la em `docs/DATABASE.md` como exceção
declarada em vez de acidente.

**D3. Contagem de caracteres do id da revisão está errada em dois lugares.**
`0010_strategy_purpose` tem **21** caracteres; o docstring da migração
(`infra/migrations/versions/0010_strategy_purpose.py:24`) diz "20 characters" e
`docs/DATABASE.md:3553` diz "22 caracteres". Inofensivo (o teto é 32), mas é um
número no contrato que não confere — e §17.6 existe porque um número desses já
derrubou a `0005`. *Correção:* trocar os dois por 21.

**D4. Modelo com `server_default="research_only"` sem aspas SQL**
(`packages/core/hunter_core/db/models/agents.py:99`). Hoje é inerte: `env.py` não
liga `compare_server_default`, não há `Base.metadata.create_all` em lugar nenhum
do repo, e o default real vem do DDL escrito à mão. Mas se alguém emitir DDL a
partir do metadata, sai `DEFAULT research_only` (referência a coluna) em vez de
`DEFAULT 'research_only'`. O mesmo padrão já existe em `status`
(`agents.py:85-87`), então é dívida antiga, não regressão.
*Correção:* `server_default=text("'research_only'")`.

**D5. O round trip da `0010` só passa por linha ativada por acidente de ordem.**
`test_0010_reverses_on_a_populated_database_and_gives_0002s_trigger_back`
(`packages/core/tests/integration/test_migrations.py:2016`) cria uma linha
`draft`; o que garante que exista uma linha **ativada** no banco durante o `DROP
COLUMN` é `test_0010_freezes_purpose_after_activation` (`:1948`) ter rodado
antes, no mesmo banco module-scoped, por ordem de definição no arquivo.
*Cenário:* alguém reordena o arquivo ou roda o teste isolado com `-k`, e o caso
que de fato importa — reverter com linha congelada presente — deixa de ser
exercido sem que nada falhe.
*Correção:* dentro do próprio teste, criar uma linha `activated=True,
purpose="research_only"` antes do `command.downgrade`, tornando a condição
explícita em vez de emergente.

**D6. `restore_purpose_write()` reconcede `INSERT, UPDATE` mas nada verifica que
era isso que a `0001` tinha.** Conferi manualmente (`ddl/grants.py:76` dá
`INSERT, UPDATE, DELETE`; a `0010` só revoga os dois primeiros, então o `DELETE`
sobrevive e o estado final confere), mas nenhum teste compara a ACL pós-downgrade
com a da `0009`. *Correção:* asserir
`has_table_privilege('hunter_worker','strategy_versions', p)` para
`INSERT/UPDATE/DELETE` dentro do bloco `finally` do round trip, antes do
`upgrade`.

**D7. `add_purpose_column()` não é idempotente** (`strategy_purpose.py:120-135`:
`ADD COLUMN` e `ADD CONSTRAINT` sem `IF NOT EXISTS`), enquanto
`drop_purpose_column()` usa `DROP CONSTRAINT IF EXISTS`. É consistente com o
resto do pacote (o Alembic garante a execução única) e não é problema — fica
anotado só para não ser confundido com esquecimento se alguém tentar reaplicar a
revisão à mão depois de um `upgrade` interrompido.

**D8. Verificação não executada nesta revisão.** O brief desta revisão proíbe
rodar suítes com testcontainers, então **eu não rodei** `alembic upgrade head`,
`alembic check`, `downgrade -1 && upgrade head`, nem o teste de isolamento RLS. A
única evidência de execução é a de `.claude/state/notes-T3.15.md` (test_migrations
49, test_schema_privileges 23, test_schema_rls 17, `alembic check` via
`test_alembic_check_reports_no_drift`), produzida pelo próprio autor da mudança.
*Correção:* antes de subir para a VPS, rodar um arquivo por invocação —
`packages/core/tests/integration/test_migrations.py`,
`test_schema_privileges.py`, `test_schema_rls.py` — e colar a saída. A revisão
acima é estática e não substitui isso.

---

**Bloqueia o deploy da VPS: não.**
