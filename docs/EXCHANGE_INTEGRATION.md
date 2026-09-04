# Integração com exchanges

## 1. Escopo do MVP

| Exchange | Segmento | REST público | WS público | Privado |
|---|---|---|---|---|
| Binance | USDS-M Futures (perpétuos USDT) | exchangeInfo, klines, ticker/24hr, depth, premiumIndex, fundingRate, openInterest, openInterestHist | aggTrade, bookTicker, depth20@100ms/depth@250ms, kline_1m, markPrice@1s, forceOrder | Fase 3+ |
| Bybit | Linear (perpétuos USDT) | instruments-info, kline, tickers, orderbook, funding/history, open-interest | publicTrade, orderbook.25, kline.1, tickers, liquidation | Fase 3+ |

Spot fica no adapter (`market_type=spot`) para listagem e candles, mas não é monitorado no MVP.

## 2. Contrato `ExchangeAdapter`

Ver `ARCHITECTURE.md` §6. Regras:
- O adapter **só** fala o dialeto da exchange e devolve modelos `Normalized*`. Nenhum campo cru vaza para fora do pacote `hunter_exchanges`, exceto em `metadata` explicitamente rotulado.
- Timestamps: `ts` = hora da exchange (event time); `received_at` = hora local. Ambos em UTC.
- Símbolos: interno = símbolo da exchange sem separadores (`BTCUSDT`) mais `exchange_code` e `market_type`. O mesmo base asset em duas exchanges é ligado por `assets` para a anomalia `CROSS_EXCHANGE_DIVERGENCE`.
- Precisão: `Decimal` para preço e quantidade; `tick_size`, `step_size`, `min_notional`, `contract_size` lidos de `exchangeInfo`/`instruments-info` e persistidos em `markets`.

## 3. Modelos normalizados

```
NormalizedMarket      exchange, symbol, market_type, base, quote, status, tick_size, step_size, min_notional,
                      contract_size, max_leverage, metadata
NormalizedTicker      exchange, symbol, ts, last, bid, ask, bid_qty, ask_qty, volume_24h, quote_volume_24h,
                      high_24h, low_24h, change_24h_pct
NormalizedTrade       exchange, symbol, ts, trade_id, price, qty, side (taker side), is_block (opcional)
NormalizedOrderBook   exchange, symbol, ts, bids[(price, qty)], asks[(price, qty)], sequence, is_snapshot
NormalizedCandle      exchange, symbol, timeframe, open_time, close_time, o, h, l, c, volume, quote_volume,
                      trade_count, taker_buy_volume, is_final
NormalizedFunding     exchange, symbol, ts, funding_rate, next_funding_time, mark_price, index_price
NormalizedOpenInterest exchange, symbol, ts, open_interest, open_interest_value
NormalizedLiquidation exchange, symbol, ts, side, qty, price, notional
```

## 4. WebSocket: conexão e resiliência

- Binance: até 1024 streams por conexão; usamos no máximo 200 símbolos × 5 streams = 1000 por conexão, logo 1 conexão por 200 símbolos. Ping/pong conforme doc; reconectar antes das 24 h de vida da conexão.
- Bybit: `subscribe` em lotes de 10 args; heartbeat `ping` a cada 20 s.
- Reconexão: backoff exponencial 1 s → 60 s com jitter; ao reconectar, snapshot REST do book e verificação de gaps de candle.
- Book: manter livro local a partir de snapshot + diffs (Binance) ou snapshot/delta (Bybit); checar sequência; ressincronizar ao detectar salto.
- Heartbeat por exchange em `hb:market:{exchange}` com `last_event_at`; `/system` mostra `stale` se > 10 s.

## 5. REST e rate limit

- Token bucket por exchange em Redis (`rl:{exchange}:{bucket}`) com os pesos oficiais (Binance: weight por endpoint, 2400/min; Bybit: 120 req/5 s por endpoint group). Recovery e universo têm prioridade sobre consultas de UI.
- Resposta `429`/`418` → backoff e `system_event warning`; IP banido → `critical`.
- Chaves de sistema (`BINANCE_API_KEY` etc.) são opcionais e servem só para elevar limites de dados públicos. Nunca têm permissão de trade.

## 6. Testes

- Fixtures gravadas (JSON de respostas REST e sequências de mensagens WS) por exchange em `hunter_exchanges/testing/fixtures/`; testes de parse e normalização rodam offline.
- Teste de contrato opcional (`pytest -m live`) que bate na API pública real, fora do CI padrão.
- Cenários obrigatórios: símbolo delistado, candle duplicado, book fora de sequência, reconexão com gap, mensagem malformada.

## 7. Roadmap de exchanges

| Fase | Exchange | Motivo |
|---|---|---|
| MVP | Binance, Bybit | Maior liquidez em perpétuos |
| 3 | OKX, Hyperliquid | Perpétuos com dados ricos; Hyperliquid é on-chain |
| 3 | Coinbase, Kraken | Spot institucional; pouca cobertura de derivativos |

## 8. Conexões privadas (Fase 3)

- Criação: OWNER/ADMIN informa key/secret → `api` valida assinatura chamando `fetch_permissions()` **antes** de persistir → se `withdraw=true`, rejeita com mensagem clara → cifra e grava → audit.
- Uso: só o execution-worker descriptografa, e só quando `ENABLE_LIVE_TRADING` e o entitlement da org permitem.
- Rotação: nova conexão substitui a antiga; a antiga vai a `revoked` e o material cifrado é apagado após 7 dias.
