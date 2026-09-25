---
tags: [knowledge, nota, meme, pumpfun, creator-flow, contrafactual, taxcoin, m4]
tema: memecoin / pump.fun / T4.45 (fluxo do criador pela cadeia) teria recusado a TAXCOIN — o criador vendeu 53 s antes da compra
fonte: banco da VPS (meme_trades, meme_tokens), retroativo sobre a noite de 16/09/2026
fonte_url: ""
lido_em: 2026-09-17
evidencia: medição própria (R46 §3 — contrafactual sobre commit não implantado no momento da medição; SQL em .claude/state/notes-R46.md)
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

# KB-0132 — T4.45 teria recusado a TAXCOIN (criador vendeu 53 s antes)

## O que afirma
Prova retroativa (antes do deploy de T4.45) de que a leitura do fluxo do criador pela cadeia teria
evitado a primeira perda real da mesa.

## Número
TAXCOIN teve **6 vendas do criador, somando 10,624 SOL**, a primeira **53 s antes** da compra real
(21:31:28 BRT). Nas 10 candidatas do contrafactual do R46 (bundle ≤ 20 %, top-10 ≤ 25 %, progresso
≤ 50 %), TAXCOIN é a **única** com veredito certo de recusa (`creator_net_seller`); as outras 9 ficam
em "admitiria" (CELINE, BUFFETT — ambas subiram depois) ou "lê sob demanda" (indeterminado sem dado).
Contexto mais amplo (R44, 47 recusas `creator_flow_unknown` em 12 h anteriores ao deploy): T4.45 teria
mudado o veredito de só **5 de 47** (3 admitiria por `creator_net_seller = false`, 2 recusaria por
venda confirmada).

## O que muda na operação
Confirma o mecanismo por trás do check que entrou em produção (T4.45, 16–17/09) e que, uma vez ligado,
gerou 64 recusas reais por `creator_net_seller` no estágio 1b (R56) — a ordem de grandeza da perda
evitada (−0,04 a −0,18 SOL) é comparável ao que o estágio 1 inteiro perdeu.

## Relacionados
`.claude/state/notes-R44.md` · `.claude/state/notes-R46.md` §3 · `.claude/state/notes-T4.45.md`
