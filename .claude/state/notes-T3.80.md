# Notes — T3.80: o replay sai do container da linha viva

## 1. Entregas

### 1.1 Motivo `decision_lag` no portão de pausa

- `services/strategy-worker/hunter_strategy_worker/config.py`: `ShadowConfig.decision_lag_p50_alert_s`
  (10.0) / `decision_lag_p95_alert_s` (30.0), env `SHADOW_DECISION_LAG_P50_ALERT_S` /
  `SHADOW_DECISION_LAG_P95_ALERT_S` — os números canônicos, documentados junto dos outros
  limiares operacionais do worker vivo (`outbox_lag_alert_s`, `consumer_stall_s`).
- `services/strategy-worker/hunter_strategy_worker/replay/decision_lag.py` (novo): lê
  `decision_lag_p50_s`/`_p95_s` do heartbeat (`hb:strategy:shadow`, já escritos desde T3.74c),
  compara contra os limiares e mantém a histerese de retomada em Redis
  (`replay:decision_lag_last_bad_at`). Sem sinal ainda (`""`) nunca é tratado como degradado, e
  nunca toca o Redis nesse caso — testado explicitamente (`_ExplodingRedis`), porque nenhum
  fixture de heartbeat anterior a esta tarefa carrega esses dois campos.
- `services/strategy-worker/hunter_strategy_worker/replay/budget.py`: `ReplayBudget` ganhou
  `decision_lag_p50_max_s`/`_p95_max_s` (10.0/30.0, espelham `ShadowConfig`, como
  `outbox_lag_max_s` já espelha `outbox_lag_alert_s`) e `decision_lag_resume_healthy_s` (300.0 —
  5 min); `live_lane_degraded` chama `decision_lag_reason` entre o `outbox_lag` e o `consumer_lag`
  (mais barato: mesmo `HGETALL`, sem outra ida ao Redis). Novos env: `REPLAY_DECISION_LAG_P50_MAX_S`,
  `REPLAY_DECISION_LAG_P95_MAX_S`, `REPLAY_DECISION_LAG_RESUME_HEALTHY_S`.
- **Refatoração de tamanho (não pedida, necessária):** `budget.py` passou de 338 para 366 linhas
  com o novo motivo; para caber no orçamento de 350, `ReplayRequest`/`enqueue`/`take_next`/
  `queue_depth` foram movidos para `services/strategy-worker/hunter_strategy_worker/replay/queue.py`
  (novo), reexportados por `budget.py` — mesmo padrão que já separou `consumer_lag.py` de
  `budget.py` no T3.74b. Nenhuma API pública mudou (`from ...budget import ReplayRequest, ...`
  continua funcionando; `test_replay_contract.py`/`test_replay_drain_pause.py`/
  `test_replay_explain.py` passam sem alteração).
- Testes: `services/strategy-worker/tests/test_replay_decision_lag_gate.py` (novo, 16 casos —
  sem sinal, sob/sobre limiar em cada eixo, histerese: cooldown, retomada exata na borda, uma
  leitura ruim durante o cooldown reinicia o marcador, falha do Redis no `get`/`set`, e o portão
  completo com `live_lane_degraded` incluindo a checagem "decision_lag antes de consumer_lag").

### 1.2 Replay em processo próprio

- `services/strategy-worker/hunter_strategy_worker/replay/role_guard.py` (novo):
  `refuse_inside_live_worker(role=None)` — recusa quando `HUNTER_ROLE=="strategy"` (o valor real do
  serviço `strategy-worker` no compose; `entrypoint.sh` despacha por esse literal, não por
  `"strategy-worker"` como o brief especulava — conferido em `infra/docker/entrypoint.sh` e
  `packages/core/hunter_core/settings.py::Role`). `role` é parâmetro, não só leitura de ambiente —
  "exceto em testes" cai de graça disso, sem bandeira dedicada.
- `services/strategy-worker/hunter_strategy_worker/replay/run.py`: `_main` chama o guard **antes**
  de qualquer parsing de argumento, `--stress`, drenagem de fila ou corrida direta — um `docker exec`
  no worker vivo por engano é recusado antes de tocar Redis/Postgres, seja qual for o subcomando.
- `infra/docker/docker-compose.yml`: serviço `replay-worker` — mesma imagem
  `hunter-api:${GIT_SHA:-dev}`, `profiles: ["replay"]`, `entrypoint: []`/`command: ["true"]`/
  `cap_drop` copiados do `ops`, `DB_POOL_SIZE`/`DB_MAX_OVERFLOW=2` (contra 5+5 do worker vivo),
  `deploy.resources.limits.cpus: "3"` (= `workers_for(ReplayBudget(), 12)`)/`memory: 2g`. **Nunca
  define `HUNTER_ROLE`** — de propósito, é o que deixa o guard passar.
- `infra/vps/docker-compose.prod.yml`: override `replay-worker` com `*prod-db-env` (mesma razão de
  todo outro worker: sem isso herda a senha de dev e cai em `InvalidPasswordError`).
- `infra/vps/compose.sh`: subcomando `replay` — mesmo padrão do `ops` (recusa se
  `hunter-api:${GIT_SHA:-dev}` não existir localmente; nunca constrói); `run --rm replay-worker "$@"`.
- Testes: `services/strategy-worker/tests/test_replay_role_guard.py` (novo, 13 casos — o papel do
  worker vivo é recusado, todo outro papel passa, leitura real do ambiente via `monkeypatch`, e a
  fiação do CLI: uma corrida direta *e* um `--drain-queue` são recusados **antes** de `_drain` ser
  sequer chamado, com contraprova de que um papel são chega até o parsing normal).
- `infra/scripts/tests/test_replay_not_docker_exec_docs.py` (novo, no molde de
  `test_partitions_ops_docs.py`): nenhum doc (`DEPLOYMENT.md`, `ACTIVATION.md`, `PIPELINE.md`,
  `infra/vps/README.md`) pode instruir `docker exec ... strategy-worker ... replay.run`; hoje
  nenhum instrui (0 ocorrências) — o lint é guarda contra regressão futura.
- Docs: `docs/DEPLOYMENT.md` §5.2 (comando `compose.sh replay ...`, tabela `REPLAY_*` com os três
  novos knobs, regra de convívio atualizada), `docs/ACTIVATION.md` §7 (parágrafo "Rodar o replay de
  validação da variante"), `docs/PIPELINE.md` §6c (não §6b — §6b é o Shadow Lab em si; §6c é a
  seção de replay de fato, e é onde o parágrafo foi colocado; desvio deliberado do texto literal do
  brief, registrado aqui).

  **Concern de rastreamento (não uma violação de regra — nunca commitei nada):** esta árvore é
  compartilhada; enquanto meu parágrafo do §6c estava só no working tree, um commit concorrente
  (`107abc6`, T3.81, outro agente, `docs/PIPELINE.md` mudado por eles mesmos) fez `git add` do
  arquivo inteiro e varreu meu parágrafo junto — `git show 107abc6 -- docs/PIPELINE.md` mostra as
  duas inserções (a deles em §6b sobre `flush`, a minha em §6c sobre T3.80) no mesmo diff. O
  conteúdo está correto e completo; só a atribuição do commit está errada (foi para 107abc6/T3.81,
  não para o commit que o orquestrador vai fazer desta tarefa). `docs/PIPELINE.md` por isso **não
  aparece** no `git status --porcelain` abaixo — já está em HEAD.

### 1.3 Prova local (11×200 + replay concorrente)

- `services/strategy-worker/tests/test_dispatch_benchmark.py`: nova classe
  `TestSurvivesAConcurrentReplayProcess`. Um processo do SO separado (`subprocess.Popen`, script
  `python -c`, nunca importa este módulo de teste — evita todo problema de `spawn`/pickle do
  Windows com um diretório de pacote hifenizado) abre `CONTENTION_CONNECTIONS=3` conexões próprias
  contra o **mesmo** Postgres do testcontainer e, em loop, roda uma query real (`SELECT 1`) mais
  `hashlib.sha256` sobre 4 KB aleatórios — os dois recursos que o T3.76 mediu a linha viva perdendo
  para um replay que compartilhava o container (CPU e pool de conexões). Com essa contenção rodando
  de verdade, 6 rodadas do dreno vivo (5 mercados × 3 versões, `BarDispatcher` em concorrência 8, o
  mesmo `_deliver_all` que `TestConcurrentDispatchAgreesWithSerial` já usa) são cronometradas.
  **Resultado real, uma corrida:** `durations_s=[2.86, 3.02, 3.18, 3.26, 3.33, 7.0]`, `p95_s=3.33`
  — bem abaixo do orçamento de 20 s.

  **Honesto sobre o que isto não prova:** não reproduz o teto de CPU/memória do cgroup
  (`replay-worker`'s `deploy.resources.limits`) nem o número de vCPU/disco da VPS — só prova que,
  mesmo sem esse teto (portanto no cenário *mais* desfavorável que a produção real terá, já que a
  VPS terá o cgroup limitando o replay), um processo de replay separado, com pool próprio, não
  reproduz a degradação medida quando o replay rodava *dentro* do mesmo container. **Medição real
  a fazer na VPS** (o orquestrador, pós-deploy): rodar `compose.sh replay ...` concorrente com o
  worker vivo por uma janela e ler `decision_lag_p50_s`/`_p95_s` de `hb:strategy:shadow` durante
  ela — esperado ficar abaixo de 10 s/30 s (os limiares novos), ao contrário dos 90 s/171 s medidos
  em 10/09 com o replay dentro do container.

## 2. Comandos rodados e saída real

```
$ uv run pytest services/strategy-worker/tests/test_replay_decision_lag_gate.py -q
................                                                         [100%]
16 passed in 0.71s

$ uv run pytest services/strategy-worker/tests/test_replay_contract.py services/strategy-worker/tests/test_replay_drain_pause.py services/strategy-worker/tests/test_replay_explain.py -q
................................................................         [100%]
64 passed in 58.14s

$ uv run pytest services/strategy-worker/tests/test_replay_role_guard.py -q
.............                                                            [100%]
13 passed in 15.82s

$ uv run pytest infra/scripts/tests/test_replay_not_docker_exec_docs.py infra/scripts/tests/test_partitions_ops_docs.py -q
.................                                                        [100%]
17 passed in 0.46s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_dispatch_benchmark.py -q
..                                                                       [100%]
2 passed in 69.65s

$ timeout 290 uv run pytest services/strategy-worker/tests/test_dispatch_benchmark.py::TestSurvivesAConcurrentReplayProcess -q -s
... t380_replay_contention_proof durations_s=[2.86, 3.02, 3.18, 3.26, 3.33, 7.0] p95_s=3.33
1 passed in 46.81s

$ timeout 280 uv run pytest services/strategy-worker/tests -m "not integration" -q
........................................................................ [ 13%]
...
523 passed, 236 deselected in 11.89s

$ uv run ruff check services/strategy-worker infra/scripts/tests/test_replay_not_docker_exec_docs.py
All checks passed!

$ uv run ruff format --check <every touched/new file>
all formatted (fixed 4 with --fix during the task)

$ uv run pyright services/strategy-worker infra/scripts/tests/test_replay_not_docker_exec_docs.py
6 errors, 0 warnings — all 6 pre-existing `reportPrivateUsage` on `_main`/`_drain`/`_delayed`/
`_plan_for` used from tests (same pattern already present in test_replay_drain_pause.py and
test_replay_stress.py before this task; test_replay_role_guard.py's 3 new ones follow the same
accepted style, not a new problem).

$ uv run python infra/scripts/check_file_size.py
scanned 620 files; 0 over budget, 0 grandfathered

$ docker compose -f infra/docker/docker-compose.yml --profile replay config --services
... replay-worker (present, alongside every other service)

$ env POSTGRES_PASSWORD=x HUNTER_PUBLIC_URL=... HUNTER_WS_URL=... HUNTER_SITE_ADDRESS=:80 \
  docker compose -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml \
  --env-file .env --profile replay config
... replay-worker renders with *prod-db-env, DB_POOL_SIZE/DB_MAX_OVERFLOW=2, staging HUNTER_ENV,
    no HUNTER_ROLE, deploy.resources.limits.cpus=3/memory=2147483648, logging: *prod-logging

$ bash -n infra/vps/compose.sh
syntax OK
```

No VPS command was ever run; every check above is local (Docker Desktop on this dev machine) or a
pure text/config read. The T3.76 replay running live on the VPS was never touched.

## 3. Desvios do brief, registrados

- **`PIPELINE.md §6b` → §6c.** §6b é "Shadow Lab: `strategy-worker` em modo sombra" (a linha viva em
  si); §6c é "Replay histórico" — a seção real sobre o assunto desta tarefa. O parágrafo foi
  colocado em §6c; ver §1.2 acima para o efeito colateral do commit concorrente.
- **`HUNTER_ROLE` do worker vivo é `"strategy"`, não `"strategy-worker"`** como o brief especulava —
  conferido em `infra/docker/docker-compose.yml`/`docker-compose.prod.yml` e
  `infra/docker/entrypoint.sh`. `role_guard.py` usa o valor real.
- **`budget.py` precisou de uma extração adicional (`queue.py`)** para caber no orçamento de 350
  linhas com o novo motivo — não pedido explicitamente, mas necessário e no mesmo padrão já usado
  para `consumer_lag.py`.

## 4. `git status --porcelain` — só os arquivos desta tarefa

(A árvore tem dezenas de arquivos não relacionados de outras tarefas em andamento em paralelo;
listados aqui só os meus.)

```
 M infra/docker/docker-compose.yml
 M infra/vps/compose.sh
 M infra/vps/docker-compose.prod.yml
 M services/strategy-worker/hunter_strategy_worker/config.py
 M services/strategy-worker/hunter_strategy_worker/replay/budget.py
 M services/strategy-worker/hunter_strategy_worker/replay/run.py
 M services/strategy-worker/tests/test_dispatch_benchmark.py
 M docs/ACTIVATION.md
 M docs/DEPLOYMENT.md
?? services/strategy-worker/hunter_strategy_worker/replay/decision_lag.py
?? services/strategy-worker/hunter_strategy_worker/replay/queue.py
?? services/strategy-worker/hunter_strategy_worker/replay/role_guard.py
?? services/strategy-worker/tests/test_replay_decision_lag_gate.py
?? services/strategy-worker/tests/test_replay_role_guard.py
?? infra/scripts/tests/test_replay_not_docker_exec_docs.py
?? .claude/state/notes-T3.80.md
```

Not in this list, but mine (already in HEAD via the concurrent T3.81 commit, `107abc6` — see §1.2):

```
docs/PIPELINE.md — §6c paragraph, "O replay roda no seu próprio processo... (T3.80)"
```
