**Eu ainda não aprovaria o fix pass: M2 continua aberto, M3 está parcial e encontrei outra falha de runtime com Web Storage bloqueado.** Os quatro HIGH originais estão corrigidos no código.

Revisão somente de leitura, limitada aos arquivos `M`/`??` de `apps/web` e `docs/DESIGN.md`, além das regras e da revisão solicitadas. Não li `.env`, não alterei arquivos nem fiz commit. Não executei build ou testes; os 309 testes verdes são o resultado informado por você.

**Must-fix**

1. **M2 — a correção ARIA remove também a estrutura necessária para navegar pelas células.**  
   Cenário: usuário de leitor de tela entra na grade de mercados e tenta navegar pelas células associando preço, variação e cabeçalho. O container declara `grid`, mas a tabela recebeu `role="presentation"` em [markets-table.tsx:263](/C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:263); as células continuam sem papéis explícitos em [market-row.tsx:46](/C:/dev/project-hunter/apps/web/components/markets/market-row.tsx:46). A apresentação se propaga aos descendentes estruturais da tabela, conforme a [documentação WAI-ARIA](https://www.w3.org/WAI/ARIA/apg/practices/hiding-semantics/). Portanto, eliminar a segunda tabela não estabeleceu uma grade acessível completa.

   **O teste agora codifica essa correção insuficiente:** exige apenas ausência de `role=table`, sem verificar linhas/células/cabeçalhos em [markets-table.test.tsx:240](/C:/dev/project-hunter/apps/web/tests/markets-table.test.tsx:240).

2. **M3 — Enter ainda abre uma linha fora da tela quando ela permanece no overscan.**  
   Cenário concreto: selecionar a primeira linha, rolar manualmente **160px** no modo confortável e apertar Enter. A linha fica entre **−128px e −88px** relativamente ao viewport, completamente invisível. Entretanto, `startIndex` continua **0**, porque a virtualização subtrai oito linhas de overscan em [useVirtualizedRows.ts:47](/C:/dev/project-hunter/apps/web/hooks/useVirtualizedRows.ts:47). O guard aceita esse índice e navega em [markets-table.tsx:180](/C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:180).

   O teste cobre apenas um salto de `4000px`, quando a seleção já saiu também do DOM: [markets-table.test.tsx:229](/C:/dev/project-hunter/apps/web/tests/markets-table.test.tsx:229). Falta distinguir **renderizada** de **visível**.

3. **Novo — preferência visual pode derrubar a renderização de Mercados quando Web Storage está bloqueado.**  
   Cenário: usuário com sessão válida abre Mercados num navegador/política que nega Web Storage. Cada linha chama `usePriceFlash`, cujo initializer acessa `window.localStorage` sem tratamento: [usePriceFlash.ts:24](/C:/dev/project-hunter/apps/web/hooks/usePriceFlash.ts:24) e [usePriceFlash.ts:43](/C:/dev/project-hunter/apps/web/hooks/usePriceFlash.ts:43). O acesso pode lançar `SecurityError`, interrompendo a renderização da tabela. Essa possibilidade faz parte do [contrato de Web Storage](https://html.spec.whatwg.org/multipage/webstorage.html#dom-localstorage).

   Há acessos igualmente desprotegidos na montagem de Appearance em [appearance-form.tsx:41](/C:/dev/project-hunter/apps/web/components/settings/appearance-form.tsx:41). Eu tornaria leitura e gravação tolerantes à indisponibilidade do armazenamento.

**Confirmação dos 16 achados**

| ID | Estado | Evidência |
|---|---|---|
| H1 | **FECHADO** | Default fixo `comfortable`; DOM lido no efeito. [useDensity.ts:39](/C:/dev/project-hunter/apps/web/hooks/useDensity.ts:39) |
| H2 | **FECHADO** | UTC no primeiro render; offset local calculado no efeito. [recent-trades.tsx:27](/C:/dev/project-hunter/apps/web/components/markets/recent-trades.tsx:27) |
| H3 | **FECHADO** | Check não tentado produz badge neutro, sem expor `not_configured`. [readiness-panel.tsx:29](/C:/dev/project-hunter/apps/web/components/system/readiness-panel.tsx:29) |
| H4 | **FECHADO** | Coordenadas incluem os 32px do cabeçalho; borda inferior considera a altura real. [useArrowKeyRowSelection.ts:58](/C:/dev/project-hunter/apps/web/hooks/useArrowKeyRowSelection.ts:58) |
| M1 | **FECHADO** | Defaults fixos nos dois controles de flash. [appearance-form.tsx:38](/C:/dev/project-hunter/apps/web/components/settings/appearance-form.tsx:38), [motion-showcase.tsx:25](/C:/dev/project-hunter/apps/web/components/design/motion-showcase.tsx:25) |
| M2 | **ABERTO** | Estrutura ARIA insuficiente, descrita acima. |
| M3 | **PARCIAL** | Bloqueia seleção desmontada; permite seleção invisível no overscan. |
| M4 | **FECHADO** | Ausência de variação recebe `text-fg-muted`. [market-row.tsx:75](/C:/dev/project-hunter/apps/web/components/markets/market-row.tsx:75) |
| M5 | **FECHADO** | Reduced motion aplica override global às animações/transições. [globals.css:171](/C:/dev/project-hunter/apps/web/app/globals.css:171) |
| M6 | **FECHADO** | Testes incluem `bg-overlay` e `fg-muted` sobre `gold-soft`, nos dois temas. [theme-contrast.test.ts:182](/C:/dev/project-hunter/apps/web/tests/theme-contrast.test.ts:182) |
| M7 | **FECHADO** | Sessão ausente retorna antes de `listMarkets`. [markets-actions.ts:45](/C:/dev/project-hunter/apps/web/lib/api/markets-actions.ts:45) |
| M8 | **FECHADO no escopo acordado** | Mínimo de dois caracteres, debounce 250ms e máximo 64 no servidor. [useMarketSearch.ts:15](/C:/dev/project-hunter/apps/web/hooks/useMarketSearch.ts:15), [markets-actions.ts:41](/C:/dev/project-hunter/apps/web/lib/api/markets-actions.ts:41) |
| M9 | **FECHADO estruturalmente** | Extrações presentes. [useMarketSearch.ts:42](/C:/dev/project-hunter/apps/web/hooks/useMarketSearch.ts:42), [useVirtualizedRows.ts:34](/C:/dev/project-hunter/apps/web/hooks/useVirtualizedRows.ts:34). Zero warnings conforme sua execução. |
| L1 | **FECHADO** | Segmentos codificados na palette e tabela. [command-palette.tsx:130](/C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:130), [markets-table.tsx:185](/C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:185) |
| L2 | **FECHADO** | Anel dourado no foco do container. [markets-table.tsx:250](/C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:250) |
| L3 | **FECHADO** | Falha do widget recebe “status dos mercados: sem verificação”. [topbar.tsx:114](/C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:114) |

**Next/App Router e hidratação**

Não encontrei **outro bloqueador de compilação** nos arquivos do recorte. O único módulo alterado com diretiva efetiva `"use server"` exporta em runtime apenas `searchMarketsAction`, assíncrona; as interfaces são tipos: [markets-actions.ts:8](/C:/dev/project-hunter/apps/web/lib/api/markets-actions.ts:8), [markets-actions.ts:38](/C:/dev/project-hunter/apps/web/lib/api/markets-actions.ts:38).

Também estão corretas duas separações importantes:

- Readiness client importa o helper neutro, não `system.ts`: [readiness-panel.tsx:8](/C:/dev/project-hunter/apps/web/components/system/readiness-panel.tsx:8).
- A função de intervalo saiu do módulo client para um módulo compartilhável: [auto-refresh-interval.ts:38](/C:/dev/project-hunter/apps/web/lib/auto-refresh-interval.ts:38).

Não apareceu import de `node:` no código de produção inspecionado nem novo acesso direto indevido a `server-only`. Isso não certifica módulos inalterados, excluídos pelo seu escopo.

**Ainda existe um mismatch concreto no showcase:** com redução de movimento habilitada, o servidor inicia `false`, enquanto o navegador inicia `true`, pois [usePrefersReducedMotion.ts:19](/C:/dev/project-hunter/apps/web/hooks/usePrefersReducedMotion.ts:19) consulta `matchMedia` no initializer. Isso acrescenta texto já na hidratação de [motion-showcase.tsx:68](/C:/dev/project-hunter/apps/web/components/design/motion-showcase.tsx:68). Trato como nice-to-have de desenvolvimento: [DESIGN.md:88](/C:/dev/project-hunter/docs/DESIGN.md:88) declara a preview indisponível em produção; não reinspecionei seu gate inalterado.

Já o initializer de `usePriceFlash` **não prova mismatch de HTML por si só**: o valor retornado inicialmente continua `null`. Seu problema concreto é a exceção de armazenamento. [usePriceFlash.ts:44](/C:/dev/project-hunter/apps/web/hooks/usePriceFlash.ts:44)

**O que os testes realmente provam**

| Teste | Avaliação |
|---|---|
| `command-palette` | Cobre abertura, navegação, mínimo de busca e resposta antiga chegando depois da nova. A API está mockada; não prova integração Next. [linha 145](/C:/dev/project-hunter/apps/web/tests/command-palette.test.tsx:145) |
| `topbar` | Confirma copy de indisponibilidade versus ausência de verificação. Falta caso degradado. [linha 23](/C:/dev/project-hunter/apps/web/tests/topbar.test.tsx:23) |
| `use-density` | Boa regressão: registra explicitamente o primeiro render, antes do estado final. [linha 53](/C:/dev/project-hunter/apps/web/tests/use-density.test.tsx:53) |
| `use-arrow-key-row-selection` | H4 deixou de codificar `−32`: exige `0` no topo e `32` no fundo nas duas densidades. Não mede layout real. [linha 103](/C:/dev/project-hunter/apps/web/tests/use-arrow-key-row-selection.test.ts:103), [linha 117](/C:/dev/project-hunter/apps/web/tests/use-arrow-key-row-selection.test.ts:117) |
| `use-virtualized-rows` | Confirma a janela com overscan; não prova visibilidade física. [linha 14](/C:/dev/project-hunter/apps/web/tests/use-virtualized-rows.test.ts:14) |
| `markets-actions` | Confirma rejeição sem sessão e limite de tamanho; não verifica regras de exportação do compilador Next. [linha 25](/C:/dev/project-hunter/apps/web/tests/markets-actions.test.ts:25) |
| `appearance-form` | Prova persistência e estado final. **Passaria com o initializer antigo.** [linha 28](/C:/dev/project-hunter/apps/web/tests/appearance-form.test.tsx:28) |
| `motion-showcase` | Mesmo limite: testa depois dos efeitos, sem SSR/hidratação. **Passaria com o bug antigo.** [linha 13](/C:/dev/project-hunter/apps/web/tests/motion-showcase.test.tsx:13) |
| `reduced-motion-css` | Confirma regra global no CSS real; não mede CSS computado. [linha 35](/C:/dev/project-hunter/apps/web/tests/reduced-motion-css.test.ts:35) |
| `use-price-flash` | Boa regressão do segundo tick que cancelava a limpeza. Não cobre storage lançando exceção. [linha 65](/C:/dev/project-hunter/apps/web/tests/use-price-flash.test.ts:65) |

**DESIGN.md, regras duras e nice-to-have**

Concordo com densidades **40/32**, corpo da tabela **13px**, candles **verde/vermelho** e classificação operacional em quatro estados: [useDensity.ts:19](/C:/dev/project-hunter/apps/web/hooks/useDensity.ts:19), [markets-table.tsx:263](/C:/dev/project-hunter/apps/web/components/markets/markets-table.tsx:263), [candles-chart.tsx:73](/C:/dev/project-hunter/apps/web/components/markets/candles-chart.tsx:73), [topbar.tsx:44](/C:/dev/project-hunter/apps/web/components/layout/topbar.tsx:44).

A documentação **não descreve integralmente a tipografia real**: apresenta cinco tamanhos e uma exceção em [DESIGN.md:66](/C:/dev/project-hunter/docs/DESIGN.md:66), mas existem metadados de **11px**, atalho de **10px** e showcase de **18px**. Exemplos: [market-row.tsx:53](/C:/dev/project-hunter/apps/web/components/markets/market-row.tsx:53), [command-palette.tsx:69](/C:/dev/project-hunter/apps/web/components/layout/command-palette.tsx:69), [design-preview.tsx:21](/C:/dev/project-hunter/apps/web/components/design/design-preview.tsx:21). Eu documentaria essas exceções para evitar que a próxima implementação siga uma regra diferente da interface existente.

O showcase contém `OK/atrasado/gap/sem dado` em [staleness-showcase.tsx:17](/C:/dev/project-hunter/apps/web/components/design/staleness-showcase.tsx:17). Não certifico aqui a implementação inalterada de `quality-badge.tsx`.

Não encontrei novo segredo literal, número financeiro inventado ou botão inerte nos fluxos de produção inspecionados. A busca consome resultados reais e retorna apenas exchange/símbolo: [markets-actions.ts:49](/C:/dev/project-hunter/apps/web/lib/api/markets-actions.ts:49).

Existem vazios sem milestone: [markets-empty.tsx:18](/C:/dev/project-hunter/apps/web/components/markets/markets-empty.tsx:18), [recent-trades.tsx:45](/C:/dev/project-hunter/apps/web/components/markets/recent-trades.tsx:45), [candles-chart.tsx:157](/C:/dev/project-hunter/apps/web/components/markets/candles-chart.tsx:157). Isso diverge da formulação geral de [DESIGN.md:70](/C:/dev/project-hunter/docs/DESIGN.md:70), mas **não inventaria um milestone futuro para dados já implementados e apenas ausentes**. Ajustaria a documentação para distinguir ausência operacional de funcionalidade futura.

**O que eu faria diferente:** manteria uma única estrutura semântica de tabela/grade, calcularia a visibilidade efetiva separadamente do overscan e acrescentaria regressões de hidratação real e storage bloqueado. Para fechar o aceite, priorizaria esses comportamentos observáveis e a execução do build de produção pelo responsável pela implementação.