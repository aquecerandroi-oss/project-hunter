# Notas T3.51 — Lab: abas "Concluídas/Abertas/Pendentes/Todas" não faziam nada

**Agente:** frontend-specialist. **Data:** 2026-09-08, ~17:50–20:45 BRT (20:50–23:45 UTC). **Base:** `main` @ `dfe6116`. **Status: DONE (parte local dos entregáveis 1–3); aguardando o orchestrator rebuildar `web` e rodar a prova final local + VPS.**

## 1. Hipótese confirmada (e refinada) — os dois runs Playwright pedidos

### 1a. Baseline, `AutoRefresh` ativo (repro original do orchestrator, `.claude/state/tmp/lab-tabs-repro.mjs`, rodado de `tests/e2e/`)

```
URL0 http://localhost:3000/ever/lab
tabs: [ 'Concluídas (159)', 'Abertas (0)', 'Pendentes/sem entrada (41)', 'Todas (200)' ]
selected0: [ 'true', 'false', 'false', 'false' ]
URL1 http://localhost:3000/ever/lab
selected1: [ 'true', 'false', 'false', 'false' ]      <- clique em "Abertas": nada mudou
URL2 http://localhost:3000/ever/lab
selected2: [ 'true', 'false', 'false', 'false' ]      <- clique em "Todas": nada mudou
```

Reproduz exatamente a reclamação do Everton: clique não muda nada, nem a URL nem `aria-selected`.

### 1b. Mesmo repro com `AutoRefresh` neutralizado (sem tocar o container: `document.visibilityState` forçado para `"hidden"` via `page.addInitScript`, exatamente o guard que `AutoRefresh` já tinha) — script `.claude/state/tmp/lab-tabs-repro-norefresh.mjs`

```
URL0 http://localhost:3000/ever/lab
selected0: [ 'true', 'false', 'false', 'false' ]
URL1 http://localhost:3000/ever/lab        <- clique em "Abertas": URL não mudou
selected1: [ 'false', 'true', 'false', 'false' ]   <- mas aria-selected mudou desta vez
URL2 http://localhost:3000/ever/lab        <- clique em "Todas": URL não mudou
selected2: [ 'false', 'false', 'false', 'true' ]
```

**Isto contraria a previsão literal do brief** ("se a URL passar a carregar `?state=open`, a corrida está confirmada"): a URL nunca carrega `?state=` em nenhum dos dois cenários, com ou sem `AutoRefresh`. Ou seja, a corrida com o `AutoRefresh` é real e vale corrigir, mas **não é a única nem a causa raiz principal**.

### 1c. Diagnóstico mais fundo (instrumentação extra, além do que o brief pediu, porque 1b não bateu com a hipótese)

Repeti o clique com instrumentação em três camadas independentes, todas simultâneas num mesmo run (session Clerk refrescada a cada tentativa — o storage state expira em ~1 navegação nesta VPS de teste):

- `history.pushState`/`replaceState` monkey-patched via `addInitScript` → **nunca chamado** no clique.
- `window.fetch` monkey-patched via `addInitScript` → **nenhum fetch novo** no clique (só os 6 prefetches da sidebar, que já tinham acontecido antes).
- `context.route("**/*", ...)` catch-all (camada do Chromium, independente do JS da página) → **nenhuma requisição** no clique.

```
BEFORE: ['... aria-selected="true" ...', '... aria-selected="false" ...' x3]
=== clicking Abertas ===
AFTER:  ['... aria-selected="false" ...', '... aria-selected="true" ...', ...]
```
(sem nenhum PUSHSTATE/FETCH/ROUTE logado entre "BEFORE" e "AFTER")

**Conclusão:** o `<button onClick={() => startTransition(() => router.push(hrefs[segment]))}>` às vezes chegava a re-renderizar `aria-selected` localmente (uma transição React que nunca commitava de verdade uma navegação), mas em NENHUM caso tocava `window.location`, disparava um `history.pushState` ou um fetch RSC. Ou seja: o problema não era só o `AutoRefresh` correndo atrás de um `push` que funcionava — o `push` em si nunca produzia uma navegação real nessa página, com botão. Isso bate com dois erros `pageerror: Error: Value is null` (lightweight-charts, linhagem T3.31, já conhecidos e fora de escopo) presentes em toda carga da página — plausível que uma exceção não capturada durante o commit quebre a transição do clique sem deixar rastro, mas não persegui a causa exata do Next.js/React porque é irrelevante para a correção: um `<a href>` real funciona mesmo que a transição JS nunca rode, que é exatamente o pedido do item 1 do brief.

## 2. O que foi implementado

### 2.1 `apps/web/components/lab/lab-segment-tabs.tsx`
Cada aba virou um `<Link href={hrefs[segment]} role="tab" aria-selected={...}>` (era `<button onClick={() => router.push(...)}>`). `state` (prop vindo do servidor) continua sendo a única fonte de verdade para qual aba está selecionada. Feedback de pendência mantido de forma barata: `useLinkStatus()` (Next 15) dentro de cada `<Link>`, um marcador `sr-only` por aba — sem estado compartilhado/elevado entre abas (o `isPending` global antigo, do `useTransition` do botão, foi removido).

### 2.2 `apps/web/components/lab/lab-signal-pager.tsx`
"Anterior"/"Próxima" viraram `<Button asChild><Link href={...}>` quando há href (ou um `<Button disabled>` simples quando não há — não dá pra ter um link sem destino). "Por página" continua um `<select onChange={...router.push...}>` — não dá pra ser um `<a>`, é a exceção que o próprio brief previu ("if they use router.push").

### 2.3 `apps/web/components/auto-refresh.tsx` + `apps/web/lib/auto-refresh-interval.ts`
`router.refresh()` agora passa por `startTransition` e três guards antes de disparar (função pura `shouldSkipAutoRefreshTick`, testável isolada):
1. `document.visibilityState !== "visible"` → pula (já existia).
2. um `refresh()` anterior desta mesma instância ainda não comitou (`isPending` do próprio `useTransition`) → pula.
3. `window.location.href` mudou desde o último tick (uma navegação acabou de acontecer) → pula esse tick e reinicia a janela de espera.

**Desvio deliberado do texto literal do brief:** ao invés de `usePathname()`/`useSearchParams()`, uso `window.location.href` lido direto dentro do próprio `setInterval`. Motivo: `AutoRefresh` é montado cru em várias páginas Server Component que não são minhas (`dashboard`, `markets`, `market/[exchange]/[symbol]`, `opportunities`, `portfolio`, `system` — arquivos fora do escopo deste brief e alguns de dono T3.44d/T3.46c). `useSearchParams()` exige `<Suspense>` ao redor de quem o chama (regra do Next 15 para não perder otimização estática) — adotar os hooks do brief à risca teria me obrigado a editar todas essas páginas só para envolver `<AutoRefresh>` num `<Suspense>`, o que violaria "arquivos exatos" e "não tocar" nos donos de T3.44d/T3.46c. `window.location.href` é uma API do browser sem esse requisito e cobre exatamente o mesmo evento (a URL mudou).

## 3. Testes (Vitest)

Arquivos tocados: `apps/web/tests/lab-segment-tabs.test.tsx`, `apps/web/tests/lab-signal-pager.test.tsx`, `apps/web/tests/lab-signals-table.test.tsx` (assertion mudou de `pushMock` para `toHaveAttribute("href", ...)`), `apps/web/tests/auto-refresh.test.tsx` (+ testes novos do guard de navegação e da função pura).

```
$ pnpm exec vitest run tests/lab-segment-tabs.test.tsx tests/lab-segment-tabs-distinct-operations-warning.test.tsx tests/lab-signal-pager.test.tsx tests/auto-refresh.test.tsx
 Test Files  4 passed (4)
      Tests  26 passed (26)

$ pnpm exec vitest run tests/lab-signals-table.test.tsx tests/lab-signals-table-grouping.test.tsx tests/lab-page.test.tsx tests/lab-totals-card-in-table.test.tsx
 Test Files  4 passed (4)
      Tests  44 passed (44)

$ pnpm exec vitest run   # suíte inteira do @hunter/web
 Test Files  2 failed | 111 passed (113)
      Tests  2 failed | 1069 passed (1071)
```
As 2 falhas (`markets-table-visibility.test.tsx`, `org-layout.test.tsx`) são timeout de 5s por contenção de CPU rodando a suíte inteira de uma vez (jsdom criado 113x) — não tocam nenhum arquivo desta tarefa nem `AutoRefresh`. Rodadas isoladas:
```
$ pnpm exec vitest run tests/markets-table-visibility.test.tsx tests/org-layout.test.tsx --testTimeout=20000
 Test Files  2 passed (2)
      Tests  11 passed (11)
```
Pré-existentes, não relacionadas.

## 4. Lint / Typecheck

```
$ pnpm lint
@hunter/web:lint: ✖ 2 problems (0 errors, 2 warnings)   <- os 2 warnings são arquivos que eu não toquei (lab-page.test.tsx, ws.test.ts, > 350 linhas, pré-existentes)
```
(Achado durante o processo: as novas regras `react-hooks/refs`/`react-hooks/purity` do ESLint bloquearam meu primeiro rascunho do `AutoRefresh` — `ref.current = x` e `useRef(Date.now())` direto no corpo do componente. Corrigido: a escrita do ref foi movida para dentro de um `useEffect`, e `Date.now()` só é chamado dentro do próprio callback do `setInterval`/efeito, nunca durante o render.)

```
$ pnpm typecheck
@hunter/web:typecheck   -> passa (sem saída de erro)
@hunter/e2e:typecheck   -> falha, mas só em tests/e2e/design-audit.audit.ts (arquivo pré-existente, não tocado por mim, fora do escopo deste brief; 9 erros de `exactOptionalPropertyTypes`/optional chaining, linhagem de outra tarefa)
```
Confirmado isolado: `cd apps/web && pnpm exec tsc --noEmit` → sem saída (limpo). `cd tests/e2e && pnpm exec tsc --noEmit | grep lab-tabs` → sem saída (meu arquivo novo não introduz nenhum erro).

## 5. Repro Playwright permanente (deliverable 3, arquivo novo)

`tests/e2e/lab-tabs-click.audit.ts` + `tests/e2e/lab-tabs-click.config.ts` (mesmo padrão de `design-audit.audit.ts`/`ws-disconnect-repro.audit.ts`: reaproveita o storage state do design-audit, `testMatch` restrito ao próprio arquivo). Roda o fluxo completo do item 3: clica "Abertas" → espera `?state=open` na URL → clica "Todas" → espera `?state=all` → espera 30s (>= 3 ticks do `AutoRefresh` no default de 12s) → confirma que ainda está em "Todas".

Rodado agora, **antes** do rebuild (esperado falhar, prova que o repro é real e vai virar a prova positiva depois do rebuild):
```
$ cd tests/e2e && E2E_BASE_URL=http://localhost:3000 pnpm exec playwright test -c lab-tabs-click.config.ts --timeout 90000
URL0 http://localhost:3000/ever/lab
tabs: [ 'Concluídas (159)', 'Abertas (0)', 'Pendentes/sem entrada (41)', 'Todas (200)' ]
selected0: [ 'true', 'false', 'false', 'false' ]
  x  1 [chromium] › ... T3.51: clicking a /lab segment tab changes ?state= and survives 3 AutoRefresh ticks (14.4s)
  TimeoutError: page.waitForURL: Timeout 10000ms exceeded.
  1 failed
```
Falha exatamente como esperado (o `web` rodando ainda é o código antigo).

## 6. Arquivos exatos para o commit

Modificados:
- `apps/web/components/lab/lab-segment-tabs.tsx`
- `apps/web/components/lab/lab-signal-pager.tsx`
- `apps/web/components/auto-refresh.tsx`
- `apps/web/lib/auto-refresh-interval.ts`
- `apps/web/tests/lab-segment-tabs.test.tsx`
- `apps/web/tests/lab-signal-pager.test.tsx`
- `apps/web/tests/lab-signals-table.test.tsx`
- `apps/web/tests/auto-refresh.test.tsx`

Novos:
- `tests/e2e/lab-tabs-click.audit.ts`
- `tests/e2e/lab-tabs-click.config.ts`

`apps/web/components/lab/lab-signals-table.tsx` (citado no escopo do brief) **não precisou de mudança de código** — ele só repassa os `hrefs` já prontos para `LabSegmentTabs`; só o teste dele (`lab-signals-table.test.tsx`) precisou de ajuste porque a asserção antiga verificava `pushMock`.

## 7. Próximo passo (do orchestrator, não meu)

1. Rebuildar `web` (`docker compose -f infra/docker/docker-compose.yml build web && ... up -d web`, ou o script `compose.sh update` combinado).
2. Refrescar a sessão (`bash .claude/state/tmp/run-design-audit.sh -g signup`).
3. Rodar `cd tests/e2e && E2E_BASE_URL=http://localhost:3000 pnpm exec playwright test -c lab-tabs-click.config.ts` — esperado passar, colar a saída (URLs + contagens).
4. Repetir contra `https://169.58.116.99` (`E2E_BASE_URL=https://169.58.116.99`, com o storage state apontando pra sessão da VPS) para fechar com o Everton.

## 8. Preocupações / pontos de atenção

- O mecanismo exato do Next/React por trás de "o `push` de um botão nunca commitava" não foi identificado até a causa-raiz do framework (não era necessário para a correção, e o tempo gasto tentando isolar via `window.fetch`/`pushState`/`route` já foi considerável). Se o `<Link>` real, por algum motivo eu não tenha antecipado, também não navegar depois do rebuild, o próximo passo de investigação seria capturar o `pageerror` exato do lightweight-charts (`Error: Value is null`, T3.31) e verificar se ele derruba a árvore de Fiber durante o commit da transição — mas isso seria escopo de outra tarefa (T3.31), não deste brief.
- A sessão de teste do Clerk (`design-audit-auth.json`) expirou/redirecionou para o sign-in em quase toda tentativa nova nesta sessão de trabalho — tive que rodar `run-design-audit.sh -g signup` umas 10 vezes. Não é um problema do meu código; é o comportamento da sessão de teste em si (não investiguei mais fundo, fora de escopo).
- Não toquei `useRealtime.ts`, `live-status.tsx`, topbar (T3.44d) nem as páginas do radar (T3.46c) — confirmado via `git diff --stat` isolado à minha lista de arquivos.
- Não parei/recriei containers locais; não fiz commit; não toquei `.env*`.
