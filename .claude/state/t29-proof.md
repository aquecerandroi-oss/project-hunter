# Prova operacional T2.9 — outbox transacional no market-worker

**Quando:** 2026-09-06, 11:47Z → 12:05Z (16 min contínuos, 6 amostras).
**Como:** `docker compose -f infra/docker/docker-compose.yml up -d --build market-worker`
no stack local (postgres 16 + redis 7 + api + strategy-worker), Binance USDT-M
real, ~200 mercados. Amostragem a cada 3 min pelo script
`sample.sh` (`/ready` de dentro do contêiner, `psql` em `outbox_events`,
`redis-cli XLEN`, contagem de `candles`).

## 0. Bug encontrado antes de tudo: imagem obsoleta, não código

O contêiner estava em **crash loop** (`Restarting (1)`) com:

```
File "/app/services/market-worker/hunter_market_worker/durable.py", line 27
  from hunter_core.events.outbox import build_envelope, enqueue_many, event_id_for
ImportError: cannot import name 'build_envelope' from 'hunter_core.events.outbox'
```

A causa **não** é o fonte: `build_envelope` é definida em
`hunter_core/events/outbox_store.py:98` e reexportada por `outbox.py`. A imagem
`hunter-api:dev` é *baked* (sem bind mount, ver `docker-compose.yml`) e tinha
sido construída no meio da edição anterior. Confirmado por inspeção da imagem:

```
$ docker run --rm --entrypoint sh hunter-api:dev -c "grep -c 'build_envelope' /app/packages/core/hunter_core/events/outbox.py"
0
```

No host, `uv run python -c "from hunter_core.events.outbox import build_envelope"`
sempre funcionou, e `pytest apps/api/tests/integration/test_t17_market_pipeline_contract.py`
coleta e passa (`2 passed`). **Correção: rebuild.** Nenhuma linha de código foi
necessária.

## 1. Reconciliação na partida — provada de graça

O processo morto (crash loop) deixou eventos committados e não publicados. No
boot do processo novo:

```
2026-09-06T11:47:59.293487Z  market_worker_starting    exchange=binance role=market
2026-09-06T11:47:59.762412Z  market_outbox_reconciled  events=15 role=market
```

15 eventos que o processo anterior devia ao stream saíram antes de qualquer
evento novo. É exatamente o caminho "morreu entre o commit e o `XADD`", com
uma falha real em vez de injetada.

## 2. Amostras (saída real)

| t | contêiner | `/ready` | pendentes | idade do mais antigo | despachados | com `last_error` |
|---|---|---|---|---|---|---|
| 11:49:09Z | Up 1 min (healthy) | tudo `true` | 0 | 0 s | 3374 | 0 |
| 11:52:26Z | Up 4 min (healthy) | tudo `true` | 0 | 0 s | 4492 | 0 |
| 11:55:34Z | Up 7 min (healthy) | tudo `true` | 0 | 0 s | 5625 | 0 |
| 11:58:46Z | Up 10 min (healthy) | tudo `true` | 48 | 1,8 s | 6357 | 0 |
| 12:01:54Z | Up 13 min (healthy) | tudo `true` | 0 | 0 s | 7635 | 0 |
| 12:05:12Z | Up 17 min (healthy) | tudo `true` | 2 | 0,2 s | 9311 | 0 |

`/ready` em todas as amostras:

```
{"database":true,"redis":true,"ingestion":true,"persistence":true,"partitions":true,"outbox":true}
```

Os pendentes não-zero (48 e 2) são amostras tiradas **no meio de um flush de
virada de minuto**: a idade do mais antigo era 1,8 s e 0,2 s, e a consulta
por stream 2 s depois já mostrava zero. O alvo de prontidão é
`MAX_PENDING=500` / `MAX_LAG_S=30 s` — a folga medida é de mais de uma ordem de
grandeza em ambos os eixos.

## 3. Eventos chegando no stream, vindos da outbox

Última entrada de `market.candles.closed` no fim da janela — envelope inteiro,
`event_id` determinístico, `Decimal` serializado como string:

```
1788696333581-1
{"event_id":"521c7848-3882-50e2-a14a-d48156b8f4ca","type":"market.candles.closed",
 "ts":"2026-09-06T12:05:32.474382Z","producer":"market-worker","key":"binance:TRUMPUSDT",
 "payload":{"low":"2.381000","high":"2.383000","kind":"candle","open":"2.381000",
 "close":"2.383000","symbol":"TRUMPUSDT","volume":"7397.24","exchange":"binance",
 "is_final":true,"open_time":"2026-09-06T03:22:00Z","timeframe":"1m", ...}}
```

`XLEN` estável nos tetos de `DEFAULT_MAXLEN` (trim funcionando):
`market.candles.closed` 50 002 (teto 50 000), `market.derivatives` 20 007
(teto 20 000), `market.liquidations` 1 421 (abaixo do teto de 20 000).

Distribuição final por stream em `outbox_events` (despachados):
`market.candles.closed` 8216, `market.derivatives` 1106, `market.liquidations` 26.

Persistência correndo junto: ~800 candles finais por janela de 5 min
(~200 mercados x 4 min), consistente com o universo monitorado.

## 4. Saúde do processo

```
$ docker inspect -f '{{.RestartCount}} {{.State.StartedAt}}' docker-market-worker-1
0 2026-09-06T11:47:55.871300602Z
```

Zero reinícios. Ocorrências nos logs dos 16 min de
`outbox_sweep_failed | outbox_publish_failed | outbox_row_unreadable |
market_outbox_reconcile_failed | consume_read_deadline | rate_limit_gate_degraded`:
**0**.

## 5. Achado da prova (corrigido no diff)

O envelope acima mostra `"producer":"market-worker"` — o nome de serviço, não o
`market-worker@{instance}`. É uma vela de **backfill REST** (`open_time`
03:22Z contra `ts` 12:05Z, precedida de `market_gap_recovered` nos logs):
`recovery.py:157` chama `upsert_candles` sem `producer=`, porque não tem o
runtime em escopo. Só o campo de diagnóstico difere — `event_id` vem da chave
natural da vela, então a identidade é a mesma pelos dois caminhos. O docstring
de `durable.py` afirmava o contrário ("every runtime call site passes the
instance-scoped..."); foi corrigido e o comportamento real ficou fixado em
`test_a_rest_backfilled_candle_is_published_too`. Passar a instância pela
cadeia de recovery é follow-up (notes-T2.9.md).

## 6. O que esta prova NÃO cobre

- **Um só shard.** `FOR UPDATE SKIP LOCKED` com N despachantes está coberto por
  teste de integração (`test_two_dispatchers_never_publish_the_same_row_twice`),
  não por esta janela.
- **Redis caindo em produção.** Coberto por teste
  (`test_a_redis_outage_leaves_the_row_pending_with_its_error`); não foi
  injetado no stack durante os 16 min.
- **Retenção.** ~9 300 linhas em 16 min só do market-worker (da ordem de
  700 mil/dia). Nada apaga linhas despachadas hoje — pendência registrada para
  o database-architect em notes-T2.9.md.

## 7. Segunda janela — após as correções pedidas pela Astra

Depois de fechar os dois must-fix da Astra (grace de prontidão limitado,
truncamento de replay visível) e de dividir `outbox.py` em
`outbox.py` + `outbox_recovery.py`, o worker foi reconstruído e revalidado.
Importa porque a **semântica do `/ready` mudou**: `outbox` agora fica vermelho
se a primeira observação de backlog nunca acontecer.

| t | contêiner | `/ready` | pendentes | idade | despachados | com `last_error` |
|---|---|---|---|---|---|---|
| 12:34:25Z | Up 1 min (healthy) | tudo `true` | 1 | 0,8 s | 39056 | 0 |
| 12:38:40Z | Up 5 min (healthy) | tudo `true` | 2 | 2,0 s | 40068 | 0 |

O `outbox` fica verde dentro da janela de graça e continua verde depois dela,
porque a primeira varredura acontece em menos de um segundo — a graça termina
por observação, não por relógio.

**Reconciliação de novo, com uma morte de verdade:** o `docker compose up -d`
matou o processo anterior no meio da operação. O novo drenou o que ele devia:

```
2026-09-06T12:33:58.948880Z  market_outbox_reconciled  events=3674 role=market
```

3 674 eventos committados e não publicados saíram na ordem de criação antes de
qualquer evento novo. Zero reinícios; zero ocorrências de
`outbox_sweep_failed | outbox_publish_failed | outbox_row_unreadable |
market_outbox_reconcile_failed` em toda a janela.
