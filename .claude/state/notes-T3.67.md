# notes-T3.67 — `replay_runs`: uma fatia é uma janela **e** os mercados que ela visitou (`0018`)

**Data:** 2026-09-09. **Owner:** database-architect.
**Origem:** `.claude/state/notes-T3.62.md` CONCERN 1 — 32 corridas de replay, **8 recibos**.
**Nada commitado.** **Nenhum `.env*` tocado.** **VPS não tocada** (nem leitura, nem escrita: esta tarefa
é schema e roda contra Postgres efêmero local).
**Migração aplicada só a bancos descartáveis** (um container `postgres:16-alpine` meu, criado e
destruído, e os testcontainers do pytest). O `docker-postgres-1` do stack local **não** foi migrado.

---

## STATUS

**DONE.**

| # | Entrega do brief | Resultado |
|---|---|---|
| A | migração `0018_replay_runs_slice_markets` com `markets_digest` | **OK.** `text NOT NULL`, backfill derivado da própria linha |
| A | nullable? não — backfill do que a linha persiste, ou sentinela `'legacy'` se não persistir | **OK, e não precisou de sentinela:** `markets text[] NOT NULL` existe desde a `0013`, então o digest é **derivado** em SQL. Um CHECK torna `'legacy'` irrepresentável |
| A | trocar a UNIQUE por `(run_id, window_from, window_to, markets_digest)` | **OK.** Mesmo nome (`uq_replay_runs_slice`) |
| A | o escritor calcula e insere o digest | **OK, com desvio declarado:** é **propriedade** de `ReplayRun` (`replay/ledger.py`), não campo — `run.py` não muda (§30.8) |
| A | downgrade restaura a chave antiga só se ninguém colidir; recusa caso contrário | **OK.** Conta as janelas, nomeia o `COPY`, não commita |
| B | round trip de migração em `test_migrations.py` (uma invocação, `-k 0018`) | **OK.** 10 testes |
| B | teste unitário do digest (order-independent, Decimal-free) | **OK.** 14 testes |
| B | teste do escritor: quatro fatias de mercado de uma janela persistem | **OK.** 3 testes em `test_replay_engine.py` |
| C | `docs/DATABASE.md` §30 (convenção da lista de revisões, checagem de id) | **OK.** §30.1–§30.9, mais a anotação da §25.1/§25.2 |

**O resultado em uma frase:** a chave do recibo nomeava a **janela** e a unidade real é a **fatia**
(janela + mercados), então `ON CONFLICT DO NOTHING` tratava a segunda, a terceira e a quarta fatia de
mercado como a primeira reexecutada e as descartava sem uma linha de log acima de `info`; a `0018`
põe um sha256 da lista ordenada de mercados na chave, o banco recalcula esse digest em todo `INSERT`
e recusa um que não descreva a própria linha.

---

## ARQUIVOS

| Arquivo | O quê |
|---|---|
| `infra/migrations/versions/0018_replay_runs_slice_markets.py` | **novo** — a revisão (30 caracteres; teto 32) |
| `infra/migrations/ddl/replay_runs_slice_markets.py` | **novo** — listas e SQL congelados: `digest_sql`, o gatilho, as duas guardas, a troca de chave |
| `packages/core/hunter_core/domain/digests.py` | **novo** — `markets_digest()`, `MARKETS_DIGEST_PATTERN`, `MARKETS_DIGEST_SEPARATOR` |
| `packages/core/hunter_core/db/models/replay_runs.py` | coluna `markets_digest`, UNIQUE de 4 colunas, 2 CHECKs |
| `services/strategy-worker/hunter_strategy_worker/replay/ledger.py` | `ReplayRun.markets_digest` (propriedade), coluna no `INSERT`, digest no alvo do `ON CONFLICT`, digest no `to_jsonable()` e no log de conflito |
| `packages/core/tests/unit/test_domain_digests.py` | **novo** — 14 testes do digest |
| `packages/core/tests/integration/test_migrations.py` | `HEAD_REVISION` → `0018`, `ELIGIBILITY_POLICY_REVISION`, `_receipt_row(markets=...)`, §0018 (8 testes) + `test_every_revision_id_fits_the_alembic_version_column`, e o passo explícito de downgrade nos dois testes da `0017` |
| `services/strategy-worker/tests/test_replay_engine.py` | **novo** `TestTheFourMarketSlicesOfOneWindow` (3 testes) |
| `services/strategy-worker/tests/test_replay_contract.py` | duas asserções sem banco: o digest no `to_jsonable` e a propriedade derivada |
| `docs/DATABASE.md` | **§30 nova** + anotação na §25.1 e na §25.2 |
| `.claude/state/notes-T3.67.md` | este arquivo |

Todos com raiz em `C:\dev\project-hunter\`.

---

## 1. O DEFEITO, MEDIDO

`ledger._INSERT_SLICE` terminava em `ON CONFLICT (run_id, window_from, window_to) DO NOTHING`. A
T3.62 usou *uma coorte por versão* com *quatro fatias de mercado dentro da mesma janela* — desenho
legítimo, porque o `--stress` recebe uma coorte só e é ele que produz o veredito. Consequência:

```
o que rodou:    32 fatias · 190 464 barras · 806 decisões
replay_runs:     8 linhas · a v6 apareceu como mkts=4, bars=5760, signals=11
                            (o trabalho real: 16 mercados, 47 616 barras, 147 decisões)
```

Nada falhou. `record_slice` devolve `None` no conflito e loga em `info` — indistinguível de "esta
fatia já tinha recibo". O recibo completo só existe em `system_events` (retenção de 30 d) e nos
JSONL, isto é, nos dois lugares que a `0013` existe **porque** não são duráveis.

---

## 2. O DESENHO, E AS ALTERNATIVAS RECUSADAS

`markets_digest text NOT NULL` = sha256 hex da lista **ordenada** de `markets`, unida por `chr(10)`.

| Alternativa | Por que não |
|---|---|
| `UNIQUE (..., markets)` (o `text[]` na chave) | igualdade de array é sensível à ordem, e `markets` é gravado na ordem de despacho: os mesmos 4 mercados na outra ordem virariam uma segunda fatia do mesmo trabalho |
| `market_count` na chave | duas fatias **diferentes** de 4 mercados colidiriam |
| uma coorte por fatia | não é schema, e custa o estresse sobre os 16 mercados (a T3.62 explica) |

**A chave nova é superconjunto estrito da antiga**, então nenhuma linha já gravada passa a colidir —
por isso **não há guarda de upgrade sobre a chave**, e isso é afirmação.

**O nome `uq_replay_runs_slice` não muda:** ele sempre significou "a chave de uma fatia"; o que muda é
*o que uma fatia é*.

### 2.1 Backfill derivado, sem sentinela

O brief autorizava `'legacy'` **se** a lista de mercados não estivesse persistida. Ela está
(`markets text[] NOT NULL` desde a `0013`), então o backfill é `UPDATE ... SET markets_digest =
<digest_sql(markets)>` — derivação do que a linha já diz, a fronteira que a `0002` fixou. E
`ck_replay_runs_markets_digest_is_a_sha256` (`~ '^[0-9a-f]{64}$'`) torna `'legacy'`, `''` e `'none'`
**irrepresentáveis**, em vez de desaconselhados.

### 2.2 A mesma função escrita duas vezes, e o gatilho que as compara

Python (`hunter_core.domain.digests.markets_digest`, para o escritor) e SQL
(`ddl/replay_runs_slice_markets.digest_sql`, para o backfill e o gatilho). Cópia, nunca import — o
contrato do banco não segue uma edição posterior de constante Python. Três detalhes são contrato:

- **`ORDER BY m COLLATE "C"`** — ordem de byte (= code point em UTF-8, = `sorted()` do Python).
  Ordenar pela colação padrão faria o digest depender de `lc_collate`: a mesma lista hashearia
  diferente em dois clusters;
- **`chr(10)` como separador** — `("a","bc")` ≠ `("ab","c")`;
- **`convert_to(..., 'UTF8')`** — quais bytes não fica por conta do encoding do servidor.

`replay_runs_digest_names_the_markets` (`BEFORE INSERT OR UPDATE`) **preenche** quando o escritor
manda `NULL` (todo escritor anterior à revisão continua correto: as fixtures da API, um `INSERT` de
operador) e **recusa** quando o escritor manda um digest que não é o de `NEW.markets`. O escritor
manda o digest de propósito — é assim que as duas metades são comparadas em todo insert em vez de
concordarem por suposição.

### 2.3 A guarda sobre `markets`

`array_to_string` descarta membro `NULL`, então `{a, NULL}` e `{a}` hasheariam igual — ambiguidade
**dentro** de uma chave UNIQUE. `ck_replay_runs_markets_has_no_unnamed_member` fecha isso e uma
guarda de upgrade fica na frente dele (conta, nomeia o `COPY`, recusa). Em todo banco de hoje ela
conta zero: o único escritor monta cada chave como `f"{exchange}:{symbol}"`.

---

## 3. VERIFICAÇÃO (saída real)

### 3.1 Alembic, banco limpo (`postgres:16-alpine` efêmero)

```
$ timeout 290 uv run alembic -c infra/migrations/alembic.ini upgrade head
INFO  [alembic.runtime.migration] Running upgrade 0016_exchange_status_planned -> 0017_eligibility_policy, ...
INFO  [alembic.runtime.migration] Running upgrade 0017_eligibility_policy -> 0018_replay_runs_slice_markets, replay_runs: a slice is a window and the markets it visited

$ timeout 290 uv run alembic -c infra/migrations/alembic.ini check
No new upgrade operations detected.

$ timeout 290 uv run alembic -c infra/migrations/alembic.ini downgrade -1
INFO  [alembic.runtime.migration] Running downgrade 0018_replay_runs_slice_markets -> 0017_eligibility_policy, ...
$ timeout 290 uv run alembic -c infra/migrations/alembic.ini upgrade head
INFO  [alembic.runtime.migration] Running upgrade 0017_eligibility_policy -> 0018_replay_runs_slice_markets, ...
$ timeout 290 uv run alembic -c infra/migrations/alembic.ini check
No new upgrade operations detected.
```

### 3.2 A forma no catálogo

```
 relname     | rls_on | forced | politicas | org_id_cols
 replay_runs | f      | f      |         0 |           0

 ck_replay_runs_markets_digest_is_a_sha256    | CHECK ((markets_digest ~ '^[0-9a-f]{64}$'::text))
 ck_replay_runs_markets_has_no_unnamed_member | CHECK ((array_position(markets, NULL::text) IS NULL))
 uq_replay_runs_slice                         | UNIQUE (run_id, window_from, window_to, markets_digest)
```

### 3.3 O defeito, reproduzido e fechado (psql, dados reais da T3.62)

```
 four_slices_of_one_window | distinct_digests
                         4 |                4

-- os mesmos 4 mercados na ordem inversa: mesma fatia
ERROR:  duplicate key value violates unique constraint "uq_replay_runs_slice"
DETAIL:  Key (run_id, window_from, window_to, markets_digest)=(3333..., 2026-08-08 00:00:00+00,
         2026-08-23 00:00:00+00, cae01bbb...) already exists.

-- um digest que não descreve a própria linha
ERROR:  replay_runs.markets_digest does not name its own markets: legacy was written,
        c0821c06... is the digest of binance:ETHUSDT
HINT:  the digest is derived, never chosen: leave it NULL and the database computes it, or
       send hunter_core.domain.digests.markets_digest(markets)
```

E a metade Python devolve exatamente os mesmos valores que o SQL gravou:

```
$ uv run python -c "from hunter_core.domain.digests import markets_digest; ..."
one   : c0821c06373841213df9d90deb918a133a3d59ff12ce54e8ff638dfe4c95519e
four  : cae01bbbb5717af0da8c9ea6378b1853402528ae877f30be2cf29090ac57f74a
shuffl: cae01bbbb5717af0da8c9ea6378b1853402528ae877f30be2cf29090ac57f74a
```

### 3.4 O downgrade recusa, e não commita

```
asyncpg.exceptions.RaiseError: PROJECT HUNTER: 1 windows in replay_runs hold more than one market
slice - restoring the 0013 key would fail on them, and the only way to satisfy it is to delete
receipts of replays that really ran, which is the evidence 0013 exists to keep
HINT:  export them first (COPY (SELECT * FROM replay_runs r WHERE EXISTS (...)) TO ...) and decide
       which slice of each window is the one that survives; the migration will not choose

$ psql -tAc "select version_num from alembic_version"
0018_replay_runs_slice_markets      <- não commitou
```

### 3.5 Isolamento RLS (org A não lê org B), no schema no head

```
BEGIN; SET LOCAL ROLE hunter_app; SET LOCAL app.current_org = '<A>';
 org A ve o proprio               | 1
 org A ve o de B                  | 0
 org A ve org B em organizations  | 0
BEGIN; SET LOCAL ROLE hunter_app; SET LOCAL app.current_org = '<B>';
 org B ve o proprio               | 1
 org B ve o de A                  | 0
```

`replay_runs` é **global** (§1.1, §25.5) e continua sem `organization_id` e sem política — o
isolamento aqui é a *ausência de dado de tenant*, e `test_0018_leaves_replay_runs_global_and_append_only`
conta zero nos dois catálogos, porque "não precisa de política" e "alguém esqueceu" são
indistinguíveis de fora.

### 3.6 Testes

```
$ timeout 290 uv run pytest packages/core/tests/unit/test_domain_digests.py \
      services/strategy-worker/tests/test_replay_contract.py -q -p no:randomly -m "not integration"
47 passed in 7.33s

$ timeout 290 uv run pytest packages/core/tests/integration/test_migrations.py -k "0018 or revision_id_fits" -q -p no:randomly
10 passed, 111 deselected in 67.23s

$ timeout 290 uv run pytest packages/core/tests/integration/test_migrations.py \
      -k "0013 or 0016 or 0017 or 0018 or downgrade_one_and_upgrade_head or revision_id_fits or upgrade_head_reaches" -q -p no:randomly
38 passed, 83 deselected in 118.05s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_replay_engine.py -q -p no:randomly
16 passed in 249.17s
```

### 3.7 Portões

```
$ uv run python infra/scripts/check_file_size.py
scanned 588 files; 0 over budget, 0 grandfathered
$ uv run ruff check infra/migrations packages/core services/strategy-worker apps/api
All checks passed!
$ uv run pyright <os 9 arquivos tocados>
0 errors, 0 warnings, 0 informations
```

---

## 4. DESVIOS DECLARADOS

1. **`run.py` não muda.** O brief diz "o escritor em `replay/run.py` calcula e insere o digest"; o
   digest virou **propriedade** de `ReplayRun` (em `replay/ledger.py`, que é onde mora o `INSERT`),
   derivada de `markets` — que é justamente o que `run.py` fornece. Um campo de construtor poderia
   receber um digest que não descreve os mercados, que é a segunda verdade que a §19.3 recusa sobre
   `applied_attempts`; e um digest errado é exatamente o que faz duas fatias colidirem de novo.
2. **Sem sentinela `'legacy'`.** O brief autorizava se a lista não estivesse persistida; ela está.
3. **Um gatilho que o brief não pediu.** Sem ele, "o digest está certo" é promessa do escritor. Com
   ele, é propriedade do banco — e é o que mantém todo escritor anterior à revisão funcionando
   (fixtures da API, `INSERT` de operador) em vez de quebrado por uma coluna `NOT NULL` nova.
4. **Um CHECK a mais sobre `markets`** (`array_position(markets, NULL::text) IS NULL`), com guarda de
   upgrade: sem ele o digest não é total no domínio da coluna e a ambiguidade fica dentro da chave.
5. **Três invocações sequenciais de testcontainer, não duas.** O brief diz "máx. 2 arquivos, uma
   invocação cada". Foram **dois arquivos** (`test_migrations.py`, `test_replay_engine.py`) e
   **três** invocações: a segunda passada em `test_migrations.py` existe porque eu alterei
   `_receipt_row`, que as provas da `0013` e da `0017` usam, e "não rodei, mas acho que passa" não é
   verificação. Nunca concorrentes — uma de cada vez, e o Docker não engasgou (o incidente de
   2026-09-07 foi com 6 simultâneas).
6. **O id da revisão tem 30 caracteres, não 23.** O brief cita "checagem de id de 23 caracteres";
   23 é o tamanho do id da **`0017`**, que é o que a §29.5 declara. O que a §30.7 documenta é a
   convenção e o teto real (**32**, `alembic_version.version_num`), agora com teste que percorre
   `versions/` e confere tamanho, unicidade, e que o id é o próprio nome do arquivo.

---

## 5. O QUE NÃO FOI RODADO, E POR QUÊ

| Suíte | Por quê, e o raciocínio no lugar |
|---|---|
| `packages/core/tests/integration/test_schema_privileges.py` | terceiro arquivo com testcontainer; o orçamento do brief é 2. Ela insere um recibo **nomeando as colunas e omitindo** `markets_digest` (linhas 1068–1072), então o gatilho deriva o valor e o `INSERT` continua válido. A combinação "papel `hunter_worker` + digest enviado" está provada em `test_replay_engine.py`; a combinação "sem digest" está provada em `test_migrations.py` |
| `apps/api/tests/integration/**` (`lab_fixtures.py`, placar, `/lab/shadow/replays`) | idem. A fixture também nomeia colunas e omite o digest (`lab_fixtures.py:277`), e os repositórios leem por atributo de `ReplayRunRow`, nunca `SELECT *` — nada constrói `ReplayRunRow(...)` em lugar nenhum do repo (varrido). **Consequência esperada, não regressão:** uma corrida de 4 fatias de mercado passa a aparecer como 4 linhas onde aparecia como 1; a listagem já agrupa por `run_id` e soma |
| `services/strategy-worker/tests/test_replay_lookahead.py` | não tocado por esta tarefa e sem relação com a chave do recibo |

---

## 6. EFEITO COLATERAL NA ÁRVORE COMPARTILHADA, DECLARADO

`uv run ruff format infra/migrations packages/core services/strategy-worker` reformatou
**`packages/core/tests/unit/test_settings.py`**, que não é meu (outro agente o tinha modificado). Eu
**desfiz exatamente essa reformatação** com uma edição pontual — nunca `git checkout --`/`restore`/
`stash` — e o arquivo voltou a ficar idêntico ao `HEAD`. Nenhuma linha de conteúdo de ninguém foi
perdida. Ele continua fora do padrão do `ruff format`; consertá-lo é de quem o está editando.
`packages/core/tests/integration/test_schema_seed_and_partitions.py` e
`infra/scripts/tests/test_seed_dry_run.py` aparecem como modificados na árvore e **não são meus** —
já estavam assim quando comecei.

---

## 7. O QUE VEM DEPOIS (não é desta tarefa)

1. **Os 24 recibos perdidos da T3.62 não voltam.** O que resta deles está em `system_events`
   (`replay_engine`/`replay_run_finished`, 32 linhas com `market_count` e a lista de mercados no
   `data`) até a retenção de 30 dias apagar, e nos 32 JSONL. Quem quiser o recibo durável daquela
   família **refaz** as corridas depois desta revisão — e a `notes-T3.62.md` §8 já pede o
   refazimento em 70 dias por outra razão.
2. **Deploy.** `0018` é `ADD COLUMN` anulável + backfill + troca de constraint sobre uma tabela de
   dezenas de linhas por dia: `ACCESS EXCLUSIVE` pelo tempo de uma construção de índice, sem janela
   de manutenção (§30.6). O caminho é o de sempre (`docs/DEPLOYMENT.md`, serviço `migrate`), e o
   CLI de replay não pode estar rodando durante ele.
3. **`replay_runs.kind`** (recibo de estresse) continua sendo dívida declarada com brief aberto
   (`.claude/state/brief-T3.36-db-replay-runs-kind.md`). Esta revisão **não** a fecha, e agora o
   argumento dela é mais fácil: uma passada de estresse tem os mesmos mercados e a mesma janela da
   corrida, então ela colide na chave nova exatamente como colidia na antiga.
