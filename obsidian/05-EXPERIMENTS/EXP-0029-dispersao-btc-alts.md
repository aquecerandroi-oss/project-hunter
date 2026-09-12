---
tags: [experimento, dispersao, btc, alts, elegibilidade, populacao, mean-reversion, pre-registro]
updated: 2026-09-12
status: inviavel-populacao
owner: quant-engineer
exp: EXP-0029
strategy: "mean_reversion v10 (pai sem portão) + dois braços com portão"
version: "nenhuma derivada (v20 braço A e v21 braço B previstas; a checagem de população §2 falhou nos dois — v19 continua a última)"
result: inconclusivo
evaluable: 0
days: 0
last_eval: "2026-09-12"
---

# EXP-0029 — a discordância BTC × alts como estado: `dispersion_24h_v1` em 90 dias de replay

> **Pré-registro escrito em 2026-09-12 às 00:0x BRT, ANTES de derivar qualquer variante, ANTES de
> qualquer replay e ANTES de o backfill da série ter rodado.** A régua abaixo é a da T3.90,
> congelada; nada nesta página é dinheiro real (`ENABLE_LIVE_TRADING=false`) e nenhuma versão é
> promovida por ela.
>
> **Os campos marcados `‹backfill›` são placeholders deliberados.** Eles são a *distribuição
> medida* da série, que só existe depois de `infra/scripts/backfill_dispersion.py --days 90
> --apply` rodar na VPS — o orquestrador preenche, com a data e a hora da leitura, **antes** de
> derivar as variantes. Nenhuma faixa, nenhum limiar e nenhuma condição da régua depende do que eles
> vierem a dizer: as faixas dos braços estão fixadas aqui, agora, sem olhar para a distribuição.

## Hipótese (congelada)

**A diferença entre o retorno de 24 h da mediana das alts e o retorno de 24 h do BTC
(`dispersion_24h_v1`), medida no fechamento da barra, separa a expectancy das decisões de reversão
à média** — comprar reversão num dia em que as alts caíram 5 pontos a mais que o BTC não é a mesma
aposta que comprar reversão num dia em que elas subiram junto com ele.

Origem: **H-P18**, dos plantões de 06/09, 10/09 e 11/09 (`obsidian/00-INBOX/Hipoteses-do-plantao.md`).
Em **10/09** a mediana do retorno de 24 h dos 16 mercados do universo sombra era **−4,80 %** com o
BTC em **−1,50 %** (dispersão **−0,033**); em **11/09**, **−3,85 %** contra **−1,30 %** (dispersão
**−0,0255**). Duas leituras, o mesmo sinal: as alts caindo sozinhas.

**Isto é uma hipótese sobre dois dias**, e escolher o estado presente nos dois dias que chamaram
atenção para depois "confirmá-lo" é o erro que esta página existe para não cometer. Daí a régua, daí
o braço de falseamento ser o lado oposto do eixo, e daí a cláusula de identidade contra o regime
horário — que foi exatamente o que derrubou a EXP-0027.

## Os must-fix da Astra, e onde cada um está cumprido

| must-fix | onde |
|---|---|
| `r24h(t)` medido **no corte da decisão** | o portão lê a linha cujo `end_time` é **exatamente** `source_bar_close`; a linha do minuto `T` dobra só velas com `open_time + 1 min <= T` (`endpoint_open_times`) |
| **congelado por aposta** | a linha é imutável (`0020` não dá `UPDATE`/`DELETE` a ninguém) e o id dela vai no envelope de cada decisão; o replay lê a mesma linha que a faixa viva leria |
| **quatro células** | os dois braços pré-registrados (A e B) mais as duas células descritivas sem braço — `[−0,03; 0,00)` e tudo fora de ±0,10 —, medidas na leitura descritiva abaixo e **sem** variante derivada |
| **contraste suave dentro do BTC** | a referência é o próprio BTC e a dispersão é uma *diferença*: um dia em que tudo cai junto (BTC −4 %, alts −4,2 %) fica em `[−0,03; 0,00)` e **não** entra no braço A. O braço A é a discordância, não a queda |
| **sem antecipação** | duas velas por mercado, instantes exatos, nada que abra no corte; provado em `packages/indicators/tests/unit/test_dispersion_series.py` e, pela via do banco, em `services/scanner-worker/tests/test_dispersion_job.py` |

## Por que uma série nova e não `breadth_v2`

A EXP-0027 fechou com a frase que abre esta: `compute_breadth` compara **o próprio** fechamento de
cada mercado em duas pontas de 5 min com `<` estrito — sem mercado de referência, sem horizonte de
24 h, sem comparação de *retornos*. H-P18 precisa dos três. Reinterpretar a amplitude como dispersão
seria o mesmo erro que `hunter_indicators.breadth` e `hunter_indicators.regime.breadth` existem
separados para evitar.

| | `breadth_v2` (T3.88) | `dispersion_24h_v1` (T3.90) |
|---|---|---|
| pergunta | quantos mercados caíram | **quão longe do BTC** a mediana das alts ficou |
| horizonte | 5 min | **24 h** |
| referência | nenhuma | **`BTCUSDT`, dentro do fold** |
| valor | fração em `[0, 1]` | diferença **com sinal**, negativa na discordância |
| universo | os 16 com ≥ 90 d de velas de 1 min | **o mesmo** (`hunter_core.universe`, regra única) |
| tabela | `market_breadth` (`0019`) | `market_dispersion` (`0020`, irmã, mesmas convenções) |

O universo ser **o mesmo** é o que faz esta série nascer com passado: é a população de onde sai toda
coorte de replay, e é sobre ela que a EXP-0025 mediu o pai.

## Os braços

Pai: **`mean_reversion v10`** sem portão — coorte `replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3`,
**798 decisões terminais em 89 dias × 16 mercados**, expectativa ex-funding **−0,0293 R**, PF 0,910,
IC 95 % [−0,1336; +0,0728] (indistinguível de zero). Decisão em 15 min, outcome em 1 min, horizonte
de 4 h.

| braço | versão | política | o que afirma | previsão registrada |
|---|---|---|---|---|
| **A** (discordância) | `v20` | `dispersion=-0.10--0.03` | a reversão compradora vive onde as alts caíram **bem abaixo** do BTC | Δ > 0 contra o pai, e **< +0,05 R** (isto é: **A não aprova**) |
| **B** (falseamento) | `v21` | `dispersion=0.00-0.10` | concordância / alts **acima** do BTC é o outro extremo do eixo | Δ ≤ 0 |

Corpo gravado, byte a byte:
`{"dispersion": {"min": "-0.10", "max": "-0.03", "version": "dispersion_24h_v1"}}` (A) e
`{"dispersion": {"min": "0.00", "max": "0.10", "version": "dispersion_24h_v1"}}` (B).

As faixas são **meia-abertas no topo** (`min <= valor < max`) e estão escritas aqui antes de
qualquer leitura desta série. Elas **não ladrilham** o eixo, e isso é deliberado e declarado: ficam
**sem braço** a faixa `[−0,03; 0,00)` (a queda conjunta, o "contraste suave dentro do BTC" da
Astra), a faixa `[−1; −0,10)` (a discordância extrema, que a leitura descritiva vai dizer se
existe) e tudo acima de `+0,10`. Uma faixa que ninguém pré-registrou não ganha braço — a lição que a
EXP-0027 pagou com o degrau `1,0000` órfão.

**Se B aprovar e A não**, a hipótese "a vantagem vive na discordância" está **refutada**; o que
sobra nasce como candidata da EXP seguinte, com pré-registro próprio, e **não** pode ser declarada
vencedora aqui.

## Regra de sucesso — congelada, a mesma da EXP-0026/0027/0028

A quantidade que a hipótese afirma é **condicional contra incondicional**:

> **Δ = média de `r_ex_funding` das decisões do braço − média de `r_ex_funding` das decisões do pai
> na janela inteira**, por natureza **não pareada** (as duas populações não compartilham barras),
> com IC 95 % por **bootstrap de blocos de dia inteiro, não pareado**
> (`.claude/state/exp-drafts/t362b/blocos90.py`, 20 000 reamostragens, semente **20260913**).

A semente é diferente da 20260912 da EXP-0027 de propósito: uma semente por experimento, para que
duas leituras nunca compartilhem o mesmo caminho de reamostragem.

**Aprova** o braço que cumprir **todas**:

1. Δ ≥ **+0,05 R** e o IC 95 % por blocos de dia **acima de zero**;
2. **n ≥ 100** desfechos avaliáveis **e** ≥ 30 dias distintos;
3. média de `r_ex_funding` **positiva em ao menos 2 das 3 janelas** de 30 dias;
4. **leave-one-market-out nunca negativo** (16 reajustes, um por mercado retirado);
5. o Δ **pareado** por (mercado, barra) sobre as barras elegíveis compartilhadas fica **dentro de
   ±0,02 R de zero** — não como prova de vantagem, e sim como **prova de que o portão é só um
   portão** (`docs/PIPELINE.md` §4b item 11: `INELIGIBLE` não arma a barreira, logo a filha pode
   abrir um episódio numa barra que o pai nunca considerou; um Δ pareado grande só poderia ser essa
   divergência de slot ou bug). Na EXP-0027 esta condição saiu **0,0000 R** nos dois braços, que é o
   comportamento esperado do instrumento.

**Qualquer coisa a menos = `descartar`**, com aposentadoria pela via auditada
(`activate_strategy_version.py --deprecate`) **no mesmo dia**. Um braço mudo (n < 100) é `descartar
por população`, nunca "negativo".

**Cláusula de identidade (controle de falsificação) — a que matou a EXP-0027.** A mesma leitura é
repetida com as decisões do pai cortadas por `regime_hourly_v1` em vez de `dispersion_24h_v1`
(partição dentro do pai: permitido − proibido, pareada por dia, rótulos permitidos = os que dominam
≥ 50 % das decisões do braço). Se o corte por regime produzir Δ **igual ou maior**,
`dispersion_24h_v1` **não é estado novo** — é o regime horário do BTC com outro nome — e o veredito
é `descartar` mesmo que os cinco itens passem. Prior honesto, escrito antes: a dispersão é
**construída** a partir do BTC, então esta cláusula é mais provável de disparar aqui do que foi na
EXP-0027, e é por isso que ela é a primeira coisa a medir depois da condição 1.

**K4 e K5.** K4 (`unavailable`) **não é mensurável num braço com portão** (`docs/PIPELINE.md` §4b
item 12): é lido no **pai**, na mesma janela (0,93 % na coorte de 90 d), e a fração `ineligible` da
filha é reportada como número próprio. K5: a cobertura de `R_net` da coorte de 90 d da `v10` é
**37,59 %** (300 de 798), então o eixo primário é **`r_ex_funding`** (798 de 798) e **toda tabela
declara o eixo**.

## Distribuição de `dispersion_24h_v1` — medida em 2026-09-12 às 04:40–04:41 BRT (07:40–07:41 UTC), antes de derivar

Preencher **antes** de derivar, com SQL somente-leitura sobre a série já populada
(`infra/scripts/sql/research/2026-09-12-t390-*.sql`), e com a hora BRT da leitura:

> **Preenchido em 2026-09-12 às 04:40–04:41 BRT (T3.91, quant-engineer).** Os `t390-*.sql` previstos
> acima não chegaram a existir; a leitura é a de
> `infra/scripts/sql/research/2026-09-12-t391-q01-dispersao-distribuicao.sql` (série),
> `-q02-dispersao-nas-barras-de-15m.sql` (barras de 15 min) e `-q03-celulas-do-pai.sql` (pai),
> todas `repeatable read read only`; saída verbatim em `.claude/state/notes-T3.91.md`. A série
> **começa em 2026-06-16 00:00Z** (o backfill `--days 90` de 04:33 BRT dobrou 88 dias, 06-16 → 09-11;
> a faixa viva grava desde 2026-09-12 00:00Z), e nenhuma faixa desta página foi tocada.

| campo | valor |
|---|---|
| linhas na série / usáveis | **126 911 / 126 911** (126 720 do backfill = 88 dias × 1 440, mais 191 da faixa viva de 12/09; **zero** inutilizáveis) |
| janela coberta (`min(end_time)` → `max(end_time)`) | **2026-06-16 00:00Z → 2026-09-12 07:40Z** (a faixa viva continua) |
| dias com cobertura ≥ 80 % (de 90) | **88 de 88 dias completos** (06-16 → 09-11), cobertura mínima **1,0000** (16 de 16) em **todos** os 126 911 minutos; o 89.º dia (12/09) é o dia vivo parcial, também 16/16 |
| linhas `insufficient_coverage` / `btc_missing` | **0 / 0** |
| mínimo / p05 / p10 / p25 | **−0,083542 / −0,021014 / −0,016014 / −0,008182** |
| **p50** | **−0,001284** |
| p75 / p90 / p95 / máximo | **+0,005167 / +0,012107 / +0,018892 / +0,131334** |
| média | **−0,001125** (desvio-padrão 0,013216; histograma em degraus de 0,01: `[−0,01; 0)` 35,33 %, `[0; 0,01)` 31,52 %, `[−0,02; −0,01)` 14,20 %, `[0,01; 0,02)` 8,54 %, `[−0,03; −0,02)` 4,39 % — unimodal, estreita, centrada perto de zero) |

**Share de barras elegíveis por braço** — o denominador honesto são os **fechamentos de 15 min** da
janela de replay (a grade de decisão da `v10`), não todos os minutos:

| célula | barras de 15 min | share |
|---|---|---|
| **A** `[−0,10; −0,03)` | **124** | **1,48 %** |
| **B** `[0,00; +0,10)` | **3 746** | **44,85 %** |
| sem braço `[−0,03; 0,00)` (queda conjunta) | 4 475 | 53,58 % |
| sem braço `< −0,10` (discordância extrema) | 0 | 0,00 % |
| sem braço `>= +0,10` | 7 | 0,08 % |
| sem linha usável | 0 | 0,00 % |

Denominador: **8 352 fechamentos de 15 min** em (2026-06-16 00:00Z; 2026-09-11 00:00Z] — 87 dias × 96,
a janela de replay que o protocolo abaixo fixa (medido às 04:40 BRT). Dias distintos com **ao menos
uma** barra de 15 min na célula: **A = 9 de 88** (06-23: 4 barras · 08-20: 1 · 08-21: 4 · 08-23: 7 ·
08-24: 28 · 08-25: 9 · 08-26: 14 · 09-09: 2 · **09-10: 55** — o dia que motivou a hipótese é 44 % do
braço), **B = 75 de 88**. As 7 barras `>= +0,10` são todas de 08-22.

Por janela de 30 dias (a régua exige as três; J1 06-16→07-16, J2 07-16→08-15, J3 08-15→09-11 com
27 d): A **0,14 % / 0,00 % / 4,63 %** (4 / 0 / 120 barras) · B **41,28 % / 42,67 % / 51,23 %**
(1 189 / 1 229 / 1 328 barras). **O braço A não tem uma barra sequer em J2** e 120 das suas 124
barras estão em J3.

**Tercis congelados (só para a leitura descritiva).** Calibrados sobre as linhas **usáveis** de
**2026-06-13 → 2026-07-31**, todos os minutos, e **nunca recalculados**: `t1 = −0,005913` e
`t2 = +0,001660` (n = **66 240**). A janela de calibração é **descartada** da leitura descritiva,
que é medida sobre as decisões de 2026-08-01 em diante. Se a série começar depois de 06-13 (como a
`breadth_v2` começou em 06-14), a calibração efetiva é o que existir e **fica escrito aqui**, com o
n exato: **a série começa em 2026-06-16 00:00Z, então a calibração efetiva é 2026-06-16 00:00Z →
2026-07-31 23:59Z, 46 dias × 1 440 = os 66 240 exatos** (medido às 04:40 BRT).

## Previsões numéricas registradas antes da primeira derivação

Elas podem estar erradas e é para isso que estão aqui.

1. **Distribuição.** A dispersão é uma diferença de dois retornos de 24 h de ativos correlacionados,
   então espero uma distribuição **unimodal e centrada perto de zero** — mediana entre **−0,01 e
   +0,01** — e não em U como a da amplitude (aquela tinha 17 degraus sobre 16 mercados; esta é
   contínua). Previsão de cauda: **menos de 15 %** dos minutos abaixo de −0,03.
2. **População.** Braço A entre **10 % e 30 %** das barras de 15 min; braço B entre **20 % e 40 %**.
   Se A ficar abaixo de 100 desfechos projetados, o braço morre por população e isso é `descartar`,
   não "negativo".
3. **Direção.** Δ do braço **A positivo mas pequeno (< +0,05 R)** e Δ do braço **B negativo**, isto
   é: **previsão de que nenhum dos dois aprova**. O prior vem da EXP-0025 (a família é −0,0293 R em
   90 d e nenhum corte de contexto a salvou até agora) e da EXP-0027 (o corte por amplitude não
   moveu nada além do que o regime já movia).
4. **Cláusula de identidade.** Espero que ela **dispare** — a dispersão é construída a partir do BTC
   e o regime horário é do BTC. Se ela não disparar, é o achado mais interessante desta página.
5. **`dispersion_unavailable`** abaixo de **1 %** das barras da janela de replay, se o backfill
   cobrir os 89 dias dobráveis. Acima disso, a leitura é sobre cobertura e não sobre a hipótese.

## Leitura descritiva por célula — medida em 2026-09-12 às 04:41 BRT (07:41 UTC), sobre as decisões do PAI antes do replay

Juntando cada uma das 798 decisões de `replay:c7d138eb…` à linha de `dispersion_24h_v1` do seu
`source_bar_close`. **Não é o resultado do experimento** — a população dos braços difere pela
divergência de máquina de estados do slot (`docs/PIPELINE.md` §4b item 11) — e **não move a régua**:

| célula | n | dias | `r_ex_funding` médio | soma R |
|---|---|---|---|---|
| **A** `[−0,10; −0,03)` | **7** | **2** (08-24 e 08-25) | −0,0261 | −0,1826 |
| **B** `[0,00; +0,10)` | **414** | 61 | **+0,0203** | +8,4233 |
| `[−0,03; 0,00)` (sem braço) | 342 | 69 | **−0,0721** | −24,6663 |
| `< −0,10` (sem braço) | 0 | 0 | — | — |
| `>= +0,10` (sem braço) | 1 | 1 (08-22 04:45Z) | −1,0203 | −1,0203 |
| sem linha usável | 34 | 4 (06-12 → 06-15, antes do início da série) | −0,1737 | −5,9057 |

O pai cortado no início da série (`emitted_at >= 2026-06-16`, o controle que o protocolo abaixo
declara) fica com **764 decisões em 85 dias, −0,0228 R, soma −17,4459 R**. Eixo `r_ex_funding`
(764 de 764). K4 do pai, lido do recibo original de 90 d: **0,9259 %** (1 280 de 138 240 barras).

Tercis congelados, decisões de 2026-08-01 em diante: **T1 baixo `[−1; −0,005913)` +0,1502 R
(n = 77, 23 dias) · T2 meio `[−0,005913; +0,001660)` −0,0468 R (n = 60, 21 dias) · T3 alto
`[+0,001660; +1]` +0,1016 R (n = 213, 29 dias)**. **Não é monótono** — o meio é a pior célula, e as
duas pontas são positivas — logo a leitura descritiva **não** dá evidência de um gradiente ao longo
do eixo. (T3 concentra 213 das 350 decisões de agosto–setembro porque a calibração de junho–julho
tem média −0,0018 e agosto–setembro tem média +0,0005: o eixo derivou para cima entre as duas
janelas.) **Monotonicidade é evidência sobre o eixo, não sobre os braços** — foi assim que a
EXP-0027 descobriu que a ponta boa da amplitude estava fora das duas faixas pré-registradas.

## Não-antecipação (o que está provado e o que custa)

A série dobra, para o minuto `T`, exatamente **duas** velas por mercado: `open_time = T−1min` e
`open_time = T−24h−1min`, ambas `is_final`. Nada que abra em `T` entra, e não há "fechamento mais
próximo antes": um mercado sem **as duas** pontas exatas não é contado e entra como faltante
(`packages/indicators/tests/unit/test_dispersion_series.py`, inclusive a prova de que mudar a vela
que abre no corte não move o número; e
`services/scanner-worker/tests/test_dispersion_job.py::TestNaoAntecipacaoNoCaminhoDoProdutor`, que
prova o mesmo pela via real do banco e que **virar o bit `is_final`** é o que faz o minuto existir).
O universo é resolvido **uma vez por passada**, com `universe_rule`/`universe_as_of`/
`reference_symbol` gravados em `inputs`. O portão lê a linha cujo `end_time` é **exatamente** o
`source_bar_close`, **na série que a política nomeia** — sem tolerância, sem "a mais recente antes".
O custo declarado: um produtor atrasado **emudece** a versão com `dispersion_unavailable` em vez de
deixá-la decidir com valor velho.

**Custo declarado do backfill:** `--days 90` dobra no máximo **89** dias, porque cada minuto lê o
dia anterior e o dia mais velho do relatório não tem véspera dentro dele; e um dia cuja véspera não
passou o piso (ou em que o BTC não tem velas) **não é dobrado**, porque seriam 1 440 lápides
permanentes — `0020` não dá `UPDATE`/`DELETE` a ninguém.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `mean_reversion` — `v20` (braço A) e `v21` (braço B), derivadas de `v10`. O número
  exato é o que o `derive_variant.py` atribuir; `v19` era a última em 11/09.
- **code_ref:** o **do pai, byte a byte**
  (`hunter_core.strategies.mean_reversion_v1@sha256:a970c9d9…`) — nenhum parâmetro muda, só o
  envelope de elegibilidade
- **params_hash / params_format:**
  `d4fcf66f94497742d82527bfe5980bfd1f1dd630187e289b9c5cca8f1458409b` / `1`
- **Parameters:** os de `v10`, byte a byte (`atr_bars 24`, `atr_period 14`, `atr_timeframe 1h`,
  `stop_atr 1.5`, `target_atr 2.25`, `target2_atr 3.75`, `zscore_bars 20`, `trend_sma_bars 20`,
  `trend_timeframe 1h`, `atr_pct_min 0.008`, `atr_pct_max 0.05`, `horizon_s 14400`, `fee_bps 4`,
  `slippage_bps 5`, `assumed_spread_bps 2`, `max_entry_delay_s 120`, `base_confidence 0.5`,
  `zscore_depth_min 1`)
- **Política de elegibilidade:** A `{"dispersion": {"min": "-0.10", "max": "-0.03", "version":
  "dispersion_24h_v1"}}` · B `{"dispersion": {"min": "0.00", "max": "0.10", "version":
  "dispersion_24h_v1"}}`
- **Timeframe de decisão / de outcome:** 15 min / 1 min, UTC
- **Entrada / saída / custos:** os do pai (open da primeira barra de 1 min após `decision_at`, com
  `entry_bar_open − source_bar_close ≤ 120 s`; gap na abertura, depois toques intrabar, stop vence
  empate; horizonte 4 h; 2 bps de spread, 5 bps de slippage por lado, 4 bps de taxa por lado,
  funding assinado)
- **Cohort:** uma por braço, `replay:<uuid>`, registrada na avaliação
- **Controle predeclarado:** o **pai já medido** (`v10`, coorte `replay:c7d138eb…`, EXP-0025), que
  **não** será re-rodado; mais o braço de falseamento B; mais a cláusula de identidade contra
  `regime_hourly_v1`
- **Universo elegível:** os 16 mercados com ≥ 90 d de velas de 1 min (ARB BNB BTC DASH DOGE ETH LINK
  NEAR PROM SAHARA SOL SUI TAO UNI XRP ZEC), `markets.is_monitored` de hoje — a limitação declarada
  do método (`docs/PIPELINE.md` §6c: não há histórico de pertencimento por barra)
- **Janela:** **2026-06-16** (o início da série `dispersion_24h_v1`, preenchido em 2026-09-12 às
  04:40 BRT) → 2026-09-11, **com a população do pai cortada no mesmo início**, como a EXP-0027 fez, e
  a diferença de calendário declarada antes da corrida (o pai tem 34 decisões em 06-12 → 06-15 que
  saem das duas leituras: 798 → 764)
- **Data de início:** 2026-09-12

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-12 — pré-registro arquivado, nenhuma corrida ainda

**Cobertura:** nenhuma decisão. A série `dispersion_24h_v1` não tinha uma linha no instante em que
esta página foi escrita (a `0020` não estava aplicada em lugar nenhum: o código foi entregue e
**nada foi implantado nem rodado na VPS** — `.claude/state/notes-T3.90.md`). **Result:**
`nao-iniciado`. **Next Action:** (1) implantar; (2) rodar
`backfill_dispersion.py --days 90` em modo relatório e colar a saída; (3) `--apply --reason
"EXP-0029"`; (4) preencher todos os `‹backfill›` desta página com a hora BRT da leitura; (5) só
então derivar `v20`/`v21` com `--dry-run` primeiro, ativar como `research_only`, replayar por braço
e aplicar a régua acima — o que falhar é aposentado no mesmo dia.

### Avaliação de 2026-09-12 — `as_of = 2026-09-12T07:41:13Z` (04:41 BRT): checagem de população §2 — inviável nos dois braços, nenhuma variante derivada

**Corridas:** nenhuma. Nenhuma derivação, nenhum replay, nenhum estresse: `mean_reversion v20`/`v21`
**não existem** (a última versão da família continua `v19`, `deprecated`; `strategy_versions` lida
às 04:38 BRT). Tudo nesta seção é leitura somente-leitura da série e da coorte do pai (q01/q02/q03,
04:40–04:41 BRT), feita **antes** de derivar — a ordem que o brief T3.91 fixa: "se A ou B ficar fora
da sua faixa, PARE depois de escrever o resultado na EXP e não derive". Comandos e saídas verbatim em
`.claude/state/notes-T3.91.md`.

**A checagem de população, contra a previsão 2 (congelada antes do backfill):**

| braço | faixa | previsto (share das barras de 15 min) | medido (8 352 barras, 06-16 → 09-11) | dias com barra | veredito |
|---|---|---|---|---|---|
| **A** (discordância) | `[−0,10; −0,03)` | entre 10 % e 30 % | **1,48 %** (124 barras) | **9 de 88** | **fora da faixa** — 6,7× abaixo do piso |
| **B** (falseamento) | `[0,00; +0,10)` | entre 20 % e 40 % | **44,85 %** (3 746 barras) | 75 de 88 | **fora da faixa** — acima do teto |

Por janela de 30 d: A **0,14 % / 0,00 % / 4,63 %** — o braço A não tem **uma barra sequer** em J2
(07-16 → 08-15) e 120 das 124 estão em J3; B 41,28 % / 42,67 % / 51,23 %.

**Projeção de n, dos dois lados.** Pelo share: 764 decisões do pai cortado × 1,48 % ≈ **11**
desfechos; medido diretamente na coorte do pai, a célula A tem **7 decisões em 2 dias**. Mesmo no
limite absurdo em que toda barra A decidisse em todos os 16 mercados (124 × 16 = 1 984 slots), a
condição 2 exige **≥ 30 dias distintos** e a célula só existe em **9** — o braço A é
**`descartar por população`** antes de nascer, exatamente o caso que a régua já nomeava ("um braço
mudo é descartar por população, nunca negativo"). O braço B cobre quase metade das barras e **54,2 %
das decisões do pai** (414 de 764 — o pai decide mais quando as alts estão acima do BTC do que o
share de barras diz): "concordância" não é um estado dentro desta série, é o padrão dela; o braço
de falseamento pré-registrado não falseia nada porque quase tudo cabe nele.

**Result:** **`inviavel-populacao`**. Nenhum Δ, nenhum IC, nenhuma cláusula de identidade — nada a
medir e **nada a aposentar**, porque nada foi derivado. A hipótese H-P18 **como foi pré-registrada**
(célula A = `[−0,10; −0,03)`) não é testável nesta história: **não foi refutada nem confirmada**
(`result: inconclusivo`, o vocabulário da base).

**As previsões numéricas, pontuadas:**

1. **Distribuição — forma certa, cauda errada por uma ordem de grandeza.** Unimodal, estreita,
   mediana **−0,001284** (dentro do previsto [−0,01; +0,01]); mas "menos de 15 % dos minutos
   abaixo de −0,03" foi **1,45 %**. O desvio-padrão da série é **0,0132** e o p05 é **−0,0210**: o
   corte −0,03 fica perto do **percentil 1,5**. A faixa A foi fixada a partir de duas leituras
   (−0,033 em 10/09, −0,0255 em 11/09 — a série as reproduz: **−0,035624** às 19:10Z de 10/09 e
   **−0,026937** às 11:11Z de 11/09, ambas 16/16), e o próprio pré-registro avisou que era "uma
   hipótese sobre dois dias". A checagem de população existia para isto, e disparou: **55 das 124
   barras de A (44 %) são o próprio 10/09**.
2. **População — falsificada nos dois braços** (tabela acima).
3. **Direção** e 4. **cláusula de identidade** — **não mensuráveis**, sem corrida.
5. **`dispersion_unavailable` < 1 %** — **0,00 %**: nenhuma das 8 352 barras de 15 min fica sem
   linha usável; cobertura 16/16 em todos os 126 911 minutos; `insufficient_coverage` e
   `btc_missing` são zero. O instrumento entregou; a faixa é que não existe.

**O que a leitura descritiva diz (evidência sobre o eixo, não veredito, e não move a régua):** os
tercis **não são monótonos** (T1 +0,1502 · T2 −0,0468 · T3 +0,1016, n = 77/60/213, decisões de
08-01 em diante); por célula, a **pior** célula do pai é a queda conjunta `[−0,03; 0,00)` (342
decisões, 69 dias, **−0,0721 R**, soma −24,67 R) e a célula B `[0; 0,10)` é **+0,0203 R** (414
decisões). É a mesma assinatura da EXP-0027 (a célula "de dentro" pior que a de falseamento) lida
sem replay, e vale o que valeu lá: **uma faixa que ninguém pré-registrou não ganha braço.**

**Conclusion:** `inviavel-populacao` nos dois braços; `v20`/`v21` não derivadas; nada aposentado;
H-P18 marcada `testada` na INBOX com este veredito. Custo da corrida: **zero replays** — a checagem
de população poupou 24 fatias.

**Next Action:** nenhuma sobre estas faixas. Se H-P18 for perseguida, é uma **EXP nova** com
pré-registro próprio, faixas calibradas nos quantis da série (tercis `t1`/`t2` acima, ou p10/p90)
e o prior escrito de que a célula `[−0,03; 0,00)` é a pior do pai (−0,0721 R) enquanto `[0; 0,10)`
é a melhor (+0,0203 R) — a cláusula de identidade contra `regime_hourly_v1` continua por medir. E um
aviso para o plantão: a célula original de H-P18 ("mediana < −3 % **e** BTC > −2 %") **não é** a
mesma coisa que `dispersion < −0,03` — a dispersão é uma diferença, e a leitura de 10/09 (mediana
−5,08 %, BTC −1,52 %) cabe nas duas definições por coincidência, não por construção.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `v20` (A, `dispersion=-0.10--0.03`) / `v21` (B, `dispersion=0.00-0.10`) | 2026-09-12 | **não derivadas** — a checagem de população §2 falhou nos dois braços (A 1,48 %, B 44,85 % das barras de 15 min; A com 9 dias) | esta página, avaliação de 2026-09-12 (04:41 BRT) |

## Relacionadas

[[Experiments Index]] · [[Strategies]] · [[Strategy Performance]] · [[Dialogos/SHADOW]] ·
[[EXP-0025-mean-reversion-90-dias]] · [[EXP-0026-regime-como-estrategia]] ·
[[EXP-0027-amplitude]] · [[KB-0083-uma-hora-de-34-r-deriva-e-impulso]] · [[Diario/2026-09-12]] (a
madrugada em que a checagem de população parou esta EXP)

## Fontes

- brief: `.claude/state/brief-T3.90-dispersao-btc-alts.md`; notas: `.claude/state/notes-T3.90.md`
- hipótese: `obsidian/00-INBOX/Hipoteses-do-plantao.md` (H-P18, plantões de 06/09, 10/09 e 11/09)
- série e portão: `docs/PIPELINE.md` §4b item 16, `docs/ACTIVATION.md` §7c,
  `packages/indicators/hunter_indicators/dispersion/`,
  `services/scanner-worker/hunter_scanner_worker/dispersion_job.py`,
  `services/strategy-worker/hunter_strategy_worker/dispersion_gate.py`, `dispersion_policy.py`,
  `infra/migrations/versions/0020_market_dispersion.py`
- régua: [[EXP-0027-amplitude]] (a mesma, congelada), bootstrap
  `.claude/state/exp-drafts/t362b/blocos90.py`
- leitura de 2026-09-12 (T3.91): brief `.claude/state/brief-T3.91-exp-0029-dispersao.md`; notas
  `.claude/state/notes-T3.91.md`; SQL `infra/scripts/sql/research/2026-09-12-t391-q01-dispersao-distribuicao.sql`,
  `-q02-dispersao-nas-barras-de-15m.sql`, `-q03-celulas-do-pai.sql`
