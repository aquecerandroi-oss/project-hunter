# Notas T4.20 — rótulos do front para a fita por lote (T4.2g) e o plano para executar à mão (T4.19) (12/09/2026 18:2x BRT)

**Brief:** `.claude/state/brief-T4.20-rotulos-fita-por-lote-e-plano-a-mao.md`. Só `apps/web/**` + estas notas; `pnpm gen:types` não rodado; tipos lidos de `packages/shared-types/src/generated/api.d.ts` como estavam.

## O que os tipos carregam de fato (verificado antes de rotular)

| Valor do brief | Nos tipos gerados | Feito |
|---|---|---|
| fonte `swap_api_activity` | `MemeSourceOut.name` é `string` (não literal); `SOURCE_NAMES` da API (`services/meme_sources.py`) inclui o nome | rótulo "fita por lote (swap-api)" em `MEME_FEED_SOURCES` |
| `activity_mints`, `activity_live_1m`, `activity_dark_60s` | `MemeSourcesOut` (opcionais, `number \| null`) | "moedas no lote", "janela de 1 min viva", "lote sem janela de 1 min (60 s)" |
| `activity_calls_60s` (se existir) | **não existe**; existe `activity_batch_calls_60s` | rotulado o que existe: "chamadas do lote por minuto" |
| `tape_activity_pct` | `MemeSourcesOut` (mesma escala 0..100 de `tape_coverage_pct` — `_pct` no worker) | "cobertura da fita por lote N%" no detalhe do medidor "Fita coberta" |
| motivo `no_sol_quote` | união `MemeNullReason` (10 membros) | "sem cotação SOL/USD no minuto"; `MEME_NULL_REASONS` agora bate a lista inteira do contrato |
| motivo `no_trade_feed` | idem | "sem fita" (era "sem fita de negociações neste minuto") |
| `tape_source` (`activity_1m`/`swap_api`), `tape_as_of`, `tape_window_s` nas linhas de features | **não existem** em `MemeFeaturePointOut` nem em `schemas/meme.py` (só no `coverage_explanation` e nas colunas do banco, notas T4.2g §3) | **não rotulado** — nada a exibir em `/meme/{mint}` ou na mesa sem o campo no contrato |
| `manual_plan` | `DeskRowOut.manual_plan?: string \| null` (só ali; `TestRowOut` e `BetOut` não o trazem) | bloco no card da proposta; aba Testes **sem mudança** (lista apostas, não propostas, e o tipo não carrega o texto) |

Além do brief, os outros campos `activity_*` do contrato entraram na mesma linha para não ficar número sem rótulo: `activity_coverage_pct` ("cobertura do lote N% (K com leitura)" com `activity_covered`), `activity_cycle_s` ("ciclo do lote N s"), `activity_quote_age_s` ("cotação SOL/USD há N s"), `activity_skipped_60s` ("ciclos do lote pulados por minuto N").

`swap_api` passou de "fita do site (swap-api)" para **"fita por mint (swap-api)"** — com a fita por lote ao lado, as duas nunca se leem como uma só (par do `tape_source` que o brief nomeia).

## Arquivos (só `apps/web/**`)

- `components/meme/labels.ts` — fonte nova, `no_sol_quote`, `no_trade_feed` → "sem fita".
- `components/meme/meme-sources-format.ts` — `tapeGauge` com `tape_activity_pct`; `activityLine()` nova (todos os `activity_*`; `null` num worker anterior à rota, nunca linha vazia; um 0 real ao lado de `activity_dark_60s` é mostrado, não escondido).
- `components/meme/meme-sources-panel.tsx` — linha "fita por lote: …" no `full` (parágrafo) e no `line` (span com o texto inteiro no `title`).
- `components/meme-desk/manual-plan-block.tsx` — **novo**, `"use client"`: `<section aria-labelledby>` "Plano para executar à mão", tokens `warning`/`warning-soft` (estado de atenção, DESIGN.md §2), texto inteiro em `whitespace-pre-wrap` 13 px, botão "Copiar mint" (outline, `navigator.clipboard`; sucesso → "Mint copiado"; recusa → "não foi possível copiar — selecione o mint" + `logger.warn`, mint inteiro visível em `break-all`), a mesma contagem regressiva do cabeçalho.
- `components/meme-desk/proposal-card.tsx` — renderiza o bloco quando `row.manual_plan` vem; sem ele o card é o de antes.
- Testes: `tests/meme-labels.test.ts` (listas exaustivas: 7 fontes, 10 motivos), `tests/meme-sources-format.test.ts` (`activityLine`, `tape_activity_pct`, `source()` exportado), `tests/meme-sources-panel.test.tsx` (full + line), `tests/proposal-card.test.tsx` (4 casos do plano: ausente, inteiro + contagem, cópia, recusa do clipboard).

## Comandos e saídas reais (BRT = UTC − 3)

```
pnpm vitest run tests/meme tests/proposal-card   # 18:18 — antes de implementar (TDD)
 Test Files  4 failed | 18 passed (22)
      Tests  16 failed | 267 passed (283)

pnpm vitest run tests/meme tests/proposal-card   # 18:20 — depois
 Test Files  22 passed (22)
      Tests  283 passed (283)

pnpm turbo typecheck lint --filter=@hunter/web   # 18:21
@hunter/web:lint: ✖ 2 problems (0 errors, 2 warnings)   # tests/lab-page.test.tsx 377 linhas, tests/ws.test.ts 557 — pré-existentes, não tocados
 Tasks:    2 successful, 2 total

pnpm --filter web build                          # 18:23
 ✓ Generating static pages (6/6)
   Collecting build traces ...
> Build error occurred
[Error: EPERM: operation not permitted, symlink '...\@next\env' -> '...\.next\standalone\...']   # limitação conhecida do Windows (CLAUDE.md, docs/reports/M0.md #0); compilação e type-check passaram
```

## Preocupações / pendências

1. `tape_source`/`tape_as_of`/`tape_window_s` ficam sem tela até a API expor os campos em `MemeFeaturePointOut` (+ `pnpm gen:types`); os rótulos do brief ("fita por lote"/"fita por mint", "fita de HH:MM:SS", "janela de N s") entram aí, em `labels.ts` + `meme-features-table.tsx`.
2. Aba Testes: `TestRowOut` não traz `manual_plan`; se quiser o plano na ficha da aposta, é campo novo na API (`proposal_id` já existe para o join).
3. Não houve checagem visual no navegador (sem preview local; navegador embutido não abre localhost/Clerk). Contraste: `text-warning` sobre `warning-soft` já medido na DESIGN-5; a contagem no bloco usa `text-fg` (o vermelho sobre `warning-soft` mediria < 4,5:1 no escuro).
4. `navigator.clipboard` exige contexto seguro (HTTPS/localhost) — na VPS via HTTPS funciona; em HTTP o bloco diz que não copiou e deixa o mint selecionável.
5. Astra não consultada (`SendMessage` desabilitado).
6. Build: só o trace do standalone falha (EPERM no Windows); Linux/CI não afetados.

## `git status --porcelain -- apps/web` (18:2x BRT)

```
 M apps/web/components/meme-desk/proposal-card.tsx
 M apps/web/components/meme/labels.ts
 M apps/web/components/meme/meme-sources-format.ts
 M apps/web/components/meme/meme-sources-panel.tsx
 M apps/web/tests/meme-labels.test.ts
 M apps/web/tests/meme-sources-format.test.ts
 M apps/web/tests/meme-sources-panel.test.tsx
 M apps/web/tests/proposal-card.test.tsx
?? apps/web/components/meme-desk/manual-plan-block.tsx
```
