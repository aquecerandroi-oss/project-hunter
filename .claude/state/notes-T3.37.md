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

## T3.37b — Web (frontend-specialist)

**Data:** 2026-09-08. **Base:** `main` local (T3.37a já concluída e commitada nas notas acima
antes de eu terminar — consumi o contrato real, não fixtures adivinhadas). **Não commitado.**

### STATUS

`DONE`. Tabs e paginador agora mostram os números reais (`totals`/`page` do contrato T3.37),
navegação 100% por URL (Server Component refaz o fetch, nunca filtro client-side de uma página
parcial), scope switch do card de totais implementado ("desta página" | "de todas as concluídas",
nunca soma de página). `pnpm --filter @hunter/web lint|typecheck|test`: 0 erros, 923/923 testes
passando (saída real abaixo). Único aviso remanescente é pré-existente/de escala (arquivo de teste
compartilhado 27 linhas acima do orçamento de 350, nível `warn`, não bloqueia `lint`).

### Decisão de arquitetura (por que sem Server Action para paginar)

O brief citava "SectionUnavailable" para erro do paginador — o caminho mais simples e honesto que
satisfaz isso é reusar o padrão que `loadScoreboard` já usa nesta mesma página: separei o fetch de
sinais (`loadSignals`) do fetch de resumo/versões (`loadLab`), cada um com seu próprio
try/catch. Tabs e paginador viram navegação de URL pura (`buildLabHref`, mesmo padrão que
`lab-filters.tsx` já usava para window/cohort/versão) — o clique reescreve `?state=&page_size=&c=`
e o Server Component (`page.tsx`) refaz `getLabSignals` com os parâmetros novos. Uma falha nesse
fetch agora aparece como `SectionUnavailable` só na seção "Sinais — Sombra", sem derrubar o
cabeçalho/Placar/Versões — antes, uma falha em `getLabSignals` derrubava a página inteira dentro do
mesmo `Promise.all` que também buscava `summary`/`versions`. Isso elimina a necessidade de uma
Server Action dedicada para paginação (a antiga `loadLabSignalsAction`/"Carregar mais" foi
removida — sem acumulação client-side de itens, cada página é uma resposta do servidor completa e
correta).

### Cursor stack (por que "Anterior" funciona sem "previous cursor" da API)

O contrato T3.37a só dá `next_cursor` (keyset forward). Para "Anterior", a URL carrega a pilha de
cursores visitados como parâmetros `?c=` repetidos (`lab-signals-query.ts`'s `buildLabHref`):
clicar "Próxima" empilha o `next_cursor` atual; "Anterior" remove o último da pilha. Trocar de aba
(`state`) ou de `page_size` sempre zera a pilha (volta pra página 1) -- datasets diferentes, cursor
não faz sentido carregar entre eles.

### Reset de seleção/scroll sem `useEffect` + `setState`

A primeira versão usava um `useEffect` que chamava `setScrollTop`/`setSelectedSignal`/
`resetSelection()` a cada troca de página -- o lint (`react-hooks/set-state-in-effect`, erro nesta
config) rejeitou isso, corretamente: é exatamente o antipadrão que a própria doc do React
(“You Might Not Need an Effect”) descreve. Corrigido extraindo `LabSignalsGrid` (grade
virtualizada + painel lateral) como componente próprio, remontado via
`key={`${state}-${page.from}-${pageSize}`}` pelo pai -- uma nova página vira um mount novo, com
estado limpo de fábrica, sem efeito nenhum.

### Scope switch do card de totais ("desta página" | "de todas as concluídas")

- **"Desta página"**: exatamente o `summarizeRows` que já existia (T3.17/T3.17b), sem mudança de
  comportamento.
- **"De todas as concluídas"**: usa `GET /lab/shadow/summary` — já buscado no carregamento da
  página com os mesmos filtros (cohort/window) que o brief pede, então reaproveitado como prop em
  vez de um segundo fetch client-side (que o brief pede para nunca ser "um cálculo de página" — um
  fetch já feito para os mesmos filtros conta como "usar o endpoint", só que sem round-trip
  duplicado). Operações concluídas usa `totals.closed` (real, do próprio endpoint de sinais,
  sempre exato independente de filtro de versão). Resultado acumulado soma
  `metrics.sum_of_hypothetical_r` de cada versão relevante (`summary.versions`, filtrado pelo
  `versionId` corrente se houver) via a régua de dinheiro — nunca dado de página, e nunca soma se
  qualquer versão relevante não tiver amostra madura (retorna motivo explícito em vez de subestimar
  silenciosamente). **Concern honesto:** "Com lucro/prejuízo" e "Taxa de acerto" (quando mais de uma
  versão está em vista) não têm dado agregável exato no schema atual de `/summary` (não expõe
  numerador/denominador por versão) — em vez de inventar uma média ponderada ou arredondar uma taxa
  de volta pra contagem, mostro "—" com o motivo "não agregável somando versões diferentes". Com
  exatamente uma versão em vista, a taxa de acerto real da versão aparece. Ponto de revisão pedido
  ao product-designer/code-reviewer: aceitar essa lacuna honesta ou pedir uma mudança de contrato
  em `/summary` (fora do escopo cirúrgico deste brief).

### Tipos do contrato (T3.18-style: hand-written até o `pnpm gen:types` real, depois aliased)

`lib/api/lab-types.ts` ganhou `LabSignalsState`, `LAB_SIGNALS_PAGE_SIZES`/`LabSignalsPageSize`
(hand-written, literais estáveis e pequenos, verificados byte-a-byte contra
`operations["list_signals_..._get"]["parameters"]["query"]` do OpenAPI já regenerado) e
`LabSignalsTotals`/`LabSignalsPageRange` — **estes dois já aliased diretamente de
`components["schemas"]["SegmentTotalsOut"]`/`["SignalsPagePositionOut"]`** porque a T3.37a já
rodou `pnpm gen:types` antes de eu terminar (vi o arquivo gerado real, conferi campo a campo —
`SegmentTotalsOut {closed,open,pending,all}`, `SignalsPagePositionOut {from,to}`, `SignalsPage
{items,next_cursor,page,totals}` batem 100% com o que eu tinha escrito à mão contra o brief).
`SignalListItemOut`/`LabSignalsPage` continuam hand-written (fora do escopo cirúrgico deste brief
tocar, mesma nota que already existia no cabeçalho do arquivo para o legado pré-T3.18).

### FILES

**Criados:**
- `apps/web/components/lab/lab-signal-pager.tsx` — "1–200 de 2.135 · página N", Anterior/Próxima,
  select de page-size; navega via `router.push` num `useTransition` (indicador "carregando...").
- `apps/web/components/lab/lab-signals-grid.tsx` — grade virtualizada + painel lateral, extraída de
  `lab-signals-table.tsx`; remontada por `key` a cada página (ver seção acima).
- `apps/web/components/lab/lab-signals-query.ts` — `buildLabHref` puro (window/cohort/version/
  state/page_size/pilha de cursores → querystring), testável sem montar componente.
- `apps/web/components/lab/lab-signals-search-params.ts` — `parseLabSignalsQuery` puro (parsing de
  `?state=&page_size=&c=`, com fallback honesto pro default da web quando o valor é desconhecido).
- `apps/web/components/lab/lab-page-body.tsx` — "Sinais — Sombra" + "Versões (pesquisa)", extraído
  de `page.tsx` para caber no orçamento de 350 linhas por arquivo.
- `apps/web/tests/lab-signal-pager.test.tsx`, `apps/web/tests/lab-segment-tabs.test.tsx`,
  `apps/web/tests/lab-signals-query.test.ts`.
- `apps/web/tests/fixtures/lab-pagination.ts` — fixtures de `totals`/`page`/props completas de
  `LabSignalsTable`, separadas de `tests/fixtures/lab.ts` pra não estourar o orçamento de linhas
  desse arquivo compartilhado (edição líquida em `lab.ts` acabou zero — `git diff` confirma).

**Modificados:**
- `apps/web/lib/api/lab-types.ts`, `apps/web/lib/api/lab.ts` (`state`/`page_size` substituem
  `limit` no endpoint de sinais — `limit` nunca fazia parte do contrato novo), `apps/web/lib/api/
  lab-actions.ts` (removida `loadLabSignalsAction`, sem uso restante; `loadLabSignalEnvelopeAction`
  migrada para `page_size`).
- `apps/web/app/(app)/[orgSlug]/lab/page.tsx` — `loadLab` (resumo+versões) separado de
  `loadSignals` (sinais, T3.37); `parseLabSignalsQuery` para `state`/`page_size`/pilha de cursor.
- `apps/web/components/lab/lab-signals-table.tsx` — reescrito: sem acumulação client-side, sem
  filtro client-side por segmento, delega grade/painel para `LabSignalsGrid`.
- `apps/web/components/lab/lab-segment-tabs.tsx` — usa `totals`/`hrefs` reais em vez de contar
  `rows` carregadas; `aria-live` anuncia a contagem real a cada troca de aba.
- `apps/web/components/lab/lab-totals-card.tsx` — scope switch (ver acima).
- `apps/web/components/lab/lab-money.ts` — `totalsHeading` ganha o parâmetro `scope`;
  `combineClosedSumRUsdt` (nova, pura, testada).
- `apps/web/components/lab/lab-format.ts` — `formatCount` (agrupamento pt-BR, D17); dois motivos
  novos em `REASON_LABELS`.
- `apps/web/components/lab/lab-signal-segments.ts` — **lógica existente (`matchesSegment` etc.)
  intocada** (é a definição que a T3.37a espelhou em SQL); só acrescentei `SEGMENT_TO_STATE`/
  `stateToSegment` (mapeamento pt-BR ↔ contrato).
- `apps/web/components/lab/lab-filters.tsx` — preserva `state`/`page_size` ao trocar
  window/cohort/versão (zera a pilha de cursor, nunca o estado da aba).
- `apps/web/components/design/lab-hierarchy-showcase.tsx` — atualizado para os novos props de
  `LabSegmentTabs` (é só uma vitrine dev-only, `/_design`).
- Testes: `lab.test.ts`, `lab-signal-segments.test.ts`, `lab-money.test.ts`,
  `lab-signals-table.test.tsx` (reescrito), `lab-totals-card-in-table.test.tsx`,
  `lab-signal-panel.test.tsx`, `lab-page.test.tsx`.

**Removidos:** `apps/web/components/lab/lab-load-more.tsx` ("Carregar mais" não existe mais --
virou o paginador).

**Não tocados (lista de proibição do brief):** `.env*`, `apps/api/**`, `services/**`,
`obsidian/**`, `lab-curve-chart.tsx`, `candles-chart.tsx`, `portfolio-equity-chart.tsx`.

### TESTS (saída real)

```
$ pnpm --filter @hunter/web typecheck
$ tsc --noEmit
(sem saída — 0 erros)

$ pnpm --filter @hunter/web lint
$ eslint .
apps/web/tests/lab-page.test.tsx
  1:1  warning  File too large (377 lines | max 350).
✖ 1 problem (0 errors, 1 warning)

$ pnpm --filter @hunter/web test
$ vitest run
 Test Files  101 passed (101)
      Tests  923 passed (923)
   Duration  133.53s
```

### CONCERNS

1. **`tests/lab-page.test.tsx` 27 linhas acima do orçamento** (`warn`, não bloqueia `lint`) --
   arquivo compartilhado com muito trabalho em voo de outras tasks; não separei pra não arriscar
   conflito adicional numa árvore compartilhada. Se o code-reviewer preferir, dá pra extrair os 5
   testes T3.37 novos pra um `lab-page-signals.test.tsx` dedicado.
2. **Scope "de todas as concluídas" com mais de uma versão em vista**: "Com lucro/prejuízo" e
   "Taxa de acerto" mostram motivo honesto em vez de número (schema de `/summary` não tem
   numerador/denominator por versão pra agregar corretamente) -- ver seção própria acima.
3. **`LabFilters.cohorts`** (a lista de coortes do `<select>`) volta a depender só da página de
   sinais atualmente carregada (como já era antes de T3.37) -- se a busca de sinais falhar
   (`SectionUnavailable`), a lista cai pra `["prospective"]` apenas; isso é honesto (nunca inventa
   uma coorte) mas é uma pequena regressão de descoberta nesse caso raro (API de sinais fora do
   ar, resto da página ok).
4. **Prova visual em navegador não feita por mim** -- por instrução do brief e da memória
   ("in-app-browser-limits"), a captura de tela ("Concluídas" mostrando > 200 na VPS) é trabalho do
   orquestrador depois do deploy e do rebuild do `docker-web-1`.
5. Não fiz `git commit` (instrução explícita). Nenhum arquivo de `.env*`/API/serviços foi tocado.

## T3.37c — os dois índices de coorte (`0014_lab_signals_indexes`) (database-architect)

### STATUS

**DONE_WITH_CONCERNS.** A migração `0014` entrou com os dois índices, medidos
antes/depois em 50 000 linhas, reversível e sem deriva (`alembic check` limpo).
A ressalva é grande e está declarada: **os dois índices que a T3.37a pediu não
são escrevíveis como ela os escreveu**, e a página do Lab continua sem índice
até que uma linha de `apps/api/hunter_api/repositories/lab_common.py` mude.
Detalhes em `docs/DATABASE.md` §26.

O que o Postgres recusa (reproduzido no stack local e no testcontainer):

```
CREATE INDEX ix_probe_cast ON t337c_probe (((sf->>'decision_at')::timestamptz) DESC, id DESC);
ERROR:  functions in index expression must be marked IMMUTABLE
```

`text -> timestamptz` roda `timestamptz_in`, que é `STABLE` (`provolatile = 's'`
em `pg_proc`; aceita `'now'` e depende de `TimeZone`). Nenhum índice — e nenhuma
coluna `GENERATED` — pode ser construído sobre esse cast. Como
`LabSignalsRepository` ordena por
`CAST(supporting_features ->> 'decision_at' AS TIMESTAMPTZ) DESC, id DESC`,
**nenhuma migração** consegue tirar o `Sort` daquela consulta.

E não precisa: `emitted_at` **é** o mesmo instante, escrito da mesma variável
(`persist.py:93` `emitted_at=record.decision_at`; `record.py:164`
`envelope["decision_at"] = _jsonable(decision_at)`), o placar já ordena por
`s.emitted_at, s.id` (`replication_stats._ORDER`), e no banco do stack local as
840 linhas têm zero divergência entre os dois. A correção é uma linha, em
arquivo fora do meu escopo:

```python
# apps/api/hunter_api/repositories/lab_common.py
DECISION_AT = AgentSignal.emitted_at   # hoje: sa_cast(...supporting_features["decision_at"].astext...)
```

Com ela, a primeira página passa de **264 ms** para **0,96 ms** com 50 000
linhas (planos abaixo). Sem ela, os índices desta migração servem o placar, o
`count_population` do replay e o `cohort_cases` do stress — que já rodam hoje —
e ficam prontos para a página no dia em que a linha mudar.

### FILES

Criados:

- `infra/migrations/versions/0014_lab_signals_indexes.py` — dois `CREATE INDEX`
  simples, `downgrade` derruba os dois.

Modificados:

- `packages/core/hunter_core/db/models/_common.py` — `SHADOW_COHORT` (a
  expressão da coorte, byte a byte) e `shadow_cohort_indexes()`, que devolve as
  duas `Index(...)`.
- `packages/core/hunter_core/db/models/agents.py` — `*shadow_cohort_indexes()`
  no `__table_args__` de `AgentSignal`. As declarações moram no `_common` porque
  este módulo estava a 4 linhas do teto de 350 (`check_file_size.py`); com elas
  inline ele ia a 364 e quebrava o gate do CI.
- `apps/api/tests/integration/test_lab_signals_explain.py` — reescrito: 50 000
  sinais + 50 000 outcomes por SQL em massa, seis versões, três coortes; planos
  antes/depois/com-só-um-índice; três asserções novas (o `Index Scan` da visão
  padrão, a recusa `IMMUTABLE` e o `Sort` que ela causa, e o índice de
  `tracking_state` que ninguém lê).
- `packages/core/tests/integration/test_migrations.py` — `HEAD_REVISION` para
  `0014_lab_signals_indexes` (o próprio docstring da constante diz que toda
  revisão a sobe), `REPLAY_RUNS_REVISION` nova, dois testes da `0013` que usavam
  `downgrade -1` a partir do head agora descem até a `0013` primeiro (o mesmo
  padrão das guardas da `0003`), e dois testes novos da `0014`.
- `docs/DATABASE.md` — §26 inteira (o quê, por quê, medições, o que não entrou,
  trava, e a tabela de desvios em relação ao brief).

**Não** toquei: `apps/api/hunter_api/**`, `apps/web/**`, `services/**`,
`obsidian/**`, `.env*`. Nada foi commitado.

### TESTS (saída real)

`alembic` pela CLI, contra um Postgres 16 descartável (`docker run --rm
postgres:16-alpine`, porta 5434, removido ao final):

```
$ uv run alembic -c infra/migrations/alembic.ini upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial_schema, initial schema: ...
... (14 revisões) ...
INFO  [alembic.runtime.migration] Running upgrade 0013_replay_runs -> 0014_lab_signals_indexes, agent_signals: the cohort stops being invisible to the planner

$ uv run alembic -c infra/migrations/alembic.ini check
No new upgrade operations detected.

$ uv run alembic -c infra/migrations/alembic.ini downgrade -1
INFO  [alembic.runtime.migration] Running downgrade 0014_lab_signals_indexes -> 0013_replay_runs, ...
$ docker exec pg-t337c psql ... -c "SELECT indexname FROM pg_indexes WHERE tablename='agent_signals'"
ix_agent_signals_market_emitted
ix_agent_signals_opportunity_id
ix_agent_signals_regime_id
ix_agent_signals_status_expires
ix_agent_signals_version_emitted
pk_agent_signals
uq_agent_signals_id_slot

$ uv run alembic -c infra/migrations/alembic.ini upgrade head
INFO  [alembic.runtime.migration] Running upgrade 0013_replay_runs -> 0014_lab_signals_indexes, ...
$ uv run alembic -c infra/migrations/alembic.ini check
No new upgrade operations detected.
```

O `alembic check` **enxerga** a falta dos índices (derrubei os dois à mão, com a
versão ainda em `0014`):

```
INFO  [alembic.autogenerate.compare.constraints] Detected added index 'ix_agent_signals_cohort_emitted' on '('emitted_at', 'id')'
INFO  [alembic.autogenerate.compare.constraints] Detected added index 'ix_agent_signals_version_cohort_emitted' on '('strategy_version_id', 'emitted_at', 'id')'
FAILED: New upgrade operations detected: [...]
```

— mas repare que ele lista só as colunas **não-expressão**: uma divergência no
texto da expressão passaria calada. Por isso o teste novo lê
`pg_indexes.indexdef` e exige `supporting_features ->> 'cohort'` lá dentro.

Definição instalada:

```
CREATE INDEX ix_agent_signals_cohort_emitted ON public.agent_signals USING btree (((supporting_features ->> 'cohort'::text)), emitted_at, id)
CREATE INDEX ix_agent_signals_version_cohort_emitted ON public.agent_signals USING btree (strategy_version_id, ((supporting_features ->> 'cohort'::text)), emitted_at, id)
```

Suítes (testcontainers, um arquivo por invocação, em primeiro plano):

```
$ uv run pytest packages/core/tests/integration/test_migrations.py -q
96 passed in 224.97s (0:03:44)

$ uv run pytest apps/api/tests/integration/test_lab_signals_explain.py -q -s
3 passed in 37.43s
CREATE INDEX ix_agent_signals_cohort_emitted on 50000 rows: 147.6 ms
CREATE INDEX ix_agent_signals_version_cohort_emitted on 50000 rows: 191.8 ms

$ uv run pytest apps/api/tests/integration/test_lab_signals_pagination_api.py -q
8 passed in 42.19s

$ uv run pytest apps/api/tests/integration/test_isolation.py -q -k "another_organization or never_leak or nonexistent_organization or only_the_callers_own"
26 passed, 3 deselected in 178.79s (0:02:58)
```

Gates:

```
$ uv run ruff check .            -> All checks passed! (nos arquivos tocados)
$ uv run ruff format --check ... -> 4 files already formatted
$ uv run pyright <arquivos tocados> -> 0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py
error   386 > 350  packages/core/hunter_core/strategies/session_orb_v1.py
error   370 > 350  packages/core/hunter_core/strategies/constraints.py
scanned 547 files; 2 over budget, 0 grandfathered
```

Os dois arquivos acima do teto são de outra tarefa em voo (`strategies/**`), não
desta; `models/agents.py` fechou em **349**.

### PLANOS — antes/depois

**VPS, somente `EXPLAIN`, hoje (5 571 linhas em `agent_signals`, sem a `0014`).**
A consulta de totais da aba, exatamente como o repositório a emite:

```
Aggregate  (cost=768.69..768.70 rows=1 width=32)
  ->  Nested Loop  (cost=0.56..768.16 rows=28 width=4)
        ->  Nested Loop  (cost=0.28..715.97 rows=28 width=20)
              ->  Seq Scan on agent_signals  (cost=0.00..515.57 rows=28 width=32)
                    Filter: ((supporting_features ->> 'cohort'::text) = 'prospective'::text)
              ->  Index Scan using pk_signal_outcomes on signal_outcomes  (cost=0.28..7.16 rows=1 width=20)
        ->  Index Only Scan using pk_markets on markets  (cost=0.28..1.86 rows=1 width=16)
```

**28 linhas estimadas** — o palpite de 0,5 % para uma expressão sem estatística —
quando quase todas as 5 571 casam. A primeira página soma a esse `Seq Scan` um
`Sort` pela expressão do cast; o placar (`_EVALUABLE_SQL`) usa
`ix_agent_signals_version_emitted` e ainda paga `Filter` de coorte + `Sort`.

**Testcontainer, 50 000 linhas, 6 versões, 3 coortes (10 % replay, 10 %
replication, 80 % prospective), `EXPLAIN (ANALYZE, BUFFERS)`:**

| consulta | antes | depois |
|---|---|---|
| totais (coorte, todas as versões) | 96,7 ms · 122 633 buffers | **43,3 ms · 3 860 buffers** |
| página 1, todas as versões, `ORDER BY emitted_at` | 180,7 ms · 122 633 buffers | **0,96 ms · 634 buffers** |
| página 1, uma versão, `ORDER BY emitted_at` | 33,4 ms · 22 717 buffers | **1,6 ms · 700 buffers** |
| `count_population(cohort='replay:<run>')` | 27,8 ms · 17 632 buffers | **17,7 ms · 3 899 buffers** |
| placar: população avaliável de uma versão | 32,2 ms · 22 709 buffers (estimativa 42 × 6 667 reais) | **19,7 ms · 3 871 buffers** (estimativa 6 644) |
| página 1 **como a API a escreve hoje** | 264 ms · `top-N heapsort` de 40 000 linhas | **inalterada** |

A visão padrão, depois:

```
Limit  (cost=0.85..155.53 rows=201 width=704) (actual time=0.066..0.833 rows=201 loops=1)
  Buffers: shared hit=634
  ->  Nested Loop ...
        ->  Index Scan Backward using ix_agent_signals_cohort_emitted on agent_signals
              (actual time=0.025..0.080 rows=201 loops=1)
              Index Cond: ((supporting_features ->> 'cohort'::text) = 'prospective'::text)
              Buffers: shared hit=21
Execution Time: 0.963 ms
```

E a mesma página como a rota a escreve hoje, **com os índices já instalados**:

```
Limit  (cost=7267.71..7290.83 rows=201 width=704) (actual time=258.403..263.952 rows=201 loops=1)
  ->  Gather Merge
        ->  Sort  (Sort Key: (((supporting_features ->> 'decision_at'::text))::timestamp with time zone) DESC, id DESC)
              Sort Method: top-N heapsort  Memory: 227kB
              ->  Parallel Seq Scan on agent_signals (rows=20000 loops=2)
Execution Time: 264.336 ms
```

O placar é o caso mais interessante: continua sendo hash join com `Sort` (ele lê
a população inteira, não uma página) e mesmo assim cai pela metade — **só porque
a estimativa deixou de ser ficção**. Esse ganho vale hoje, sem nenhuma mudança
na API.

### CONCERNS

1. **A página do Lab só fica rápida com a linha do `lab_common.py`** (§26.2).
   Enquanto ela não mudar, a rota tem `Seq Scan` + `top-N heapsort` e 264 ms com
   50 000 linhas — hoje são ~5 600 linhas na VPS, então é rápido; a curva é
   linear no tamanho da tabela. Entrego a mudança pronta e testada do lado do
   banco; quem a fizer deve inverter a asserção de
   `test_the_lab_page_still_sorts_because_it_orders_by_a_cast` (o teste existe
   para falhar nesse dia) e conferir que o cursor keyset continua codificando o
   mesmo instante (é o mesmo valor, então os cursores emitidos antes continuam
   válidos).
2. **A consulta de totais é O(n) por natureza** e nenhum índice a conserta: ela
   conta o conjunto filtrado inteiro, sem `LIMIT`, a cada requisição. Caiu de
   96,7 ms para 43,3 ms com 50 000 linhas por causa da estimativa, mas com 500
   mil linhas volta a ser centenas de milissegundos. Se isso incomodar, a saída
   é do lado da API (cache curto por filtro, ou não recalcular totais quando só
   a página muda) — não é um índice que falta.
3. **`docs/reports/M3.md`** tem uma tabela de migrações com o estado de
   implantação de cada uma; a `0014` precisa de uma linha lá ("commitada, não
   aplicada em nenhum stack"). Não editei o arquivo por estar fora do escopo do
   brief.
4. **`models/agents.py` está em 349 de 350 linhas.** Coube porque as duas
   `Index(...)` foram para `_common.shadow_cohort_indexes()`. A próxima coisa
   que esse módulo ganhar vai quebrar o gate; o conserto de verdade é separar as
   tabelas de tenant (`Agent`, `AgentStats`) num módulo próprio, que toca todos
   os importadores e não cabia aqui.
5. **Achado fora do meu escopo, anterior a esta tarefa:**
   `apps/api/tests/integration/test_isolation.py::test_the_route_list_covers_every_tenant_route_the_app_serves`
   falha em `assert 24 == 23`. A rota que falta na matriz de isolamento é
   `GET /api/v1/orgs/{org_id}/portfolios/{portfolio_id}/risk/limits`, servida
   desde a T3.25 (`79c52c3`) e nunca acrescentada à lista `_tenant_routes`. Ou
   seja: **nenhum teste afirma que um membro da organização A recebe 404 nos
   limites de risco da B**. Os outros 26 testes de isolamento passam. Não
   corrigi (é `apps/api`, fora do meu escopo de escrita) — vale um brief curto.
6. **A `0014` não foi aplicada em lugar nenhum**: nem no stack local (que segue
   em `0013`) nem na VPS, onde só rodei `EXPLAIN`. O deploy a aplica; a trava é
   de dezenas de milissegundos (§26.5).
