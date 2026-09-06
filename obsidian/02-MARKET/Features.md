---
tags: [mercado, features, m2]
updated: 2026-09-06
status: implementado, sem scanner
---

# Features (Feature Engine)

## Status

**`implementado, sem scanner`.** T2.2 (commit `487bc4a`, 2026-09-05) entregou `hunter_indicators.features` completo e testado: `MarketContext` carregado do hot state do `market-worker` (msgpack, mais-novo-primeiro, campos de timestamp sombra), as calculadoras — a mensagem do commit fala em 28 —, `FeatureVector` com qualidade e proveniência por feature, e um checkpoint de ATR de Wilder ancorado. `feature_set_version` está fixado em teste como `a2b12fcd…cac51` (`.claude/state/notes-T2.2.md` §"DEFAULT_REGISTRY.feature_set_version"). Prova real: 232 testes passando, `ruff`/`format`/`pyright` limpos, revisão de código aprovada, cross-review de outro quant reproduzindo ATR e features de forma independente (3 must-fix corrigidos com teste) e 4 rodadas de revisão da Astra absorvidas.

**O que falta para valer em produção: nada calcula isto sobre o universo ao vivo.** Não existe `scanner-worker` — é a T2.5 do plano do M2 (`docs/plans/M2.md`), que consome `market.ticks`/`market.candles.closed` e roda as calculadoras nas cadências do pipeline. Até a T2.5 (e a T2.4, que depende destas features para o Regime/Opportunity Engine) fecharem, `feature_definitions`/`feature_snapshots` continuam sem uma linha escrita fora dos testes. **Não há nenhum número de produção para citar aqui** — nenhuma cobertura, nenhuma taxa de qualidade, nada medido contra mercado real; só a suíte sintética do pacote.

Três features ficam **honestamente indisponíveis** até a T2.5 trazer cobertura do coletor e histórico de derivativos (`.claude/state/notes-T2.2.md` §11) — o commit não lista quais no stat, então não afirmo os nomes aqui sem conferir o `quality.py`.

## Especificação (a implementar em `hunter_indicators`)

Cada `FeatureCalculator` é registrado com `FeatureDefinition {name, version, parameters, description, inputs}`. A versão do conjunto (`feature_set_version`) é o hash ordenado de todas as definições ativas — confirmado no código: `packages/indicators/hunter_indicators/features/definitions.py` constrói o hash com `canonical_json` e exclui a descrição de propósito (reescrever prosa não pode invalidar `feature_snapshots.feature_set_version` já gravados). Contexto por mercado em memória: últimos 1500 candles 1m, book atual, últimos trades, derivativos, mais BTC como referência.

**Anti-look-ahead, já com código e teste** (não mais só regra de design): candle em formação só entra nas features marcadas `_live`; livros cruzados/travados e livros curtos são recusados com motivo, nunca um número errado (`test_no_lookahead.py`, T2.2).

### Features do MVP (v1) — spec original; ver acima o que T2.2 efetivamente entregou

| Grupo | Features |
|---|---|
| Preço | `price_return_1m/5m/15m/1h/4h`, `distance_from_24h_high_pct`, `distance_from_24h_low_pct`, `breakout_strength_20` |
| Volume | `relative_volume_5m/15m/1h`, `volume_acceleration`, `quote_volume_1h` |
| Volatilidade | `volatility_5m/1h`, `atr_14_pct`, `volatility_ratio` |
| Microestrutura | `spread_pct`, `orderbook_imbalance_5/25`, `buy_sell_pressure_1m/5m`, `trade_velocity_1m` |
| Momentum | `momentum_15m`, `momentum_acceleration`, `rsi_14`, `ema_ratio_9_21` |
| Derivativos | `funding_rate`, `funding_change_8h`, `open_interest_change_1h/4h`, `oi_price_divergence`, `liquidation_pressure_1h` |
| Cross | `btc_correlation_1h`, `market_beta_1h`, `relative_strength_vs_btc_1h` |

Saída planejada quando o scanner existir: `FeatureVector {market_id, ts, feature_set_version, values}` para Redis `feat:*` e evento `features.updated`. Persistência em `feature_snapshots` apenas no fechamento de minuto — hoje o `FeatureVector` já existe e é montado em memória pelos testes; a publicação em Redis/Postgres é trabalho da T2.5.

## Comportamento sob falha

**Implementado, não só planejado:** `hunter_indicators/features/quality.py` (T2.2) já julga cada entrada por sua própria função — uma feature só herda a qualidade das entradas que de fato usou, então um histórico de funding ainda aquecendo não degrada um retorno perfeitamente bom. A política de frescor é versionada (`quality_v1`) porque mudar o orçamento muda quais snapshots contam como degradados. O que ainda não existe é o efeito rio abaixo: bloquear anomalias/oportunidades a partir de `quality=degraded` é papel do `scanner-worker` (T2.5) e do Anomaly/Opportunity Engine (T2.3/T2.4), que ainda não leem este vetor em produção.

## Testes

Implementados em T2.2 (232 testes, `packages/indicators/tests/unit/test_{atr,context,definitions,deriv,engine,hotstate,micro,price,trend,vector,volume,windows}.py`): cada feature com série sintética e valor esperado; anti-look-ahead dedicado (`test_no_lookahead.py` — feature não muda quando um candle não-final muda; livros cruzados/travados/curtos recusados com motivo). O que falta é o nível de integração: rodar isso contra o universo ao vivo é a prova operacional da T2.8, ainda não feita.

## Relacionadas

[[Market Collector]] · [[Anomalies]] · [[Data Flow]] · [[Workers]]

## Fontes

`docs/PIPELINE.md` §2, `docs/ARCHITECTURE.md` §6, `docs/plans/M2.md` (T2.2, T2.5), commit `487bc4a`, `.claude/state/notes-T2.2.md`
