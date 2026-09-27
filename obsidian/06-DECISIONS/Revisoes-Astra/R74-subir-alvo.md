---
tags: [revisao-astra, meme, pumpfun, alvo, h-011]
date: 2026-09-23
updated: 2026-09-23
status: registro
owner: sexta-feira
decided_on: 2026-09-23
by: astra
tarefa: R74 — H-011, subir o alvo de saída (KB-0154)
veredito: REFUTA pela cláusula literal, com leitura estatística ao lado
---

# Revisão da Astra — R74 (subir o alvo não paga)

A Astra achou a guarda do replay **contornável**: `reset(P, view)` recebia o caminho completo de `P`, e
uma política reproduzida lia o ponto futuro dentro de `reset`, mudando a saída de 1,6 s para 301,6 s
sem exceção — must-fix aceito, corrigido para passar só o contexto de entrada. No veredito
(`r74-veredito.md`): pode-se escrever "REFUTA pela cláusula literal" nas duas hipóteses, mas para H-011
nas apostas reais a leitura correta é "não confirma vantagem; +5 pp não excluídos a 1,6 s" — não
publicar REFUTA isolado, preservando a distinção entre refutação e limite de dado.

**Bruto:** `.claude/state/astra-review-r74.md` · `.claude/state/astra-review-r74-veredito.md`
**Relacionado:** [[KB-0154-subir-o-alvo-nao-paga|KB-0154]]
