---
tags: [experimento, meme, pumpfun, curva, paper, pre-registro, linhas, m4]
updated: 2026-09-12
status: pre-registrado
owner: quant-engineer
exp: EXP-M2
strategy: "meme/pumpfun — a linha manda: suporte pelos dois últimos fundos, rompimento da máxima da janela anterior (carteira paper, sem ordem real)"
version: "gate a_linha_manda v1 + saida alvo_2x_trailing_30_tempo_15m_linha v1 (conjunto trendline_v0/1, migração 0026)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-M2 — a linha manda: comprar quando o suporte sobe e a máxima anterior é rompida

> **Pré-registro escrito na T4.10 em 2026-09-12 (11:3x BRT), ANTES de existir uma única linha
> `meme_features_v3` em `meme_features_1m` e ANTES de qualquer proposta do conjunto
> `trendline_v0/1`.** O protocolo abaixo é congelado: nada nesta seção muda depois; avaliações são
> **acrescentadas** datadas, nunca reescritas (`exp_reescrita` do `obsidian_lint.py`). Nada aqui é
> dinheiro real — o conjunto é `research_only`, a carteira é a do Lab meme (`meme_paper_bets`,
> `mode = 'paper'` travado por CHECK), sem chave, sem RPC de escrita. Série `EXP-M<n>`
> ([[03-TRADING/Meme/README|Meme (Trading)]]), irmã da [[EXP-M1-comprar-cedo-na-curva]].

## Diretiva de origem

"Lembra: você é obrigado a usar traçamento de linha" (Everton, 12/09/2026 10:5x BRT). A leitura do
orquestrador que este experimento mede: toda moeda analisada tem as **linhas traçadas** — suporte pela
reta dos dois últimos fundos locais, resistência pela máxima recente, rompimento — **como feature
calculada** (`hunter_indicators.meme.lines`), nunca como desenho à mão. Este experimento pergunta se
essas linhas, na escala de 15 minutos de uma curva de bonding, **separam expectância**.

## Hipótese (congelada)

**Numa curva da pump.fun com ≥ 5 minutos de fotografias, comprar quando (a) os dois últimos fundos
locais de 15 minutos são ascendentes, (b) a capitalização do minuto fechado iguala ou supera a máxima
da janela anterior de 15 minutos e (c) o preço está entre 0 e 25 % acima da reta de suporte — além de
tudo o que a EXP-M1 já exige (progresso 2–50 %, participação ≤ 1 %, criador não vendedor líquido) — e
vender em 2× / trailing 30 % / time stop 15 min / **linha rompida** (dois fechos seguidos abaixo do
suporte) produz expectância líquida positiva em SOL depois de 1,75 % por ponta e do impacto da própria
ordem.**

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **REVISE** | O mecanismo declarado é o de toda análise técnica: fundos ascendentes = demanda absorvendo oferta; rompimento = quem estava vendido na máxima anterior desiste. Numa curva de 15 minutos com 15 fotografias, "fundo local" é ruído de amostragem com a mesma frequência que é demanda; e o rompimento no minuto fechado chega 60–120 s depois de acontecer — na EXP-0016 (SPOT) a mesma família não sobreviveu ao pedágio. O mecanismo existe; a vantagem nossa nele não está argumentada |
| C2 | Sobreajuste | **PASS** | Três condições novas (fundos ascendentes, rompimento, banda 0–25 %) sobre as quatro da EXP-M1: 7 condições de entrada (< 8). Todo limiar tem ≤ 2 algarismos: W = 15 min, mínimo 5 pontos, banda 0–0,25, 2 fechos, idade ≥ 300 s. **Nenhum limiar foi escolhido olhando dado** — vêm do brief da T4.10 |
| C3 | Amostra | **REVISE** | A linha exige ≥ 5 fotografias numa janela de 15 min: com um poll por minuto e 250 mints rastreados, boa parte das moedas morre antes dos 5 minutos ([[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]]: vida mediana 0,01 dia). Estimativa declarada: das ~40 mil criações/dia, < 5 % chegam a 5 min com linha; das que chegam, a porta completa (linha + progresso + criador + participação) deve passar < 1 %. 30 dias podem dar **0 a 200** desfechos |
| C4 | Regime | **REVISE** | O que existe é hora UTC e dia; a avaliação estratifica por isso e diz que o resto não foi controlado (igual à EXP-M1) |
| C5 | Saídas | **N/A → substituído** | R = PnL ÷ custo inteiro (uma curva não tem livro). A saída própria é a **linha rompida**: dois fechos seguidos abaixo da reta projetada ao instante da fotografia (`lines_exit.py`); ela fica **depois** do piso de 50 % e **antes** do alvo na precedência (`hunter_indicators.meme.exits`) |
| C6 | Concentração | **PASS condicionado** | Mesmos tetos da EXP-M1 (carteira 2,0 SOL, 0,05 por aposta, perda do dia 0,20, 3 posições, 0,05 por mint), parâmetros na semente da `0026`, revisáveis pelo Everton (`docs/RISK_ENGINE_MEME.md` §14) |
| C7 | Execução | **REJECT para dinheiro real, PASS para papel** | Igual à EXP-M1: fill na primeira fotografia posterior à decisão, venda na fotografia seguinte à regra, 1,75 % por ponta, impacto pela fórmula da curva; sem MEV, sem bundle, sem transação falhada |
| C8 | Invalidação | **PASS** | Pela primeira vez a invalidação é **própria da tese**: a linha que a justificou deixa de segurar (`line_broken`). Continuam genéricos o piso de perda e o time stop; `creator_dump` e migração continuam como na EXP-M1; `rug_suspected` continua sem detector |

**Veredito do portão:** **`REVISE`** — 2026-09-12, quant-engineer (T4.10). O experimento abre para
medir; a régua de sucesso impede que abrir cedo vire ativar cedo.

## Protocolo (congelado — nunca editar)

- **Conjunto de regras:** `trendline_v0/1` (semente da migração `0026_meme_lines`, id
  `01994d00-6c1a-7000-8000-000000000003`, `kind = research_only`, `exp_ref = EXP-M2`), porta
  `a_linha_manda v1` + saída `alvo_2x_trailing_30_tempo_15m_linha v1`. Mudar qualquer limiar é versão
  nova e `EXP-M2b`.
- **code_ref:** `hunter_indicators.meme.rules:evaluate_entry+evaluate_exit` — `lines.py` (as linhas),
  `rules.py` (porta), `exits.py` (saídas, `line_broken`); fold em
  `services/meme-worker/hunter_meme_worker/features_lines.py` (`meme_features_v3`); saída no laço em
  `lines_exit.py` + `lab_bets.py`.
- **Features (definição, `LINE_DEFINITIONS` v1):** janela `(end_time − 15 min, end_time]` sobre
  `mcap_sol` das fotografias com `received_at <= end_time`; fundo local = ponto estritamente abaixo dos
  dois vizinhos; `support_line_sol` = reta pelos **dois últimos** fundos avaliada em `end_time`;
  `support_line_slope` em SOL/min; `higher_lows` = 2.º fundo > 1.º; `distance_to_support_pct` =
  (mcap − suporte)/suporte; `high_15m_sol`/`low_15m_sol` = extremos da janela; `breakout_15m` = mcap
  do minuto ≥ máxima da janela **anterior** `(end_time − 16 min, end_time − 1 min]` (o minuto nunca é a
  própria referência); `mcap_slope_5m/15m` = inclinação OLS de ln(mcap) × minutos. Nulos nomeados:
  `too_few_points` (< 5 pontos), `no_snapshot`, `flat` (sem dois fundos), `out_of_range`.
- **Porta (JSON completo):** `{"min_age_s": 300, "max_age_s": 600, "min_progress_pct": "2",
  "max_progress_pct": "50", "max_participation_pct": "1", "require_creator_not_net_seller": true,
  "require_higher_lows": true, "require_breakout_15m": true, "min_distance_to_support_pct": "0",
  "max_distance_to_support_pct": "0.25"}`. Recusas nomeadas por insumo ausente: `line_<motivo>`,
  `breakout_unknown`, mais as da EXP-M1.
- **Saídas:** `{"target_x": "2", "trailing_pct": "30", "max_hold_s": 900, "max_loss_pct": "50",
  "exit_on_line_break": true, "line_break_snapshots": 2, "exit_on_migration": true,
  "exit_on_creator_dump": true}`. Precedência: rug (sem detector) → creator_dump → migração/conclusão →
  piso 50 % → **linha rompida** → alvo → trailing → time stop. A linha usada na saída é a do último
  minuto dobrado **em ou antes** da fotografia julgada, projetada pela inclinação — nunca um minuto
  dobrado depois.
- **Tamanho e tetos:** `size_sol = 0,05`, `wallet_max_sol = 2,0`, `daily_loss_cap_sol = 0,20`,
  `max_open_positions = 3`, `max_exposure_per_mint_sol = 0,05`, `fee_pct = 1,75`, `priority_fee_sol = 0`.
- **Preço:** fill na primeira fotografia com `observed_at > decided_at`; venda na fotografia seguinte à
  que disparou a regra; sem fotografia em 3 min → `rug_no_snapshot` (posição a zero).
- **Coorte:** prospectiva, `meme_paper_bets.rule_set_id = trendline_v0/1`, a partir do primeiro minuto
  `meme_features_v3` dobrado na VPS (`‹pendente›` — data do deploy da T4.10).
- **Controle pré-declarado:** os mesmos minutos em que a porta **sem os três critérios de linha**
  (= a porta da EXP-M1 com idade ≥ 300 s) abriria, com a mesma geometria de saída sem `line_broken`;
  o Δ da linha é reportado contra esse controle. Cláusula de identidade: se o mesmo Δ aparecer cortando
  por `mcap_slope_15m > 0` sozinho, a linha é redundante com "está subindo" e o veredito é `descartar`.
- **Universo:** todo mint rastreado, sem filtro de sobrevivência.

## Priors contrários, com número

1. [[EXP-0016-trendline-breakout]] (SPOT/perp): a mesma família de sinal não pagou o pedágio de 8 bps;
   aqui o pedágio é **3,44 %** de ida e volta ([[EXP-M1-comprar-cedo-na-curva]] P2).
2. Com 15 pontos por janela, dois fundos "ascendentes" por acaso têm probabilidade alta demais para uma
   série i.i.d.; a linha existe sempre que a série não é monótona — o que a torna barata de satisfazer.
3. O rompimento é lido no minuto fechado, 60–120 s depois: os bots do
   [[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] já compraram.

## Previsões congeladas

- **P1 — a linha é rara.** Em 30 dias, < 5 % das linhas de minuto (`meme_features_v3`) têm
  `line_reason IS NULL` **e** `higher_lows` **e** `breakout_15m` **e** distância em [0, 0,25]; a
  maioria dos minutos diz `too_few_points`.
- **P2 — a linha rompe rápido.** Mediana do tempo até `line_broken` < 4 min; ≥ 50 % das saídas são
  `line_broken` ou `max_loss`, < 15 % são `target`.
- **P3 — expectância.** Entre −0,30 e 0,00 R (ponto −0,12 R). **Veredito previsto: `descartar`.**
- **P4 — Δ contra o controle:** dentro de ±0,05 R — a linha não faz trabalho que "idade ≥ 5 min e
  subindo" não faça.

## Regra de sucesso (congelada)

`validada` exige todas as seis da EXP-M1 (expectância > 0 com IC 95 % por blocos de dia, semente
20260912; ≥ 100 desfechos e ≥ 30 dias; 2 de 3 janelas; leave-top-1 %-out; Δ contra o controle > 0 sem
identidade; ≤ 20 % censura) **e** uma sétima: **≥ 100 minutos com linha traçável** por dia distinto na
média — abaixo disso o instrumento é o gargalo. Qualquer coisa menos: `descartar`.

## Regras de morte

- **K1** — `line_reason IN ('too_few_points', 'no_snapshot')` em > 90 % dos minutos de mints com idade
  ≥ 5 min: a cadência do poll não sustenta a linha; parar e consertar o instrumento.
- **K2** — > 30 % de censura. **K3** — fill sem fotografia posterior (impossível por construção).
- **K4** — expectância positiva vinda de < 3 mints.

## Avaliações (acrescentadas, nunca reescritas)

*Nenhuma.* A página nasce em 2026-09-12 com `result: nao-iniciado`, `evaluable: 0`, `days: 0`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde |
|---|---|---|---|
| — | — | — | — |

## Relacionadas

[[Experiments Index]] · [[03-TRADING/Meme/README|Meme (Trading)]] · [[EXP-M1-comprar-cedo-na-curva]] ·
[[EXP-M3-sonda-de-hype]] (a sonda escala para a perna 2 quando **esta** porta confirma) ·
[[EXP-0016-trendline-breakout]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] ·
[[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]

## Fontes

`packages/indicators/hunter_indicators/meme/{lines,rules,exits}.py` · `packages/indicators/tests/unit/test_meme_lines.py`,
`test_meme_rules_lines.py` · `services/meme-worker/hunter_meme_worker/{features_lines,repo_lines,lines_exit,lab_bets}.py` ·
`infra/migrations/versions/0026_meme_lines.py` · `docs/DATABASE.md` §38 · `docs/plans/T4-MEME-RADAR.md` §T4.10 ·
`.claude/state/brief-T4.10-tracado-de-linhas-e-sonda-de-hype.md`.
