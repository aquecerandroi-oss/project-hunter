---
tags: [experimento, timeframe, custo, mean-reversion, momentum, populacao]
updated: 2026-09-09
status: em-andamento
owner: quant-engineer
exp: EXP-0021
strategy: "mean_reversion + momentum"
version: "mean_reversion v10 (viva) + momentum v10 (aposentada 2026-09-09T14:58:42Z, T3.56) + mean_reversion_h1_v1 (braço bloqueado)"
result: inconclusivo
evaluable: 306
days: 29
last_eval: "2026-09-09"
---

# EXP-0021 — o eixo de timeframe: o ATR% cresce 2,2× de 15 m para 1 h, o pedágio cai, e o ganho aparece na população

> **Arquivada pela Sexta-feira em 2026-09-09** a partir do rascunho do `quant-engineer`
> (`.claude/state/exp-drafts/EXP-0021-timeframe.md`, T3.54). Nada aqui é dinheiro real
> (`ENABLE_LIVE_TRADING=false`). 1 R = **48,33 USDT** (conversão declarada do Lab, [[KB-0076-por-que-perdemos-2026-09-08|KB-0076]]).
> Medições completas em `.claude/state/notes-T3.54.md`.
> **Acréscimo do arquivamento (T3.56, mesmo dia, 14:58:42Z = 11:58:42 BRT):** `momentum v10` (braço
> B2) foi **aposentada** pelo veredito medido do roster — 37,3 % das decisões de replay e 94,0 % das
> prospectivas furam o teto de stop do `paper_v1` (o mesmo achado do C5 abaixo), e a expectativa
> líquida continua negativa nas duas coortes. `mean_reversion v10` (braço B1) **continua ativa** — é
> a única versão da família `mean_reversion` com `n ≥ 30` e veredito `robusto` no roster de 9 versões
> que sobrou do T3.56. Nada nas seções abaixo foi reescrito; esta nota é append-only.

## Hipótese (congelada antes de derivar, brief T3.54)

> `custo_R = 0,0020 / (stop_atr × ATR%)` ([[KB-0076-por-que-perdemos-2026-09-08|KB-0076]], com a correção aritmética da notes-T3.40 §8b)
> e `ATR%` **cresce com o timeframe**. Se `ATR%(1h) ≈ 2–4 × ATR%(15m)` no mesmo mercado, decidir e
> parar em 1 h custa 2 a 4 vezes menos por R do que em 15 m, com a mesma geometria em múltiplos de
> ATR. Duas formas de testar: **(a)** mover só o ATR **de referência** para 1 h (parâmetro,
> derivação barata) e **(b)** decidir em barras de 1 h (módulo novo).

**O que a hipótese não promete, e o experimento tem de separar:** ATR maior é stop mais largo, e
stop mais largo muda a **dependência de caminho** da operação (a mesma ressalva do
[[EXP-0018-stop-largo|EXP-0018]]). O pedágio é aritmética; a vantagem é aposta sobre a distribuição.

## Medição prévia (a que decide se vale 2× ou 4×)

16 mercados com 31 dias completos de vela de 1 min (2026-08-08 → 2026-09-08), Wilder(14) congelado
sobre janelas rolantes de 97 barras em cada grade:

| grade | ATR% p50 (mediana dos 16) | `custo_R` com `stop_atr = 1` | razão vs 15 m |
|---|---:|---:|---:|
| 15 m | 0,5585 % | 0,3581 R | — |
| **1 h** | **1,2331 %** | **0,1622 R** | **2,208** |
| 4 h | 2,7031 % | 0,0740 R | 4,840 |

A razão 1h/15m fica entre **2,128 e 2,486** nos 16 mercados, sem exceção. **A alavanca vale 2×, não
4×** — e 2,21 contra os 2,0 do passeio aleatório (√4) é o excedente de reversão intrabarra.
Para 4× seria preciso ir a 4 h, e ali 6 dos 16 mercados já teriam `stop_atr = 1` acima do teto de
3 % da banda `paper_v1`.

## Braços

| braço | versão | pai | mudança | `params_hash` | estado |
|---|---|---|---|---|---|
| **A1** | `mean_reversion v9` | `v6` | `atr_timeframe` 15m → 1h | `9061c3971ebb` | **aposentada sem nenhuma decisão** |
| **A2** | `momentum v9` | `v8` | `atr_timeframe` 15m → 1h | `f0ba96e4260a` | **aposentada sem nenhuma decisão** |
| **B1** | `mean_reversion v10` | `v6` | `atr_timeframe` 1h + `atr_bars` 97 → 24 | `d4fcf66f9449` | **ativa** (roster de 9 do T3.56), 54 decisões |
| **B2** | `momentum v10` | `v8` | `atr_timeframe` 1h + `atr_bars` 97 → 24 | `a9f1cef0fa58` | **aposentada** (T3.56, 2026-09-09T14:58:42Z), 252 decisões |
| **C1** | `mean_reversion_h1_v1` | módulo novo | decide em barras de **1 h** | `985316dde262…` | **código pronto**; o botão que a bloqueava (`SHADOW_CONTEXT_MINUTES`) **subiu** no mesmo dia (T3.52, commit `d21a11d`) — ver §Pré-registro |

**A1 e A2 morreram na primeira barra, e o motivo é o achado operacional do experimento.**
`atr_bars = 97` numa grade de 1 h pede **5820 min** de velas de 1 min por avaliação, e o worker
corta o contexto em `SHADOW_CONTEXT_MINUTES = 1560` (26 h). Replay de 31 d × 4 mercados:
**5760 barras, 100 % `atr_warmup`, zero sinais.** Recibo:

```
{"state": "unavailable", "reason": "atr_warmup",
 "detail": {"window_start": "2026-08-31T23:00:00Z", "first_candle": "2026-09-03T22:00:00Z"}}
```

B1/B2 são as mesmas alavancas com a janela de ATR encolhida para as 24 barras que cabem. Preço
medido de encolher: o ATR% mediano cai para **0,905–0,975** do valor de 97 barras (p50 0,948),
porque o peso da semente sobe de 0,23 % para 51,3 %.

**C1 é o braço que a hipótese realmente pede** e ele exige `SHADOW_CONTEXT_MINUTES ≥ 5820`
(recomendado 5880) — um botão **compartilhado** por todas as versões vivas. Isso era decisão de
operação; deixou de ser bloqueio no mesmo dia (§Pré-registro).

## Portão de desenho (C1–C8)

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **REVISE** | O mecanismo de **custo** é aritmético e mediu-se em 16 mercados (2,208×, faixa 2,13–2,49). O de **vantagem** não existe: mover o ATR de referência não muda nenhuma condição de entrada, só a escala do stop e do alvo — e o [[EXP-0018-stop-largo|EXP-0018]] já mostrou que o bruto devolve o que a largura economiza. **Medido: devolveu 22 % (`mean_reversion`) e 42 % (`momentum`) da expectativa bruta.** O que sobrou de real foi **população** |
| C2 | Risco de sobreajuste | **PASS** | Zero limiares garimpados. `1h` é um valor do enum `Timeframe`, não um número escolhido; `atr_bars = 24` foi derivado do orçamento de contexto do worker (1560 min ÷ 60), não do resultado. Nenhuma condição de entrada nova. **Exceção declarada:** a lente de hora do dia (§lente) **é** melhor-de-24 e por isso está registrada como hipótese, não como braço |
| C3 | Adequação da amostra | **PASS em B1 e B2** | B1: **54 decisões em 16 dias** (o pai `v6` tinha 15 em 7 — `amostra_insuficiente`); B2: **252 em 29 dias** (pai 181 em 24). K1 (< 20) não dispara em nenhum. K3 (< 30 dias distintos) ainda dispara nos dois |
| C4 | Dependência de regime | **REVISE** | B1 é positiva nas duas metades (+0,2664 e +0,1452 R) e nos quatro recortes por mercado — o melhor comportamento de qualquer coorte de `mean_reversion` até hoje. B2 herda o padrão do pai: primeira metade ~zero (−0,0020), segunda metade −0,0668. Corte por regime horário (`market_regimes`, T3.43) ainda não feito nestas coortes |
| C5 | Calibração das saídas | **REJECT em B2, PASS em B1** | Banda `paper_v1` `[0,003; 0,03]` (`packages/risk-core/hunter_risk/limits.py:151-152`). Ninguém fura o piso. Teto: **B2 põe 37,3 % das decisões acima de 3 %** (94 de 252) contra 7,2 % do pai — `stop_atr = 3` sobre um ATR de 1 h. **B1 põe 11,1 %** (6 de 54), *abaixo* dos 20,0 % do pai `v6`. B2 não é candidata a `paper` sem baixar `stop_atr` ou o teto de ATR% |
| C6 | Concentração de risco | **PASS** | Tudo `research_only`, sem linha em `agents`, sem carteira. **`shadow_outbox` = 0 e `trade_proposals` = 0** para as duas coortes de replay, conferido. K6 não dispara: em B1 o pior recorte por mercado (`sem ETHUSDT`) ainda rende +0,1541 R |
| C7 | Realismo de execução | **PASS** | Mesmos custos assumidos e `max_entry_delay_s = 120 s` dos pais. `entrada_mais_1_barra`: −0,0117 R (B1) e +0,0008 R (B2), IC contendo zero nos dois. `custos_x2` derruba B1 para +0,0952 R / PF 1,56 — **ainda positivo**, que é a diferença material contra B2 (−0,1248 / PF 0,50) |
| C8 | Qualidade da invalidação | **PASS por ausência (B1) / herdado (B2)** | `mean_reversion` não tem invalidação estrutural (braço INV-B da [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo|KB-0006]]), então o eixo de timeframe não interage com o vício documentado no [[EXP-0018-stop-largo|EXP-0018]] C8. B2 herda a invalidação de `momentum_v1` inteira, sem mudança |

**Veredito do portão:** `REVISE` para B1 (C1 e C4 pedem mais janela; tudo o mais passa) e `REJECT`
para B2 (C5 reprova por larga margem e o estresse diz `sem_vantagem_na_base`). C1 (o módulo de 1 h)
fica **pré-registrado**, e o bloqueio de contexto foi removido no mesmo dia (§Pré-registro).
2026-09-09, quant-engineer. **Confirmado pelo roster do T3.56, no mesmo dia**: B2 foi aposentada
pelo veredito medido de C5 (o mesmo 37,3 % citado acima), B1 continua viva.

## Protocolo (congelado na ativação)

- **code_ref:** `hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f`
  (B1) e `hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c`
  (B2) — **idênticos aos dos pais**, conferidos nos seis dry-runs e nas quatro ativações
- **params_format:** `1`; `params_hash` na tabela de braços
- **Janela:** 2026-08-08 → 2026-09-08 (31 d), duas fatias contíguas por braço
- **Mercados:** `binance:` ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (os mesmos das coortes dos pais)
- **Coortes:** B1 `replay:71c76d86-ceb0-4d48-b3be-88c3c055061e`; B2 `replay:6eff77c0-566d-4a80-b580-0b0267b86f65`
- **`decision_lag_s` = 2, `workers` = 3, `errors` = 0** nas quatro corridas
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com
  `entry_bar_open − source_bar_close <= 120 s`
- **Custos assumidos:** spread 2 bps, slippage 5 bps/lado, fee 4 bps/lado — iguais aos dos pais

## Resultado medido (2026-09-09)

| versão | grade do ATR | n | dias | ATR% p50 | risco% p50 | `custo_R` médio | exp. bruta | exp. líquida | soma R | PF | > 3 % de stop |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `mean_reversion v6` (pai) | 15 m | 15 | 7 | 1,051 % | 1,631 % | 0,1075 | +0,3953 | **+0,2861** | +4,29 | 2,282 | 20,0 % |
| **`mean_reversion v10`** | **1 h** | **54** | 16 | 1,274 % | 1,990 % | **0,1038** | +0,3071 | **+0,2013** | **+10,87** | **2,496** | 11,1 % |
| `momentum v8` (pai) | 15 m | 181 | 24 | 0,516 % | 1,496 % | 0,1305 | +0,1013 | −0,0299 | −5,42 | 0,906 | 7,2 % |
| **`momentum v10`** | **1 h** | 252 | 29 | 0,836 % | 2,542 % | **0,0934** | +0,0584 | −0,0357 | −8,99 | 0,809 | **37,3 %** |

**Contraste transversal, bloco = dia UTC, 10 000 reamostragens, seed 20260909:**

```
mean_reversion v10 (+0,2013) − v6 (+0,2861) = -0,0847 R   IC95% [-0,7132; +0,2682]   NÃO distingue de zero
momentum       v10 (-0,0357) − v8 (-0,0299) = -0,0057 R   IC95% [-0,1323; +0,1105]   NÃO distingue de zero
```

**Estresse (`replay.stress`, `READ ONLY`, 2026-09-09T03:33Z):**

| coorte | veredito | base | `custos_x2` | 1ª metade | 2ª metade |
|---|---|---:|---:|---:|---:|
| `mean_reversion v10` | **robusto** | +0,2013 R · PF 2,496 | +0,0952 · PF 1,558 | +0,2664 | +0,1452 |
| `mean_reversion v6` (pai) | `amostra_insuficiente` (15/30) | +0,2861 R · PF 2,282 | +0,1716 · PF 1,709 | +0,2587 | +0,6692 (n=1) |
| `momentum v10` | `sem_vantagem_na_base` | −0,0357 R · PF 0,809 | −0,1248 · PF 0,500 | −0,0020 | −0,0668 |
| `momentum v8` (pai) | `sem_vantagem_na_base` | −0,0299 R · PF 0,906 | −0,1531 · PF 0,612 | +0,1913 | −0,1864 |

## As três conclusões

1. **O pedágio cai, mas muito menos do que a aritmética incondicional promete.** 2,21× vira ÷1,40
   (`momentum`) e ÷1,04 (`mean_reversion`) no pedágio medido **nas decisões** — porque o piso de
   ATR% já selecionava a cauda de volatilidade na grade de 15 m (ATR% condicional 1,05 %, não
   0,56 %). **Toda conta futura de pedágio precisa ser condicional à decisão.** Ressalva a
   acrescentar à [[KB-0076-por-que-perdemos-2026-09-08|KB-0076]].
2. **O que a economia compra é devolvido no bruto** — o mesmo padrão do [[EXP-0018-stop-largo|EXP-0018]]: −22 % e −42 %
   de expectativa bruta. Líquido por decisão: nada distinguível de zero.
3. **O ganho real é de amostra, não de expectativa.** O mesmo piso de ATR% quase não morde na grade
   de 1 h: `mean_reversion` foi de 15 para 54 decisões e passou de `amostra_insuficiente` para
   **`robusto`** — a primeira coorte da família com `n ≥ 30` e veredito positivo. É um resultado
   sobre **quanto o Lab consegue medir**, não sobre quanto ele ganha.

## A lente da abertura (`session_orb` revisitada)

- `session_orb v1` é negativa em três dos quatro baldes de 4 h em que decide (−0,15 / −0,33 /
  −0,30 R; o único positivo tem n = 1). Nenhuma hora do dia salva "operar a abertura". **`session_orb
  v1` foi aposentada no mesmo dia pelo T3.56** ([[EXP-0010-session-orb-faixa-de-abertura|EXP-0010]]).
- **A abertura de NY (13:00–14:59 UTC = 10:00–11:59 BRT) é negativa** nas três coortes que a tocam.
  A virada do dia (00:00 UTC) também.
- **A única hora positiva nas duas coortes de `momentum` é 12:00–12:59 UTC = 09:00 BRT:** +0,69 R
  (n = 6) no pai e **+0,70 R (n = 16, soma +11,26 R)** na variante de 1 h — mais do que o prejuízo
  total daquela coorte (−8,99 R).
- **Isso é melhor-de-24 com n ≤ 16: hipótese, não achado.** Vale como pré-registro de um
  experimento próprio (janela declarada antes de olhar), nunca como filtro acrescentado agora.

## Pré-registro para a próxima rodada (declarado antes de rodar)

1. **C1 (`mean_reversion_h1_v1`)** — o pré-requisito operacional deste item mudou **no mesmo dia**:
   o commit `d21a11d` (T3.52/b/c) tornou a janela de contexto uma propriedade **por versão**
   (`required_context_minutes`), com piso `SHADOW_CONTEXT_MINUTES = 1560` e teto
   `SHADOW_CONTEXT_MAX_MINUTES = 6000`, e a irmã de 1 h passa a pedir `context_minutes = 5880` — que
   cabe dentro do teto novo. O código (`eaebf8f`, T3.54) já existe com 35 testes. **Falta**: rodar
   `seed --only strategies`, ativar e replayar 31 d em 16 mercados (§2.1), bootstrap de blocos por
   dia contra `mean_reversion v10`. Predição: mesma expectativa por decisão, **mais** população.
2. **`momentum v10` com `stop_atr` menor** (1,5 em vez de 3), para tirar os 37,3 % de decisões
   acima da banda de stop — **superado pela aposentadoria da `momentum v10`** no T3.56; se a família
   `momentum` retomar o eixo de timeframe, é uma versão nova, não uma reativação desta.
3. **A janela das 12:00–12:59 UTC**, com a hora declarada antes: braço `momentum` que só decide
   naquela hora, 31 d, mesmos mercados. Predição honesta: **regride à média** — n = 16 num universo
   de 24 baldes é exatamente o que a sorte produz.

## Relacionadas

[[Experiments Index]] · [[KB-0076-por-que-perdemos-2026-09-08]] ·
[[EXP-0018-stop-largo]] · [[EXP-0020-regime-gate]] ·
[[EXP-0010-session-orb-faixa-de-abertura]] · [[mean_reversion]] · [[momentum]] ·
[[Strategy Backlog]] · [[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.54.md` · `.claude/state/notes-T3.56.md` ·
`infra/scripts/derive_variant.py` · `infra/scripts/activate_strategy_version.py` ·
`packages/core/hunter_core/strategies/mean_reversion_h1_v1.py`
