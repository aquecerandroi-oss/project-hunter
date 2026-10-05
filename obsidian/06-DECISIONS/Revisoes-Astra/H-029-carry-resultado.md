---
tags: [revisao-astra, cripto, perpetuos, funding, carry, resultado, h-029]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: quant-engineer
decided_on: 2026-10-05
by: astra
tarefa: R87 — resultado da H-029 (carry de funding protegido) e o código que o produziu, antes do advogado-de-jesus e do defensor
veredito: "rótulos reproduzidos (A0 e A1 NÃO CONFIRMA; A2 limite de dado); sem dupla contagem na liquidação; 2 defeitos de contabilidade corrigidos sem mudar rótulo; diagnóstico de cauda reescrito; conclusão restringida ao A1 medido"
---

# Revisão da Astra — resultado da H-029 (R87)

**Pedido:** revisar `h029.txt`, `audit.txt`, `check_funding.py` e o código (`engine87.py`, `sim87.py`, `analyze87.py`,
`data87.py`, `run_real.py`) contra o pré-registro e a emenda ([[H-029-carry-prereg]]), com cinco perguntas: bugs que
inventem ou escondam dinheiro, coerência entre IC percentil e p centrado, rótulo do A2, honestidade da leitura e o que
o [[Advogado de Jesus]] e o [[Defensor]] atacariam. Transcrição: `.claude/state/astra-review-carry-result.md` (cópia
em `.claude/state/r87/astra_result.log`).

**O que ela reproduziu (rodando o código, sem gravar relatório):** as quatro células e os três rótulos; o teste de
antecipação no dado real (25 semanas, 0 divergências); `check_funding.py` (2023: −0,69 % no simulador × −0,61 % na soma
direta; 2024: +6,68 % × +6,20 %). O p do A1 pessimista: 583 de 10 000 réplicas acima de 2× a estimativa → p 0,0584;
intervalo básico refletido [−1,63 %; +9,66 %] (diagnóstico, não substitui o congelado).

**Com o que concordou:** A1 NÃO CONFIRMA (Holm falha nas 4 células, inclusive a de p bruto 0,0497 → Holm 0,1491; IC
superior não exclui 5 %); A2 em limite de dado (12 blocos < 15, checado antes de confirmar ou refutar); a liquidação
**não** duplica a perda (`funding + liq = −margem0`; a perna à vista segue até a saída prevista, premissa explícita);
S7 defasado, F̂ adverso/favorável pelo sinal da taxa, custos finais, A1 − A0 só descritivo.

**Quatro must-fix — o que foi feito:**

1. **Vaga presa reservava o nocional, não o saldo de margem** (cenário dela: posição cai à metade e fica presa → 102,5 %
   do capital comprometido). → reserva = q·(S + (2F_ref − F)/m); teste novo. Efeito medido por ela no A0: −0,0004 p.p. a.a.
2. **Custo de entrada fora do orçamento** (carteira toda ligada pedia 100,125 % de caixa). → q = w ÷ (S(1 + c_s) +
   F/m(1 + c_p)); testes de valor conhecido refeitos. Números movem na 2.ª casa; **rótulos idênticos** (v1 guardada em
   `h029_v1_antes_da_revisao.txt`).
3. **"Sem semanas de liquidação" descrevia outra conta** (subtraía só as vagas liquidadas). → texto corrigido e a versão
   "semanas inteiras com alguma liquidação" publicada (A1: +2,8 % nessas 20 semanas, +2,5 % nas demais); a perna à
   vista descoberta saiu do "basis" para um componente próprio (o basis protegido do A1 é +0,0 %).
4. **Conclusão generalizava** ("o carry foi um negócio de 2020–2021", "exatamente o que a literatura avisava"). →
   restringida ao A1 deste modelo; funding recebido (+3,1 % desde 2023) separado do líquido (+0,6 %); a tabela de He et
   al. mostra o funding da estratégia deles de volta a +6 % no BTC em 2024 — variação, não desaparecimento.
   [[KB-0180-carry-de-funding]] também foi corrigida: os −1,94 %/−0,94 % são a parte do funding **na estratégia** de He
   et al., não o funding do mercado (no nosso dado o BTC somou +4,2 % e +7,9 % do nocional em 2022 e 2023).

**Nice-to-have aceito:** a guarda de antecipação no dado real agora refaz a **trajetória inteira** (posições abertas e
P&L semanal dos três braços) com o dado cortado — posições idênticas; 4 semanas do A0 diferem só na marca da vaga FTT
presa, que o painel cortado não consegue carregar. **Registrado, não feito:** `check_funding.py` é conferência de
plausibilidade (metade do capital por vaga, sem preço), não reconciliação exata do caixa.

**Primeiro ataque previsto por ela:** advogado — "quanto do ganho depende da perna descoberta depois da liquidação, de
2021 e de financiamento não reconciliado?" (sem 2021: +1,4 %); defensor — "falhar no Holm não condena todo carry: o IC
superior comporta efeitos relevantes e o teste mede uma implementação" (aceito na redação da KB).

Relacionados: [[KB-0181-carry-de-funding-no-dado]] · [[KB-0180-carry-de-funding]] · [[Fila de Hipoteses]] (H-029) ·
[[Revisoes-Astra/Index|Índice]]
