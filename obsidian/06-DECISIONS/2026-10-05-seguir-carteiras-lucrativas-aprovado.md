---
tags: [decisao, meme, carteiras, pesquisa]
status: decidida
owner: sexta-feira
updated: 2026-10-05
decided_on: 2026-10-05
by: Everton
---

# Seguir carteiras que ganham de verdade — projeto aprovado (05/10/2026)

**Pedido do Everton:** "pesquise e começamos a seguir quem faz dinheiro de verdade no mercado" (05/10), a partir do exemplo do perfil "sadcrissy" (+US$ 144 mil num dia, dos quais só US$ 19 mil realizados).

**O que foi apresentado** ([[carteiras-lucro-design]], desenho em `docs/design/seguir-carteiras-lucrativas.md`, evidência em [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]]):
- ranquear carteiras pelo que **nós** ganharíamos copiando (atraso medido ~5 slots ≈ 2 s, custos reais, saída depois da venda delas, gêmeas juntadas numa entidade, posse mediana ≥ 60 s), nunca pelo PnL delas;
- subsistema novo: migração com 7 tabelas, contêiner `wallet-tape` próprio, 10–20 GB de disco (fita bruta de 9 dias fora do backup noturno);
- pré-registro H-030 (coorte futura: 7 dias de aquecimento, 14–28 de teste, leitura única); previsão honesta do pesquisador: **NÃO CONFIRMA**;
- pré-condição: deploy do conserto dos decodificadores (T4.8e) — o feed de eventos está cego desde 02/10 15:47Z.

**Opções:** teste curto grátis de 2 h primeiro (recomendado) · aprovar tudo · não seguir agora.

**Decisão do Everton: aprovar tudo** — inclusive o uso do plano pago da Helius se for preciso para rodar 24 h. **Dinheiro real fica fora do escopo:** um CONFIRMA só libera a onda 5 (papel ao vivo pelo Risk Engine); qualquer passo com dinheiro volta ao Everton.

**Complemento (05/10, noite):** seguidores entram como pergunta secundária, não como critério ([[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]]).

## Relacionado

[[EXP-M15-carteiras-vencedoras]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[KB-0142-kol-e-call-antecipam-ou-confirmam]] · [[2026-10-05]]
