---
tags: [revisao-astra, meme, pumpfun, buys1m, out-of-sample]
date: 2026-09-23
updated: 2026-09-23
status: registro
owner: sexta-feira
decided_on: 2026-09-23
by: astra
tarefa: R67 — validação fora de amostra de buys_1m ≤ 25
veredito: NÃO confirmado fora de amostra; permanece em sombra
---

# Revisão da Astra — R67 (buys_1m fora de amostra)

No desenho (`r67-design.md`): **NÃO** ao estudo como confirmação fora de amostra da regra real, **SIM**
como validação histórica complementar, com correções — `buys_1m ≤ 25` continua sendo o parâmetro a
testar, sem ser tratado como ótimo. No veredito (`r67-veredito.md`), a Astra concordou com "não
confirmado fora de amostra; permanece em sombra" e pediu para evitar "refutado"/"não sobrevive" sem
essa qualificação: o IC contém zero **e** efeitos relevantes — ausência de significância não é ausência
de efeito.

**Bruto:** `.claude/state/astra-review-r67-design.md` · `.claude/state/astra-review-r67-veredito.md`
**Relacionado:** [[KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista|KB-0147]] · [[Fila de Hipoteses]]
