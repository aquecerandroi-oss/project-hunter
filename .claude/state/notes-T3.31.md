# Notas — T3.31: "Error: Value is null" em todos os gráficos lightweight-charts

Owner: frontend-specialist. Base: `main` em `970c20b`. **Não commitado** (regra
do brief). Árvore compartilhada: durante esta sessão `apps/web/app/(app)/[orgSlug]/lab/**`
e `apps/web/components/lab/lab-signals-table.tsx`/`lab-totals-card.tsx` mudaram
de estado entre uma rodada de `typecheck`/`lint` e a seguinte (ver CONCERNS) —
nenhum desses arquivos está no meu escopo e nenhuma mudança deles é minha.

## CAUSA RAIZ (confirmada lendo o bundle real servido pelo `docker-web-1`, não por suposição)

Copiei o chunk exato citado no brief de dentro do container em execução
(`docker cp docker-web-1:/app/apps/web/.next/static/chunks/3e7f71f0-ce61d2fde1a727ed.js`)
e inspecionei o texto minificado diretamente. Achados, em ordem:

1. **A linha exata que lança o erro** — confirmada byte a byte:
   ```js
   function M(t){if(null===t)throw Error("Value is null");return t}
   ```
   (`ensureNotNull`, chamado por `b(t){return M(w(t))}` = `ensureNotNull(ensureDefined(x))` em outros pontos, mas o brief mostra `M` chamado **direto**.)

2. **A cadeia de chamada do brief bate literalmente, função por função**, com uma
   classe real do próprio `lightweight-charts` dentro do chunk:
   ```js
   class tR{
     constructor(t){
       this.wh=(t,i)=>void 0!==i?i.Wt:this.Te.Un().Mh(t),
       this.Te=t,
       this.gh=tN[t.bh()]              // = tN.Line para uma LineSeries
     }
     Sh(t,i){ return this.gh(this.wh, this.Te.N(), t, i) }   // <- aparece como "tR.Line [as gh]" via tR.Sh
   }
   ```
   Verifiquei empiricamente (harness isolado, Playwright + Chromium real) que
   `this.gh = obj.Line` chamado como `this.gh(...)` produz **exatamente**
   `"Tr.Line [as gh]"` no stack do V8 — a mesma anotação do brief, não uma
   coincidência de nomes curtos.

   E a classe que fecha o ciclo (`sp` no brief):
   ```js
   class sp extends sv {
     Rb(t,i,e){ return {...this.Tb(t,i), ...e.Sh(t)} }   // <- "sp.Rb", chama tR.Sh
     Lg(){
       let t = this.ae.Sa();
       this.kg = this.ae.Ua().Bh().map(i => this.Rb(i.$n, i, t));  // <- "Array.map -> sp.Rb", chamado por "sp.Lg"
     }
   }
   ```

3. **Mecanismo**: `Lg()` reconstrói o cache de desenho de UMA série
   percorrendo `this.ae.Ua().Bh()` — a lista de **todos os tempos conhecidos
   pela TIME SCALE COMPARTILHADA do gráfico inteiro** (todas as séries juntas),
   não só os pontos da própria série. Para cada tempo global, pede a esta
   série o seu próprio bar (`this.wh(e, s)` com `s===undefined` cai em
   `this.Te.Un().Mh(e)` — busca **exata**, sem fallback de vizinhança; ver
   `Ih(t,i){ ...; if(null===e && 0!==i){...} return e }` com `i` default `0`).
   Se esta série não tiver um ponto **exatamente** naquele tempo — porque o
   tempo só existe porque OUTRA série do mesmo gráfico o usa — `Mh()` devolve
   `null`, e `M(null)` explode.

   `LabCurveChart` é o **único** gráfico do app com mais de uma `LineSeries`
   compartilhando uma única time scale (uma linha por versão de estratégia,
   cada uma só com os tempos em que aquela versão realmente emitiu sinal —
   praticamente nunca idênticos entre versões). `candles-chart.tsx` e
   `portfolio-equity-chart.tsx` têm exatamente uma série cada — nunca podem
   cair nesse caminho, o que bate com a medição do brief (só o Lab quebrou) e
   com a análise anterior do T3.28b (aviso 3 daquelas notas), que já tinha
   isolado o bug em lightweight-charts mas não tinha chegado à causa exata.

4. **Por que só em produção**: o build de desenvolvimento tem asserções
   próprias (`checkSeriesValuesType`, `checkItemsAreOrdered`) que capturam
   `value: null`/`NaN`/ordem incorreta com mensagens legíveis **antes** de
   `setData` aceitar os dados — confirmei isso rodando os dois bundles
   (`lightweight-charts.development.mjs` vs `.production.mjs`, ambos 5.2.1,
   mesma versão do `apps/web/package.json`) num harness Playwright isolado.
   `lightweight-charts.production.mjs` **não contém nenhuma dessas strings**
   (grep = 0 ocorrências) — são eliminadas como dead code no build de
   produção, então qualquer dado limítrofe que o dev pegaria com uma mensagem
   clara chega sem guarda nos internals de produção, incluindo o
   `ensureNotNull` do item 1.

**Nível de confiança**: a cadeia de chamada e o mecanismo estão confirmados
lendo o código real do bundle publicado (não é hipótese). **Não consegui**
fechar o ciclo com uma reprodução sintética 100% determinística dentro do
tempo desta sessão (várias tentativas com dois `LineSeries` de tempos
disjuntos/intercalados no bundle de produção real não dispararam o erro —
ver CONCERNS 1) nem com dado real de produção (a API de scoreboard do Lab
está retornando 500 nesta sessão — ver CONCERNS 2, fora do meu escopo). A
correção abaixo foi desenhada diretamente a partir do mecanismo encontrado no
código-fonte da lib, não validada por um crash ao vivo antes/depois.

## O que foi implementado

Correção no **helper compartilhado** (brief item 2 — "um lugar só, não por
gráfico"), não em cada componente:

1. **`apps/web/lib/charts/css-var.ts`** (novo): `cssVar(name, fallback)` —
   fallback para um hex literal (nunca outro token, para nunca recursar numa
   segunda busca quebrada) + `logger.warn` uma vez por token (não uma vez por
   render). `chartColor(name)` é o atalho usado nos três componentes, com uma
   tabela `CHART_TOKEN_FALLBACK` com o valor dark-theme atual de cada token
   lido (`app/globals.css`), e `"#a3a3a3"` (fg-muted) como default neutro para
   qualquer token fora da tabela.
2. **`apps/web/lib/charts/series-data.ts`** (novo):
   - `sortAndDedupeByTime`: ascendente por tempo, último valor escrito vence
     num tempo duplicado (a asserção de dev exige exatamente isso —
     `allowDuplicates` nunca é usado nos três gráficos).
   - `sanitizeLinePoints`: descarta `value` não finito (mantém `WhitespaceData`
     — um gap intencional continua sendo um gap, nunca um número inventado),
     depois ordena/dedupe.
   - `sanitizeCandlePoints`: descarta um candle com qualquer OHLC não finito.
   - **`alignToUnionTimes`** (a correção da causa raiz, item 3 acima): recebe
     as séries de um mesmo gráfico e devolve cada uma com um ponto
     `WhitespaceData` explícito em todo tempo que QUALQUER série do grupo usa
     — fecha exatamente o buraco que `Mh()` encontrava.
3. **Efeitos idempotentes sob Strict Mode** (brief item 2, terceira parte):
   nas três funções de criação do gráfico, uma flag local `disposed` (não a
   ref mutável) é fechada `true` no cleanup e checada dentro do handler de
   `resize` — um callback que sobreviva ao próprio efeito nunca mais toca
   `chart`/`series` depois do teardown.
4. **Uso nos três componentes**:
   - `components/lab/lab-curve-chart.tsx`: `attachSeries` agora chama
     `alignToUnionTimes` sobre todas as séries desenháveis antes de qualquer
     `addSeries`/`setData`; o efeito de atualização (`[series, currency,
     ruler]`, dispara ao trocar USDT/R ou ao recarregar) faz o mesmo —
     reabriria a mesma brecha se só sanitizasse cada série isolada.
   - `components/markets/candles-chart.tsx`: `toChartData` passa por
     `sanitizeCandlePoints`; `cssVar` local removido, usa `chartColor`.
   - `components/portfolio/portfolio-equity-chart.tsx`: `toSeriesData` passa
     por `sanitizeLinePoints` (uma série só, `alignToUnionTimes` não se
     aplica); `cssVar` local removido, usa `chartColor`.

## FILES

**Criados**
- `apps/web/lib/charts/css-var.ts`
- `apps/web/lib/charts/series-data.ts`
- `apps/web/tests/chart-css-var.test.ts`
- `apps/web/tests/chart-series-data.test.ts`

**Modificados**
- `apps/web/components/lab/lab-curve-chart.tsx`
- `apps/web/components/markets/candles-chart.tsx`
- `apps/web/components/portfolio/portfolio-equity-chart.tsx`
- `apps/web/tests/lab-curve-chart.test.tsx` (um teste de regressão novo)

**Criados e apagados nesta sessão** (item 1 do brief, descartáveis)
- `tests/e2e/_probe.audit.ts`, `tests/e2e/_probe.config.ts`

## TESTS (saída real)

Suíte isolada dos arquivos deste brief, `npx vitest run` (dentro de `apps/web`):
```
$ npx vitest run tests/chart-css-var.test.ts tests/chart-series-data.test.ts tests/lab-curve-chart.test.tsx tests/candles-chart.test.tsx tests/portfolio-equity-chart.test.tsx tests/lab-curve.test.tsx tests/lab-scoreboard.test.ts tests/market-detail-view.test.tsx

 Test Files  9 passed (9)
      Tests  73 passed (73)
```

`pnpm --filter web lint` (escopo completo do pacote):
```
$ eslint .

C:\dev\project-hunter\apps\web\app\(app)\[orgSlug]\lab\page.tsx
    1:1   error  File too large (388 lines | max 350)
   98:1   warning  ...max-params...
  200:16  warning  ...complexity...

C:\dev\project-hunter\apps\web\components\lab\lab-signals-table.tsx
  135:5  error  Calling setState synchronously within an effect can trigger cascading renders
  162:5  warning  Unused eslint-disable directive

C:\dev\project-hunter\apps\web\components\lab\lab-totals-card.tsx
  146:8   warning  complexity 17 (max 12)
  164:20/89/157  error  Forbidden non-null assertion (x3)

C:\dev\project-hunter\apps\web\tests\fixtures\lab.ts
  1:1  warning  File too large (379 lines | max 350)

✖ 10 problems (5 errors, 5 warnings)
```
Nenhum desses 5 erros/5 avisos está nos arquivos deste brief — todos em
`lab/page.tsx`, `lab-signals-table.tsx`, `lab-totals-card.tsx`,
`tests/fixtures/lab.ts` (nenhum tocado por mim). ESLint escopado só nos meus
arquivos:
```
$ npx eslint components/lab/lab-curve-chart.tsx components/markets/candles-chart.tsx components/portfolio/portfolio-equity-chart.tsx lib/charts/css-var.ts lib/charts/series-data.ts tests/chart-css-var.test.ts tests/chart-series-data.test.ts tests/lab-curve-chart.test.tsx
(sem saída -- 0 problemas)
```

`pnpm --filter web typecheck` (repo root):
```
$ tsc --noEmit
app/(app)/[orgSlug]/lab/page.tsx(106,38): error TS2379: Argument of type '{ strategy_version_id?: string; cohort: string; state: LabSignalsState; page_size: 200 | 50 | 100 | 500; cursor: string | undefined; }' is not assignable to parameter of type 'LabSignalsParams' with 'exactOptionalPropertyTypes: true'. ...
```
Um erro só, em `lab/page.tsx` (não tocado por mim). Antes de eu corrigir dois
erros próprios de indexação (`aligned[index]` sob `noUncheckedIndexedAccess`,
já resolvidos com `?? []`), meu diff também não tinha erros.

`npx vitest run` (suíte inteira, `apps/web`):
```
 Test Files  4 failed | 94 passed (98)
      Tests  30 failed | 870 passed (900)
```
As 30 falhas são 100% em `tests/lab-page.test.tsx`, `tests/lab-signal-panel.test.tsx`,
`tests/lab-signals-table.test.tsx`, `tests/lab-totals-card-in-table.test.tsx`
-- nenhum arquivo deste brief. Causa raiz visível no próprio stack:
`lab-signals-table.tsx:139` lê `page.from` de um `page` `undefined`
(`TypeError: Cannot read properties of undefined (reading 'from')`), e
`hooks/useVirtualizedRows.ts:46` lê `.length` de `rows` `undefined` --
consistente com o `loadLabSignalsAction`/`LabSignalsParams`/`LabTotalsCardProps`
quebrados que o typecheck já apontava. Confirmei que nenhum desses arquivos
importa `lab-curve-chart`, `lib/charts/css-var` ou `lib/charts/series-data`
(grep). Pré-existente/em edição concorrente na mesma árvore, fora do escopo
deste brief.

## Reprodução com Playwright (item 1 do brief)

`tests/e2e/_probe.audit.ts` + `_probe.config.ts` (descartáveis, apagados ao
final) rodaram contra o `docker-web-1` atual com o storage state existente:

- `/ever/markets/binance/BTCUSDT`: renderizou normalmente, **7 canvases**,
  zero `pageerror`. (Os "7 canvases" do brief são a contagem normal de UM
  gráfico `lightweight-charts` — confirmei isso separadamente com um harness
  isolado: um único `createChart` sempre cria 7 `<canvas>`. Não é sinal de
  gráfico duplicado.)
- `/ever/lab`: a seção "Placar" (que contém `LabCurveChart`) mostrou
  **"Placar indisponível: falha ao carregar (An unexpected error occurred.)"**
  em vez do gráfico. Confirmado no log do `docker-api-1`:
  ```
  File ".../hunter_api/routers/lab_scoreboard.py", line 75, in get_scoreboard
      runs_summary = await repo.replay_runs_summary(meta.id)
  TypeError: LabScoreboardRepository.replay_runs_summary() missing 1 required keyword-only argument: 'as_of'
  INFO: "GET /api/v1/lab/shadow/scoreboard?as_of=... HTTP/1.1" 500 Internal Server Error
  ```
  Isso é um bug **novo, no backend** (`apps/api/**`, T3.18c em voo, fora do
  meu escopo e da minha permissão de tocar) que impede o `LabCurveChart` de
  sequer montar nesta sessão -- **não é o mesmo bug deste brief**, mas
  bloqueia a prova visual "antes"/"depois" com dado real ao vivo (ver
  CONCERNS 2).

## CONCERNS

1. **Reprodução sintética não fechou o ciclo dentro do tempo desta sessão.**
   Construí um harness isolado (Playwright + Chromium real, servindo o
   `lightweight-charts.production.mjs` exato do `apps/web/node_modules`, mesma
   versão 5.2.1 do chunk real) e testei ~15 hipóteses (cor vazia, `value:
   null`/`NaN`, tempo não-finito, ordem invertida, tempo duplicado, série
   criada/atualizada após `chart.remove()`, container desanexado do DOM antes
   do cleanup, duas séries com tempos totalmente disjuntos, duas séries com
   tempos intercalados + hover simulado sobre o canvas). Nenhuma reproduziu
   "Value is null" isoladamente -- só consegui confirmar a causa raiz **lendo
   o código-fonte real do bundle** (seção CAUSA RAIZ acima), não vendo o
   crash acontecer ao vivo sob meu controle. A correção implementada ataca
   exatamente o mecanismo encontrado no código (não uma hipótese chutada),
   mas o par antes/depois "eu vi quebrar, apliquei o fix, vi parar de
   quebrar" não foi fechado nesta sessão.
2. **Prova visual "depois" com dado real bloqueada por um bug do backend, fora
   do meu escopo.** A API `/api/v1/lab/shadow/scoreboard` está retornando 500
   agora (`TypeError` em `hunter_api/routers/lab_scoreboard.py:75`, argumento
   `as_of` faltando em `replay_runs_summary()`), então `LabCurveChart` nunca
   chega a montar com as 5 versões reais que o brief mediu às 14:55Z. Preciso
   que o dono de `apps/api/**` (T3.18c ou quem revisar depois) corrija esse
   500 antes que a prova "curva do Lab renderiza linhas" seja possível --
   sem isso, mesmo com `docker-web-1` reconstruído, `/ever/lab` mostra
   "Placar indisponível", não a curva.
3. **Comando exato para a reconstrução** (item 4 do brief, deixado para o
   orquestrador -- não executei):
   ```
   docker compose -f infra/docker/docker-compose.yml build web && \
   docker compose -f infra/docker/docker-compose.yml up -d web
   ```
   Depois disso, com o bug do item 2 acima corrigido no backend, rodar
   `bash .claude/state/tmp/run-design-audit.sh -g "screens 1440 dark"` (ou um
   probe equivalente em `/ever/lab` e `/ever/markets/binance/BTCUSDT`) e
   confirmar console sem `Value is null`.
4. **Árvore compartilhada mudando durante a sessão.** `pnpm typecheck`/`pnpm
   lint` deram contagens de erro diferentes em `apps/web/app/(app)/[orgSlug]/lab/**`
   e `components/lab/lab-signals-table.tsx`/`lab-totals-card.tsx` entre duas
   rodadas consecutivas minhas (ex.: um erro de módulo não resolvido
   desapareceu, um erro de `setState` síncrono em efeito apareceu) -- alguém
   mais está editando essa área ao vivo apesar do brief dizer "nada mais em
   `apps/web/**` em voo". Nenhuma dessas mudanças é minha; documentei a saída
   real de cada rodada para rastreabilidade.
5. **`.claude/state/design/2026-09-08/` não recebeu screenshots novos** (item
   4 do brief) -- sem um `docker-web-1` reconstruído com esta correção e sem
   o Placar carregando dado real (concern 2), uma captura "depois" seria uma
   tela sem o gráfico de qualquer forma. Recomendo ao orquestrador rodar a
   captura só depois dos dois follow-ups acima (rebuild + fix do 500).
