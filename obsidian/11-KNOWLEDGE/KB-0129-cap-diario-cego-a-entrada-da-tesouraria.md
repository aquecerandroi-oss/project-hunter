---
tags: [knowledge, nota, meme, pumpfun, cap-diario, tesouraria, kill-switch, dinheiro-real, m5]
tema: memecoin / pump.fun / o freio de perda diária ficava cego a entradas da tesouraria — corrigido no mesmo dia (T4.60)
fonte: banco da VPS (meme_treasury_swaps, meme_live_positions) + código do executor, 18/09/2026 13:12 BRT
fonte_url: ""
lido_em: 2026-09-18
evidencia: relato de defeito e correção com dinheiro real (T4.60 — .claude/state/notes-T4.60.md)
hipotese_testavel: não
astra: não consultada nesta nota
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-18
status: vivo
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

# KB-0129 — O cap de perda diária era cego a entradas da tesouraria

## O que afirma
Com a tesouraria (T4.54) ligada, o freio `MEME_DAILY_LOSS_CAP_SOL` (0,15) nunca dispararia, porque
cada perda era reposta em USDC → SOL e o cálculo comparava só saldo atual contra saldo do início do
dia.

## Número
13:12:06 BRT: posição YOU perdeu **0,0395 SOL** (−0,77 R). No mesmo segundo a tesouraria trocou 5,75
USDC → 0,0516 SOL porque a carteira caiu abaixo do piso. O heartbeat seguinte publicou
**`daily_loss_sol = 0`** (`equity_sol 0,732 > day_start_sol_equity 0,686`) — o check 18 (`daily_loss`)
e o `assess` do kill switch usam `day_start − equity`, cegos ao influxo.

## O que muda na operação
T4.60 (mesmo dia): `daily_loss_sol = max(0, day_start + inflow_hoje − equity)`, com
`treasury_inflow_today_sol` lido do banco (`meme_treasury_swaps`, linhas `submitted`+`confirmed`), cache
de 10 s, e **falha nunca vira zero** (mantém o último valor conhecido, nunca `None → 0`). Sem essa
correção, o cap de 0,15 SOL não seria mais um freio real enquanto a tesouraria estivesse ligada — o
defeito foi achado e fechado no mesmo pacote de deploy (pacote 5, 18/09).

## Relacionados
`.claude/state/notes-T4.54.md` · `.claude/state/notes-T4.60.md` ·
[[06-DECISIONS/2026-09-12-teste-pequeno-meme-real]] adendo 18/09 10:1x
