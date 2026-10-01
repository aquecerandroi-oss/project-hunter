---
tags: [trading, spot, spot-1, perda, consolidado, mean-reversion, jupiter]
tipo: consolidado
hipotese: —
variavel: "duas etiquetas por operação: eixo econômico (custo / denominacao_sol / movimento_adverso, sobre o PnL verdadeiro e os retornos brutos da mesma janela) e eixo de incidente (cotacao_fantasma / aluguel_constante)"
populacao: 10 posições fechadas da spot/1 (25/09 14:30Z → 01/10 00:45Z), mean_reversion v14, ficha 0,05 SOL
efeito: "8 perdas verdadeiras (−0,004561 SOL) e 2 ganhos (+0,000622); Σ verdadeiro −0,003938 SOL (−4,40 R) contra −0,001735 (−1,92 R) registrado"
ic: —
veredito: —
proximo_passo: "corrigir os dois bugs de execução (aluguel constante, saída decidida por uma cotação só) antes de ler a 11.ª operação; as hipóteses propostas estão em KB-0172 e ainda não estão na Fila"
classe_de_perda: movimento_adverso
mercado: cripto
status: vivo
owner: quant-engineer
updated: 2026-10-01
---

# Perdas da `spot/1` — as 10 primeiras operações, uma a uma (01/10/2026)

Mesmo formato das [[Perdas/Index|classes de perda da mesa de memes]]: uma nota consolidada, cada perda com **uma**
etiqueta econômica pela primeira regra que casar e, à parte, o incidente de execução que a acompanhou. A síntese e as
hipóteses estão em [[KB-0172-perdas-da-spot-1]]; o custo por operação vem de [[KB-0171-custo-real-da-spot-1]].

## As regras (escritas antes de rotular; revisadas pela Astra)

Sobre o **PnL verdadeiro**, isto é, com o aluguel de ATA corrigido (1 488 440 lamports, não 2 039 280; ver
[[Open Bugs]] e [[KB-0171-custo-real-da-spot-1]]). Os retornos são **brutos**, na **mesma janela da posição real**
(abertura do minuto da entrada → fechamento do minuto da saída), em velas 1 m `is_final` da Binance perp do mercado
do sinal e de `SOLUSDT`. alt/SOL é a razão dos fechamentos.

**Eixo econômico** (só para PnL < 0):
1. `custo` — alt/SOL na janela ≥ 0: o mercado deu alguma coisa e o custo levou.
2. `denominacao_sol` — alt/SOL < 0 **e** alt/USD ≥ 0: a moeda subiu em dólar, mas o SOL subiu mais.
3. `movimento_adverso` — alt/SOL < 0 **e** alt/USD < 0: o repique não veio.

**Eixo de incidente** (qualquer operação):
- `cotacao_fantasma` — a decisão de saída usou uma cotação que a Binance e a execução contradizem por mais de 1 R.
- `aluguel_constante` — a posição abriu ATA e o código descontou 2 039 280 em vez de 1 488 440: o gasto ficou 550 840
  lamports menor, o PnL ficou maior e `r_now` deslocou-se +0,53 a +0,75 R. O stop registrado em −1 R corresponde a
  −1,53…−1,75 R verdadeiros; o alvo registrado em +1,5 R, a +0,75…+0,97 R.

Primeira versão: a Astra recusou usar o R do Lab como "direção" (o `r_net` do Lab já desconta 11 bp e funding) e
pediu os dois eixos separados ([[06-DECISIONS/Revisoes-Astra/KB-0172-perdas-spot-1|revisão]]). O que era
`sinal_errado` passou a se chamar `movimento_adverso`.

## Uma linha por operação

R = risco inicial da própria posição (ficha × stop_frac). MFE/MAE em USD: desde o preço de referência do sinal, por
máximas/mínimas 1 m; o toque é o primeiro minuto em que a máxima/mínima cruzou o alvo/stop do sinal. MFE/MAE alt/SOL
**aproximados** (máxima/mínima do alt ÷ fechamento do SOL no mesmo minuto; não são extremos simultâneos). Custo = R da
tabela da [[KB-0171-custo-real-da-spot-1]].

| # | entrada (UTC) | mercado | z · ATR% · 1 h/SMA20 | saída real | R reg. → verd. | PnL verd. (SOL) | Lab (USD, líquido) | MFE/MAE USD (R) e toque | MFE/MAE alt/SOL (R) | alt/USD · SOL · alt/SOL | custo (R) | econômica | incidente |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 25/09 14:30 | TAO | −1,10 · 1,38 · +1,79 % | tempo, 240 min | −0,03 → **−0,56** | −0,000586 | expirou +0,09 | +1,08 / −0,63, nenhum | +0,54 / −0,71 | +0,90 · +1,86 · −0,94 % | 0,13 | `denominacao_sol` | `aluguel_constante` |
| 2 | 26/09 00:45 | NEAR | −1,02 · 1,26 · +1,45 % | tempo, 240 min | +0,44 → **−0,15** | −0,000139 | expirou −0,34 | +0,82 / −0,93, nenhum | +0,64 / −0,80 | −0,35 · −0,81 · +0,47 % | 0,49 | `custo` | `cotacao_fantasma` (alvo) · `aluguel_constante` |
| 3 | 26/09 19:15 | TAO | −1,47 · 1,00 · +0,37 % | stop, 54 min | −1,16 → −1,16 | −0,000869 | stop −1,09 (20:10) | +0,23 / −1,45, stop aos 53 min | +0,27 / −1,22 | −1,60 · −0,35 · −1,26 % | 0,59 | `movimento_adverso` | — |
| 4 | 27/09 11:15 | NEAR | −1,38 · 1,27 · +3,05 % | tempo, 240 min | +0,62 → +0,62 | **+0,000590** | stop −1,07 (13:05) | +0,74 / −1,02, stop aos 108 min | +1,74 / −0,73 | −0,54 · −1,95 · +1,44 % | 0,24 | ganho | — |
| 5 | 28/09 00:00 | NEAR | −1,32 · 1,33 · +1,73 % | tempo, 240 min | −0,80 → −0,80 | −0,000801 | stop −1,06 (02:01) | +0,35 / −1,72, stop aos 119 min | +0,37 / −0,89 | −3,29 · −2,00 · −1,31 % | 0,11 | `movimento_adverso` | — |
| 6 | 29/09 02:45 | LINK | −1,22 · 1,20 · +4,29 % | stop, 79 min | −1,05 → **−1,66** | −0,001494 | stop −1,07 (04:04) | +0,17 / −1,43, stop aos 77 min | +0,09 / −1,68 | −2,56 · +0,45 · −3,00 % | 0,05 | `movimento_adverso` | `aluguel_constante` (stop atrasado) |
| 7 | 29/09 14:30 | UNI | −1,10 · 0,97 · +2,80 % | "stop", 91 min | +0,39 → **−0,37** | −0,000267 | stop −1,09 (15:21) | +0,34 / −1,81, stop aos 49 min | +0,30 / −0,45 | −1,49 · −1,87 · +0,39 % | 0,54 | `custo` | `cotacao_fantasma` (stop) · `aluguel_constante` |
| 8 | 30/09 00:15 | NEAR | −1,02 · 1,38 · +0,48 % | tempo, 240 min | +0,03 → +0,03 | **+0,000032** | alvo +1,17 (00:36) | +1,70 / −0,47, alvo aos 19 min | +1,53 / −0,59 | +1,04 · +0,58 · +0,46 % | 0,23 | ganho | — |
| 9 | 30/09 14:45 | UNI | −1,16 · 1,18 · +1,16 % | tempo, 240 min | −0,01 → −0,01 | −0,000010 | alvo +1,02 (16:03) | +1,59 / −0,06, alvo aos 76 min | +1,25 / −0,10 | +0,28 · −0,29 · +0,57 % | 0,33 | `custo` | — |
| 10 | 30/09 20:45 | NEAR | −1,08 · 1,57 · +3,37 % | tempo, 240 min | −0,34 → −0,34 | −0,000396 | expirou −0,44 | +0,61 / −0,78, nenhum | +0,50 / −0,74 | −0,73 · +0,02 · −0,75 % | 0,09 | `movimento_adverso` | — |

**Os "4 ganhos pequenos" eram 2.** NEAR 26/09 (+0,000412 registrado) e UNI 29/09 (+0,000284) são perdas quando o
aluguel é contado certo: −0,000139 e −0,000267.

## Por classe

| classe econômica | n | SOL verdadeiro | R verdadeiro |
|---|---:|---:|---:|
| `movimento_adverso` | 4 (TAO 26/09, NEAR 28/09, LINK 29/09, NEAR 30/09 20:45) | −0,003559 | −3,96 |
| `denominacao_sol` | 1 (TAO 25/09) | −0,000586 | −0,56 |
| `custo` | 3 (NEAR 26/09, UNI 29/09, UNI 30/09) | −0,000416 | −0,53 |
| ganhos | 2 (NEAR 27/09, NEAR 30/09 00:15) | +0,000622 | +0,65 |
| **total** | 10 | **−0,003938** | **−4,40** |

Incidentes: `aluguel_constante` em 4 (as que abriram ATA), `cotacao_fantasma` em 2.

## O que cada incidente fez

- **UNI 29/09, stop fantasma.** Às 16:01 a cotação do lote inteiro deu 0,043310 SOL, −13,6 % sobre o gasto
  (`r_now` −8,55 registrado). No mesmo minuto o alt/SOL da Binance estava **+0,39 %** sobre a entrada. A venda recotou
  normalmente e saiu a 0,049838. A posição foi vendida 2 h 29 min antes do prazo. Segurar até 18:30 teria dado
  alt/SOL **+0,56 % bruto**. A Astra lembra que isso é referência, não fill: não prova que a posição chegaria lá sem
  stop. A saída usou tolerância de pânico (300 bp) porque o motivo era `stop`.
- **NEAR 26/09, alvo fantasma.** Às 04:30:56 a cotação deu +3,6 % sobre o gasto (`r_now` +2,48 registrado; +1,90 com
  o aluguel certo). No minuto, o alt/SOL da Binance estava em +0,25 %, e o MFE alt/SOL da posição inteira foi +0,64 R.
  A venda "target" falhou na simulação (`Custom 6001`, compatível com slippage excedido; o programa que emitiu o código
  não foi conferido). Saiu por tempo 15 min depois. O incidente não custou nada aqui, mas mostra que a decisão de
  saída se apoiou numa cotação só.
- **LINK 29/09, stop atrasado pelo aluguel.** O stop foi decidido em `r_now` −1,023 registrado, que corresponde a
  **−1,64 R verdadeiro**. Pela razão dos fechamentos, o alt/SOL cruzou −1 R aos 51 min (≈ 03:36); o stop real disparou
  aos 79 min. Isso **corrige** a frase "nenhuma ordem errada" da entrada do bug em [[Open Bugs]]: o deslocamento muda
  decisões, não só o placar. Quanto ela teria economizado é contrafactual e não está medido.

## Relacionado

[[KB-0172-perdas-da-spot-1]] · [[KB-0171-custo-real-da-spot-1]] · [[03-TRADING/Spot/Mesa-spot-1|Mesa-spot-1]] ·
[[Perdas/Index|Perdas (memes)]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0145-binance-como-sinal-solana-como-execucao]] ·
[[Open Bugs]] · [[06-DECISIONS/Revisoes-Astra/KB-0172-perdas-spot-1|Revisão da Astra]]
