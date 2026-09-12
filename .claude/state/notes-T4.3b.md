# T4.3b — painel de fontes do Meme Radar na tela (`/meme` e `/meme/mesa`)

Execução de 12/09/2026, ~10:35 BRT (13:35 UTC) em diante, papel frontend-specialist. Sem commit.
Retomada de uma tentativa anterior cortada no meio: já existiam no disco (não commitados) os rótulos
novos em `components/meme/labels.ts` (`MEME_FEED_SOURCES`, `MEME_RADAR_STATUSES`, `MEME_SOURCE_STATUSES`
+ funções), os tipos `MemeSources`/`MemeSourceOut`/`MemeRadarStatus`/`MemeSourceStatus` em
`lib/api/meme-types.ts`, `getMemeSources`/`loadMemeSources` em `lib/api/meme.ts`, os testes ampliados
`tests/meme-labels.test.ts` e `tests/meme.test.ts`, e os dois testes novos
`tests/meme-sources-format.test.ts` + `tests/meme-sources-panel.test.tsx` (que definem a API do painel).
Nenhum componente existia ainda. Continuei a partir daí, sem refazer.

## Tipos gerados

`packages/shared-types/src/generated/api.d.ts` já traz `MemeSourcesOut` com todos os campos de
`apps/api/hunter_api/schemas/meme_sources.py` (inclusive os opcionais de T4.2d/T4.2e:
`discovery_blind_share_1h`, `progress_coverage_pct`, `tape_coverage_pct`, `fold_minute`, `fold_rows`,
`tape_*`, `mayhem_pending`, `mayhem_denominators_60s`, `coverage_explanation`) — conferido campo a campo
antes de codar. `pnpm gen:types` não era necessário e não foi rodado (a T4.2f mexe no backend em
paralelo; regenerar agora arriscaria trazer schemas a meio caminho).

## Regras de cor do chip (por fonte), na ordem de precedência

1. `disabled` → cinza "desligada"; `unknown` → cinza "sem leitura: <motivo do worker em português>"
   (`never_observed`, `never_connected`, `heartbeat_missing`; slug desconhecido vira texto com espaços).
2. `disconnected` → vermelho "desconectada"; `erroring` → vermelho "com erro · N na hora".
3. `errors_1h > 0` em fonte `ok`/`connected` → vermelho "N erro(s) na hora" (vermelho vence âmbar).
4. `age_s > stalled_after_s` (o limiar do próprio radar) → âmbar "atrasada há N s|min|h".
5. orçamento usado ≥ 90 % do limite → âmbar "orçamento N%".
6. senão verde "conectada" (socket) / "em dia" (REST).

Detalhe do chip: "atraso N.N s · usado/limite req/min" (ou "N/min (sem limite declarado)", ou "sem
leitura"); `observed_at` = `last_observed_at`; o `title` traz tudo + último erro + testemunha do banco.

## O que foi construído

- `apps/web/components/meme/meme-sources-format.ts` (241 linhas): `formatAgeS`, `formatBudget`,
  `budgetShare`, `sourceChip`, `progressGauge`, `tapeGauge`, `blindnessGauge`, `sourceGauges`,
  `radarStateLabel`, `trackedLabel`, `minuteFlags`, `BLINDNESS_SENTENCE`, `NOT_REPORTED`.
- `apps/web/components/meme/meme-sources-panel.tsx` (220 linhas): `MemeSourcesPanel({ sources, loop?,
  variant?: "full" | "line" })`, Server Component (sem `"use client"`); chips com `Badge`
  `positive|warning|negative|default` (tokens `-soft`, DESIGN-5), medidores em cards 3-col (1-col no
  mobile), estado do radar/laço com ponto colorido + texto; a versão `line` é uma linha que quebra, com
  os detalhes no `title`. O laço reaproveita `loopStateLabel` de `components/meme-desk/meme-desk-format`
  medido contra o `as_of` da API (relógio único).
- `/meme/page.tsx`: `Promise.all` ganhou `loadMemeSources` + `getMemeLoopState`; painel completo entre a
  faixa de visão geral e a lista; falha → `SectionUnavailable title="Fontes"`.
- `/meme/mesa/page.tsx`: `Promise.all` ganhou `loadMemeSources`; versão de uma linha entre o rótulo
  PAPEL e a faixa da mesa (acima das propostas, independente da falha da mesa; sem `loop`, porque a faixa
  da mesa já mostra o laço); falha → `SectionUnavailable compact`.
- `tests/meme-sources-panel.test.tsx`: só uma correção de lint (`@typescript-eslint/no-dynamic-delete`
  no `delete payload[key]` da tentativa anterior → `Object.fromEntries(...filter)`); asserções intactas.
- `docs/plans/T4-MEME-RADAR.md` §T4.3b (novo, entre §T4.2e e §7).

Montagem do medidor de cegueira quando `discovery_new_board_entries_1h === 0`: motivo "o board new não
listou nada na última hora" e detalhe omitido (um "0 de 0 entradas" ao lado seria redundante).

## Comandos e saída real (10:37–10:4x BRT)

`cd apps/web && timeout 290 npx vitest run tests/meme-sources-format.test.ts` → `Test Files 1 passed (1)
/ Tests 27 passed (27)` (primeira rodada do formatador, já com o arquivo escrito contra o teste).

`cd apps/web && timeout 290 npx vitest run tests/meme-sources-panel.test.tsx` → `1 passed / 34 passed`
(7 do painel + os 27 do formatador, que o arquivo importa para o `sourcesPayload`).

`cd apps/web && timeout 290 npx vitest run tests/meme*.test.ts tests/meme-sources-panel.test.tsx` →
`Test Files 11 passed (11) / Tests 145 passed (145)` (rodado duas vezes: antes e depois da correção de
lint no teste; mesmo resultado).

`timeout 590 npx turbo run typecheck lint --filter=@hunter/web` — 1.ª rodada: typecheck OK; lint
`✖ 3 problems (1 error, 2 warnings)`, o erro `tests/meme-sources-panel.test.tsx 64:48
@typescript-eslint/no-dynamic-delete` (herdado). 2.ª rodada, após a correção: `Tasks: 2 successful,
2 total`; lint `✖ 2 problems (0 errors, 2 warnings)` — os dois avisos são pré-existentes e de outros
arquivos (`tests/lab-page.test.tsx` 377 linhas, `tests/ws.test.ts` 557 linhas, `quality/max-lines`).

`cd apps/web && timeout 590 npx next build` (Next.js 15.5.25) → `✓ Compiled successfully in 9.0s` →
`Linting and checking validity of types ...` (passou) → `✓ Generating static pages (6/6)` → em
`Collecting build traces ...` falhou com `EPERM: operation not permitted, symlink ... .next\standalone\...`
(react, react-dom, client-only, @next/env). É a limitação conhecida do `output: standalone` no Windows
sem Developer Mode/elevação (`CLAUDE.md` "Build", `docs/reports/M0.md` KNOWN ISSUES #0; Linux/CI não
afetados) — acontece depois da compilação e do type-check, sem relação com os arquivos desta tarefa.
O aviso `The Next.js plugin was not detected in your ESLint configuration` também é pré-existente.

`wc -l`: `meme-sources-panel.tsx` 220, `meme-sources-format.ts` 241, `meme/page.tsx` 121,
`meme/mesa/page.tsx` 118, `labels.ts` 189 — todos abaixo de 350.

## Concerns

- Nenhuma tela verificada no navegador com dado real: não há stack rodando e subir dev server viola as
  regras da tarefa; fica para a sessão Playwright logada (memória "in-app browser não abre
  localhost/Clerk"). O layout foi pensado para 375 (chips em `flex-wrap`, medidores `grid-cols-1
  sm:grid-cols-3`), mas isso é raciocínio, não evidência.
- A T4.2f mexe no backend em paralelo: o painel tolera campo ausente (`undefined` → "o worker não
  informou este número") e fonte nova por nome, mas um **valor novo** nos enums `radar_status`/`status`
  cairia fora dos dicionários — `tests/meme-labels.test.ts` falha quando os tipos gerados ganharem um
  membro sem rótulo (é o gate que quebrou o deploy três vezes hoje); regenerar `pnpm gen:types` antes do
  commit se a T4.2f mudar `schemas/meme_sources.py`.
- `tests/meme-sources-panel.test.tsx` importa `sourcesPayload` de `meme-sources-format.test.ts` (desenho
  da tentativa anterior): os 27 testes do formatador rodam duas vezes na suíte. Inofensivo; se incomodar,
  mover o `sourcesPayload` para `tests/fixtures/`.
- "consultado em" fica em minúsculas no meio da frase (como a faixa de visão geral já faz); DESIGN-5
  pede "Consultado em" maiúsculo quando é o rótulo isolado — aqui é continuação de frase.
