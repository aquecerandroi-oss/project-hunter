# T3.0a — Adaptador Binance SPOT (só o pacote de exchanges)

**Data:** 2026-09-06. **Escopo:** `packages/exchange-adapters/**` apenas. Nada em `services/**`,
`packages/core/**`, `apps/**`, `docs/**`, `.env*`. Sem commit.
**Consultas à Astra:** `.claude/state/astra-review-T3.0a-spot.md` (identidade e estrutura, antes de
codar) e a revisão de diff registrada no fim desta nota.

---

## 1. Identidade de mercado — decisão e o que ficou pendente

**Decisão:** opção B do mapa (`.claude/state/map-T3.0-market-identity.md`), na forma que cabe dentro
do escopo desta tarefa:

| Item | Valor | Por quê |
|---|---|---|
| `BinanceSpotAdapter.code` | `"binance"` | Mesma venue: **uma** linha em `exchanges`, um IP, uma superfície de ban 429/418. Opção A (`binance_spot` como exchange própria) exigiria uma segunda linha em `exchanges` e mexeria em ~40 arquivos de `services/**`, que esta tarefa não pode tocar. O banco já discrimina certo: `UNIQUE (exchange_id, symbol, market_type)` em `markets`. |
| `BinanceSpotAdapter.market_type` | `MarketType.SPOT` (atributo de classe, declarado) | É o discriminador. Nunca inferido: um default errado rotularia um par spot como perpétuo. |
| `BinanceAdapter.market_type` | `MarketType.PERPETUAL` (aditivo) | Simetria: quem tem um adaptador e um símbolo consegue montar a identidade completa. Mudança **declarativa**, sem efeito em comportamento; a suíte USDS-M continua verde sem edição de teste. |
| Chave de identidade | `market_identity(exchange, symbol, market_type)` → `"binance:spot:BTCUSDT"` | `hunter_exchanges/binance_spot/identity.py`. Nunca `exchange+symbol`, que é idêntico para o par spot e o perpétuo. |
| `NormalizedMarket` de spot | `exchange="binance"`, `market_type=SPOT` | O upsert de `markets` por `(exchange_id, symbol, market_type)` funciona sem mudança. |

### Pendência bloqueante (registrada, **não** contornada) — dona: T3.0b + `packages/core`

Os modelos de **evento** (`NormalizedTicker`, `NormalizedTrade`, `NormalizedOrderBook`,
`NormalizedCandle`) **não têm** `market_type` — só `NormalizedMarket` tem — e são
`frozen=True, extra="forbid"`. Como esta tarefa não pode editar `packages/core`, um ticker spot e um
ticker perpétuo de `BTCUSDT` continuam, no fio, distinguíveis apenas por **qual adaptador os
produziu**.

Consequência concreta: hoje os dois escreveriam `mkt:binance:BTCUSDT:ticker`
(`hunter_core/redis.py`) e o último sobrescreveria o primeiro.

**Portanto: o adaptador spot está pronto como componente isolado e NÃO deve ser ligado ao
market-worker antes de T3.0b fazer, em `packages/core`:**

1. `market_type` nos quatro modelos de evento (`Normalized*`), com default `PERPETUAL` para não
   quebrar quem já grava, ou obrigatório se preferirem quebrar alto;
2. `market_type` nos builders de chave de `hunter_core/redis.py` (`mkt:`, `feat:`, `opp:`,
   `scan:state:`, `scan:baseline:`) — 8 funções;
3. leitores/escritores do hot state (`market-worker/hot_state.py`, `scanner-worker/context.py`,
   `coverage.for_symbol`) passando `market_type`;
4. `market_type` sempre presente na resposta da API e no Radar/UI.

Não foi usada nenhuma gambiarra (subclasse local do modelo, campo extra em `metadata` do evento,
`exchange="binance_spot"` só nos eventos) — qualquer uma delas esconderia o problema em vez de
resolvê-lo, e `exchange="binance_spot"` num `NormalizedMarket` quebraria a resolução de `exchanges`
por `code`.

---

## 2. Estrutura entregue

Novo subpacote `hunter_exchanges/binance_spot/` (a Astra recomendou reuso por injeção, não
duplicação; a escolha do nome de subpacote foi essa em vez de `binance/spot/**` para não misturar o
namespace do adaptador USDS-M, cujos módulos são globais por design):

| Arquivo | O que é |
|---|---|
| `identity.py` | `EXCHANGE`, `MARKET_TYPE`, `market_identity()`, `MarketTyped` (Protocol aditivo) + o registro da pendência acima |
| `filters.py` | `SpotMarketFilters`, `parse_filters()`, `round_qty_down()`, `check_market_order()`, `price_band()`, `round_price()` |
| `normalize.py` | REST → `Normalized*` (exchangeInfo, ticker/24hr, depth, trades, aggTrades, avgPrice, rateLimits); reutiliza `parse_klines`/`parse_server_time`/`to_decimal`/`ms_to_datetime` do USDS-M |
| `http.py` | Núcleo HTTP: bucket, 429/418, retry/backoff, `X-MBX-USED-WEIGHT-1M` |
| `rest.py` | Endpoints públicos `/api/v3` + tabela de pesos |
| `streams.py` | Nomes de stream, rota única, parsers de frame |
| `throttle.py` | `ThrottledConnection` / `throttled_connect` (5 msg/s por conexão) |
| `ws.py` | `BinanceSpotWsClient` |
| `fees.py` | `SPOT_VIP0`, `SPOT_VIP0_BNB`, `fee_for()` com fonte e política |
| `__init__.py` | `BinanceSpotAdapter` |

**Reuso por injeção** (mudanças aditivas, todas com default = comportamento USDS-M atual; suíte
USDS-M verde sem editar nenhum teste):

- `binance/subscription_plan.py`: `StreamNameFn`, `names_for(..., stream_name_fn=)`,
  `plan_updates(..., stream_name_fn=)`;
- `binance/subscriptions.py`: `SubscriptionController(..., stream_name_fn=, split_channels_fn=)`
  (a Astra apontou o segundo: sem ele um diff de universo planejaria grupos `public:*`/`market:*`
  para um cliente cujo mapa de URLs só conhece `spot`);
- `binance/connection.py`: `ConnectionRunner(..., stream_name_fn=)`.

`ConnectionRunner`, `SubscriptionController`, `StreamConsumer`/`BoundedEventQueue` são reaproveitados
inteiros — backoff com jitter, rotação proativa antes das 24 h, idle timeout, ack deadline,
`connection_generation`, `queue_progress`, `queue_oldest_pending_ts`.

---

## 3. REST: tabela de pesos do SPOT (medida, não copiada)

Medida em 2026-09-06 lendo o delta de `x-mbx-used-weight-1m` a cada chamada real (sem chave).
Orçamento confirmado pelo próprio `exchangeInfo.rateLimits`: **REQUEST_WEIGHT 6000 / 1 MINUTE**
(o USDS-M é 2400/min — orçamentos **independentes**).

| Endpoint | Peso medido | Uso |
|---|---|---|
| `GET /api/v3/time` | 1 | relógio da exchange (candle fechado?) |
| `GET /api/v3/exchangeInfo` | 20 | universo + filtros de ordem MARKET |
| `GET /api/v3/klines` (limit 5 e 1000) | 2 | candles 1m |
| `GET /api/v3/ticker/24hr` 1 símbolo | 2 | preço/volume de um par |
| `GET /api/v3/ticker/24hr` 2 símbolos | 2 | (tabela oficial: 1–20 → 2; 21–100 → 40) |
| `GET /api/v3/ticker/24hr` todos | 80 | piso de 50 M USDT/24 h (D1) |
| `GET /api/v3/depth` limit 20 | 5 | hot state |
| `GET /api/v3/depth` limit 100 | 5 | **walk do livro** |
| `GET /api/v3/depth` limit 500 | 25 | |
| `GET /api/v3/depth` limit 1000 | 50 | |
| `GET /api/v3/trades` limit 5 | 25 | trades crus (caro) |
| `GET /api/v3/aggTrades` limit 5 | 4 | trades agregados (barato) |
| `GET /api/v3/avgPrice` | 2 | referência do filtro `NOTIONAL` para MARKET |

**Bucket:** `rl:binance:spot_request_weight` (capacidade 6000/60 s). **Nunca** o
`rl:binance:request_weight` do USDS-M: são cotas separadas, e dois limitadores com capacidades
diferentes na mesma chave corromperiam os dois (apontado pela Astra). O `IpRateGate` é injetável e
pode ser **compartilhado** com o cliente USDS-M — o ban 429/418 é por IP, não por API.

---

## 4. WebSocket SPOT: limites e decisões

| Item | Valor | Nota |
|---|---|---|
| Endpoint | `wss://stream.binance.com:9443/stream?streams=` | rota **única** (o USDS-M tem `/public` + `/market`) |
| Streams por conexão | 1024 | 200 símbolos × 4 canais = 800 |
| Mensagens de entrada por conexão | **5/s** | inclui PONG; nosso orçamento é 4/s (`CONTROL_SEND_BUDGET_PER_S`), 1 slot reservado para o PONG da lib |
| Tentativas de conexão | 300 / 5 min / IP | respeitado pelo backoff 1 s→60 s com jitter |
| Vida da conexão | 24 h | rotação proativa em ~23,5 h com jitter (reuso do `ConnectionRunner`) |
| Canais | `@aggTrade`, `@bookTicker`, `@kline_1m`, `@depth20@100ms` | |

**Confirmado contra a API real (o mapa T3.0 estava errado nisto):** o spot **tem**
`<symbol>@bookTicker`. O que não existe no spot: funding, open interest, mark price, liquidação — o
adaptador **recusa** (`ExchangeError` não-retryable) em vez de devolver zero.

**Decisão `@depth20@100ms` (e não `@depth@100ms` + `lastUpdateId`):** o walk do livro que o
simulador precisa vem do REST `depth?limit=100` (peso 5) no instante da decisão; a stream serve o hot
state e o preço de execução, onde um snapshot consistente de 20 níveis a cada 100 ms é mais seguro do
que manter livro local por diff (que exigiria snapshot REST + fila de buffers + ressincronização por
`U`/`u` a cada reconexão, com risco de livro divergente silencioso). O **check de sequência** existe
mesmo assim: `lastUpdateId` tem de crescer estritamente por símbolo, senão o frame é descartado e
contado em `out_of_sequence_count`.

**Achado honesto e importante — carimbo de tempo:** no spot, `@bookTicker` e `@depth20` **não trazem
tempo de evento algum** (confirmado nos frames gravados: `{"u","s","b","B","a","A"}` e
`{"lastUpdateId","bids","asks"}`), e o `depth20` também **não traz símbolo** (vem do nome da stream).
Como os modelos de evento exigem `ts`, esses dois canais são carimbados com a **hora de recepção**, e
`ts == received_at` exatamente — é assim que o leitor distingue "sem relógio da exchange" de um
`ts` real. `@aggTrade` e `@kline_1m` mantêm o tempo da exchange (`T`/`E`). O REST `depth` tem o mesmo
problema e a mesma solução. **Para a T3.0b/T3.1:** medir latência spot com esse `ts` seria medir zero;
qualquer métrica de latência do livro spot precisa vir de outra fonte (`aggTrade`).

---

## 5. Filtros de ordem MARKET (spot)

Lidos de `exchangeInfo` e expostos em `NormalizedMarket.metadata["spot_market_filters"]` (rótulo
explícito, `docs/EXCHANGE_INTEGRATION.md` §2):

- `LOT_SIZE` (`minQty`/`maxQty`/`stepSize`) e `MARKET_LOT_SIZE` (idem, e `stepSize=0` significa "não
  aplicado a market"): a quantidade é **arredondada para baixo** ao passo mais grosso dos dois;
- `NOTIONAL` com `minNotional`/`applyMinToMarket`/`maxNotional`/`applyMaxToMarket`/`avgPriceMins`
  (campo real da API hoje; a forma legada `MIN_NOTIONAL` + `applyToMarket` também é aceita). Para
  MARKET a referência de preço é o **`avgPrice` dos últimos `avgPriceMins` minutos**
  (`/api/v3/avgPrice`), **não** o último trade; com `avgPriceMins == 0` a Binance usa o último preço.
  **Sem `avgPrice` disponível a checagem recusa** (`reason="avg_price_unavailable"`) em vez de
  substituir por outro preço;
- `PRICE_FILTER` → `round_price()` arredonda **contra** a operação (compra paga o tick de cima, venda
  recebe o de baixo);
- `PERCENT_PRICE_BY_SIDE` → `price_band()`. **Registrado:** na Binance esse filtro limita preço de
  ordem **limitada**; a exchange não recusa MARKET por causa dele. Aqui ele é uma **guarda nossa** de
  sanidade para um fill simulado que andou o livro, e está rotulado como tal no código.

---

## 6. Taxas SPOT — fonte, política e a diferença para `AssumedCosts`

| Cronograma | Maker | Taker | Fonte |
|---|---|---|---|
| Spot VIP 0, sem BNB (**padrão**) | 0,1000 % | 0,1000 % | tabela de taxas spot da Binance, VIP 0 |
| Spot VIP 0 com dedução BNB | 0,0750 % | 0,0750 % | 25 % de desconto sobre a linha acima |
| USDS-M VIP 0 (**nunca herdar**) | 0,0200 % | 0,0500 % | produto diferente — herdar subestimaria todo custo |

**Política declarada:** padrão `SPOT_VIP0` (0,1 %/0,1 %, **sem** BNB) — a carteira não tem BNB, e
supor um desconto que não temos deixaria todo resultado simulado melhor que a realidade. VIP > 0
também não é assumido (R$100.000 está longe de qualquer tier). `fee_for()` arredonda o custo com
`ROUND_HALF_UP` em 8 casas.

**Diferença para o contrato do Lab (para a T3.4):** `hunter_core.strategies.envelope.AssumedCosts`
(`spread_bps`, `slippage_bps`, `fee_bps`, `max_entry_delay_s`) é a **hipótese declarada e congelada**
de um experimento shadow, presa à versão da estratégia para que um R hipotético continue comparável.
O que está em `fees.py` é a **taxa publicada** da venue onde a carteira executa de verdade. A T3.4
pode ler essa taxa para *escolher* um `fee_bps`, mas a hipótese congelada de um experimento não muda
porque a Binance mudou a tabela — e vice-versa. Não são o mesmo número nem o mesmo contrato.

---

## 7. Fixtures gravadas (API pública, sem chave)

Gravadas por `hunter_exchanges/testing/record_spot.py` em 2026-09-06 (`spot_*.json`):
`spot_server_time`, `spot_exchange_info` (BTC/ETH/BNB/SOL/XRP USDT + **NEOBTC `BREAK`** (halt) +
**ETHBTC** (quote não-USDT), com o bloco `rateLimits` inteiro), `spot_klines`, `spot_ticker_24hr`,
`spot_ticker_24hr_all`, `spot_depth` (20), `spot_depth_100`, `spot_trades`, `spot_agg_trades`,
`spot_avg_price`, e os frames de WS com envelope: `spot_ws_kline_1m`, `spot_ws_depth20`,
`spot_ws_agg_trade`, `spot_ws_book_ticker`. Nenhuma foi montada à mão.

Casos obrigatórios cobertos offline: **símbolo delistado/halt** (NEOBTC filtrado + `400 -1121` no
REST como erro não-retryable), **candle duplicado** (paginação com sobreposição de página não repete
`open_time`), **livro fora de sequência** (`lastUpdateId` que não avança é descartado), **reconexão
com gap** (socket cai, cliente reconecta sozinho, o minuto do meio não aparece e
`connection_generation()` avança — é o sinal que abre `ingestion_gaps`), **mensagem malformada**
(JSON inválido, campo faltando, stream desconhecida: contados e ignorados, nunca propagados).

Teste `live` opt-in (`HUNTER_LIVE_TESTS=1`, marcador `live`, nunca em CI):
`tests/live/test_live_binance_spot.py` — confirma o teto de 6000/min no `exchangeInfo`, mede o
universo acima do piso de 50 M, e abre **3 streams por 20 s** medindo eventos/s, malformadas e
frames fora de sequência.

---

## 8. Pendências e ressalvas honestas

1. **Bloqueador de integração (§1):** `market_type` nos eventos + nas chaves do Redis, antes de o
   market-worker ingerir spot. Sem isso, spot e perpétuo colidem no hot state.
2. **Duplicação consciente:** `binance_spot/http.py` repete a lógica de 429/418/retry de
   `binance/rest.py::_get` (~90 linhas). Foi decidido duplicar para não arriscar a suíte USDS-M de
   505 linhas que não posso editar. **Sugestão para T3.1:** unificar num `binance/http.py`
   compartilhado com as duas suítes verdes.
3. **`PERCENT_PRICE_BY_SIDE`** é guarda nossa, não regra da exchange para MARKET (§5).
4. **Livro spot sem relógio da exchange** (§4) — impacta qualquer métrica de latência do livro.
5. **`services/market-worker/hunter_market_worker/coverage.py` está com 377 linhas** (acima do
   orçamento de 350) desde `fe8872c` (T2.5e) — pré-existente, fora do meu escopo, mas
   `check_file_size.py` falha por causa dele.
6. **4 erros de pyright pré-existentes** em `tests/unit/test_event_queue.py`
   (`reportPrivateUsage`, `_pending_get`), arquivo que não toquei. Todos os meus arquivos passam.
7. **`fetch_trades` (peso 25)** é seis vezes mais caro que `fetch_agg_trades` (peso 4): quem for usar
   no backfill deve preferir aggTrades.

---

## 9. Revisão de diff da Astra (`.claude/state/astra-review-T3.0a-spot-diff.md`) — 2 MUST-FIX aplicados

1. **PING automático estourava o orçamento de 5 msg/s.** `websockets.connect` usa
   `ping_interval=20` por padrão: manda um PING **nosso** a cada 20 s, e a Binance conta PING e PONG
   no mesmo teto das nossas mensagens de controle (4 controles + PING + PONG = 6 numa janela → a
   conexão cai). **Corrigido:** `binance_spot/throttle.py::spot_connect` abre com
   `ping_interval=None` (a lib continua respondendo automaticamente aos pings do servidor; socket
   morto é pego pelo idle timeout de 60 s do `ConnectionRunner`), e há teste da configuração.
2. **`fetch_candles` não respeitava `[start, end)`.** O `endTime` da Binance é **inclusivo**, então
   `[12:00, 12:30)` trazia a barra das 12:30 — que, dependendo do relógio do servidor, chegaria com
   `is_final=True` e contaminaria uma janela histórica de volume. **Corrigido:** envia
   `endTime = end_ms - 1` e filtra `start <= open_time < end` na saída, com teste de fronteira. O
   teste de paginação também virou paginação de verdade (`klines_page_limit` injetável = 3; com o
   limite de 1000 a segunda página nunca era pedida).

Também aplicados (nice-to-have / "o que eu faria diferente" da Astra):

3. `duplicate_book_count` separado de `out_of_sequence_count`: `lastUpdateId` **igual** é livro
   inalterado republicado (duplicata, `debug`); **menor** é regressão (`warning`). Os dois continuam
   descartados, mas uma regressão real não fica enterrada sob repetições inofensivas.
4. `fee_for()` passou de `ROUND_HALF_UP` para `ROUND_CEILING`: um custo arredondado "para o mais
   próximo" às vezes fica mais barato que a realidade, e esse número alimenta resultado simulado.

Aceito pela Astra sem mudança: `ts=received_at` como fallback documentado; `@depth20@100ms` + REST
`depth=100` para o walk (com as três cautelas para a T3.4: livro elegível **após** a latência, não
misturar top-20 novo com níveis 21–100 antigos, não extrapolar quantidade além dos níveis
observados); duplicação temporária do núcleo HTTP.

---

## 10. Medição real (teste `live`, 2026-09-06)

`HUNTER_LIVE_TESTS=1 uv run pytest packages/exchange-adapters/tests/live/test_live_binance_spot.py -m live -s`

```
spot USDT pairs: 487; >= 50M USDT/24h: 19
BTCUSDT min_qty=0.00001000 avg=80182.86070643 -> MarketOrderCheck(ok=False, qty=0.00001000,
    notional=0.8018286070643000, reason='min_notional')
2684 events in 19.9s of streaming (134.7/s), 26.8s wall including teardown;
breakdown={'book:BTCUSDT': 186, 'book:ETHUSDT': 184, 'trade:ETHUSDT': 58, 'ticker:ETHUSDT': 799,
           'trade:BTCUSDT': 90, 'ticker:BTCUSDT': 1367};
out_of_sequence=0; duplicates=0; malformed=0; generation=0
4 passed
```

Três coisas para quem for tocar T3.0b/T3.4:

- **Universo real:** hoje são **19** pares spot USDT acima de 50 M USDT/24 h (de 487 pares USDT
  listados). A D1 estimava "~50 pares"; o número medido é bem menor e varia com o dia. Quem
  dimensionar conexões/streams deve usar o número medido, não a estimativa.
- **`min_notional` morde:** a quantidade mínima de LOT_SIZE do BTCUSDT (0,00001 BTC ≈ 0,80 USDT) é
  **recusada** pelo filtro `NOTIONAL` (piso de 5 USDT). O simulador precisa tratar essa recusa como
  um motivo de decisão, não como erro.
- **Teardown dentro do cancelamento:** cancelar o `stream()` faz o `on_close` do `StreamConsumer`
  (código compartilhado com o USDS-M) rodar **dentro** do desenrolar do cancelamento — no teste,
  ~6,9 s entre o último evento e o retorno. Não é streaming: é desligamento. O teste mede a taxa até
  o **último evento** e reporta o wall separadamente, para não vender 26,8 s como janela de dados.
  Vale olhar isso no shutdown do worker (T3.0b).

**Ressalva adicional:** `binance_spot/ws.py` está com 345 linhas (orçamento 350). A próxima adição
nesse arquivo tem de vir acompanhada de uma extração.
