---
tags: [astra, revisao, roster, pesquisa]
status: fechada
owner: sexta-feira
updated: 2026-10-01
decided_on: 2026-10-01
by: Astra + Sexta-feira
---

# Revisão da Astra — cartões do Advogado de Jesus e do Defensor (01/10/2026)

Pedido do Everton: red team rebatizado de "advogado de Jesus" e um defensor ao lado. Cartões: `.claude/agents/advogado-de-jesus.md`, `.claude/agents/defensor.md`. Bruto: `.claude/state/astra-review-roster-advogado-defensor.md`.

**Aceitos (três must-fix):**
- **Anti-resgate do defensor era fraco:** "não usado no teste original" permitia usar uma coorte já explorada em outro estudo, de resultado conhecido. Agora exige histórico de exposição (amostra não usada em nenhum estudo da fila), protocolo congelado antes de abrir a amostra e a família de tentativas com correção de multiplicidade.
- **O advogado não tinha saída "não verificável":** agora há um terceiro desfecho, "veredito pendente por falta de evidência", e é proibido dizer "resiste" para ameaça não checada.
- **Contrato de leitura contraditório:** os cartões mandavam chamar `astra.sh`, que grava arquivo. Agora quem chama a Astra sobre o parecer deles é a orquestradora.

**Aceito do nice-to-have:** limites explícitos (nunca redefinir critério depois do resultado, nunca reclassificar o estudo original, nunca tocar banco/parâmetros/flags/ordens/ativações).

**Não adotado agora:** revisor `quant-engineer` independente obrigatório sobre os pareceres — a reconciliação fica com a Sexta-feira + Astra; reavaliar se os pareceres começarem a decidir vereditos.

## Relacionado

[[Advogado de Jesus]] · [[Defensor]] · [[Agents Overview]]
