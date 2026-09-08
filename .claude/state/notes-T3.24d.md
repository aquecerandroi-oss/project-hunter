# Notas T3.24d — segunda passada da auditoria de design (capturas), 2026-09-08

Base: `main` em `d91fac8`. Sem commit; nenhum código de tela editado (T3.24a está editando `apps/web/**` em paralelo — o que eu capturo é a **imagem em execução** `hunter-web:dev`, construída 2026-09-08 12:29 UTC, antes de qualquer edição da T3.24a chegar ao contêiner). Chaves `CLERK_E2E_*`: carregadas pelo shell dentro do processo do runner (`.claude/state/tmp/run-design-audit.sh`, só as duas linhas `CLERK_E2E_*`), nunca impressas nem gravadas — o único eco é o comprimento (64/50).

## 1. Ambiente (conferido, saída real, 12:3x UTC)

```
$ docker ps --format "{{.Names}} {{.Status}} {{.Ports}}"
docker-web-1   Up About a minute (healthy)  0.0.0.0:3000->3000/tcp      <- reconstruído
docker-api-1   Up About a minute (healthy)  0.0.0.0:8000-8001->8000-8001/tcp
(market/execution/strategy workers healthy; scanner-worker unhealthy há 33h; postgres/redis healthy)

$ curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/sign-in                      -> 200
$ curl -s http://localhost:3000/sign-in | grep -c "clerk.example.com"                        -> 0      (E1 resolvido)
$ curl -H "Sec-Fetch-Dest: document" ... -w "%{http_code} %{redirect_url}" .../sign-in
307 https://measured-stingray-3890.clerk.accounts.dev/v1/client/handshake?...&__clerk_hs_reason=dev-browser-missing   <- instância real
$ curl -s http://localhost:8000/ready                                                        -> {"database":true,"redis":true}
$ docker exec docker-postgres-1 psql ... -c "select version_num from alembic_version;"       -> 0013_replay_runs
$ docker exec docker-web-1 sh -c 'echo $NODE_ENV $HUNTER_ENV'                                -> production development  (/_design continua 404 no contêiner)
```

## 2. Carteira principal de `ever` no banco local (E2 resolvido)

`infra/scripts/open_paper_wallet.py` lido antes: permanente/irreversível por organização, exige `--yes <slug>` + `--actor`, busca USDTBRL na Binance spot e escreve `fx_observations` + carteira + âncora + primeiro ponto da curva numa transação; nunca lê `.env`. Workspace de `ever` no local chama-se `ever` (não `principal`).

```
$ docker exec docker-api-1 python infra/scripts/open_paper_wallet.py --org ever --workspace ever --dry-run
USDTBRL 5.14510000 from Binance spot ticker/24hr (closeTime observed)
opening capital is fixed at R$100000 (directive §1; not a flag)
--dry-run: nothing written

$ docker exec docker-api-1 python infra/scripts/open_paper_wallet.py --org ever --workspace ever --yes ever --actor designer
USDTBRL 5.14520000 from Binance spot ticker/24hr (closeTime observed)
fx_observations: wrote 01a08102-ff61-74ef-b45a-0f60c1f521ac at rate 5.14520000
paper_wallet_opened credited=19435.5904532379 ... portfolio_id=01a08102-fff2-7593-bcad-48a80cf4dbdc rounding_policy=floor_10dp_v1
opened portfolio 01a08102-fff2-7593-bcad-48a80cf4dbdc: R$100000 -> 19435.5904532379 USDT at 5.1452000000 (residual 4E-10)

$ psql ... "select action, actor_type from audit_logs where ... action like 'portfolio.opened%'"
portfolio.opened.confirmed_by | system        (actor_id = operator:designer)
portfolio.opened              | system
```

A Carteira local e a régua do Lab passam a ter dado real quando a sessão existir.

## 3. Sign-up de teste — falhou 2× e parei (regra da tarefa)

Spec: `tests/e2e/design-audit.audit.ts` (descartável). Ajuste feito entre as tentativas: cópia local de `signUpAndOnboard` com `getByRole("button", { name: "Continue", exact: true })`.

**Tentativa 1** (`-g signup`, 11.7 s):

```
Error: locator.click: Error: strict mode violation: getByRole('button', { name: /continue/i }) resolved to 2 elements:
  1) <button ... class="cl-socialButtonsBlockButton ... cl-button__google">  aka getByRole('button', { name: 'Sign in with Google Continue' })
  2) <button ... data-localization-key="formButtonPrimary" class="cl-formButtonPrimary ...">  aka getByRole('button', { name: 'Continue', exact: true })
   at clerk-session.ts:36
```

→ a instância dev do Clerk tem o botão social Google ligado; o helper **compartilhado** `tests/e2e/clerk-session.ts:36,39` (e `signup-onboarding.spec.ts`, que usa o mesmo regex) quebra em strict mode. Achado para o test-engineer, não corrigido aqui.

**Tentativa 2** (`-g signup`, 2.0 min, timeout em `getByLabel(/verification code/i)`). Tela exata (snapshot de acessibilidade do Playwright, `.claude/state/tmp/design-audit-artifacts/.../error-context.md`):

```
heading "Create your account" [level=1]
paragraph: Welcome! Please fill in the details to get started.
button "Sign in with Google Continue with Google"
paragraph: or
  Username        textbox "Username" [active]   placeholder "Enter your username"
  Email address   textbox "Email address"       text: hunter.e2e+clerk_test_design_1788870921517@example.com
  Password        textbox "Password"            placeholder "Create a password"   button "Show password"
button "Continue"
Already have an account? link "Sign in"
Secured by Clerk · Development mode
```

Depois do clique em "Continue" a página **fica no formulário** (o foco vai para `Username`): a instância exige **username + senha** no cadastro; o passo "verification code" nunca aparece. `/sign-in` confirma (texto da página capturada: "Email address or username" + "Password"). Isso contradiz o que `tests/e2e/signup-onboarding.spec.ts:4-12` documenta como pré-requisito da instância ("Email address + email verification code as the sign-up strategy"). Criar conta digitando senha não é algo que eu faça, e a regra da tarefa manda parar na segunda falha — parei. `users` no banco: 0 linhas `hunter.e2e+clerk_test_design_%` (nada foi criado).

**Como destravar (Everton, Clerk Dashboard da instância `measured-stingray-3890`):** Configure → *Email, phone, username*: `Username` desligado (ou opcional), `Password` desligado (ou opcional), `Email address` obrigatório com *verification code* como estratégia; Test mode ligado (já está). Depois, a captura é foreground e em partes (≤ 5 min cada):

```
bash .claude/state/tmp/run-design-audit.sh -g signup
bash .claude/state/tmp/run-design-audit.sh -g "screens 1440 dark"     (idem 1440 light, 768 dark/light, 375 dark/light)
bash .claude/state/tmp/run-design-audit.sh -g "lab interactions"
```

(o script carrega só `CLERK_E2E_PUBLISHABLE_KEY`/`CLERK_E2E_SECRET_KEY` do `.env` para dentro do processo, sem imprimir; alternativa sem script: exportar as duas no shell e rodar `cd tests/e2e && E2E_BASE_URL=http://localhost:3000 pnpm exec playwright test -c design-audit.config.ts --timeout 120000 -g ...`).

## 4. O que foi capturado (público, sem sessão)

```
$ bash .claude/state/tmp/run-design-audit.sh -g public
[design-1440-dark]   theme=(none=dark) overflow=false fails=0 families=system-ui sizes=14,24   <- 404 do Next ("This page could not be found.")
[sign-in-1440-dark]  theme=dark  overflow=false fails=0 families=Inter sizes=12,13,17
[design-1440-light]  theme=(none=dark) overflow=false fails=0 families=system-ui sizes=14,24   <- 404
[sign-in-1440-light] theme=light overflow=false fails=0 families=Inter sizes=12,13,17
  ok 1 › public: /_design and /sign-in 1440 dark+light (15.0s)
```

Arquivos: `.claude/state/design/2026-09-08/sign-in-1440-{dark,light}.png`, `metrics-sign-in-1440-*.json`, `text-sign-in-1440-*.txt`, `design-1440-*.png` (404). Contraste renderizado do `/sign-in` no relatório §"Capturas".

## 5. Arquivos desta rodada

- `.claude/state/review-design-2026-09-08.md` (STATUS, §0 Ambiente, §8 Sign-in, "Capturas", PRÓXIMO PASSO).
- `.claude/state/brief-T3.24-design-{quick-wins,lab,consistency}.md` (uma linha cada, aceite "Tela real").
- `tests/e2e/design-audit.audit.ts` (sign-up local com `exact: true`), `.claude/state/tmp/run-design-audit.sh`.
- `obsidian/04-AGENTS/Product Designer.md` (uma linha).
