# notes T3.43b — a hora de regime nunca é "stale" por construção

**Data:** 2026-09-08. **Base:** `main` @ `259d6f6`. **Não commitado.**

## STATUS

`DONE_WITH_CONCERNS` — as três entregas do brief (API aditiva, tile do dashboard,
testes com a forma real da linha horária) estão prontas e verdes. A única concern
real é operacional, não de código: `pnpm gen:types` regenerou
`packages/shared-types/src/generated/api.d.ts` a partir do estado *atual* da
árvore compartilhada, que já continha um campo alheio (`MarketStatusOut
.exchanges_planned`) de outro agente em voo — ver CONCERNS.

## O problema, resolvido

`RegimeRepository.current_per_scope` sempre devolvia a linha mais recente por
escopo, e `is_stale` era `end_time is not None or not scanner_alive`. A linha
horária do T3.43 (`regime_hourly_v1`, escopo `btc`) é **sempre** fechada por
construção (`end_time = start_time + 1h`) — essa regra a marcaria `stale` para
sempre, honesto ("a hora passou") mas lido como defeito no tile "Regime atual"
depois do scanner subir.

Regra nova, só para linhas do motor horário (`classifier_version` começando com
`regime_hourly_v1`): `is_stale = (agora − end_time > 2h) OU (heartbeat
regime_last_ts do produtor mais velho que 2h)`. A regra antiga (`regime_v0`,
escopo `global`, linha aberta) fica intocada.

## FILES

**API (aditivo, sem migração):**
- `apps/api/hunter_api/schemas/regime.py` — `RegimeComponentOut` (novo:
  `name`/`normalized`/`weight`/`contribution`); `RegimeOut` ganha
  `as_of`/`score`/`components`/`identity`, todos opcionais/aditivos; docstring de
  `is_stale` reescrita para descrever as duas regras (v0 vs. horária).
- `apps/api/hunter_api/services/regime.py` — `HOURLY_ENGINE_VERSION_PREFIX`,
  `HOURLY_STALE_AFTER` (2h), `is_regime_hourly_fresh`, `_is_hourly_engine`,
  `_hourly_is_stale`, `_decimal`, `_components` (extrai `supporting_features`
  para os 4 campos do tile, nunca fabrica); `_to_out`/`build_current`/
  `build_history_page` ganham o parâmetro `regime_hourly_fresh`.
- `apps/api/hunter_api/routers/regime.py` — `_newest_regime_last_ts` (lê
  `hb:scanner:*` cru, campo `regime_last_ts`, que `WorkerHeartbeatOut` não
  carrega) e `_regime_hourly_fresh` (fail-safe: erro/ausência = não fresco);
  os dois endpoints passam `regime_hourly_fresh` para o service.
- `apps/api/hunter_api/repositories/regime.py` — **não tocado** (lido, a leitura
  já trazia `classifier_version`, suficiente).

**Testes API:**
- `apps/api/tests/unit/test_regime_service.py` (novo, 26 testes) — detecção do
  motor horário (versão exata e com sufixo `+<digest>`), `is_regime_hourly_fresh`
  nos limites de 2h, `_hourly_is_stale` nas quatro combinações, parsing de
  `_decimal`/`_components` (inclusive componente ausente = `None`, nunca `0`),
  `_to_out`/`build_current` fim a fim.
- `apps/api/tests/integration/analysis_fixtures.py` — `seed_regime` ganha
  `classifier_version`; `hourly_regime_features()` (novo) monta o
  `supporting_features` real — mesmo formato que
  `services/scanner-worker/tests/test_regime_job.py
  ::test_the_row_carries_the_whole_decomposition` valida contra o banco de
  verdade (todo número é string decimal canônica, nunca um número JSON).
- `apps/api/tests/integration/test_regime_api.py` (+4 testes, 11 no arquivo) —
  linha horária fresca não é stale (com heartbeat); linha horária velha (>2h) é
  stale mesmo com heartbeat fresco; linha horária recente sem heartbeat é stale;
  linha `regime_v0` nunca fabrica os campos novos. As três primeiras usam
  `/regime/history` (nunca `/regime`) porque o banco de teste, compartilhado e
  session-scoped, já tem linhas `BTC` em `start_time` 3650/7300 dias no futuro
  (dos testes de `is_stale` do `regime_v0` no mesmo arquivo) que sempre
  venceriam `current_per_scope()` — `_find_in_regime_history` documenta isso.

**Web:**
- `apps/web/components/dashboard/regime-tile.tsx` — reescrito: rótulo do regime
  via `REGIME_LABEL` (pt-BR, D19 — antes mostrava o enum cru `BTC_BULL`);
  linha "score X/100 · confiança 0,8" (D17, vírgula) só quando `identity` não é
  nulo; linha "hora HH:mm Brasília · atualizado há Xmin" (só linhas horárias);
  `<details>` recolhido com os 5 componentes (rótulos pt-BR: Tendência,
  Amplitude, Volatilidade, Drawdown, Funding) e a contribuição de cada um,
  "sem leitura" honesto quando `normalized`/`contribution` são `null` (funding
  sem funding, por exemplo) — nunca um "0" fabricado. Nada disso aparece para
  uma linha `regime_v0` (`identity` nulo).
- `apps/web/lib/api/regime-types.ts` — export de `RegimeComponentOut`.
- `apps/web/tests/fixtures/radar.ts` — `makeRegime()` ganha os 4 campos novos
  com default honesto (`null`/`[]`).
- `apps/web/tests/dashboard-radar-tiles.test.tsx` — teste antigo de UNKNOWN
  atualizado (mostrava o enum cru "UNKNOWN"; D19 já aprovado por Everton em
  2026-09-08 pede rótulo pt-BR — agora "Sem classificação", com a asserção
  extra de que o enum cru não aparece); +5 testes novos para a decomposição
  horária (score/confiança/hora, badge stale numa linha horária, os 5
  componentes no `<details>`, e uma linha `regime_v0` que não mostra nada disso).

**Gerado:**
- `packages/shared-types/src/generated/api.d.ts` via `pnpm gen:types` — ver
  CONCERNS, o diff inclui um campo alheio.

## TESTS (saída real)

```
$ uv run pytest apps/api/tests/unit/test_regime_service.py -q
..........................
26 passed in 1.04s

$ uv run pytest apps/api/tests/integration/test_regime_api.py -q
...........
11 passed in 56.15s

$ uv run ruff check <7 arquivos tocados> && uv run ruff format --check <mesmos>
All checks passed!
7 files already formatted

$ uv run pyright <mesmos 7 arquivos>
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
error   359 > 350  packages/core/hunter_core/settings.py   # alheio, não tocado por mim
scanned 570 files; 1 over budget, 0 grandfathered
(nenhum arquivo meu no relatório — os 4 arquivos de teste tocados ficam entre
314 e 420 linhas, mas tests/** está fora do orçamento do checker)

$ pnpm gen:types
✨ openapi-typescript 7.13.0
🚀 …/openapi.json → …/api.d.ts [823.9ms]

$ pnpm --filter web lint
1 warning (tests/lab-page.test.tsx, arquivo alheio > 350 linhas) — 0 erros

$ pnpm --filter web typecheck
(limpo)

$ pnpm --filter web exec vitest run tests/dashboard-radar-tiles.test.tsx tests/dashboard-page.test.tsx tests/radar-labels.test.ts
Test Files  3 passed (3)
     Tests  59 passed (59)

$ pnpm --filter web test   (suíte inteira)
Test Files  1 failed | 105 passed (106)
     Tests  1 failed | 972 passed (973)
```

A única falha da suíte inteira do web é `tests/markets-table-visibility.test.tsx`
("Not implemented: navigation to another Document", limitação do jsdom com
`Enter` navegando a página) — arquivo que eu não toquei, sem relação com
regime/dashboard; provável flake pré-existente na árvore compartilhada.

## CONCERNS

1. **`packages/shared-types/src/generated/api.d.ts` carrega uma mudança
   alheia.** O brief pede `pnpm gen:types` (item 1 do "Deliver") mas a
   instrução de escopo do lançador proíbe tocar `packages/**` ("outro
   agente"). Como o gerador lê o estado *atual* de todo o app FastAPI, e a
   árvore compartilhada já tinha `schemas/system.py`/`repositories/markets.py`
   modificados por outro agente em voo (`MarketStatusOut.exchanges_planned`,
   ligado ao par de migrations `0015_runtime_login_role`/
   `0016_exchange_status_planned` que também apareceram no `git status`), o
   arquivo gerado carrega os dois diffs juntos — não dá para separá-los sem
   tocar/reverter o trabalho do outro agente, o que as regras de segurança
   proíbem. Ação sugerida ao orquestrador: ao integrar, `git add` só os
   trechos de `RegimeComponentOut`/`RegimeOut` desse arquivo (ou regenerar de
   novo depois que a outra tarefa também estiver commitada) em vez de atribuir
   o diff inteiro a T3.43b.
2. **`identity` duplica `classifier_version`.** Para uma linha horária os dois
   campos carregam exatamente a mesma string (`regime_hourly_v1[+digest]`) —
   o brief pediu os dois nomes explicitamente (o tile lê "identity" como "esta
   linha é do motor horário", sem precisar casar o prefixo de
   `classifier_version` ela mesma); documentado no docstring de `RegimeOut
   .identity`, mas é redundância de propósito, não descuido.
3. **Prova visual pendente.** O brief item 3 ("Screen proof… `run-design-audit
   .sh` … dashboard") é explicitamente "depois que o orquestrador reconstruir"
   — não rodei o script eu mesmo (stack Docker/Clerk fora do meu escopo desta
   tarefa isolada, e o navegador embutido não abre localhost/Clerk logado por
   nota de memória). A prova que tenho é os 5 testes de Vitest que renderizam
   o tile com a forma real da linha e verificam o texto pt-BR/score/hora/
   componentes.
4. **Teste antigo de UNKNOWN mudado.** `dashboard-radar-tiles.test.tsx` tinha
   um teste que esperava o enum cru "UNKNOWN" na tela; troquei a asserção para
   o rótulo pt-BR "Sem classificação" porque D19 (já aprovado por Everton em
   2026-09-08) proíbe enum cru na copy e o brief pede exatamente essa
   tradução para o regime. Sinalizando explicitamente por ser uma mudança de
   comportamento visível, não só aditiva.
5. **Nada tocado em `services/**`/`packages/**` fora do gerado.** Não precisei
   alterar o produtor (`regime_writer.py`) nem o heartbeat do scanner
   (`health.py`) — o campo `regime_last_ts` já existia; só passei a lê-lo, cru,
   do lado da API (não exposto por `WorkerHeartbeatOut`/`scan_heartbeats`, que
   pertencem a `services/system_status.py`, fora do escopo `*regime*`).
