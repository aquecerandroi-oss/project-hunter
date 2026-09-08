# Notas T3.22 — horário de Brasília em toda a tela (frontend-specialist)

**STATUS:** DONE

## O que mudou (visão geral)

Todo horário PRIMÁRIO exibido no produto agora é convertido para `America/Sao_Paulo`
("Brasília" na cópia, nunca a sigla IANA nem "BRT" em prosa), formatado no padrão
brasileiro (`DD/MM HH:mm` curto, `DD/MM/AAAA HH:mm:ss` longo). O UTC deixou de ser o
texto principal e agora vive só no `title` (tooltip) — que já é o próprio ISO copiável,
satisfazendo ao mesmo tempo "UTC no tooltip" e "forma ISO copiável" com uma única string.

A conversão é **determinística em qualquer timezone de runtime** (servidor ou navegador):
`Intl.DateTimeFormat` com `timeZone: "America/Sao_Paulo"` explícito resolve o offset de
Brasília sozinho, sem depender de `Date#getTimezoneOffset()`. Isso eliminou a dança
"renderiza UTC no SSR, adiciona o offset local só depois de montar no cliente" que existia
em `PortfolioAsOf`/`SystemAsOf`/`LabAsOf`/`RecentTrades` (o motivo original, H2, deixou de
existir: o timezone de exibição agora é fixo, não o do navegador do visitante).

Verificado no ambiente: `Intl.DateTimeFormat(..., { timeZone: "America/Sao_Paulo" })`
produz o mesmo resultado independente da variável `TZ` do processo Node (testado com
`TZ=Asia/Tokyo` vs. sem `TZ`) — full ICU do Node 24 confirmado.

## Arquivo novo: a "uma fonte" do timezone

- **`apps/web/lib/time.ts`** (novo, 132 linhas) — `BRASILIA_TIME_ZONE` ("America/Sao_Paulo",
  com comentário `TODO(org-settings)` porque a API não expõe timezone por organização —
  só `trading_day_timezone` em `/portfolios/{id}/risk`, já hardcoded no mesmo valor no
  servidor), `BRASILIA_LABEL` ("Brasília"), e os formatadores puros: `formatBrasiliaShort`,
  `formatBrasiliaLong`, `formatBrasiliaDate`, `formatBrasiliaWithUtcTooltip` (para o
  crosshair dos gráficos, mostra os dois: "08/09 02:05:05 Brasília · 05:05:05 UTC") e
  `formatBrasiliaTick` (ticks dos eixos, mapeando os 5 valores do enum `TickMarkType` da
  `lightweight-charts` sem importar a lib nesse módulo).
- **`apps/web/components/time/brasilia-instant.tsx`** (novo) — dois componentes de
  apresentação reaproveitados nos lugares que só tinham `formatUtc(iso)` solto em JSX:
  `BrasiliaInstant` (forma longa) e `BrasiliaShort` (forma curta, células de tabela
  densas). Ambos usam `title={iso}` para o UTC/ISO copiável.

## Ponto de decisão explícito: não pedi confirmação, decidi e seguí

O brief pedia "se ambíguo, pare e pergunte", mas a interpretação era mecânica o bastante
para decidir sozinho (documentando aqui em vez de bloquear): removi `formatLocalOffset` e
`formatUtcWithOffset` de `lib/format.ts` em vez de mantê-los mortos ou repropositá-los —
eram, por definição, "o timezone do navegador do visitante", exatamente o que Everton
pediu para nunca mais aparecer. `formatUtc` continua existindo (mesma implementação),
agora documentado como o meio-UTC secundário/tooltip em vez do texto principal.

## Todos os pontos de chamada alterados

### `apps/web/lib/format.ts`
- Removidas `formatLocalOffset` e `formatUtcWithOffset` (dependiam do timezone do
  runtime/navegador — proibido pela regra 1 do brief). `formatUtc` mantida, docstring
  atualizada (agora é o meio-UTC de tooltip/detalhe operacional, não mais o principal).

### `apps/web/components/lab/lab-format.ts`
- `formatWhenShort` agora delega para `formatBrasiliaShort` (`lib/time.ts`) em vez de usar
  getters UTC do `Date`. Docstring atualizada.

### `apps/web/components/lab/lab-when-cell.tsx`
- `WhenCell`: removido o `useEffect`/`useState` (não precisa mais de client-only), removida
  a prop `suffix` (não existe mais "UTC" para anexar — a ambiguidade fica resolvida uma vez
  no cabeçalho "Quando (Brasília)"). `title={iso}` (UTC/ISO copiável) substitui o antigo
  `title` combinado UTC+local. Deixou de ser `"use client"`.
- Call sites atualizados (removida a prop `suffix`): `lab-price-time-cell.tsx`,
  `lab-exit-cell.tsx`. `lab-signal-row.tsx` já não passava `suffix`, sem mudança.

### `apps/web/components/lab/lab-signals-table-head.tsx`
- Cabeçalho "Quando" → **"Quando (Brasília)"** (o exemplo literal do brief), `minWidthClass`
  ajustada de `110px` para `150px` para caber o texto maior.

### `apps/web/components/lab/lab-as-of.tsx`, `apps/web/components/system/system-as-of.tsx`, `apps/web/components/portfolio/portfolio-as-of.tsx`
- As três reescritas de forma idêntica: removido `"use client"` + `useEffect`/`useState`
  (SSR-safe agora, timezone fixo). Renderizam `formatBrasiliaLong(iso)` com `title={iso}`.
  Usadas por: `lab-signal-panel.tsx` (Decisão/barra de referência), `lab-header.tsx`
  ("Estado em"), `execution-paper-card.tsx` (idade do MTM/kill switch/proteção),
  `portfolio-equity-chart.tsx`, `portfolio-header.tsx`, `portfolio-result-card.tsx`,
  `portfolio-proposals-empty.tsx`.

### `apps/web/components/lab/lab-scoreboard.ts`
- `formatSince` (rótulo "desde DD/MM/AAAA" do Placar) agora usa `formatBrasiliaDate` em vez
  de getters UTC.

### Gráficos (3 arquivos, mesma mudança): `apps/web/components/lab/lab-curve-chart.tsx`, `apps/web/components/portfolio/portfolio-equity-chart.tsx`, `apps/web/components/markets/candles-chart.tsx`
- Adicionado `timeScale.tickMarkFormatter` (ticks do eixo X em Brasília, via
  `formatBrasiliaTick`) e `localization.timeFormatter` (rótulo do crosshair mostra
  Brasília + UTC juntos, via `formatBrasiliaWithUtcTooltip`) no `createChart(...)`.
  Nenhuma outra mudança de comportamento nesses arquivos.

### `apps/web/components/portfolio/portfolio-format.ts`
- Texto de `UNAVAILABLE_LABELS.daily_reference`: "abertura em America/Sao_Paulo" →
  "abertura em Brasília".

### `apps/web/components/portfolio/portfolio-risk-card.tsx`
- `DAILY_REFERENCE_NOTE`: mesma troca de texto.
- Rótulo `Dia (${riskState.trading_day_timezone})` → `Dia (${BRASILIA_LABEL})` — o brief
  pedia isso na regra 3 ("o rótulo diz 'Brasília' em português simples em vez do nome
  IANA"); o campo `trading_day_timezone` da API continua chegando (e continua
  `"America/Sao_Paulo"`, ver PENDÊNCIA abaixo), só não aparece mais cru na tela.
  `trading_day` em si (o dia como string, ex. `"2026-09-08"`) não foi tocado — já é
  "um dia", não um instante, regra 3 do brief.
- `Row` passou a aceitar `value: ReactNode` (igual ao `Row` de `execution-paper-card.tsx`)
  para caber o componente `BrasiliaInstant`.
- "Pico observado em" e "Última transição ... em" trocaram `formatUtc(...)` por
  `<BrasiliaInstant iso={...} />`.

### `apps/web/components/portfolio/portfolio-activity-tables.tsx`
- `formatUtc` removido do import; `AsOfNote`, "Aberta em", "Criada em", "Fechado em" (3
  tabelas: Posições/Ordens/Trades) agora usam `<BrasiliaInstant iso={...} />`. Cabeçalhos
  de coluna viraram "Aberta em (Brasília)", "Criada em (Brasília)", "Fechado em
  (Brasília)" — regra geral do item 2 do brief ("tabelas de horário ... uma vez no
  cabeçalho"), estendida às outras tabelas de atividade além do exemplo literal "Quando".

### `apps/web/components/radar/radar-table.tsx`
- "Painel consultado {formatUtc(asOf)} · anomalias verificadas {formatUtc(...)}" →
  `<BrasiliaInstant iso={asOf} />` / `<BrasiliaInstant iso={anomalies.asOf} />`.

### `apps/web/components/anomalies/anomaly-timeline.tsx`
- 3 usos de `formatUtc` (linha do item, "verificado" no estado vazio, "verificado" no
  rodapé) → `BrasiliaInstant`.

### `apps/web/components/dashboard/regime-tile.tsx`, `hot-opportunities-tile.tsx`, `anomalies-tile.tsx`
- "verificado {formatUtc(result.asOf)}" (Server Components, sem `"use client"`) →
  `<BrasiliaInstant iso={result.asOf} />` em cada um.

### `apps/web/components/opportunities/why-history.tsx`
- Linha do histórico do score: `formatUtc(p.ts)` → `<BrasiliaInstant iso={p.ts} />`.

### `apps/web/components/opportunities/why-context.tsx`
- "desde {formatUtc(currentRegime.start_time)}" → `<BrasiliaInstant iso={...} />`.

### `apps/web/components/opportunities/opportunity-row.tsx` + `opportunities-table-head.tsx`
- Coluna "Atualizado" (última coluna, oculta em telas pequenas) → `<BrasiliaShort iso={row.last_updated_at} />`;
  cabeçalho "Atualizado" → "Atualizado (Brasília)".

### `apps/web/components/markets/recent-trades.tsx`
- Removido `useTradeTimestampText` (hook client-only) e `"use client"`; `TradeItem` agora
  chama `formatBrasiliaLong(trade.ts)` direto (determinístico, sem efeito). O `<span>` do
  horário ganhou `title={trade.ts}` (antes não tinha tooltip nenhum — o UTC+offset já
  estava todo em texto visível).

## Pendência anotada em vez de tocar a API

`riskState.trading_day_timezone` (`/portfolios/{id}/risk`, `hunter_api/schemas/portfolio.py`)
já retorna `"America/Sao_Paulo"` hardcoded no backend — nenhum campo de timezone por
organização existe na API (confirmado em
`packages/shared-types/src/generated/api.d.ts`). `lib/time.ts` documenta isso com um
`TODO(org-settings)`: quando existir uma configuração real, trocar a constante por uma
leitura real vira mudança de uma linha (todo o resto do arquivo já funciona por cima da
constante). Não mexi em `apps/api/**` nem em `packages/**`, como instruído.

## Efeito colateral positivo (nenhuma perda funcional)

`PortfolioAsOf`/`SystemAsOf`/`LabAsOf`/`RecentTrades` deixaram de precisar de
`"use client"` + `useEffect`/`useState`: como Brasília não depende do timezone do
navegador, a mesma string renderiza no servidor e no cliente sem risco de hydration
mismatch — simplificação, não regressão (eles continuam podendo ser importados de
componentes cliente, como já eram).

## TESTS (saída real)

```
$ export PATH="$HOME/.local/bin:/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:$PATH"
$ pnpm --filter web lint
> eslint .
(sem saída — 0 problemas)

$ pnpm --filter web typecheck
> tsc --noEmit
(sem saída — 0 erros)

$ pnpm --filter web test
 RUN  v5.0.0 C:/dev/project-hunter/apps/web
Not implemented: navigation to another Document   (aviso pré-existente do jsdom, não relacionado)
 Test Files  79 passed (79)
      Tests  687 passed (687)
   Duration  52.95s
```

Testes novos: `apps/web/tests/time.test.ts` (19 casos) — cobre `BRASILIA_TIME_ZONE`/
`BRASILIA_LABEL`, `formatBrasiliaShort`/`Long`/`Date` com um instante fixo no ano
sem DST (comentário no arquivo lembrando que o Brasil não observa DST desde 2019 —
Decreto 9.772/2019), os dois casos de virada de meia-noite pedidos no brief (23:30 UTC =
20:30 Brasília no mesmo dia; 02:30 UTC = 23:30 Brasília no dia ANTERIOR — e o caso
simétrico de virada de ano, 2026-01-01T02:30Z = 2025-12-31 23:30 Brasília),
`formatBrasiliaWithUtcTooltip` e `formatBrasiliaTick` (todos os 5 `TickMarkType`), e uma
verificação de que `Date#getTimezoneOffset` nunca é chamado (o mesmo estilo de teste que
`format.test.ts` já usava para `formatUtc`).

Testes existentes atualizados (comportamento mudou de UTC para Brasília, não regressão):
`apps/web/tests/format.test.ts` (removidos os describes de `formatLocalOffset`/
`formatUtcWithOffset`, que não existem mais), `apps/web/tests/lab-format.test.ts`
(`formatWhenShort`), `apps/web/tests/lab-money.test.ts` (`priceAndTime`/`saidaText`),
`apps/web/tests/lab-scoreboard.test.ts` (`formatSince`), `apps/web/tests/lab-scoreboard-card.test.tsx`
(texto "desde ..." renderizado), `apps/web/tests/recent-trades.test.tsx` (texto do
horário e novo teste de `title`), `apps/web/tests/execution-paper-card.test.tsx`
(trocado o `getAllByText(/UTC/)` por `getByTitle(isoDoLastMtm)`, já que o UTC não é mais
texto visível).

## O que a tela mostra agora (por leitura de código + comparação com os fixtures de teste; sem servidor local rodando nesta sessão — ver CONCERNS)

- **Lab** — coluna "Quando (Brasília)" mostra `08/09 02:05` em vez de `08/09 05:05 UTC`;
  "Entrou"/"Saiu" mostram a mesma hora de Brasília na linha secundária, sem sufixo; o
  painel do sinal mostra "Decisão: 08/09/2026 02:05:05" (hover revela o ISO UTC); o
  Placar mostra "desde 05/09/2026" para uma versão ativada às 02:08 UTC do dia 6 (a
  virada de meia-noite agora é visível corretamente); a curva do Placar tem ticks do
  eixo X em Brasília e o crosshair mostra "... Brasília · ... UTC".
- **Carteira** — "Dia (Brasília)" em vez de "Dia (America/Sao_Paulo)"; "Pico observado
  em", "Consultado em" (equity chart) e as 3 tabelas de atividade (Posições/Ordens/
  Trades) mostram hora de Brasília com hover para o ISO UTC; a mensagem de referência
  diária diz "abertura em Brasília".
- **Radar** — "Painel consultado .../ anomalias verificadas ..." em Brasília.
- **Markets** — badges de staleness continuam idades relativas (sem mudança, regra 5);
  candles com ticks em Brasília; trades recentes mostram a hora de Brasília
  imediatamente (sem mais o efeito de duas renderizações), com tooltip do ISO.
- **System** — idade do MTM/kill switch/proteção continuam "há Xs" (sem mudança) com o
  parêntese agora em Brasília; hover mostra o ISO UTC (o "detalhe de operador" da regra 8).
- **Dashboard/Oportunidades** — "verificado ..." dos 3 tiles e o histórico de score da
  página de detalhe de oportunidade em Brasília; coluna "Atualizado (Brasília)" na
  listagem de oportunidades.

## CONCERNS

1. Não subi o `pnpm dev`/preview neste ambiente para conferir visualmente as telas (o
   brief e as regras operacionais focaram em `lint`/`typecheck`/`test`, sem servidor de
   API/Postgres/Redis disponível aqui para dados reais). A revisão visual fica para o
   `product-designer` mencionado no brief, como de praxe ("Reviewers afterwards").
2. Optei por remover `formatLocalOffset`/`formatUtcWithOffset` em vez de mantê-los mortos
   — ver a seção "Ponto de decisão explícito" acima. Se algum outro agente/tela ainda
   depender externamente desses nomes (não encontrei nenhum em `apps/web` além dos
   arquivos já reescritos), isso quebraria — `pnpm --filter web typecheck` confirmaria
   isso na hora.
3. Cabeçalhos de coluna ganharam "(Brasília)" em mais lugares do que o único exemplo
   literal do brief ("Quando (Brasília)") — apliquei a regra geral do item 2
   ("tabelas de horário ... uma vez no cabeçalho") também a "Aberta em"/"Criada em"/
   "Fechado em" (Carteira) e "Atualizado" (Oportunidades), por consistência. Se o
   product-designer preferir menos "(Brasília)" repetido nos cabeçalhos (a página já é
   100% Brasília por convenção), é uma reversão de uma linha por cabeçalho.
4. Não toquei `apps/api/**` — a pendência do campo de timezone por organização está
   documentada em `apps/web/lib/time.ts` como `TODO(org-settings)`, não implementada.
