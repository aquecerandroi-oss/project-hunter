# Mapeamento de Identidade de Mercado T3.0 — SPOT vs Perpétuos

**Objetivo:** localizar todos os pontos de colisão quando `BTCUSDT` coexistir como SPOT e como perpétuo USDS-M na Binance.

**Contexto:** `docs/plans/M3.md` T3.0 — "Caminho de dados SPOT", exigindo "identidade de mercado sem colisão com perpétuos (chaves do hot state, do universo, de cobertura, de liderança e dos eventos por `market_type`)".

---

## 1. Tabela de Pontos de Identidade

| Arquivo | Linha | Tipo | O que Colide | Sugestão |
|---------|-------|------|-------------|----------|
| `packages/core/hunter_core/redis.py` | 140–165 | Redis key builder | `mkt:{exchange}:{symbol}:ticker` (ambos BTCUSDT sobrescrevem) | Adicionar `:{market_type}` antes de `:ticker` |
| idem | idem | idem | `mkt:{exchange}:{symbol}:book` | Idem |
| idem | idem | idem | `mkt:{exchange}:{symbol}:trades` | Idem |
| idem | idem | idem | `mkt:{exchange}:{symbol}:candles:1m` | Idem |
| idem | idem | idem | `feat:{exchange}:{symbol}` | Idem para features |
| idem | idem | idem | `opp:{exchange}:{symbol}` | Idem para oportunidades |
| idem | idem | idem | `scan:state:{exchange}:{symbol}` | Idem para scanner state |
| idem | idem | idem | `scan:baseline:{exchange}:{symbol}` | Idem para baseline |
| `services/scanner-worker/hunter_scanner_worker/context.py` | 127 | Hot state reader | `read_hot_state(redis, exchange, symbol)` sem market_type | Assinar: `read_hot_state(..., market_type: str)` |
| idem | 96 | Coverage reader | `coverage.for_symbol(symbol)` | Assinar: `for_symbol(symbol, market_type)` |
| `services/market-worker/hunter_market_worker/hot_state.py` | 100+ | Hot state writer | Escreve sem market_type na chave | Passar `market_type` ao chamar `keys.*()` |

---

## 2. Estado Atual de `markets` Tabela

**Já existe:**
- Coluna `market_type ENUM` (spot | perpetual) — linha 62 de markets.py
- Constraint `UNIQUE (exchange_id, symbol, market_type)` — linha 54
- Upsert em universe_repo.py linha 88 já usa market_type no conflict index

**Status:** DB está **correto**. Problema é **Redis** — chaves não discriminam tipo.

---

## 3. Duas Opções de Solução (Prós/Contras)

### Opção A: Exchange Codes Distintos (binance_spot vs binance_usdm)

Prós:
- Redis jamais colide; natural para keys baseadas em exchange_code

Contras:
- 40+ arquivos afetados: toda query `WHERE exchange_id = ?` precisa duplicação ou loop
- Seed cria dois Exchange rows para uma venue
- Breaking change em API pública

Arquivos Afetados:
- `services/market-worker/universe.py` leader/follower logic
- `services/market-worker/universe_repo.py` rank_and_monitor filtering
- `services/scanner-worker/**/` all exchange filtering
- `services/strategy-worker/**/` pricing and derivatives

### Opção B: Incluir market_type na Chave Redis

Prós:
- Localizado: só 10–12 arquivos (redis builders, market-worker writes, scanner reads)
- Uma única Exchange row; queries já funcionam com existente WHERE ... AND market_type = ?

Contras:
- Domain contract change: NormalizedEvent (NormalizedTicker, NormalizedTrade, etc.) precisa carregar market_type
- Requer passar market_type em 8 builders de redis.py

Arquivos Afetados:
- `packages/core/hunter_core/redis.py` (key builders)
- `packages/core/hunter_core/domain/market.py` (Normalized* models)
- `services/market-worker/hot_state.py` (write calls)
- `services/market-worker/ingest.py` (demux)
- `services/scanner-worker/context.py` (read_hot_state)
- `services/strategy-worker/hot_state.py` (pricing)

---

## 4. Reaproveitamento Adaptador Binance para SPOT

**100% Reutilizável:**
- Kline parser (OHLCV structure identical)
- Depth/orderbook parser (bids/asks format)
- Aggregate trades parser (price, qty, side)
- Symbol convention (BTCUSDT without separators)

**URLs Diferem:**
- `/fapi/v1/` (perpetual) → `/api/v3/` (spot)
- `/fapi/v1/exchangeInfo` vs `/api/v3/exchangeInfo`

**Não Existe em SPOT:**
- bookTicker stream (use depth stream instead)
- Funding rate stream
- Open interest stream
- Liquidations stream
- Premium index

---

## 5. Piso de 50M: Leitura de Volume por Venue

**Fluxo:**
1. `universe.py` chama `adapter.list_markets(MarketType.SPOT)`
2. `_fetch_tickers()` retorna `quote_volume_24h` em USDT
3. `upsert_markets()` persiste volume (linha 78)
4. `rank_and_monitor()` filtra com `volume_24h_usd >= 50_000_000`

**Mudança:** Adicionar threshold absoluto de volume (não só rank):
```python
# universe_repo.py::rank_and_monitor
min_volume = 50_000_000  # for SPOT; perpetual has settings.market_universe_size
eligible_rows = [r for r in rows if r.volume_24h_usd is None or r.volume_24h_usd >= min_volume]
```

---

## 6. Riscos S2 e Radar

### S2: agent_signals.market_id aponta perpétuo
- Risk: novo sinal gerado em perpétuo; antigo código tenta carregar "BTCUSDT" sem type specification
- Mitigation: sempre WHERE market_id = ? (é UUID, unívoco) ou WHERE symbol AND market_type = PERPETUAL

### Radar: opp:{exchange}:{symbol} armazena score
- Risk: duas opportunities (spot + perp) aparecem como uma na lista
- Mitigation: always return market_type in API response; use market_type em Redis key ou skip caching

---

## 7. Hold Durável para Posições Paper

**Problema:** `tracking_hold_symbols()` lê ShadowEpisode; não cobre posições paper abertas

**Solução:**
```python
# Estender universe_repo.py
async def portfolio_hold_symbols(session, exchange_id, portfolio_id):
    rows = await session.scalars(
        select(Market.symbol)
        .join(Position, Position.market_id == Market.id)
        .where(Market.exchange_id == exchange_id,
               Position.portfolio_id == portfolio_id,
               Position.status == 'open')
    )
    return set(rows)

# No refresh_universe(), agregar:
holds = await tracking_hold_symbols(...) | await portfolio_hold_symbols(...)
```

Depois, no rank_and_monitor, respeitar holds even if rank falls.

---

## 8. Resposta Curta: Impacto por Opção

**Opção A (distinct codes):**
- Custo: Alto (40 arquivos)
- Benefício: natural para exchange-keyed Redis
- Risco: breaking change pública

**Opção B (market_type na chave):**
- Custo: Médio (10 arquivos)
- Benefício: local, contracts já contêm market_type
- Risco: baixo, domain change contido

**Recomendação:** Opção B é mais circunscrito. Opção A mais elegante se banco de dados for renomeado para city-level (spot vs perp como two venues).

---

## 9. Checklist T3.0

- [ ] Escolher opção (A ou B) com Everton
- [ ] Se B: adicionar `market_type` a NormalizedEvent (6 models)
- [ ] Se B: atualizar redis.py key builders (8 functions)
- [ ] Implementar `BinanceSpotAdapter` reutilizando parsers
- [ ] Hold durável: estender universe_repo + portfolios schema
- [ ] Filtro volume ≥ 50M em rank_and_monitor
- [ ] Testes de coexistência sem colisão em redis/scanner/radar
- [ ] API response: sempre incluir `market_type`
- [ ] Radar/UI: exibir tipo (SPOT vs PERP)
