---
tags: [experimento, meme, pumpfun, curva, paper, pre-registro, fluxo, holders, relogio-15s, m4]
updated: 2026-09-12
status: pre-registrado
owner: quant-engineer
exp: EXP-M5
strategy: "meme/pumpfun — fluxo e holders: comprar só a moeda jovem com demanda líquida, compradores distintos, holders e progresso subindo, decidida por fotografia de 15 s (carteira paper, sem ordem real)"
version: "gate fluxo_e_holders v1 + saida alvo_3x_trailing_35_apos_1_5x_tempo_30m v1 (conjunto flow_v2/1, relógio 15 s) e gate sonda_de_hype v2 (conjunto hype_probe_v0/2, relógio 1 min), migração 0030"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-M5 — fluxo e holders: a porta v2 e o relógio de 15 s

> **Pré-registro escrito na T4.16 em 2026-09-12 (15:xx BRT), ANTES de existir uma única linha de
> `meme_features_15s` e ANTES de qualquer proposta de `flow_v2/1` ou `hype_probe_v0/2`.** Protocolo
> congelado; avaliações acrescentadas, nunca reescritas. Tudo em papel (`meme_paper_bets`, `mode = 'paper'`);
> sem chave, sem ordem real. Série `EXP-M<n>`; origem: E1 do
> [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas|estudo das 21 apostas de 12/09]].

## Diretiva de origem

"aparecendo bastante proposta mas estamos perdendo todas; não está analisando direito? estamos muito lentos?
analisa o caso" (Everton, 12/09/2026 14:0x BRT). O estudo mediu: em 17 de 21 apostas a moeda **nunca subiu**
depois da entrada; entramos em moedas paradas no valor inicial (~28 SOL) com 1–7 holders; as sondas entraram com
44–53 compras/min **e** 32–48 vendas/min (giro, não demanda); decisão → fill 5–148 s (mediana 27 s) sobre minutos
fechados → idade na entrada 99–289 s, com o dev já fora em 5 das 8 sondas. Esta página ataca os dois defeitos de
**entrada** (o que se compra, e quando); o terceiro (o artefato do placar) é o `outcome_quality` da `0030`.

## Hipótese (congelada)

**H1 (braço 1, `flow_v2/1`):** entre as moedas com 30–300 s de vida, comprar **só** quando há demanda líquida
(`net_sol_flow_1m > 0`, ou `mcap_delta_60s > 0` na série de 15 s quando a fita falta), ≥ 10 compradores
distintos no minuto, `sells/buys ≤ 0,6`, holders subindo em duas leituras seguidas, progresso ≥ 5 % **e**
subindo, snipers ≤ 2, `dev_share ≤ 0,10`, criador não vendedor líquido, participação ≤ 1 % — **decidido por
fotografia de 15 s e preenchido na fotografia de 15 s seguinte** — e vender em 3× / trailing 35 % armado após
1,5× / 1 800 s / `creator_dump` / `line_broken` quando houver linha / piso 50 %, produz expectância líquida
positiva em SOL. **H2 (braço 2, `hype_probe_v0/2`):** a sonda de hype (EXP-M3) com as mesmas três condições
de fluxo somadas ao `hype_score ≥ 0,6` deixa de entrar em giro de robô e tem expectância maior que a
`hype_probe_v0/1` teve.

**H0 (a previsão desta página):** a porta v2 corta a maior parte das entradas ruins **e** a maior parte das
entradas — sobra pouca amostra, e o que sobra continua pagando o pedágio de 3,44 % sem a cauda que o paga.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **REVISE** | Mecanismo: demanda líquida com compradores distintos e holders crescendo é o oposto do que perdeu em 12/09 (giro, 1–7 holders, valor inicial). Mas `buys`/`unique_buyers` continuam fabricáveis por wash (≥ 17 %, [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores|KB-0091]]) e `holders` do board muda em minutos (M-D5). A porta mede demanda **ou** simulação de demanda; a EXP-M6 (pedigree) é a defesa barata contra a segunda |
| C2 | Sobreajuste | **PASS condicionado** | 10 condições de entrada (acima do teto editorial de 8 — declarado: são as do estudo, escritas antes de qualquer dado prospectivo; nenhum limiar tem mais de 2 algarismos: 30, 300, 5, 10, 0,6, 2, 0,10, 1, 3×, 35, 1,5×, 1 800, 50). **Dentro da amostra** de 12/09 a porta teria excluído 18 das 20 perdedoras — o que não vale nada como confirmação (KB-0092) |
| C3 | Amostra | **REVISE** | `unique_buyers ≥ 10` e `sells/buys` exigem a fita, cuja cobertura é ~40 % por IP (T4.2f); a série de 15 s cobre a moeda jovem mas não a fita dela. Estimativa: 0–10 propostas/dia; a maioria das recusas será `buyers_unknown`/`flow_not_polled` — medir isso é o primeiro resultado |
| C4 | Regime | **REVISE** | Hora UTC e dia; sessão americana |
| C5 | Saídas | **N/A → substituído** | 3× / 35 % armado após 1,5× / 1 800 s / dump / linha / piso 50 %; risco = o gasto inteiro. O trailing só arma depois de 1,5× porque o alvo é 3× e um trailing desde a entrada vende o ruído de 15 s |
| C6 | Concentração | **PASS condicionado** | 2,0 SOL, 0,20/dia, **5 abertas** (declarado: horizonte de 30 min num relógio de 15 s abre mais de 3 ao mesmo tempo), 0,05 por mint |
| C7 | Execução | **REJECT para dinheiro real, PASS para papel** | O fill na fotografia de 15 s seguinte é mais realista que o do minuto (o `observed_at` é o block time, ~11 s antes da chegada — a fotografia seguinte é o estado após a decisão), mas MEV, tip, falha de transação e disputa com bots continuam fora |
| C8 | Invalidação | **REVISE** | `creator_dump`, `line_broken` (só quando houver linha — 5+ min de fotografias), trailing, tempo. Sem detector de rug nem de wash |

**Veredito do portão:** **`REVISE`** — 2026-09-12, quant-engineer (T4.16).

## Protocolo (congelado — nunca editar)

- **Conjuntos:** `flow_v2/1` (id `01994d00-6c1a-7000-8000-000000000008`, `research_only`, `exp_ref =
  EXP-M5`, `clock = 15s`) e `hype_probe_v0/2` (`…0009`, `research_only`, `exp_ref = EXP-M5`, relógio de
  1 min — o `hype_score` é feature do minuto: fita do minuto + boards do minuto; a série de 15 s não tem board).
  Semente da `0030` (`infra/migrations/ddl/meme_gate_v2_seed.py`). Ambos com `pedigree_exclusions: true`
  ([[EXP-M6-exclusoes-de-pedigree]] é pré-condição de todo conjunto).
- **code_ref:** `hunter_indicators.meme.rules:evaluate_entry+evaluate_exit` — critérios em
  `rules_criteria.py` (`flow_refusals`), série instantânea em `hunter_indicators.meme.fast`
  (`mcap_delta_60s`, `mcap_slope_60s`, `progress_delta_60s`, `holders_rising`, v1); laço em
  `services/meme-worker/hunter_meme_worker/{fast_lane,features_fast,repo_fast,lab_fast,lab_repo_fast}.py`.
- **Porta de `flow_v2/1` (JSON completo):** `{"min_age_s": 30, "max_age_s": 300, "min_progress_pct": "5",
  "max_progress_pct": "100", "require_progress": true, "require_progress_rising": true,
  "require_positive_flow": true, "min_unique_buyers": 10, "max_sells_to_buys": "0.6",
  "require_holders_rising": true, "max_snipers": 2, "max_dev_share": "0.10",
  "dev_share_unknown_allowed": false, "require_creator_not_net_seller": true,
  "max_participation_pct": "1"}`. *Decisões declaradas:* `dev_share` desconhecido **recusa** (o brief não
  abre exceção aqui, ao contrário da sonda); a série de 15 s substitui `net_sol_flow_1m` por
  `net_sol_flow_60s` (mesma fita, janela `(as_of − 60 s, as_of]`) e o progresso "subindo" por
  `progress_delta_60s > 0`; "holders subindo em duas leituras" = a leitura mais recente acima da anterior
  (board ou risco, `received_at <= as_of`).
- **Saídas de `flow_v2/1`:** `{"target_x": "3", "trailing_pct": "35", "trailing_arm_x": "1.5",
  "max_hold_s": 1800, "max_loss_pct": "50", "exit_on_line_break": true, "line_break_snapshots": 2,
  "exit_on_creator_dump": true}`; `size_sol = 0,05`.
- **Porta de `hype_probe_v0/2`:** a de `hype_probe_v0/1` verbatim (30–300 s, `hype_score ≥ 0,6`,
  `dev_share ≤ 0,10` ou desconhecido com motivo, snipers ≤ 2, criador, participação; progresso não é critério)
  **mais** `require_positive_flow`, `min_unique_buyers 10`, `max_sells_to_buys 0,6`; sonda 0,01 SOL, 3× / 40 % /
  600 s / piso 50 %, escala 0,04 por `trendline_v0/1` (inalterada).
- **Relógio:** `flow_v2/1` é julgado **em cada fotografia** de 15 s (`meme_features_15s`, uma linha por mint
  < 5 min por leitura do laço `meme-fast`; `features_end_time` da proposta = `as_of`; `reasons[0].series =
  meme_features_15s_v1`); o fill é a primeira fotografia com `observed_at > decided_at` — a seguinte, 15 s
  depois. `hype_probe_v0/2` continua no minuto fechado. Não-antecipação: só insumos com `received_at <=
  as_of` (SQL e puro), provado por look-ahead em três camadas.
- **Tetos:** `wallet_max_sol 2,0`, `daily_loss_cap_sol 0,20`, `max_open_positions 5`, `max_sol_per_bet 0,05`,
  `max_exposure_per_mint_sol 0,05`, `fee_pct 1,75`, `priority_fee_sol 0`.
- **Coorte:** prospectiva, os dois `rule_set_id`, a partir da primeira proposta na VPS (`‹pendente›`).
- **Controle pré-declarado:** para o braço 1, a mesma porta **sem** os cinco critérios de fluxo/holders
  (idade, progresso ≥ 5 %, snipers, dev, criador, participação — i.e. a EXP-M1 com progresso a 5 %) sobre os
  mesmos mints e instantes; o Δ mede o que "demanda" acrescenta. Para o braço 2, a própria `hype_probe_v0/1`
  (descartada) sobre o mesmo período: o Δ mede o que o fluxo acrescenta ao hype. Cláusula de identidade: se o Δ
  aparecer cortando por `unique_buyers ≥ 10` sozinho, a porta é redundante com "teve comprador" → `descartar`.
- **Placar:** só desfechos `measured` entram nas somas; `indeterminate` (sem fotografia) é contado à parte
  (`0030`).
- **Universo:** todo mint rastreado com `created_at` conhecido (a série de 15 s exige a idade), sem filtro de
  sobrevivência.

## Priors contrários, com número

1. Wash ≥ 17 % e clusters de criadores 63 % ([[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores|KB-0091]]):
   compradores distintos e holders são fabricáveis.
2. Cobertura da fita ~40 % por IP (T4.2f): a porta vai recusar por cegueira (`buyers_unknown`) na maioria
   dos instantes — a amostra pode não fechar.
3. Pedágio 3,44 % por ida e volta; alvo 3× com piso 50 % exige ≥ 20 % de alvos para empatar (0,5/2,5).
4. Um modelo que parecia bom caiu a 0,46 fora da amostra ([[KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]]):
   os "18 de 20 excluídas" do estudo são dentro da amostra.

## Previsões congeladas

- **P1 — a cegueira primeiro:** ≥ 60 % das avaliações da porta de 15 s recusam por insumo ausente
  (`buyers_unknown`/`flow_not_polled`/`holders_too_few_readings`), não por o fluxo dizer não.
- **P2 — a latência cai:** `decision_to_fill_s` p50 ≤ 15 s e p95 ≤ 20 s nos fills de `flow_v2/1` (medido no
  heartbeat; era 27 s / 148 s nas 21 apostas).
- **P3 — a idade na entrada cai:** mediana ≤ 120 s (era 99–289 s).
- **P4 — expectância do braço 1:** entre −0,40 e +0,10 R (ponto **−0,15 R**); ≤ 15 % das entradas atingem 3×.
  **Veredito previsto: `descartar`** (H0), com a ressalva de população: < 100 apostas em 30 dias é o
  resultado mais provável.
- **P5 — braço 2 vs `hype_probe_v0/1`:** a fração de entradas em giro (`sells/buys > 0,6` no minuto da
  entrada) cai de 8/8 para ≤ 20 %; a expectância da sonda sobe ≥ 0,10 R mas continua ≤ 0.
- **P6 — pedigree:** ≥ 30 % das recusas de qualquer porta são `creator_serial`/`symbol_clone` (EXP-M6).

## Regra de sucesso (congelada)

`validada` (por braço) exige as seis da EXP-M1 **e** Δ contra o controle > 0 sem identidade **e** leave-top-out
positivo **e** ≥ 100 apostas em ≥ 30 dias. Qualquer coisa menos: `descartar`, com o conjunto retirado pelo
script auditado (`infra/scripts/meme_rule_set.py --deprecate`) no mesmo dia; a página fica.

## Regras de morte

- **K1** — `buyers_unknown` + `flow_*` em > 80 % das avaliações: o instrumento (fita) não cobre a janela; parar
  e consertar a cobertura (2.º IP ou `market-activity/batch`), não relaxar a porta.
- **K2** — > 30 % de censura. **K3** — fill sem fotografia posterior (impossível por construção: `test_lab_fast`).
- **K4** — expectância positiva vinda de < 3 mints. **K5** — uma proposta de `flow_v2/1` com
  `features_end_time` sem linha correspondente em `meme_features_15s`: bug de laço, invalida a coorte.

## Avaliações (acrescentadas, nunca reescritas)

*Nenhuma.* A página nasce em 2026-09-12 com `result: nao-iniciado`, `evaluable: 0`, `days: 0`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde |
|---|---|---|---|
| — | — | — | — |

## Relacionadas

[[Experiments Index]] · [[03-TRADING/Meme/README|Meme (Trading)]] · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas]] ·
[[EXP-M1-comprar-cedo-na-curva]] · [[EXP-M3-sonda-de-hype]] · [[EXP-M4-moonshot]] · [[EXP-M6-exclusoes-de-pedigree]] ·
[[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · [[KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout]]

## Fontes

`packages/indicators/hunter_indicators/meme/{fast,rules,rules_criteria}.py` · `packages/indicators/tests/unit/{test_meme_fast,test_meme_rules_flow}.py` ·
`services/meme-worker/hunter_meme_worker/{fast_lane,features_fast,repo_fast,lab_fast,lab_repo_fast,lab}.py` ·
`services/meme-worker/tests/{test_fast_lane,test_features_fast,test_proposals_flow,test_lab_fast}.py` ·
`infra/migrations/versions/0030_meme_gate_v2.py` · `docs/DATABASE.md` §43 · `docs/plans/T4-MEME-RADAR.md` §T4.16 ·
`docs/RISK_ENGINE_MEME.md` §10.7 · `.claude/state/brief-T4.16-porta-v2-e-relogio-de-15s.md` ·
`infra/scripts/sql/research/2026-09-12-t416-caso-das-21-apostas.sql`.
