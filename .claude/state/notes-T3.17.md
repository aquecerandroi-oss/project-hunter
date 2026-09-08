# Notas de desenho — T3.17 (Lab em termos de dinheiro)

Decisões tomadas ao implementar `.claude/state/brief-T3.17-lab-in-money-terms.md` sobre a tela
já existente de S3/S3b (`docs/plans/SHADOW-LAB.md`, `.claude/state/notes-S3b.md`). Nada no
`strategy-worker`/API mudou — só a leitura. Nenhum campo faltou na API (`lab_signals.py`,
`lab_summary.py`); a única peça externa usada é `GET /orgs/{org}/portfolios` + seu resumo, já
implementados e testados (T3.8a), reaproveitados exatamente como `portfolio/page.tsx` já faz.

## 1. A régua de 0,25% é uma constante do produto, não um campo da API do Lab
`risk_per_trade_pct = 0.0025` vem de `docs/RISK_ENGINE.md` §3 (paper_v1), não de
`lab_summary`/`lab_signals` — nenhum dos dois schemas carrega essa razão. Ela virou uma constante
nomeada em `components/lab/lab-money.ts` (`RISK_PER_TRADE_PCT`), com o comentário explicando a
origem, do mesmo jeito que `LAB_LABEL` é uma string fixa do lado da API
(`hunter_api/schemas/lab_common.py`) — uma regra declarada do produto, não um número inventado
pela tela. O que **vem** da API e nunca é digitado é o patrimônio (`GET /portfolios` +
`GET /portfolios/{id}`, campo `equity`/`brl.equity_brl`).

## 2. Carteira principal: mesmo critério de `portfolio/page.tsx`, reaproveitado
"A carteira paper principal da organização" = `type === "paper" && !is_arena`
(`packages/core/hunter_core/db/models/portfolios.py`'s índice único parcial, já documentado em
`portfolio/page.tsx`). `loadMoneyRuler` em `app/(app)/[orgSlug]/lab/page.tsx` faz exatamente essa
busca (`listPortfolios` → filtra → `getPortfolioSummary`) e nunca lança: qualquer falha (sem
carteira, sessão ausente, API fora) degrada para `buildReferenceRuler()` (10.000 USDT, rotulada
"carteira de referência, sem carteira aberta") em vez de derrubar a página inteira por causa de um
aperfeiçoamento de exibição. Isso está coberto em `tests/lab-page.test.tsx` (carteira ausente,
carteira `is_arena` que não conta, carteira real "ever" com 19.333,01 USDT, e falha de rede na
própria consulta de portfolios).

## 3. Matemática do dinheiro é `Number`, não o caminho decimal-seguro de `lib/format.ts`
`lib/format.ts` evita `Number()` para *renderizar* um único Decimal (evitar perda de precisão em
saldos de 28 dígitos). Aqui a conta é aritmética real (multiplicação/divisão) sobre dois ou três
números já hipotéticos, só para tradução em tela — nunca persistida, nunca reenviada à API. A
regra "Decimal, nunca float" do CLAUDE.md mira dinheiro *armazenado*; nada aqui é armazenado, e as
magnitudes (preços de cripto, patrimônio de carteira paper) estão muito abaixo de 2^53, então
`Number` não perde nenhum dígito que mudaria o resultado arredondado a 2 casas que
`formatUsdt`/`formatBrl` mostram depois. Documentado no topo de `lab-money.ts`.

## 4. Convenção de formatação: mantida a que já existe (en-US para USDT, pt-BR só para BRL)
O brief escreve os números de exemplo em convenção brasileira ("19.333,01 USDT"), mas o produto já
usa `formatUsdt` (agrupamento en-US, sufixo "USDT") de forma consistente em toda a tela de carteira
(`portfolio-header.tsx`, `portfolio-risk-card.tsx`) e `formatBrl` (convenção pt-BR) só para valores
em Real — com um comentário explícito em `lib/format.ts` sobre por que BRL tem sua própria função.
Introduzir uma terceira convenção só para o Lab quebraria essa consistência sem necessidade; a
régua e as colunas de dinheiro usam `formatUsdt`/`formatUsdtSigned` (en-US) para USDT e
`formatBrl`/`formatBrlSigned` (pt-BR) para o BRL ao lado, exatamente como a carteira já faz. Único
lugar deliberadamente literal (não passa por `formatPct`): o "0,25%" da frase da régua, porque é o
nome de uma regra fixa do produto, não um número calculado a cada render. Se o Everton quiser o
padrão brasileiro para TODO valor em USDT do produto (não só do Lab), isso é uma mudança maior,
cross-cutting, fora do escopo deste brief — sinalizado como ponto aberto no relatório final.

## 5. "R" só no toggle de pesquisa: colunas duplicadas, não substituídas
A visão padrão da tabela agora é só dinheiro (Mercado, Quando, Entrou, Saiu, Variação, Quantia
simulada, Resultado); o botão "Detalhes de pesquisa" acrescenta as colunas antigas (Versão,
Referência, Stop, Alvo, Tracking, Toque, R líquido, R ex-funding) ao lado, nunca substitui as de
dinheiro — layout implementado em `lab-signals-table-head.tsx` (`labSignalsHeaders(showResearch)`)
e `lab-research-cells.tsx`. `LabSignalRow`/`LabResearchCells` foram separados para não estourar o
teto de complexidade ciclomática do ESLint numa função só (o card de versão -- `lab-version-card.tsx`
-- e o funil não mudaram: o brief pediu para tocar só a tabela de sinais e o painel de detalhe).

## 6. `lab-signal-detail.tsx` do brief é, na prática, `lab-signal-panel.tsx`
O item 4 do brief nomeia `lab-signal-detail.tsx` como o lugar do bloco de dinheiro, mas esse
arquivo hoje é só o painel do envelope JSON sob demanda (`Ver envelope`/`Ocultar envelope`); o
detalhe completo do sinal (Referência/Stop/Alvo/Entrada virtual/Saída/R líquido/excursões) vive em
`lab-signal-panel.tsx`. O bloco de dinheiro (`SignalMoneyBlock`) foi colocado ali, no topo, acima
do rótulo "Detalhe de pesquisa" que agora separa visualmente o bloco antigo (mantido sem mudanças
de conteúdo) do novo.

## 7. Totais calculados só sobre as linhas carregadas, nunca uma segunda chamada
`LabTotalsCard` (novo) recebe as `rows` que já estão no estado de `LabSignalsTable` (as mesmas
~200 que a tabela virtualizada mostra) e computa tudo em `summarizeRows` (`lab-money.ts`), puro e
testado isoladamente. Quando existe `next_cursor` (a lista está truncada pelo `limit`), aparece
"calculado das N operações listadas -- há mais sinais além desta página" acima do card
(`truncationNote`), nunca escondido.

## 8. Pendente/sem entrada/censurada: contados e nomeados à parte, nunca dentro de "concluídas"
Espelha os três eixos do próprio Shadow Lab (`SignalStatus`/`OutcomeResult`/`tracking_state`,
SHADOW-LAB.md item 4): "concluídas" = `tracking_state === "terminal"`; pendente
(`pending_entry|active`), sem entrada e censurada são estados que nunca contam como vitória, derrota
ou "ainda em aberto" no mesmo sentido de um `active`. Um caso raro dentro de "concluídas" (funding
não apurável, `r_multiple` nulo mesmo terminal) não vira uma quarta caixa separada no card — soma
em "concluídas" mas fica fora de "com lucro"/"com prejuízo"/"taxa de acerto", coberto por
`withKnownPnl` em `RowsSummary` e testado em `lab-money.test.ts`.

## 9. Tooltip fixo em todo número de dinheiro (brief: "mesmo sufixo/tooltip, nunca escondido")
Em vez de repetir a frase completa ao lado de cada célula (o que violaria "menos chips por célula",
`docs/DESIGN.md` §2), cada célula/bloco monetário carrega `title="simulado — dado real, custos
assumidos, sem dinheiro"` (`MONEY_TOOLTIP`) como tooltip nativo no hover — descobrível, não
poluidor. A frase completa e sempre visível continua na régua do cabeçalho.
