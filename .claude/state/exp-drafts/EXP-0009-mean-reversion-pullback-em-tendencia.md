---
tags: [experimento, mean-reversion, shadow-lab, custos]
updated: 2026-09-08
status: proposto
owner: sexta-feira
exp: EXP-0009
strategy: mean_reversion
version: v1
result: inconclusivo
evaluable: 0
days: 0
last_eval: —
---

# EXP-0009 — recuo comprado dentro de tendência de 1 h (`mean_reversion_v1`)

> **RASCUNHO do quant-engineer (T3.33, 2026-09-08).** Para a Sexta-feira arquivar em
> `obsidian/05-EXPERIMENTS/EXP-0009-mean-reversion-pullback-em-tendencia.md` e ligar a partir de
> [[Strategy Backlog]], [[KB-0002-momentum-e-reversao-em-cripto]],
> [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]], [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]]
> e [[Experiments Index]]. Não editei `obsidian/**`.
>
> **Nada foi rodado. Nada foi ativado.** "Hipótese" e "Protocolo" **congelados**; avaliações
> **acrescentadas** abaixo, datadas. Brief: `.claude/state/brief-T3.33b-mean_reversion_v1.md`.

## Hipótese (congelada)

Num perpétuo USDT, um fechamento de 15 minutos **esticado para baixo** contra a própria média
recente (z-score dos 20 últimos fechamentos ≤ −1), **dentro** de uma tendência de alta de 1 hora
(fechamento da última hora completa acima da média de 20 horas), e numa barra que **fecha acima do
próprio meio**, tem expectancy líquida hipotética maior que zero com stop a 1,0 ATR e alvo a
1,5 ATR da referência.

**Por que esta versão existe, antes de por que ela poderia funcionar.** O Lab só sabe comprar força
(`momentum_v1` compra rompimento, `volume_anomaly_v1` compra pico de volume). Sem uma versão que
compre fraqueza, **toda perda medida se confunde com "o mercado caiu"**. Esta é a única do conjunto
que separa as duas coisas.

**Evidência externa, declarada como fraca:** a família vem de Connors & Alvarez (RSI(2)), medida em
ações e barras diárias; [[KB-0002-momentum-e-reversao-em-cripto]] registra reversão intradiária em
cripto na literatura, **mas não neste recorte**. A extrapolação de horizonte e de mercado é minha e
está declarada.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = mean_reversion`, versão `v1`, `purpose = research_only`.
  Módulo `packages/core/hunter_core/strategies/mean_reversion_v1.py`.
- **`code_ref`:** digest por versão, congelado na ativação; os digests de `momentum_v1`
  (`…ab2e0398…`) e `volume_anomaly_v1` (`…9b8c14ab…`) **não se movem** com esta entrega (teste).
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Regra de entrada (exata), na ordem:** elegibilidade → janela de sinal 15 m → janela de ATR
  (Wilder 14 × 15 m, `atr_bars = 97`, `rolling_window_v1`) → **porta de tendência de 1 h**
  (`close` da última hora **completa** > média dos 20 fechamentos horários anteriores; a hora em
  formação nunca entra) → **z-score** dos 20 fechamentos de 15 m, barra atual **incluída**, desvio
  populacional, `z ≤ −1` → **estabilização** (`close ≥ (high+low)/2`) → `0,006 ≤ ATR% ≤ 0,05`.
- **Geometria:** `stop = C − 1,0·ATR`, `alvo1 = C + 1,5·ATR`, alvo informativo `C + 2,5·ATR`.
- **Invalidação (exata): NENHUMA.** `invalidations = ()`. Stop, alvo e horizonte são a política de
  saída inteira — este é o braço `INV-B` de
  [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] nascido como versão própria. Uma entrada
  cuja tese é "o preço está **abaixo** do que deveria" não pode carregar uma regra que sai quando o
  preço cai mais.
- **Horizonte:** 4 h (14 400 s). Uma tese de reversão que não funcionou em dezesseis barras de 15 min
  está errada; e um horizonte maior aumentaria a chance de atravessar liquidação de funding e perder
  cobertura de `R_net` ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).
- **Custos assumidos:** spread total 2 bps, slippage 5 bps/lado, taxa 4 bps/lado,
  `max_entry_delay_s = 120`. Entrada/saída pelo perfil congelado do SHADOW-LAB §3.
- **Parâmetros congelados:** a tabela de `.claude/state/brief-T3.33b-mean_reversion_v1.md` §6, 18 chaves.
- **Universo:** replay de abertura em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT; `prospective` no universo
  elegível inteiro.

### Geometria — e a geometria que foi **recusada**, com o número

Este é o ponto onde a versão quase nasceu errada. A geometria "natural" da reversão à média é alvo
pequeno e stop largo. Com o custo assumido do Lab ela é **aritmeticamente inviável**:

| geometria | ATR% | R_net no alvo | R_net no stop | acerto de equilíbrio |
|---|---:|---:|---:|---:|
| **1,5/1,0 — recusada** | 0,003 | 0,1955 | −1,2736 | **0,8669** |
| **1,5/1,0 — recusada** | 0,010 | 0,5122 | −1,0888 | 0,6801 |
| **1,0/1,5 — escolhida** | 0,006 | 1,0592 | −1,2112 | **0,5335** |
| **1,0/1,5 — escolhida** | 0,008 | 1,1614 | −1,1619 | 0,5001 |

Nenhuma regra de reversão acerta 86,7 % das vezes. Invertendo a geometria e subindo o piso de ATR%
para 0,006, o equilíbrio cai para 53,4 % — que é uma taxa que uma reversão à média **pode**
plausivelmente ter, e por isso a hipótese é falsificável em vez de morta na origem.

### Premissas numéricas declaradas

`zscore_bars = 20` e `zscore_depth_min = 1` são convenção, não medida. `trend_sma_bars = 20` foi
escolhido porque 21 barras horárias **cabem** no orçamento de contexto de 26 h
(`SHADOW_CONTEXT_MINUTES = 1560`); uma média horária de 50 períodos **não cabe**, e dizer isso é mais
honesto que escolher 50 e ver toda barra voltar `warmup`. `atr_pct_min = 0,006` sai da tabela acima.

## O que falsifica esta hipótese

- **K1/K2/K3/K4/K5** de `.claude/state/notes-T3.33.md` §5.1. **K2 é o risco real aqui**: um portão de
  z ≤ −1 dispara com frequência, e passar de 1 500 decisões em 31 dias × 4 mercados significa que a
  profundidade é um relógio, não uma condição.
- **A porta de tendência tem de pagar por si.** A primeira avaliação precisa publicar a expectancy
  com e sem `no_uptrend_1h` sobre a mesma população de recuos, no formato pareado da
  [[EXP-0006-momentum-piso-de-custo]]. Se a porta não separar nada, ela só encolheu a amostra — que é
  exatamente o risco que a candidata #6 do [[Strategy Backlog]] já carregava.
- **Cobertura de gap.** Esta versão exige 1 260 minutos **contíguos** para a porta de 1 h. Se
  `trend_gap` for a maioria dos `unavailable`, a versão está medindo a nossa coleta, não o mercado.

## O que este experimento **não** prova

- **Não é o experimento de política de saída.** "Sem invalidação" aqui é uma escolha de desenho sobre
  uma população própria, não o contraste pareado `INV-A/B` que a
  [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] exige (esse é o `brief-T3.27`).
- **Multiplicidade:** uma de quatro versões abertas no mesmo dia
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **O replay de abertura não confirma nada** (mesma janela que gerou a hipótese); sai rotulado
  **REPLAY**.
- **Mistura de slot** com as outras versões, como sempre.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de <primeira data> — replay de abertura

<a preencher: coorte, janela, mercados, recibos, comandos exatos, cobertura completa, métricas com
denominador, decomposição com/sem porta de tendência, distribuição de `z` na decisão, `Result`,
`Next Action`>

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| geometria 1,5/1,0 | 2026-09-08 | recusada **antes** de rodar, por aritmética de custo (equilíbrio 86,7 % no piso) | esta página, seção Geometria |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[KB-0002-momentum-e-reversao-em-cripto]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.33.md` · `.claude/state/brief-T3.33b-mean_reversion_v1.md` ·
`infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
