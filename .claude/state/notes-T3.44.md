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

## T3.44b — todo fechamento do gateway WS loga com contador; Bybit vira `planned` bloqueado por schema

Base: `main` em `8770ff4` (o commit `f6d222f` que salvou o brief já estava em cima dele).
Brief: `.claude/state/brief-T3.44b-ws-close-logging-and-bybit-status.md`.

### Item 1 — log + contador para todo fechamento do gateway (feito)

Causa raiz confirmada por leitura de código (Achado 1b acima já apontava): `realtime/endpoint.py`
só logava em alguns ramos de fechamento (`ws_auth_unavailable`, `ws_auth_rejected`,
`ws_connection_cap_reached`, `ws_channel_denied`); os fechamentos por `4401`
("authentication required"/"authentication timeout"), `4400` (frame malformado/tipo
desconhecido) e `4408`/`4409`/`4403` sem exceção nomeada fechavam em silêncio, e um cliente
que derruba o próprio socket antes de mandar o frame de auth (`WebSocketDisconnect` dentro do
`receive_text()` de `_authenticate`/`_serve`) não passava por lugar nenhum — nem por
`close_socket`, porque o socket já tinha ido embora.

**Desenho:** um único ponto de log, `realtime.session.log_ws_closed(websocket, code, reason)`,
chamado (a) de dentro de `close_socket` — cobre todo fechamento que o próprio gateway decide
(`_close` em `endpoint.py` sempre delega a `close_socket`) — e (b) diretamente dos dois pontos
em `endpoint.py` (`_authenticate`, `_serve`) que capturam `WebSocketDisconnect` vindo do
cliente. `authenticated` e `connected_at` (para `duration_ms`) são lidos de
`websocket.state` em vez de passados por parâmetro em cada call site: `mark_connected(websocket)`
carimba `connected_at` uma vez, logo depois de `websocket.accept()` (antes da autenticação —
é exatamente a janela onde o bug original acontecia), e `websocket.state.authenticated = True`
é setado uma vez, em `_authenticate`, só no caminho de sucesso. `client` é
`websocket.client.host` (ou `"unknown"` se ausente, ex.: sockets de teste sem endereço real).

Contador `hunter_ws_closed_total{code}` (Prometheus, `apps/api/hunter_api/metrics.py`, mesmo
registry compartilhado que `hunter_rate_limit_internal_peer_total`), incrementado dentro de
`log_ws_closed` — cobre gateway-iniciado e cliente-iniciado com o mesmo rótulo `code` (para o
cliente, é o código que ele mandou no `websocket.disconnect`, tipicamente `1000`).

**Orçamento de 350 linhas:** `realtime/endpoint.py` já estava em 349 linhas antes desta tarefa.
Para não estourar, `_handshake_allowed`/`_connection_cap`/`_setting` (limites de admissão —
responsabilidade separada de "servir um socket já admitido") saíram para um módulo novo,
`apps/api/hunter_api/realtime/admission.py` (64 linhas), sem mudança de lógica — só
relocação e queda do prefixo `_` (agora são a API pública desse módulo:
`handshake_allowed`, `connection_cap`, `setting`). `endpoint.py` ficou em 328 linhas depois de
tudo. Nenhum teste importava essas três funções diretamente (só `RealtimeHub`/`_serve`); um
comentário de docstring em `tests/integration/test_websocket.py` que citava
`realtime.endpoint._handshake_allowed` foi corrigido para o novo caminho.

### Item 2 — Bybit `planned` (bloqueado, conforme a cláusula de escape do brief)

Confirmado por leitura de `infra/migrations/ddl/enums.py:76-79` e
`infra/migrations/versions/0001_initial_schema.py:144-149`: o enum Postgres `exchange_status`
só tem `active`/`inactive` — não existe `planned`. Gravar `status='planned'` hoje falharia em
runtime (`invalid input value for enum`). O brief já previa essa saída ("diga isso e acione o
database-architect em vez de editar migrações"), então **nenhum código de `seed_reference.py`
ou `system_status.py` foi alterado** para este item — implementar a exclusão do agregado sem o
enum existir exigiria ou (a) uma migração, fora do meu escopo nesta tarefa, ou (b) um workaround
não documentado (ex.: usar `capabilities` JSONB como catálogo paralelo), que decidiria uma
questão de schema por conta própria — exatamente o que a Regra 1 do CLAUDE.md pede para não
fazer em silêncio.

Escrito `.claude/state/brief-T3.44c-exchange-status-planned.md` para o database-architect, com:
a localização exata do enum, as duas opções de desenho (estender o enum vs. um campo separado
tipo `has_collector`/`onboarding_status`, já que "sem coletor" não é o mesmo que "inactive" no
sentido operacional), os pontos que passam a mudar depois da migração
(`seed_reference.py`/`seed.py:seed_exchanges` hoje nem escreve `status` no upsert;
`system_status.py:build_market_status`; `schemas/system.py`; `pnpm gen:types`), e uma correção:
`seed.py --only exchanges`, citado no brief como "o comando do operador", **não existe** hoje —
`--only` (`seed_cli.py`/`seed_dry_run.TABLE_CHOICES`) só cobre `strategies`/`risk_profiles`/
`feature_definitions`/`opportunity_weights`; `seed_exchanges` roda incondicionalmente dentro de
`seed()`. Documentado no próprio brief para quem for implementar depois da migração.

`docs/PIPELINE.md` §1 ganhou um item novo (9) explicando o achado e apontando para o brief
T3.44c, sem inventar um comportamento que ainda não existe.

### Item 3 — nota para o frontend (não implementado, `apps/web` é só leitura para mim)

Quando `exchanges_planned` existir na resposta de `/system/market-status` (depois da T3.44c +
sua implementação), `apps/web/components/system/live-status.tsx` deve parar de contar exchanges
`planned` no agregado (`worstExchange`/`CompactStatus`) e mostrar algo como
"1 exchange · CONNECTED · N mercados (bybit planejada)" — uma linha a mais no texto do topbar,
lendo a nova lista separada em vez de tratar toda `exchanges[]` como operável. Não é uma
mudança de uma linha *hoje* porque o campo ainda não existe no schema; é uma linha depois que
existir.

### FILES

Modificados:
- `apps/api/hunter_api/realtime/endpoint.py` — `_handshake_allowed`/`_connection_cap`/
  `_setting` removidos (foram para `admission.py`); `mark_connected(websocket)` chamado logo
  após `accept()`; `websocket.state.authenticated = True` no sucesso de `_authenticate`;
  os dois `except WebSocketDisconnect` (`_authenticate`, `_serve`) agora chamam
  `log_ws_closed` antes de retornar; docstring do módulo documenta o `ws_closed`/contador novo.
- `apps/api/hunter_api/realtime/session.py` — `close_socket` loga via `log_ws_closed` antes de
  fechar; `mark_connected` e `log_ws_closed` novos.
- `apps/api/hunter_api/metrics.py` — `hunter_ws_closed_total` (Counter, label `code`).
- `apps/api/tests/unit/test_ws_endpoint.py` — 6 testes novos (4401 sem frame de auth, 4401
  token inválido, cliente que nunca autentica e cai fora, 4403 por membership revogada, close
  normal 1000 pós-auth, `duration_ms` reflete o tempo desde o accept).
- `apps/api/tests/integration/test_websocket.py` — comentário corrigido
  (`realtime.admission.handshake_allowed`, não mais `endpoint._handshake_allowed`).
- `docs/PIPELINE.md` — item 9 novo no §1 (achado Bybit + link para o brief T3.44c).

Criados:
- `apps/api/hunter_api/realtime/admission.py` — admissão (`handshake_allowed`,
  `connection_cap`, `setting`), relocado de `endpoint.py` sem mudança de lógica.
- `.claude/state/brief-T3.44c-exchange-status-planned.md` — handoff para o
  database-architect.

Nenhum arquivo em `apps/web/**`, `services/**`, `infra/migrations/**`, `obsidian/**`,
`.env*`, ou `apps/api/hunter_api/{repositories,services,schemas}/lab_*` foi tocado.
`infra/scripts/seed_reference.py` aparece modificado no `git status` compartilhado, mas por
outro agente (trendline_breakout, já presente antes desta tarefa começar) — não toquei nele.

### TESTS (saída real)

```
$ uv run pytest apps/api/tests/unit/test_ws_endpoint.py -q
....................................                                     [100%]
36 passed, 1 warning in 9.02s

$ uv run pytest apps/api/tests/unit -q -k "not lab"
377 passed, 106 deselected, 1 warning in 77.06s

$ uv run pytest apps/api/tests/integration/test_websocket.py -q
4 passed, 1 warning in 70.82s
(uma tentativa anterior deu ConnectionResetError do asyncpg contra o Postgres do
testcontainer — ambiente/Docker compartilhado, não relacionado ao diff; repetição limpa)

$ uv run ruff check apps/api
All checks passed!

$ uv run ruff format --check apps/api/hunter_api/realtime/ apps/api/hunter_api/metrics.py apps/api/tests/unit/test_ws_endpoint.py
10 files already formatted

$ uv run pyright apps/api/hunter_api/realtime/endpoint.py apps/api/hunter_api/realtime/session.py apps/api/hunter_api/realtime/admission.py apps/api/hunter_api/metrics.py apps/api/tests/unit/test_ws_endpoint.py
0 errors, 0 warnings, 0 informations

$ uv run pyright apps/api
14 errors — todos em test_lab_signals_pagination_api.py (lab_*, outro agente) e
test_regime_service.py (regime.py sendo mexido por outro agente agora, git status
compartilhado mostra M em routers/schemas/services/regime.py); nenhum nos arquivos desta tarefa.

$ uv run python infra/scripts/check_file_size.py
error   359 > 350  packages/core/hunter_core/settings.py
scanned 570 files; 1 over budget, 0 grandfathered
(pré-existente, não tocado nesta tarefa — packages/core/hunter_core/settings.py não faz
parte do meu diff)
```

### CONCERNS

1. Item 2 do brief não foi implementado em código (só diagnosticado + handoff) porque o
   enum `exchange_status` não tem `planned` — a própria cláusula de escape do brief cobre
   este caso. Sem a migração do database-architect (brief T3.44c), a Bybit continua contada
   no agregado do topbar como hoje.
2. Item 3 (nota para o frontend) é só texto — não há campo `exchanges_planned` no schema
   ainda para `live-status.tsx` ler, então não escrevi o one-liner como um diff pronto, só
   como especificação do que a linha deve fazer quando o campo existir.
3. A frase do brief "tipos regenerados" (resumo do despachante) não se aplica: como nenhum
   schema Pydantic mudou, não há nada novo para `pnpm gen:types` gerar nesta tarefa.
4. `duration_ms` é medido a partir de `mark_connected` (logo após `accept()`), não do
   instante em que o TCP chega — a diferença é o tempo de handshake HTTP/WS em si, sub-ms
   normalmente, irrelevante para o caso que este log existe para diagnosticar (~1,8 s).
