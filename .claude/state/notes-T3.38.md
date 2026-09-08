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
- `docs/plans/SHADOW-LAB.md` — parágrafo em "Placar (T3.18)" (a seção §"Funil" é da T3.36 e foi arrastada por este commit).

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

## T3.38c-api (backend-specialist, 2026-09-08)

**Escopo executado:** achados 2, 3 e 4 da revisão `code-reviewer` sobre 96eea21/cb18c1a/c86ed19 (`.claude/state/brief-T3.38c-identity-key-fixes.md`), lado API apenas. Achados 1, 5 e 6 (misattribution do §Funil, dedupe de página no web, `console.warn`) são do T3.38c-web, fora do meu escopo.

**Achado 2 (HIGH) — `stop` entra na tupla:** a tupla passa de seis para sete campos: `(market, source_bar_close, entry_price, stop, exit_price, exit_reason, result)`. Decisão de design não explícita no brief, registrada aqui: `stop` é `signal_outcomes.virtual_stop` (o stop realmente rastreado pelo shadow tracker), não `agent_signals.stop` (o stop originalmente proposto no plano) — o mesmo padrão que `entry_price` já seguia (`virtual_entry`, não o preço de referência do plano) e `exit_price` (`signal_outcomes.exit_price`, não um target do plano). Isso exigiu um campo novo em `SignalRow`/`_row_from` (`virtual_stop`) já que o repositório só carregava `stop` (o campo do plano, exposto no contrato para exibição) — nenhum campo novo no contrato JSON, `virtual_stop` fica interno ao cálculo do `identity_key`.

**Achado 3 (MEDIUM) — normalização de Decimal:** `_decimal_part` agora faz `value.quantize(Decimal("1e-10"))` (dez casas decimais, mesma escala do `numeric(28,10)` do lado SQL) dentro de um `localcontext(prec=50)` (margem acima das 28 casas totais de `numeric(28,10)`, evita `InvalidOperation` em valores com muitos dígitos) e formata com `format(quantized, "f")` — não `str()` — porque `str()` de um `Decimal` quantizado próximo de zero (ex. `Decimal("1e-10")`) renderiza em notação científica (`"1E-10"`), que não bateria com a saída de texto do `numeric` do Postgres para o mesmo valor. Teste unitário novo prova a colisão pedida no brief: `Decimal("1.16930116")` e `Decimal("1.169301160")` agora geram a mesma chave.

**Achado 4 (MEDIUM) — separador seguro no SQL + teste de paridade:** `_IDENTITY_KEY_TEXT` trocou o literal `"|"` por `_IDENTITY_SEP = chr(31)` (mesmo `\x1f` do lado Python) e passou a fazer `cast(cast(campo, Numeric(28, 10)), Text)` nos três campos decimais (`virtual_entry`, `virtual_stop`, `exit_price`) — mesma normalização do achado 3, do lado SQL. Teste de integração novo (`test_python_identity_key_matches_the_sql_side_text_for_a_seeded_row`) semeia uma linha com todo campo do caminho de identidade não-nulo, lê o texto bruto de `_IDENTITY_KEY_TEXT` diretamente do Postgres (via `select(_IDENTITY_KEY_TEXT)`, importado do módulo do repositório com `# pyright: ignore[reportPrivateUsage]`, mesmo padrão já usado em `test_rate_limit.py`/`test_redis_bridge.py`), aplica `hashlib.sha256(...).hexdigest()` sobre esse texto e afirma que é **igual** ao `identity_key` que a API devolveu para a mesma linha — passou de primeira, confirmando que separador, ordem de campos e normalização decimal batem byte a byte entre os dois lados. Documentei no docstring de `_IDENTITY_KEY_TEXT` que essa igualdade só vale quando nenhum campo do caminho é `NULL`: `concat()` do Postgres descarta argumentos `NULL` silenciosamente (desloca o texto restante), enquanto o lado Python usa um sentinela `\x00` — assimetria pré-existente, fora do escopo dos achados 2-4, não corrigida (ver CONCERNS).

**Arquivos modificados:**
- `apps/api/hunter_api/services/lab_signal_identity.py` — `compute_identity_key` ganha o parâmetro `stop`; `_decimal_part` normaliza via `quantize`/`format(..., "f")`; docstrings do módulo atualizadas com os três achados.
- `apps/api/hunter_api/services/lab_signals.py` — `_to_out` passa `stop=row.virtual_stop` para `compute_identity_key`.
- `apps/api/hunter_api/repositories/lab_signals.py` — `_IDENTITY_NUMERIC`/`_IDENTITY_SEP` novos; `_IDENTITY_KEY_TEXT` ganha `virtual_stop` e os casts `numeric(28,10)`; `SignalRow.virtual_stop` novo campo; `_row_from` popula `virtual_stop=outcome.virtual_stop`.
- `apps/api/hunter_api/schemas/lab_signals.py` — docstring de `identity_key` atualizada (campo em si não mudou: contrato intacto, `pnpm gen:types` não necessário, confirmado por `git diff --stat` só mostrando a docstring).
- `apps/api/tests/unit/test_lab_signal_identity.py` — `stop` adicionado à base do `_key(...)`; 3 testes novos: `test_a_different_stop_is_a_different_operation`, `test_none_stop_does_not_collapse_into_the_same_key_as_zero_stop`, `test_decimal_values_that_differ_only_by_trailing_zeros_collide` (achado 3, com `entry_price`/`stop`/`exit_price`).
- `apps/api/tests/integration/test_lab_signals_identity_api.py` — 1 teste novo, `test_python_identity_key_matches_the_sql_side_text_for_a_seeded_row` (achado 4); testes pré-existentes (siblings compartilham `identity_key`, near-miss diverge, `distinct_operations`) continuaram verdes sem alteração porque os fixtures usados já seedam `stop` idêntico entre irmãos.

**Testes (saída real):**
- `uv run pytest tests/unit/test_lab_signal_identity.py -q` (dentro de `apps/api`) → antes do ajuste: `10 failed` (todos `TypeError: compute_identity_key() missing 1 required keyword-only argument: 'stop'` — falha pela razão certa, confirmando TDD). Depois: `13 passed in 0.51s`.
- `uv run pytest tests/unit -q` (dentro de `apps/api`) → `469 passed, 1 warning in 69.72s` (466 pré-existentes + 3 novos; nenhuma regressão).
- `uv run pytest tests/integration/test_lab_signals_identity_api.py -q` (dentro de `apps/api`, testcontainer único, um arquivo por invocação) → baseline (antes do teste novo) `3 passed in 40.03s`; depois de adicionar o teste do achado 4, `4 passed in 32.98s`, e novamente `4 passed in 35.19s` após o ajuste do `pyright: ignore`.
- `uv run ruff check <arquivos tocados>` → `All checks passed!`; `uv run ruff check .` (todo `apps/api`) → `All checks passed!`.
- `uv run ruff format --check <arquivos tocados>` → `6 files already formatted`.
- `uv run pyright <arquivos tocados>` → 1 erro (`reportPrivateUsage` no import de `_IDENTITY_KEY_TEXT`), corrigido com `# pyright: ignore[reportPrivateUsage]` na linha do nome (mesmo padrão de `test_rate_limit.py`); depois, `0 errors, 0 warnings, 0 informations`.
- `uv run pyright` (workspace inteiro) → 2604 erros pré-existentes em `packages/indicators/tests/unit/test_windows_memo.py` e `services/strategy-worker/tests/test_replay_stress.py`, nenhum nos arquivos tocados por mim (confirmado por busca — não são desta tarefa, `services/**` está fora do meu escopo permitido).
- `uv run python infra/scripts/check_file_size.py` → `scanned 554 files; 0 over budget, 0 grandfathered`.
- `pnpm gen:types` não executado — nenhum campo do contrato mudou (só docstring), conforme a seção "Prove" do brief previa ("não muda — só o input do hash").

**CONCERNS:**
- Assimetria de `NULL` entre os dois lados (Python: sentinela `\x00`; SQL: `concat()` descarta `NULL` e desloca o texto) não foi corrigida — não fazia parte dos achados 2-4, e corrigi-la exigiria trocar `func.concat` por uma expressão que preserve posição de `NULL` (ex. `COALESCE(..., '\x00')` em cada campo), o que é uma mudança maior fora do escopo cirúrgico pedido. Documentei isso no docstring de `_IDENTITY_KEY_TEXT` e restringi o teste de paridade a uma linha sem nenhum `NULL` no caminho. Quem tocar essa expressão depois deve saber que a igualdade "Python == SQL" só é garantida sem `NULL`s.
- Não toquei no lado web (achados 1, 5, 6) — reportado por T3.38c-web separadamente.

## T3.38c-web (frontend-specialist, 2026-09-08)

**Escopo executado:** achados 1, 2, 5 e 6 da revisão `code-reviewer` sobre 96eea21/cb18c1a/c86ed19 (`.claude/state/brief-T3.38c-identity-key-fixes.md`), lado web. Achados 3 e 4 (normalização de Decimal, separador SQL) são do T3.38c-api — não implementados por mim, confirmados lidos na seção acima.

**Achado 1 — misattribution do §Funil:** a única mudança pedida era a frase falsa em `.claude/state/notes-T3.38.md:23` (agora a linha do "Arquivos modificados" da T3.38b). Troquei "(não tocado §"Funil", T3.36)" por "(a seção §"Funil" é da T3.36 e foi arrastada por este commit)" — nenhuma reversão em `docs/plans/SHADOW-LAB.md` (o brief é explícito: "No revert").

**Achado 2 (HIGH) — grupo com R/dinheiro divergente mostra faixa, nunca só o primeiro membro:** criei `apps/web/components/lab/lab-signal-divergence.ts` (módulo puro): `pnlRangeUsdt`/`notionalRangeUsdt` comparam o dinheiro de cada membro do grupo (via `moneyForRow`, mesma régua) e retornam `{min, max}` só quando os valores realmente divergem — com tolerância de arredondamento ao centavo (`Math.round(x*100)`), para nunca sinalizar uma "divergência" que o leitor nem consegue ver na tela (ruído de Decimal sub-centavo nunca dispara isso). `formatMoneyRange` formata as duas pontas com o mesmo `formatUsdtSigned` de todo o resto da tela. Isso é uma salvaguarda de exibição: com o achado 2 da API fechado (stop entra na tupla do hash), a divergência não deveria mais acontecer — mas a tela nunca mais vai *esconder* o caso se acontecer (regressão futura, edge case não coberto pelo hash).
- Linha da tabela (`LabSignalRow`): quando o grupo mesclado (`versionChips`/`members.length > 1`) diverge em `pnlUsdt`/`notionalUsdt`, as células "Quantia simulada"/"Resultado" mostram a faixa (`LabMoneyRangeValue`, novo em `lab-money-cells.tsx`) com nota em `title` em vez do valor do `primary` isolado; sem divergência, nada muda (mesmo `LabResultValue`/`LabMoneyOrReason` de sempre).
- Painel lateral (`LabSignalPanel`/`SignalMoneyBlock`): mesma lógica, usando `siblingSignals` (que o painel já recebia desde a T3.38b) — "Resultado"/"Quantia simulada" mostram a faixa com `(faixa)` quando os irmãos divergem.
- Card de totais (`LabTotalsCard`): nova nota (`text-warning`, só no escopo "página", só quando `countDivergentGroups > 0`) nomeando quantas operações da página têm R/dinheiro divergente entre irmãs, em vez de somar a primeira versão em silêncio — "abra a linha na tabela para ver a faixa exata".
- Refatorei `LabSignalRow`/`SignalMoneyBlock` para extrair o cálculo da faixa e a renderização condicional em funções/componentes próprios (`moneyRangesForRow`/`ResultCell`, `moneyRangesForSiblings`/`notionalCellText`/`ResultCellContent`) depois que o `eslint complexity` acusou as duas funções acima do orçamento (14 e 16, máximo 12) com a lógica inline — voltou a 0 avisos novos.

**Achado 5 (MEDIUM) — card "desta página" dedupica por `identity_key` puro, como o servidor:** `dedupeByIdentity` (que reusava a regra de fusão visual de `groupSignalsByIdentity` — só mescla quando o grupo abrange mais de uma versão) foi **substituída** por `dedupeByIdentityKey`, nova em `lab-signal-grouping.ts`: dedupe puro por `identity_key`, ignorando quantas versões o grupo tem — a mesma regra `DISTINCT` que `totals.distinct_operations` do servidor usa. Isso fecha o gap: uma duplicata da **mesma versão** (que `groupSignalsByIdentity` deliberadamente nunca funde na tabela, por design da T3.38b — nunca esconder uma linha real quando só uma versão está carregada) antes era somada duas vezes pelo card; agora conta uma vez só, igual ao servidor. A regra de fusão *visual* (tabela) não mudou em nada — só a matemática de dinheiro do card. Também generalizei o gate de `totalsHeading` (`lab-totals-heading.ts`) de `page.versionsMixed` para `page.versionsMixed || page.uniqueCount !== page.rowCount`, para que o texto "N únicas de M linhas" também apareça nesse caso de duplicata-mesma-versão (senão o cabeçalho diria "(2)" ao lado de um stat "Operações: 1", uma inconsistência visível) — os testes antigos de `totalsHeading` continuam batendo (o `||` é estritamente aditivo).
- **Efeito colateral em fixtures, corrigido:** `makeSignal()` (fixture padrão) usava um `identity_key` fixo compartilhado por toda chamada sem override explícito (decisão documentada da T3.38b, para nunca acionar `groupSignalsByIdentity` sem querer). Com o dedupe puro agora usado pelo card, isso colapsava testes pré-existentes que criavam 2-3 `makeSignal({signal_id: "N", ...})` distintos esperando que o card somasse todos separadamente (`lab-totals-card-in-table.test.tsx` quebrou primeiro). Corrigido em `apps/web/tests/fixtures/lab.ts`: `identity_key` agora deriva de `signal_id` quando só `signal_id` é sobrescrito (sem override explícito de `identity_key`) — um override explícito de `identity_key` sempre vence (os cenários de irmãos/duplicata intencional continuam intactos).

**Achado 6 (LOW) — `console.warn` uma vez quando `distinct_operations` faltar:** `LabSegmentTabs` ganhou um `useEffect` que chama `logger.warn("lab_signals_totals_missing_distinct_operations", {...})` (via `@/lib/logger`, nunca `console.*` cru — regra do CLAUDE.md) na primeira vez que `totals.distinct_operations` vier ausente, guardado por uma flag em nível de módulo (nunca por render, nunca por aba/tab).

**Arquivos criados:**
- `apps/web/components/lab/lab-signal-divergence.ts` — `pnlRangeUsdt`/`notionalRangeUsdt`/`formatMoneyRange`/`countDivergentGroups`/`MONEY_DIVERGENCE_NOTE`.
- `apps/web/tests/lab-signal-divergence.test.ts` — testes unitários puros do módulo acima.
- `apps/web/tests/lab-segment-tabs-distinct-operations-warning.test.tsx` — achado 6, módulo isolado via `vi.resetModules()` para não poluir a flag "avisou uma vez" entre arquivos de teste.

**Arquivos modificados:**
- `.claude/state/notes-T3.38.md` — achado 1 (linha falsa corrigida) + esta seção.
- `apps/web/components/lab/lab-signal-grouping.ts` — `dedupeByIdentity` → `dedupeByIdentityKey` (achado 5).
- `apps/web/components/lab/lab-money-cells.tsx` — `LabMoneyRangeValue` novo.
- `apps/web/components/lab/lab-signal-row.tsx` — prop `members`; `moneyRangesForRow`/`ResultCell` (achado 2).
- `apps/web/components/lab/lab-signals-table-body.tsx` — passa `members={group.members}` para `LabSignalRow`.
- `apps/web/components/lab/lab-signal-panel.tsx` — `moneyRangesForSiblings`/`notionalCellText`/`ResultCellContent` (achado 2).
- `apps/web/components/lab/lab-totals-card.tsx` — usa `dedupeByIdentityKey` (achado 5); `MoneyDivergenceNote` novo (achado 2).
- `apps/web/components/lab/lab-totals-heading.ts` — gate estendido (achado 5); docstring/jsdoc atualizados.
- `apps/web/components/lab/lab-segment-tabs.tsx` — `warnOnceIfMissingDistinctOperations` (achado 6).
- `apps/web/tests/fixtures/lab.ts` — `makeSignal` deriva `identity_key` de `signal_id` por padrão (efeito colateral do achado 5, ver acima).
- `apps/web/tests/lab-signal-grouping.test.ts` — `dedupeByIdentity` → `dedupeByIdentityKey`; teste novo de duplicata mesma-versão.
- `apps/web/tests/lab-totals-heading.test.ts` — teste novo do gate estendido.
- `apps/web/tests/lab-signals-table-grouping.test.tsx` — 2 describes novos (achados 2 e 5, nível de integração via `LabSignalsTable`).
- `apps/web/tests/lab-signal-panel.test.tsx` — describe novo (achado 2, painel lateral).

**Testes (saída real):**
- `pnpm --filter web typecheck` → limpo (`tsc --noEmit`, sem saída).
- `pnpm --filter web lint` → `0 erros, 1 warning` — o mesmo pré-existente e não relacionado de sempre (`tests/lab-page.test.tsx`, 377 linhas, não tocado). Um momento intermediário (antes da extração `ResultCell`/`ResultCellContent`) mostrou 2 warnings novos de `complexity` (14 e 16, máx. 12) em `LabSignalRow`/`SignalMoneyBlock` — corrigidos por refatoração, confirmados de volta a 0 antes de reportar.
- `pnpm --filter @hunter/web test` → `106 arquivos, 963 testes, todos passando` (baseline T3.38b era 942/943 com 1 falha isolada pré-existente; a suíte completa rodou limpa desta vez, incluindo o `command-palette.test.tsx` mencionado como flaky).
- Verificação de linhas (`wc -l`/o próprio `eslint quality/max-lines`) em todo arquivo tocado: nenhum acima de 350 linhas (o maior, `lab-totals-card.tsx`, tem 300; o fixture `lab.ts` chegou a 354 no meio do trabalho por causa de um docstring longo — encurtado para 349 antes de reportar).

**CONCERNS:**
- O gate estendido de `totalsHeading` (achado 5) cobre o caso "mesma versão, `identity_key` duplicado" apontando "(N única(s) de M linhas)" — mas não adicionei uma nota textual explicando *por que* nesse caso específico (ao contrário do caso "versões irmãs", que tem `SIBLING_VERSIONS_NOTE`). Considerei suficiente porque o próprio texto do cabeçalho já é honesto (mostra as duas contagens); quem quiser uma explicação mais didática pode adicionar uma segunda nota condicionada a `!versionsMixed && uniqueCount !== rowCount` depois.
- Não validei visualmente no navegador (Playwright) — o cenário do achado 2 (R divergente entre irmãs) é uma salvaguarda defensiva que não deve ocorrer com dado real após o fix da API (achado 2 do lado API, `stop` na tupla); os testes de unidade/integração (`lab-signal-divergence.test.ts`, os dois describes novos em `lab-signals-table-grouping.test.tsx`, o describe novo em `lab-signal-panel.test.tsx`) fabricam a divergência artificialmente para provar que a tela nunca a esconde, mas ninguém verá isso na tela real do Lab hoje. Recomendo checagem visual (Playwright, per a nota "in-app-browser-limits") só se/quando os dois lados (API T3.38c-api + este) forem publicados juntos na VPS.
- Não toquei os achados 3 e 4 (API) nem `apps/api/**`/`services/**`/`obsidian/**`/`docs/**`/`.env*`, conforme escopo.
