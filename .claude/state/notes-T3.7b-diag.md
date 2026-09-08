# notes-T3.7b-diag — por que BTCUSDT e UNIUSDT ficaram em 14 dias

Data: 2026-09-08, ~13:06Z. Autor: exchange-integration-specialist. Diagnóstico **somente
leitura** na VPS (`ssh hunter-vps`, `/opt/project-hunter`). Nenhuma escrita feita na VPS, nenhum
código alterado. Fonte: `docker logs`, `psql` (read-only via `docker cp` + `docker exec ... -f`),
`redis-cli` (`XINFO GROUPS`, `HGETALL`).

## Achado central

BTCUSDT e UNIUSDT estão os dois no **shard 3** (`crc32(symbol) % 4 == 3`, confirmado por
`python3 -c "zlib.crc32(...)"` dentro do próprio container). O pedido de 31 dias **foi planejado
por inteiro** (outbox `market.backfill.requested`: 0 pendentes, `XINFO GROUPS` dos 4 grupos
`market-worker.backfill.binance.{0..3}of4` com `pending=0, lag=0`; `ingestion_gaps` tem 109/110
linhas `open` para BTC/UNI cobrindo exatamente 2026-08-08 → 2026-08-26, a janela que faltava). O
problema **não é a fila de admissão do pedido** — é o **estrato histórico do `recovery.py`**
(`MAX_HISTORY_GAPS_PER_CYCLE = 6` por shard por ciclo de 60 s, ordenado globalmente por
`gap_end DESC`), que está sendo **monopolizado por `MARSCOINUSDT`**, também no shard 3.

`MARSCOINUSDT` foi listada na Binance por volta de **2026-09-01 09:45 UTC** (primeiro candle
persistido). O mesmo pedido em lote de 31 dias (`infra/scripts/request_backfill.py`, mesmo
`event_id` batch às 04:34:46Z, mesmo `reason=beta_history`) pediu história para ela também — 5
janelas de 7 dias, 2026-08-08 → 2026-09-08, igual a BTC/UNI. As 4 janelas mais antigas
(2026-08-08 → 2026-09-01) são **impossíveis por construção**: a Binance nunca terá candles de
antes da listagem. `recover_registered` não distingue "resposta vazia porque é antes da listagem"
de "resposta vazia transitória": incrementa `gap.attempts` incondicionalmente, recebe `200 OK` com
zero candles no intervalo, não marca `recovered`, e após 5 tentativas marca `failed`
(`recovery_drain.MAX_ATTEMPTS = 5`) — sem nenhum log de erro, porque não houve exceção. Uma hora
depois (`FAILED_RETRY_AFTER_S = 3600`), `reopen_stale_failed` reabre até `MAX_REOPEN_PER_CYCLE = 20`
por ciclo, e o ciclo se repete **para sempre**: nenhuma dessas 148 janelas (116 `open` + 32
`failed` no momento da medição) jamais vai virar `recovered`.

Como `pending_gaps` ordena o estrato histórico inteiro do shard por `gap_end DESC` (não por
mercado, não round-robin), e o `gap_end` mais recente de `MARSCOINUSDT` (2026-08-31 23:59 aberto,
2026-09-01 03:59 falho) é **mais novo** que o de BTC/UNI/NEAR/DASH/ARB (todos travados em
2026-08-26), `MARSCOINUSDT` sempre ganha os 6 slots do ciclo. BTC tem `attempts=0` em todas as 109
linhas `open` — **nunca foi tocado uma única vez** desde a criação às 04:34:46Z, ~8h30 antes desta
medição.

## Evidência (comandos e saída real)

**Shard dos containers e do símbolo:**
```
$ ssh hunter-vps 'docker inspect hunter-market-worker-1 --format "{{range .Config.Env}}{{println .}}{{end}}" | grep SHARD'
MARKET_SHARD=0/4
# (idem para -1-1=1/4, -2-1=2/4, -3-1=3/4)

$ docker exec hunter-market-worker-1 python3 -c "import zlib; ..."
BTCUSDT 3
UNIUSDT 3
ETHUSDT 0
SOLUSDT 0
XRPUSDT 0
DOGEUSDT 2
```

**Todos os 4 shards reiniciaram juntos às 12:10:00Z** (30 min antes da medição, ~1h20 antes desta
nota) — `docker inspect --format 'StartedAt'` idêntico (±0,7 s) nos 4 containers, `RestartCount=0`
em todos, primeira linha de log é `"Started server process [1]"` às 12:10:0x. Não investigado
o motivo do reinício (fora do escopo de leitura desta tarefa — não há indício de crash: sem
traceback antes do corte de log, `ExitCode(prev)=0`); registrado porque explica por que
`market_backfill_planned` de BTC/UNI (feito às 04:34–04:35Z) não aparece em `docker logs` (o buffer
do container atual só começa às 12:10Z).

**Ingestion_gaps por mercado:**
```sql
SELECT market_id, status, count(*), min(gap_start), max(gap_end), sum(attempts), max(attempts)
FROM ingestion_gaps WHERE market_id IN (<BTCUSDT>, <UNIUSDT>) GROUP BY market_id, status;
```
```
 BTCUSDT | open      |   109 | 2026-08-08 03:32 | 2026-08-26 04:31 | attempts sum=0 max=0
 BTCUSDT | recovered |    91 | 2026-08-26 04:32 | 2026-09-08 12:09 | attempts sum=91 max=1
 UNIUSDT | open      |   110 | 2026-08-08 03:32 | 2026-08-26 08:31 | attempts sum=0 max=0
 UNIUSDT | recovered |    92 | 2026-08-26 08:32 | 2026-09-08 12:09 | attempts sum=92 max=1
```

**Ranking do estrato histórico do shard 3 (o que compete pelos 6 slots/ciclo):**
```sql
SELECT m.symbol, g.status, count(*), min(g.gap_end), max(g.gap_end)
FROM ingestion_gaps g JOIN markets m ON m.id=g.market_id JOIN exchanges e ON e.id=m.exchange_id
WHERE e.code='binance' AND m.symbol IN (<57 símbolos do shard 3>) AND g.status IN ('open','failed')
GROUP BY m.symbol, g.status ORDER BY max(g.gap_end) DESC;
```
```
 MARSCOINUSDT | failed |  32 | 2026-08-27 04:31 | 2026-09-01 09:44   <- mais novo, ganha sempre
 MARSCOINUSDT | open   | 116 | 2026-08-08 07:31 | 2026-08-31 23:59
 NEARUSDT     | open   | 110 | 2026-08-08 07:31 | 2026-08-26 08:31
 UNIUSDT      | open   | 110 | 2026-08-08 07:31 | 2026-08-26 08:31
 BTCUSDT      | open   | 109 | 2026-08-08 07:31 | 2026-08-26 04:31
 DASHUSDT     | open   | 109 | 2026-08-08 07:31 | 2026-08-26 04:31
 ARBUSDT      | open   | 109 | 2026-08-08 07:31 | 2026-08-26 04:31
```

**MARSCOINUSDT: candle mais antigo persistido = data de listagem:**
```sql
SELECT min(open_time), max(open_time), count(*) FROM candles c JOIN markets m ON m.id=c.market_id
WHERE m.symbol='MARSCOINUSDT' AND c.timeframe='1m';
-- 2026-09-01 09:45:00+00 | 2026-09-08 13:02:00+00 | 10278
```

**Falhas recentes de MARSCOINUSDT, sem exceção, HTTP 200 sempre:**
```sql
SELECT gap_start, gap_end, status, attempts, detected_at FROM ingestion_gaps
WHERE market_id=<MARSCOINUSDT> AND status='failed' ORDER BY detected_at DESC LIMIT 15;
-- 15 linhas, todas attempts=5, detected_at entre 12:39 e 13:02Z (nesta sessão do container)
```
```
$ docker logs hunter-market-worker-3-1 --since ... --until ... | grep MARSCOINUSDT
{"event": "HTTP Request: GET .../klines?symbol=MARSCOINUSDT&...&startTime=1788220800000... \"HTTP/1.1 200 OK\""}
(nenhum log de erro/exceção associado — as 5 tentativas "sucedem" no transporte e falham em silêncio
porque o intervalo pedido é inteiramente anterior à listagem)
```

**Origem do pedido — mesmo lote, mesma razão, para BTC/UNI e MARSCOINUSDT:**
```sql
SELECT payload->'payload'->>'symbol', payload->'payload'->>'reason', payload->'payload'->>'gap_start', ...
FROM outbox_events WHERE stream='market.backfill.requested' AND symbol IN (...);
```
18 linhas: BTCUSDT, MARSCOINUSDT e UNIUSDT com **as mesmas 5 janelas de 7 dias**
(`reason=beta_history`, `requested_by=infra/scripts/request_backfill.py`), mais uma janela
`funding_history` — confirma que `MARSCOINUSDT` entrou no mesmo lote de 20 mercados sem checar
data de listagem.

**Outbox e grupos, sem pendência:**
```
$ psql: SELECT count(*), pending FROM outbox_events WHERE stream='market.backfill.requested';
 108 | pending=0 | max_attempts=1

$ docker exec hunter-redis-1 redis-cli XINFO GROUPS market.backfill.requested
market-worker.backfill.binance.0of4  pending=0 lag=0
market-worker.backfill.binance.1of4  pending=0 lag=0
market-worker.backfill.binance.2of4  pending=0 lag=0
market-worker.backfill.binance.3of4  pending=0 lag=0
market-worker.backfill.binance.0of1  pending=0 lag=114   <- grupo órfão de topologia antiga (N=1),
                                                              conhecido (PIPELINE §1b item 2), não é a causa
```

**Orçamento REST — não é o gargalo:**
```
$ docker exec hunter-redis-1 redis-cli HGETALL rl:binance:request_weight
tokens=2397.2 (teto 2400)   <- praticamente cheio, sem contenção
```

**Heartbeats — só o shard 3 tem backlog:**
```
hb:market:binance:0of4  open_gaps=0     (ETH/SOL/XRP)
hb:market:binance:1of4  open_gaps=2
hb:market:binance:2of4  open_gaps=0     (DOGE)
hb:market:binance:3of4  open_gaps=666   (BTC/UNI)   rest_gate=ok, ws_state=connected, reconnects=0
```
`open_gaps=666` isolado no shard 3 é a assinatura direta do monopólio de `MARSCOINUSDT`.

## Respostas às 4 perguntas

**(1) Shard e planejamento.** BTC e UNI estão os dois no shard 3 (`3/4`). O pedido de 31 dias foi
planejado por inteiro — `ingestion_gaps` tem exatamente as 109/110 linhas `open` esperadas para a
janela que faltava (08-08→08-26), outbox com 0 pendentes, grupo `...3of4` com `pending=0 lag=0`.
Não há log `market_backfill_planned` recuperável para confirmar o `outcome` textual (o container
reiniciou às 12:10Z, depois do planejamento às 04:35Z), mas a evidência de estado (linhas certas,
sem `deferred`/`blocked` residual visível, sem `no_partition` no log atual) é consistente com
`accepted` ou `truncated` — nunca `refused`/`empty`.

**(2) Por que a fila parou.** Não parou por orçamento REST (bucket em 2397/2400) nem por rate
limit/429 (nenhum `system_event` de rate limit nos logs do shard 3) nem por erro de infraestrutura.
Parou porque o estrato histórico do `recovery.py` serve **6 lacunas por ciclo de 60 s, por shard,
numa fila única ordenada por `gap_end DESC`** (`recovery_queries.pending_gaps`), e
`MARSCOINUSDT` — listada em ~2026-09-01, mas incluída no mesmo lote de 31 dias — tem lacunas
`open`/`failed` cujo `gap_end` (até 2026-08-31/09-01) é mais recente que o de BTC/UNI (até
2026-08-26). Essas lacunas de `MARSCOINUSDT` são **irrecuperáveis por construção** (não existem
candles antes da listagem), mas o código não sabe disso: incrementa `attempts` até 5, marca
`failed`, e uma hora depois `reopen_stale_failed` as reabre — um ciclo que nunca termina e que
sempre vence a disputa pelos 6 slots contra BTC/UNI. Confirmado por `attempts=0` em **todas** as
109 linhas `open` de BTC: nunca foram sequer tentadas.

**(3) O que faz o BTC andar sem mudar código.** Republicar `request_backfill.py --days 31
--markets BTCUSDT,UNIUSDT` **não ajuda** — o pedido já está totalmente planejado (mesmo
`event_id`, mesma janela; nada novo para gravar). O que destravaria, sem mudar código, é uma
**operação de escrita no banco** que este diagnóstico (somente leitura) não executou nem deveria
executar sem autorização explícita: aposentar as ~148 lacunas de `MARSCOINUSDT` cujo `gap_end` é
anterior a `2026-09-01 09:45:00+00` (a data real de listagem, medida em `candles`), tirando-as de
`open`/`failed` para que parem de competir. Exemplo do que seria necessário (não executado):
```sql
UPDATE ingestion_gaps SET status='recovered', recovered_at=now()
WHERE market_id = <MARSCOINUSDT> AND status IN ('open','failed')
  AND gap_end < '2026-09-01 09:45:00+00';
```
Marcar como `recovered` é uma aproximação imprecisa (nenhum candle foi de fato recuperado); o
correto seria um status novo (`unrecoverable`/`not_listed`) — que é mudança de código (item 4). Com
essas linhas fora da fila, o `gap_end` mais recente do estrato histórico do shard 3 passa a ser o
de BTC/UNI/NEAR/DASH/ARB (2026-08-26), e a 219 lacunas restantes a 6/ciclo de 60 s levariam
~37 min para zerar. **Nenhuma ação de escrita foi tomada nesta tarefa.**

**(4) Mudança de código que evitaria isso.** Duas frentes, a segunda é a raiz:
- *Prioridade para pedido explícito*: o estrato histórico hoje é uma fila global por `gap_end DESC`
  sem noção de "quem pediu". Dar um sub-orçamento reservado (ex.: 2–3 dos 6 slots) para lacunas
  nascidas de um `market.backfill.requested` explícito (`reason` != o motivo orgânico da detecção
  periódica), ou trocar a ordenação por um round-robin por mercado dentro do estrato histórico, faz
  um mercado com backlog grande parar de monopolizar os outros.
- *Raiz real*: `recover_registered` não distingue "resposta vazia porque é antes da listagem" de
  "resposta vazia transitória". Um mercado cujo histórico pedido é inteiramente anterior ao seu
  primeiro candle conhecido (ou ao primeiro trade retornável pela exchange) deveria virar um estado
  terminal explícito (`unrecoverable`, com `reason`) na primeira tentativa, nunca reentrar no ciclo
  `failed` → `reopen_stale_failed` a cada hora. Isso é o análogo, para "listado depois", do caso
  obrigatório "mercado delistado" que a suíte de fixtures já cobre (`docs/EXCHANGE_INTEGRATION.md`)
  — vale um teste próprio (`test_gap_entirely_before_listing_never_retries_forever`).

## Observação lateral (fora do escopo desta pergunta)

Shards 0 e 2 mostram `dropped_events` alto (2542 e 7714) e o log do shard 3 tem
`tape_coverage_interval_broken reason=queue_backlog` (backlog até 942) nos ~50 min desde o
reinício às 12:10Z. Não investigado — é ingestão ao vivo, não backfill — mas registrado porque
pode ser sintoma do mesmo reinício simultâneo dos 4 shards.
