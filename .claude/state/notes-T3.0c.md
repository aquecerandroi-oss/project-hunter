# T3.0c — ingestão SPOT no market-worker

**Data:** 2026-09-07. **Escopo:** `services/market-worker/**`,
`packages/core/hunter_core/{settings,observability}.py`, `apps/api` (rota `markets`),
`packages/exchange-adapters/hunter_exchanges/testing/` (um gravador + uma fixture).
Sem commit. Sem `.env*`, `infra/migrations/**`, `services/{execution,scanner,strategy}-worker/**`,
`packages/core/hunter_core/{portfolio,risk,execution,admission}/**`, `packages/risk-core/**`,
`apps/web/**`, `docs/**`.

**Astra indisponível até 2026-09-12 (cota)** — nenhuma segunda opinião foi obtida. Todas as
decisões de desenho abaixo estão registradas com o raciocínio para revisão posterior.

Fecha a metade final da T3.0 (adaptador = T3.0a `078d6ef`; `market_type` na identidade = T3.0b
`cefad8c`) e resolve os cinco itens que a `notes-T3.0b.md` §7 deixou explicitamente aqui.

---

## 1. O desenho, em uma linha

**Um segundo caminho de dados no mesmo processo, não um segundo modo do primeiro.**

`hunter_market_worker/spot.py` é uma subárvore de tasks com adaptador próprio, universo
próprio, fila de persistência própria, cobertura própria, heartbeat próprio e recovery
próprio. O único estado compartilhado com o perpétuo é o `TickCoalescer` (que desde a T3.0b
é chaveado por `(exchange, symbol, market_type)`, então um flush serve os dois) e o
`outbox_wake`.

### Um shard só

O coletor spot roda **no shard 0** e é dono do universo spot inteiro. 17–19 pares × 4 canais =
68–76 streams contra um teto de 1024, e algumas chamadas REST a cada 15 min: dividir custaria
eleição de líder, quatro heartbeats e um merge de cobertura, e não compraria nada. Os demais
shards **criam a task e a deixam ociosa** (`asyncio.Event().wait()`), em vez de não criá-la:
a topologia fica visível na lista de tasks, e `forever()` trata `return` como fatal.

Chave/registro: `hb:market:spot:{ex}` e `mkt:{ex}:spot:coverage` são publicados como **solo**
(`shard=(0, 1)`), nunca `0of4` — declarar-se "0 de 4" faria a API esperar por três shards spot
que não existem.

---

## 2. As cinco superfícies que a T3.0b deixou para cá

| Item da §7 da T3.0b | O que foi feito |
|---|---|
| 1. `market.ticks` e `rt:market:{ex}:{sym}` sem tipo | **payload ganhou `market_type`** (aditivo, o perpétuo diz `perpetual`); **canal não ganhou segmento** — spot publica em `rt:market-spot:{ex}:{sym}` (§3) |
| 2. `heartbeat.py` sem `market_type` | `hb_key`/`_write_hash`/`_safe_publish`/`run_heartbeat` receberam `market_type` + `shard`; extração de `heartbeat_events.py` pagou o orçamento |
| 2b. `coverage.py` em 350 linhas cravadas | `CoverageTracker(..., market_type=)`; extração de `coverage_limits.py` pagou o orçamento |
| 3. `streaming.py: trade_memory.forget(...)` no default | passa `market_type` |
| 4. mapas em processo do scanner por símbolo | **medido e registrado, não corrigido** — §6 |
| 5. `/api/v1/markets/{ex}/{sym}` só alcança o perpétuo | continua assim; o que ganhou filtro foi a **lista** (§5) |

---

## 3. Decisão registrada: o canal de pub/sub do spot

**`rt:market-spot:{exchange}:{symbol}`**, e não `rt:market:{exchange}:spot:{symbol}`.

O custo das duas opções foi medido antes de escolher:

- **`rt:market:{ex}:spot:{sym}`** exige mudar a gramática de
  `apps/api/hunter_api/realtime/channels.py` (`_MARKET_RE`, que recusa um `:` extra **de
  propósito**, com teste afirmando a recusa: `apps/api/tests/unit/test_channels.py` linha 113)
  **e** o consumidor em `apps/web` — que esta tarefa não pode tocar. Sem os dois, o canal
  novo seria recusado na assinatura;
- **publicar spot no canal do perpétuo** colocaria dois preços diferentes no mesmo canal. Foi
  descartado sem discussão: é exatamente a colisão que a T3.0a registrou como bloqueante.

`rt:market-spot:` é um nome que **nenhum cliente assina hoje** e que a gramática atual recusa —
o que é honesto: melhor um canal inalcançável e correto do que um canal alcançável e ambíguo.
Dar rota a ele (gramática + classe de autorização + cliente web) fica **registrado para a
T3.8c**. Não há perda de dado: o `market.ticks` (stream durável) carrega o tick spot com tipo
e chave de roteamento `binance:spot:BTCUSDT`.

A chave de envelope do `market.ticks` passou a usar `keys.market_slug`: o perpétuo continua
`{ex}:{sym}` byte a byte, o spot é `{ex}:spot:{sym}`.

---

## 4. Universo spot: um piso, não um top-N

`hunter_market_worker/spot_universe.py`.

- **regra (D1):** `quote_volume_24h >= 50 000 000 USDT` medido **no spot**, quote `USDT`,
  status `ACTIVE`, fora da blocklist. `>=` inclusivo;
- **sem ticker = fora.** O piso é uma permissão, e permissão não se concede por leitura que
  falhou;
- `market_type` filtrado na própria seleção, então um adaptador que respondesse `list_markets`
  com o produto errado não consegue fazer a carteira executar contra um listing de perpétuo;
- `monitor_rank` continua sendo escrito (por volume), mas **não decide nada** — serve para o
  operador ver a que distância do piso um par está;
- `market.universe.changed` ganhou `market_type` no payload (aditivo) e uma **identidade de
  evento distinta** (`universe_event_id(..., market_type)`): o perpétuo mantém a string que
  sempre teve, então nenhum id já anunciado muda, e o universo spot do mesmo conjunto no mesmo
  instante não é uma duplicata que a outbox descartaria;
- **restart:** `monitored_spot_symbols()` lê o último universo commitado antes do primeiro
  refresh, então um processo que volta coleta na hora em vez de ficar 15 min sem assinatura.

### Filtros de ordem: coluna que existe vs. `metadata`

`markets` tem `tick_size`/`step_size`/`min_notional` (preenchidos pelo `NormalizedMarket`) e
**não tem** coluna para `MARKET_LOT_SIZE`, `applyMinToMarket`, `avgPriceMins` ou os
multiplicadores de `PERCENT_PRICE_BY_SIDE`. Esses vão para o JSONB `markets.metadata`, sob o
rótulo explícito `spot_market_filters` (que é onde o adaptador já os coloca, T3.0a §5).

`upsert_markets` ganhou `write_metadata: bool = False` e **só o caminho spot liga**. Motivo
declarado: o perpétuo roda há dois milestones sem escrever essa coluna, e ligar para todo mundo
reescreveria as 528 linhas de perpétuo com `{"contractType": ...}` na mesma release que
introduz o spot — mudança que ninguém pediu, nas linhas em que quatro shards estão ao vivo.
**Nenhuma migração foi necessária.**

Armadilha registrada (custou duas execuções vermelhas): na entidade declarativa, o nome
`metadata` resolve para o `MetaData` do SQLAlchemy. A chave do `values()` é `"meta"` e a do
`set_` é o objeto `Market.meta`; o lado direito é `excluded["metadata"]`, por índice.

---

## 5. API

`GET /api/v1/markets?market_type=spot` **existe** (a rota aceitava filtro de exchange/símbolo,
não de produto; foi acrescentado).

**A mudança que importa mais é o default.** `MarketRepository.list_markets` não filtrava por
`market_type` — respondia "o universo perpétuo" **por acidente**, porque não havia outra coisa
em `markets`. Com as linhas spot que o coletor agora escreve, a página de Markets e as
contagens do `summary` ganhariam 19 linhas, sem aviso, vindas de uma tarefa que não pode tocar
`apps/web`. Agora o filtro é sempre aplicado, com default `perpetual`.

Não existe `market_type=all` de propósito: uma página misturando os dois listings de `BTCUSDT`
mostraria duas linhas que a UI de hoje não sabe distinguir. Um valor inválido dá 422 (teste),
nunca um fallback silencioso para o perpétuo.

`/api/v1/markets/{exchange}/{symbol}` continua só alcançando o perpétuo (item 5 da T3.0b),
porque dar essa capacidade é trabalho de contrato/UI.

---

## 6. Achado honesto: o scanner **não** filtra spot (e não quebra)

Pedido do brief: "confirme que o consumidor do scanner filtra por tipo ou não quebra". Medido,
com teste (`services/market-worker/tests/test_spot_ingest.py::
test_the_scanner_survives_a_spot_tick_but_does_not_yet_filter_one_out`):

- **não quebra**: `coalesce()` agrega a mensagem normalmente e ela é ackada;
- **não filtra**: `consumers.symbol_of()` lê `payload["symbol"]`, que é `BTCUSDT` para os dois
  listings, e `ScannerState.touch(symbol, ...)` é chaveado só por símbolo. Um tick spot marca
  o **perpétuo** como sujo e pode escrever o `last_input_ts` dele.

Dano hoje é limitado — todo símbolo spot já recebe tick de perpétuo a 4 Hz, então o mercado já
estava sujo, e os dois carimbos são ~agora — mas é **contaminação real da contabilidade de
latência de outro serviço** (`scanner_stream_delay_seconds` passa a misturar dois venues).

**Correção de uma linha, dona: quem for o dono do `services/scanner-worker`:** em
`hunter_scanner_worker/main.py::touch_batch_handler`, descartar a entrega cujo
`envelope.payload.get("market_type", "perpetual") != "perpetual"`. O campo já viaja e a chave
de roteamento (`binance:spot:BTCUSDT`) também. Não foi feito aqui porque o brief proíbe
alterar `services/scanner-worker/**`.

Alternativa considerada e recusada: publicar o tick spot num stream próprio
(`market.ticks.spot`). Isso resolveria a contaminação sem tocar no scanner, mas contraria o
pedido explícito do brief ("ticks spot publicados em `market.ticks` com `market_type` no
payload") e criaria um segundo contrato de stream que a T3.4 teria de desfazer.

---

## 7. Persistência, recovery e métricas

- **fila e drain por produto.** `flush_batch`/`drain_loop`/`report_losses` receberam
  `market_type`. Motivo: `load_market_ids` devolve `{symbol: market_id}`, então um lote com os
  dois listings de `BTCUSDT` só resolve um deles e gravaria vela spot sob o `market_id` do
  perpétuo — o bug 1 da T3.0b §5, agora impossível por construção (uma fila por produto);
- **o recovery cobre os dois tipos** — confirmado por teste nos dois sentidos
  (`test_spot_recovery.py`): `check_gaps(..., SPOT)` abre lacunas contra o `market_id` spot e
  **não** contra o do perpétuo, e o recovery do perpétuo continua sem enxergar o listing spot.
  O `pg_advisory_xact_lock` continua chaveado só por exchange, e **de propósito**: os quatro
  escritores de `ingestion_gaps` daquele venue têm de serializar entre si;
- **métricas por venue, séries novas** (`market_spot_universe_size`,
  `market_spot_events_total{exchange,kind}`, `market_spot_ingestion_gaps{exchange,status}`).
  Séries novas em vez de um label `market_type` nas existentes: acrescentar label a um counter
  vivo zera todo dashboard e alerta construído sobre ele, e — no caso do gauge de lacunas —
  dois coletores escreveriam a **mesma** série `{exchange,status}` e um sobrescreveria o outro;
- **readiness:** `spot: connected|degraded|absent` como *status detail*
  (`WorkerRuntime.status_details`), nunca check. `absent` = este processo não coleta spot
  (shard ≠ 0 ou `MARKET_SPOT_ENABLED=false`); `degraded` = socket spot reconectando. Um socket
  spot ruim **não** deixa `/ready` vermelho: o que a M2 entregou e de que o Radar inteiro
  depende é o perpétuo. Mesmo padrão do `rest_gate` (T2.9);
- **`rt:system` nunca sai do coletor spot.** Aquela mensagem substitui a linha inteira da
  exchange na página System, e um `ws_state` spot ali descreveria a conexão errada.

### Rate limit

`build_spot_adapter` monta o `TokenBucketRateLimiter` **com o Redis explícito** e com a
capacidade do spot (6000/60 s, bucket `rl:binance:spot_request_weight`). Sem isso o cliente cai
no default local por processo — N processos com orçamento local somam N cotas contra uma cota
só, que é exatamente a regra fail-closed do `PIPELINE.md` §1.7 e cujo preço é ban de IP.
Bucket separado do `rl:binance:request_weight` (2400/min do USDS-M): são cotas independentes e
duas capacidades na mesma chave corromperiam as duas (T3.0a §3).

---

## 8. Livro spot sem relógio da exchange (item 3 do brief)

`@bookTicker` e `@depth20@100ms` do spot **não trazem tempo de evento** (T3.0a §4), então o
adaptador carimba `ts == received_at`. Consequência para a cobertura, verificada por teste
(`test_a_spot_book_carries_no_exchange_clock_and_coverage_survives_it`): a margem do
`CoverageTracker` é medida contra o **relógio do coletor**, nunca contra o `ts` do evento, então
um livro sem relógio nem infla nem quebra o intervalo. Quem prova a fita spot é o `aggTrade`,
que carrega `T` de verdade — e é dele que qualquer métrica de latência do spot tem de sair.

---

## 9. Arquivos movidos (orçamento de 350 linhas)

Nenhum orçamento elevado. Duas extrações, ambas com re-export para que nenhum importador mude:

| Novo arquivo | Saiu de | Por quê |
|---|---|---|
| `coverage_limits.py` | `coverage.py` (350 cravadas → 350 depois de receber `market_type`) | as três constantes são a **política** da prova (quanto aquém do relógio, de quanto em quanto, por quanto tempo vale); o que ficou é a máquina que decide o que pode ser reivindicado |
| `heartbeat_events.py` | `heartbeat.py` (343 → 332) | o heartbeat é o sinal **vivo** no Redis; isto é o registro **durável** em Postgres, e a regra inteira do `safe_record_system_event` é que o segundo falhar não pode derrubar o primeiro |

`spot.py` (188), `spot_universe.py` (216) e `coverage_limits.py` (28) são novos.
`check_file_size.py`: 452 arquivos, 0 acima do orçamento.

---

## 10. Testes existentes editados (só onde a forma mudou)

- `test_ingest_coalesce.py::test_build_tick_payload_shape` — o dict inteiro é comparado e ganhou
  `market_type`;
- `test_universe_outbox.py` (3 asserções de payload) — idem;
- `test_persistence_contracts.py` (2 monkeypatches de `load_market_ids`) e
  `test_recovery_gate.py` (1 spy de `check_gaps`) — assinaturas ganharam um parâmetro;
- `apps/api/tests/integration/test_markets_api.py::test_spot_and_perpetual_of_one_symbol_...`
  — os dois listings agora estão em **duas páginas** (§5). A propriedade que o teste existe
  para provar (cada listing lê o próprio hot state) continua asserida, inalterada;
- `services/market-worker/tests/db_helpers.py::seed_market` — `market_type` entrou também no
  **lookup**, não só no insert: um helper que achasse qualquer um dos dois listings entregaria
  o `market_id` errado ao teste.

Nenhuma asserção de comportamento foi afrouxada.

---

## 11. Fixture nova

`packages/exchange-adapters/hunter_exchanges/testing/fixtures/spot_universe_ticker_24hr.json`
(500 KB) — **todas** as 740 linhas com quote USDT de uma chamada real
`GET /api/v3/ticker/24hr`, verbatim, gravadas por
`hunter_exchanges/testing/record_spot_universe.py` (novo, público, re-executável) em
2026-09-07 03:36Z. Não é trimada de propósito: um piso aplicado a cinco megacaps escolhidas a
dedo não prova nada sobre uma regra cujo trabalho inteiro é dizer **não**. O teste afirma
**19 de 740** — o mesmo 19 que a T3.0a mediu ao vivo, e não os ~50 que a D1 estimava.

---

## 12. Ressalvas honestas

1. **A ressalva principal, medida em A/B: spot e 200 perpétuos não cabem no mesmo event loop.**
   Dois arms consecutivos de 6 min na mesma máquina, universo perpétuo cheio nos dois
   (`t30-proof.md` §1):

   | | spot OFF | spot ON |
   |---|---|---|
   | idade do `last_event_at` perpétuo | 28 s | **5 min** |
   | velas perpétuas / 5 min | **600** | **0** |
   | reconnects do WS perpétuo | 2 | **8** |
   | erro no log | `no close frame received` | `sent 1011 — **keepalive ping timeout**` |

   Causa: o coletor perpétuo com 200 mercados já satura um core (achado da T2.5g); somar o
   parse do spot faz o socket perpétuo perder o orçamento de keepalive, a Binance derruba com
   `1011`, ele reconecta 1 200 streams e entra em backlog. **Não é bug do spot** — é falta de
   folga de event loop no shard, e o próprio T2.5g já dizia que `0/1` com 200 mercados é
   topologia inadequada.

   **Por isso `MARKET_SPOT_ENABLED` nasce `false`.** Um default que muda o comportamento de um
   coletor já saturado no próximo restart não é um default. Ligar é uma variável, com a
   checagem obrigatória em `t30-proof.md` §5. Com folga (universo perpétuo reduzido a 20 no
   diagnóstico), o caminho spot roda 15 min 41 s com 0 reconnects, 0 exceções, 16 livros/16
   tickers/19 fitas no hot state e velas spot na hora — `t30-proof.md` §2.

2. **A cobertura spot congela sob descarte contínuo.** Na janela de prova, `covered_until` do
   spot parou em 08:37:04Z enquanto `dropped_events` subia. É o comportamento desenhado (um
   descarte quebra o intervalo e a prova congela em vez de reivindicar fita não coletada), mas
   a consequência prática é que **um scanner que lesse spot recusaria as janelas**. Numa
   máquina com folga não há descarte; nesta há, para os dois produtos.

3. **`market_persist_flush_failed` com `TimeoutError` (10 s) apareceu no arranque.** O log não
   diz de qual fila veio (perpétuo ou spot) — o `drain_loop` não carimba o produto no log de
   erro. Pré-existente na forma (o timeout de 10 s é da T1.3), mas agora há **duas** filas
   disputando o mesmo Postgres. Registrado como item de observabilidade: o log do `drain_loop`
   deveria carregar `market_type`.
4. **O scanner ainda contamina** — §6. É o item aberto mais importante desta entrega.
5. ~~`pyright apps/api` tem 1 erro pré-existente...~~ **Superado.** Na varredura final
   (2026-09-07, fechamento da T3.0c), `uv run pyright services/market-worker
   packages/exchange-adapters apps/api` dá **0 erros, 0 avisos** — o erro de
   `test_admission_adapter.py` (arquivo de outro agente) já não existe na árvore.
6. **A rota de detalhe (`/markets/{ex}/{sym}`) e o `radar` continuam cegos ao spot.** Nada
   disso regrediu; simplesmente não foi escopo.
7. **`monitor_by_floor` não cria linha para um símbolo elegível sem linha ativa.** Só pode
   acontecer se o par saiu de `TRADING` entre o upsert e o ranking, na mesma transação — e
   monitorar um par suspenso nunca é certo. Registrado por ser silencioso.
8. **O universo spot flapa na borda do piso.** `PROMUSDT` entrou e saiu entre dois refreshes
   durante a prova (volume 24 h oscilando em torno de 50 M). Isso gera um
   `market.universe.changed` a cada 15 min para esses pares. Não há histerese; se incomodar,
   é decisão do Everton (o número é dele).
9. **`review-T3.0b.md` item 1 ("bloqueante para a T3.0c") continua aberto — verificado agora,
   não corrigido.** `candle_event_id` (`durable.py:78-86`) não recebeu `market_type` nesta
   entrega (a chave do envelope em `enqueue_candles`/`_key` também não). Reproduzido ao vivo
   na varredura final:

   ```
   perp id: 10fec7fa-c293-5400-966d-d921d8defed5
   spot id: 10fec7fa-c293-5400-966d-d921d8defed5
   COLLIDE: True
   ```

   (mesmo exchange/símbolo/timeframe/`open_time`, só o `market_type` difere.) Consequência: a
   **linha em `candles` é gravada certa** para os dois produtos (o `market_id` já é resolvido
   por tipo desde §7), mas o evento `market.candles.closed` de quem commitar depois no mesmo
   minuto é **descartado em silêncio** pelo `ON CONFLICT (event_id)` do outbox — nenhum
   consumidor de `market.candles.closed` vê o fechamento daquele lado. Não foi pego por nenhum
   teste desta entrega (nenhum exercita as duas fitas fechando a mesma vela no mesmo lote). Não
   corrigi aqui: `durable.py` já está no meio de outra mudança desta tarefa
   (`universe_event_id`) e o item já está explicitamente atribuído à T3.0d por quem revisou a
   T3.0b — mas ele **bloqueia ligar `MARKET_SPOT_ENABLED=true` em qualquer ambiente
   compartilhado** antes de ser fechado, o que a ressalva 1 ainda não cobria.
