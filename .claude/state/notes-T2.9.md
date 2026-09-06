# Notas T2.9 — outbox transacional, `consume()`, rate limit coordenado

Registro do que **não** foi feito (e por quê), das divergências com a Astra e dos
follow-ups que dependem de arquivos fora da minha lista permitida.

## Bloqueado por arquivos travados (S2 em correção final)

- **`market.universe.changed` NÃO migrou para a outbox.** A publicação está em
  `services/market-worker/hunter_market_worker/universe.py:172-183` e o brief da
  minha dispatch proíbe tocar em `universe.py`, `universe_repo.py`,
  `tests/test_universe.py` e `tests/test_universe_tracking_hold.py`. O evento é
  durável pelo critério de §10b do PIPELINE (o scanner faz warm-up dos novos
  mercados e encerramento dos excluídos a partir dele), então ele **continua
  sendo o único produtor durável do market-worker publicando best-effort**.
  Migração quando a S2 fechar (é pequena):
  1. o `event_id` determinístico é `event_id_for(Streams.MARKET_UNIVERSE_CHANGED,
     exchange, version)` — a versão do universo que `universe.py` já calcula;
  2. o `enqueue` vai na transação de `universe_repo.py` que grava a composição
     (não no `publish` do fim do ciclo);
  3. some o `await publish(...)` de `universe.py:178`.
  Enquanto isso não acontece, uma troca de universo perdida por um Redis fora do
  ar continua sendo perdida.

## Divergências com a Astra (opinião de desenho, rodada 1)

1. **Fallback do rate limit durante indisponibilidade do Redis.** A Astra
   recomendou **suspender novas admissões REST** enquanto a coordenação estiver
   fora, porque N shards com bucket local cheio somam N cotas contra uma quota
   compartilhada. O brief pede explicitamente "fallback em memória se o Redis
   cair (com log)". Implementei o fallback, com dois reforços que atacam o
   cenário dela: (a) um bloqueio que este processo conhece nunca é esquecido (o
   deadline é espelhado localmente antes da escrita compartilhada, e `wait_s()`
   devolve `max(local, compartilhado)`), (b) `IpRateGate.degraded` + log
   `rate_limit_gate_degraded` tornam o estado visível.
   **Não resolvido:** N shards ainda podem gastar N budgets locais durante uma
   queda longa do Redis. A decisão de suspender admissões é de política de
   produto/ops, não minha — fica para T1.6b com a Astra e o dono do serviço.
   **RESOLVIDO em 2026-09-06:** a Astra tinha razão e o orquestrador decidiu
   pelo aceite da M2. O fallback foi removido; ver a seção "DECIDIDO" no fim.
2. **Clock dos scripts de bucket.** A Astra queria `TIME` do Redis em tudo. Usei
   `TIME` só no gate (`rate_limit_lua.py`: `BLOCK_IP_SCRIPT`, `IP_WAIT_SCRIPT`),
   porque lá o valor é um **deadline absoluto comparado entre processos**. Os
   scripts de bucket seguem com o relógio do chamador: o estado deles é um delta
   (`elapsed`), o skew para trás já é clampado em zero, e trocar o relógio
   invalidaria o ponto de injeção `clock=` que a suíte de unidade usa. Skew entre
   hosts que compartilham um IP de saída é de milissegundos.
   **Follow-up T1.6b:** se algum dia dois shards ficarem em hosts com NTP ruim,
   migrar `ACQUIRE_SCRIPT`/`RECORD_USED_WEIGHT_SCRIPT` para `TIME` também (e
   adaptar `_FakeRedisEval`).
3. **Janela do header de peso.** A Astra apontou, com razão, que
   `uw`/`uw_at` tornam a guarda atômica mas **não identificam a janela real da
   exchange**: "60 s desde a última leitura aceita" é heurística, não prova. Não
   há nada no header que dê o início da janela, então mantive a heurística e
   registrei a limitação. Não inventei um campo que a Binance não manda.

## Follow-ups em arquivos fora da minha lista

- **`packages/core/hunter_core/redis.py`:** `_SOCKET_TIMEOUT_S` é privado e agora
  é lido por `events/consume.py` (com `# pyright: ignore[reportPrivateUsage]`).
  O acoplamento é proposital — derivar o `block_ms` do deadline de leitura do
  cliente é o que impede os dois números de divergirem de novo. Falta exportá-lo
  publicamente (`SOCKET_TIMEOUT_S = _SOCKET_TIMEOUT_S`) e trocar os três imports.
- **`packages/core/hunter_core/db/models/system.py` (database-architect):** o
  índice parcial de `outbox_events` é `ix_outbox_events_pending (id) WHERE
  dispatched_at IS NULL`, mas o despachante ordena por `(created_at, id)` — a
  sequência tem buracos e não é ordem de commit, então `id` sozinho não serve
  como ordem. Com a fila rasa que o alvo de prontidão permite (≤ 500) o custo é
  irrelevante; se a fila crescer, o índice certo é `(created_at, id) WHERE
  dispatched_at IS NULL`. **Não fiz** porque migrações estão fora do escopo.
- **Absorção da `shadow_outbox` (S2 → genérico), quando a S2 fechar.** O
  despachante genérico guarda o **envelope inteiro** em `payload`; a
  `shadow_outbox` guarda só o payload de negócio e monta o envelope no dispatch
  (`services/strategy-worker/hunter_strategy_worker/outbox.py:95-101`). Migrar
  sem perder pendências:
  1. parar o `run_outbox` da S2 e deixar `dispatch_once` drenar até
     `shadow_outbox` ficar sem `dispatched_at IS NULL` (o ponto de corte);
  2. um script de migração copia as linhas restantes para `outbox_events`,
     **envolvendo** o payload legado num envelope (`event_id` = o mesmo
     `event_id` — a identidade se preserva; `producer` = `PRODUCER` da S2; `key`
     = a mesma heurística `payload["symbol"] or event_id`; `ts` = `created_at` da
     linha, documentado como substituto: o `ts` histórico não existe, ele era
     gerado no dispatch);
  3. trocar o `enqueue` da S2 pelo `hunter_core.events.outbox.enqueue` na mesma
     transação da decisão;
  4. só então apagar `shadow_outbox`.
  Se o passo 1 não drenar (Redis fora), o passo 2 ainda é seguro: as linhas
  chegam como pendentes no genérico e saem pela reconciliação.

## Coisas que decidi não fazer

- **`market.backfill.requested`** não existe em `hunter_core.events.streams` nem
  em nenhum produtor. Ele é o pedido do *scanner* ao market-worker (T2.5, que não
  existe), não um produtor durável do market-worker. Não inventei o stream.
- **Retry/DLQ por `attempts`.** `attempts` e `last_error` são gravados e
  observáveis, mas nenhuma linha é abandonada por excesso de tentativas: sem um
  destino para a carta morta, desistir seria perder o evento em silêncio. Uma
  linha com payload ilegível (não é envelope) é contabilizada, logada e **pulada**
  para não travar o stream — mas continua na tabela.
- **Índice/coluna de claim (`claimed_by`/`claimed_at`).** Resolvido com
  `FOR UPDATE SKIP LOCKED`, que não precisa de coluna nova nem de migração.

## Segunda rodada com a Astra (revisão do diff) — o que ficou pendente

Ela devolveu REQUEST_CHANGES com cinco must-fix. Os cinco foram corrigidos (cada
um com teste que falha sem a correção); o que **não** ficou fechado dentro dos
meus arquivos:

- **`packages/exchange-adapters/hunter_exchanges/binance/rest.py:161`** chama
  `record_used_weight()` **antes** de olhar o status 429/418. Fechei o buraco
  pelo lado que me cabe — `record_used_weight` agora degrada (log + flag) em vez
  de propagar um erro do Redis, então o `_get` sempre alcança o ramo do 429 e
  aplica o `cooldown()`. Mas a **ordem** continua frágil: qualquer exceção nova
  nessa reconciliação volta a pular o cooldown. O certo é `rest.py` tratar
  429/418 **antes** de reconciliar o header. Fora da minha lista de arquivos —
  para o exchange-integration-specialist em T1.6b.

## Retenção de `outbox_events` (para o database-architect)

Medido no stack local com 200 mercados: ~2.900 linhas em 6 minutos de operação,
ou seja da ordem de **700 mil linhas/dia** só do market-worker. Nada apaga linhas
despachadas hoje. `docs/DATABASE.md` já define retenção por DELETE diário em
lotes para outras tabelas; `outbox_events` precisa entrar nessa política —
sugestão: apagar `dispatched_at IS NOT NULL AND dispatched_at < now() - 7 dias`,
prazo que precisa ser **maior** que a janela de replay que se queira suportar
(`reconcile(since=...)` só alcança o que ainda estiver na tabela).

## Custo do enqueue no caminho quente (achado meu, na prova operacional)

A primeira versão emitia **um INSERT por evento**. Numa virada de minuto com 200
mercados isso são ~200 round trips extras dentro da transação de flush, no
caminho quente do `drain_loop` — e o `/ready` do market-worker ficou vermelho em
`persistence` (a fila de persistência atrasando), com o `outbox` verde. Corrigido
com `enqueue_many`: um único `INSERT ... ON CONFLICT DO NOTHING` multi-linha por
flush, igual ao que o resto de `persist_rows.py` já fazia. Teste:
`services/market-worker/tests/test_outbox_producers.py::test_a_whole_flush_of_candles_costs_one_insert`.

## Retomada (2026-09-06) — o que a segunda passada mudou

1. **O "bug do `build_envelope`" não existia no código.** A quebra era **imagem
   Docker obsoleta**: `hunter-api:dev` fora construída no meio da edição anterior
   e não continha a reexportação. `docker run --rm --entrypoint sh hunter-api:dev
   -c "grep -c build_envelope .../outbox.py"` devolvia `0`, enquanto no host o
   import sempre funcionou e `apps/api/.../test_t17_market_pipeline_contract.py`
   coletava e passava. Corrigido com rebuild; detalhes em `t29-proof.md` §0.
2. **Três erros de pyright fechados** (a suíte estava verde, o typecheck não):
   - `outbox_store.py:277` passava valores Python crus para `tuple_()`. Agora o
     cursor de replay usa `literal(valor, Coluna.type)`, o que também faz a
     comparação de row-value e o driver concordarem sobre datetimes com tz em
     vez de depender da coerção em runtime. Coberto por
     `test_replay_pages_by_the_whole_sort_key_not_by_id`.
   - `test_outbox_producers.py:303`: `list` é invariante; a variável agora é
     anotada `list[PersistItem]`.
3. **`producer` do backfill REST.** `recovery.py:157` chama `upsert_candles` sem
   `producer=`, então as velas recuperadas saem como `market-worker` e não
   `market-worker@{instance}` — visto no envelope real da prova. O docstring de
   `durable.py` afirmava o oposto; foi corrigido e o comportamento real está
   fixado em `test_a_rest_backfilled_candle_is_published_too`.
   **Não plumbei a instância** porque exigiria mudar quatro assinaturas
   (`run_recovery` -> `check_gaps` -> `_recover_one` -> `recover_registered`) e
   sete chamadas em testes, num caminho de gap recovery delicado (T1.6), por um
   campo puramente diagnóstico: `event_id` vem da chave natural da vela, então a
   identidade é idêntica pelos dois caminhos. **Follow-up:** passar
   `runtime.instance` pela cadeia quando alguém já estiver mexendo em
   `recovery.py`.

## Fora do meu escopo, encontrado ao rodar os gates

- **`packages/exchange-adapters/tests/unit/test_ws_client.py::test_quiet_socket_rotates_cleanly_at_the_rotation_deadline`
  é intermitente.** Em execução isolada: passou, passou, falhou
  (`assert 3 == 2` no número de conexões). O teste crava a contagem exata de
  reconexões com `max_connection_age_s=0.02` — um prazo real de 20 ms numa
  máquina carregada rende uma rotação a mais. `ws_client.py` e
  `test_ws_client.py` **não** são tocados pelo diff T2.9. Para o
  exchange-integration-specialist (T1.6): a asserção deveria ser `>= 2`, ou o
  prazo deveria vir de um relógio injetado em vez do relógio real.
- **`packages/indicators/hunter_indicators/regime/model.py` tem 465 linhas
  (> 350) e `regime/classifier.py` falha `ruff check` (I001) e
  `ruff format --check`.** Arquivos da T2.3, que aterrissaram no meio desta
  retomada (o gate de tamanho passava com 246 arquivos no início e falhou com
  251 no fim). `packages/indicators` está fora da minha lista permitida. Para o
  quant-engineer/T2.3.

## Segunda opinião da Astra sobre o diff da retomada (`astra-review-T2.9-outbox-diff.md`)

Três must-fix. Dois foram corrigidos; o terceiro é uma decisão que não é minha.

- **CORRIGIDO (HIGH) — prontidão verde para sempre sem nenhuma observação.**
  `OutboxHealth.ready()` devolvia `True` sempre que `last_sweep_at is None`. Se a
  consulta de backlog falhasse **desde o boot** (um `GRANT` faltando em
  `outbox_events`, por exemplo, com o health check do banco e os INSERTs dos
  produtores ainda funcionando), `run_dispatcher` só logava e tentava de novo, e
  o `/ready` respondia verde indefinidamente a partir de um retrato nunca
  tirado. Agora `OutboxHealth` tem `started_at` e a graça de partida é
  **limitada** a `max_lag_s * STALE_SWEEP_FACTOR`: sem a primeira varredura
  dentro dela, vermelho. Teste:
  `test_health_is_green_during_the_startup_grace_but_not_forever`.
- **CORRIGIDO (MEDIUM) — replay truncado em silêncio.** `reconcile(since=...)`
  parava em `limit` e devolvia só a contagem. Como `since` é o único botão do
  chamador, duas chamadas com o mesmo `since` republicavam a mesma primeira
  página e a cauda ficava inalcançável para sempre. Agora `replay_since` loga
  `outbox_replay_truncated` com `resume_since` (o `created_at` da última linha
  publicada), que é por onde continuar. Retomar nesse instante republica os
  empates — o lado seguro, porque duplicata o consumidor já deduplica e pular
  perderia evento numa recuperação. Teste:
  `test_a_truncated_replay_says_so_and_says_where_to_resume`.
- **CORRIGIDO em 2026-09-06 (HIGH) — fallback do rate limit contrariava o aceite da M2.**
  O orquestrador decidiu pelo aceite; ver a seção "DECIDIDO" abaixo.

Aproveitei a sugestão dela de dividir `outbox.py` (estava em 349/350 e passou de
350 com a correção da prontidão): `reconcile`/`_replay` saíram para
`hunter_core/events/outbox_recovery.py`. A costura é de responsabilidade real,
não de contagem de linhas — recuperação de *stream perdido* é read-only, sem
lock e sem re-marcação, ao contrário do despacho contínuo, e por isso tem
paginação própria (`PAGE`) em vez do `MICRO_BATCH` do despachante (o que também
elimina o import circular). `outbox.py` ficou em 333 linhas.

## DECIDIDO (2026-09-06, orquestrador): rate limit fail-closed durante queda do Redis

**Veredito:** prevalece o **aceite conjunto da M2** (`.claude/state/dialogue-M2.md`
linha T2.9: "sem orçamento independente durante indisponibilidade"), não o brief
original da T2.9 ("fallback em memória se o Redis cair"). Motivo: N shards com
bucket local cheio somam N cotas contra a cota única que a Binance contabiliza
por IP de saída, e o preço do erro é um ban de IP — irreversível no curto prazo.
Um gap pode esperar o Redis voltar; um IP banido não.

### O que mudou

1. **Fallback em memória removido do caminho de indisponibilidade.**
   `TokenBucketRateLimiter._try_consume` devolve `None` ("coordenação fora") em
   vez de cair para o bucket local; `acquire` então **suspende**: backoff curto
   exponencial com jitter (`rate_limit_suspension.backoff_s`, 0,25 s → 2 s +
   25 % de jitter), re-tentativa a cada volta e, esgotado o `max_wait_s` do
   chamador, `RateLimited(reason="redis_unavailable")`. Nunca uma exceção do
   Redis: `RateLimited` é o sinal que `rest.py`, `recovery.py` e os laços de
   funding/OI já sabem sobreviver.
   `record_used_weight` também suspende em vez de propagar (a ordem frágil de
   `rest.py:161` continua valendo: ele reconcilia o header antes de olhar o
   429/418, e uma exceção ali pularia o `cooldown()`).
2. **O bucket em memória continua existindo — só que para o caso "nunca houve
   coordenação"** (limiter construído **sem** `redis=`: testes de unidade, um
   `BinanceRestClient()` de script). Isso não é indisponibilidade, é um
   processo só. Ficou isolado em `rate_limit_local.LocalBuckets` (o split que
   trouxe `rate_limit.py` de 377 de volta para 336 linhas).
   **Cuidado que sobra:** um caminho de produção que esqueça de passar `redis=`
   volta a ter orçamento próprio sem nenhum alarme. Hoje o único construtor de
   produção é `services/market-worker/hunter_market_worker/config.py:72`, que
   passa. Se um segundo serviço passar a falar REST, isso vira um risco real e
   o certo é o construtor exigir a coordenação explicitamente (`redis=None` só
   com um argumento `uncoordinated=True`).
3. **Observabilidade.** Contador
   `exchange_rest_admissions_suspended_total{exchange,bucket,reason}` (uma
   incrementação por admissão recusada, não por tentativa de re-probe) e os
   logs de transição `rest_admissions_suspended` / `rest_admissions_resumed`
   (uma linha por transição, não por request). O market-worker publica
   `rest_gate` (`ok`/`suspended`) no hash `hb:market:{exchange}` e no
   `rt:system`.
4. **Recovery de gaps espera.** `run_recovery` consulta
   `recovery.rest_gate_suspended(adapter)` **antes** de consumir o slot de
   `last_check`: enquanto suspenso não chama `check_gaps` (nenhum
   `ingestion_gaps.attempts` avança, nada vira `failed` por causa de uma queda
   de infraestrutura) e volta a checar em `POLL_S`, não em `CHECK_INTERVAL_S`.

### `/ready` ganhou o campo `rest_gate` (retomada de 2026-09-06)

A passada anterior parou no contrato de `hunter_core.runtime._build_app`
(`dict[str, bool]`: um `rest_gate: false` deixaria a prontidão vermelha, que é
o que o brief proíbe) e `packages/core` estava fora daquela lista de arquivos.
Nesta retomada ele estava dentro, e o follow-up foi executado — mas **não** como
`str | bool` no mesmo dicionário de checks: um campo que não participa do
veredito não deve entrar pela porta dos que participam, senão a próxima pessoa
que somar `details.values()` volta a acoplar diagnóstico a veredito.

`WorkerRuntime` ganhou `status_details: dict[str, Callable[[], str]]` — leituras
de estado síncronas e baratas, mescladas no corpo do `/ready` **depois** de o
`checks_ok` já estar decidido. O `run_market` registra
`status_details["rest_gate"] = lambda: rest_gate_status(adapter)` e o remove no
`finally`, junto com os readiness checks. Um detalhe que levantar exceção vira
`"unknown"` em vez de derrubar o endpoint que carrega o veredito (era
exatamente a classe de bug "verde/vermelho para sempre" que a Astra pegou no
`OutboxHealth`). Testes:
`packages/core/tests/unit/test_runtime.py::test_status_details_annotate_ready_without_changing_the_verdict`
e `::test_a_broken_status_detail_does_not_break_ready`;
`services/market-worker/tests/test_rest_gate.py::test_run_market_publishes_the_gate_on_ready_without_failing_it`.

**Ainda em aberto:** `apps/api/.../system_status.py` lê o hash com
`fields.get(...)`, então `rest_gate` já chega lá de forma aditiva, mas
`/system/market-status` **não** o expõe. `apps/**` está fora da minha lista;
é uma linha para o backend/frontend da T2.7.

### O que NÃO foi feito, e por quê
- **Custo de latência durante a queda, aceito conscientemente.** Com o
  `max_wait_s=30` padrão de `rest.py`, cada tentativa de request gasta até 30 s
  de backoff antes do `RateLimited`, e `_get` tenta 3 vezes → até ~90 s por
  chamada REST enquanto o Redis estiver fora. Os laços de funding/OI/universo
  ficam lentos (não morrem). O recovery não paga isso porque desiste antes.
  Se um dia incomodar, o botão é `max_wait_s` no chamador, não a política.
- **Uma queda que começa no meio de um ciclo de recovery** ainda gasta uma
  tentativa: o portão é consultado no início do ciclo, e o `fetch_candles` que
  já estava em voo falha por `FETCH_TIMEOUT_S`. Bounded e raro; fechar isso
  exigiria checar o portão dentro de `_recover_one` também.

## Terceira rodada com a Astra (`astra-review-T2.9-gate-failclosed.md`, 2026-09-06)

Três must-fix, todos reais e todos corrigidos com teste que falha sem a correção.
Ela também corrigiu uma afirmação minha na documentação.

1. **CORRIGIDO (HIGH) — o portão de IP falhava *aberto*.** `IpRateGate.wait_s()`
   cai para o espelho local quando a leitura do deadline compartilhado falha, e
   esse espelho é `0` sempre que o 429 aconteceu num **outro** shard. Numa falha
   parcial do Redis (a leitura do `blocked_until` falha, o `eval` do bucket
   responde) o `acquire` admitia o request sem saber do ban que outro processo
   já estava cumprindo — exatamente o que o portão existe para evitar. Agora
   `_gate_wait_s()` devolve `None` quando `gate.degraded`, e `None` entra no
   mesmo caminho de suspensão do bucket: portão ilegível é coordenação fora, e
   coordenação fora não admite nada. Teste:
   `test_an_unreadable_ip_gate_suspends_instead_of_admitting` (o fake responde
   ao bucket e recusa só o `IP_WAIT_SCRIPT`; sem a correção admite 10/10).
   A política de "espera ou desiste" foi para `Suspension.next_delay`, que é
   quem já era dona do backoff e do contador.
2. **CORRIGIDO (HIGH) — o Redis fora matava o worker pelo heartbeat.**
   Suspender admissões REST só mantém a ingestão viva se mais nada morrer da
   mesma queda. `run_heartbeat` é uma tarefa `forever()` do TaskGroup do market
   e escrevia `hb:market:*` e `rt:system` sem tratamento: um `ConnectionError`
   ali cancelava **todas** as irmãs, inclusive o WS que a política protege.
   Agora `_safe_publish` degrada para "heartbeat não publicado" (com log e sem
   `mark_success`, então o `last_success` não mente), no mesmo contrato que
   `safe_record_system_event` já dava ao Postgres. O hash expira pelo TTL, que
   é a leitura correta: o worker está degradado. Teste:
   `test_the_heartbeat_survives_redis_being_down`.
3. **CORRIGIDO (MEDIUM) — queda no meio do ciclo ainda queimava tentativas.**
   Era o buraco que eu mesmo tinha registrado como "bounded e raro" na seção
   anterior; a Astra mostrou que o custo não é bounded: quatro ciclos com o
   Redis fora levam o gap a `failed` por uma hora, ou seja dado de mercado
   perdido por causa de infraestrutura. `recover_registered` agora reconhece
   `is_coordination_outage(exc)` (só `RateLimited` com
   `reason="redis_unavailable"`) e devolve a tentativa em vez de gastá-la.
   Deliberadamente estreito: um `RateLimited` comum (orçamento gasto) e
   qualquer outro erro continuam contando, senão um gap quebrado de verdade é
   tentado para sempre. Testes: `test_a_coordination_outage_does_not_burn_a_gap_attempt`
   mais os dois de contraste.
4. **CORRIGIDO (nice-to-have) — colisão de nome em `status_details`.** Um
   diagnóstico chamado `redis` sobrescrevia o booleano do veredito no corpo do
   `/ready` e escondia o motivo do próprio 503. Agora vira `redis_detail`.
   Teste: `test_a_status_detail_never_overwrites_a_verdict_key`.
5. **CORREÇÃO NA DOCUMENTAÇÃO (ela tem razão).** Eu tinha escrito no §7 do
   PIPELINE que "a prontidão continua verde". O `rest_gate` sozinho de fato
   nunca deixa o `/ready` vermelho — mas numa queda **total** do Redis o
   `/ready` fica vermelho de qualquer jeito, pelo check `redis`, porque o
   worker também depende do Redis para coalescer, streams e heartbeat. O §7
   agora diz isso com todas as letras: o que continua é a **ingestão pelo WS**
   e a persistência, não o verde do `/ready`.

### O que ficou em aberto depois dessa rodada

- **`redis=None` continua admitindo** (`LocalBuckets`). A Astra insiste, com
  razão, que a garantia é condicional: é o construtor que decide. Hoje o único
  construtor de produção passa `redis=` (`config.py:72`) e há teste fixando o
  comportamento, mas a proteção certa continua sendo exigir
  `uncoordinated=True` para construir sem coordenação. Segue como follow-up
  (T1.6b), agora com o aval dela.
- **Retomada "de verdade" do recovery.** O teste força `adapter.status = "ok"`.
  Provar a retomada ponta a ponta exige um limiter real com Redis derrubado e
  religado no meio (integração com testcontainers, `docker stop`), que é o
  cenário da prova operacional, não da suíte de unidade. Não fiz.
- **`recovery.py` está em 338 linhas** e `rate_limit.py` em 341. Nesta rodada
  `rest_gate_suspended` mudou de `recovery.py` para `supervision.py` (que já
  era dona de `rest_gate_status`) para caber sem espremer nada; o próximo
  recurso que aterrissar em `recovery.py` vai precisar de um split de verdade
  (o candidato é `run_recovery`/`_should_check` num módulo de ciclo, e ele
  quebra os `monkeypatch.setattr(recovery, "check_gaps", ...)` das suítes).

## Quarta rodada com a Astra (reconciliação das correções, `astra-review-T2.9-gate-failclosed-fixes.md`)

Ela confirmou (1), (2) e o `-= 1` de (3), e achou um buraco que os meus três
testes não pegavam:

- **CORRIGIDO (HIGH) — o timeout chegava antes do `RateLimited`.**
  `FETCH_TIMEOUT_S` é 20 s e `rest.py:163` chama `acquire()` com o
  `max_wait_s=30` padrão. Ou seja: durante uma queda do Redis o backfill morre
  pelo `asyncio.wait_for` **antes** de o limiter conseguir levantar
  `RateLimited(reason="redis_unavailable")` — que era a única coisa que o meu
  predicado reconhecia. Na prática o caso comum continuava queimando tentativa.
  A correção deixa de olhar só o tipo da exceção e passa a olhar o **estado do
  portão**: `is_coordination_outage(exc) or rest_gate_suspended(adapter)`, o
  que cobre `TimeoutError`, `ConnectionError` e qualquer outra forma de morrer
  da mesma queda. Testes: `test_a_timeout_while_the_gate_is_suspended_does_not_burn_an_attempt`
  e o contraste `test_a_timeout_with_a_healthy_gate_still_burns_an_attempt`.
  (A alternativa era alinhar `max_wait_s` ao `FETCH_TIMEOUT_S`; não escolhi
  essa porque ela só troca a corrida de lugar — o estado do portão é a
  pergunta certa, e um falso positivo aqui é seguro: o gap continua aberto.)
- **CORRIGIDO (nice-to-have) — a colisão só estava meio resolvida.** Se
  existisse um check chamado `redis_detail`, o diagnóstico `redis` passaria a
  sobrescrever *esse*. Virou um laço de sufixo até achar chave livre.
- **CORRIGIDO (precisão) — o docstring de `_safe_publish` prometia demais.**
  "nothing is permanently lost" é largo: o `rt:system` é feed ao vivo sem
  replay, então uma transição que acontece **e volta** dentro da janela da
  queda some do pub/sub. O que converge é o *snapshot* atual, dentro de
  `HEARTBEAT_INTERVAL_S` depois da queda; o registro durável da transição é a
  linha em `system_events`, que vai pelo caminho do Postgres.

### Divergência que fica registrada (não resolvida por escolha)

Ela pediu um teste de ponta a ponta com limiter real e Redis derrubado no meio
do fetch, com o gap começando em 4 tentativas. Concordo que é o teste que
provaria a coisa toda, mas ele é de **integração com testcontainers** (derrubar
e religar o Redis no meio de um ciclo), não de unidade, e é o mesmo cenário da
prova operacional. Ficam os testes de unidade nas duas pontas (limiter e
recovery) e o furo permanece: nenhum teste automatizado exercita a composição
real limiter+timeout+recovery com um Redis de verdade morrendo. Para T1.6b.
