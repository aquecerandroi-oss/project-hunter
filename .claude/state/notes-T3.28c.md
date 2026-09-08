# Notas — T3.28c (Server Actions públicas não podem gastar o balde interno da API sem sessão)

## STATUS
DONE

## Achado
`organizations-actions.ts`, `workspaces-actions.ts`, `members-actions.ts` e `invitations-actions.ts`
chamavam `apiFetch` sem checar sessão primeiro. Como `/` é público em `middleware.ts`, um POST não
autenticado carregando um `Next-Action` id chegava até a Server Action, que emitia a chamada real
à API (a API respondia 401 corretamente, mas a requisição já tinha gastado o balde compartilhado
do peer `web`, 6 000/min após T3.28a) — um chamador sem sessão conseguia esgotar o orçamento de SSR
do site. O padrão correto já existia em `markets-actions.ts:44-46` (`getServerSession()` antes de
qualquer chamada).

## Divergência do brief (registrada, não escondida)
O brief cita `apps/web/lib/server/session.ts` como o arquivo do helper de sessão. Esse arquivo não
existe no repo — o helper de sessão real é `apps/web/lib/server/auth.ts` (`getServerSession`,
já usado por `apiFetch`, `markets-actions.ts` etc.). Adicionei `requireSession()` ali, ao lado de
`getServerSession()`, em vez de criar um `session.ts` novo e desnecessário que duplicaria o mesmo
wrapper `server-only` do Clerk. Se o nome `session.ts` for uma convenção pretendida para o futuro,
sinalizar para um brief de rename.

`system-actions.ts::refreshReadiness()` NÃO foi tocado: `ready()` (`lib/api/system.ts`) é
deliberadamente não-autenticado por design (`GET /ready` — probe de infra, documentado no próprio
arquivo como "plain, unauthenticated fetch mirrors what an infra probe does"), não usa `apiFetch`
e não é o padrão descrito no achado. `anomalies-actions.ts`, `opportunities-actions.ts`,
`radar-actions.ts` e `lab-actions.ts` já seguiam o padrão de `markets-actions.ts` (checagem de
sessão antes de qualquer chamada) — nenhuma mudança necessária ali.

## FILES
Modificados:
- `apps/web/lib/server/auth.ts` — novo `requireSession()` (alias com propósito explícito sobre
  `getServerSession()`, doc explicando o achado T3.28c/T3.28a).
- `apps/web/lib/api/types.ts` — novo `unauthenticatedProblem()` (Problem RFC 9457 sintético,
  `status: 401`, nunca chega à API).
- `apps/web/lib/api/organizations-actions.ts` — `createOrganization` e `updateOrganization` chamam
  `requireSession()` depois da validação zod e antes de `apiFetch`.
- `apps/web/lib/api/workspaces-actions.ts` — `putOnboarding` idem.
- `apps/web/lib/api/members-actions.ts` — `updateMemberRole` e `removeMember` idem.
- `apps/web/lib/api/invitations-actions.ts` — `createInvitation`, `revokeInvitation` e
  `acceptInvitation` idem (a checagem de token/shape do `acceptInvitation` continua rodando
  primeiro, sem sessão, exatamente como já fazia — só o `apiFetch`/`getOrganization` reais passam
  a exigir sessão).
- `docs/SECURITY.md` §5 — uma linha nova logo após a explicação do rate limiting, citando
  `requireSession()` e o achado T3.28a.
- `apps/web/tests/invitations-actions.test.ts` — mock de `requireSession` adicionado; novo bloco
  de testes cobrindo `createInvitation`/`revokeInvitation`/`acceptInvitation` sem sessão.

Criados:
- `apps/web/tests/organizations-actions.test.ts`
- `apps/web/tests/workspaces-actions.test.ts`
- `apps/web/tests/members-actions.test.ts`

Não tocados (fora do escopo, conforme o brief): `apps/web/components/lab/**`,
`app/(app)/[orgSlug]/lab/**`, `lib/api/lab.ts` (T3.24b); `app/**/layout.tsx`, `app/global-error.tsx`,
`components/shell/**` (T3.28b); `system-actions.ts` (não é o padrão do achado, ver acima).

## TESTS

`pnpm --filter web typecheck`:
```
$ tsc --noEmit
```
(saída vazia — sem erros)

`pnpm --filter web lint`:
```
C:\dev\project-hunter\apps\web\app\global-error.tsx
  66:13  error  Do not use an `<a>` element to navigate to `/`. ... @next/next/no-html-link-for-pages  (x3)

C:\dev\project-hunter\apps\web\components\lab\lab-signals-table.tsx
  68:8  warning  Function 'LabSignalsTable' has too many statements (21). Maximum allowed is 20  max-statements

C:\dev\project-hunter\apps\web\components\layout\me-unavailable-banner.tsx
  35:7  error  Error: Calling setState synchronously within an effect can trigger cascading renders ...

✖ 5 problems (4 errors, 1 warning)
```
Nenhum dos arquivos que editei aparece nessa lista. Os 3 arquivos com erro/aviso
(`app/global-error.tsx`, `components/lab/lab-signals-table.tsx`, `components/layout/me-unavailable-banner.tsx`)
são pré-existentes e pertencem a escopos de outros agentes em voo (`app/global-error.tsx` é
explicitamente T3.28b; `lab-signals-table.tsx` é T3.24b) — não modifiquei nenhum deles.

`pnpm --filter web test -- tests/organizations-actions.test.ts tests/workspaces-actions.test.ts tests/members-actions.test.ts tests/invitations-actions.test.ts tests/markets-actions.test.ts`
(a flag de arquivo do vitest acabou rodando a suíte inteira mesmo assim — 96 arquivos):
```
 Test Files  96 passed (96)
      Tests  879 passed (879)
   Start at  11:18:34
   Duration  133.65s
[exited with code 0]
```
Uma primeira tentativa dessa mesma suíte (minutos antes) mostrou 17 falhas isoladas em
`tests/lab-signals-table.test.tsx`, `lab-signal-panel.test.tsx`, `lab-page.test.tsx` e
`lab-totals-card-in-table.test.tsx`, todas com `ReferenceError: panelOpen is not defined` em
`components/lab/lab-signals-table.tsx:165` — consistente com uma edição concorrente do agente
T3.24b nesse mesmo arquivo compartilhado, não com nada que toquei. A segunda execução, poucos
minutos depois, passou 100% (879/879), incluindo os 4 arquivos de teste novos/alterados deste
brief.

## CONCERNS
- O brief nomeia `lib/server/session.ts` como o arquivo do helper; esse arquivo não existe —
  usei `lib/server/auth.ts` (o wrapper de sessão real) e documentei a divergência acima. Se havia
  intenção de renomear `auth.ts` para `session.ts` em outro brief, isso ainda não aconteceu e pode
  gerar confusão futura.
- `refreshReadiness()` (`system-actions.ts`) continua sem guard de sessão, de propósito: `ready()`
  é uma probe de infra deliberadamente pública (comentário no próprio `lib/api/system.ts`) e não usa
  `apiFetch`. Sinalizando explicitamente para o security-reviewer confirmar que este não é o mesmo
  padrão de risco do achado (não consome o balde da mesma forma que uma Server Action com corpo
  arbitrário e `Next-Action` id).
- Vi uma falha transitória de 17 testes em arquivos de `lab-*` durante uma corrida de teste,
  causada por edição concorrente de outro agente (T3.24b) no mesmo arquivo `lab-signals-table.tsx`
  compartilhado — não é uma regressão minha; a suíte voltou a passar 100% na execução seguinte.
  Reportando para que o dono de T3.24b esteja ciente do estado transitório observado.
- Não toquei `markets-actions.ts` nem os outros `*-actions.ts` que já seguiam o padrão
  (`anomalies`, `opportunities`, `radar`, `lab`), para respeitar o escopo exato do brief — eles não
  usam o novo `requireSession()`/`unauthenticatedProblem()` compartilhados, então o código ficou com
  dois estilos de "fail closed sem sessão" convivendo (o outcome custom com `reason: "unauthenticated"`
  nesses arquivos, e o `ActionResult`/`unauthenticatedProblem()` nos quatro que editei). Isso é
  consistente com o que já existia antes (os quatro editados não tinham NENHUM guard; os outros já
  tinham o seu próprio). Uma unificação total exigiria tocar arquivos fora do meu escopo.
