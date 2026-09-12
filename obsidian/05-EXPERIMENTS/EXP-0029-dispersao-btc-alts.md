---
tags: [experimento, dispersao, btc, alts, elegibilidade, populacao, mean-reversion, pre-registro]
updated: 2026-09-12
status: pre-registrado
owner: quant-engineer
exp: EXP-0029
strategy: "mean_reversion v10 (pai sem portão) + dois braços com portão"
version: "a derivar (v20 braço A, v21 braço B — v19 era a última em 11/09)"
result: nao-iniciado
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

## Distribuição de `dispersion_24h_v1` — `‹backfill›`

Preencher **antes** de derivar, com SQL somente-leitura sobre a série já populada
(`infra/scripts/sql/research/2026-09-12-t390-*.sql`), e com a hora BRT da leitura:

| campo | valor |
|---|---|
| linhas na série / usáveis | `‹backfill›` |
| janela coberta (`min(end_time)` → `max(end_time)`) | `‹backfill›` |
| dias com cobertura ≥ 80 % (de 90) | `‹backfill›` |
| linhas `insufficient_coverage` / `btc_missing` | `‹backfill›` |
| mínimo / p05 / p10 / p25 | `‹backfill›` |
| **p50** | `‹backfill›` |
| p75 / p90 / p95 / máximo | `‹backfill›` |
| média | `‹backfill›` |

**Share de barras elegíveis por braço** — o denominador honesto são os **fechamentos de 15 min** da
janela de replay (a grade de decisão da `v10`), não todos os minutos:

| célula | barras de 15 min | share |
|---|---|---|
| **A** `[−0,10; −0,03)` | `‹backfill›` | `‹backfill›` |
| **B** `[0,00; +0,10)` | `‹backfill›` | `‹backfill›` |
| sem braço `[−0,03; 0,00)` (queda conjunta) | `‹backfill›` | `‹backfill›` |
| sem braço `< −0,10` (discordância extrema) | `‹backfill›` | `‹backfill›` |
| sem braço `>= +0,10` | `‹backfill›` | `‹backfill›` |
| sem linha usável | `‹backfill›` | `‹backfill›` |

Por janela de 30 dias (a régua exige as três): A `‹backfill›` · B `‹backfill›`.

**Tercis congelados (só para a leitura descritiva).** Calibrados sobre as linhas **usáveis** de
**2026-06-13 → 2026-07-31**, todos os minutos, e **nunca recalculados**: `t1 = ‹backfill›` e
`t2 = ‹backfill›` (n = `‹backfill›`). A janela de calibração é **descartada** da leitura descritiva,
que é medida sobre as decisões de 2026-08-01 em diante. Se a série começar depois de 06-13 (como a
`breadth_v2` começou em 06-14), a calibração efetiva é o que existir e **fica escrito aqui**, com o
n exato.

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

## Leitura descritiva por célula — `‹backfill›`, medida sobre as decisões do PAI antes do replay

Juntando cada uma das 798 decisões de `replay:c7d138eb…` à linha de `dispersion_24h_v1` do seu
`source_bar_close`. **Não é o resultado do experimento** — a população dos braços difere pela
divergência de máquina de estados do slot (`docs/PIPELINE.md` §4b item 11) — e **não move a régua**:

| célula | n | dias | `r_ex_funding` médio | soma R |
|---|---|---|---|---|
| **A** `[−0,10; −0,03)` | `‹backfill›` | `‹backfill›` | `‹backfill›` | `‹backfill›` |
| **B** `[0,00; +0,10)` | `‹backfill›` | `‹backfill›` | `‹backfill›` | `‹backfill›` |
| `[−0,03; 0,00)` (sem braço) | `‹backfill›` | `‹backfill›` | `‹backfill›` | `‹backfill›` |
| `< −0,10` (sem braço) | `‹backfill›` | `‹backfill›` | `‹backfill›` | `‹backfill›` |
| `>= +0,10` (sem braço) | `‹backfill›` | `‹backfill›` | `‹backfill›` | `‹backfill›` |
| sem linha usável | `‹backfill›` | `‹backfill›` | `‹backfill›` | `‹backfill›` |

Tercis congelados, decisões de 2026-08-01 em diante: T1 `‹backfill›` · T2 `‹backfill›` · T3
`‹backfill›`. **Monotonicidade é evidência sobre o eixo, não sobre os braços** — foi assim que a
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
- **Janela:** `‹backfill›` (o início da série `dispersion_24h_v1`) → 2026-09-11, **com a população
  do pai cortada no mesmo início**, como a EXP-0027 fez, e a diferença de calendário declarada antes
  da corrida
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

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| — | — | nenhuma derivada ainda; a série precisa existir primeiro | — |

## Relacionadas

[[Experiments Index]] · [[Strategies]] · [[Strategy Performance]] · [[Dialogos/SHADOW]] ·
[[EXP-0025-mean-reversion-90-dias]] · [[EXP-0026-regime-como-estrategia]] ·
[[EXP-0027-amplitude]] · [[KB-0083-uma-hora-de-34-r-deriva-e-impulso]]

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
