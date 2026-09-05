---
tags: [mercado, features, m2]
updated: 2026-09-05
status: planejado
---

# Features (Feature Engine)

## Status

**Planejado para o Milestone 2**, depende do Market Collector (M1) existir primeiro. Hoje não há nenhum `FeatureCalculator` implementado; a tabela `feature_definitions`/`feature_snapshots` existe vazia desde o M0.

## Especificação (a implementar em `hunter_indicators`)

Cada `FeatureCalculator` é registrado com `FeatureDefinition {name, version, parameters, description, inputs}`. A versão do conjunto (`feature_set_version`) é o hash ordenado de todas as definições ativas. Contexto por mercado em memória: últimos 1500 candles 1m, book atual, últimos trades, derivativos, mais BTC como referência.

### Features do MVP (v1)

| Grupo | Features |
|---|---|
| Preço | `price_return_1m/5m/15m/1h/4h`, `distance_from_24h_high_pct`, `distance_from_24h_low_pct`, `breakout_strength_20` |
| Volume | `relative_volume_5m/15m/1h`, `volume_acceleration`, `quote_volume_1h` |
| Volatilidade | `volatility_5m/1h`, `atr_14_pct`, `volatility_ratio` |
| Microestrutura | `spread_pct`, `orderbook_imbalance_5/25`, `buy_sell_pressure_1m/5m`, `trade_velocity_1m` |
| Momentum | `momentum_15m`, `momentum_acceleration`, `rsi_14`, `ema_ratio_9_21` |
| Derivativos | `funding_rate`, `funding_change_8h`, `open_interest_change_1h/4h`, `oi_price_divergence`, `liquidation_pressure_1h` |
| Cross | `btc_correlation_1h`, `market_beta_1h`, `relative_strength_vs_btc_1h` |

Saída: `FeatureVector {market_id, ts, feature_set_version, values}` para Redis `feat:*` e evento `features.updated`. Persistência em `feature_snapshots` apenas no fechamento de minuto.

**Anti-look-ahead** (regra de design a testar): bar-features usam só candles `is_final`; o candle em formação entra apenas nas tick-features, marcadas `_live`.

## Comportamento sob falha (planejado)

Dados `degraded` → features marcadas `quality=degraded` e não alimentam anomalias nem oportunidades até o gap fechar.

## Testes planejados

Cada feature com série sintética e valor esperado; teste específico de anti-look-ahead (feature não muda quando um candle não-final muda).

## Relacionadas

[[Market Collector]] · [[Anomalies]] · [[Data Flow]]

## Fontes

`docs/PIPELINE.md` §2, `docs/ARCHITECTURE.md` §6, `docs/ROADMAP.md` (Milestone 2)
