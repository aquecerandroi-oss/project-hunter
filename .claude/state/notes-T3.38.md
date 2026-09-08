# Notas T3.38 — sinais idênticos de versões irmãs

## T3.38b (frontend-specialist, 2026-09-08)

**Escopo executado:** itens 1, 3, 4 e 5 do brief (`.claude/state/brief-T3.38-lab-identical-signals-grouped.md`) — agrupamento visual na tabela, card de resultado com "operações únicas", `title` das abas, e o parágrafo em `docs/plans/SHADOW-LAB.md`. Item 2 (campo `identity_key`/`totals.distinct_operations` na API) é do backend (T3.38a) — não implementado por mim; ao final da tarefa confirmei que `apps/api/hunter_api/schemas/lab_signals.py` já declara `identity_key: str` e `SegmentTotalsOut.distinct_operations: DistinctOperationsOut`, mas `packages/shared-types/src/generated/api.d.ts` **ainda não foi regenerado** (`pnpm gen:types` não rodou) — construí contra tipos hand-written marcados "contrato T3.38" em `apps/web/lib/api/lab-types.ts`, com fallback honesto (nunca quebra se o campo estiver ausente em runtime).

**Decisão de design não explícita no brief, registrada aqui:** o agrupamento só funde visualmente linhas quando o grupo (mesmo `identity_key`) abrange **mais de uma** `strategy_version_id`. Um grupo cujas linhas compartilham `identity_key` mas têm a mesma única versão nunca funde — cada linha continua sua própria linha. Isso não é só "com uma única versão selecionada nada muda" (texto literal do brief): é necessário mesmo com múltiplas versões carregadas, porque testes existentes (`lab-signals-table.test.tsx`, `lab-totals-card-in-table.test.tsx`) têm fixtures com `identity_key` padrão idêntico entre sinais de mercados/estados diferentes mas mesma versão — sem essa regra, o agrupamento por engano fundiria linhas genuinamente diferentes e faria uma delas desaparecer da tela. Documentado no docstring de `groupSignalsByIdentity` (`lab-signal-grouping.ts`).

**Arquivos criados:**
- `apps/web/components/lab/lab-signal-grouping.ts` — módulo puro de agrupamento (`groupSignalsByIdentity`, `hasMultipleVersions`, `dedupeByIdentity`).
- `apps/web/components/lab/lab-totals-heading.ts` — `totalsHeading`/`SIBLING_VERSIONS_NOTE`/`TotalsScope` extraídos de `lab-money.ts` (orçamento de 350 linhas).
- `apps/web/tests/lab-signal-grouping.test.ts`, `apps/web/tests/lab-signals-table-grouping.test.tsx`, `apps/web/tests/lab-totals-heading.test.ts`.

**Arquivos modificados:**
- `apps/web/lib/api/lab-types.ts` — `SignalListItemOut.identity_key` e `LabSignalsTotals.distinct_operations?` (contrato T3.38).
- `apps/web/components/lab/lab-strategy-cell.tsx` — `LabStrategyChips` (chips por versão).
- `apps/web/components/lab/lab-signal-row.tsx`, `lab-signals-table-body.tsx`, `lab-signals-grid.tsx` — operam sobre `LabSignalGroup[]` em vez de `SignalListItemOut[]`.
- `apps/web/components/lab/lab-signal-panel.tsx` — bloco "N versões irmãs decidiram..." quando o grupo selecionado tem mais de um membro (opção "ou o painel lateral" do brief — nunca muda a altura da linha, que a virtualização depende).
- `apps/web/components/lab/lab-money.ts` — `totalsHeading` movido, assinatura estendida.
- `apps/web/components/lab/lab-totals-card.tsx`, `lab-segment-tabs.tsx`, `lab-signals-table.tsx` — itens 3 e 4.
- `apps/web/tests/fixtures/lab.ts`, `apps/web/tests/fixtures/lab-pagination.ts` — `identity_key` na fixture padrão + fixtures do cenário do screenshot (`exampleSiblingSignals`, `exampleNearMissSignal`, `SIBLING_VERSION_LABELS`).
- `apps/web/tests/lab-money.test.ts`, `lab-segment-tabs.test.tsx`, `lab-signal-panel.test.tsx` — testes atualizados/adicionados.
- `docs/plans/SHADOW-LAB.md` — parágrafo em "Placar (T3.18)" (não tocado §"Funil", T3.36).

**Testes (saída real):**
- `pnpm --filter web typecheck` → limpo.
- `pnpm --filter web lint` → 0 erros, 1 warning pré-existente e não relacionado (`tests/lab-page.test.tsx`, 377 linhas, não tocado nesta tarefa).
- `pnpm --filter @hunter/web test` → 942/943 passando; a falha isolada (`tests/command-palette.test.tsx`) é pré-existente/flaky (passa sozinha, arquivo não tocado por mim) — não relacionada a T3.38.

**Pendente para reconciliar com T3.38a quando `pnpm gen:types` rodar:** nenhuma ação necessária do lado web — `LabSignalsTotals`/`SignalListItemOut` já compilam contra o tipo gerado real (interseção com campo opcional resolve para obrigatório quando presente).

## T3.38a (backend-specialist, 2026-09-08)

**Escopo executado:** item 2 do brief — `identity_key` por item de `GET /lab/shadow/signals` e `totals.distinct_operations` por estado. `pnpm gen:types` rodou; o intersection type de T3.38b em `apps/web/lib/api/lab-types.ts` agora resolve contra o campo real (confirmado por leitura, `apps/web/**` não tocado).

**Decisão de design não explícita no brief, registrada aqui:** a tupla do hash é `(market, source_bar_close, virtual_entry, exit_price, exit_reason, result)`. `exit_reason` não é um campo novo no schema (o brief só pede `identity_key`) — é calculado internamente por sinal: para `tracking_state=no_entry`/`censored` é o `no_entry_reason`/`censored_reason` específico; para qualquer outro estado (`terminal`/`active`/`pending_entry`) é o próprio `result.value` (`target`/`stop`/`expired`/`invalidated`/`open`) — o mesmo campo que `EXIT_REASON_LABEL` usa na coluna "Saiu" do web (T3.17b). Isso evita que dois sinais `no_entry`/`censored` com motivos diferentes (ex.: "geometria" vs. "atraso") colapsem no mesmo `identity_key` só por ambos terem `result=open`, sem duplicar informação nova no contrato.

`identity_key` é um sha256 hex (64 chars) de `market|source_bar_close.isoformat()|entry|exit|exit_reason|result` com separador `\x1f` (unit separator, nunca aparece em símbolo/decimal/ISO/motivo) e um sentinela `\x00` para `None` — para que "sem preço de entrada" nunca colida com "preço de entrada zero" nem "sem motivo" com motivo vazio (coberto por teste unitário dedicado). O algoritmo não tem significado além de "estável e sem colisão razoável"; nada decodifica o hash de volta.

`totals.distinct_operations` é computado por uma expressão SQL irmã (não o mesmo hash — apenas uma concatenação com os mesmos seis campos, delimitada por `|`), permitindo `COUNT(DISTINCT ...)` como agregado único com `FILTER` por estado (mesmo formato de `_count_totals`), em vez de trazer todo o dataset filtrado para Python só para desduplicar. As duas expressões (Python sha256 vs. SQL concat) não precisam produzir a mesma string — servem propósitos diferentes (`identity_key` é exposto e comparado pelo web; a expressão SQL só agrupa para contar) — mas usam o mesmo agrupamento de campos, então sempre concordam sobre "quantas operações distintas existem".

**Arquivos criados:**
- `apps/api/hunter_api/services/lab_signal_identity.py` — `compute_identity_key(...)`.
- `apps/api/tests/unit/test_lab_signal_identity.py` — 10 testes (determinismo, cada campo isoladamente diferente, tz-naive rejeitado, `None` não colide com `0`/string vazia).
- `apps/api/tests/integration/test_lab_signals_identity_api.py` — 3 testes: três versões irmãs decidindo a mesma operação compartilham `identity_key`; um "quase-igual" (preço de saída diferente) gera dois `identity_key`; `totals.distinct_operations` conta 2 operações distintas onde `totals.closed` conta 4 linhas.

**Arquivos modificados:**
- `apps/api/hunter_api/schemas/lab_signals.py` — `SignalListItemOut.identity_key: str`; novo `DistinctOperationsOut` (`closed`/`open`/`pending`/`all`); `SegmentTotalsOut.distinct_operations: DistinctOperationsOut`.
- `apps/api/hunter_api/services/lab_signals.py` — `_exit_reason(row)`; `_to_out` calcula e injeta `identity_key` via `compute_identity_key`.
- `apps/api/hunter_api/repositories/lab_signals.py` — expressões SQL `_SOURCE_BAR_CLOSE_TEXT`/`_EXIT_REASON_TEXT`/`_IDENTITY_KEY_TEXT`; `_count_distinct_operations` (mesma forma de `_count_totals`, `COUNT(DISTINCT ...)` com `FILTER`); `list_page` injeta `totals["distinct_operations"]`.
- `apps/api/tests/integration/test_lab_signals_pagination_api.py`, `apps/api/tests/integration/test_lab_api.py` — as duas asserções de igualdade exata de `totals` (que já existiam antes de T3.38) precisaram do novo campo aninhado; como todo fixture usado nesses dois arquivos tem `decision_at` distinto por linha, `distinct_operations` sempre coincide com as contagens brutas ali (nenhuma duplicata proposital nesses fixtures).
- `packages/shared-types/src/generated/api.d.ts` — via `pnpm gen:types` (diff aditivo: `DistinctOperationsOut`, `SegmentTotalsOut.distinct_operations`, `SignalListItemOut.identity_key`). `packages/shared-types/openapi.json` não versionado (gitignored) — apenas regenerado localmente.

**Testes (saída real):**
- `uv run pytest apps/api/tests/unit/test_lab_signal_identity.py -q` → `10 passed in 0.67s` / `1.01s` (após ajuste de tipo).
- `uv run pytest apps/api/tests/integration/test_lab_signals_identity_api.py -q` → `3 passed in 34.14s`.
- `uv run pytest apps/api/tests/integration/test_lab_signals_identity_api.py apps/api/tests/integration/test_lab_signals_pagination_api.py apps/api/tests/integration/test_lab_api.py -q` → `32 passed in 146.07s`.
- `uv run pytest apps/api/tests/unit -q` → `466 passed, 1 warning in 78.78s`.
- `uv run ruff check apps/api` → `All checks passed!`.
- `uv run ruff format --check <arquivos tocados>` → `already formatted` (2 arquivos reformatados uma vez com `ruff format`, depois limpos).
- `uv run pyright apps/api` → 0 erros nos arquivos tocados; 11 erros pré-existentes e não relacionados em `apps/api/tests/integration/test_lab_signals_pagination_api.py` (linhas 36-130, fora de qualquer trecho editado por mim — débito técnico anterior a T3.38, confirmado via `git diff` de que essas linhas não mudaram).
- `uv run python infra/scripts/check_file_size.py` → `scanned 552 files; 0 over budget, 0 grandfathered`.
- `pnpm gen:types` → `openapi-typescript 7.13.0 ... [575.9ms]`, diff conferido (18 inserções, aditivo).

**CONCERNS:**
- Os 11 erros pré-existentes do pyright em `test_lab_signals_pagination_api.py` (linhas 36-130: parâmetros sem anotação de tipo, `dict[str, list[Unknown]]`) já existiam antes desta tarefa e não fazem parte do escopo do brief; não corrigidos para manter a mudança cirúrgica. Reportando para quem for revisar essa suíte depois.
- `exit_reason` não é exposto como campo próprio no contrato (o brief só pede `identity_key`); é um detalhe de implementação interno tanto no lado Python (`_exit_reason`) quanto no SQL (`_EXIT_REASON_TEXT`). Se o web algum dia precisar do "motivo" isolado para outro fim, esse cálculo já existe e pode virar campo próprio sem quebrar `identity_key`.
- Não validei visualmente o rebuild do `docker-web-1`/design audit (fora do escopo do item 2, que é só a API) — quem fechar T3.38 como um todo deve rodar isso após reconciliar com T3.38b.
