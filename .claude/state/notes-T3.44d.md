# Notas T3.44d — quem fecha o WebSocket é o navegador, não uma corrida de auth; o topbar agora tolera isso sem gritar "interrompido" à toa

Base: brief pede `main` em `2e39774` (implantado na VPS). A árvore local de trabalho está
compartilhada com vários outros agentes em voo (`git status` mostra `M`/`??` em
`apps/api/hunter_api/{routers,schemas,services}/regime.py`,
`packages/shared-types/src/generated/api.d.ts`, `infra/scripts/seed_*.py`,
`docs/*.md`, `apps/web/components/{radar,opportunities}/*` etc. — nenhum desses tocado
por mim). Esta tarefa só editou os arquivos listados em FILES. **Nenhum commit feito.**
**Nenhum comando destrutivo de git rodado.** `.env*` nunca foi escrito — só lido (via
`grep`) para exportar `CLERK_E2E_PUBLISHABLE_KEY`/`CLERK_E2E_SECRET_KEY` no meu próprio
shell, mesmo padrão de `.claude/state/tmp/run-design-audit.sh`, nunca impresso/logado.
Containers locais (`docker-*`) nunca parados/recriados — só lidos (`docker logs`,
`docker exec ... grep`). **A VPS não foi tocada nesta tarefa** (nem leitura): o brief
autoriza só `docker logs` na VPS para o Deliverable 3, que fica para depois do deploy do
orquestrador (ver seção própria abaixo) — tudo que segue é diagnóstico **local**.

## Descoberta 0 — os containers locais estão desatualizados (pré-T3.44/T3.44b)

Antes de confiar em qualquer log do meu próprio repro local, confirmei que
`docker-web-1`/`docker-api-1` (as imagens já buildadas, rodando desde 14:48Z/17:02Z de
hoje) **predatam** as correções já presentes no código-fonte atual:

```
$ MSYS_NO_PATHCONV=1 docker exec docker-web-1 grep -rl "realtime_auth_token_missing" /app/apps/web/.next
(sem saída — a correção do T3.44 em lib/ws.ts não está no bundle rodando)

$ MSYS_NO_PATHCONV=1 docker exec docker-api-1 test -f /app/apps/api/hunter_api/realtime/admission.py && echo EXISTS || echo MISSING
admission.py MISSING (pré-T3.44b -- log_ws_closed/mark_connected também não existem nesse container)
```

Consequência: meu repro local reproduz a **topologia/ciclo de vida real dos sockets no
navegador** (que não depende de nenhum log do servidor) com total confiança, mas **não
consegue observar** o log `ws_closed` novo nem a resposta `{"type":"authenticated"}`
timing exato do código atual — isso só a VPS (já no `main` certo) tem. Documentado para
não ser confundido com "o log não aparece porque o bug não existe".

## Descoberta 1 — reproduzido localmente: quem fecha o socket, quando, e por quê

Metodologia (Playwright real, usuário Clerk de teste, `waitUntil: "load"`, nunca
`networkidle`, OTP digitado com `page.keyboard.type("424242", {delay:80})` — `.fill()`
trava para sempre nesta instância Clerk, confirmado de novo aqui antes de eu saber da nota
já registrada em `design-audit.audit.ts`): `tests/e2e/ws-disconnect-repro.audit.ts`,
instrumentando a API **nativa** do Playwright `page.on("websocket", ...)` (nunca dependeu
de nenhum log da app) por > 3 minutos de navegação real.

**Primeira tentativa (descartada, mas reveladora):** naveguei com `page.goto()` entre as
páginas. Resultado: cada `page.goto()` para uma URL — mesmo a MESMA já aberta — abre um
par TOTALMENTE NOVO de sockets sem nunca disparar o evento `close` dos antigos antes do
timeout do teste. **Isso é o comportamento correto e essperado de uma navegação DURA do
navegador** (URL digitada, F5, `<a>` sem `next/link`, fechar a aba): o documento inteiro
é destruído, o JS morre, e o socket é derrubado pelo SO sem handshake de fechamento —
exatamente o padrão `code: 1005, reason: "client disconnected"` que a VPS registrou.
`page.goto()` é o equivalente Playwright disso, não de um clique em link do app.

**Segunda tentativa (a que importa): cliquei nos `<Link>` reais do Sidebar** (nunca
`page.goto()` depois do primeiro load), 3,4 minutos, 11 sockets observados:

```
[open]  #1 +16.2s route=Markets url=ws://localhost:8000/ws          <- topbar (rt:system), aberto assim que o layout do org monta
[open]  #2 +16.3s route=Markets url=ws://localhost:8000/ws          <- artefato do bug de corrida já corrigido no código-fonte (container pré-T3.44, ver Descoberta 0)
[close] #2 +16.4s lifetime=0.1s
[open]  #3 +17.7s route=Markets url=ws://localhost:8000/ws          <- socket real da tabela de Markets
[close] #3 +36.4s route(now)=Radar lifetime=18.7s                   <- fecha ao SAIR de Markets (unmount correto)
[open]  #4 +36.9s route=Radar url=ws://localhost:8000/ws?channel=rt%3Aradar  <- useRealtime (Radar)
[close] #4 +56.5s route(now)=Dashboard lifetime=19.6s
[open]  #5 +57.1s route=Dashboard url=ws://localhost:8000/ws        <- LiveStatus "full" da dashboard
[close] #5 +76.6s route(now)=System lifetime=19.5s
[open]  #6 +117.7s route=Dashboard url=ws://localhost:8000/ws       <- segunda visita à dashboard
[open]  #7 +140.4s route=Markets  (erro: ERR_CONNECTION_RESET aos +170.4s, 30s de vida)
[open]  #8 +140.8s route=Markets
[close] #8 +160.6s route(now)=Radar lifetime=19.7s
[open]  #9 +161.6s route=Radar
[open]  #10 +170.9s route=Radar   (reconexão automática do #7 após o erro)
[close] #9 +180.7s route(now)=Dashboard lifetime=19.0s
[open]  #11 +181.7s route=Dashboard

total sockets opened: 11 | ainda abertos ao fim: 4 (#1 topbar, #6/#10/#11 -- página em que o teste parou)
```

**Achado central: `#1` (o socket do topbar/`LiveStatus` compact, montado uma vez no
layout do org) sobrevive a TODA navegação real via `<Link>` pelos 3,4 minutos inteiros,
sem nunca fechar.** Isto é a prova direta de que **"o provider já vive no nível do
layout"** (item 3 do Deliverable 2) — `apps/web/app/(app)/[orgSlug]/layout.tsx` monta
`Topbar` uma vez por segmento de rota compartilhado, e o React Server Components +
reconciliação do App Router preserva a instância do componente cliente `LiveStatus`
embaixo dele através de toda navegação client-side (nunca `page.goto()`). **Nenhuma
mudança de código foi necessária aqui** — documentado como já correto, com prova, no
mesmo espírito da Descoberta 1a da nota T3.44 sobre a Bybit.

Cada socket **por página** (`MarketsTable`, `RadarTable`, o `LiveStatus` "full" da
dashboard) abre ao montar e fecha de forma limpa ao desmontar (navegar para outra
página) — comportamento correto, não um bug.

## Descoberta 2 — bug real e confirmado, dentro do escopo nomeado do brief: `useRealtime.ts` nunca responde ao `ping` do servidor

Ao investigar por que o socket `#4`/`#9`/`#10` do Radar (`ws://.../ws?channel=rt%3Aradar`)
usa uma URL com `?channel=` — assinatura exclusiva de `hooks/useRealtime.ts`, não de
`useMarketChannels.ts` — confirmei por leitura de código:

- `apps/api/hunter_api/realtime/endpoint.py`'s `_heartbeat()`: manda `{"type":"ping"}` a
  cada 25s; se o socket não respondeu `pong` até o PRÓXIMO ping (~25-50s depois), fecha
  com `4408 "pong timeout"`.
- `apps/web/hooks/useMarketChannels.ts` (usado por Markets/market-detail/o topbar) já
  respondia `pong` corretamente há tempos.
- `apps/web/hooks/useRealtime.ts` (usado só por `radar-table.tsx`, canal `rt:radar`)
  **nunca respondia** — encaminhava todo frame, incluindo `ping`, direto para o
  `onMessage` do chamador (`() => void reconcile()`), sem nunca mandar `pong`.

Consequência real: todo socket do Radar seria fechado pelo SERVIDOR com `4408` a cada
~25-50s, para sempre, independente de qualquer outra coisa — nunca aparece como "cliente
desconectou" (não é o sintoma exato da VPS), mas é um fechamento real, recorrente, dentro
de um dos dois arquivos que o brief nomeia explicitamente (`apps/web/hooks/useRealtime.ts`).
Impacto no usuário era baixo (o próprio `RadarTable` já reconcilia a cada 5s
independente do socket, por design — comentário do próprio arquivo), mas é uma correção
de estado-da-máquina genuína e barata.

**Corrigido na raiz** (não duplicado): `RealtimeClient.handleMessage` (`lib/ws.ts`) agora
responde `pong` a qualquer `ping`, para TODO consumidor deste cliente de uma vez —
`hooks/useRealtime.ts` não precisou de nenhuma mudança própria (herda a correção
automaticamente), e a resposta duplicada que já existia em `useMarketChannels.ts`'s
`handleFrame` foi removida por ficar morta (nunca mais alcançada).

## Diagnóstico final para a evidência da VPS (1005, `authenticated: true`, 3,5s e 101,8s)

Com as Descobertas 0-2 em mãos: **não há nenhuma corrida de auth nem nenhum bug de
"provider errado" explicando os dois fechamentos da VPS** — ambos já autenticados,
então não é a corrida do T3.44 (essa fecharia ANTES da autenticação, em ~1-2s, sem
`authenticated: true`). O padrão observado localmente (`page.goto()` derruba o socket sem
handshake, exatamente `1005`/"no status code") mais a ausência de qualquer log
`ws_membership_revoked`/`ws_idle_timeout`/`ws_channel_denied` nas janelas do brief T3.44
aponta para a explicação mais simples e consistente com TODA a evidência: **o navegador
do Everton fechou a aba/recarregou/navegou para uma URL fora do app (uma navegação DURA)
nesses dois instantes** — 3,5s depois de abrir uma página, e de novo 101,8s depois de
abrir outra. Isso é fisicamente inevitável (nenhum código em `apps/web` pode impedir o
navegador de derrubar um socket ao destruir o documento) e não é, em si, um defeito.

O que **é** corrigível — e é o que o Deliverable 2 endereça — é o que acontece **depois**:
a página seguinte reconecta (o `RealtimeClient` já faz isso sozinho), e o topbar não deve
gritar "interrompido" pelos poucos segundos que essa reconexão leva, nem ficar preso nesse
estado se a reconexão de fato teve sucesso.

## Deliverable 2 — o que foi corrigido

1. **`apps/web/lib/ws.ts`**
   - `handleMessage`: responde `ping` com `pong` (Descoberta 2), nunca repassa `ping` ao
     `onMessage`.
   - `handleClose(event: CloseEvent)` (antes não recebia o evento nativo): grava
     `{code, reason, wasClean, at}` em `lastClose` (novo campo privado), logando via
     `@/lib/logger` — `debug` (silencioso em produção) quando o próprio cliente pediu o
     fechamento (`closedByUser`, ex.: desmontagem de componente — rotineiro, não é
     incidente), `warn` com `code/reason/wasClean/attempt` quando não foi o cliente que
     pediu (fechamento do servidor OU o navegador derrubando o socket por baixo — o
     equivalente client-side do `ws_closed` do servidor, T3.44b).
   - `setStatus` grava `statusSince = Date.now()` a cada transição.
   - `getDiagnostics(): RealtimeDiagnostics` novo — `{since, lastClose, attempt}`, lido
     pelos hooks de dentro do próprio `onStatusChange`.
2. **`apps/web/lib/realtime-health.ts`** (novo, função pura, sem DOM/rede — testável
   isoladamente): `deriveConnectionHealth({status, since, now, lastClose, graceMs?})` →
   `{live, since, lastCloseLabel}`. `live` permanece `true` durante uma desconexão mais
   curta que `RECONNECT_GRACE_MS` (8s por padrão — cobre as primeiras tentativas do
   backoff exponencial do próprio `RealtimeClient`, que já reconecta sozinho); só vira
   `false` quando a desconexão ATUAL já ultrapassou essa janela. Robusto a um `since`
   `undefined` (não só `null`) vindo de um mock de teste mais antigo que ainda não conhece
   estes campos (`dashboard-page.test.tsx` — não tocado, mas quebrava sem esse cuidado,
   ver TESTS abaixo).
   - **Sobre "re-auth em banda"** (uma das duas opções que o brief pede): confirmado por
     leitura de `apps/api/hunter_api/realtime/endpoint.py::_serve` que o protocolo
     **não permite** reenviar `{"type":"auth",...}` depois do handshake inicial — qualquer
     tipo de mensagem fora de `ping`/`pong`/`subscribe`/`unsubscribe` fecha com `4400
     "unknown message type"`. Portanto a única opção realmente disponível é a segunda que
     o brief já previa: "reconectar sem cair para 'interrompido' a menos que a reconexão
     falhe além de um limite" — é exatamente o que `RECONNECT_GRACE_MS` implementa.
     Mudar o protocolo do servidor para permitir reautenticação em banda está fora do
     escopo autorizado desta tarefa (`apps/api/**` não listado); registrado aqui para o
     backend-specialist decidir se vale a pena no futuro.
3. **`apps/web/hooks/useMarketChannels.ts`**: expõe `since`/`lastClose` (lidos de
   `client.getDiagnostics()` dentro do `onStatusChange`); removida a resposta duplicada
   de `ping` (Descoberta 2); `handleFrame` perdeu o parâmetro `client` (só existia para
   essa resposta).
4. **`apps/web/components/system/live-status.tsx`**: `liveFeedDown` agora vem de
   `!deriveConnectionHealth(...).live` em vez de `socketStatus !== "open"` cru. O tooltip
   (`title`, nunca o texto inline — o brief pede isso "no tooltip") ganha, quando
   `liveFeedDown` é verdadeiro: `"... (tempo real do navegador interrompido · desde
   <Brasília> Brasília · último fechamento: <motivo> (<código>))"` — Brasília via
   `formatBrasiliaLong` (`lib/time.ts`, já existente, D16/D17/T3.22), nunca UTC cru na
   tela.
5. **`apps/web/hooks/useRealtime.ts`**: nenhuma mudança de código necessária — herda a
   correção do `ping` centralizada em `lib/ws.ts` (Descoberta 2).

## Deliverable 1 (script pronto, reutilizável)

- `tests/e2e/ws-disconnect-repro.audit.ts` + `tests/e2e/ws-repro.config.ts`: o repro local
  usado acima, descartável (mesmo padrão de `design-audit.audit.ts`), roda com:
  ```
  set -a; eval "$(grep -E '^CLERK_E2E_(PUBLISHABLE|SECRET)_KEY=' .env | tr -d '\r')"; set +a
  cd tests/e2e && pnpm exec playwright test -c ws-repro.config.ts --timeout 280000
  ```

## Deliverable 3 — NÃO executado nesta tarefa (conforme instrução do despachante)

`tests/e2e/ws-vps-proof.audit.ts` está pronto: `test.skip` honesto se
`VPS_STORAGE_STATE`/`VPS_ORG_SLUG` não estiverem configurados (mesmo padrão
`HAS_CLERK_E2E_KEYS` do resto do suite) — **deliberadamente não faz nenhum signup contra a
VPS** (seria uma ESCRITA no Postgres dela, fora do "somente leitura" desta tarefa);
precisa de uma sessão já autenticada (storageState) que o orquestrador/Everton forneça.
Amostra o tooltip do topbar a cada 15s por 5 minutos e imprime o comando de correlação
(rodado pelo orquestrador, não por este script):
```
ssh hunter-vps 'docker logs --since 6m hunter-api-1 2>&1 | grep ws_closed'
```
Critério de sucesso: toda amostra "ao vivo", OU — se uma desconexão real acontecer — a
nota aparece com `since`/motivo explicado pela contagem de `ws_closed` da VPS na janela, e
some de novo dentro de uma `RECONNECT_GRACE_MS` do reconnect ter tido sucesso, nunca presa
em "interrompido" através de uma reconexão que na verdade funcionou.

## FILES

Modificados:
- `apps/web/lib/ws.ts` — ping/pong central; `handleClose` recebe o `CloseEvent` real,
  grava `lastClose`, loga debug/warn conforme `closedByUser`; `getDiagnostics()`.
- `apps/web/hooks/useMarketChannels.ts` — expõe `since`/`lastClose`; remove a resposta de
  `ping` duplicada (agora morta).
- `apps/web/components/system/live-status.tsx` — `liveFeedDown` derivado com carência;
  tooltip com `since` (Brasília) + último motivo de fechamento.
- `apps/web/tests/ws.test.ts` — `FakeWebSocket.close()`/`simulateClose()` agora carregam
  `{code, reason, wasClean}`; 7 testes novos (ping→pong, diagnostics.lastClose para
  fechamento próprio e do servidor, `since` avança a cada transição, log debug vs. warn).
- `apps/web/tests/live-status.test.tsx` — 2 testes novos (carência mantém "ao vivo";
  nota + tooltip com "desde"/motivo depois da carência).

Criados:
- `apps/web/lib/realtime-health.ts` — `deriveConnectionHealth` (função pura) +
  `RECONNECT_GRACE_MS`.
- `apps/web/tests/realtime-health.test.ts` — 8 testes (aberto sempre "ao vivo"; dentro/fora
  da carência; `since=null` nunca é "ao vivo" falso; rótulo do motivo; `graceMs`
  customizável).
- `tests/e2e/ws-disconnect-repro.audit.ts`, `tests/e2e/ws-repro.config.ts` — Deliverable 1,
  descartável.
- `tests/e2e/ws-vps-proof.audit.ts` — Deliverable 3, pronto, não executado.

Nenhum arquivo em `apps/api/**`, `.env*`, `infra/**`, `obsidian/**`, ou qualquer arquivo já
em `M`/`??` de outro agente (`git status` no topo desta nota) foi tocado.

## TESTS (saída real)

```
$ cd apps/web && npx vitest run tests/ws.test.ts tests/realtime-health.test.ts tests/live-status.test.tsx tests/use-market-channels.test.ts tests/topbar.test.tsx tests/radar-table.test.tsx tests/dashboard-page.test.tsx
 Test Files  7 passed (7)
      Tests  66 passed (66)

$ cd apps/web && npx vitest run
 Test Files  107 passed (107)
      Tests  991 passed (991)
   Duration  112.32s

$ pnpm --filter @hunter/web lint
✖ 1 problem (0 errors, 1 warning)   # tests/lab-page.test.tsx, 377 linhas — pré-existente, não tocado

$ pnpm --filter @hunter/web typecheck
(sem saída — sucesso; uma checagem intermediária pegou 2 erros em
apps/web/components/{opportunities,radar}/*.tsx vindos de outro agente regenerando
packages/shared-types/src/generated/api.d.ts em paralelo -- já resolvido pelo próprio
outro agente antes da checagem final acima, confirmado repetindo o comando)

$ cd tests/e2e && npx tsc --noEmit | grep '^ws-'
(sem saída — os 3 arquivos novos desta tarefa typecheckam limpo; os erros restantes no
mesmo comando são todos em design-audit.audit.ts, pré-existente, não tocado)
```

Nenhum teste de `apps/api` rodado (nenhum arquivo de `apps/api/**` tocado nesta tarefa).

## CONCERNS

1. **Não pude observar o log `ws_closed`/`realtime_closed_unexpectedly` do lado servidor
   nem cliente contra um build real do código atual** — os containers locais predatam
   T3.44/T3.44b (Descoberta 0). A prova completa da correção (Deliverable 2) depende do
   Deliverable 3 rodar depois do deploy.
2. **`RECONNECT_GRACE_MS = 8000` é uma escolha de julgamento**, não derivada de dado real
   de produção — cobre confortavelmente o backoff inicial do `RealtimeClient`
   (500ms→1s→2s→4s de tentativas antes de 8s), mas se a VPS mostrar reconexões
   legitimamente mais lentas que isso (rede ruim, JWKS frio), vale revisitar com os números
   reais do Deliverable 3.
3. **Re-autenticação em banda não é possível hoje** (protocolo do servidor fecha com 4400
   qualquer mensagem pós-auth que não seja ping/pong/subscribe/unsubscribe) — documentado
   como decisão de escopo, não implementado; mudança de protocolo ficaria para o
   backend-specialist se algum dia for necessária.
4. **A causa raiz mais provável da evidência da VPS (navegação dura/fechar aba) não é
   "corrigível" por definição** — nenhum código em `apps/web` impede o navegador de
   derrubar um socket ao destruir o documento. O que esta tarefa corrige é a
   HONESTIDADE/ESTABILIDADE do que aparece na tela depois disso (não gritar por um
   reconnect que funciona sozinho em segundos), não o fechamento em si.
5. Não toquei em `apps/web/components/**/topbar*` além de nada — `topbar.tsx` já estava
   correto (renderiza `LiveStatus` uma vez, no layout); confirmado por leitura + pelo
   repro (Descoberta 1), nenhuma mudança feita ali.

## T3.44e

**Owner:** frontend-specialist. Base: `main` em `9ff2d47`, construído sobre o diff
não-commitado do T3.44d acima (lido via `git diff` antes de qualquer edição — nada dele
foi desfeito ou reformatado). Nenhum commit feito. Nenhum comando destrutivo de git
rodado. `.env*` não tocado. Nenhum container local parado/recriado. VPS não tocada
(o Deliverable 4 do brief — histograma `ws_closed` pós-deploy — fica para depois do
orquestrador implantar, mesmo padrão do Deliverable 3 do T3.44d).

### O que motivou

Evidência do brief: 10 fechamentos `4409` ("idle timeout")/hora na VPS, todos em socket
autenticado — o servidor (`apps/api/hunter_api/realtime/session.py`,
`IDLE_TIMEOUT_SECONDS = 15*60`) fecha qualquer socket que fique 15 min sem um frame
**cliente-iniciado**; o `pong` que o cliente já manda em resposta ao `ping` periódico do
servidor (`endpoint.py`, corrigido no T3.44d) **não** conta como atividade, por decisão
deliberada do servidor ("a pong is our own heartbeat"). O socket do topbar (`rt:system`)
só recebe, nunca manda nada por conta própria — batia no limite a cada ~15 min, sempre.

### O que foi implementado (aditivo, sem tocar linhas do T3.44d)

1. **`apps/web/lib/ws.ts`** — só métodos/constantes novos, nenhuma linha do T3.44d
   reformatada ou restruturada:
   - `KEEPALIVE_MS = 5*60_000`, `KEEPALIVE_JITTER_MS = 10_000` (constantes exportadas,
     novo bloco de documentação).
   - Campos novos na classe: `keepaliveTimer`, `lastActivityAt`.
   - `send()`: ganhou UMA linha aditiva (`if (message.type !== "pong") this.lastActivityAt
     = Date.now();`) — este método não pertencia ao diff do T3.44d, então editá-lo não
     viola a regra do revisor. Registra atividade só para frames que o servidor
     realmente credita (`session.mark_frame()`): `ping`/`subscribe`/`unsubscribe`, nunca
     `pong` — decisão deliberada para não deixar `handleVisibilityChange` achar que uma
     aba está coberta por uma atividade que o servidor não contabiliza.
   - `setStatus()`: ganhou duas linhas aditivas no final do corpo (`if (status ===
     "open") this.startKeepalive(); else this.stopKeepalive();`) — nenhuma linha
     existente alterada.
   - Métodos novos, todos privados, num bloco delimitado com comentário
     `--- T3.44e: visible-tab keepalive (additive) ---`: `startKeepalive`,
     `stopKeepalive`, `scheduleKeepalive`, `handleVisibilityChange` (campo de classe —
     arrow function — para que `addEventListener`/`removeEventListener` sempre vejam a
     mesma referência).
   - Comportamento: enquanto `document.visibilityState === "visible"` e o socket está
     `"open"`, manda `{"type":"ping"}` a cada `KEEPALIVE_MS` com jitter uniforme
     `±KEEPALIVE_JITTER_MS`; ao ficar oculta, cancela o timer pendente na hora (uma aba
     em segundo plano deve mesmo expirar — comportamento intencional do servidor); ao
     voltar a ficar visível, manda um ping imediato SE a última atividade já tem
     `>= KEEPALIVE_MS`, e sempre reagenda o próximo. O timer é limpo em todo caminho que
     leva a `setStatus` != `"open"` (fechamento próprio, fechamento do servidor,
     reconexão em andamento).
   - `{"type":"pong"}` do servidor (resposta ao ping do cliente) nunca é tratado
     especialmente em `handleMessage` — não é `"ping"`, então já cai no fluxo existente
     do T3.44d sem nenhuma mudança ali; não há dupla resposta.
   - **Limite de 350 linhas (CLAUDE.md):** a primeira versão passou de 350 linhas
     (356) e o `pnpm lint` acusou erro (`quality/max-lines`) — os comentários muito
     longos das primeiras versões foram condensados (mantendo o "porquê") até o arquivo
     ficar em 336 linhas. Nenhuma lógica foi cortada, só prosa redundante.

2. **`apps/web/lib/realtime-health.ts`** — aditivo dentro de `closeLabel` (função do
   T3.44d): uma nova constante exportada `IDLE_TIMEOUT_CLOSE_CODE = 4409` e um `if`
   inserido ANTES das duas linhas existentes da função (nenhuma delas alterada), que
   troca o rótulo cru do servidor ("idle timeout (4409)") por
   `"encerrado por ociosidade (15 min)"` em português — o único close code que o
   keepalive existe especificamente para evitar merece a explicação mais direta
   possível. O requisito "um 4409 seguido de reconexão dentro da carência continua 'ao
   vivo'" já valia sem mudança nenhuma: `deriveConnectionHealth` retorna `live: true`
   incondicionalmente quando `status === "open"`, independente de qualquer close code
   anterior — só precisava de um teste explícito provando isso para o caso 4409
   (adicionado).

3. **Testes** — `apps/web/tests/ws.test.ts`: novo describe `"visible-tab keepalive
   (T3.44e)"` (9 testes, timers falsos, `random: () => 0.5` para zerar o jitter): ping
   aos 5 min visível; repete a cada ciclo; nada enquanto oculta mesmo passando 3
   intervalos; ping imediato ao voltar a ficar visível com atividade >= 5 min velha;
   NENHUM ping imediato se a atividade é recente; timer limpo em `close()`; timer
   limpo também num fechamento inesperado do servidor; ignora o `pong` do servidor sem
   mandar nada de volta; e um teste específico provando que a resposta deste cliente ao
   PING do servidor (`pong`) não é contada como atividade própria (o caso que motivou a
   exclusão em `send()`). `apps/web/tests/realtime-health.test.ts`: novo describe para
   o código 4409 — rótulo em português, "ao vivo" com `status: "open"` mesmo tendo um
   4409 como último close, e "ao vivo" com 4409 ainda dentro da janela de carência sem
   reconexão confirmada.

4. **`docs/ARCHITECTURE.md` §5.2** — um parágrafo novo depois do já existente,
   explicando o fechamento por ociosidade (15 min, 4409), que um `pong` não reseta o
   relógio do servidor, e que `RealtimeClient` manda seu próprio `ping` a cada 5 min
   enquanto a aba está visível.

### Decisão de design que exigiu atenção extra

O `pong` que este cliente manda em resposta ao PING do servidor passa pelo mesmo
`send()` que o `ping` do próprio keepalive — sem o `if (message.type !== "pong")`,
`lastActivityAt` seria atualizado por uma resposta que o servidor deliberadamente NÃO
credita como atividade (`session.mark_frame()` não é chamado nesse caminho, conforme a
evidência do brief e o comentário citado de `endpoint.py`). Isso teria deixado
`handleVisibilityChange` subestimar o tempo ocioso e pular um ping que o servidor ainda
esperava — testado explicitamente (último teste do describe acima).

### TESTS (saída real)

```
$ cd apps/web && npx vitest run tests/ws.test.ts tests/realtime-health.test.ts tests/live-status.test.tsx tests/use-market-channels.test.ts
 Test Files  4 passed (4)
      Tests  53 passed (53)

$ cd apps/web && npx vitest run tests/ws.test.ts tests/realtime-health.test.ts tests/live-status.test.tsx tests/use-market-channels.test.ts tests/topbar.test.tsx tests/radar-table.test.tsx
 Test Files  6 passed (6)
      Tests  71 passed (71)

$ pnpm --filter web lint
✖ 5 problems (2 errors, 3 warnings)
# os 2 erros são em apps/web/components/auto-refresh.tsx ("Cannot access/update refs
# during render", "Cannot call impure function during render") -- arquivo NÃO tocado
# por esta tarefa; `git status` mostra `M` nele por um agente concorrente na mesma
# árvore compartilhada (confirmado: não estava em `M`/`??` no `git status` do início
# desta tarefa). As 3 warnings são pré-existentes (tests/lab-page.test.tsx e
# tests/ws.test.ts too-large -- warning, não erro, mesmo padrão de lab-page.test.tsx
# já em 377 linhas antes desta tarefa; lab-trendline-overlay.tsx complexity).

$ pnpm --filter web typecheck
lib/charts/lab-trendline-series.ts(53,27): error TS2532: ...
# arquivo `??` (não rastreado, de outro agente concorrente) -- não tocado por esta
# tarefa; `npx tsc --noEmit | grep -i "lib/ws.ts\|lib/realtime-health.ts\|tests/ws"`
# não retornou nenhuma linha (zero erros nos arquivos desta tarefa).

$ npx vitest run   # suíte inteira -- INSTÁVEL nesta árvore compartilhada
# 3 execuções seguidas do comando completo (sem tocar em nada entre elas) falharam em
# arquivos DIFERENTES a cada vez (ws.test.ts uma vez com 2 falhas de timing em testes
# de backoff pré-existentes que eu não toquei; depois lab-signals-table.test.tsx;
# depois 36 falhas espalhadas em 9 arquivos) -- consistente com contenção de
# CPU/paralelismo na árvore compartilhada (muitos agentes rodando ao mesmo tempo), não
# com uma regressão desta tarefa: os arquivos tocados aqui (ws.test.ts,
# realtime-health.test.ts) passam de forma estável e repetida quando rodados isolados
# (comandos acima), e as falhas da suíte completa nunca se repetem no mesmo arquivo
# duas vezes seguidas.
```

### FILES (T3.44e)

Modificados:
- `apps/web/lib/ws.ts` — keepalive de aba visível (aditivo).
- `apps/web/tests/ws.test.ts` — 9 testes novos (`visible-tab keepalive (T3.44e)`).
- `docs/ARCHITECTURE.md` — 1 parágrafo novo em §5.2.
- `.claude/state/notes-T3.44d.md` — esta seção.

Modificados (arquivos que já eram `??` do T3.44d, aditivo dentro deles):
- `apps/web/lib/realtime-health.ts` — `IDLE_TIMEOUT_CLOSE_CODE`, rótulo especial 4409.
- `apps/web/tests/realtime-health.test.ts` — 3 testes novos (4409).

Nenhum arquivo de `apps/api/**`, `.env*`, `infra/**`, `obsidian/**`, nem qualquer
arquivo pertencente a T3.51/T3.49/T3.46c foi tocado.

### CONCERNS (T3.44e)

1. **Deliverable 4 do brief (prova pós-deploy com `docker logs` na VPS) não foi
   executado** — depende do orquestrador implantar este código primeiro; mesma
   limitação documentada no Deliverable 3 do T3.44d acima.
2. **`lastActivityAt` reseta para `Date.now()` em `startKeepalive()`** (quando o status
   vira `"open"`) para espelhar que o relógio ocioso do servidor começa na autenticação
   — é uma suposição de que `WsSession.__init__` roda essencialmente no mesmo instante
   que o cliente recebe `{"type":"authenticated"}`; num delay de rede real isso é uma
   diferença de milissegundos, irrelevante contra uma janela de 5 min.
3. **A suíte completa (`npx vitest run`) está instável nesta árvore compartilhada**
   (ver TESTS acima) — não é uma regressão desta tarefa (confirmado rodando os arquivos
   tocados isolados, repetidamente, sempre verdes), mas registro aqui para quem for
   validar não confundir uma falha de outro arquivo com algo desta entrega.
4. Dois arquivos fora do escopo desta tarefa (`apps/web/components/auto-refresh.tsx`,
   `apps/web/lib/charts/lab-trendline-series.ts`) já estão com erro de lint/typecheck
   na árvore antes desta tarefa começar (confirmado por `git status`/`git log` — um é
   `M` por outro agente em voo, o outro é `??` novo de outro agente) — não corrigidos
   aqui por estarem fora do escopo nomeado do brief T3.44e.

## T3.44f

**Owner:** frontend-specialist. Fecha o achado CRITICAL da revisão de código do
T3.44d/e sobre `apps/web/lib/ws.ts:59-65` (`setStatus`, raiz apontada pelo próprio
achado). Base: construído sobre o diff não-commitado do T3.44d+T3.44e já em
`apps/web/lib/ws.ts`, `apps/web/lib/realtime-health.ts`,
`apps/web/components/system/live-status.tsx` e seus testes — lido por inteiro (`git
diff`, este arquivo, seções T3.44d e T3.44e) antes de qualquer edição; nada desse diff
foi desfeito ou reformatado (conferido depois com `git diff -- apps/web/lib/ws.ts`: o
único trecho alterado é o corpo de `setStatus`, tudo em volta — ping/pong,
`handleClose`, `getDiagnostics`, o keepalive inteiro do T3.44e — permanece igual).
Nenhum commit feito. Nenhum comando destrutivo de git rodado. `.env*` não tocado.
Nenhum container local parado/recriado. Nenhum arquivo de T3.51/T3.49/T3.46c/T3.44c
tocado (`live-status.tsx` continua exatamente como o T3.44d/e deixou — não editado
nesta tarefa).

### A causa raiz confirmada

`RealtimeClient.setStatus()` (`lib/ws.ts`) gravava `this.statusSince = Date.now()` em
TODA transição de status, inclusive "connecting" — que dispara de novo a cada
tentativa do próprio backoff exponencial (`scheduleReconnect` -> `open()` ->
`setStatus("connecting")`). Como `deriveConnectionHealth`
(`lib/realtime-health.ts`, correto e já testado desde o T3.44d) calcula
`disconnectedForMs = now - since` usando exatamente esse `since`, cada nova tentativa
de reconexão reiniciava a contagem da carência de `RECONNECT_GRACE_MS` (8s) — então
uma queda real de minutos lia "ao vivo" pelos primeiros ~8s de CADA tentativa de
reconexão, não só da queda inteira. O mesmo mecanismo também dava um "ao vivo" falso
nos primeiros ~8s da carga inicial da página, antes de qualquer "open" jamais ter
acontecido: `connect()` já chama `setStatus("connecting")`, que já carimbava um
`since` real mesmo sem nenhuma conexão bem-sucedida na história do cliente.
`deriveConnectionHealth` em si nunca teve bug — o achado do revisor aponta
corretamente a raiz em `ws.ts`, não em `realtime-health.ts` (por isso este arquivo e
seus testes ficam intocados, confirmado abaixo).

### O que foi corrigido

`apps/web/lib/ws.ts` — só o corpo de `setStatus` mudou, mais um campo novo:
- Campo novo `private everOpened = false` — se este cliente já alcançou "open" alguma
  vez.
- `setStatus(status)` agora carimba `statusSince = Date.now()` em só dois casos: (1)
  entrando em "open" (mais o `everOpened = true`), ou (2) no PRIMEIRO passo saindo de
  "open" (`wasOpen`, capturado antes de sobrescrever `this.status`) — ou seja, o
  instante em que uma queda contínua começa. Qualquer outra transição
  ("connecting" -> "closed" -> "connecting" -> ... dentro da MESMA queda, ou qualquer
  transição antes do primeiro "open" já ter acontecido) não mexe em `statusSince` —
  ele fica `null` até o primeiro "open" da vida do cliente (que
  `deriveConnectionHealth` já tratava como `Infinity` ms desconectado, nunca "ao vivo"
  — sem mudança nenhuma ali), e depois disso fica ancorado no início da queda atual,
  atravessando quantas tentativas de reconexão o backoff fizer.
- Arquivo ficou em 349 linhas (limite 350, CLAUDE.md) — a primeira versão passou
  (356/363 em iterações intermediárias) e o comentário novo foi condensado (mantendo
  o "porquê") até caber, mesmo padrão já registrado no T3.44e para o mesmo arquivo.

`apps/web/lib/realtime-health.ts`: nenhuma mudança — a função já fazia a coisa certa
com o `since` que recebia; o bug inteiro estava em `ws.ts` alimentando-a com o `since`
errado. Confirmado por leitura completa antes de decidir não tocar.

`apps/web/components/system/live-status.tsx` / `apps/web/hooks/useMarketChannels.ts`:
nenhuma mudança — já consomem `since`/`lastClose` via `getDiagnostics()`/
`onStatusChange` exatamente como o T3.44d desenhou; o `since` que recebem agora está
certo, sem precisar de nenhuma mudança no consumidor.

### Testes

`apps/web/tests/ws.test.ts`:
1. Reescrito o teste "stamps `since` on every status transition, not just the first"
   (T3.44d) para "stays `null` through every connecting/closed attempt before the
   first ever `open`, then anchors once open" — o teste antigo afirmava exatamente o
   comportamento com bug (asserindo que `since` já era um timestamp real logo após
   `connect()`, antes de qualquer "open") descrito literalmente no achado CRITICAL
   ("also on initial page load before the first open"); mantê-lo como estava teria
   deixado a suíte verde travando o bug no lugar. Reescrito para provar o contrato
   corrigido: `since` fica `null` durante "connecting" inicial, só vira timestamp
   depois do primeiro "open".
2. Novo describe "grace window survives a real reconnect loop (T3.44f, review of
   T3.44d)" (2 testes, exatamente os dois pedidos pelo achado):
   - "never reads live before the very first open — no initial-load grace window":
     `connect()` sem nunca simular open, chama `deriveConnectionHealth` de verdade com
     os diagnósticos reais do cliente — prova `live: false`, `since: null`.
   - "stays not-live through a minutes-long outage across many backoff attempts,
     never flashing 'ao vivo' at any retry": timers falsos (mesmo padrão do describe
     "reconnect backoff schedule" já existente — `vi.useFakeTimers()`/
     `vi.advanceTimersByTimeAsync`, `random: () => 1` para determinismo), abre de
     verdade, autentica, depois simula o servidor/navegador fechando o socket
     (`code: 1005, reason: "client disconnected"`, a mesma evidência real do T3.44d) e
     conduz ~10 tentativas reais de reconexão ("connecting" -> "closed", cada uma via
     o `scheduleReconnect` de produção, nunca mockado) ao longo de ~2,5 minutos de
     tempo falso simulado, chamando `deriveConnectionHealth` com os diagnósticos reais
     do cliente a cada passo. Prova três coisas a cada iteração: (a) `live` nunca
     volta a `true` numa transição "connecting" fresca (a reprodução exata do
     achado), (b) o `since`/âncora nunca muda ao longo de toda a queda
     (`toBe(outageAnchor)` — o mecanismo da correção, não só o efeito observável), (c)
     a carência inicial de `RECONNECT_GRACE_MS` ainda funciona normalmente logo no
     início da queda (`live` continua `true` por 8s antes de virar `false`).

`apps/web/tests/realtime-health.test.ts`: nenhuma mudança — a função pura já estava
certa e já tinha o teste "treats a never-yet-connected client (since=null) as
immediately not-live" (T3.44d) cobrindo o contrato do lado da função; o que faltava
era a prova de que `ws.ts` de fato entrega esse `since=null`/o `since` ancorado certo
em produção, que é exatamente o que os 2 testes novos acima em `ws.test.ts` fazem.

`apps/web/tests/live-status.test.tsx`: nenhuma mudança — os 2 testes do T3.44d
("grace mantém 'ao vivo'"; "nota + tooltip com 'desde'/motivo depois da carência") já
testam o componente com um `since` fixo passado por mock, então já eram (e continuam)
verdes independente deste bug — o bug só aparecia com uma sequência real de várias
transições, que só um teste dirigindo o `RealtimeClient` de verdade (como os novos em
`ws.test.ts`) conseguia expor.

### TESTS (saída real)

```
$ pnpm --filter @hunter/web exec vitest run tests/ws.test.ts tests/realtime-health.test.ts tests/live-status.test.tsx
 Test Files  3 passed (3)
      Tests  52 passed (52)

$ pnpm --filter @hunter/web exec vitest run tests/ws.test.ts tests/realtime-health.test.ts tests/live-status.test.tsx tests/use-market-channels.test.ts tests/topbar.test.tsx tests/radar-table.test.tsx
 Test Files  6 passed (6)
      Tests  73 passed (73)

$ pnpm --filter @hunter/web lint
2 problems (0 errors, 2 warnings)
# as 2 warnings (tests/lab-page.test.tsx 377 linhas, tests/ws.test.ts agora maior ainda
# por causa dos testes novos) já eram avisos pre-existentes no T3.44d/e para o mesmo
# padrao (arquivo de teste grande e warning, nao erro, nesta config de ESLint) -- 0
# erros. lib/ws.ts, que tinha virado erro numa iteracao intermediaria (351 linhas),
# esta limpo na versao final (349 linhas).

$ pnpm --filter @hunter/web typecheck
(sem saida -- sucesso)
```

### FILES (T3.44f)

Modificados:
- `apps/web/lib/ws.ts` — `setStatus` ancora `statusSince` no início da queda contínua
  (ou no último "open"), não mais a cada sub-transição; campo novo `everOpened`.
- `apps/web/tests/ws.test.ts` — 1 teste reescrito (contrato de `since` corrigido) + 2
  testes novos (describe dedicado) provando a queda de minutos e a carga inicial.
- `.claude/state/notes-T3.44d.md` — esta seção.

Não modificados nesta tarefa (lidos, confirmados corretos, herdam a correção sem
mudança própria): `apps/web/lib/realtime-health.ts`,
`apps/web/tests/realtime-health.test.ts`, `apps/web/components/system/live-status.tsx`,
`apps/web/hooks/useMarketChannels.ts`, `apps/web/tests/live-status.test.tsx`.

Nenhum arquivo de `apps/api/**`, `.env*`, `infra/**`, `obsidian/**`, nem qualquer
arquivo de T3.51/T3.49/T3.46c/T3.44c foi tocado.

### CONCERNS (T3.44f)

1. `apps/web/tests/ws.test.ts` cresceu para 557 linhas (aviso de lint, não erro) — já
   era um arquivo grande antes desta tarefa (T3.44e já registrava a mesma classe de
   aviso); os 2 testes novos + a reescrita de 1 são o mínimo pedido pelo achado, mas
   se algum dia isso virar erro (mudança de config do ESLint) vale separar os
   describes de diagnóstico/saúde de conexão ("close diagnostics", "grace window
   survives...") num arquivo próprio (`ws-diagnostics.test.ts`).
2. Não há prova pós-deploy contra a VPS desta correção específica — mesma limitação
   estrutural documentada nos Deliverables 3/4 do T3.44d/T3.44e (containers locais
   desatualizados, VPS não tocada nesta tarefa); a prova aqui é 100% de unidade contra
   o `RealtimeClient` real (não mockado) dirigido por timers falsos, o que já reproduz
   fielmente a máquina de estados de produção (mesmo `scheduleReconnect`, mesmo
   `handleClose`), mas não o timing de rede real.
3. Confirmei que `deriveConnectionHealth`/seus testes não precisavam de nenhuma
   mudança lendo o arquivo inteiro antes de decidir isso — registrado aqui para quem
   revisar não estranhar um achado sobre `realtime-health.ts:59-65` (linha citada no
   brief) resultar em zero linhas mudadas nesse arquivo: a raiz sempre esteve em
   `ws.ts`, como o próprio brief já apontava ("root in ws.ts setStatus").
