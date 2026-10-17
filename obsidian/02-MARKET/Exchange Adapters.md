---
tags: [mercado, exchanges, binance, bybit, m1]
updated: 2026-10-17
status: implementado
owner: sexta-feira
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

### Eventos on-chain da pump.fun/PumpSwap (T4.8e, 05/10/2026)

Os decodificadores de evento (`hunter_exchanges/pumpfun/trade_event_codec.py`, `pumpswap/sell_event.py`) validam a
**cauda depois dos campos variáveis**, aceitam só os comprimentos vistos na cadeia e expõem a cauda sem nome
(`trailing_u64`) sem somá-la; `scan_trade_event_logs` separa "sem `TradeEvent`" de "`TradeEvent` indecodificável".
Contexto e checklist do pino em [[T4.8e-decoders]]; o incidente em [[Open Bugs]].

**T4.8f (05/10):** o `sell` da PumpSwap passou a exigir remaining accounts (`pool_v2` quando o pool tem coin
creator; recipient de buyback e o ATA dele; em pool cashback, o acumulador antes) — achado pela simulação dos nossos
bytes, não pelas fixtures. O builder (`pumpswap/tx.py`) e o `GlobalConfig` decodificado (`buyback_fee_recipients`)
seguem isso; `program_watch.py` vigia o slot de deploy da PumpSwap e do programa de taxas ao lado do pump. Detalhe,
simulações e limites em [[T4.8f-pumpswap-guard]].

**Programa inteiro, por `logsSubscribe` (onda 0 de H-030, 05/10):** um `logsSubscribe` com `mentions` no programa entrega a transação inteira, com os eventos como linhas `Program data:` (os dois programas as emitem antes do self-CPI), e **53 % das transações entregues só mencionam o programa**. A identidade correta do evento é `(assinatura, programa, ordinal)` e a atribuição vem da pilha de `invoke` do próprio log. Os decodificadores da T4.8e leram 100 % dos `TradeEvent` e `SellEvent` ao vivo (~1,2 milhão de eventos); o `BuyEvent` da PumpSwap (36 % dos swaps) ainda não tem decodificador. Números, custo do RPC pago e achados laterais (tx versão 1; slot de ≈ 268 ms) em [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar|KB-0183]].

**Onda 1a do H-030 (05/10/2026) — `BuyEvent` e leitor de logs do programa inteiro.** Três módulos novos em `hunter_exchanges`, **sem ligar a nenhum worker**:
`pumpswap/buy_event.py` (decodificador do `BuyEvent`, 36 % dos swaps: cauda de 49 B aceita, qualquer outra, inclusive nenhuma, recusada com `BuyEventError`; nunca soma a cauda sem nome),
`pumpfun/swap_record.py` (um registro `SwapRecord` para o `TradeEvent` da curva, o `BuyEvent` e o `SellEvent`: SOL bruto de taxas + `fee_lamports` + `lp_fee_lamports`, tudo em `int`; reservas sempre **pós-trade**,
na pool derivadas do fluxo exato do cofre e provadas contra o trade seguinte; `virtual_quote_reserves` para cotar a pool) e `pumpfun/program_logs.py` (leitor puro `logs → SwapRecord`:
atribuição pela pilha de `invoke` — estrita, contexto quebrado vira lacuna —, identidade `(assinatura, programa, ordinal)` com o ordinal reservado antes de validar, contadores para tudo o que não é swap limpo e `gap` para o coletor).
O `BuyEvent` tem armadilhas só vistas na cadeia (campos trocados no `buy_exact_quote_in`, reservas de antes do trade, quote virtual, cashback): [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro|KB-0184]]. Fixtures **reais** `t1a_*` com proveniência em `tests/fixtures/t1a_provenance.json`.
`SolanaTxRpcClient.get_transaction` e `WalletRpc.get_transaction` pedem `maxSupportedTransactionVersion: 1` (com `0` o nó recusa toda transação versão 1 com `-32015`; [[Resolved Bugs]]). Revisão: [[wallets-1a]].

**Onda 1b do H-030 (05/10/2026, fim da noite) — o registro diz a completude da curva e as mints da pool.** Dois módulos novos, ainda **sem ligar a nenhum worker**:
`pumpfun/curve_completion.py` (decodificador do `CompleteEvent`, 144 B, qualquer outro tamanho recusado; o tri-estado `complete` / `not_complete` / `unknown` de `SwapRecord.curve_completion`, pontual: `real_token_reserves` depois do trade corroborado pelo `CompleteEvent` do próprio programa, nunca por leitura posterior da conta) e
`pumpswap/pool_legs.py` (casa o evento com a instrução de swap, direta ou por roteador, pelas contas 0, 1, 5 e 6 e anexa `base_mint`/`quote_mint`, conferidos contra os saldos de token dos cofres; `quote_is_sol` vem da mint da quote e `wsol_is_base` marca as pools com WSOL na base). `SwapRecord` ganha `real_token_reserves`, `curve_completion` (+ `curve_complete`), `base_mint`, `quote_mint` e as contas de token do usuário. `read_transaction_logs` (REST/recuperação) anexa as pernas e conta `pool_mints_unresolved` e `pool_mints_conflict` (**não** são lacuna); `read_program_logs` (logs de um `logsSubscribe`) não tem contas e as deixa `None`. **Perto de dois quintos dos eventos de pool são em pools com WSOL na base** (41,6 % numa amostra de 40 blocos) e as instruções `SellV2`, `BuyExactQuoteInV2` e `BoostBuyAndBurn` ainda não têm layout: [[Open Bugs]]. Prova, fixtures `t1b_*` com proveniência em `tests/fixtures/t1b_provenance.json` e medição: [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro|KB-0184]]. Revisão: [[wallets-1b-record]]. **Integração pendente na ponte** (`hunter_indicators.meme.wallets.bridge`, outro dono): ela ainda exige `curve_complete=record.curve_complete` e `PoolMints(pool, record.base_mint, record.quote_mint)` passados pelo chamador; os campos novos existem no registro, mas a ponte não os lê sozinha, e cada recusa dela é buraco de cobertura da fita. `orphan_complete_events` é lacuna (inclui o `CompleteEvent` cujo trade fechador ainda tinha tokens: o que drena sumiu); `pool_mints_unresolved`, `pool_mints_conflict`, `pool_mints_via_sibling` (mints certas por construção, mas a invocação é de um swap desconhecido como `SellV2`, que só empresta a evidência de uma conhecida) e `curve_completion_unknown` não são. Limite: o casamento evento → instrução é por pool, usuário e contas, não por invocação; só `encoding=json` é entendido (`jsonParsed` dá `unresolved`, sem atribuição errada).

### Adaptador MT5 — robô B3 do Everton (R2, 17/10/2026; nada ligado a worker)

`packages/exchange-adapters/hunter_exchanges/mt5/` (tarefa R2 do desenho `docs/design/robo-b3-mt5.md` §9, contrato
`docs/RISK_ENGINE_B3.md`, pós-congelamento). Não é um `ExchangeAdapter` de mercado: é a **porta** `Mt5Port` (Protocol) de
tudo que o robô precisa do MetaTrader 5 — ler terminal/conta/símbolo/tick/posições/ordens/negócios (com `magic` e `reason`),
`order_check`, margem, e três mutações: entrada com `sl`/`tp` anexados, `TRADE_ACTION_SLTP` e cancelamento. Forma e regras:

- **`float` só na fronteira** (`convert.py`/`builders.py`/`parse.py`): saindo, o valor tem de ser múltiplo exato do tick/step
  (senão `Mt5NotSent`, nunca arredonda); entrando, 1 ULP de ruído volta exato à grade e o que não é de grade (VWAP de
  `price_open`) fica com o repr curto, sem recusar um relato do terminal. Dinheiro da conta usa `currency_digits`.
- **Antes do terminal, nomeado:** `would_delete_stop` (aumenta/inverte com `sl=0`, a armadilha do *netting*), `would_loosen_stop`,
  SLTP com `sl=0`/mais largo que o confirmado ou que o piso/ticket que não é o atual/posição de outro `magic`. Redução e fechamento
  total **nunca** são recusados por isso. Depois que a requisição pode ter saído (`None`, exceção, estouro de prazo) não há
  exceção: é `SendOutcome` com veredito `UNCERTAIN` — nunca reenviar.
- **Tabela de retcodes fechada por ação × retcode** (`retcodes.py`): construída para os 41 códigos × 3 ações; o que não está numa
  linha terminal da própria ação é incerto (`PLACED`/`DONE_PARTIAL` não concluem uma SLTP; só `DONE` aceita um cancelamento, e
  cancelado só com a ordem final no histórico).
- **Uma pista IPC com prazo** (`ipc.py`): um fio, `ipc_call_timeout_s`, trava `ipc_hung` que só cai com reinício; trabalho em fila
  que não começou nunca começa depois da trava; envio cujo `await` foi cancelado deixa a pista `unresolved` (nenhuma mutação nova)
  até o resultado tardio — normalizado, nunca o objeto cru — ser recolhido em `drain_late_results()`. SLTP também é recusada
  localmente se o nível ficaria do lado errado do toque (`floor_unplaceable`, §4.2).
- **Vigia da especificação** (`spec.py`): divergência de tick/step/modo/versões recusa entradas e é *latched*; 3 falhas seguidas =
  `UNREADABLE`; só `rearm` limpa. Saídas seguem.
- **Segredo:** a API não tem onde pôr `login`/`password`/`server`; `initialize` só recebe `path`/`timeout`; a conta é
  `account_hash`. `MetaTrader5` só é importado sob demanda e só no Windows (a CI Linux importa o pacote sem a roda).
- **Teste:** o falso (`services/b3-robot/tests/fakes/mt5_fake.py` e vizinhos, rotulado FAKE) fala a superfície do módulo
  `MetaTrader5` (floats, tuplas nomeadas); a suíte de contrato em `tests/mt5/` roda contra ele e, marcada `live` (e só com
  `HUNTER_LIVE_TESTS=1` + `HUNTER_LIVE_MT5_SYMBOL`, só em conta DEMO), contra um terminal. Revisão: [[Revisoes-Astra/R2-mt5-adapter|R2-mt5-adapter]].

**Premissas sobre o terminal que o código assume e só a sessão demo confirma:** `positions_get`/`orders_get` devolvem `()` quando não há
nada e `None` só em erro (`None` vira `Mt5ReadError`, nunca lista vazia); `history_orders_get(ticket=…)` devolve `()` para ticket
desconhecido; `order_check` aprova com `retcode 0`; o `time` do tick é o relógio do servidor, sem correção (T11 mede o
deslocamento). O `TRADE_RETCODE_HEDGE_PROHIBITED` (10046) está na documentação da MetaQuotes mas **não** na roda 5.0.6231.
O falso é uma hipótese de modelagem (reversão = dois negócios, parcial de IOC = `CANCELED`), não a Rico.

## Relacionadas

[[Market Collector]] · [[WebSockets]] · [[System Overview]] · [[Execution Engine]]

## Fontes

`docs/EXCHANGE_INTEGRATION.md`, `docs/ARCHITECTURE.md` §6
