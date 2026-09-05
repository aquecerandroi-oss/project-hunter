# Kit de revisão — T1.6b (performance do market-worker)

Meta do orquestrador (registrada em `.claude/state/review-T1.6.md`, "Decisão do orquestrador sobre
o HIGH-1"): **200 mercados com `markets_ok` >= 95% e < 70% de um core por shard**, zero eventos
descartados, `market_persist_lag` < 10 s, `/system/market-status` correto.

Perfil que justifica cada mudança: `.claude/state/t16b-profile.md` (dados brutos em
`.claude/state/profile/raw-50.txt` e `raw-200.txt`).

## Tarefas da onda

| Tarefa | Dono | Arquivos | Brief |
|---|---|---|---|
| T1.6b-A — caminho quente do adaptador | `exchange-integration-specialist` | `packages/exchange-adapters/**` | `.claude/state/brief-T1.6b-A-adapter.md` |
| T1.6b-B — caminho quente do worker | `backend-specialist` | `services/market-worker/hunter_market_worker/{streaming,hot_state,ingest,persist,queues}.py`, `tests/**`, `benchmarks/**`, `packages/core/hunter_core/runtime.py` | `.claude/state/brief-T1.6b-B-worker.md` |
| T1.6b-C — sharding por símbolo | `backend-specialist` | `services/market-worker/hunter_market_worker/{config,universe,heartbeat,main}.py`, `packages/core/hunter_core/{settings,observability}.py`, `infra/docker/**` | `.claude/state/brief-T1.6b-C-sharding.md` |

Conjuntos disjuntos. `apps/**` é proibido nas três — o `/system/market-status` tem de continuar
funcionando **sem** mudança na API.

## Itens de aceite (verificados por comando, não por declaração)

### Comuns às três
- [ ] `uv run pytest services/market-worker packages/exchange-adapters -q -p no:cacheprovider` verde
- [ ] `uv run pytest packages/core/tests/unit -q -p no:cacheprovider` verde
- [ ] `uv run ruff check` / `ruff format --check` / `uv run pyright` nos pacotes tocados
- [ ] `uv run python infra/scripts/check_file_size.py` → 0 acima do orçamento
- [ ] `docker compose -f infra/docker/docker-compose.yml build api` verde
- [ ] Nenhum `float` para dinheiro, nenhum datetime naive, nenhum segredo, nenhum `print`
- [ ] Benchmark antes/depois com saída real (sem isso a alegação de performance é rejeitada)

### T1.6b-A
- [ ] `event_queue`: descarte O(1); kline final nunca é vítima; backpressure quando só há finais;
      `dropped_events` continua contado na conexão de origem; FIFO estrita preservada
- [ ] `model_construct` não perdeu garantia: `ts` UTC-aware, `qty >= 0`, bids desc / asks asc
      ainda levantam `MalformedMessage`; `received_at` populado
- [ ] `orjson`: frame malformado continua contado em `malformed_count` e nunca propaga
- [ ] `depth20@500ms`: `channel_for_stream_name` resolve os dois nomes; teste dos dois sentidos
- [ ] `to_decimal` continua recusando `float`/`bool`/`None`

### T1.6b-B
- [ ] `consume_once` sem task/timer por evento; `restart_stream` ainda funciona **com o stream
      silencioso**; `update_subscriptions` ainda aplica o diff; `StopAsyncIteration` → `RuntimeError`
- [ ] Script Lua do hot state: uma ida ao Redis; fallback `NOSCRIPT` → `EVAL` testado (o Redis
      reinicia — a T1.6 provou); campos `ts`/`funding_ts`/`mark_ts`/`oi_ts` com nome e formato
      inalterados (a API lê)
- [ ] Coalescência: um pipeline por ciclo para todos os símbolos; staleness extra <= 250 ms,
      declarada; kline final nunca coalescido/perdido; flush no shutdown
- [ ] `push_trade`: dedupe em memória limitada, liberada quando o símbolo sai do universo;
      reinício frio não duplica trade no Redis
- [ ] `build_tick_payload` byte-idêntico ao atual (contrato do `rt:market:*` que o front lê)
- [ ] uvloop com import guardado; Windows inalterado

### T1.6b-C
- [ ] `hb:market:binance` (chave canônica que a API lê) continua correta e agregada
- [ ] Um shard morto degrada honestamente (não some da conta, não mente `connected`)
- [ ] Universo: sem divergência danosa entre shards; líder por lock com TTL, sem split-brain que
      cause dupla escrita de candle
- [ ] Rate limit REST continua respeitado com N processos (o token bucket já é Redis-distribuído)
- [ ] `/ready` por shard; healthcheck do Compose por shard
- [ ] Métrica de saturação exposta e documentada em `obsidian/09-OPERATIONS/Monitoring.md`

## Revisores a despachar quando cada relatório chegar
- `code-reviewer` em cada tarefa (sempre)
- `exchange-integration-specialist` cruzado na T1.6b-B (contrato do `stream()`)
- `backend-specialist` cruzado na T1.6b-A
- `security-reviewer` na T1.6b-C (compose, novos serviços, cardinalidade de labels de métrica)
- `database-architect` na T1.6b-C **se** o sharding mudar quem escreve em Postgres
- Astra em todos os diffs: `bash infra/scripts/astra.sh ask review-T1.6b-<x> "..."`
  (chamar com `< /dev/null`: sem isso o `codex` fica preso em "Reading additional input from stdin")

## Prova final (executada pela Sexta-feira, não pelos implementadores)
1. `docker compose build api` + subir a stack com 200 mercados (arquivo compose temporário, não
   commitado) por 10 minutos.
2. Coletar: `docker stats` por shard, `markets_ok`/`markets_degraded` do `/system/market-status`,
   `dropped_events` do heartbeat, `market_persist_lag`, e um `py-spy record` de 90 s por shard.
3. Critério: `markets_ok` >= 95%, `dropped_events` = 0, CPU < 70% de um core por shard,
   `market_persist_lag` < 10 s.
4. Se fechar, `docker-compose.override.yml` local passa a 200; se não, fica no maior número
   sustentado **medido**, escrito em `t16b-profile.md`, e o [[Market Collector]] fica `parcial`.

## Tarefa D — pendente, despachar assim que a T1.6b-A entregar
**Cooldown de 429 por IP não é distribuído** (`packages/exchange-adapters/hunter_exchanges/rate_limit.py:114`).
Achado da Astra na revisão de sharding. Cenário de falha concreto: o shard A recebe `Retry-After`
da Binance e para; os outros N-1 shards continuam chamando do **mesmo IP** porque o cooldown é
estado local do processo — é exatamente assim que um IP sai de `429` para `418` (ban). O token
bucket já é distribuído em Redis; o cooldown não é.
**Bloqueia rodar N shards contra a Binance real.** Dono: `exchange-integration-specialist`,
arquivo `packages/exchange-adapters/hunter_exchanges/rate_limit.py` (+ testes). Não pode ser
despachado agora porque a T1.6b-A está com o pacote aberto.

## Critérios da prova final (endurecidos pela Astra, 2026-09-05)
Não aceitar CPU média + heartbeat verde. Exigir, na mesma corrida:
- **200 mercados no denominador** (não um universo reduzido chamado de 200);
- cobertura `markets_ok / 200` >= 95% — soma dos shards, não média das porcentagens;
- **cada** shard abaixo de 70% de um core (o pior shard decide, não a média);
- profundidade de fila e lag estáveis (sem tendência de alta);
- **zero incremento** dos contadores de descarte, atravessando um refresh de universo, um ciclo de
  recovery e uma reconexão;
- `max_connections` do Postgres compatível com N shards × pool por processo.
