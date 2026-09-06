---
tags: [mercado, anomalias, m2]
updated: 2026-09-06
status: implementado, sem scanner
---

# Anomalies (Anomaly Engine)

## Status

**`implementado, sem scanner`.** T2.3 (commit `72cfe72`, 2026-09-06) entregou `hunter_indicators.baselines`, `hunter_indicators.anomalies` e `hunter_indicators.stage` completos e testados, sobre as calculadoras de [[Features]] (T2.2). Prova real: 462 testes passando, `ruff`/`format`/`pyright`/`check_file_size` limpos, revisão de código aprovada, cross-review de quant (2 must-fix corrigidos) e rodadas de design/diff/fixes da Astra absorvendo 7 bugs reais.

**O que falta para valer em produção: mesma lacuna de [[Features]] — não existe `scanner-worker`.** É a T2.5 do plano do M2 (`docs/plans/M2.md`) que vai ler `feature_snapshots`, alimentar as baselines em produção e escrever em `anomalies`. Até lá a tabela `anomalies` continua vazia fora dos testes, e **não há nenhum número de produção para citar** — nenhuma contagem de anomalias reais, nenhuma taxa de disparo, nada medido contra mercado. `EXP-0003-baselines-v1` (as primeiras 24 h reais) é entregável da T2.8, não deste commit.

## O que T2.3 entregou de fato (conferido no diff, `72cfe72`)

**Baselines (`hunter_indicators/baselines/`).** Imutáveis: cada revisão é só inserida, nunca sobrescrita (`revision.py`). A estatística é mediana + MAD **exata**, ambas em `Decimal` (`compute.py: median`, `median_absolute_deviation`) sobre janelas semi-abertas `[window_start, window_end)` de 420 observações (7 dias × 1/hora). O **corte causal é duplo**, não um só: `available_at <= as_of` **e** `window_end < observation_ts` (`projection.py`) — a segunda condição existe porque uma feature das 10:00 processada às 10:02 passaria no primeiro corte sozinho contra uma revisão publicada às 10:01 que já continha as 10:00. O gate de usabilidade é aplicado pelo **leitor** (`BaselineGate` em `revision.py`), nunca congelado como booleano na linha gravada. Bootstrap de 7 dias reusa as mesmas calculadoras do T2.2, provado byte-idêntico ao cálculo ao vivo (bar-only).

**Anomalias (`hunter_indicators/anomalies/`).** `d = (x − mediana)/MAD`, severidade `clip((|d|−1)/5·100)` (piso de disparo 40 = 3 MADs, piso de manutenção 20 = 2 MADs — política declarada, não calibração histórica). **10 detectores registrados, 8 armados e 2 desarmados com motivo legível por máquina**: `VOLUME_SPIKE`, `PRICE_ACCELERATION`, `MOMENTUM_SHIFT`, `VOLATILITY_EXPANSION`, `ORDERBOOK_IMBALANCE`, `TRADE_VELOCITY_SPIKE`, `OPEN_INTEREST_SPIKE`, `FUNDING_ANOMALY` armados; `LIQUIDATION_CLUSTER` (falta `liquidation_pressure_1h`, que não existe em `MarketContext` v1) e `CROSS_EXCHANGE_DIVERGENCE` (precisa de uma segunda exchange, M1b) desarmados. **Isso já é uma divergência da spec original desta página**: o MVP planejado listava `VOLUME_SPIKE, PRICE_ACCELERATION, VOLATILITY_EXPANSION, ORDERBOOK_IMBALANCE, OPEN_INTEREST_SPIKE, FUNDING_ANOMALY, LIQUIDATION_CLUSTER, CROSS_EXCHANGE_DIVERGENCE` (8, sem `MOMENTUM_SHIFT`/`TRADE_VELOCITY_SPIKE`); o código entregue tem 10, com dois novos tipos armados e os dois que dependiam de pré-requisitos externos corretamente desarmados em vez de fingidos. Ciclo de vida `active → resolved/expired` é uma máquina **pura** sobre dados (`lifecycle.py`): nunca resolve por ausência nem por relógio sozinho — precisa de 5 leituras (não 5 minutos corridos) provadamente abaixo do piso de manutenção; dado ausente ou degradado mantém `active` com `evaluation_state = unknown`/`stale` e **quebra** a sequência; expira em 4 h de qualquer forma; uma linha `active` por `(market, type)`.

**Estágio (`hunter_indicators/stage/`).** `r = |return_1h| / atr_14_pct` sobre o ATR de Wilder ancorado do T2.2. `EARLY` só com as quatro confirmações da diretiva, precedência entre estágios, histerese de 2 observações, invalidação imediata, direção publicada sobrevive a restart, retirada ≠ substituição. Puro: sem relógio, sem IO.

**Fase 2/3 (fora do MVP e sem mudança):** `SOCIAL_SPIKE`, `WHALE_ACTIVITY` continuam não implementados.

## Especificação (histórico, para contexto do que mudou)

Persiste em `anomalies` com `feature_snapshot` — ainda não escrito em produção, ver acima. Publica `anomalies.detected` (novas ou aumento de severidade ≥ 20) — publicação é trabalho da T2.5.

## Testes

Implementados em T2.3: detectores com spikes sintéticos injetados na série (`test_anomaly_detectors.py`), ciclo de vida (`test_anomaly_lifecycle.py`, 513 linhas), pipeline ponta a ponta em memória (`test_anomaly_pipeline.py`), severidade (`test_anomaly_severity.py`), baselines (`test_baselines_bootstrap.py`, `test_baselines_collect.py`, `test_baselines_compute.py`, `test_baselines_sql.py`, `test_baselines_store.py`), anti-look-ahead específico do T2.3 (`test_no_lookahead_t23.py`), estágio (`test_stage.py`, 613 linhas) e o contrato dos pesos (`test_weights_contract.py`). O que falta é a prova operacional — scanner rodando 5 min/24 h contra o `market-worker` real (T2.5/T2.8), ainda não feita.

## Relacionadas

[[Features]] · [[Data Flow]] · [[Workers]] · [[Risk Engine]] (componente "Anomalies" no Opportunity Engine)

## Fontes

`docs/PIPELINE.md` §3, `docs/DATABASE.md` §5, `docs/plans/M2.md` (T2.3, T2.5), commit `72cfe72`, `.claude/state/notes-T2.3.md`
