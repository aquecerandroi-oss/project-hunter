---
tags: [experimento, meme, pumpfun, curva, paper, pre-registro, hype, sonda, m4]
updated: 2026-09-12
status: pre-registrado
owner: quant-engineer
exp: EXP-M3
strategy: "meme/pumpfun — semi-comprado por hype: sonda de 1/5 do tamanho antes de a linha existir, escalada para a perna 2 quando a linha confirma (carteira paper, sem ordem real)"
version: "gate sonda_de_hype v1 + saida alvo_3x_trailing_40_tempo_10m v1 + escala via trendline_v0/1 (conjunto hype_probe_v0/1, migração 0026)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-M3 — a sonda de hype: semi-comprado antes de a linha existir, escalado quando ela confirma

> **Pré-registro escrito na T4.10 em 2026-09-12 (11:3x BRT), ANTES de existir uma única linha
> `meme_features_v3` e ANTES de qualquer proposta do conjunto `hype_probe_v0/1`.** Protocolo
> congelado; avaliações acrescentadas, nunca reescritas. Tudo em papel (`meme_paper_bets`, `mode =
> 'paper'`); sem chave, sem ordem real. Série `EXP-M<n>`, irmã da [[EXP-M1-comprar-cedo-na-curva]] e
> par da [[EXP-M2-a-linha-manda]].

## Diretiva de origem

"…e os que não tiver [linha] você vai deixar já semi-comprado por causa do hype" (Everton, 12/09/2026).
Uma moeda jovem demais para ter linha (< 5 minutos de fotografias) não fica de fora: entra **semi-
comprada** — uma sonda de **1/5** do tamanho (0,01 SOL) justificada por um **score de hype documentado**
— e **escala** para o tamanho cheio (segunda perna de 0,04 SOL, aposta separada com `parent_bet_id`)
quando a mesma moeda passa a satisfazer a porta da EXP-M2 com a sonda ainda aberta; se a sonda sai por
time stop sem linha, não escala.

## Hipótese (congelada)

**Uma moeda com 30 s a 5 min de vida, `hype_score ≥ 0,6` (média ponderada documentada de compras do
minuto, compradores únicos, posição nos boards `movers`/`new`, presença social e poucos snipers),
`dev_share ≤ 10 %` (ou desconhecido com motivo), `snipers ≤ 2`, criador não vendedor líquido e
participação ≤ 1 %, comprada com 0,01 SOL e vendida em 3× / trailing 40 % / 600 s, produz expectância
líquida positiva em SOL; e a segunda perna de 0,04 SOL, aberta só quando a linha da EXP-M2 confirma com a
sonda aberta, tem expectância maior que a da sonda sozinha.** São duas hipóteses; a régua julga as duas.

## O score de hype (definição congelada, `hype_score` v1)

| componente | insumo | normalizado | peso |
|---|---|---|---|
| `buys_1m` | `meme_features_1m.buys_1m` | min(buys, 30)/30 | 0,35 |
| `unique_buyers_1m` | `meme_features_1m.unique_buyers` | min(u, 20)/20 | 0,25 |
| `board` | melhor posição (0-based) em `movers`/`new` no minuto | top-10 → 1; top-50 → 0,5; senão 0 | 0,20 |
| `has_social` | `meme_board_observations.has_social` | 1 se verdadeiro | 0,10 |
| `snipers_low` | `meme_features_1m.snipers` | 1 se snipers ≤ 2 (desconhecido → 0) | 0,10 |

`score = Σ peso × normalizado`, em [0, 1]; NULL com `hype_reason = no_tape_no_board` quando nem a fita
nem o board falaram do mint no minuto; `partial` ao lado de um número quando só uma das duas fontes
falou (a outra entra com 0). A decomposição (raw, normalizado, peso, contribuição) acompanha o número.
Exemplo que os testes fixam: 15 compras, 10 compradores, posição 3, social, 1 sniper → **0,700000**.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **REVISE** | "Hype" aqui é fluxo de compra + visibilidade no site. O mecanismo é o do sniper: chegar antes de quem chega pelo board. Só que ≥ 17 % do volume das criações é wash trading atômico e 63 % vem de clusters de criadores ([[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]]): `buys_1m` e `unique_buyers` são exatamente o que um criador fabrica para aparecer no `new`. O score mede hype **ou** simulação de hype, e este experimento não separa os dois |
| C2 | Sobreajuste | **PASS** | 6 condições de entrada (idade, hype, dev, snipers, criador, participação); 5 pesos e 4 limiares do score fixados pelo brief, nenhum ajustado a dado; 2 algarismos em todos (0,6; 0,10; 2; 30; 20; 10; 50) |
| C3 | Amostra | **PASS condicionado** | A janela de 30 s–5 min alcança quase toda criação rastreada; o gargalo é a fita (`tape_coverage_pct` ~40 % em 12/09) e o board. Estimativa: 5–50 sondas/dia; a **escala** é rara (exige a porta da EXP-M2 com a sonda aberta): 0–5/dia |
| C4 | Regime | **REVISE** | Igual às irmãs: hora UTC e dia |
| C5 | Saídas | **N/A → substituído** | Sonda: 3× / trailing 40 % / 600 s / piso 50 %. Perna 2: as saídas da EXP-M2 (2× / 30 % / 900 s / linha rompida). Risco de cada perna = o gasto inteiro; a sonda de 0,01 é 1/5 do risco de uma aposta cheia |
| C6 | Concentração | **PASS condicionado** | Carteira 2,0 SOL, perda do dia 0,20 SOL, **máximo 5 sondas abertas** (a perna 2 ocupa a vaga da sonda, não uma nova), 0,05 por mint (= sonda + perna 2), `max_sol_per_bet = 0,04` |
| C7 | Execução | **REJECT para dinheiro real, PASS para papel** | Igual às irmãs; e a sonda a 30 s de vida compete com os bots mais rápidos que existem — a perda entre decisão e fill vai ser a maior das três páginas |
| C8 | Invalidação | **REVISE** | A sonda invalida por trailing/tempo (genéricos) e por `creator_dump`; a perna 2 herda `line_broken`. Não há detector de rug nem de wash trading — o que C1 diz que mais importa aqui |

**Veredito do portão:** **`REVISE`** — 2026-09-12, quant-engineer (T4.10).

## Protocolo (congelado — nunca editar)

- **Conjunto:** `hype_probe_v0/1` (semente da `0026`, id `01994d00-6c1a-7000-8000-000000000004`,
  `research_only`, `exp_ref = EXP-M3`), porta `sonda_de_hype v1`, saída `alvo_3x_trailing_40_tempo_10m
  v1`, escala pela porta de `trendline_v0/1`.
- **code_ref:** `hunter_indicators.meme.rules:evaluate_entry+evaluate_exit` — `hype.py` (score),
  `rules.py` (porta); laço em `services/meme-worker/hunter_meme_worker/{proposals_scale,lab,paper_fill}.py`.
- **Porta (JSON completo):** `{"min_age_s": 30, "max_age_s": 300, "require_progress": false,
  "min_progress_pct": "0", "max_progress_pct": "100", "max_participation_pct": "1",
  "require_creator_not_net_seller": true, "min_hype_score": "0.6", "max_dev_share": "0.10",
  "dev_share_unknown_allowed": true, "max_snipers": 2}`. *Decisão declarada:* o progresso **não** é
  critério (o brief não o lista e uma curva de 30 s raramente tem denominador); `dev_share` desconhecido
  **com motivo** passa (o brief manda); snipers desconhecidos **recusam** (`snipers_unknown`); criador
  desconhecido recusa, como hoje.
- **Sonda:** `size_sol = 0,01`, `target_x = 3`, `trailing_pct = 40`, `max_hold_s = 600`,
  `max_loss_pct = 50` (o piso da EXP-M1, carregado — o brief não fixa outro), `leg = probe`.
- **Escala (perna 2):** `scale_size_sol = 0,04`, `scale_gate = trendline_v0/1`; **só** enquanto a sonda
  está `open`, **só** quando a porta de `trendline_v0/1` é satisfeita para o mesmo mint no minuto
  fechado (participação julgada com **0,04**, não com 0,01), **uma vez por sonda** (qualquer aposta ou
  proposta pendente que já nomeie a sonda como `parent_bet_id` impede outra); aposta separada, `leg =
  scale`, `parent_bet_id` = a sonda, saídas da EXP-M2 (2× / 30 % / 900 s / `line_broken`). Se a sonda
  saiu (time stop, trailing, dump), não há escala. A recusa da escala é contada no heartbeat com prefixo
  `scale:` (`scale:line_too_few_points`…).
- **Tetos:** `wallet_max_sol = 2,0`, `daily_loss_cap_sol = 0,20`, `max_open_positions = 5` (sondas e
  singles; a perna 2 não ocupa vaga), `max_exposure_per_mint_sol = 0,05`, `max_sol_per_bet = 0,04`,
  `fee_pct = 1,75`, `priority_fee_sol = 0`.
- **Preço:** fill na primeira fotografia posterior à decisão; venda na fotografia seguinte à regra;
  `rug_no_snapshot` sem fotografia em 3 min.
- **Coorte:** prospectiva, `rule_set_id = hype_probe_v0/1`, a partir do primeiro minuto
  `meme_features_v3` na VPS (`‹pendente›`).
- **Controle pré-declarado:** sondas sorteadas em mints com 30 s–5 min **sem** a porta de hype (só
  criador, snipers e participação), mesma geometria de saída, mesma frequência. O Δ do hype é reportado
  contra isso. Para a perna 2, o controle é a **própria sonda**: a perna 2 só tem sentido se a sua
  expectância em R for maior que a da sonda no mesmo mint. Cláusula de identidade: se o Δ aparecer
  cortando por `buys_1m ≥ 15` sozinho, o score é redundante com "teve compra" e o veredito é
  `descartar`.
- **Universo:** todo mint rastreado, sem filtro de sobrevivência.

## Priors contrários, com número

1. Wash trading ≥ 17 % e clusters de criadores 63 % ([[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]]):
   o insumo do score é fabricável pelo vendedor.
2. Vida mediana 0,01 dia: a maior parte das sondas sai por time stop com a moeda morta — e a marcação
   honesta de uma curva sem comprador é zero.
3. Pedágio de 3,44 % por ida e volta, cinco vezes por 0,05 SOL de exposição: a sonda paga o mesmo
   pedágio proporcional que uma aposta cheia e tem 1/5 do ganho.

## Previsões congeladas

- **P1 — a sonda abre.** ≥ 5 sondas/dia em dias com o radar vivo; `hype_no_tape_no_board` e
  `snipers_unknown` são as duas recusas mais frequentes da porta.
- **P2 — a escala quase não acontece.** ≤ 10 % das sondas viram perna 2; a mediana do tempo até a
  escala > 4 min depois do fill da sonda.
- **P3 — expectância da sonda:** entre −0,40 e −0,05 R (ponto **−0,20 R**); ≥ 60 % das saídas por
  `time_stop`/`trailing`. **Veredito previsto: `descartar`.**
- **P4 — perna 2 vs sonda:** a perna 2 tem R **maior** que a sonda no mesmo mint em ≥ 55 % dos pares
  (a linha filtra alguma coisa), mas a expectância da perna 2 sozinha fica ≤ 0 R.
- **P5 — a perda de fill:** mediana ≥ 5 % dos tokens entre decisão e fill (pior que os ≥ 2 % da EXP-M1).

## Regra de sucesso (congelada)

`validada` (sonda) exige as seis da EXP-M1 **e** Δ contra o controle sorteado > 0 sem identidade.
`validada` (perna 2) exige ainda expectância da perna 2 > expectância da sonda no mesmo mint, com IC por
blocos de dia acima de zero, ≥ 30 pares. Qualquer coisa menos: `descartar`, com o conjunto retirado
no mesmo dia; a página fica.

## Regras de morte

- **K1** — `hype_no_tape_no_board` em > 70 % das avaliações da porta: o instrumento (fita + board) não
  cobre a janela de 30 s–5 min; parar e consertar a cobertura.
- **K2** — > 30 % de censura. **K3** — fill sem fotografia posterior (impossível por construção).
- **K4** — expectância positiva vinda de < 3 mints. **K5** — uma perna 2 aberta sem sonda aberta ou
  com `parent_bet_id` nulo: bug de laço, invalida a coorte (o CHECK da `0026` torna o segundo caso
  irrepresentável).

## Avaliações (acrescentadas, nunca reescritas)

*Nenhuma.* A página nasce em 2026-09-12 com `result: nao-iniciado`, `evaluable: 0`, `days: 0`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde |
|---|---|---|---|
| — | — | — | — |

## Relacionadas

[[Experiments Index]] · [[03-TRADING/Meme/README|Meme (Trading)]] · [[EXP-M1-comprar-cedo-na-curva]] ·
[[EXP-M2-a-linha-manda]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] ·
[[KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos]] ·
[[KB-0088-o-teto-de-participacao-nos-motores-de-backtest]]

## Fontes

`packages/indicators/hunter_indicators/meme/{hype,rules}.py` · `packages/indicators/tests/unit/test_meme_hype.py`,
`test_meme_rules_lines.py` · `services/meme-worker/hunter_meme_worker/{proposals_scale,paper_fill,lab,lab_repo_lines}.py` ·
`services/meme-worker/tests/{test_proposals_scale,test_lab_lines}.py` · `infra/migrations/versions/0026_meme_lines.py` ·
`docs/DATABASE.md` §38 · `docs/plans/T4-MEME-RADAR.md` §T4.10 · `.claude/state/brief-T4.10-tracado-de-linhas-e-sonda-de-hype.md`.
