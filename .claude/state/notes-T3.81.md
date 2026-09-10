# T3.81 — o flush da vela é o segundo salto que estoura o orçamento

Brief salvo em `.claude/state/brief-T3.81-flush-da-vela.md`. Medição só-leitura na VPS (`hunter-vps`), nenhum contêiner tocado, nenhuma escrita. Correção local (unit + testcontainer), não implantada.

## 1. Onde os segundos estavam

**Fato de partida (T3.79):** `flush` (proxy `candles.received_at − (open_time + 1 min)`, `source='ws'`) media p50 ≈ 1,03 s, p95 ≈ 3,5-4,1 s. Alvo p95 < 1 s.

**Por shard (real, `crc32(symbol) % 4`, mesma regra de `MARKET_SHARD=i/N`, item 8 do §1 do `PIPELINE.md`)** — 200 mercados monitorados na Binance perpétuo, mapeados localmente com o mesmo `zlib.crc32` do código (`shard_symbols`, `universe.py:87`) e confirmado batendo com `markets_monitored=56` do heartbeat real do shard 0:

| Shard | Candles (6h) | p50_s | p95_s | max_s |
|---|---|---|---|---|
| 0 (56 mercados) | 19 629 | 1.047 | 4.139 | 6.828 |
| 1 (42 mercados) | 14 863 | 1.022 | 3.721 | 4.932 |
| 2 (43 mercados) | 15 397 | 1.023 | 3.933 | 6.219 |
| 3 (59 mercados) | 20 271 | 1.034 | 3.914 | 6.306 |

Praticamente idêntico entre shards — **não é desbalanceamento de shard**. CPU dos 4 contêineres (`docker stats --no-stream`): shard 0 = 79,3 %, shard 1 = 47,5 %, shard 2 = 46,8 %, shard 3 = 53,1 % (host com 12 núcleos) — shard 0 mais quente mas sua distribuição de lag não destoa dos outros, então CPU por shard não é o gargalo dominante.

**Por minuto-da-hora** (`q01`, 60 linhas, `.claude/state/notes-T3.81.md` mesmo arquivo — ver §3): p50/p95 uniformes nos 60 minutos, **sem pico em :00/:15/:30/:45** (quando o refresh de universo de 15 min ou o housekeeping de cobertura rodam) — descarta os dois como causa.

**A causa (`persist.py::drain_loop`):** o lote de candles finais só é escrito quando `age = agora − (hora de chegada do primeiro item do lote) ≥ FLUSH_INTERVAL_S` (hardcoded `1.0`) **ou** o lote atinge 500 linhas/1 MiB. Com ~42-59 mercados por shard fechando quase juntos, o segundo critério nunca dispara — todo lote espera o segundo inteiro. Pior: um candle final cujo evento chegasse **depois** desse corte de 1,0 s perdia o lote corrente (já em flush) e iniciava um lote novo, pagando **outro segundo inteiro** por conta própria — dobrando o próprio jitter de emissão da Binance (kline final ~0-2 s após o fechamento da barra) em vez de absorvê-lo.

**Prova direta (q04):** distribuição de `received_at` por segundo real dentro de um minuto de fechamento (todos os shards + spot, 30 min): o grosso (60-75 %) cai exatamente em T+1s (o piso de `FLUSH_INTERVAL_S`), com cauda decrescente até T+6/7s — o padrão exato de "lote fixo de 1s + straggler pagando de novo".

**Contribuição da outbox** (`outbox_events.created_at → dispatched_at`, `q03`): tipicamente **0,09-0,3 s**, picos de 1-4 s só em minutos com rajada (>1000 eventos, ex. `16:11` com 1656 eventos → mediana 3,2 s — provavelmente recovery/backfill concorrente despejando muitas linhas de uma vez). Isso é **depois** do instante medido por `flush` (que fecha em `candles.received_at`, antes do `XADD`), então não explica o p95 de `flush` em si — é um segundo orçamento, o do outbox, geralmente pequeno.

**Orçamento (o que dava para medir hoje):**

| Trecho | p50 | p95 | Onde |
|---|---|---|---|
| exchange → nosso parse (`event_ts→received_at`) | `unknown` | `unknown` | instrumentação da T3.79 ainda não implantada na VPS |
| espera do lote em `drain_loop` (o alvo desta tarefa) | ≈ 1,0 s (piso fixo) | ≈ 3,5-4,1 s (piso + straggler pagando 2×) | `persist.py`, corrigido abaixo |
| escrita em Postgres (dentro do commit medido acima, não isolada) | pequena (lotes de 40-60 linhas) | — | `persist_rows.flush_batch` |
| outbox (fora do `flush` medido, e sim do envio ao stream) | 0,1-0,3 s | 1-4 s só em rajada | `outbox_events` |

## 2. A correção — maior alavanca primeiro

`services/market-worker/hunter_market_worker/persist.py`: `FLUSH_INTERVAL_S` deixa de ser `1.0` fixo e passa a ler `MARKET_CANDLE_FLUSH_MS` (padrão **200 ms**, mesma cadência que `tick_coalesce_ms` já usa no caminho efêmero). Isso corta o piso determinístico de ~1 s **e** encurta o "segundo pago em dobro" do straggler para ~0,2 s. Nenhuma mudança em `is_final`, `source`, cobertura (`observe_proof`/`stamp`, T3.46) ou no que cada linha carrega — só quando o lote fecha. Nenhum call site novo: o valor continua um módulo-constante lido uma vez na importação, exatamente como antes (um teste que precisa de outro número faz `monkeypatch.setattr(persist, "FLUSH_INTERVAL_S", ...)`, como toda a suíte já fazia).

Não implantado na VPS (regra do brief) — o "depois" ao vivo é tarefa de quem fizer o deploy medir de novo.

## 3. Comandos e saídas reais

```
$ timeout 30 ssh hunter-vps "echo ok && date -u"
ok
Thu Sep 10 16:30:44 UTC 2026

$ timeout 60 ssh hunter-vps "docker ps --format '{{.Names}}' | sort"
hunter-api-1 hunter-caddy-1 hunter-execution-worker-1 hunter-market-worker-1
hunter-market-worker-1-1 hunter-market-worker-2-1 hunter-market-worker-3-1
hunter-market-worker-spot-1 hunter-postgres-1 hunter-redis-1
hunter-scanner-worker-1 hunter-strategy-worker-1 hunter-web-1

$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli HGETALL hb:market:binance:0of4"
last_event_at 2026-09-10T16:30:55.607000+00:00
ws_state connected
subscriptions 336
markets_monitored 56
open_gaps 0
rest_gate ok
shard_index 0
shard_total 4
(sem ingest_lag_p50_s/flush_lag_p50_s -- instrumentação da T3.79 ainda não implantada nesta imagem, container criado 2026-09-09T15:20:32Z)
```

Shard por `crc32(symbol) % 4` (200 mercados perpétuos monitorados, Binance) — confere byte a byte com `markets_monitored=56` do heartbeat real do shard 0:
```
0 56
1 42
2 43
3 59
```

Flush-lag por shard (uma query por shard, `IN (<ids do shard>)`), `q02`-style manual:
```
=== shard 0 === candles=19629 p50_s=1.047 p95_s=4.139 max_s=6.828
=== shard 1 === candles=14863 p50_s=1.022 p95_s=3.721 max_s=4.932
=== shard 2 === candles=15397 p50_s=1.023 p95_s=3.933 max_s=6.219
=== shard 3 === candles=20271 p50_s=1.034 p95_s=3.914 max_s=6.306
```

Flush-lag por minuto-da-hora (`infra/scripts/sql/research/2026-09-10-t381-q01-flush-lag-by-minute.sql`, 60 linhas, ver saída completa na sessão — uniforme, p50 1.02-1.16, p95 3.4-4.3, sem pico em :00/:15/:30/:45).

Contribuição da outbox (`infra/scripts/sql/research/2026-09-10-t381-q03-outbox-contribution.sql`):
```
2026-09-10 16:34:00+00 | 215 events | p50=0.143 p95=0.215
2026-09-10 16:33:00+00 | 215 events | p50=0.149 p95=0.183
...
2026-09-10 16:11:00+00 | 1656 events | p50=3.200 p95=4.466  <- rajada (recovery/backfill concorrente)
2026-09-10 16:10:00+00 | 216 events | p50=0.125 p95=0.323
```

Burst de chegada por segundo real (`infra/scripts/sql/research/2026-09-10-t381-q04-candles-per-minute-burst.sql`), amostra de um minuto:
```
bar=16:34:00 -> :35:01=129 :35:02=31 :35:03=43 :35:04=10 :35:05=2
bar=16:33:00 -> :34:01=144 :34:02=44 :34:03=27
bar=16:32:00 -> :33:01=129 :33:02=16 :33:03=60 :33:04=3 :33:05=7
```
(grosso em T+1s = o piso do `FLUSH_INTERVAL_S` antigo; cauda decrescente até T+6/7s = stragglers pagando o segundo em dobro)

CPU dos shards (`docker stats --no-stream`):
```
hunter-market-worker-1       79.29%   (shard 0/4)
hunter-market-worker-1-1     47.48%   (shard 1/4)
hunter-market-worker-2-1     46.83%   (shard 2/4)
hunter-market-worker-3-1     53.13%   (shard 3/4)
hunter-market-worker-spot-1  22.11%
```
Host: 12 núcleos (`nproc`).

Testes locais (saída real):
```
$ timeout 290 uv run pytest services/market-worker/tests/test_flush_latency.py -q
..                                                                       [100%]
2 passed in 2.34s

$ timeout 290 uv run pytest services/market-worker/tests/test_persist.py -q
........                                                                 [100%]
8 passed in 26.48s

$ timeout 290 uv run pytest services/market-worker/tests/test_persist_batch.py -q
.........                                                                [100%]
9 passed in 34.14s

$ timeout 290 uv run pytest services/market-worker/tests/test_persistence_contracts.py -q
............                                                             [100%]
12 passed in 34.38s

$ timeout 290 uv run pytest services/market-worker/tests/test_tape_coverage.py -q
.................                                                        [100%]
17 passed in 6.29s

$ timeout 120 uv run ruff check services/market-worker/hunter_market_worker/persist.py services/market-worker/tests/test_flush_latency.py services/market-worker/tests/test_persist.py
All checks passed!

$ timeout 120 uv run ruff format --check services/market-worker/hunter_market_worker/persist.py services/market-worker/tests/test_flush_latency.py services/market-worker/tests/test_persist.py
3 files already formatted

$ timeout 180 uv run pyright services/market-worker/hunter_market_worker/persist.py services/market-worker/tests/test_flush_latency.py services/market-worker/tests/test_persist.py
0 errors, 0 warnings, 0 informations

$ timeout 120 uv run python infra/scripts/check_file_size.py
scanned 620 files; 0 over budget, 0 grandfathered
```

## 4. Arquivos (git status --porcelain, só os meus)

```
 M docs/EXCHANGE_INTEGRATION.md
 M docs/PIPELINE.md
 M services/market-worker/hunter_market_worker/persist.py
 M services/market-worker/tests/test_persist.py
?? .claude/state/brief-T3.81-flush-da-vela.md
?? .claude/state/notes-T3.81.md
?? infra/scripts/sql/research/2026-09-10-t381-q01-flush-lag-by-minute.sql
?? infra/scripts/sql/research/2026-09-10-t381-q02-flush-lag-by-shard.sql
?? infra/scripts/sql/research/2026-09-10-t381-q03-outbox-contribution.sql
?? infra/scripts/sql/research/2026-09-10-t381-q04-candles-per-minute-burst.sql
?? services/market-worker/tests/test_flush_latency.py
```

Todo o resto em `git status --porcelain` da árvore (T3.76, T3.74c/replay, obsidian, design artifacts, `.claude/state/tmp/**` etc.) é de outros agentes — não tocado por esta tarefa. `q02` foi escrita para o caso geral (`crc32` via `md5`/`hashtext` no SQL não reproduz o `zlib.crc32` do código), mas a medição por shard real que está na tabela do §1 foi feita com os `market_id` corretos, calculados localmente em Python com o mesmo `zlib.crc32` (ver comandos acima) e quatro `IN (...)` diretos — não a query `q02` como está no arquivo (deixada como esqueleto documentado, ver comentário nela).

## 5. Concerns / o que não foi feito

- **Não implantado na VPS** (regra do brief): o número "depois" da correção (o novo p50/p95 de `flush`) só existe depois de um deploy + nova janela de medição. O que existe é a prova de mecanismo (unit com clock real via `time.monotonic` mostrando que o lote flush em <0,5s ao invés de ~1,0-1,1s, e um caso com Postgres real de ponta a ponta em <1,0s incluindo a escrita).
- **O hop `exchange → ingest` continua `unknown`** em produção (instrumentação da T3.79 não implantada) — não dá para separar hoje "jitter da Binance" de "tempo de parse do nosso WS" com dados reais; a evidência indireta é a distribuição de `received_at` por segundo (q04), que mistura os dois.
- **`q02-flush-lag-by-shard.sql`** (o arquivo, não a medição real usada) usa uma aproximação (`md5`/`hashtext`) porque Postgres não tem `crc32` nativo — documentado no comentário do arquivo; a tabela do §1 usa a partição exata (Python `zlib.crc32`, mesma função do código).
- Não toquei `coalesce.py` (ticks) nem `coverage.py`/`coverage_publish.py` — o problema estava inteiramente em `persist.py`; os testes de cobertura (`test_tape_coverage.py`) continuam verdes sem alteração alguma nesse código.
- `MARKET_CANDLE_FLUSH_MS` não tem, por ora, um valor diferente por shard no `docker-compose.prod.yml` (fora do escopo desta tarefa — não editei `infra/`); o mecanismo aceita, mas os quatro shards seguem o mesmo padrão de 200 ms até alguém tunar por container.
