---
tags: [knowledge, nota, meme, pumpfun, snipers, porta, calibracao, m4]
tema: memecoin / pump.fun / o piso de snipers ≥ 21 nunca custou uma vencedora real, mas zera as vencedoras do papel
fonte: banco da VPS (meme_features_15s, meme_paper_bets, meme_live_orders), 16/09/2026
fonte_url: ""
lido_em: 2026-09-16
evidencia: medição própria (R46, R54 — SQL em .claude/state/notes-R46.md e notes-R54.md)
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

# KB-0120 — O piso de snipers ≥ 21 nunca custou uma vencedora real; as vencedoras do papel têm 0–10

## O que afirma
O `operator/5` exige `snipers ∈ [21, 1000]` desde 16/09 16:24 ([[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]]).
Duas leituras da mesma noite mostram lados opostos do mesmo piso.

## Número
- **Nunca violado nas 27 ordens reais** da noite de 16/09 (R46): todas tinham snipers ≥ 21 na foto de
  entrada. No radar, o piso cortou 15 das 44 moedas que passavam os demais critérios; **11 das 15
  (73 %) perderam ≥ 50 %** — o corte protegeu.
- **Zero das 45 apostas vencedoras do braço de papel `flow_v2/5`** (R54, mesma noite) tinham snipers
  ≥ 21 — todas as entradas do braço que deu **+0,109 SOL (20 vitórias)** vieram com 0–10 snipers. O
  `operator/5` recusou **11 das 20 maiores vencedoras** por `snipers_below_min` (Ghosty +1,91 R com
  2 snipers, FLOCK +1,33 R com 3), e as outras 9 nem aparecem no log por caírem em **duas** recusas
  ao mesmo tempo (snipers **e** progresso > 50 %).

## O que muda na operação
O piso não é "certo" nem "errado" — é uma escolha de qual população servir. Motivou a **Proposta A**
(18/09, [[06-DECISIONS/2026-09-12-teste-pequeno-meme-real]] adendo 10:5x): `min_snipers` removido,
`max_snipers` 1000 → 10 no `operator/5`, alinhando a mesa real à faixa do braço vencedor de papel.

## Relacionados
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] ·
[[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] ·
[[06-DECISIONS/2026-09-12-teste-pequeno-meme-real]] ·
`.claude/state/notes-R46.md` · `.claude/state/notes-R54.md`
