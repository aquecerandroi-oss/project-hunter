---
tags: [knowledge, nota, meme, pumpfun, entrada, drawdown, dinheiro-real, m4]
tema: memecoin / pump.fun / o padrão "comprar logo depois de uma queda" da KB-0118 se confirma no dinheiro real, estágios 1 e 1b
fonte: banco da VPS (meme_live_positions, meme_curve_snapshots, meme_features_15s), 16–18/09/2026 BRT
fonte_url: ""
lido_em: 2026-09-17
evidencia: medição própria (R54, R56 — SQL em .claude/state/notes-R54.md e notes-R56.md)
hipotese_testavel: sim
astra: não consultada nesta nota (compilação de duas rodadas de pesquisa)
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-18
status: vivo
---

# KB-0119 — Entrada depois da queda, agora com dinheiro real: 4 de 5, depois 7 de 7

## O que foi medido
Nas mesmas cinco compras reais do estágio 1 (R54) e nas sete do estágio 1b (R56), quantas entraram
logo depois de uma queda de progresso/SOL real da curva — o mecanismo que a
[[11-KNOWLEDGE/KB-0118-nao-entrar-depois-da-queda|KB-0118]] já tinha medido no histórico como o pior
padrão de entrada (−0,305 R em 73 apostas, queda ≥ 50 % com pico ≤ 60 s).

## Número
- **Estágio 1 (R54): 4 de 5.** TAXCOIN 67 → 23 %, Catbyte 81 → 14 %, DOPEY 51 → 36 %, PlanB 20 → 12 %.
- **Estágio 1b (R56): 7 de 7.** Em 6 das 7 a curva perdeu ≥ 50 % do SOL real nos 90 s antes do fill; em
  3 (soly, COVER, Punch) a queda foi de 94–97 %. Em duas (soly, ===) a queda aconteceu **entre a cota
  da proposta e o fill** (≈ 20 s) — a admissão só olha a janela 2–50 % de progresso no instante, nunca
  a cota nem o pico recente.

## O que muda na operação
Confirma em produção real o que a KB-0118 media no histórico: o defeito das 12 compras reais (estágio
1 + 1b, −0,0371 SOL acumulado) é a **entrada**, não a saída — nenhuma regra de saída alternativa deixa
as 5 do estágio 1 no azul (R54 §1). Dois consertos apontados e ainda não ligados: religar
`progress_or_mcap_rising` no `operator/5` (desligado em 16/09, KB-0099) — nenhuma das 7 do estágio 1b
entraria com ele ligado — e armar a guarda `recent_drawdown` (EXP-M13), construída em código (T4.52b-2)
mas ainda **desligada** em qualquer conjunto vivo.

## Relacionados
[[11-KNOWLEDGE/KB-0118-nao-entrar-depois-da-queda|KB-0118]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] ·
[[05-EXPERIMENTS/EXP-M13-sem-entrar-apos-queda|EXP-M13]] ·
[[03-TRADING/Meme/Balanco-2026-09-17-estagio-1]] · [[03-TRADING/Meme/Balanco-2026-09-18-estagio-1b]] ·
`.claude/state/notes-R54.md` · `.claude/state/notes-R56.md`
