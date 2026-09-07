# T3.0b — `market_type` em toda identidade de mercado fora do banco

**Data:** 2026-09-07. **Escopo:** `packages/core`, `packages/indicators`,
`packages/exchange-adapters`, `services/{market,scanner,strategy}-worker`, `apps/api`.
Sem commit. Sem `.env*`, sem `infra/migrations/**`, sem `docs/**`, sem
`market-worker/{main,supervision,fx}.py`, sem `packages/risk-core/**`, sem `apps/web/**`.
**Astra indisponível até 2026-09-12 (cota)** — nenhuma segunda opinião foi obtida; as decisões
de desenho abaixo estão registradas com o raciocínio para revisão posterior.

Fecha o bloqueio declarado em `.claude/state/notes-T3.0a.md` §1 (opção B do
`.claude/state/map-T3.0-market-identity.md`).

---

## 1. A regra, em uma linha

**O segmento de venue da chave carrega o tipo; o perpétuo não se move.**

```
mkt:binance:BTCUSDT:ticker        perpétuo  (byte a byte o que já está no Redis)
mkt:binance:spot:BTCUSDT:ticker   spot      (novo)
```

`market_type` tem default `PERPETUAL` em **todo** construtor de chave e em todo modelo de
evento, e o default produz a string idêntica à de antes. Nada migra: a VPS está com 4 shards
+ scanner + strategy + API lendo a forma da esquerda enquanto isso sobe.

### Chaves — antes / depois

| Construtor | Perpétuo (inalterado) | Spot (novo) |
|---|---|---|
| `keys.ticker` | `mkt:{ex}:{sym}:ticker` | `mkt:{ex}:spot:{sym}:ticker` |
| `keys.book` | `mkt:{ex}:{sym}:book` | `mkt:{ex}:spot:{sym}:book` |
| `keys.trades` | `mkt:{ex}:{sym}:trades` | `mkt:{ex}:spot:{sym}:trades` |
| `keys.candles_1m` | `mkt:{ex}:{sym}:candles:1m` | `mkt:{ex}:spot:{sym}:candles:1m` |
| `keys.derivatives` | `mkt:{ex}:{sym}:deriv` | `mkt:{ex}:spot:{sym}:deriv` (sempre vazia — é o ponto) |
| `keys.features` | `feat:{ex}:{sym}` | `feat:{ex}:spot:{sym}` |
| `keys.opportunity` | `opp:{ex}:{sym}` | `opp:{ex}:spot:{sym}` |
| `keys.scanner_state` | `scan:state:{ex}:{sym}` | `scan:state:{ex}:spot:{sym}` |
| `keys.baseline_projection` | `scan:baseline:{ex}:{sym}` | `scan:baseline:{ex}:spot:{sym}` |
| `keys.tape_coverage` | `mkt:{ex}:coverage` | `mkt:{ex}:spot:coverage` |
| `keys.market_slug` (membro do ZSET `radar:scores`, e chave de mapa) | `{ex}:{sym}` | `{ex}:spot:{sym}` |
| `keys.market_heartbeat` | `hb:market:{ex}` / `hb:market:{ex}:{i}of{N}` | `hb:market:spot:{ex}` / `hb:market:spot:{ex}:{i}of{N}` |
| `keys.market_heartbeat_shard_pattern` | `hb:market:{ex}:*of*` | `hb:market:spot:{ex}:*of*` |

**Exceção deliberada — o heartbeat põe o tipo ANTES do exchange.** Glob do Redis casa `:` com
`*`: `hb:market:binance:spot:0of4` seria varrido pelo `SCAN MATCH hb:market:binance:*of*` do
perpétuo, passaria o teste de sufixo `{i}of{N}` de `apps/api/.../market_shards.py` e entraria na
conta de shards USDS-M. Com `hb:market:spot:binance:0of4` os dois padrões são disjuntos — há
teste com `fnmatchcase` provando isso nos dois sentidos.

`mkt:{ex}:spot:coverage` não colide com `mkt:{ex}:{sym}:*` porque nenhum construtor produz
sufixo `:coverage` para um símbolo (colidiria apenas com um símbolo literalmente chamado
`spot` cujo sufixo fosse `coverage` — não existe).

## 2. Modelos de evento

`NormalizedTicker/Trade/OrderBook/Candle` ganharam `market_type: MarketType = PERPETUAL`
(`NormalizedFunding/OpenInterest/Liquidation` **não**: são conceitos só de perpétuo).

- **wire novo sempre explícito**: `to_wire` usa `model_dump`, que escreve o default — todo
  payload produzido de agora em diante diz qual mercado é;
- **wire antigo é lido como perpétuo**: um dict sem o campo valida no default. É o que está no
  Redis e nos streams agora, e é o que ele sempre significou. Teste dedicado.
- **exceção no hash de ticker**: `hot_state._ticker_fields` remove `market_type` junto com
  `kind`/`exchange`/`symbol`/`received_at` — identidade que já está *na chave* não se repete
  dentro do hash, e um campo novo sem dono num hash de dois produtores (KB-0044) mudaria o
  conteúdo do perpétuo à toa. A linha de candle (`to_wire`) **carrega** o campo, e é por isso
  que `strategy-worker/hot_state.read_tail` consegue recusar uma linha de outro listing.
- **T2.5g (caminho quente)**: `test_streams.py` exige que todo parser preencha *todos* os
  campos explicitamente (`model_construct` sem defaults custa 96 µs vs 32 µs). Por isso os
  parsers USDS-M passaram a escrever `market_type=MarketType.PERPETUAL` **explicitamente** —
  mesmo valor de antes, custo zero, contrato de performance preservado. (O brief dizia "os
  parsers USDS-M continuam sem passar o campo"; esse teste medido manda o contrário.)

## 3. Adaptadores

- `binance/normalize.parse_kline(s)` e `binance/streams.parse_kline_ws` receberam
  `market_type=PERPETUAL`. São compartilhados com o spot (formato de linha idêntico);
- `binance_spot/normalize.parse_klines` deixou de ser **re-export** do parser USDS-M e virou
  um wrapper que passa `SPOT`. Como estava, toda vela spot vinha rotulada `perpetual` e seria
  escrita na chave do perpétuo — exatamente a colisão que a T3.0a registrou;
- `binance_spot/{normalize,streams}` passam `market_type=MARKET_TYPE` em ticker, trade e livro.

## 4. Onde o tipo passou a viajar

| Componente | O que mudou |
|---|---|
| market-worker `hot_state*` | chave a partir de `event.market_type` (ticker, book, trades, candles) |
| market-worker `TradeMemory` | mapa `(exchange, symbol)` → `(exchange, symbol, market_type)`; `forget(..., market_type=PERPETUAL)` |
| market-worker `TickCoalescer` | estado `(exchange, symbol)` → `(exchange, symbol, market_type)`; `dirty_items()`/`reset()` usam a tripla |
| market-worker `AcceptedEvents.accept` | watermark `(exchange, symbol, kind)` → `(exchange, symbol, market_type, kind)` |
| market-worker `sampling.write_snapshots` | novo parâmetro `market_type` (chaves + `market_id`) |
| market-worker `coverage_publish.{publish,shards_key}` | novo parâmetro `market_type` |
| market-worker `load_market_ids` | **filtro `Market.market_type`** — ver §5 |
| indicators `read_hot_state` | novo kwarg `market_type` |
| scanner `MarketRef` | novo campo `market_type` (default perpétuo; `load_universe` já filtrava `PERPETUAL`) |
| scanner `context.build_market_context`, `coverage.read_coverage`, `checkpoint.{save,load}_checkpoint`, `publish.*` | recebem/propagam o tipo (via `ref.market_type`) |
| strategy `MarketRow` + `load_market` | novo campo/parâmetro e **filtro no WHERE** — ver §5 |
| strategy `hot_state.{read_tail,read_derivatives}`, `derivatives.load_derivatives`, `context`, `consumer` | propagam `market.market_type` / `candle.market_type` |
| api `MarketRepository.get_market` | novo parâmetro + filtro (default perpétuo) |
| api hot state | `pipeline_hot_state` passou a ser chaveado por `markets.id` (era `"{exchange}:{symbol}"`, uma entrada para dois mercados) |

### Resposta à pergunta do brief ("resolvem por `market_id`?")

- **scanner**: resolve por `market_id` para baselines/anomalias/oportunidades
  (`registry.ref_by_id`) e por **símbolo** para hot state/estado em memória. O registry só
  carrega perpétuos (`WHERE market_type = 'perpetual'`), então os mapas em processo
  (`state.markets: dict[str, MarketState]`) continuam por símbolo — sem ambiguidade hoje,
  **item de T3.0c** quando o scanner rodar spot;
- **strategy**: resolvia por **símbolo** em `load_market(exchange, symbol)` com `LIMIT 1` sem
  ordem. Corrigido (§5);
- **api**: `get_market(exchange, symbol)` idem. Corrigido.

## 5. Dois bugs reais fechados (não são só chaves)

1. **`market-worker/load_market_ids`** devolvia `{symbol: id}` a partir de um `SELECT` sem
   `market_type`. Com a linha spot no banco, o dict guardaria **silenciosamente** a última das
   duas e todo `upsert_*` (velas, funding, liquidações, snapshots, OI) gravaria sob o
   `market_id` errado. Nada detecta isso depois: as duas linhas são válidas.
2. **`strategy/load_market` e `api/get_market`** faziam `LIMIT 1` sem ordem sobre
   `(exchange, symbol)`. Devolveriam um listing arbitrário.

Ambos agora filtram por `market_type`, com default `PERPETUAL` — hoje o resultado é idêntico
(não há linha spot em `markets`), amanhã é determinístico.

## 6. Arquivos movidos (orçamento de 350 linhas)

Nenhuma linha de orçamento foi elevada. Quatro extrações, todas com re-export para que nenhum
importador mude:

| Novo arquivo | Saiu de | Por quê |
|---|---|---|
| `packages/core/hunter_core/domain/quality.py` | `domain/market.py` (350 → 347) | `DataQuality`/`data_quality` é um juízo sobre *idade* de payload, não o contrato de payload |
| `services/market-worker/.../market_ids.py` | `persist_rows.py` (350 → 335) | busca de `market_id`, não upsert — e era o arquivo que precisava do filtro de tipo |
| `packages/exchange-adapters/.../binance/parse.py` | `binance/normalize.py` | coerção de valores (`to_decimal`, `ms_to_datetime`, `require_field`, `EXCHANGE`), usada por 4 módulos e por todo o pacote spot |
| `packages/exchange-adapters/.../binance/normalize_derivatives.py` e `streams_derivatives.py` | `normalize.py` / `streams.py` | endpoints/stream **só de perpétuo** (premiumIndex, fundingRate, openInterest, markPrice) — exatamente a linha que o spot desenha |
| `apps/api/hunter_api/services/markets_hot_state.py` | `services/markets.py` (350 → 274) | mesmo padrão que `markets_codec`/`markets_quality` já documentam nesse arquivo |

## 7. O que **não** foi feito (dono: T3.0c) — registrado, não contornado

1. **`market.ticks` e `rt:market:{exchange}:{symbol}` continuam sem o tipo.** O canal é
   validado por `apps/api/hunter_api/realtime/channels.py`
   (`\Art:market:[a-z0-9_-]{1,32}:[\w.-]{1,32}\Z`), que **recusa** um segmento `:` extra — e há
   teste afirmando essa recusa. Mudar isso é gramática de canal + frontend, não cabia aqui.
   O payload também não ganhou o campo porque `test_build_tick_payload_shape` compara o dict
   inteiro. Hoje é inofensivo (o worker não ingere spot); **antes de ligar o spot no
   market-worker isso tem de ser resolvido**, senão dois mercados publicam no mesmo canal.
2. **`heartbeat.py` do market-worker não passa `market_type`** (o construtor de chave já
   aceita). Um shard spot precisa disso, junto com `coverage.py` (que está em 350 linhas
   cravadas e não pôde receber nem uma linha).
3. **`streaming.py: trade_memory.forget(adapter.code, symbol)`** usa o default perpétuo. Com
   spot no mesmo processo, a memória do spot vazaria na saída do universo.
4. **Mapas em processo do scanner por símbolo** (`state.markets`, `deriv`) — ver §4.
5. **`/api/v1/markets/{exchange}/{symbol}` só alcança o perpétuo.** A rota não tem onde dizer
   o tipo; dar essa capacidade é trabalho de UI/contrato.
6. **`universe.py` continua só perpétuos**, como pedido.
7. **Duas grafias de identidade**: `keys.market_slug` (`binance:BTCUSDT` / `binance:spot:BTCUSDT`
   — preserva o que já roda) e `hunter_exchanges.binance_spot.identity.market_identity`
   (`binance:perpetual:BTCUSDT` / `binance:spot:BTCUSDT` — sempre explícita, uso local do
   adaptador). Não foram unificadas porque unificar significaria mudar a string do perpétuo em
   algum dos dois lados. Se um dia forem, `market_identity` é a que deve ceder.

## 8. Ressalvas honestas

- **`apps/api/tests/unit/test_system_workers_status.py` tem 3 falhas pré-existentes**
  (`'_StaticHgetallRedis' object has no attribute 'scan_iter'`): `market_shards.read_collector`
  passou a fazer `SCAN` (T2.5g, arquivo alterado em 06/09 23:21) e o fake do teste nunca foi
  atualizado. Não tem relação com esta tarefa — o fake não implementa o método, qualquer que
  seja o padrão passado.
- **`services/execution-worker/**` estava sendo editado por outro agente durante esta tarefa**
  (mtimes 02:52–03:05 de 07/09). Por isso `uv run pyright packages/core services apps/api`
  termina com 74 erros e `check_file_size.py` acusa `apply.py` com 436 linhas — **tudo em
  `execution-worker`, nada meu**. Com o escopo restrito aos pacotes desta tarefa, pyright dá
  0 erros e o gate de tamanho passa.
- **Testes existentes editados** (só onde a assinatura/forma mudou, como o brief permite):
  `market-worker/tests/test_hot_state.py` e `test_ingest_coalesce.py` (a tupla interna do
  coalescer/TradeMemory virou tripla) e `apps/api/tests/unit/test_markets_quality.py`
  (`_pipeline_hot_state` virou `markets_hot_state.pipeline_hot_state`, chaveado por
  `markets.id`). Nenhuma asserção de comportamento foi afrouxada.
- **O teste novo da API foi escrito depois da implementação** (os demais foram TDD-first).
  Para não ficar por conta da palavra: revertido o `row.market_type` de uma linha de
  `pipeline_hot_state`, ele falha; restaurado, passa — as duas execuções estão no relatório.
- **`tests/integration/test_market_pipeline.py::test_full_pipeline_...` falha por motivo
  pré-existente**, e é reprodutível: na linha 101 ele lê `market.universe.changed` do stream
  logo depois de `refresh_universe`, mas desde a T2.9b esse evento é apenas **enfileirado no
  outbox** dentro da transação (`universe.py` §"Durável por §10b"), e o teste não roda nenhum
  dispatcher. Nada nesta tarefa toca `universe.py`, `durable.py`, `outbox.py` nem a camada de
  eventos; `services/market-worker/tests/test_universe_outbox.py` (que cobre o mesmo caminho
  com o dispatcher) passa 6/6. O outro teste do arquivo passa. Não corrigido: fora do escopo
  declarado (`tests/integration/**` não está na lista da tarefa).
