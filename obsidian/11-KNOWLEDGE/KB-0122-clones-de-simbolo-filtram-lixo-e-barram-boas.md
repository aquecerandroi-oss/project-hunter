---
tags: [knowledge, nota, meme, pumpfun, pedigree, symbol-clone, porta, m5]
tema: memecoin / pump.fun / a regra symbol_clone filtra lixo por rank (6,1 % vs 2,6 %) mas barrou 42 moedas boas no dia
fonte: banco da VPS (meme_tokens, meme_features_1m), janela de 24 h em 17/09/2026
fonte_url: ""
lido_em: 2026-09-17
evidencia: medição própria (R49 — SQL em .claude/state/notes-R49.md)
hipotese_testavel: sim
astra: não consultada nesta nota
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-18
status: vivo
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0122 — A regra `symbol_clone` filtra lixo por rank, mas barrou 42 moedas boas no dia

## O que afirma
`symbol_dup_24h > 2` (3ª+ moeda com o mesmo ticker em 24 h) recusa por `symbol_clone`
(`packages/indicators/hunter_indicators/meme/pedigree.py`), cross-cutting em toda porta.

## Número
- Taxa de graduação por rank de clone: **1º 6,1 %, 2º 3,9 %, 3º 4,3 %, 4º+ 2,6 %** — a 1ª moeda de um
  símbolo tem **2,3× melhor taxa** que a 4ª+.
- Das moedas rejeitadas **só** por `symbol_clone` (rank > 1, passando todos os outros critérios do
  `operator/5`): **42 no dia, 0 graduaram, mas 28 (66,7 %) tiveram progresso > 25 %**. Caso emblemático:
  o **5º LINK** (`4TcftzQv…`), 75,5 % de progresso, 167 holders, 137 compradores, bloqueado.

## O que muda na operação
A regra é defensável como filtro de lixo (2,3× de diferença de taxa por rank) mas o custo de
oportunidade é real e concentrado nos casos como o 5º LINK. Recomendação não implementada: relaxar
quando **todos os predecessores estiverem mortos** (< 5 % de progresso, sem graduação) — liberaria
~15–20 moedas/dia sem custo material de risco. Nenhuma mudança de código foi feita; segue como item
de backlog.

## Relacionados
[[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] · [[11-KNOWLEDGE/Strategy Backlog]] ·
`.claude/state/notes-R49.md`
