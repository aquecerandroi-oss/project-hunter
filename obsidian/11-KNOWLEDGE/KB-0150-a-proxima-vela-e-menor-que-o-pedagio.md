---
id: KB-0150
titulo: A próxima vela é menor que o pedágio
origem: R68 (23/09/2026) — `.claude/state/notes-R68.md`
tipo: business-rule
confianca: alta (parte A, aritmética sobre 2,38 M minutos) / média (parte B, potência limitada em h≥60)
tags: [custo, previsibilidade, horizonte, spot, walk-forward, anti-look-ahead]
relacionados: [KB-0126, KB-0133, KB-0145, KB-0147, R63, R67]
---

# KB-0150 — A próxima vela é menor que o pedágio

## O facto

Nas nossas 16 perpétuas com 104 dias de velas de 1 minuto (`is_final`, 2 378 230 pontos de
decisão, 11/06–23/09/2026):

| horizonte | mediana de \|retorno\| | ida-e-volta 0,14 % | ida-e-volta 0,54 % (bilhete 0,05 SOL) |
|---:|---:|---|---|
| **1 min** | **0,045 %** | custo = **3,1×** o movimento típico | **12×** |
| 5 min | 0,099 % | 1,4× | 5,5× |
| 15 min | 0,171 % | 0,8× | 3,2× |
| 60 min | 0,340 % | 0,4× | 1,6× |
| 240 min | 0,688 % | 0,2× | 0,8× |

A taxa de acerto necessária para empatar, com o equilíbrio correcto
`p* = (b + c) / (a + b)`, onde `a = E[r | r > 0]` e `b = −E[r | r < 0]` são medidos
(condicionais ao **sinal do retorno**, não ao sinal de entrada — ver ressalva abaixo):

| horizonte | `p*` a 0,14 % | `p*` a 0,54 % |
|---:|---:|---:|
| 1 min | **1,34** | **3,75** |
| 5 min | 0,89 | **2,03** |
| 15 min | 0,72 | **1,40** |
| 60 min | 0,60 | 0,94 |
| 240 min | 0,51 | 0,68 |

**`p* > 1` significa que, mantendo aquele perfil de ganho e perda, nem acertar sempre
empata.** A 1 minuto isso acontece já ao nosso custo mais barato, o de 0,14 % medido no
Jupiter (R63). A 5 e a 15 minutos acontece ao custo real do bilhete de 0,05 SOL.
*Ressalva:* `a` e `b` são **incondicionais** (médias sobre todas as barras); um selector
suficientemente bom mudaria os dois. Portanto isto é um diagnóstico forte do obstáculo
económico, **não** uma impossibilidade matemática de selecção lucrativa — é a parte B que
testa a selecção, e não a encontra.

## A regra que fica

**Não procurar vantagem de preço em horizontes de 1 a 15 minutos com o nosso custo.**
Não é uma questão de encontrar o preditor certo: o prémio inteiro é menor que o pedágio.
Só 7,04 % dos minutos têm retorno futuro acima de 0,14 %; 0,39 % acima de 0,54 %.

Se alguém propuser uma estratégia de minuto, a primeira pergunta é: *qual é o teu ganho
condicional médio quando acertas?* Se for menor que o custo de ida-e-volta, não há taxa de
acerto que salve.

## E os horizontes onde o custo é pequeno?

Aí não sabemos prever. 25 células congeladas (5 preditores × 5 horizontes), fora de amostra,
bootstrap de blocos temporais conjuntos, Holm: **zero confirmações**. **Ao custo da mesa
(0,54 %) as 25 têm média estimada negativa** (a menos má: −12,42 bp). A 0,14 % há quatro
médias positivas, todas a 240 min — a maior **+27,58 bp**, IC [−12,67; +72,71] — e **todas
com IC a atravessar zero**. **20 das 25 células têm o limite superior do IC 95 % (individual,
não simultâneo) abaixo de +10 bp** — evidência *contra* uma vantagem útil. As **cinco de
240 min ficam inconclusivas**: o estudo não as promove nem as enterra.

"Sempre long" também não salva: é negativo em todos os 20 cortes horizonte × custo.

## Três coisas que aprendemos de lado

1. **MFE não é dinheiro.** A 240 min, 89,7 % das barras tocam +0,14 % nalgum momento. É o
   preço que uma saída perfeita teria apanhado, não o que uma saída realizável apanha. Não
   usar excursão favorável como prova de oportunidade.
2. **Ganhar em USDT pode ser perder em SOL.** O retorno da mesa no numerário que interessa é
   `(1+r_token)/(1+r_SOL) − 1`. Nos 104 dias medidos, a coluna em SOL é quase sempre **pior**
   que a em USDT. Toda a medição de vantagem para a mesa spot tem de declarar o numerário.
3. **A perda do `momentum v3` pode ser sobretudo da saída, não da entrada.** O R63 mediu
   Σ R −42,9 em 223 sinais. No R68, um **parente** da regra de entrada (fecho acima do máximo
   das máximas de 20 barras, saída por tempo puro) **bate** o "sempre long" a partir de 15 min
   (+1,3 / +6,7 / +16,4 bp). **Não é a mesma regra**: o `momentum_v1` usa o máximo dos
   *fechos*, em 15 m, com portões de rvol e ATR % e stop/alvo a 1,5 ATR. Logo: **hipótese
   sobre a família, gerada e não testada** — testável com o replay histórico
   (`docs/PIPELINE.md` §6c) usando a estratégia real.

## Limites desta nota

- Medido em **perpétuos da Binance** com entrada/saída ao fecho da vela: é um **proxy
  optimista** (sem latência, slippage, impacto ou falha de transacção). Um veredito negativo
  com um proxy optimista é forte; um positivo teria sido fraco.
- Só **8 dos 35 mercados** da mesa spot/1 têm os 104 dias; os outros 26 têm 25.
- Em h = 60 e 240 min há apenas ~35 blocos independentes de 3 dias: sobre as 5 células que
  não têm "evidência contra", o estudo diz **inconclusivo**, não "não existe".
- Um preditor **muito mais selectivo** (< 0,5 % das barras, ganho condicional > 0,5 %) não
  foi testado. Os do R68 entram em 3–45 % das barras.
- Nada aqui exclui um sinal vindo de **outra fonte** (livro, fluxo tick-a-tick, cadeia).
  Só `candles` foi testado.
- **Falta validação temporal independente.** Limiares congelados antes da execução não
  tornam 104 dias de histórico "fora de amostra" — a motivação dos preditores já vem do R63.
  Um veredito negativo aguenta isso; um positivo não aguentaria sem sombra prospectiva.
