# Notas T3.37 — a tabela de sinais do Lab mostra os totais reais e pagina o conjunto inteiro

## T3.37a — API (backend-specialist)

**Data:** 2026-09-08. **Base:** `main` em `c8c9dc6` (T3.18c já commitada). **Não commitado.**

### STATUS

`DONE_WITH_CONCERNS`. O contrato está implementado, testado (unitário + integração com
testcontainers) e o OpenAPI/TS foi regenerado. A concern real: nenhum índice novo foi criado (a
regra do brief proíbe editar `infra/migrations/**`); o `EXPLAIN` mostra que a consulta é rápida
**quando `strategy_version_id` é informado** (o índice composto existente resolve) mas cai para
`Seq Scan` + sort em memória quando não é — ver §"EXPLAIN dos totais" e o pedido para
`database-architect` ao final.

### Contrato entregue

`GET /api/v1/lab/shadow/signals` — mesmos filtros de antes (`strategy_version_id`, `market`,
`tracking_state`, `result`, `cohort`) **mais**:

- `state=closed|open|pending|all` (default `all`) — segmento server-side. Mapeamento (mirror exato
  de `apps/web/components/lab/lab-signal-segments.ts`'s `matchesSegment`, implementado em
  `hunter_api/repositories/lab_common.py::tracking_states_for_lab_state`):

  | `state` | `signal_outcomes.tracking_state` |
  |---|---|
  | `closed` | `terminal` |
  | `open` | `active` |
  | `pending` | `pending_entry` ∪ `no_entry` ∪ `censored` |
  | `all` | (sem filtro) |

- `page_size` — `50 \| 100 \| 200 \| 500`, default `200`. Substitui o antigo `limit` (livre,
  `ge=1, le=200`) — decisão de simplicidade: um único parâmetro de paginação, não dois sobrepostos.
  `Literal[int, ...]` do Pydantic não faz coerção "lenient" de string de query (`"100"` não vira
  `100` automaticamente, ao contrário de um `int` puro) — resolvido com
  `Annotated[Literal[50,100,200,500], BeforeValidator(...)]` em `routers/lab.py`.
- `cursor` — keyset já existente sobre `(decision_at DESC, id DESC)`, sem mudança de formato.
- Resposta ganha:
  - `totals: {closed, open, pending, all}` — contagem sobre **todo o conjunto filtrado**
    (`cohort`/`strategy_version_id`/`market`/`tracking_state`/`result` aplicados, `state` **não**
    aplicado) — uma única query agregada com 4 `COUNT(*) FILTER (...)`.
  - `page: {from, to}` — posição 1-based **dentro da ordenação do `state` selecionado** (ex.:
    `state=closed` com 3 linhas fechadas → `{from:1, to:3}` mesmo se `totals.all` for 13). `0`/`0`
    quando a página é vazia. Calculado com uma única query de contagem sobre o mesmo predicado do
    seek do cursor (sem `OFFSET`): "quantas linhas, dentro do filtro+segmento, vêm antes ou empatam
    com o cursor" = posição do cursor; `from = posição + 1`.

**Sobre "keeps its filters (cohort, version, window)" do brief:** o endpoint de sinais nunca teve
um parâmetro `window` (isso é do `/summary`); mantive os filtros que de fato existem
(`strategy_version_id`, `market`, `tracking_state`, `result`, `cohort`) e não inventei um `window`
para `/signals` — não fazia sentido de produto (a listagem não agrega por janela) e nenhum outro
lugar do código pedia isso. Sinalizado aqui em vez de perguntar e travar, porque a leitura mais
provável é "os filtros que já existem continuam existindo", que é o que ficou.

### FILES

**Modificados:**
- `apps/api/hunter_api/repositories/lab_common.py` — `LabSignalState`, `PENDING_TRACKING_STATES`,
  `tracking_states_for_lab_state()`; docstring do módulo atualizada com o achado do `EXPLAIN`.
- `apps/api/hunter_api/repositories/lab_signals.py` — `SignalsPageResult` (dataclass); `list_page`
  reescrito (parâmetros `state`, `page_size` no lugar de `limit`; retorna totais + posição, não só
  `(items, next_cursor)`); métodos privados `_base_filters`, `_count_totals`, `_rank_of_cursor`.
- `apps/api/hunter_api/schemas/lab_signals.py` — `SegmentTotalsOut`, `SignalsPagePositionOut`
  (alias `from`/`to`), `SignalsPage` deixou de ser `CursorPage[SignalListItemOut]` e virou um
  modelo próprio com `totals`/`page`.
- `apps/api/hunter_api/services/lab_signals.py` — `build_signals_page` recebe `SignalsPageResult`
  inteiro (não mais `rows, next_cursor` soltos) e monta `SignalsPage` com os três blocos.
- `apps/api/hunter_api/routers/lab.py` — `list_signals` ganha `state`/`page_size` (substitui
  `limit`); `_PageSize` (`Annotated[Literal[50,100,200,500], BeforeValidator(...)]`).
- `apps/api/tests/integration/test_lab_api.py` — `test_signals_empty_list_is_200_not_404` (novo
  formato de resposta); `test_signals_filters_by_tracking_state_and_result_and_pages` e
  `test_signals_cursor_tie_breaks_by_id_when_decision_at_matches_across_markets` reescritos para
  `page_size` (51 linhas em vez de 3, porque o menor `page_size` válido é 50).
- `packages/shared-types/src/generated/api.d.ts` — `pnpm gen:types`.

**Criados:**
- `apps/api/tests/unit/test_lab_signals_state.py` — mapeamento `state` → `tracking_state`, um
  fixture por estado + invariante "todo `ShadowTrackingState` cai em exatamente um segmento".
- `apps/api/tests/integration/test_lab_signals_pagination_api.py` — totais sobre o conjunto
  inteiro (não a página), totais estáveis entre páginas, filtro `state` (um fixture por estado,
  parametrizado), `page.from/to` escopado ao `state` selecionado, estabilidade do cursor sob
  inserção concorrente de uma linha mais nova.
- `apps/api/tests/integration/test_lab_signals_explain.py` — `EXPLAIN (ANALYZE, BUFFERS)` das
  três formas de consulta (totais, primeira página, posição de um cursor no meio do conjunto)
  sobre uma população de 6.000 linhas, com e sem filtro de `strategy_version_id`. Diagnóstico, não
  regressão: falha só se a seed quebrar.

**Não tocados (lista de proibição do brief):** `.env*`, `apps/web/**`, `services/**`,
`obsidian/**`, `infra/migrations/**`, `lab_replication*.py`, `lab_scoreboard*.py`, `lab_curve.py`.

### TESTS (saída real)

Unitário (mapeamento de estado):
```
$ uv run pytest tests/unit/test_lab_signals_state.py -q
.....                                                                    [100%]
5 passed in 0.59s
```

Suíte base (`test_lab_api.py`, testcontainers, um arquivo por invocação):
```
$ uv run pytest tests/integration/test_lab_api.py -q
.....................                                                    [100%]
21 passed in 71.23s (0:01:11)
```

Suíte nova T3.37a (`test_lab_signals_pagination_api.py`):
```
$ uv run pytest tests/integration/test_lab_signals_pagination_api.py -q
........                                                                 [100%]
8 passed in 45.33s
```
Os 8 casos: totais refletem o conjunto inteiro (não a página carregada); totais idênticos entre
página 1 e página 2 da mesma consulta; `state` filtra corretamente para os 4 valores (parametrizado,
um fixture por estado, com uma população de 2 `closed` + 2 `open` + 1 `pending_entry` + 1
`no_entry` + 1 `censored`); `page.from/to` escopado ao `state` selecionado (não ao total); cursor
estável quando uma linha mais nova é inserida entre a página 1 e a página 2 (não duplica, não pula,
não deixa a linha nova vazar para trás).

Diagnóstico de `EXPLAIN` (`test_lab_signals_explain.py`):
```
$ uv run pytest tests/integration/test_lab_signals_explain.py -q
.                                                                        [100%]
1 passed in 30.15s
```

Regressão (suíte unitária inteira da API, sem testcontainers):
```
$ uv run pytest tests/unit -q -m "not integration"
456 passed, 1 warning in 69.90s (0:01:09)
```

Qualidade:
```
$ uv run ruff check apps/api
All checks passed!
$ uv run ruff format --check <9 arquivos tocados>
9 files already formatted
$ uv run pyright <5 arquivos de produção tocados>
0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py
scanned 543 files; 0 over budget, 0 grandfathered
$ pnpm gen:types
✨ openapi-typescript 7.13.0
🚀 packages/shared-types/openapi.json → packages/shared-types/src/generated/api.d.ts [755.9ms]
```

`ruff check --config packages/config/ruff.strict.toml` (camada lenta, só CI) tem violações
pré-existentes em `lab.py`/`lab_signals.py` (baseline de 631 no `apps/api` inteiro hoje) — não é
gate deste brief; duas violações `SIM300` (condição "Yoda") que adicionei em `_rank_of_cursor`
repetem literalmente o padrão que já existia em `list_page` antes desta mudança (mesmo estilo, não
uma regressão nova).

### EXPLAIN dos totais

Seed: 6.000 sinais (`agent_signals` + `signal_outcomes`) numa única `strategy_version_id`,
`cohort='prospective'`, distribuídos ~75% `terminal`, 5% `active`, 5% `pending_entry`, 5%
`no_entry`, 5% `censored` — ordem de grandeza do "milhares de sinais (momentum v1 sozinho, 929
avaliáveis)" que Everton mediu. Plano real (`EXPLAIN ANALYZE, BUFFERS`), Postgres do
testcontainer:

**Com `strategy_version_id` informado (caso comum: usuário olhando uma versão)** — o índice
composto existente `ix_agent_signals_version_emitted (strategy_version_id, emitted_at)` resolve o
filtro por versão via `Bitmap Index Scan`; o `cohort` (extração JSONB) e o `tracking_state` viram
`Filter`/`Recheck` residual sobre um conjunto já pequeno:

```
Aggregate  (actual time=19.897..19.899 rows=1 loops=1)
  ->  Nested Loop  (actual time=0.418..18.680 rows=6000 loops=1)
        ->  Nested Loop  (actual time=0.369..13.077 rows=6000 loops=1)
              ->  Bitmap Heap Scan on agent_signals
                    Recheck Cond: (strategy_version_id = '...'::uuid)
                    Filter: ((supporting_features ->> 'cohort'::text) = 'prospective'::text)
                    ->  Bitmap Index Scan on ix_agent_signals_version_emitted
                          Index Cond: (strategy_version_id = '...'::uuid)
              ->  Index Scan using pk_signal_outcomes on signal_outcomes
        ->  Index Only Scan using pk_markets on markets
Execution Time: 20.025 ms
```

A primeira página (`page_size=200`, `state=all`) sobre o mesmo filtro soma um nó `Sort`
(`Sort Method: top-N heapsort`, 227kB) porque **não existe índice na expressão
`(supporting_features->>'decision_at')::timestamptz`** — 39.79 ms com 6.000 linhas, aceitável hoje.
A consulta de posição do cursor (`page.from/to`) no meio do conjunto (~3.000ª linha) fica em
15.8 ms.

**Sem `strategy_version_id` (caso "todas as versões" — provavelmente a visão padrão do Lab no
produto):** nenhum índice ajuda o filtro de `cohort`, e o plano cai para `Seq Scan on agent_signals`
+ `Hash Join` + `Sort`:

```
Aggregate  (actual time=10.580..10.583 rows=1 loops=1)
  ->  Nested Loop  (actual time=0.162..10.243 rows=6000 loops=1)
        ->  Hash Join  (actual time=0.102..2.939 rows=6000 loops=1)
              ->  Seq Scan on agent_signals
                    Filter: ((supporting_features ->> 'cohort'::text) = 'prospective'::text)
              ->  Hash  (-> Seq Scan on markets)
        ->  Index Only Scan using pk_signal_outcomes on signal_outcomes
Execution Time: 10.698 ms
```
(a lista com `ORDER BY`+`LIMIT 201` no mesmo cenário: 28.56 ms, com `Sort` de novo.)

**Leitura:** em 6.000 linhas isso ainda é rápido (Postgres cabe tudo em cache, `shared hit` em
tudo, zero leitura de disco). O risco é de escala: `Seq Scan` cresce linear com o tamanho da
tabela e o `Sort` de `ORDER BY` na expressão cresce com `n log(page_size)` a cada página — ambos
sem índice para ajudar quando **não** há filtro de versão, que é exatamente a visão "Todas" que o
brief está corrigindo. A query de totais (`COUNT` sem `LIMIT`) é a mais exposta: seu custo é
proporcional ao tamanho do conjunto filtrado inteiro, toda requisição, sem forma de paginar em
torno dela.

**Pedido para `database-architect` (não editei `infra/migrations/**`, conforme a regra do
brief):**

1. Índice de expressão composto para o caminho "uma versão" (hoje já rápido, mas ainda faz um
   `Recheck`/`Sort` residual):
   ```sql
   CREATE INDEX ix_agent_signals_version_cohort_decision_at
   ON agent_signals (
     strategy_version_id,
     (supporting_features->>'cohort'),
     ((supporting_features->>'decision_at')::timestamptz) DESC,
     id DESC
   );
   ```
2. Índice (parcial, se `cohort='prospective'` for de fato o caso dominante — o argumento do brief
   para "partial index") para o caminho "todas as versões", que hoje é `Seq Scan`:
   ```sql
   CREATE INDEX ix_agent_signals_cohort_decision_at
   ON agent_signals (
     (supporting_features->>'cohort'),
     ((supporting_features->>'decision_at')::timestamptz) DESC,
     id DESC
   ) WHERE supporting_features->>'cohort' = 'prospective';
   ```
3. Um índice simples em `signal_outcomes.tracking_state` (hoje sem nenhum), para o `FILTER` dos
   totais e o filtro de `state`/`tracking_state` pararem de depender só do `Nested Loop` via PK.

Nenhum dos três é urgente no volume medido (dezenas de ms com 6.000 linhas); vira urgente quando o
Lab acumular dezenas de milhares de sinais em produção sem filtro de versão, que é o padrão de uso
que a T3.37b está prestes a habilitar (a visão "Todas" com paginação real).

### CONCERNS

1. **Índice pendente** — coberto acima; comportamento correto hoje, degrada com volume sem filtro
   de `strategy_version_id`.
2. **`page_size` substitui `limit`** em vez de conviver com ele — decisão de simplicidade (um único
   parâmetro de paginação com contrato fixo), não pedida explicitamente no brief mas coerente com
   "no unrequested configurability". Nenhum outro código chamava esse endpoint com `limit=`; só os
   testes deste próprio arquivo, que atualizei.
3. **`state` e `tracking_state` convivem** — mantive o filtro bruto `tracking_state` (usado por um
   teste já existente) ao lado do novo `state` (segmento). Não há teste combinando os dois ao mesmo
   tempo (uso esperado real: a UI usa `state`, não os dois); se alguém combinar os dois de forma
   contraditória (`state=open&tracking_state=terminal`), o resultado é a interseção vazia — não
   validei isso com um 422 explícito porque o brief não pediu e a combinação é inofensiva (lista
   vazia, não erro).
4. **`window`** não foi adicionado a `/signals` (ver seção "Contrato entregue" acima) — se a
   intenção real de T3.37 era outra, preciso de uma frase de confirmação antes de eu adicionar algo
   que a UI ainda não pediria de fato.
5. Os testes de paginação usam 50-55 linhas por caso (o menor `page_size` válido é 50) em vez dos
   2-3 do arquivo original — mais lento (cada teste ~1-2s de setup) mas ainda dentro do orçamento de
   5 min por arquivo.
