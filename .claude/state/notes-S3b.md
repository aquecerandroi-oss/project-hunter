# Notas de desenho — S3b (tela `/lab`, aba Sombra)

Decisões tomadas ao implementar `.claude/state/brief-S3b-lab-page.md` sobre o contrato já
fixado e implementado em S3a (`.claude/state/contract-S3-lab.md`, código real em
`apps/api/hunter_api/{routers,schemas,repositories,services}/lab*.py`). Onde o brief era omisso
ou o contrato tinha uma restrição não óbvia, a escolha está aqui com o motivo.

## 1. `lab` não existia em `lib/nav-registry.ts` — item novo, não uma promoção
O brief dizia "nav: `lab` → `available` só agora" como se o item já existisse como `planned`.
Ele não existia: nem em `docs/PRODUCT.md` §4 (tabela de 17 rotas do plano de milestones), nem no
registro. O Shadow Lab é uma trilha paralela aos milestones (`docs/plans/SHADOW-LAB.md`), então o
item foi **adicionado** (não promovido) como `status: "available"` desde já, usando o ícone
`flask-conical` já registrado (reservado para `backtests`, que continua `planned`/oculto em
produção, então não há conflito visual). `apps/web/tests/nav-registry.test.ts` foi atualizado de
17 para 18 itens e a lista de `available` passa a incluir `lab`.

## 2. `GET /signals` não aceita `window`/`as_of` — declarado, nunca implícito
Achado da Astra na revisão de hierarquia (pedida antes de implementar, `bash infra/scripts/
astra.sh ask S3-lab-page`): o contrato (`routers/lab.py::list_signals`) não tem parâmetro de
janela — só `/summary` é filtrado por `window`. Um filtro "7d" que reduzisse silenciosamente a
lista de sinais abaixo seria uma mentira por implicação. `LabFilters` rotula o seletor de janela
como "Janela do resumo" e `LabSignalsTable` imprime "Sinais · todo o período disponível (este
endpoint não aceita janela/`as_of`)" acima da tabela.

## 3. Custos assumidos: nunca globalizados a partir da primeira versão
Segundo must-fix da Astra: `coverage.assumed_costs` é por `strategy_version` e pode divergir
entre versões. `components/lab/lab-costs.ts::commonAssumedCosts` só deixa o rótulo fixo do topo
citar números quando **todas** as versões em vista concordam; caso contrário o rótulo diz "custos
assumidos: discriminados por versão" e cada card (`LabVersionCard`) sempre mostra os seus próprios
`coverage.assumed_costs`, nunca dependendo do banner para essa informação.

## 4. Maturidade dentro do card, ao lado do funil — não um aviso editorial global
A Astra recomendou (e eu segui) manter o selo "Inconclusivo · N/100 · D/30" dentro de cada card,
logo após identidade/status e antes das métricas — nunca como um aviso acima de todas as versões,
porque isso separaria a ressalva dos números e trataria as versões deprecated com menos contexto
que as ativas. Acrescentei "nesta janela e coorte" (nice-to-have da Astra) para deixar explícito o
escopo do selo.

## 5. PnL/drawdown "não aplicável": parágrafo próprio, nunca uma badge anexada a outra métrica
Também por recomendação da Astra: as duas linhas ("PnL de carteira: não aplicável", "Drawdown de
carteira: não aplicável") ficam em texto próprio, depois das cinco métricas principais e antes do
bloco `r_ex_funding` — uma badge colada na métrica financeira mais próxima (ex.: expectancy)
correria o risco de parecer que ela está qualificando aquele número específico, quando na verdade
é um fato sobre o produto (não existe carteira no Shadow Lab).

## 6. `SignalListItemOut.market` não tem exchange — link resolvido sob demanda, nunca adivinhado
`repositories/lab_signals.py::list_page` só faz `join(Market, ...)` e seleciona `Market.symbol`
— não há `Market.exchange` na resposta. Construir `/markets/[exchange]/[symbol]` exigiria
adivinhar a exchange, que pode estar errada se o mesmo símbolo existir em mais de uma (CLAUDE.md:
sem dado inventado). `lib/api/lab-actions.ts::resolveMarketHrefAction` resolve a exchange de
verdade via `listMarkets({ q: symbol })` (já implementado e testado, T1.4): exatamente um match
navega direto para o detalhe; zero ou vários matches caem no fallback honesto de busca
(`/markets?q=<symbol>`). `components/lab/lab-market-link.tsx` é um `<button>` real (nunca um
`<a href>` fabricado), porque o destino só é conhecido depois de uma chamada assíncrona.

## 7. Painel lateral em vez de linha expansível por sinal
O brief permite "painel lateral/expansível". Uma linha expansível mudaria a altura daquela linha
especificamente, o que quebra a matemática de janela fixa de `hooks/useVirtualizedRows.ts` (que
assume `rowHeight` constante para todas as linhas). Implementado como um painel lateral
(`components/lab/lab-signal-panel.tsx`, abaixo da tabela no mobile, ao lado em `lg:`) que mostra o
sinal selecionado (clique ou Enter, reaproveitando `hooks/useArrowKeyRowSelection.ts` como
`markets-table.tsx` já faz) com todos os campos, excursões e o botão de envelope sob demanda.

## 8. Envelope sob demanda: sem `GET /signals/{id}`, resolvido por página filtrada
Não existe endpoint de item único. `loadLabSignalEnvelopeAction` pede uma página filtrada por
`market` + `strategy_version_id` + `cohort` com `include=envelope` e `limit=200`, e localiza a
linha pelo `signal_id`. Correto no volume atual (centenas de linhas por versão, mesmo teto que
`notes-S3.md` já documenta para as métricas); registrado como limitação caso um mercado acumule
mais de 200 sinais de uma mesma versão/coorte no futuro.

## 9. Auto-refresh: mesma cadência do System, sem `stale_after_ms` próprio
O Shadow Lab é um endpoint de pesquisa, não dado de mercado ao vivo — não tem `stale_after_ms`
por resposta. `revalidate = 15` + `<AutoRefresh intervalMs={DEFAULT_AUTO_REFRESH_INTERVAL_MS} />`
seguem o mesmo padrão de `system/page.tsx`, não o de `/markets` (que deriva o intervalo do próprio
`stale_after_ms`, algo que este contrato não expõe). Limitação registrada: um `router.refresh()`
atualiza o resumo/primeira página de sinais, mas o estado client-side de paginação por cursor
(itens já carregados via "Carregar mais") não é resetado por um refresh — o usuário mantém o que
já paginou; um refresh manual da página (F5) começa do zero.

## 10. Dourado como borda fina, não como fundo do rótulo fixo
O rótulo "SOMBRA" é o texto mais importante da tela, mas `docs/DESIGN.md` §2 é explícito: "nunca
em fundos grandes". `LabHeader` usa um `border-l-4 border-l-gold` sobre `bg-bg-elevated` neutro,
não um fundo `gold-soft` preenchendo a faixa inteira.

## 11. Tabs: array de dados com uma única entrada, não um "coming soon" desabilitado
`components/lab/lab-tabs.tsx`'s `LAB_TABS` tem hoje exatamente um item ("Sombra"). "Backtests"/
"Paper" não estão no array até que a API deles exista — CLAUDE.md proíbe itens inertes/"coming
soon"; a estrutura de dados é reutilizável quando a segunda aba existir, mas não há placeholder
visível agora.

## 12. Fechamento (2026-09-06): 2 testes + 5 lints, sem lacuna de brief encontrada
Retomando a árvore quase pronta: `pnpm vitest run` reportava 2 falhas, ambas por rótulos
Portugueses legitimamente duplicados, nunca por um bug de produto:
- `tests/lab-page.test.tsx`: o texto de custos assumidos aparece no banner fixo (`LabHeader`,
  obrigatório) **e** no rodapé de cada `LabVersionCard` (item 3 acima — custos nunca dependem do
  banner). Adicionei `data-testid="lab-header"` em `LabHeader` e escopei a asserção com `within`
  em vez de uma checagem solta por `getAllByText`, seguindo o nice-to-have da revisão de diff da
  Astra (`.claude/state/astra-review-S3-lab-page-diff.md`); acrescentei um segundo teste com duas
  versões com custos diferentes confirmando "discriminados por versão" no banner e os dois valores
  reais nos cards.
- `tests/lab-version-card.test.tsx`: `LabRExFunding` reusa de propósito o rótulo Português de
  `net_profit_rate` ("Taxa de lucro líquido") para a mesma métrica sobre a população ex-funding —
  correto pelo contrato, mas duplica o texto do botão de tooltip dentro do mesmo card. Adicionei
  `data-testid="lab-main-metrics"` no grid das cinco métricas principais (`lab-version-card.tsx`) e
  escopei a query do teste com `within` a esse grid, sem tocar a semântica visível da UI.
- 5 erros `@typescript-eslint/no-non-null-assertion` estavam em `tests/markets-path-escaping.test.ts`
  (arquivo de segurança pré-existente, não relacionado ao Lab, mas dentro de `apps/web/tests/**`
  permitido pelo brief) — trocado `mock.calls[0]![0]` por uma função `firstCallPath()` com `throw`
  explícito, e um `.split("/")[5]!` por checagem de `undefined` com `throw`.
Astra revisou o diff (`APPROVE_WITH_NITS`, `.claude/state/astra-review-S3-lab-page-diff.md`):
manter o `data-testid` (escopo de teste, não semântica artificial de UI) e cobrir banner/card
separadamente — os dois incorporados acima.

Conferi o brief item a item contra a árvore existente (rótulo fixo com custos da API, "PnL/Drawdown
de carteira: não aplicável", selo de maturidade, chips semânticos, excursões honestas com `bounds`,
painel do envelope sob demanda, estados vazio/503, nav `lab` → `available`, boundary
`components/**`/`hooks/**` nunca importa `@/lib/server/**`, arquivos ≤ 350 linhas) — tudo já
implementado corretamente na sessão anterior; nenhuma lacuna nova encontrada, só os 7 arquivos
listados no relatório final foram tocados nesta sessão.

## 13. Os 3 MUST-FIX do code-reviewer (2026-09-06): 1 bug real, 2 lacunas de teste
Revisão externa (`code-reviewer`) pediu correção via TDD em três pontos. Achado central: só o
primeiro era um bug de produto; os outros dois já estavam corretos no código e a lacuna era a
ausência do teste que provaria isso (e pegaria a regressão se alguém a reintroduzisse).

1. **`lab-header.tsx:19-33` — bug real.** No caminho em que todas as versões concordam nos custos
   (`common` truthy), `costsText = formatAssumedCosts(common)` produzia só os números
   ("spread 2 bps, ..."), sem o prefixo "custos assumidos:" que os outros dois ramos (`versions.
   length > 0` sem acordo, e zero versões) já tinham. O rótulo fixo saía "SOMBRA — hipotético, sem
   capital, spread 2 bps, ..." em vez da frase exigida pelo brief. Corrigido prefixando
   `` `custos assumidos: ${formatAssumedCosts(common)}` ``. `tests/lab-page.test.tsx`'s primeiro
   teste foi trocado de uma regex parcial (`/spread 2 bps.../`) para o texto completo e exato da
   frase, escopado com `within(getByTestId("lab-header"))` — falhava antes da correção (confirmado
   rodando o teste isolado antes de tocar o componente), passa depois.
2. **`lab-funnel.tsx:24-26` — já correto, sem teste.** O componente já usava
   `reasonLabel(counts.decisions_reason)`, nunca `String(counts.decisions ?? 0)` nem
   `counts.signals_emitted`. Não existia nenhum teste do `LabFunnel` isolado. Criado
   `tests/lab-funnel.test.tsx`: injetei manualmente a mutação `String(counts.decisions ?? 0)` no
   componente para confirmar que o teste novo a pega (falhou, como esperado) antes de reverter para
   o código original (voltou a passar) — mesma verificação para o `LabSignalPanel` abaixo.
3. **`lab-excursions.tsx`/`lab-signal-panel.tsx`/`lab-signal-detail.tsx` — cobertura zero, já
   corretos.** Nenhum teste selecionava uma linha (nem clique nem Enter) para abrir o painel
   lateral. Criado `tests/lab-signal-panel.test.tsx`: seleção por clique e por teclado (ArrowDown +
   Enter) via `LabSignalsTable`, depois testes diretos de `LabSignalPanel` para `mfe: null` +
   `bounds` + `ambiguous: true` ("indeterminado", limites, badge "ambíguo"), `mfe` conhecido (valor
   real, sem "0", sem badge), e `LabSignalDetail`'s botão "Ver envelope" (chama a action mockada,
   mostra o JSON, alterna para "Ocultar envelope", e mostra o motivo em caso de falha). Injetei a
   mutação citada no brief (`const known = asString(value) ?? "0"`) em `lab-excursions.tsx` para
   confirmar que o teste falha (falhou) antes de reverter.

Nice-to-haves do brief, também adicionados: `tests/lab-maturity-badge.test.tsx` (ramo "Pesquisa",
`inconclusive: false`); `tests/lab.test.ts` (`summaryQuery`/`signalsQuery` via `apiFetch` mockado,
inclusive `include=envelope` e `cursor`, seguindo o padrão de mock de `tests/api/system.test.ts`);
`tests/lab-actions.test.ts` (`resolveMarketHrefAction` com 0, 1 e vários matches, sessão ausente, e
`listMarkets` rejeitando — mesmo padrão de `tests/markets-actions.test.ts`).

Resultado: `pnpm --filter @hunter/web test` foi de 50 arquivos/360 testes para 55 arquivos/381
testes, todos verdes; `pnpm lint` e `pnpm typecheck` sem erros. Arquivos tocados: `components/lab/
lab-header.tsx` (1 linha), `tests/lab-page.test.tsx` (asserção mais estrita), mais 6 arquivos de
teste novos. `lab-funnel.tsx` e `lab-excursions.tsx`/`lab-signal-panel.tsx`/`lab-signal-detail.tsx`
não precisaram de nenhuma mudança de produto — só ganharam a cobertura que faltava.
