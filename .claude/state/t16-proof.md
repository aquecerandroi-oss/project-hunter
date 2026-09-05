# T1.6 — Prova operacional do market-worker contra a Binance (dado real)

Executado por Sexta-feira em 2026-09-05, stack local `infra/docker/docker-compose.yml`.
Regra: nada aqui é declaração — cada linha tem o comando e a saída real colada.

---

## 0. Build e subida

```
$ docker compose -f infra/docker/docker-compose.yml build api
...
#52 naming to docker.io/library/hunter-api:dev done
#52 unpacking to docker.io/library/hunter-api:dev 10.7s done
 Image hunter-api:dev Built
EXIT=0
```

```
$ docker compose -f infra/docker/docker-compose.yml up -d migrate api market-worker
 Container docker-migrate-1 Exited
 Container docker-market-worker-1 Started
 Container docker-api-1 Started
```

Egress até a Binance a partir do container do worker (pré-requisito de tudo):

```
$ docker compose ... exec -T market-worker python -c "<urlopen fapi.binance.com>"
status 200 b'{"serverTime":1788625352881}'
symbols total 895
TRADING PERPETUAL USDT 526
```

Configuração vigente: `market_universe_size = 200`, `market_universe_refresh_s = 900`
(`packages/core/hunter_core/settings.py:93,105`).

---

## 1. BUG CRITICAL-1 — rate limiter morre contra Redis real (encontrado nesta prova)

Primeira subida do worker contra Redis real. O universo **nunca** carregou:

```
$ docker compose ... logs --tail=200 market-worker
2026-09-05T16:19:58Z info  market_worker_starting          exchange=binance role=market
2026-09-05T16:19:58Z info  partition_startup_check_ok      target=2026-09-05T16:19:58.286801+00:00
2026-09-05T16:19:58Z info  partition_lookahead_ready
2026-09-05T16:19:58Z error market_universe_refresh_failed
Traceback (most recent call last):
  File "/app/services/market-worker/hunter_market_worker/universe.py", line 325, in run_universe
    monitored = await refresh_universe(...)
  File "/app/packages/exchange-adapters/hunter_exchanges/binance/rest.py", line 146, in _get
    await limiter.acquire(bucket, weight)
  File "/app/packages/exchange-adapters/hunter_exchanges/rate_limit.py", line 242, in _consume_redis
    result = await self._redis.eval(...)
redis.exceptions.ResponseError: value is not an integer or out of range script: ef72698071095b337b29adae4cf3d955b81f3d7c, on @user_script:26.
2026-09-05T16:20:01Z info  127.0.0.1:48226 - "GET /ready HTTP/1.1" 503
```

**Causa raiz** (reproduzida, não inferida): linha 26 de `_ACQUIRE_SCRIPT` é
`redis.call('EXPIRE', key, ARGV[5])`; ARGV[5] é `_bucket_state_ttl_s`, um **float**
(`120.0`, `rate_limit.py:182`). redis-py serializa como `"120.0"` e `EXPIRE` recusa
string não inteira. Reprodução isolada contra o Redis do compose:

```
$ redis-cli SET tmpkey v
OK
$ redis-cli EVAL "redis.call('EXPIRE', KEYS[1], ARGV[1]) return 1" 1 tmpkey 120.0
ERR value is not an integer or out of range script: ... on @user_script:1.
$ redis-cli EVAL "redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1])) return 1" 1 tmpkey 120.0
(integer) 1
```

`_RECORD_USED_WEIGHT_SCRIPT` não é afetado (já faz `tonumber(ARGV[5])`).
Por que a suíte não pegou: `tests/unit/test_rate_limit.py::_FakeRedisEval` reimplementa
a semântica do Lua em Python — a tipagem enviada ao Redis nunca é exercitada.

**Comportamento honesto observado apesar do bug** (isto conta como prova a favor do T1.3):
- o processo **não** morreu: a falha do universo é capturada e re-tentada;
- `hb:market:binance` foi escrito com `ws_state=disconnected`, `markets_monitored=0`;
- `/ready` respondeu **503** e o healthcheck do Compose marcou o container `unhealthy`.

```
$ docker compose ... ps market-worker
docker-market-worker-1   hunter-api:dev   market-worker   Up 57 seconds (unhealthy)
$ redis-cli HGETALL hb:market:binance
last_event_at        (vazio)
ws_state             disconnected
subscriptions        0
reconnects           0
markets_monitored    0
open_gaps            0
ts                   2026-09-05T16:20:53.795160+00:00
```

Correção despachada para `exchange-integration-specialist` (arquivos permitidos:
`packages/exchange-adapters/hunter_exchanges/rate_limit.py` + testes).

---

## 2. Depois da correção — o pipeline funciona com dado real

Imagem reconstruída com o fix (`docker compose build api` → `BUILD_EXIT=0`) e
`docker compose up -d --force-recreate market-worker`. Log real, 40 s depois do boot:

```
16:28:27 info HTTP Request: GET https://fapi.binance.com/fapi/v1/klines?symbol=USELESSUSDT&interval=1m&... "HTTP/1.1 200 OK"
16:28:28 info market_gap_recovered  candles_inserted=1500  symbol=USELESSUSDT
16:28:30 info market_gap_recovered  candles_inserted=1500  symbol=HYPEUSDT
16:28:32 info 127.0.0.1:59362 - "GET /ready HTTP/1.1" 200
16:28:34 info market_gap_recovered  candles_inserted=1500  symbol=DOGEUSDT
...
```

`/ready` passou de **503** (antes do fix, sem universo) para **200**.

### 2.1 Hot state real no Redis

```
$ redis-cli HGETALL mkt:binance:BTCUSDT:ticker
ts       2026-09-05T16:28:52.321000+00:00
last     79801.30
bid      79801.20
ask      79801.30
bid_qty  17.563
ask_qty  8.532

$ redis-cli HGETALL mkt:binance:BTCUSDT:deriv
funding_rate      0.00002391
funding_kind      estimated
next_funding_time 2026-09-06T00:00:00+00:00
funding_ts        2026-09-05T16:28:43.001000+00:00
mark_price        79801.64594203
index_price       79843.89630435
mark_ts           2026-09-05T16:28:43.001000+00:00

$ redis-cli HGETALL hb:market:binance
last_event_at     2026-09-05T16:28:56.638000+00:00
ws_state          connected
subscriptions     1200
reconnects        0
markets_monitored 200
open_gaps         0
ts                2026-09-05T16:28:58.568558+00:00
```

**Preço muda entre duas leituras** (exigência explícita da tarefa):

```
$ redis-cli HMGET mkt:binance:BTCUSDT:ticker ts last bid ask      # leitura A
2026-09-05T16:29:06.878000+00:00 / 79812.70 / 79812.70 / 79812.80
$ sleep 12
$ redis-cli HMGET mkt:binance:BTCUSDT:ticker ts last bid ask      # leitura B
2026-09-05T16:29:18.744000+00:00 / 79823.90 / 79823.80 / 79823.90
```

Trades são reais (msgpack decodificado, `trade_id` da Binance, lado e quantidade):

```
$ redis-cli LRANGE mkt:binance:BTCUSDT:trades 0 2
ts 2026-09-05T16:29:23.511000+00:00 price 79834.90 qty 0.500 side sell trade_id 3441132746
ts 2026-09-05T16:29:11.091000+00:00 price 79813.50 qty 0.001 side buy  trade_id 3441132593
ts 2026-09-05T16:28:16.359000+00:00 price 79801.80 qty 0.003 side sell trade_id 3441132365
```

### 2.2 Postgres real (≈ 2 min depois do boot)

```
$ psql -c "select count(*) from markets where is_monitored"
 200
$ psql -c "select count(*), max(open_time) from candles where is_final"
 76900 | 2026-09-05 16:29:00+00
$ psql -c "select count(*) from market_snapshots"
 236
$ psql -c "select timeframe, status, count(*) from ingestion_gaps group by 1,2"
 1m | open      | 342
 1m | recovered |  58
$ psql -c "select level, component, event, count(*) from system_events group by 1,2,3"
 warning | market-worker | ws_state_changed | 1
 warning | market-worker | ws_reconnected   | 1
```

Os dois `system_events` são a transição de boot (`disconnected -> connecting -> connected`).
Os gaps são o bootstrap sem watermark previsto no plano: por símbolo, um gap de 24 h
(recuperado por REST, 1500 velas) e um gap de 1 minuto para o minuto em que o worker
ainda estava subindo:

```
$ psql -c "select m.symbol, g.status, g.gap_start, g.gap_end, g.attempts from ingestion_gaps g join markets m on m.id=g.market_id where m.symbol='BTCUSDT'"
 BTCUSDT | recovered | 2026-09-04 15:27:00+00 | 2026-09-05 16:26:00+00 | 1
 BTCUSDT | open      | 2026-09-05 16:27:00+00 | 2026-09-05 16:27:00+00 | 0
```

---

## 3. API real (item 4 da tarefa)

As rotas de mercado exigem token Clerk e eu não tenho sessão de navegador. Provei em dois
níveis: (a) que a autenticação está mesmo ligada, por HTTP real; (b) que o **código exato
que o handler executa** devolve os dados reais, chamando o serviço dentro do container `api`
contra o Postgres e o Redis de verdade.

### 3.1 A auth está ligada (HTTP real, sem token)

```
$ curl -s -o /dev/null -w '%{http_code}' localhost:8000/api/v1/markets                -> 401
$ curl ... /api/v1/markets/binance/BTCUSDT                                            -> 401
$ curl ... /api/v1/system/workers                                                     -> 401
$ curl ... /health                                                                    -> 200
$ curl ... /ready                                                                     -> 200
$ curl -s localhost:8000/api/v1/markets
{"type":"https://hunter.dev/problems/invalid-token","title":"Unauthorized","status":401,
 "detail":"The access token is missing or invalid.","instance":"/api/v1/markets",
 "request_id":"01a0726b-0b19-7140-ba20-abafebe054c1"}
```

### 3.2 O serviço devolve dado real (`docker compose exec api python`)

Script chama `MarketRepository`, `build_market_list_page` e `build_market_detail` — o mesmo
caminho de `GET /api/v1/markets` e `GET /api/v1/markets/{ex}/{sym}` — dentro de
`user_session(...)`, a mesma transação que a dependência `PrincipalSession` abre.

```
markets monitored (repo): 200
GET /api/v1/markets (service) summary:
{"markets_total":200,"markets_monitored":200,"markets_ok":0,"markets_stale":0,
 "markets_degraded":189,"markets_unavailable":11}

GET /api/v1/markets/binance/BTCUSDT (service):
  last_price     "79915.20"      bid "79915.40"   ask "79915.50"
  mark_price     "79863.86179710"
  open_interest  "106876.833"
  funding_rate   "0.00002352"  funding_kind "estimated"
  data_quality   "degraded"    has_open_gap true   stale_after_ms 10000
  components.ticker  ts 2026-09-05T16:34:09.896Z  age_ms 2974    quality "ok"
  components.book    ts null                       age_ms null    quality "absent"
  components.mark    ts 2026-09-05T16:30:24Z       age_ms 228870  quality "stale"
  book: null
  recent_trades: [
    {ts 16:33:50.703Z price "79871.30" qty "0.004" side "buy"  trade_id "3441137711"},
    {ts 16:33:46.915Z price "79871.30" qty "0.120" side "buy"  trade_id "3441137692"},
    {ts 16:33:36.705Z price "79861.30" qty "0.021" side "sell" trade_id "3441137589"} ]
```

Preço, bid, ask, mark, open interest e funding são **reais e corretos**; a idade por
componente é real; a qualidade `degraded` é **honesta** — e é justamente o que revela o
achado da seção 4.

Limitação: `volume_24h`, `quote_volume_24h` e `price_change_24h_pct` vêm `null` — o
`markets_summary` do universo grava `quote_volume_24h` no hash do ticker, mas o hash tem
TTL de 30 s e é reescrito pela ingestão sem esses campos, então some entre refreshes do
universo (15 min). Registrado como achado.

---

## 4. ACHADO HIGH-1 — o worker satura um core e perde eventos, sem sinal para o operador

Não é hipótese: é medição.

```
$ docker stats --no-stream
docker-market-worker-1 cpu=99.92%  mem=215.6MiB
docker-api-1           cpu= 0.15%  mem=101.3MiB
docker-postgres-1      cpu=24.57%  mem=128.0MiB
docker-redis-1         cpu= 0.90%  mem= 23.2MiB

$ redis-cli INFO stats
instantaneous_ops_per_sec:103
```

Redis a 0,9 % e 103 ops/s; Postgres a 25 %; **o worker a 99,9 % de um core**. O gargalo é
CPU de Python no processo do worker, não Redis, não Postgres, não a rede.

Consequência medida no socket — o kernel tem dado da Binance parado esperando o Python ler:

```
$ docker run --rm --network container:docker-market-worker-1 alpine ss -tn state established
Recv-Q  Send-Q Local Address:Port  Peer Address:Port
5529    0      172.18.0.4:54112    13.159.59.76:443     <- WS Binance
769197  0      172.18.0.4:54122    13.159.59.76:443     <- WS Binance (769 KB parados)
0       0      172.18.0.4:34460    13.32.16.24:443      <- REST Binance
0       0      172.18.0.4:33378    172.18.0.2:6379      <- Redis
```

Efeitos observáveis, todos consistentes:

| Sintoma | Medição |
|---|---|
| Book (`@depth20`, cadência 250 ms) quase nunca chega | 8 chaves `mkt:binance:*:book` vivas de 200 (TTL 10 s) |
| Ticker expira por falta de atualização | chaves `:ticker` caíram de 171 → 162 → 134 → 124 (TTL 30 s) |
| Trades muito abaixo do real | 230 trades/min somados nos 200 mercados; `trade_id` da Binance pula ~150–230 entre dois consecutivos guardados no BTCUSDT |
| Persistência atrasa | `market_persist_lag lag_s=13.6` e `TimeoutError` no `wait_for(flush, 10)` do `drain_loop` |
| API reflete a verdade | `markets_ok: 0`, `markets_degraded: 189`, `markets_unavailable: 11` |

**O worker é honesto sobre a degradação** (métricas reais do `:8001/metrics`):

```
market_snapshot_stale_fields_total{field="price"}         325.0
market_snapshot_stale_fields_total{field="mark_price"}    840.0
market_snapshot_stale_fields_total{field="open_interest"} 622.0
market_snapshot_skipped_no_data_total                     726.0
market_persistence_loss_reports_dropped_total               0.0
market_ingestion_gaps{exchange="binance",status="open"}   300.0
market_ingestion_gaps{exchange="binance",status="failed"}   0.0
```

**Mas há um buraco de observabilidade (HIGH-1b):** o adaptador conta os eventos que descarta
por fila cheia em `ConnectionState.dropped_events`
(`packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:55,70`), e **nada lê esse
contador**:

```
$ grep -rn "dropped_events" --include=*.py packages/ services/ apps/ | grep -v test
packages/exchange-adapters/hunter_exchanges/base.py:63:    dropped_events: int = 0
packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:8:  (docstring)
packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:55:  states[key].dropped_events += 1
packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:70:  states[victim_key].dropped_events += 1
```

Não vai para métrica, nem para `hb:market:binance`, nem para `system_events`, nem para log.
Perda de ingestão é invisível para quem opera.

### 4.1 O que a saturação **não** quebra — a série durável está íntegra

Medição que corrige a leitura pessimista acima: as velas finais de 1 minuto chegam para os
**200 mercados, todo minuto**, mesmo com o processo a 99 % de CPU.

```
$ psql -c "select open_time, count(*) as mercados_com_vela from candles
           where is_final and open_time > now() - interval '12 minutes' group by 1 order by 1"
 2026-09-05 16:28:00+00 | 200
 2026-09-05 16:29:00+00 | 200
 2026-09-05 16:30:00+00 | 200
 2026-09-05 16:31:00+00 | 200
 2026-09-05 16:32:00+00 | 200
 2026-09-05 16:33:00+00 | 200
 2026-09-05 16:34:00+00 | 194   <- 6 buracos, e o detector abriu exatamente 6 gaps
 2026-09-05 16:35:00+00 | 200
 2026-09-05 16:36:00+00 | 200
 2026-09-05 16:37:00+00 | 200

$ psql -c "select date_trunc('minute', detected_at), count(*) from ingestion_gaps group by 1"
 2026-09-05 16:28:00+00 | 200   <- bootstrap (24 h por símbolo)
 2026-09-05 16:30:00+00 | 200   <- segunda detecção antes do 1o backfill terminar
 2026-09-05 16:36:00+00 |   6   <- os 6 minutos perdidos, detectados e enfileirados
```

Isto é o contrato do `BoundedEventQueue` funcionando como especificado: **kline final nunca é
descartado**; sob pressão, o que se perde é o fluxo de alta frequência (`@depth20` a 250 ms,
`bookTicker`, `aggTrade`). Ou seja: sob sobrecarga o sistema **preserva o dado durável e
degrada o tempo real** — e a API diz isso (`data_quality: degraded`, `book: absent`), sem
inventar número nenhum. O que falta é o sinal explícito de perda (HIGH-1b acima).

---

## 5. Cenários da decisão conjunta (T1.6)

### (a) Reinício do container — PASSOU

```
=== ANTES  16:40:55
candles finais: 269392
duplicatas (market_id, timeframe, open_time com count>1): 0
RestartCount=0 StartedAt=2026-09-05T16:28:00Z

$ docker compose restart market-worker
 Container docker-market-worker-1 Restarting
 Container docker-market-worker-1 Started
real 0m4.205s

=== DEPOIS 16:41:43
RestartCount=0 StartedAt=2026-09-05T16:41:02Z Exit=0     <- shutdown limpo, SEM falso fatal
candles finais: 282892
duplicatas: 0                                            <- nada duplicado
hb: ws_state=connected subscriptions=1200 markets_monitored=200
Status: Up 44 seconds (healthy)
```

Resubscreveu os 1200 streams e voltou a `healthy` em menos de 45 s. `Exit=0` na parada
comprova o item "shutdown normal não é falso fatal".

### (b)+(c)+(e) Corte de rede só para a Binance, com `/ready` medido — PASSOU (cadeia inteira)

Método: sidecar com `NET_ADMIN` **no namespace de rede do worker**, derrubando só `tcp/443`
(Redis 6379 e Postgres 5432 continuam vivos). Registro completo em
`.claude/state/t16-netcut.log`.

```
$ docker run --rm --network container:docker-market-worker-1 --cap-add=NET_ADMIN alpine \
    sh -c "apk add iptables; iptables -I OUTPUT -p tcp --dport 443 -j DROP;
                            iptables -I INPUT  -p tcp --sport 443 -j DROP"
```

| Instante | `/ready` | Container |
|---|---|---|
| T=0 (16:46:38) | **200** `{"database":true,"redis":true,"ingestion":true,"persistence":true}` | RestartCount=0 |
| T+15s | 200 | RestartCount=0 |
| T+30s | **503** `ingestion:false` | RestartCount=0 |
| T+45s .. T+75s | 200 (tolerância de reconexão) | RestartCount=0 |
| T+90s (16:48:21) | 200 | **RestartCount=1**, StartedAt novo |
| T+105s .. T+135s | 200 | RestartCount=1, reconectado |

Log real durante o corte — as **duas rotas** falham, e o backfill REST também:

```
16:47:35 warning binance_ws_connect_error error='timed out during opening handshake' key=market:0 route=market
16:47:37 warning binance_ws_connect_error error='timed out during opening handshake' key=public:0 route=public
16:47:20 error   market_gap_backfill_failed attempt=1 symbol=ETHFIUSDT
         hunter_exchanges.base.ExchangeUnavailable: binance transport error:
```

E a saída fatal, no instante 16:48:15 — watchdog estourou os 3 reinícios sem progresso:

```
16:48:15 info Shutting down                 role=market
16:48:15 info Finished server process [1]   role=market
  + Exception Group Traceback (most recent call last):
  |   File "<frozen runpy>", line 198, in _run_module_as_main
  |     asyncio.run(runtime.run(run_market))
  |   File "/app/packages/core/hunter_core/runtime.py", line 179, in run
  |     raise error
  |   File "/app/services/market-worker/hunter_market_worker/main.py", line 55, in run_market
  |     async with asyncio.TaskGroup() as group:
  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)

16:48:18 info Started server process [1]     role=market       <- Compose reiniciou
16:48:18 info partition_startup_check_ok
16:48:19 info GET https://fapi.binance.com/fapi/v1/exchangeInfo "HTTP/1.1 200 OK"
16:48:20 info market_universe_changed added=['GWEIUSDT'] removed=['LISTAUSDT'] total=200
```

O traceback escapou até o topo do interpretador, então a saída é **não zero**. Verificado
que o `entrypoint.sh` propaga o código (o `exec` não engole nada):

```
$ docker compose run --rm -e HUNTER_ROLE=api api python -c "raise RuntimeError('falha fatal simulada')"  -> exit=1
$ docker compose run --rm -e HUNTER_ROLE=api api python -c "print('ok')"                                  -> exit=0
$ docker compose run --rm -e HUNTER_COMMAND=inexistente api
unknown HUNTER_ROLE: inexistente                                                                          -> exit=64
```

**`restart: unless-stopped` deixou de ser declaração e virou prova:** `RestartCount` foi de
0 para 1 sozinho, e o processo novo recarregou o universo e reconectou em ~4 s. Como o
namespace de rede é recriado no restart, a regra de bloqueio caiu junto — por isso a
reconexão é visível já em T+90s.

**Cenário (e) — `kill -9`:** não é reproduzível pelos caminhos disponíveis e isso é uma
limitação do método, não do sistema: `docker kill` é tratado pelo Docker como *parada
manual* e por contrato **não** aciona `restart: unless-stopped` (verificado: `ExitCode=137`,
`RestartCount=0`, container parado); e um `kill -9 1` de dentro do namespace de PID é
ignorado pelo kernel, que protege o PID 1 de sinais sem handler vindos do próprio
namespace (verificado: processo seguiu vivo). O que o `kill -9` deveria provar — "o
processo morre e o Compose o traz de volta" — está provado acima pelo caminho fatal real.

### (b') Ressalva honesta: "silêncio só na rota public" não foi isolável

As duas rotas (`wss://fstream.binance.com/public/stream` e `/market/stream`,
`binance/ws.py:77-78`) usam o **mesmo host e o mesmo IP** (`13.159.59.76:443`), então não há
como silenciar uma e manter a outra no nível de rede. O corte acima silenciou as duas e os
dois watchdogs dispararam separadamente (`key=public:0` e `key=market:0` nos logs), que é o
mesmo código. O caso "só a public silenciosa, a market ativa" continua coberto pelo teste
unitário `services/market-worker/tests/test_supervision.py::test_watchdog_restarts_only_silent_connection`.

### Recuperação do apagão de rede — gaps `open → recovered`

O detector encontrou **exatamente** os dois minutos do corte, nos 200 mercados:

```
$ psql -c "select open_time, count(*) from candles where is_final and open_time >= '16:44' group by 1"
 16:44 | 200
 16:45 | 200
 (16:46 e 16:47 ausentes — o apagão)
 16:48 | 200
 16:49 | 200

$ psql -c "select status, count(*) from ingestion_gaps where gap_start >= '16:45' group by 1"
 open | 399        <- 2 minutos x 200 mercados
```

E a transição para `recovered` aconteceu sozinha, por REST:

```
16:50:48 open 399
16:51:34 open 399
   ...
16:58:33 open 399
16:59:19 recovered 23  open 376     <- primeira leva recuperada
$ psql -c "select open_time, count(*) from candles where is_final and open_time between '16:45' and '16:49' group by 1"
 16:45 | 200
 16:46 |  45      <- 45 mercados já com a vela do apagão de volta
 16:48 | 200
 16:49 | 200
```

Funciona, mas **devagar**: o backfill compete com uma fila de ~800 gaps abertos herdada do
bootstrap e dos reinícios, com teto de `MAX_GAPS_PER_CYCLE = 50` por ciclo de 60 s e cada
busca REST levando ~2 s em série. Registrado como achado MEDIUM.

### (d) Postgres parado por 60 s — **FALHOU** (achado HIGH-2)

```
T=0    (17:02:05) ready 200 {"database":true,...}      RestartCount=1
### docker compose stop postgres
T+15s  ready 503 {"database":false,"redis":true,"ingestion":true,"persistence":true}
T+30s  ready 503 {"database":false,...,"persistence":false}
T+45s  ready 503 {"database":false,...,"ingestion":false}
T+60s  ready 503 {"database":false,...}
### docker compose start postgres (17:03:30)
+20s   ready 503 {"database":true,...,"ingestion":false}   RestartCount=2   <- reiniciou!
+80s   ready 503 {"database":true,...,"ingestion":false}   RestartCount=2
```

O `/ready` reagiu certo (503 com `database:false` em 15 s) e a **persistência se comportou
como o contrato manda** — a fila reteve e re-tentou, com o lote crescendo, tudo capturado e
não fatal:

```
17:02:14 error market_persist_flush_failed batch_size=8
17:02:19 error market_persist_flush_failed batch_size=15
17:02:26 error market_persist_flush_failed batch_size=18
17:02:32 error market_persist_flush_failed batch_size=21
17:02:38 error market_persist_flush_failed batch_size=23
17:02:44 error market_persist_flush_failed batch_size=26
17:02:37 error market_recovery_failed
17:02:08 error market_snapshot_failed
```

**Mas o processo morreu aos 52 s de apagão** — o critério é "sobrevive, sem morrer":

```
17:02:57 info Shutting down / Finished server process [1]
  | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
  +-+---------------- 1 ----------------
    |   File ".../supervision.py", line 18, in forever
    |     await coro
    |   File ".../heartbeat.py", line 173, in run_heartbeat
    |     await record_system_event(
    |   File ".../heartbeat.py", line 106, in record_system_event
    |     async with role_session(session_factory, db_role="hunter_worker") as session:
```

`run_heartbeat` é a **única** tarefa permanente que deixa o erro de banco escapar para o
`TaskGroup`; persistência, recovery, snapshot e universo capturam os seus. Cenário real:
qualquer restart de Postgres (manutenção, failover, upgrade menor) derruba a ingestão.

E o efeito em cascata, pior que a queda em si (achado HIGH-3): o processo novo subiu às
17:03:01 com o Postgres ainda fora, o refresh de universo falhou —

```
17:03:13 error market_universe_refresh_failed role=market
```

— e `run_universe` dorme `market_universe_refresh_s` (**900 s**) depois de uma falha do mesmo
jeito que depois de um sucesso. O Postgres voltou às 17:03:30 e três minutos depois o worker
continuava `unhealthy`, com `ws_state=disconnected`, `subscriptions=0`, `markets_monitored=0`:
ficaria cego até 17:18. Só voltou porque eu reiniciei à mão.

```
$ docker compose restart market-worker
$ redis-cli HGETALL hb:market:binance
ws_state=connected subscriptions=1200 reconnects=1 markets_monitored=200
Status: Up 36 seconds (healthy)
```

Correções despachadas ao `backend-specialist` (HIGH-2, HIGH-3, HIGH-1b e a incoerência do
payload de `/ready`).

### MEDIUM-1 — o corpo do `/ready` contradiz o próprio status

`packages/core/hunter_core/runtime.py:117-131` monta o payload com
`details[check.__name__] = ok`, e `main.py:43` registra `partitions.ready`, cujo `__name__` é
literalmente `ready`. Resultado real, com HTTP **503**:

```
503 {"database":true,"redis":true,"ingestion":false,"persistence":true,"ready":true}
```

Quem ler `body["ready"]` conclui o contrário do que o endpoint está dizendo.

### MEDIUM-2 — a prontidão volta de 503 para 200 sem nenhum dado ter chegado

Levantado pela Astra na segunda opinião e confirmado no código.
`ReadinessState.observe_adapter` (`supervision.py:49-58`) zera `connect_timed_out`
incondicionalmente a cada observação e o rededuz de `connect_attempt_started_monotonic >= 15`.
Quando o adaptador desiste de uma tentativa pendurada e abre outra, o relógio da tentativa
reinicia, `connect_timed_out` volta a `False` e a prontidão volta ao ramo tolerado. Foi
exatamente o que o log mostrou: **503 em T+30s, 200 em T+45s**, com a Binance inalcançável e
zero dado recebido no intervalo.

A tolerância de 120 s acumulados em `connecting/reconnecting` é o contrato acordado na decisão
conjunta, então responder 200 durante ela não é bug. O que é incoerente é a **regressão**
(`false` → `true`) que o teste `test_readiness_grace_is_monotonic_and_not_reset_by_flapping`
existe justamente para impedir. Observação relacionada: o fatal do watchdog dispara aos ~90 s
(3 reinícios sem progresso) — **antes** dos 120 s da tolerância —, então na prática o processo
morre antes de a tolerância expirar e o ramo de 120 s quase nunca chega ao fim. Mudar isso
altera um contrato fechado na decisão conjunta; fica registrado como **MEDIUM para o M2**, com
a recomendação da Astra: exigir *progresso recente* nas conexões, não apenas uma tentativa em
curso, para voltar a declarar `ingestion` pronta.

### Correção de exagero meu

Escrevi acima "velas finais para os 200 mercados, todo minuto". A tabela mostra 16:34 com
**194**, e o detector abriu exatamente 6 gaps por isso. A afirmação correta é: cobertura de
200/200 na maioria dos minutos, com quedas pontuais sempre detectadas e enfileiradas para
recuperação. A Astra pegou o exagero.

### Achado já conhecido, reconfirmado de forma independente

A Astra apontou `recovery.py:138` (o gap encolhe até a primeira vela recebida) como risco de
falsa recuperação. É a limitação **já registrada** em `docs/plans/M1.md`, T1.3: "Sufixo REST
parcial no bootstrap pode ser lido como 'o histórico começa aqui'". O código tem o comentário
explicando a intenção (mercado listado depois de `gap_start` nunca teve histórico anterior).
Continua aceita no M1; a Astra chegou nela sozinha, o que reforça o registro.

---

## 6. Segunda opinião (Astra) — `.claude/state/astra-review-t16-proof.md`

Veredito da Astra: **parcial**, o mesmo a que cheguei. "Está provado que o pipeline recebe dado
real, persiste e inicia recuperação automática. Ainda não está provado que sustenta os 200
mercados continuamente e conclui a recuperação sem intervenção."

**Onde concordamos** (absorvido sem discussão): CRITICAL-1 como bloqueador total; HIGH-2 e
HIGH-3 como bloqueadores de aceite pela cascata e pela intervenção manual que exigiram;
MEDIUM-1; e o valor da prova real — "encontrou defeitos que testes simulados não capturaram".

**Onde discordamos, e o que decidi:**

| Ponto | Astra | Decisão |
|---|---|---|
| Severidade de HIGH-1b (`dropped_events` invisível) | MEDIUM — "a degradação já aparece em métricas e na API" | **Mantido HIGH.** A API mostra *sintoma* (`degraded`, `absent`), não *perda*. Sem o contador, ninguém sabe se o sistema perdeu 10 ou 10 milhões de eventos, e é justamente a regra "todo 'feito' vem com o número". Correção já despachada, custo baixo. |
| `/ready` 200 durante o bloqueio | must-fix | **MEDIUM para o M2** (MEDIUM-2 acima): a tolerância de 120 s é contrato fechado na decisão conjunta; mexer nela é mudança de contrato, não correção de bug. Registrado com o mecanismo exato. |
| Backfill lento | "MEDIUM só se convergir no prazo; se o backlog cresce, é HIGH e bloqueia" | **Aceito como critério.** É o teste que falta rodar (item 1 abaixo). |

**O que a Astra pediu e ainda não está provado** — vira a lista de pendências do T1.6, não
"feito":

1. **Recuperação até o fim.** O registro para em 376 gaps abertos e 45 de 200 mercados com a
   vela de 16:46. Prova recuperação *iniciada*, não *concluída*. Falta acompanhar até cada par
   `(mercado, minuto)` esperado estar preenchido, dentro de um prazo definido **antes** do teste.
2. **Apagão que sobreviva ao restart.** O bloqueio caiu junto com o namespace de rede quando o
   container reiniciou, então não houve indisponibilidade externa longa atravessando vários
   reinícios. Precisa de um proxy/gateway fora do worker.
3. **Redis fora do ar** — só testei Postgres. O heartbeat também escreve e publica no Redis sem
   tratamento local (`heartbeat.py:167`).
4. **Corrida longa (24–48 h)** atravessando a virada UTC, medindo idade por componente, memória,
   atraso do event loop, descartes e idade do gap mais antigo.
5. **Morte abrupta sem chance de limpeza** (OOM controlado em stack descartável).
6. **Conferir o conteúdo, não só a contagem:** `count(*) = 200` não prova identidade dos mercados
   nem OHLCV correto. Falta comparar uma amostra de velas com o REST.
7. **HTTP autenticado ponta a ponta** (hoje provei a auth por 401 e o serviço por chamada direta).

---

## 7. Conteúdo das velas conferido contra a Binance (item 6 da Astra — FECHADO)

A Astra observou, com razão, que `count(*) = 200` não prova que o **valor** está certo. Comparei
OHLCV vela a vela contra o REST da Binance, dentro do container `api`:

```
BTCUSDT:  200 idênticas / 0 divergentes / 0 sem par no REST  (13:45 -> 17:13 UTC)
ETHUSDT:  200 idênticas / 0 divergentes / 0 sem par no REST  (13:46 -> 17:13 UTC)
SOLUSDT:  200 idênticas / 0 divergentes / 0 sem par no REST  (13:47 -> 17:13 UTC)
DOGEUSDT: 200 idênticas / 0 divergentes / 0 sem par no REST  (13:46 -> 17:13 UTC)
```

Comparação em `Decimal`, campo a campo (open, high, low, close, volume). **800 velas, zero
divergência.** A janela de 3,5 h atravessa o apagão de rede e os reinícios, então as velas
**recuperadas por backfill também batem** — a recuperação não inventa nem deforma valor.

Exemplo cru do banco: `2026-09-05 17:11:00+00  O=80068.40  H=80088.50  L=80068.40  C=80076.90  V=42.652`.

---

## 8. ACHADO HIGH-4 — Redis fora do ar deixa o worker **zumbi** (vivo, sem ingestão, sem restart)

Cenário pedido pela Astra (item 3) e que faltava. `docker compose stop redis` às 17:15:15,
`start` às 17:16:36 — 81 s fora.

**Durante o apagão o comportamento foi correto e melhor que o do Postgres:**

```
T+15s  503 {"database":true,"redis":false,"ingestion":true,"persistence":false}  RC=0 running
T+30s  503 {"database":true,"redis":false,"ingestion":true,"persistence":false}  RC=0 running
T+45s  503 {"database":true,"redis":false,"ingestion":false,"persistence":false} RC=0 running
T+60s  503 {"database":true,"redis":false,"ingestion":false,"persistence":false} RC=0 running
```

O processo **não morreu** (`RestartCount` ficou em 0 o tempo todo) e a escrita do heartbeat
falhou de forma tratada, como deve ser:

```
17:15:28 warning heartbeat_write_failed role=market
17:15:42 warning heartbeat_write_failed role=market
17:15:55 warning heartbeat_write_failed role=market
```

**O problema é depois.** Com o Redis de volta às 17:16:36, medido às 17:20:43 — quatro minutos
depois:

```
$ redis-cli --scan --pattern 'hb:*'
hb:market:a91854f066f1:1            <- só o heartbeat genérico do runtime
                                       (hb:market:binance NÃO existe mais)
$ psql -c "select max(open_time) from candles where is_final"
 2026-09-05 17:13:00+00              <- 7 minutos sem vela nova
$ docker stats --no-stream
docker-market-worker-1 cpu=7.45%     <- estava em 99%; agora ocioso
$ docker compose ps market-worker
Up 12 minutes (unhealthy)
$ /ready -> 503 {"database":true,"redis":true,"ingestion":false,"persistence":false,"ready":true}
```

Ou seja: **processo vivo, CPU ociosa, `/ready` 503 permanente, zero ingestão, heartbeat de
mercado sumido — e nada reinicia.** `restart: unless-stopped` não ajuda porque nada morre;
`unhealthy` no healthcheck do Compose **não** dispara restart (Compose puro não age sobre
healthcheck). O único sinal de vida no log é o loop de recovery, que continua alegremente
fazendo backfill por REST dos buracos que a própria ingestão morta está criando:

```
17:19:44 info market_gap_recovered candles_inserted=1 symbol=BICOUSDT
17:19:45 info market_gap_recovered candles_inserted=1 symbol=APRUSDT
17:19:47 info market_gap_recovered candles_inserted=1 symbol=ENJUSDT
```

Este é o pior modo de falha encontrado na prova: **degradação silenciosa que parece atividade**.
Um operador olhando o log vê linhas de sucesso rolando.

Causa provável (a confirmar com a correção da HIGH-3): o refresh de universo falhou durante o
apagão de Redis e o loop dormiu os 900 s, deixando o worker sem símbolos; com universo vazio a
ingestão fica `idle` e o heartbeat de mercado para de ser escrito, expirando por TTL. Se for
isso, a correção da HIGH-3 (backoff curto na falha) fecha também a HIGH-4 — está sendo medido
(monitor de auto-recuperação rodando).

**Independentemente da causa, fica o achado estrutural:** nenhuma camada age quando o worker
fica vivo-e-parado. `restart: unless-stopped` só cobre morte de processo. O healthcheck existe,
detecta corretamente, e ninguém escuta.

### HIGH-4 — causa raiz confirmada no código (não é só a HIGH-3)

Deixei o zumbi rodando 19 minutos para separar as duas hipóteses.

```
17:22:02 hb_binance=0 ultima_vela=17:13 cpu=4.76%
17:24:08 hb_binance=0 ultima_vela=17:13 cpu=0.23%
17:29:23 hb_binance=0 ultima_vela=17:13 cpu=0.26%
17:31:29 hb_binance=0 ultima_vela=17:15 cpu=30.85%   <- o timer de 900 s da HIGH-3 disparou
17:33:34 hb_binance=0 ultima_vela=17:15 cpu=11.26%
17:34:37 hb_binance=0 ultima_vela=17:15 cpu=0.25%    <- e voltou a congelar
```

O timer de 15 minutos disparou às ~17:31, deu um sopro de vida (uma vela atrasada persistida) e
o processo **voltou a congelar**. Então a HIGH-4 **não** é apenas consequência da HIGH-3.

Última linha de log do container: **17:16:37**. Depois disso, 19 minutos de silêncio absoluto —
nenhum erro, nenhuma tentativa de reconexão, nenhum `market_gap_recovered`. E a tabela de
sockets mostra que as conexões WebSocket sumiram e **nunca foram reabertas**:

```
$ docker run --rm --network container:docker-market-worker-1 alpine ss -tn state established
172.18.0.3:41318   172.18.0.2:6379     <- Redis
172.18.0.3:58616   172.18.0.2:6379     <- Redis
172.18.0.3:43674  13.32.16.27:443      <- uma conexão REST
(várias para :5432)
                                       <- NENHUMA para fstream.binance.com
```

Antes do apagão havia duas conexões estabelecidas para `13.159.59.76:443` (as duas rotas WS).

**Causa raiz, lida no código:** `packages/core/hunter_core/redis.py::create_redis` é

```python
return redis_asyncio.from_url(redis_url.get_secret_value(), decode_responses=False)
```

Sem `socket_timeout`, sem `socket_connect_timeout`, sem `health_check_interval`, sem política de
retry. O padrão do redis-py é timeout `None`: um `await` numa conexão que o servidor derrubou ao
reiniciar **bloqueia para sempre** — a tarefa nunca retorna, nunca levanta exceção e por isso
nunca chega à supervisão que a tornaria fatal e deixaria o Compose reiniciar o container. Tudo
que depende dessa tarefa congela junto, em silêncio.

Correção despachada: timeouts limitados e auto-cura no cliente Redis (`packages/core/hunter_core/redis.py`),
mais a regra de que um erro de Redis na ingestão tem de **chegar à supervisão** — sair não-zero e
deixar o Compose reiniciar é estritamente melhor que um zumbi silencioso.

**Lição estrutural, independente desta correção:** `restart: unless-stopped` só cobre morte de
processo. O healthcheck do Compose detecta o zumbi corretamente e **ninguém escuta** — Compose
puro não reinicia por healthcheck. Enquanto o deploy for Compose, falta um mecanismo (por exemplo
`autoheal`, ou um watchdog que mate o processo quando `/ready` reprovar por N minutos seguidos).
Registrado para a T1.7/ops.

---

## 9. Correções feitas nesta tarefa

| # | Achado | Correção | Arquivo | Teste |
|---|---|---|---|---|
| CRITICAL-1 | `EXPIRE` com float no Lua do rate limiter — o worker **nunca** carregava o universo contra Redis real | TTL vira `int` (`math.ceil`) no Python **e** `tonumber(ARGV[5])` no Lua, igualando o script que já estava certo | `packages/exchange-adapters/hunter_exchanges/rate_limit.py` | 2 unitários que olham o tipo do argumento cru enviado ao `eval` + 2 de integração contra Redis real em testcontainer |
| HIGH-1b | `dropped_events` contado e nunca lido por ninguém | contador Prometheus `market_dropped_events_total{exchange}` + campo `dropped_events` no hash `hb:market:{exchange}` | `heartbeat.py`, `observability.py` | delta por tique no `test_supervision.py` + escrita no hash e no contador no `test_heartbeat.py` |
| HIGH-2 | queda do Postgres matava o processo via `run_heartbeat` | `safe_record_system_event` (captura tudo menos `CancelledError`, loga e conta em `market_system_event_record_failures_total`); e a ordem do loop mudou para o **Redis ser escrito antes** de qualquer tentativa de gravar `system_events`. Mesmo defeito achado e corrigido no closure `warning()` do watchdog | `heartbeat.py`, `main.py`, `observability.py` | `test_run_heartbeat_survives_a_broken_system_event_write` |
| HIGH-3 | falha no refresh de universo dormia 900 s e cegava o worker | backoff exponencial a partir de 5 s, teto de `min(120, refresh/3)`, com jitter; volta ao intervalo cheio no primeiro sucesso | `universe.py` (+ `universe_repo.py`, extraído para caber no orçamento de 350 linhas) | `test_run_universe_retries_fast_after_failure_and_resets_after_success` |
| HIGH-4 | restart de Redis congelava o worker para sempre | `socket_connect_timeout=5s`, `socket_timeout=5s`, `health_check_interval=30s`, `retry_on_timeout` e `Retry(ExponentialWithJitterBackoff(0.05, cap 0.5), 3)` — cada número justificado no código contra o cenário que cobre (inclusive os 2,25 s de travada do event loop que eu medi, que é por que não é 1 s) | `packages/core/hunter_core/redis.py` | asserção sobre os `connection_kwargs` reais do pool |
| MEDIUM-1 | corpo do `/ready` com chave `ready` contradizendo o 503 | o check é registrado por um wrapper chamado `partitions`, sem tocar em `runtime.py` nem em `partitions.py` | `main.py` | `test_readiness_naming.py` (2 testes, um documentando a causa) |
| D4 | `create_partitions.py` sem `lock_timeout` — DDL enfileirava atrás de leitura e travava todo `INSERT` de vela | `SET LOCAL lock_timeout = '3s'` por transação de DDL; grupo que estoura é pulado com log e o processo sai 1 para o cron notar | `infra/scripts/create_partitions.py` | 5 unitários + prova no Postgres vivo com `log_statement=all` |
| D12 | bounds de partição resolvidas pelo `TimeZone` da sessão | `SET LOCAL TimeZone='UTC'` na mesma transação **e** reescrita das bounds para `'2026-09-01 00:00:00+00'` a partir do script, sem tocar no `_partitions.py` congelado | `infra/scripts/create_partitions.py` | `pg_get_expr` mostrando `+00` em todas as partições |
| — | agendamento de partições não existia | `HUNTER_COMMAND=partitions` no entrypoint + cron diário documentado na VPS | `infra/docker/entrypoint.sh`, `infra/vps/README.md`, `docs/DEPLOYMENT.md` | execução real, idempotente na segunda vez |

---

## 10. Retestes com as correções no ar (imagem reconstruída)

`docker compose build api` → `BUILD_EXIT=0`; `up -d --force-recreate market-worker`.

### A perda de ingestão deixou de ser invisível (HIGH-1b)

O contador novo apareceu no heartbeat **no primeiro minuto**:

```
$ redis-cli HGETALL hb:market:binance
ws_state=connected subscriptions=1200 markets_monitored=200 reconnects=0
dropped_events=256733            <- 75 s de operação
...mais tarde:
dropped_events=1317314
```

**256.733 eventos descartados em ~75 s**, e 1,3 milhão depois de alguns minutos. É o número que
antes existia no processo e não chegava a lugar nenhum. Ele quantifica a HIGH-1 de forma que
ninguém pode ignorar — e é exatamente por isso que mantive HIGH-1b como HIGH contra a sugestão
da Astra de rebaixar para MEDIUM.

### HIGH-4 (Redis fora do ar) — **PASSOU**

```
T=0            200 {"database":true,"redis":true,"ingestion":true,"persistence":true,"partitions":true}
### stop redis 17:53:47  ... start redis 17:55:08   (81 s fora)
recup+30s      200 {...tudo true} | hb_markets=200 | RC=8 running
recup+60s      200 {...tudo true} | hb_markets=200 | RC=8
recup+180s     200 {...tudo true} | hb_markets=200 | RC=8
```

Trinta segundos depois do Redis voltar: `/ready` **200**, 200 mercados monitorados, 1200
assinaturas. Antes: zumbi permanente. Repare também na chave `partitions` no lugar de `ready` —
a MEDIUM-1 corrigida e visível no payload.

**Contrapartida honesta:** `RestartCount` foi de 0 a **8** durante os 81 s de apagão. É o
comportamento desejado (morrer alto e deixar o Compose reiniciar em vez de congelar), mas
significa **crash-loop enquanto o Redis estiver fora**. Com um apagão longo isso vira dezenas de
reinícios, e o `IpRateGate` do rate limiter é **local ao processo** (limitação já registrada no
M1): cada reinício perde o cooldown de `Retry-After`, o que pode escalar um `429` da Binance
para `418` (ban de IP). **Registrado como MEDIUM-4 para o M2:** persistir `blocked_until` em
Redis — que é justamente o follow-up já listado no plano — ou dar um teto de reinício.

### HIGH-2 (Postgres fora do ar) — **PASSOU**

```
RestartCount inicial = 8
T=0            200 {"database":true,...}
### stop postgres 18:00:22
T+30s          503 {"database":false,"redis":true,"ingestion":true,"persistence":false,"partitions":true} | RC=8
T+60s          503 {"database":false,...}                                                                 | RC=8
T+90s          503 {"database":false,...}                                                                 | RC=8
### start postgres 18:02:14   (112 s fora)
recup+30s      200 {...tudo true} | hb_markets=200 | RC=8
recup+120s     200 {...tudo true} | hb_markets=200 | RC=8
RestartCount final = 8 (inicial 8)
```

Exatamente o contrato: **o processo não morreu** (`RestartCount` intacto), `ingestion` continuou
`true` (o WebSocket seguiu fluindo com o banco fora), `persistence` e `database` reprovaram
honestamente, e 30 s depois do banco voltar tudo estava `true` outra vez — **sem intervenção
manual**, que era exatamente o que faltava na primeira rodada.

### MEDIUM-3 (encontrado no reteste) — o healthcheck do Compose dava falso negativo

Com `/ready` respondendo 200, o container aparecia `unhealthy`. Medição da latência do próprio
endpoint sob carga plena (200 mercados + backlog de recovery):

```
0: 200 em 8.12s     4: 503 em 24.79s
1: 200 em 7.16s     5: 503 em  5.39s
2: 503 em 9.69s     6: 200 em  0.02s
3: 503 em 15.15s    7: 200 em  0.01s

$ docker inspect --format '{{.Config.Healthcheck.Timeout}}'
3s
$ histórico do healthcheck
18:05:34 exit=1 · 18:05:46 exit=1 · 18:05:59 exit=1 · 18:06:12 exit=1 · 18:06:24 exit=0
```

O servidor de saúde divide o mesmo event loop com a ingestão saturada, então o teto de 3 s dava
sequências de quatro falhas seguidas num worker que estava pronto. Um `unhealthy` falso é pior
que nenhum: qualquer coisa que aja sobre ele (autoheal, probe de orquestrador, load balancer)
reinicia ou tira de serviço um worker saudável.

Corrigido em `infra/docker/docker-compose.yml` com valores **medidos, não chutados**
(`timeout: 30s`, `interval: 15s`, `retries: 5`, `start_period: 60s`, timeout do cliente 25 s),
com o comentário dizendo que isto absorve a cauda medida e que a correção de verdade é a
capacidade de ingestão (HIGH-1, M2). Resultado:

```
$ docker compose ps market-worker
Up About a minute (healthy)
$ docker inspect --format 'Health={{.State.Health.Status}} FailingStreak={{.State.Health.FailingStreak}}'
Health=healthy FailingStreak=0
```

---

## 11. Estado final medido (18:10 UTC, ~1h50 de operação com ~10 apagões induzidos)

```
$ redis-cli HGETALL hb:market:binance
ws_state=connected  subscriptions=1200  markets_monitored=200  reconnects=0
open_gaps=4501      dropped_events=1152613

$ chaves quentes
tickers=0   books=0   trades=203

$ psql
candles finais  = 316794
market_snapshots=   3191
ingestion_gaps  : recovered 2324 | open 4729
system_events   : critical 1 | warning 844
   persistence_drop 686 · ws_state_changed 44 · ws_reconnected 40
   adapter_reconnect 36 · persistence_lag 34 · connection_watchdog 5 · ws_disconnected 1

$ cobertura de velas por minuto
 18:03 | 200      18:07 | 200
 18:04 | 200      18:08 | 200
 18:05 | 200      18:09 |  16   (minuto em curso)
 (18:06 ausente — foi quando recriei o container para o fix do healthcheck)

$ docker stats
docker-market-worker-1 cpu=100.40% mem=252.3MiB
```

O único `critical` é o `ws_disconnected` do corte de rede das 16:47 — correto. E os 686
`persistence_drop` provam o item da decisão conjunta "filas descartam **com métrica**": o
descarte não é silencioso, vira `system_event`.

**O ponto duro, sem maquiagem: `tickers=0` e `books=0`.** Com 200 mercados e um backlog de 4.700
gaps para recuperar, o hot state de alta frequência não existe. Na tela isso significa preço ao
vivo ausente e `markets_ok = 0`. A série durável continua íntegra (200/200 por minuto, valores
conferidos contra o REST), mas o tempo real não se sustenta nesta máquina neste tamanho de
universo.

Ressalva de honestidade: **boa parte desses 4.700 gaps é obra minha** — provoquei ~10 apagões
(rede, Postgres, Redis, reinícios) em 1h50. Não é o backlog de uma operação normal. Mas o
mecanismo que ele expõe é real: **quanto maior o backlog de recovery, mais REST, mais CPU, menos
hot state, mais buracos**. É um laço de realimentação, e nada hoje o amortece (não há teto de
taxa no backfill nem prioridade entre ingestão ao vivo e recuperação histórica).

---

## 12. Veredito

**T1.6: `parcial`.** Mesmo veredito da segunda opinião da Astra, pelas mesmas razões.

**O que está provado, com comando e saída real:**

| Critério | Situação |
|---|---|
| Dado real da Binance ponta a ponta (WS + REST) | provado — 200 mercados, 316.794 velas, valores conferidos vela a vela contra o REST (800 velas, 0 divergência) |
| Preço muda entre duas leituras | provado (79812.70 → 79823.90 em 12 s) |
| Persistência real no Postgres | provado (velas, snapshots, gaps, system_events) |
| API devolve dado real e a auth está ligada | provado (401 sem token; serviço chamado direto devolve BTCUSDT real) |
| Reinício do container sem duplicar candle | provado (0 duplicatas, `Exit=0`, sem falso fatal) |
| `restart: unless-stopped` reinicia de verdade | provado (`RestartCount` 0 → 1 sozinho, no caminho fatal do watchdog) |
| Saída não-zero em falha fatal | provado (traceback no topo do interpretador; entrypoint propaga 1 / 0 / 64) |
| 503 quando devido | provado (`ingestion:false` no corte de rede; `database:false` no apagão de Postgres) |
| Watchdog reinicia conexão e vira fatal em 3 sem progresso | provado (log das duas rotas + fatal aos ~90 s) |
| Gap detectado e recuperado (`open → recovered`) | provado (399 gaps = 2 min × 200 mercados, com recuperação e valores corretos) |
| Queda do Postgres não mata o worker | provado **depois da correção** (RestartCount intacto, tudo `true` 30 s após voltar) |
| Queda do Redis não deixa zumbi | provado **depois da correção** (`/ready` 200 e 200 mercados 30 s após voltar) |
| Perda de ingestão visível | provado **depois da correção** (`dropped_events` no heartbeat e em métrica) |
| Descarte de fila com métrica | provado (686 `persistence_drop` em `system_events`) |
| Partições: `lock_timeout`, bounds UTC, agendamento | provado (execução real, idempotente, `pg_get_expr` com `+00`, cron documentado) |

**O que NÃO está provado e é por isso que não é `implementado`:**

1. **Capacidade.** O worker satura um core com 200 mercados; hot state de alta frequência não se
   sustenta (`tickers=0`, `books=0`, 1,15 M de eventos descartados). O produto entrega série
   durável correta, não tempo real, neste tamanho.
2. **Recuperação até o fim.** 4.729 gaps abertos ao final. Provei que recupera; não provei que
   converge dentro de um prazo, e não existe prazo definido.
3. **Corrida longa.** O mais longo foi ~1h50, com apagões induzidos. Falta 24–48 h atravessando a
   virada UTC e a rotação de conexão de ~23,5 h da Binance.
4. **Apagão externo longo atravessando reinícios** (o bloqueio caía junto com o container).
5. **Morte abrupta sem chance de limpeza** — `docker kill` não aciona a política de restart e
   `kill -9 1` de dentro do namespace é ignorado pelo kernel; falta um OOM controlado.
6. **"Só a public silenciosa"** — impossível isolar na rede (as duas rotas usam o mesmo IP);
   coberto por teste unitário, não pela prova operacional.
7. **HTTP autenticado ponta a ponta** — provei a auth (401) e o serviço (chamada direta), não o
   caminho completo com token Clerk.

**Recomendação ao dono (decisão dele, não minha):** reduzir `MARKET_UNIVERSE_SIZE` de 200 para
algo entre 20 e 50 até a HIGH-1 ser tratada no M2. Com universo menor o mesmo código deve
sustentar o hot state completo, e a tela mostra preço ao vivo de verdade em vez de `degraded` em
tudo. É mudança de escopo do M1 (o plano diz top-200), por isso não fiz sozinha.

---

## 13. Revisões

### `security-reviewer` (obrigatório em T1.6 — imagem e compose)

**Veredito: bloqueado por 1 HIGH, que era de documentação, não de código.** As mudanças de
código (`redis.py`, `observability.py`, `heartbeat.py`, `universe.py`, `universe_repo.py`,
`main.py`, `rate_limit.py`, `create_partitions.py`) foram aprovadas como estão.

**HIGH — o cron diário de partições rodava as migrations do Alembic em produção.**
`docker compose run` sobe as dependências de `depends_on` a menos que se passe `--no-deps`, e
`api` declara `migrate` com `condition: service_completed_successfully`. Provado, não inferido:

```
$ docker compose --dry-run run --rm -e HUNTER_COMMAND=partitions api
 Container docker-migrate-1 Starting
 Container docker-migrate-1 Started
 Container docker-migrate-1 Waiting
 Container docker-migrate-1 Exited
 Container docker-api-run-1dd043b65892 Created
```

Cenário: alguém dá `git pull` em `/opt/project-hunter` deixando uma revisão não aplicada na
árvore. Às 04:07 o cron — cujo propósito documentado é "criar partições", descrito como
idempotente e inofensivo — executa `alembic upgrade head` com a credencial dona do schema. Uma
mudança de schema entra em produção sozinha, de madrugada, sem release e sem ninguém olhando,
enquanto `api` e `market-worker` seguem rodando a imagem anterior contra o schema novo. O
inverso é igualmente ruim: se essa migration falhar, o `compose run` aborta pela dependência e
o trabalho de partições **nunca roda** — a falha enterrada no log atrás do ruído do compose, e
a virada de mês quebra exatamente como o recurso existia para evitar.

Correção despachada (`--no-deps` em todas as variantes, `GIT_SHA` exportado para todo
subcomando do `compose.sh`, e o código de saída do skip por `lock_timeout` distinguido do erro
duro).

**Aprovado explicitamente pela revisão** (verificado, não assumido): nenhum segredo na imagem
(`/app` sem `.env*`, sem chave; `docker history` com um único build arg `GIT_SHA=dev`);
`.dockerignore` cobrindo `.env`; `create_redis` mantendo o `SecretStr` como temporário, sem
vazar a URL em log ou exceção; usuário não-root (`uid=10001(hunter)`); a ação `partitions` sem
privilégio novo além do que `migrate` já tinha; `/opt/backups` ainda 700; o `market-worker` não
publica porta nenhuma e o servidor de saúde escuta só em `127.0.0.1:8001` (confirmado com `ss
-ltn` dentro do namespace); **cardinalidade dos labels novos limitada** (`exchange` tem um valor
por processo, `event` tem cinco literais — nenhum símbolo da Binance, nem os não-ASCII, vira
label); retry do Redis com teto de ~21,5 s por comando e jitter, sem amplificação; e a regex que
reescreve as bounds de partição aplicada **só** ao `create_partition_sql`, sem alcançar
`REVOKE`, `FORCE ROW LEVEL SECURITY` ou corpo de policy — não consegue mexer no predicado de
tenant.

### `code-reviewer`

**Veredito: APPROVE_WITH_NITS.** Confirmou, verificando por conta própria, que cada defeito foi
corrigido de forma coerente com o cenário que o originou; que a assimetria HIGH-2 / HIGH-4 está
implementada de verdade (erro de banco ao *registrar* um `system_event` é engolido e contado;
erro de Redis na escrita do heartbeat é fatal, e `CancelledError` nunca é engolido); que a
extração de `universe_repo.py` é movimento puro; e que os testes novos **falhariam se o bug
voltasse** — ponto que importa aqui, já que a CRITICAL-1 passou por um teste que reimplementava
o Lua em Python. Também traçou o `pubsub.listen()` do `apps/api` dentro do código do redis-py
8.1.0 e confirmou que ele passa `timeout=math.inf`, ignorando o `socket_timeout` novo: a ponte
de WebSocket não quebra.

Dois achados, ambos corrigidos por mim nesta tarefa:

**HIGH — os 5 testes de `infra/scripts/tests/` não rodavam em lugar nenhum.** O `testpaths` do
`pyproject.toml` era `["packages", "apps", "services", "tests"]`, sem `infra`, e o job do CI roda
`pytest -m "unit or integration"` sem sobrescrever caminho. Cenário: alguém remove o
`try/except` do `lock_timeout` (D4) ou o `_explicit_utc_bounds` (D12) e o CI passa verde — a rede
de proteção dos dois bugs que esta tarefa existia para fechar era invisível para o pipeline.
Corrigido: `infra` entrou no `testpaths`, com comentário dizendo por quê.

```
$ uv run pytest -m "unit or integration" --collect-only -q | grep -c test_create_partitions
7        (antes: 0)
```

**LOW — `_retry_delay` estourava `OverflowError` depois de ~41 h de falha contínua.**
`min(cap, BASE * (2 ** (attempt - 1)))` calcula a potência inteira **antes** do `min`; com
`attempt` perto de 1024 o Python levanta `OverflowError: int too large to convert to float`
dentro do próprio helper, matando `run_universe` e o `TaskGroup` por um motivo que nada tem a ver
com o apagão. Corrigido limitando o expoente antes de elevá-lo:

```
$ attempt=      1 -> 5.0s        attempt=     10 -> 120.0s
$ attempt=      2 -> 10.0s       attempt=   1024 -> 120.0s
$ attempt=      5 -> 80.0s       attempt= 100000 -> 120.0s
```

### Correção do HIGH da segurança (cron de partições)

`--no-deps` em todas as quatro ocorrências do comando, com prosa explicando que não é
otimização. Prova antes/depois:

```
--- ANTES (sem --no-deps) ---
 Container docker-migrate-1 Starting
 Container docker-migrate-1 Started
 Container docker-migrate-1 Waiting
 Container docker-migrate-1 Exited
 Container docker-api-run-e09efa56bf74 Created

--- DEPOIS (com --no-deps) ---
 Container docker-api-run-cfa64a68bcf6 Creating
 Container docker-api-run-cfa64a68bcf6 Created
```

Junto: `GIT_SHA` passou a ser exportado para **todo** subcomando do `infra/vps/compose.sh` (antes
só `up` e `update`, então o cron resolvia `hunter-api:dev`, tag que não existe na VPS, e
dispararia um `docker build` de madrugada numa máquina de um core já saturada); e o skip benigno
por `lock_timeout` ganhou código de saída próprio (**75**, `EX_TEMPFAIL`), deixando o `1` só para
erro duro — antes o README prometia uma distinção que o código não fazia.

