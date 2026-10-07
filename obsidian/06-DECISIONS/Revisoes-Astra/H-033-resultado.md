---
tags: [revisao-astra, cripto, open-interest, resultado, h-033]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: sexta-feira
decided_on: 2026-10-07
by: astra
tarefa: R90 — resultado e código da H-033 (OI relativo à mediana semanal nos sinais da momentum do Lab)
veredito: concorda com momentum NÃO CONFIRMA, volume_anomaly LIMITE DE DADO e H-033 global NÃO CONFIRMA; reproduziu corrida, lista e réplica; 5 must-fix (1 de redação, 4 de instrumento sem efeito nos números) aceitos e corrigidos com teste, saída numericamente idêntica
---

# Revisão da Astra — resultado da H-033 (R90)

**Pedido:** se o rótulo segue o registro e a emenda cláusula a cláusula; defeito de instrumento que mude números; como
redigir a leitura (FE e blocos perto de +0,05 sem o REFUTA do protocolo); se `oi_vol` ou o descritivo `mean_reversion`
merecem pré-registro novo. Fonte bruta: `.claude/state/astra-review-H-033-resultado.md`.

**Reprodução:** rodou `run90.py` (mesmos números e rótulos), `replica90.py` (869 unidades, β +0,0026, IC dia
[−0,0463; +0,0594]) e os testes; reconstruiu o sha256 da lista congelada. Tabela cláusula a cláusula igual à da
[[KB-0191-oi-acima-da-semana-nao-separa-os-sinais-do-lab]].

## Must-fix (aceitos)

1. **Redação das robustezes — eu tinha escrito errado.** FE dia tem IC superior **+0,0501** e blocos de 3 d
   **+0,0512**: os dois **passam** de +0,05 (a emenda exige < +0,05, sem arredondar). Cenário: "todas as sensibilidades
   excluem +0,05" transformaria duas falhas em evidência de refutação. → KB e Fila dizem o número exato.
2. **Rótulo dos grupos da secundária `oi_vol`.** A saída imprimia "oi_rel7d<0" para grupos definidos por `oi_vol`
   (808/61 unidades, não 399/470). → corrigido em `run90.py`; números iguais.
3. **Prova da janela inteira contava buckets, não conferia os usados.** Cenário reproduzido por ela: remove-se a
   evidência de um bucket e a janela ainda saía "provada". → `window_evidence` recebe os buckets usados (do OI cru) e
   sem a lista nunca certifica; ela conferiu que nenhuma das 28 janelas provadas tinha bucket sem evento (a contagem
   ficou 28).
4. **MAD zero numa metade não bloqueava.** Cenário sintético dela: metade com maioria de x = 0 e posto completo → saía
   REFUTA. → a metade passa a exigir dispersão própria (escala global mantida); nas metades reais MAD > 0.
5. **Folgas 30/60 não estavam ligadas ao CONFIRMA.** → `label(..., slack=(β30, β60))` rebaixa um CONFIRMA a NÃO
   CONFIRMA se alguma for ≤ 0 ou não finita; nesta corrida +0,0023 / +0,0046, sem efeito.

Cada correção entrou com teste que falhou antes (`test_r90.py`, 31 testes; `replica/test_replica90.py`, 3); a nova
saída (`h033.txt`, sha256 `29ac13b1…`) difere da primeira (`h033_v1.txt`) só em rótulos e linhas acrescentadas.

## Como redigir (absorvido)

Pode-se afirmar: **estimativa próxima de zero, ausência de confirmação e nível favorável negativo nesta população.**
Não se pode afirmar: efeito exatamente zero, inutilidade do OI, refutação do MRE, mecanismo de "comprados lotados" ou
rentabilidade de execução real. A margem de ~0,009 acima do MRE explica o bloqueio formal; não mede quão perto da
verdade ficou a refutação. A réplica é **implementação computacional independente da manchete** (compartilha lista,
covariáveis e desfechos), não auditoria da seleção.

## Sobre pistas novas

- **`oi_vol`:** sem prioridade — β −0,012 no sentido contrário, os dois IC com zero, os dois grupos perdem.
- **`mean_reversion`:** pista fraca, compatível com ruído; IC por dia da média do grupo favorável (calculado por ela,
  diagnóstico pós-desfecho, 10 000) **[−0,206; +0,228]**. Uma hipótese de reversão só com justificativa própria e
  **sinais futuros**, nunca outro corte nesta amostra.

Nice-to-have feito depois da revisão: manifesto com sha256 de todos os insumos, saídas e código
(`.claude/state/r90/manifest.txt`; a corrida continua conferindo só o da lista congelada). Revisão gravada às 05:34:38Z.

Pré-registro em [[H-033-prereg]]; bloco na [[Fila de Hipoteses]] § H-033.
