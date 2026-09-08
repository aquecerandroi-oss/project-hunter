---
tags: [mercado, features, m2]
updated: 2026-09-07
status: implementado
owner: sexta-feira
---

# Features (Feature Engine)

## Status

**`implementado`.** T2.2 (commit `487bc4a`, 2026-09-05) entregou `hunter_indicators.features` completo e testado: `MarketContext` carregado do hot state do `market-worker` (msgpack, mais-novo-primeiro, campos de timestamp sombra), as calculadoras — a mensagem do commit fala em 28 —, `FeatureVector` com qualidade e proveniência por feature, e um checkpoint de ATR de Wilder ancorado. `feature_set_version` está fixado em teste como `a2b12fcd…cac51` (`.claude/state/notes-T2.2.md` §"DEFAULT_REGISTRY.feature_set_version"). Prova real: 232 testes passando, `ruff`/`format`/`pyright` limpos, revisão de código aprovada, cross-review de outro quant reproduzindo ATR e features de forma independente (3 must-fix corrigidos com teste) e 4 rodadas de revisão da Astra absorvidas.

**Atualização de 2026-09-07: agora existe quem calcule isto sobre o universo ao vivo.** O `scanner-worker` (T2.5, `551d542`, e as sucessoras até `9ceb389`) roda as calculadoras nas cadências do pipeline contra os 200 mercados monitorados da Binance. Os números de produção que faltavam nesta página, lidos hoje em modo somente-leitura:

| Medida | VPS (2026-09-07T03:24Z) | Local (mesma hora) |
|---|---|---|
| `feature_snapshots` gravadas | **108.688** sobre 212 mercados | 128.786 sobre 216 mercados |
| Início da série viva | 2026-09-06T18:17Z (9 h 07 min) | 2026-09-06T15:35Z (11 h 49 min) |
| `feature_definitions` seedadas | 28 | 28 |
| Revisões de baseline vigentes | 88.746 | 73.051 |

**E a limitação medida, que é o achado desta página.** Das 27 features com baseline, **12 têm ao menos um bucket utilizável e 15 têm zero** — e as 15 são exatamente as de **tape** (`trade_velocity_1m`, `buy_pressure_5m`, `sell_pressure_5m`), **livro** (`spread_pct`, `orderbook_imbalance_20`), **derivativos** (`funding_rate`, `open_interest_change_1h/4h`) e todas as `_live`. O motivo é estrutural e estava declarado desde a T2.3: o bootstrap sobre candles persistidas **não pode** produzir baseline de tape nem de livro (`historical_source_unavailable`), então elas só amadurecem com 7 dias de `feature_snapshots` ao vivo. A contagem completa, com o SQL e a saída real, está em [[EXP-0003-baselines-v1]]; a consequência rio abaixo (teto de score 25,00 de 100) está em `docs/reports/M2.md`.

Na melhor feature, **29 dos 200 mercados** têm bucket utilizável. Na prova operacional de 2026-09-06 (`.claude/state/t25-proof.md` §3), num minuto fechado sobre 202 mercados, `trade_velocity_1m` saiu com `quality = ok` em **179** mercados e `orderbook_imbalance_20`/`spread_pct` em **86** — qualidade de dado é uma coisa, maturidade de baseline é outra, e a página separa as duas de propósito.

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
