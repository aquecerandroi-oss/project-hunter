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
- Kline final (`x=true`) e o lote de escrita (T3.81): o `market-worker` não escreve cada vela final assim que ela chega — acumula por `MARKET_CANDLE_FLUSH_MS` (padrão 200 ms) antes do `INSERT` em `candles`, para não abrir uma transação por mercado a cada minuto. Esse número é deliberadamente pequeno: a Binance já emite o kline final com um jitter próprio de ~0-2 s depois do fechamento da barra, e um lote longo (1 s, valor anterior) somava o próprio atraso da exchange ao nosso — um candle que chegasse um instante depois do corte do lote pagava outro ciclo inteiro por conta própria (`PIPELINE.md` §6b, T3.81). `MARKET_CANDLE_FLUSH_MS` nunca muda `is_final`, `source` nem a matemática de cobertura (§4 acima) — só quando o lote fecha.

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

## 9. pump.fun — adapter de observação T4.1

`packages/exchange-adapters/hunter_exchanges/pumpfun/` fornece modelos próprios:
`NormalizedMemeTokenCreated`, `NormalizedMemeMigration`, `NormalizedCurveState` e
`NormalizedMayhemOverview`. `NormalizedMemeTrade` é somente contrato, **sem produtor**.
Não implementa execução nem simula livro de ofertas; wiring e persistência são tarefas posteriores.

| Cliente | Fonte e leitura | Limite aplicado |
|---|---|---|
| `PumpPortalWsClient` | `wss://pumpportal.fun/api/data`: `subscribeNewToken`, `subscribeMigration` | Uma conexão por stream; ping/pong 20 s, timeout de ping 20 s, ociosidade 60 s, backoff exponencial com jitter, até 5 falhas consecutivas sem evento válido |
| `PumpFunRestClient` | `https://frontend-api-v3.pump.fun`: `/coins/{mint}`, `/coins/mayhem-mode?limit=&mayhemState=`, `/mayhem/overview` | Token bucket 60 requisições/60 s; 429/418 propaga `RateLimited`, 5xx/transporte têm retentativas limitadas |
| `SolanaRpcClient` | `getAccountInfo`, `base64`, compromisso `finalized`; **T4.2e** `getMultipleAccounts` (`get_mayhem_flows`: curva + `MayhemState` + cofre do agente + mint, 25 mints = 100 contas por chamada, reconciliadas no mesmo slot — `mayhem_state.py`, `docs/PUMPFUN-ONCHAIN.md` §3.5); **T4.2f** `get_curve_states` (`rpc_curves.py`: a curva de 100 mints por `getMultipleAccounts` sobre a PDA `["bonding-curve", mint]`, + `getBlockTime` do slot como `observed_at`; recusas `curve_not_found`/`unsupported_quote`/`curve_emptied`/`malformed` por nome — §5.5) | Bucket 10 requisições/s; no endpoint público, 1 chamada/s por método (os cabeçalhos do próprio RPC dizem `x-ratelimit-method-limit: 10`, `rps 250`); cada chamada de um lote conta **uma** requisição |
| `SwapApiClient` | `https://swap-api.pump.fun/v2/coins/{mint}/trades` (T4.2c, fita com cursor) | **T4.2f:** bucket 16/60 s — o limite real é a regra do Cloudflare (erro 1015, ~20/60 s por IP, bloqueio de 60 s), não o `x-ratelimit-limit: 1000` do backend; o construtor recusa capacidade acima de 20; 429/418 → `HttpRateLimited` com os cabeçalhos (`rate_shared.py`), nunca retentativa silenciosa. **T4.2g:** `market_activity_batch(mints, windows)` → `POST /v1/coins/market-activity/batch` (`market_activity.py`): ≤ 50 mints por requisição (teto do validador, medido), as 10 métricas, janelas `1m`/`5m`/`1h`/`6h`/`24h`; `NormalizedMarketActivity` por mint e janela (contagens, USD como entregue), `observed_at` = `Date` da resposta; `null` = janela sem trade, e `ActivityBatch.windows_live` diz quais janelas a resposta preencheu para alguém; uma requisição do **mesmo** bucket |

Os limitadores são injetáveis e reutilizam `TokenBucketRateLimiter`; sem Redis, o orçamento
é local à instância. O futuro serviço deve compartilhar o orçamento por IP e transformar
`RateLimited` em evento de sistema. O bucket REST permite burst inicial; não prova SLA nem
substitui os limites efetivos do servidor. RPC público é apropriado ao ensaio, não à coleta
contínua de produção. `SOLANA_RPC_URL` é consultada no ambiente do processo (sem carregar
dotenv), ou passada como `rpc_url`; padrão `https://api.mainnet-beta.solana.com`.
Provedor com chave e qualquer serviço pago continuam decisões do Everton.

Reservas normalizadas são `Decimal` em SOL/tokens: lamports ÷ 10⁹ e subunidades ÷ 10⁶.
Market cap teórico = reserva virtual SOL / reserva virtual de tokens × supply, nunca preço
de fill. As constantes iniciais de referência são 30 SOL e 1.073.000.000 tokens; snapshots
usam suas próprias reservas. Conclusão da curva (`complete` e reserva real de tokens zero)
e migração PumpSwap são eventos distintos. Quotes diferentes de SOL são recusadas nas
leituras de curva, em vez de rotular USDC como SOL.

Cada leitura leva `observed_at`, `received_at` e `source`. Nos eventos WS, `created_at` e
`migrated_at` significam **hora local de observação**, pois o frame não informa block time;
não constituem prova de finalidade on-chain. RPC acrescenta slot e compromisso. O chamador
fornece o par mint/conta da curva; derivação e verificação de PDA ficam para o coletor.
O decoder valida owner, discriminador Anchor e booleanos no layout de
[`idl/pump_fun_idl.json`, commit a0540fdc](https://github.com/chainstacklabs/pumpfun-bonkfun-bot/blob/a0540fdc9e6bb108d52f0f512f2e396d2396bdef/idl/pump_fun_idl.json).
Contas com menos de 115 bytes são recusadas; extensões finais não são interpretadas.

Mayhem preserva enabled, estado e modo quando fornecidos. Ausência continua `None`;
enabled on-chain não implica agente ativo. O overview guarda o objeto em `metadata`
explicitamente rotulado, sem inventar uma série de métricas. A API REST é complementar:
leituras REST/RPC não são atômicas, e reservas diferentes não provam erro do decoder.

Dedupe WS usa `(mint, signature)` em FIFO de 10.000 entradas, preservado nas reconexões da
instância. Não é checkpoint durável, não distingue instruções dentro de uma transação e
não recupera gaps. `state.reconnects` sinaliza reconexões; persistência, reconciliação e
finalidade de eventos aguardam o coletor. Não iniciar vários streams simultâneos.

Captura pública em **12/09/2026, 02:20–02:21 BRT**: 11 frames WS em até 55 s;
listagem Mayhem, overview, consulta por mint e RPC responderam HTTP 200. Fixtures cruas e
carimbos estão em `packages/exchange-adapters/tests/fixtures/pumpfun/`; os testes são offline.
Isso comprova acesso anônimo nessa amostra, não disponibilidade permanente.
Segundo a [documentação PumpPortal](https://pumpportal.fun/data-api/real-time/), os dois
canais usados são gratuitos; trades por token/conta são cobrados e não são assinados aqui.
Comandos e saídas desta execução: `.claude/state/notes-T4.1.md`.
