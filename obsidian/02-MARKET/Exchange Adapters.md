---
tags: [mercado, exchanges, binance, bybit, m1]
updated: 2026-09-05
status: implementado
---

# Exchange Adapters

## Status

**Binance USDS-M: implementado** (público, commit `97c36ff`, 2026-09-05, T1.2 + T1.2b). **Bybit Linear: planejado** (M1b, mesmo contrato). Conexões privadas continuam Fase 3+.

### Binance USDS-M — o que existe

| Arquivo | Papel |
|---|---|
| `packages/exchange-adapters/hunter_exchanges/base.py` | Protocol `ExchangeAdapter`, `ExchangeAdapterExtras` (capacidades T1.2b), `ConnectionState`, `ExchangeError`/`RateLimited` |
| `.../binance/rest.py` | `exchangeInfo`, `klines`, `ticker/24hr`, `depth`, `premiumIndex`, `fundingRate` (paginado), `openInterest`, `serverTime` |
| `.../binance/ws.py` + `.../binance/connection.py` | cliente WS combinado, laço de conexão/rotação/backoff, `restart_connection(key)` |
| `.../binance/subscriptions.py` + `subscription_plan.py` | `update_subscriptions` diff-only, grupos estáveis, JSON-RPC SUBSCRIBE/UNSUBSCRIBE com ACK, catch-up |
| `.../binance/streams.py` + `normalize.py` | parse de cada canal e de cada rota REST para os `Normalized*` de `hunter_core.domain.market` |
| `.../binance/event_queue.py` | fila limitada que nunca descarta kline final |
| `.../rate_limit.py` | token bucket em Redis (`rl:binance:{bucket}`), bucket próprio de histórico de funding, gate de IP com `Retry-After` |
| `.../testing/` | `FakeExchangeAdapter`, `record.py` e as fixtures gravadas da API pública real |

Decisões que valem como contrato: `fetch_funding()` devolve a **estimativa** do `premiumIndex` com `funding_kind="estimated"` (uma chamada HTTP); o histórico **realizado** sai só de `fetch_realized_funding()` (`/fapi/v1/fundingRate`, `ts` = instante do settlement, paginado). O limite de 1024 streams por conexão é asserido no código (levanta, nunca trunca).

Testes: `uv run pytest packages/exchange-adapters` → **189 passed, 3 skipped**; `HUNTER_LIVE_TESTS=1 uv run pytest packages/exchange-adapters -m live` → **3 passed**, com dado real recebido nas duas rotas (ACK sozinho não conta como prova de vida).

### Limitações conhecidas (aceitas no M1)

Detalhe e cenário de falha de cada uma em `docs/plans/M1.md` → "Limitações conhecidas do M1": cooldown de rate limit não persiste entre processos (M1 assume um processo por IP); reconciliação do header de peso é por instância; rotação de conexão sem sobreposição (buraco do handshake, sub-segundo no caso normal); janela de ~31 s para detectar leitor morto; `last_data_event_*` avança em frame duplicado (o gate de progresso aceito é do worker); fila limitada por número de itens, não por bytes/idade; regenerar fixtures exige rodar o recorder com rede.

## Escopo do MVP

| Exchange | Segmento | REST público | WS público | Privado |
|---|---|---|---|---|
| Binance | USDS-M Futures (perpétuos USDT) | exchangeInfo, klines, ticker/24hr, depth, premiumIndex, fundingRate, openInterest | aggTrade, bookTicker, depth, kline_1m, markPrice@1s, forceOrder | Fase 3+ |
| Bybit | Linear (perpétuos USDT) | instruments-info, kline, tickers, orderbook, funding/history, open-interest | publicTrade, orderbook.25, kline.1, tickers, liquidation | Fase 3+ |

Spot fica no adapter para listagem/candles, mas não é monitorado no MVP.

## Contrato `ExchangeAdapter` (interface definida, sem implementação)

```python
class ExchangeAdapter(Protocol):
    code: str
    async def list_markets(self, market_type) -> list[NormalizedMarket]: ...
    async def fetch_candles(self, symbol, timeframe, start, end) -> list[NormalizedCandle]: ...
    async def fetch_ticker(self, symbol) -> NormalizedTicker: ...
    async def fetch_order_book(self, symbol, depth=25) -> NormalizedOrderBook: ...
    async def fetch_funding(self, symbol) -> NormalizedFunding: ...
    async def fetch_open_interest(self, symbol) -> NormalizedOpenInterest: ...
    def stream(self, symbols, channels) -> AsyncIterator[NormalizedEvent]: ...
    # privado (pós-MVP, só execution-worker): place_order, cancel_order, fetch_permissions
```

Regras a valer quando implementado: o adapter só fala o dialeto da exchange, nenhum campo cru vaza para fora do pacote (exceto `metadata` rotulado); `Decimal` para preço/quantidade; `tick_size`/`step_size`/`min_notional`/`contract_size` persistidos em `markets`.

## Testes planejados

Fixtures gravadas (JSON de REST e sequências WS) em `hunter_exchanges/testing/fixtures/`, testes offline. Teste de contrato opcional (`pytest -m live`) fora do CI padrão. Cenários obrigatórios: símbolo delistado, candle duplicado, book fora de sequência, reconexão com gap, mensagem malformada.

## Roadmap de exchanges

| Fase | Exchange | Motivo |
|---|---|---|
| MVP | Binance, Bybit | Maior liquidez em perpétuos |
| 3 | OKX, Hyperliquid | Perpétuos com dados ricos |
| 3 | Coinbase, Kraken | Spot institucional |

Conexões privadas (chaves de usuário, trading real) são Fase 3+ e passam por `fetch_permissions()` antes de persistir — chave com `withdraw=true` é sempre rejeitada (ver [[Risk Engine]] e `docs/SECURITY.md`).

## Relacionadas

[[Market Collector]] · [[WebSockets]] · [[System Overview]]

## Fontes

`docs/EXCHANGE_INTEGRATION.md`, `docs/ARCHITECTURE.md` §6
