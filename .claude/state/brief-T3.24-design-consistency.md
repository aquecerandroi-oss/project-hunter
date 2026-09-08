# Brief T3.24c — consistência transversal (a mesma coisa igual em toda tela)

**Owner:** frontend-specialist. **Revisor:** product-designer (diff + telas renderizadas), Sexta-feira (copy). **Pré-requisito:** T3.24a. **Decisões pendentes que mudam o escopo:** D1 (idioma dos nomes de página) e D2 (convenção numérica) — se o Everton decidir antes do dispatch, entram aqui (§5); senão ficam de fora e o brief não as inventa. **Base:** `main` ≥ T3.24a. **Regras:** não commitar; foreground ≤ 5 min; sem testcontainers; nunca `.env*`; árvore compartilhada. Escopo: `apps/web/components/{time,layout,radar,portfolio,system,markets,dashboard}/**`, `apps/web/lib/format.ts`, `apps/web/lib/time.ts`, `apps/web/hooks/useAgeTicker.ts`, `apps/web/lib/nav-registry.ts`. Lab só nos re-exports de `lab-as-of.tsx` (T3.24b cuida do resto).

## 1. Vocabulário de tempo (relatório X3, X9; DESIGN-5)

Três rótulos e um componente:

| Fato | Rótulo | Onde |
|---|---|---|
| Quando o servidor leu (`as_of` de página/seção) | **Consultado em** `dd/mm/aaaa hh:mm:ss` (`BrasiliaInstant`, `title` = ISO UTC) | Radar ("Painel consultado" → "Consultado em"; "anomalias verificadas" → "anomalias consultadas em"), Lab (`LabHeader` "Estado em" → "Consultado em"), Carteira (4×, mesma capitalização), Lab curva/equity ("consultado em" → "Consultado em") |
| Idade de um dado que envelhece | **Atualizado há** `N s` / `N min` / `N h` (com espaço) | Radar `QualityCell`, Markets `AsOf`/`AgeSuffix`, System `AgeWithAsOf` ("há Xs (<t>)" → "Atualizado há X s · <t>"), workers `AgeCell` |
| Foto tirada no load | **Snapshot · há** `N s` | book/trades (já) |

- `hooks/useAgeTicker.ts` `formatAge`: `12s`→`12 s`, `3min`→`3 min`, `2h`→`2 h` (contrato §2). Atualizar `tests/useAgeTicker.test.ts` e todo teste que compara a string.
- `components/time/brasilia-instant.tsx` é o único componente; `components/lab/lab-as-of.tsx`, `portfolio/portfolio-as-of.tsx`, `system/system-as-of.tsx` viram `export { BrasiliaInstant as LabAsOf }` (etc.) para não quebrar imports, com docstring de uma linha apontando o motivo; remover a duplicação de docstring.
- Placeholder único de ausência: `--` (Radar `—` e workers/live-status `?` → `--`).

## 2. Títulos de seção e erro de seção (X2, S2, S3, L9)

- Um idioma: título de página `h1 text-xl font-semibold text-fg`; título de seção/card = **eyebrow** `h2 text-xs font-medium uppercase tracking-wide text-fg-muted`; subtítulo dentro do card `h3 text-sm font-semibold text-fg`. Migrar `portfolio-header.tsx` (nome da carteira vira `h2` eyebrow "Carteira principal" + nome em `text-xl`), `portfolio-result-card.tsx`/`risk-card.tsx`/`activity-tables.tsx`/`equity-chart.tsx` (`h3 text-sm` → eyebrow `h2`), `execution-paper-card.tsx` (`h3` → eyebrow), Radar sem seção nomeada (ok), Markets detalhe (já eyebrow).
- Erro de seção: todo `Indisponível: {reason}` usa `ui/section-unavailable.tsx` (T3.24a) — Dashboard `EmptyStateCard` de erro, Carteira (`PortfolioError` fica: é erro de página), System (já em T3.24a).

## 3. Foco e controles (X6)

- `components/layout/nav-links.tsx`: já em T3.24a. Aqui: `components/layout/theme-toggle.tsx`, `command-palette.tsx` (botão e resultados), `sidebar.tsx` (botão recolher) — conferir que todos usam `Button` (anel dourado) e que a linha selecionada do palette tem `aria-selected` + `ring-gold`.
- Tabelas: `components/portfolio/portfolio-activity-tables.tsx` passam a `text-[13px]`, `thead` `bg-bg-overlay text-xs text-fg-muted h-8`, linhas com `style={{ height: rowHeight }}` de `useRowHeight()` (client) — mesma densidade das tabelas virtualizadas (§2 40/32px). Sem virtualização (vazias por contrato).

## 4. Radar: linha legível (R2, R3, R4; PR-7)

- `components/radar/radar-row.tsx`: célula `Mercado` = símbolo (link) + exchange 11px + **uma** linha de chips em ordem fixa `StatusChip · StageChip · RegimeChip` (rótulos pt de T3.24a); "Em posição"/"Bloqueado (risco)" viram ícone (`lucide` `briefcase`/`shield-alert`, `size-3.5`, com `title` e `sr-only`). Colunas `Status`, `Estágio`, `Regime` **saem** do `RADAR_TABLE_HEADERS`; `Score` (valor 14px mono + delta 12px com " pts"), `Confiança` (badge + "Atualizado há"), `Anomalias` (md+), `Idade` (md+). Abaixo de `md`: Mercado + Score + Confiança.
- `components/radar/radar-filters.tsx`: botão `outline sm` "Aplicar" que chama `navigate` com o estado local (campos deixam de navegar no `onBlur`); `aria-busy` na caixa enquanto `useTransition` pendente; rótulos com unidade (T3.24a).
- Nota de paginação (11px, duas linhas) → 12px `fg-muted`, uma frase: "Ranking em movimento: uma oportunidade pode mudar de página entre um carregamento e outro."

## 5. Só com decisão do Everton

- **D1 (idioma):** `lib/nav-registry.ts` labels + `h1` de `dashboard`, `markets`, `opportunities`, `system`, `settings/*`, `trades` (planejado) conforme a opção escolhida; `docs/PRODUCT.md` §4 tabela; testes de nav (`nav-registry.test.ts`, `signup-onboarding.spec.ts` procura "Dashboard").
- **D2 (números):** se A (pt-BR): `lib/format.ts` `formatUsdt`/`formatMoney` com `locale: "pt-BR"` e junção `,` (mesmo caminho decimal-seguro de `formatBrl`), `formatPct` `pt-BR`, `formatCompact` `pt-BR` ("12,3 mi" → decidir "12,3M" para caber na coluna); atualizar `tests/format.test.ts`, os testes do Lab/Carteira que comparam strings e o contrato §2. Se B: `docs/DESIGN.md` §2 passa a dizer "USDT e % como a exchange (en-US); BRL pt-BR" e nada muda no código.

## 6. Shell (X8)

- `components/layout/sidebar.tsx`: remover o texto "Hunter" do topo (o logotipo dourado já está na topbar); o botão recolher fica sozinho à direita.
- `components/layout/topbar.tsx`: mostrar `organization.name` (já vem em `resolveOrgContext`) em vez do slug; slug em `title`.

## Aceite

- `pnpm --filter web lint|typecheck|test` verdes; nenhum teste removido.
- Testes novos: `tests/time-vocabulary.test.tsx` (grep no render de Radar/Carteira/System por "Consultado em"/"Atualizado há"/"Snapshot · há" e ausência de "Painel consultado", "Estado em", "consultado em" minúsculo); `formatAge` com espaço; `radar-row.test.tsx` (3 chips na célula Mercado, 5 colunas no header, ícones com `sr-only`); `radar-filters.test.tsx` (só navega no "Aplicar"); `portfolio-activity-tables.test.tsx` (13px, `thead` overlay, altura da linha = `useRowHeight`).
- `grep -rn -E "text-lg|<h3 className=\"text-sm font-semibold" apps/web/components/{portfolio,system,dashboard}` vazio; `grep -rn "Painel consultado\|Estado em \|consultado em" apps/web/components` vazio (exceto "Consultado em").
- Tela real (product-designer, spec `design-audit`): Radar 375 sem rolagem horizontal no grid (`overflowers` vazio); os três rótulos de tempo idênticos em Radar/Lab/Carteira/System nas capturas; `text-*.txt` de cada tela sem `_` em texto visível fora de `<pre>`.
- `docs/DESIGN.md` §3 ganha "Títulos: eyebrow 12px para seção/card, 20px para página" e "Radar row" como âncora; §5 uma linha DESIGN-6 com o que mudou e por quê.
