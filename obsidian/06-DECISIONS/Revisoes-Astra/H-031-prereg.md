---
tags: [revisao-astra, meme, concentracao, maior-comprador, e2b, pre-registro, h-031]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: R88 — pré-registro da H-031 (fatia do maior comprador no preenchimento como aviso de golpe)
veredito: "B admissível como extensão pré-registrada, não equivalente a A; 5 must-fix aceitos numa emenda datada (00:36Z) antes de qualquer desfecho"
---

# Revisão da Astra — pré-registro da H-031 (R88)

**Pedido:** rever o bloco congelado às 00:32Z (`.claude/state/r88/prereg_frozen.md`, cópia na [[Fila de Hipoteses]])
com as contagens cegas (`r88/avail1.txt`–`avail3.txt`), oito perguntas: incluir a medida B (`decision_tape`) numa
hipótese nascida do `pedigree_e2b`; confusão por conjunto; unidade e cluster; a guarda `ledger.wallets ≥ 10`; os
limiares; a censura `indeterminate`; a redação da errata do R76; antecipação; nível positivo obrigatório.
Transcrição: `.claude/state/astra-review-H-031-prereg.md`. Nenhum desfecho tinha sido lido.

**Concordou com:** B capturada antes do primeiro `await` (evidência disponível, não lida pelo portão); A gravada em
`reasons` é o valor que o portão usou (sem antecipação ao reaproveitá-lo; não recalcular A hoje); manter o nível
positivo obrigatório; a cláusula `max(IC superior) < MRE` respeita a errata, se a inferência for válida; 0,35 em B e
quantil 2/3 em A, congelados às cegas.

**Cinco must-fix, todos aceitos na emenda das 00:36Z (texto original preservado):**

1. **D ajustado por conjunto decisório** — a permutação estratificada não transforma o D agrupado em efeito dentro do
   conjunto. Cenário: a composição entre conjuntos infla D acima de +0,05. → D_adj com pesos ∝ unidades, só conjuntos
   com suporte nos dois braços; o moinho agrupado vira descritivo.
2. **p que respeita a mint** — a permutação do moinho é linha a linha e a mesma mint aparece em vários conjuntos. →
   p = maior dos dois p do bootstrap centrado (mint e dia).
3. **`ledger.wallets` não é "dez compradores"** (vendedoras também entram). → declarado como proxy de participantes.
4. **Censura com sensibilidade decisória** — excluir `indeterminate` pode retirar golpes sem foto. → unidade
   congelada antes de classificar o desfecho, nunca trocada; S1 com `indeterminate` = −1; CONFIRMA e REFUTA têm de valer
   nos dois.
5. **Rótulo da família** — "todas as fora do limite refutarem" deixava A sem dado + B refutada virar REFUTA. → REFUTA
   só com A **e** B refutando; o resto NÃO CONFIRMA.

**Nice-to-have aceitos:** genealogia de B (fluxo líquido de SOL, não o estoque que a [[KB-0153-o-maior-comprador-nao-estava-no-arquivo|KB-0153]]
pediu); empate (≤ seleciona a igualdade, a E2-b a recusa); suporte da grade contado antes dos desfechos; a taxa de
`creator_dump` depende da saída estar ligada (ela é padrão em `ExitRules`).

**Divergência:** nenhuma.

Resultado e segunda revisão: [[H-031-resultado]] · nota: [[KB-0188-a-concentracao-do-maior-comprador-nao-separa-o-retorno]].
