# T3.74c — a entrada tem que ser instantânea: onde os segundos estavam e o dispatch concorrente

**Escopo:** medição somente leitura na VPS (`hunter-vps`, `hunter-postgres-1`/`hunter-redis-1`/
`hunter-strategy-worker-1`), toda consulta SQL em `begin transaction isolation level repeatable
read read only; … commit;`, todo comando com `timeout` explícito em primeiro plano. **Nenhuma
escrita na VPS. Nenhum reinício/recriação de contêiner. Nenhum `git pull` na VPS. Nenhum parâmetro
de versão viva tocado. Nenhum commit.** Leitura de referência: **2026-09-10 15:01–15:04Z = 12:01–
12:04 BRT**. Horários em Brasília (UTC−3) com o UTC ao lado.

---

## 1. Onde os segundos estavam

### 1.1 Confirmação: nenhum replay concorrente durante a medição

```bash
$ timeout 90 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t374c-q02-replay-hoje.sql
```
`replay_runs` mostra um lote (T3.76) de 02:26Z a 04:28Z (mean_reversion v10/v1/v2, 4 mercados, 3
workers, fatias de ~3 min encadeadas) e **nenhuma linha entre 04:28Z e 15:28Z** — a leitura ao vivo
desta tarefa (15:01–15:04Z) caiu exatamente nesse vão. A próxima fatia (v15) só começou às 15:28Z,
27 minutos depois da minha amostra. **A linha viva sozinha, sem replay, já produzia o sintoma.**

### 1.2 O worker não conseguia nem ler a próxima vela

```bash
$ timeout 120 ssh hunter-vps "docker exec hunter-redis-1 redis-cli XINFO GROUPS market.candles.closed; \
  docker exec hunter-redis-1 redis-cli XPENDING market.candles.closed strategy-worker.shadow; \
  docker exec hunter-redis-1 redis-cli HGETALL hb:strategy:shadow"
```
```
strategy-worker.shadow  consumers=55  pending=9  lag=303   (15:01:48Z)
hb:strategy:shadow: outbox_lag_s=0.0  evaluated_bars=79870  errors=0
  evaluations_by_state: not_triggered=59527 ineligible=6582 unavailable=13321 triggered=440
```
`lag=303` no próprio grupo consumidor — o worker está **303 entradas atrás** do stream, não apenas
lento para decidir. Reconferido 8s/16s/24s depois: `pending` caiu a 0, mas o `lag` já tinha sido
visto crescer em outras janelas do dia (T3.74b já documentava isso oscilando).

### 1.3 O processo estava saturado — em rajada, não continuamente

```bash
$ timeout 120 ssh hunter-vps "docker stats --no-stream"
hunter-strategy-worker-1   92.72%   105.4MiB   (PIDs=2)
hunter-postgres-1          87.84%   592.3MiB
hunter-redis-1            129.09%   13.06GiB
```
```bash
$ timeout 90 ssh hunter-vps "docker top hunter-strategy-worker-1; \
  docker exec hunter-strategy-worker-1 sh -c 'cat /proc/loadavg; nproc'"
python -m hunter_strategy_worker   C=16   (amostra alguns segundos depois)
loadavg 6.96 6.43 5.79 (host)  nproc=12
```
A CPU do worker é em rajada (92,7 % num instante, 16 % pouco depois) — coerente com **~200
mercados perpétuos fechando o candle de 1 min quase juntos a cada minuto** e um processo Python
asyncio de um núcleo só processando essa rajada em série.

### 1.4 `pg_stat_activity` no instante da amostra: calmo (a pressão é em rajada, não constante)

```bash
$ timeout 90 ssh hunter-vps "docker exec hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 \
  -c \"select state, wait_event_type, wait_event, count(*) from pg_stat_activity \
       where pid <> pg_backend_pid() group by 1,2,3 order by count(*) desc;\""
idle/ClientRead: 39   active: 1   (Activity: AutoVacuum/BgWriter/WalWriter/Checkpointer/LogicalLauncher: 1 cada)
```
`pg_stat_statements` **não está instalado** (`select extname from pg_extension` só lista
`plpgsql`) — item 3 do brief T3.74b (devops-engineer) segue pendente, fora do meu papel.

### 1.5 A série do dia confirma: sem tendência de melhora com o cache de contexto sozinho

```bash
$ timeout 90 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t374c-q01-lag-recente.sql
```
| hora UTC | sinais | mediana s | p95 s | máx s |
|---|---|---|---|---|
| 00:00 | 37 | 125,4 | 209,9 | 210,1 |
| 05:00 | 29 | 97,9 | 184,8 | 185,0 |
| 07:00 | 18 | 37,7 | 109,3 | 121,6 |
| 08:00 | 36 | 24,7 | 78,8 | 125,6 |
| 09:00 | 10 | 59,5 | 87,1 | 89,4 |
| 10:00 | 26 | 46,1 | 131,6 | 137,3 |
| 11:00 | 30 | 21,4 | 84,4 | 106,2 |
| 12:00 | 57 | 26,1 | 81,3 | 104,0 |
| 13:00 | 35 | 45,3 | 98,2 | 128,1 |
| 14:00 | 42 | 57,7 | 140,5 | 165,7 |
| 15:00 (parcial, corta às ~15:04Z) | 21 | 89,7 | 171,5 | 171,5 |

O deploy do T3.74b (cache de contexto por família, 10:25Z) não produz uma queda visível e sustentada
— consistente com o próprio benchmark local do T3.74b (~9,5 % de ganho de relógio, a maior parte do
custo em outro lugar). A causa dominante é a que 1.2/1.3 mostram: **dispatch serial contra uma
rajada**, não o número de leituras de candle por si.

### 1.6 O orçamento por barra, escrito

Com 11 versões ativas sobre ~200 mercados perpétuos monitorados e fechamentos de 1 min quase
simultâneos: se cada `handle_candle` leva `t` segundos de ponta a ponta (fila→mercado→família→N
versões→persistência) e o processo trata **um por vez**, uma rajada de ~200 mercados custa `~200 ×
t` segundos de fila — e é exatamente essa fila que o SQL mede como "atraso decisão-menos-barra"
crescendo dentro do próprio minuto (T3.74b §1.3: uma barra lógica com sinais entre 36,7 s e 185,0 s
de atraso). Reduzir `t` (T3.74b) ajuda; processar vários `t` **ao mesmo tempo** ataca o `× 200`
diretamente — essa é a maior alavanca, e é a corrigida nesta tarefa.

---

## 2. A correção: dispatch concorrente por mercado, serial dentro do mesmo mercado

**Novo módulo** `services/strategy-worker/hunter_strategy_worker/dispatch.py` — `BarDispatcher`:
processa mercados diferentes em paralelo (semáforo, `ShadowConfig.worker_concurrency`, padrão 8,
dimensionado contra o pool de conexões do processo — `db_pool_size + db_max_overflow` = 5+5=10
hoje) e serializa qualquer barra do **mesmo** mercado com um `asyncio.Lock` por
`exchange:symbol:market_type` (`market_key`). O semáforo é adquirido **antes** de criar a tarefa em
segundo plano, então um dispatcher cheio aplica contrapressão no próprio leitor do stream
(`run_consumer`), em vez de crescer uma fila sem limite.

`consumer.py::run_consumer` foi reescrito para usar o dispatcher: o laço de leitura só bloqueia no
semáforo, nunca no processamento de uma barra específica; a confirmação (`ack`) e a contagem de
sucesso/erro (`runtime.mark_success`/`mark_error`) continuam por mensagem, dentro do fechamento
`_handle_and_ack`, com o mesmo contrato de isolamento de falha que já existia (uma mensagem ruim não
trava as outras). No fim de cada corte de stream (e antes do backoff), `await dispatcher.drain()`
espera todo trabalho já aceito terminar; `cancel_all()` cancela e junta tudo no `CancelledError`.

**Nada tocado**: nenhum parâmetro de versão, nenhum dos sete módulos do fecho de `code_ref`
(`packages/core/hunter_core/strategies/**`), nenhum gate de elegibilidade — `gate_policy.py`,
`regime_gate.py`, `hours_gate.py`, `variant.py`, `catalogue.py` não foram abertos (são do T3.77,
que está em execução na mesma árvore hoje — confirmado por `git status --porcelain` mostrando esses
arquivos e `funding.py`/`record.py` já modificados por outra tarefa antes desta começar). `context.py`
não foi tocado.

### 2.1 A válvula de segurança (item d do brief), não a correção

`ShadowConfig.late_delay_backlog_max_s` (padrão 120 s, `SHADOW_LATE_DELAY_BACKLOG_MAX_S`): checado
uma vez por **barra**, em `handle_candle`, antes de `versions_for_bar`/`load_market`/
`load_family_readers` — qualquer coisa por versão. Uma barra já mais velha que isso quando chega ao
worker seria, avaliada por completo, quase sempre `no_entry: late:delay` de qualquer forma (o
`max_entry_delay_s` congelado por versão em `plan.py` está tipicamente perto disso); durante uma
fila real, pagar o custo cheio só para chegar à mesma conclusão mais devagar é o que compõe o
atraso até os 300 s do portão de elegibilidade (`eligibility_max_lag_s`, que continua existindo,
intocado, para o caso de uma barra passar da válvula e ainda assim envelhecer durante a avaliação).
Contada por nome, nunca silenciosa: `hunter_shadow_bars_skipped_total{reason="late_delay_backlog"}`.
Este número é **independente** do gate de 300 s e não o substitui.

### 2.2 Instrumentação nova (item 1 do brief)

`metrics.py`: `hunter_shadow_stage_seconds{stage}` (histogram; stages: `queue_wait`, `market_lookup`,
`family_preload`, `context_load`, `evaluate`, `persist`) e `hunter_shadow_decision_lag_seconds`
(histogram, observado uma vez por sinal persistido, `decision_at - bar_close` — o gêmeo em processo
do que a query SQL mede em `agent_signals`). Como este worker não roda um servidor Prometheus para
tirar `histogram_quantile`, um reservatório de amostras em memória (últimas 500, `deque`) alimenta
`decision_lag_percentiles()`, exposto direto em `hb:strategy:shadow` como `decision_lag_p50_s`/
`decision_lag_p95_s` — lido com `HGETALL`, sem infraestrutura extra.

Pontos instrumentados: `consumer.py` (`queue_wait` no laço de leitura, a partir de `envelope.ts`;
`market_lookup` e `family_preload` em volta das duas chamadas de banco antes do laço de versões);
`decide.py` (`context_load` em volta de `build_market_context`; `evaluate` em volta de
`strategy.explain`; `persist` em volta de `persist_decision`; `observe_decision_lag` no momento em
que um sinal é de fato escrito).

**Ressalva honesta**: esta instrumentação não foi implantada na VPS por este agente — as leituras
de `hb:strategy:shadow` em 1.2 são do código de antes desta tarefa (sem os campos
`decision_lag_p50_s`/`p95_s` ainda). O "antes" desta tarefa é o SQL contra `agent_signals`; o "depois"
ao vivo, incluindo a nova instrumentação, é do próximo deploy do orquestrador.

---

## 3. Provas locais

### 3.1 Vazão sintética na forma medida (11 × 200, sem banco)

```bash
$ timeout 120 uv run pytest services/strategy-worker/tests/test_dispatch.py -q
..........
10 passed in 4.84s
```
`TestThroughputAtTheMeasuredShape` (11 versões-equivalente × 200 mercados, custo simulado por barra
de 10 ms, concorrência 8 vs. serial): mais de 4× de ganho de vazão (metade do fator teórico de 8×,
de propósito — a asserção é conservadora contra ruído de agendamento do asyncio numa máquina
carregada, e ainda assim muito acima do ~9,5 % que o cache de contexto sozinho mediu no T3.74b).
Também prova: no máximo `concurrency` manipuladores em voo ao mesmo tempo; duas barras do mesmo
mercado nunca se sobrepõem e sempre rodam na ordem de submissão; mercados diferentes rodam
concorrentemente de verdade; `cancel_all()` cancela o que está em voo.

**Por que 11 × 200 sintético, não 2200 avaliações reais contra Postgres**: no ritmo medido pelo
T3.74b (~1,4–1,5 avaliações/s), 2200 avaliações reais levariam a maior parte de meia hora **por
passada** — não é um teste, e não mede o dispatcher, mede o Postgres do container. O benchmark
sintético isola exatamente o mecanismo que esta tarefa muda.

### 3.2 Decisões byte-idênticas contra Postgres real (testcontainer, uma invocação)

```bash
$ timeout 290 uv run pytest services/strategy-worker/tests/test_dispatch_benchmark.py -q -s
.
1 passed in 46.00s
```
5 mercados (um com gatilho real de `volume_anomaly_v1`, quatro quietos), 3 versões da mesma
família, mesma `bar_close`: `evaluate_slot` é interceptado (não substituído) para gravar cada
`Evaluation` real, uma vez entregue em série (`concurrency=1`) e outra vez através do
`BarDispatcher` (`concurrency=4`). `Evaluation` é computada **antes** de qualquer lock de slot ou
persistência (`decide.py`; a mesma propriedade que `test_context_cache_engine.py::TestEquivalence`
já usa para o T3.74b), então chamar a mesma barra duas vezes nunca corrompe a comparação — só a
persistência da segunda passada vira no-op (o log mostra `shadow_bar_behind_barrier` nas repetições
da passada concorrente, exatamente o esperado). Resultado: as 15 combinações (5 mercados × 3
versões) bateram estado/motivo/decisão byte a byte entre as duas passadas, e o mercado com gatilho
real produziu `triggered` nas duas.

### 3.3 Testes novos, unitários (sem banco)

```bash
$ timeout 120 uv run pytest services/strategy-worker/tests/test_late_delay_backlog.py -q
.....
5 passed in 2.91s

$ timeout 120 uv run pytest services/strategy-worker/tests/test_metrics_decision_lag.py -q
.....
5 passed in 1.02s

$ timeout 120 uv run pytest services/strategy-worker/tests/test_heartbeat_decision_lag.py -q
..
2 passed in 2.58s
```

### 3.4 Regressão: nenhuma suíte existente quebrou

A reescrita de `run_consumer` (dispatch em vez de `await` sequencial) mudou o instante em que uma
barra de fato executa em relação ao instante em que a mensagem é lida — `test_consumer_supervision.py`
dependia disso implicitamente (esperava `handled == 3` antes do backoff simulado). Corrigido
adicionando `await dispatcher.drain()` no ramo "stream terminou" antes do sleep de backoff — a
mesma garantia de sempre (nenhuma mensagem aceita fica pra trás), só que agora explícita. As duas
outras suítes (`test_consumer_isolation.py`, `test_spot_not_in_shadow_universe.py`) usavam
`BAR_CLOSE` fixo no passado sem `clock=` explícito; a nova válvula de atraso (que lê o relógio real
por padrão) as teria recusado antes do laço que elas testam — corrigido fixando `clock=BAR_CLOSE +
2s`, o mesmo padrão que `test_shadow_decisions.py` já usava.

```bash
$ timeout 200 uv run pytest services/strategy-worker/tests -q -m unit
343 passed, ... deselected in 15.54s   (318 antes desta tarefa — 25 testes novos)

$ timeout 290 uv run pytest services/strategy-worker/tests/test_shadow_decisions.py -q
15 passed in 102.32s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_spot_not_in_shadow_universe.py -q
6 passed in 24.24s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_shadow_outcomes.py -q
16 passed in 120.46s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_replay_reproduce.py -q
6 passed in 55.56s

$ timeout 120 uv run pytest services/strategy-worker/tests/test_consumer_supervision.py \
  services/strategy-worker/tests/test_consumer_isolation.py -q
8 passed in 3.72s
```

### 3.5 Qualidade

```bash
$ uv run ruff check services/strategy-worker/
All checks passed!

$ uv run ruff format --check services/strategy-worker/
135 files already formatted

$ uv run pyright services/strategy-worker
3 errors, 0 warnings, 0 informations
  (pré-existentes: test_replay_drain_pause.py:91 e test_replay_stress.py:35, mesma família aceita
   em T3.73/T3.74/T3.74b, `reportPrivateUsage` sobre símbolos privados de outro módulo por
   convenção — nenhum é meu)

$ uv run python infra/scripts/check_file_size.py
error   381 > 350  services/strategy-worker/hunter_strategy_worker/funding.py
scanned 612 files; 1 over budget, 0 grandfathered
  (pré-existente, de outra tarefa em andamento na mesma árvore — confirmado com
   `git diff --stat -- .../funding.py`: modificado, mas não por mim nesta sessão; nenhum arquivo
   desta tarefa passa do orçamento — consumer.py 306, dispatch.py 133, outcome_sweep.py 97,
   decide.py 258, metrics.py 185, config.py 201)
```

---

## 4. Por que não sharding em múltiplos processos (candidato b, variante "réplicas")

Medido: `hunter-strategy-worker-1` em rajada de CPU (92,7 % de um núcleo, depois 16 %) — coerente
com custo dominado por E/S (round trips de Postgres) na maior parte do tempo, com picos de CPU
durante o burst. Um pool de concorrência em processo único (`asyncio`) já explora essa folga de E/S
sem o custo operacional de novos serviços/grupos de consumidor Redis. Sharding por múltiplos
processos (como o `market-worker`, `MARKET_SHARDS`) continua sendo a alavanca certa **se** a rajada
se mostrar dominada por CPU pura depois desta correção — não descartado, só não é o primeiro corte,
e exigiria mudança de topologia do compose (novos serviços, novos nomes de grupo consumidor) que
está fora do que esta tarefa pode implantar (regra: nenhuma escrita na VPS). Registrado como
próximo passo se `decision_lag_p95_s` não cair o suficiente pós-deploy.

---

## 5. Ressalvas honestas (resumo)

1. **Não implantei nada na VPS.** Todo número "antes" é real (SQL/Redis/docker, somente leitura);
   todo número "depois" é local (testcontainer + benchmark sintético). O "depois" ao vivo depende
   do deploy do orquestrador e de uma nova leitura das mesmas consultas.
2. **A válvula de 120 s troca uma fatia da população de pesquisa `no_entry: late:delay` pela
   capacidade do worker de não compor atraso** — só ativa sob fila real (hoje o worker saudável
   nunca chegaria a 120 s), mas é uma perda real de dado de pesquisa quando ativa, e está contada,
   não escondida.
3. **`pg_stat_statements` continua ausente** (item 3 do T3.74b, devops-engineer, fora do meu papel).
4. **`funding.py`/`gate_policy.py`/`record.py`/`variant.py`/`breadth_gate.py` já apareciam
   modificados no `git status` antes desta tarefa começar** — outra frente (T3.77) ativa na mesma
   árvore; nenhum foi tocado por mim, confirmado arquivo a arquivo abaixo.
5. **A válvula de 120 s (`late_delay_backlog_max_s`) pode disparar logo após um restart/deploy do
   próprio worker, sem que haja rajada nenhuma** — não é um bug, é a mesma lógica batendo num caso
   diferente (nota pedida pela revisão do T3.74d, código HIGH abaixo). Um worker recém-subido lê
   `market.candles.closed` a partir do último offset confirmado do grupo consumidor
   (`strategy-worker.shadow`); se o processo ficou fora do ar por mais de 120 s (deploy, restart do
   contêiner, OOM), as primeiras barras que ele processa ao voltar já nascem mais velhas que a
   válvula — não porque o worker está sob fila agora, mas porque elas *já estavam* atrasadas quando
   ele parou de ler. Isso aparece em `hunter_shadow_bars_skipped_total{reason="late_delay_backlog"}`
   como uma rajada curta de incrementos logo no boot (visível também em
   `docker logs`/`shadow_bar_skipped_late_backlog`), e é esperado nesse momento — não indica que o
   `BarDispatcher` está saturado. Distingue-se de uma rajada real de mercado (200 fechamentos quase
   simultâneos) pelo `evaluated_bars`/`errors` de `hb:strategy:shadow` estarem baixos ou zerados
   nesse mesmo instante (nada mais está sendo processado), e pelo timestamp coincidir com o instante
   do deploy, não com o minuto de fechamento de vela. Nenhuma ação corretiva é necessária: o worker
   recupera o backlog normalmente depois dessa rajada curta de skips.

---

## 6. Arquivos tocados/criados (árvore compartilhada — abaixo só o que é desta tarefa)

```
 M docs/DEPLOYMENT.md
 M docs/PIPELINE.md
 M obsidian/07-BUGS/Open Bugs.md
 M services/strategy-worker/hunter_strategy_worker/config.py
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/decide.py
 M services/strategy-worker/hunter_strategy_worker/heartbeat.py
 M services/strategy-worker/hunter_strategy_worker/main.py
 M services/strategy-worker/hunter_strategy_worker/metrics.py
 M services/strategy-worker/tests/test_consumer_isolation.py
 M services/strategy-worker/tests/test_replay_reproduce.py
 M services/strategy-worker/tests/test_shadow_outcomes.py
 M services/strategy-worker/tests/test_spot_not_in_shadow_universe.py
?? .claude/state/brief-T3.74c-atraso-instantaneo.md
?? .claude/state/notes-T3.74c.md
?? infra/scripts/sql/research/2026-09-10-t374c-q01-lag-recente.sql
?? infra/scripts/sql/research/2026-09-10-t374c-q02-replay-hoje.sql
?? services/strategy-worker/hunter_strategy_worker/dispatch.py
?? services/strategy-worker/hunter_strategy_worker/outcome_sweep.py
?? services/strategy-worker/tests/test_dispatch.py
?? services/strategy-worker/tests/test_dispatch_benchmark.py
?? services/strategy-worker/tests/test_heartbeat_decision_lag.py
?? services/strategy-worker/tests/test_late_delay_backlog.py
?? services/strategy-worker/tests/test_metrics_decision_lag.py
```

**Não tocados por mim, apesar de aparecerem modificados no `git status` da árvore compartilhada**
(outra frente, T3.77, em execução hoje): `services/strategy-worker/hunter_strategy_worker/{funding,
gate_policy,record,variant}.py`, `services/strategy-worker/hunter_strategy_worker/breadth_gate.py`
(novo), `services/strategy-worker/tests/{test_funding,test_breadth_gate,test_breadth_gate_policy}.py`,
`services/strategy-worker/hunter_strategy_worker/context.py` (do T3.74b, anterior a esta tarefa).

`outcome_sweep.py` nasceu de uma extração mecânica: `sweep_outcomes`/`run_outcomes` saíram de
`consumer.py` para caber no orçamento de 350 linhas depois do trabalho de dispatch — mesmo
comportamento, import atualizado em `main.py` e nos três arquivos de teste que os usavam
diretamente (`test_replay_reproduce.py`, `test_shadow_outcomes.py`, e o monkeypatch de
`load_open_trackings` em `test_shadow_outcomes.py`, que agora aponta para o módulo novo).

## 7. Próximo passo

Deploy pelo orquestrador; depois, reler `2026-09-10-t374c-q01-lag-recente.sql` (ou uma janela
equivalente do dia do deploy) e `HGETALL hb:strategy:shadow` para `decision_lag_p50_s`/`p95_s` ao
vivo. Se a mediana não cair para < 5 s / p95 < 20 s, o próximo corte é CPU pura dentro da rajada
(§4) — sharding em múltiplos processos, análogo ao `market-worker`.

---

## 8. T3.74d — o achado HIGH da revisão (fix, não implantado)

**Escopo:** corrigir o achado HIGH da revisão de código sobre o trabalho não commitado do T3.74c
(`dispatch.py`, `consumer.py`, `config.py`). Nenhum arquivo além destes três (e testes/`docs/
DEPLOYMENT.md`) foi tocado; nenhum dos módulos do T3.77 em andamento na mesma árvore
(`gate_policy.py`, `variant.py`, `context.py`, `record.py`, `breadth_gate.py`) foi aberto.

### 8.1 O laço de realimentação

Com o `BarDispatcher` do T3.74c, `run_consumer` só bloqueia no semáforo do dispatcher, nunca no
processamento de uma barra específica — o próprio `consume()` (`packages/core/hunter_core/events/
consume.py:178`) reclama (`XAUTOCLAIM`) qualquer mensagem parada há mais de `claim_idle_ms` (padrão
antigo, fixo, 30 000 ms) na lista de pendências deste **mesmo** grupo consumidor, mesmo que este
mesmo processo ainda a esteja segurando (em fila atrás do semáforo, ou atrás do lock de mercado).
Antes desta correção, essa reentrega era resubmetida ao dispatcher e rodava uma segunda vez —
dobrando trabalho exatamente durante a rajada que o dispatcher existe para absorver.

### 8.2 A correção, em duas camadas

1. **`BarDispatcher.submit`** (`dispatch.py`) agora recebe `message_id` e recusa (contado por nome,
   `hunter_shadow_bars_skipped_total{reason="already_in_flight"}`) uma mensagem já em fila ou em
   execução — checado e registrado **antes** da espera pelo semáforo, então uma reentrega ainda na
   fila (nunca chegou a rodar) também é coberta, não só uma cujo handler já começou.
2. **`ShadowConfig.claim_idle_ms`** (`config.py`, nova var `SHADOW_CLAIM_IDLE_MS`) substitui o padrão
   fixo de `consume()`. Padrão derivado: `worker_concurrency × EXPECTED_BAR_COST_S` (8,0 s,
   conservador — de `docs/DEPLOYMENT.md`/T3.74b: ~1,4-1,5 avaliações/s por versão devida, até 11
   versões de uma família avaliadas em série dentro de um único `handle_candle`) = 64 000 ms no
   padrão de 8. **O limite, por escrito**: nunca deixar chegar perto de `consumer_stall_s` (300 s) —
   esse já é o ponto em que `/ready` considera o processo sem progresso, então um consumidor
   realmente morto precisa ser reclamado bem antes disso; 64 000 ms é ~21 % desse orçamento. `run_
   consumer` agora passa `config.claim_idle_ms` para `consume(...)` em vez do padrão da função.

Nota da revisão registrada em §5 item 5 acima: a válvula de 120 s (`late_delay_backlog_max_s`, não
tocada nesta tarefa) também pode disparar logo após um restart/deploy do worker, sem rajada nenhuma
— documentado ali com como isso aparece no métrico e por que é esperado.

### 8.3 TDD

**Prova de que falha pela razão certa (dedup desligado temporariamente, script fora do pytest para
não arriscar um hang real durante a suíte):**

```bash
$ timeout 60 uv run python <script standalone com o mesmo cenário de test_reclaim_dedup.py>
handled: ['AAA']
skipped already_in_flight delta: 0.0
EXPECTED FAILURE (proves the bug without the fix): dedup metric never incremented
```

Confirma o mecanismo exato: sem a guarda, a segunda entrega da mesma mensagem fica presa no lock de
mercado (não dobra `handled` na hora, mas dobraria assim que o lock liberasse) e o métrico de recusa
nunca incrementa — a razão certa, não um efeito colateral.

**Depois da correção:**

```bash
$ timeout 60 uv run pytest services/strategy-worker/tests/test_dispatch.py -q
13 passed in 4.83s

$ timeout 120 uv run pytest services/strategy-worker/tests/test_reclaim_dedup.py -q
1 passed in 1.60s

$ timeout 90 uv run pytest services/strategy-worker/tests/test_claim_idle_ms.py -q
6 passed in 0.66s
```

`test_dispatch.py::TestDuplicateMessageIsRefused` (3 casos): mensagem já **rodando** é recusada sem
rodar de novo; mensagem só **em fila** (nunca chegou a rodar) também é recusada; depois que a
primeira entrega termina, o mesmo `message_id` pode rodar de novo (não é um bloqueio permanente —
um replay genuíno da mesma mensagem precisa continuar funcionando).

`test_reclaim_dedup.py` (1 caso, imita `test_consumer_supervision.py`): `consume()` é substituído por
um gerador falso que entrega a mesma mensagem duas vezes (a segunda representa a reclamação do
`XAUTOCLAIM`) enquanto o handler da primeira ainda está bloqueado — prova, através de `run_consumer`
de ponta a ponta (não só do dispatcher isolado), que a barra é processada e confirmada (`ack`)
exatamente uma vez.

`test_claim_idle_ms.py` (6 casos): a conta (`worker_concurrency × EXPECTED_BAR_COST_S`), a derivação
por instância (`ShadowConfig(worker_concurrency=4)` deriva diferente de `8`), que um valor explícito
nunca é sobrescrito, o limite (`claim_idle_ms < consumer_stall_s × 1000 / 2`) e a leitura da variável
de ambiente (`SHADOW_CLAIM_IDLE_MS`, com e sem override).

**Regressão — suíte unit completa e o benchmark real (uma invocação, testcontainer):**

```bash
$ timeout 200 uv run pytest services/strategy-worker/tests -q -m unit
353 passed, 376 deselected in 12.26s   (343 antes desta tarefa — 10 testes novos)

$ timeout 290 uv run pytest services/strategy-worker/tests/test_dispatch_benchmark.py -q
1 passed in 41.61s
```

### 8.4 Qualidade

```bash
$ uv run ruff check services/strategy-worker/
All checks passed!

$ uv run ruff format --check services/strategy-worker/
137 files already formatted

$ uv run pyright services/strategy-worker
3 errors, 0 warnings, 0 informations
  (os 3 pré-existentes de sempre — test_replay_drain_pause.py:91, test_replay_stress.py:35 (dois),
   `reportPrivateUsage` sobre símbolos privados de outro módulo por convenção, aceitos desde
   T3.73/T3.74/T3.74b/T3.74c; nenhum é meu, nenhum novo apareceu)

$ uv run python infra/scripts/check_file_size.py
scanned 614 files; 0 over budget, 0 grandfathered
  (consumer.py 311, dispatch.py 164, config.py 293 — todos dentro do orçamento de 350;
   `funding.py`, que aparecia acima do orçamento na nota do T3.74c, não é mais reportado — outra
   frente em andamento na mesma árvore já corrigiu, não fui eu)
```

### 8.5 Arquivos tocados/criados nesta tarefa (T3.74d, subconjunto do compartilhado abaixo)

```
 M docs/DEPLOYMENT.md
 M services/strategy-worker/hunter_strategy_worker/config.py
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/dispatch.py
 M .claude/state/notes-T3.74c.md
 M services/strategy-worker/tests/test_dispatch.py
 M services/strategy-worker/tests/test_dispatch_benchmark.py
?? services/strategy-worker/tests/test_claim_idle_ms.py
?? services/strategy-worker/tests/test_reclaim_dedup.py
```

`hunter_strategy_worker/metrics.py` **não foi modificado**: `hunter_shadow_bars_skipped_total` já
existia com um label `reason` livre desde o T3.74c; a nova razão (`already_in_flight`) só precisou de
uma chamada nova a `.labels(reason=...).inc()`, nenhuma mudança na definição do métrico.

### 8.6 `git status --porcelain` completo — T3.74c + T3.74d (filtrado ao universo desta frente; a
árvore tem outras frentes ativas em paralelo, não listadas aqui)

```
 M docs/DEPLOYMENT.md
 M services/strategy-worker/hunter_strategy_worker/config.py
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/context.py            (T3.74b, não mexido aqui)
 M services/strategy-worker/hunter_strategy_worker/decide.py             (T3.74c)
 M services/strategy-worker/hunter_strategy_worker/gate_policy.py        (T3.77, não é meu)
 M services/strategy-worker/hunter_strategy_worker/heartbeat.py          (T3.74c)
 M services/strategy-worker/hunter_strategy_worker/main.py               (T3.74c)
 M services/strategy-worker/hunter_strategy_worker/metrics.py            (T3.74c)
 M services/strategy-worker/hunter_strategy_worker/record.py             (T3.77, não é meu)
 M services/strategy-worker/hunter_strategy_worker/variant.py            (T3.77, não é meu)
 M services/strategy-worker/tests/test_consumer_isolation.py             (T3.74c)
 M services/strategy-worker/tests/test_replay_reproduce.py               (T3.74c)
 M services/strategy-worker/tests/test_shadow_outcomes.py                (T3.74c)
 M services/strategy-worker/tests/test_spot_not_in_shadow_universe.py    (T3.74c)
?? .claude/state/notes-T3.74c.md                                          (T3.74c, +§5 item 5/§8 aqui)
?? infra/scripts/sql/research/2026-09-10-t374c-q01-lag-recente.sql        (T3.74c)
?? infra/scripts/sql/research/2026-09-10-t374c-q02-replay-hoje.sql        (T3.74c)
?? services/strategy-worker/hunter_strategy_worker/breadth_gate.py        (T3.77, não é meu)
?? services/strategy-worker/hunter_strategy_worker/dispatch.py            (T3.74c + T3.74d)
?? services/strategy-worker/hunter_strategy_worker/outcome_sweep.py       (T3.74c)
?? services/strategy-worker/tests/test_breadth_gate.py                   (T3.77, não é meu)
?? services/strategy-worker/tests/test_breadth_gate_policy.py            (T3.77, não é meu)
?? services/strategy-worker/tests/test_claim_idle_ms.py                  (T3.74d)
?? services/strategy-worker/tests/test_dispatch.py                       (T3.74c + T3.74d)
?? services/strategy-worker/tests/test_dispatch_benchmark.py             (T3.74c + T3.74d)
?? services/strategy-worker/tests/test_heartbeat_decision_lag.py         (T3.74c)
?? services/strategy-worker/tests/test_late_delay_backlog.py             (T3.74c)
?? services/strategy-worker/tests/test_metrics_decision_lag.py           (T3.74c)
?? services/strategy-worker/tests/test_reclaim_dedup.py                  (T3.74d)
```

### 8.7 Ressalva honesta

Nada implantado na VPS (regra da tarefa: leitura em produção quando aplicável, escrita nunca). O
achado era sobre o código não commitado do T3.74c; a correção fica igualmente não commitada, pronta
para revisão/commit junto com o resto do T3.74c pelo orquestrador.
