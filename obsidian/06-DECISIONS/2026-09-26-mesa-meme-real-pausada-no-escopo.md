---
tags: [decisao, meme, mesa-real, risco]
date: 2026-09-26
owner: sexta-feira
decidido_por: Sexta-feira, por delegação explícita do Everton ("sexta feira pode decidir", 26/09/2026)
status: vigente
---

# Decisão — a mesa real de memes fica parada no fim do escopo do teste pequeno (26/09/2026)

## O fato

O escopo escrito do teste pequeno (`small_test.max_total_sol = 10` SOL de giro em `meme_gates.json`, [[2026-09-12-teste-pequeno-meme-real]]) chegou a **9,987575929** com a compra das 00:13Z de 26/09. Desde então toda entrada é recusada por `below_min_sol` (restam 0,0124 < mínimo 0,02). Carteira real: **0,3845 SOL**; nenhuma posição aberta ([[2026-09-26]]).

## A decisão

**Não ampliar o escopo.** A mesa real de memes fica parada onde a regra do próprio teste a parou. A `spot/1` (mesa de cripto pela Jupiter, custo 0,14 %) segue ligada com os seus limites próprios, e todos os braços de papel e pesquisas seguem rodando.

## Por quê

- **161 operações reais, −0,5204 SOL**, nenhum dia verde no fechamento; nenhuma das hipóteses de entrada confirmou (13 variáveis do R65, H-014, H-015, H-016, H-019 — [[Mapa de Estrategias]]).
- O maior vazamento medido (`comprou_no_topo`, [[Perdas/comprou_no_topo]]) não tem hoje nenhuma regra que o evite — seguir operando é pagar pelo mesmo erro.
- Everton já tinha autorizado pausar em 24/09; a pausa não pegou por um detalhe de configuração. O escopo esgotado faz agora o que ele autorizou.
- O que a mesa real ensinava que o papel não ensina (custo real, aluguel de ATA, execução) **já foi aprendido e corrigido** ([[KB-0149-o-que-a-mesa-real-ensinou]]).

## Condição para voltar (escrita antes, para não virar vontade)

A mesa real volta **só** quando as três coisas forem verdade:
1. Uma hipótese de entrada com veredito **CONFIRMA** na [[Fila de Hipoteses]] (pré-registrada, população independente).
2. Um braço de papel dessa regra com **≥ 150 decisões resolvidas** e diferença emparelhada positiva contra a porta atual.
3. A proposta de volta levada ao Everton com o novo escopo (valor de giro, ticket, prazo) — **a ampliação do escopo é dinheiro real novo e volta a ser decisão dele**, mesmo com esta delegação.

## O que não muda

Saídas, kill switch e a venda de qualquer posição continuam livres. As correções de segurança do escopo (T4.96) seguem, porque só restringem.

## Relacionado

[[2026-09-12-teste-pequeno-meme-real]] · [[2026-09-26]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[Mapa de Estrategias]] · [[EXP-M25-controle-do-recuo]]
