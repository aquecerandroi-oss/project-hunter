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
last_eval: 2026-09-08 (REPLAY de abertura, T3.33e)
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

## Portão C1–C8 (`edge-strategy-reviewer`) — aplicado em 2026-09-08, antes de escrever o módulo

Acrescentado pela T3.33b. **Não altera Hipótese nem Protocolo** (congelados acima): registra o
veredito do portão sobre o rascunho como ele está, com o número de cada critério e a fórmula de
`.claude/skills/edge-strategy-reviewer/references/review_criteria.md`.

| # | Critério (peso) | Leitura sobre este EXP | Sev. | Nota |
|---|---|---|---|---|
| C1 | Edge Plausibility (20) | tese com mecanismo causal nomeado — fluxo impaciente empurra o preço além do valor em minutos, a tendência de 1 h dá a direção; termos de domínio (`reversion`, `momentum`, `breakout` ausente por opção) | pass | 80 |
| C2 | Overfitting Risk (20) | 5 condições de entrada + 1 porta de tendência = 6 ≤ 10 → 80; penalidade −10 por limiar com casa decimal em condição: `atr_pct_min = 0,006` e `atr_pct_max = 0,05` → −20 | pass | **60** |
| C3 | Sample Adequacy (15) | 252 ÷ 2 (a porta de 1 h é um filtro de regime declarado) × 0,8⁴ × 0,85 ≈ 44/ano ≥ 30 | pass | 80 |
| C4 | Regime Dependency (10) | o plano de validação congelado (K1–K5) **não** menciona regime | **warn** | 40 |
| C5 | Exit Calibration (10) | `stop_loss_pct = stop_atr × ATR% ≤ 1,0 × 0,05 = 0,05 ≤ 0,15`; `take_profit_rr = 1,5/1,0 = 1,5`, que **não** é `< 1,5` | pass | 80 |
| C6 | Risk Concentration (10) | não aplicável por construção (`research_only`, sem carteira); o perfil que existiria é `PAPER_V1`: `risk_per_trade_pct = 0,0025 ≤ 0,015` e `max_concurrent_positions = 5 ≤ 10` | pass | 80 |
| C7 | Execution Realism (10) | **não há filtro de volume nas condições**, deliberadamente: um portão de volume confundiria este eixo com o da `volume_anomaly_v1`. `export_ready_v1` não se aplica | **warn** | 50 |
| C8 | Invalidation Quality (5) | `invalidations = ()` — vazio | **fail** | 10 |

`confidence_score = (80·20 + 60·20 + 80·15 + 40·10 + 80·10 + 80·10 + 50·10 + 10·5)/100 = 65,5`.

**Veredito: `REVISE`** — não é `REJECT` (C1 e C2 não são `fail`) e não é `PASS` (há um `fail` e
65,5 < 70). As três instruções de revisão, e o que foi feito com cada uma:

1. **C4 — plano de validação sem regime.** Aceita e corrigida **na avaliação**, não no protocolo: a
   primeira avaliação publica a decomposição por regime de BTC e por decil de ATR%, no mesmo formato
   do item 5 da `notes-T3.32.md`. Com C4 = 80 o escore vai a **69,5** — ainda `REVISE`, porque C8
   sozinho já impede o `PASS`.
2. **C7 — sem filtro de volume.** **Recusada, com motivo.** Acrescentar um portão de volume mudaria
   a tabela de parâmetros congelada e faria esta versão medir o mesmo eixo da `volume_anomaly_v1`. A
   mitigação existente é declarada e é outra: o universo elegível (`markets.is_monitored`, top N por
   volume) e o piso de ATR% de 0,006. Fica como **warn aceito**, e a primeira avaliação publica a
   distribuição de `quote_volume` dos mercados que dispararam.
3. **C8 — sem invalidação.** **Recusada, e é o desenho.** Este é o braço `INV-B` de
   [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]]: uma entrada cuja tese é "o preço está
   abaixo do que deveria" não pode carregar uma regra que sai quando o preço cai mais. O portão está
   calibrado para estratégias que **têm** invalidação e pontua a ausência como defeito; aqui a
   ausência é a hipótese. **Divergência declarada, não conserto.**

**Limite do próprio portão, declarado:** C3 é uma fórmula de barra diária em ações (base 252). Esta
versão avalia 96 barras por dia por mercado; a leitura honesta da frequência aqui não é escassez de
amostra, é o **risco oposto** — K2 de `.claude/state/notes-T3.33.md` §5.1 (mais de 1 500 decisões em
31 dias × 4 mercados = a profundidade é um relógio, não uma condição). O portão não sabe disso.

### O teto de custo desta geometria (confirmação pedida pela `notes-T3.32.md`)

A T3.32 mediu, em dez populações, que `custo_R × risco%_do_preço = 0,0020` **constante**
(desvio ≤ 1,9×10⁻⁵) — aritmética de 20 bps de ida e volta, não estatística. Para esta geometria
(`stop = 1,0 ATR`, portanto `risco% = ATR%`), reproduzido em `Decimal` nesta tarefa:

| versão | risco% no piso | **teto de custo** | risco% no teto de ATR% | custo no teto |
|---|---:|---:|---:|---:|
| `mean_reversion_v1` (`stop_atr` 1,0, `atr_pct_min` 0,006) | 0,60 % | **0,3333 R** | 5,0 % | 0,0400 R |
| `momentum_v1` (`stop_atr` 1,5, `atr_pct_min` 0,003) | 0,45 % | 0,4444 R | — | — |
| `momentum v4` (piso 0,0089) | 1,335 % | 0,1498 R | — | — |
| `volume_anomaly v2` — **medido** no replay | 0,552 % | 0,6152 R | — | — |

**O teto de custo desta versão é 0,3333 R por operação**, no pior caso admissível (ATR% no piso).
Está **abaixo** do teto do `momentum_v1` (0,4444 R) apesar do stop mais apertado em ATR, e é isso que
o piso de ATR% em 0,006 compra. Não é uma previsão de custo médio: o custo médio depende da
distribuição de ATR% dos disparos, que só o replay diz.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — replay de abertura — **REPLAY, não coleta prospectiva** (T3.33e)

**Ativação (início do experimento, `Registro de Tentativas`):** 2026-09-08T16:32:33,947955Z
(13:32:33 BRT), `purpose = research_only`, `status = active`,
`code_ref = hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f`
— digest do dry-run igual ao exigido no brief antes de qualquer escrita. 18 parâmetros congelados, os
do `brief-T3.33b` §6.

**Coorte:** `replay:d0f77894-1e04-454e-a49f-d9a98d894968`, uma só, duas fatias contíguas
(2026-08-08→2026-08-23 e 2026-08-23→2026-09-08), ETHUSDT/SOLUSDT/XRPUSDT/DOGEUSDT, `--workers 3`,
`decision_lag_s = 2`.

**Recibos do livro-razão (`replay_runs`, `system_events[replay_engine]`, JSONL em `/tmp`):**

| fatia | barras | sinais* | desfechos* | seg | barras/s | estados | erros |
|---|---:|---:|---:|---:|---:|---|---:|
| 08-08 → 08-23 | 5 760 | 17 | 17 | 93,110 | 61,86 | `{"unavailable":448,"not_triggered":5284,"triggered":28}` | 0 |
| 08-23 → 09-08 | 6 144 | 37 | 37 | 104,545 | 58,77 | `{"not_triggered":6108,"triggered":36}` | 0 |

\* contagem **da coorte inteira** a cada corrida (não da fatia): a população final é **37 decisões**,
confirmada por `count(*)` em `agent_signals` (uma única coorte; primeira decisão 2026-08-20 03:45:02Z,
última 2026-09-06 15:15:02Z).

**Cobertura (denominador = 11 904 barras = 31 dias × 96 × 4 mercados):** `unavailable` 448 (3,76 %),
`not_triggered` 11 392 (95,70 %), `triggered` 64 (0,538 %), `rejected` 0, `ineligible` 0. Das 64
barras disparadas, **37** viraram decisão; as 27 restantes caíram na barreira de re-arme / regra "um
acompanhamento por (versão, mercado, coorte)".

**`atr_gap` / `trend_gap` — medidos por diferença, e o resultado é zero.** As razões de
`unavailable` não são persistidas pelo replay (só o estado). Mas a `breakout v1` rodou **as mesmas
11 904 barras** no mesmo dia e devolveu **exatamente 448** `unavailable` — e ela **não tem** porta de
1 h. Como o total não subiu nem uma barra ao acrescentar a exigência de 1 260 minutos contíguos,
**`trend_gap` = 0 nesta janela**: os 448 são o aquecimento comum do início (112 barras por mercado
≈ 28 h). A preocupação "a versão estaria medindo a nossa coleta" **não se confirmou**.

**Métricas (denominador explícito: 37 decisões, todas terminais e todas avaliáveis):**

| métrica | valor |
|---|---:|
| decisões | 37 (0,298 por mercado-dia) |
| avaliáveis / cobertura de `R_net` | 37 / **100,0 %** |
| dias distintos · mercados | 11 · 4 |
| expectancy **bruta** (`r_gross`) | **+0,3210 R** |
| expectancy ex-funding | +0,0948 R |
| expectancy **líquida** (`R_net`) | **+0,0938 R** |
| pedágio médio (`custo_R`) | 0,2263 R |
| soma `R_net` | +3,47 R |
| acerto (`target`) | 40,5 % |
| profit factor líquido · bruto | 1,186 · 1,800 |
| risco/preço médio | 1,050 % |

Identidade de custo da T3.32 verificada linha a linha: `custo_R × (risco/preço)` = 0,00200332 em
média (mín 0,00197308, máx 0,00202846) — desvio ≤ 2,9×10⁻⁵ de 0,0020.

**Por motivo de saída:** `stop` 16 (43,2 %, `R_net` −1,1682, soma −18,69) · `target` 15 (40,5 %,
+1,2732, +19,10) · `expired` 6 (16,2 %, +0,5104, +3,06). **O saldo inteiro está no horizonte:** alvo e
stop somam +0,41 R em 31 decisões; os +3,47 R da coorte são as seis saídas por tempo. Por isso 40,5 %
de acerto e expectancy positiva não contradizem o equilíbrio de 53,35 % da tabela congelada — aquela
conta supõe população binária stop/alvo.

**Profundidade de `z` na decisão (decomposição obrigatória):**

| faixa de z | n | exp. bruta R | exp. líquida R | soma R | acerto |
|---|---:|---:|---:|---:|---:|
| −1,25 < z ≤ −1,00 | 11 | +0,8808 | **+0,6879** | +7,57 | 63,6 % |
| −1,50 < z ≤ −1,25 | 5 | −0,2655 | −0,5027 | −2,51 | 20,0 % |
| −2,00 < z ≤ −1,50 | 11 | +0,3917 | +0,1379 | +1,52 | 45,5 % |
| z ≤ −2,00 | 10 | −0,0792 | −0,3101 | −3,10 | 20,0 % |

**Não há monotonicidade**, e o sinal aparente é o inverso do esperado: o balde mais raso — o que passa
raspando no `zscore_depth_min = 1` — carrega o resultado, e o mais fundo perde. Com n = 10–11 por
balde isto é ruído do tamanho do efeito; o que fica registrado é que "mais esticado" **não** se mostrou
melhor, e que `zscore_depth_min` continua sendo convenção declarada, não medida.

**Por faixa de ATR% (piso congelado 0,006):** `0,006–0,008` n = 20, líquida **−0,0814** ·
`0,008–0,010` n = 6, líquida **−0,0912** · `0,010–0,015` n = 6, +0,5212 · `≥ 0,015` n = 5, +0,5033.
**26 das 37 decisões (70,3 %) estão abaixo de ATR% 0,010 e são líquidas negativas com bruta positiva**
— é o pedágio (KB-0008/T3.32). Subir o piso é `v2`, não ajuste.

**Por mercado:** DOGE 12 (−1,11 R, 25,0 %) · ETH 6 (+1,28 R, 50,0 %) · SOL 8 (+2,79 R, 50,0 %) ·
XRP 11 (+0,51 R, 45,5 %). **Por dia:** 11 dias com decisão; 08-20 e 08-21 valem +11,4 R e os outros
nove somam −7,9 R.

**A porta de tendência não pôde ser paga: o braço "sem porta" não existe no banco.** Os recuos que a
porta rejeita saem `not_triggered` e não persistem nada, então a comparação pareada que esta página
exige precisa de uma irmã de parâmetro (`derive_variant.py`) com a porta desligada, replayada na mesma
janela. **Não foi feito**; fica declarado como pendência, não como resultado.

**Corte por regime de BTC: impossível** — `market_regimes` tem uma linha no banco, começando em
2026-09-06 18:18. Só o prospectivo poderá fazê-lo.

**Critérios de morte (congelados antes da corrida):**

| # | leitura | disparou? |
|---|---|---|
| K1 — < 20 decisões | 37 | não |
| K2 — > 1 500 decisões (o risco real desta versão) | 37 (0,298/mercado-dia) | não |
| K3 — ≥ 100 avaliáveis **e** ≥ 30 dias **e** bruta < 0 | 37 (< 100), 11 dias (< 30), bruta +0,3210 R | não |
| K4 — `unavailable` > 40 % | 3,76 % | não |
| K5 — cobertura de `R_net` < 70 % | 100 % | não |
| gap da porta de 1 h | `trend_gap` = 0 | não |

**Result: `inconclusivo`** — madura exige ≥ 100 avaliáveis **e** ≥ 30 dias distintos; temos 37 e 11.
**Next Action: seguir prospectivo** (coorte `prospective`, universo elegível inteiro) e reavaliar pela
régua de 30 dias. O saldo positivo desta janela é da mesma amostra que gerou a hipótese, vem de seis
saídas por tempo e de dois dias, e **não** é evidência.

Fonte integral (comandos, saídas verbatim, SQL e recibos): `.claude/state/notes-T3.33e.md`.

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
