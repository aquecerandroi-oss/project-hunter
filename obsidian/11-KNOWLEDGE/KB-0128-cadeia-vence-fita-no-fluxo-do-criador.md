---
tags: [knowledge, nota, meme, pumpfun, creator-flow, precedencia, dinheiro-real, m5]
tema: memecoin / pump.fun / a cadeia deve vencer a fita no veredito sobre o criador — o caso COVER (T4.56)
fonte: banco da VPS (meme_live_orders, meme_features_1m) + código do executor, 17/09/2026 19:46–19:48 BRT
fonte_url: ""
lido_em: 2026-09-18
evidencia: medição própria (R56 §3.2) + relato de construção e revisão (T4.56, review-T4.55-56)
hipotese_testavel: não
astra: não consultada nesta nota
confiança: backtest do autor (o caso) e relato de implementação (a correção)
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

# KB-0128 — A cadeia deve vencer a fita no fluxo do criador (COVER, T4.56)

## O que afirma
COVER (17/09) mostrou que a fita (atrasada) tinha precedência sobre a cadeia (lida na hora) na decisão
sobre se o criador vendeu — o oposto do que deveria valer.

## Número
Criador vendeu 200 M tokens (20,1 SOL) às 19:46:28. Às 19:46:56 a leitura on-chain da ATA (saldo 0
contra base 200 M) **recusou** `creator_net_seller`. 23 s depois (19:47:20) a mesa **repropôs** o mesmo
mint: `meme_features_1m.creator_sold = false` (a venda entrou na fita com 37,7 s de atraso) tinha
precedência sobre a cadeia, e `creator_net_seller` **não estava** no cooldown determinístico →
comprada, **−0,08 R real**.

## O que muda na operação
T4.56 mudou a precedência (`resolve_creator_flow`: qualquer fonte que diga "vendeu" vence; cadeia
`+1` nunca sobrepõe fita `true`; fita `false` só preenche cadeia ausente/falha), colocou
`creator_net_seller` no cooldown determinístico e criou uma memória de 30 min por mint
(`CreatorSoldMemory`). Residual **MÉDIO**, não fechado: quando a leitura de cadeia **falha** (timeout)
e a fita diz `false`, o veredito ainda vira `+1` (compra) em vez de `unknown` — é o mesmo buraco da
T4.45 reaberto num caso mais raro.

## Relacionados
`.claude/state/notes-R56.md` §3.2 · `.claude/state/notes-T4.56.md` ·
`.claude/state/review-T4.55-56.md` · `.claude/state/notes-T4.45.md`
