# T3.77 — `breadth_5m`: a amplitude do universo vira série persistida e terceira regra do envelope

Horários em **Brasília (UTC−3)**, UTC ao lado. Executado em 2026-09-10, 09:00–13:20 BRT
(12:00–16:20Z). **Nada foi commitado. Nada foi escrito na VPS** — as duas consultas contra
`hunter-postgres-1` rodaram dentro de `begin transaction isolation level repeatable read read only`.

---

## 1. A decisão do item 1 do brief: opção (a), com migração

O brief deixava escolher entre (a) um job do `scanner-worker` gravando `market_breadth` e (b)
cálculo sob demanda dentro do portão, com cache por barra. **Escolhi (a) e escrevi a migração**
(`0019_market_breadth`), pelo motivo que não é o custo:

- (b) faria o **replay** dobrar a tabela `candles` de **hoje** para produzir um número que a decisão
  viva tirou das velas **daquele** minuto. As duas populações que o Shadow Lab existe para comparar
  deixariam de ser comparáveis, e nenhum teste conseguiria provar o contrário — o valor não estaria
  gravado em lugar nenhum;
- (a) transforma "o replay leu o que a faixa viva leu" em propriedade do **esquema**: a linha é
  imutável, ancorada em `end_time`, e o portão a lê por igualdade exata.

O custo de (a) é uma migração e um produtor por minuto. Está escrito e testado.

**Contagem declarada para a decisão de particionar:** 1 linha por minuto por exchange =
`60 × 24 × 365 = 525 600` linhas/ano (binance sozinha, 53 % do limiar de 1 M/ano do brief);
com bybit viva seriam **1 051 200** (105 %). **Não particionei**, e `ix_market_breadth_lookup` já
está chaveado de modo que um `RANGE (end_time)` futuro não muda uma única consulta.

**Dívida declarada:** `docs/DATABASE.md` **§31** descrevendo `market_breadth` **não foi escrita** —
o brief não pediu e o capítulo é do database-architect. Os dois módulos da migração dizem isso por
extenso em vez de apontar para uma seção inexistente.

---

## 2. O que a série mede (e o que ela recusa)

`breadth_5m` (`hunter_indicators/breadth/series.py`, `breadth_v1`):

- por mercado: `close(T) < close(T−5min)`, **estrito** (empate não é queda);
- as velas admitidas são as **seis** com `open_time` em `[T−6min, T−1min]` — nenhuma com
  `open_time + 1 min > T`. Um mercado sem as seis **não é contado**;
- valor = `caindo / cobertos`; cobertura = `cobertos / universo_monitorado`;
- cobertura < **80 %** → `value = NULL`, `reason = insufficient_coverage`, e o portão responde
  `breadth_unavailable`. Cobertura **recusa**, nunca inclina para baixo.

Universo = perpétuas `is_monitored` + `status='active'` da exchange (o mesmo conjunto de
`registry.load_universe`). Spot fora, de propósito.

---

## 3. A regra `breadth` no envelope

`{"breadth": {"window_m": 5, "min": "0.10", "max": "0.60"}}`, meia-aberta no `max`.

- **Âncora exata:** a linha lida é a de `end_time = source_bar_close`. Sem tolerância, sem "a mais
  recente antes". Produtor atrasado → `breadth_unavailable` (falha fechada), e não há janela de
  obsolescência para calibrar (ao contrário do `MAX_STALENESS` do portão de regime);
- **motivo:** `breadth_gate:0.97` (duas casas — o histograma de `ineligible` agrupa por essa
  string; quatro casas dariam um balde por barra) e `breadth_unavailable`. O valor exato de quatro
  casas e o id da linha vão na proveniência do envelope;
- **limites em string**, não número: `variant.canonical_policy` emite todo número como string
  decimal normalizada, e foi isso que quase matou a regra de horas da T3.59
  (`variant.stored_policy`). Strings atravessam as duas serializações byte a byte;
- **ordem de avaliação: hora → regime → amplitude.** A amplitude por último **de propósito**: uma
  versão que só declare as duas regras antigas reporta byte a byte o motivo que reportava antes da
  T3.77, então nenhum histograma de `ineligible` já medido muda de forma;
- `derive_variant.py --policy breadth=0.10-0.60` funciona por acréscimo ao envelope; largar a regra
  do pai em silêncio continua recusado (é `resolve_policy`, que não precisou mudar).

---

## 4. A medição do item 3 — **e ela muda o experimento**

Somente leitura na VPS, 2026-09-10 ~12:40Z:

```
select count(*) from markets m join exchanges e on e.id=m.exchange_id
 where e.code='binance' and m.is_monitored and m.status='active' and m.market_type='perpetual';
--> 200
```

Cobertura de velas de 1 min por dia, últimos 90 dias, contra o universo de 200:

| medida | valor |
|---|---|
| dias na janela | 91 (2026-06-12 a 2026-09-10) |
| dias com ≥ 80 % do universo tendo ≥ 1 200 velas/dia | **4** |
| dias abaixo do piso | **87** |

Recorte por data (coluna "densos" = mercados com ≥ 1 200 das 1 440 velas do dia):

| dia | mercados | densos | cobertura |
|---|---|---|---|
| 12/06 a 28/08 | 16 | 16 | 8,0 % |
| 29/08 | 150 | 16 | 8,0 % |
| 30/08 | 152 | 151 | 75,5 % |
| 02/09–03/09 | 154 | 154 | 77,0 % |
| **05/09** | 163 | 162 | **81,0 %** |
| 06/09 | 171 | 158 | 79,0 % |
| **07/09** | 174 | 162 | **81,0 %** |
| **08/09** | 184 | 170 | **85,0 %** |
| **09/09** | 200 | 186 | **93,0 %** |

**Conclusão a registrar, não a esconder:** um backfill de 90 dias produziria **87 dias de
`insufficient_coverage`** (≈125 mil linhas dizendo "não deu para olhar") e **4 dias utilizáveis**.
Os 16 mercados que a T3.7c backfillou são 8 % do universo — e amplitude é uma medida
*universo-inteiro*, então backfillar "os 16" não produz breadth, produz um número diferente com o
mesmo nome. **Portanto a EXP-0027 é prospectiva**: o primeiro entregável dela é subir o produtor e
esperar, não rodar o backfill.

O CLI existe (`infra/scripts/backfill_breadth.py`), é **relatório-primeiro e dry-run por padrão**
(imprime exatamente a tabela acima antes de qualquer escrita), grava uma linha de `audit_logs` de
escopo de sistema com `--apply --reason …`, e **não foi rodado na VPS**.

---

## 5. Comandos e saídas (locais, foreground, `timeout 290`)

```
$ .venv/Scripts/python.exe -m pytest packages/indicators/tests/unit/test_breadth_series.py -q
13 passed in 1.70s

$ .venv/Scripts/python.exe -m pytest services/strategy-worker/tests/test_breadth_gate_policy.py -q
40 passed in 1.76s

$ .venv/Scripts/python.exe -m pytest services/strategy-worker/tests/test_breadth_gate.py -q -p no:randomly
8 passed in 55.21s          # testcontainers, um arquivo por vez

$ .venv/Scripts/python.exe -m pytest services/strategy-worker/tests -q -m "not integration"
459 passed, 234 deselected in 12.15s

$ .venv/Scripts/python.exe -m pytest packages/indicators/tests -q -m "not integration"
1043 passed in 41.85s

$ .venv/Scripts/python.exe -m pytest services/scanner-worker/tests -q -m "not integration"
115 passed, 49 deselected, 1 xfailed in 82.92s

$ .venv/Scripts/python.exe -m pytest services/strategy-worker/tests/test_hours_gate.py -q -p no:randomly
10 passed in 65.94s          # regressão T3.59

$ .venv/Scripts/python.exe -m pytest services/strategy-worker/tests/test_regime_gate.py -q -p no:randomly
9 passed in 66.21s           # regressão T3.52

$ .venv/Scripts/python.exe -m pytest packages/core/tests/integration/test_schema_privileges.py -q -p no:randomly
43 passed in 147.39s

$ .venv/Scripts/python.exe -m pytest packages/core/tests/integration/test_db_integration.py -q -p no:randomly
6 passed in 11.21s

# test_migrations.py em três levas (o arquivo inteiro passa de 290 s)
60 passed in 185.67s   |   56 passed in 111.88s   |   5 passed in 26.22s      # 121 no total

$ .venv/Scripts/python.exe -m ruff check <21 arquivos>        -> All checks passed!
$ .venv/Scripts/python.exe -m ruff format --check <16>        -> 16 files already formatted
$ .venv/Scripts/python.exe -m pyright <20 arquivos>           -> 0 errors, 0 warnings
$ .venv/Scripts/python.exe infra/scripts/check_file_size.py --max 350
scanned 612 files; 2 over budget, 0 grandfathered
  error 381 > 350 services/strategy-worker/hunter_strategy_worker/funding.py
  error 357 > 350 packages/core/hunter_core/settings.py
```

**Os dois arquivos acima do orçamento não são meus** — a árvore é compartilhada e outra tarefa está
mexendo em `funding.py` e `settings.py` neste momento. `services/scanner-worker/.../main.py` ficou
em **exatamente 350** depois do meu acréscimo (era 338).

---

## 6. Três testes que outra tarefa quebrou por eu ter movido a cabeça das migrações

`HEAD_REVISION` passou a ser `0019_market_breadth`, e três testes usavam `"-1"` para dizer "volte
para 0017/0018". `"-1"` significa "um passo atrás da cabeça", e isso deixou de ser o que eles
queriam provar no instante em que a `0019` entrou. Passaram a nomear a revisão:

- `test_0018_reverses_on_a_database_whose_windows_hold_one_slice_each` → `downgrade(ELIGIBILITY_POLICY_REVISION)`;
- `test_0018_derives_a_stored_receipt_instead_of_stamping_a_sentinel` → idem;
- `test_0018_refuses_to_downgrade_while_a_window_holds_two_market_slices` → desce até
  `REPLAY_SLICE_REVISION` primeiro e só então tenta o passo que a guarda da `0018` tem de recusar.

E `test_schema_privileges.py::test_the_grant_lists_cover_every_table_exactly_once` ganhou
`_breadth_tables("BREADTH_APP_READ_ONLY_TABLES")` — a tabela nova tem de estar numa classe de
grant, e esse teste é justamente a trava que pega quem esquece.
`test_health.py::test_every_status_detail_the_scanner_registers_is_removed_when_it_stops` ganhou
`"breadth"` porque o produtor virou detalhe de status (nunca readiness check).

---

## 7. O que ficou de fora, por escolha declarada

1. **`docs/DATABASE.md` §31** — dívida, nomeada acima.
2. **Métricas Prometheus do produtor.** `beta`/`regime_hourly` têm `Counter`/`Gauge` próprios; o
   `breadth` publica hoje o log estruturado `scanner_breadth_pass` e o detalhe de status
   `breadth` no `hb:scanner:*`. Acrescentar duas métricas é trivial e não cabia sem tocar
   `metrics.py`, que outra tarefa está usando.
3. **Nenhum backfill rodado, nenhuma variante derivada, nenhuma ativação.** A EXP-0027 está
   pré-registrada em `.claude/state/exp-drafts/EXP-0027-amplitude.md` e o passo 1 dela é o deploy.
4. **Um único `window_m` (5).** `SUPPORTED_WINDOWS` recusa qualquer outro no parser: uma política
   pedindo 15 min não recebe a série de 5 min com outro rótulo.

---

## 8. `git status --porcelain` — apenas os meus arquivos

```
 M docs/ACTIVATION.md
 M docs/PIPELINE.md
 M packages/core/hunter_core/db/models/__init__.py
 M packages/core/tests/integration/test_migrations.py
 M packages/core/tests/integration/test_schema_privileges.py
 M services/scanner-worker/hunter_scanner_worker/main.py
 M services/scanner-worker/tests/test_health.py
 M services/strategy-worker/hunter_strategy_worker/context.py
 M services/strategy-worker/hunter_strategy_worker/gate_policy.py
 M services/strategy-worker/hunter_strategy_worker/record.py
 M services/strategy-worker/hunter_strategy_worker/variant.py
?? .claude/state/brief-T3.77-amplitude-como-estado.md
?? .claude/state/exp-drafts/EXP-0027-amplitude.md
?? .claude/state/notes-T3.77.md
?? infra/migrations/ddl/breadth.py
?? infra/migrations/versions/0019_market_breadth.py
?? infra/migrations/versions/0019_market_breadth.py
?? infra/scripts/backfill_breadth.py
?? packages/core/hunter_core/db/models/breadth.py
?? packages/indicators/hunter_indicators/breadth/__init__.py
?? packages/indicators/hunter_indicators/breadth/series.py
?? packages/indicators/tests/unit/test_breadth_series.py
?? services/scanner-worker/hunter_scanner_worker/breadth.py
?? services/scanner-worker/hunter_scanner_worker/breadth_job.py
?? services/scanner-worker/hunter_scanner_worker/breadth_repo.py
?? services/strategy-worker/hunter_strategy_worker/breadth_gate.py
?? services/strategy-worker/tests/test_breadth_gate.py
?? services/strategy-worker/tests/test_breadth_gate_policy.py
```

**Não são meus** (apareceram no `git status` da árvore compartilhada e eu não os toquei):
`.claude/launch.json`, `docs/DESIGN.md`, `.claude/state/notes-T3.74c.md`, `.claude/state/tmp/*`,
`services/strategy-worker/hunter_strategy_worker/main.py`,
`infra/scripts/tests/test_seed_dry_run.py`,
`packages/core/tests/integration/test_schema_seed_and_partitions.py`, e a árvore de PNGs em
`.claude/state/design/`.

---

## T3.77b — fechando o achado HIGH: o produtor não tinha teste próprio

Executado em 2026-09-10, ~13:00–13:22 BRT (16:00–16:22Z). Um arquivo novo,
`services/scanner-worker/tests/test_breadth_job.py`, testcontainer único (Postgres + Redis),
rodado em primeiro plano com `timeout 290`. Nada commitado, nenhum arquivo de produção
editado.

**O achado:** `breadth.py`/`breadth_job.py`/`breadth_repo.py` (`minutes_due`, `_fold_chunk`,
`write_readings`, `window_closes`, `run_breadth_once`, `claim_minute`, `BACKFILL_MINUTES`) não
tinham teste algum contra banco real — `test_breadth_gate.py` insere `market_breadth` à mão e
prova só o portão, nunca o produtor. Fechado.

**O que o arquivo novo prova, com números à mão (nunca tirados de `compute_breadth` em tempo de
teste):**

1. `TestAFracaoExata` — universo de 10, 8 cobertos (6 caem, 2 sobem), 2 excluídos por motivos
   diferentes (`HOLED` sem uma vela, `UNFINAL` com a sexta vela não final) e que cairiam se
   entrassem — prova que a exclusão muda o numerador, não só o denominador. `value ==
   Decimal("0.7500")` (`str` = `"0.750000"`, numeric(9,6)), `coverage == Decimal("0.8000")` —
   exatamente o piso de `test_breadth_series.py::test_exatamente_no_piso_a_leitura_vale`.
2. `TestCoberturaInsuficiente` — 5 de 10 (50 %): linha gravada com `usable=false`,
   `reason='insufficient_coverage'`, `value=NULL` — o contrato exato que o portão lê e que
   `test_breadth_gate.py` só tinha simulado à mão.
3. `TestIdempotencia` — segunda passagem do mesmo minuto: `due=0`, `written=0`, a linha
   recuperada depois é `dict(row._mapping)`-igual à de antes (nem uma coluna mudou).
4. `TestOLimiteDoMinutosDue` (pura, sem banco) — `minutes_due(cut, back=5, known={cut-3min})`
   devolve exatamente `[cut-5,cut-4,cut-2,cut-1,cut]`; `cut-back` está na lista, `cut-back-1` não
   (a fronteira off-by-one), `cut` sozinho aparece sempre que não é conhecido. Mais
   `TestNaoAntecipacaoNoCaminhoDoProdutor` — pelo caminho real do banco (não só a série pura já
   provada em `packages/indicators`): uma vela que abre exatamente no corte e uma mais velha que
   a janela existem no banco e não mudam o resultado.
5. `TestOTrancaDoRedis` — dois `run_breadth_once` concorrentes atrás do mesmo `claim_minute`:
   `sorted(outcomes) == ["ran", "skipped"]`, uma linha só.
6. `TestUniversoSomentePerpetuo` — um mercado spot que cairia forte fica fora do universo e da
   conta (T3.73).

**Prova de que os testes não são carimbo (regra do brief):**
- `TestAFracaoExata`: troquei `Decimal("0.7500")` por `Decimal("0.6667")` (errado de propósito)
  → `AssertionError: assert Decimal('0.750000') == Decimal('0.6667')`. Revertido, roda verde.
- `TestOTrancaDoRedis`: tirei o `if not await claim_minute(...): return "skipped"` do produtor
  (chamando `claim_minute` mas ignorando o resultado) → os dois processos rodam,
  `sorted(outcomes) == ["ran", "ran"]` ≠ `["ran", "skipped"]`, falha. Revertido, roda verde.

**Nenhum bug de produção encontrado** — nenhum `xfail` foi necessário.

### Comandos e saídas

```
$ .venv/Scripts/python.exe -m ruff format services/scanner-worker/tests/test_breadth_job.py
1 file reformatted (import fora de ordem na primeira versão; corrigido com --fix + format)
$ .venv/Scripts/python.exe -m ruff check services/scanner-worker/tests/test_breadth_job.py
All checks passed!
$ .venv/Scripts/python.exe -m ruff format --check services/scanner-worker/tests/test_breadth_job.py
1 file already formatted
$ .venv/Scripts/python.exe -m pyright services/scanner-worker/tests/test_breadth_job.py
0 errors, 0 warnings, 0 informations

$ timeout 290 .venv/Scripts/python.exe -m pytest services/scanner-worker/tests/test_breadth_job.py -q -p no:randomly
........
8 passed in 40.76s          # testcontainers, arquivo único, primeiro plano

$ .venv/Scripts/python.exe -m pytest packages/indicators/tests/unit/test_breadth_series.py -q
13 passed in 0.77s
```

### `git status --porcelain` — só o meu arquivo

```
?? services/scanner-worker/tests/test_breadth_job.py
```

Nenhum outro arquivo tocado. `.claude/state/notes-T3.77.md` (este arquivo) recebeu só este
apêndice.

---

## T3.77c — aplicando os próprios APPROVE-WITH-NOTES na `0019` (ainda não commitada)

A `0019` nunca saiu de container de teste local, então os seis itens foram aplicados **no
lugar**, não numa `0020`. Uma revisão que só existe em testcontainer ainda é rascunho; uma
revisão que já rodou em qualquer banco vivo não é, e aí a resposta teria sido outra.

### 1. Dois btrees a menos (`ddl/breadth.py`, modelo em paridade)

`ix_market_breadth_lookup` repetia coluna a coluna o índice que `uq_market_breadth_reading`
já cria e `ix_market_breadth_exchange_id` era prefixo dela: três btrees mantidos num caminho
de escrita de **uma linha por minuto por venue**, onde um responde tudo. Ficou só o índice
da UNIQUE. O modelo perdeu o `Index(...)` e também o `index=True` da FK — a §1 pede "todo FK
indexado" e um composto que *começa* pela coluna da FK **é** esse índice (mesma regra dos
compostos liderados por `organization_id`). `alembic check` sem drift, provado abaixo.

### 2. Nomes de constraint da convenção, no DDL literal

`pk_market_breadth`, `fk_market_breadth_exchange_id_exchanges`, `uq_market_breadth_reading`.
Antes a PK e a FK saíam com o nome cunhado pelo Postgres. O `alembic check` **não** compara
nome de constraint, então nada notaria — até a revisão que particionar esta tabela precisar
de `DROP CONSTRAINT` pelo nome para pôr `end_time` na PK (§15.2) e ser escrita contra um
nome que não existe.

### 3. `--include-unusable` no backfill, e o plano puro num módulo

`--apply` agora dobra **só** os minutos dos dias cuja cobertura densa alcança `MIN_COVERAGE`.
O porquê: uma recusa **é** uma escrita nesta tabela — o minuto vira linha
`reason = 'insufficient_coverage'` e ninguém tem `UPDATE`/`DELETE`, então é **lápide
permanente** em `breadth_v1`, só superável por um `breadth_version` novo. Noventa dias com
onze aproveitáveis seriam ~114 mil lápides compradas para ganhar ~15 mil leituras.
`--include-unusable` dobra tudo mesmo assim, para quem quer a ausência registrada como fato.

O plano é puro e saiu para `infra/scripts/breadth_windows.py` (`days_above_the_floor`,
`fold_windows`) — pelo mesmo motivo que `partition_plan` saiu de `create_partitions.py`
(§1.3): o executor cresceu para 371 linhas com a mudança e o orçamento é 350. Dias mantidos
contíguos viram uma janela só, então onze dias bons espalhados custam onze folds e nunca
noventa. Fronteira declarada no docstring e na §31: os cinco primeiros minutos de um dia
mantido dobram velas do dia anterior, então, se aquele dia foi pulado, esses poucos minutos
ainda podem cair como `insufficient_coverage` — lápides **medidas**, não adivinhadas.
`audit_logs` passou a gravar as janelas dobradas e o `include_unusable`.

### 4. O comentário de prepared statement em `breadth_repo.py`

O docstring de `_CLOSES` dizia que o sub-select "mantém um prepared statement pela vida do
processo". Não mantém: a sessão constrói o engine com `statement_cache_size=0` e
`prepared_statement_cache_size=0`, justamente porque um prepared do servidor vaza entre
transações sob pooler de transação. O argumento verdadeiro — **texto de SQL estável**, um
parse e um plano em vez de um novo a cada listagem/deslistagem — ficou, e a afirmação falsa
saiu. Só esse bloco foi tocado no arquivo.

Junto, o docstring de `_LOOKUP` em `breadth_gate.py` deixou de nomear o índice derrubado
(uma linha; era referência a objeto que não existe mais).

### 5. Comandos e saídas (locais, primeiro plano, `timeout 290`, um arquivo de container por vez)

```
$ timeout 290 uv run pytest packages/core/tests/integration/test_migrations.py -q -p no:randomly \
    -k "0019 or head or new_revision_reverses or no_drift"
........                                                                 [100%]
8 passed, 117 deselected in 38.41s
# repetido depois do ajuste de docstring da versions/0019: 8 passed em 40.36s

$ timeout 290 uv run pytest packages/core/tests/integration/test_schema_privileges.py -q -p no:randomly -k breadth
......                                                                   [100%]
6 passed, 43 deselected in 18.20s

$ timeout 290 uv run pytest infra/scripts/tests/test_backfill_breadth.py -q -p no:randomly
..........                                                               [100%]
10 passed in 0.57s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_breadth_gate.py -q -p no:randomly
........                                                                 [100%]
8 passed in 52.44s

$ timeout 290 uv run pytest packages/core/tests/integration/test_schema_rls.py -q -p no:randomly
.................                                                        [100%]
17 passed in 50.71s

$ uv run ruff check infra/ packages/core/tests/integration/ services/scanner-worker/ services/strategy-worker/
All checks passed!

$ uv run ruff format --check <os arquivos deste diff>
(todos já formatados; os 3 "would be reformatted" em infra/scripts/ são pré-existentes:
 backfill_funding.py, request_backfill.py, tests/test_request_backfill.py)

$ timeout 290 uv run pyright <os arquivos deste diff>
0 errors, 0 warnings, 0 informations

$ .venv/Scripts/python.exe infra/scripts/check_file_size.py
scanned 617 files; 0 over budget, 0 grandfathered
```

`upgrade head` em banco limpo, `alembic check` e `downgrade -1 && upgrade head` da revisão
nova estão dentro da primeira leva: a fixture `upgraded` **é** o `upgrade head` num banco
recém-criado (falhar ali é falhar o módulo), `test_alembic_check_reports_no_drift` é o
`alembic check`, e `test_the_new_revision_reverses_and_re_applies` mais
`test_0019_reverses_on_a_database_that_never_read_the_universe` são o `downgrade -1` seguido
de `upgrade head` — este último conferindo também que os grants voltam. O isolamento RLS
(org A não lê org B) é o `test_schema_rls.py` acima; `market_breadth` é global e sem RLS
(§1.1), então a prova que lhe cabe é a *ausência* de `organization_id` e de política, que é
um dos seis testes de privilégio.

### 6. Testes novos

`test_migrations.py` (`-k 0019`): `test_0019_refuses_a_downgrade_that_would_lose_a_reading`
(uma leitura na mesa → `downgrade -1` levanta com a mensagem do DDL, revisão continua em
head, tabela continua lá), `test_0019_reverses_on_a_database_that_never_read_the_universe`
(round trip com a tabela vazia + os seis grants de volta),
`test_0019_names_its_constraints_the_way_the_model_does` e
`test_0019_carries_one_reading_index_and_answers_the_gates_probe_from_it`.

`test_schema_privileges.py` (`-k breadth`): o worker insere e apanha `permission denied` em
`UPDATE`/`DELETE`; o app só lê; os conjuntos de privilégio são exatamente `{SELECT}` e
`{SELECT, INSERT}`; `hunter_runtime` não alcança a tabela sem `SET ROLE` (`NOINHERIT`);
`market_breadth` é global e sem política.

`infra/scripts/tests/test_backfill_breadth.py`: dez testes puros sobre `breadth_windows`,
incluindo "nenhum minuto de dia abaixo do piso é dobrado" minuto a minuto e "mantendo todos
os dias, as janelas cobrem exatamente o que uma chamada `back = days * 1440` cobria".

### 7. O plano do portão, conferido uma vez

Com `enable_seqscan = off` (tabela vazia no banco de teste; a pergunta é se existe índice
capaz, propriedade do schema e não da cardinalidade do momento):

```
Nested Loop  (cost=0.30..20.96 rows=1 width=79)
  Join Filter: (b.exchange_id = e.id)
  ->  Index Scan using uq_market_breadth_reading on market_breadth b  (cost=0.15..12.78 rows=1 width=95)
        Index Cond: ((breadth_version = 'breadth_v1'::text) AND (window_minutes = '5'::smallint)
                 AND (end_time = '2026-09-09 22:08:00+00'::timestamptz))
  ->  Index Scan using uq_exchanges_code on exchanges e  (cost=0.15..8.17 rows=1 width=16)
        Index Cond: (code = 'binance'::text)
```

A sonda cai no índice da UNIQUE, que é o que a queda dos dois redundantes tinha de
preservar. Honestidade sobre o detalhe: com a tabela vazia o planejador começa por
`market_breadth` e deixa `exchange_id` como *join filter* (três das quatro colunas como
`Index Cond`); com estatísticas reais ele resolve a venue primeiro e as quatro viram
condição de índice. `Seq Scan` em nenhum dos dois casos — por isso a asserção do teste é
sobre o **nome do índice**, não sobre a forma do join. Registrado também na §31.

### 8. `docs/DATABASE.md` §31

As duas linhas de "desvio declarado" e "dívida" saíram (viraram fato consertado) e entraram
quatro: **um índice só**, **FK indexada pelo prefixo**, **nomes de constraint** e **provas**;
a linha "sem reparo" ganhou o par sobre o backfill pular o que o relatório reprovou, com o
`--include-unusable`. Mais o bloco com o plano acima. Nenhum desvio novo ao contrato.

### 9. `git status --porcelain` — apenas os meus arquivos

```
 M docs/DATABASE.md
 M packages/core/tests/integration/test_migrations.py
 M packages/core/tests/integration/test_schema_privileges.py
?? .claude/state/notes-T3.77.md
?? infra/migrations/ddl/breadth.py
?? infra/migrations/versions/0019_market_breadth.py
?? infra/scripts/backfill_breadth.py
?? infra/scripts/breadth_windows.py
?? infra/scripts/tests/test_backfill_breadth.py
?? packages/core/hunter_core/db/models/breadth.py
?? services/scanner-worker/hunter_scanner_worker/breadth_repo.py
?? services/strategy-worker/hunter_strategy_worker/breadth_gate.py
```

`infra/migrations/versions/0019_market_breadth.py` mudou **uma frase de docstring** (dizia
"one CREATE TABLE, two CREATE INDEX and two GRANTs"; não há mais CREATE INDEX). O corpo da
revisão continua `create_breadth_table()` + `grant_breadth_privileges()` e toda a mudança de
forma está no módulo `ddl/`. Nada foi commitado. `breadth_job.py`, `breadth.py` do scanner e
`services/scanner-worker/tests/test_breadth_job.py` não foram tocados.
