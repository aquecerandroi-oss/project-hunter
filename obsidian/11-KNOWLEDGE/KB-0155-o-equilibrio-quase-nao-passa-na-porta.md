---
tags: [knowledge, meme, mesa-real, fluxo, equilibrio, porta, selecao, hipotese, m4]
tema: a conjunção "moeda em equilíbrio" (vendas ≈ compras, fluxo fraco, curva rasa) quase nunca passa pela porta fluxo_e_holders — 1 em 587 decisões, e é o próprio SHORT que a inspirou; não há o que julgar, e o filtro seria irrelevante na mesa
fonte: R75 (`.claude/state/notes-R75.md`) — H-013 da Fila de Hipóteses, origem na perda real do SHORT (23/09/2026)
fonte_url:
lido_em: 2026-09-23
evidencia: medição própria — 93 posições reais + 1 219 apostas de papel da porta fluxo_e_holders (587 mints), features lidas de meme_proposals.reasons (gravadas na decisão); moinho run_hypothesis; 7 testes
hipotese_testavel: sim (coorte prospectiva)
astra: concorda (uma ronda; 2 achados corrigidos)
status: vivo
owner: sexta-feira
updated: 2026-09-23
---

# KB-0155 — O equilíbrio quase não passa na porta

## Em uma frase

A tese "não comprar moeda em equilíbrio" **não pôde ser julgada**. Das 587 decisões da porta `fluxo_e_holders`
(uma por mint), só **uma** tinha vendas ÷ compras ≥ 0,6, fluxo < 2 SOL/min e progresso < 25 % ao mesmo tempo, e
é o próprio `SHORT` que originou a hipótese. **H-013: NÃO CONFIRMA, por limite de dado.**

## O que se mediu (R75)

- **Sem risco de antecipação na fonte.** As features vêm de `meme_proposals.reasons`, que a porta **gravou** ao
  criar a proposta. Não vêm de `meme_trades`, a cópia por polling atrasada ~44 s (KB-0153). Cobertura de
  **100 %**: as três grandezas existem em todas as 1 312 linhas.
- **Contagem:** 1 de 587 (uma por mint) e 2 de 1 312 (a segunda é a sombra de papel do mesmo `SHORT`). A
  pré-registo pede pelo menos 20; abaixo disso é limite de dado, e **não refutação**.
- **Por que tão pouco: a porta já seleciona.** 502 das 587 decisões vêm de braços com teto de vendas ÷ compras em
  0,6, que recusam a conjunção quase por construção. Onde o teto é 1,0 (`operator/5` depois de 18/09 e
  `flow_v2/8`), a taxa é 1 em 85.
- **As condições sozinhas não confirmam** (exploratório, fora do veredito), e duas vão contra a tese:

  | condição | n | D (verd. − falso) | IC 95 % |
  |---|---:|---:|---|
  | razão ≥ 0,6 | 49 | −0,019 | [−0,109, +0,074] |
  | fluxo < 2 | 40 | **+0,062** | [−0,075, +0,217] |
  | progresso < 25 % | 71 | **+0,038** | [−0,047, +0,132] |

  Nenhum par chega a 20 casos.
- **Saída relâmpago** (perda ≥ 15 % em ≤ 3 s): 3 das 29 perdas grandes reais. Duas delas (`DOOM`, `PHILINU`) eram
  de fluxo **forte** (+11,7 e +18,0 SOL/min). O recuo instantâneo não é assinatura do equilíbrio. No papel a
  medida não existe: a posição mais curta dura 10,2 s.
- **Contrafactual nas 93 reais** (PnL −0,3498 SOL):
  - recusar o equilíbrio bloqueia **1** (o `SHORT`), **0 vencedoras mortas**, Δ **+0,0134 SOL**;
  - alargando os três limiares de uma vez, bloqueia 2, com Δ +0,0207.
  
  É circular: a regra remove o caso a partir do qual foi desenhada.

## Por que importa

1. **Lição de método: a população de uma hipótese sobre a porta está condicionada pela própria porta.** Antes de
   pré-registar uma conjunção, contar quantas decisões a porta deixa passar nela. Isso não custa olhar desfechos.
2. **Um filtro que dispara 1 vez em 93 operações não muda a mesa**, mesmo que a tese esteja certa.
3. **A perda do `SHORT` foi um caso raro dentro do que a porta aceita.** Não é um padrão frequente escondido.

## Para reabrir

- **Coorte prospectiva** do `operator/5` (teto 1,0, série WS) depois do corte de 23/09 20:47 UTC, com a variável
  congelada. Julgar com 20 equilíbrios.
- À taxa atual, isso leva **meses**. Até lá, nenhum parâmetro de mesa.

Ver: [[Fila de Hipoteses]] (H-013) · [[KB-0153-o-maior-comprador-nao-estava-no-arquivo]] · [[KB-0149-o-que-a-mesa-real-ensinou]]
