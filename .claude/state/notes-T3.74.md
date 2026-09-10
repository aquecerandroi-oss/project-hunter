# T3.74 — atraso de decisão de 2 s para 125 s: diagnóstico e o primeiro fio puxado

**Escopo:** medição somente leitura na VPS (`hunter-vps`, `hunter-postgres-1`/`hunter-redis-1`),
toda consulta em `begin transaction isolation level repeatable read read only; … commit;`; depois a
menor correção segura, com testes. **Nenhuma escrita na VPS. Nenhum reinício/recriação de contêiner.
Nenhum parâmetro de versão viva tocado. Nenhum commit.** Leitura de referência:
**2026-09-10 04:48Z = 01:48 BRT**. Horários em Brasília (UTC−3) com o UTC ao lado.

SQL, verbatim, em `infra/scripts/sql/research/`:

| arquivo | o que responde |
|---|---|
| `2026-09-10-t374-q00-replay-runs.sql` | histórico de `replay_runs`: fatias, janelas, duração, workers |
| `2026-09-10-t374-q01-replay-coverage.sql` | quantos segundos por hora o dreno de replay ficou ocupado desde 08/09 |
| `2026-09-10-t374-q02-lag-por-hora.sql` | mediana/p95 do atraso decisão-menos-barra por hora desde 08/09 |
| `2026-09-10-t374-q03-roster-universo.sql` | roster ativo e universo monitorado agora (11 versões, 200 perpétuos) |

Receita usada em todas:
```bash
timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t374-q02-lag-por-hora.sql
```

---

## 1. A série do atraso: sobe antes dos dois deploys do dia

`q02` (mediana/p95 de `emitted_at − supporting_features.observation_ts`, por hora UTC, 08–10/09):

| hora UTC | mediana | p95 | | hora UTC | mediana | p95 |
|---|---|---|---|---|---|---|
| 08/09 00:00 | 11,9 s | 32,6 s | | 09/09 12:00 | 85,1 s | 258,3 s |
| 08/09 12:00 | 17,2 s | 79,1 s | | 09/09 14:00 | **154,9 s** | 291,3 s |
| 08/09 17:00 | 32,9 s | 134,9 s | | 09/09 21:36 (deploy 572d3b6) | — | — |
| 08/09 22:00 | 87,3 s | 255,8 s | | 09/09 23:00 | **207,5 s** | 293,6 s |
| 09/09 00:00 | 103,3 s | 265,2 s | | 10/09 02:00 | 135,3 s | 221,5 s |
| 09/09 12:19 (deploy d21a11d) | — | — | | 10/09 03:00 | 94,1 s | 234,5 s |

A mediana **já estava em 87–110 s na noite de 08/09**, bem antes de `d21a11d` (T3.52/T3.54b, 09/09
12:19 BRT) e `572d3b6` (T3.67, 18:36 BRT) — os dois deploys do dia não são a causa isolada, ainda que
possam ter somado custo (o portão de elegibilidade e a janela de contexto por versão de `d21a11d`
adicionam leituras por avaliação). O crescimento é anterior e mais contínuo.

## 2. Três fatores medidos, nenhum isolado

### 2a. O dreno de replay/backfill roda quase sem folga em certas janelas

`q00`/`q01`: `replay_runs` mostra fatias de 30 dias × 4 mercados, 3 workers, ~11 520 barras, ~3 min
cada, encadeadas **de volta em volta sem intervalo visível** em vários trechos — 93,7 % de uma hora
ocupada às 10/09 03:00Z, 57,5 % às 02:00Z, picos de 22–40 % em horas de 08/09. Entre 09/09 20:00Z e
10/09 02:00Z não há nenhuma linha em `replay_runs`, mas o atraso continua em 120–207 s — coerente com
o backfill de 90 dias/16 mercados (T3.62), que termina por volta de 23:00 BRT/02:00Z 09→10/09 e não
aparece nesta tabela (é um processo de ingestão, não um `replay_run`).

### 2b. O código morto: o portão que deveria proteger a linha viva nunca era chamado

`replay/budget.py::live_lane_degraded` — escrito, testado (`test_replay_contract.py::TestReadinessGate`,
6 casos) e documentado como "antes de toda fatia, o heartbeat da linha viva é lido" — **não tinha
nenhum chamador em código de produção**. Confirmado por grep antes de tocar em nada:

```
$ grep -rn "live_lane_degraded" services/strategy-worker --include=*.py | grep -v /tests/
services\strategy-worker\hunter_strategy_worker\replay\run.py:...  (só a import de load_budget/take_next/workers_for; live_lane_degraded NÃO estava na lista)
services\strategy-worker\hunter_strategy_worker\replay\budget.py:...
```
`replay/run.py` só importava `load_budget`/`workers_for` de `budget.py` — nunca `live_lane_degraded`.
`_drain` (dreno da fila) e o caminho direto `--version/--from/--to` (ambos chamam `_run`) despachavam
fatias no orçamento de CPU cheio (`workers_for`) **sem nunca perguntar se a linha viva estava bem**.

### 2c. Custo por barra é N (versões) × M (mercados), sem cache entre versões

`q03`: 11 versões ativas, 200 mercados perpétuos monitorados agora. `handle_candle` (`consumer.py`)
percorre sequencialmente cada versão devida e chama `evaluate_slot` → `build_market_context`
(`context.py`), que relê o histórico de candles (até `SHADOW_CONTEXT_MAX_MINUTES` = 6000 min, T3.54b)
**por versão**, sem nenhum cache por `(mercado, fechamento de barra)` compartilhado entre versões da
mesma família — confirmado lendo `context.py`/`decide.py`: nada memoiza a leitura. Numa barra alinhada
para as 8 versões `mean_reversion`, isso é até 8 leituras completas de contexto para o mesmo mercado
no mesmo instante. `docker stats` pegou `hunter-postgres-1` em **178,64 % de CPU** num instante em
que **nenhum processo de replay estava rodando** (`docker top hunter-strategy-worker-1` só mostrava o
processo do worker vivo) — ou seja, a linha viva sozinha já pressiona o Postgres o bastante para que
qualquer replay/backfill concorrente sature.

## 3. A correção feita (a menor, e não a única necessária)

Liguei o portão nos dois pontos de entrada de `services/strategy-worker/hunter_strategy_worker/replay/run.py`:

- `_drain()`: `live_lane_degraded(redis, budget)` é checado **antes** de `take_next` — de propósito
  nessa ordem: checar depois teria consumido (`RPOP`) um pedido da fila para então recusá-lo, e um
  pedido perdido não volta (T3.74 notes §2.1 do docstring novo).
- `_main()`, caminho direto (`--version`/`--from`/`--to`, fora de `--dry-run`): nova função
  `refuse_direct_run` em `budget.py` (abre e fecha seu próprio Redis, já que essa invocação não tem
  um cliente em mãos como o dreno da fila) recusa a fatia com `exit code 1` e a razão nomeada.

**Ressalva honesta, e é a mais importante desta tarefa**: o portão só enxerga `outbox_lag_s` e o
heartbeat (`hb:strategy:shadow`), nunca o atraso decisão-menos-barra que é o sintoma medido. Lido ao
vivo (`HGETALL hb:strategy:shadow`, 04:48Z): `outbox_lag_s = 0.0`, heartbeat fresco — ou seja, **o
portão diria "saudável" durante o pior período já medido**. Ligar o portão fecha um bug real e
documentado (código morto que devia estar vivo), mas não deve ser reportado como tendo resolvido o
atraso — por isso o brief `T3.74b` pede um terceiro motivo (`consumer_lag`) lendo o lag do próprio
grupo consumidor (`XINFO GROUPS market.candles.closed` grupo `strategy-worker.shadow`, medido em 69
agora) antes de qualquer coisa mais cara.

## 4. TDD

`test_replay_drain_pause.py::test_a_degraded_lane_never_pops_a_request` foi escrito, rodado e visto
falhar pelo motivo certo contra o código sem a checagem (`assert ['take_next'] == []` falhava com
`take_next` chamado), depois a checagem foi restaurada e o teste passa. `test_replay_contract.py`
ganhou `TestRefuseDirectRun` (2 casos, saudável/degradado, prova que o cliente Redis é sempre
fechado).

## 5. Comandos de qualidade (saída real)

```
$ uv run pytest services/strategy-worker/tests/test_replay_contract.py services/strategy-worker/tests/test_replay_drain_pause.py -q
37 passed in 2.99s

$ uv run pytest services/strategy-worker/tests -q -m unit
292 passed, 325 deselected in 7.61s

$ uv run ruff check services/strategy-worker/
All checks passed!

$ uv run ruff format --check services/strategy-worker/
120 files already formatted

$ uv run pyright services/strategy-worker
3 errors, 0 warnings, 0 informations
  (2 pré-existentes em test_replay_stress.py:35 — reportPrivateUsage de _delayed/_plan_for, mesmo
   padrão já aceito em T3.73 — e 1 novo da mesma família em test_replay_drain_pause.py:79, testando
   `_drain`, privado por convenção e não por API pública)

$ uv run python infra/scripts/check_file_size.py
scanned 593 files; 0 over budget, 0 grandfathered
  (run.py 356→346 linhas, budget.py 283→302 — ambos dentro do orçamento)
```

## 6. Arquivos tocados/criados (a árvore é compartilhada — abaixo só o que é desta tarefa)

```
 M obsidian/07-BUGS/Open Bugs.md
 M services/strategy-worker/hunter_strategy_worker/replay/budget.py
 M services/strategy-worker/hunter_strategy_worker/replay/run.py
 M services/strategy-worker/tests/test_replay_contract.py
?? .claude/state/brief-T3.74-atraso-de-decisao.md
?? .claude/state/brief-T3.74b-consumer-lag-e-custo-por-barra.md
?? .claude/state/notes-T3.74.md
?? infra/scripts/sql/research/2026-09-10-t374-q00-replay-runs.sql
?? infra/scripts/sql/research/2026-09-10-t374-q01-replay-coverage.sql
?? infra/scripts/sql/research/2026-09-10-t374-q02-lag-por-hora.sql
?? infra/scripts/sql/research/2026-09-10-t374-q03-roster-universo.sql
?? services/strategy-worker/tests/test_replay_drain_pause.py
```

`git diff --stat` dos dois arquivos de produção: `budget.py +19`, `run.py +17/-1` (confirmado com
`git diff` completo, revisado linha a linha nesta tarefa).

## 7. Próxima tarefa

`.claude/state/brief-T3.74b-consumer-lag-e-custo-por-barra.md`: (1) terceiro motivo `consumer_lag`
no portão, lendo o lag real do grupo consumidor — pequeno, testável igual a este; (2) desenho
(doc antes de codar, Astra opina) de cache de contexto por `(mercado, fechamento de barra)`
compartilhado entre versões da mesma família, para atacar o custo N×M; (3) opcional, devops: subir
`pg_stat_statements` (ausente hoje) para medir custo por query em vez de amostrar às cegas.
