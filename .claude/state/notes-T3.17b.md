# Notas de desenho — T3.17b (tabela e totais do Lab, corrigidos e mais detalhados)

Decisões tomadas ao executar `.claude/state/brief-T3.17b-lab-table-detail.md` (screenshot real de
Everton, VPS `/ever/lab`, 2026-09-08 ~05:05Z) sobre a tela entregue em T3.17
(`.claude/state/notes-T3.17.md`). Não toquei `apps/web/components/lab/lab-version-card.tsx`
(T3.15e em voo), `apps/api/**`, `packages/**`, `services/**`, `infra/**`, `obsidian/**` nem
`.env*`. Base `main` em `adc4cb9`.

## 1. Totais: "desta página" explícito, sem a frase que soava a alarme

`truncationNote` (T3.17) foi **removida** e trocada por duas peças (`lab-money.ts`):
`totalsHeading(rowCount, hasMore)` — "Resultado das operações desta página (N)" quando a lista
está truncada, "Resultado de todas as operações do período (N)" quando `next_cursor` é `null` — e
a constante `LAB_TOTALS_SCOPE_NOTE` ("os totais do Lab inteiro chegam com o placar (T3.18)"),
sempre visível abaixo do título. A frase antiga "há mais sinais além desta página" nunca mais
aparece (testado explicitamente em `lab-money.test.ts` e `lab-signals-table.test.tsx`). Adicionei
`avgProfitUsdt`/`avgLossUsdt`/`best`/`worst` a `RowsSummary` — médias e melhor/pior operação
(mercado + resultado), computadas nas mesmas linhas já carregadas, cada uma rotulada "(desta
página)" no card (`lab-totals-card.tsx`).

## 2. A nota técnica do endpoint virou tooltip, não parágrafo

O parágrafo "Sinais · todo o período disponível (este endpoint não aceita janela/`as_of`...)" saiu
da UI. No lugar, um rótulo curto e sublinhado "período: todo o disponível" carrega o fato completo
no `title` nativo (`lab-signals-table.tsx`'s `PERIOD_TOOLTIP`) — descobrível, não permanente na
tela. Testado em "the endpoint's own window scope is a tooltip, not a paragraph".

## 3. "Quando"/"Entrou"/"Saiu" em uma linha fixa, sem o wrap de quatro linhas

`formatUtcWithOffset` (a string longa "05:05:05 UTC (02:05:05 -03:00)", sem data) foi trocada por
`formatWhenShort` (`lab-format.ts`): `"08/09 05:05"`, construído com os getters UTC do `Date`
(nunca `Intl`, para não depender de locale) — determinístico, sem dependência de fuso do
navegador. O componente `WhenCell` (`lab-when-cell.tsx`) mostra esse texto curto (mais " UTC" na
coluna "Quando") e guarda o horário local + o ISO completo num único `title`, calculado no cliente
após o mount (mesmo padrão H2 de `LabAsOf`, nunca no SSR — o container roda UTC). "Entrou"/"Saiu"
viraram duas linhas por célula (preço em cima, hora embaixo, sem "UTC") via `LabPriceTimeCell`/
`LabExitCell`, nunca três linhas mesmo com o motivo (ver item 5).

## 4. Segmentos: "Concluídas" por padrão, contagens visíveis, ordem concluída-primeiro

Novo módulo puro `lab-signal-segments.ts`: `matchesSegment`/`segmentCounts`/
`sortSignalsConcludedFirst`/`visibleSignalsForSegment`. "Pendentes/sem entrada" agrupa
`pending_entry`, `no_entry` e `censored` — nenhum dos três é vitória, derrota, ou "em
acompanhamento" no sentido de `active` (mesmo eixo de três estados do próprio Shadow Lab,
já usado em `TRACKING_BUCKET`). A ordem padrão é `decision_at` desc **com as concluídas primeiro**
(`sortSignalsConcludedFirst`), e filtrar um segmento preserva essa ordem dentro do próprio
segmento. `LabSegmentTabs` (`lab-segment-tabs.tsx`) mostra as quatro guias com contagem
(`"Concluídas (137)"`), calculada sobre **todas** as linhas carregadas (não afetada pela guia
ativa). Trocar de guia zera a seleção de teclado e o scroll (`handleSegmentChange`). Um segmento
sem linhas mostra seu próprio estado vazio (`LabSignalsTableBody`), nunca o "0 sinais" da tabela
inteira — são fatos diferentes (seleção vazia vs. Lab vazio).

## 5. Detalhe por linha: Estratégia, Duração e "por que saiu" chegaram na visão padrão

`LAB_MONEY_HEADERS` ganhou "Estratégia" (chip de versão + chip de propósito
`pesquisa`/`paper`, de `strategy_versions.purpose`, `LabStrategyCell`) e "Duração" (h:mm,
`durationText` em `lab-format.ts` — `null` quando falta `entry_ts`/`exit_ts`, **nunca** calculado
contra "agora" para uma posição ainda aberta, o que mudaria a cada render sem um novo fetch). A
coluna "Saiu" ganhou o motivo real (`EXIT_REASON_LABEL`: alvo/stop/expirou/invalidada — vocabulário
de concordância verbal próprio, distinto do `RESULT_LABEL` adjetivo do chip) na mesma segunda linha
do horário, nunca uma terceira linha. Para `no_entry`/`censored` (sem preço), o texto completo do
motivo vai num `title` + `truncate` de largura máxima (`max-w-[220px]`) — nunca mais corta no meio
da palavra ("motivo: s…"): a informação completa fica a um hover, que é a alternativa "wrap or
tooltip" que o próprio brief autoriza (o wrap quebraria a altura fixa da linha, exigida pela
virtualização). As colunas de pesquisa da tabela (toggle "Detalhes de pesquisa") foram reduzidas
à lista exata do brief — R líquido, R ex-funding, Stop, Alvo, Tracking — `Versão` (agora em
"Estratégia"), `Referência` e `Toque` (`ResultChip`) saíram da tabela; ambos continuam no painel de
detalhe (`lab-signal-panel.tsx`, inalterado além do que T3.17 já fez).

## 6. Badge do Resultado nunca mais foge da tela

A causa raiz do "badge fora da tela" era `className="w-full ..."` na `<table>`: isso força a
tabela a nunca ultrapassar 100% do contêiner, então as colunas se espremem em vez de crescer e
disparar o scroll horizontal do `overflow-x-auto` que já envolvia a tabela. Troquei para
`"w-full min-w-max ..."` (padrão Tailwind para permitir crescer além do contêiner) e dei
`min-width` fixo às colunas "Quando" e "Resultado" (`minWidthClass` em `LabHeaderDef`). Com isso o
scroll horizontal passa a ocorrer de verdade dentro do card da tabela — nunca na página — em
telas estreitas.

## 7. Complexidade ciclomática: extraído, não ignorado

`pnpm lint` reportou `complexity` acima do teto (12) em `LabSignalRow`/`LabSignalsTable`/
`LabTotalsCard` assim que os novos ramos entraram. Em vez de aceitar o warning, extraí: 
`lab-money-cells.tsx` (`LabMoneyOrReason`/`LabResultValue`, reutilizáveis entre a linha e o
painel), `pctColorClass` em `lab-format.ts`, `lab-load-more.tsx` e `lab-signals-table-body.tsx`
(tirados de `LabSignalsTable`), e `buildTotalsDisplay` (função pura fora do componente, em
`lab-totals-card.tsx`). `pnpm lint` final: 0 erros, 0 avisos.

## 8. Verificação em navegador: bloqueada por falta de sessão real, não pulada

`pnpm build` compila com sucesso (7/7 páginas geradas; o único erro é `EPERM` do Windows ao criar
symlinks no output "standalone" — falha de trace de arquivo, não do meu código). Subi
`next dev` localmente (porta 3101, `NEXT_PUBLIC_API_URL=http://localhost:8000`, chaves Clerk lidas
do `.env` da raiz só como variáveis de ambiente do processo, nunca escritas em arquivo): `/` e
`/sign-in` respondem 200. Confirmei que o Postgres local **tem dado real**: `docker exec
docker-postgres-1 psql -U hunter -d hunter -c "select count(*) from signal_outcomes"` → 840 linhas,
org `ever` presente. Mas não tenho uma sessão Clerk autenticada (sem chaves de teste
`CLERK_E2E_*` locais, sem acesso ao e-mail/OTP de Everton) nem uma ferramenta de navegador nesta
sessão — não consegui abrir `/ever/lab` de fato e tirar um print. Verificação feita: 628 testes
(unitários/componente) usando fixtures tiradas do exemplo real do contrato
(`contract-S3-lab.md`), incluindo os novos cenários do próprio bug do Everton (badge cortado,
motivo truncado, data quebrando linha, pendentes empurrando concluídas). Recomendo que o
`product-designer` (ou o próprio Everton) abra `/ever/lab` com uma sessão real antes do
merge — ver "Para o designer" abaixo.

## Para o designer

1. Confirme que "Resultado" nunca sai da área visível mesmo em ~1024px de largura, e que o scroll
   horizontal acontece dentro do card da tabela (não a página inteira) — o fix foi `min-w-max` na
   `<table>`, preciso de um olho real sobre isso em vários breakpoints.
2. O rótulo "período: todo o disponível" ficou como texto sublinhado pontilhado com `title` nativo
   — mesma linguagem visual de `LabMetricItem`? Se quiser um ícone de info em vez do sublinhado,
   me avise (troca de meia hora).
3. Os chips de "Estratégia" (versão + propósito) ficaram empilhados verticalmente numa coluna
   estreita — confira se cabe bem ao lado de "Mercado" sem alargar demais a tabela em telas médias.
4. As guias "Concluídas · Abertas · Pendentes/sem entrada · Todas" usam a mesma borda
   dourada de seleção do resto do produto; "Pendentes/sem entrada" é o rótulo mais longo — confira
   se quebra em telas pequenas (mobile mostra só overview/posições/PnL/alertas/kill switch por
   CLAUDE.md, então o Lab detalhado é desktop-first, mas os rótulos ainda devem caber sem cortar).
5. "Melhor/pior operação" no card de totais usa a mesma cor verde/vermelha do restante; a
   sub-legenda ("alvo"/"stop"/...) fica em `fg-subtle` 11px — compare com o resto do card para ver
   se o contraste está bom nos dois temas.

## Pontos em aberto (não resolvidos neste brief)

- Os totais do Lab inteiro (todas as páginas, todo o cohort) continuam pendentes do T3.18 web
  (scoreboard); o card aqui é honesto sobre isso, mas ainda não os mostra.
- Não fiz uma verificação visual real (browser) por falta de sessão autenticada nesta execução —
  ver item 8 acima.
