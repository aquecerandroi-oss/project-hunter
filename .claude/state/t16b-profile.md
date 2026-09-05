# T1.6b — perfil real do market-worker (py-spy no container)

Método (não hipótese): `py-spy record` anexado ao PID 1 do container `docker-market-worker-1`
a partir de um sidecar no mesmo namespace de PID, com `SYS_PTRACE`:

```
docker run --rm --pid=container:docker-market-worker-1 --cap-add SYS_PTRACE --cap-add SYS_ADMIN \
  -v "C:/dev/project-hunter/.claude/state/profile:/out" \
  python:3.12-slim sh -c "pip install --quiet py-spy; \
    py-spy record --pid 1 --duration 90 --rate 120 --format raw --output /out/raw-<N>.txt"
```

Agregação: `.claude/state/profile/agg.py` (top por self/cumulativo) e `.claude/state/profile/buckets.py`
(por subsistema). Dados brutos: `.claude/state/profile/raw-50.txt`, `raw-200.txt`.

## Corrida A — 50 mercados (300 assinaturas), estado atual do `main`

`docker stats`: **CPU 95,1%** de um core, 151 MiB. 10.878 amostras em 90 s.

### Self time por subsistema

| Subsistema | Self |
|---|---|
| ssl read/socket (asyncio+ssl) | 13,15% |
| websockets `permessage_deflate` + `frames.parse` | 11,62% |
| **`pydantic/main.py:__init__`** | **10,83%** |
| cliente `redis` (encode/send/parse) | 6,33% |
| `json.loads` (stdlib) | 5,52% |
| `normalize.py` (`to_decimal`, `ms_to_datetime`) | 4,31% |
| sqlalchemy | 2,68% |
| msgpack | 0,07% |
| idle / epoll wait | 1,29% |

### Cumulativo por função da aplicação

| Função | Cumulativo |
|---|---|
| `_handle_raw_message` (adapter, ws.py) | **32,40%** |
| — `parse_stream_message` | 20,13% |
| — — `parse_depth20` | 10,50% |
| — — `parse_book_ticker` | 6,87% |
| — — `parse_agg_trade` | 1,31% |
| — — `parse_kline_ws` | 0,55% |
| `handle_event` (worker, ingest.py) | **15,03%** |
| — `write_ticker` → `hot_state._hash` | 10,02% |
| — `push_trade` | 2,48% |
| — `write_book` | 0,98% |
| `flush_ticks` (coalescer 250 ms) | 3,25% |
| `run_recovery` | 3,55% |
| `data_received` (websockets) | 15,09% |

## Corrida B — 200 mercados (1.200 assinaturas), alvo do plano

`docker stats`: **CPU 99,2% → 99,9%** de um core, 248→265 MiB. 11.385 amostras em 90 s.

| Subsistema | Self |
|---|---|
| **`pydantic/main.py:__init__`** | **20,36%** |
| websockets deflate + frames | 10,80% |
| `json.loads` (stdlib) | 6,23% |
| `normalize.py` Decimal/datetime | 5,69% |
| ssl read/socket | 2,02% |
| cliente `redis` | 0,21% |
| sqlalchemy | 0,18% |

| Função | Cumulativo (200) | Cumulativo (50) |
|---|---|---|
| `_handle_raw_message` | **66,05%** | 32,40% |
| — `parse_stream_message` | 33,92% | 20,13% |
| — — `parse_depth20` | **23,02%** | 10,50% |
| — — `parse_book_ticker` | 7,82% | 6,87% |
| `handle_event` (worker) | **0,18%** | 15,03% |
| — `write_ticker`/`_hash` | 0,08% | 10,02% |
| `drain_loop` / `snapshot_loop` / `run_recovery` | 0,11 / 0,11 / 0,18% | — |

### Leitura honesta da corrida B

Com 200 mercados o processo **não é lento, é faminto**: 66% do tempo está dentro do
`_handle_raw_message` das tarefas leitoras e o consumidor (`handle_event`, hot state, persistência)
recebe **0,18%** do processador. É por isso que a T1.6 mediu book em 8/200 e tickers expirando:
não é o Redis nem o Postgres, é que o consumidor nunca é agendado.

## Hipóteses da tarefa — confirmadas / refutadas pelo perfil

| Hipótese | Veredito | Número |
|---|---|---|
| `pydantic` por evento é o maior custo da aplicação | **CONFIRMADA** | 10,8% (50) → 20,4% (200) de self time, o maior item isolado |
| `json.loads` puro vs `orjson` | **CONFIRMADA, custo médio** | 5,5% → 6,2% de self time |
| `Decimal(str)` por campo | **CONFIRMADA, custo médio** | `normalize.py` 4,3% → 5,7% |
| `redis` comando a comando sem pipeline | **CONFIRMADA a 50, irrelevante a 200** | 6,3% (50) → 0,2% (200), porque o consumidor nem roda |
| `msgpack` caro | **REFUTADA** | 0,07% |
| logging por evento | **REFUTADA** | não aparece no perfil |
| overhead de `asyncio` com 1.200 streams | **PARCIAL** | ver ACHADO-2 |

## Dois achados que o perfil entregou e que ninguém tinha levantado

### ACHADO-1 (CRITICAL de performance) — a fila descarta em O(n) e alimenta a própria saturação

`packages/exchange-adapters/hunter_exchanges/binance/event_queue.py`:

| Linha | Self time a 200 mercados |
|---|---|
| `_is_final_kline` (l.30-31) | **11,51%** |
| `_evict_one` (l.66/67/70) | **6,30%** |

Somados, **~17,8% do processador** é gasto só decidindo quem descartar. `_evict_one` faz uma
varredura linear de um `deque` de 10.000 itens a cada `put` com a fila cheia, chamando
`isinstance` + acesso a atributo em cada item, e ainda usa `del self._items[index]`, que num
`deque` é O(n). Com a fila permanentemente cheia (o caso real a 200 mercados), **todo** `put`
paga esse custo. É um laço de realimentação: quanto mais saturado, mais caro fica processar,
mais satura. Correção: contar os finais separadamente (ou manter duas filas) para que o descarte
seja O(1) — o item da cabeça quase nunca é um kline final.

### ACHADO-2 — o consumidor cria uma task e um timer por evento

`services/market-worker/hunter_market_worker/streaming.py:36-37` chama
`asyncio.ensure_future(stream.__anext__())` + `asyncio.wait({...}, timeout=0.1)` **por evento**:
uma task nova, um `call_at` no heap de timers e um cancelamento a cada evento, só para poder
checar a mudança de universo e o watchdog. A dez mil eventos por segundo isso é overhead puro
(`wait_for` 0,82% self, `call_at`/`time` visíveis no perfil da corrida A). O laço deveria ser um
`async for` limpo, com a checagem de universo/watchdog movida para uma task de 100 ms à parte.

## Aritmética da meta

Transporte (ssl + websockets + deflate) é ~25% a 50 mercados e é proporcional a bytes: a 200
mercados sozinho já custa ~100% de um core. Mesmo zerando **todo** o custo da aplicação, um
processo não sustenta 200 mercados abaixo de 70% de um core. **O sharding não é o plano B, é o
único caminho para a meta** — as otimizações do caminho quente decidem *quantos* shards.
