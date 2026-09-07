## RESUMO

**Recomendo sua proposta de identidade e a opção (i), com duas condições: T3.0a não libera ingestão SPOT no pipeline atual; e a reutilização precisa separar também o roteamento, além dos nomes dos streams.**

Parecer como `exchange-integration-specialist`: **DONE_WITH_CONCERNS**.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executados. Revisão estática do código e consulta à documentação oficial da Binance; compatibilidade dos testes ainda precisa ser comprovada após a implementação.

## MUST-FIX

### 1. Identidade: mantenha `binance`, mas registre uma dependência impeditiva de integração

Faça em T3.0a:

- `adapter.code = 'binance'`;
- atributo explícito `adapter.market_type = MarketType.SPOT`;
- `NormalizedMarket(exchange='binance', market_type=MarketType.SPOT)`;
- demais eventos com `exchange='binance'`, registrando que **a identidade completa depende de T3.0b/core**.

Isso preserva a identidade da venue: o repositório resolve `Exchange` por `code` e diferencia mercados no conflito por `(exchange_id, symbol, market_type)` — [universe_repo.py:30](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:30), [universe_repo.py:88](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:88).

**É seguro entregar esse componente isolado; não é seguro conectá-lo ao pipeline atual.** O atributo do adaptador não acompanha automaticamente o evento serializado. `NormalizedMarket` tem `market_type`, mas ticker/trade/book/candle não; a configuração é `frozen=True, extra="forbid"` — [market.py:111](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:111), [market.py:136](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:136), [market.py:153](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:153), [market.py:179](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:179), [market.py:195](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:195), [market.py:252](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:252).

**Cenário de falha:** ticker SPOT e perpétuo de BTCUSDT escrevem `mkt:binance:BTCUSDT:ticker`; o último sobrescreve o primeiro — [redis.py:140](C:/dev/project-hunter/packages/core/hunter_core/redis.py:140).

Portanto, registre **“requisito cada Normalized* carregar market_type bloqueado pelo escopo; obrigatório antes da integração”**. Não contorne com atributos extras ou subclasses locais. T3.0b precisa preservar o tipo nos eventos, escritores, leitores e identidades de universo/cobertura/liderança, conforme [M3.md:53](C:/dev/project-hunter/docs/plans/M3.md:53).

### Rate limit: mesma venue não significa mesmo orçamento

**Separe os buckets, mantendo o gate compartilhado como política conservadora.** Minha configuração recomendada:

| Componente | Configuração |
|---|---|
| Limitador USDS-M | Manter configuração atual |
| Limitador SPOT | Outra instância, `exchange='binance'`, capacidade inicial `6000`, período `60s` |
| Bucket SPOT | `spot_request_weight` → `rl:binance:spot_request_weight` |
| Gate | `rl:binance:ip:blocked_until`, coordenado pelo mesmo Redis |

O limitador já separa orçamento por `exchange + bucket`, mas vincula o gate ao `exchange` — [rate_limit.py:224](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:224), [rate_limit.py:298](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:298). **Isso evita mudar a infraestrutura para obter `rl:binance_spot:request_weight`.** Com esse namespace alternativo, compartilhar o mesmo objeto gate entre exchanges diferentes provoca `ValueError` — [rate_limit_gate.py:99](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit_gate.py:99).

Use os limites de `exchangeInfo` como autoridade; a documentação exemplifica SPOT com **6000/min** e USDS-M com **2400/min**. Reconcilie cada header exclusivamente no orçamento da respectiva API. [SPOT](https://developers.binance.com/en/docs/products/spot/web-socket-api), [USDS-M](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data).

**Cenário de falha:** duas instâncias com capacidades diferentes operando a mesma chave aplicam parâmetros incompatíveis ao mesmo saldo — [rate_limit.py:224](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:224). Não é apenas desperdício de cota.

Compartilhar o gate entre SPOT/futuros é minha recomendação conservadora; a documentação consultada confirma bloqueios por IP, mas não estabelece explicitamente que um ban SPOT sempre abrange `/fapi`. [Limites REST](https://developers.binance.com/en/docs/products/spot/rest-api).

### 2. Estrutura: opção (i), com propagação completa

Adicione `stream_name_fn: Callable[[str, StreamChannel], str]` **opcional, somente por palavra-chave, com default atual**, nestes pontos:

| Local exato | Alteração |
|---|---|
| [connection.py:138](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:138) | Usar callback na construção da assinatura inicial **e das reconexões**. |
| [subscription_plan.py:57](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscription_plan.py:57) | `names_for()` recebe callback; a chamada direta de `stream_name()` está na linha 58. |
| [subscription_plan.py:93](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscription_plan.py:93) | `plan_updates()` recebe callback e repassa para `names_for()` nas linhas **109 e 127**. |
| [subscriptions.py:51](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:51) | Construtor armazena callback. |
| [subscriptions.py:112](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:112) | `update()` repassa callback para `plan_updates()`. |
| [subscriptions.py:142](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:142) | `catch_up()` repassa callback para `names_for()`. |

**Também injete `split_channels_by_route_fn` no controlador**, com default atual, substituindo a chamada de [subscriptions.py:110](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:110). O `binance_spot/ws.py` deve usar a mesma função na criação inicial dos grupos, agrupando os quatro canais numa rota única, por exemplo `spot`, com chaves `spot:0`, `spot:1`.

**Cenário de falha:** você abre `spot:0`, mas um update usa o splitter de futuros e cria grupos `public:*`/`market:*`; o runner procura URLs dessas rotas num mapa que só contém `spot` — [streams.py:86](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:86), [connection.py:140](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:140).

Reutilize `StreamConsumer` **sem parâmetro novo**: ele recebe eventos já normalizados, não gera nomes — [event_queue.py:245](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:245). O runner já aceita URL e handler de mensagens injetados — [connection.py:62](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:62).

### Dois cuidados adicionais obrigatórios no WS SPOT

**Parsers próprios para book/ticker.** SPOT tem `bookTicker`, contrariando o mapa. Seu payload não traz `E/T`; `depth20` traz `lastUpdateId/bids/asks`, sem símbolo ou timestamp. [Payloads oficiais](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-streams/~).

Os parsers atuais exigem `E/T` e, no depth, `s/b/a/u`: reutilização direta rejeitaria frames válidos — [streams.py:160](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:160), [streams.py:208](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:208), [streams.py:305](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:305). Extraia o símbolo do nome do stream e registre a pendência semântica de timestamp: **hora de recebimento não pode ser apresentada como timestamp fornecido pela exchange**.

**Controle de envio por conexão.** `send_control()` envia imediatamente, sem limitação — [subscriptions.py:179](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:179). Três updates rápidos podem emitir seis frames e desconectar o SPOT. Use um wrapper de conexão SPOT que limite `send()`, preservando o controlador; reserve margem para PING/PONG, que também entram nas cinco mensagens por segundo. [Limites oficiais](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#websocket-limits).

## NICE-TO-HAVE

Mantenha inicialmente **200 símbolos × 4 canais = 800 streams**. Não precisa ampliar para 256 símbolos: o planejamento atual usa 200 e já verifica o teto de 1024 — [subscription_plan.py:61](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscription_plan.py:61), [subscription_plan.py:123](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscription_plan.py:123).

## O QUE EU FARIA DIFERENTE

Manteria `binance/ws.py` inalterado, compondo o cliente SPOT com os componentes compartilhados. **Não chamaria `set_book_cadence_ms()` no SPOT**: ele altera estado global — [streams.py:73](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:73).

Preservaria assinaturas antigas, exports, ordenação dos nomes e defaults. Os testes existentes exigem book de futuros em `500ms` e grupos de 200 — [test_streams.py:34](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_streams.py:34), [test_subscriptions.py:99](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_subscriptions.py:99). Acrescentaria testes SPOT em arquivos novos, sem editar os proibidos.

## CONCORDO COM

Uma venue no banco, identidade de mercado explícita, buckets separados por família de API e reutilização do ciclo de conexão. A pendência de identidade precisa bloquear a integração, não a construção isolada do adaptador.

## OBSIDIAN

- **Exchange Adapters** — registrar identidade SPOT, orçamento REST separado e dependências de T3.0b/core.
- **WebSockets** — documentar rota única SPOT, callbacks, diferenças de payload/timestamp e limite de controle.
- **Market Collector** — registrar que coexistência exige identidade completa em eventos, Redis e coordenação antes da ingestão.