---
tags: [operacoes, shadow-lab, graficos]
status: em-andamento
owner: quant-engineer
updated: 2026-09-08
---

# Operações traçadas — índice

Uma nota por versão, uma linha e um gráfico por operação **concluída** (entrou, saiu, R apurado). Reproduzir: `docs/PIPELINE.md` §9b.

- [[Operacoes-tracadas/mean_reversion-v2]]
- [[Operacoes-tracadas/mean_reversion-v3]]
- [[Operacoes-tracadas/momentum-v6]]
- [[Operacoes-tracadas/momentum-v7]]
- [[Operacoes-tracadas/momentum-v8]]
- [[Operacoes-tracadas/session_orb-v1]]
- [[Operacoes-tracadas/trendline_breakout-v1]]

## O que as linhas significam

**Lê linhas para decidir:** apenas `trendline_breakout_v1` — nela a linha é a regra (rompimento de resistência descendente ou repique em suporte ascendente) e a invalidação estrutural. O `line_id` da tabela é o que a decisão usou, gravado no envelope pelo próprio worker.

**Não lê linhas:** `momentum`, `mean_reversion`, `session_orb`, `volume_anomaly`, `breakout`, `sweep_reclaim`. As linhas desenhadas nos gráficos dessas versões são **contexto calculado depois**, pelo mesmo scanner congelado e cortado na barra da decisão — servem para olhar a operação, nunca foram entrada dela. Confundir as duas coisas é a forma mais barata de inventar uma explicação retrospectiva.

Ver [[KB-0077-linhas-de-tendencia]] (as regras de detecção e os seis pontos em que um humano traçaria diferente) e [[KB-0076-por-que-perdemos-2026-09-08]].
