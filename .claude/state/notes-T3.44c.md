# Notas T3.44c — `exchange_status` ganha `planned`: uma exchange que ninguém coleta deixa de ser um feed quebrado

Fechamento da T3.44c (database-architect), 2026-09-08, 17:40–20:55 BRT. O trabalho
chegou **já implementado na árvore não commitada** por um agente anterior que foi
interrompido dentro de uma suíte longa; esta sessão **revisou o diff, fechou as duas
pontas que faltavam e verificou tudo**. **Nenhum commit foi feito.** Nenhum
`git stash/checkout --/restore/reset/clean` rodou. `.env*` nunca foi lido nem escrito.
Nenhum container do stack local (`docker-*`) foi parado ou recriado — só `docker ps`.
Todo comando rodou em primeiro plano com `timeout 290`.

A árvore é compartilhada com vários agentes em voo. Arquivos de outras tarefas
(`packages/shared-types/src/generated/api.d.ts`, `apps/web/**` de regime/radar/ws,
`docs/DESIGN.md`, a linha `sweep_reclaim_v1` de `seed_reference.py`, tudo da T3.15f)
**não foram tocados** — mas dois arquivos são **mistos** e isso muda a lista de commit
(§5 e CONCERN 1).

---

## 1. O que a T3.44c faz, em um parágrafo

`exchanges` tem `binance` e `bybit`, a Bybit nunca teve coletor implantado, e
`build_market_status` renderiza **uma linha por entrada de `exchanges`** de propósito
(uma exchange que o worker nunca tocou tem de aparecer, não sumir) — então a redução
"pior de todas" do topbar lia **`2 exchanges · UNAVAILABLE`** com a Binance conectada o
tempo inteiro. O que faltava não era um valor de linha, era um estado que o tipo não
sabia dizer: a **`0016_exchange_status_planned`** acrescenta o rótulo `planned` a
`exchange_status`, `BEFORE 'active'` (`ALTER TYPE ... ADD VALUE`, dentro da transação da
migração, porque o Postgres 12+ só proíbe *usar* o rótulo novo na mesma transação e esta
revisão não usa nenhum); `hunter_core.domain.enums.ExchangeStatus` declara `PLANNED`
primeiro para casar com o `enumsortorder`; o **seed passa a escrever `status` nas duas
metades do upsert** (`seed_reference.EXCHANGES` carrega `(code, name, status,
capabilities)`, Bybit como `planned`) e `exchanges` entra em `--only`/`--dry-run`, que é
o que torna "ganhou/perdeu coletor" uma correção reexecutável; a API ganha
`MarketRepository.list_exchanges_with_status()` e `MarketStatusOut.exchanges_planned:
list[str]` (aditivo, default `[]`), com a exchange `planned` **fora** das linhas, fora do
Redis, fora de `markets_monitored_total` e — a parte que não é cosmética — fora do teste
"todas as leituras falharam", que com a Bybit dentro faria uma queda real do Redis numa
implantação de um coletor só responder `200` em vez de `503`; e o topbar passa a ler
`binance · CONNECTED · N mercados (bybit planejada)`, com uma linha
`bybit planejada · sem coletor` no painel completo em vez de a exchange sumir da tela.
O downgrade reconstrói o tipo (renomeia, recria com os rótulos que a `0001` congelou,
retipa em volta do default, derruba) e **recusa antes** enquanto houver linha `planned`,
porque os dois rótulos que sobrevivem mentem sobre ela.

---

## 2. Revisão do diff herdado — o que já estava certo

Li `docs/DATABASE.md` inteiro (5 027 linhas) antes de tocar em qualquer coisa. O diff
herdado está **de acordo com o contrato**, incluindo as partes que costumam escapar:

| Ponto do contrato | Como o diff o cumpre |
|---|---|
| enum estendido por migração, posição no contrato (§17.1) | `EXCHANGE_PLANNED_ADDED_VALUES = (("exchange_status", "planned", "active"),)`, congelada por revisão em `ddl/enums.py`; `ExchangeStatus.PLANNED` declarado primeiro; `test_every_enum_type_exists_with_the_expected_labels` e `test_each_revision_creates_exactly_the_labels_it_froze` comparam rótulos **e** `enumsortorder` |
| listas congeladas por revisão (§15.6/§16.5/§17.1) | `ddl/exchange_planned.py` lê `INITIAL_ENUMS["exchange_status"]` (dona da `0001`) para reconstruir, e `EXCHANGE_STATUS_COLUMNS_0016` nomeia as colunas em vez de descobri-las |
| downgrade implementado e guardado (§17.7) | guarda conta e **nomeia** as linhas `planned` antes de qualquer DDL; não apaga nada; instrução operacional no `HINT` |
| default retipado corretamente (receita da `0003`, §17.1) | `DROP DEFAULT` → `ALTER COLUMN TYPE ... USING x::text::tipo` → `SET DEFAULT 'active'` |
| pooler (§1.2) | um `ALTER TYPE`; sem prepared statement de sessão, sem `LISTEN/NOTIFY`, sem advisory lock de sessão |
| RLS/grants | `exchanges` é tabela global de referência (§1.1) — sem `organization_id`, sem política; um rótulo não é coluna, nenhuma ACL envolvida. Nada em `APP_*`/`WORKER_*` muda |
| orçamento do nome da revisão (§17.6) | `0016_exchange_status_planned` = 28 caracteres (teto 32) |
| `withdraw_enabled` (§8) | intocado — esta revisão não chega perto de `exchange_connections` |

**Desvios em relação ao brief T3.44c, ambos já declarados na doc** e ambos corretos:
(a) o brief pedia o `ADD VALUE` **fora** de transação "como o Postgres exige" — não
exige (§28.2); (b) o brief dizia que `seed.py --only exchanges` não existia — passou a
existir (§28.5). E o desvio em relação à **§15.1** (que congelou `exchange_status` em
`active|inactive`) está escrito na §28.1, com a linha da §15.1 *anotada* em vez de
reescrita, que é o que "congelado por revisão" significa.

---

## 3. O que esta sessão mudou

### 3.1 `seed_reference.py` de volta ao orçamento (356 → 291), sem mexer em uma linha de dado

O rótulo novo custou linhas a `seed_reference.py` (uma coluna a mais por linha de
`EXCHANGES`, o import de `ExchangeStatus`, o comentário da tupla) e o levou a **356**,
sobre o teto de 350 do `infra/scripts/check_file_size.py`.

O corte é o da §17.8, uma tabela adiante: **`infra/scripts/seed_risk_reference.py`**
passa a ser o conteúdo de **`risk_profiles`** — `RISK_LIMITS`, `REGIME_MULTIPLIERS`,
`RISK_PRESETS`, `PAPER_V1_NAME`, `PAPER_V1_LIMITS` —, uma tabela inteira e nada além
dela. `seed_reference.py` fica com os catálogos (exchanges, estratégias, entitlements,
flags, features) e os vetores de peso.

Três propriedades, cada uma verificada e não suposta:

- **os dois blocos foram movidos byte a byte** (comparação programática entre
  `git show HEAD:infra/scripts/seed_reference.py` e o arquivo novo: `risk block
  identical: True`, `paper block identical: True`);
- **a ordem das linhas do seed é a mesma**, e a linha `sweep_reclaim` (de outra tarefa)
  está intacta: `['momentum', 'breakout', 'volume_anomaly', 'order_flow',
  'mean_reversion', 'derivatives', 'session_orb', 'trendline_breakout',
  'sweep_reclaim', 'narrative', 'ensemble']`;
- **os cinco nomes continuam sendo lidos de `seed_reference`, por reexportação**
  (`from seed_risk_reference import X as X`) — precedente do `execution.py` da §18.10 e
  do `create_partitions.py` da §1.3. Não são só os irmãos (`seed.py`, `seed_dry_run.py`,
  `seed_paper.py`): são **três módulos de teste que carregam `seed_reference.py` por
  caminho** e leem os atributos dele (`test_schema_paper.py::_shipped_paper_limits`,
  `packages/indicators/tests/unit/test_weights_contract.py`,
  `services/scanner-worker/tests/policies.py`). Os três põem `infra/scripts` no
  `sys.path` antes de executar o módulo, então o import irmão resolve — testado pelos
  três caminhos (saída em §4.5).

### 3.2 A guarda do downgrade percorre a mesma tupla congelada que o rebuild

`refuse_rows_using_the_planned_label()` lia `EXCHANGE_STATUS_COLUMNS_0016[0]` enquanto
`restore_exchange_status_without_planned()` **itera** a tupla inteira. Hoje dá no mesmo
(há uma coluna só), mas a §28.3 promete que a lista congelada é o que protege uma
segunda coluna futura, e uma guarda que confere uma coluna enquanto o rebuild retipa
várias falharia *dentro* do rebuild com `invalid input value for enum` — um erro que não
nomeia saída nenhuma. Agora as duas metades leem a mesma tupla. A mensagem passou de
`' || offenders || ' exchanges are still status = ''planned''` para
`' || offenders || ' rows in <tabela> are still status = ''planned''`; o `match` do teste
(`"still status = 'planned'"`) continua valendo sem edição.

### 3.3 `docs/DATABASE.md`

Três acréscimos, nenhum reescrevendo uma linha congelada:

- **§28.7 (nova)** — o terceiro módulo irmão do seed: por que o corte, o que cada metade
  guarda, a reexportação e os três carregadores por caminho, e a prova byte a byte;
- **§17.8** — uma frase anotando que a T3.44c acrescenta um terceiro irmão, apontando
  para a §28.7 (a linha antiga, que diz "dois módulos irmãos", fica como está: descreve
  o que a T2.1 fez);
- **§28.3** — um parágrafo dizendo que a guarda percorre a mesma tupla que o rebuild.

**Nenhum desvio novo em relação ao contrato.** Os desvios desta revisão (§15.1 estendida,
`ADD VALUE` dentro da transação, `--only exchanges` que o brief dizia não existir) já
estavam escritos na doc pelo agente anterior.

---

## 4. Testes, com saída real

### 4.1 Unidade da API — as 5 falhas anteriores sumiram

```
$ uv run pytest apps/api/tests/unit/test_system_workers_status.py -q
....................................                                     [100%]
36 passed in 1.10s
```

(as duas novas são `test_build_market_status_keeps_a_planned_venue_out_of_the_aggregate`
e `test_a_planned_venue_never_counts_toward_the_every_read_failed_test`; o patch alvo
passou a ser `hunter_api.services.market_status.MarketRepository` — patchar o nome
antigo simplesmente deixaria de patchar qualquer coisa, que era a causa das falhas.)

### 4.2 Unidade dos scripts de infra

```
$ uv run pytest infra/scripts/tests -q -m unit
................................                                         [100%]
32 passed, 121 deselected in 20.59s
```

### 4.3 Migrações (testcontainers, um arquivo por invocação)

```
$ uv run pytest packages/core/tests/integration/test_migrations.py \
      -k "0016 or alembic_check or downgrade_base" -q
......                                                                   [100%]
6 passed, 98 deselected in 47.32s
```

Os seis são exatamente a verificação que o contrato exige:

| Teste | O que prova |
|---|---|
| `test_alembic_check_reports_no_drift` | `alembic check` limpo no head — modelos e migrações sem drift |
| `test_downgrade_base_then_upgrade_head` | `downgrade base` + `upgrade head` em banco limpo, a cadeia inteira até a `0016` |
| `test_0016_adds_planned_before_active_and_nowhere_else` | `exchange_status == ['planned', 'active', 'inactive']` |
| `test_0016_lets_a_venue_be_catalogued_without_a_collector` | grava `planned`; o default da coluna continua `'active'::exchange_status` |
| `test_0016_refuses_to_downgrade_while_a_venue_is_planned` | a guarda recusa (`still status = 'planned'`) e **a revisão não commita** |
| `test_0016_reverses_on_a_database_where_nothing_is_planned` | `downgrade -1` + `upgrade head` da revisão nova, conferindo rótulos, default e a linha `active` no meio do caminho, e `alembic check` no fim |

Contrato dos enums, no mesmo arquivo (a `0016` mexe num tipo que a `0001` congelou):

```
$ uv run pytest packages/core/tests/integration/test_migrations.py -q \
      -k "every_enum_type_exists_with_the_expected_labels or \
          each_revision_creates_exactly_the_labels_it_froze or \
          every_enum_type_belongs_to_exactly_one_revision"
...                                                                      [100%]
3 passed, 101 deselected in 48.13s
```

### 4.4 API sobre Postgres e Redis reais + isolamento de RLS

```
$ uv run pytest apps/api/tests/integration/test_system_workers_api.py -q
................                                                         [100%]
16 passed in 123.44s (0:02:03)
```

(é o arquivo que cobre `/api/v1/system/market-status` com `exchanges` e Redis de
verdade; não existe `test_system_status.py`.)

```
$ uv run pytest packages/core/tests/integration/test_schema_rls.py -q \
      -k "each_org_sees_only_its_own_portfolio or without_current_org or \
          with_another_orgs_id or equity_snapshots_are_not_readable or \
          reading_a_partition_directly"
.....                                                                    [100%]
5 passed, 43.78s
```

Org A não lê a linha de B (nem pela partição filha), sem `app.current_org` a política
devolve zero linhas, e o `WITH CHECK` recusa inserir com o id de outra organização —
no head, isto é, com a `0016` aplicada. (A `0016` não cria dado de tenant nem mexe em
política; esta é a prova de que continua assim.)

### 4.5 Reexportação do seed e importabilidade dos irmãos

```
$ uv run python -            # carrega seed_reference.py pelos três caminhos usados em teste
PAPER_V1_LIMITS keys: 24 | PAPER_V1_NAME: Paper v1
RISK_PRESETS: ['Conservative', 'Balanced', 'Aggressive']
RISK_LIMITS keys: 16 | REGIME_MULTIPLIERS: 3
ACTIVE_WEIGHTS_VERSION: v2 | V2 components: 9
EXCHANGES: ('binance', 'Binance', 'active') ('bybit', 'Bybit', 'planned')
STRATEGIES order: ['momentum', 'breakout', 'volume_anomaly', 'order_flow',
 'mean_reversion', 'derivatives', 'session_orb', 'trendline_breakout',
 'sweep_reclaim', 'narrative', 'ensemble']
every seed module imports; re-exports are the same objects
public names lost: []
```

### 4.6 Orçamento de arquivo, lint e tipos

```
$ uv run python infra/scripts/check_file_size.py --max 350 --baseline infra/scripts/file_size_baseline.txt
scanned 579 files; 0 over budget, 0 grandfathered

$ wc -l infra/scripts/seed_reference.py infra/scripts/seed_risk_reference.py
  291 infra/scripts/seed_reference.py
  108 infra/scripts/seed_risk_reference.py

$ uv run ruff format --check <17 arquivos tocados>
17 files already formatted
$ uv run ruff check <17 arquivos tocados>
All checks passed!
$ uv run pyright <14 arquivos tocados fora de infra/migrations>
0 errors, 0 warnings, 0 informations

$ uv run pytest packages/core/tests/unit/test_domain_enums.py -q
.......................                                                  [100%]
23 passed in 0.87s
```

---

## 5. FILES — a lista exata para commitar

**Commitar por pathspec, nunca `git add <diretório>`** (a árvore é compartilhada).

### 5.1 T3.44c puro (modificados)

```
apps/api/hunter_api/repositories/markets.py
apps/api/hunter_api/schemas/system.py
apps/api/hunter_api/services/system_status.py
apps/api/tests/unit/test_system_workers_status.py
infra/migrations/ddl/enums.py
infra/scripts/seed.py
infra/scripts/seed_cli.py
infra/scripts/seed_dry_run.py
infra/scripts/seed_reference.py
infra/scripts/tests/test_seed_dry_run.py
packages/core/hunter_core/domain/enums.py
```

### 5.2 T3.44c puro (novos, `git add` explícito)

```
apps/api/hunter_api/services/market_status.py
infra/migrations/ddl/exchange_planned.py
infra/migrations/versions/0016_exchange_status_planned.py
infra/scripts/seed_risk_reference.py
```

### 5.3 Mistos — leia o CONCERN 1 antes de commitar

```
docs/DATABASE.md                                   # §3, §15.1, §28 (T3.44c) + §22.3, §23.5, §27 (T3.15f)
packages/core/tests/integration/test_migrations.py # bloco 0016 (T3.44c) + bloco 0015 (T3.15f)
apps/web/components/system/live-status.tsx         # cópia "(bybit planejada)" (T3.44c) + realtime-health/Brasília (outra tarefa)
apps/web/tests/live-status.test.tsx                # idem
apps/web/tests/dashboard-page.test.tsx             # 1 linha
packages/shared-types/src/generated/api.d.ts       # `pnpm gen:types` — carrega várias tarefas
```

### 5.4 NÃO commitar como T3.44c

- `docs/DESIGN.md` — os +2 são **DESIGN-6 / T3.24b** (reordenação do `/lab`), não têm
  relação com esta tarefa apesar de aparecerem na lista do despachante.
- Qualquer arquivo de T3.15f, regime/radar, ws ou `sweep_reclaim_v1` — não tocados aqui.

---

## CONCERNS

1. **A `0016` depende da `0015`, e a `0015` ainda não está commitada.**
   `down_revision = "0015_runtime_login_role"`, e `0015` (T3.15f) está na árvore como
   **arquivo não rastreado** (`infra/migrations/versions/0015_runtime_login_role.py`,
   `infra/migrations/ddl/runtime_login_role.py`,
   `packages/core/tests/integration/test_runtime_login_role.py`). Consequências:
   **(a)** commitar a T3.44c sozinha deixa a cadeia de migrações quebrada no `main`;
   **(b)** `docs/DATABASE.md` e `packages/core/tests/integration/test_migrations.py`
   carregam as duas tarefas e **não dá para separá-los por pathspec** — `HEAD_REVISION`
   virou `0016` no mesmo arquivo em que o bloco de testes da `0015` foi escrito. A saída
   honesta é **commitar a T3.15f primeiro (ou as duas no mesmo commit)**; a decisão é do
   orquestrador, não minha, e por isso não commitei.

2. **`apps/web/components/system/live-status.tsx` é misto.** A cópia do ladrilho
   ("(bybit planejada)", `bybit planejada · sem coletor`) é da T3.44c; o mesmo arquivo
   traz `deriveConnectionHealth` (`lib/realtime-health.ts`, não rastreado) e
   `formatBrasiliaLong` de outra tarefa. Não toquei em nenhum arquivo web. Se a outra
   tarefa não for junto, o arquivo não compila (import de módulo não rastreado).

3. **Três testes de integração do seed não foram executados**, por respeito à regra do
   brief (testcontainers só nos dois arquivos nomeados):
   `infra/scripts/tests/test_seed_dry_run.py::TestOnlyExchanges` (3 testes: `--only
   exchanges` como escolha do CLI, o `--dry-run` mostrando
   `exchanges.bybit: status: 'active' -> 'planned'` sem commitar, e a escrita movendo o
   rótulo sem tocar em `strategies`). Eles são o caminho que de fato grava `planned`.
   O que **foi** verificado do lado do seed: importabilidade e identidade dos objetos
   após o split (§4.5), `-m unit` verde, e o rótulo aceito pelo banco real (§4.3).
   Recomendo rodar `uv run pytest infra/scripts/tests/test_seed_dry_run.py -q -k
   OnlyExchanges` na próxima janela com Docker livre.

4. **Duas execuções dos testes de migração falharam com `ConnectionResetError [WinError
   64] O nome da rede especificado não está mais disponível`** (uma vez em todos os 6
   testes no *setup* do fixture, outra vez em um só). Não é lógica: o mesmo teste passa
   isolado (`1 passed in 43.35s`) e a seleção completa passa na execução seguinte
   (`6 passed in 47.32s`, §4.3). É a rede do Docker Desktop nesta máquina sob carga —
   há um testcontainer órfão (`nifty_engelbart`, up 25 min) e o stack local inteiro de
   pé. Registrado porque, se a CI apresentar isso, o sintoma já tem nome.

5. **`markets_monitored_total` mudou de significado** (soma só as exchanges coletadas).
   É deliberado e documentado (§28.6): os mercados de uma exchange planejada podem
   carregar `is_monitored` de uma sincronização de catálogo e ninguém os lê, então
   contá-los faria o cabeçalho discordar da soma das linhas abaixo — que é o número que
   o cliente web calcula sozinho (`totalMonitoredFrom`). Quem consumir esse campo em
   painel/alerta externo verá o total cair no dia em que a Bybit for semeada como
   `planned`.

6. **`--only exchanges` não passa pelo portão de `--yes`**, e isso é correto (o portão é
   da diretiva de risco, §17.8), mas significa que mover uma exchange entre `active` e
   `planned` é uma escrita de um comando só. O portão de execução não assistida (diff
   não vazio + `stdin` sem TTY) continua valendo. Registrado, não corrigido.
