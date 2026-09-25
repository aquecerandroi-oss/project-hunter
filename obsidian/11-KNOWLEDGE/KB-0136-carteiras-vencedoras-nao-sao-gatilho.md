---
tags: [knowledge, meme, carteiras, smart-money, r57, m4]
status: vivo
owner: sexta-feira
updated: 2026-09-18
fonte: .claude/state/notes-R57.md
tipo: leitura
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

# KB-0136 — Carteiras vencedoras existem, mas seguir não é gatilho (R57, 18/09/2026)

**Pergunta.** "Seguir quem sabe" (2+ carteiras do top-30 do dia anterior comprando a mesma moeda em ≤ 60 s) tem vantagem?

**Medido (72 h de fita, 15/09 → 18/09).**
- Carteiras vencedoras **persistem**: correlação do ranking dia a dia ρ ≈ 0,6; o top-30 de um dia ganhou +79,6 SOL no dia seguinte (24 de 27 positivas).
- **Mas o lucro delas é velocidade e pacote**: metade segura 1–13 s; 16 % das compras estão no bloco do `create`; 43 % dos "sinais" são duas carteiras do mesmo operador no mesmo segundo.
- Sinal replicado (341 casos): a +60 s o preço está 1,11× do gatilho, mas quem entra 3 s depois pega 1,01× e 20 s depois 0,96×. Com a saída da mesa (trailing 30 %, 30 min): **R médio −0,06, acerto 29 %, igual ao controle aleatório** (Δ 0,00; IC95 [−0,14; +0,16]).
- Única fresta: segurar 15 min sem stop, Δ R +0,18 (IC toca zero), cauda longa, mediana negativa.

**O que muda na operação.** Não ligar "seguir carteiras" como gatilho. Manter o placar de carteiras como **contexto** (feature) para o portão de evento, onde a latência de 1 s ainda pega 1,01×; e só voltar ao tema com o feed de evento (cobertura 100 %) em vez da fita (5 % dos mints, 26 s de atraso).

**Ressalvas.** Fita cobre 5,3 % dos mints e ~100 s por mint; universo já filtrado pela mesa (16 % graduaram vs 3,1 % da população); 30 % das trajetórias censuradas.

Ligações: [[EXP-M15-carteiras-vencedoras]] · [[KB-0124-latencia-de-decisao]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] · [[KB-0135-a-vantagem-nao-esta-na-saida]]
