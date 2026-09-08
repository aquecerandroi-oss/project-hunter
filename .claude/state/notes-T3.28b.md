# Notas — T3.28b: um 429 no `/me` ou na barra de status não pode derrubar a tela inteira

Owner: frontend-specialist. Base: `main` em `385dac6`. Não commitado (regra do brief).

## Causa raiz confirmada (item 1 do brief)

`app/(app)/[orgSlug]/layout.tsx` chamava `resolveOrgContext(orgSlug)` (→ `me()` →
`apiFetch`) sem `try`/`catch`. Um 429/5xx/erro de rede em `/api/v1/me` lançava um
`ApiError` que escapava da função `OrgLayout` inteira. `error.tsx` na mesma pasta
**não pega esse throw**: no App Router, um `error.tsx` embrulha os segmentos
*abaixo* do `layout.tsx` do mesmo diretório, nunca o próprio `layout.tsx`. Sem um
`error.tsx`/`global-error.tsx` acima dele (não existiam), o throw ia direto para a
tela padrão do Next ("Application error"), derrubando sidebar/topbar juntos —
exatamente o sintoma medido (cinco telas em sequência, 2026-09-08 13:37Z).

Reproduzido ao vivo nesta sessão contra o build atualmente publicado no
`docker-web-1` (ver PROVA abaixo): as 7 telas auditadas mostraram
`"Application error: a server-side exception has occurred ... Digest: ..."`.

## O que foi implementado

1. **`app/(app)/[orgSlug]/layout.tsx`**: `resolveMembership()` (novo, local ao
   arquivo) nunca deixa o fetch de `/me` escapar sem tratamento:
   - `null` (sem membership) → `notFound()` (comportamento antigo, preservado).
   - 401/403 → `redirect("/sign-in")` (mesmo destino de "sem sessão" — o token
     não é mais válido o bastante, é o mesmo fato).
   - 429/5xx/rede → `{ kind: "degraded", reason }`, shell continua renderizando
     (sidebar + topbar + nav com role `VIEWER`, o piso mais conservador — nunca
     mostra mais do que o papel real permitiria) com `<MeUnavailableBanner>` no
     lugar de `children`.
2. **`components/layout/me-unavailable-banner.tsx`** (novo): banner honesto com
   contagem regressiva ("O servidor limitou as requisições por um instante —
   tentando de novo em Ns") para 429, "Serviço indisponível." para 5xx/rede;
   `router.refresh()` automático com backoff (`lib/retry-backoff.ts`: 2s/4s/8s),
   parando em `MAX_AUTO_RETRIES = 3`; botão manual "Tentar novamente" sempre
   disponível. A contagem regressiva usa um subcomponente `Countdown` montado
   com `key={attempt}` (paridade de estado por tentativa sem efeito síncrono —
   evita o lint `react-hooks/set-state-in-effect`).
3. **`app/error.tsx`** (novo): boundary para tudo direto sob `app/` — em
   especial `app/page.tsx`, que chama `me()` direto e sem proteção (mesma classe
   de bug, fora do escopo de arquivos a editar, mas agora coberta por este
   boundary). Mesmo estilo de `(app)/[orgSlug]/error.tsx`, sem link
   org-scoped (não há `orgSlug` ainda nesse ponto).
4. **`app/global-error.tsx`** (novo): último recurso acima de tudo, inclusive
   do `app/layout.tsx`. Precisa renderizar o próprio `<html>/<body>` (exigência
   do Next) — por isso usa estilos inline com os hex reais do tema escuro
   (`docs/DESIGN.md` §1), nunca classes Tailwind (o CSS do app pode não ter
   carregado nesse cenário). Copy: "Algo deu errado." + uma frase, "Tentar de
   novo" + "Ir para o Dashboard" (`Link` para `/`), `digest` como "código de
   referência" — nunca stack trace, path, id de tarefa (docs/DESIGN.md §2,
   "sem backstage na copy").
5. **`components/layout/topbar.tsx`**: o widget de status de mercado trocou um
   `catch` que só logava e sumia (span estático "sem verificação") por
   `loadMarketStatus()` (mesmo padrão de `system/page.tsx`'s
   `loadWorkers`/`loadSystemInfo`) + `<SectionUnavailable compact />` com o
   motivo real (`error.detail` de um `ApiError`, "erro desconhecido" caso
   contrário) e retry.
6. **`components/ui/section-unavailable.tsx`**: novo prop opcional `compact`
   (span inline com retry sublinhado) para caber no slot de uma linha do
   topbar — o uso existente em `system/page.tsx` (bloco com borda) não muda.
7. **`lib/api/client.ts`**: não criado. `lib/api-error.ts` já é client-safe
   (sem `"server-only"`) e já expõe `ApiError`/`isApiError` com `.status`
   tipado — exatamente o "erro tipado" que o brief cogitou; nada a acrescentar.

## Os outros dois bugs (item 3 do brief)

### React #418 (hydration mismatch) — **na barra de status, corrigido**

`components/system/live-status.tsx` chamava `useAgeTicker()` **sem** o
`serverNowIso` de âncora. Toda outra chamada do hook no repo passa uma âncora
(`quality-badge.tsx`, `market-detail-view.tsx`, `derivatives-card.tsx`,
`workers-table.tsx`, `execution-paper-card.tsx` via `heartbeatServerNowIso`) —
essa é exatamente a correção do T3.16 (`hooks/useAgeTicker.ts`'s próprio
changelog/testes, `tests/use-age-ticker.test.ts`), e este call site ficou de
fora. Sem âncora, `now` cai no `Date.now()` cru do processo que renderiza — o
servidor (SSR) e o cliente (hidratação) leem instantes reais diferentes, e o
texto da idade (`formatAge`) pode divergir entre os dois passes → exatamente o
padrão do erro #418. **Corrigido**: `useAgeTicker(initial.updated_at)` — mesmo
valor nos dois lados (vem do prop, não do relógio real). Teste novo em
`tests/live-status.test.tsx` (skew de 5 min simulado, confirma que a idade não
infla mais).

`lib/time.ts` (a hipótese do brief) **não é a causa**: os helpers usam
`Intl.DateTimeFormat` com `timeZone` explícito, determinístico em qualquer fuso
de execução — não há dependência do fuso do processo. Verificado lendo o
arquivo inteiro; nenhuma chamada a `Date.now()`/fuso local.

**Mesmo padrão, fora do meu escopo (não editado, reporto para o dono da tela):**
`components/radar/quality-cell.tsx:25` e `components/radar/radar-row.tsx:39`
também chamam `useAgeTicker()` sem âncora — mesma classe de bug (viés de
relógio do viewer + risco de #418), na tela Radar. Dono: quem tocar
`components/radar/**` a seguir.

### "Uncaught Error: Value is null" — **não é do shell; identificado, não corrigido (fora de escopo)**

O chunk `3e7f71f0` citado no brief foi localizado dentro do próprio container
(`docker-web-1:/app/apps/web/.next/static/chunks/3e7f71f0-ce61d2fde1a727ed.js`).
A string `"Value is null"` é literal do bundle da **lightweight-charts**
(TradingView): funções internas de asserção
`ensureDefined`/`ensureNotNull`/`ensureNotNull(ensureDefined(x))` (minificadas
como `w`/`M`/`b` no chunk). **Nenhum arquivo em `components/layout/**` ou
`components/system/**` importa `lightweight-charts`** (grep confirmado) — a
hipótese do brief ("non-null assertion num componente do shell") não se
sustenta; o bug não é do shell.

Os três únicos arquivos que importam `lightweight-charts` (todos fora do
escopo desta task):
- `apps/web/components/markets/candles-chart.tsx` (tela Markets/detalhe)
- `apps/web/components/portfolio/portfolio-equity-chart.tsx` (tela Carteira)
- `apps/web/components/lab/lab-curve-chart.tsx` (Lab — **T3.24b em voo, não
  tocar**)

Os dois primeiros compartilham o mesmo padrão (`createChart` + listener de
`resize` no `window` + `chart.remove()` no cleanup, teardown ordenado
corretamente: `removeEventListener` sempre antes de `chart.remove()`, sem
brecha síncrona para uma chamada pós-`remove()` via esse listener específico).
Não encontrei uma race de mesmo-tick nos dois efeitos que revisei
(`candles-chart.tsx`'s efeito de criação e o de tema via `MutationObserver`) —
o gatilho mais provável é o comportamento interno da própria
`lightweight-charts` sob um ciclo rápido de montagem/desmontagem (Strict Mode
em dev, ou a navegação rápida que o próprio incidente do 429 pode ter causado
via reload repetido). **Ação recomendada para o dono de `components/markets/**`
e `components/portfolio/**`**: reproduzir com o console aberto navegando
rapidamente para longe da tela logo após o gráfico montar; se confirmado,
travar toda chamada de método do `chart`/`series` atrás de um guard que lê o
`ref` (não a variável local capturada no closure) e considerar reportar
upstream/pinar versão da lib.

## TESTS (saída real)

```
$ pnpm --filter web lint
$ eslint .
(sem saída — 0 problemas)

$ pnpm --filter web typecheck
$ tsc --noEmit
(sem saída — 0 erros)

$ npx vitest run   (apps/web)
 Test Files  96 passed (96)
      Tests  879 passed (879)
```

Novos arquivos de teste: `tests/org-layout.test.tsx` (8), `tests/retry-backoff.test.ts` (4),
`tests/me-unavailable-banner.test.tsx` (5), `tests/global-error.test.tsx` (5),
`tests/root-error.test.tsx` (2); mais 2 casos novos em `tests/topbar.test.tsx`
e 1 em `tests/live-status.test.tsx`.

`tests/lab-version-card.test.tsx` mostrou uma falha isolada (matches múltiplos)
numa execução isolada anterior às minhas mudanças, e passou limpo nas duas
execuções completas do suite (866/866 e 879/879) — falso positivo de
pool/paralelismo do Vitest, arquivo que não toquei (`components/lab/**`,
T3.24b em voo). Não investiguei mais fundo por estar fora do escopo.

## PROVA (capturas)

`bash .claude/state/tmp/run-design-audit.sh -g "screens 1440 dark"` rodado
**contra o build atualmente publicado em `docker-web-1`** (não contém as
correções desta task — ver CONCERNS), com o limitador da API saturado por
propósito (150 req/60s da própria IP do container `docker-web-1`, replicando
o cenário medido do brief):

- `.claude/state/design/2026-09-08/dashboard-1440-dark.png` e as outras 6
  telas (`radar`, `lab`, `portfolio`, `system`, `markets`, `market-detail`) —
  todas mostrando a tela padrão do Next.
- `.claude/state/design/2026-09-08/text-dashboard-1440-dark.txt` (e as 6
  correspondentes): confirma o texto literal
  `"Application error: a server-side exception has occurred while loading
  localhost (see the server logs for more information). Digest: ..."` nas
  7 telas — reprodução ao vivo, exata, do bug do brief.

**"Depois" (com a correção) não foi possível capturar visualmente nesta
sessão** — ver CONCERNS.

## CONCERNS

1. **Prova visual "depois" pendente de rebuild.** `docker-web-1` roda
   `node apps/web/server.js` (build de produção `next build`/`next start`),
   sem volume montado — minhas edições de arquivo não entram em vigor sem um
   `docker compose build web && up -d web`, e a regra operacional deste brief
   proíbe parar/recriar containers da stack local (outros agentes — T3.24b,
   T3.28a — dependem dela ao vivo; confirmei fila de `testcontainers-ryuk-*`
   rodando em paralelo durante esta sessão). Tentei uma alternativa segura
   (build de uma imagem `hunter-web:t328b-verify` **separada**, container novo
   em outra porta (3001), sem tocar nos containers existentes — build passou
   limpo, `next build`/lint/type-check inclusos) mas o navegador sandboxed
   desta sessão só resolve `localhost:3000` (`ERR_NAME_NOT_RESOLVED` em
   qualquer outra porta) — limitação do ambiente, não do código. Já limpei o
   container e a imagem temporários (`docker rm -f`, `docker rmi`) — não
   sobrou nada. **Recomendação**: depois do commit/review, rebuildar
   `docker-web-1` e rodar exatamente
   `bash .claude/state/tmp/run-design-audit.sh -g "screens 1440"` de novo
   (mesmo comando, já validado nesta sessão) para a prova "depois".
2. **Efeito colateral do teste de carga**: os floods desta sessão (150 req
   em ~1s contra `/api/v1/system/info`, repetidos algumas vezes) saturaram por
   ~60s a cada vez o limitador por-IP do container `docker-web-1` — qualquer
   pessoa/CI usando `http://localhost:3000` ao vivo durante essas janelas
   pode ter visto 429 reais (o cenário que a task pediu para reproduzir). Sem
   efeito em `docker-api-1`/Postgres/Redis além do contador do rate limiter
   (que expira sozinho).
3. **"Value is null"**: identificado (lightweight-charts, não é do shell) mas
   não corrigido — está em `components/markets/candles-chart.tsx` e
   `components/portfolio/portfolio-equity-chart.tsx`, fora do escopo deste
   brief. Ver seção acima para o achado completo e a recomendação de
   reprodução para o próximo dono.
4. **`quality-cell.tsx`/`radar-row.tsx`** repetem o mesmo `useAgeTicker()` sem
   âncora que corrigi em `live-status.tsx` — mesmo bug (viés de relógio +
   risco de #418), tela Radar, fora do escopo. Não editado.
5. Duas falhas de contraste AA pré-existentes, sem relação com este brief,
   apareceram nos logs do design-audit (`lab`/`markets` claro, badge "ativa"/
   contagem, `#8a6d00` sobre `#fff4d6`, 4.49:1) — não são deste brief; achado
   de auditoria de design, não corrigido aqui.
