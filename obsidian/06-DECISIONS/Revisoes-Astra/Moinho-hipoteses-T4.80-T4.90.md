---
tags: [revisao-astra, meme, moinho-de-hipoteses, infra, t4-80, t4-90]
date: 2026-09-23
updated: 2026-09-23
status: registro
owner: sexta-feira
decided_on: 2026-09-23
by: astra
tarefa: T4.80–T4.90 — construção do moinho de hipóteses (run_hypothesis, spec, market_id) que sustenta R65–R81
veredito: várias rodadas DONE_WITH_CONCERNS/REQUEST_CHANGES, todas com must-fix corrigido antes do próximo elo
---

# Revisão da Astra — moinho de hipóteses (T4.80–T4.90)

Treze revisões cobrem a construção do "moinho de hipóteses" — o carregador `run_hypothesis`, os
predicados de interseção mercado × notícia, os índices e o desenho de captura prospectiva que
sustentam a fila de R65 a R81. Padrão observado: cada tarefa saiu `DONE_WITH_CONCERNS` ou
`REQUEST_CHANGES` na primeira passada (achados típicos — truncamento silencioso, deduplicação que
impede associar uma notícia a vários mercados, preenchimento ambíguo de `market_id`, dois
bloqueadores na recuperação de posições sem tokens) e fechou "sem regressão bloqueadora" ou
`APPROVE_WITH_NITS` na rodada seguinte, revisada como `code-reviewer`/`risk-engine-guardian`/
`quant-engineer` conforme o arquivo. T4.89 (design prospectivo para a lacuna da R73) exigiu seis
pontos fechados antes de implementar, incluindo a garantia de `received_at ≤ as_of`.

**Bruto:** `.claude/state/astra-review-t480.md` · `t481.md` · `t481-diff.md` · `t482.md` · `t483.md` ·
`t484.md` · `t484b.md` · `t485.md` · `t486.md` · `t486b.md` · `t487-desenho.md` · `t487-diff.md` ·
`t488.md` · `t488-diff.md` · `t48d.md` · `t489-design.md` · `t490.md`
**Relacionado:** [[Fila de Hipoteses]] · [[06-DECISIONS/Revisoes-Astra/R73-maior-comprador|R73]]
