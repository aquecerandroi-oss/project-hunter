---
tags: ["estrategia", "catalogo", "mean_reversion_m5"]
strategy: mean_reversion_m5
version: v1
purpose: research_only
status: "active — ativada em 2026-09-11T08:32:18Z (05:32 BRT), sem coorte de replay"
code_ref: "hunter_core.strategies.mean_reversion_m5_v1@sha256:f733467fedc529c661f53cf84653e9c5a514d86767471757ee43679af763734b"
params_hash: "5eaf76a7188078e773341b3e509d67509326107a80c5f0e2a1e781d5934fa6c7"
activated_at: "2026-09-11T08:32:18Z"
deprecated_at: ""
derived_from: ""
cohorts: []
exp: ["[[EXP-0028-mean-reversion-5-min]]", "[[EXP-0021-timeframe]]"]
updated: 2026-09-11
---
# mean_reversion_m5 v1 (research_only, ativada — sem replay)

## Parâmetros

Só três chaves diferem do contrato congelado da mãe (`mean_reversion_v1`), e são **os mesmos três
nomes** que [[mean_reversion_h1-v1]] moveu: o experimento tem um eixo só.

| Parâmetro | Mãe (`mean_reversion_v1`) | Irmã 1 h | **Esta versão** | Regra |
|---|---|---|---|---|
| `atr_timeframe` | `15m` | `1h` | **`5m`** | o ATR é medido **na própria grade de decisão**, nas três |
| `trend_timeframe` | `1h` | `4h` | **`15m`** | o **degrau seguinte** da grade. A mãe e a irmã de 1 h realizam 4×, mas `4 × 5 min = 20 min` não existe em `Timeframe` — 15 m é 3×, e é a **única liberdade** que esta derivação teve |
| `horizon_s` | `14400` (4 h) | `57600` (16 h) | **`4800`** (1 h 20) | 16 barras da grade, nas três |

Os outros **15** parâmetros são os da mãe, byte a byte — `zscore_bars` 20, `zscore_depth_min` 1,
`atr_period` 14, `atr_bars` 97, `atr_pct_min` 0,006, `atr_pct_max` 0,05, `stop_atr` 1,
`target_atr` 1,5, `target2_atr` 2,5, `trend_sma_bars` 20, `max_entry_delay_s` 120,
`base_confidence` 0,5 e os três custos assumidos (spread 2 bps, slippage 5 bps/lado, taxa 4 bps/lado).
**Nenhum limiar novo foi introduzido**, e nenhum número desta versão foi garimpado em dado de 5 min.

**Janela de contexto: 490 min**, declarada em `hunter_strategy_worker.context_budget.WINDOWS` pela
**mesma** entrada `_MEAN_REVERSION` que a mãe e a irmã de 1 h usam (as três são um caminho de código
só; o que difere são os parâmetros de timeframe que cada reivindicação lê da linha congelada). 490 é
**abaixo** do piso `SHADOW_CONTEXT_MINUTES = 1560`, logo o worker carrega os 1 560 de sempre e esta
versão **não encarece nenhuma outra** — o oposto da irmã de 1 h, que precisou de 5 880.

## Origem

**Changelog:** T3.84 passo 1 (código, commit `e517f69`) — módulo de fecho próprio
(`aggregate`, `base`, `canonical`, `envelope`, `indicators`, `mean_reversion_m5_v1`, `numeric`,
`schema`; a mãe **não** está no fecho, e este módulo não está no fecho de nenhuma das outras nove
versões), 39 testes próprios com valores escritos à mão, incluindo a prova de **não-antecipação**
(mutar a vela em formação nunca move o envelope) e o teste de digest do `code_ref`. Os digests das
versões vivas ficaram intocados, provado por teste.

**Semeada e ativada em 2026-09-11 (T3.84 passo 2), pelos scripts auditados:**

```
seed.py --only strategies --dry-run   ->  duas linhas NEW, e só elas
seed.py --only strategies --yes       ->  14 strategies / 14 strategy_versions
activate_strategy_version.py mean_reversion_m5 v1 --dry-run
   would activate ... (18 parameters)
activate_strategy_version.py mean_reversion_m5 v1
   activated mean_reversion_m5 v1 (purpose research_only) at 2026-09-11T08:32:18Z
```

O digest que o banco congelou é **idêntico** ao que a [[EXP-0028-mean-reversion-5-min]]
pré-registrou antes de qualquer escrita — a página descreve a versão que rodou.

## Avaliações

**Nenhuma sobre desfechos.** O replay de 90 d × 16 mercados **não rodou**: o portão do
`replay-worker` (T3.74b/T3.80) recusa toda corrida na VPS desde que o worker vivo foi shardado —
ele lê `hb:strategy:shadow` (ninguém escreve; os shards escrevem `hb:strategy:shadow:{i}of4`) e o
grupo `strategy-worker.shadow` (abandonado há ≥ 11,9 h, `lag = 50000`, enquanto os quatro grupos
vivos estão em `lag = 0`). Não se contorna um portão; o conserto está nomeado em
`.claude/state/notes-T3.84.md`.

**O que foi medido sem população** (2026-09-11, `as_of = 08:50:10Z`; detalhe e tabelas na
[[EXP-0028-mean-reversion-5-min]]):

| medida | previsto | medido (90 d, 16 mkt) |
|---|---:|---:|
| ATR%(5m) p50 | 0,298 % | **0,2714 %** (0,2984 % na janela de 31 d da T3.54) |
| fração de barras que passam `atr_pct_min` | "quase nada" | **8,85 %** (a mãe: 33,04 %) |
| ATR% p50 condicional ao portão | 0,60–0,75 % | **0,7875 %** |
| pedágio p50 por decisão | 0,267–0,333 R | **0,2540 R** (a mãe, mesma janela: 0,2454 R) |
| Δ de pedágio contra a mãe | +0,05 a +0,12 R | **+0,0086 R** |
| stops fora da faixa `[0,3 %; 3 %]` do `paper_v1` | — | **0,00 %** abaixo, **1,11 %** acima |

Leitura em uma frase: **a previsão de custo desta versão estava errada na direção que a desfavorecia**
— o piso de ATR% não encarece a filha, ele seleciona a cauda volátil da grade de 5 min, e o que
sobra paga quase o mesmo pedágio da mãe. O preço disso é raridade: **91,15 %** das barras de 5 min
ficam de fora, e em **11 dos 16 mercados** a mediana da grade está abaixo até do piso de risco de
0,3 %. A versão não escolhe volatilidade alta; ela é **definida** pelo piso.

## Replicação

não iniciada — depende da coorte de replay.

## Ligações

- Família: [[mean_reversion_m5]]
- Família-mãe (código-fonte, não herança): [[mean_reversion]] · Irmã de 1 h: [[mean_reversion_h1-v1]]
- Experimento: [[EXP-0028-mean-reversion-5-min]] · Eixo: [[EXP-0021-timeframe]]
- Priores de custo: [[KB-0076-por-que-perdemos-2026-09-08]] ·
  [[KB-0086-ic-positivo-nao-paga-o-pedagio-btc-perp-5-min]]

## Notas

`code_ref` e `params_hash` acima são **leituras do que o banco congelou na ativação** (a saída do
`activate_strategy_version.py`), não valores copiados do código. A versão segue `active` e
`research_only`: aposentá-la sem medição jogaria fora a única resposta que ainda falta.
