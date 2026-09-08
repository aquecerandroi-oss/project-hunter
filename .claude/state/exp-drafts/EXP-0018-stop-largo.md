---
tags: [experimento, momentum, mean-reversion, custo, geometria]
updated: 2026-09-08
status: em-andamento
owner: quant-engineer
exp: EXP-0018
strategy: "momentum + mean_reversion"
version: "momentum v7/v8, mean_reversion v4/v5/v6/v7"
result: inconclusivo
evaluable: 412
days: 24
last_eval: "2026-09-08"
---

# EXP-0018 — stop largo: dividir o pedágio pela largura do stop (seis braços, um contraste pareado cada)

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0018** é a
> próxima vaga livre lida em 2026-09-08T23:10Z; se outra tarefa tomar o número antes, renumerar.
> Nada aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`). 1 R = **48,33 USDT** (conversão declarada
> do Lab, [[KB-0076]]).

## Hipótese (congelada antes de derivar)

A identidade do pedágio ([[KB-0076]], com a correção da notes-T3.40 §8b) diz que

```
custo_R = 0,0020 / risco%        e        risco% = stop_atr × ATR%
```

Logo **multiplicar `stop_atr` por k divide o pedágio por k**. A hipótese testada é a que o Everton
formulou em 2026-09-08 19:35 ("precisamos começar a positivar as entradas; se necessário aumentar
valores de estratégia e ser mais arriscado"): **um stop mais largo (mais distância até o stop, menos
pedágio por R) inverte o sinal das versões que já estão perto de zero.**

**O que a hipótese explicitamente não promete, e o experimento tem de separar:** R é a **própria
distância até o stop**. Alargando o stop, o mesmo movimento de preço vale menos R — o bruto em R cai
pelo mesmo fator k. Se a distribuição de resultados fosse invariante à escala, `expectancy_net`
apenas encolheria por 1/k **sem trocar de sinal**. A única fonte possível de ganho é a
**dependência de caminho**: operações que morreriam no stop antigo sobrevivem, e operações que
alcançariam o alvo antigo não alcançam o novo. **É essa troca, e só ela, que o EXP mede.**

**Escala da mudança:** o stop e a escada inteira de alvos são multiplicados pelo **mesmo** fator, o
que preserva os múltiplos de R do pai (`momentum`: alvo × {1, 2, 3}; `mean_reversion`: 1,5 / 2,5) e
a ordem estrita que `constraints_table.py` exige. Nenhum outro parâmetro muda: piso e teto de ATR%,
horizonte, atraso máximo de entrada, custos assumidos e invalidação ficam **idênticos ao pai**.

## Braços (seis, todos `research_only`, todos com `code_ref` idêntico ao do pai)

| braço | versão | pai | `stop_atr` | escada | `params_hash` |
|---|---|---|---|---|---|
| **C1** | `momentum v7` | `momentum v6` | 1,5 → 2,25 | 4,5 / 9 / 13,5 | `5e456ae9eb5b` |
| **C2** | `momentum v8` | `momentum v6` | 1,5 → 3 | 6 / 12 / 18 | `69152dbc9173` |
| **A1** | `mean_reversion v4` | `mean_reversion v3` | 1 → 1,5 | 2,25 / 3,75 | `1b868c55ebed` |
| **A2** | `mean_reversion v5` | `mean_reversion v3` | 1 → 2 | 3 / 5 | `dd8b22cd30a0` |
| **B1** | `mean_reversion v6` | `mean_reversion v2` | 1 → 1,5 | 2,25 / 3,75 | `11ce73ed48b5` |
| **B2** | `mean_reversion v7` | `mean_reversion v2` | 1 → 2 | 3 / 5 | `6b6168718cf2` |

## Portão de desenho (C1–C8) — congelado

Nenhum código novo: `momentum_v1` (`sha256:ab2e0398…`) e `mean_reversion_v1` (`sha256:a970c9d9…`)
congeladas, com três ou quatro parâmetros de geometria movidos na mesma proporção.

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **REVISE** | O mecanismo do **custo** é aritmético e verificável (`custo_R = 0,0020 / risco%`, erro máximo medido 0,0034 R em 637 decisões). O mecanismo da **vantagem** não é: ele depende de a dependência de caminho ser favorável, e isso é uma aposta sobre a distribuição, não uma identidade. Medido: no `momentum`, 88 % a 105 % da economia é devolvida no bruto |
| C2 | Risco de sobreajuste | **PASS** | Dois fatores redondos (1,5 e 2), aplicados à escada inteira, sem nenhum limiar ajustado à série. Não há parâmetro livre garimpado: o único grau de liberdade é k, e os dois valores foram escritos no brief antes de qualquer corrida |
| C3 | Adequação da amostra | **REVISE, e REJECT nos quatro braços de `mean_reversion`** | `momentum v7`/`v8`: 184 e 181 decisões, 24 dias — população real. `mean_reversion v4`/`v5`/`v6`/`v7`: **10, 9, 15 e 14** decisões, em 4 e 7 dias. **K1 (< 20 decisões) dispara nos quatro** e o estresse recusou veredito com `amostra_insuficiente` nos quatro |
| C4 | Dependência de regime | **REJECT declarado como achado** | As duas metades da coorte, medidas: `momentum v8` +0,1913 R até 08-24 e −0,1864 R depois; `mean_reversion v6` tem **14 decisões na primeira metade e 1 na segunda**. O stop largo **não** muda o regime — ele herda o do pai, inclusive o vício de quatro dias de agosto que a T3.42 documentou |
| C5 | Calibração das saídas | **REJECT parcial — o achado mais importante deste EXP** | A banda de stop do `paper_v1` é `[0,003; 0,03]` do preço (`packages/risk-core/hunter_risk/limits.py:151-152`). Medido: `mean_reversion v5` põe **44,4 %** das decisões acima do teto, `v7` 28,6 %, `v4` 30,0 %, `v6` 20,0 %; `momentum v8` 7,2 %, `v7` 1,1 %. Os pais: **zero**. Numa linha `paper`, o Risk Engine recusaria o sizing de um quinto a quase metade das decisões destas versões |
| C6 | Concentração de risco | **PASS** | `research_only`, sem linha em `agents`, sem carteira. O stop largo **reduz** a frequência (ocupação de slot mais longa: 196 → 184 → 181 e 17 → 15 → 14) e reduz a exposição por operação com `risk_per_trade_pct` fixo |
| C7 | Realismo de execução | **PASS, e melhora** | Mesmos custos assumidos e mesmo `max_entry_delay_s = 120 s` do pai. Medido: `entrada_mais_1_barra` vale **−0,0004 R** (`v7`) e **−0,0009 R** (`v8`), contra −0,0253 R do pai — o stop largo compra robustez de execução. Ressalva: `stop_atr` **efetivo** varia de 2,27 a 3,99 num `stop_atr` declarado de 3,0 |
| C8 | Qualidade da invalidação | **REJECT no `momentum`, PASS por herança na `mean_reversion`** | A `momentum_v1` invalida em `close_below prior_max`, um nível **estrutural que não escala com o stop**. Consequência medida: as saídas por stop caem de 45 para 9, mas as invalidações sobem de 82 para **108** (59,7 % do livro) — a invalidação toma o espaço que o stop largo abriu. A `mean_reversion_v1` não invalida nunca (0 em todas as coortes) |

**Veredito do portão:** `REVISE` — C1, C3, C4, C5 e C8 registrados. 2026-09-08, quant-engineer.

## Protocolo (congelado na ativação)

- **Strategies / versions:** `momentum v7`, `momentum v8`, `mean_reversion v4`, `v5`, `v6`, `v7`
- **code_ref:** `hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c`
  (braços C) e `hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f`
  (braços A e B) — **idênticos aos dos pais**, conferidos no banco (`code_ref_igual_ao_pai = t`)
- **params_format:** `1`; `params_hash` na tabela de braços acima
- **Parâmetros alterados (e só eles):** `stop_atr`, `target_atr`, `target2_atr` e, no `momentum`,
  `target3_atr` — todos pelo mesmo fator. `atr_pct_min`, `atr_pct_max`, `horizon_s = 14400`,
  `max_entry_delay_s = 120`, `assumed_spread_bps = 2`, `slippage_bps = 5`, `fee_bps = 4`,
  `base_confidence = 0.5` e a invalidação **iguais ao pai**
- **Timeframe de decisão / de outcome:** 15 min / 1 min, UTC
- **Agregação e ATR:** 1 m → 15 m só com barras UTC contíguas e finais; ATR = Wilder(14) de 15 min,
  97 barras
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com
  `entry_bar_open − source_bar_close <= 120 s`
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra → **stop**;
  horizonte de 4 h contado da entrada
- **Custos assumidos (hipóteses, não tarifas verificadas):** spread total 2 bps, slippage 5 bps por
  lado, taxa 4 bps por lado; funding assinado
- **Política de reentrada:** um acompanhamento `pending_entry|active` por
  `(strategy_version_id, market_id, cohort)` — é ela que explica 196 → 184 e 17 → 15
- **Cohorts (retrospectivas):** `replay:293d98b7-90e1-4dfe-a604-60556f3b175e` (C1),
  `replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd` (C2), `replay:af24ee08-01cf-41ba-9b7a-1b43172bea28`
  (A1), `replay:66fa85cb-1d51-4330-a00b-00964b430ab4` (A2),
  `replay:9d99748b-21b9-44a7-8980-32c37b931e6e` (B1), `replay:264b227f-5bc0-4930-8c5b-2e883c0a858e` (B2)
- **Cohorts (prospectivas), abertas em:** C1 **2026-09-08T22:29:28,783999Z** (19:29:28 Brasília),
  C2 **22:29:33,049734Z** (19:29:33), A1 **22:38:37,842745Z** (19:38:37), A2 **22:38:41,887854Z**
  (19:38:41), B1 **22:38:46,022557Z** (19:38:46), B2 **22:38:49,950926Z** (19:38:49)
- **Controle predeclarado:** o **pai de cada braço**, pareado por `(mercado, barra de decisão)` —
  `replay:9a08835a-ae13-4c23-b521-734b2f60a3a2` (`momentum v6`),
  `replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4` (`mean_reversion v3`),
  `replay:d570b19a-f6e2-4312-86ed-9394b16ac81a` (`mean_reversion v2`)
- **Estimando:** Δ pareado de `expectancy_net` em R, com **IC 95 % por bootstrap de blocos de dia**
  (10 000 reamostragens, semente 20260908, `.claude/state/exp-drafts/t347-blocos/blocos_pareado.py`)
- **Universo elegível:** `markets.is_monitored` **de hoje** (limitação declarada do motor,
  `docs/PIPELINE.md` §6c)
- **Markets:** binance ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (replay); universo monitorado inteiro
  (prospectiva)
- **Janela de replay:** 2026-08-08 → 2026-09-08, em duas fatias contíguas

## Critérios de morte (K1–K5, régua do EXP-0017) — escritos antes da leitura

| # | Regra | Consequência |
|---|---|---|
| K1 | < 20 decisões na janela | ausência de população: **deprecar**; mais 30 dias não a criam |
| K2 | > 1 500 decisões | é um relógio, não uma condição |
| K3 | >= 100 avaliáveis **E** >= 30 dias distintos **E** expectancy **bruta** < 0 | **deprecar** |
| K4 | `unavailable` > 40 % das barras | bug de janela, não resultado |
| K5 | cobertura de `R_net` < 70 % | não mata; rebaixa o relato |
| K6 | >= 60 % das decisões num único mercado | não mata; obriga a decomposição por mercado |

## Avaliação de 2026-09-08 — **REPLAY** (retrospectiva) — `read_at = 2026-09-08T22:54:05Z`

> **Rótulo obrigatório: REPLAY.** Mesma janela que gerou a hipótese ([[KB-0010]]). Não é evidência
> prospectiva e não decide ativação nenhuma sozinha.

**SQL usado:** `2026-09-09-t347-q10-populacoes.sql`, `-q11-pareado.sql`, `-q12-dump-pareado.sql`,
`-q13-motivos.sql`, `-q16-cobertura-c5.sql`, `-q17-dias.sql` em `infra/scripts/sql/research/`.
Livro-razão: 12 arquivos `--explain-ledger` com `bars = lines` (11 904 linhas por variante).

### Cobertura

| coorte | emitidos | pendentes | entradas | ativos | alvo | stop | expirado | invalidado | censurados | sem funding | **avaliáveis** | dias |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 `momentum v7` | 184 | 0 | 184 | 0 | 27 | 19 | 39 | 99 | 0 | 1 | **183** | 24 |
| C2 `momentum v8` | 181 | 0 | 181 | 0 | 21 | 9 | 43 | 108 | 0 | 0 | **181** | 24 |
| A1 `mr v4` | 10 | 0 | 10 | 0 | 1 | 1 | 8 | 0 | 0 | 0 | **10** | 4 |
| A2 `mr v5` | 9 | 0 | 9 | 0 | 1 | 0 | 8 | 0 | 0 | 0 | **9** | 4 |
| B1 `mr v6` | 15 | 0 | 15 | 0 | 1 | 2 | 12 | 0 | 0 | 0 | **15** | 7 |
| B2 `mr v7` | 14 | 0 | 14 | 0 | 1 | 1 | 12 | 0 | 0 | 0 | **14** | 7 |

### Métricas e o contraste pré-registrado

| braço | pedágio pai → variante | bruto pai → variante | **líquido pai → variante** | Δ pareado (n) | **IC 95 % por bloco de dia** |
|---|---|---|---|---|---|
| C1 | 0,2554 → **0,1731** | 0,2028 → 0,1159 | −0,0513 → **−0,0568** | **−0,0040** (181) | [−0,1556; +0,1276] |
| C2 | 0,2554 → **0,1305** | 0,2028 → 0,1013 | −0,0513 → **−0,0299** | **+0,0161** (180) | [−0,1761; +0,1851] |
| A1 | 0,1452 → **0,0897** | 0,6587 → 0,4251 | +0,5131 → **+0,3337** | **+0,0472** (9) | [−0,1338; +0,2843] |
| A2 | 0,1452 → **0,0697** | 0,6587 → 0,5541 | +0,5131 → **+0,4830** | **+0,0572** (9) | [−0,3176; +0,1919] |
| B1 | 0,1685 → **0,1075** | 0,4686 → 0,3953 | +0,2998 → **+0,2861** | **+0,0547** (14) | [−0,2122; +0,5274] |
| B2 | 0,1685 → **0,0838** | 0,4686 → 0,4301 | +0,2998 → **+0,3450** | **+0,0275** (14) | [−0,3137; +0,4616] |

**Os seis intervalos contêm zero.** O pedágio caiu pelo fator pedido nos seis (÷1,48 a ÷2,08,
identidade conferida decisão a decisão com erro máximo de 0,0034 R).

**Quanto da economia sobrevive** (par a par: economia de pedágio menos perda no bruto):
C1 **−4,5 %**, C2 **12,2 %**, A1 88,2 %, A2 73,0 %, B1 **95,1 %**, B2 32,1 %.

### O mecanismo, medido (matriz de transição de `momentum v6 → v8`, 180 pares)

| motivo pai → variante | n | Δ soma (R) |
|---|---:|---:|
| `invalidated` → `invalidated` | 72 | **+22,81** |
| `stop` → `invalidated` | 31 | **+18,02** |
| `stop` → `expired` | 6 | +6,57 |
| `target` → `target` | 21 | +3,72 |
| `stop` → `stop` | 5 | +0,45 |
| `expired` → `expired` | 16 | −2,28 |
| `target` → `invalidated` | 4 | −8,46 |
| `target` → `stop` | 4 | −11,01 |
| `target` → `expired` | 21 | **−26,90** |
| **saldo** | 180 | **+2,90** |

41 stops salvos e 72 invalidações mais baratas em R, contra **29 ganhadores devolvidos**. É uma troca
de distribuição, não uma vantagem nova — e é a razão de o Δ ser +0,0161 R em vez dos +0,1249 R que a
economia de pedágio sozinha prometia.

### Estresse (`replay.stress`, `READ ONLY`)

| braço | `base` | `custos_x2` | `entrada_mais_1_barra` | 1ª metade | 2ª metade | **veredito** |
|---|---:|---:|---:|---:|---:|---|
| **pai `momentum v6`** | −0,0513 (PF 0,906) | −0,2798 (Δ −0,2285) | −0,0251 | +0,1763 | −0,2309 | `sem_vantagem_na_base` |
| C1 | −0,0568 (PF 0,859) | −0,2163 (Δ −0,1595) | −0,0004 | +0,1985 | −0,2422 | `sem_vantagem_na_base` |
| C2 | −0,0299 (PF 0,906) | −0,1531 (Δ −0,1232) | −0,0009 | +0,1913 | −0,1864 | `sem_vantagem_na_base` |
| A1 | +0,3337 (PF 2,479) | +0,2350 | −0,0944 | +0,8755 (3) | +0,1015 (7) | `amostra_insuficiente` (10/30) |
| A2 | +0,4830 (PF 21,18) | +0,4048 | −0,0838 | +0,6494 (3) | +0,3998 (6) | `amostra_insuficiente` (9/30) |
| B1 | +0,2861 (PF 2,282) | +0,1716 | −0,0235 | +0,2587 (14) | +0,6692 (1) | `amostra_insuficiente` (15/30) |
| B2 | +0,3450 (PF 4,761) | +0,2557 | −0,0251 | +0,3335 (13) | +0,4953 (1) | `amostra_insuficiente` (14/30) |

### K1–K6 aplicados

- **K1 dispara em A1, A2, B1 e B2** (10, 9, 15 e 14 decisões). Não dispara em C1/C2.
- K2, K4 (`unavailable` 3,8 %), K5 (cobertura 99,5 % a 100 %) e K6 (maior mercado 29,8 % em C2,
  40 % em B1) não disparam em nenhum braço.
- K3 não é avaliável: **24 dias distintos < 30** em C1/C2, e o bruto dos dois é positivo.

## Veredito

**Formal: `inconclusivo` nos seis braços** — nenhum IC exclui zero, e a régua prospectiva do
[[SHADOW-LAB]] §9 não deixa concluir por replay.

**Recomendação por braço:**

| braço | recomendação | razão de uma linha |
|---|---|---|
| C1 `momentum v7` | **descartar** | Δ pareado **negativo** (−0,0040 R); dominada pelo braço C2 em toda métrica |
| C2 `momentum v8` | **manter em pesquisa** — a única com população para julgar em 30 dias | Δ +0,0161 R com IC contendo zero; ainda perde (−0,0299 R, PF 0,906) |
| A1 `mean_reversion v4` | **descartar** | K1 (10 decisões), pior que a irmã A2 em tudo |
| A2 `mean_reversion v5` | **descartar** | K1 (9 decisões), 8 saídas por horizonte, 4 dias, **44 % fora da banda do `paper_v1`** |
| B1 `mean_reversion v6` | **manter em pesquisa — melhor candidata do eixo** | guarda **95 % da economia de pedágio**; K1 (15 decisões) e 20 % fora da banda do `paper_v1` |
| B2 `mean_reversion v7` | **manter em pesquisa com ressalva** | só 32 % da economia sobrevive; 28,6 % fora da banda do `paper_v1` |

**O que muda o veredito:** as seis coortes `prospective` abertas em 2026-09-08T22:29–22:38Z,
reavaliadas em **2026-10-08** contra os pais na **mesma** janela e sobre o universo inteiro. Se o Δ
prospectivo de C2 for negativo, o eixo "geometria" se esgota: piso de ATR% ([[EXP-0014]]/[[EXP-0015]]),
alvo mais longe ([[EXP-0013]]) e stop mais largo (este) terão sido medidos, os três mexendo no
pedágio e nenhum fabricando vantagem — e a conclusão volta a ser a da [[KB-0076]] item 10:
**falta vantagem na entrada, e nenhuma geometria a inventa.**

## A frase honesta para levar adiante

Com `risk_per_trade_pct` fixo em 0,25 %, **dobrar o stop corta a posição pela metade**. O prejuízo
por operação da `momentum` cai de **−2,48 para −1,45 USDT** — e cai porque a exposição caiu, não
porque a entrada melhorou. O stop largo é, em dinheiro, quase indistinguível de **operar menor**;
é uma alavanca de variância, não de sinal.
