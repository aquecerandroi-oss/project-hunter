---
tags: [agentes, volume, m4, shadow-lab]
updated: 2026-09-05
status: planejado-sombra
---

# Volume Agent

## Status

**`planejado-sombra`** — desenho fechado pela [[Dialogos/SHADOW|decisão conjunta do Shadow Lab]] (2026-09-05, commit `fc336d9`), **sem implementação e sem ativação**. Vira `sombra` só depois da prova operacional de S0–S2; nenhum item da checklist de aceite foi verificado. O agente completo do MVP, ao lado de [[Momentum Agent]], continua sendo Milestone 4.

Hoje: `strategies.key = volume_anomaly` e `strategy_versions` v1 existem só como seed `status = draft`.

## `volume_anomaly_v1` — parâmetros congelados pela decisão SHADOW

Protocolo do experimento `EXP-0002` (reservado em [[Experiments Index]]); imutável a partir da primeira ativação.

| Item | Valor |
|---|---|
| Timeframe de decisão | **5 min** (fechamentos distintos, UTC) |
| Timeframe de outcome | 1 min |
| Condição de entrada | volume da barra ≥ **4×** a mediana das **288 barras anteriores** de 5 min · fechamento **acima do meio** da barra · `return_5m` entre **0 e 2 ATR%** |
| ATR | **Wilder(14) sobre 15 min** — o timeframe de decisão de 5 min **não** altera implicitamente o timeframe do ATR; seed e âncora persistidos |
| Stop | **mínima da barra do sinal** |
| Alvo (único no v0) | **1,5 ATR** |
| Horizonte | **2 h** contadas da entrada |
| Direção | **LONG apenas** no v0 |

## Duas coisas diferentes com o mesmo nome

Esta é a **variante por velas**: detecta o pico de volume a partir das barras de 5 min persistidas, sozinha, sem depender de nada além do dado do M1. A versão futura do M4 é outra: entra a partir da anomalia `VOLUME_SPIKE` do Anomaly Engine ([[Anomalies]], M2) combinada com `buy_sell_pressure_1m/5m` do order flow. **São versões distintas e comparáveis, nunca a mesma coisa renomeada** — cada uma tem seu `code_ref`, seu `params_hash` e sua própria coorte; comparar as duas exige rodar em paralelo no mesmo intervalo e universo elegível, com cobertura e exclusões reportadas por versão.

## Como a entrada e a saída são medidas

Idêntico ao perfil "por barras" v0 descrito em [[Momentum Agent]]: entrada no open da primeira barra de 1 min posterior a `decision_at` com limite de 120 s desde a barra de referência, geometria revalidada com `P_entry`, custos declarados (spread total 2 bps, slippage 5 bps por lado, taxa 4 bps por lado), gap na abertura antes de toques intrabar, stop e alvo na mesma barra → **stop**, `R_net` nulo com motivo quando o funding aplicável não é apurável.

## Especificação do agente do M4 (inalterada)

Componentes correspondentes no Opportunity Engine: "Volume" (peso padrão 0.20, de `relative_volume_*` e `volume_acceleration`) e "Anomalies" (peso padrão 0.10). Depende do Anomaly Engine do M2 — a versão sombra acima existe justamente para não precisar esperar por ele.

## O que ainda não existe

Nenhum sinal gerado, nenhum outcome, nenhuma versão `v2` para comparar. Sinais do Lab carregam `purpose = research_only` e não são elegíveis a execução: `active` numa versão não implica elegibilidade (o M4 terá `execution_eligible` explícito).

## Relacionadas

[[Agents Overview]] · [[Strategies]] · [[Momentum Agent]] · [[Anomalies]] · [[Experiments Index]] · [[Dialogos/SHADOW]] · [[Agent Performance]] · [[Risk Engine]]

## Fontes

`docs/plans/SHADOW-LAB.md` (decisão conjunta, seção "Desenho") · `.claude/state/dialogue-SHADOW.md` · `docs/PIPELINE.md` §3, §5–6 · `docs/DATABASE.md` §6
