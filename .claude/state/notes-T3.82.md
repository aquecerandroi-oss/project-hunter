# notes-T3.82 — Universo de pesquisa do Shadow Lab (≥ 90 dias de `candles_1m`)

Brief: `.claude/state/brief-T3.82-universo-de-pesquisa.md`. Aprovação do Everton, 2026-09-10
19:1x BRT: "boaaa perfeito".

## 1. Desenho

- Regra pura: `hunter_strategy_worker.universe._is_eligible(min_open_time, as_of, min_history_days)`
  — `min_open_time <= as_of - min_history_days dias` (inclusivo, `<=`), `None` nunca elegível.
- Query única (`load_universe_snapshot`): `GROUP BY (exchange, symbol)` sobre `markets LEFT JOIN
  candles` (timeframe `1m`, `is_final=true`), filtrado a `market_type='perpetual' AND
  is_monitored=true`. Uma leitura por hora por processo, não por bar — decisão registrada em
  `universe.py` (GROUP BY simples, não `LATERAL ... LIMIT 1`; ~200 mercados/hora não é o orçamento
  que a T3.74g protege).
- `UniverseCache`: TTL de 1 h fixo (`CACHE_TTL_S`), em processo (não Redis) — razão no docstring do
  módulo e em `docs/PIPELINE.md` §6b: a resposta não precisa de acordo entre shards, e uma query/h
  é mais barata que um round-trip de Redis por barra. Loader injetável
  (`_load_via_session`, default) para que os testes de unidade nunca abram sessão real.
- Falha de reload: mantém o último snapshot bom, loga aviso, e o relógio do TTL avança mesmo assim
  (uma base fora do ar é tentada de novo uma vez por hora, não uma vez por barra).
- Porta: `hunter_strategy_worker.pre_dispatch.refuse_before_dispatch` — unifica a recusa de shard
  (T3.74f) e a recusa de universo (T3.82) num único ponto, chamado por `run_consumer` **antes** de
  `BarDispatcher.submit`. `ack_fn` é passado por parâmetro (não importado dentro do módulo) para
  preservar o monkeypatch que os testes existentes (`test_consumer_sharding.py`,
  `test_reclaim_dedup.py`) já faziam em `consumer_mod.ack`.
- Config: `ShadowConfig.universe_min_history_days` (padrão 90, `0` desliga), env
  `SHADOW_UNIVERSE_MIN_HISTORY_DAYS`.
- Métrica: reaproveita `hunter_shadow_bars_skipped_total{reason="universe_history"}` (contador já
  existente, só um `reason` novo).
- Heartbeat: `universe_size`/`universe_total` (por shard, `ConsumerHealth`) +
  `universe_min_history_days` (sempre presente, mesmo desligado) em `hb:strategy:shadow[:{i}of{N}]`.
- API: `GET /api/v1/system/latency` ganhou `research_universe: {markets_in_universe,
  markets_total, min_history_days} | null` — somado entre shards (cada shard é uma fatia disjunta
  de símbolos), `null` quando nada publicou os campos ainda (worker não implantado, ou porta
  desligada).

## 2. Orçamento de linhas — por que existem `claim_idle.py`, `consumer_health.py`, `pre_dispatch.py`

`consumer.py` e `config.py` já estavam exatamente nos 350 do orçamento (confirmado via
`git show <HEAD>:<path> | wc -l`, 350 e 350). Qualquer adição líquida estourava o limite. Em vez de
comprimir prosa não relacionada à tarefa, segui o precedente já registrado no rodapé de
`consumer.py` ("`outcome_sweep`... split out when the bar-dispatch work above grew past this
file's own budget"):

- `hunter_strategy_worker.consumer_health` — só a dataclass `ConsumerHealth` (estado que
  `heartbeat.py`/`main.py` já importam de fora, não lógica do laço de consumo).
- `hunter_strategy_worker.pre_dispatch` — as duas recusas antes do despachante (shard + universo).
- `hunter_strategy_worker.claim_idle` — `EXPECTED_BAR_COST_S`/`CLAIM_IDLE_MS_CEILING`/
  `default_claim_idle_ms` (a aritmética de um campo, não o dataclass `ShadowConfig` em si);
  `config.py` reexporta os três nomes, então `test_claim_idle_ms.py` não mudou nada.

Resultado (`uv run python infra/scripts/check_file_size.py`): `scanned 627 files; 0 over budget, 0
grandfathered`.

## 3. Testes existentes ajustados (comportamento default mudou)

`ShadowConfig()` agora tem `universe_min_history_days=90` por padrão. Três testes que chamam
`run_consumer` com `factory=None` e payloads `market_type=perpetual` passaram a ser recusados por
`universe_history` (a query real falha com `factory=None`, cai no fallback fail-closed do primeiro
load — snapshot vazio). Corrigido passando `ShadowConfig(universe_min_history_days=0)` nesses três
pontos, já que nenhum deles testa o portão de universo:

- `services/strategy-worker/tests/test_consumer_sharding.py`
- `services/strategy-worker/tests/test_reclaim_dedup.py`
- `services/strategy-worker/tests/test_shard_dispatch_equivalence.py` (integration; mercados de
  fixture não têm 90 dias de histórico)

## 4. Comandos e saídas reais

```
$ uv run python infra/scripts/check_file_size.py
scanned 627 files; 0 over budget, 0 grandfathered

$ uv run ruff check services/strategy-worker/hunter_strategy_worker/
All checks passed!

$ uv run pyright services/strategy-worker/hunter_strategy_worker/
0 errors, 0 warnings, 0 informations

$ uv run pytest services/strategy-worker/tests -m unit -q
434 passed, 383 deselected in 36.01s

$ uv run pytest services/strategy-worker/tests/test_universe_gate.py -q -m integration
1 passed in 25.05s

$ uv run pytest apps/api/tests/unit/test_system_latency.py -q
12 passed in 0.51s

$ uv run pytest apps/api/tests/unit -k "system or latency" -q
51 passed, 547 deselected, 1 warning in 5.47s
```

## 5. Plano de medição (para o orquestrador, pós-deploy)

- **Avaliações por fechamento de 15 min esperadas:** 16 mercados × 10 versões = 160 (vs. ~2 000
  hoje, ~92 % de redução).
- **Confirmar ao vivo que os sinais do dia vêm só dos 16 elegíveis:**

```sql
select m.symbol, count(*) as sinais
from agent_signals s
join markets m on m.id = s.market_id
where s.emitted_at >= now() - interval '1 day'
group by m.symbol
order by sinais desc;
-- toda linha deve estar entre ARB, BNB, BTC, DASH, DOGE, ETH, LINK, NEAR, PROM, SAHARA, SOL, SUI,
-- TAO, UNI, XRP, ZEC
```

- **Confirmar `universe_history` contando de verdade:**

```
XINFO GROUPS market.candles.closed   -- lag não deve subir por causa do universo (ack rápido)
HGETALL hb:strategy:shadow           -- universe_size, universe_total, universe_min_history_days
```

- **Latência ponta a ponta:** `GET /api/v1/system/latency` → `research_universe.markets_in_universe`
  deve estabilizar em 16 (ou subir devagar, conforme mais mercados cruzam a linha de 90 dias).

## 6. Arquivos tocados por esta tarefa (git status --porcelain, restrito ao meu diff)

```
 M apps/api/hunter_api/schemas/latency.py
 M apps/api/hunter_api/services/latency.py
 M apps/api/tests/unit/test_system_latency.py
 M docs/PIPELINE.md
 M docs/plans/SHADOW-LAB.md
 M services/strategy-worker/hunter_strategy_worker/config.py
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/heartbeat.py
 M services/strategy-worker/tests/test_consumer_sharding.py
 M services/strategy-worker/tests/test_reclaim_dedup.py
 M services/strategy-worker/tests/test_shard_dispatch_equivalence.py
?? .claude/state/brief-T3.82-universo-de-pesquisa.md
?? .claude/state/notes-T3.82.md
?? obsidian/06-DECISIONS/2026-09-10-universo-de-pesquisa-90-dias.md
?? services/strategy-worker/hunter_strategy_worker/claim_idle.py
?? services/strategy-worker/hunter_strategy_worker/consumer_health.py
?? services/strategy-worker/hunter_strategy_worker/pre_dispatch.py
?? services/strategy-worker/hunter_strategy_worker/universe.py
?? services/strategy-worker/tests/test_universe.py
?? services/strategy-worker/tests/test_universe_gate.py
```

`docs/DESIGN.md`, `.claude/launch.json`, `infra/scripts/tests/test_seed_dry_run.py` e
`packages/core/tests/integration/test_schema_seed_and_partitions.py` aparecem modificados no
`git status` completo da árvore compartilhada — **não** foram tocados por esta tarefa (trabalho
concorrente de outro agente).

## 7. Concerns / limitações assumidas

- Não implantado na VPS por este agente (regra do brief: sem escrita/reinício de contêiner). A
  confirmação ao vivo (item 5 acima) é tarefa de quem fizer o deploy.
- `as_of` da checagem de universo é o `clock()` passado a `run_consumer` (produção: `utcnow()` real,
  não o `bar_close` da barra) — aproximação deliberada, documentada no docstring de `universe.py`:
  como o cache recarrega no máximo uma vez por hora, toda barra checada contra um snapshot está no
  máximo uma hora "à frente" do instante em que o snapshot foi tirado, e a retenção de 90 dias de
  `candles_1m` (DATABASE.md §1.3) garante que, uma vez elegível, um mercado nunca deixa de ser
  (o corte mais antigo sobrevivente da retenção nunca fica mais velho que a janela).
- A query de universo (`GROUP BY`/`MIN` simples, sem `LATERAL ... LIMIT 1`) roda uma vez por hora
  por processo — não otimizada para um `candles` muito maior do que os ~200 mercados × 90 dias de
  hoje; registrado no docstring de `load_universe_snapshot` como tradeoff assumido, não escondido.
