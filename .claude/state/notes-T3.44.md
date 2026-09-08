# Notas T3.44 — stream em tempo real do navegador e painel "Execução paper" na VPS

Base: `main` em `2df9f679` (working tree local; VPS rodando a imagem `d829546` — sem
diffs entre os dois nos arquivos investigados, confirmado por
`git log --oneline d829546..HEAD -- apps/web/lib/ws.ts apps/web/hooks/useMarketChannels.ts
apps/web/components/system/live-status.tsx apps/web/components/system/execution-paper-card.tsx
apps/api/hunter_api/realtime/endpoint.py apps/api/hunter_api/services/system_status.py
infra/vps/Caddyfile` → vazio). Diagnóstico feito via `ssh hunter-vps` somente leitura:
`docker logs`, `docker exec ... redis-cli` (comandos de leitura), `docker exec ... psql`
(SELECT), `docker exec hunter-web-1 grep` no bundle já buildado, `curl -k` externo contra
`https://169.58.116.99`. Nenhum `docker restart`/`up`/escrita em `.env*`/serviço parado.

## Achado 1 — "tempo real do navegador interrompido" no topbar

**Duas coisas distintas estavam misturadas na mesma leitura do Everton:**

### 1a. "2 exchanges · UNAVAILABLE · 215 mercados" — NÃO é bug, é honesto

- `SELECT * FROM exchanges` na VPS: **duas** linhas, `binance` e `bybit`, ambas
  `status=active` (bybit criada em 2026-09-06, sem worker nunca implantado).
- `hb:market:binance:{0,1,2,3}of4` e `hb:market:spot:binance` no Redis da VPS: todos
  `ws_state=connected`, heartbeats frescos (TTL 25-30s) no momento da checagem
  (2026-09-08 21:31 UTC / 18:31 BRT).
- Não existe nenhuma chave `hb:market:bybit*`.
- `apps/api/hunter_api/services/system_status.py:270-309` (`build_market_status`): monta
  **uma linha por exchange cadastrada** (`repository.list_exchange_codes()`), não uma
  linha por heartbeat encontrado — uma exchange sem worker aparece com
  `ws_state="unavailable"` de propósito (comentário na própria função, linha 271-274).
- `apps/web/components/system/live-status.tsx:33-35` (`worstExchange`) e `:195-215`
  (`CompactStatus`) mostram o **pior `ws_state` real por exchange**, vindo direto do
  backend — nunca sintetizado a partir do estado do socket do navegador
  (`liveFeedDown` só acrescenta a nota entre parênteses, nunca substitui o rótulo da
  exchange).
- **Conclusão:** "UNAVAILABLE" no topbar é o estado real e correto da Bybit (cadastrada,
  sem coletor rodando) — não é o bug relatado, e o requisito do brief ("nunca UNAVAILABLE
  para a exchange quando a exchange está conectada") **já está garantido pelo código
  atual**, com evidência de arquivo:linha acima. Nenhuma mudança feita aqui.
  Recomendação (fora do escopo desta tarefa, para product-designer/backend-specialist):
  a Bybit "active" sem worker confunde quem lê o topbar; considerar `status=planned` na
  tabela `exchanges` até o worker existir, ou uma legenda explícita.

### 1b. A nota "(tempo real do navegador interrompido)" — bug real, corrigido parcialmente

Evidência ponta a ponta, cronológica (BRT = UTC-3):

1. `NEXT_PUBLIC_WS_URL` está corretamente embutido no bundle buildado da VPS:
   `docker exec hunter-web-1 grep -rl 'wss://169.58.116.99' /app/apps/web/.next/static`
   → 3 arquivos, incluindo o chunk da página `/radar`. **Não é o env var ausente.**
2. `curl -k` externo (minha máquina → VPS) contra `https://169.58.116.99/ws` com headers
   de upgrade: `HTTP/1.1 101 Switching Protocols`, certificado autoassinado aceito com
   `-k`. Fecha ~9.5s depois com "authentication timeout" (o timeout de 5s do servidor,
   `apps/api/hunter_api/realtime/endpoint.py:69,218-221`) — **Caddy proxeia `/ws`
   corretamente, TLS termina, handshake chega até a API.**
3. `docker logs hunter-caddy-1`: uma conexão WS **real do Chrome do Everton**
   (`187.101.9.196`, `Chrome/152`, `Origin: https://169.58.116.99`) em
   `2026-09-08T21:16:54.299Z` (18:16:54 BRT) recebeu `status:101` e durou
   `duration: 1.813685575` segundos — bem menos que os 5s de timeout de autenticação.
4. `docker logs hunter-api-1 -t`: essa mesma janela mostra `WebSocket /ws [accepted]` +
   `connection open` às 21:16:53.589 e 21:16:54.299 (duas instâncias de `LiveStatus`
   provavelmente montadas na mesma página — compact no topbar + full em alguma seção —
   cada uma abrindo seu próprio socket via `useMarketChannels`/`RealtimeClient`), e
   **nenhuma linha de log** nos 2h seguintes para `token_rejected`, `ws_auth_unavailable`,
   `ws_channel_denied`, `ws_connection_cap_reached`, `ws_idle_timeout`,
   `ws_membership_revoked`, `ws_principal_gone` ou `ws_revalidation_failed`.
5. Nenhuma requisição nova a `.../jwks.json` nessa janela (cache de 3600s
   `apps/api/hunter_api/auth/jwks.py:45` ainda válido de uma leitura 9s antes) — não dá
   para diferenciar, só pelos logs, "token nunca chegou" de "token chegou e a chave já
   estava em cache" (ver CONCERNS).

**Causa raiz confirmada por leitura de código (sem precisar do log do servidor):**
`apps/web/lib/ws.ts:103-111` (`RealtimeClient.authenticate()`, código antes da correção)
enviava `{"type":"auth","token":null}` mesmo quando `getAuthToken()` (o `getToken()` do
Clerk chamado no `open` do socket, `apps/web/components/system/live-status.tsx:129`) ainda
não resolvia um token de verdade, **e marcava `status="open"` imediatamente após o
`send()`, sem esperar a resposta do servidor**. Do lado do servidor,
`apps/api/hunter_api/realtime/endpoint.py:226-232` fecha com `4401 "authentication
required"` quando `token` não é uma string válida — **sem nenhum log** (só os ramos de
exceção logam; "authentication required"/"authentication timeout" são silenciosos). Isso
bate exatamente com a duração de ~1.8s observada e a ausência total de log de erro: o mais
provável é uma corrida entre o socket abrir e o `getToken()` do Clerk ainda não estar
pronto (nenhum dos 4 call-sites — `live-status.tsx`, `radar-table.tsx`,
`markets-table.tsx`, `market-detail-view.tsx` — espera `isLoaded` do Clerk antes de
conectar).

**Corrigido nesta tarefa** (`apps/web/lib/ws.ts`, dentro do escopo autorizado
`apps/web/**`):
- `authenticate()` não envia mais `token: null` — se `getAuthToken()` não resolve um
  token, loga `realtime_auth_token_missing` via `@/lib/logger` e fecha o socket
  (reconecta pelo backoff já existente), em vez de mandar um frame inválido silenciosamente.
- `status` só vira `"open"` quando o servidor responde `{"type":"authenticated"}`
  (tratado agora em `handleMessage`), nunca só por ter enviado o frame de auth. Isso torna
  `liveFeedDown` (`live-status.tsx:155`) honesto: para de piscar "conectado" por uma
  fração de segundo antes de um 4401 fechar o socket.

**Não corrigido nesta tarefa (fora do escopo autorizado do brief):** o brief autoriza
tocar `apps/api/hunter_api/routers/stream*.py|system*.py` "se a causa estiver lá" — mas o
gateway WS mora em `apps/api/hunter_api/realtime/endpoint.py` (não existe nenhum
`routers/stream*.py` no repositório) e a limitação de taxa correlata em
`apps/api/hunter_api/middleware/rate_limit.py`; nenhum dos dois está no padrão liberado.
Recomendação para `backend-specialist`: logar `token_missing`/`authentication_required`/
`authentication_timeout`/`malformed_frame`/`unknown_message_type` em
`realtime/endpoint.py` (hoje só alguns ramos de fechamento logam, ver linhas 220,
227-232, 259-260, 279-280) — sem isso, uma repetição deste sintoma volta a exigir leitura
de código em vez de log direto. Também vale confirmar com uma sessão Playwright
autenticada de verdade (não feita aqui: exigiria criar um usuário/sessão na VPS, o que
violaria o modo somente leitura desta tarefa) se `getToken()` do Clerk está de fato
resolvendo `null` nessa corrida, ou se o problema é outro que também fecha em ~1.8s sem
logar (ver CONCERNS).

## Achado 2 — painel "Execução paper" com todos os campos "indisponível"

**Causa raiz confirmada com certeza (reprodução por hash determinístico, não só leitura de
código):**

`apps/web/app/(app)/[orgSlug]/system/page.tsx:92` (antes da correção) selecionava o
worker do painel com `workersLoad.workers.find((worker) => worker.role === "execution")`.
Existem **duas** heartbeats com `role="execution"` na VPS:

- `hb:execution:137f1a8d4f24:1` — heartbeat genérico de liveness que todo
  `WorkerRuntime` escreve, campos `ts`/`last_success`/`errors`/`version` **apenas**
  (confirmado por `HGETALL` real na VPS).
- `hb:execution:paper` — o agregado do execution-worker com os 14 campos T3.13/T3.14
  (`equity`, `kill_switch`, `open_positions`, `paper_autonomy`, etc., confirmado por
  `HGETALL` real na VPS).

`apps/api/hunter_api/services/system_status.py:266` (`scan_heartbeats`) ordena a lista por
`(role, instance)`. `apps/api/hunter_api/services/system_status.py:97-107`
(`anonymize_instance`) transforma a instância do heartbeat genérico (`137f1a8d4f24:1`,
contém `:`) num hash hex minúsculo de 12 caracteres — verificado:
`sha256("execution:137f1a8d4f24:1")[:12] = "3f997610fcc8"`. Qualquer dígito hex minúsculo
(`0-9a-f`) ordena **antes** de `"paper"` em ASCII (`f` < `p`), então o heartbeat genérico
**sempre** vem primeiro na lista — `.find(role === "execution")` pegava
**determinística e permanentemente** o heartbeat errado. `worker` chegava não-nulo (por
isso não caía no estado "sem heartbeat"), mas nenhum dos campos T3.13 existe nesse
heartbeat genérico → todos undefined → `ExecutionPaperCard` (que já fazia "indisponível"
por campo corretamente, `apps/web/components/system/execution-paper-card.tsx:32-68`)
mostrava "indisponível" em Autonomia, Patrimônio, Posições, Pedidos, Proteções, Atraso,
Idade do MTM e kill switch — exatamente o relatado. **Não é** um desalinhamento de forma
entre T3.29 (`mark_quality`/`marked_positions`) e o parser: esses dois campos novos
existem no hash real e não são lidos por este card (não fazem parte do contrato dele) e
não quebram nada.

**Corrigido nesta tarefa:** `page.tsx:92-108` agora filtra
`worker.role === "execution" && worker.instance === "paper"`, com comentário explicando a
ordenação hex-vs-"paper". `ExecutionPaperCard` em si não precisou de nenhuma mudança — já
fazia "indisponível" por campo, nunca para o bloco inteiro (o brief item 3 já estava
implementado ali).

## FILES

Modificados (todos dentro de `apps/web/**`, nada em `.env*`/`services/**`/`obsidian/**`/
`components/lab/**`):

- `apps/web/lib/ws.ts` — `authenticate()` não envia token nulo, loga e fecha; `status`
  só vira `"open"` após `{"type":"authenticated"}` do servidor (`handleMessage`).
- `apps/web/tests/ws.test.ts` — `FakeWebSocket.simulateMessage`; teste atualizado (não
  assume mais `"open"` antes da confirmação do servidor); dois testes novos (honestidade
  do status; token ausente não é enviado, loga e fecha).
- `apps/web/app/(app)/[orgSlug]/system/page.tsx` — seleção do worker do
  `ExecutionPaperCard` por `role + instance`, com comentário da causa raiz.
- `apps/web/tests/system-page.test.tsx` — teste novo com os dois heartbeats
  `role="execution"` na ordem real (hash antes de `"paper"`), provando que o agregado
  certo é escolhido e nenhum campo mostra "indisponível".

Nenhum arquivo de `apps/api/**`, `infra/vps/Caddyfile`, `services/**` ou `.env*` foi
tocado.

## TESTS (saída real)

```
$ cd apps/web && npx vitest run tests/ws.test.ts tests/system-page.test.tsx tests/execution-paper-card.test.tsx tests/live-status.test.tsx tests/topbar.test.tsx
 Test Files  5 passed (5)
      Tests  40 passed (40)
   Duration  7.75s

$ cd apps/web && npx vitest run
 Test Files  106 passed (106)
      Tests  966 passed (966)
   Duration  86.07s

$ pnpm --filter @hunter/web lint
✖ 1 problem (0 errors, 1 warning)   # tests/lab-page.test.tsx, 377 linhas — pré-existente, não tocado nesta tarefa

$ pnpm --filter @hunter/web typecheck
(sem saída — sucesso)
```

Nenhum teste de `apps/api` foi tocado (nenhuma mudança em `apps/api/**`), então
`uv run pytest` não foi executado para este escopo.

## CONCERNS

1. **Não confirmei 100% por que `getToken()` falha/demora** na corrida do `open` do
   socket — só por leitura de código + timing dos logs da VPS (fechamento em ~1.8s,
   silencioso, batendo com o ramo "authentication required"). Confirmar de verdade exigiria
   uma sessão Playwright autenticada de verdade contra a VPS capturando frames WS via CDP,
   o que criaria um usuário/organização reais no Postgres da VPS — decidi não fazer isso
   porque o brief pede "somente leitura". Se o sintoma persistir após o deploy desta
   correção (o socket deve parar de mentir "aberto", mas pode continuar falhando a
   autenticação e só reconectando honestamente), o próximo passo é essa sessão Playwright
   com log de auditoria/consentimento do Everton, ou pedir para ele abrir o DevTools
   (aba Network → WS) no próprio Chrome dele.
2. **Escopo do brief não bate com a topologia real**: ele autoriza tocar
   `routers/stream*.py|system*.py` "se a causa estiver lá", mas o gateway WS vive em
   `realtime/endpoint.py` (sem `routers/stream*.py` no repo) — não toquei nada em
   `apps/api/**` por isso. Ver recomendação de logging no Achado 1b.
3. **Achado 1a (Bybit "active" sem worker) não é bug desta tarefa**, mas é a causa real do
   texto "UNAVAILABLE" que o brief atribuiu ao stream do navegador — vale um brief
   separado para product-designer/backend-specialist decidir entre `status=planned` na
   tabela `exchanges` ou uma legenda mais clara.
4. Não fiz prova de tela via Playwright na VPS (brief item 4 pede isso "depois que o
   orquestrador fizer o deploy") — deixo para o orquestrador depois do deploy: no topbar,
   `liveFeedDown` deve parar de piscar "conectado" e, se a autenticação do WS continuar
   falhando, a nota "(tempo real do navegador interrompido)" deve ficar estável (não mais
   alternando) e o console do navegador deve mostrar
   `{"level":"warn","msg":"realtime_auth_token_missing",...}` se for esse o motivo; no
   `/system`, o card "Execução paper" deve mostrar Patrimônio/Posições/kill switch reais
   (não mais "indisponível" em bloco).
