---
tags: [agentes, volume, m4]
updated: 2026-09-05
status: planejado
---

# Volume Agent

## Status

**Planejado para o Milestone 4** — a segunda estratégia do MVP, ao lado de [[Momentum Agent]]. Sem implementação hoje; `strategies.key = volume_anomaly` e `strategy_versions` v1 existem só como seed `status=draft`.

## Especificação (a implementar)

Estratégia `volume_anomaly_v1`: entrada após detecção de anomalia `VOLUME_SPIKE` (ver [[Anomalies]]) combinada com pressão compradora ou vendedora (`buy_sell_pressure_1m/5m`). Stop posicionado na mínima (long) ou máxima (short) do próprio spike.

Depende diretamente do Anomaly Engine (M2) estar rodando antes de poder gerar qualquer sinal — não pode ser implementado isoladamente do restante do pipeline.

Componente correspondente no Opportunity Engine: "Volume" (peso padrão 0.20), a partir de `relative_volume_*` e `volume_acceleration`; e "Anomalies" (peso padrão 0.10), soma ponderada de severidade das anomalias ativas.

## O que ainda não existe

Nenhum sinal gerado, nenhuma versão `v2` ainda para comparar. Quando a primeira versão rodar por tempo suficiente, esta página passa a linkar para [[Experiments Index]] com os `EXP-NNNN` correspondentes.

## Relacionadas

[[Agents Overview]] · [[Strategies]] · [[Anomalies]] · [[Agent Performance]]

## Fontes

`docs/PIPELINE.md` §3, §5–6, `docs/DATABASE.md` §6
