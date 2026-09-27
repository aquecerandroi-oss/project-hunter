---
tags: [revisao-astra, meme, exp-m26, grafico, database]
date: 2026-09-26
updated: 2026-09-26
status: registro
owner: sexta-feira
decided_on: 2026-09-26
by: astra
tarefa: EXP-M26 — desenho R1 do gráfico em moedas maduras (retenção K=60, pins, migração 0067)
veredito: REVISE — bloqueio principal na garantia da primeira oportunidade
---

# Revisão da Astra — EXP-M26, desenho R1 (database-architect)

Parecer de `database-architect`: **REVISE**. O bloqueio principal é a garantia da primeira
oportunidade de leitura/gravação do braço. A Astra concordou que a migração 0067 (retenção madura
K=60) deve ficar para outro deploy, depois de F aprovado e J congelado na sequência do desenho — não
faz sentido ativá-la antes disso. Esta é a opinião pontual que antecedeu o diálogo de 5 rodadas com a
Astra sobre o desenho completo do EXP-M26 (ver Dialogos).

**Bruto:** `.claude/state/astra-review-EXP-M26-R1-design.md`
**Relacionado:** [[Dialogos/EXP-M26|Diálogo EXP-M26]] · `docs/design/exp-m26-grafico-moedas-maduras.md`
