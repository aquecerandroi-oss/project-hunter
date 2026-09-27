---
tags: [revisao-astra, meme, pumpfun, golpe, h-020, pumpfun-rest]
date: 2026-09-26
updated: 2026-09-26
status: registro
owner: sexta-feira
decided_on: 2026-09-26
by: astra
tarefa: R80 — H-020, link reciclado não avisa o golpe (KB-0160); coleta REST do pump.fun
veredito: NÃO CONFIRMA mantido; diff da coleta REST não fecharia T4.97/R80 como estava
---

# Revisão da Astra — R80 (o link reciclado não avisa o golpe)

No desenho (`R80-design.md`): a Astra ainda não aprovaria emitir CONFIRMA/REFUTA — a hipótese é
testável, mas faltavam garantias sobre a identidade observada, o significado de "zero reusos" e a
definição de golpe usada no veredito; concordou condicionalmente com a premissa de imutabilidade. No
veredito (`R80-verdict.md`): manteria **NÃO CONFIRMA**, reproduziu `h020.txt` por completo — o cálculo
sustenta o rótulo, as correções ficam na interpretação da observabilidade e do mecanismo (a cláusula
(a) isolada daria REFUTA, mas o protocolo já incorporava a errata do R76 antes dos desfechos). Em
paralelo, a revisão da coleta REST do pump.fun para T4.97/R80 (`pumpfun-rest-r80.md`) não fecharia o
diff como estava: contabilidade de chamadas com problema, descarte silencioso, continuidade do poll
quebrado e proveniência temporal do sweep ainda incompleta — todos aceitos, endereçados no T4.97b.

**Bruto:** `.claude/state/astra-review-R80-design.md` · `.claude/state/astra-review-R80-verdict.md` ·
`.claude/state/astra-review-pumpfun-rest-r80.md`
**Relacionado:** [[KB-0160-o-link-reciclado-nao-avisa-o-golpe|KB-0160]] · [[06-DECISIONS/Revisoes-Astra/T4.97b-identity-breaker|T4.97b]]
