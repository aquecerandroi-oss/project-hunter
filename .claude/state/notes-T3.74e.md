# T3.74e — o atraso pós-deploy não é fila, é a rajada do universo inteiro contra uma concorrência pequena demais

Brief salvo em `.claude/state/brief-T3.74e-atraso-constante.md`. Medição ao vivo na VPS
(`hunter-vps`), somente leitura (`begin ... read only`/`XRANGE`/`HGETALL`/`docker exec ... curl`),
nenhum contêiner tocado, nenhuma escrita, nenhum `git pull`. Correção local (config + testes),
**não implantada**. Horários em Brasília (UTC−3) com o UTC ao lado; hoje é 2026-09-10.

## 0. Resumo executivo

O brief presumia uma banda apertada e constante de ~55 s. A medição completa (não só a amostra de
8 sinais do heartbeat) mostra algo mais preciso: **um espalhamento de 4,9 s a 61,2 s dentro da
mesma barra fechada**, proporcional à posição de cada mercado na fila do `BarDispatcher`
(T3.74c). O lado do `market-worker` (exchange → vela durável no stream) está saudável — 0,5-2 s,
dentro do orçamento (T3.79/T3.81, já implantados). O gargalo é inteiramente dentro do
`strategy-worker`: `ShadowConfig.worker_concurrency` (padrão 8, T3.74c) drena rajadas de
~200 mercados simultâneos a `≈ trabalho_total / 8`, e o trabalho total medido de uma rajada real é
≈ 325 s → ≈ 41 s de drenagem no pior caso, batendo com o que foi observado ao vivo. Correção: subir
`worker_concurrency` para 32 e o pool de conexões do serviço para 20+20, projetando ≈ 10 s.

## 1. Onde os segundos estavam

### 1.1 O lado do `market-worker` está saudável (T3.79/T3.81 já implantados)

```
$ timeout 60 ssh hunter-vps "docker exec hunter-market-worker-1 python -c \"import urllib.request; \
  print(urllib.request.urlopen('http://localhost:8001/metrics').read().decode())\" | grep -i 'ingest_lag\|flush_lag'"
```
`hunter_market_ingest_lag_seconds{kind="candle"}`: 1225/1232 amostras ≤ 0,25 s, todas ≤ 5 s.
`hunter_candle_flush_lag_seconds`: 641/1232 ≤ 1,0 s, 865/1232 ≤ 2,0 s, todas ≤ 5 s (sum=1840,5,
count=1232 → média ≈ 1,49 s). O hop "exchange → vela durável no nosso stream" está dentro do
orçamento de <1s/<1s do §6b/§6c da T3.79/T3.81 — **descartado como causa**.

`parse_kline_ws` (`hunter_exchanges/binance/streams.py:282`) usa `is_final=bool(k["x"])` — o próprio
flag de fechamento da Binance, nunca inferido pela chegada da vela seguinte. Confirmado no código,
não só na métrica: a hipótese "espera a próxima vela para confirmar o fechamento" do brief está
**descartada**.

### 1.2 As métricas por estágio do `strategy-worker`: todas rápidas, somadas não chegam a 2 s

```
$ timeout 60 ssh hunter-vps "docker exec hunter-strategy-worker-1 python -c \"import urllib.request; \
  print(urllib.request.urlopen('http://localhost:8001/metrics').read().decode())\" | grep -A 20 hunter_shadow_stage_seconds"
```
Uma rajada real de 200 mercados (`market_lookup`/`family_preload` count=200 no processo desde o
boot, ~18 min antes):

| stage | count | sum (s) | média (s) |
|---|---|---|---|
| queue_wait | 4280 | 10995,9 | 2,57 (dominado por velas M1 sem versão devida; a maioria ≤0,1s) |
| market_lookup | 200 | 32,23 | 0,16 |
| family_preload | 200 | 43,47 | 0,22 |
| context_load | 1800 | 237,36 | 0,13 (por versão devida; ~9 versões/mercado em média) |
| evaluate | 1800 | 11,25 | 0,006 |
| persist | 8 | 1,10 | 0,14 (só as 8 que dispararam) |

**Soma total de uma rajada de 200 mercados**: 32,23+43,47+237,36+11,25+1,10 ≈ **325,4 s** de trabalho
real, medido sob a própria contenção da rajada (não um número de laboratório).

`hunter_shadow_decision_lag_seconds` (histograma fim-a-fim, `decision_at - bar_close`, observado só
nas 8 decisões persistidas nesta janela): todas as 8 caem no bucket `(34, 60]` — sum=436,36,
count=8 → média 54,5 s. Isso é **maior** que qualquer estágio somado, confirmando que o tempo
"perdido" não está em nenhum estágio individual: está em quanto tempo uma barra fica **esperando um
lugar no semáforo** do `BarDispatcher` antes de qualquer estágio começar a contar.

### 1.3 SQL contra `agent_signals`: o espalhamento completo dentro da mesma barra

```sql
-- infra/scripts/sql/research/2026-09-10-t374e-q01-signals-per-bar.sql
select id, ex.code, m.symbol, m.market_type,
       (supporting_features->>'observation_ts')::timestamptz as observation_ts,
       emitted_at,
       extract(epoch from (emitted_at - (supporting_features->>'observation_ts')::timestamptz)) as lag_s
from agent_signals s join markets m ... join exchanges ex ...
where emitted_at > now() - interval '25 minutes'
order by emitted_at desc limit 30;
```
Rodado às 18:49Z (15:49 BRT) contra a barra `observation_ts = 2026-09-10 18:45:00Z` (15:45 BRT) —
27 decisões, todas da mesma barra:

| symbol | emitted_at (UTC) | lag_s |
|---|---|---|
| BIRBUSDT | 18:46:01.18 | 61,18 |
| BIRBUSDT | 18:46:00.22 | 60,22 |
| BIRBUSDT | 18:45:59.79 | 59,79 |
| BIRBUSDT | 18:45:59.38 | 59,38 |
| BIRBUSDT | ... (mais 4 linhas) | 58,98 → 57,08 |
| CHIPUSDT | 18:45:40.55 | 40,55 |
| PROMUSDT | 18:45:37.13 → 18:45:32.93 (8 linhas) | 37,13 → 32,93 |
| TUTUSDT | 18:45:20.27 | 20,27 |
| ORDERUSDT | 18:45:09.31 → 18:45:04.93 (7 linhas) | 9,31 → 4,93 |
| MUBARAKUSDT | 18:45:07.39 | 7,39 |

**Não é uma banda apertada em 55 s — é um espalhamento de 4,9 s a 61,2 s**, exatamente o formato de
"mercados perto do início da fila do dispatcher decidem em segundos, mercados perto do fim decidem
no fim da rajada inteira". A amostra de 8 do `hb:strategy:shadow` (que só guarda os últimos 500
sinais em memória, §1.2) pegou a cauda alta (BIRBUSDT, o último a ser atendido) e não o resto —
por isso o brief media "uma banda fixa".

### 1.4 O padrão se repete a cada fronteira, com magnitude variável (3h de histórico)

```sql
-- infra/scripts/sql/research/2026-09-10-t374e-q02-band-recurs-per-boundary.sql
```
| observation_ts (UTC) | sinais | min_lag_s | max_lag_s |
|---|---|---|---|
| 19:00:00 | 1 | 13,6 | 13,6 |
| 18:45:00 | 27 | 4,9 | 61,2 |
| 18:30:00 | 8 | 52,0 | 57,1 |
| 18:00:00 | 5 | 5,8 | 122,3 |
| 17:45:00 | 15 | 2,4 | 132,6 |
| 17:30:00 | 11 | 24,1 | 67,7 |
| 17:15:00 | 5 | 17,4 | 102,6 |
| 17:00:00 | 5 | 17,0 | 163,1 |
| 16:45:00 | 32 | 88,2 | 158,2 |
| 16:30:00 | 2 | 90,9 | 115,7 |
| 16:15:00 | 1 | 13,3 | 13,3 |
| 16:00:00 | 2 | 26,0 | 76,5 |

O deploy do T3.74c/d + T3.81 foi às 15:25 BRT / 18:25Z; as janelas 16:00Z-18:00Z são portanto
**anteriores** ao deploy (rodando o dispatch totalmente serial de antes do T3.74c ou uma versão
anterior — daí o `max_lag` até 163 s, coerente com o espalhamento sem limite já documentado em
`notes-T3.74c.md`/`notes-T3.74.md`). Só 18:30Z e 18:45Z são pós-deploy: 18:30Z ficou entre 52-57 s
(poucos sinais, 8, todos no fim de uma rajada pequena), 18:45Z entre 4,9-61,2 s (rajada maior, 27
sinais, mostrando a rampa completa). **Conclusão honesta**: mesmo pós-deploy do T3.74c/d, o
`max_lag` por janela continua variável e ainda alto (até ~61 s nas duas amostras pós-deploy) —
o dispatcher de concorrência 8 não é suficiente para a rajada real do universo inteiro.

### 1.5 A aritmética que fecha a conta

Trabalho total de uma rajada (§1.2): ≈ 325,4 s. Com concorrência 8: `325,4 / 8 ≈ 40,7 s` de
drenagem no pior caso — bate com o teto observado (57-61 s, considerando alguma perda de eficiência
por agendamento do asyncio e contenção de conexões sob carga real, não o número idealizado). Isso
não é fila crescendo sem limite (T3.74 antes do T3.74c): é um **trabalho fixo por rajada, dividido
por uma concorrência fixa** — daí o teto mais previsível (mas ainda alto) do que o espalhamento
20-170 s+ de antes do T3.74c.

## 2. A correção — subir a concorrência e o pool de conexões junto

**`services/strategy-worker/hunter_strategy_worker/config.py`**:
- `ShadowConfig.worker_concurrency` (padrão) sobe de 8 para **32**, com a aritmética do §1.5 escrita
  na docstring: `325,4 / 32 ≈ 10,2 s`, dentro de `decision_lag_p95_alert_s` (30 s), perto de
  `decision_lag_p50_alert_s` (10 s).
- `load_config()`'s fallback de `SHADOW_WORKER_CONCURRENCY` também sobe de 8 para 32 — sem isso o
  processo real (que chama `load_config()`, não `ShadowConfig()` direto) continuaria em 8.
- **Novo**: `CLAIM_IDLE_MS_CEILING = 90_000` e `default_claim_idle_ms` agora aplica
  `min(worker_concurrency * EXPECTED_BAR_COST_S * 1000, CLAIM_IDLE_MS_CEILING)`. Sem o teto, a
  concorrência 32 levaria o `claim_idle_ms` derivado a 32 × 8,0 × 1000 = 256 000 ms — 85% de
  `consumer_stall_s` (300 000 ms), violando o "well under" que `ShadowConfig.claim_idle_ms` já
  documentava e que `test_claim_idle_ms.py::test_the_default_stays_well_under_the_consumer_stall_bound`
  já cobrava (`< metade do orçamento de stall`). 90 000 ms mantém ≈8x de margem sobre o pior caso
  real medido (§1.5, ~10-40 s) e fica em 30% do orçamento de stall — a mesma proteção, recalibrada
  para uma concorrência 4x maior.

**`infra/docker/docker-compose.yml`** e **`infra/vps/docker-compose.prod.yml`** (serviço
`strategy-worker` em cada um): `DB_POOL_SIZE: "20"` / `DB_MAX_OVERFLOW: "20"` (40 no total) — o
padrão compartilhado de `Settings` (5+5=10) é pequeno demais para concorrência 32; 40 mantém a
mesma proporção de folga (~1,25x) que 10/8 tinha antes, seguindo o mesmo padrão de override que o
`replay-worker` já usa no mesmo arquivo para o seu próprio pool menor. Confirmado que os dois
arquivos continuam válidos (`docker compose config strategy-worker`, ver §3).

**Postgres tem folga para isso**: `docker stats` no momento da medição mostrou `hunter-postgres-1`
em 21,81% de CPU (12 vCPUs disponíveis) e `pg_stat_activity` contava 33 conexões totais de todos os
serviços somados, contra `max_connections = 100` — subir o pool do `strategy-worker` em +30 deixa
folga confortável.

**Nada tocado nas sete camadas de fechamento** (`packages/core/hunter_core/strategies/**`),
nenhuma mudança em `is_final`/`close_time`/`observation_ts` (o carimbo já estava correto — é sempre
o fechamento teórico da barra, nunca a hora de chegada; a ressalva "stamp errado" do brief não se
aplica). `dispatch.py`/`consumer.py`/`decide.py` não foram tocados — o mecanismo do T3.74c já
estava certo, só dimensionado para uma rajada 25x menor do que a real.

## 3. Comandos e saídas reais

```
$ timeout 30 ssh hunter-vps "echo ok && date -u"
ok
Thu Sep 10 18:42:29 UTC 2026

$ timeout 60 ssh hunter-vps "docker ps --format '{{.Names}}\t{{.Status}}' | sort"
(12 contêineres, todos healthy/up — strategy-worker up 18 minutes)

$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli HGETALL hb:strategy:shadow"
decision_lag_p50_s 54.1   decision_lag_p95_s 56.2   evaluations_by_state {"not_triggered":1786,"triggered":13,"unavailable":1}
```
(métricas completas de `hunter_shadow_stage_seconds`/`hunter_shadow_decision_lag_seconds` e
`hunter_candle_flush_lag_seconds`/`hunter_market_ingest_lag_seconds`: ver tabelas do §1, coletadas
via `docker exec ... python -c "urllib.request.urlopen('http://localhost:8001/metrics')"` — sem
`curl` disponível dentro dos contêineres).

```
$ timeout 60 ssh hunter-vps "docker stats --no-stream"
hunter-postgres-1   21.81%   485.9MiB    (12 vCPUs no host — folga confirmada)
hunter-strategy-worker-1   0.59%   (fora de rajada no instante da amostra)
```

SQL (q01/q02, saídas completas no §1.3/§1.4):
```
$ timeout 90 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t374e-q01-signals-per-bar.sql
$ timeout 90 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t374e-q02-band-recurs-per-boundary.sql
```

Validação dos composes (sem subir nada, `docker compose config`, dev machine local — não a VPS):
```
$ POSTGRES_PASSWORD=x HUNTER_WS_URL=ws://x HUNTER_PUBLIC_URL=http://x HUNTER_SITE_ADDRESS=:80 \
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=x timeout 30 docker compose \
  -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml config strategy-worker \
  | grep 'DB_POOL_SIZE\|DB_MAX_OVERFLOW'
DB_MAX_OVERFLOW: "20"
DB_POOL_SIZE: "20"

$ HUNTER_WS_URL=ws://x HUNTER_PUBLIC_URL=http://x timeout 30 docker compose \
  -f infra/docker/docker-compose.yml config strategy-worker | grep 'DB_POOL_SIZE\|DB_MAX_OVERFLOW'
DB_MAX_OVERFLOW: "20"
DB_POOL_SIZE: "20"
```

Testes (TDD — os dois primeiros novos falharam antes da implementação, por `ImportError`, motivo
certo):
```
$ timeout 120 uv run pytest services/strategy-worker/tests/test_claim_idle_ms.py -q
8 passed in 0.39s   (6 antes desta tarefa — 2 novos + 1 valor atualizado)

$ timeout 200 uv run pytest services/strategy-worker/tests -q -m unit
384 passed, 377 deselected in 10.72s   (383 antes desta tarefa)

$ timeout 290 uv run pytest services/strategy-worker/tests/test_dispatch_benchmark.py -q -s
2 passed in 69.44s   (não usa o default de ShadowConfig -- concorrência passada explícita 1/4/8;
  confirma que a correção não muda nenhuma decisão real: byte-idênticas serial vs. concorrente,
  e p95 < 20s com um processo de replay concorrente hammering o mesmo Postgres)
```

Qualidade:
```
$ uv run ruff check services/strategy-worker/hunter_strategy_worker/config.py
All checks passed!

$ uv run ruff format --check services/strategy-worker/hunter_strategy_worker/config.py
1 file already formatted

$ uv run pyright services/strategy-worker/hunter_strategy_worker/config.py
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 620 files; 0 over budget, 0 grandfathered
  (config.py chegou a 352/350 na primeira versão da docstring -- enxugada para 348)
```

## 4. Ressalvas honestas

1. **Não implantado na VPS** (regra do brief): o número "depois" ao vivo (a nova projeção de ~10 s)
   depende do deploy do orquestrador e de uma nova leitura de `hb:strategy:shadow` +
   `agent_signals`. A projeção vem da aritmética do §1.5 sobre o trabalho medido, não de uma
   execução real com concorrência 32.
2. **O brief presumia uma "banda fixa de ~55 s"; a medição completa mostra um espalhamento de
   4,9-61,2 s dentro da mesma barra.** A amostra de 8 do heartbeat (últimos 500 sinais em memória)
   pegou só a cauda alta de uma rajada de 27 decisões — corrigido no relatório e nos documentos
   (`docs/PIPELINE.md`, `Open Bugs.md`).
3. **32 é uma escolha calibrada pelo trabalho medido numa única rajada (200 mercados, ~9 versões
   médias/mercado), não uma prova de que toda rajada futura terá esse mesmo custo.** Se o roster de
   versões ativas crescer, o mesmo cálculo (`total_burst_work_s / worker_concurrency`) deve ser
   refeito; o teste `test_the_new_default_projects_the_measured_burst_under_the_p95_alert` (novo)
   existe para que essa conta nunca fique implícita de novo.
4. **Se 10 s de mediana projetada ainda não for "instantâneo" o suficiente para o produto**, o
   próximo corte (não tentado aqui) é sharding em múltiplos processos (T3.74c §4) — a CPU do host
   tem folga (12 vCPUs, Postgres em 21,81%), mas subir a concorrência de um único processo Python
   asyncio além de ~32-40 começa a competir por GIL/scheduling em vez de I/O puro.
5. **As janelas 16:00Z-18:00Z de `q02` são anteriores ao deploy** (15:25 BRT/18:25Z) — não usadas
   como evidência do comportamento pós-fix, só para mostrar que o padrão antigo (espalhamento maior,
   até 163 s) continua reconhecível nelas.
6. **`EXPECTED_BAR_COST_S` (8,0 s) não foi revisto** — continua sendo o pior caso por *versão*
   dentro de um mercado (não afetado pela concorrência entre mercados), e a T3.74d já o calibrou
   coerentemente (`11 versões / 1,4 avaliação/s`). Só o multiplicador de `worker_concurrency` no
   `default_claim_idle_ms` precisava do teto novo.

## 5. Arquivos (git status --porcelain — só os meus)

```
 M docs/PIPELINE.md
 M infra/docker/docker-compose.yml
 M infra/vps/docker-compose.prod.yml
 M "obsidian/07-BUGS/Open Bugs.md"
 M services/strategy-worker/hunter_strategy_worker/config.py
 M services/strategy-worker/tests/test_claim_idle_ms.py
?? .claude/state/brief-T3.74e-atraso-constante.md
?? .claude/state/notes-T3.74e.md
?? infra/scripts/sql/research/2026-09-10-t374e-q01-signals-per-bar.sql
?? infra/scripts/sql/research/2026-09-10-t374e-q02-band-recurs-per-boundary.sql
```

**Não tocados por mim, apesar de aparecerem no `git status` da árvore compartilhada** (outras
frentes ativas hoje): `.claude/launch.json`, `docs/DESIGN.md`,
`infra/scripts/tests/test_seed_dry_run.py`,
`packages/core/tests/integration/test_schema_seed_and_partitions.py`, tudo sob
`.claude/state/design/2026-09-08/**` e o restante dos arquivos `astra-*`/`design/**` não listados
acima.

## 6. Próximo passo

Deploy pelo orquestrador; depois, reler `hb:strategy:shadow` (`decision_lag_p50_s`/`_p95_s`) e
rodar `2026-09-10-t374e-q01-signals-per-bar.sql`/`q02-band-recurs-per-boundary.sql` de novo numa
janela pós-deploy limpa (sem rajadas anteriores ao deploy misturadas, como aconteceu com as janelas
16:00Z-18:00Z desta medição) para confirmar a projeção de ~10 s. Se `decision_lag_p95_s` continuar
acima de 30 s, o próximo corte é sharding em múltiplos processos (T3.74c §4), não mais este knob.
