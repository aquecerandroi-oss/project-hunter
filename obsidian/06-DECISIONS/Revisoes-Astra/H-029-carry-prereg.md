---
tags: [revisao-astra, cripto, perpetuos, funding, carry, pre-registro, h-029]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: quant-engineer
decided_on: 2026-10-05
by: astra
tarefa: R87 — pré-registro da H-029 (carry de funding protegido, à vista comprado + perpétuo USDT-M vendido, top-20 Binance), antes de qualquer sinal, universo ou desfecho no dado real
veredito: "S7 sem antecipação; 7 must-fix aceitos numa emenda datada (15:40Z) antes do run; 1 preferência rejeitada com motivo (ordem filtro → ranking); markPrice da API trocado por limites de faixa de marca"
---

# Revisão da Astra — pré-registro da H-029 (R87)

**Pedido:** revisar o texto congelado às 15:31Z (`.claude/state/r87/prereg_frozen.md`, registrado então como H-028 e
renumerado para H-029 às 15:50Z para não colidir com o rascunho [[H-028-forward-prereg]]) com perguntas sobre instante,
braços e limiares, contabilidade das duas pernas, inferência e o que o [[Advogado de Jesus]] e o [[Defensor]] atacariam.
Nenhuma vela de perpétuo ou série de funding tinha sido aberta. Transcrição: `.claude/state/astra-review-carry-prereg.md`
(cópia em `.claude/state/r87/astra_prereg.log`).

**O que ela confirmou:** o S7 (liquidações em (T − 7 d − 1 h, T − 1 h]) não tem antecipação; os limiares são aritmética
de custo (0,50 %/4 = 0,125 %; (0,50 % + 0,80 %)/2 = 0,65 %) com premissas econômicas a nomear, não escolha posterior;
Holm sobre os três braços é a família certa (cada um recebe rótulo); capital parado, custos das duas pernas, bootstrap
por semana com índices comuns e refutação restrita ao tamanho.

**Sete must-fix, todos aceitos na emenda da [[Fila de Hipoteses]] (H-029), antes de qualquer cálculo:**

1. **Relógio e dono do funding.** Cenário: sair às 00:00 e ainda receber a liquidação carimbada segundos depois. →
   execução aproximada pela abertura diária com convenção declarada e **fronteira nas duas convenções** (o rótulo exige
   as duas). *Parcial:* execução às 00:30 com preço intradiário não foi adotada (não há intradiário à vista com
   deslistados no painel).
2. **Orçamento de capital.** Cenário: S = 100, F = 105 — margem 100 vira 1,05×. → q = w ÷ (S + F/m), margem = q·F/m,
   capital fixo com lucro retirado e perda reposta, vaga presa consome capital (regra do R84).
3. **Liquidação pelo saldo e pela marca.** Cenário: gatilho 2F/1,05 deixa passar uma máxima de 197 que o próprio
   modelo liquidaria a 195,2. → velas diárias de **marca**, saldo com funding acumulado, perda do saldo inteiro sem
   dupla contagem, funding negativo do dia da liquidação mantido (ordem intradiária desconhecida → a pior).
4. **F̂ do funding.** Cenário: abertura 100, marca 150, funding −1 % debitado a 1 em vez de 1,5. → 00:00 pela abertura de
   marca; demais liquidações pelo extremo adverso/favorável da faixa de marca do dia nos dois limites. *Diferente do
   que ela pediu:* o campo `markPrice` da API não foi usado (cobertura histórica não auditada); os limites cobrem o erro
   e o rótulo exige os dois.
5. **Elegibilidade e cobertura.** Cenários: 7 de 21 liquidações bastavam; vigésimo ativo sem perpétuo ambíguo; ticker
   reaproveitado passando a guarda de 5 %. → janela completa (nenhum intervalo > 9 h), duplicatas removidas, guarda só de
   entrada e declarada como guarda de preço, funding ausente na posse contado (> 1 % → limite de dado).
   **Rejeitado:** a preferência dela por "top-20 à vista primeiro, vaga sem perpétuo em caixa" — o pedido define o
   universo como pares com as duas pernas; ficou **filtrar → classificar**, escrito na emenda.
6. **Fim de série.** Cenário: recompra no último fecho conhecido em retrospecto. → pessimista recompra na máxima de marca
   do último dia; resultados de fim de série são cenários condicionais; precedência no mesmo dia; posições abertas no
   fim pagam a saída.
7. **Calendário e dispersão.** Cenário: entradas num único trimestre bom e centenas de semanas em caixa cumprindo o piso.
   → calendário inteiro, ≥ 15 blocos não sobrepostos de 13 semanas com exposição (≥ 5 de cada lado de 2023-01-01).

**Absorvido sem discussão:** A2 é "inspirada" na proposta dela (a original era BTC/ETH com saída em 14 d); o custo do
perpétuo tem o **mesmo total** do Lab (10 bps/lado), não é validação de tarifa; poder declarado virou palpite
condicionado; leitura de CONFIRMA escrita (média positiva com estimativa ≥ 5 % a.a., não prova de que o filtro melhora o
carry ingênuo).

**Testes que ela pediu antes do run (todos escritos e passando, `.claude/state/r87/test_r87.py`, 20 testes):**
conservação (semana = funding + basis + liquidação − custos), multiplicador 1000×, fronteira nas duas convenções, vaga
presa com capital, liquidação com funding negativo, fechamento final, janela incompleta, faixa de marca, guarda de
antecipação com estratégia trapaceira pega.

Relacionados: [[KB-0180-carry-de-funding]] · [[KB-0181-carry-de-funding-no-dado]] · [[H-029-carry-resultado]] ·
[[Revisoes-Astra/Index|Índice]]
