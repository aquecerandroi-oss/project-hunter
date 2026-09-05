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
| `--color-fg-subtle` | `#828282` | placeholders, metadados (idades, código de exchange, rótulos de snapshot -- ver DESIGN-2) |
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
| `--color-fg-subtle` | `#666666` |
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

- **Dourado é raro.** Marca, uma ação primária por tela, item de navegação ativo, anel de foco. Nunca em texto corrido, nunca em fundos grandes, **nunca nos candles** (verdes/vermelhos -- T1.5b joint decision #3: dourado nos dois eixos de um gráfico inteiro dominaria a tela).
- **Verde e vermelho só com significado.** Long/short, PnL, status saudável/erro, candle de alta/baixa. Nunca para destacar botões neutros. Uma variação ausente é neutra (`fg-muted`), nunca colorida como se fosse positiva.
- **Preto como base, não como caixa preta.** Três níveis de fundo (`bg`, `bg-elevated`, `bg-overlay`) dão profundidade sem sombras pesadas. Bordas de 1px, sem gradientes decorativos, exceto um brilho dourado sutil permitido no logotipo e no cabeçalho do dashboard.
- **Números em `tabular-nums`**, alinhados à direita, com sinal explícito (`+1,23%`, `−0,45%`) e cor semântica. Preço nunca é arredondado além da precisão que a API já mandou (o contrato atual não expõe tick size por instrumento -- a string decimal recebida É a precisão correta a mostrar).
- **Menos chips por célula.** Preço com o maior contraste da linha; variação em segundo nível; bid/ask/spread/volume são colunas secundárias (ocultas no mobile). Volume compacto (`12.3M`) sempre com o ativo de cotação explícito ao lado -- o universo mistura USDT/USDC/BUSD, então um cabeçalho de coluna fixo mentiria para as linhas fora do padrão.
- **Densidade.** Grade de 4px, 8px entre grupos. Escala de 5 tamanhos: `12` labels/eyebrows, `14` texto, `16` texto de destaque, `20` títulos de seção, `28` números grandes (preço no detalhe do mercado). **Exceção documentada:** o corpo da tabela de mercados usa `13px` (`markets-table.tsx`), meio degrau abaixo do `14`, para caber as colunas numéricas na largura útil sem truncar — decisão do orquestrador em 2026-09-05, mantida conscientemente em vez de forçar `14` e perder colunas. Tabelas com **40px** de altura de linha no modo confortável e **32px** no compacto (`hooks/useDensity.ts`'s `useRowHeight()` -- a mesma constante alimenta a virtualização E a altura inline de cada linha, nunca dois números que podem divergir). **Outras exceções nomeadas** (T1.5b fix pass 2, honestidade sobre o que a interface realmente usa em vez de uma regra que ela não obedece): `11px` no código de exchange ao lado do símbolo (`market-row.tsx`, metadado secundário, mesmo nível de importância do `fg-subtle`); `10px` na dica de atalho `Ctrl K` do command palette (`command-palette.tsx`); `18px` nos títulos de seção da página de pré-visualização de design, `/_design`, dev-only e fora de produção (`design-preview.tsx`). Nenhuma delas vira precedente -- um componente novo usa a escala de 5, não esses três tamanhos.
- **Tipografia.** Duas famílias, nunca três: `Inter` (ou stack do sistema) para UI e texto; `JetBrains Mono` (ou `ui-monospace`) para **todo** número, id e código, em qualquer tamanho -- inclusive o preço de 28px. Não existe uma terceira fonte "de exibição" só para números grandes: o número grande é o mesmo mono, maior.
- **Movimento (calmo por padrão).** Transições de 120–200ms em hover/foco. Preço: o **fundo** da célula pisca verde/vermelho (nunca a cor do texto) só quando o valor muda de fato, no máximo 1x a cada 2s por linha, desligável (`hooks/usePriceFlash.ts`, persistido em `localStorage`). Shimmer só no primeiro carregamento. **Sem pulso** em conexão saudável -- um ponto de status muda de cor, não pisca. Idades sempre em segundos/minutos/horas (`há 3 s`, `2 min`, `1 h`), nunca em milissegundos. Transições de página: nenhuma. Tudo respeita `prefers-reduced-motion` (`hooks/usePrefersReducedMotion.ts`) além do próprio botão de desligar.
- **Staleness sem alarme falso.** Três fatos distintos, nunca fundidos em um: **snapshot** (book/trades do detalhe do mercado são uma foto tirada no load, rotulada "Snapshot · há N s", nunca uma fita "ao vivo"), **conexão** (o socket do navegador para o gateway -- `CONNECTED`/`RECONNECTING`/`DOWN`) e **frescor por componente** (idade de ticker/book/mark/funding/OI contra o `stale_after_ms` da própria API). "Sem verificação" (o check em si não rodou, ex.: `/ready` sem `API_URL`) é um quarto estado, diferente de "Indisponível" (rodou e falhou) e de "Atrasado" (rodou, está velho) -- nunca colapsados no mesmo rótulo/cor.
- **Estados vazios são honestos e separados, e distinguem dois casos diferentes** (T1.5b fix pass 2 -- a regra antiga só cobria o segundo caso, e um empty state do primeiro caso que inventasse um milestone estaria mentindo sobre por que o dado falta):
  - **Ausência operacional:** a funcionalidade já existe e está implementada; só não há dado agora, por um motivo real e atual (universo vazio, nada aconteceu ainda na janela, uma leitura falhou). O texto diz o que falta e por quê -- nunca inventa ou empresta um milestone futuro que não é o motivo real. Exemplos já no código: "Nenhum mercado monitorado ainda" + link para System → Workers (`markets-empty.tsx`, redigido como algo a verificar, nunca afirma que o worker parou); "Nenhum trade recente." vs. "Trades indisponíveis: falha ao ler o estado em tempo real (Redis)." -- duas mensagens distintas para "nada aconteceu" e "a leitura falhou" (`recent-trades.tsx`); "Sem candles ainda para este mercado." vs. "Gráfico indisponível [...] recarregue a página" -- dado chegou mas a lib de gráfico falhou (`candles-chart.tsx`).
  - **Não construído ainda:** a funcionalidade em si não existe no produto hoje. O texto nomeia o milestone real que a traz (histórico em §5, ex.: sparklines por linha adiadas para o M2 por o endpoint agregado ainda não existir), nunca fingindo que é apenas um caso de ausência operacional.
  - Dentro do caso de ausência operacional, "Nenhum resultado" (busca sem match) ≠ "Nenhum mercado monitorado" (universo vazio) ≠ "Falha ao carregar" (com botão de tentar de novo) continuam três mensagens distintas, nunca fundidas numa só. Sem ilustrações que fingem dados.
- **Sem promessas que os dados não sustentam.** Se o contrato não tem index price, horário do próximo funding ou uma fita de trades que realmente atualiza sozinha, a UI não finge que tem -- cada card diz sua própria natureza e idade.

## 3. Componentes-âncora

- **Sidebar:** fundo `bg-elevated`, item ativo com barra dourada de 2px à esquerda e texto `fg`; itens planejados em `fg-subtle` com badge "Planejado (Mx)".
- **Topbar:** logotipo HUNTER em dourado, nome da organização em `fg`, indicador de estado do sistema (ponto verde/âmbar/vermelho/cinza-`fg-subtle` para "sem verificação") ligado ao `/ready` (`components/layout/topbar.tsx`'s `dotState`, reexportado para `components/dashboard/system-health-line.tsx`), botão visível "Buscar mercados" (Ctrl/⌘K) abrindo o command palette.
- **Command palette** (`components/layout/command-palette.tsx`): Radix Dialog centralizado, busca real via Server Action (`lib/api/markets-actions.ts`'s `searchMarketsAction`, `GET /api/v1/markets?q=`), resultados com símbolo + exchange, navegação por setas/Enter, copy explícita de que a busca cobre o universo monitorado.
- **Cards KPI:** título em `fg-muted` 12px maiúsculas, valor em 28px `tabular-nums`, variação com cor semântica e seta; borda `border`, hover eleva para `border-strong`.
- **Botão primário:** fundo `gold`, texto `gold-fg`, hover `gold-strong`; secundário: borda `border-strong`, texto `fg`; destrutivo: `red`.
- **Badges de status:** `NORMAL` cinza, `WATCHING` info, `ANOMALY` âmbar, `HOT` dourado, `ENTRY_CANDIDATE` verde, `BLOCKED_BY_RISK` vermelho.
- **Quality badge** (`components/markets/quality-badge.tsx`): `OK` verde, `atrasado há Ns` âmbar, `gap` vermelho, `sem dado` cinza neutro -- vocabulário de qualidade POR COMPONENTE, nunca reduzido a um único "conectado"/"desconectado".
- **Gráfico de candles** (`components/markets/candles-chart.tsx`): candles verdes (alta) / vermelhos (baixa) sobre o fundo escuro -- dourado reservado para marca/ação/ativo/foco em outras partes da tela, nunca no próprio gráfico.
- **Markets table** (`components/markets/markets-table.tsx` + `market-row.tsx`): colunas essenciais (símbolo, status/qualidade, preço, variação 24h) sempre visíveis; bid/ask/spread/volume ocultos abaixo de `md`. Navegação por teclado (setas movem a seleção, Enter abre o detalhe, `/` foca a busca); seleção ativa marcada com `ring-gold` (foco é um dos usos permitidos do dourado).
- **Kill switch:** botão vermelho com confirmação em duas etapas; estado `EMERGENCY` tinge a topbar de `red-soft`.

## 4. Página de pré-visualização (desenvolvimento)

`apps/web/app/_design/page.tsx` renderiza tokens e componentes-âncora nos dois temas para revisão visual. Retorna 404 em produção (`HUNTER_ENV`/`NODE_ENV`) e não aparece na navegação. É ferramenta de design, não feature.

## 5. Histórico

- 2026-09-04 — direção inicial (dourado/verde/preto/branco) definida pelo produto; aplicada no M0 após T09.
- 2026-09-04 — DESIGN-1: `--color-gold` do tema claro ajustado de `#B8860B` para `#8A6D00` (e `--color-gold-strong` de `#9A7009` para `#6E5700`). `#B8860B` sobre branco (e como fundo com texto `gold-fg` branco) mede 3.25:1, abaixo do mínimo AA de 4.5:1; `#8A6D00` mede 4.92:1 nos dois pares. Verificado em `apps/web/tests/theme-contrast.test.ts`.
- 2026-09-05 — T1.5b ("lindo demais"): decisão conjunta Claude ⇄ Astra (`.claude/state/astra-review-design-T1.5b.md`, `.claude/state/brief-T1.5b-ux.md`) prevalece sobre a direção original onde diferem -- hierarquia, estabilidade e clareza sobre os dados, não mais elementos. Mudanças aplicadas: candles verdes/vermelhos (dourado deixa de aparecer no gráfico); dashboard reordenado (Mercados/cobertura primeiro, saúde em uma linha, sem cards financeiros placeholder); `topbar.tsx` ganha um quarto estado "sem verificação" distinto de "indisponível"; book/trades do detalhe do mercado rotulados "Snapshot · há N s"; sparklines por linha adiadas para o M2 (endpoint agregado ainda não existe); densidade de tabela passa a 40px (confortável) / 32px (compacto) com `hooks/useDensity.ts` alimentando tanto o CSS quanto a virtualização; flash de preço calmo (fundo, 1x/2s, desligável, `hooks/usePriceFlash.ts`); sem pulso em conexão saudável; idades em segundos; horários de trades em UTC com offset local visível (`lib/format.ts`'s `formatUtcWithOffset`); command palette com botão visível "Buscar mercados" (`components/layout/command-palette.tsx`); mobile mostra símbolo/preço/variação/qualidade, esconde bid/ask/spread/volume.
- 2026-09-05 — DESIGN-2 (valor final do tema claro corrigido logo em seguida por DESIGN-3, abaixo): `--color-fg-subtle` ajustado (dark `#6B6B6B` → `#828282`; light `#8A8A8A` → `#737373`) -- o token rotula idades, código de exchange e labels de snapshot (informação real, não só metadados decorativos), mas media apenas 3.72:1/3.54:1 (dark, contra `bg`/`bg-elevated`) e 3.45:1 (light, contra `bg`), abaixo do mínimo AA de 4.5:1. Os novos valores medem >= 4.5:1 nos mesmos pares. Verificado em `apps/web/tests/theme-contrast.test.ts`.
- 2026-09-05 — DESIGN-3 (revisão de design da Astra sobre o próprio diff do T1.5b): DESIGN-2 só verificou `fg-subtle` contra `bg`/`bg-elevated` -- contra `bg-overlay` (`#F3F3F3` no tema claro) o `#737373` media 4.27:1, ainda abaixo de AA. Ajustado para `#666666` (5.10:1 em `bg`, 4.60:1 em `bg-overlay`). O command palette também parou de usar `fg-subtle` para o código de exchange na linha selecionada (fundo `gold-soft`), onde media só 3.47:1 (escuro) / 4.33:1 (claro) -- passou a usar `fg-muted`, que mede >= 5.28:1 nesse par nos dois temas.
- 2026-09-05 — DESIGN-4 (honestidade da própria doc, T1.5b fix pass 2, Astra): §2 documentava só a escala de 5 tamanhos + a exceção de `13px` da tabela, mas a interface já usa `11px` (código de exchange, `market-row.tsx`), `10px` (dica de atalho do command palette) e `18px` (títulos de seção do `/_design`, dev-only) sem que a doc os reconhecesse -- agora nomeados como as exceções que são, para o próximo componente não seguir uma regra que a própria interface não obedece. A regra de estados vazios também foi corrigida: dizia que todo empty state nomeia um milestone, mas `markets-empty.tsx`, `recent-trades.tsx` e `candles-chart.tsx` são ausência operacional (a funcionalidade já existe, só falta o dado agora) e corretamente nunca inventaram um milestone -- a regra agora distingue ausência operacional (diz o que falta e por quê) de não-construído-ainda (nomeia o milestone, como as sparklines do T1.5b acima).
