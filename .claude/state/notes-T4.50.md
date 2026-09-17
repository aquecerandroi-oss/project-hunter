# T4.50 — CPU/timeout no Postgres compartilhado (perps/spot vs. funil de memes)

## O culpado

`hunter_core.universe.load_history_universe` (`packages/core/hunter_core/universe.py`),
usado por três chamadores: `breadth_repo.history_universe_ids` (scanner-worker),
`dispersion_repo.universe_members` (scanner-worker) e
`hunter_strategy_worker.universe` (cache de 1h, shadow gate). O texto exato do
`STATEMENT:` no log do Postgres (17/09 12:22–12:24Z, pids 1586580/1586385/1647179/...)
bate byte a byte com a query gerada por essa função.

## Frequência real (não é "uma vez por hora")

O docstring da função dizia "~200 rows, read at most once an hour by the shadow
cache and once per pass by the breadth producer" — mas "per pass" do
`breadth_job.py`/`dispersion_job.py` é **uma vez por minuto, por exchange**
(`breadth.py`: "the per-minute cadence around run_breadth_once"). Com uma
exchange configurada (`binance`), isso é 1 chamada/min para breadth + 1/min
para dispersion = a query cara rodando 2x por minuto, o que bate com o
intervalo de ~60s entre cancelamentos no log.

## Por que `min(open_time)` era caro

`candles` é particionada por LIST(timeframe) e depois RANGE(open_time) mensal
(DATABASE.md §1.3). A PK `(market_id, timeframe, open_time)` ordena cada
partição perfeitamente para achar o primeiro candle de um mercado — mas a
query antiga fazia `GROUP BY markets.id` sobre um `LEFT JOIN` com `MIN()`, e o
Postgres não tem "partitionwise aggregate" para um `GROUP BY` cuja chave
(`market_id`) não é a chave de particionamento (`open_time`). Resultado
(`EXPLAIN ANALYZE` no VPS, 17/09, dados reais, timeout elevado a 120s pra medir):

- **Antes**: `HashAggregate` sobre `Nested Loop Left Join` que materializa
  **6.149.176 linhas** (todo candle final de 1m de cada um dos 200 mercados,
  em todas as 7 partições mensais vivas) — **~1.982.232 buffers** (hit+read,
  ~15,5 GB) e **16.159 ms** de execução.
- **Depois** (reescrita para `LEFT JOIN LATERAL (... ORDER BY open_time ASC
  LIMIT 1) ON true`, usando a mesma PK): **~2.150 buffers** e **8,3 ms** —
  ~1950x mais rápido, ~920x menos I/O. Validado com um `diff` das 200 linhas
  entre a query antiga e a nova rodando lado a lado no mesmo snapshot: **0
  divergências**.

O I/O da query antiga (a maior parte na partição do mês corrente,
`candles_1m_2026_09`, via Bitmap Heap Scan) é o motivo mais provável de o
Postgres compartilhado ficar com CPU/IO saturado a ponto de as leituras
per-tick do meme-worker (`meme_pedigree_read_failed`) também estourarem
timeout — mesmo tabela nenhuma em comum, a contenção é de recurso da
instância, não de lock.

## O que foi feito

- `packages/core/hunter_core/universe.py`: reescrita de `load_history_universe`
  de `GROUP BY`/`MIN` para `LEFT JOIN LATERAL ... ORDER BY open_time ASC LIMIT 1`,
  por mercado — sem migração, porque a PK que já existe
  (`market_id, timeframe, open_time`) já é o índice ideal para isso. Docstring
  da função atualizado para não repetir a suposição errada ("cheap ~200 rows,
  once an hour") e para registrar a frequência real medida.
- Testes: `packages/core/tests/unit/test_universe_history.py` (7, sem DB) +
  `packages/core/tests/unit` completo (1350 passed) + `ruff check`/`format
  --check` (limpos) + `check_file_size.py` (0 arquivo estourado) — todos
  locais, sem Docker.
  Com Docker local (não é a VPS): as três suítes de integração que exercitam
  essa query contra Postgres real passaram sem alteração de expectativa —
  `services/scanner-worker/tests/test_breadth_job.py` (11), `test_dispersion_job.py`
  (13) e `services/strategy-worker/tests/test_universe_gate.py` (1).
- Na VPS: só leitura — `docker logs`, dois `EXPLAIN (ANALYZE, BUFFERS)`
  (antes/depois) e um `diff` de resultado, todos via `docker exec -i
  hunter-postgres-1 psql`, nenhuma escrita, nenhum reinício.

## `pg_stat_statements` / `pg_stat_activity`

`pg_stat_statements` **não está instalada** (`pg_extension` não tem a linha).
Rodei 3 amostras de `pg_stat_activity` (~25s de intervalo, só leitura) em vez
disso — e peguei a própria query do título ao vivo, dentro da janela: no
snapshot 1, pid 1647179 esperando `IPC/BufferIO` havia 13,9s (a mesma query,
lendo do disco); no snapshot 3, pids 1647179 e 1627826 rodando a mesma query,
um deles também em `BufferIO`, enquanto uma leitura (`SELECT t.mint...`) e uma
escrita (`INSERT INTO meme_curve_snapshots`) do funil de memes corriam ao lado
— evidência direta, não só inferida, de que a query cara está competindo por
I/O com os caminhos do meme na mesma instância. Recomendo instalar a extensão
(`CREATE EXTENSION pg_stat_statements` — é uma escrita de catálogo; pedir
autorização) para ter `total_exec_time`/`calls` contínuos em vez de depender
de grep de log ou de pegar o pid certo por sorte numa amostra.

## O que falta (fora do escopo deste fix)

- **CPU do próprio `scanner-worker-1`** (100%): o `EXPLAIN` já mostrou que a
  query deixa de ser o problema, mas o worker tem outros custos por tick
  documentados em notes anteriores (T2.5c/T2.5d) — `build_context` re-varre
  1500 candles e `MarketContext.__post_init__` revalida 2000 trades a cada
  tick; não foi tocado aqui.
- **CPU dos 4 `hunter-market-worker-*`** (60–90%): não investigado nesta
  tarefa; a query do título não aparece nesses processos, o que sugere causa
  separada (fora do escopo do brief).
- Confirmar no ambiente real (não só no snapshot medido) que os
  cancelamentos por `statement_timeout` pararam depois do deploy — preciso
  reler `docker logs --since` depois que este código for implantado.
- `pg_stat_statements` não habilitado — sem ele, medir o "antes/depois" em
  produção depende de grep manual do log, como fiz aqui.
