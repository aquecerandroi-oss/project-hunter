---
tags: [knowledge, nota, meme, pumpfun, snipers, graduacao, portao, base-rate, m5]
tema: memecoin / pump.fun / snipers na primeira foto x chegar a 30 SOL reais e encher a curva, com n grande
fonte: banco da VPS (meme_features_15s, meme_tokens, meme_curve_snapshots), 12-16/09/2026
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r7-q02-teto-de-snipers-agregado.sql
lido_em: 2026-09-16
evidencia: medicao propria (SQL em infra/scripts/sql/research/2026-09-16-r7-q0{1,2}-*.sql; 64 267 moedas nao-Mayhem, 5 dias)
hipotese_testavel: sim
astra: nao consultada nesta nota (pesquisa quant, 16/09)
confiança: backtest do autor
owner: astra
updated: 2026-09-16
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

# KB-0101 — Snipers e graduacao, a medida com n grande (5 dias, 64 mil moedas)

**Pergunta (16/09, alerta R1):** na janela de uma hora do executor, as **duas** unicas moedas que encheram a curva tinham
**39 e 61 snipers** — e `max_snipers <= 10` as recusaria. n = 2 nao decide nada. Esta nota refaz a conta com n grande.

## 1. Como foi medido
- **Unidade = uma moeda.** `snipers` lido na **primeira foto de 15 s com `age_s` 30-120 s** (`meme_features_15s.snipers`,
  a mesma leitura que o portao usa; `NULL` -> faixa `desconhecido`, motivo sempre `no_holders_reader`).
- **Mayhem fora:** `meme_tokens.mayhem_enabled = true` **ou** `mayhem_mode` nao nulo (KB-0098 §1/§5: SOL virtual nao e preco).
- **Desfechos:** (a) pico de `meme_curve_snapshots.real_sol_reserves >= 30`; (b) **encheu a curva** =
  `meme_tokens.completed_at` **ou** `migrated_at` nao nulo; (c) mediana do pico de `mcap_sol` (teorico, dentro da janela
  rastreada de ate 300 s — e uma ordem de grandeza, nao uma marca).
- **Janela do executor:** a mesma foto com `curve_progress_pct` entre 0,02 e 0,50 (fracao 0-1), **fita presente**
  (`tape_reason IS NULL`) e **fluxo > 0** (`net_sol_flow_60s > 0`).
- **Cobertura:** 5 dias (12-16/09; a serie de 15 s nasceu em 12/09 e retem 7 d). 1,68 M linhas, 98,2 % com `snipers` medido.
  SQL: `infra/scripts/sql/research/2026-09-16-r7-q01-snipers-por-faixa-por-dia.sql` (um dia por execucao) e `…-r7-q02-…sql`.

## 2. Universo inteiro (todas as moedas nao-Mayhem com foto aos 30-120 s), 5 dias

| Snipers na 1ª foto | Moedas | >= 30 SOL reais | Encheu a curva | Pico mediano `mcap_sol` (faixa diaria) |
|---|---|---|---|---|
| 0-2 | 40 532 | 202 (**0,50 %**) | 55 (**0,14 %**) | 28 |
| 3-10 | 12 132 | 458 (3,78 %) | 109 (0,90 %) | 33 |
| 11-30 | 6 962 | 810 (11,6 %) | 207 (2,97 %) | 43-50 |
| 31-60 | 3 351 | 725 (21,6 %) | 157 (4,69 %) | 60-74 |
| > 60 | 1 326 | 600 (**45,3 %**) | 104 (**7,84 %**) | 70-111 |
| desconhecido | 647 | 14 (2,2 %) | 68 (10,5 %) | 29 |

Monotono em tudo, nos **cinco dias separados** (o q01 roda por dia: nenhuma inversao de faixa em nenhum dia).
A faixa `desconhecido` e **buraco de medida**, nao sinal: `no_holders_reader` concentra moedas que ja estavam
no fim da curva quando o leitor falhou (10,5 % encheram, mas 2,2 % tem pico de SOL real lido).

## 3. Janela do executor (progresso 0,02-0,50, fita, fluxo > 0) — o que a mesa realmente ve

| Snipers na 1ª foto | Moedas | >= 30 SOL reais | Encheu a curva | IC 95 % (encheu) | Pico mediano `mcap_sol` |
|---|---|---|---|---|---|
| 0-2 | 4 957 | 59 (1,19 %) | 14 (**0,28 %**) | [0,17; 0,47] | 31 |
| 3-10 | 3 651 | 116 (3,18 %) | 32 (0,88 %) | [0,62; 1,24] | 35 |
| 11-30 | 2 152 | 172 (7,99 %) | 49 (2,28 %) | [1,73; 3,00] | 46-50 |
| 31-60 | 1 044 | 144 (13,8 %) | 27 (2,59 %) | [1,79; 3,74] | 58-69 |
| > 60 | 316 | 74 (23,4 %) | 9 (**2,85 %**) | [1,51; 5,32] | 70-90 |
| **total** | 12 118 | 565 (4,66 %) | 131 (1,08 %) | [0,91; 1,28] | — |

## 4. `max_snipers <= 10` remove mais vencedora do que perdedora — sim, e por muito
Na janela do executor o teto **mantem 71 % das moedas (8 608/12 118) e perde 65 % das graduadas (85 de 131)**.
Graduacao **fora** do teto 2,42 % contra **0,53 %** dentro: **razao 4,53×, IC 95 % [3,17; 6,47]** (Katz, log-RR).
No universo inteiro a razao e **13,0× [10,9; 15,6]**. O teto nao e neutro-com-ruido: e o inverso do sinal.

**Qual teto maximiza graduadas por moeda proposta?** Nenhum: a taxa cresce monotonamente ate a ultima faixa
(> 60 snipers = 2,85 %, ainda subindo), entao qualquer teto so corta a cauda boa. O que maximiza e um **piso**:

| Regra (janela do executor) | Moedas/5 d | Graduadas | Por moeda proposta | IC 95 % |
|---|---|---|---|---|
| sem filtro de snipers | 12 118 | 131 | 1,08 % | [0,91; 1,28] |
| `max_snipers <= 10` (hoje) | 8 608 | 46 | **0,53 %** | [0,40; 0,71] |
| `min_snipers >= 11` | 3 510 (702/dia) | 85 | 2,42 % | [1,96; 2,99] |
| `min_snipers >= 16` | 2 654 (531/dia) | 71 | 2,68 % | [2,13; 3,36] |
| `min_snipers >= 21` | 2 096 (419/dia) | 61 | **2,91 %** | [2,27; 3,72] |
| banda 11-60 | 3 194 (639/dia) | 76 | 2,38 % | [1,91; 2,97] |

O melhor ponto com n confortavel e **`min_snipers >= 21`** (2,91 %, 419 moedas/dia propostas, 12 graduadas/dia no
universo). Acima de 21 o ganho e ruido (as ICs de 11, 16 e 21 se sobrepoem); abaixo de 11 a queda e real.

## 5. Recomendacao (3 linhas)
1. **Estagio 1 (mesa):** `max_snipers <= 10` esta invertido — tirar o teto e colocar **piso** `min_snipers >= 11`
   (conservador) ou `>= 21` (o otimo medido); manter teto so se voltar como limite de risco declarado, nunca como filtro de qualidade.
2. **Executor:** remover o teto de snipers da admissao; com o piso >= 11 a fita cai de 2 424 para 702 moedas/dia e a
   densidade de graduadas por proposta sobe 4,5×, o que cabe no orcamento de propostas/hora da T4.29b.
3. **Ressalva que fica:** isto mede **graduacao**, nao **R**. Sniper alto tambem e quem despeja; antes de virar padrao
   o piso precisa do R medido em papel (EXP-M5 braco 3, `flow_v2/3`, `min_snipers 3` — o piso certo pelos numeros e 11-21,
   nao 3). Ate o R fechar, o piso entra como **braco de pesquisa**, nao como conjunto de operador.

## Ligacoes
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] · [[05-EXPERIMENTS/EXP-M5-fluxo-e-holders|EXP-M5]] (bracos 3/4 ja mexem em snipers) · [[05-EXPERIMENTS/EXP-M7-organica-lenta|EXP-M7]] (`snipers <= 2` — previsao de que nao propoe nada; esta nota explica por que) · `docs/DATABASE.md` §43.2

## Errata 16/09 — desfecho refeito sem as nascidas cheias (append-only; nada acima foi editado)

O desfecho desta nota ("encheu" = `completed_at` OU `migrated_at`) inclui moedas que **nascem cheias** (KB-0103/KB-0104).
Refeito em [[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] com `organica` = graduou, `completed_at − created_at > 60 s`
e ao menos uma foto de 15 s com progresso < 0,9. **O veredito não muda:** a escada do §2 continua monotônica nos 5 dias
(0,12 / 0,74 / 2,64 / 4,15 / 6,33 %), o teto ≤ 10 continua perdendo 64,6 % das vencedoras da janela (RR 4,46) e o piso 21
continua no topo (2,841 %). **Muda três coisas:** (a) a faixa `desconhecido` era 96 % forja e cai de 10,5 % para 0,46 %;
(b) na janela do executor a limpeza é quase um no-op (131 → 130) porque exigir progresso 0,02–0,50 na 1.ª foto já exclui a
nascida cheia por construção; (c) a frase "> 60 ainda subindo" **não se sustenta** — na janela é platô, com inversão de faixa
em 4 dos 5 dias; ali manda a corcova de R em 31–60 do KB-0102.

→ [[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] · `infra/scripts/sql/research/2026-09-16-r15-q0{1,2}-*.sql`
