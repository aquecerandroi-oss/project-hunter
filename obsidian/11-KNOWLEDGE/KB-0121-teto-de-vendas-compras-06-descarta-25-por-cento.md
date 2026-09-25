---
tags: [knowledge, nota, meme, pumpfun, porta, calibracao, sells-buys, m5]
tema: memecoin / pump.fun / o teto de sells/buys em 0,6 descarta 24,6 % das graduadas; 0,81 reteria 90 %
fonte: banco da VPS (meme_features_1m, meme_tokens), 16/09/2026, 24 h retroativas
fonte_url: ""
lido_em: 2026-09-17
evidencia: medição própria (R48 + sensibilidade R51 — SQL em .claude/state/notes-R48.md e notes-R51.md)
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

# KB-0121 — Teto de sells/buys em 0,6 descarta 24,6 % das graduadas; 0,81 reteria 90 %

## O que afirma
O cap de `sells/buys ≤ 0,6` (`operator/5`, `flow_v2/6`) corta uma faixa de transição onde a taxa de
graduação está subindo, não caindo.

## Número
- Graduadas com `sells/buys ≤ 0,6`: **6 de 1 135 (0,53 %)**; acima de 0,6: **113 de 5 365 (2,12 %)** —
  **4,0×** menor abaixo do cap. Cap 0,6 descarta **113 de 459 graduadas do dia (24,6 %)**; um cap em
  **0,81** (P10 das graduadas) reteria **90 %**.
- Sensibilidade posterior (R51, 77 graduadas × 2 000 mortas, com viés de "melhor leitura" declarado):
  **remover** o teto de razão ganha **+9 graduadas (2 → 11) por +5 losers extras (1 → 6)**, precisão
  66,7 % → 64,7 %; remover o piso de compradores (`unique_buyers ≥ 10`) ganha **+1 sem custo** (75 %
  de precisão). Remover o piso de holders é **custo puro** (0 ganho, +1 loser).

## O que muda na operação
Motivou [[05-EXPERIMENTS/EXP-M14-razao-vendas-compras|EXP-M14]] (teto 0,6 → 1,0, braço `flow_v2/8`,
semeado 17/09). O valor 0,81 sugerido pelo R48 **não** foi testado como braço próprio — a régua ainda
não fechou (≥ 150 propostas **e** 10 dias). R51 avisa que a sensibilidade "online" real (sem espiar
30 min à frente) é **2–5× menor** que a medida aqui.

## Relacionados
[[05-EXPERIMENTS/EXP-M14-razao-vendas-compras|EXP-M14]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] ·
`.claude/state/notes-R48.md` · `.claude/state/notes-R51.md`
