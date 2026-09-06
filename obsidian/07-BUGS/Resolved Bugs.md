---
tags: [bugs, resolvidos]
updated: 2026-09-06
---

# Resolved Bugs

Correções reais extraídas do `git log`. A maioria veio de rodadas de revisão de segurança/qualidade, não de bugs reportados em produção — não houve produção ainda.

## Shadow Lab — S2 (`5d0153b`, 2026-09-05/06)

Três defeitos que **os testes verdes não pegavam**, todos encontrados rodando de verdade ou por
revisão adversarial. A lição comum está registrada em [[Architecture Decisions]]: um duplo de teste
que reimplementa a semântica do sistema real (o Lua do rate limiter, o timeout do Redis, o digest do
código) esconde exatamente a classe de falha que só aparece em produção.

- **HIGH — `consume()` matava o worker sempre que o mercado ficava quieto.** Na primeira tentativa
  da prova operacional (23:18–23:21 UTC) o `strategy-worker` morreu com
  `redis.exceptions.TimeoutError: Timeout reading from redis:6379` em
  `hunter_core/events/consume.py:85`. Causa: `consume()` bloqueia o `XREADGROUP` por 5000 ms e o
  cliente Redis tem `socket_timeout = 5.0` — num stream ocioso os dois vencem no mesmo instante. O
  container reiniciava (`restart: unless-stopped`) e nada se perdia, mas um worker que morre no
  silêncio do mercado não está supervisionado. Corrigido no consumidor do `strategy-worker`
  (`CONSUME_BLOCK_MS = 2000` + backoff no laço), com regressão em `test_consumer_supervision.py`.
  **O default de `consume()` continua perigoso para os outros consumidores** — segue em
  [[Open Bugs]].
- **HIGH — `code_ref` era o digest da árvore inteira, e um módulo novo matava o Lab em silêncio.**
  `strategies_code_ref()` fazia o digest de *todos* os `.py` de `hunter_core/strategies/` e a
  comparação exigia igualdade exata. Cenário reproduzido pelo `risk-engine-guardian`: acrescentar
  `momentum_v2.py` — ou **um comentário** em `indicators.py` — mudava o digest,
  `load_active_versions` passava a pular **todas** as versões congeladas com
  `shadow_version_code_ref_mismatch`, e o Lab parava de avaliar com `/ready` ainda **verde**.
  Corrigido em duas frentes: (a) o `code_ref` passou a ser o digest do módulo da própria estratégia
  mais o fecho transitivo dos módulos irmãos que ela realmente importa, derivado por análise `ast`
  (formato `hunter_core.strategies.<módulo>@sha256:<64 hex>`); (b) a checagem `shadow_versions` de
  `/ready` fica **falsa** quando há linhas `active` e nenhuma executável, com as recusas contadas
  por motivo. Como campo congelado não se corrige no lugar (a trigger recusa o `UPDATE`), a correção
  obrigou `momentum v2` e `volume_anomaly v2`, com as v1 `--supersede`d para `deprecated`
  **mantendo a população que já tinham** — é a razão de cada experimento ter duas coortes
  ([[EXP-0001-momentum-v1]], [[EXP-0002-volume-anomaly-v1]]).
- **MEDIUM — a censura por gap era cega e o viés era o pior possível.** `_handle_gap` censurava por
  relógio (`censor_after_s = 1800 s`) sem olhar o que o coletor estava fazendo. Na prova da S2 o
  recovery levou ~10 min para 786 gaps; uma janela pior censuraria acompanhamentos que o dado ainda
  ia cobrir — e a perda seria **correlacionada com a instabilidade do market-worker**, ou seja,
  sumiria justamente o que foi decidido nas condições que mais interessam. Corrigido: a censura
  consulta `ingestion_gaps` e o veredito vira o sufixo do motivo — `gap:<minuto>:failed` (censura
  na hora), `gap:<minuto>:unregistered` (censura ao esgotar 7200 s), `gap:<minuto>:stalled` (gap
  `open` parado além de `gap_recovery_max_s = 86 400 s`), e `open` recente **espera o quanto for
  preciso**. As três populações são contadas separadamente pela S3.

## Prova operacional do market-worker (T1.6, 2026-09-05)

Seis defeitos que **só apareceram rodando de verdade** contra a Binance em Docker. Nenhum era visível na suíte de testes — a prova completa, com o comando e a saída de cada um, está em `.claude/state/t16-proof.md`.

- **CRITICAL-1 — `EXPIRE` recebendo um float no Lua do rate limiter.** `_ACQUIRE_SCRIPT` fazia `redis.call('EXPIRE', key, ARGV[5])` e o Python mandava `_bucket_state_ttl_s = 120.0`; redis-py serializa isso como `"120.0"` e o Redis recusa (`value is not an integer or out of range`). Efeito: **todo** `list_markets` falhava, o universo nunca carregava e o worker ficava em `/ready` 503 desde o boot — o pipeline inteiro estava morto contra um Redis real. Passou despercebido porque `_FakeRedisEval`, no teste, reimplementa a semântica do Lua em Python e nunca exercita a tipagem enviada ao Redis. Corrigido: TTL vira `int` (`math.ceil`) no Python **e** `tonumber(ARGV[5])` no Lua, com teste que olha o tipo do argumento cru mais teste de integração contra Redis real.
- **HIGH-1b — `dropped_events` contado e nunca lido.** O `BoundedEventQueue` incrementava `ConnectionState.dropped_events` ao descartar evento por fila cheia, e nada no repositório lia esse campo: nem métrica, nem heartbeat, nem `system_event`, nem log. Perda de ingestão era invisível. Corrigido: `market_dropped_events_total{exchange}` e campo `dropped_events` no hash do heartbeat — que na primeira medição real marcou **256.733 descartes em 75 s**.
- **HIGH-2 — queda de Postgres matava o worker.** `run_heartbeat` era a única tarefa permanente que deixava o erro de banco de `record_system_event` escapar para o `TaskGroup`. Com o Postgres fora por 52 s o processo morreu; ao voltar, ainda com o banco fora, entrou em cascata com a HIGH-3. Cenário real: qualquer restart de Postgres (manutenção, failover, upgrade menor) derrubava a ingestão. Corrigido: `safe_record_system_event` (captura tudo menos `CancelledError`, loga e conta), e o heartbeat escreve no Redis **antes** de tentar gravar em `system_events`.
- **HIGH-3 — refresh de universo falhado cegava o worker por 15 minutos.** `run_universe` dormia `market_universe_refresh_s` (900 s) depois de uma falha exatamente como depois de um sucesso. Medido: o banco voltou em 76 s e o worker ficou 16 minutos com `markets_monitored=0`, `ws_state=disconnected`, sem ingestão. Corrigido: backoff exponencial a partir de 5 s com jitter, teto de `min(120, refresh/3)`, reset no primeiro sucesso.
- **HIGH-4 — restart de Redis congelava o worker em zumbi silencioso.** `create_redis` não definia `socket_timeout`, `socket_connect_timeout`, `health_check_interval` nem retry; o padrão do redis-py é timeout `None`, então um `await` numa conexão derrubada pelo restart bloqueia **para sempre** — a tarefa nunca retorna, nunca levanta, e por isso nunca chega à supervisão que a tornaria fatal. Medido depois de um apagão de 81 s: processo vivo a 0,23 % de CPU, `/ready` 503, **19 minutos sem uma linha de log**, nenhuma conexão WebSocket restante, e `restart: unless-stopped` sem agir porque nada morreu. Corrigido: `socket_connect_timeout=5s`, `socket_timeout=5s`, `health_check_interval=30s` e `Retry(ExponentialWithJitterBackoff(0.05, cap 0.5), 3)`, cada número justificado no código contra o cenário que cobre. Reteste: `/ready` 200 com 200 mercados 30 s depois de o Redis voltar.
- **MEDIUM-1 — o corpo do `/ready` contradizia o próprio status.** O runtime monta o payload com `details[check.__name__]`, e o worker registrava `partitions.ready`, cujo `__name__` é literalmente `ready`. Resultado: `503 {"...","ingestion":false,"ready":true}` — quem lesse `body["ready"]` concluía o oposto do que o endpoint dizia. Corrigido registrando o check por um wrapper chamado `partitions`.
- **MEDIUM-3 — healthcheck do Compose com falso negativo.** O servidor de saúde divide o event loop com a ingestão saturada; a latência do próprio `/ready` foi medida entre 0,01 s e 24,79 s, contra um `timeout: 3s`. Resultado: sequências de quatro falhas seguidas num worker que estava pronto — e um `unhealthy` falso é pior que nenhum, porque qualquer autoheal ou probe de orquestrador reiniciaria um worker saudável. Corrigido com valores medidos (`timeout: 30s`, `interval: 15s`, `retries: 5`, `start_period: 60s`), documentando que isto absorve a cauda e que a correção real é a capacidade de ingestão (M2).

## Market worker (T1.3, commit `b8c4766`)

CRITICAL e HIGH levantados pelo `database-architect` (duas passadas), pelo `code-reviewer` e pela Astra adversarial, todos com cenário de falha medido antes da correção. Uma linha cada.

- **CRITICAL-1** — `market_snapshots` e `open_interest_history` gravavam uma linha por `INSERT`; 400 inserts levavam 19,85 s contra 83 ms em lote, estourando o timeout de flush e descartando a fila inteira por idade. Corrigido: um `INSERT ... ON CONFLICT DO NOTHING` multi-linha por tabela por flush.
- **CRITICAL D1 (convenção de porcentagem)** — o snapshot gravava fração (correto, `NUMERIC(9,6)`), mas o fix-brief original mandava multiplicar por 100; a instrução errada foi rejeitada e o banco continua em fração. Divergência dos helpers de domínio virou o follow-up T1.1c.
- **CRITICAL D2** — `PersistQueues.drop()` levantava `RuntimeError` ao encher a fila de perdas; com Postgres fora, o processo morria ~9 min depois. Corrigido: `deque(maxlen=...)` que evicta e conta, nunca levanta.
- **HIGH-2** — a detecção de gaps fazia 1005 statements e 202 transações por passada (60,6 s com 200 mercados num ciclo de 60 s), segurando `ACCESS SHARE` em `candles` por ~40 s/min. Corrigido: três consultas set-based sobre o universo inteiro.
- **HIGH-3** — nada garantia que existisse partição para a data corrente; em 2027-01 o primeiro insert derrubaria o flush inteiro em silêncio. Corrigido: `assert_writable_partitions` fatal no startup para *agora*, `/ready` falso e `system_event` critical para o lookahead de +1 dia.
- **HIGH-4** — o ranking do universo fazia ~500 `UPDATE`s numa transação depois de zerar `is_monitored` de todos, travando linhas de `markets` por segundos. Corrigido: um único `UPDATE ... FROM (VALUES ...)`.
- **HIGH D3** — sem `command_timeout`/`statement_timeout`, um flush cancelado deixava o `drain_loop` preso para sempre num socket morto, com `/ready` falso e nada reiniciando. Corrigido: `command_timeout=30` no engine e `SET LOCAL statement_timeout = '15s'` nas sessões `hunter_worker`.
- **HIGH D5** — a detecção terminava em `align(now) - 1 min` e disputava com a fila de persistência, registrando até 200 gaps falsos por ciclo e disparando 200 backfills REST contra o banco já lento. Corrigido: graça de 2 min, maior que a tolerância de atraso da fila.
- **HIGH H1** — falha em `report_losses` sem `try/except` matava o processo num blip do Postgres; corrigido, e as perdas só saem da fila depois do commit.
- **HIGH H2..H10** — série de correções de hot state e coalescência: `event_ts` propagado, `HDEL` do campo opcional ausente na mesma transação do `HSET`, staleness por componente (`mark_ts`/`oi_ts`/`funding_ts` independentes), dedupe de trades em janela de 50, candles em janela rápida de 16, final substituindo parcial mesmo com `event_ts` igual, e `price_ts`/`book_ts` separados no payload.
- **D8 (caminho de produção)** — o bucket de open interest por ciclo só existia no caminho sem fila, morto em produção; um poll de 200 mercados atravessando o limite de 5 min espalhava as leituras por dois buckets, com o corte mudando a cada ciclo. Corrigido: `OpenInterestSample` carrega o `bucket_ts` do ciclo pela fila.
- **Staleness dos campos de ticker no snapshot** — `price`, `bid`, `ask`, `spread_pct` e volumes eram gravados por mais velho que estivesse o hash, republicando preço congelado como observação nova. Corrigido: gate pelo `ts` do próprio ticker, medido contra o instante real de coleta (não o minuto alinhado, que dava até 59 s de folga), com contador por campo; se tudo é descartado, a linha não é escrita.

## Infraestrutura de dev

- **`b2e48b5`** — `setup_env.ps1` juntava todas as variáveis numa única linha: em PowerShell 5.1 a vírgula liga mais forte que `+`, então a concatenação de linhas do `.env` colapsava tudo. Corrigido parenteizando cada linha.
- **`4e7e878`** — `setup_env.ps1` extraía a chave errada de entradas `NAME=value` ou de colagens multi-linha; corrigido, e passou a imprimir o tamanho da chave para conferência sem expor o valor.
- **`43ee7c3`** — `setup_env.ps1` tinha caracteres fora de ASCII que o PowerShell 5.1 não parseava; reescrito ASCII-only.
- **`cd1c2d3`** — instalação canônica corrigida para `uv sync --all-packages` (o root é um projeto uv virtual; sem essa flag os pacotes `hunter_*` não eram instalados).
- **`1a15013`** — `noqa` não utilizado no healthcheck do Docker removido (ruff `RUF100`).
- **`46993a0`** — comentário sobre loopback ajustado para passar no gate `forbidden-patterns`; porta padrão de `/health` corrigida para 8001; `DEPLOYMENT.md` atualizado para descrever o entrypoint real.

## Frontend

- **`541ef78`** — o registro de navegação (`nav-registry`) carregava referências a componentes React, que não serializam entre Server e Client Components; corrigido para ser dado puro (segmento + chave de ícone), permitindo que o layout server-side passe a sidebar para o client.
- **`4988645`** — formatação de dinheiro corrigida para ser segura com `Decimal` (não `float`); backoff de reconexão do WebSocket ganhou jitter; itens de navegação ainda não disponíveis (`Disponível a partir de: M<n>`) passaram a ser acessíveis (não só visualmente desabilitados).
- **`f48da11`** — a prévia de desenvolvimento `/_design` foi excluída do matcher do middleware do Clerk (estava sendo protegida por engano).

## Backend / API

- **`c6eb407`** — rodada de revisão T05 (CRITICAL/HIGH/MEDIUM): erros de validação passaram a nunca ecoar o input do usuário; timeouts adicionados a `/ready`; modelo de confiança de IP de proxy corrigido; `/metrics` passou a exigir token; `request_id` limitado em tamanho.
- **`149c542`** — ponte Redis→WebSocket unificada num único dispatcher roteado por canal de mensagem; broadcast passou a expulsar conexões mortas.
- **`94b26a4`** e **`8a454f4`** — endurecimento de auth/tenancy da revisão de segurança T06: cap no corpo de streaming, staleness máxima do JWKS, limites por-principal e por-WebSocket, claims de webhook em duas fases (evita processar duas vezes um evento entregue de novo no meio de um crash).
- **`a900926`**, **`ca3cab3`**, **`a9da9ea`** — correções de pyright strict e cobertura de teste (ponte Redis expõe `is_running`; branch de banco fora do ar em `/ready`; auditoria em exceção; liberação de lock verificada por token).

## Banco de dados

- **`c28c1bc`** — endurecimento de schema da cross-review T04 (a migração `0001` foi emendada no lugar, nunca sucedida por uma `0002`, porque o schema nunca tinha sido aplicado em lugar nenhum além de CI/testcontainers): políticas por comando (não `FOR ALL`) em `organizations`/`users`, classe de grant sem `DELETE`, verificação de existência dos papéis antes de prosseguir.
- **`720102f`** — política de `users` para colegas de organização tornada somente-leitura (`FOR SELECT`; antes permitia `UPDATE`/`DELETE` na linha de um colega); `organizations` perdeu `DELETE` para o papel da aplicação; contagem real de linhas semeadas por `seed.py` (antes reportava a contagem de entrada, não o que de fato foi gravado sob RLS).
- **`154ecea`** — schema inicial, RLS, partições, papéis e seeds (T04), base sobre a qual as duas correções acima foram aplicadas.

## Segurança / CI

- **`9b7afe8`** — revisão T10: allowlist do `gitleaks` baseada em valor (não em padrão frouxo), regra para senha de URI de banco, actions do GitHub fixadas por SHA, isenções por segmento de caminho.
- **`4035cd4`**, **`7d25f8a`** — senha de fixture de teste marcada conforme a convenção de allowlist do gitleaks, para não ser confundida com segredo real.

## Testes de integração

- **`744fdf8`** — suíte de integração T11: isolamento entre organizações, matriz de RBAC, mutações, webhook, rate limits, WebSocket, casos-limite de autenticação. Não corrige um bug específico; fecha a cobertura de teste que valida as correções acima.

## Relacionadas

[[Open Bugs]] · [[Changelog]]

## Fontes

`git log` (M0, commits acima), `docs/plans/M0.md` (rodadas T04–T11), `.claude/state/milestone.json`

## Resolvidos em 2026-09-05 (fechamento do M0 / início do M1)
- `3c31ef0` **Imagem web não construía**: `Dockerfile.web` não copiava `packages/shared-types`, então `@hunter/shared-types` virava `any` e o `next build` falhava dentro da imagem. Encontrado pelo agente de fechamento do M0.
- `560c94c` **`pnpm test` rodava o Playwright** porque `tests/e2e` expunha `test`; renomeado para `e2e` (CI ajustado).
- `d76a0cf` **`worker` do compose saía com 0 sem fazer nada**; substituído por `market-worker` com `restart: unless-stopped` e healthcheck; papéis sem pacote falham explicitamente (implementado pela Astra).
- `b2e48b5` **`setup_env.ps1` gravava o `.env` numa linha só** (precedência da vírgula sobre `+` no PowerShell).
- `541ef78` **500 em toda rota `/[orgSlug]`**: menu passava função e componente do servidor para o cliente.
- `744fdf8` **8 testes dependentes de ordem** por balde de rate limit compartilhado entre TestClients.
