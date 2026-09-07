# Revisão — T3.0b (`cefad8c`) — REQUEST_CHANGES, deploy seguro (code-reviewer, 2026-09-07)

**Resposta central:** chaves Redis do perpétuo, `event_id`, `radar:scores`, hash do ticker, book, trades, `market.ticks`: **byte a byte iguais**. Única mudança de bytes: a linha msgpack de candle e o payload de `market.candles.closed` ganham `market_type:"perpetual"` (+22 bytes) — não atravessa `code_ref`, `feature_set_version`, `input_fingerprint`; não invalida o `hotcache` (linhas antigas continuam decodificando como PERPETUAL). Mutação: neutralizar `_venue` derruba 12 testes de spot e mantém os de "perpétuo inalterado" verdes.

## A fechar (T3.0d, junto com/depois da T3.0c, que está em `durable.py`)
1. **`durable.py:74-86` — `candle_event_id` e a `key` do envelope não incluem `market_type`.** Com spot ingerido, o candle spot e o perpétuo do mesmo minuto computam o mesmo uuid5 e o `ON CONFLICT (event_id)` do outbox descarta o segundo em silêncio. **Bloqueante para a T3.0c.**
2. **`market_ids.py:47`** — o filtro por tipo não tem teste (duas linhas no banco, como `test_load_market_returns_the_listing_it_was_asked_for` do strategy).
3. **Runbook**: rollback deste commit exige `DEL mkt:*:candles:1m` — código anterior é `extra="forbid"` e não lê a linha nova; uma linha envenena a lista de 1.500 (scanner esvazia o Radar, strategy avalia com tail vazio). → `docs/DEPLOYMENT.md` (feito pelo orquestrador).
4. **Teste**: o hash `mkt:*:ticker` **não** contém `market_type` (exceção deliberada, KB-0044).
5. **Docstrings** de `binance_spot/identity.py:23-33,78` ficaram falsas (o gap foi fechado; a chave real do perpétuo não tem segmento).
Sugestões: `coverage_publish`/`sampling` sem teste do caminho spot; `ingest.py:78` `Any`/`getattr`; +6,6 MB de Redis; `keys.venue(exchange, market_type)` em vez de `market_slug(ex, "", type).rstrip(":")` (a T3.0c já está fazendo isso em `durable.py`).
