---
tags: [revisao-astra, meme, teste, bugfix, apostrofo]
date: 2026-09-23
updated: 2026-09-23
status: registro
owner: sexta-feira
decided_on: 2026-09-23
by: astra
tarefa: teste de guarda para escape de apóstrofo em razões de recusa (refused_probe)
veredito: APPROVE_WITH_NITS — o teste detectaria o bug original
---

# Revisão da Astra — guarda de apóstrofo nas razões de recusa

`APPROVE_WITH_NITS`: a Astra confirmou que o teste teria detectado o bug original ao reintroduzir
`{why}` sem escape, somente em memória, nos três helpers afetados — os três testes falharam na
asserção de paridade como esperado, provando que a guarda funciona.

**Bruto:** `.claude/state/astra-review-meme-refused-probe-apostrophe-guard.md`
**Relacionado:** [[09-OPERATIONS/Diario/2026-09-26]]
