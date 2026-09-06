---
tags: [knowledge, backlog, estrategias]
updated: 2026-09-06
---

# Backlog de estratégias (candidatas ao Shadow Lab)

Fila ordenada de ideias que o conhecimento externo e as falhas observadas no Lab sugerem. **Nada aqui está ativo.** Uma candidata só vira experimento pelo caminho normal: brief → código de `Strategy` → revisão (quant cruzado, code-reviewer, Astra) → ativação auditada → `EXP-xxxx`. Dinheiro real não entra nesta página.

Status: `ideia` → `especificada` (parâmetros e regra fechados) → `sombra` (EXP aberto) → `avaliada` (100 outcomes E 30 dias) → `descartada` ou `promovida ao M4`.

**Antes de rodar qualquer linha desta tabela, ela entra em [[Registro de Tentativas]] com data de
início e fim.** Todas as candidatas abaixo nasceram da inspeção da coorte de 2026-09-06, então
**nenhuma pode ser confirmada nessa mesma população** — a confirmação exige janela futura reservada
([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

## Features do M2 disponíveis (verificado em 2026-09-06)

`return_1m/5m/15m/1h/4h` (+ `_live` de 1m/5m/15m/1h) · `distance_from_24h_high` ·
`distance_from_24h_low` · `atr_14_pct` · `momentum_15m` · `momentum_acceleration` ·
`breakout_strength_20` · `relative_volume_5m/15m/1h` · `volume_acceleration` · `funding_rate` ·
`funding_change_8h` · `open_interest_change_1h/4h` · `spread_pct` · `orderbook_imbalance_*` ·
`buy/sell_pressure_*` · `trade_velocity_*`. Nas velas: `volume` e `taker_buy_volume`.
**`return_24h` não existe.**

## Fila

| # | Candidata | Notas-fonte | Dado necessário (temos?) | Esforço | Edge esperado e evidência | Status |
|---|---|---|---|---|---|---|
| 1 | **Valor incremental da invalidação** — braços `INV-A/B/C/E` (atual · sem invalidação · dois fechamentos · buffer de 0,25 ATR) | [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] · [[KB-0005-stops-quando-eles-param-perdas]] | velas 1m/15m (sim) · ATR₀ congelado (sim) | médio (4 braços + replay) | **desconhecido.** Os −13,8430 R dos 24 invalidados são atribuição contábil, não efeito; o ganho exige contrafactual pós-saída | especificada |
| 2 | **Piso de custo** — `atr_pct_min = 0,0089` | [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] | `atr_pct_15m` da decisão (sim) | baixo | pressão de custo é **aritmética**: no piso atual 20 bps consomem 39,2% de 1 R efetivo. Que o piso maior melhore expectancy é hipótese | especificada, exige janela futura |
| 3 | **Diagnóstico por decil de ATR%** (análise, não variante) | [[KB-0007-atr-e-escala-por-volatilidade]] | `atr_pct_15m` persistido (sim) | baixo | nenhum edge prometido; descobre se a estratégia depende de faixa de volatilidade | especificada |
| 4 | **H1 timing + H2 atraso de execução** (`baseline + 60 s`) | [[KB-0009-o-efeito-do-quarto-de-hora]] | velas 1m com `taker_buy_volume` (existe; **cobertura a conferir**) | baixo (H1) / médio (H2) | artigo mede ~0,5 bps brutos em 10 s — serve para execução, não como estratégia | ideia |
| 5 | **Família de lookback 10/20/40** | [[KB-0003-rompimento-de-canal-e-data-snooping]] | velas 15m (sim) · 3 `strategy_version_id` | médio | canal breakout tem evidência histórica, muito enfraquecida por data snooping e custos | ideia |
| 6 | **Gate de tendência** `return_4h > 0` | [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] | `return_4h` (sim) | baixo | transferência de horizonte **não demonstrada**; risco alto de só encolher amostra | ideia |
| 7 | **Impulso recente excessivo** `momentum_15m ≤ 2,0` | [[KB-0002-momentum-e-reversao-em-cripto]] | `momentum_15m` (sim) | baixo | reversão intradiária em cripto existe na literatura, mas não neste recorte; `K=2` é escolha experimental | ideia |
| 8 | **Proximidade da máxima de 24 h** `distance_from_24h_high ≥ −0,005` | [[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] | `distance_from_24h_high` (existe, mas **não está no envelope da v1**) | baixo + medição prévia | George & Hwang é mensal e transversal em ações; extrapolação declarada | bloqueada pela medição de redundância |
| 9 | **Valor incremental do stop** — braços `STOP-A/B/C` | [[KB-0005-stops-quando-eles-param-perdas]] | velas 1m (sim) | médio | prêmio de parada depende do processo; passeio aleatório sozinho não implica que o stop custe | ideia |
| 10 | **Alvo assimétrico** (alvo > stop) | [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] | — | médio | separada de propósito: muda acertos, exposição, invalidações e funding ao mesmo tempo | ideia |

## Ordem em que eu testaria, e por quê

1. **#3 e #4-H1 primeiro** — são diagnósticos, custam quase nada, não gastam tentativa de estratégia
   e podem tornar várias candidatas desnecessárias. #4-H1 também audita o timing real das entradas.
2. **#1 (invalidação)** — é a única candidata cuja pergunta o dado já existente consegue atacar por
   **replay** sobre as mesmas entradas, sem esperar 30 dias, e é onde o Lab mostra o maior bloco de
   perda atribuída a uma regra nossa.
3. **#2 (piso de custo)** — a pressão é aritmética e não depende de amostra; o que depende de amostra
   é o efeito da correção, e por isso ela precisa de janela futura reservada.
4. **#8 (proximidade da máxima)** só depois da medição de redundância; se a retenção for ~100%, morre
   sem gastar dia de sombra.
5. **#5, #6, #7, #9, #10** por último: cada uma é uma tentativa a mais sobre a mesma população, e
   #5 sozinha já são três braços.

## Já em sombra
- `momentum_v1` → [[EXP-0001-momentum-v1]] (coortes `v1` e `v2`; `v2` difere só pelo `code_ref`)
- `volume_anomaly_v1` → [[EXP-0002-volume-anomaly-v1]]

## Relacionados

[[Index]] · [[Registro de Tentativas]] · [[Experiments Index]] · [[Strategy Performance]] ·
[[Features]] · [[Momentum Agent]]
