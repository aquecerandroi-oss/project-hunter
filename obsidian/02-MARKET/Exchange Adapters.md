---
tags: [mercado, exchanges, binance, bybit, m1]
updated: 2026-09-05
status: planejado
---

# Exchange Adapters

## Status

**Planejado para o Milestone 1.** O pacote `packages/exchange-adapters` (`hunter_exchanges`) e as classes `BinanceAdapter`/`BybitAdapter` ainda não existem. O que já existe é só a definição da interface (Protocol) em `docs/ARCHITECTURE.md` §6 e o escopo em `docs/EXCHANGE_INTEGRATION.md`.

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
