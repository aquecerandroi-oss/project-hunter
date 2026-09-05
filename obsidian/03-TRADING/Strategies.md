---
tags: [trading, estrategias, m4, m6]
updated: 2026-09-05
status: planejado
---

# Strategies

## Status

**Planejado, principalmente M4 (duas estratégias ativas) e M6 (versionamento na UI).** O catálogo (`strategies`, `strategy_versions`) existe como schema desde o M0, e os seeds do M0 já inserem `strategy_versions` v1 como `status=draft` para as duas estratégias do MVP — mas nenhuma foi ativada e nenhum código de avaliação existe ainda.

## Contrato (definido, sem implementação)

```python
class Strategy(Protocol):
    key: str; version: str; parameters_schema: type[BaseModel]
    def evaluate(self, ctx, opp, regime, params) -> Signal | None: ...
```

`Strategy.evaluate` é uma **função pura** (sem IO) — mesma exigência que o Risk Engine, para permitir backtest determinístico sem look-ahead (M6).

## Catálogo planejado

`momentum | breakout | volume_anomaly | order_flow | mean_reversion | derivatives | narrative | ensemble` — chaves já fixadas em `docs/DATABASE.md` §6, mas só as duas primeiras do MVP têm especificação de comportamento hoje:

- **`momentum_v1`** — entrada em continuação com volume relativo e breakout; stop em ATR; alvos em múltiplos de R.
- **`volume_anomaly_v1`** — entrada após `VOLUME_SPIKE` + pressão compradora/vendedora; stop na mínima/máxima do spike.

As demais (`breakout`, `order_flow`, `mean_reversion`, `derivatives`, `ensemble`) são Fase 2.

## Versionamento (M6)

Cada versão de estratégia (`v1`, `v2`, ...) nunca é sobrescrita — `strategy_versions.status` vai de `draft` → `active` → `deprecated`, ativação exige OWNER, changelog obrigatório. Quando esta prática começar a valer, cada versão significativa ganha sua própria página nesta pasta (ex.: `Volume Anomaly v1.md`, `v2.md`) documentando o que mudou, por quê e os resultados antes/depois — ver ADR 0003.

## Relacionadas

[[Agents Overview]] · [[Risk Engine]] · [[Experiments Index]]

## Fontes

`docs/PIPELINE.md` §6, `docs/DATABASE.md` §6, `docs/ARCHITECTURE.md` §6, `docs/ROADMAP.md` (Milestones 4 e 6)
