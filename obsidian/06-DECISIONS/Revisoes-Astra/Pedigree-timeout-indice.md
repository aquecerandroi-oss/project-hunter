---
tags: [revisao-astra, meme, pedigree, indice, database]
date: 2026-09-24
updated: 2026-09-24
status: registro
owner: sexta-feira
decided_on: 2026-09-24
by: astra
tarefa: índice para o timeout de pedigree por minuto (gargalo medido na VPS)
veredito: concordância com o reparo (A+B) em três rodadas, sem must-fix bloqueante
---

# Revisão da Astra — índice do timeout de pedigree (24/09)

Três revisões em sequência, todas favoráveis: a opinião inicial (`pedigree-timeout.md`, papel
`database-architect`) concordou com as opções (A) e (B), manteria o SQL intacto neste reparo, e não
achou consumidor oculto do pedigree do minuto — o índice proposto ataca o gargalo medido sem alterar
critérios. O diff (`pedigree-timeout-diff.md`, papel `code-reviewer`) saiu `APPROVE_WITH_NITS`, sem
must-fix com cenário concreto no caminho atual. O downgrade de prioridade (`pedigree-timeout-downgrade.md`)
foi aceito sem ressalvas, com o teste de migração 0064 confirmando a preservação do índice.

**Bruto:** `.claude/state/astra-review-pedigree-timeout.md` · `pedigree-timeout-diff.md` ·
`pedigree-timeout-downgrade.md`
**Relacionado:** [[KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]]
