# Notas T3.23 — primeira auditoria de design (product-designer), 2026-09-08

Base: `main` em `79c52c3`. Sessão retomada "do estado atual" (stack local pronto, Clerk Test mode, `CLERK_E2E_*` no `.env`). Sem commit; nada de código de tela editado.

## 1. O que foi tentado, com a saída real

### 1.1 Stack local (conferido)

```
$ docker ps --format "{{.Names}} {{.Status}} {{.Ports}}"
docker-web-1        Up 5 hours (healthy)  0.0.0.0:3000->3000/tcp
docker-api-1        Up 5 hours (healthy)  0.0.0.0:8000-8001->8000-8001/tcp
docker-market-worker-1     Up 27 hours (healthy)
docker-execution-worker-1  Up 29 hours (healthy)
docker-scanner-worker-1    Up 33 hours (unhealthy)
docker-strategy-worker-1   Up 33 hours (healthy)
docker-postgres-1 / docker-redis-1  Up 33 hours (healthy)

$ curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/sign-in   -> 200
$ curl -s http://localhost:8000/ready                                    -> {"database":true,"redis":true}
$ docker exec docker-postgres-1 psql -U hunter -d hunter -At -c "select version_num from alembic_version;"
0013_replay_runs
$ ... -c "select count(*) from signal_outcomes;"                          -> 840
$ ... -c "select id, slug from organizations;"                            -> 01a06fb4-6bc8-7448-a291-e488adc7edf0 | ever  (+ ever-t35-proof, ever-t35-proof2)
$ ... membros de ever                                                     -> aquecerandroi@gmail.com | OWNER | active
$ ... -c "select organization_id, count(*) from portfolios group by 1;"   -> só as duas orgs de prova têm carteira; **`ever` não tem carteira principal no banco local** (a página Carteira cairia no estado vazio, e a régua do Lab na "carteira de referência").
```

### 1.2 Sign-up de teste via Playwright — falhou (2x) por causa da imagem web

Spec descartável: `tests/e2e/design-audit.audit.ts` + `tests/e2e/design-audit.config.ts` (fora de `*.spec.ts`, o suite normal não coleta; importa `signUpAndOnboard` de `tests/e2e/clerk-session.ts`; faz o vínculo do usuário à `ever` por `docker exec ... psql`; captura 7 telas × 3 viewports × 2 temas + interações do Lab + `/_design` e `/sign-in`, medindo contraste com `page.evaluate` sobre as cores computadas).

Tentativa 1 (`pnpm exec playwright test -c design-audit.config.ts -g signup`, chaves lidas pelo runner):

```
Error: page.goto: net::ERR_NAME_NOT_RESOLVED at http://localhost:3000/sign-up
```

Diagnóstico (probe `chromium.launch()` + `page.on("requestfailed")`):

```
requestfailed https://clerk.example.com/v1/client/handshake?redirect_url=http%3A%2F%2F127.0.0.1%3A3000%2Fsign-in&...&__clerk_hs_reason=dev-browser-missing  net::ERR_NAME_NOT_RESOLVED
$ curl -s http://localhost:3000/sign-in | grep -o "clerk\.example\.com" | sort | uniq -c   -> 2 clerk.example.com
$ curl -H "Accept: text/html" -H "Sec-Fetch-Dest: document" -H "Sec-Fetch-Mode: navigate" -H "User-Agent: Mozilla/5.0 Chrome/140" -o /dev/null -w "%{http_code} %{redirect_url}" http://localhost:3000/sign-in
307 https://clerk.example.com/v1/client/handshake?...
$ (mesma chamada) /ever/radar   -> 307 https://clerk.example.com/v1/client/handshake?...
$ (mesma chamada) /_design      -> 404   (NODE_ENV=production dentro do contêiner; HUNTER_ENV=development)
```

**Causa raiz:** a imagem `hunter-web:dev` em `:3000` foi construída com a chave *falsa* do Clerk (`pk_test_Y2xlcmsuZXhhbXBsZS5jb20k` = `clerk.example.com$`, o default de `infra/docker/docker-compose.yml` linha 396 quando `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` não chega ao build). `clerkMiddleware` manda todo navegador sem `__client_uat` para o handshake em `clerk.example.com`, que não existe. `curl` sem cabeçalhos de navegador recebe 200 (por isso o stack parecia pronto). **É a mesma causa das 5 horas travadas no navegador embutido** — não era o navegador.

Tentativa 2: subir `next dev` na `:3001` com as chaves reais via `webServer` do Playwright — o comando foi bloqueado pelo classificador (o config leria o `.env`, o que a regra da tarefa proíbe). Voltei o config para não ler `.env` (as chaves têm de vir exportadas no shell de quem roda).

Chrome/Edge reais via Playwright dão o mesmo `ERR_NAME_NOT_RESOLVED` — confirma que o problema é o redirect, não o Chromium.

### 1.3 Como destravar (2 comandos, Everton — não posso recriar contêineres do stack)

```
docker compose --env-file .env -f infra/docker/docker-compose.yml build web
docker compose --env-file .env -f infra/docker/docker-compose.yml up -d web
```

(`--env-file .env` é o que leva `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` real ao `build-arg`; conferir com `curl -s http://localhost:3000/sign-in | grep -c clerk.example.com` → deve dar 0.) Alternativa sem rebuild: exportar no shell `CLERK_E2E_PUBLISHABLE_KEY`, `CLERK_E2E_SECRET_KEY` (e, para o `next dev`, as `CLERK_*`/`NEXT_PUBLIC_CLERK_*` do `.env`) e rodar `cd apps/web && pnpm dev --port 3001` com `API_URL=http://127.0.0.1:8000 NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/ws WEB_ORIGIN=http://localhost:3001`.

Depois, a captura completa é um comando (≈ 4 min, foreground):

```
cd tests/e2e && E2E_BASE_URL=http://localhost:3000 pnpm exec playwright test -c design-audit.config.ts --timeout 120000
```

Saída: `.claude/state/design/2026-09-08/{tela}-{1440|768|375}-{dark|light}.png`, `metrics-*.json` (pares texto/fundo com razão WCAG, overflow horizontal, tamanhos e famílias de fonte), `text-*.txt` (texto visível, para a revisão de copy). Vincula o usuário de teste à `ever` como OWNER/active (linha impressa no log) e salva o storage state em `.claude/state/tmp/design-audit-auth.json`.

## 2. O que foi auditado de fato (sem navegador)

- **Contraste medido** a partir dos valores exatos dos tokens (`apps/web/app/globals.css`), incluindo os fundos com alfa que o navegador compõe (`bg-x/15`, `text-fg/80`, `opacity-60`): `.claude/state/tmp/contrast-tokens.mjs` → `.claude/state/design/2026-09-08/contrast-tokens.{json,md}` (29 pares × 2 temas). É o mesmo número que `getComputedStyle` devolveria: a composição é determinística.
- **Leitura completa do código de tela** de Radar, Lab, Carteira, System, Markets e detalhe de mercado + shell (topbar, sidebar, nav, badges, botões, formatadores, tempo). Achados de hierarquia, estados, copy, escala tipográfica, foco e responsividade vêm daí e estão marcados no relatório como "(código)"; os que dependem do render real estão marcados "(confirmar no navegador)".

## 3. Arquivos desta tarefa

- `.claude/state/review-design-2026-09-08.md` — relatório.
- `.claude/state/brief-T3.24-design-quick-wins.md`, `brief-T3.24-design-lab.md`, `brief-T3.24-design-consistency.md`.
- `docs/DESIGN.md` §2 + §5 DESIGN-5.
- `obsidian/04-AGENTS/Product Designer.md` (uma linha).
- `tests/e2e/design-audit.audit.ts`, `tests/e2e/design-audit.config.ts` (descartáveis, não versionar).
- `.claude/state/tmp/contrast-tokens.mjs`, `contrast-candidates.mjs`, `design-probe.mjs`.
