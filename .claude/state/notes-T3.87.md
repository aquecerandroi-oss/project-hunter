# T3.87 — o portão do replay ficou cego quando o worker vivo foi shardado

Horários em Brasília (UTC−3); hoje é 2026-09-11. Trabalho local (leitura/edição/testes) e uma
leitura somente-leitura na VPS (`hunter-vps`) para provar a causa raiz e o efeito da correção,
sem escrever nada, sem tocar contêiner.

## 1. Diagnóstico (herdado da T3.84, confirmado ao vivo nesta tarefa às 06:16 BRT/09:16Z)

`STRATEGY_SHARDS=4` (T3.74f) shardou o worker vivo em quatro processos, cada um com sua própria
chave de heartbeat (`hb:strategy:shadow:{i}of4`) e grupo consumidor
(`strategy-worker.shadow.{i}of4`). O portão de pausa do replay (`replay/budget.py`) nunca foi
atualizado: continuava lendo o literal `hb:strategy:shadow` (chave que ninguém mais escreve) e o
grupo `strategy-worker.shadow` (abandonado). Confirmado ao vivo, somente leitura:

```
$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli XINFO GROUPS market.candles.closed"
name               scanner-worker.market.candles.closed   pending 0   lag 0
name               strategy-worker.shadow                 pending 36  lag 50001   <- órfão
name               strategy-worker.shadow.0of4             pending 0   lag 0
name               strategy-worker.shadow.1of4             pending 0   lag 0
name               strategy-worker.shadow.2of4             pending 0   lag 0
name               strategy-worker.shadow.3of4             pending 0   lag 0

$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli EXISTS hb:strategy:shadow"
0   # a chave sem sufixo nao existe mais

$ timeout 60 ssh hunter-vps "for i in 0 1 2 3; do docker exec hunter-redis-1 redis-cli HGET hb:strategy:shadow:\${i}of4 ts; done"
2026-09-11T09:16:40.939100+00:00
2026-09-11T09:16:36.425714+00:00
2026-09-11T09:16:35.767251+00:00
2026-09-11T09:16:35.930462+00:00
```

O portão antigo lia `hb:strategy:shadow` → `hgetall` vazio → `heartbeat_missing`, sempre (efeito
já medido pela T3.84 05:36 BRT: `refused: live lane degraded (heartbeat_missing)` em toda corrida).
Mesmo contornando a chave (`REPLAY_HEARTBEAT_KEY` para um shard), o grupo `strategy-worker.shadow`
(`lag=50001` e subindo) teria recusado de novo pelo eixo de consumer-lag — não havia variável de
ambiente para o nome do grupo.

## 2. Correção (TDD: teste falho → mínimo → verde → refactor)

**Nunca uma segunda fórmula.** `hunter_strategy_worker.shard.heartbeat_key`/`consumer_group`
(T3.74f) são as únicas funções que nomeiam um shard; o portão agora as chama para os `N` índices
de `STRATEGY_SHARDS`, nunca reconstrói o padrão de string.

- `services/strategy-worker/hunter_strategy_worker/shard.py` — `heartbeat_keys(shard_total)` e
  `consumer_groups(shard_total)`, novas: `tuple(heartbeat_key(i, N) for i in range(N))` e o
  espelho para grupos. `shard_total<=1` devolve a tupla de um elemento, byte a byte igual ao nome
  clássico sem sufixo.
- `services/strategy-worker/hunter_strategy_worker/replay/consumer_lag.py` —
  `topology_group_lag(redis, *, groups, prefix=LIVE_CONSUMER_GROUP)`: uma chamada `XINFO GROUPS`
  cobre todo o stream; devolve o **pior** (`max`) `lag` entre os `N` grupos esperados (`None` se
  qualquer um for ilegível — falha fechada, mesma regra de `group_lag`) e a tupla de grupos órfãos
  (nome começa com o prefixo da família mas não está na topologia atual) via `find_orphan_groups`.
- `services/strategy-worker/hunter_strategy_worker/replay/budget.py` —
  `ReplayBudget.shard_total: int = 1` (lido de `STRATEGY_SHARDS` em `load_budget()`);
  `live_lane_degraded` reescrito: com `shard_total<=1` usa exatamente `budget.heartbeat_key`
  (honra `REPLAY_HEARTBEAT_KEY`) e `LIVE_CONSUMER_GROUP`, sem mudança de comportamento; com
  `shard_total>1` lê os `N` heartbeats, recusa fechado no primeiro shard sem heartbeat
  (`heartbeat_missing:<key>`, nomeando-o), toma o **pior** `outbox_lag_s`/frescor de `ts` entre os
  `N`, monta um par sintético `(max p50, max p95)` de `decision_lag_p50_s`/`_p95_s` entre os `N` e
  repassa a `decision_lag_reason` (reuso, não reimplementação da histerese), e por fim
  `topology_group_lag` para o eixo de consumer-lag, logando cada órfão uma vez por checagem
  (`orphan_consumer_group`).

## 3. Composição — `replay-worker` precisa ver `STRATEGY_SHARDS`

- `infra/docker/docker-compose.yml`: `replay-worker.environment` ganhou
  `STRATEGY_SHARDS: ${STRATEGY_SHARDS:-1}` (mesma variável que já renderiza `STRATEGY_SHARD=i/N`
  nos serviços `strategy-worker*`).
- `infra/vps/compose.sh`: `export STRATEGY_SHARDS` explícito (antes só herdado implicitamente do
  prefixo do comando) e uma linha ecoada a cada `replay` (`STRATEGY_SHARDS=$STRATEGY_SHARDS`) para
  que o operador veja a topologia que o portão vai usar — quem rodar `replay` precisa passar o
  mesmo `STRATEGY_SHARDS` que o `update`/`up` mais recente usou, mesmo risco que já existia para
  `update`/`up` em si (T3.74f, documentado).
- Validado com `docker compose config` (sem subir nada): a variável sobrevive ao merge com
  `infra/vps/docker-compose.prod.yml` (que não repete `environment.STRATEGY_SHARDS` no override do
  `replay-worker`, então o valor da base passa direto).

```
$ HUNTER_WS_URL=ws://x HUNTER_PUBLIC_URL=http://x timeout 30 docker compose \
    -f infra/docker/docker-compose.yml --profile replay config replay-worker | grep -i STRATEGY_SHARD
      STRATEGY_SHARDS: "1"

$ STRATEGY_SHARDS=4 POSTGRES_PASSWORD=x HUNTER_WS_URL=ws://x HUNTER_PUBLIC_URL=http://x \
    HUNTER_SITE_ADDRESS=:80 NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=x timeout 30 docker compose \
    -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml \
    --profile strategy-shards --profile replay config \
    replay-worker strategy-worker strategy-worker-1 strategy-worker-2 strategy-worker-3 \
    | grep -iE "STRATEGY_SHARD|^  strategy-worker|^  replay-worker"
  replay-worker:
      STRATEGY_SHARDS: "4"
  strategy-worker:
      STRATEGY_SHARD: 0/4
  strategy-worker-1:
      STRATEGY_SHARD: 1/4
  strategy-worker-2:
      STRATEGY_SHARD: 2/4
  strategy-worker-3:
      STRATEGY_SHARD: 3/4

$ bash -n infra/vps/compose.sh
syntax OK
```

## 4. Testes (TDD)

Novos/estendidos, todos unit, nenhum testcontainer (o gate é aritmética + Redis falso — nenhuma
integração real necessária):

```
$ timeout 60 uv run pytest services/strategy-worker/tests/test_shard_topology.py -q
......                                                                   [100%]
6 passed in 0.45s

$ timeout 60 uv run pytest services/strategy-worker/tests/test_replay_decision_lag_gate.py -q
........................                                                 [100%]
24 passed in 0.94s

$ timeout 60 uv run pytest services/strategy-worker/tests/test_replay_drain_pause.py -q
......                                                                   [100%]
6 passed in 1.73s

$ timeout 60 uv run pytest services/strategy-worker/tests/test_replay_decision_lag_gate.py \
    services/strategy-worker/tests/test_replay_drain_pause.py \
    services/strategy-worker/tests/test_shard_topology.py \
    services/strategy-worker/tests/test_replay_contract.py -q
.................................................................................
81 passed in 2.49s

$ timeout 280 uv run pytest services/strategy-worker/tests -m "not integration" -q
595 passed, 242 deselected in 39.59s
```

Casos novos cobertos (N=4, `TestShardedTopology`/`TestDrainPausesOnDegradedShardedTopology`):
quatro shards saudáveis não pausam; um shard sem heartbeat recusa fechado nomeando a chave
(`heartbeat_missing:hb:strategy:shadow:2of4`); o motivo de frescor/`outbox_lag`/`decision_lag`
reportado é sempre o pior dos quatro; o grupo órfão `strategy-worker.shadow` (lag 50 000) nunca
conta e não bloqueia um dreno saudável; um shard ausente do próprio `XINFO GROUPS` é
`consumer_lag_unreadable` (falha fechada, nunca zero). N=1 (`ReplayBudget()` sem `shard_total`)
continua produzindo as mesmas strings de motivo de antes desta tarefa, provado pela suíte
pré-existente (`test_replay_contract.py::TestReadinessGate`/`TestConsumerLagGate`,
`test_replay_decision_lag_gate.py` original) passando sem alteração.

## 5. Qualidade

```
$ uv run ruff check services/strategy-worker packages/core/hunter_core/sharding.py
All checks passed!

$ uv run ruff format --check services/strategy-worker
161 files already formatted

$ uv run pyright services/strategy-worker
7 errors, 0 warnings, 0 informations
  (todos pré-existentes, `reportPrivateUsage` sobre `_drain`/`_main`/`_delayed`/`_plan_for` usados
   a partir de teste, mesmo padrão aceito desde T3.73/74/74b/80 — minha 2ª ocorrência de `_drain`
   em test_replay_drain_pause.py:187 segue o mesmo padrão já aceito na linha 92)

$ uv run python infra/scripts/check_file_size.py
scanned 629 files; 0 over budget, 0 grandfathered
  (budget.py: 348/350 — sem margem para crescer mais sem nova extração)

$ timeout 120 uv run python infra/scripts/obsidian_lint.py
RESULTADO: base limpa
```

## 6. Docs

- `docs/DEPLOYMENT.md` §5.2: nova linha `STRATEGY_SHARDS` na tabela `REPLAY_*` (explicitamente
  marcada "não é `REPLAY_*` de propósito"), parágrafo "Portão com topologia (T3.87)" explicando
  pior-dos-N/nomeação de shard faltante/órfão ignorado, e um bloco `bash` de checagem
  somente-leitura (per-shard heartbeat age + group lag) para o operador rodar antes de tentar um
  replay. §3.1b ganhou duas observações: o portão agora ignora (mas não apaga) o grupo órfão, e
  `replay-worker` precisa do mesmo `STRATEGY_SHARDS` que o deploy vivo usa.
- `obsidian/07-BUGS/Open Bugs.md`: nova entrada no topo ("Código corrigido na T3.87") documentando
  causa raiz, correção, composição e pendência de deploy — link cruzado com a observação já
  registrada pela T3.85 sobre o grupo órfão.

## 7. Arquivos desta tarefa (`git status --porcelain`, só os meus)

```
 M docs/DEPLOYMENT.md
 M infra/docker/docker-compose.yml
 M infra/vps/compose.sh
 M "obsidian/07-BUGS/Open Bugs.md"
 M services/strategy-worker/hunter_strategy_worker/replay/budget.py
 M services/strategy-worker/hunter_strategy_worker/replay/consumer_lag.py
 M services/strategy-worker/hunter_strategy_worker/shard.py
 M services/strategy-worker/tests/test_replay_decision_lag_gate.py
 M services/strategy-worker/tests/test_replay_drain_pause.py
 M services/strategy-worker/tests/test_shard_topology.py
?? .claude/state/notes-T3.87.md
```

Nenhum `.env*` tocado. Nenhum contêiner parado/recriado/reiniciado. Nenhuma escrita na VPS — as
duas leituras do §1 são `redis-cli XINFO GROUPS`/`HGET`, ambas somente-leitura. Nenhum `git pull`
rodado na VPS. Nenhum commit feito.

## 8. Pendências (não desta tarefa)

1. **Deploy**: nada implantado na VPS (regra do brief) — o efeito "depois" (replay saindo do
   `heartbeat_missing`) só é observável após `bash infra/vps/compose.sh update` (ou `up`) recriar
   `replay-worker` com a imagem que carrega este código, com `STRATEGY_SHARDS=4` no ambiente do
   comando.
2. **Faxina do grupo órfão**: `strategy-worker.shadow` (36 pending, lag crescente) continua existindo
   no Redis da VPS. O portão agora o ignora para efeito de saúde, mas não o remove — segue sendo
   trabalho manual (`XGROUP DESTROY market.candles.closed strategy-worker.shadow`, depois de
   confirmar que as 36 pendências não são recuperáveis), já registrado como observação pela T3.85.
3. **`STRATEGY_SHARDS` continua sendo estado que o operador tem que lembrar de repetir** em todo
   comando que toca a topologia (`update`/`up`/`replay`) — não há introspecção automática da
   contagem de shards viva a partir do compose.sh nesta tarefa; o eco adicionado (§3) é a mitigação
   mínima (visibilidade, não prevenção). **Mas o esquecimento falha para o lado seguro**: rodar
   `replay` sem `STRATEGY_SHARDS=4` contra uma stack de 4 shards volta ao modo N=1, que lê a chave
   `hb:strategy:shadow` sem sufixo — e essa chave **não existe mais** (`EXISTS` = 0, confirmado
   ao vivo no §1) desde que o worker foi shardado, então o portão recusa com `heartbeat_missing`
   em vez de aceitar silenciosamente uma leitura da topologia errada.
