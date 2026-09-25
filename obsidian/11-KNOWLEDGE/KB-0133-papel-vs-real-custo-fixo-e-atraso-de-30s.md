---
tags: [knowledge, nota, meme, pumpfun, papel-vs-real, custos, atraso, m4]
tema: memecoin / pump.fun / papel × real — custo fixo 0,0028 SOL/aposta e 30 s de atraso custam +2,8 % na entrada
fonte: banco da VPS (meme_live_positions, meme_paper_bets), 16–17/09/2026 (14 h)
fonte_url: ""
lido_em: 2026-09-17
evidencia: medição própria (R54 §3 — SQL em .claude/state/notes-R54.md)
hipotese_testavel: não
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

# KB-0133 — Papel × real: 0,0028 SOL/aposta de custo fixo, 30 s de atraso = +2,8 % na entrada

## O que afirma
Quantifica quanto da vantagem medida em papel sobrevive quando convertida em dinheiro real, separando
custo fixo de atraso de execução.

## Número
Ida e volta real (5 posições) custa **≈ 0,0028 SOL/aposta (5,4 % do tamanho)**: taxa 1,25 % × 2 + rent
da ATA **não devolvido** (T4.46 OFF) + rede. O papel cobra 1,75 % × 2, sem rent — mais pessimista na
taxa, cego ao rent. Fill real chega 19–38 s depois da cota; em curvas subindo (`flow_v2/5`, 45
apostas), o **mesmo atraso de 30 s** encarece a entrada em **+2,8 % em média** (mediana 0 %, 23/45
pioram, soma **0,061 SOL** nas 45 apostas) — a piora se concentra justamente nas vencedoras.

## O que muda na operação
Decompõe a vantagem do braço `flow_v2/5`: **+0,109 SOL (papel) → ≈ +0,07 com a ATA fechada (T4.46
ligado) → ≈ 0,00 com a ATA aberta (estado real de hoje)**. É o argumento quantitativo central para
ligar `MEME_CLOSE_ATA_ON_FULL_SELL` e para descontar sistematicamente qualquer "vantagem de papel"
antes de apostar dinheiro real nela.

## Relacionados
`.claude/state/notes-R54.md` §3 · `.claude/state/notes-T4.46.md` · `.claude/state/review-T4.46.md`
