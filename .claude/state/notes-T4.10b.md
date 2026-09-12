# T4.10b — traçado de linhas no gráfico, colunas de linha/hype na tabela, sonda/escala na mesa (frontend)

Execução de 12/09/2026, início ~10:51 BRT (UTC−3). Papel: frontend-specialist. Sem commit.
Contrato: `.claude/state/brief-T4.10-tracado-de-linhas-e-sonda-de-hype.md` (Parte B). A Parte A
(backend) roda em paralelo; no início desta execução **nenhum** campo novo existia em
`apps/api/hunter_api/schemas/meme.py`/`meme_desk.py` nem em `packages/shared-types/src/generated/api.d.ts`
— tudo aqui é construído contra os nomes do contrato, lido de forma tolerante (campo ausente →
"linha: sem leitura"), e `pnpm gen:types` é rodado de novo no fim.

## Estado da árvore antes de mim (não são meus, não tocados)

`git status --porcelain -- apps/web packages/shared-types` vazio às 13:51 UTC. Na raiz havia
`.claude/launch.json`, `docs/DESIGN.md`, `pumpfun/rate_shared.py`, `pumpfun/swap_api.py` modificados
por outros agentes.

## Plano (cada passo com sua verificação)

1. Rótulos exaustivos (`components/meme/labels.ts`: `line_reason`, `hype_reason`;
   `components/meme-desk/labels.ts`: `leg`) + testes de exaustividade — vitest falha primeiro.
2. `components/meme/meme-lines.ts` (puro): leitura tolerante dos campos de linha/hype, `lineReading`
   (absent | untraceable | traced), overlay geométrico em espaço de dados (reta de suporte projetada
   até agora, máxima 15 min da janela anterior, marca de rompimento) — `tests/meme-lines.test.ts`.
3. Gráfico (`meme-curve-chart.tsx` + `meme-curve-lines.tsx`): desenha as linhas com a mesma escala
   de tempo/valor da curva; legenda em texto; "linha ainda não traçável: <motivo>" / "linha: sem leitura".
4. Tabela (`meme-features-table.tsx` + `meme-features-line-cells.tsx`): colunas Suporte / Fundos
   ascendentes / Rompimento / Hype com motivo nomeado.
5. Mesa: `leg = probe` → "semi-comprado (sonda)", `scale` → "escalado (perna 2)" com link para a
   sonda-mãe (âncora `#bet-<id>` só quando a mãe está na página; senão o id curto, sem link inerte).
6. `npx turbo run typecheck lint --filter=@hunter/web`, `npx next build` ("Compiled successfully"),
   `pnpm gen:types` de novo, `git status --porcelain -- apps/web`.

## Decisões

- **Tolerância a campo ausente** é por leitura de chave (`Object.hasOwn`), não por versão: um payload
  sem nenhuma das colunas de linha rende `absent` ("linha: sem leitura"); com `support_line_sol` nulo
  rende `untraceable` com o `line_reason` (ou "motivo não informado"); com valor rende `traced`.
- **Máxima da janela anterior** = `high_15m_sol` da linha de features anterior à mais recente
  (a de `breakout_15m` compara contra a janela anterior, sem o minuto atual). Só uma linha de
  features → "sem janela anterior", sem linha desenhada.
- **Reta de suporte** desenhada de `max(início do gráfico, end_time − 15 min)` até o fim do gráfico
  ("projetada até agora"): `y(t) = support_line_sol + support_line_slope × (t − end_time)/1 min`.
- Cores: suporte verde só quando `higher_lows = true` (estrutura positiva com significado), cinza
  caso contrário; máxima anterior `info` tracejada; rompimento = círculo verde no minuto. Nada de
  dourado no gráfico (DESIGN.md §2).
- Rótulos com fallback textual para valor não previsto (nunca lança em produção) **e** teste de
  exaustividade sobre o vocabulário do contrato.

## Arquivos

**Novos** — `apps/web/components/meme/meme-lines.ts` (puro, 275 linhas), `meme-curve-lines.tsx`
(camada SVG + legenda), `meme-features-line-cells.tsx` (células Suporte/Fundos/Rompimento/Hype),
`apps/web/components/meme-desk/bet-leg.tsx` (badge da perna + âncora `#bet-<id>`),
`apps/web/tests/meme-lines.test.ts` (32 testes), `apps/web/tests/meme-lines-render.test.tsx` (11).
**Modificados** — `components/meme/labels.ts` (`MemeLineReason`/`MemeHypeReason`, textos
"linha: sem leitura", "linha ainda não traçável: …", "sem hype: …"), `meme-curve-chart.tsx`
(`features` prop, `markY`, `overflow-hidden`, camada e legenda), `meme-features-table.tsx` (4 colunas),
`components/meme-desk/labels.ts` (`betLegLabel`), `open-bets-section.tsx` e `closed-today-section.tsx`
(badge, `id` de âncora, `knownBetIds`), `lib/api/meme-desk-types.ts` (`MemeBetLeg`, `readBetLeg`),
`app/(app)/[orgSlug]/meme/[mint]/page.tsx` (passa `features` ao gráfico), `meme/mesa/page.tsx`
(`knownBetIds`), `tests/meme-labels.test.ts`, `tests/meme-desk-labels.test.ts`.

## Comandos e saídas reais

```
$ npx vitest run tests/meme-labels.test.ts tests/meme-desk-labels.test.ts tests/meme-lines.test.ts tests/meme-lines-render.test.tsx
Test Files 4 failed (4) · Tests 6 failed | 17 passed      ← antes (TypeError: memeLineReasonLabel is not a function etc.)
$ npx vitest run tests/meme-labels.test.ts tests/meme-desk-labels.test.ts tests/meme-lines.test.ts
Test Files 3 passed (3) · Tests 48 passed (48)            ← após rótulos + meme-lines.ts
$ npx vitest run tests/meme                                (todos os 13 arquivos meme*)
Test Files 13 passed (13) · Tests 187 passed (187)
$ npx turbo run typecheck lint --filter=@hunter/web
Tasks: 2 successful, 2 total · tsc --noEmit limpo · eslint: 0 errors, 3 warnings
  → 1 aviso meu (complexity 18 em CurveLinesLayer) corrigido em seguida (três subcomponentes);
    os outros 2 são pré-existentes (tests/lab-page.test.tsx 377 linhas, tests/ws.test.ts 557)
$ npx eslint components/meme components/meme-desk lib/api/meme-desk-types.ts "app/(app)/[orgSlug]/meme" tests/meme-l*.test.ts* tests/meme-labels.test.ts tests/meme-desk-labels.test.ts
(sem saída, exit 0) — todos os arquivos tocados ≤ 275 linhas
$ npx vitest run tests/meme-lines-render.test.tsx tests/meme-lines.test.ts tests/meme-curve-chart.test.ts
Test Files 3 passed (3) · Tests 41 passed (41)            ← após a refatoração da camada
$ cd apps/web && npx next build
✓ Compiled successfully in 10.2s · Linting and checking validity of types ... · ✓ Generating static pages (6/6)
  ⚠ EPERM: operation not permitted, symlink … .next/standalone … → o KNOWN ISSUE #0 do CLAUDE.md
  (saída standalone no Windows sem Developer Mode; compilação e tipos passaram; CI/Linux não afeta)
$ pnpm gen:types                                           (14:05 UTC = 11:05 BRT)
openapi-typescript 7.13.0 · packages/shared-types/openapi.json → src/generated/api.d.ts [435.4ms]
$ git status --porcelain -- packages/shared-types           → vazio (gerado idêntico ao commitado)
$ grep -c "line_reason\|hype_score\|parent_bet_id" packages/shared-types/src/generated/api.d.ts → 0
  → a Parte A ainda não pousou; o build acima é contra o contrato SEM os campos (caminho "sem leitura")
```

## `git status --porcelain -- apps/web` (14:06 UTC = 11:06 BRT; `packages/shared-types` vazio)

```text
 M apps/web/app/(app)/[orgSlug]/meme/[mint]/page.tsx
 M apps/web/app/(app)/[orgSlug]/meme/mesa/page.tsx
 M apps/web/components/meme-desk/closed-today-section.tsx
 M apps/web/components/meme-desk/labels.ts
 M apps/web/components/meme-desk/open-bets-section.tsx
 M apps/web/components/meme/labels.ts
 M apps/web/components/meme/meme-curve-chart.tsx
 M apps/web/components/meme/meme-features-table.tsx
 M apps/web/lib/api/meme-desk-types.ts
 M apps/web/tests/meme-desk-labels.test.ts
 M apps/web/tests/meme-labels.test.ts
?? apps/web/components/meme-desk/bet-leg.tsx
?? apps/web/components/meme/meme-curve-lines.tsx
?? apps/web/components/meme/meme-features-line-cells.tsx
?? apps/web/components/meme/meme-lines.ts
?? apps/web/tests/meme-lines-render.test.tsx
?? apps/web/tests/meme-lines.test.ts
```

Fim da execução: ~11:06 BRT.

## Pendências / preocupações

1. **A Parte A não pousou durante esta execução** (`schemas/meme.py` e `meme_desk.py` sem `line_reason`,
   `hype_score`, `leg`, `parent_bet_id` às 11:05 BRT). Tudo aqui lê por chave; quando os campos chegarem,
   o orquestrador deve rodar `pnpm gen:types` + `npx turbo run typecheck lint --filter=@hunter/web` +
   `npx vitest run tests/meme` de novo. Risco conhecido: se o Pydantic gerar os campos como
   **obrigatórios** (sem default), os fixtures `feature()`/`bet()` dos testes precisam ganhá-los —
   é erro de typecheck, não de comportamento.
2. **Caminho "traçado" nunca visto com dado real** — só com fixtures (vitest/jsdom). Sem servidor de
   desenvolvimento (regra do brief), sem checagem visual no navegador. Quem tiver a sessão Playwright
   logada deve abrir `/meme/{mint}` de uma moeda com ≥ 5 min de fotografias após o deploy da Parte A.
3. **Máxima da janela anterior** vem da linha de features anterior à mais recente. Se a série tiver
   um buraco (minuto sem fold), "anterior" é o último minuto existente, não necessariamente
   `end_time − 1 min` — a legenda diz "janela anterior", não "minuto anterior", de propósito.
4. `next build` só falha no `EPERM symlink` da saída standalone (Windows sem Developer Mode), como em
   toda execução anterior; "Compiled successfully" + tipos + 6 páginas estáticas passaram.
5. `distance_to_support_pct` renderiza como percentual com sinal (`+30.00%`) — a contract diz
   `(mcap − suporte)/suporte`, fração; `formatPct` escala 0..1 → %. Se a Parte A gravar já em pontos
   percentuais, a coluna mostra 100× o valor — decidido por leitura literal do contrato ("numeric(9,6)",
   mesma escala de `curve_progress_pct`).
6. Astra não consultada (`SendMessage` desabilitado); a revisão do diff foi minha.
