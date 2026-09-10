# T3.74f — concorrência 32 não bastou: perfil da rajada e sharding do `strategy-worker`

Brief salvo em `.claude/state/brief-T3.74f-sharding-do-worker.md`. Perfil ao vivo na VPS
(`hunter-vps`), somente leitura (`docker stats`/`redis-cli`/`psql` em transação `read only`),
nenhum contêiner tocado, nenhum reinício, nenhum `git pull`, nenhum parâmetro de versão viva
tocado. Sharding implementado e testado localmente (unit + testcontainer + benchmark), **não
implantado na VPS** (regra do brief). Horários em Brasília (UTC−3) com o UTC ao lado; hoje é
2026-09-10.

## 0. Resumo executivo

O gargalo não é o pool de conexões nem o Postgres — é CPU de um processo Python só. Medido ao
vivo em dois fechamentos reais (16:45 BRT/19:45Z e 17:00 BRT/20:00Z): `hunter-strategy-worker-1`
ficou preso em 97-100 % de **um** núcleo pelos 36-70 s inteiros que cada rajada levou para
drenar, enquanto `hunter-postgres-1` ficou em 20-25 % dos seus 12 núcleos no mesmo intervalo e
`pg_stat_activity` no pico mostrou a maioria dos backends esperando o **cliente** (este mesmo
processo), não executando nada. `decision_lag_p50_s`/`_p95_s` no heartbeat: 49,2/61,1 — pior que
a leitura mais cedo hoje (27,1/37,8, com menos amostra) e muito acima do alvo (mediana < 5 s,
p95 < 20 s). Um processo `asyncio` não gasta mais que um núcleo de CPU não importa quantas
corrotinas estejam "concorrentes" (GIL); `worker_concurrency` além do ponto em que o trabalho
agregado é limitado por CPU deixa de comprar vazão — provado em bancada (`test_shard_cpu_
benchmark.py`, sem Docker): concorrência 32 sobre carga presa à CPU não move o tempo de parede
(~1,0x), 4 processos reais batem a mesma carga em ~2,2-3,8x menos tempo. **Correção**:
`STRATEGY_SHARDS=N`, mesma fatia `crc32(symbol) % N` do coletor (`hunter_core.sharding`,
reaproveitada — nunca rederivada), cada shard com grupo consumidor e heartbeat próprios. Provado
com testcontainer (`test_shard_dispatch_equivalence.py`): duas topologias de grupo sobre o mesmo
stream produzem o mesmo conjunto de decisões, byte a byte, nenhuma duplicata.

---

## 1. O perfil da rajada

### 1.1 Linha de base, antes da rajada de 19:45Z (19:36:07Z / 16:36:07 BRT)

```
$ timeout 60 ssh hunter-vps "docker exec hunter-strategy-worker-1 python -c \"import urllib.request; \
  print(urllib.request.urlopen('http://localhost:8001/metrics').read().decode())\""
```
`hunter_shadow_stage_seconds` acumulado desde o boot do processo (~19:06Z, T3.74e implantado):
`queue_wait` count=6525 sum=22839,22; `market_lookup` count=400 sum=228,35 (média 0,16 s);
`family_preload` count=400 sum=284,31 (média 0,22 s); `context_load` count=3600 sum=1953,94
(média 0,13 s); `evaluate` count=3600 sum=23,54; `persist` count=5 sum=2,55 (média 0,14 s).
`hunter_shadow_decision_lag_seconds`: count=5 sum=154,02 (média 30,8 s).

### 1.2 A rajada de 19:45Z (15m/30m), capturada ao vivo (`docker stats` a cada ~7 s por 90 s)

```
$ timeout 130 ssh hunter-vps "bash -s" < burst_1945.sh   # loop local, comando abaixo
```
```bash
END=$(( $(date +%s) + 90 ))
while [ "$(date +%s)" -lt "$END" ]; do
  echo "== $(date -u +%H:%M:%S) =="
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' \
    hunter-strategy-worker-1 hunter-postgres-1
  sleep 5
done
```
Saída (resumida — série completa é maior, isto são os extremos e o padrão):
```
19:45:40  strategy-worker  99.29%   postgres  38.98%
19:45:47  strategy-worker  97.84%   postgres 226.84%
19:45:55  strategy-worker  99.50%   postgres  25.02%
19:46:02  strategy-worker  99.20%   postgres  22.87%
19:46:09  strategy-worker  98.41%   postgres  24.87%
19:46:16  strategy-worker  98.54%   postgres  23.06%
19:46:23  strategy-worker   0.68%   postgres   3.58%   <- rajada terminou (36-43s de pico)
19:46:30  strategy-worker   0.77%   postgres   6.90%
```
`hunter-strategy-worker-1` ficou pinado em 97-99,5 % de CPU por ~36-43 s seguidos (uma amostra a
cada ~7 s não fecha o segundo exato de início/fim); `hunter-postgres-1` (12 vCPUs) oscilou entre
22-39 %, com um pico isolado de 226,84 % (~2,3 de 12 núcleos, longe da saturação).

Métricas pós-rajada (19:47Z):
```
$ timeout 60 ssh hunter-vps "docker exec hunter-strategy-worker-1 python -c \"...\""
```
Delta desta rajada (uma passada de ~200 mercados): `market_lookup` +200, +112,13 s (média
0,56 s — 3,5x a linha de base); `family_preload` +200, +138,24 s (média 0,69 s — 3,1x);
`context_load` +1800, +989,38 s (média 0,55 s — **4,2x** a linha de base de 0,13 s);
`evaluate` +1800, +11,75 s (média 0,0065 s, inalterado); `persist` +10, +3,14 s (média 0,31 s).
Trabalho total desta rajada (soma dos deltas, sem `queue_wait`): **≈ 1255 s** — quase 4x o `≈ 325 s`
que a T3.74e mediu numa rajada equivalente.

`hb:strategy:shadow` logo depois: `decision_lag_p50_s 49.2`, `decision_lag_p95_s 61.1`,
`evaluated_bars 5400`.

### 1.3 A rajada de 20:00Z (15m/30m/60m juntos — maior), capturada com `pg_stat_activity`/`XPENDING` no meio

```
$ timeout 130 ssh hunter-vps "bash -s" < burst_2000.sh
```
```bash
END=$(( $(date +%s) + 100 )); i=0
while [ "$(date +%s)" -lt "$END" ]; do
  echo "== $(date -u +%H:%M:%S) =="
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' \
    hunter-strategy-worker-1 hunter-postgres-1
  i=$((i+1))
  if [ "$i" -eq 8 ]; then
    echo "-- pg_stat_activity mid-burst --"
    docker exec hunter-postgres-1 psql -U hunter -d hunter -t -c \
      "select state, wait_event_type, wait_event, count(*) from pg_stat_activity \
       where pid <> pg_backend_pid() group by 1,2,3 order by 4 desc;"
    echo "-- redis stream pending mid-burst --"
    docker exec hunter-redis-1 redis-cli XPENDING market.candles.closed strategy-worker.shadow
  fi
  sleep 5
done
```
Saída:
```
19:59:35  strategy-worker  0.65%   postgres  4.77%   <- antes da rajada
19:59:42  strategy-worker  0.66%   postgres  9.85%
19:59:49  strategy-worker 31.06%   postgres  2.80%
19:59:56  strategy-worker  0.92%   postgres  7.89%
20:00:03  strategy-worker 97.22%   postgres 156.04%  <- rajada começou
20:00:10  strategy-worker 99.33%   postgres 123.53%
20:00:17  strategy-worker 97.84%   postgres 260.79%
20:00:24  strategy-worker 99.61%   postgres  50.35%
-- pg_stat_activity (20:00:24, ~21s dentro da rajada) --
 idle                | Client   | ClientRead           | 37
 active              | Client   | ClientRead           | 17
 idle in transaction  | Client   | ClientRead           | 14
                      | Activity | BgWriterMain         |  1
                      | Timeout  | CheckpointWriteDelay |  1
 active               |          |                      |  1   <- só ESTE executava algo de fato
                      | Activity | AutoVacuumMain       |  1
                      | Activity | LogicalLauncherMain  |  1
                      | Activity | WalWriterMain        |  1
-- redis stream pending (mesmo instante) --
39
1789070400395-0
1789070400583-0
strategy-worker@02c41815f3b6:1
39
20:00:32  strategy-worker  99.93%   postgres 28.46%
20:00:39  strategy-worker 100.02%  postgres 16.27%
20:00:46  strategy-worker 100.64%  postgres 19.74%
20:00:53  strategy-worker  98.51%  postgres 29.56%
20:01:00  strategy-worker  99.55%  postgres 83.92%
20:01:07  strategy-worker  99.67%  postgres 15.77%
20:01:14  strategy-worker  99.16%  postgres 247.69%  <- ainda em rajada ao fim da captura de 100s
```
`hunter-strategy-worker-1` ficou em 97-100,6 % de CPU pelos **100 s inteiros** da captura (a
rajada de hora cheia — 15/30/60 min compartilhados — é maior que a de 19:45Z), enquanto
`hunter-postgres-1` variou 15,8-260,8 % (picos curtos, nunca perto de 1200 % = 12 núcleos).
`pg_stat_activity` no pico: **17 backends `active` + 14 `idle in transaction`, todos esperando o
cliente** (`wait_event_type=Client`), contra **1 único backend** de fato executando algo — a
prova mais direta de que o Postgres tinha trabalho pronto e estava esperando o processo Python
(saturado) vir buscá-lo, não o contrário. `XPENDING` mostrava 39 entradas pendentes no grupo
consumidor no mesmo instante.

Métricas pós-rajada (20:02:20Z):
```
$ timeout 60 ssh hunter-vps "docker exec hunter-strategy-worker-1 python -c \"...\""
```
Delta desta rajada: `market_lookup` +186, +182,26 s (média **0,98 s** — quase o dobro da rajada
anterior); `family_preload` +186, +180,06 s (média **0,97 s**); `context_load` +1857, +1717,34 s
(média **0,93 s** — **7,2x** a linha de base de 0,13 s); `evaluate` +1857, +14,90 s (inalterado);
`persist` +0 (nenhum sinal novo persistido nesta rajada — `decision_lag_*` no heartbeat ficou
igual, 49,2/61,1, e `triggered` no `evaluations_by_state` também não mudou: 41→41). Trabalho
total desta rajada: **≈ 2095 s** — a mais pesada das duas, coerente com o pico de CPU mais
sustentado (100 s cheios vs. ~40 s).

**A leitura honesta do padrão**: o custo por estágio não é constante — ele **piora** com o
tamanho da rajada (0,13 s → 0,55 s → 0,93 s de `context_load` médio, conforme a rajada cresce de
"nenhuma" para "15/30 min" para "15/30/60 min juntos"). Isso é a assinatura de contenção de
CPU/escalonamento sob o GIL, não de Postgres ficando mais lento — o próprio `pg_stat_activity`
mostra o Postgres com folga (17+14=31 backends esperando o cliente, 1 executando) exatamente no
pico da segunda rajada.

### 1.4 `agent_signals` na janela: a rajada de 19:45Z fechou com sinais entre 42,8 s e 62,6 s

```sql
-- infra/scripts/sql/research/2026-09-10-t374f-q02-signals-per-bar.sql
```
```
$ timeout 90 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t374f-q02-signals-per-bar.sql
```
10 sinais da barra `observation_ts = 2026-09-10 18:45:00Z`(*): SKYUSDT 62,55 s; PHAROSUSDT (×7)
42,76-60,25 s; ETHUSDT 49,73 s. Espalhamento mais estreito que o da T3.74e (4,9-61,2 s) mas
uniformemente alto — coerente com a leitura de §1.3: quando o teto é CPU, não é só a posição na
fila do despachante que importa, é o processo inteiro ficando mais lento por contenção.

(*) horário em UTC na tabela; 18:45:00Z = 15:45 BRT — a query rodou às 19:48Z (16:48 BRT), pouco
depois do fim da rajada de 19:45Z.

A rajada de 20:00Z (17:00 BRT) não produziu nenhum sinal novo (0 `triggered` novos) — não há
linha de `agent_signals` para comparar dessa janela; o achado de CPU não depende disso, vem de
`docker stats`/`pg_stat_activity`/`hunter_shadow_stage_seconds`, que são medidos independente de
haver ou não um sinal disparado.

### 1.5 Conclusão do perfil (item 1 do brief)

**O limite é CPU de um processo Python só (GIL), não Postgres, não o pool de conexões.**
Evidência convergente: (a) `hunter-strategy-worker-1` fica pinado em ~99-100 % de **um** núcleo
pela duração inteira de cada rajada real medida (36-100 s), enquanto `hunter-postgres-1` (12
núcleos) nunca passa de ~26 % de uso sustentado (picos curtos e isolados a 150-260 %, ~1,3-2,3
núcleos, não perto da saturação); (b) `pg_stat_activity` no pico da rajada maior mostra a
esmagadora maioria dos backends (31 de 32) esperando o **cliente**, não executando nada — o
Postgres está pronto e ocioso, esperando o processo Python vir buscar o próximo resultado; (c) o
custo médio por estágio (inclusive `context_load`, que é I/O contra o Postgres) **cresce** com o
tamanho da rajada (0,13 s → 0,55 s → 0,93 s), o oposto do que se esperaria se o gargalo fosse o
banco ficando mais devagar sob mais conexões simultâneas — é o padrão de um único núcleo de CPU
dividido entre cada vez mais trabalho pronto para rodar. Item 3 do brief (janela rolante em
memória por família/mercado) **não se aplica**: essa mudança ataca carga do Postgres, e o
Postgres tem folga de sobra.

---

## 2. A correção — sharding do `strategy-worker` por processo (item 2 do brief)

**`packages/core/hunter_core/sharding.py` (novo)**: `crc32_shard`/`owns`/`parse_shard_spec` — a
mesma fórmula `crc32(symbol) % N` que `hunter_market_worker.universe.shard_symbols` sempre usou,
movida para `hunter_core` e reimportada por `universe.py`/`backfill.py` (comportamento idêntico,
provado pelos testes de sharding do coletor continuando verdes) para que o `strategy-worker`
reaproveite a **mesma** função, nunca uma rederivação com chance de divergir.

**`packages/core/hunter_core/settings.py`**: novo campo `strategy_shard: str = "0/1"`
(`STRATEGY_SHARD`), mesmo formato e validação de `market_shard` (`_parse_shard` generalizado,
compartilhado entre os dois via `parse_shard_spec`), com `strategy_shard_index`/
`strategy_shard_total`.

**`services/strategy-worker/hunter_strategy_worker/shard.py` (novo)**: `owns_market` (a fatia,
por símbolo puro — não `exchange:symbol:market_type`, porque o Lab só decide sobre o perpétuo e
hoje só existe uma exchange, então a fatia por símbolo é idêntica à do coletor), `consumer_group`
e `heartbeat_key` — os dois últimos movidos de `config.py` para cá quando adicioná-los ali
estourou o orçamento de 350 linhas (mesma responsabilidade — "topologia de shard" —, então a
extração não é um recorte arbitrário).

**Topologia de consumo escolhida: um grupo consumidor por shard sobre o stream inteiro** (não um
grupo compartilhado). `strategy-worker.shadow.{i}of{N}`, mesma forma que
`hunter_market_worker.backfill.BackfillConsumer.group` já usa para "stream compartilhado, dono
fatiado" — `owns()` refuta (mesmo padrão) um pedido de outro dono. Um grupo único compartilhado
entre shards **não funcionaria**: o Redis entrega cada entrada nova a qualquer consumidor do
grupo que chamar `XREADGROUP` primeiro, não ao shard dono do símbolo — perderia barras em
silêncio em vez de garantir uma avaliação por barra. Cada shard não-dono confirma (`ack`) sem
avaliar, contado por nome (`hunter_shadow_bars_skipped_total{reason="not_my_shard"}`) —
`consumer.py::run_consumer`, checado **antes** do despachante ou de qualquer cronômetro de
estágio. Ordenação por mercado preservada: um mercado pertence a exatamente um shard, então toda
barra dele passa pelo mesmo `BarDispatcher` (T3.74c), que já serializa por mercado.

**`consumer.py`**: `run_consumer` ganha `shard_index`/`shard_total` (padrão `0`/`1`, comportamento
de hoje inalterado) e um parâmetro `clock` (encaminhado a `handle_candle`, que já o tinha) — costura
de teste que permite ao testcontainer de equivalência rodar o consumidor real contra barras com
carimbo fixo sem que cada uma leia como atrasada em horas/anos.

**`heartbeat.py`**: `write_heartbeat`/`run_heartbeat` ganham `shard_index`/`shard_total`; a chave
vira `hb:strategy:shadow:{i}of{N}` (`hb:strategy:shadow` sem sufixo com `shard_total<=1`), mesma
convenção de `hunter_market_worker.heartbeat.hb_key`. A varredura genérica de
`/api/v1/system/workers` (`parse_heartbeat_key`, que separa `role`/`instance` no primeiro `:`)
já mostra uma linha por shard sem nenhuma mudança de código. `open_trackings` (contagem não
particionada por mercado) só é consultado pelo shard 0 — os outros reportam vazio, evitando N
cópias da mesma consulta de até 10 000 linhas a cada 10 s.

**`outcome_sweep.py`**: `run_outcomes` só varre de verdade no shard 0 (`sweep_outcomes` não é
particionado por mercado — avança qualquer tracking aberto, não só os do shard que o decidiu);
os outros shards ficam ociosos no mesmo laço, mesma convenção de `fx`/`spot` no coletor ("uma
tarefa por cluster, não por shard", `hunter_market_worker.spot.run_spot`). O outbox
(`SKIP LOCKED`) continua rodando em todos — seguro por design, mesmo padrão do coletor.

**`main.py`**: lê `settings.strategy_shard_index`/`_total` e encaminha para `run_consumer`/
`run_heartbeat`/`run_outcomes`.

**A guarda de replay não precisou de mudança.** `replay/role_guard.py` recusa com base em
`HUNTER_ROLE == "strategy"`, que não muda entre shards (todos os `strategy-worker-{i}` rodam
`HUNTER_ROLE=strategy`) — a recusa já cobre qualquer shard automaticamente.

**Compose**: `STRATEGY_SHARD: 0/${STRATEGY_SHARDS:-1}` no serviço base `strategy-worker`
(`infra/docker/docker-compose.yml`), mais `strategy-worker-1..3` sob o perfil `strategy-shards`
(mesmo padrão de `market-worker-1..3`/perfil `shards`) — validado com `docker compose config`
(abaixo). `infra/vps/docker-compose.prod.yml` ganha os três blocos mínimos (`*prod-db-env` +
`HUNTER_ROLE`/pool), sem repetir `STRATEGY_SHARD` (herdado do `extends` da base). `compose.sh`
lê `STRATEGY_SHARDS` e ativa o perfil (só até 4 — não há `strategy-worker-4..7`/perfil
`strategy-shards8`, registrado como próximo passo se o universo crescer muito).

### 2.1 Ressalva honesta: o portão de lag do replay não foi rewireado para múltiplos shards

`replay/budget.py::LIVE_HEARTBEAT_KEY` continua um literal próprio (`"hb:strategy:shadow"`, já
independente de `config.py` antes desta tarefa) usado para checar o atraso da linha viva antes
de deixar um replay avançar. Com `STRATEGY_SHARDS > 1` essa chave solo não existe mais (cada
shard escreve a sua própria, sufixada) — o portão continuaria lendo uma chave vazia/expirada em
vez de agregar os N shards, a menos que `REPLAY_HEARTBEAT_KEY` seja apontado manualmente para um
shard (já configurável via variável de ambiente, sem mudança de código). Fora do escopo desta
tarefa (replay fica no `replay-worker`, T3.80); registrado como lacuna conhecida, não corrigido
aqui.

---

## 3. Provas locais

### 3.1 Sharding — mapeamento e recusa (unit, sem banco)

```
$ timeout 60 uv run pytest services/strategy-worker/tests/test_shard.py -q
11 passed in 2.37s

$ timeout 60 uv run pytest services/strategy-worker/tests/test_shard_topology.py -q
3 passed in 0.42s

$ timeout 60 uv run pytest services/strategy-worker/tests/test_consumer_sharding.py -q
3 passed in 1.64s

$ timeout 60 uv run pytest services/strategy-worker/tests/test_heartbeat_sharding.py -q
4 passed in 1.27s

$ timeout 60 uv run pytest services/strategy-worker/tests/test_outcome_sweep_sharding.py -q
2 passed in 1.07s
```
`test_shard.py::test_agrees_with_the_market_worker_shard_function` importa
`hunter_market_worker.shard_symbols` só para provar, para 200 símbolos sintéticos (incluindo os
quatro símbolos reais não-ASCII que o T1.6b-C2 mediu quebrando um `s.encode("ascii")`), que a
fatia do `strategy-worker` bate símbolo a símbolo com a do coletor.
`test_consumer_sharding.py` prova, com `consume()` substituído (mesmo padrão de
`test_reclaim_dedup.py`): uma barra de um mercado não possuído é confirmada e nunca chega a
`handle_candle`; um deploy solo (`shard_total=1`) continua dono de tudo; a união de 4 shards
sobre 20 símbolos sintéticos cobre cada símbolo exatamente uma vez, sem sobreposição.

### 3.2 Dois shards sobre o stream real produzem as mesmas decisões, byte a byte (testcontainer)

```
$ timeout 290 uv run pytest services/strategy-worker/tests/test_shard_dispatch_equivalence.py -q -s
1 passed in 30.50s
```
6 mercados reais (`SHARDEQ0..5USDT`, um com gatilho real de `volume_anomaly_v1`), 2 versões
ativas de uma família isolada (`isolate_catalogue`), publicados **uma vez** em
`market.candles.closed` (Redis real, testcontainer). `evaluate_slot` é interceptado (não
substituído) para gravar cada `Evaluation` real numa lista por `(symbol, version)` — uma lista,
não um dicionário sobrescrito, para que "avaliado mais de uma vez" seja uma asserção de verdade,
não um acidente de semântica de dicionário. Passada 1: um `run_consumer` sem shard
(`shard_total=1`, grupo `strategy-worker.shadow`) até as 12 chaves esperadas (6 mercados × 2
versões) aparecerem. Passada 2: dois `run_consumer` concorrentes (`shard_index=0/1`,
`shard_total=2`, grupos `strategy-worker.shadow.{0,1}of2`) contra o **mesmo** stream, sem
republicar nada — grupos novos começam em `id="0"` (`ensure_group`), então enxergam as mesmas 6
entradas publicadas na passada 1. Resultado: as 12 chaves batem estado/motivo/decisão byte a
byte entre as duas passadas, cada uma avaliada **exatamente uma vez** em cada passada (nenhuma
lista com mais de 1 item), e o mercado com gatilho real produziu `triggered` nas duas — visível
no log: `shadow_signal_emitted symbol=SHARDEQ2USDT` uma vez por passada, com
`shadow_bar_behind_barrier` na segunda tentativa de persistir o mesmo slot (esperado — a
barreira já tinha avançado na passada 1).

Adição de produção necessária para esta prova (documentada em `consumer.py`): `run_consumer`
ganhou um parâmetro `clock` opcional (padrão `utcnow`, comportamento real inalterado) —
encaminhado a `handle_candle`, que já o tinha — porque sem ele o teste teria que rodar com o
relógio de parede real e um `bar_close` preso a 2026-09-10 11:00 UTC teria lido como horas
atrasado (`late_delay_backlog_max_s`) segundo o horário real de execução do teste.

### 3.3 Bancada: CPU real de processos vs. concorrência em um processo só

```
$ timeout 120 uv run pytest services/strategy-worker/tests/test_shard_cpu_benchmark.py -q -s
1 processo: 2,08s (1059 bars/s); 4 shards: 0,58s (3770 bars/s); speedup=3,56x
concorrência=1: 1,82s; concorrência=32: 1,67s; ratio=1,09
2 passed in 8.44s
```
Rodado 3 vezes para checar estabilidade (máquina local de 22 núcleos):
```
speedup=2.16x / 2.55x / 3.56x   (todas > 1,8x, o limiar da asserção)
ratio (concorrência 32 vs. 1) = 0.97 / 1.05 / 1.09   (banda aceita: 0,6-1,5x — "quase nada")
```
11 × 200 (2200 avaliações, forma medida do T3.74) com um custo por avaliação deliberadamente
**preso à CPU** (laço aritmético puro, não `asyncio.sleep` — o oposto do que
`test_dispatch.py::TestThroughputAtTheMeasuredShape` já usa para provar o caso I/O-bound, onde
concorrência dentro de um processo ajuda de verdade). `TestRealProcessesBeatOneProcessOnCPUBoundWork`
usa `ProcessPoolExecutor(max_workers=4)`, com um aquecimento (`pool.map` de trabalho zero) fora
do cronômetro — um shard de produção é um contêiner de vida longa, não gerado por rajada, então
o número que importa é a vazão de regime permanente, não a latência de `spawn` do Windows/CI.
`TestAsyncioConcurrencyAloneDoesNotHelpCPUBoundWork` roda a mesma carga através do
`BarDispatcher` real (`concurrency=1` vs. `32`) **no mesmo processo** — sem ganho, a prova direta
de que subir `worker_concurrency` de novo não teria ajudado a rajada real.

### 3.4 Regressão — suíte completa

```
$ timeout 200 uv run pytest services/strategy-worker/tests -q -m unit
409 passed, 378 deselected in ~20s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_shadow_decisions.py -q
15 passed in 92.25s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_spot_not_in_shadow_universe.py -q
6 passed in 20.27s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_dispatch_benchmark.py -q
2 passed in 69.18s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_replay_reproduce.py \
  services/strategy-worker/tests/test_shadow_outcomes.py -q
22 passed in 144.79s

$ timeout 120 uv run pytest services/market-worker/tests/test_universe_sharding.py \
  services/market-worker/tests/test_backfill_consumer.py packages/core/tests/unit/test_settings.py -q
85 passed in 59.38s

$ timeout 60 uv run pytest apps/api/tests/unit/test_system_latency.py -q
9 passed in 0.39s

$ timeout 120 uv run pytest apps/api/tests/unit -q
595 passed in 68.51s
```
Nenhuma suíte pré-existente quebrou. O refactor de `zlib.crc32` em `universe.py`/`backfill.py`
(delegando para `hunter_core.sharding`) não muda nenhum resultado — provado pelas próprias
suítes de sharding do coletor continuando verdes.

### 3.5 Qualidade

```
$ uv run ruff check services/strategy-worker/ packages/core/hunter_core/sharding.py \
  packages/core/hunter_core/settings.py services/market-worker/hunter_market_worker/universe.py \
  services/market-worker/hunter_market_worker/backfill.py apps/api/hunter_api/services/latency.py \
  apps/api/tests/unit/test_system_latency.py
All checks passed!

$ uv run ruff format <mesmos arquivos>
(todos formatados; nenhuma mudança de comportamento)

$ uv run pyright services/strategy-worker packages/core/hunter_core/sharding.py \
  packages/core/hunter_core/settings.py services/market-worker/hunter_market_worker/universe.py \
  services/market-worker/hunter_market_worker/backfill.py
6 errors, 0 warnings, 0 informations
  (pré-existentes, nenhum meu, confirmado por git status --porcelain mostrando esses 3 arquivos
   de teste sem modificação: test_replay_drain_pause.py:91, test_replay_role_guard.py:59/77/90,
   test_replay_stress.py:35 (dois) — reportPrivateUsage sobre símbolos privados de outro módulo
   por convenção, aceito desde T3.73/74/74b/74c/74e. Nota: a contagem de "3 erros" nas notas
   anteriores não incluía test_replay_role_guard.py — recontado aqui, não é regressão minha)

$ uv run pyright apps/api/hunter_api/services/latency.py apps/api/tests/unit/test_system_latency.py
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 622 files; 0 over budget, 0 grandfathered
  (settings.py chegou a 388/350 e config.py a 385/350 nas primeiras versões — settings.py:
   função de parsing movida para hunter_core/sharding.py, docstrings enxugadas, chamadas
   diretas a parse_shard_spec em vez de wrappers locais, 349 linhas finais; config.py:
   consumer_group/heartbeat_key movidos para shard.py — mesma responsabilidade, "topologia de
   shard" —, 349 linhas finais)
```

Validação de compose (sem subir nada, `docker compose config`, máquina local — não a VPS):
```
$ HUNTER_WS_URL=ws://x HUNTER_PUBLIC_URL=http://x STRATEGY_SHARDS=4 timeout 30 docker compose \
  -f infra/docker/docker-compose.yml --profile strategy-shards config \
  strategy-worker strategy-worker-1 strategy-worker-2 strategy-worker-3 \
  | grep STRATEGY_SHARD
      STRATEGY_SHARD: 0/4
      STRATEGY_SHARD: 1/4
      STRATEGY_SHARD: 2/4
      STRATEGY_SHARD: 3/4

$ POSTGRES_PASSWORD=x HUNTER_WS_URL=ws://x HUNTER_PUBLIC_URL=http://x HUNTER_SITE_ADDRESS=:80 \
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=x STRATEGY_SHARDS=4 timeout 30 docker compose \
  -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml \
  --profile strategy-shards config strategy-worker strategy-worker-1..3 \
  | grep -E 'STRATEGY_SHARD:|HUNTER_ROLE:|DATABASE_URL:'
(4 blocos strategy-worker* com HUNTER_ROLE=strategy, STRATEGY_SHARD 0/4..3/4,
 DATABASE_URL usando a credencial de produção do .env simulado)
```

---

## 4. Ressalvas honestas

1. **Nada implantado na VPS** (regra do brief): o número "depois" ao vivo (drenagem por shard)
   depende do deploy do orquestrador e de uma nova leitura de `hb:strategy:shadow:{i}of{N}` +
   `agent_signals` numa janela pós-deploy limpa.
2. **`replay/budget.py`'s portão de atraso da linha viva não foi rewireado para múltiplos
   shards** (§2.1) — fora do escopo desta tarefa, `REPLAY_HEARTBEAT_KEY` já permite apontar
   manualmente para um shard se necessário.
3. **`STRATEGY_SHARDS` só sobe até 4** (`strategy-worker-1..3` declarados no compose); um
   universo bem maior que os ~200 mercados de hoje pediria um perfil `strategy-shards8` análogo
   ao do coletor, não criado aqui.
4. **O benchmark de CPU (`test_shard_cpu_benchmark.py`) é sintético** (laço aritmético, não
   `Decimal`/estratégia real) — mede a forma do problema (CPU-bound vs. I/O-bound), não o custo
   exato de um `handle_candle` real. O testcontainer de equivalência (§3.2) é o que prova
   correção contra decisões reais; nenhum dos dois mede vazão real de decisões/s contra Postgres
   em 4 processos simultâneos (levaria a maior parte de uma hora nesta forma, mesma razão que
   `test_dispatch_benchmark.py` já registra para não rodar 2200 avaliações reais).
5. **`sweep_outcomes`/`open_trackings` só no shard 0**: se o shard 0 cair, a varredura de
   outcomes para junto com ele até o container reiniciar — mesmo risco que `fx`/`spot` já
   aceitam no coletor para uma tarefa por cluster; não é um regressão desta tarefa, é a mesma
   troca já feita alhures.
6. **A rajada de 20:00Z não produziu nenhum sinal novo** (0 `triggered`) — o achado de CPU não
   depende disso (vem de `docker stats`/`pg_stat_activity`/`hunter_shadow_stage_seconds`), mas
   não há uma segunda linha de `agent_signals` para comparar o espalhamento dessa janela como a
   §1.4 fez para 19:45Z.
7. **A contagem "3 erros" de pyright nas notas do T3.74c/d/e não incluía `test_replay_role_guard.py`**
   (3 erros ali, pré-existentes) — recontado aqui como 6 no total; nenhum é meu, confirmado por
   `git status --porcelain` desses três arquivos não aparecerem modificados.

---

## 5. Arquivos (git status --porcelain — só os meus)

```
 M apps/api/hunter_api/services/latency.py
 M apps/api/tests/unit/test_system_latency.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M docs/PIPELINE.md
 M infra/docker/docker-compose.yml
 M infra/vps/compose.sh
 M infra/vps/docker-compose.prod.yml
 M "obsidian/07-BUGS/Open Bugs.md"
 M packages/core/hunter_core/settings.py
 M services/market-worker/hunter_market_worker/backfill.py
 M services/market-worker/hunter_market_worker/universe.py
 M services/strategy-worker/hunter_strategy_worker/config.py
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/heartbeat.py
 M services/strategy-worker/hunter_strategy_worker/main.py
 M services/strategy-worker/hunter_strategy_worker/outcome_sweep.py
?? .claude/state/brief-T3.74f-sharding-do-worker.md
?? .claude/state/notes-T3.74f.md
?? infra/scripts/sql/research/2026-09-10-t374f-q01-pg-stat-activity-peak.sql
?? infra/scripts/sql/research/2026-09-10-t374f-q02-signals-per-bar.sql
?? packages/core/hunter_core/sharding.py
?? services/strategy-worker/hunter_strategy_worker/shard.py
?? services/strategy-worker/tests/test_consumer_sharding.py
?? services/strategy-worker/tests/test_heartbeat_sharding.py
?? services/strategy-worker/tests/test_outcome_sweep_sharding.py
?? services/strategy-worker/tests/test_shard.py
?? services/strategy-worker/tests/test_shard_cpu_benchmark.py
?? services/strategy-worker/tests/test_shard_dispatch_equivalence.py
?? services/strategy-worker/tests/test_shard_topology.py
```

**Não tocados por mim, apesar de aparecerem no `git status` da árvore compartilhada** (outras
frentes ativas hoje): `.claude/launch.json`, `docs/DESIGN.md`,
`infra/scripts/tests/test_seed_dry_run.py`,
`packages/core/tests/integration/test_schema_seed_and_partitions.py`, `tests/e2e/design-audit.*`,
e tudo sob `.claude/state/design/2026-09-08/**`, `.claude/state/exp-drafts/**`,
`.claude/state/tmp/**`, `.claude/state/t346/**`, `.claude/state/astra-*` não listados acima.

## 6. Próximo passo

Deploy pelo orquestrador (`STRATEGY_SHARDS=4 bash infra/vps/compose.sh update`); depois, reler
`hb:strategy:shadow:{i}of4` (`decision_lag_p50_s`/`_p95_s` por shard) e `XINFO GROUPS
market.candles.closed` (4 grupos `strategy-worker.shadow.{i}of4`, `pending` baixo em cada) numa
janela pós-deploy limpa. Se `decision_lag_p95_s` continuar acima de 30 s mesmo com 4 shards, o
próximo corte é rever `EXPECTED_BAR_COST_S`/o roster de versões ativas (mais shards, ou revisar
se alguma versão específica está cara demais por avaliação) — não mais concorrência dentro de um
processo, que este perfil já mostrou não ajudar.
