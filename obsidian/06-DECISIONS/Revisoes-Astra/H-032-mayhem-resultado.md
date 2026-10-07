---
tags: [revisao-astra, meme, mayhem, resultado, h-032, simulador, bug]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: R89 — resultado da H-032 (moeda Mayhem na sonda de recusadas)
veredito: "concorda com NÃO CONFIRMA — instrumento; recomputou D_adj e médias do CSV por PowerShell; 3 must-fix absorvidos sem mudar o rótulo"
---

# Revisão da Astra — resultado da H-032 (R89)

**Pedido:** revisar o código (`.claude/state/r89/h032.py`, `h032_run.py`, `test_r89.py`), a saída real
(`h032.txt`), a réplica por SQL (`q_replica.sql`) e o diagnóstico pós-hoc do teto (`q_capdiag.sql`).
Transcrição: `.claude/state/astra-review-H-032-resultado.md`.

**O que ela confirmou:**

- O rótulo **NÃO CONFIRMA — instrumento** segue o registrado. Os portões precedem o rótulo, e o I2 sozinho (63,34 % das saídas Mayhem com teto) já o dá.
- O I1 falha só por bit nulo na foto (239 registros), sem conflito entre os bits não nulos.
- Recomputação independente em memória a partir do CSV: D_adj = 0,5352830488 com 137 estratos; médias −0,5971 e −0,0494; 463 saídas com teto.
- Estratificação, pesos e bootstrap correspondem à emenda. Isso não é réplica independente dos intervalos.

**Três must-fix, absorvidos:**

1. **Registrar o defeito do simulador.** As marcas e as saídas Mayhem são cortadas no SOL real observado, que omite o aporte da compra hipotética. Cenário: SOL real 0 e foto seguinte idêntica levam o recebimento a 0, a prioridade é descontada e dispara a perda máxima.
   - Feito em [[Open Bugs]].
   - "Real + curve_cost" **não** é correção validada para a trajetória.
2. **Avisar o EXP-M23.** Cenário: admitidas sem Mayhem contra recusadas com muitas Mayhem; a perda criada pelo teto aparece como vantagem do portão.
   - Feito em [[EXP-M23-desfecho-das-recusadas]]. Os 30 % são em contagem, não peso medido no estimador.
   - Não invalida automaticamente os contrastes do estrato A.
3. **"Ponto de inversão" mal rotulado.** O código imprimia uma grade de imputações, não um limiar.
   - Rerrotulado na saída como "grade de imputação". A resposta literal é: nenhum valor imputado muda o rótulo enquanto I1/I2 falharem.

**Nice-to-have aceitos:**

- Denominadores precisos: o I1 inclui a proposta sem aposta, e o I3 é "entre avaliáveis".
- O I3 valida a compra, não a venda Mayhem.
- A errata de carimbo foi preservada.

**O que não se pode afirmar (dela, adotado na [[KB-0189-o-papel-nao-sabe-medir-a-moeda-mayhem]]):**

- Que Mayhem é pior, melhor ou igual de verdade.
- Que o veto paga, ou que deveria sair.
- Que o teto explica toda a diferença, ou que tirá-lo recuperaria aqueles retornos.
- Que as saídas sem teto estão limpas.
- Que a réplica por SQL valida o simulador.

Pré-registro: [[H-032-mayhem-prereg]].
