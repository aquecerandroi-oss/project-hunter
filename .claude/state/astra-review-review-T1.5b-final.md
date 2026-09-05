Astra: **ainda não aprovaria o conjunto**. Considerei a [decisão conjunta, que prevalece](C:/dev/project-hunter/.claude/state/brief-T1.5b-ux.md:32), a revisão anterior, o diff e todos os 17 arquivos novos. Fiz somente leitura; não acessei `.env`, não modifiquei arquivos e não fiz commit.

**Must-fix da revisão anterior**

1. **FECHADO — “Sem verificação” no loader real.**  
   A ausência de configuração agora retorna `database_detail: READY_CHECK_NOT_CONFIGURED` em [system.ts:60](C:/dev/project-hunter/apps/web/lib/api/system.ts:60). O layout traduz esse resultado com `return wasReadyCheckAttempted(status) ? status : null` em [layout.tsx:28](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/layout.tsx:28), e `if (!status) return "unchecked"` chega ao rótulo correto em [topbar.tsx:30](C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:30).  
   **Falha anterior resolvida:** uma verificação não configurada deixa de produzir o mesmo estado de uma tentativa que falhou. Isso não fecha a questão de **“Atrasado”**, descrita abaixo.

2. **FECHADO — Enter abrindo resultado da consulta anterior.**  
   Em [command-palette.tsx:158](C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:158):
   ```tsx
   const isCurrent = search.forQuery === trimmedQuery;
   const status = isEmpty ? "idle" : isCurrent ? search.status : "loading";
   const visibleResults = isEmpty || !isCurrent ? [] : search.results;
   ```
   Enter usa `openResult(visibleResults[activeIndex])`, na linha 177.  
   **Falha anterior resolvida:** buscar BTC, trocar para ETH e imediatamente pressionar Enter não abre BTC. O debounce também passa a mostrar carregamento, sem anunciar vazio prematuramente.

3. **FECHADO — teclado da tabela interceptando controles internos.**  
   A proteção `if (event.target !== event.currentTarget) return` está em [useArrowKeyRowSelection.ts:72](C:/dev/project-hunter/apps/web/hooks/useArrowKeyRowSelection.ts:72).  
   **Falha anterior resolvida:** selecionar uma linha, tabular até um botão de ordenação e pressionar Enter preserva a ação desse botão.

4. **PARCIAL — seleção visível durante virtualização.**  
   A altura compartilhada está correta no código: `comfortable: 40, compact: 32` em [useDensity.ts:19](C:/dev/project-hunter/apps/web/hooks/useDensity.ts:19), usada nos espaçadores em [markets-table.tsx:154](C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:154) e em `style={{ height: rowHeight }}` em [market-row.tsx:37](C:/dev/project-hunter/apps/web/components/markets/market-row.tsx:37).

   **O cálculo da posição ainda está errado:**
   ```tsx
   const rowTop = index * rowHeight;
   const rowBottom = rowTop + rowHeight;
   ```
   [useArrowKeyRowSelection.ts:50](C:/dev/project-hunter/apps/web/hooks/useArrowKeyRowSelection.ts:50) não soma os 32 px do cabeçalho que precede o corpo da tabela.

   **Falha atual:** focar a grade e descer até a 12ª linha no padrão: seu fim real é `32 + 12 × 40 = 512`, mas o cálculo usa 480 e não rola. No compacto, a 15ª linha fica inteiramente abaixo do limite: começa em 480 e termina em 512.

   A referência ARIA desmontada foi evitada por `isSelectedRowRendered` em [markets-table.tsx:207](C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:207), mas a seleção interna permanece. Selecionar A, rolar manualmente até A desaparecer e pressionar Enter ainda abre A, sem seleção visível. O teste novo chega a exigir `scrollTop === -32`, sem representar a geometria real da tabela: [use-arrow-key-row-selection.test.ts:101](C:/dev/project-hunter/apps/web/tests/use-arrow-key-row-selection.test.ts:101).

5. **FECHADO — controle de flash e reset com ticks rápidos.**  
   O switch está em [appearance-form.tsx:94](C:/dev/project-hunter/apps/web/components/settings/appearance-form.tsx:94), numa página real de [Aparência](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/settings/appearance/page.tsx:5). A persistência usa `localStorage.setItem` em [usePriceFlash.ts:30](C:/dev/project-hunter/apps/web/hooks/usePriceFlash.ts:30).  
   O timeout agora depende de `[direction]`, em efeito separado dos ticks: [usePriceFlash.ts:92](C:/dev/project-hunter/apps/web/hooks/usePriceFlash.ts:92).  
   **Falhas anteriores resolvidas:** existe onde desligar o efeito; um segundo tick após 50 ms não cancela mais seu reset.

6. **PARCIAL — contraste e foco corrigidos; cobertura incompleta.**  
   O input ganhou `focus-visible:ring-2 focus-visible:ring-gold` em [command-palette.tsx:206](C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:206), e a exchange usa `text-fg-muted` na linha 240.

   Recalculei em memória com os tokens de [globals.css:37](C:/dev/project-hunter/apps/web/app/globals.css:37) e [globals.css:79](C:/dev/project-hunter/apps/web/app/globals.css:79): exchange sobre seleção dourada **5,29:1 escuro / 7,13:1 claro**; `fg-subtle` sobre overlay claro **5,17:1**. **Os defeitos visuais específicos anteriores estão corrigidos.**

   Falta a proteção pedida: [theme-contrast.test.ts:168](C:/dev/project-hunter/apps/web/tests/theme-contrast.test.ts:168) testa `fg-subtle` somente sobre `bg` e `bg-elevated`. Não cobre os fundos da seleção nem overlay. É uma lacuna de regressão, não evidência de que o contraste anterior continue ruim hoje.

7. **PARCIAL — responsividade.**  
   Houve tratamento concreto: `min-w-0 ... overflow-hidden` no [topbar.tsx:95](C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:95), busca reduzida a ícone abaixo de `sm` em [command-palette.tsx:69](C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:69), e trades com `flex-col ... sm:flex-row` em [recent-trades.tsx:38](C:/dev/project-hunter/apps/web/components/markets/recent-trades.tsx:38).

   **Falha residual:** abrir o detalhe numa janela de 1024 px, com sidebar expandida. A sidebar ocupa `w-60` em [sidebar.tsx:26](C:/dev/project-hunter/apps/web/components/layout/sidebar.tsx:26), e os painéis viram duas colunas em [market-detail-view.tsx:147](C:/dev/project-hunter/apps/web/components/markets/market-detail-view.tsx:147). O trade continua numa linha, com relógio `sm:shrink-0` e preço/quantidade crus. O painel estreito volta a disputar largura com os três valores. **Inferência de layout; não medi no navegador.**

**Outros must-fix e cenários atuais de UX ruim**

- **Topbar ainda não distingue frescor de conexão.** Abra mercados com exchanges `CONNECTED`; deixe os eventos envelhecerem. `if (normalized === "connected") return "ok"` mantém a cor saudável em [live-status.tsx:25](C:/dev/project-hunter/apps/web/components/system/live-status.tsx:25). Com várias exchanges, o rótulo compacto nem mostra idade: [live-status.tsx:185](C:/dev/project-hunter/apps/web/components/system/live-status.tsx:185). Falta sinalizar atraso com evidência apropriada da API, mantendo separado o resultado de `/ready`.

- **No celular, a explicação de saúde fica inacessível visualmente.** Abra Markets abaixo de `md`: o status de mercados fica oculto em [topbar.tsx:106](C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:106). O ponto do sistema oferece apenas `title` e texto `sr-only`, sem controle acionável: [topbar.tsx:55](C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:55). Uma pessoa usando toque vê uma cor, mas não tem interação explícita para consultar seu significado.

- **Reduced motion ainda não cobre o shell.** Ative redução de movimento no sistema e recolha a sidebar. Ela mantém `transition-[width] duration-150` em [sidebar.tsx:25](C:/dev/project-hunter/apps/web/components/layout/sidebar.tsx:25). A regra de redução adicionada cobre somente `.flash-up` e `.flash-down`: [globals.css:171](C:/dev/project-hunter/apps/web/app/globals.css:171).

**Nice-to-have**

- **Retry na palette:** provoque uma falha de busca e pressione Enter para tentar novamente. Nada dispara nova consulta: Enter apenas abre resultado, e o erro só diz “Tente novamente”. [command-palette.tsx:175](C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:175), [linha 215](C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:215).
- **Ausência de variação neutra:** com `price_change_24h_pct = null`, o usuário vê `--` verde, pois `changeNegative` assume falso. [market-row.tsx:30](C:/dev/project-hunter/apps/web/components/markets/market-row.tsx:30), [linha 66](C:/dev/project-hunter/apps/web/components/markets/market-row.tsx:66).
- **Explicação da qualidade:** ao encontrar “atrasado”, o usuário não consegue descobrir pelo badge qual componente causou isso; ele mostra apenas a maior idade. [quality-badge.tsx:60](C:/dev/project-hunter/apps/web/components/markets/quality-badge.tsx:60).
- **Tipografia:** ainda há tabela de 13 px e relógio de 11 px, além de famílias distintas para corpo e números. [markets-table.tsx:240](C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:240), [recent-trades.tsx:48](C:/dev/project-hunter/apps/web/components/markets/recent-trades.tsx:48), [globals.css:17](C:/dev/project-hunter/apps/web/app/globals.css:17).

**O que faria diferente**

Eu calcularia a posição das linhas incluindo o cabeçalho e invalidaria deliberadamente a seleção que saiu da janela renderizada. Usaria a largura disponível do painel para decidir o layout dos trades. No topbar, daria acesso por toque a uma explicação curta de verificação, conexão e frescor.

Também exigiria uma verificação geométrica da tabela nas duas densidades: compartilhar a constante é correto, mas `height` no `<tr>` sozinho não comprova que conteúdo quebrado em linhas nunca aumentará sua altura.

**O que concordo**

- Candles verdes/vermelhos, incluindo corpo, borda e pavio: [candles-chart.tsx:72](C:/dev/project-hunter/apps/web/components/markets/candles-chart.tsx:72).
- UTC com horário e offset local visíveis nos trades: [format.ts:145](C:/dev/project-hunter/apps/web/lib/format.ts:145) e [recent-trades.tsx:48](C:/dev/project-hunter/apps/web/components/markets/recent-trades.tsx:48).
- Busca com botão, Ctrl/Cmd+K, setas/Enter e consulta real por `q`: [command-palette.tsx:42](C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:42), [markets-actions.ts:34](C:/dev/project-hunter/apps/web/lib/api/markets-actions.ts:34).
- Separação entre universo vazio, busca sem resultados e erro com retry: [markets-empty.tsx:18](C:/dev/project-hunter/apps/web/components/markets/markets-empty.tsx:18), [markets-table.tsx:272](C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:272), [markets-error.tsx:21](C:/dev/project-hunter/apps/web/components/markets/markets-error.tsx:21).
- Flash limitado e bloqueado por redução de movimento no hook: [usePriceFlash.ts:76](C:/dev/project-hunter/apps/web/hooks/usePriceFlash.ts:76).

Não executei testes, build, screenshots ou gravação de 30 segundos. Os fechamentos acima são de revisão do código; a aceitação visual continua pendente.