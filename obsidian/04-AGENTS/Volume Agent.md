---
tags: [agentes, volume, m4, shadow-lab]
updated: 2026-09-06
status: sombra
---

# Volume Agent

## Status

**`sombra`** desde 2026-09-06, com prova operacional em `.claude/state/s2-proof.md`.
`volume_anomaly v1` foi ativada pelo script auditado em 2026-09-05 23:20:09 UTC e sucedida por `v2`
em 2026-09-06 02:08:19 UTC (correção do `code_ref`, não mudança de estratégia). Contagens da
primeira avaliação datada, `as_of = 2026-09-06T02:55:00Z`: **107 sinais emitidos** (92 na coorte v1,
15 na v2), **72 acompanhamentos encerrados avaliáveis**, e as três populações de exclusão que a
decisão conjunta manda separar apareceram todas — `late:delay` (11), `geometry` (5) e censura por
gap (1). Números, SQL e leitura em [[EXP-0002-volume-anomaly-v1]].

O agente completo do MVP, ao lado de [[Momentum Agent]], continua sendo Milestone 4: não há
carteira, ordem, posição nem PnL.

## `volume_anomaly_v1` — parâmetros congelados pela decisão SHADOW

Protocolo do experimento [[EXP-0002-volume-anomaly-v1]]; imutável desde a primeira ativação.
`params_hash = fa5dce78173b2b9688578f7c96a5f37544eb504aa7b2227262ad296c32f63bb9`
(`params_format = 1`), idêntico em v1 e v2.

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

## O que já existe e o que ainda não existe

**Existe:** decisões sombra de 5 min sobre o mercado real, entradas hipotéticas por barras,
outcomes com `R_net`, e a recusa explícita de entrar quando a geometria não fecha
(`no_entry: geometry`, 5 casos na primeira avaliação) — com stop na mínima da barra do sinal, uma
barra de pico com corpo grande coloca a entrada acima do alvo, e a versão prefere não entrar a
inventar geometria.

**Não existe:** a versão do M4 baseada na anomalia `VOLUME_SPIKE` do Anomaly Engine e no order
flow — é **outra versão**, comparável em paralelo, nunca esta renomeada. Também não existe
execução: sinais do Lab carregam `purpose = research_only` e não são elegíveis; `active` numa
versão não implica elegibilidade (o M4 terá `execution_eligible` explícito).

## Relacionadas

[[Agents Overview]] · [[Strategies]] · [[Momentum Agent]] · [[Anomalies]] · [[Experiments Index]] · [[EXP-0002-volume-anomaly-v1]] · [[Dialogos/SHADOW]] · [[Agent Performance]] · [[Strategy Performance]] · [[Workers]] · [[Risk Engine]]

## Fontes

`docs/plans/SHADOW-LAB.md` (decisão conjunta, seção "Desenho") · `.claude/state/dialogue-SHADOW.md` · `docs/PIPELINE.md` §3, §5–6 · `docs/DATABASE.md` §6
