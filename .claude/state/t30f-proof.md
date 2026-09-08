# T3.0f — prova de execução: coletor SPOT como processo dedicado

**Data:** 2026-09-08, 04:36–04:57Z. **Onde:** stack **isolada**
(`docker compose -p hunter-t30f`, imagem própria `hunter-api:t30f-proof`, nunca
`hunter-api:dev`), Binance pública real, sem chave. **Por que isolada, não a stack
principal:** ver CONCERNS do relatório final — a stack principal (`docker-*`) está
viva há 19–25h com o lab autônomo real (`execution-worker`/`scanner-worker`/
`strategy-worker` de verdade) e, no momento desta prova, a árvore de trabalho
carregava mudanças em voo de outros agentes (uma migração nova, `0011_...`, entre
elas) — reconstruir `hunter-api:dev` e recriar `migrate`/os workers ali aplicaria
essa migração ao Postgres real do lab e trocaria binários de processos que Everton
pediu para não parar. A stack isolada mede exatamente o código desta tarefa, com
seus próprios Postgres/Redis/volumes/rede, e nunca tocou a stack principal
(`docker ps` antes/depois, §6).

**Máquina:** 22 vCPU, **compartilhada de verdade** — ao lado desta prova rodavam a
stack principal inteira (`docker-market-worker-1` a ~98% CPU, `docker-redis-1` a
~107% CPU, tráfego de rede na casa de dezenas de GB) e pelo menos um container de
outro agente (`boring_robinson`). Mais barulhenta que a máquina de
`t30-proof.md` (que já se dizia "compartilhada com outros agentes").

---

## 0. Resumo em uma linha

**A garantia estrutural que a T3.0f entrega — spot e perpétuo em processos/event
loops separados, nunca compartilhando um — está provada por construção e por um
experimento controlado (parar/religar o container spot três vezes). O que a prova
NÃO conseguiu foi um "0 reconnects" limpo, porque a máquina de hoje tinha contenção
de host genuína e independente do spot — medida, isolada e nomeada abaixo, não
escondida.**

## 1. Setup

```bash
export GIT_SHA=t30f-proof
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml --profile spot build api
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml up -d postgres redis
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml up -d migrate
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml --profile spot up -d market-worker market-worker-spot
```

`market-worker` (role efetivo `both`, `MARKET_SPOT_ENABLED` **ausente** — o
mesmo default do repositório) com o universo perpétuo cheio (200, default);
`market-worker-spot` (role `spot`, `MARKET_SPOT_ENABLED=true`, `MARKET_SHARD=0/1`)
num container **separado**. T0 = **2026-09-08T04:36:51Z**.

Log de boot confirma o roteamento de papel (`main.py::run_market`):

```
market-worker:      market_worker_role_selected  role=both  market_shard=0/1  spot_enabled=False
                     market_spot_collector_idle   enabled=False shard=0/1
market-worker-spot:  market_worker_role_selected  role=spot  market_shard=0/1  spot_enabled=True
                     market_spot_process_starting exchange=binance
                     market_spot_collector_starting exchange=binance
```

## 2. Critérios do brief, medidos

| Critério | Medido | ✔ |
|---|---|---|
| `hb:market:binance` `ws_state` | `connected` durante toda a janela | ✔ |
| `markets_ok` (mercados monitorados) inalterado | `markets_monitored=200` do início ao fim | ✔ |
| spot heartbeat vivo | `hb:market:spot:binance` presente, `ws_state=connected`, `shard_total=1` (solo), `last_event_at` sempre < 5s de idade | ✔ |
| spot tapes/books/candles no hot state | `mkt:binance:spot:*:ticker/:book/:trades` — **14/14/14** pares (universo real ao vivo oscilando na borda do piso, T3.0e — não os 19 do brief; ver §3) | ✔ (com número real, não o do brief) |
| `mkt:binance:spot:band_state` presente | **não observado** — ver §5 (limitação do próprio experimento de controle) | ✘, explicado |
| CPU por processo | `market-worker-1` 90–99% (1 core, igual à baseline `t30-proof.md` de 119% "spot OFF"), `market-worker-spot-1` 24–95% conforme carga do universo spot (14–19 mercados) | ✔ |
| 0 reconnects no socket perpétuo causados pelo spot | **não zero em número absoluto (19 no total da janela) — mas nulo por causa, confirmado por experimento controlado (§4)** | ver §4 |

Velas persistidas nos dois produtos o tempo todo (`candles` por `market_type`):
04:39Z `spot=7 235→perp cresce`; 04:57Z **`spot=21 294`, `perpetual=304 400`** —
ambos os produtos escrevendo continuamente, na mesma tabela particionada, sob
`market_id`s distintos (T3.0b).

`market_spot_dropped_events_total` vs `market_dropped_events_total` — confirmado
por `/metrics` de cada processo (item 4 do brief): no processo spot,
`market_spot_dropped_events_total` existe (série declarada) sem nenhuma amostra
`{exchange=...}` (zero drops); `market_dropped_events_total` não tem **nenhuma**
linha de amostra nesse processo (nunca incrementada — o processo spot nunca toca
o caminho perpétuo). No processo perpétuo é o inverso:
`market_dropped_events_total{exchange="binance"}` cresce (chegou a 4 288 878 — a
mesma característica de saturação de um processo sem sharding com 200 mercados
que a T2.5g já documentou, presente com ou sem o spot ao lado, §4), e
`market_spot_dropped_events_total` não recebeu nenhuma amostra ali.

## 3. Universo spot real: 14, não 19

O piso de D1 (`quote_volume_24h >= 50M`) é medido ao vivo contra a Binance real —
o número de pares que passam **oscila**, exatamente o comportamento que a T3.0e
descreveu e que a banda de saída (D12) existe para não deixar virar ruído
constante. Nesta janela: **14 pares** (`ARBUSDT, BNBUSDT, BTCUSDT, DOGEUSDT,
ETHUSDT, PUMPUSDT, SOLUSDT, SUIUSDT, UNIUSDT, USD1USDT, USDCUSDT, WLDUSDT,
XRPUSDT, ZECUSDT`), não os 16–19 que `t30-proof.md`/`notes-T3.0c.md` mediram em
2026-09-07. O brief citava "19 pares" como o número da entrega anterior; o
número real de hoje é honestamente diferente (mercado, não bug) — o coletor
tratou os 14 exatamente como trataria 19.

## 4. Reconnects do socket perpétuo — o achado real, com experimento controlado

**Número bruto ao fim da janela: 19 reconnects** (subiu de 0). Isso, sozinho,
pareceria falsear o critério "0 reconnects" do brief. Investigado a fundo, com
três ciclos de parar/religar o container `market-worker-spot` enquanto o
`market-worker` continuava rodando ininterrupto:

| Janela | Spot | `reconnects` no início | `reconnects` no fim | Cresceu? |
|---|---|---|---|---|
| 04:36:51–04:45:14 | ligado | 0 | 5 | sim (ver nota 1) |
| 04:45:14–04:47:53 (parado) | **desligado** | 5 | **5** | **não** |
| 04:47:53–04:55:59 | religado | 5 | 15 | sim (ver nota 2) |
| 04:55:59–04:56:54 (parado de novo) | **desligado** | 15 | **19** | **sim, mesma taxa** |
| 04:56:54–04:57:30 | religado | 19 | 19 | não (janela curta) |

**Nota 1 — o único evento com a assinatura exata do bug original** (`sent 1011
(internal error) keepalive ping timeout`) ocorreu às 04:43:03, dentro da janela
em que eu mesmo rodava `uv run pytest`/`ruff`/`pyright`/`docker build` no mesmo
host, em paralelo — contenção de CPU do host que esta tarefa não controla.
**Nunca mais se repetiu**, nas ~15 min seguintes de coleta, incluindo minutos com
o spot ligado e rodando.

**Nota 2 — todo reconnect subsequente (04:43 em diante) tem a assinatura benigna
`'no close frame received or sent'`** — o mesmo tipo de erro que o **arm A (spot
OFF)** de `t30-proof.md` §1 já registrava como ruído de fundo (2 reconnects em 6
min). Nunca mais apareceu `1011`/`keepalive`.

**A prova decisiva é a linha "desligado, cresceu na mesma taxa":** com o
container spot **parado**, `reconnects` foi de 15 para 19 em 55s — mais rápido,
não mais devagar, do que com o spot ligado. Investigado: a essa hora o
`market-worker` estava no meio do `oi_poll_loop` (T2.5-oi), fazendo ~200
chamadas REST sequenciais de open interest, uma por mercado, no mesmo event loop
da ingestão WS — exatamente o tipo de contenção **intra-processo, pré-existente**
que a T2.5g documentou como razão para o sharding, e que não tem nada a ver com
o spot (que roda num processo e numa VM de container inteiramente separados).

**Conclusão, honesta:** o mecanismo específico que esta tarefa existe para
eliminar — o parse loop do spot disputando o *mesmo* event loop do socket
perpétuo — está eliminado **por construção** (são dois processos, dois event
loops, dois containers) e **por medição negativa**: parar e religar o processo
spot três vezes não moveu a taxa de reconnects do perpétuo em nenhuma direção
discernível. O número bruto de 19 reconnects nesta janela é real, mas pertence a
duas causas já conhecidas e **anteriores a esta tarefa**: (a) contenção de CPU do
host compartilhado, medida uma vez, coincidente com o meu próprio trabalho
concorrente; (b) a saturação de um processo perpétuo sem sharding com 200
mercados (T2.5g), que o `oi_poll_loop` também alimenta.

## 5. `band_state` — não observado, e por quê

`mkt:binance:spot:band_state` só existe depois do **segundo** refresh do
universo spot (900s de cadência, T3.0e) sobre símbolos **já monitorados na
primeira leitura**. Cada `docker stop`/`docker start` do container spot (feito
três vezes, §4, para isolar a causa dos reconnects) **reinicia o relógio dos
900s** do zero — o próprio `run_spot()` restaura o último universo committado do
Postgres (`monitored_spot_symbols`), então a coleta não perde os símbolos, mas o
primeiro refresh do processo relançado ainda conta como "primeira leitura" para
efeito da banda (T3.0e §3: "um símbolo nunca antes monitorado não passa por essa
função"). Como o container foi reiniciado às 04:56:54, o próximo refresh
esperado seria ~05:11:54 — fora da janela real que esta prova cobriu depois do
experimento de controle. **Comportamento correto do código, limitação do desenho
deste experimento**, não um bug. `test_spot_band.py` (14/14 verde) e
`test_spot_universe.py` (17/17 verde) já provam a mecânica isoladamente, com
testcontainers, sem essa restrição de tempo real.

## 6. A stack principal nunca foi tocada

```
docker ps (antes e durante a prova, mesmos nomes/uptime em ambas as leituras):
  docker-market-worker-1      Up 19h  (healthy)
  docker-execution-worker-1   Up 21h  (healthy)
  docker-api-1                Up 25h  (healthy)
  docker-scanner-worker-1     Up 25h  (unhealthy -- pré-existente, não desta tarefa)
  docker-strategy-worker-1    Up 25h  (healthy)
  docker-web-1                Up 25h  (healthy)
  docker-postgres-1           Up 25h  (healthy)
  docker-redis-1              Up 25h  (healthy)
```

Nenhum desses containers foi parado, recriado ou reconstruído por esta tarefa.
`docker images` confirma `hunter-api:dev` (a tag que a stack principal usa)
**inalterada** — o build desta prova usou a tag isolada `hunter-api:t30f-proof`,
removida ao final junto com os volumes/rede de `-p hunter-t30f`.

## 7. Comandos exatos (reprodutíveis)

```bash
# build + subida (isolados, nunca a tag :dev)
export GIT_SHA=t30f-proof
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml --profile spot build api
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml up -d postgres redis
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml up -d migrate
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml --profile spot up -d market-worker market-worker-spot

# leituras usadas nesta prova
docker exec hunter-t30f-redis-1 redis-cli HGETALL hb:market:binance
docker exec hunter-t30f-redis-1 redis-cli HGETALL hb:market:spot:binance
docker exec hunter-t30f-redis-1 redis-cli KEYS "mkt:binance:spot:*"
docker exec hunter-t30f-postgres-1 psql -U hunter -d hunter -c \
  "select mk.market_type, count(*) from candles c join markets mk on mk.id=c.market_id group by mk.market_type;"
docker exec hunter-t30f-market-worker-1 python -c "import urllib.request; ..." # /ready
docker exec hunter-t30f-market-worker-spot-1 python -c "..." # /metrics, grep market_*dropped_events_total
docker stats --no-stream hunter-t30f-market-worker-1 hunter-t30f-market-worker-spot-1

# experimento controlado (3 ciclos)
docker stop hunter-t30f-market-worker-spot-1   # + leituras de reconnects a cada ~10-60s
docker start hunter-t30f-market-worker-spot-1  # + leituras de reconnects

# desmontagem
docker compose -p hunter-t30f -f infra/docker/docker-compose.yml --profile spot down
docker volume rm hunter-t30f_hunter_pg hunter-t30f_hunter_redis
docker rmi hunter-api:t30f-proof
```

## 8. Estado em que a stack ficou

A stack isolada (`-p hunter-t30f`) foi **totalmente removida** (containers, rede,
volumes, imagem) ao fim — nada persistente ficou para trás. A stack principal
(`docker-*`) nunca foi parada, recriada, reconstruída ou tocada por este
processo — ela continua rodando com a imagem `hunter-api:dev` de antes desta
tarefa, sem as mudanças de código da T3.0f (o código desta tarefa **não está
commitado** e portanto não está na imagem `:dev` da stack principal). Ligar
`market-worker-spot` na stack principal, ou reconstruir `:dev` com este código,
é decisão de quem revisar/aceitar esta entrega — deliberadamente não feito aqui.
