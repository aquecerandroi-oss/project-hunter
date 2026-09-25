---
tags: [knowledge, nota, meme, pumpfun, execucao, blockhash, prioridade, m5]
tema: memecoin / pump.fun / blockhash_expired_never_landed = prioridade fixa 500× abaixo do teto + zero reenvio, não o blockhash
fonte: banco da VPS (meme_live_orders) + código do executor, 30 h em 17–18/09/2026
fonte_url: ""
lido_em: 2026-09-18
evidencia: medição própria (R56 §2.1, §3) + relato de construção e revisão (T4.55, review-T4.55-56)
hipotese_testavel: não
astra: não consultada nesta nota
confiança: backtest do autor (diagnóstico) e relato de implementação (correção)
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

# KB-0127 — `blockhash_expired` é prioridade fixa + zero reenvio, não o blockhash

## O que afirma
3 de ~23 envios reais em 30 h terminaram `blockhash_expired_never_landed` (13 % dos envios do estágio
1b); o diagnóstico descarta o blockhash como causa.

## Número
Blockhash lido ≈ 1 s antes de assinar (`confirmed`, válido ~60 s) — não é "cedo demais" nem "apertado
demais". A causa real: **taxa de prioridade fixa de 4 000 lamports (0,000004 SOL)**, 500× abaixo do
teto da doutrina (0,002 SOL); `send_transaction(..., max_retries=0)`; e **nenhum reenvio** da mesma tx
assinada durante os 30 s de confirmação — a regra 3 da doutrina §9.4 ("retentativa reusa o mesmo
blockhash") não estava implementada. Casos: PlanB (17/09 06:08), PS venda 1 (18/09 18:00), FAMILY
(18/09 08:38); mais uma venda morta na simulação por `Custom 6003 = TooLittleSolReceived`.

## O que muda na operação
T4.55 implementou: reenvio da mesma tx assinada a cada 2 s (mesmos bytes, sem risco de posição
dupla), prioridade dinâmica (`getRecentPrioritizationFees` p75, piso 0,00004 SOL, teto 0,002 SOL) e
slippage de saída maior (5 %, 15 % para `creator_dump`/`rug_signal`). Revisão (`review-T4.55-56.md`)
achou uma corrida residual **MÉDIA** ainda aberta: status→altura pode marcar `failed` uma tx que na
verdade aterrissou, na fronteira exata dos 2 s de poll.

## Relacionados
`.claude/state/notes-R56.md` §2.1, §3 · `.claude/state/notes-T4.55.md` ·
`.claude/state/review-T4.55-56.md`
