---
tags: [revisao-astra, spot-1, perdas, mean-reversion, execucao, aluguel]
date: 2026-10-01
updated: 2026-10-01
status: registro
owner: quant-engineer
decided_on: 2026-10-01
by: astra
tarefa: classificação das 10 operações fechadas da spot/1 (KB-0172) e as hipóteses propostas
veredito: concorda com os achados do aluguel e da cotação única; a classificação servia de triagem e foi refeita em dois eixos, com retornos brutos da mesma janela
---

# Revisão da Astra — perdas da `spot/1` (01/10/2026)

**Pedido:** `bash infra/scripts/astra.sh ask KB-0172-perdas` (somente leitura). Fonte bruta:
`.claude/state/astra-review-KB-0172-perdas.md`. O pedido trouxe os números da VPS e cinco achados (A aluguel,
B cotação fantasma, C denominação em SOL, D custo, E o sinal), a regra de classificação e três hipóteses.

## O que ela confirmou

- **A — aluguel:** a conta está certa (diferença de 550 840 lamports; correção de −0,00220336 SOL nas 4). O
  deslocamento de `r_now` de +0,53 a +0,75 R faz o stop registrado em −1 R disparar perto de −1,53…−1,75 R
  verdadeiros e o alvo de +1,5 R perto de +0,75…+0,97 R. A mesma constante está na reconciliação
  (`spot_reconcile.py:320`), conferido. Ela citou a SIMD-0437 (patamar 5 080) como compatível, o que não conferi. A
  prova por assinatura já estava feita pela [[KB-0171-custo-real-da-spot-1]]. Avisou para **não trocar uma constante
  pela outra** e para não copiar `rent_labels` da pump.fun, que pode somar contas transitórias de uma rota Jupiter.
- **B — cotação única:** a primeira marca decide o motivo; `spot_leg` recota e confere par, quantidade e execução,
  mas **não reavalia a condição**. Um `stop` ainda autoriza tolerância de pânico desde a 1.ª tentativa. Revalidar o
  gatilho na cotação que vai ser executada é **correção de robustez**. Esperar várias observações ou exigir paridade
  com a Binance seria hipótese. Sobre o `6001`: indica slippage excedido **se** veio do programa Jupiter; o programa
  não foi conferido.

## O que mudou por causa dela (absorvido)

1. **Dois eixos:** incidente de execução × decomposição econômica, com múltiplas etiquetas por operação.
2. **Sem R do Lab como "direção":** o `r_net` do Lab desconta 11 bp e funding (`pricing.py`, conferido). O eixo
   econômico passou a usar alt/USD e alt/SOL **brutos, na mesma janela da posição real**.
3. **`sinal_errado` → `movimento_adverso`.**
4. **Funil completo dos 44 sinais** na KB (ela achou 11 faltando, porque o pedido só listava parte dos grupos).
5. **H-c sem custo em dobro:** reprecificar a partir do bruto. Aplicar 0,3 R sobre um R já líquido cobra parte do
   custo duas vezes e mantém o funding do perpétuo numa simulação spot.
6. **O que não se conclui com 10 operações**, copiado para a KB: frequência de fantasmas, custo médio, "o SOL
  prejudica sempre", "os recusados por custo deviam ter entrado", "o UNI teria lucrado até 18:30".

## Onde discordamos

Em nada de substância. Ela sugeriu publicar o custo por operação sem somar medianas. A tabela por operação da
[[KB-0171-custo-real-da-spot-1]] já faz isso, e a KB-0172 cita essa tabela em vez da minha estimativa por resíduo.

## Relacionado

[[KB-0172-perdas-da-spot-1]] · [[Perdas-spot-1]] · [[KB-0171-custo-real-da-spot-1]] · [[Open Bugs]] ·
[[Revisoes-Astra/Index|Revisões da Astra]]
