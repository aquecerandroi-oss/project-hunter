# Notas T4.28c — o painel "Executor real" mostra o modo sozinho (estágio 1), escopo, recusas por motivo e portões recarregados

Execução: 2026-09-16, papel frontend-specialist. Brief do orquestrador. Nenhum `.env*` lido ou escrito,
nenhuma migração, nenhuma rede, VPS não tocada. Nenhum `sendTransaction`.

## 1. O que estava medido (motivo da tarefa)

`hb:meme:executor` já carregava (T4.28/T4.28d/T4.28e/T4.28f) `auto_approve`, `auto_approve_max_per_hour`,
`auto_approved_1h`, `auto_refused_1h` (JSON motivo→contagem), `auto_skipped` (JSON), `small_test_used_sol`,
`small_test_trades_done`, `small_test_remaining_sol`, `small_test_exhausted`, `gates_mtime`,
`gates_reloaded_at`, `gates_reload_error`, mas `meme_live.py::read_executor` só mapeava os campos mais
antigos — confirmado por leitura antes de codar (`LiveExecutorOut` não tinha nenhum desses campos).

## 2. API (`apps/api`)

- `hunter_api/schemas/meme_live.py`: `LiveExecutorOut` ganhou os 12 campos, todos opcionais (`= None`/`= {}`)
  — um heartbeat de antes desta feature não inventa nada. SOL como `DecimalStr`; contagens como `int`;
  `auto_refused_1h`/`auto_skipped` como `dict[str, int]`.
- `hunter_api/services/meme_live.py::read_executor`: mapeamento campo a campo, mais dois helpers novos —
  `_int` (string → `int | None`, nunca crasha) e `_int_dict` (um `dict[str, Any]` do JSON → `dict[str, int]`,
  descarta silenciosamente uma contagem que não vira `int`, nunca derruba a leitura por uma linha ruim).
  `kill_switch_latch_reason` **já** fluía ponta a ponta desde antes (T4.28d); não precisei mexer no schema
  nem no `read_executor` para ele — só corrigi como o **web** o mostra (§3).
- Teste novo `apps/api/tests/unit/test_meme_live_service.py` (4 casos, `read_executor` puro, sem DB/Redis):
  heartbeat de antes da feature (tudo `None`/`{}`), estágio 1 ligado com escopo parcialmente gasto e
  releitura recente, escopo esgotado + falha adiada dos portões, e uma linha corrompida (`auto_refused_1h`
  com valor não numérico, `auto_skipped` não é JSON) que não derruba a leitura.
- Tipos web: `pnpm gen:types` roda sem servidor (`infra/scripts/dump_openapi.py` monta o app com clients
  preguiçosos) — gerei de verdade, não editei `api.d.ts` à mão. Único arquivo mudado:
  `packages/shared-types/src/generated/api.d.ts` (+34 linhas, os 12 campos novos).

## 3. Web (`apps/web`)

- **Achado ao ler o painel existente:** `KillSwitchBlock` já mostrava `kill_switch_latch_reason`, mas **cru**
  (`motivo da trava: {texto}`) — quebra DESIGN-5 ("sem backstage na copy"), invisível antes porque o único
  valor real até hoje era `daily_loss_cap_reached` (que ao menos lê como frase); T4.28d passou a gravar
  `gates_invalid:<motivo>` também. Corrigi com a mesma função de tradução usada no bloco novo
  (`killSwitchLatchReasonLabel`), nas duas telas.
- `components/meme-live/refusal-labels.ts` (+75 l., 205 no total): vocabulário novo —
  `autoSkipLabel` (pulos do robô: `expired`, `too_old`, `mint_busy`, `recently_refused`, `suggested_incomplete`,
  `exceeds_max_sol_per_bet`, `hourly_cap`, `tick_cap`, `mint_repeated`, `decided_concurrently`, `kill_switch`,
  `program_upgraded`, mais o prefixo dinâmico `scope_exhausted:<max_trades|max_total_sol>` via
  `scopeExhaustedLabel`, exportada e reusada pela linha de escopo); `gatesReloadErrorLabel` (vocabulário do
  `hunter_core.execution.meme.gates`, com o prefixo `deferred:` da graça de um tique, T4.28f);
  `killSwitchLatchReasonLabel` (`daily_loss_cap_reached` reusa `executorRefusalLabel`; `gates_invalid:<motivo>`
  reusa o mapa de `gatesReloadErrorLabel` — os dois nunca divergem na tradução). `progress_above_window`/
  `progress_below_window` já existiam em `CHECK_REFUSAL_LABEL` — nada a fazer ali.
- `components/meme-live/live-format.ts` (+52 l., 146 no total): `autoApprovedLine` ("aprovadas na hora N de
  M", cada número ausente dito por si) e `autoScopeLine` (tetos de `gates.small_test.{max_trades,
  max_total_sol}` + contadores do executor → `tradesLine`/`solLine`/`exhaustedLabel`; refatorado em
  `tradesLineOf`/`solLineOf` para ficar sob o teto de complexidade do ESLint, warning zero).
- `components/meme-live/age-note.tsx` (novo, 26 l.): `AgeNote` extraído de `live-executor-panel.tsx` com um
  `prefix` configurável ("atualizado"/"mudou"/"recarregado") — evita duplicar o componente no bloco novo.
- `components/meme-live/auto-stage1-panel.tsx` (novo, 95 l.): `AutoStage1Block`, Server Component puro (sem
  hooks) — pílula ligado/desligado, "aprovadas na hora", escopo (compras feitas/teto, SOL usado/restante/teto,
  badge "esgotado"), chips de recusas da hora (por motivo, `executorRefusalLabel`) e de pulos da hora (por
  motivo, `autoSkipLabel`, ordenados por contagem desc.), portões (mtime + recarregado há, `AgeNote`, mais o
  erro se houver) e o motivo da trava do corta-circuito quando travado.
- `components/meme-live/live-executor-panel.tsx`: importa `AgeNote` do novo arquivo em vez de definir local;
  renderiza `<AutoStage1Block>` em `LigadoBody` só quando `executor.auto_approve === true` (linha inteira,
  `sm:col-span-2`); `KillSwitchBlock` passa a usar `killSwitchLatchReasonLabel` (§ achado acima).
- Fixtures de teste (`tests/{approve-real-sheet,live-executor-panel,meme-live-labels}.test.tsx/.ts`):
  `auto_refused_1h`/`auto_skipped` têm default `{}` no Pydantic mas o OpenAPI gerado os marca **obrigatórios**
  (mesmo padrão de `orders_by_state`/`blocked_exits`/`kill_switch_sources`, já assim antes de mim) — `tsc`
  apontou os três literais `LiveExecutor` que ainda não tinham os dois campos; adicionei `{}` nos três.
- Teste novo `apps/web/tests/meme-live-auto-stage1.test.ts` (19 casos): `autoApprovedLine` (os dois números,
  ambos ausentes, um dos dois ausente, zero não é "sem leitura"), `autoScopeLine` (parcialmente gasto, sem
  portões, esgotado por cada contador, contadores sem `gates.small_test`), `autoSkipLabel` (todo o conjunto
  nomeado + o prefixo dinâmico + fallback nunca-visto), `gatesReloadErrorLabel` (nulo, trava semântica,
  `deferred:` da graça, motivo não reconhecido) e `killSwitchLatchReasonLabel` (não travado, perda diária,
  `gates_invalid:`, motivo não reconhecido).

## 4. Comandos e saídas (primeiro plano)

```
uv run pytest apps/api/tests/unit/test_meme_live_service.py -q                 -> 4 passed
uv run pytest apps/api/tests/unit -q -k meme                                   -> 126 passed, 602 deselected (antes: 122)
uv run pytest apps/api/tests/unit -q                                           -> 728 passed (antes: 724)
uv run ruff check / ruff format --check (arquivos tocados)                     -> All checks passed! / already formatted
uv run pyright apps/api/hunter_api/{schemas,services,routers}/meme_live.py
   apps/api/tests/unit/test_meme_live_service.py                              -> 0 errors, 0 warnings, 0 informations
pnpm gen:types                                                                 -> openapi-typescript ok (484ms)
pnpm --filter @hunter/web exec tsc --noEmit                                    -> sem saída (limpo)
pnpm --filter @hunter/web exec eslint <arquivos tocados>                       -> 0 problems (após extrair
                                                                                   tradesLineOf/solLineOf por complexidade)
pnpm --filter @hunter/web exec vitest run tests/meme-live-auto-stage1.test.ts
   tests/meme-live-labels.test.ts tests/live-executor-panel.test.tsx
   tests/approve-real-sheet.test.tsx                                          -> 4 files, 59 passed
pnpm --filter @hunter/web lint                                                -> 0 errors (2 warnings pré-existentes,
                                                                                   arquivos não tocados: lab-page.test.tsx,
                                                                                   ws.test.ts, > 350 linhas)
pnpm --filter @hunter/web test                                                -> 160 files, 1601 passed
uv run python infra/scripts/check_file_size.py                                -> 1 acima do orçamento, pré-existente
                                                                                   e não tocado por mim
                                                                                   (packages/exchange-adapters/.../pumpfun/quote.py)
```

## 5. O que fica com o Everton

Checagem visual no navegador não foi possível aqui (login Clerk). Depois do deploy, em `/ever/meme/mesa`
(com `MEME_LIVE_AUTO_APPROVE` ligada na VPS, como já está desde a T4.28): dentro do painel vermelho
"Executor real", estado `ligado`, deve aparecer um bloco cinza "Modo sozinho — estágio 1" com a pílula
"ligado", a linha "aprovadas na hora N de 5", o escopo (compras/teto, SOL usado/restante/teto, badge
"esgotado" se for o caso), os chips de recusas e de pulos da última hora (ambos podem estar vazios —
"nenhuma nesta hora" é honesto, não um erro), a linha de portões (arquivo mudou há X, recarregado há Y) e,
se o corta-circuito estiver travado, o motivo em português (não mais o código cru).

## 6. Concerns

1. `auto_rejected_total` (heartbeat) não foi mapeado — não estava na lista de campos do brief e o painel não
   pede um total de rejeitadas; fica disponível no Redis (`HGETALL hb:meme:executor`) se for útil depois.
2. Os chips de "pulos da hora" (`auto_skipped`) são um contador em memória do processo (zera no restart,
   T4.28 concern 3) — o painel não avisa isso explicitamente; se incomodar, um texto pequeno ("desde o
   último início do executor") resolveria.
3. Não recomputei o `SectionUnavailable`/estados `ausente`/`desligado` — o bloco novo só aparece em `ligado`
   com `auto_approve === true`, por desenho do brief.

## 7. Commit

```
git add -- apps/api/hunter_api/schemas/meme_live.py apps/api/hunter_api/services/meme_live.py \
  apps/api/tests/unit/test_meme_live_service.py packages/shared-types/src/generated/api.d.ts \
  apps/web/components/meme-live/live-executor-panel.tsx apps/web/components/meme-live/live-format.ts \
  apps/web/components/meme-live/refusal-labels.ts apps/web/components/meme-live/age-note.tsx \
  apps/web/components/meme-live/auto-stage1-panel.tsx apps/web/tests/approve-real-sheet.test.tsx \
  apps/web/tests/live-executor-panel.test.tsx apps/web/tests/meme-live-labels.test.ts \
  apps/web/tests/meme-live-auto-stage1.test.ts .claude/state/notes-T4.28c.md
git commit -- <os mesmos arquivos>
```

**Atenção:** a árvore compartilhada tem `.claude/launch.json`, `docs/DESIGN.md`,
`packages/core/tests/unit/test_settings.py`, `docs/ACTIVATION.md`, `docs/RISK_ENGINE_MEME.md` e
`packages/exchange-adapters/hunter_exchanges/pumpfun/quote.py` modificados por outro trabalho — não
incluídos aqui, nunca `git add -A`.
