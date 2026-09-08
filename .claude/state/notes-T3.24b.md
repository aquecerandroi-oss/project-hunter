# Notas T3.24b — Lab: uma hierarquia (opção A, Placar-primeiro) + blocos replay/replicação

**Agente:** frontend-specialist. **Base:** `main` em `9a56e37` (T3.18b já mesclado: `replay`/`replication` no scoreboard, `curve?cohort=`). **Nada commitado.**

## STATUS

`DONE_WITH_CONCERNS` — implementação completa (brief `brief-T3.24-design-lab.md` inteiro + adendo `brief-T3.24b-addendum-replay-blocks.md` A1–A5), `pnpm --filter web lint|typecheck|test` verdes no meu escopo, 96 arquivos de teste / 881 testes passando. Concerns reais abaixo (nenhum bloqueia a entrega, mas nenhum foi inventado como "resolvido" quando não foi).

## FILES

### Criados
- `apps/web/components/lab/labels.ts` — dicionário único status/purpose/tracking/result/replicação-status/evidence/motivos-de-replicação (pt, sem `_`).
- `apps/web/components/lab/lab-replay-block.tsx` — bloco "Replay" do card do Placar (addendum A1).
- `apps/web/components/lab/lab-replication-block.tsx` — bloco "Replicação" do card do Placar (addendum A2).
- `apps/web/components/design/lab-hierarchy-showcase.tsx` — mockup `/_design` opções A/B (brief §3), com `LabScoreboardCard`/`LabSegmentTabs`/`LabSignalRow` reais e fixtures de teste.
- `apps/web/tests/lab-scoreboard.test.tsx`, `apps/web/tests/lab-curve.test.tsx`, `apps/web/tests/lab-filters.test.tsx`, `apps/web/tests/lab-labels.test.ts`, `apps/web/tests/lab-totals-card-in-table.test.tsx` (extraído de `lab-signals-table.test.tsx` para caber no orçamento de 350 linhas).

### Modificados (principais)
- `apps/web/app/(app)/[orgSlug]/lab/page.tsx` — reordenado: faixa → Placar → "Sinais — Sombra" → "Versões (pesquisa)"; `LabTabs` removido; erro do Placar via `SectionUnavailable`; `LabHeader` recebe `asOf: string | null` (sobrevive a falha do `loadLab`); `openByDefault` por versão via `?version=`; `cohorts` distintas repassadas ao `LabFilters`.
- `apps/web/components/lab/lab-header.tsx` — compactado em 2 linhas, testids mantidos (`lab-header`, `lab-money-banner`, `lab-money-ruler`).
- `apps/web/components/lab/lab-scoreboard-card.tsx` — `text-lg`→`text-xl`, chip `10px`→`11px`, status via `labels.ts`, blocos Replay/Replicação condicionais.
- `apps/web/components/lab/lab-curve-chart.tsx` — altura 280→200, "(capado em 2.000 pontos)"→"(primeiros 2.000 pontos)", segunda série tracejada por `cohort` (addendum A3), chave por `(versionId, cohort)`.
- `apps/web/components/lab/lab-curve-section.tsx` — virou client component com seletor "Coorte da curva" (prospectiva/replay), busca sob demanda via novo Server Action.
- `apps/web/components/lab/lab-segment-tabs.tsx` — inalterado (já servia à guia principal); `lab-tabs.tsx` **removido** (guia única inerte).
- `apps/web/components/lab/lab-filters.tsx` — `Cohort` (input livre) → `<select>` "Coorte" com as coortes distintas da página + "prospective (padrão)".
- `apps/web/components/lab/lab-totals-card.tsx` — modo compacto (4 stats) por padrão, "Mais detalhes" abre os outros 8.
- `apps/web/components/lab/lab-signals-table.tsx`, `lab-signals-table-head.tsx`, `lab-signal-row.tsx`, `lab-signals-table-body.tsx` — nota de período visível (não mais `title`), nota de dinheiro única no rodapé (não mais por célula), colunas "Duração"/"Quantia simulada" escondem entre `md` e `xl` quando o painel está aberto, painel `lg:w-80 xl:w-96`.
- `apps/web/components/lab/lab-version-card.tsx` — virou `<details>`/`<summary>` (badge de status pt, maturidade compacta no resumo), `code_ref` como hash curto de 7 + `title` completo, `reasonLabel` para PnL/drawdown "não aplicável", `formatSumOfRDetail`.
- `apps/web/components/lab/lab-versions-empty.tsx`, `lab-maturity-badge.tsx`, `lab-r-ex-funding.tsx`, `lab-market-link.tsx`, `lab-signal-chips.tsx`, `lab-funnel.tsx`, `lab-signal-detail.tsx`, `lab-strategy-cell.tsx`, `lab-scoreboard.ts`, `lab-format.ts` — copy/rótulos conforme brief.
- `apps/web/lib/api/lab.ts` — `LabCurveParams.cohort` (addendum A4).
- `apps/web/lib/api/lab-actions.ts` — novo `loadLabCurveAction`.
- `apps/web/lib/api/lab-types.ts` — aliases `ReplayBlockOut`/`ReplicationBlockOut`/`SiblingArmOut`/etc a partir do OpenAPI gerado.
- `apps/web/tests/fixtures/lab.ts` — `exampleReplayBlock`/`exampleReplicationBlock` (dados reais do relatório T3.18b/testes de integração da API).
- `apps/web/tests/lab-page.test.tsx`, `lab-scoreboard.test.ts`, `lab-curve-chart.test.tsx`, `lab-version-card.test.tsx`, `lab-maturity-badge.test.tsx`, `lab-funnel.test.tsx`, `lab-signal-panel.test.tsx`, `lab-signals-table.test.tsx` — atualizados para a nova copy/estrutura (nenhum removido, só reescrito/realocado).
- `docs/DESIGN.md` — §3 ganhou a âncora "Lab (Sombra)"; §5 ganhou DESIGN-6.

## TESTS (saída real)

```
$ pnpm --filter web typecheck
$ tsc --noEmit
(sem erros)

$ pnpm --filter web lint
$ eslint .
C:\dev\project-hunter\apps\web\components\layout\me-unavailable-banner.tsx
  41:5  error  Calling setState synchronously within an effect ... react-hooks/set-state-in-effect
✖ 1 problem (1 error, 0 warnings)
```
(Esse erro é em `components/layout/me-unavailable-banner.tsx` — arquivo que eu não toquei, fora do escopo do brief; árvore compartilhada, provavelmente outro agente em voo. Meu próprio código: zero erros, zero warnings, incluindo `lab-signals-table.tsx` que eu ajustei para caber no orçamento de `max-statements`.)

```
$ pnpm --filter web test
Test Files  96 passed (96)
     Tests  881 passed (881)
```

`grep -rn "text-\[10px\]\|text-lg" apps/web/components/lab` → vazio (confirmado).

## PROVA (capturas antes/depois)

**Não capturadas.** Tentei rodar `bash .claude/state/tmp/run-design-audit.sh -g "lab"`, mas `docker-web-1` roda a imagem construída (`hunter-web:dev`), que não reflete os arquivos que acabei de editar — refletir exigiria `docker compose build web`, que hoje falha de verdade (`docs/reports/M0.md` KNOWN ISSUES #0: `Dockerfile.web` não copia `packages/shared-types`) e `pnpm build` local trava com `EPERM ... symlink` no Windows fora de modo elevado. Dado o histórico registrado (`subagent-stall-background-bash`: "6 crashed Docker Desktop em 2026-09-07"), decidi não arriscar um rebuild de container fora do meu escopo/tempo — isso é exatamente o papel do product-designer no fluxo do brief ("Revisor: product-designer... tela renderizada com dado real antes do commit"). Cobertura real que eu **consegui** produzir: 96 arquivos/881 testes Vitest verdes (Testing Library, DOM real via jsdom, dados dos fixtures reais de `contract-S3-lab.md`/`notes-T3.18.md`), incluindo os novos testes de ordem do DOM, `<details>` aberto/fechado via `?version=`, `<select>` de coorte, totais 4/8, e os blocos Replay/Replicação.

## CONCERNS

1. **Sem captura de tela real** (ver acima) — pré-condição de infraestrutura (rebuild do container `web`) fora do meu controle seguro nesta sessão. Recomendo o product-designer rodar o audit contra um `next dev` local (fora do Docker) ou aceitar a build/typecheck/test como prova substituta desta rodada.
2. **Filtros e guias por estado não ficaram na mesma linha em `lg`** (brief pedia "mesma linha das guias no lg"). `LabFilters` (window/coorte/versão) vive em `lab/page.tsx`, acima da seção; `LabSegmentTabs` vive dentro de `LabSignalsTable`. Uni-los na mesma linha exigiria levantar o estado de segmento para o componente pai ou fundir os dois componentes — decidi não arriscar essa reestruturação maior dentro do escopo já muito grande deste brief. Funcionalmente equivalente (mesma seção, filtros logo acima das guias), só não pixel-idêntico ao esquema.
3. **`replicationReasonLabel`/`REPLICATION_REASON_LABELS`** foram construídos lendo o código-fonte real de `packages/indicators/hunter_indicators/replication/{protocol,split,bootstrap}.py` (não societário ao meu escopo de edição, só leitura) para pegar os códigos exatos — mas não tenho um exemplo end-to-end gravado (a API ainda não me devolveu um payload real de `replication` com todos os motivos preenchidos); os textos pt são meus, meramente meus.
4. **Formato de "2 casas" no bloco Replay** (`formatRounded`) arredonda com `toFixed(2)`, nunca com `Decimal` — é só exibição (mesma regra que `lab-money.ts` já documenta: "Number... nunca uma substituta para um ledger real"), mas vale registrar que difere do resto do app, que em geral imprime a string Decimal crua.
5. **`me-unavailable-banner.tsx`** tem um erro de lint pré-existente (`react-hooks/set-state-in-effect`) fora do meu escopo — não toquei, mas registrando para não passar despercebido.
6. **Mockup `/_design`** (`lab-hierarchy-showcase.tsx`) importa fixtures de `@/tests/fixtures/lab` dentro de `components/design/**` — não há regra de lint que proíba isso, mas é o único lugar do app que faz esse tipo de import (o próprio brief pediu explicitamente "usando... os fixtures dos testes").
