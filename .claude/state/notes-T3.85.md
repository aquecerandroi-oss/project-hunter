# notes-T3.85 — Redis sem teto, 12,57 GiB / 2 014 chaves

Inspeção read-only na VPS (`hunter-vps`, container `hunter-redis-1`) em
2026-09-11, ~08h18-08h37 UTC (05h18-05h37 America/Sao_Paulo). Todos os
comandos abaixo foram `redis-cli` de leitura (`INFO`, `CONFIG GET`, `KEYS`,
`SCARD`, `MEMORY USAGE`, `XLEN`, `XINFO`, `--bigkeys`) ou `docker
inspect`/`free -h` no host — nenhuma escrita, nenhum `XTRIM`, nenhum `CONFIG
SET`, nenhum container parado ou recriado.

## 1. Sintoma (herdado da T3.83)

```
$ docker exec hunter-redis-1 redis-cli INFO memory
used_memory_human:12.57G
maxmemory:0
maxmemory_policy:noeviction        # já era noeviction antes desta tarefa
$ docker exec hunter-redis-1 redis-cli INFO keyspace
db0:keys=2014,expires=1315,avg_ttl=129741614,subexpiry=0
$ docker exec hunter-redis-1 redis-cli INFO persistence
rdb_changes_since_last_save:3132929
rdb_bgsave_in_progress:1
rdb_last_bgsave_time_sec:161
rdb_saves:2467
aof_enabled:1
aof_current_size:13257140494
$ docker exec hunter-redis-1 redis-cli CONFIG GET save
3600 1 300 100 60 10000
$ docker exec hunter-redis-1 redis-cli CONFIG GET appendfsync
everysec
$ docker inspect hunter-redis-1 --format 'Memory={{.HostConfig.Memory}}'
Memory=0        # sem limite de container — só o limite do host
$ free -h
Mem: 47Gi total, 18Gi used, 21Gi free, 7.9Gi buff/cache, 28Gi available
Swap: 4.0Gi total, 0B used
```

## 2. `--bigkeys` (amostra quase completa: 2012/2014 chaves)

```
684 lists  1 146 344 items (avg 1675.94)     -- mkt:*:trades / candles:1m (LTRIM, saudável)
446 hashs  5 112 fields (avg 11.46)          -- feat:*, hb:*, scan:* (TTL/tamanho fixo, saudável)
13 streams 375 566 entries (avg 28889.69)    -- MAXLEN em vigor, saudável (ver §3)
824 strings 1 543 008 bytes (avg 1872.58)    -- scan:state:*, feat:* (pequeno, saudável)
44 sets    215 379 602 members (avg 4 894 990.95)  -- hunter:processed:* -- AQUI
1 zset     159 members                       -- radar:scores, saudável
```

## 3. Streams — MAXLEN confirmado em vigor (não é a causa)

`XLEN` + `MEMORY USAGE` de cada uma das 19 streams do `PIPELINE.md` §10:

| Stream | XLEN | MAXLEN alvo | MEMORY USAGE |
|---|---:|---:|---:|
| `market.ticks` | 100 003 | 100k | 65,4 MB |
| `market.candles.closed` | 50 000 | 50k | 58,2 MB |
| `market.derivatives` | 20 004 | 20k | 11,6 MB |
| `market.liquidations` | 20 007 | 20k | 10,4 MB |
| `features.updated` | 100 003 | 100k | 51,2 MB |
| `opportunities.updated` | 50 005 | 50k | 33,1 MB |
| `anomalies.detected` | 20 004 | 20k | 13,2 MB |
| `shadow.signals.emitted` | 9 315 | 20k | 9,7 MB |
| `market.candles.backfilled` | 5 003 | 5k | 2,6 MB |
| `market.backfill.requested` | 793 | 5k | 0,5 MB |
| `market.universe.changed` | 329 | 1k | 0,13 MB |
| `regime.changed` | 60 | 1k | 0,03 MB |
| `market.funding.backfilled` | 49 | 1k | 0,02 MB |
| `signals.emitted`, `proposals.decided`, `executions.completed`, `positions.updated`, `risk.events`, `kill_switch.changed`, `audit` | 0 | — | — |

Total: **~256 MB**, ~2% do `used_memory`. Todas batem com o alvo de
`DEFAULT_MAXLEN` (`packages/core/hunter_core/events/streams.py`) dentro da
margem do trim aproximado (`MAXLEN ~`). Conclusão: **as streams nunca foram o
problema** — a hipótese do brief (streams sem `MAXLEN`) não se confirmou.

`XINFO GROUPS` (lag): `market.ticks`/`market.derivatives`/`market.liquidations`/
`market.universe.changed` — lag 0, pending 0, 40 consumers cada (scanner-worker,
4 shards × 10 réplicas do enunciado de teste). `market.candles.closed`:
`scanner-worker.market.candles.closed` lag 25 516, pending 19 245 (fora do
escopo desta tarefa — registrado, não investigado); `strategy-worker.shadow`
(grupo órfão, sem sufixo `.NofM`) lag 50 000, pending 36 — parece resquício de
um grupo pré-sharding, também fora do escopo.

## 4. `hunter:processed:*` — a causa real

`packages/core/hunter_core/events/processed.py` grava um `SADD` por
`event_id` processado num `SET` por dia por grupo consumidor
(`hunter:processed:{group}:{YYYYMMDD}`), para dar idempotência a efeitos
duráveis. O próprio docstring do módulo estimava a memória a partir de "~700k
eventos/dia" do market-worker. `SCARD`+`MEMORY USAGE` de todas as 44 chaves
que existiam (comando único, foreground, `timeout 280`):

| Chave (grupo:dia) | SCARD | MEMORY USAGE |
|---|---:|---:|
| `scanner-worker.market.ticks:20260908` | 44 429 274 | 3 380 344 608 (3,15 GB) |
| `scanner-worker.market.ticks:20260909` | 47 145 610 | 3 822 625 568 (3,56 GB) |
| `scanner-worker.market.ticks:20260910` | 47 997 135 | 3 877 123 168 (3,61 GB) |
| `scanner-worker.market.ticks:20260911` (parcial) | 15 737 924 | 1 208 557 152 (1,13 GB) |
| `scanner-worker.market.derivatives:20260908` | 16 364 671 | 1 181 556 832 (1,10 GB) |
| `scanner-worker.market.derivatives:20260909` | 17 256 389 | 1 507 062 240 (1,40 GB) |
| `scanner-worker.market.derivatives:20260910` | 17 276 430 | 1 307 018 272 (1,22 GB) |
| `scanner-worker.market.derivatives:20260911` (parcial) | 6 019 181 | 485 891 040 (0,45 GB) |
| `strategy-worker.shadow*` (5 chaves, 4 shards + 1 órfã) | 106k–388k cada | 7,9–30,1 MB cada |
| `scanner-worker.market.candles.closed:*` (4 dias) | 77k–389k | 6,0–29,1 MB cada |
| `scanner-worker.market.liquidations:*` (4 dias) | 7,6k–39k | 0,6–3,3 MB cada |
| `market-worker.backfill.binance.*of4:*`, `market.universe.changed:*` | ≤ 102 | ≤ 4,2 KB cada |

**Ticks + derivatives sozinhos somam ~17,6 GB de `MEMORY USAGE`** (a soma
excede o `used_memory` medido — `MEMORY USAGE` de sets grandes superestima
via amostragem interna do comando; a ordem de grandeza é o que importa: essas
duas famílias são, na prática, toda a memória do Redis).

**Causa raiz.** `market.ticks` roda a ~45-48M eventos/dia (não ~700k como o
docstring assumia) e `market.derivatives` a ~16-17M/dia — porque cada tick é
uma atualização de preço por mercado monitorado, não um evento agregado. O
guarda de idempotência é necessário para efeitos duráveis (uma linha em
Postgres), mas essas três streams (`market.ticks`, `market.derivatives`,
`market.liquidations`) já eram documentadas, antes desta tarefa, como sem
efeito durável — `hunter_scanner_worker/consumers.py`: "Ticks, derivatives and
liquidations are pure notifications with no durable effect of their own", e
`PIPELINE.md` §10b classifica `market.ticks` como *efêmero*. O `SET` diário
crescia mesmo assim, porque `consume_batches`/`ack_many` sempre gravavam,
sem essa distinção.

## 5. Correção de código

- `packages/core/hunter_core/events/processed.py`: `ack_many(..., record:
  bool = True)`. `record=False` só faz `XACK`, sem `SADD`/`EXPIRE`.
- `packages/core/hunter_core/events/consume.py`: `_unprocessed(..., track:
  bool = True)` e `consume_batches(..., track: bool = True)`. `track=False`
  pula o `SMISMEMBER` e entrega tudo que foi decodificado.
- `services/scanner-worker/hunter_scanner_worker/consumers.py`:
  `run_batch_consumer(..., track: bool = True)`, repassado a
  `consume_batches` e como `record=` a `ack_many`.
- `services/scanner-worker/hunter_scanner_worker/main.py`: as três chamadas
  de `run_batch_consumer` para `MARKET_TICKS`/`MARKET_DERIVATIVES`/
  `MARKET_LIQUIDATIONS` passam `track=False`. `market.candles.closed`
  (`run_stream_consumer`, ack por mensagem após persistência) e todo o resto
  do sistema não mudam — o guarda continua exatamente como era para qualquer
  stream com efeito durável.
- Testes novos: `packages/core/tests/unit/test_events_consume_batch.py`
  (4 testes: `track=False` entrega até evento marcado, zero round trips do
  guarda, `record=False` não grava `SADD`/`EXPIRE`, `record=False` de lista
  vazia não toca o servidor) e
  `services/scanner-worker/tests/test_consumers.py` (1 teste: `track=False`
  chega tanto em `consume_batches` quanto em `ack_many` como `record=`).

Todos os testes tocados passaram (`pytest packages/core/tests/unit -k
"events or outbox or consume or processed"` — 61 passed; `pytest
services/scanner-worker/tests -m unit` — 56 passed, 1 falha pré-existente e
não relacionada, ver §7). `ruff format --check`, `ruff check` e `pyright`
limpos nos arquivos tocados; `check_file_size.py` — 629 arquivos escaneados,
0 acima do orçamento (todos os arquivos tocados ≤ 350 linhas:
`consume.py` 350, `consumers.py` 332, `main.py` 350, `processed.py` 204).

## 6. Correção de configuração (compose, não aplicada na VPS)

`infra/vps/docker-compose.prod.yml`, serviço `redis`: `--maxmemory 4gb
--maxmemory-policy noeviction` (política já era `noeviction` por padrão de
fábrica; faltava o teto). Justificativa e detalhe em `docs/DEPLOYMENT.md`
§9.3 e §9.7. **Não implantado** — exige `docker compose ... up` (recria o
container `redis`), proibido nesta tarefa ("nunca parar/recriar
containers"). Fica para o orquestrador decidir quando aplicar
(`MARKET_SHARDS=... bash infra/vps/compose.sh update`, depois do merge).

## 7. Proposta de faxina única — NÃO EXECUTADA

Runbook completo (comando genérico + a lista concreta de 2026-09-11) em
`docs/DEPLOYMENT.md` §9.7. Resumo: as chaves `hunter:processed:*` datadas de
`20260908` e `20260909` já estão fora da janela de leitura do guarda
(`PROCESSED_DAYS=2` = hoje + ontem) — apagá-las não perde nenhuma linha de
Postgres, é lixo de transporte que o TTL (3 dias) ainda não coletou.
`UNLINK` (não `DEL`) por ser não-bloqueante em sets de dezenas de milhões de
membros. Total estimado liberado: **~9,3 GiB**. Não executado por regra
explícita da tarefa ("DO NOT RUN") — decisão do Everton.

## 8. Observação fora de escopo (registrada, não investigada)

`XINFO GROUPS market.candles.closed` mostrou um grupo órfão
`strategy-worker.shadow` (sem sufixo `.NofM`, diferente dos 4 grupos
`strategy-worker.shadow.{0..3}of4` ativos) com lag 50 000 e pending 36 — não
mexi nisso, é resquício de sharding anterior e não faz parte do achado da
T3.85.

## 9. `git status --porcelain` — apenas os arquivos desta tarefa

```
 M docs/DEPLOYMENT.md
 M infra/vps/docker-compose.prod.yml
 M obsidian/07-BUGS/Open Bugs.md
 M packages/core/hunter_core/events/consume.py
 M packages/core/hunter_core/events/processed.py
 M packages/core/tests/unit/test_events_consume_batch.py
 M services/scanner-worker/hunter_scanner_worker/consumers.py
 M services/scanner-worker/hunter_scanner_worker/main.py
 M services/scanner-worker/tests/test_consumers.py
?? .claude/state/brief-T3.85-redis-sem-teto.md
?? .claude/state/notes-T3.85.md
```

(O restante de `git status --porcelain` na árvore — `.claude/launch.json`,
`docs/DESIGN.md`, `infra/scripts/seed_reference.py`,
`packages/core/hunter_core/strategies/*`, `services/strategy-worker/...` e
dezenas de `.claude/state/**` não listados acima — é trabalho de outros
agentes em voo na mesma árvore compartilhada; não toquei nenhum desses
arquivos.)

## 10. Nota sobre a T3.83 (não fechada por esta tarefa)

O `BGSAVE`/fork longo que causava os timeouts de leitura da T3.83 é
consequência do dataset de ~13 GB, não uma causa independente. Depois do
deploy da correção de código e da faxina (quando aprovada), o dataset deve
cair para a ordem de ~300 MB e o fork deve voltar a levar frações de segundo
— o que deve resolver o sintoma da T3.83 como efeito colateral. Isso não foi
medido ao vivo (exigiria aplicar as duas mudanças, fora do escopo "read-only
+ não implantar" desta tarefa) — fica registrado como previsão, não como
resultado confirmado.
