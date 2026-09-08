---
tags: [experimento, mean-reversion, custo]
updated: 2026-09-08
status: em-andamento
owner: quant-engineer
exp: EXP-0014
strategy: "mean_reversion"
version: "v2"
result: inconclusivo
evaluable: 17
days: 7
last_eval: "2026-09-08"
---

# EXP-0014 — mean_reversion com teto de pedágio 0,25 R (`atr_pct_min` 0,006 → 0,008)

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0014** é a
> próxima vaga livre lida em 2026-09-08T21:45Z; se outra tarefa tomar o número antes, renumerar.

## Hipótese (congelada)

O estresse da T3.36 mediu a `mean_reversion v1` **frágil a custos**: base +0,0938 R, `custos_x2`
−0,1213 R, com o IC 95 % do Δ inteiramente negativo. A identidade de custo
(`custo_R = 0,0020 / risco%`, [[KB-0076]] com a correção da T3.40: `risco%` é a **distância do
stop**, não o ATR%) diz que a única alavanca que move o pedágio é o piso de ATR%. Como a
`mean_reversion_v1` usa **`stop_atr = 1`**, aqui o ATR% **é** a distância do stop e a conta do brief
vale sem correção: `atr_pct_min = 0,008` ⇒ **pedágio ≤ 0,25 R**.

**O que a hipótese não promete:** teto de custo não fabrica vantagem ([[KB-0076]] item 9). E há um
efeito colateral que este EXP mede e nomeia: **um piso de ATR% é também um filtro de regime** — ele
não corta decisões ao acaso, corta os dias calmos.

## Portão de desenho (C1–C8) — congelado

Nenhum código novo: `mean_reversion_v1` congelada (`sha256:a970c9d9…`) com **um** parâmetro movido.

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **PASS com ressalva** | O mecanismo é aritmético, não preditivo: com `stop_atr = 1`, `custo_R = 0,0020 / ATR%`. Quem está do outro lado é a corretora, não um perdedor informado. A ressalva é a de sempre: despesa cortada não é vantagem criada |
| C2 | Risco de sobreajuste | **PASS com ressalva** | Um limiar, dois algarismos (`0,008`), origem declarada (o valor que faz o pedágio valer 0,25 R). **Mas**: a irmã EXP-0015 difere desta por **seis decisões e 0,55 R** — a distância entre as duas variantes é menor que o ruído da janela, e escolher entre elas por este replay seria garimpo |
| C3 | Adequação da amostra | **REVISE** | Previsto antes da corrida a partir da população do pai: 17 das 37 decisões têm ATR% ≥ 0,008 ⇒ corte de **54,1 %**, abaixo dos 70 % da regra do EXP-0006/[[KB-0008]]. Medido: exatamente 17 decisões, em **7** dias. `n = 17 < 30` ⇒ a passada de estresse recusa veredito |
| C4 | Dependência de regime | **REJECT declarado como achado, não como falha** | Medido nesta nota: as 17 decisões concentram-se em 2026-08-20…08-23 (13 decisões, +7,72 R) e sobram 4 decisões em 16 dias depois (−2,61 R). O piso de ATR% **é** um filtro de regime de volatilidade — o que o EXP mede é um episódio, não uma vantagem estacionária |
| C5 | Calibração das saídas | **PASS** | Stop 1 ATR com piso 0,008 ⇒ distância mínima do stop **0,8 % do preço**, dentro da banda `[0,003; 0,03]` do `paper_v1` (`limits.py:151-152`). O problema de C5 do [[EXP-0012]] não se repete. Ressalva medida: **2 das 17** decisões têm ATR% > 3 % (teto do preset) e somam −0,13 R — seriam recusadas pelo sizing numa linha `paper` |
| C6 | Concentração de risco | **PASS** | `research_only`, sem linha em `agents`, sem carteira; o teto reduz frequência, nunca a aumenta |
| C7 | Realismo de execução | **PASS com ressalva** | Mesmos custos assumidos do pai (2 bps de spread, 5 bps de slippage por lado, 4 bps de taxa por lado), mesmo `max_entry_delay_s = 120 s`. A ressalva é que **o teto é médio, não garantido**: a identidade prevê ≤ 0,25 R e a pior decisão desta coorte pagou **0,269 R**, porque o risco inicial efetivo varia entre 0,61 e 1,25 ATR (§CONCERNS da nota) |
| C8 | Qualidade da invalidação | **PASS por herança** | A `mean_reversion_v1` não emite invalidação nesta janela (0 de 37 no pai, 0 de 17 aqui); mexer nela seria outro experimento |

**Veredito do portão:** `PASS` com C3, C4, C5 e C7 registrados — 2026-09-08, quant-engineer.

## Protocolo (congelado na ativação)

- **Strategy:** `mean_reversion` / `v2`
- **code_ref:** `hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f` (idêntico ao do pai `v1`)
- **params_hash / params_format:** `ecd26dfc017a` / `1`
- **Parameters:** `{"fee_bps":"4","atr_bars":"97","stop_atr":"1","horizon_s":"14400","atr_period":"14","target_atr":"1.5","atr_pct_max":"0.05","atr_pct_min":"0.008","target2_atr":"2.5","zscore_bars":"20","slippage_bps":"5","atr_timeframe":"15m","trend_sma_bars":"20","base_confidence":"0.5","trend_timeframe":"1h","zscore_depth_min":"1","max_entry_delay_s":"120","assumed_spread_bps":"2"}`
- **Linhagem:** `variante de v1 | derived_from=v1 | overrides=atr_pct_min=0.008 | params_hash=ecd26dfc017a | T3.42 V1: coorte de pesquisa do teto de pedagio 0,25 R (atr_pct_min 0,008) aberta`
- **Timeframe de decisão / de outcome:** 15 min / 1 min, UTC
- **Agregação e ATR:** 1 m → 15 m só com barras UTC contíguas e finais; ATR = Wilder(14) de 15 min
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com `entry_bar_open − source_bar_close ≤ 120 s`
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra → **stop**; horizonte 4 h contado da entrada
- **Custos assumidos (hipóteses, não tarifas verificadas):** spread total 2 bps, slippage 5 bps por lado, taxa 4 bps por lado; funding assinado
- **Política de reentrada:** um acompanhamento `pending_entry|active` por `(strategy_version_id, market_id, cohort)`
- **Cohort:** `replay:d570b19a-f6e2-4312-86ed-9394b16ac81a` (retrospectiva) e `prospective` (aberta em **2026-09-08T21:24:26,306302Z** = 18:24:26 Brasília)
- **Controle predeclarado:** o **pai** `mean_reversion v1` na coorte `replay:d0f77894-1e04-454e-a49f-d9a98d894968`, pareado por `(mercado, barra de decisão)`
- **Universo elegível:** `markets.is_monitored` **de hoje** (limitação declarada do motor, `docs/PIPELINE.md` §6c)
- **Markets:** binance ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (replay); universo monitorado inteiro (prospectiva)
- **Janela de replay:** 2026-08-08 → 2026-09-08, em duas fatias contíguas

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — **REPLAY** (retrospectiva) — `read_at = 2026-09-08T21:37:59Z`

> **Rótulo obrigatório: REPLAY.** Mesma janela que gerou a hipótese ([[KB-0010]]). Não é evidência
> prospectiva e não decide ativação nenhuma sozinha.

**SQL usado:** `q10-pop.sql`, `q11-pareado.sql`, `q12-motivos.sql`, `q13-blocos.sql`,
`q21-identidade.sql`, `q24-dias.sql` em `.claude/state/exp-drafts/t342-sql/`.

**Cobertura (contagens completas):**

| Emitidos | Pendentes | Entradas | Não entradas | Ativos | Target | Stop | Expired | Invalidated | Censurados | Funding indisponível | Avaliáveis |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 17 | 0 | 17 | 0 | 0 | 7 | 6 | 4 | 0 | 0 | 0 | **17** |

**Livro-razão** (11 904 barras, 4 mercados, 31 dias, `--explain-ledger`): `unavailable` 448
(`warmup` 140, `atr_warmup` 308), `not_triggered` 11 426 (`no_uptrend_1h` 5 288,
`not_stretched` 5 424, `close_below_mid` 525, **`atr_out_of_range` 189**), `triggered` 30. As 189
recusas do porteiro de ATR estão **todas** abaixo do piso (máx 0,7967 %); nenhuma acima do teto de 5 %.

**Métricas:** expectancy bruta **+0,4686 R**, custo **0,1685 R**, expectancy líquida **+0,2998 R**,
soma **+5,10 R**, acerto **41,2 %**, PF líquido **1,7483**, PF bruto **2,4100**, **7** dias com
outcome avaliável. `PnL de carteira` e `Max Drawdown`: **não aplicáveis** (não há carteira no Shadow Lab).

**Os quatro grupos pareados (método T3.26):**

| Grupo | n | avaliáveis | bruta (R) | custo (R) | líquida (R) | soma R | dias |
|---|---:|---:|---:|---:|---:|---:|---:|
| pai pareado com a variante | 17 | 17 | +0,4686 | 0,1685 | **+0,2998** | +5,10 | 7 |
| pai **sem par** (eliminadas pelo piso) | 20 | 20 | +0,1956 | 0,2753 | **−0,0814** | −1,63 | 8 |
| variante pareada com o pai | 17 | 17 | +0,4686 | 0,1685 | +0,2998 | +5,10 | 7 |
| variante **sem par** no pai | **0** | 0 | — | — | — | — | — |

**Δ pareado decisão a decisão: 0,0000 R em 17 pares**, com `mesmo_risco_inicial = 17/17` e
`mesmo_motivo = 17/17`. A variante é **subconjunto exato** do pai: o piso não muda nenhuma operação,
só apaga 20 delas. Logo o estimando é a diferença **entre populações**, não entre pares.

**Contraste com bootstrap de blocos por dia** (11 dias, 10 000 reamostragens, semente 20260908,
`t342-blocos/blocos.py`): Δ = expectancy(variante) − expectancy(pai) = **+0,2060 R**,
**IC 95 % [−0,1089; +0,7276] — contém zero**.

**Passada de estresse** (`replay.stress`, `as_of 2026-09-08T21:30:42Z`, 17 entradas congeladas):
`custos_x2` **+0,1297 R / PF 1,2932** (Δ −0,1701, IC [−0,2197; −0,1292]) — **a fragilidade a custos
do pai desaparece**; `stop_x0.75/x1.25`, `alvo_x0.75/x1.25` e `entrada_mais_1_barra` todos com IC do
Δ contendo zero. **Veredito da passada: `amostra_insuficiente` (17 de 30)**.

- **Result:** **inconclusivo**
- **Conclusion:** o teto de pedágio faz **exatamente** o que a aritmética prometia — custo médio cai
  de 0,2263 R para 0,1685 R e o cenário `custos_x2`, que condenava o pai, fica positivo. Mas o ganho
  medido **não se distingue de zero** por bloco de dia, o `n` é metade do mínimo do estresse, e a
  distribuição no tempo denuncia o mecanismo: **13 das 17 decisões e +7,72 R estão em 2026-08-20…23**;
  nos 16 dias seguintes sobram 4 decisões e −2,61 R. Isto é um filtro de **regime**, não só de custo
- **Next Action:** deixar a coorte `prospective` (aberta em 2026-09-08T21:24:26Z) correr **30 dias**
  sobre o universo inteiro e reavaliar contra `mean_reversion v1` na mesma janela. **Não** promover a
  `paper`. Se o Δ prospectivo for negativo, `descartar`

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `atr_pct_min = 0,006` (`mean_reversion v1`, pai) | 2026-09-08 16:32:33Z | desenho original do [[EXP-0009]] | [[EXP-0009-mean-reversion-pullback-em-tendencia]] |
| `atr_pct_min = 0,008` (`v2`) | **2026-09-08 21:24:26Z** | pedágio ≤ 0,25 R | **este EXP** |
| `atr_pct_min = 0,010` (`v3`) | 2026-09-08 21:34:01Z | pedágio ≤ 0,20 R | [[EXP-0015-mean-reversion-teto-020]] |

## Relacionadas

[[EXP-0009-mean-reversion-pullback-em-tendencia]] · [[EXP-0015-mean-reversion-teto-020]] ·
[[EXP-0012-momentum-teto-de-pedagio]] · [[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0008]] ·
[[KB-0010]] · [[Experiments Index]] · [[Strategy Backlog]]

## Fontes

`.claude/state/notes-T3.42.md` (comandos, recibos e SQL verbatim) · `replay_runs` coortes
`replay:d570b19a-f6e2-4312-86ed-9394b16ac81a` e `replay:d0f77894-1e04-454e-a49f-d9a98d894968` ·
`system_events` (`strategy_version_variant_derived`, `strategy_version_activated`,
`replay_run_finished`) · livro-razão `--explain-ledger` de 11 904 linhas ·
`.claude/state/stress-mean-reversion-v1-2026-09-08.md`.
