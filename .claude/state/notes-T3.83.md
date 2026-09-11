# T3.83 — `shadow_consumer_restarting` / `shadow_version_evaluation_failed` (Redis TimeoutError)

Overnight 10→11/09, os 4 shards do `strategy-worker` na VPS logaram `shadow_consumer_restarting` e
`shadow_version_evaluation_failed` com `redis.exceptions.TimeoutError: Timeout reading from
redis:6379`. Investigação read-only na VPS (foreground, `timeout 290`) + correção no código.

## 1. VPS — read-only

Containers (`docker ps` — todos `hunter-strategy-worker-{1,1-1,2-1,3-1}`):

```
$ docker inspect -f '{{.Name}} started={{.State.StartedAt}} restarts={{.RestartCount}}' ...
/hunter-strategy-worker-1   started=2026-09-10T23:19:27.987653626Z restarts=0
/hunter-strategy-worker-1-1 started=2026-09-10T23:19:27.627246846Z restarts=0
/hunter-strategy-worker-2-1 started=2026-09-10T23:19:28.16691938Z  restarts=0
/hunter-strategy-worker-3-1 started=2026-09-10T23:19:27.801019557Z restarts=0
```

`restarts=0` a nível de container — o "restart" do brief é o backoff *interno* do
`run_consumer`, não um restart do Docker. Todos os 4 shards subiram às 23:19:27–28Z (deploy),
dentro da janela relatada (23:20Z–07:45Z).

### 1.1 Timestamps exatos (`docker logs --since 2026-09-10T23:00:00Z --until 2026-09-11T08:00:00Z <container> | jq` filtrando por evento)

| Timestamp (UTC) | Shard | Evento | Chamada Redis que estourou |
|---|---|---|---|
| 00:00:06.483Z | strategy-worker-1-1 | `shadow_consumer_restarting` | `XAUTOCLAIM` |
| 00:00:06.534Z | strategy-worker-2-1 | `shadow_consumer_restarting` | (traceback sem xautoclaim/xreadgroup — provável 2ª leitura do mesmo lote) |
| 00:00:06.821Z | strategy-worker-3-1 | `shadow_consumer_restarting` | idem |
| 00:00:07.021Z | strategy-worker-1   | `shadow_consumer_restarting` | `XAUTOCLAIM` |
| 00:00:12.494Z | strategy-worker-1-1 | `consume_read_deadline` (tolerado) | `XREADGROUP` |
| 00:00:12.767Z | strategy-worker-2-1 | `consume_read_deadline` (tolerado) | `XREADGROUP` |
| 00:00:13.378Z | strategy-worker-1   | `shadow_consumer_restarting` | `SISMEMBER` (`is_processed`, dentro de `consume()`) |
| 00:00:13.380Z | strategy-worker-1   | `shadow_version_evaluation_failed` | `mean_reversion v8` / `binance:XRPUSDT` |
| 00:00:13.382Z | strategy-worker-1   | `shadow_version_evaluation_failed` | `mean_reversion v8` / `binance:ETHUSDT` |
| 00:00:13.379Z | strategy-worker-3-1 | `consume_read_deadline` (tolerado) | `XREADGROUP` |
| 00:00:17.698Z | strategy-worker-1-1 | `shadow_consumer_restarting` | `XAUTOCLAIM` |
| 00:00:17.970Z | strategy-worker-2-1 | `shadow_consumer_restarting` | `XAUTOCLAIM` |
| 00:00:18.754Z | strategy-worker-3-1 | `shadow_consumer_restarting` | `XAUTOCLAIM` |

**Coincidem entre shards** — tudo dentro de uma janela de ~12,3 s (00:00:06.483Z–00:00:18.754Z),
os 4 shards ao mesmo tempo. Isso descarta conexão isolada de um shard: é o **Redis
compartilhado** que estagnou por alguns segundos, não uma rede ruim de um container.

**Não coincide com o cron de backup nem com fronteiras de 15 min em geral.** `grep` na mesma
janela completa (23:00Z–08:00Z) não encontrou nenhum outro cluster de eventos — só este, às
00:00 UTC. O backup roda `17 3 * * *` (`/etc/cron.d/hunter-backup`, ver abaixo) — sem relação. O
próprio `00:00 UTC` é ao mesmo tempo fronteira de 15 min, de hora e de dia; o fato de não haver
outro cluster nas fronteiras de 15/30/45/01:00 etc. da mesma madrugada aponta para o fechamento
**diário** (1h/4h/1d simultâneos à meia-noite UTC) como o gatilho mais provável, não o grid de 15
min por si.

### 1.2 Cron / timers do sistema

```
$ cat /etc/cron.d/hunter-backup
17 3 * * * hunter bash /opt/project-hunter/infra/vps/backup_postgres.sh >> /opt/backups/backup.log 2>&1
```

`systemctl list-timers` mostra `dpkg-db-backup.timer`/`logrotate.timer` disparando à meia-noite
**local** (CEST, UTC+2) = 22:00 UTC do dia anterior — não bate com 00:00 UTC. Nenhum cron/timer do
SO cai em 00:00 UTC.

### 1.3 `redis-cli INFO`/`SLOWLOG`/`XINFO` (lidos às ~07:48 UTC / 04:48 BRT, não no instante do
incidente — Redis não guarda histórico retroativo de latência além do `SLOWLOG`, que já girou)

```
INFO clients:  connected_clients=79  blocked_clients=12  clients_in_timeout_table=12
INFO memory:   used_memory=13 394 163 872 (12,47 GiB)  used_memory_peak=15 357 134 000 (14,30 GiB, 87,22%)
INFO stats:    instantaneous_ops_per_sec=9585  total_commands_processed=4 188 453 509
INFO persistence:
  rdb_bgsave_in_progress: 1        (BGSAVE rodando NO MOMENTO da leitura)
  rdb_saves: 2459
  rdb_last_bgsave_time_sec: 164
  rdb_current_bgsave_time_sec: 86  (ainda rodando)
  aof_last_rewrite_time_sec: 160
CONFIG GET maxmemory:        0            (sem teto)
CONFIG GET maxmemory-policy: noeviction
CONFIG GET save:             "3600 1 300 100 60 10000"  (dispara sozinho com ~9 585 ops/s)
CONFIG GET slowlog-log-slower-than: 10000  (10 ms)
SLOWLOG LEN: 128 (cheio, girando)
SLOWLOG GET 20: dominado por XREADGROUP/EVALSHA/HSET/SET de 10–22 ms cada, um deles
  (id 486) um HSET de ~371 campos em `mkt:binance:coverage` gravado às 00:00:23Z/00:00:21Z
  (timestamps de `sym:*` dentro do próprio payload) — confirma a rajada de escrita coincidindo
  com o horário do incidente.
```

Leitura: Redis com dataset de 12+ GiB sem `maxmemory`, `BGSAVE`/`AOF rewrite` quase contínuos
(2459 saves, o de agora levando >164 s) disparados pela política `60 10000` sob ~9,6 mil ops/s.
Fork + COW de um dataset desse tamanho é conhecido por empurrar comandos individuais além de
alguns segundos durante o fork; combinado com a rajada de escrita/leitura de meia-noite (todos os
timeframes fechando ao mesmo tempo — a mesma rajada que T3.74f já mediu saturando um core de CPU
do `strategy-worker`), é condição suficiente para alguns comandos passarem do `socket_timeout` de
5 s por alguns segundos, exatamente a janela observada.

```
$ redis-cli XINFO GROUPS market.candles.closed   (lido depois, agora)
strategy-worker.shadow.{0,1,2,3}of4: pending=0 lag=0 (todos)
```

`pending=0` em todos os 4 grupos confirma que a **mensagem** (a barra inteira) foi sempre
redistribuída corretamente pelo `XAUTOCLAIM` já existente — nenhuma barra ficou presa no nível de
stream. A perda, quando existe, é mais fina: uma *versão* dentro de uma barra (ver §2).

## 2. Código

### 2.1 `packages/core/hunter_core/events/consume.py`

`BLOCK` (`CONSUME_BLOCK_MS=2000` no strategy-worker) já era menor que `socket_timeout` (5 s,
`hunter_core/redis.py::_SOCKET_TIMEOUT_S`) — HIGH-4 já resolvia a forma clássica do "self-inflicted
timeout" (`BLOCK 5000` vs `socket_timeout=5`). O que faltava: só `XREADGROUP` tinha
retry-com-backoff (`try/except RedisTimeoutError`, até `MAX_CONSECUTIVE_TIMEOUTS=5`). `XAUTOCLAIM`
(não bloqueante, mas sujeito ao mesmo `socket_timeout`) e o `SISMEMBER` de `is_processed` (chamado
por `consume()` a cada mensagem, antes de entregá-la) não tinham nenhuma tolerância — um único
timeout aí derrubava `run_consumer` inteiro. Os tracebacks da VPS confirmam: 2 dos 4
`shadow_consumer_restarting` vieram de `XAUTOCLAIM`, 1 de `SISMEMBER`.

**Corrigido**: os três agora passam pelo mesmo padrão retry-com-backoff, com contadores
independentes por operação (um contador do sucesso de `XAUTOCLAIM` não pode apagar a sequência de
timeouts de `XREADGROUP`, e vice-versa — bug encontrado e corrigido durante o TDD desta tarefa,
antes de existir em produção). `consume_read_deadline` ganhou um campo `op` (`xautoclaim` /
`xreadgroup` / `is_processed`).

### 2.2 `services/strategy-worker/hunter_strategy_worker/consumer.py`

`handle_candle` isola a falha de cada versão (T3.26: uma versão com parâmetro congelado quebrado
não deve abortar as demais) — mas até agora isso incluía `RedisTimeoutError`: contado em
`hunter_shadow_version_failed_total`, logado como `shadow_version_evaluation_failed`, e a barra
**segue confirmada** (`ack`) ao final do laço. Como o `event_id`/redelivery só protege a
*mensagem* (a barra inteira), não a *versão* individual, um timeout de Redis durante
`evaluate_slot` fazia essa versão nunca decidir sobre aquela barra — para sempre, sem
reprocessamento e sem sinal visível de que era falha de infra, não de estratégia. Batizado nesta
tarefa: **decisão silenciosamente perdida por timeout de Redis** (`shadow_bar_skipped_late_backlog`
já nomeia o análogo para atraso; este era o buraco equivalente para timeout).

**Corrigido**: `RedisTimeoutError` tem ramo próprio no laço de versões — conta
`hunter_shadow_redis_timeouts_total{stage="version_evaluate"}`, loga
`shadow_version_redis_timeout` e **relança** em vez de engolir. Isso deixa a mensagem inteira sem
`ack`, então ela é reentregue pelo `XAUTOCLAIM` já existente assim que `claim_idle_ms` expira —
seguro porque o próprio docstring do módulo já garante idempotência: uma versão que já commitou
antes do timeout é *no-op* na redelivery (barreira do slot). `run_consumer` ganhou o mesmo
contador em `stage="consumer_loop"` quando é o laço externo que reinicia por timeout.

`consumer.py` estava a 342/350 linhas; a constante `DECISION_MARKET_TYPE` (só um comparador, mas
com ~30 linhas de docstring histórico do T3.73) foi movida para
`hunter_strategy_worker/decision_market_type.py` — puro split por tamanho, sem mudança de
comportamento nem de import externo (só usada dentro de `consumer.py`).

### 2.3 `services/strategy-worker/hunter_strategy_worker/metrics.py`

Novo `hunter_shadow_redis_timeouts_total` (`Counter`, label `stage` ∈
{`version_evaluate`, `consumer_loop`}).

## 3. Comandos e resultados (íntegra relevante)

```
$ uv run pytest packages/core/tests/unit/test_events_consume.py packages/core/tests/unit/test_events_consume_batch.py -q
26 passed in 0.95s

$ uv run pytest packages/core/tests/unit -q -k "consume or event"
70 passed, 1155 deselected in 13.68s

$ uv run pytest services/scanner-worker/tests/test_consumers.py -q
12 passed in 3.35s

$ uv run pytest services/strategy-worker/tests/test_consumer_isolation.py services/strategy-worker/tests/test_consumer_supervision.py services/strategy-worker/tests/test_consumer_sharding.py -q
14 passed in 2.31s

$ uv run ruff check <arquivos tocados>
All checks passed!

$ uv run python infra/scripts/check_file_size.py
scanned 628 files; 0 over budget, 0 grandfathered

$ uv run pyright packages/core/hunter_core/events/consume.py services/strategy-worker/hunter_strategy_worker/consumer.py services/strategy-worker/hunter_strategy_worker/decision_market_type.py services/strategy-worker/hunter_strategy_worker/metrics.py
0 errors, 0 warnings, 0 informations
```

`uv run pytest services/strategy-worker -q` (suíte completa do serviço, incluindo os marcadores
`integration`) foi disparada em foreground mas excedeu o timeout de 120 s do shell e o harness a
moveu para segundo plano automaticamente — não foi uma escolha deliberada de rodar em background.
Terminou depois (24m30s, banco Postgres local compartilhado com outros agentes na mesma árvore):
**819 passed, 2 failed**. As duas falhas (`test_spot_not_in_shadow_universe.py::
test_a_spot_candle_writes_no_shadow_row` — `ForeignKeyViolationError` em `candles`/`markets`; e
`test_version_roster.py::TestRosterCounts::test_a_version_frozen_with_this_code_is_runnable` —
roster com conteúdo de outra sessão) passam isoladas
(`uv run pytest <os dois ids> -q` → **2 passed in 20.85s**), confirmando ruído de concorrência no
banco de teste compartilhado, não regressão deste diff. Nesse meio tempo também rodei o escopo
equivalente e conclusivo `uv run pytest services/strategy-worker -m unit -q` →
**438 passed, 383 deselected in 47.94s**.

Depois do `ruff format` (2 arquivos reformatados por linha longa), `consume.py` voltou a passar de
350 linhas (354) — cortado de volta para **349** encurtando dois comentários (mesmo conteúdo, menos
prosa); `check_file_size.py`, `ruff check` e `ruff format --check` voltaram a passar limpos e a
suíte de testes acima foi re-executada depois do corte (53 passed).

## 4. `git status --porcelain` (arquivos desta tarefa)

```
 M "obsidian/07-BUGS/Open Bugs.md"
 M packages/core/hunter_core/events/consume.py
 M packages/core/tests/unit/test_events_consume.py
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/metrics.py
 M services/strategy-worker/tests/test_consumer_isolation.py
 M services/strategy-worker/tests/test_consumer_supervision.py
?? .claude/state/notes-T3.83.md
?? services/strategy-worker/hunter_strategy_worker/decision_market_type.py
```

Nada em `apps/**` foi tocado, nenhum `.env*` foi lido/escrito, nenhum container foi parado ou
recriado, nenhuma escrita foi feita na VPS (toda a investigação de §1 foi `docker logs`/`docker
inspect`/`redis-cli`/`cat`/`crontab -l`/`systemctl list-timers`, comandos de leitura, em foreground,
com `timeout 290`).
