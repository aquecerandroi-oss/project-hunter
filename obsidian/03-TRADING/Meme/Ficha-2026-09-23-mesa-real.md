---
tags: [trading, meme, mesa-real, ficha-diaria, operator-5, metricas]
data: 2026-09-23
mesa: operator/5 (porta fluxo_e_holders/2, pista por evento)
regra: alvo 1,15× · recuo 10 % armado na entrada · máx. 5 min · saídas por evento · ficha 0,07 SOL
owner: sexta-feira
updated: 2026-09-23
---

# Ficha do dia — 23/09/2026 · mesa real de memes

## O placar

| # | moeda | entrada | duração | saída | resultado | aluguel devolvido |
|---|---|---|---:|---|---:|---|
| 1 | `RIGBY` | 10:58:35 | 190 s | alvo | **+0,0112** (+15,7 %) | não (flag entrou às 11:19) |
| 2 | `SENTHOS` | 16:31:03 | **24 s** | alvo | **+0,0142** (+19,6 %) | **sim** |
| 3 | `AIRAA` | 17:03:19 | 43 s | dump do criador | **−0,0556** (−77,6 %) | sim |
| 4 | `MMKT` | 17:08:59 | **2 s** | alvo | **+0,0294** (+63,0 %) | sim |

**Dia: 4 operações · 3 alvos (75 %) · −0,0008 SOL.** Ganhos somam +0,0548; a única perda tirou −0,0556. Carteira 0,5608 SOL.

## A estratégia que está no ar (canalizada)

**Entrada** — porta `fluxo_e_holders/2` na **pista por evento** (reage ao fluxo de negócios, não a vela): idade 30–300 s · progresso da curva 5–100 % e **subindo** · fluxo de SOL do minuto **positivo** · ≥ 10 compradores únicos · vendas/compras ≤ 1 · criador **não** vendedor líquido · dev share ≤ 10 % · participação nossa ≤ 1 % do movimento · exclusões de pedigree (criador reincidente, símbolo clonado). `operator/5` aceita ≤ 10 snipers; `operator/6` ≤ 2.
**Saída** — alvo **1,15×** · recuo **10 %** armado desde a entrada · tempo máximo **300 s** · saídas por evento ligadas (dump do criador, venda grande) · pânico 15 % na escada de venda.
**Tamanho** — 0,07 SOL por operação · máx. 2 posições abertas · teto diário de perda 0,15 SOL · pausa de 300 s no mesmo mint após perda (T4.78).
**Custo** — **2,23 %** por ida e volta desde hoje 11:19 (era 4,09 % com o aluguel preso). Ponto de equilíbrio caiu de ~27 % para **~19 %** de acerto.

## As métricas da decisão, lado a lado

| métrica no instante da compra | RIGBY +15,7 % | SENTHOS +19,6 % | **AIRAA −77,6 %** | MMKT +63,0 % |
|---|---:|---:|---:|---:|
| idade (s) | 114 | 62 | 135 | 150 |
| progresso da curva | 51,5 % | 79,0 % | 73,3 % | 73,4 % |
| compras no minuto | 15 | 51 | 31 | **79** |
| vendas no minuto | 9 | 6 | 5 | 8 |
| compradores únicos | 13 | 22 | 14 | **76** |
| fluxo líquido (SOL/min) | 2,4 | 14,4 | 8,0 | **29,5** |
| valor de mercado +60 s | +5,9 | +63,3 | +30,5 | **+93,2** |
| snipers | 6 | 10 | 9 | **4** |
| holders subindo | não | não | **sim** | sim |
| dev share | 0 | 0 | 0 | 0,09 % |
| participação nossa | 0,65 % | 0,30 % | 0,56 % | **0,19 %** |

## O que estes quatro ensinam (e o que não ensinam)

1. **Os três ganhos foram rápidos**: 190 s, 24 s e **2 s**. O `MMKT` bateu o alvo em dois segundos — o alvo de 1,15× saiu a +63 % porque o preço disparou dentro da mesma janela. **Quanto mais rápido bate, mais o alvo "vaza" para cima.**
2. **Intensidade de fluxo acompanha o ganho**: o melhor (`MMKT`) tinha 79 compras/min, 76 compradores únicos e +29,5 SOL de fluxo — o triplo do `AIRAA`. Amostra de 4, mas é a direção que o `SENTHOS` também mostra. **Contraria a hipótese `buys_1m ≤ 25` do R65, já refutada fora da amostra (R67).**
3. **Nada nas 11 métricas separou o `AIRAA`**: ele estava no meio do pelotão em tudo. O que o afundou foi **uma carteira que comprou 8,89 SOL às 17:01 e vendeu 21,33 SOL às 17:03:55** — fora do conjunto de coisas que a porta olha. Daí a [[Fila de Hipoteses|H-010]].
4. **A assimetria é o problema, não o acerto**: 75 % de acerto e o dia fecha empatado. Três ganhos de +0,011 a +0,029 contra uma perda de −0,056. **Enquanto uma perda apagar três ganhos, acerto alto não basta.**
5. **Amostra de 4 não é evidência.** Tudo acima é leitura, não conclusão; as conclusões saem das medições pré-registradas ([[Fila de Hipoteses]]).

## O que está sendo medido por causa deste dia

- **H-010** — concentração do maior comprador (nasceu do `AIRAA`): mede se o dono grande visível na fita prevê o dump, **e quantos ganhos o filtro mataria junto** (o `SENTHOS` é o caso de teste).
- **H-009** — giro rápido na oscilação (ideia do Everton): vender o repique e recomprar a queda, com 2,23 % de custo por giro.
- **T4.88** — a escada de saída: no `AIRAA` a primeira tentativa a 5 % **falhou** e os 6,4 s até a segunda tentativa custaram a maior parte da perda.

## Relacionado

[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Fila de Hipoteses]] · [[Mesa-operator-6]] · [[2026-09-12-teste-pequeno-meme-real]]
