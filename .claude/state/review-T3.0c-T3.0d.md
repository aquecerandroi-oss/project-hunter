# Revisao adversarial — T3.0c (`8822b31`) + T3.0d (`999640a`) — identidade spot

**Revisor:** code-reviewer (segunda opiniao, Astra indisponivel ate 2026-09-12). **Data:** 2026-09-07.
**Metodo:** leitura do diff real (`git diff e57908a..999640a`), inspecao dos arquivos completos citados
abaixo, recomputacao manual do uuid5 pinado, execucao direta (primeiro plano, sem testcontainers) de
`ruff check`, `ruff format --check`, `pyright` e `check_file_size.py` sobre os pacotes tocados.

**Resposta central:** o bloqueante que a T3.0d existia para fechar — colisao de `event_id` entre a vela
perp e a vela spot do mesmo minuto — esta corrigido, testado com um caso real (duas fitas fechando a
mesma vela no mesmo lote) e o valor do perpetuo esta pinado byte a byte contra a formula antiga
(recomputei a mao: `uuid5(0d0d5f8e-6f1c-4f2f-9a3b-2b1f5a7c9e40, "market.candles.closed|binance|BTCUSDT|1m|2026-09-07T07:00:00+00:00")` = `40b42f73-c29e-5e66-ad43-670b8f7d1ae4`, exatamente o valor do teste). Os cinco
outros itens do brief (filtro de `load_market_ids`, docstring da identidade spot, filtro do scanner,
assercao do hash do ticker, `docs/PIPELINE.md` §1d) foram entregues, cada um com teste que exercita o
caminho real (Redis/Postgres via fixtures, nao mocks vazios) e nenhum codigo fora do escopo do brief.
Achei um problema novo, nao coberto pelo brief nem pelas notas honestas do autor: duas metricas
Prometheus compartilhadas por `exchange` sem `market_type` misturam o sinal do perpetuo com o do spot.

**Comandos que rodei e resultado real (nao citacao de notas):**
```
$ uv run ruff check services/market-worker services/scanner-worker packages/exchange-adapters apps/api
All checks passed!
$ uv run ruff format --check services/market-worker services/scanner-worker packages/exchange-adapters apps/api
383 files already formatted
$ uv run pyright services/market-worker packages/exchange-adapters apps/api services/scanner-worker
0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py
scanned 462 files; 0 over budget, 0 grandfathered
$ uv run pytest services/scanner-worker/tests/test_consumers.py -m unit -q
12 passed in 2.90s
```
Nao rodei as suites de integracao (`test_outbox_producers.py`, `test_market_ids.py`,
`test_spot_recovery.py`, etc.) por proibicao explicita de testcontainers nesta tarefa; a leitura de
codigo e a recomputacao manual do uuid5 substituem essa evidencia para os pontos criticos. **Achado
de processo:** `notes-T3.0d.md` §7 item 4 descreve o que foi rodado em prosa, sem colar a saida real
(diferente de `t30-proof.md`, que tem saida ao vivo colada). Peco, antes do proximo brief, que a nota
cole `pytest -q` real por arquivo, nao so a lista de arquivos.

---

## Bloqueantes

Nenhum. O bloqueante herdado (`review-T3.0b.md` item 1 / `notes-T3.0c.md` §12 ressalva 9) esta fechado
por esta entrega, com teste que reproduz a colisao original e prova que ela nao existe mais
(`test_a_perp_and_a_spot_candle_of_the_same_minute_get_different_ids`,
`test_a_spot_and_a_perp_history_batch_of_the_same_span_get_different_identities`) e com o valor do
perpetuo pinado (`test_the_perpetuals_candle_event_id_is_the_exact_value_it_had_before_market_type_existed`).

---

## Antes do deploy da VPS (ou antes de ligar `MARKET_SPOT_ENABLED` em producao)

### 1. `market_dropped_events_total{exchange}` mistura o sinal do perpetuo com o do spot

`packages/core/hunter_core/observability.py:143-149` declara o counter com labels `["exchange"]`
apenas. `services/market-worker/hunter_market_worker/heartbeat.py:282`
(`market_dropped_events_total.labels(exchange=adapter.code).inc(dropped)`) roda dentro de
`run_heartbeat`, que e chamado tanto pelo laco perpetuo quanto pelo spot
(`services/market-worker/hunter_market_worker/spot.py:177-185`, `run_heartbeat(..., market_type=MarketType.SPOT, shard=SPOT_SHARD)`), e os dois adaptadores respondem `adapter.code == "binance"`
por desenho (T3.0a/b — uma linha em `exchanges`). Nao ha segunda label nem serie separada aqui, ao
contrario do que o proprio T3.0c fez para `market_ingestion_gaps`/`market_spot_ingestion_gaps`
(`recovery.py:236`, correto) e para as tres series novas de `observability.py:150-173`.

**Cenario concreto:** esta e exatamente a metrica que `obsidian/09-OPERATIONS/Monitoring.md` chama de
"o sinal de que a ingestao esta perdendo dado — sem ele, a degradacao era invisivel", e e exatamente o
sintoma que `t30-proof.md` §1 mediu ao vivo (spot ligado faz o perpetuo perder o orcamento de
keepalive e reconectar com `1011`). Na VPS, ao ligar `MARKET_SPOT_ENABLED=true`, se o socket spot
reconectar sob condicao de rede normal (comportamento esperado, nao critico), `market_dropped_events_total{exchange="binance"}` sobe pelo motivo errado — e um operador olhando o dashboard nao consegue
distinguir "o spot esta reconectando, normal" de "o perpetuo, do qual todo o Radar depende, esta
perdendo tape" sem abrir os dois hashes `hb:market:binance` e `hb:market:spot:binance` na mao. Isso
mina a propria checagem que `t30-proof.md` §5 e `PIPELINE.md` §1d tornam obrigatoria para ligar spot
em producao. Correcao: rotulo `market_type` na serie existente teria o mesmo problema de zerar
dashboards (nota do proprio T3.0c) — o caminho consistente com a decisao ja tomada e uma serie nova
(`market_spot_dropped_events_total{exchange}`), no mesmo padrao de `market_spot_ingestion_gaps`.

Mesma classe de problema, menor severidade, sem correcao pedida agora: `market_publish_failures_total{stream}` (`publication.py:55`) e `market_persistence_loss_reports_dropped_total` (`queues.py:176`, sem label nenhuma) tambem sao somadas entre os dois produtos — aqui o dano e menor porque nenhum dos
dois e o sinal primario de "a coleta esta saudavel".

### 2. A condicao para ligar MARKET_SPOT_ENABLED e um checklist manual, nao um portao automatico

`docs/PIPELINE.md` §1d (e `t30-proof.md` §5) documentam a condicao corretamente — tres sinais
verificaveis (`hb:market:spot:{ex}` presente com `reconnects=0`; `hb:market:{ex}` com `last_event_at`
fresco e `reconnects` nao subindo; velas perpetuas continuando a entrar) — mas nada no codigo impede
um operador de exportar `MARKET_SPOT_ENABLED=true` no shard 0 da VPS sem seguir o runbook. Nao e uma
regressao desta entrega (o brief so pediu para documentar, nao para automatizar), mas como a VPS e o
primeiro ambiente compartilhado real, vale registrar: hoje a unica coisa que separa a VPS de repetir o
arm B do §1 do `t30-proof.md` (0 velas perpetuas em 5 min) e a disciplina de quem sobe a variavel.
Sugestao para depois do M3: um script de pre-voo que leia `hb:market:{ex}` antes de aceitar a variavel,
ou pelo menos um aviso automatico (`system_event warning`) se `reconnects` do perpetuo subir nos
primeiros 5 minutos com spot ligado.

---

## Depois

1. **Dois processos "shard 0" simultaneos nao sao impedidos.** `services/market-worker/hunter_market_worker/spot.py:92-94` (`collects_spot`) e o comentario em `spot_universe.py:183-188`
   assumem "exatamente um coletor spot por venue... por construcao", mas nada no Redis impoe isso —
   e inteiramente disciplina de deploy (`MARKET_SHARD` unico por replica). Um rolling restart na VPS
   em que o container antigo (shard 0) e o novo (tambem shard 0) coexistem por alguns segundos faria
   os dois assinarem o book/trade spot em duplicidade e os dois escreverem `hb:market:spot:binance` e
   `mkt:binance:spot:coverage` (chave solo, sem o script Lua de merge que o perpetuo usa para N>1) —
   last-writer-wins, cobertura oscilando. Hoje isso e inofensivo porque nada consome cobertura spot
   nem `hb:market:spot:*` alem do `/ready` do proprio processo (`spot.py` §7 do PIPELINE confirma: "o
   scanner nao consome spot"), mas vira relevante quando a T3.5/T3.8c passarem a depender desses
   sinais. Nao bloqueia nada agora; registrar no runbook de deploy da VPS que o rolling restart do
   shard 0 deve ser "stop antes de start", nao "start antes de stop".
2. **`market_backfill_planned`/`market_persist_flush_failed` continuam sem `market_type` no log**
   (ressalva 3 de `notes-T3.0c.md`, nao tocada por esta entrega, o proprio autor ja registrou). Com
   spot ligado, um `TimeoutError` de 10 s no `drain_loop` nao diz de qual das duas filas veio.
3. **Histerese do piso de 50M (`PROMUSDT` flapando) segue como pergunta aberta para o Everton**,
   corretamente nao decidida aqui, conforme o brief pediu.
4. **`rt:market-spot:{ex}:{sym}` e um canal que ninguem assina hoje** (gramatica de
   `apps/api/hunter_api/realtime/channels.py` recusa o segmento extra, confirmado lendo
   `apps/api/tests/unit/test_channels.py:113` — inalterado por este diff). Registrado para T3.8c,
   consistente com a decisao tomada.

---

## Verificacoes especificas do pedido

- **Colisao de chaves/heartbeat/evento (item 1):** `mkt:*`, `hb:*`, `rt:*`, `outbox.event_id/key` e
  `mkt:coverage:*` foram conferidos um a um lendo `hunter_core/redis.py` (`keys.ticker/book/trades/
  candles_1m/market_slug/tape_coverage/market_heartbeat`, nao tocado neste diff, ja correto desde
  T3.0b/c) e `durable.py`/`backfill_announce.py` (corrigidos agora). Unico ponto de colisao real
  encontrado: as duas series Prometheus do item "Antes do deploy" acima — nao fazem parte da lista
  citada no pedido (`mkt:*`, `hb:*`, `rt:*`, outbox, coverage) mas sao a mesma classe de bug
  ("series Prometheus com o mesmo `{exchange}`"), entao reportei.
- **Shard 0 dedicado (item 2):** `collects_spot()` so olha `shard_index == 0`; todo outro shard
  idla a task sem nunca criar socket. Se `MARKET_SPOT_ENABLED=true` for ligado so num shard != 0,
  nada coleta spot (silencioso, sem erro) — comportamento documentado em `t30-proof.md` §5 ("nenhum
  outro shard reage a variavel"). Se o shard 0 morrer, a VPS perde o spot inteiro ate o restart (e a
  topologia aceita, um unico coletor, mesma classe de risco que qualquer shard perpetuo perder sua
  fatia). Dois processos achando que sao o shard 0 ao mesmo tempo: ver item "Depois" 1 — nao impedido,
  mas hoje inofensivo.
- **Filtro do scanner e leitura pelo execution-worker (item 3):** confirmado com o filtro em
  `hunter_scanner_worker/main.py::touch_batch_handler` (drop com ACK, antes do coalescer) e, do lado
  do execution-worker (so leitura, nao editei nada la): `services/execution-worker/hunter_execution_worker/market_data.py:185` le `keys.trades(market.exchange, market.symbol, MarketType.SPOT)` e o
  book via `keys.book(...)`, os **mesmos** builders que `hot_state.py`/`hot_state_trades.py` usam para
  escrever no lado do market-worker — as duas pontas concordam byte a byte na chave
  (`mkt:{ex}:spot:{sym}:trades`/`:book`). Nenhuma divergencia encontrada.
- **Universo spot e market_betas/beta_v1 (item 4):** piso medido no ticker spot
  (`spot_universe.py:99`, `>=` inclusivo, sem ticker = fora), refresh nos 15 min do perpetuo,
  flapping de `PROMUSDT` ja registrado como pergunta aberta. `market_betas` (nao tocado neste diff)
  usa `market_id` (FK para `markets`, ja unico por `(exchange, symbol, market_type)`) como identidade,
  nunca a string `exchange+symbol` — nao ha classe de colisao aqui porque a tabela ja resolve por tipo
  desde antes desta entrega.
- **Condicao para ligar (item 5):** ver "Antes do deploy" item 2 — verificavel mas manual, nao um
  portao automatico.
- **Rollback (item 6):** `DEL mkt:*:candles:1m` de `docs/DEPLOYMENT.md` continua valido: T3.0d nao
  mudou o formato msgpack da lista de velas (`to_wire(candle)`), so o `event_id`/`key` do envelope da
  outbox — dois contratos diferentes. Confirmei que nenhum id ja anunciado muda: recomputei a mao o
  uuid5 do perpetuo com a formula pre-fix e bate com o valor pinado no teste.
- **Testes que provam pouco (item 7):** nao encontrei mock que nao exercite o caminho real nos
  arquivos novos — `test_market_ids.py`, `test_outbox_producers.py` e `test_market_type_identity.py`
  usam Postgres/Redis reais via fixture (`db_session_factory`/`redis_client`), nao dubles. `pyright`
  nao esta suprimido em nenhum arquivo tocado (rodei e confirmei 0/0/0).
- **Tamanho de arquivo (item 8):** todos os arquivos tocados <= 350 linhas (`coverage.py` exatamente
  350, `durable.py` 344); `check_file_size.py` confirma 0 acima do orcamento em 462 arquivos.

---

**Bloqueia o deploy da VPS: nao.**
**Bloqueia ligar spot: nao.**
