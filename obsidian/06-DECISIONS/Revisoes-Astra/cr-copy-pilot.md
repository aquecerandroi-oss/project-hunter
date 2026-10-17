---
tags: [revisao-astra, meme, copiar-carteiras, h-037, exp-m28, papel, revisao-de-codigo, pre-registro]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: quant-engineer
decided_on: 2026-10-09
by: astra + sexta-feira
tarefa: revisão R2 do código do piloto de copiar carteiras (pista, fonte, combinação) e a emenda 5 do H-037 que dela decorre
veredito: "R2 REQUEST_CHANGES (8 must-fix, todos HIGH). Sete decisões da Sexta-feira levadas ao diálogo h037-emenda5: DECISÃO CONJUNTA na rodada 2, com quatro trechos que contrariam a letra da Sexta-feira (cobertura efetiva, entradas durante perda só da NATS, sinal do viés do stop, fechamento do funil). A emenda 5 está em rascunho e não foi congelada; T0 fica bloqueado até as correções e a re-revisão R2"
---

# Revisão R2 do código do piloto e a emenda 5 do H-037

Fontes brutas:

- revisão: `.claude/state/astra-review-cr-copy-pilot.md`;
- diálogo: `.claude/state/dialogue-h037-emenda5.md`;
- rascunho da emenda: `.claude/state/h037/emenda5-draft.md`.

Protocolo: o bloco H-037 da [[Fila de Hipoteses]]. Experimento: [[EXP-M28-copiar-carteiras-no-papel]]. Revisões
anteriores do código: [[copy-lane]] e [[copy-leader-source]].

## A revisão R2: REQUEST_CHANGES, 8 must-fix (todos HIGH)

| # | Achado (com o cenário dela) | Onde fica |
|---|---|---|
| 1 | Uma escrita do funil que falha bloqueia as entradas só em memória, e reiniciar limpa a trava. Uma recompra de B depois do reinício passaria como primeira | Emenda 5 item 7 + aceite C5 |
| 2 | A reentrega pode perder a confirmação de uma saída (o `UPDATE` atualiza zero linhas sem erro) e reprecifica uma saída já decidida | Emenda 5 itens 5 e 7 + C5 |
| 3 | O orçamento de retentativas de `RecordGap` é compartilhado entre lacunas distintas; a sexta lacuna é descartada na primeira falha | Aceite C5 (implementação) |
| 4 | A lacuna aberta e o período anterior ao reinício não são duráveis, e T0 é gravado antes de a fonte abrir | Emenda 5 item 2 + C5 |
| 5 | O stop é amostrado a cada 5 s e só testado depois de `update_mark`, sem validar o slot da marca | Emenda 5 item 4 + C5 |
| 6 | `rpc_error` é ignorado e expira como `not_found` | Emenda 5 item 3 + C5 |
| 7 | O fallback não vê transferências; uma transferência legítima vista pela NATS vira `divergent/not_a_trade` | Emenda 5 itens 1(d) e 3 + C5 |
| 8 | Lacunas diferentes com o mesmo início se sobrescrevem no `GapRegistry` | Emenda 5 item 1(b) + C5 |

Ela também confirmou o que estava bem:

- nenhuma conversão de SOL desconhecido em zero;
- preços em `Decimal`;
- o seletor nominal respeita instante, prazo e piso de slot;
- não encontrou vazamento da credencial nos logs examinados, numa inspeção estática, não num teste.

## As sete decisões da Sexta-feira e o que o diálogo fez com elas

| Item | Decisão | Resultado do diálogo |
|---|---|---|
| 1 | Três medidas (saúde da fonte, cobertura efetiva, contaminação) | Aceito, com dois **DELTAs**, abaixo. O estimando passa a ser explícito: a política operada com observação degradada. M passa a incluir as contaminadas |
| 2 | Reinício abre lacuna desde o último marcador durável; abertas precificadas e contaminadas; pico relido | Aceito, com uma exigência de implementação: um marcador durável **de progresso**. Ver abaixo |
| 3 | `rpc_error` próprio, `unverified` não liquida, portão de 10 % | Aceito e precisado (detalhe abaixo) |
| 4 | Stop em todo estado observado; limite da cadência; "viés esperado otimista" | Aceito, com **DELTA**: o sinal do viés é indeterminado |
| 5 | Prazo do fill a partir de `decided_at` | Aceito: `decided_at + 30 s`; saída até a intenção original + 60 s; a reentrega não reinicia o prazo |
| 6 | `post_reserves` (ideal) + leitura a +3,9 s (p90) | Aceito, sem tocar o primário |
| 7 | `funil_indisponivel` até uma escrita bem-sucedida | Aceito, com **DELTA**: fecha só por reconciliação |

**Item 2 em detalhe.** O marcador não pode ser o maior carimbo de atividade. O cenário: a fonte perde cobertura às
10h, o processo marca até 10h09, cai às 10h10 e volta às 10h20; contar desde 10h09 perde nove minutos. O pico
relido é só o **pico observado**: no cenário 100 → 300 → 120, o máximo perdido não é recuperado. T0 só é gravado
com o estado reconstruído e a admissão habilitada.

**Item 3 em detalhe.** O `unverified` fica terminal no prazo original. Pendência real na maturação continua indo
para U. Transferência verificável é confirmada como redução de saldo. O numerador do portão conta bet_ids distintos
com algum evento não verificável na entrada, no pico ou na saída.

**Os quatro DELTAs que vão à Sexta-feira antes de congelar.** São cenários concretos contra a letra da decisão.

1. **Cobertura efetiva.** A decisão dizia "só as linhas `no_coverage:*`". O cenário: a NATS fica aberta em lacuna
   enquanto a perda da cadeia chega como intervalo já fechado. O combinador calcula `no_coverage` só com as lacunas
   abertas e perde a interseção. Troca: interseção histórica das lacunas das duas filhas, calculada a partir das
   linhas de saúde.
2. **Entradas durante perda só da NATS.** O cenário: o líder recebe o token por transferência, transfere tudo para
   fora e depois compra por swap. A cadeia não vê o recebimento, e a compra passa como primeira. Troca: a dispensa de
   recomposição só vale quando o fallback emitir a transferência recebida como fato de elegibilidade. Até lá, novas
   entradas desse líder ficam bloqueadas até a recomposição.
3. **Stop.** A decisão dizia "viés esperado otimista". Isso é otimista quando a queda se recupera e pessimista
   quando ela continua. Troca: "sinal indeterminado".
4. **Funil.** A decisão dizia "até uma escrita bem-sucedida". O cenário: o fato de A falha e um fato de B é gravado
   depois; reabrir aí deixa um reinício esquecer A. Troca: fecha só com a reconciliação de todas as obrigações e a
   elegibilidade recomposta.

**Requisito de implementação (não é delta de política).** Um marcador durável de progresso, sem tabela nova
obrigatória. O local fica com a implementação e a revisão de banco.

## O que discordo da Astra

Na rodada 2 ela corrigiu a referência do achado da reentrega para "#3 da R2". No arquivo da revisão, esse achado é
o **2**; o 3 é o orçamento de retentativas. O rascunho cita o 2 e põe o 3 nos aceites.

## Estado

- A emenda 5 **não está congelada**: não entrou na Fila nem no `manifest.txt`. Rascunho com sha256 `7ce54f88…` às
  08:22Z.
- A decisão dos quatro DELTAs é da Sexta-feira, e o Everton pode revogar até T0.
- **T0 bloqueado** até: as correções C5 do desenho §9, a re-revisão R2, a tarefa X refeita sobre o M/U novo e os
  demais aceites anteriores.

## Relacionados

[[EXP-M28-copiar-carteiras-no-papel]] · [[copy-lane]] · [[copy-leader-source]] ·
[[Revisoes-Astra/H-037-prereg|H-037-prereg]] · [[Dialogos/copy-paper|copy-paper]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]]
