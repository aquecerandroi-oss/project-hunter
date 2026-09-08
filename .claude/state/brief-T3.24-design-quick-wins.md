# Brief T3.24a — design quick wins (um dia, sem mudança de direção)

**Owner:** frontend-specialist. **Revisor do diff e da tela renderizada:** product-designer (antes do commit). **Origem:** `.claude/state/review-design-2026-09-08.md` (C1–C7, X1, X5, X6, X9, X10, R1/R4/R6, P1/P2, S1/S2, M1/M2, L3) e `docs/DESIGN.md` §5 DESIGN-5. **Base:** `main` ≥ `79c52c3`. **Não commitar; foreground, timeout ≤ 5 min; sem testcontainers; nunca `.env*`; árvore compartilhada (sem stash/checkout --/restore/reset/clean/commit -a).** Não tocar `apps/web/components/lab/**` (é o brief T3.24b) nem `lib/format.ts`/`lib/time.ts` (T3.24c), exceto onde este brief nomeia o arquivo.

## 1. Tokens (`apps/web/app/globals.css` + `docs/DESIGN.md` §1)

Adicionar aos dois temas e à tabela §1 (com a linha de histórico já escrita em DESIGN-5):

| Token | Escuro | Claro | Uso |
|---|---|---|---|
| `--color-warning-soft` | `#2E1F06` | `#FEF3C7` | fundo de badge âmbar |
| `--color-info-soft` | `#0F1F33` | `#DBEAFE` | fundo de badge info |
| `--color-border-input` | `#666666` | `#8A8A8A` | contorno de campo de formulário (≥ 3:1 sobre `bg`/`bg-overlay`) |

Ajustar no tema claro: `--color-gold` `#8A6D00` → `#7F6400`, `--color-gold-strong` `#6E5700` → `#665000`, `--color-warning` `#B45309` → `#A34A05`. Atualizar a tabela §1 do `docs/DESIGN.md` com os três valores e a nota do dourado (DESIGN-1 → DESIGN-5).

## 2. Componentes compartilhados

- `components/ui/badge.tsx`: `positive` → `border-transparent bg-green-soft text-green`; `negative` → `bg-red-soft text-red`; `warning` → `bg-warning-soft text-warning`; `info` → `bg-info-soft text-info`. `components/lab/lab-result-badge.tsx` usa as mesmas classes (é o único fora do `Badge` com `/15` — pode ser tocado só nessas duas linhas).
- `components/ui/button.tsx`: `destructive: "bg-red text-bg hover:bg-red/90"`.
- `components/layout/nav-links.tsx`: remover `opacity-60` do item planejado.
- Campos: criar `components/ui/input.tsx` e `components/ui/select.tsx` (shadcn base) com `h-8 rounded-md border border-border-input bg-bg px-2 text-[13px] text-fg placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-offset-2 focus-visible:ring-offset-bg` e `components/ui/checkbox.tsx` (Radix) com o mesmo anel; trocar os `<input>`/`<select>`/checkbox nativos em `components/radar/radar-filters.tsx` e a busca de `components/markets/markets-table.tsx` (o Lab fica para T3.24b). `nav-links.tsx`: `<Link>` ganha `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-inset`.
- `components/ui/section-unavailable.tsx` (novo): caixa `rounded-lg border border-dashed border-red/40 bg-bg-elevated p-4` com "{title} indisponível: {reason}" e botão `outline sm` "Tentar novamente" (`router.refresh()`), usada por `app/(app)/[orgSlug]/system/page.tsx` (`UnavailableSection` e "Workers indisponível").

## 3. Estados de rota (`app/(app)/[orgSlug]/loading.tsx`, `error.tsx`)

- `loading.tsx`: esqueleto (h1 `h-7 w-40 rounded bg-bg-overlay` + 3 caixas `h-24 rounded-lg border border-border bg-bg-elevated`), classe `animate-pulse` **só** quando `!prefers-reduced-motion` (a regra global de `globals.css` já zera a animação) — sem texto.
- `error.tsx` (`"use client"`): caixa tracejada `border-red/40`, "Esta tela falhou ao renderizar: {error.message}", botão "Tentar novamente" (`reset()`), link "Ver System" para `/{orgSlug}/system`. Português, sem stack trace.

## 4. Escala tipográfica (DESIGN-5)

- `text-[10px]` → `text-[11px]` em `components/markets/quality-badge.tsx` (hint "relógio local"), `components/markets/recent-trades.tsx` (glyph C/V), `components/opportunities/why-footer.tsx` e `why-history.tsx` (`<pre>`). `command-palette.tsx` (`kbd`) fica.
- `text-lg` → `text-xl` em `components/portfolio/portfolio-header.tsx` (nome da carteira), `components/dashboard/organization-card.tsx`, `workspace-card.tsx`, `components/opportunities/why-panel.tsx`, `components/invitations/accept-invite-card.tsx`; os `h2` do onboarding também. (Lab em T3.24b.)
- `components/design/typography-scale.tsx`: mostrar os 7 degraus (11/12/13/14/16/20/24/28) com o nome de cada um.

## 5. Copy (dicionários; sem mudança de layout)

- Novo `components/radar/labels.ts`: `STATUS_LABEL`, `STAGE_LABEL`, `REGIME_LABEL`, `ANOMALY_TYPE_LABEL` (uma entrada por membro de `RADAR_STATUS_VALUES`, `OPPORTUNITY_STAGE_VALUES`, `MARKET_REGIME_VALUES`, `ANOMALY_TYPE_VALUES` em `lib/api/radar-types.ts` — o teste falha se faltar membro). Usar em `status-chip.tsx`, `radar-filters.tsx` (`<option>` e checkboxes) e `anomaly-count-cell.tsx`. Rótulos: Normal / Observando / Anomalia / Quente / Candidato a entrada / Esticado / Expirado / Em posição / Bloqueado (risco); Início / Em desenvolvimento / Esticado; Alta / Baixa / Lateral / Volátil / Sem classificação; anomalias: escrever em português plano a partir do nome do enum (ex.: `volume_spike` → "Pico de volume"), conferindo cada um com `docs/PIPELINE.md`. Cabeçalho "Score" → "Score" fica (termo do produto), delta ganha sufixo " pts"; filtro "Score mínimo (0–100)", "Volatilidade mín. (%)"/"máx. (%)"; `—` → `--` na idade.
- Novo `components/portfolio/labels.ts`: direção (`long`→Comprado, `short`→Vendido), lado (`buy`→Compra, `sell`→Venda), tipo/propósito/modo/status de ordem e de posição (todos os membros dos tipos em `lib/api/portfolio-types.ts`), escopos/estados do kill switch (reusar `killSwitchLabel`), `actor_type` (system/user/…→ Sistema/Usuário), fonte de câmbio (`binance.spot.ticker` → "Binance spot (ticker)"). Usar em `portfolio-activity-tables.tsx`, `portfolio-header.tsx` (badges `type`/`status`, com rótulo "Tipo · Status"), `portfolio-risk-card.tsx` (3 escopos, transição, ator), `portfolio-result-card.tsx` (fonte). Copy: `PortfolioProposalsEmpty` → "Ainda sem propostas — o serviço de admissão, que registra os checks e o limitante vencedor de cada decisão, chega no M3."; `PortfolioEmpty` → sem "ADR 0005", comando dentro de `<details><summary>Para o operador</summary>`; rodapé do `PortfolioRiskCard` → "Os limites numéricos do preset paper (risco por operação, exposição, participação) ainda não aparecem nesta tela."
- Novo `components/system/labels.ts`: papel (market→Mercados, scanner→Scanner, strategy→Estratégias, execution→Execução), status (alive→vivo, late→atrasado, dead→morto), `Ready`/`Not Ready` → "Pronto"/"Não pronto", cabeçalhos "Papel"/"Instância"/"Status"; título da página "System" só muda se D1 for decidido (ver relatório).
- Markets: cabeçalho "Status" → "Qualidade" (`markets-table-head.tsx`); `order-book.tsx` "Bids/Asks" → "Compras/Vendas"; `derivatives-card.tsx` `fundingKind` → "estimado"/"realizado".
- Lab (única linha deste brief no Lab): `LAB_TOTALS_SCOPE_NOTE` em `components/lab/lab-money.ts` → remover a constante e o `<p>` que a usa em `lab-totals-card.tsx`.

## 6. `/_design`

`badges-showcase.tsx`, `buttons-showcase.tsx`, `inputs-showcase.tsx`: cada variante com a razão de contraste calculada por `components/design/contrast.ts` ao lado, nos dois temas; adicionar o item de sidebar "Planejado" ao `sidebar-states-showcase.tsx`.

## Aceite

- `pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test` verdes.
- `apps/web/tests/theme-contrast.test.ts` ganha, nos dois temas: `green on green-soft`, `red on red-soft`, `warning on warning-soft`, `info on info-soft`, `gold on gold-soft`, `bg on red` (destrutivo), `fg-subtle on bg-elevated` (planejado), `border-input on bg-overlay ≥ 3` e `border-input on bg ≥ 3` — todos passando com os valores acima.
- Testes novos: `tests/radar-labels.test.ts`, `tests/portfolio-labels.test.ts`, `tests/system-labels.test.ts` (todo membro do enum tem rótulo; nenhum rótulo contém `_` ou está em caixa alta); `tests/route-states.test.tsx` (`loading.tsx` renderiza sem texto; `error.tsx` mostra a mensagem e chama `reset`).
- `grep -rn "text-\[10px\]" apps/web/components apps/web/app` → só `command-palette.tsx`; `grep -rn "text-lg" apps/web/components apps/web/app --include=*.tsx | grep -v lab/` → vazio; `grep -rn -E "T3\.[0-9]+|ADR 000" apps/web/components apps/web/app --include=*.tsx | grep -v _design` → vazio.
- Tela real: product-designer abre Radar, Carteira, System, Markets nos dois temas (spec `tests/e2e/design-audit.config.ts`) e confere que nenhum badge/botão/campo mede < 4.5 (texto) / < 3 (contorno) no `metrics-*.json`.
- `docs/DESIGN.md` §1 atualizado (três tokens, três valores do tema claro) e `.claude/state/notes-T3.24a.md` com a saída real dos comandos.
