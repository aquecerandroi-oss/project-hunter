# Design — identidade visual do HUNTER

Direção dada pelo produto em 2026-09-04: **dourado** (referência ao Bitcoin), **verde**, **preto** e **branco**. Densidade de terminal (Bloomberg), limpeza de Linear, gráficos no padrão TradingView. Dark-first; tema claro obrigatório e igualmente cuidado.

## 1. Paleta (tokens)

Tokens em `apps/web/app/globals.css` (`@theme` do Tailwind 4). Nunca usar hex solto em componentes; sempre o token.

### Tema escuro (padrão)

| Token | Valor | Uso |
|---|---|---|
| `--color-bg` | `#0A0A0A` | fundo da página |
| `--color-bg-elevated` | `#111111` | cards, sidebar |
| `--color-bg-overlay` | `#161616` | popovers, sheets, linhas alternadas |
| `--color-border` | `#232323` | bordas sutis |
| `--color-border-strong` | `#2E2E2E` | bordas de foco/separadores |
| `--color-fg` | `#F5F5F5` | texto principal |
| `--color-fg-muted` | `#A3A3A3` | texto secundário, labels |
| `--color-fg-subtle` | `#6B6B6B` | placeholders, metadados |
| `--color-gold` | `#F2B705` | marca, ações primárias, item ativo, foco |
| `--color-gold-strong` | `#D99E00` | hover/pressed do dourado |
| `--color-gold-soft` | `#3A2E08` | fundo de destaque dourado (badges, seleção) |
| `--color-gold-fg` | `#0A0A0A` | texto sobre dourado |
| `--color-green` | `#22C55E` | positivo, long, PnL > 0, saudável |
| `--color-green-soft` | `#0E2A1A` | fundo de badge verde |
| `--color-red` | `#EF4444` | negativo, short, PnL < 0, erro, kill switch |
| `--color-red-soft` | `#2A0E0E` | fundo de badge vermelho |
| `--color-warning` | `#F59E0B` | atenção (WARNING do kill switch, dados atrasados) |
| `--color-info` | `#60A5FA` | informação neutra, links secundários |

O vermelho não estava na direção original, mas é obrigatório num produto financeiro: perda, short e erro precisam de um sinal distinto do verde e do dourado. Ele é usado só com significado semântico, nunca decorativo.

### Tema claro (`[data-theme="light"]`)

| Token | Valor |
|---|---|
| `--color-bg` | `#FFFFFF` |
| `--color-bg-elevated` | `#FAFAFA` |
| `--color-bg-overlay` | `#F3F3F3` |
| `--color-border` | `#E5E5E5` |
| `--color-border-strong` | `#D4D4D4` |
| `--color-fg` | `#0A0A0A` |
| `--color-fg-muted` | `#525252` |
| `--color-fg-subtle` | `#8A8A8A` |
| `--color-gold` | `#8A6D00` (dourado mais escuro para contraste AA sobre branco -- ver nota) |
| `--color-gold-strong` | `#6E5700` |
| `--color-gold-soft` | `#FFF4D6` |
| `--color-gold-fg` | `#FFFFFF` |
| `--color-green` | `#15803D` |
| `--color-green-soft` | `#DCFCE7` |
| `--color-red` | `#B91C1C` |
| `--color-red-soft` | `#FEE2E2` |
| `--color-warning` | `#B45309` |
| `--color-info` | `#1D4ED8` |

Contraste mínimo AA (4.5:1) para texto em todos os pares acima; verificar com o teste automatizado de contraste em `apps/web/tests/theme-contrast.test.ts`.

## 2. Regras de uso

- **Dourado é raro.** Uma ação primária por tela, item de navegação ativo, anel de foco, logotipo, valores-chave (score de oportunidade alto). Nunca em texto corrido, nunca em fundos grandes.
- **Verde e vermelho só com significado.** Long/short, PnL, status saudável/erro. Nunca para destacar botões neutros.
- **Preto como base, não como caixa preta.** Três níveis de fundo (`bg`, `bg-elevated`, `bg-overlay`) dão profundidade sem sombras pesadas. Bordas de 1px, sem gradientes decorativos, exceto um brilho dourado sutil permitido no logotipo e no cabeçalho do dashboard.
- **Números em `tabular-nums`**, alinhados à direita, com sinal explícito (`+1,23%`, `−0,45%`) e cor semântica.
- **Densidade.** Tabelas com 32px de altura de linha, fontes 13px no corpo de tabela, 14px em texto, 12px em labels. Espaçamento em múltiplos de 4px.
- **Tipografia.** `Inter` (ou stack do sistema) para UI; `JetBrains Mono` (ou `ui-monospace`) para números em tabelas, ids e código.
- **Movimento.** Transições de 120–160ms em hover/foco; atualização de preço pisca o fundo em `gold-soft` por 300ms (nunca a cor do texto). Sem animações decorativas.
- **Estados vazios são honestos.** Texto curto do que falta e em qual milestone chega; sem ilustrações que fingem dados.

## 3. Componentes-âncora

- **Sidebar:** fundo `bg-elevated`, item ativo com barra dourada de 2px à esquerda e texto `fg`; itens planejados em `fg-subtle` com badge "Planejado (Mx)".
- **Topbar:** logotipo HUNTER em dourado, nome da organização em `fg`, indicador de estado do sistema (ponto verde/âmbar/vermelho) ligado ao `/ready`.
- **Cards KPI:** título em `fg-muted` 12px maiúsculas, valor em 24px `tabular-nums`, variação com cor semântica e seta; borda `border`, hover eleva para `border-strong`.
- **Botão primário:** fundo `gold`, texto `gold-fg`, hover `gold-strong`; secundário: borda `border-strong`, texto `fg`; destrutivo: `red`.
- **Badges de status:** `NORMAL` cinza, `WATCHING` info, `ANOMALY` âmbar, `HOT` dourado, `ENTRY_CANDIDATE` verde, `BLOCKED_BY_RISK` vermelho.
- **Kill switch:** botão vermelho com confirmação em duas etapas; estado `EMERGENCY` tinge a topbar de `red-soft`.

## 4. Página de pré-visualização (desenvolvimento)

`apps/web/app/_design/page.tsx` renderiza tokens e componentes-âncora nos dois temas para revisão visual. Retorna 404 em produção (`HUNTER_ENV`/`NODE_ENV`) e não aparece na navegação. É ferramenta de design, não feature.

## 5. Histórico

- 2026-09-04 — direção inicial (dourado/verde/preto/branco) definida pelo produto; aplicada no M0 após T09.
- 2026-09-04 — DESIGN-1: `--color-gold` do tema claro ajustado de `#B8860B` para `#8A6D00` (e `--color-gold-strong` de `#9A7009` para `#6E5700`). `#B8860B` sobre branco (e como fundo com texto `gold-fg` branco) mede 3.25:1, abaixo do mínimo AA de 4.5:1; `#8A6D00` mede 4.92:1 nos dois pares. Verificado em `apps/web/tests/theme-contrast.test.ts`.
