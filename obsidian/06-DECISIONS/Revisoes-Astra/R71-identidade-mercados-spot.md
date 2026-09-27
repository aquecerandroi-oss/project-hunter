---
tags: [revisao-astra, spot, identidade, mercados, database]
date: 2026-09-23
updated: 2026-09-23
status: registro
owner: sexta-feira
decided_on: 2026-09-23
by: astra
tarefa: R71 — identidade dos mercados semeados na spot_desk_markets (NEAR/WBTC/ORCA/XRP)
veredito: evidência de identidade fechada; diff final sem must-fix
---

# Revisão da Astra — R71 (identidade dos mercados da mesa spot)

A Astra (papel `risk-engine-guardian`) melhorou a própria evidência durante a revisão: identificou o
NEAR como OmniBridge e confirmou o mint do XRP no site da Hex Trust — não aceitou "mesma autoridade de
tokens já semeados" como prova por si só, exigiu evidência direta por mercado. Com isso, NEAR, WBTC e
ORCA passaram na identidade e XRP também, com a fonte declarada. No diff final (`r71-diff.md`, papel
`database-architect`): sem must-fix, parecer favorável na revisão estática (execução dos testes não
certificada por ela).

**Bruto:** `.claude/state/astra-review-r71.md` · `.claude/state/astra-review-r71-diff.md`
**Relacionado:** [[03-TRADING/Spot/Mesa-spot-1|Mesa spot/1]]
