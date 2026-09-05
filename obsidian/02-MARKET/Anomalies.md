---
tags: [mercado, anomalias, m2]
updated: 2026-09-05
status: planejado
---

# Anomalies (Anomaly Engine)

## Status

**Planejado para o Milestone 2**, depende de [[Features]]. Nenhum `AnomalyDetector` existe hoje; a tabela `anomalies` está vazia desde o M0 (schema pronto, sem escrita).

## Especificação (a implementar em `hunter_indicators`)

Cada `AnomalyDetector` compara o valor atual com uma baseline (mediana + MAD sobre janela de 7 dias, mesma hora do dia) e emite `Anomaly {type, severity 0–100, confidence, baseline, current_value, deviation (em MADs), metadata}`.

**MVP (v1):** `VOLUME_SPIKE`, `PRICE_ACCELERATION`, `VOLATILITY_EXPANSION`, `ORDERBOOK_IMBALANCE`, `OPEN_INTEREST_SPIKE`, `FUNDING_ANOMALY`, `LIQUIDATION_CLUSTER`, `CROSS_EXCHANGE_DIVERGENCE` (mesmo símbolo Binance vs Bybit).

**Fase 2/3 (não no MVP):** `SOCIAL_SPIKE`, `WHALE_ACTIVITY`.

**Deduplicação:** uma anomalia `active` por (market, type); atualiza severidade enquanto persistir; `resolved` quando o desvio cai abaixo do limiar por 5 min; `expired` após 4 h.

Persiste em `anomalies` com `feature_snapshot`. Publica `anomalies.detected` (novas ou aumento de severidade ≥ 20).

## Testes planejados

Detectores com spikes sintéticos injetados na série, validando severidade e deduplicação.

## Relacionadas

[[Features]] · [[Data Flow]] · [[Risk Engine]] (componente "Anomalies" no Opportunity Engine)

## Fontes

`docs/PIPELINE.md` §3, `docs/DATABASE.md` §5, `docs/ROADMAP.md` (Milestone 2)
