# S2 — prova operacional do `strategy-worker` em modo sombra

**Janela:** 2026-09-06 00:09:22 → 00:41:51 UTC (32 min 29 s), stack local
(`infra/docker/docker-compose.yml`) contra a Binance real, com o `market-worker` já coletando o
top 50 (override do T1.6b). Imagem `hunter-api:dev` construída do código final desta tarefa
(inclui as correções da revisão de diff da Astra).

Tudo abaixo é saída real de comando. Nada aqui é estimativa.

## 1. Pré-requisitos

```
$ docker compose -f infra/docker/docker-compose.yml exec -T postgres psql -U hunter -d hunter -c "select version_num from alembic_version;"
   version_num
-----------------
 0002_shadow_lab
(1 row)
```

```
$ docker compose -f infra/docker/docker-compose.yml ps
NAME                       IMAGE            SERVICE           STATUS
docker-market-worker-1     hunter-api:dev   market-worker     Up (healthy)
docker-strategy-worker-1   hunter-api:dev   strategy-worker   Up (healthy)
docker-postgres-1          postgres:16-alpine  postgres       Up (healthy)
docker-redis-1             redis:7-alpine   redis             Up (healthy)
```

## 2. Ativação auditada das duas versões

Ensaio primeiro (nada escrito):

```
$ docker compose ... run --rm --entrypoint python strategy-worker \
    infra/scripts/activate_strategy_version.py momentum v1 --changelog "S2 dry run" --dry-run
would activate momentum v1 with code_ref hunter_core.strategies@sha256:13dfa32298cbc2dbbe54aac4cd785be4a85246cdf5daaa9564a4cf29301ea0b5 (19 parameters)
```

Ativação real:

```
$ ... activate_strategy_version.py momentum v1 --changelog "S2 operational proof 2026-09-05"
activated momentum v1 at 2026-09-05T23:19:56.334638+00:00 with code_ref hunter_core.strategies@sha256:13dfa32298cbc2dbbe54aac4cd785be4a85246cdf5daaa9564a4cf29301ea0b5

$ ... activate_strategy_version.py volume_anomaly v1 --changelog "S2 operational proof 2026-09-05"
activated volume_anomaly v1 at 2026-09-05T23:20:09.899561+00:00 with code_ref hunter_core.strategies@sha256:13dfa32298cbc2dbbe54aac4cd785be4a85246cdf5daaa9564a4cf29301ea0b5
```

```
$ psql -c "select s.key, v.version, v.status, v.activated_at, v.params_format, left(v.code_ref,40) from strategy_versions v join strategies s on s.id=v.strategy_id where v.activated_at is not null;"
      key       | version | status |         activated_at          | params_format |                   left
----------------+---------+--------+-------------------------------+---------------+------------------------------------------
 momentum       | v1      | active | 2026-09-05 23:19:56.334638+00 |             1 | hunter_core.strategies@sha256:13dfa32298
 volume_anomaly | v1      | active | 2026-09-05 23:20:09.899561+00 |             1 | hunter_core.strategies@sha256:13dfa32298
(2 rows)
```

O worker reconheceu as duas sem reinício (cache de versões, TTL 60 s):

```
2026-09-06T00:10:02Z [info] shadow_active_versions versions=['momentum:v1', 'volume_anomaly:v1'] role=strategy
```

## 3. Contagem de avaliações por estado (heartbeat `hb:strategy:shadow`)

```
$ docker compose ... exec -T redis redis-cli HGETALL hb:strategy:shadow
ts                    2026-09-06T00:41:50.337239+00:00
instance              61b490aa53b5:1
cohort                prospective
evaluated_bars        1799
evaluations_by_state  {"unavailable":1082,"triggered":40,"not_triggered":677}
errors                0
outbox_pending        0
outbox_lag_s          0.0
open_trackings        21
last_iteration        2026-09-06T00:41:04.838463+00:00
```

**Sobre os 1082 `unavailable`, que são a parte honesta desta prova.** Ao recriar os containers
às 00:09 o `market-worker` perdeu o minuto `00:08` em todos os mercados. A agregação da S1 exige
a janela contígua inteira (289 barras de 5 min = 1445 min), então **toda** avaliação ficou
`unavailable: gap` — medido diretamente:

```
$ ... exec -T strategy-worker python /tmp/probe.py
now 2026-09-06T00:11:07.888240+00:00 cut 2026-09-06T00:10:00+00:00 lag 67.88824
universe_changed_after: False
BTCUSDT volume_anomaly unavailable gap {'missing_minute': '2026-09-06T00:08:00Z'} bars 1559
ETHUSDT volume_anomaly unavailable gap {'missing_minute': '2026-09-06T00:08:00Z'} bars 1559
ZECUSDT volume_anomaly unavailable gap {'missing_minute': '2026-09-06T00:08:00Z'} bars 1559
```

A recuperação de gaps do `market-worker` preencheu o buraco entre 00:20 e 00:30
(`ingestion_gaps`: 786 → 95 `open`), e as avaliações passaram a produzir resultado. É a recusa
correta de agregar sobre um buraco — e é uma propriedade operacional que a S3 tem de mostrar
como cobertura (registrada em `.claude/state/notes-S2.md` §14).

## 4. Sinais emitidos (dado real da Binance)

```
$ psql -c "select st.key, count(*), min(s.emitted_at), max(s.emitted_at) from agent_signals s join strategy_versions v on v.id=s.strategy_version_id join strategies st on st.id=v.strategy_id group by 1;"
    strategy    | signals |             min               |             max
----------------+---------+-------------------------------+-------------------------------
 momentum       |      17 | 2026-09-06 00:30:11.496181+00 | 2026-09-06 00:32:18.872491+00
 volume_anomaly |      18 | 2026-09-06 00:25:01.939152+00 | 2026-09-06 00:35:42.297384+00
(2 rows)

$ psql -c "select count(distinct market_id) from agent_signals;"   ->  26
$ psql -c "select count(*) from agent_signals where supporting_features->>'purpose' = 'research_only';"  ->  35
```

Os 35 sinais carregam `purpose = research_only` no envelope — sem exceção.

## 5. Acompanhamentos e resultados

```
$ psql -c "select o.tracking_state, o.result, count(*), count(o.r_multiple) as with_r from signal_outcomes o group by 1,2 order by 1,2;"
 tracking_state |   result    | count | with_r
----------------+-------------+-------+--------
 active         | open        |    21 |      0
 terminal       | target      |     3 |      3
 terminal       | stop        |     4 |      4
 terminal       | invalidated |     3 |      3
 no_entry       | open        |     4 |      0
(5 rows)

$ psql -c "select coalesce(no_entry_reason, censored_reason, '-') as reason, count(*) from signal_outcomes group by 1 order by 2 desc;"
   reason   | count
------------+-------
 -          |    31
 late:delay |     3
 geometry   |     1
(3 rows)
```

Alvo, stop, invalidação, `late:delay` e `geometry` apareceram todos sobre dado real, sem
nenhum caso forçado. Um outcome encerrado, inteiro:

```
$ psql -x -c "select ... from signal_outcomes o join agent_signals s ... where o.tracking_state='terminal' limit 1;"
id            | bd7f99b6-c254-56da-8298-ac10684f8fb0
symbol        | MONUSDT
result        | stop
virtual_entry | 0.0253251860
virtual_stop  | 0.0251100000
exit_price    | 0.0250949340
r_multiple    | -1.1637376409
mfe           | 0.0000000000
mae           |                       <- nulo: a barra do stop é ambígua
funding       | 0
ambiguous     | true
coverage      | {"bars_known": "4", "bars_total": "4"}
```

`r_multiple < -1` porque os custos assumidos entram nos dois lados (spread/slippage no preço,
taxa fora dele); `mae` nulo porque a mínima da barra do stop pode ter vindo depois da saída.

## 6. Outbox e stream

```
$ psql -c "select count(*) total, count(dispatched_at) dispatched, count(*) filter (where dispatched_at is null) pending, max(attempts), count(last_error) from shadow_outbox;"
 total | dispatched | pending | max_attempts | errors
-------+------------+---------+--------------+--------
    35 |         35 |       0 |            1 |      0
(1 row)

$ redis-cli XLEN shadow.signals.emitted
42
```

Os 35 da janela mais 7 de uma janela anterior (as linhas do banco foram apagadas às 00:09 para
começar a medição limpa; o stream é append-only). Uma tentativa por evento, nenhum erro,
nenhuma pendência. Último evento:

```
{"event_id":"bd7f99b6-c254-56da-8298-ac10684f8fb0","type":"shadow.signals.emitted",
 "producer":"strategy-worker.shadow","key":"MONUSDT",
 "payload":{"purpose":"research_only","cohort":"prospective","tracking_state":"pending_entry",
 "stop":"0.02511","target1":"0.0257091969","entry_bar_open":"2026-09-06T00:36:00Z",
 "source_bar_close":"2026-09-06T00:35:00Z","decision_at":"2026-09-06T00:35:42.297384Z", ...}}
```

`event_id == signal_id`, como manda o item 6 da decisão conjunta.

## 7. Slots (`shadow_episodes`)

```
$ psql -c "select count(*) slots, count(*) filter (where armed) armed, count(open_outcome_signal_id) holding from shadow_episodes;"
 slots | armed | holding
-------+-------+---------
   402 |   371 |      21
(1 row)
```

402 slots = 2 versões × 201 mercados avaliados; 21 segurando um acompanhamento aberto (é o
mesmo 21 do heartbeat), 371 armados, os demais desarmados aguardando uma barra `not_triggered`
posterior ao término.

## 8. Readiness e log

```
$ ... exec -T strategy-worker python -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8001/ready',timeout=25); print(r.status, r.read().decode())"
200 {"database":true,"redis":true,"shadow_migration":true,"shadow_consumer":true,"shadow_outbox":true}

$ docker compose ... logs strategy-worker --since 40m | grep -cE "Traceback|Exception|error "
0
```

Nenhuma exceção, nenhum `[error]`, nenhum `[warning]` em 40 minutos de log.

## 9. Achado corrigido durante a prova

Na **primeira** tentativa (23:18–23:21) o worker morreu com
`redis.exceptions.TimeoutError: Timeout reading from redis:6379` em
`hunter_core/events/consume.py:85`. Causa: `consume()` bloqueia o `XREADGROUP` por 5000 ms e
`hunter_core/redis.py` define `socket_timeout = 5.0` — num stream ocioso os dois vencem no mesmo
instante. O container reiniciou (`restart: unless-stopped`) e nada se perdeu, mas um worker que
morre sempre que o mercado fica quieto não está supervisionado.

Corrigido em `hunter_strategy_worker/consumer.py` (`CONSUME_BLOCK_MS = 2000` + backoff no laço)
com regressão em `tests/test_consumer_supervision.py`. **O default de `consume()` continua
perigoso para qualquer outro consumidor de stream do projeto** — fica registrado como tarefa
própria em `.claude/state/notes-S2.md` §14.

## 10. O que esta prova NÃO mostra

- **Censura por gap irrecuperável** não ocorreu na janela (o `market-worker` recuperou todos os
  buracos). O caminho está coberto por teste de integração
  (`test_shadow_outcomes.py::TestCensorship`), não por dado de produção.
- **`tracking_hold`** não foi exercitado aqui: nenhum mercado com acompanhamento aberto saiu do
  top 50 em 32 minutos. Coberto por `services/market-worker/tests/test_universe_tracking_hold.py`.
- **Reentrega/restart durante o rearme** não foi provocado nesta janela; está nos testes de
  integração.
- 32 minutos e 10 outcomes encerrados estão **muito** abaixo do limiar editorial do item 9 da
  decisão conjunta (100 outcomes avaliáveis e 30 dias distintos). Nenhum número acima é
  performance de estratégia: são contagens de funcionamento do worker.
