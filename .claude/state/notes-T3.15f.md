# T3.15f — `hunter_runtime`: o runtime deixa de conectar como dono

**Estado:** DONE_WITH_CONCERNS. As secoes 1-6 sao o DESENHO, escrito antes da
migracao como o brief exige; as secoes 7-10 sao o resultado da execucao.

Base: `main` @ `3bd8f3d`. Revisão nova: `0015_runtime_login_role`.

---

## 1. O achado, em uma frase

`DATABASE_URL` e `DATABASE_URL_MIGRATIONS` são hoje **a mesma credencial**
(`hunter`: `rolsuper = true`, `rolbypassrls = true`). `hunter_app` e
`hunter_worker` são papéis `NOLOGIN` concedidos a ela, e o `SET LOCAL ROLE` de
`hunter_core.db.session._apply_context` é uma **redução voluntária** — um
`RESET ROLE` a desfaz. A T3.15d tirou `DATABASE_URL_MIGRATIONS` do ambiente dos
processos de runtime e isso não mudou nada aqui: o `DATABASE_URL` que sobrou
**é** a credencial de dono.

## 2. O papel

```sql
CREATE ROLE hunter_runtime
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION NOINHERIT;
GRANT hunter_app    TO hunter_runtime WITH INHERIT FALSE, SET TRUE;
GRANT hunter_worker TO hunter_runtime WITH INHERIT FALSE, SET TRUE;
GRANT CONNECT ON DATABASE <este banco> TO hunter_runtime;
-- senha: NUNCA aqui. Passo (b) do runbook, pelo operador.
```

Membro de `hunter_app` e `hunter_worker` **e de mais nada**. O login dono
(`hunter`) continua existindo, e continua sendo o de `migrate` e `ops`.

### 2.1 `NOINHERIT` é a decisão central — e é um acréscimo ao brief

O brief pede `NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB LOGIN` e não fala
de herança. Herança é o que decide se este papel fecha ou reabre um buraco.

Com **INHERIT** (o padrão), `hunter_runtime` carrega, **sem `SET ROLE` nenhum**,
a *união* das ACLs de `hunter_app` e `hunter_worker` — e, pior,
`pg_has_role(current_user, 'hunter_app', 'USAGE')` e
`pg_has_role(current_user, 'hunter_worker', 'USAGE')` são **as duas
verdadeiras**. Toda guarda do schema que distingue "a aplicação e nada além
dela" de "o motor e nada além dele" está escrita exatamente nessa forma:

| Guarda | Condição | O que uma conexão com os dois papéis faz |
|---|---|---|
| `trade_proposals_the_app_only_files_requests` (§19.4/§21.2) | `pg_has_role(app,'USAGE') AND NOT pg_has_role(worker,'USAGE')` | **não dispara** |
| `portfolios_are_born_audited` (§20.2) | `pg_has_role(worker,'USAGE') AND NOT pg_has_role(app,'USAGE')` | **não dispara** |
| `portfolio_risk_state_guard` (§18.7) | `pg_has_role(worker,'USAGE')` | trata como motor |

As duas primeiras são escritas assim de propósito: "quem tem os dois papéis é o
operador". Um login de runtime com os dois papéis herdados é lido pelo schema
**como se fosse o operador** — e com a união dos privilégios na mão isso é um
`INSERT INTO trade_proposals (status='approved', risk_decision=…)` que o Risk
Engine nunca tomou, escrito de dentro de um request handler comprometido.
Fecharíamos a porta da frente (a DSN de dono) reabrindo a janela que a §19.4
existe para fechar.

Com **NOINHERIT**:

- `pg_has_role(current_user, …, 'USAGE')` é **falso** para os dois enquanto não
  houver `SET ROLE`, e o privilégio efetivo do login é **nenhum**. Um caminho de
  código que esqueça o `SET LOCAL ROLE` falha alto com *permission denied* em
  vez de rodar em silêncio com a união;
- depois de `SET LOCAL ROLE hunter_app`, `current_user` **é** `hunter_app`: as
  guardas voltam a morder exatamente como hoje, e o mesmo vale para
  `hunter_worker`;
- `RESET ROLE` — a reversão voluntária que o achado cita — passa a devolver
  **nada**.

`SET ROLE` continua permitido: ele depende da *membership* (opção `SET`), nunca
de `INHERIT`.

### 2.2 `BYPASSRLS` continua funcionando para os workers

Atributo de papel **nunca** é herdado. `hunter_runtime` é `NOBYPASSRLS`; o
`SET ROLE hunter_worker` faz `GetUserId()` virar `hunter_worker`, cujo
`rolbypassrls` é `true`, e `check_enable_rls` lê o atributo do papel corrente.
Então `strategy`/`execution`/`analytics` continuam varrendo todas as
organizações, e a API (`hunter_app`) continua sem bypass. **Medido em teste, não
suposto** (§5).

## 3. O que o runtime executa hoje que precisa de dono — a varredura

| Procurado | Encontrado em `apps/api/hunter_api/**` e `services/*/hunter_*/**` |
|---|---|
| `CREATE` / `ALTER` / `DROP` / `TRUNCATE` | **nada** |
| criação de partição | **nada** — é `infra/scripts/create_partitions.py` / `prune_partitions.py`, que já rodam pelo `ops` (T3.15e) |
| `LISTEN` / `NOTIFY` | **nada** |
| advisory lock | só `pg_advisory_xact_lock` (`market-worker/recovery_queries.py:147`) — **de transação**, seguro atrás do pooler, e sem privilégio especial |
| `DATABASE_URL_MIGRATIONS` | nenhum processo de runtime a lê desde a T3.15d |

**Uma coisa quebra, e não é DDL: quatro conexões sem `SET ROLE`.**

| Arquivo | O que faz |
|---|---|
| `services/scanner-worker/hunter_scanner_worker/main.py:286` (`_warm`) | `engine.begin()` cru → `cache.refresh(connection, …)` lê `feature_baselines` |
| `services/scanner-worker/hunter_scanner_worker/refresh.py:138` | `engine.begin()` cru → lê `feature_snapshots` e **escreve** `feature_baselines` (`SqlBaselineStore.append`) |
| `services/scanner-worker/hunter_scanner_worker/refresh.py:173` | idem (recarga do cache) |
| `services/scanner-worker/hunter_scanner_worker/refresh.py:203` | idem (`reload_market`) |

Hoje isso funciona porque o login é o dono. Sob `hunter_runtime` **NOINHERIT**
é *permission denied for table feature_baselines*. É o **único** achado da
varredura e é **pré-requisito do passo (d)** do runbook — não da migração. O
ajuste é uma linha em cada um dos quatro (`services/**` não é deste diff):

```python
async with engine.begin() as connection:
    await connection.execute(text("SET LOCAL ROLE hunter_worker"))
    ...
```

## 4. A migração `0015_runtime_login_role`

Idempotente, **sem senha**, e o padrão de prova é o de `ddl/security.py`
`create_roles()` (§15.6): tenta, tolera não poder, e **verifica o resultado no
catálogo**, falhando com os comandos manuais exatos em vez de degradar para um
`NOTICE`.

1. `CREATE ROLE` num bloco `DO` que tolera `duplicate_object` e
   `insufficient_privilege`;
2. `ALTER ROLE` normalizando os atributos (idempotente, e é o que conserta um
   papel pré-existente criado errado), tolerando `insufficient_privilege`;
3. **verificação** em `pg_roles`: existe? `rolcanlogin`? e
   `rolsuper|rolbypassrls|rolcreaterole|rolcreatedb|rolinherit` todos falsos?
   Qualquer não → `RAISE EXCEPTION` nomeando o `CREATE`/`ALTER` a rodar como
   superusuário;
4. as duas memberships, `WITH INHERIT FALSE, SET TRUE` (PG16), toleradas e
   depois **verificadas** em `pg_auth_members`;
5. `GRANT CONNECT` no banco corrente (SQL dinâmico com `format`/`EXECUTE`,
   porque o nome do banco não é literal), tolerado e depois verificado com
   `has_database_privilege` — que é verdadeiro mesmo se o `GRANT` foi recusado,
   porque `PUBLIC` já tem `CONNECT`: o que se prova é o **resultado**, não o
   comando.

**Nada de senha, e nada de afirmar sobre ela.** `pg_authid.rolpassword` só é
legível por superusuário, então a migração não pode verificar que existe uma —
e não finge que pode. Quem a define é o operador, no passo (b).

**Nenhum `GRANT` de tabela.** O privilégio do runtime é exatamente o de
`hunter_app`/`hunter_worker`, alcançado por `SET ROLE`. Conceder tabela ao login
criaria uma terceira ACL a manter e a divergir (§24.5: escrever DDL para
*parecer* garantia é o erro que a §15.6 registra).

### 4.1 Downgrade

Reverso exato, e o `DROP ROLE` **só quando nada mais depende do papel**.

Papel é objeto de **cluster**; migração é de **banco**. No mesmo cluster pode
haver outro banco já na `0015` — é literalmente o caso do container de teste,
com quatro bancos —, e o `GRANT CONNECT` de cada um deixa uma linha em
`pg_shdepend`. Um `DROP ROLE` incondicional ou falharia com
*dependent objects still exist*, ou apagaria o login de um banco que ainda o
usa. Então o downgrade:

1. `REVOKE CONNECT` no banco corrente;
2. `REVOKE hunter_app, hunter_worker FROM hunter_runtime`;
3. conta o que o papel ainda possui (`pg_class`/`pg_namespace`/`pg_proc`/
   `pg_type`/`pg_database` por dono) e as dependências restantes em
   `pg_shdepend`. **Zero → `DROP ROLE`. Qualquer coisa → deixa o papel de pé**,
   com um `NOTICE` nomeando o que resta.

Um login sem membership e sem `CONNECT` neste banco não alcança nada; deixá-lo
de pé é o oposto de deixar privilégio para trás. É também o precedente da
`0001`, cujo downgrade nunca derruba `hunter_app`/`hunter_worker`.

**Declarado:** membership é cluster-wide, então o downgrade **num** banco a
revoga para todos os bancos daquele cluster. É inerente a papel de cluster e
vale igual para o `CREATE ROLE` do upgrade; na VPS há um banco só.

## 5. Prova

- `alembic upgrade head` em banco limpo, `alembic check`, `downgrade -1` +
  `upgrade head` da `0015`;
- login **de verdade** como `hunter_runtime` (senha aplicada no teste, pelo
  dono — nunca no repo) e, por essa conexão:
  - `rolsuper`/`rolbypassrls`/`rolcreaterole`/`rolcreatedb`/`rolinherit` falsos;
  - `pg_has_role(…,'USAGE')` falso e `…,'MEMBER'` verdadeiro para os dois papéis;
  - **isolamento**: `tenant_session` como `hunter_app` com o `app.current_org`
    da org A não enxerga uma linha da org B (o teste de RLS do §1.2);
  - `SET ROLE hunter_worker` **tem** bypass; `SET ROLE hunter_app` **não** tem;
  - `SET ROLE` para o dono é recusado;
  - `ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY` recusado — antes e
    depois de `SET ROLE`;
  - `UPDATE strategy_versions SET purpose='paper'` recusado — antes (sem
    privilégio nenhum) e depois de `SET ROLE hunter_worker` (coluna, §22.3);
  - sem `SET ROLE`, um `SELECT` numa tabela de tenant é *permission denied*
    (a prova de que `NOINHERIT` está valendo).

## 6. Compose, `.env` e runbook

`HUNTER_RUNTIME_DB_PASSWORD` é chave nova. `infra/scripts/setup_env.sh` a gera
(e a preserva numa reexecução, como faz com `POSTGRES_PASSWORD`); os composes a
consomem **por nome**. `migrate` e `ops` continuam com a DSN de dono.

O runbook (`docs/DEPLOYMENT.md` §3.5) é: (a) aplicar a `0015` no deploy,
(b) o operador define a senha pelo `ops`, (c) põe a chave no `.env`,
(d) `compose.sh update`, (e) verificar de dentro do `api`. Rollback: voltar o
`DATABASE_URL` para o dono e subir de novo — a `0015` não precisa ser revertida
para isso.

---

# Resultado da execução (2026-09-08)

## 7. Arquivos

| Arquivo | O que |
|---|---|
| `infra/migrations/ddl/runtime_login_role.py` | **novo** — listas congeladas (`RUNTIME_ROLE`, `RUNTIME_MEMBER_OF_0015`, `RUNTIME_ATTRIBUTES_0015`) e as duas funções da revisão |
| `infra/migrations/versions/0015_runtime_login_role.py` | **novo** — a revisão (23 caracteres) |
| `packages/core/tests/integration/test_runtime_login_role.py` | **novo** — 8 testes, com login de verdade como `hunter_runtime` |
| `packages/core/tests/integration/test_migrations.py` | `HEAD_REVISION` + 4 testes de catálogo da `0015`; o teste da `0014` passou a descer por nome |
| `packages/core/hunter_core/db/session.py` | parágrafo no docstring do módulo (297 linhas, dentro do orçamento) |
| `infra/scripts/setup_env.sh` | gera/preserva `HUNTER_RUNTIME_DB_PASSWORD` (perfil `--vps`) e imprime o passo (b) quando a senha nasce agora |
| `docs/DATABASE.md` | §23.5 reescrita (HIGH 1 fecha só depois de (a)–(e)) e §27 nova |
| `docs/DEPLOYMENT.md` | §3.5 (runbook (a)–(e) + rollback) e a linha de `HUNTER_RUNTIME_DB_PASSWORD` na tabela de env |
| `docs/SECURITY.md` | linha na tabela do §5 e o bloco "O papel de banco do runtime é um limite, não uma convenção" |

**Não commitado.** **Não tocado:** `.env*` (só o nome da chave), `apps/**`,
`services/**`, `obsidian/**`, os dois composes, a VPS.

## 8. O diff que a T3.15e / devops tem de aplicar nos composes

Eu não editei os composes (a T3.15e está neles). São **duas linhas**, uma em
cada arquivo, e nada mais: `migrate` e `ops` continuam com
`x-owner-env`/`x-prod-owner-env` intactos.

### `infra/docker/docker-compose.yml`

```diff
 x-api-env: &api-env
-  DATABASE_URL: postgresql+asyncpg://hunter:hunter@postgres:5432/hunter
+  # T3.15f: o runtime conecta como `hunter_runtime` (0015), nunca mais como o
+  # dono. O default é só do stack local; a senha do papel é aplicada uma vez
+  # com `ALTER ROLE` (docs/DEPLOYMENT.md §3.5 passo (b)) — inclusive aqui, ou
+  # `api`/workers não autenticam.
+  DATABASE_URL: postgresql+asyncpg://hunter_runtime:${HUNTER_RUNTIME_DB_PASSWORD:-hunter_runtime}@postgres:5432/hunter
   REDIS_URL: redis://redis:6379/0
   HUNTER_ENV: development
```

No stack local, uma vez, depois do `migrate`:

```bash
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U hunter -d hunter -c "ALTER ROLE hunter_runtime PASSWORD 'hunter_runtime';"
```

(Se a devops preferir não ter literal nenhum no compose de dev, a alternativa é
`${HUNTER_RUNTIME_DB_PASSWORD:?...}` como no prod — o preço é que o stack local
deixa de subir sem `.env`, quebrando a promessa "works with zero .env" do topo
do arquivo. A escolha é da T3.15e; o `hunter:hunter` que está lá hoje é o
precedente para o default.)

### `infra/vps/docker-compose.prod.yml`

```diff
 x-prod-db-env: &prod-db-env
-  DATABASE_URL: postgresql+asyncpg://hunter:${POSTGRES_PASSWORD:?defina POSTGRES_PASSWORD no .env (infra/scripts/setup_env.sh --vps)}@postgres:5432/hunter
+  # T3.15f (docs/DATABASE.md §27, docs/DEPLOYMENT.md §3.5): login sem
+  # superusuário, sem BYPASSRLS e sem herança. A senha é aplicada no papel pelo
+  # operador (passo (b)) e só então entra no .env (passo (c)).
+  DATABASE_URL: postgresql+asyncpg://hunter_runtime:${HUNTER_RUNTIME_DB_PASSWORD:?defina HUNTER_RUNTIME_DB_PASSWORD no .env (infra/scripts/setup_env.sh --vps) e aplique a senha no papel: docs/DEPLOYMENT.md §3.5 passo (b)}@postgres:5432/hunter
   REDIS_URL: redis://redis:6379/0
   HUNTER_ENV: staging
```

Ordem obrigatória na VPS: (a) `update` que aplica a `0015` → (b) `ALTER ROLE` →
(c) chave no `.env` → (d) este diff + `update`. Aplicar o diff antes de (b)/(c)
derruba `api` e todos os workers na autenticação.

### `.env.example` (não tocado — `.env*` está fora do escopo)

Acrescentar, ao lado de `DATABASE_URL`:

```
# senha do login hunter_runtime (0015); gerada por infra/scripts/setup_env.sh
# --vps e aplicada no papel pelo operador (docs/DEPLOYMENT.md §3.5 passo b)
HUNTER_RUNTIME_DB_PASSWORD=
```

## 9. Testes, com saída real

### 9.1 `alembic upgrade head` em banco limpo, `check`, `downgrade -1` da `0015`, `upgrade head`

O head passou a ser `0016_exchange_status_planned` no meio desta tarefa (outra
tarefa empilhou a revisão dela sobre a minha), então o `-1` da **`0015`** exige
um passo nomeado antes. Testcontainer `postgres:16-alpine`, banco vazio:

```
$ alembic upgrade head            # clean database
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial_schema, ...
...
INFO  [alembic.runtime.migration] Running upgrade 0014_lab_signals_indexes -> 0015_runtime_login_role, the runtime stops connecting as the owner: a login role without superuser
INFO  [alembic.runtime.migration] Running upgrade 0015_runtime_login_role -> 0016_exchange_status_planned, ...

$ alembic current
0016_exchange_status_planned (head)

$ alembic check
No new upgrade operations detected.

$ alembic downgrade 0015_runtime_login_role    # head is 0016 (concurrent task)
INFO  [alembic.runtime.migration] Running downgrade 0016_exchange_status_planned -> 0015_runtime_login_role, ...

$ alembic downgrade -1            # 0015 -> 0014, the new revision
INFO  [alembic.runtime.migration] Running downgrade 0015_runtime_login_role -> 0014_lab_signals_indexes, the runtime stops connecting as the owner: a login role without superuser

$ alembic current
0014_lab_signals_indexes

$ alembic upgrade head            # 0014 -> 0015 -> 0016
INFO  [alembic.runtime.migration] Running upgrade 0014_lab_signals_indexes -> 0015_runtime_login_role, the runtime stops connecting as the owner: a login role without superuser
INFO  [alembic.runtime.migration] Running upgrade 0015_runtime_login_role -> 0016_exchange_status_planned, ...

$ alembic current
0016_exchange_status_planned (head)

$ alembic check
No new upgrade operations detected.

OK
```

### 9.2 Isolamento de RLS e as duas recusas, pelo login de verdade

```
$ uv run pytest packages/core/tests/integration/test_runtime_login_role.py -q
........                                                                 [100%]
8 passed in 42.84s
```

Os oito, por nome:

| Teste | O que prova |
|---|---|
| `test_the_runtime_login_is_not_the_owner_and_holds_no_power` | `current_user = 'hunter_runtime'`; `rolsuper`/`rolbypassrls`/`rolcreaterole`/`rolcreatedb`/`rolinherit` todos `false` (é a consulta do passo (e)) |
| `test_without_set_role_the_runtime_login_reaches_no_table` | sem `SET ROLE`, `SELECT count(*) FROM workspaces` → *permission denied* (o `NOINHERIT` valendo) |
| `test_org_a_cannot_read_org_bs_rows_through_the_runtime_login` | **isolamento**: `tenant_session` com o org de A lê só a linha de A; e o simétrico para B |
| `test_the_engine_role_still_bypasses_rls_through_the_runtime_login` | `SET ROLE hunter_worker` continua enxergando as duas organizações |
| `test_the_runtime_login_cannot_disable_row_level_security` | `ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY` → *must be owner of table portfolios*, nos três papéis alcançáveis |
| `test_the_runtime_login_cannot_promote_a_strategy_version_to_paper` | `UPDATE strategy_versions SET purpose='paper'` → *permission denied*, nos três |
| `test_the_runtime_login_cannot_become_the_owner` | `SET LOCAL ROLE <dono>` → *permission denied to set role* |
| `test_the_guards_still_tell_the_application_and_the_engine_apart` | `pg_has_role(current_user, …, 'USAGE')`: `(false,false)` sem `SET ROLE`, `(true,false)` como app, `(false,true)` como worker |

### 9.3 Catálogo e round trip da revisão

```
$ uv run pytest packages/core/tests/integration/test_migrations.py -q \
    -k "0015 or alembic_check or new_revision_reverses or downgrade_base"
.......                                                                  [100%]
7 passed, 97 deselected in 72.56s (0:01:12)
```

E o arquivo inteiro, antes de a `0016` existir:

```
$ uv run pytest packages/core/tests/integration/test_migrations.py -q
100 passed in 349.59s (0:05:49)
```

### 9.4 Privilégios (nenhuma regressão nas classes de grant)

```
$ uv run pytest packages/core/tests/integration/test_schema_privileges.py -q
42 passed in 159.61s (0:02:39)
```

### 9.5 As duas suítes que o brief nomeia

```
$ uv run pytest services/strategy-worker/tests/test_shadow_decisions.py -q
15 passed in 132.97s (0:02:12)

$ uv run pytest apps/api/tests/integration/test_isolation.py -q
1 failed, 28 passed in 289.75s (0:04:49)
```

A única falha é **de outra tarefa e não deste diff**:
`test_the_route_list_covers_every_tenant_route_the_app_serves` conta
`assert 24 == 23` — uma rota nova sob `/api/v1/orgs/{org_id}` entrou com o
trabalho em voo de `apps/api/hunter_api/routers/regime.py` (T3.43) sem entrar na
lista do teste. É exatamente a guarda de cobertura da §20.4 fazendo o trabalho
dela. Os **28 testes de isolamento passam**.

### 9.6 Lint, tipos e orçamento de arquivo

```
$ uv run ruff check infra/migrations infra/scripts packages/core/hunter_core/db packages/core/tests/integration
All checks passed!

$ uv run ruff format --check infra/migrations packages/core/hunter_core/db packages/core/tests/integration
99 files already formatted

$ uv run pyright <os 5 arquivos .py deste diff>
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
error   380 > 350  apps/api/hunter_api/services/system_status.py
error   369 > 350  infra/scripts/seed_reference.py
error   360 > 350  infra/scripts/seed.py
scanned 571 files; 3 over budget, 0 grandfathered

$ bash -n infra/scripts/setup_env.sh
syntax ok
```

Os três acima do orçamento são de trabalho em voo de outras tarefas (as três
estavam em 349 linhas no `HEAD`); nenhum arquivo deste diff aparece.
`ruff check` na árvore inteira também acusa um import não usado em
`packages/core/hunter_core/strategies/registry.py` — T3.45, não é deste diff.

## 10. Concerns

1. **O HIGH-1 continua aberto até o passo (d).** A `0015` cria o papel; ela não
   troca credencial nenhuma. Enquanto o `DATABASE_URL` do compose nomear
   `hunter`, tudo que o achado descreve continua alcançável. Registrado na
   §23.5 com a tabela (a)–(e), e é o motivo de o relatório ser
   `DONE_WITH_CONCERNS`.
2. **Bloqueador do passo (d): quatro conexões do scanner-worker sem `SET
   ROLE`** (`main.py::_warm`, `refresh.py` ×3). Sob `hunter_runtime` elas
   respondem *permission denied for table feature_baselines*. Conserto de uma
   linha em cada (`SET LOCAL ROLE hunter_worker` como primeiro statement), e é
   do dono de `services/**` — que está com o arquivo aberto agora (T3.43 mexe em
   `scanner-worker/main.py`). DATABASE.md §27.5.
3. **`NOINHERIT` é acréscimo ao brief.** O brief não menciona herança; sem ela o
   papel reabriria as guardas de `pg_has_role` (§27.1). Está escrito na
   DATABASE.md §27.1 e é a decisão que mais merece revisão do security-reviewer.
4. **A migração recusa uma terceira membership.** ~~Conceder à mão um papel de
   monitoração a `hunter_runtime` passa a derrubar o próximo deploy.~~
   **Corrigido na T3.15g (revisão de segurança, BAIXA 7): esta frase prometia um
   alarme que não existe.** A verificação roda quando a `0015` roda, e a `0015`
   não roda de novo num banco que já está nela — um `compose.sh update` na VPS
   não tem o que aplicar. O que ela de fato pega é um **banco novo** do mesmo
   cluster (papel é objeto de cluster, a membership extra já está lá), um
   `downgrade`+`upgrade`, e a CI, que migra do zero. É guarda de
   *provisionamento*, não monitor contínuo. Continua deliberado (§27.3, onde a
   redação também foi corrigida) e continua sendo a única forma de falha nova
   que a revisão introduz — só que num banco novo, não no próximo deploy.
5. **O downgrade pode deixar o papel de pé** quando outro banco do mesmo cluster
   ainda está na `0015` (§27.4). Ele sempre remove o alcance (memberships +
   `CONNECT` deste banco); o que pode sobrar é um login inerte.
6. **As duas suítes nomeadas rodaram como o dono**, não como `hunter_runtime`:
   apontar `DATABASE_URL` delas para o login novo exige editar
   `apps/api/tests/integration/conftest.py` e o conftest do strategy-worker, e
   `apps/**`/`services/**` estão fora deste diff. O que substitui isso é
   `test_runtime_login_role.py`, que faz o login de verdade e roda o isolamento
   pelo mesmo `tenant_session` que a API usa. Desvio declarado em relação ao
   item 2 do brief.
7. **`.env.example` não foi tocado** (`.env*` fora do escopo): o texto exato a
   acrescentar está no §8 acima.
8. **A `0016` apareceu no meio da tarefa.** Outra tarefa empilhou
   `0016_exchange_status_planned` sobre a `0015`, ajustou `HEAD_REVISION` e
   adaptou dois dos meus testes para descerem por nome em vez de `-1`. Reli e as
   adaptações estão certas; a suíte foi reexecutada depois disso (§9.2, §9.3).

---

## Revisão (security)

**Veredito: APPROVE WITH RESERVATIONS.** O diff é uma melhora estrita e
fecha-por-construção o que promete no lado do banco; nada aqui deve ser
revertido. As reservas são uma reivindicação de escopo que a doc exagera (ALTA 1)
e três armadilhas operacionais que aparecem depois do passo (a).

### Verificado (não confiei no relatório)

| Ponto | Evidência |
|---|---|
| `NOINHERIT` é mesmo a decisão central | `ddl/paper_roles.py:125` `_CALLER_IS_THE_APP = (has_app AND NOT has_worker)`; `ddl/paper_roles_2.py:81` o espelho; `ddl/paper.py:203,216`. Um login com os dois herdados satisfaz os dois lados e não dispara nenhuma das duas guardas — confirmado no código, não só na doc |
| `BYPASSRLS` continua chegando ao motor | atributo lido do papel corrente; `SET ROLE hunter_worker` o restaura. Medido em `test_runtime_login_role.py:225` |
| Sem senha no repo | `HUNTER_RUNTIME_DB_PASSWORD` aparece em 6 arquivos, todos doc/script — nenhum valor. `test_runtime_login_role.py:79` gera hex efêmero |
| Idempotência / aplicar antes da troca | só `CREATE ROLE` + 2 memberships + `CONNECT`; nenhum lock de relação; o papel nasce sem senha e o `pg_hba` da imagem é `scram-sha-256` (nenhum `POSTGRES_HOST_AUTH_METHOD`), então a `0015` sozinha não dá acesso a ninguém. Verificação fail-closed antes de seguir |
| Recusa da terceira membership | `runtime_login_role.py:298-306`; o auto-grant do PG16 ao criador é `member=criador`, não casa com o filtro — sem falso positivo |
| Varredura das 4 conexões | reproduzida: `scanner-worker/main.py:291`, `refresh.py:138,173,203`. Nenhuma outra em `apps/api/hunter_api/**` nem `services/*/hunter_*/**`. `strategy-worker/activation_db.py:115` é `engine.connect()` cru mas usa `DATABASE_URL_MIGRATIONS` (`:50`), é do `ops` — fora do alcance |
| `SET LOCAL ROLE hunter_worker` resolve as 4 | `feature_baselines` é APPEND do worker (`ddl/analysis.py:74`), `feature_snapshots` é WORKER_WRITE (`ddl/tables.py:148`) |
| Nada mais quebra em (d) | `check_database` é `SELECT 1`; ops scripts todos em `DATABASE_URL_MIGRATIONS`; `request_backfill`/`open_paper_wallet` já usam `role_session(hunter_worker)` |

### Achados

**ALTA 1 — `docs/DATABASE.md` §23.5 / §27.1, `docs/SECURITY.md` §5: a doc
declara fechado, depois de (a)–(e), um furo que um login único não fecha.**
`hunter_runtime` é membro dos *dois* papéis, e `SET ROLE` depende só da opção
`SET`. Um RCE no `api` faz `SET LOCAL ROLE hunter_worker` e ganha `BYPASSRLS`
(§27.2 é a prova disso) + os grants de escrita de execução: lê e escreve toda
organização e insere `trade_proposals` já `approved` com `risk_decision`
forjado — porque `trade_proposals_the_app_only_files_requests` só morde
`app AND NOT worker`. É **exatamente** o cenário que `runtime_login_role.py:26-29`
usa para justificar o `NOINHERIT`, alcançado por outro caminho. Não é regressão
(hoje é pior: a DSN é superusuário) e não bloqueia a entrega; o que precisa
mudar é a afirmação: o `NOINHERIT` fecha o caminho *silencioso*, não o
deliberado. O fechamento de verdade são dois logins (`hunter_api` → só
`hunter_app`; `hunter_worker_login` → só `hunter_worker`), um por serviço no
compose. Registrar como risco residual declarado na §27 antes de dizer
"HIGH 1 fechado".

**MÉDIA 2 — `infra/migrations/ddl/runtime_login_role.py:369-400`: o downgrade
apaga a senha junto com o papel, em silêncio, e o próximo `update` não avisa.**
Na VPS (um banco só, papel sem objetos) o `DROP ROLE` acontece — o `NOTICE`
existe só no caminho em que ele *não* acontece. Cenário: operador desce a `0015`
por qualquer motivo; qualquer `compose.sh update` seguinte roda
`alembic upgrade head`, recria o papel **sem senha**, e `api` + todos os workers
param de autenticar com o `HUNTER_RUNTIME_DB_PASSWORD` que continua no `.env`.
Falta uma linha no `docs/DEPLOYMENT.md` §3.5 (Rollback, :370): *depois de
qualquer downgrade da `0015`, refazer o passo (b) com o valor que já está no
`.env` antes de subir*.

**MÉDIA 3 — `docs/DEPLOYMENT.md:300` e `:361`, `infra/scripts/setup_env.sh:310`:
a senha do runtime entra na linha de comando.** `psql -v pw="$RUNTIME_PW"` e
`psql "postgresql://hunter_runtime:$RUNTIME_PW@localhost:5432/hunter"` colocam o
segredo em `/proc/<pid>/cmdline`, legível por qualquer usuário da VPS enquanto o
comando roda (a doc avisa do histórico do shell, :306, mas não disso). Forma sem
argv e sem log: `psql -U hunter -d hunter` interativo + `\password hunter_runtime`
(manda o hash SCRAM, nunca o texto), ou o SQL por stdin. A verificação opcional
de :360-362 pode ser feita sem senha nenhuma, pelo próprio `api` (`SET ROLE` +
as duas recusas), como o teste de integração faz.

**MÉDIA 4 — nada em CI pega uma quinta conexão sem `SET LOCAL ROLE`.** As duas
suítes nomeadas rodaram como dono (§10.6) e todos os conftests conectam como
dono; as quatro do scanner só apareceram por grep humano. Enquanto os testes
autenticarem como dono, um caminho novo que esqueça o `SET LOCAL ROLE` passa em
CI e cai em produção depois de (d). O `test_runtime_login_role.py` prova o papel,
não os call sites. Sugestão para o dono de `apps/**`/`services/**`: apontar pelo
menos um conftest de integração para `hunter_runtime`.

**BAIXA 5 — `packages/core/hunter_core/db/session.py:114-126`: o docstring de
`get_session` ficou desatualizado** ("for global tables, migrations, or workers
that bypass RLS"). Sob `hunter_runtime` essa função não alcança tabela nenhuma.
Não é usada em produção hoje (só em testes), mas é o convite exato para o caso
da MÉDIA 4. O parágrafo novo do módulo (:43-61) diz o certo; o da função,
não.

**BAIXA 6 — `docs/DEPLOYMENT.md:299,334,360`: `docker compose -p hunter exec`
sem os dois `-f` nem `--env-file`**, contra a razão de existir do
`infra/vps/compose.sh` (:65-67 — "os dois -f na ordem certa"); não há
`docker-compose.yml` na raiz do repo. Improvisar no meio de uma troca de
credencial, com a senha viva na sessão, é o pior momento para descobrir isso.
`bash infra/vps/compose.sh exec -T postgres …` funciona (catch-all, :182).

**BAIXA 7 — `.claude/state/notes-T3.15f.md` §10.4 ("derruba o próximo deploy"):
impreciso.** A `0015` não roda de novo num banco já migrado; a terceira
membership só derruba um banco **novo** do mesmo cluster (papel é de cluster) ou
um re-upgrade. O comportamento é bom; a frase promete um alarme que não existe.

**BAIXA 8 — `WITH INHERIT FALSE, SET TRUE` é PG16+** e o `DO` só tolera
`insufficient_privilege`: num cluster PG15 a `0015` morre com erro de sintaxe e
trava o `migrate`. Todos os composes fixam `postgres:16-alpine`, então é só uma
restrição a declarar na §27.3.

### Checklist de "trancar o operador para fora"

Nada encontrado: a `0015` não toca o login dono, o downgrade não derruba
`hunter_app`/`hunter_worker` (precedente da `0001`), e as verificações falham
com o `CREATE`/`ALTER`/`GRANT` exato na mensagem. O único caminho de indisponi-
bilidade é o da MÉDIA 2, e é operacional, não de migração. O `setup_env.sh`
preserva a senha existente (:47) e grita quando ela nasce agora (:308) — que era
a armadilha óbvia e está coberta.

---

## T3.15g — as reservas da revisão de segurança, fechadas

**Estado:** DONE. Nada da `0015` foi revertido — a revisão pediu o contrário
("o diff é uma melhora estrita; nada aqui deve ser revertido"). O que muda é
uma **reivindicação de escopo** que a doc exagerava (ALTA 1), duas armadilhas
operacionais (MÉDIA 2, MÉDIA 3), a ausência de rede em CI (MÉDIA 4) e quatro
correções de precisão (BAIXA 5–8).

### 1. ALTA 1 — a doc parou de dizer "HIGH 1 fechado depois de (a)–(e)"

`docs/DATABASE.md` §23.5, §27.1 e `docs/SECURITY.md` §5. O resíduo agora está
escrito com o mecanismo, não com adjetivos:

> `hunter_runtime` é membro dos **dois** papéis e `SET ROLE` depende só da opção
> `SET` da membership — nunca de `INHERIT`. Um RCE no `api` faz
> `SET LOCAL ROLE hunter_worker`, ganha `BYPASSRLS` (§27.2) mais os grants de
> escrita da execução, e lê e escreve toda organização. A guarda que limita a
> API a arquivar pedidos é `app AND NOT worker` e **não morde** uma sessão que
> virou o worker; `portfolios_are_born_audited` morde, mas só exige uma linha de
> `audit_logs` na mesma transação, que a própria sessão escreve.

§23.5 ganhou uma tabela de quatro linhas separando o que (a)–(e) **compram**
(três) do que sobra (uma), para que "melhora estrita" e "fechado" parem de ser
lidos como sinônimos. §27.1 ganhou o bloco *"O que um login único não fecha"*
com o resíduo, três atenuantes declarados (não é regressão; não bloqueia o
deploy; o que sobra é superfície de tenant/execução, nunca de schema — o login
não é dono de nada) e o desenho de **dois logins como nota de T3.15h**, não
implementado:

```sql
CREATE ROLE hunter_runtime_api    LOGIN … NOINHERIT;   -- só hunter_app
CREATE ROLE hunter_runtime_worker LOGIN … NOINHERIT;   -- só hunter_worker
```

**E a nota nomeia o obstáculo real**, que a revisão não tinha como saber sem
abrir o `apps/api`: o `api` de hoje roda como `hunter_worker` em
`auth/principal.py:231` (resolver o id do Clerk em **toda** requisição
autenticada), `services/clerk_webhook.py` e `services/invitations.py:193` — as
políticas de `users` são chaveadas em `app.current_user`, então essas buscas
precisam atravessar a RLS. Ou esses caminhos mudam (papel novo, estreito, só
para identidade — revisão de schema), ou o login do `api` volta a ser membro dos
dois e a T3.15h **não entrega nada**. É o coração daquela tarefa, e está escrito
lá para ela não começar acreditando que é configuração de compose.

### 2. MÉDIA 2 — o downgrade avisa também quando derruba o papel

`infra/migrations/ddl/runtime_login_role.py::_drop_role_if_nothing_depends_on_it`.
O ramo que **mantém** o papel sempre teve `NOTICE`; o que o **derruba** — que é
justamente o que acontece na VPS, um banco só, papel sem objetos — era mudo. Ele
passa a dizer que a senha foi junto e que o passo (b) tem de ser refeito.

`docs/DEPLOYMENT.md` §3.5, Rollback, ganhou o parágrafo que é o controle de
verdade (um `NOTICE` no meio de um log de deploy não é): *depois de qualquer
downgrade da `0015`, refazer o passo (b) com o valor que já está no `.env`,
antes de voltar à DSN nova* — com o sintoma nomeado (`api` e todos os workers
falhando autenticação com um `.env` que parece correto, porque o
`upgrade head` do `update` seguinte recria o papel **sem senha**).

### 3. MÉDIA 3 — a senha nunca mais passa por `argv`

`docs/DEPLOYMENT.md` §3.5 passo (b) e `infra/scripts/setup_env.sh`. Saíram
`psql -v pw="$RUNTIME_PW"` e a URL `postgresql://hunter_runtime:$PW@…` (as duas
legíveis em `/proc/<pid>/cmdline` por qualquer usuário da máquina enquanto
rodam). Entraram duas formas:

- **`\password hunter_runtime`** no `psql` interativo — o cliente calcula o hash
  SCRAM-SHA-256 e o texto puro não chega nem ao servidor (nem a
  `log_statement = 'all'`, nem ao `~/.psql_history`);
- **SQL por stdin**, para sessão sem TTY, lendo o valor que já está no `.env`.

A verificação opcional do passo (e) foi reescrita para **não usar senha
nenhuma**: ela roda pela conexão que o `api` já tem, faz `SET LOCAL ROLE` e
tenta as duas recusas. É prova mais forte, além de mais segura — prova a
conexão que está em produção, não uma que o operador montou à mão.

O passo (c) ganhou a frase que a ordem exige: (b) e (c) podem trocar de ordem
(a forma por stdin lê do `.env`, então nela o (c) vem primeiro), o que não pode
é os dois valores diferirem.

### 4. MÉDIA 4 — uma quinta conexão crua agora falha em CI

**Novo:** `packages/core/tests/unit/test_no_raw_engine_begin.py` (6 testes,
unitário, sem banco). Varre `apps/api/hunter_api/**` e `services/*/hunter_*/**`
atrás de `engine.begin(` / `engine.connect(` (receptor terminando em `engine`,
para não varrer junto o `connection.begin()` de dentro de um helper) e compara
com um allowlist **por arquivo e por contagem**:

| Arquivo | Sancionadas | Por quê |
|---|---|---|
| `scanner-worker/…/main.py` | 1 | TODO(T3.15g): `_warm`; pré-requisito do passo (d) |
| `scanner-worker/…/refresh.py` | 3 | TODO(T3.15g): idem, `SqlBaselineStore.append` |
| `strategy-worker/…/activation_db.py` | 1 | não é runtime — `DATABASE_URL_MIGRATIONS`, a DSN de dono do `ops` |

A contagem é **exata nos dois sentidos**: uma quinta conexão falha, e uma
entrada que sobreviveu ao próprio conserto também — quando o dono de
`services/**` arrumar os quatro sites do scanner, o último passo do conserto é
apagar a entrada, e o teste diz isso na mensagem. Por que contagem e não
`arquivo:linha`: o conserto acrescenta uma linha em cada transação e deslocaria
todo número, fazendo o teste **atrapalhar** exatamente a correção que ele existe
para cobrar.

Provado que ele morde, e não só que passa: um arquivo `bad.py` num repositório
falso disparou a asserção (`{'apps/api/hunter_api/bad.py': [2]}`), e
`test_the_regex_recognises_a_raw_connection_and_leaves_the_rest_alone` fixa os
seis casos do regex. Limite declarado no docstring, no mesmo padrão de
`test_no_funding_route.py`: isto lê texto de fonte; SQL por helper desconhecido
ou conexão recebida de fora não aparece aqui — para esses, quem responde é o
*permission denied* que a §27.1 comprou.

**Não** apontei conftest nenhum para `hunter_runtime` (a sugestão da revisão ao
dono de `apps/**`/`services/**`): `apps/**` e `services/**` estão fora deste
diff, e um conftest que troca de credencial muda o resultado de suíte inteira.
Fica como o próximo passo natural para quem for consertar os quatro sites.

### 5. BAIXA 5 — o docstring de `get_session`

`packages/core/hunter_core/db/session.py`. Dizia "for global tables, migrations,
or workers that bypass RLS" — sob `hunter_runtime` essa função não alcança tabela
nenhuma, não faz bypass de nada e nem lê tabela global. Passa a dizer o que é
(uma sessão **sem** `SET LOCAL ROLE`), o que acontece (permission denied em todo
statement), quem a usa (dois testes de integração, que conectam como dono) e
para onde ir (`role_session` e wrappers; ops é `DATABASE_URL_MIGRATIONS`).

### 6. BAIXA 6 — `bash infra/vps/compose.sh exec -T …` no runbook

Os três `docker compose -p hunter exec` do §3.5 (passos (b) e (e)) viraram
`bash infra/vps/compose.sh exec`, com o motivo escrito ao lado: não há
`docker-compose.yml` na raiz, o stack de produção é a soma dos **dois** arquivos
mais o `--env-file`, e `exec` cai no catch-all do wrapper. Improvisar isso no
meio de uma troca de credencial é o pior momento para descobrir que faltava um
`-f`.

### 7. BAIXA 7 — "derruba o próximo deploy" era um alarme que não existe

Corrigido nos **dois** lugares: o §10.4 acima (riscado no lugar, com a correção
ao lado) e `docs/DATABASE.md` §27.3, que tinha a mesma frase. A verificação da
terceira membership roda **quando a `0015` roda**, e ela não roda de novo num
banco que já está nela: o que ela pega é banco novo do mesmo cluster,
`downgrade`+`upgrade`, e a CI. É guarda de *provisionamento*, não monitor
contínuo — e quem quiser a versão contínua tem de escrever um teste contra o
banco vivo, que não existe.

### 8. BAIXA 8 — PG16+ é requisito, e agora está escrito

`docs/DATABASE.md` §27.3. `GRANT … WITH INHERIT FALSE, SET TRUE` é sintaxe do
PG16; num cluster PG15 a `0015` morre com **erro de sintaxe** e o `DO` não o
tolera (só `insufficient_privilege`/`duplicate_object`, de propósito — tolerar
erro de sintaxe seria seguir sem a membership). Não é regressão de
compatibilidade (o topo do documento declara PG16, os dois composes fixam
`postgres:16-alpine`), mas o sintoma — `syntax error at or near "INHERIT"` no
meio do `migrate` — não sugere sozinho "o servidor é velho demais".

## Arquivos (T3.15g)

| Arquivo | O que |
|---|---|
| `packages/core/tests/unit/test_no_raw_engine_begin.py` | **novo** — o lint da MÉDIA 4 |
| `infra/migrations/ddl/runtime_login_role.py` | `NOTICE` no ramo que derruba o papel + docstring (MÉDIA 2) |
| `packages/core/hunter_core/db/session.py` | docstring de `get_session` (BAIXA 5) |
| `infra/scripts/setup_env.sh` | passo (b) sem senha em `argv` (MÉDIA 3) |
| `docs/DEPLOYMENT.md` | §3.5: (b), (c), (e) e Rollback (MÉDIA 2, 3; BAIXA 6) |
| `docs/DATABASE.md` | §23.5, §27.1 (ALTA 1), §27.3 (BAIXA 7, 8) |
| `docs/SECURITY.md` | §5: linha da tabela e o bloco do runtime (ALTA 1, MÉDIA 3) |
| `.claude/state/notes-T3.15f.md` | §10.4 corrigido (BAIXA 7) e esta seção |

**Não commitado.** **Não tocado:** `.env*`, `services/scanner-worker/**` (os
quatro sites são de outra tarefa; aqui eles viram allowlist com TODO), os dois
composes, a VPS.

## Verificação (T3.15g)

```
$ uv run pytest packages/core/tests/unit/test_no_raw_engine_begin.py packages/core/tests/unit/test_db_session.py -q
......................                                                   [100%]
22 passed in 2.40s

$ uv run pytest packages/core/tests/integration/test_runtime_login_role.py -q
........                                                                 [100%]
8 passed in 28.94s
```

Os oito continuam sendo os da §9.2 — inclusive o **isolamento de RLS**
(`test_org_a_cannot_read_org_bs_rows_through_the_runtime_login`: a org A lê só a
linha dela, pelo login de verdade) e as duas recusas. O `upgrade head` em banco
limpo e o `alembic check` estão dentro da fixture e dos testes abaixo.

**Round trip da `0015`, porque esta tarefa mexeu no `downgrade`** — declarado
como desvio: o brief limitava a **um** arquivo de teste com testcontainer, e o
`downgrade` que eu editei não é exercitado por ele. Rodei os dois testes do
round trip **na mesma invocação** (um container só, não uma segunda subida):

```
$ uv run pytest packages/core/tests/integration/test_runtime_login_role.py \
    "…/test_migrations.py::test_0015_reverses_by_taking_the_membership_away" \
    "…/test_migrations.py::test_0015_is_idempotent_over_a_role_that_already_exists" -q
1 failed, 9 passed in 98.92s
FAILED …/test_runtime_login_role.py::test_the_runtime_login_cannot_become_the_owner
```

**Os dois do round trip passaram** (com `command.check(config)` no fim de cada
um, isto é, `alembic check` sem drift depois do `downgrade`+`upgrade`), o que é
a prova que eu queria: o bloco `DO` do downgrade é compilado inteiro pelo
PL/pgSQL quando roda, então o `RAISE NOTICE` novo é validado mesmo no container
de teste, onde o ramo tomado é o que **mantém** o papel.

A falha é **da minha combinação de arquivos**, não do diff, e é literalmente o
que a §27.4 declara: *membership é cluster-wide*. Os testes de migração descem a
`0015` num banco e revogam `hunter_app`/`hunter_worker` de `hunter_runtime`
**no cluster inteiro** — inclusive no banco `hunter_runtime_login` que o outro
arquivo mantém no `head`, cuja conexão viva o servidor então derruba
(`ConnectionResetError: [WinError 64]`). Sozinho, o arquivo prescrito passa
inteiro (8/8, acima). Registrado como o que é: os dois arquivos **não** devem
ser executados na mesma sessão, e o motivo está documentado desde a T3.15f.

```
$ uv run ruff check <os 3 .py tocados>
All checks passed!

$ uv run ruff format --check <os 3 .py tocados>
3 files already formatted

$ uv run pyright <os 3 .py tocados>
0 errors, 0 warnings, 0 informations

$ bash -n infra/scripts/setup_env.sh
syntax ok

$ uv run python infra/scripts/check_file_size.py
error   356 > 350  infra/scripts/seed_reference.py
scanned 578 files; 1 over budget, 0 grandfathered
```

O único arquivo acima do orçamento é de outra tarefa (`seed_reference.py`, em
voo); nenhum deste diff aparece. `session.py` ficou em 313 linhas.

## Concerns (T3.15g)

1. **O resíduo da ALTA 1 continua aberto, por desenho.** Fechá-lo é a T3.15h e
   ela é maior do que parece: enquanto o `api` resolver identidade como
   `hunter_worker` em toda requisição autenticada, dois logins não separam nada.
   Está escrito na §27.1 com os três call sites nomeados.
2. **Os quatro sites do scanner continuam crus.** Esta tarefa não os conserta
   (outra tarefa é dona de `services/**`); ela impede o **quinto** e põe um TODO
   com nome no allowlist. O passo (d) do runbook continua bloqueado por eles.
3. **O lint da MÉDIA 4 lê texto de fonte**, não comportamento. A sugestão da
   revisão — apontar um conftest de integração para `hunter_runtime` — continua
   aberta e é de quem é dono de `apps/**`/`services/**`.
4. **O `NOTICE` da MÉDIA 2 não é o controle**, e a doc diz isso: um `NOTICE` no
   meio de um log de deploy é fácil de perder. O controle é o parágrafo do
   Rollback no §3.5; o `NOTICE` é a segunda chance.
