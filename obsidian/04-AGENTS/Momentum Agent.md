---
tags: [agentes, momentum, m4, shadow-lab]
updated: 2026-09-06
status: sombra
---

# Momentum Agent

## Status

**`sombra`** desde 2026-09-06 — e o status mudou porque a **prova operacional existe**, não porque
o desenho ficou pronto. S0 (migração `0002_shadow_lab`), S1 (estratégias) e S2
(`strategy-worker` em modo sombra) foram entregues e provados em `.claude/state/s2-proof.md`; a
versão foi ativada pelo script auditado (`momentum v1` em 2026-09-05 23:19:56 UTC, sucedida por
`v2` em 2026-09-06 02:08:13 UTC após a correção do `code_ref`); o worker está no ar contra a
Binance real. Contagens da primeira avaliação datada, `as_of = 2026-09-06T02:55:00Z`: **90 sinais
emitidos** (72 na coorte v1, 18 na v2), **57 acompanhamentos encerrados avaliáveis**, alvo, stop,
invalidação, `late:delay` e censura por gap todos observados sobre dado real. Números, SQL e
leitura em [[EXP-0001-momentum-v1]].

O que continua **não** existindo: carteira, ordem, posição, PnL. O agente completo, ligado a
portfolio e ao [[Risk Engine]], continua sendo Milestone 4. `active` numa `strategy_version` **não**
implica elegibilidade de execução.

## `momentum_v1` — parâmetros congelados pela decisão SHADOW

Estes valores são o **protocolo do experimento** [[EXP-0001-momentum-v1]]. Desde a primeira ativação
eles são imutáveis por *trigger* no banco: qualquer conteúdo diferente é uma versão nova, não uma
edição. `params_hash = 40e1688e6b5f6385674cb47a81e542b215b320eb5643a1375f6401f5c41ac2f3`
(`params_format = 1`), idêntico em v1 e v2 — o que separa as duas versões é só o `code_ref`.

| Item | Valor |
|---|---|
| Timeframe de decisão | 15 min (fechamentos distintos, UTC) |
| Timeframe de outcome | 1 min |
| Condição de entrada | `close` > máxima dos **20 fechamentos anteriores** de 15 min · `return_15m > 0` · volume relativo de 15 min ≥ **1,5×** a mediana das **96 barras anteriores** · ATR% entre **0,3%** e **5%** |
| ATR | Wilder(14) sobre 15 min, seed e âncora persistidos (mesma fórmula do M2, T2.2) |
| Stop | **1,5 ATR** abaixo da referência |
| Alvo (único no v0) | **1,5 ATR** acima da referência |
| Horizonte | **4 h** contadas da entrada |
| Direção | **LONG apenas** no v0 |

### "1 R nominal na referência" não é 1 R na entrada

Stop e alvo simétricos a 1,5 ATR **da barra de referência** valem 1 R *nominal*, medido na referência — nunca 1 R garantido na entrada, que acontece na abertura da barra seguinte. Exemplo da decisão, sem custos: referência 100, ATR 2 → stop 97, alvo 103; se a entrada sai em 101, o risco é 4 e o ganho até o alvo é 2, ou seja **0,5 R bruto**. Confundir os dois seria prometer uma relação risco/retorno que o experimento não tem.

## Como a entrada e a saída são medidas (perfil "por barras" v0)

Entrada hipotética no open da primeira barra de 1 min estritamente posterior a `decision_at`, com `entry_bar_open − source_bar_close ≤ 120 s` (senão `no_entry: late`); geometria revalidada com o preço de entrada (`stop < P_entry < target1`, senão `no_entry: geometry`); preços sintéticos sobre OHLC — `P_entry = open × (1 + 6/10000)`, `P_exit = base_exit × (1 − 6/10000)` — com spread total assumido de 2 bps, slippage de 5 bps por lado e taxa de 4 bps por lado **fora** dos preços. Saída resolve gap na abertura antes de toques intrabar; stop e alvo na mesma barra → **stop**. Custos são hipóteses declaradas do experimento, não tarifas verificadas.

## Especificação do agente do M4 (inalterada)

Features de suporte previstas (de [[Features]]): `momentum_15m`, `momentum_acceleration`, `ema_ratio_9_21`, `breakout_strength_20`, `relative_volume_5m/15m/1h`. Componente correspondente no Opportunity Engine: "Momentum" (peso padrão 0.20 em `opportunity_weights`).

A versão sombra **não** usa as features do M2: ela calcula o que precisa a partir das velas, localmente, e isso é parte do protocolo congelado — nomear os dois cálculos como se fossem a mesma feature esconderia uma mudança de método. Uma futura `v2` sobre as features do M2 é outra versão, comparada em paralelo no mesmo intervalo e universo.

## O que já existe e o que ainda não existe

**Existe:** decisões sombra sobre o mercado real, acompanhamentos hipotéticos por barras, outcomes
com `R_net` líquido dos custos assumidos, excursões honestas (nulas quando o OHLC não determina o
extremo) e cobertura contada. Escritor único desses outcomes é o `strategy-worker` ([[Workers]]).

**Não existe:** agente ligado a portfolio, ordem, posição, PnL, estatística de performance
consolidada (`agent_stats` continua vazia — [[Agent Performance]]) e qualquer forma de execução.
Nada aqui pode ordenar coisa alguma: os sinais do Lab carregam `purpose = research_only`, saem no
stream próprio `shadow.signals.emitted` e são recusados por teste pelo futuro proposal builder.

**Não leia os números do EXP-0001 como performance.** Com 1 dia distinto e menos de 100 outcomes
avaliáveis, o `Result` do experimento é obrigatoriamente `inconclusivo`. Ver
[[EXP-0001-momentum-v1]] e [[Strategy Performance]].

## Relacionadas

[[Agents Overview]] · [[Strategies]] · [[Volume Agent]] · [[Features]] · [[Experiments Index]] · [[EXP-0001-momentum-v1]] · [[Dialogos/SHADOW]] · [[Agent Performance]] · [[Strategy Performance]] · [[Workers]] · [[Risk Engine]]

## Fontes

`docs/plans/SHADOW-LAB.md` (decisão conjunta, seção "Desenho") · `.claude/state/dialogue-SHADOW.md` · `docs/PIPELINE.md` §5–6 · `docs/DATABASE.md` §6
