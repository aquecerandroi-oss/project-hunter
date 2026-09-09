# notes-T3.45c — `sweep_reclaim_v1` sai do papel: ativação `research_only` e replay de dia um

**Data:** 2026-09-09. **Horários em Brasília (UTC−3), UTC como detalhe.** **Owner:** quant-engineer.
**Contrato:** `EXP-0017` (arquivado no vault — **não editado**; o adendo está no §9 deste arquivo).
**Base:** módulo já commitado em `a9bacc6`, imagem viva `hunter-api:d21a11d`, VPS em `d21a11d`.

**Nada commitado. Nenhum `git pull` na VPS. Nenhum container parado, recriado ou reiniciado. Nenhum
arquivo de `.env*` tocado. Toda leitura de SQL dentro de `begin transaction isolation level
repeatable read read only`. Todo comando em primeiro plano, com `timeout` explícito. Único arquivo
novo no repo: este.**

---

## 1. STATUS

**DONE_WITH_CONCERNS.** A versão foi ativada, o replay de 31 dias × 4 mercados rodou inteiro em
quatro fatias contíguas na mesma coorte, o funil bateu com a pré-checagem dentro de ±10 % em todas as
portas, `geometry` saiu **zero** como previsto — e **nenhum critério de morte disparou**. O que também
não aconteceu: nenhuma vantagem apareceu. A expectancy da base é **−0,087 R** com IC 95 %
**[−0,412; +0,238]**, PF 0,84, e a passada de estresse devolveu o veredito mecânico
**`sem_vantagem_na_base`**.

| # | Entrega do brief T3.45c | Resultado |
|---|---|---|
| 1 | Ativação por script auditado, `--dry-run` e depois real | **OK.** digest conferido antes de congelar |
| 2 | Replay 31 d × 4 mercados com `--explain-ledger` e coorte explícita | **OK.** 11 904 barras, 4 recibos, 0 erros |
| 3 | Dia um por EXP-0017 (contagem vs 57, decisões, expectancy, PF, pedágio, `risk_pct`, rejeições, K1–K6) | **OK** |
| 4 | Estresse só se K1 sobreviver | **OK.** K1 sobreviveu (48 ≥ 20); estresse rodou |
| 5 | Veredito pelo funil | **`inconclusivo` no dia um; `sem_vantagem_na_base` no estresse** |
| 6 | ≤ 10 linhas em português para o Everton | **OK** (§10) |
| 7 | `notes-T3.45c.md` + adendo do EXP em rascunho | **OK** (§9) |

---

## 2. ATIVAÇÃO — o digest foi conferido antes de congelar

A linha nasceu `draft` pelo `seed --only strategies` da T3.52d, com o `code_ref` de semente
(`hunter_indicators.strategies.sweep_reclaim_v1`, placeholder). A ativação é que congela o digest
real, lido **da imagem implantada**.

```bash
$ cd /opt/project-hunter && export MARKET_SHARDS=4 MARKET_SPOT=1
$ bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py \
    sweep_reclaim v1 --changelog 'T3.45c: coorte de pesquisa do EXP-0017 (replay de 31 d x 4 mercados; research_only)' --dry-run
would activate sweep_reclaim v1 (purpose research_only) with code_ref
hunter_core.strategies.sweep_reclaim_v1@sha256:a1150343f436494e9c007a1219c90c1467ecc9359d5ca0fa5e75658f0023556c (20 parameters)

$ bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py \
    sweep_reclaim v1 --changelog 'T3.45c: coorte de pesquisa do EXP-0017 (replay de 31 d x 4 mercados; research_only)'
activated sweep_reclaim v1 (purpose research_only) at 2026-09-09T17:24:25.653491+00:00 with code_ref
hunter_core.strategies.sweep_reclaim_v1@sha256:a1150343f436494e9c007a1219c90c1467ecc9359d5ca0fa5e75658f0023556c
```

**14:24:25 BRT** (17:24:25Z). O digest é **dígito a dígito** o publicado pela `notes-T3.45b.md`
(`a1150343f436494e9c007a1219c90c1467ecc9359d5ca0fa5e75658f0023556c`) e é o mesmo que a árvore local
calcula hoje (§8). Três coisas foram lidas antes de eu rodar o real: `purpose = research_only` (por
semente, como o brief manda), 20 parâmetros (os 20 congelados da T3.45b) e nenhum
`context_budget_unknown` — o `context_budget` do worker dimensiona esta versão em **1 560 min**, o
piso, porque a janela mais longa é `atr_bars 97 × 15 min = 1 455 min`.

Estado final da linha no catálogo (leitura em 14:33 BRT):

```
      key      | version | status |    purpose    | activated_at
 sweep_reclaim | v1      | active | research_only | 2026-09-09 17:24:25.653491+00
```

**`--changelog` é obrigatório pelo script** e o brief não o trazia; o texto acima é meu e está
declarado como assunção operacional (§7, assunção 1).

---

## 3. O REPLAY — quatro fatias, uma coorte, `--explain-ledger` ligado

Coorte cunhada explicitamente: **`replay:c1c5331d-8c12-4fc8-8480-e547522c53d7`**.
Janela: `2026-08-08T00:00Z ≤ open_time < 2026-09-08T00:00Z` (31 dias), mercados `ETHUSDT, SOLUSDT,
XRPUSDT, DOGEUSDT` (binance, perpétuo) — exatamente os da pré-checagem.

Plano (`--dry-run`, 14:25 BRT): `{'markets': 4, 'bars_planned': 11904, 'context_minutes': 1560, 'workers': 3}`.

```bash
$ docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
    --version sweep_reclaim:v1 --from <de> --to <ate> \
    --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT \
    --cohort replay:c1c5331d-8c12-4fc8-8480-e547522c53d7 \
    --ledger /tmp/sr_receipts.jsonl --explain-ledger /tmp/sr_explain.jsonl
```

Recibos, lidos de volta de `replay_runs` (não da memória de quem rodou):

```
     de     |    ate     | bars_evaluated | signals | outcomes_resolved |  s   | workers | errors |          evaluations_by_state
 2026-08-08 | 2026-08-12 |           1536 |       1 |                 1 | 21.6 |       3 |      0 | {"triggered": 1, "unavailable": 448, "not_triggered": 1087}
 2026-08-12 | 2026-08-20 |           3072 |       1 |                 1 | 50.0 |       3 |      0 | {"not_triggered": 3072}
 2026-08-20 | 2026-08-28 |           3072 |      32 |                32 | 50.3 |       3 |      0 | {"triggered": 33, "not_triggered": 3039}
 2026-08-28 | 2026-09-08 |           4224 |      48 |                48 | 67.0 |       3 |      0 | {"triggered": 17, "not_triggered": 4207}
```

`1536 + 3072 + 3072 + 4224 = 11 904` — **exatamente** o plano, e o ledger de explicação tem
**11 904 linhas**, uma por barra avaliada. `errors = 0` nas quatro. Cada fatia levou 22–67 s de
motor (40–73 s de relógio incluindo o SSH), bem dentro do `timeout 290` por fatia.

**A coluna `signals` dos recibos é cumulativa da coorte** (`count_population` conta do banco, não da
memória do processo — `replay/simulate.py:292`), então ela não soma por fatia: 1 → 1 → 32 → 48. Quem
soma por fatia é `evaluations_by_state`.

---

## 4. O FUNIL MEDIDO CONTRA O PREVISTO — porta a porta

Histograma do `--explain-ledger` (11 904 linhas, `state` + `reason`):

```
  9754  not_triggered  no_sweep
  1196  not_triggered  no_reclaim
   236  unavailable    warmup
   212  unavailable    atr_warmup
   207  not_triggered  low_rvol
   125  not_triggered  no_pivot
   122  not_triggered  risk_below_floor
    51  triggered      signal
     1  not_triggered  risk_above_cap
```

| porta | SQL da pré-checagem (T3.45) | motor (T3.45c) | Δ |
|---|---:|---:|---:|
| barras avaliáveis | 11 460 | **11 456** | −0,03 % |
| com pivô confirmado | 11 398 | **11 331** | −0,6 % |
| varreram | 1 610 | **1 577** | −2,0 % |
| varreram + recuperaram | 368 | **381** | +3,5 % |
| + RVOL ≥ 1,5 | 177 | **174** | −1,7 % |
| + piso de risco (0,006) | 58 | **52** | −10,3 % |
| − teto de risco (`risk_atr ≤ 3`) | 57 | **51** | −10,5 % |
| **decisões persistidas** | 43–57 (banda da barreira) | **48** | dentro da banda |
| `REJECTED / geometry` | **0 esperado** | **0** | ✔ |

Três leituras:

1. **A previsão do SQL se sustentou.** Nenhuma porta errou por mais de 10 %, e a única que chega perto
   é a de custo — a mais sensível a `float8` vs `Decimal`, exatamente como o CONCERN 4 da T3.45b
   avisou. `risk_above_cap` recusou **1** barra em 31 dias × 4 mercados: o SQL previu **1**. Não é
   coincidência sortuda, é a mesma regra medida duas vezes.
2. **`geometry` = 0.** A guarda que matou a `breakout_v1` com 14/14 rejeições não disparou nenhuma
   vez aqui, como o CONCERN 6 da T3.45b previu e o EXP pré-registrou. O critério específico do EXP
   ("`geometry` acima de 20 % das barras que passariam pelas portas 4–7") lê **0 / 52 = 0,0 %**.
3. **Os 448 `unavailable` são aquecimento e nada mais.** Todos caem em 08/08 (384) e 09/08 (64),
   idênticos nos quatro mercados (59 `warmup` + 53 `atr_warmup` cada). **Zero** buracos internos —
   a leitura de cobertura da pré-checagem (99,5 %) sobreviveu ao motor, que é mais exigente que o SQL
   (`aggregate()` recusa a janela inteira quando falta **um** minuto).

**As 3 barras que dispararam e não viraram decisão são a barreira de re-arme, nomeadas uma a uma:**

| barra (UTC) | mercado | decisão anterior no mesmo slot | distância |
|---|---|---|---|
| 2026-08-21T09:30 | DOGEUSDT | 2026-08-21T09:15 | 15 min |
| 2026-08-25T12:15 | DOGEUSDT | 2026-08-25T10:00 | 2 h 15 |
| 2026-08-28T14:45 | SOLUSDT | 2026-08-28T14:30 | 15 min |

As três caem dentro do horizonte de 4 h da decisão anterior — uma-tracking-por-slot, o desenho. A
pré-checagem previu que a barreira levaria os 57 para algo entre 43 e 57; **51 → 48**.

---

## 5. DIA UM — os números, e o que eles podem dizer

**A primeira linha, e não a última: este resultado é `inconclusivo` por construção.** A régua de
maturidade pede **100 desfechos avaliáveis E 30 dias distintos**; há **48 e 15**. K3 nem é aplicável.

### 5.1 Agregado (48 decisões, 100 % com `R_net` conhecido)

```
 n  | dias | com_r_net | pct_r_net | exp_bruta | exp_liq | pf_bruta | pf_liq | pct_ganho
 48 |   15 |        48 |     100.0 |   -0.0852 | -0.0871 |    0.844 |  0.841 |      50.0
```

Com o intervalo, que é a única forma honesta de ler 48 desfechos:

```
 n  |  media  |   dp   |   ep   |  ic_lo  | ic_hi  | r_total
 48 | -0.0871 | 1.1498 | 0.1660 | -0.4124 | 0.2382 |  -4.180
```

**−0,087 R por decisão, IC 95 % [−0,412; +0,238] — cruza zero.** O dia um **não** pode dizer "perde";
ele diz "não mediu vantagem, e não distingue de zero". Soma da janela: **−4,18 R**.

Vocabulário, porque ele confunde: `exp_bruta` é `r_ex_funding` (R **já líquido de taxa, spread e
slippage assumidos**, sem funding) — é assim que o EXP-0017 define "bruta" no K3. `exp_liq` é
`r_multiple` (com funding). A diferença entre as duas é **0,0019 R**: nesta janela o funding é ruído
ao lado do pedágio, que já está dentro das duas.

### 5.2 Por desfecho

```
 result  | count |  bruta  |   liq
 stop    |    22 | -1.1446 | -1.1450
 expired |    17 |  0.3186 |  0.3147
 target  |     9 |  1.7414 |  1.7401
```

Nove alvos de 2R contra 22 stops. O `−1,145` do stop e o `+1,740` do alvo são a aritmética do pedágio
funcionando como a tabela do EXP prevê para `risco%` mediano de 0,94 % (o EXP publicou a linha para o
piso de 0,60 %: `−1,2112 / +1,5133`; com risco% maior, o pedágio pesa menos).

### 5.3 Por mercado (K6 — obrigatória, não opcional)

```
  symbol  | n  | pct  | dias |  bruta  |   liq   | pf_liq
 XRPUSDT  | 16 | 33.3 |   10 | -0.2160 | -0.2179 |  0.586
 DOGEUSDT | 12 | 25.0 |   11 | -0.1367 | -0.1392 |  0.771
 SOLUSDT  | 12 | 25.0 |    6 | -0.1063 | -0.1076 |  0.843
 ETHUSDT  |  8 | 16.7 |    7 |  0.2852 |  0.2835 |  1.963
```

Maior mercado **33,3 %** (previsto: 29,8 %) — K6 não dispara. E o único mercado positivo tem **n = 8**;
ler `PF 1,96` do ETHUSDT como notícia seria exatamente o erro que a KB-0010 descreve.

### 5.4 Pedágio e `risk_pct` — a porta de custo fez o que foi contratada para fazer

```
 toll_min | toll_p10 | toll_p50 | toll_p90 | toll_max | acima_do_teto_0.3333
   0.0668 |   0.1232 |   0.2120 |   0.3068 |   0.3270 |                    0

 risk_min | risk_p10 | risk_p50 | risk_p90 | risk_max | abaixo_do_piso_0.006
  0.00612 |  0.00652 |  0.00944 |  0.01623 |  0.02993 |                    0
```

- **pedágio p50 = 0,2120 R**, p90 = 0,3068 R, **máximo 0,3270 R** — nenhuma decisão acima do teto
  declarado de **0,3333 R**. Não é sorte: `pedágio = 0,0020 / risco%` e `risco% ≥ 0,006` são a mesma
  identidade, então o teto é **matematicamente** garantido pelo piso. O que a medida acrescenta é o
  **quanto** o piso morde na prática: a mediana ficou em 0,94 % de risco, 57 % acima do piso;
- **`risk_pct` mínimo 0,00612 ≥ 0,006** — o piso não vazou nem por arredondamento de `Decimal`;
- comparação com a pré-checagem: no estágio C (varreu+recuperou+RVOL) o `risco%` mediano era
  **0,398 %** e o pedágio mediano **0,50 R**. Depois da porta, **0,944 %** e **0,212 R**. **A porta de
  custo cortou o pedágio mediano por 2,4×** — ela funcionou. Não bastou.

### 5.5 As outras features na decisão (mediana)

```
 rvol_p50 | sweep_p50 | prom_p50 | pivot_back_p50 | risk_atr_p50 | atr_pct_p50
    3.082 |     0.814 |    1.342 |            8.0 |        1.378 |     0.00723
```

O RVOL mediano da decisão é **3,08** — o dobro do piso de 1,5, isto é, a porta de volume seleciona
barras muito mais extremas do que ela exige. A varredura mediana é **0,81 ATR**, contra um piso de
0,25 ATR: também aqui a população real fica longe do limiar. Isso é robustez a `sweep_atr` e
`rvol_min` (a Q4 da pré-checagem já sugeria) e, ao mesmo tempo, mata a esperança de explicar a
população por esses dois números.

### 5.6 Regime de BTC (obrigação do EXP, C4)

```
     regime      | n  |  bruta  |   liq   | pct_ganho
 BTC_BULL        | 21 | -0.4237 | -0.4245 |      33.3
 HIGH_VOLATILITY | 16 |  0.2068 |  0.2048 |      62.5
 SIDEWAYS        |  6 |  0.2069 |  0.2011 |      50.0
 BTC_BEAR        |  3 |  0.3637 |  0.3637 |     100.0
 LOW_VOLATILITY  |  1 | -1.1940 | -1.1940 |       0.0
 UNKNOWN         |  1 |  0.3578 |  0.3552 |     100.0
```

(rótulo da **hora anterior fechada**, `regime_hourly_v1`, escopo BTC — a mesma regra do portão da
T3.52.) A leitura tentadora — "só em `HIGH_VOLATILITY`" — é **exatamente** a que a T3.52d já mediu e
publicou como frágil: 16 decisões em 15 dias não sustentam um portão, e escolher o rótulo **depois**
de ver a tabela é a definição de sobreajuste. **Fica registrado como observação, não como proposta.**

### 5.7 Por quartil de ATR% e por quartil de `risco%`

```
 quartil | n  | atr_min | atr_max | risk_p_medio |  bruta  |   liq
       1 | 12 | 0.00348 | 0.00504 |      0.00888 | -0.3158 | -0.3170
       2 | 12 | 0.00506 | 0.00722 |      0.00917 |  0.3634 |  0.3600
       3 | 12 | 0.00723 | 0.00908 |      0.01004 | -0.2103 | -0.2112
       4 | 12 | 0.00914 | 0.01418 |      0.01460 | -0.1783 | -0.1802

 quartil | n  | risk_min | risk_max | pedagio_medio |  bruta  |   liq
       1 | 12 |  0.00612 |  0.00732 |        0.3056 | -0.0569 | -0.0581
       2 | 12 |  0.00751 |  0.00935 |        0.2328 | -0.1825 | -0.1849
       3 | 12 |  0.00953 |  0.01189 |        0.1949 |  0.3582 |  0.3563
       4 | 12 |  0.01228 |  0.02993 |        0.1228 | -0.4597 | -0.4616
```

Sem monotonia em nenhum dos dois eixos, com n = 12 por célula. **Nenhuma dessas linhas autoriza um
piso novo** — e a que mais tentaria (o quartil 4 de risco%, o mais caro em preço e o mais barato em
pedágio, sendo o pior) diz o **oposto** do que a identidade do pedágio previa. É ruído com 12
observações; está aqui porque o EXP obriga a publicar, não porque decida algo.

### 5.8 A objeção de sobreposição com a `mean_reversion_v1` — respondida com número

A `mean_reversion v1` tem uma coorte de replay (`replay:d0f77894…`) sobre os mesmos 4 mercados na
janela **2026-08-20 → 2026-09-06**. Restringindo as duas populações a essa janela comum:

```
 sweep_n | mr_n | mesma_barra | dentro_de_1h
      44 |   37 |           2 |            7
```

**2 barras em comum de 44 (4,5 %)**; 7 dentro de uma hora (15,9 %). A objeção que a T3.33 levantou
("é a mesma coisa que a `mean_reversion`") **não se confirmou**: as populações são quase disjuntas.
Nota honesta: a janela comum é 18 dias, não 31, porque a coorte da `mean_reversion v1` começa em 20/08.

### 5.9 Concentração no tempo — um achado que ninguém pediu

Oito barras têm ≥ 2 mercados disparando **no mesmo minuto**, e duas têm três
(`2026-08-24T01:00Z` e `2026-08-25T10:00Z`, ambas DOGE+SOL+XRP). Isso é **19 dos 51 disparos em
gatilhos sincronizados**: a regra não é independente entre mercados, ela dispara quando o BTC arrasta
o bloco inteiro. Para o Lab isso não muda nada; para qualquer leitura futura de risco de portfólio,
muda tudo — três posições abertas no mesmo minuto no mesmo fator não são três apostas.

### 5.10 K1–K6, um a um

| # | régua | leitura | disparou? |
|---|---|---|---|
| K1 | < 20 decisões | **48** (51 disparos, 3 barrados pelo re-arme) | **não** — margem 2,4× |
| K2 | > 1 500 decisões | 48 | não |
| K3 | ≥ 100 avaliáveis **E** ≥ 30 dias **E** bruta < 0 | 48 avaliáveis, **15 dias** → **não aplicável** | não |
| K4 | `unavailable` > 40 % | **3,76 %** (448/11 904), 100 % aquecimento | não |
| K5 | cobertura de `R_net` < 70 % | **100 %** (48/48, nenhum `r_net_reason`) | não |
| K6 | ≥ 60 % de um mercado | **33,3 %** (XRPUSDT) | não |
| específico | `geometry` > 20 % das barras que passam nas portas 4–7 | **0 / 52 = 0,0 %** | **não** |

**Nenhum critério de morte disparou.** E, pela régua do funil (`SHADOW-LAB.md` §3), K1 sozinho seria
`inconclusivo`; aqui nem ele disparou. O veredito do dia um é **`inconclusivo`** — pela maturidade,
não por falta de disciplina.

---

## 6. ESTRESSE — rodou porque K1 sobreviveu, e devolveu o único veredito possível

```
$ docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.stress \
    --cohort replay:c1c5331d-8c12-4fc8-8480-e547522c53d7
coorte replay:c1c5331d-8c12-4fc8-8480-e547522c53d7 · as_of 2026-09-09T17:36:14.490743+00:00 · 48 entradas congeladas · 4 mercados

| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
|---|---|---:|---:|---:|---:|---|
| `base` | reprecificacao | 48 | -0.0871 | 0.8412 | — | — |
| `custos_x2` | reprecificacao | 48 | -0.2815 | 0.5455 | -0.1945 | [-0.2414, -0.1562] |
| `stop_x0.75` | reprecificacao | 48 | -0.1101 | 0.8314 | -0.0230 | [-0.2668, +0.1434] |
| `stop_x1.25` | reprecificacao | 48 | -0.1394 | 0.7258 | -0.0523 | [-0.1313, +0.0299] |
| `alvo_x0.75` | reprecificacao | 48 | -0.0522 | 0.8956 | 0.0349 | [-0.1012, +0.1512] |
| `alvo_x1.25` | reprecificacao | 48 | -0.0145 | 0.9736 | 0.0726 | [+0.0061, +0.1550] |
| `entrada_mais_1_barra` | reprecificacao | 48 | -0.1572 | 0.7150 | -0.0701 | [-0.1612, +0.0242] |
| `sem_binance:DOGEUSDT` | recorte | 36 | -0.0697 | 0.8681 | — | — |
| `sem_binance:ETHUSDT` | recorte | 40 | -0.1612 | 0.7309 | — | — |
| `sem_binance:SOLUSDT` | recorte | 36 | -0.0803 | 0.8401 | — | — |
| `sem_binance:XRPUSDT` | recorte | 32 | -0.0217 | 0.9612 | — | — |
| `1a_metade_ate_2026-08-24` | recorte | 17 | 0.1174 | 1.2570 | — | — |
| `2a_metade_apos_2026-08-24` | recorte | 31 | -0.1992 | 0.6672 | — | — |

**Veredito:** sem_vantagem_na_base
```

**14:36 BRT** (17:36Z), 9,6 s, sessão `READ ONLY`, nada escrito no Lab.

O veredito mecânico é o único que faz sentido: a base já é ≤ 0, então "isto é robusto?" não é uma
pergunta bem posta. Ainda assim, duas linhas merecem ser lidas, com a ressalva de que reusam a mesma
população:

- **`custos_x2` é o único Δ negativo com IC que não cruza zero** ([−0,241; −0,156]): dobrar o custo
  custa **0,195 R por decisão**, ~2,2 pedágios medianos. Sensibilidade a custo alta, como esperado
  para uma versão cujo pedágio p50 é 0,21 R;
- **`alvo_x1.25`** ([+0,006; +0,155]) é o outro Δ que não cruza zero — alvo 2,5R melhora 0,073 R. É um
  eixo já em medição pela `momentum v6` (T3.40) e **não** vira variante daqui (KB-0010): sete ângulos
  sobre a mesma população não são sete experimentos, e a base continua ≤ 0.

---

## 7. ASSUNÇÕES NUMÉRICAS E OPERACIONAIS QUE PRECISEI FAZER

1. **`--changelog` não estava no comando do brief e o script o exige.** Usei
   `'T3.45c: coorte de pesquisa do EXP-0017 (replay de 31 d x 4 mercados; research_only)'`. Texto meu,
   registrado aqui, e ele fica no rastro de auditoria da ativação para sempre.
2. **As fatias do replay são quatro (4 + 8 + 8 + 11 dias), não duas.** O brief pedia `timeout 290` por
   fatia; a fatia inteira de 31 dias levaria ~170 s de motor, mas a única medida que eu tinha antes de
   rodar era zero. Cortei em quatro para que nenhuma passasse perto do teto. Fatias contíguas, mesma
   coorte, sem sobreposição — a população é uma só e o ledger é um arquivo só (o `merge` do
   `--explain-ledger` **acrescenta**, por desenho).
3. **A janela é a da pré-checagem** (`2026-08-08` a `2026-09-08`), lida do cabeçalho do SQL da T3.45,
   e os mercados são os quatro de lá. O brief dizia "31 d × 4 mercados" sem repetir as datas.
4. **O IC de 95 % da base é normal-aproximado** (`média ± 1,96 × dp/√n`), calculado em SQL sobre os 48
   `r_multiple`. Com n = 48 e desvio 1,15 R, a aproximação é razoável; o estresse usa reamostragem
   própria para os Δ e é ela que vale para comparações pareadas.
5. **A tabela por regime usa a hora anterior fechada** (`start_time = date_trunc('hour', emitted_at) −
   1 h`, escopo `btc`, `regime_hourly_v1`) — a mesma regra que o portão de elegibilidade da T3.52 usa.
   Uma decisão caiu em `UNKNOWN` e é reportada como tal, não descartada.
6. **A comparação com a `mean_reversion v1` usa a coorte de replay `d0f77894…`** — a única daquela
   versão sobre estes mercados nesta janela — e é restrita à janela comum (20/08 a 06/09). Fora dela
   não há com o que comparar.

---

## 8. TESTES — saída real

A árvore local não foi tocada; o que segue prova que o módulo congelado é o que foi ativado.

```
$ uv run pytest packages/core/tests/unit/strategies/test_sweep_reclaim_v1.py packages/core/tests/unit/strategies/test_no_lookahead.py -q
........................................................................ [ 58%]
....................................................                     [100%]
124 passed in 12.45s

$ uv run python -c "from hunter_strategy_worker.code_ref import version_code_ref; ..."
sweep_reclaim_v1 = hunter_core.strategies.sweep_reclaim_v1@sha256:a1150343f436494e9c007a1219c90c1467ecc9359d5ca0fa5e75658f0023556c
```

O digest local é **idêntico** ao congelado na ativação (§2) e ao publicado pela T3.45b. Os 124 testes
incluem o teste central de não-antecipação desta versão
(`test_a_swing_low_two_bars_old_does_not_exist_yet`: as **mesmas velas** em dois cortes; no primeiro
o fundo está em `t−2` e a resposta é `no_pivot`; duas barras depois ele é o pivô da decisão) e as
mutações do `test_no_lookahead.py` — a vela em formação não muda nenhuma feature de barra.

---

## 9. ADENDO PARA O `EXP-0017` (rascunho — o EXP está arquivado no vault e **não foi editado**)

> Para a Sexta-feira arquivar na seção "Avaliação de <segunda data> — replay de abertura", **abaixo**
> das seções congeladas, sem tocar em Hipótese / Portão / Protocolo. Frontmatter sugerido:
> `result: inconclusivo`, `evaluable: 48`, `days: 15`, `last_eval: 2026-09-09`.

### Avaliação de 2026-09-09 — replay de abertura (T3.45c)

**Este resultado é `inconclusivo`, e é a primeira linha e não a última.** A régua de maturidade pede
100 desfechos avaliáveis **e** 30 dias distintos; o replay entregou **48 e 15**. K3 não é aplicável.
Foi o que a T3.45 previu antes de o módulo existir ("17 dias distintos não viram 30") e é o que
aconteceu.

- **Coorte:** `replay:c1c5331d-8c12-4fc8-8480-e547522c53d7`. **Versão:** `sweep_reclaim v1`,
  `research_only`, ativada em 2026-09-09 14:24 BRT (17:24Z) com
  `code_ref = hunter_core.strategies.sweep_reclaim_v1@sha256:a1150343…`, `context_minutes = 1560`.
- **Janela:** 2026-08-08 a 2026-09-08 (31 d). **Mercados:** ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT
  (binance, perpétuo). **Recibos:** 4 linhas em `replay_runs`, 11 904 barras, 0 erros, `workers = 3`.
- **População:** 51 disparos, **48 decisões** (3 barrados pela barreira de re-arme, nomeados na
  notes-T3.45c §4). A pré-checagem previu 57 disparos e uma banda de 43–57 decisões: **acertou**.
- **Cobertura:** `R_net` conhecido em **48/48 (100 %)**. `unavailable` = 448 (3,76 %), **todo**
  aquecimento nas primeiras 28 h e idêntico nos quatro mercados; zero buracos internos.
- **Resultado:** expectancy bruta (`r_ex_funding`) **−0,0852 R**, líquida **−0,0871 R**, PF
  **0,844 / 0,841**, acerto 50,0 %, soma **−4,18 R**. IC 95 % da média líquida:
  **[−0,412; +0,238]** — cruza zero. O dia um **não** diz "perde"; diz "não mediu vantagem".
- **Desfechos:** 22 stops (−1,145 R médio), 9 alvos (+1,740 R), 17 expirados (+0,315 R).
- **Pedágio:** p50 **0,2120 R**, p90 0,3068 R, máximo **0,3270 R** — **nenhuma** decisão acima do teto
  declarado de 0,3333 R, o que é garantido pela identidade quando `risco% ≥ 0,006`. `risco%` mínimo
  observado **0,00612**, mediano 0,00944. **A porta de custo cortou o pedágio mediano de 0,50 R
  (estágio C da pré-checagem) para 0,21 R — 2,4×. Ela funcionou; não bastou.**
- **`geometry` = 0**, como pré-registrado (0 de 52 barras que passam nas portas 4–7 = 0,0 %).
- **K1–K6:** nenhum disparou. K1 48 ≥ 20 (margem 2,4×); K2 48 ≤ 1 500; K3 não aplicável; K4 3,76 %;
  K5 100 %; K6 33,3 % (XRPUSDT).
- **Decomposição por mercado (obrigatória):** XRPUSDT 16 / −0,218 R / PF 0,59; DOGEUSDT 12 / −0,139 /
  0,77; SOLUSDT 12 / −0,108 / 0,84; ETHUSDT 8 / **+0,284** / 1,96. O único positivo tem n = 8.
- **Decomposição por regime de BTC** (hora anterior fechada, `regime_hourly_v1`): BTC_BULL 21 /
  −0,425; HIGH_VOLATILITY 16 / +0,205; SIDEWAYS 6 / +0,201; BTC_BEAR 3 / +0,364; LOW_VOLATILITY 1 /
  −1,194; UNKNOWN 1 / +0,355. **Registro, não proposta:** escolher o rótulo depois de ver a tabela é
  sobreajuste, e a T3.52d já mediu que um portão de regime sobre ~100 decisões é frágil.
- **Por quartil de ATR% e de `risco%`:** sem monotonia em nenhum dos dois eixos, 12 por célula. Nada
  aqui autoriza mexer em piso ou faixa.
- **Sobreposição com a `mean_reversion v1`** (a objeção da T3.33), na janela comum 20/08–06/09:
  **2 barras em comum de 44 (4,5 %)**, 7 dentro de 1 h. **A objeção não se confirmou.**
- **Estresse** (`stress.py`, 48 entradas congeladas): **`sem_vantagem_na_base`**. Só dois Δ têm IC que
  não cruza zero — `custos_x2` (−0,195 R) e `alvo_x1.25` (+0,073 R). A metade 1 é +0,117 R (n = 17) e
  a metade 2 é −0,199 R (n = 31).
- **Pendências do protocolo que este replay NÃO entregou:** (a) o **grupo de controle** pré-registrado
  ("varreu e fechou **abaixo**", 1 196 barras no ledger) não tem `R` medido — o motor só mede o que
  uma versão decide, e medir o controle exige derivar um braço, o que é experimento novo com portão
  próprio; (b) o universo é o de hoje, não o de agosto (PIPELINE §6c).

**Result: `inconclusivo`.**

**Next Action (recomendação, não decisão):** **não** abrir coorte prospectiva agora. O funil manda
que o estresse possa dizer "não gaste 30 dias", e ele disse `sem_vantagem_na_base`. A versão fica
`active / research_only` (sem custo por barra relevante: 4 mercados, ~1,5 decisão/dia) e a decisão de
aposentar, alargar o universo ou derivar um braço de controle é do Everton.

---

## 10. AS ≤ 10 LINHAS PARA O EVERTON

```
1. A sweep_reclaim v1 saiu do papel hoje as 14:24 (BRT): ativada como pesquisa, digest conferido antes de congelar.
2. Rodei o replay de 31 dias nos 4 mercados: 11.904 barras, 4 recibos, zero erros.
3. A previsao do SQL acertou: 51 disparos (previa 57) e 48 decisoes (a banda prevista era 43 a 57).
4. Nenhum criterio de morte disparou: K1 48 (piso 20), K4 3,8 %, K5 100 %, K6 33 %, e a guarda de geometria deu zero, como esperado.
5. A porta de custo funcionou: o pedagio mediano caiu de 0,50 R para 0,21 R e nenhuma decisao passou do teto de 0,3333 R.
6. Mas nao apareceu vantagem: -0,087 R por decisao, fator de lucro 0,84, -4,18 R na janela, 50 % de acerto.
7. Com 48 decisoes o intervalo vai de -0,41 a +0,24 R: o resultado nao se distingue de zero. Leitura oficial: INCONCLUSIVO.
8. A passada de estresse devolveu "sem vantagem na base" - o unico teste com efeito claro e o custo dobrado (-0,195 R).
9. A objecao antiga ("e a mesma coisa que a mean_reversion") caiu: so 2 barras em comum de 44 (4,5 %).
10. Minha recomendacao: NAO abrir coorte prospectiva agora; ela fica em pesquisa, custo quase zero, e voce decide se aposenta ou alarga o universo.
```

---

## 11. FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\.claude\state\notes-T3.45c.md` | **novo** — este arquivo (único arquivo criado no repo) |

**Artefatos fora do repo (VPS):**

| caminho | o quê |
|---|---|
| `/tmp/sweep_reclaim_v1_explain_c1c5331d.jsonl` (host da VPS) | ledger de explicação, 11 904 linhas, uma por barra |
| `/tmp/sweep_reclaim_v1_receipts_c1c5331d.jsonl` (host da VPS) | os 4 recibos de fatia |
| `/tmp/sr_explain.jsonl`, `/tmp/sr_receipts.jsonl` (dentro do `hunter-strategy-worker-1`) | os originais, efêmeros |
| coorte `replay:c1c5331d-…` em `replay_runs` / `agent_signals` / `signal_outcomes` | o durável |

**Não tocados:** `obsidian/**` (o EXP-0017 está arquivado; o adendo é rascunho no §9),
`packages/**`, `services/**`, `apps/**`, `infra/**`, `.env*`, e o repo da VPS (nenhum `git pull`).

---

## 12. CONCERNS

1. **Nenhum critério de morte disparou e mesmo assim não há o que promover.** Este é o resultado mais
   incômodo possível: a versão está tecnicamente saudável (população existe, cobertura 100 %,
   geometria limpa, pedágio dentro do teto) e mede **−0,087 R** com intervalo que cruza zero. O
   funil não a mata e não a promove. Quem quiser um veredito binário vai ter que inventá-lo.
2. **O grupo de controle pré-registrado continua sem `R` medido.** O EXP-0017 obriga a comparar as 48
   decisões contra as barras que varreram e **não** recuperaram (1 196 no ledger, com todo o resto
   igual). O motor não mede o que nenhuma versão decide, então isso exige derivar um braço — e
   derivar um braço é experimento novo, com portão e contraste pareado próprios (KB-0010). **A
   hipótese central do EXP — "a recuperação prevê" — segue sem contraste.** Sem ele, os −0,087 R não
   dizem se a recuperação ajuda, atrapalha ou é irrelevante.
3. **17 dias distintos viraram 15, e a maturidade continua inalcançável nesta janela.** A barreira de
   re-arme comeu dois dias. Nesta cadência (~1,5 decisão/dia com 4 mercados), 100 desfechos levam
   ~2 meses de prospectivo. **Alargar o universo é a alavanca real e continua sendo decisão do
   Everton** — é a mesma pendência aberta desde a T3.45, agora com o número medido em vez do estimado.
4. **A tabela por regime é a tentação mais perigosa deste relatório.** `HIGH_VOLATILITY` com +0,205 R
   em 16 decisões e `BTC_BULL` com −0,425 R em 21 pedem um portão. Não peça: a T3.52d mediu um portão
   desses sobre ~100 decisões e o IC do Δ cruzou zero. Aqui são 16. **Publiquei porque o EXP obriga;
   qualquer uso disso para escolher regime é sobreajuste com nome novo.**
5. **19 dos 51 disparos são simultâneos entre mercados** (duas barras com três mercados ao mesmo
   tempo). Para o Lab, irrelevante. Para qualquer leitura de risco de portfólio, é o número mais
   importante desta página: essas decisões não são independentes, e um dimensionamento que as trate
   como três apostas separadas está errando o fator.
6. **A diferença SQL vs motor na porta de custo (58 → 52) é a maior de todas as portas (−10 %).** Era
   a previsão do CONCERN 4 da T3.45b (`float8` vs `Decimal` perto do piso) e ela se confirmou no lugar
   exato onde foi prevista. Não muda ordem de grandeza; muda a contagem em unidades, e está nomeada
   em vez de arredondada.
7. **O universo é o de hoje** (PIPELINE §6c, `is_monitored` lido na hora da corrida), não o de agosto.
   Vale para toda coorte de replay do projeto, então não enviesa comparações entre versões — mas
   nenhum número desta página descreve o universo que existia na janela.
8. **A versão fica `active / research_only` e isso é irreversível na direção do `code_ref`.** A
   ativação congelou o digest; mudar uma linha do módulo agora é `v2`, nunca edição. Aposentar exige
   `activate_strategy_version.py --deprecate` com sucessor nomeado, e é ato do operador.
9. **O `--explain-ledger` vive em `/tmp`.** Copiei para o host da VPS (`/tmp/sweep_reclaim_v1_*.jsonl`)
   porque o `/tmp` de container morre com o container, mas `/tmp` do host também não é arquivo. Se
   esse ledger tiver de sobreviver, alguém precisa decidir onde ele mora — hoje o durável é
   `replay_runs` + `agent_signals`, e o "porquê de cada barra" só existe nesse JSONL.

---

## 13. O QUE EU FARIA A SEGUIR

1. **Arquivar o adendo do §9 no `EXP-0017`** (Sexta-feira), com `result: inconclusivo`,
   `evaluable: 48`, `days: 15`, e a linha no `Registro de Tentativas`.
2. **Não abrir prospectiva.** O estresse disse `sem_vantagem_na_base`, e o funil existe para que esse
   veredito economize 30 dias de calendário.
3. **Se a hipótese merecer uma segunda chance, o caminho é o controle, não o parâmetro.** Um braço
   "varreu e não recuperou" sobre as mesmas 1 196 barras responde a pergunta que o EXP fez e que este
   replay não respondeu. É EXP novo, com portão próprio.
4. **E a pergunta que ultrapassa esta tarefa, pela terceira vez:** quatro mercados não produzem
   estatística em tempo útil para nenhuma candidata desta família. **A conversa sobre o universo é a
   alavanca**, e ela é do Everton.
