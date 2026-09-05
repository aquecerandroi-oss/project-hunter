---
tags: [agentes, momentum, m4]
updated: 2026-09-05
status: planejado
---

# Momentum Agent

## Status

**Planejado para o Milestone 4** — uma das duas estratégias do MVP (`docs/PIPELINE.md` §6). Sem implementação hoje; `strategies.key = momentum` e `strategy_versions` v1 existem só como linha de seed com `status=draft`.

## Especificação (a implementar)

Estratégia `momentum_v1`: entrada em continuação de movimento, condicionada a volume relativo e força de rompimento (breakout). Stop dimensionado em ATR; alvos definidos em múltiplos de R (risco:retorno).

Features de suporte previstas (de [[Features]]): `momentum_15m`, `momentum_acceleration`, `ema_ratio_9_21`, `breakout_strength_20`, `relative_volume_5m/15m/1h`.

Componente correspondente no Opportunity Engine: "Momentum" (peso padrão 0.20 em `opportunity_weights`), soma de `momentum_15m`, `momentum_acceleration`, `ema_ratio` e `breakout_strength`.

## O que ainda não existe

Nenhum sinal foi gerado, nenhum trade foi aberto, nenhuma estatística de performance existe. Ver [[Agent Performance]] para o que será medido quando isto rodar.

## Relacionadas

[[Agents Overview]] · [[Strategies]] · [[Features]] · [[Agent Performance]]

## Fontes

`docs/PIPELINE.md` §5–6, `docs/DATABASE.md` §6
