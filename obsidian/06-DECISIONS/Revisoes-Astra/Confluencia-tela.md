---
tags: [revisao-astra, confluencia, spot, frontend, code-review]
date: 2026-09-28
updated: 2026-09-28
status: registro
owner: sexta-feira
decided_on: 2026-09-28
by: astra
tarefa: T4.82 — correções de code review na tela "Confluência de mercado" (uncommitted)
veredito: REQUEST_CHANGES em cinco rodadas ao todo; fechado na rodada 5 (achados 1-4 da rodada 3 corrigidos e confirmados na rodada 4; achado 5 exigiu duas correções -- flex-wrap primeiro, padding vertical empilhado com a altura do Badge depois)
---

# Revisão da Astra — correções da tela de confluência (T4.82)

A implementação de `docs/design/tela-confluencia-mercado.md` (candles + sinais do Lab + notícias +
trilha da mesa `spot/1` + regime/anomalias numa linha do tempo, painel "Neste instante" em três
blocos A/B/C) chegou a **três rodadas** de revisão antes desta tarefa — nenhuma delas commitada ainda.
Esta nota cobre as três, na ordem em que aconteceram, porque a terceira só fecha lendo o que as duas
primeiras já haviam corrigido em código (os comentários `Astra's review of T4.82 (must-fix N)` e
`Code review (round 2/3, must-fix N)` espalhados pelos arquivos são o rastro disso).

## Rodada 1 — revisão inicial do frontend (`.claude/state/astra-review-confluencia-tela-frontend.md`)

10 must-fix HIGH/MEDIUM, todos corrigidos antes desta tarefa começar (visíveis em código pelos
comentários "Astra's review of T4.82"): reconstrução histórica incorreta em A (sinal/posição
filtrados pelo estado ATUAL, não pelo intervalo), `barIndexContaining` cobrindo lacunas do gráfico
sem estender geometria além da saída real, identidade do mercado (embrião do achado 1 da rodada 3),
truncamento silencioso de sinais/eventos, timeframe trocado sem re-sincronizar a série, faixas
desalinhadas do gráfico, janela comum para desk/eventos vs. candles de 1h, falha vs. ausência
misturadas, vocabulário de recusa do `spot/1` incompleto. **Concordou** com `direction`/`expires_at`
no endpoint existente e com "só o sinal selecionado desenha sobre o preço".

## Rodada 2 — revisão do code-reviewer + Astra (`.claude/state/astra-review-review-confluencia-cr.md`)

Focada em três pontos: (1) confirmou que sinais **spot** históricos (340 na coorte `prospective`,
NEARUSDT duplicado — `.claude/state/notes-T3.73.md`) tornam a filtragem por símbolo insuficiente,
**HIGH**, virou o achado 1 desta tarefa; (2) virtualização é **MEDIUM**, corte não é paginação; (3)
look-ahead residual em A **e** B: status atual da ordem exibido para um corte por `received_at`, e
notícia tardia aparecendo em B sem ressalva — vira os achados 2 e 3 desta tarefa. Nenhuma dessas
correções havia sido feita ainda quando esta tarefa começou.

## Rodada 3 — esta tarefa, minha pergunta inicial (`.claude/state/astra-review-confluencia-fixes.md`)

Corrigi os 5 achados do brief (Everton/orquestrador, citando as rodadas 1-2): `market_id` aditivo no
filtro de sinais (achado 1), status final só quando `settled_at<=cursor` senão rótulo "pendente"
(achado 2), `eventKnownInWindow` excluindo notícia tardia de B (achado 3), virtualização com o hook
interno `useVirtualizedRows` — **`@tanstack/react-virtual` não é dependência instalada neste repo**,
confirmado por grep em todos os `package.json` (achado 4), teste do link "Ver confluência" (achado 5).

**Concordou com 1 e 5.** Achou **regressão real na correção 2** e um **destino incompleto para
notícias** na correção 3:

- **MUST-FIX 1 (HIGH) — recusa na criação virava "pendente".** `spot_entries.py`/
  `spot_entry_writes.py::refuse_row` inserem `status='refused'` diretamente; `_INSERT_ORDER`
  (`spot_repo.py`) nunca grava `settled_at` nesse caminho, só `admitted_at` (e só quando
  `status='admitted'`). Meu `orderSettledAsOfCursor` exigia `settled_at<=cursor` para QUALQUER status
  terminal — uma recusa na criação (a maioria real dos casos) nunca tem `settled_at`, então passava a
  aparecer como "admitida, aguardando confirmação" mesmo sendo definitivamente recusada. O teste que
  eu tinha escrito mascarava isso porque preenchia `settled_at` por padrão.
- **MUST-FIX 2 (MEDIUM) — `failed` ficava sempre pendente.** `latestOrderStateForSignal` só resolvia
  `confirmed`/`refused`; uma ordem que falhou (com `settled_at` gravado por `_FAILED`) nunca tinha um
  destino.
- **MUST-FIX 3 (HIGH) — resultado posterior retrodatado em B.** Removi o gate de "recebida antes do
  cursor" para ordens recebidas DEPOIS do cursor mas ainda dentro de ±N — só que aí eu mostrava o
  status FINAL (ex.: "confirmada") no timestamp de `received_at`, mesmo quando `settled_at` cai fora
  da janela inteira (cenário concreto: recebida 11:46 dentro de ±15, confirmada só às 13:00). Recebimento
  e resultado são dois fatos com dois instantes; recomendou resultado posterior em C, recebimento em B.
- **MUST-FIX 4 (MEDIUM) — notícia sem destino.** Meu `eventKnownInWindow` passou a excluir de B toda
  notícia não conhecida no cursor (mais amplo que antes), mas o bloco C só admitia o caso estreito
  "`published_at` não nulo e anterior ao cursor" — uma notícia só com `observed_at`, ou publicada
  DEPOIS do cursor, sumia dos dois blocos.
- **MUST-FIX 5 (MEDIUM) — virtualização com altura variável.** `flex-wrap` nos spans deixava título de
  notícia/motivo de recusa quebrar linha, crescendo o `<tr>` além do `rowHeight` fixo que
  `useVirtualizedRows` assume — desalinha a posição de rolagem dos índices calculados.

Rodou uma sondagem sintética em `node` (sem escrever arquivo) reproduzindo os quatro casos temporais
antes de eu corrigir — não substitui as suítes, mas confirmou os cenários com saída real.

## O que mudou depois do parecer da rodada 3

- `confluence-window.ts`: `orderFinalAsOfCursor` substitui o gate único por `settled_at` —
  `admitted_at === null` (recusa na criação) é final no próprio `received_at`; `admitted_at !== null`
  exige `settled_at<=cursor` (mesma regra de antes, agora restrita a quem passou por admissão).
  `SignalOrderState` ganhou `kind: "failed"`.
- `confluence-timeline-rows.ts` (**novo arquivo** — `confluence-instant-panel.tsx` passou de 350
  linhas ao acrescentar a lógica): `pushOrderRows` grava "recebida" (sempre, na janela) e "liquidada"
  (linha independente, só se `settled_at` também cair na janela) como DOIS eventos separados;
  `buildBlockCRows` ganhou liquidações com `settled_at>cursor` fora da janela; o filtro de notícia
  virou só `classifyEventTiming === "later"`, com texto diferente conforme `published_at` é
  conhecido-antes-do-cursor ou não.
- `confluence-event-list.tsx`: `flex-wrap` → `flex-nowrap overflow-hidden`, spans de texto livre
  (título, motivo) com `truncate`/`title=`, `<td>` com `max-w-0 w-full overflow-hidden` — o idioma
  Tailwind padrão para truncar dentro de uma coluna de tabela de largura automática.
- Testes novos: `apps/web/tests/confluence-window.test.ts` (recusa na criação sem `settled_at`,
  `failed` resolvido, `orderFinalAsOfCursor` isolado) e `apps/web/tests/confluence-timeline-rows.test.ts`
  (novo arquivo, 10 casos incluindo o cenário exato do parecer: recebida 11:46/confirmada 13:00).

## Rodada 4 — confirmação (`.claude/state/astra-review-confluencia-fixes-r2.md`)

Papel de `code-reviewer`, sondagem sintética em `node` (4 cenários, saída real: recusa na criação =
`refused`; falha antes/depois = `failed`→`pending` corrigido; liquidação futura = B mostra só
"recebida" às 11:46, C mostra "confirmada" às 13:00; notícia tardia, 3 variantes = `B=0 C=1` cada).
**Fechou os achados 1-4 da rodada 3.** Achou um **residual concreto no achado 5**: a célula mantinha
`py-1.5` (12 px de padding vertical) empilhado sobre a altura própria do `Badge` (22 px — linha de
16 px + padding de 4 px + borda de 2 px, `ui/badge.tsx`), somando 34 px, **acima dos 32 px da
densidade compacta** (`useDensity.ts`) embora coubesse nos 40 px da confortável — `useVirtualizedRows`
continuava calculando espaçadores com o `rowHeight` compacto de 32 px. Apontou também a coluna do
instante sem `whitespace-nowrap` como um segundo caminho de crescimento. **Concordou** com o texto
genérico "ingerida depois deste instante" (não inventa uma publicação que não existe) e com `max-w-0`
como truncamento horizontal (nunca resolveria, por si, o orçamento vertical).

## Rodada 5 — correção do residual, sem nova pergunta à Astra

Segui o padrão que `lab-signal-row.tsx` já usa para as próprias linhas virtualizadas: **nenhum
padding vertical no `<td>`** (removido `py-1.5`/`align-top` dos dois), a altura do `<tr>` inline
(`style={{ height: rowHeight }}`) mais o `vertical-align: middle` padrão de `<td>` centralizam o
conteúdo sem inflar a linha — o `Badge` de 22 px cabe folgado tanto nos 32 px (compacta) quanto nos
40 px (confortável) sem precisar de um cálculo separado por densidade. A coluna do instante ganhou
`whitespace-nowrap`. `pnpm typecheck`/`lint` limpos, os 78 testes (agora 7 arquivos) continuam
passando -- a mudança é só de classes CSS, nenhuma lógica testável nela além do que os testes de
`confluence-timeline-rows.test.ts`/`confluence-window.test.ts` já cobrem.

## Divergência registrada

Nenhuma: todo achado da Astra nas cinco rodadas tinha um cenário de falha concreto (arquivo + linha +
timestamps, ou matemática de pixels) e foi aceito e corrigido, nunca descartado.

## Brutos

- `.claude/state/astra-review-confluencia.md` (desenho, 23/09)
- `.claude/state/astra-review-confluencia-tela-frontend.md` (rodada 1)
- `.claude/state/astra-review-review-confluencia-cr.md` (rodada 2)
- `.claude/state/astra-review-confluencia-fixes.md` (rodada 3, achados 1-5 do brief)
- `.claude/state/astra-review-confluencia-fixes-r2.md` (rodada 4, fecha 1-4, acha o residual do 5)

**Relacionado:** [[Confluencia-market-events]] · [[03-TRADING/Spot/Mesa-spot-1|Mesa spot/1]] · `docs/design/tela-confluencia-mercado.md`
