---
tags: [experimento, meme, lancamento, sniper, evento, m4]
status: pre-registrado
owner: sexta-feira
updated: 2026-09-19
origem: Everton, 19/09/2026 00:3x BRT — "assim que a moeda é criada dá um pico; se compramos assim que começa a subir conseguimos comprar no lançamento e vender na alta rápida?"
---

# EXP-M18 — Sniper de lançamento (compra no bloco da criação, venda no pico de segundos)

## Hipótese (congelada antes de medir)
Comprar em ≤ 1 s após o `create` (feed por evento em `processed`) e vender em +6 s, +15 s ou no primeiro trade de venda de terceiros paga em média, líquido de taxas (1,25 %/perna), slippage 5 % e prioridade, apesar de a maioria das moedas morrer.

## O que já sabemos (contra e a favor)
- KB-0123: 46 % das graduações nascem cheias (create → cheia em ~1 s): pico não comprável.
- R58/KB-0138: entrar "quando sobe" e sair no recuo = negativo em 54 células; quem faz o pico vende para quem chega 2–3 s depois.
- KB-0136: carteiras que lucram no lançamento seguram 1–13 s; entrada a 3 s pega 1,01×.
- A favor: nunca medimos a entrada a ≤ 1 s com custo real; o feed de `create` já existe (PumpPortal) e o de trades também (WS do RPC).

## Método (R60, papel)
Captura própria de 60 min no pico (14–20 BRT) de TODOS os `create` + trades program-wide (`logsSubscribe` no programa pump, como no R58). Para cada moeda: preço em +1 s (entrada), em +6 s, +15 s, +60 s, e no primeiro sell de terceiro; R líquido por regra; taxa de acerto; concentração no top-3; sinais por hora; comparação com "entrar em +3 s" (o que a nossa infra faz hoje) e "+0,5 s" (RPC regional).

## Braço (se pagar em papel)
Conjunto `launch_v0/1` (`research_only`): sem porta de saúde (não existe dado), ticket 0,01 SOL, saída fixa +6 s ou primeiro sell de terceiro, ≤ 200 tentativas/dia. Controle: `flow_v2/6`.

## Regra de decisão
Vira mesa só se: R médio líquido > 0 com ≥ 300 moedas, top-3 < 50 % do lucro, e o custo de prioridade cabe. Se negativo a +1 s, o jogo do lançamento é dos bots colocados no bloco: descartar e registrar.

Ligações: [[KB-0123-graduacoes-born-full]] · [[KB-0138-explosao-de-compradores-nao-tem-vantagem]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]]
