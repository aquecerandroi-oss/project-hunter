# T3.46 — o Radar prevê alguma coisa? (anomalias + score de oportunidade × Lab × retorno futuro)

**Owner:** quant-engineer · **Data:** 2026-09-08 · **Base:** `main` @ `c9691d0` · **Nada foi
commitado.** Estudo somente leitura. Todas as leituras de banco em
`begin transaction isolation level repeatable read read only` contra a VPS
(`docker exec -i hunter-postgres-1 psql -U hunter -d hunter`), primeiro plano, nenhuma acima de
40 s.

`read_at` das leituras: **2026-09-08 22:16 → 22:37 UTC** (19:16 → 19:37 de Brasília).

---

## STATUS

**DONE_WITH_CONCERNS.** As três perguntas do brief foram respondidas com SQL colado, mas a resposta
honesta para duas delas é *"o dado ainda não existe em quantidade que permita concluir"* — e isso é
resultado, não desculpa: o Radar tem **1,8 dia de histórico** e cobre **25 de 217 mercados
monitorados**. O que dá para afirmar com número está abaixo; o que não dá está declarado como tal.

---

## INVENTÁRIO

### O que é o Radar hoje

| peça | onde | estado medido |
|---|---|---|
| baselines (mediana + MAD, 7 d, mesma hora) | `scanner-worker`, tabela `feature_baselines` | 274 596 linhas, 261 mercados, **4,28 % passam o gate** da `opportunity_weights` v2 (`distinct_days >= 3` e `sample_size >= 120`) |
| detectores de anomalia | `scanner-worker` (PIPELINE §3), tabela `anomalies` | 1 292 linhas, **4 dos 12 tipos do enum** produziram alguma coisa |
| score de oportunidade | `scanner-worker` (PIPELINE §5), `opportunities` + `opportunity_history` | 390 episódios, 20 392 amostras, **score máximo já observado = 38,33** |
| página Radar / Opportunities | `apps/api/hunter_api/routers/radar.py`, `opportunities.py`, `anomalies.py` | lê exatamente essas tabelas |
| quem consome o Radar para decidir | — | **ninguém** |

**O fato que precisa ser dito primeiro:** `StrategyContext`
(`packages/core/hunter_core/strategies/base.py:109`) tem sete campos — `exchange`, `symbol`,
`source_bar_close`, `candles_1m`, `funding`, `open_interest`, `eligible`/`eligibility_reason`. **Não
há campo de Radar.** E `grep -r "opportunit\|anomal" services/strategy-worker/` não encontra
arquivo nenhum. Nenhuma estratégia do Lab — prospectiva ou replay — pode estar usando o Radar hoje,
nem por acidente. O único parâmetro que existiria para isso é `agent_configs.min_opportunity_score`
(`packages/core/hunter_core/db/models/agents.py:308`), que é do caminho de proposta do M4 e não é
lido por serviço nenhum.

### Arquivos escritos (nenhum commitado)

- `infra/scripts/sql/research/2026-09-09-radar-01-inventario.sql`
- `infra/scripts/sql/research/2026-09-09-radar-02-lab.sql`
- `infra/scripts/sql/research/2026-09-09-radar-03-retorno-futuro.sql`
- `infra/scripts/sql/research/2026-09-09-radar-04-populacao-csv.sql`
- `infra/scripts/sql/research/2026-09-09-radar-05-retorno-futuro-csv.sql`
- `infra/scripts/sql/research/2026-09-09-radar-06-cobertura.sql`
- `.claude/state/exp-drafts/KB-0078-o-radar-preve.md`
- `.claude/state/notes-T3.46.md` (este arquivo)
- saídas cruas: `.claude/state/t346/out-01.txt`, `out-02.txt`, `out-03.txt`, `out-06.txt`,
  `pop.csv` (176 linhas), `fwd.csv` (39 986 linhas)
- scripts de bootstrap (temporários, fora do repositório):
  `%TEMP%\t346\bootstrap_t346.py` e `%TEMP%\t346\bootstrap_fwd.py` — ambos importam
  `.claude/state/exp-drafts/t342-blocos/blocos.py` **sem alterá-lo**

---

## TABELAS

### T1 — Quanto Radar existe (Q1)

```bash
ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" \
  < infra/scripts/sql/research/2026-09-09-radar-01-inventario.sql
```

```
== 1a. anomalias por dia (UTC) ==
+------------+-----------+----------+-------+-----------+---------+
|    dia     | anomalias | mercados | tipos | sev_media | sev_max |
+------------+-----------+----------+-------+-----------+---------+
| 2026-09-07 |       788 |       26 |     4 |       5.4 |  100.00 |
| 2026-09-08 |       499 |       19 |     4 |       6.6 |  100.00 |
+------------+-----------+----------+-------+-----------+---------+

== 1b. anomalias por tipo (janela inteira) ==
+----------------------+-----+----------+-----------+---------+---------+------------+--------+------------+-----------+---------------+
|         tipo         |  n  | mercados | sev_media | sev_p50 | sev_max | conf_media | ativas | resolvidas | expiradas | dado_suspeito |
+----------------------+-----+----------+-----------+---------+---------+------------+--------+------------+-----------+---------------+
| VOLUME_SPIKE         | 575 |       26 |       2.2 |     0.0 |   92.20 |      0.463 |      6 |        553 |        16 |            16 |
| MOMENTUM_SHIFT       | 335 |       20 |       4.8 |     0.0 |  100.00 |      0.462 |      6 |        309 |        20 |            21 |
| PRICE_ACCELERATION   | 329 |       20 |       5.1 |     0.0 |  100.00 |      0.459 |      5 |        309 |        15 |            16 |
| VOLATILITY_EXPANSION |  48 |       13 |      61.1 |    76.2 |  100.00 |      0.441 |      5 |         14 |        29 |            21 |
+----------------------+-----+----------+-----------+---------+---------+------------+--------+------------+-----------+---------------+

== 1d. cobertura: mercados monitorados x mercados com anomalia x com score ==
+-------------+--------------+------------------+--------------+
| monitorados | com_anomalia | com_oportunidade | com_baseline |
+-------------+--------------+------------------+--------------+
|         217 |           26 |               26 |          261 |
+-------------+--------------+------------------+--------------+

== 3b. o score é ranqueado? faixas do Radar (PIPELINE §5) ==
+---------------+----------+--------+
|     faixa     | amostras |  pct   |
+---------------+----------+--------+
| a) <40 NORMAL |    20392 | 100.00 |
+---------------+----------+--------+

== 3. decis do score (sobre opportunity_history, a série completa) ==
+-------+----------+-----------+-----------+-------------+
| decil | amostras | score_min | score_max | score_medio |
+-------+----------+-----------+-----------+-------------+
|     1 |     2040 |      0.00 |      0.00 |        0.00 |
|     2 |     2040 |      0.00 |      1.90 |        0.77 |
|     3 |     2039 |      1.90 |      3.90 |        3.05 |
|     4 |     2039 |      3.90 |      5.00 |        4.33 |
|     5 |     2039 |      5.00 |      6.34 |        5.56 |
|     6 |     2039 |      6.34 |      8.19 |        7.29 |
|     7 |     2039 |      8.20 |     10.47 |        9.44 |
|     8 |     2039 |     10.47 |     13.66 |       11.97 |
|     9 |     2039 |     13.66 |     18.25 |       15.57 |
|    10 |     2039 |     18.25 |     38.33 |       22.54 |
+-------+----------+-----------+-----------+-------------+

== 5. baselines: cobertura e maturidade ==
+---------------+------------+-----------+--------+----------+----------+-----------------+----------------------+
| algo_version  | amostragem |   fonte   | linhas | mercados | features | cobertura_media | dias_distintos_media |
+---------------+------------+-----------+--------+----------+----------+-----------------+----------------------+
| median_mad_v1 | per_minute | live      | 194389 |      261 |       24 |           0.126 |                 1.39 |
| median_mad_v1 | per_minute | bootstrap |  80207 |      206 |       15 |           0.260 |                 1.84 |
+---------------+------------+-----------+--------+----------+----------+-----------------+----------------------+
```

Três leituras que mandam no resto da nota:

1. **O Radar tem 1,8 dia de vida.** Primeira anomalia em `2026-09-07 02:24:01Z`, primeira amostra de
   score em `2026-09-07 02:40:20Z`. Antes disso as tabelas estão vazias — não porque o mercado
   estivesse calmo, mas porque ninguém estava medindo.
2. **A página "Opportunities" nunca teve um candidato.** O maior score já gravado é **38,33**, e o
   primeiro degrau do §5 (`WATCHING`) é **40**. 100 % das 20 392 amostras estão em `NORMAL`.
   `HOT` (75) e `ENTRY_CANDIDATE` (80) são, hoje, faixas que o produto desenha e que o dado nunca
   alcançou. O ranqueamento existe (o decil 10 vai a 38, o decil 1 fica em 0), mas ele ranqueia
   dentro de uma faixa que o próprio sistema chama de "nada acontecendo".
3. **Severidade quase sempre é 0.** A mediana de `VOLUME_SPIKE`, `MOMENTUM_SHIFT` e
   `PRICE_ACCELERATION` é **0,0** — porque `anomalies.severity` é *mutável* (o §3 atualiza a linha
   enquanto o episódio dura) e o que está gravado é a severidade do **fim**. Consequência prática, e
   é séria: **não existe no schema a severidade que a anomalia tinha no instante da decisão.** Todo
   este estudo usa apenas `detected_at` e `type`, que são imutáveis; usar `severity` seria
   antecipação pura.

### T2 — Por que só 25 mercados (Q1, diagnóstico)

```bash
ssh hunter-vps "docker exec -i hunter-postgres-1 psql ... -f -" \
  < infra/scripts/sql/research/2026-09-09-radar-06-cobertura.sql
```

```
== 1. os mercados com anomalia, com a posicao alfabetica deles no universo monitorado ==
| posicao |    symbol     | exchange | anomalias |
|       1 | 0GUSDT        | binance  |        63 |
|       2 | 1000BONKUSDT  | binance  |        68 |
|       3 | 1000CATUSDT   | binance  |        38 |
|       4 | 1000FLOKIUSDT | binance  |        78 |
|       6 | 1000PEPEUSDT  | binance  |        86 |
|       7 | 1000SHIBUSDT  | binance  |        87 |
|       8 | 4USDT         | binance  |        65 |
|       9 | AAVEUSDT      | binance  |        66 |
|      10 | ACEUSDT       | binance  |        55 |
|      12 | ADAUSDT       | binance  |        74 |
|      13 | AEROUSDT      | binance  |        68 |
|      16 | AKEUSDT       | binance  |        51 |
|      17 | ALGOUSDT      | binance  |        79 |
|      18 | APRUSDT       | binance  |        82 |
|      19 | APTUSDT       | binance  |        83 |
|      20 | ARBUSDT       | binance  |        83 |
|      22 | ARUSDT        | binance  |        78 |
|      40 | BTCUSDT       | binance  |        55 |
|     206 | ZECUSDT       | binance  |        17 |
|     210 | ZKCUSDT       | binance  |         1 |
|     211 | ZKUSDT        | binance  |         1 |
|     212 | ZORAUSDT      | binance  |         2 |
|     213 | ZROUSDT       | binance  |         1 |
|     216 | 牛来USDT      | binance  |         2 |
|     217 | 龙虾USDT      | binance  |         1 |
(25 rows)

== 2. a cobertura e um prefixo alfabetico? ==
| monitorados | cobertos | primeira_posicao | ultima_posicao | cobertos_no_top30_alfabetico | cobertos_nas_30_ultimas |
|         217 |       25 |                1 |            217 |                           17 |                       7 |

== 3. baselines utilizaveis (gate da opportunity_weights v2: distinct_days>=3 e sample_size>=120) ==
| linhas_baseline | passam_o_gate | pct  | mercados | mercados_com_alguma_baseline_valida |
|          274596 |         11754 | 4.28 |      261 |                                 163 |

== 4. os detectores que existem no enum contra os que produziram linha ==
| VOLUME_SPIKE              |    580 |
| MOMENTUM_SHIFT            |    335 |
| PRICE_ACCELERATION        |    331 |
| VOLATILITY_EXPANSION      |     48 |
| CROSS_EXCHANGE_DIVERGENCE |      0 |
| FUNDING_ANOMALY           |      0 |
| LIQUIDATION_CLUSTER       |      0 |
| OPEN_INTEREST_SPIKE       |      0 |
| ORDERBOOK_IMBALANCE       |      0 |
| SOCIAL_SPIKE              |      0 |
| TRADE_VELOCITY_SPIKE      |      0 |
| WHALE_ACTIVITY            |      0 |
```

A cobertura **não é uma escolha de risco nem um filtro de liquidez**: 17 dos 25 mercados cobertos
estão entre os 30 primeiros em ordem alfabética e 7 entre os 30 últimos. É uma janela que anda em
volta do universo ordenado. O heartbeat do scanner confirma a causa (leitura, `redis-cli hgetall
hb:scanner:a97f07636e72:1`, 2026-09-08 22:36 UTC):

```
markets                       200
baselines_usable             9029
baselines_under_construction 102597     -> 8,1 % utilizáveis
baselines_state              "bootstrapping 1000FLOKIUSDT (4/200)"
anomalies_open                 10
detectors_disarmed  CROSS_EXCHANGE_DIVERGENCE:single_exchange_until_m1b=200,
                    FUNDING_ANOMALY:funding_unavailable=200,
                    LIQUIDATION_CLUSTER:feature_not_implemented=200
```

O Radar está em **aquecimento de baselines**, no mercado 4 de 200, e três detectores estão
desarmados por design declarado. Isto explica de uma vez a cobertura (25/217), o score teto de 38
(componente sem baseline é `None` e o peso dele é redistribuído — §4b item 4 — então a nota final
nunca sobe) e a severidade mediana 0.

### T3 — O Radar separa os desfechos do Lab? (Q2)

```bash
ssh hunter-vps "docker exec -i hunter-postgres-1 psql ... -f -" \
  < infra/scripts/sql/research/2026-09-09-radar-02-lab.sql
```

```
== 1. populacao: quanto do Lab cai na janela do Radar, e quanto e coberto ==
+-------------+-----------+----------+-------------+----------+-------------------+
|   coorte    | desfechos | cobertos | pct_coberto | mercados | mercados_cobertos |
+-------------+-----------+----------+-------------+----------+-------------------+
| prospective |      3195 |      176 |         5.5 |      247 |                20 |
| replay      |        24 |        0 |         0.0 |        4 |                 0 |
+-------------+-----------+----------+-------------+----------+-------------------+

== 3. COM anomalia x SEM anomalia, so onde o Radar estava olhando (pooled) ==
+---------------+--------------+-----+------+-----------+-------------+------------+-------+--------+
|    janela     | tem_anomalia |  n  | dias | exp_bruto | exp_liquido | acerto_pct |  pf   | soma_r |
+---------------+--------------+-----+------+-----------+-------------+------------+-------+--------+
| 4b (60min)    | f            |  35 |    2 |   -0.0195 |     -0.1479 |       37.1 | 0.702 |  -5.18 |
| 4b (60min)    | t            | 141 |    2 |    0.0775 |     -0.1722 |       31.2 | 0.710 | -24.28 |
| 16b (240min)  | f            |  23 |    1 |    0.2558 |      0.1469 |       52.2 | 1.451 |   3.38 |
| 16b (240min)  | t            | 153 |    2 |    0.0285 |     -0.2146 |       29.4 | 0.649 | -32.84 |
| 96b (1440min) | t            | 176 |    2 |    0.0582 |     -0.1674 |       32.4 | 0.708 | -29.46 |
+---------------+--------------+-----+------+-----------+-------------+------------+-------+--------+

== 5. por TIPO de anomalia nos 240 min (coberto) ==
+----------------------+-----+-------------+------------+--------+
|         tipo         |  n  | exp_liquido | acerto_pct | soma_r |
+----------------------+-----+-------------+------------+--------+
| VOLUME_SPIKE         | 152 |     -0.2215 |       28.9 | -33.66 |
| MOMENTUM_SHIFT       | 124 |     -0.1874 |       32.3 | -23.23 |
| PRICE_ACCELERATION   | 116 |     -0.2534 |       31.0 | -29.40 |
| VOLATILITY_EXPANSION |  66 |     -0.0854 |       30.3 |  -5.63 |
| SEM_ANOMALIA         |  23 |      0.1469 |       52.2 |   3.38 |
+----------------------+-----+-------------+------------+--------+

== 6/6b/7. decis do score na decisao, Spearman e o corte do quartil ==
+------------------------+-----+-----------+-----------+-----------+-------------+------------+--------+----------+
|         faixa          |  n  | score_min | score_max | exp_bruto | exp_liquido | acerto_pct | soma_r | spearman |
+------------------------+-----+-----------+-----------+-----------+-------------+------------+--------+----------+
| Q1-Q3 (75%)            | 132 |      0.00 |     20.86 |   -0.0357 |     -0.2576 |       28.0 | -34.00 |          |
| Q4 top 25%             |  44 |     20.86 |     37.71 |    0.3400 |      0.1032 |       45.5 |   4.54 |          |
| SPEARMAN score x r_net | 176 |           |           |           |             |            |        |  -0.0896 |
| decil 1                |  18 |      0.00 |      3.90 |    0.1597 |      0.0086 |       33.3 |   0.16 |          |
| decil 2                |  18 |      3.90 |      5.60 |    0.4742 |      0.3447 |       38.9 |   6.20 |          |
| decil 3                |  18 |      5.60 |      8.57 |   -0.1422 |     -0.3862 |       27.8 |  -6.95 |          |
| decil 4                |  18 |      8.58 |     10.73 |   -0.2956 |     -0.5245 |       16.7 |  -9.44 |          |
| decil 5                |  18 |     10.80 |     15.00 |   -0.0818 |     -0.3133 |       27.8 |  -5.64 |          |
| decil 6                |  18 |     15.00 |     16.95 |   -0.0447 |     -0.2957 |       33.3 |  -5.32 |          |
| decil 7                |  17 |     17.33 |     19.98 |   -0.2050 |     -0.5226 |       17.6 |  -8.88 |          |
| decil 8                |  17 |     20.00 |     21.13 |    0.1294 |     -0.0638 |       47.1 |  -1.09 |          |
| decil 9                |  17 |     21.61 |     25.21 |    0.2946 |     -0.0281 |       47.1 |  -0.48 |          |
| decil 10               |  17 |     25.42 |     37.71 |    0.3099 |      0.1164 |       35.3 |   1.98 |          |
+------------------------+-----+-----------+-----------+-----------+-------------+------------+--------+----------+

== 8. CONTAMINACAO DE COBERTURA: o mesmo contraste sem exigir cobertura (NAO usar) ==
+--------------+------+-------------+------------+
| tem_anomalia |  n   | exp_liquido | acerto_pct |
+--------------+------+-------------+------------+
| f            | 3003 |     -0.2614 |       30.5 |
| t            |  216 |     -0.2047 |       30.1 |
+--------------+------+-------------+------------+
```

**O tamanho da amostra é o resultado principal.** De 6 283 desfechos do Lab, só **176** têm o Radar
efetivamente olhando o mesmo mercado no instante da decisão — **5,5 %** da população prospectiva
dentro da janela, **0 %** de qualquer replay (o replay opera 4 mercados que o Radar não cobre, e o
Radar não existia nas datas replayadas). Duas consequências:

- na janela de 96 barras **todos os 176** têm anomalia: não há grupo de controle, o contraste é
  indefinido;
- o único contraste com os dois lados razoavelmente povoados (16 b) tem **n = 23** do lado "sem
  anomalia", concentrados em **um** dia. Uma diferença de +0,36 R construída sobre 23 decisões de um
  dia não é achado; é ruído com número.

**Decomposição por cobertura, para não confundir as duas coisas.** A tabela 8 mostra o que aconteceria
se alguém rodasse o contraste ignorando a cobertura: −0,2614 R (sem anomalia) contra −0,2047 R (com
anomalia), 3 003 contra 216 — pareceria que a anomalia *ajuda*. Não ajuda: os 3 003 "sem anomalia"
são majoritariamente mercados que o scanner nunca olhou. Esse contraste mede **cobertura**, não
previsão, e está aqui exatamente para ninguém repetir o erro.

### T4 — O contraste sobrevive ao bootstrap por blocos? (Q2)

`%TEMP%\t346\bootstrap_t346.py` importa `.claude/state/exp-drafts/t342-blocos/blocos.py` sem
alterá-lo: `contraste_por_piso` define a variante como o subconjunto do pai com `atr_pct >= piso`, e
aqui o campo `atr_pct` carrega um **indicador 0/1** (gate ligado/desligado) com `piso = 0.5`. O Δ
medido é o mesmo do T3.42: `média(variante) − média(pai)` na **mesma** reamostragem.

**Desvio declarado:** o t342 reamostra **dias**. A janela do Radar tem **2 dias**. Reamostrar 2
blocos não produz intervalo com significado, então rodei os dois e mostro os dois — o de dia fica
como prova da degeneração, o de **hora** (38 blocos) é o que deve ser lido.

```bash
uv run python %TEMP%\t346\bootstrap_t346.py .claude/state/t346/pop.csv
```

```
# linhas=176  arquivo=.claude\state\t346\pop.csv
gate: anomalia <=60min (4b)        | bloco=dia  blocos=  2 | n_pai= 176 n_var= 141 | exp_pai=-0.1674 exp_var=-0.1722 | delta=-0.0048 | IC95=[-0.2130; +0.0543] | reamostragens=10000
gate: anomalia <=240min (16b)      | bloco=dia  blocos=  2 | n_pai= 176 n_var= 153 | exp_pai=-0.1674 exp_var=-0.2146 | delta=-0.0472 | IC95=[-0.2156; +0.0000] | reamostragens=10000
gate: anomalia <=1440min (96b)     | bloco=dia  blocos=  2 | n_pai= 176 n_var= 176 | exp_pai=-0.1674 exp_var=-0.1674 | delta=+0.0000 | IC95=[+0.0000; +0.0000] | reamostragens=10000
gate: SEM anomalia <=240min        | bloco=dia  blocos=  2 | n_pai= 176 n_var=  23 | exp_pai=-0.1674 exp_var=+0.1469 | delta=+0.3143 | IC95=[+0.3143; +0.4500] | reamostragens=7490
gate: score >= 20.86 (Q4)          | bloco=dia  blocos=  2 | n_pai= 176 n_var=  46 | exp_pai=-0.1674 exp_var=+0.0495 | delta=+0.2169 | IC95=[-0.0483; +0.4073] | reamostragens=10000
gate: score >= 10                  | bloco=dia  blocos=  2 | n_pai= 176 n_var= 114 | exp_pai=-0.1674 exp_var=-0.2109 | delta=-0.0435 | IC95=[-0.2278; +0.0659] | reamostragens=10000

gate: anomalia <=60min (4b)        | bloco=hora blocos= 38 | n_pai= 176 n_var= 141 | exp_pai=-0.1674 exp_var=-0.1722 | delta=-0.0048 | IC95=[-0.1186; +0.0996] | reamostragens=10000
gate: anomalia <=240min (16b)      | bloco=hora blocos= 38 | n_pai= 176 n_var= 153 | exp_pai=-0.1674 exp_var=-0.2146 | delta=-0.0472 | IC95=[-0.1556; +0.0265] | reamostragens=10000
gate: anomalia <=1440min (96b)     | bloco=hora blocos= 38 | n_pai= 176 n_var= 176 | exp_pai=-0.1674 exp_var=-0.1674 | delta=+0.0000 | IC95=[+0.0000; +0.0000] | reamostragens=10000
gate: SEM anomalia <=240min        | bloco=hora blocos= 38 | n_pai= 176 n_var=  23 | exp_pai=-0.1674 exp_var=+0.1469 | delta=+0.3143 | IC95=[-0.2669; +0.7754] | reamostragens=10000
gate: score >= 20.86 (Q4)          | bloco=hora blocos= 38 | n_pai= 176 n_var=  46 | exp_pai=-0.1674 exp_var=+0.0495 | delta=+0.2169 | IC95=[-0.2169; +0.6006] | reamostragens=10000
gate: score >= 10                  | bloco=hora blocos= 38 | n_pai= 176 n_var= 114 | exp_pai=-0.1674 exp_var=-0.2109 | delta=-0.0435 | IC95=[-0.1939; +0.0704] | reamostragens=10000
```

**Todos os seis intervalos por hora cruzam o zero.** Inclusive os dois que "pareciam bons" na tabela
pontual: "sem anomalia" (+0,3143 R) tem IC95 `[−0,2669; +0,7754]` e "score no quartil de cima"
(+0,2169 R) tem IC95 `[−0,2169; +0,6006]`. Repare no bloco de **dia**: ali o "sem anomalia" aparece
com IC `[+0,3143; +0,4500]`, que **exclui** o zero — e é exatamente o artefato que o bloco de dia
produz quando existem 2 blocos e o subconjunto vive dentro de um só deles. Se este estudo tivesse
parado na primeira tabela, teria anunciado um achado inexistente.

**Monotonicidade do score: não há.** Spearman = **−0,0896** entre score na decisão e `r_net`
(n = 176). Os decis sobem, descem e sobem de novo (decil 2 = +0,34 R, decil 4 = −0,52 R, decil 10 =
+0,12 R); a soma de R é negativa em 7 dos 10 decis. Não é uma escada com barulho — é barulho.

### T5 — A anomalia carrega informação sozinha, sem estratégia? (Q3)

```bash
ssh hunter-vps "docker exec -i hunter-postgres-1 psql ... -f -" \
  < infra/scripts/sql/research/2026-09-09-radar-03-retorno-futuro.sql
```

```
== 1. retorno futuro depois da anomalia x base pareada (pooled, ponderado por mercado) ==
+-----------+---------+-------------+----------+------------------+--------------+----------------------+------------------+
| horizonte | eventos | barras_base | mercados | ret_anomalia_pct | ret_base_pct | mov_abs_anomalia_pct | mov_abs_base_pct |
+-----------+---------+-------------+----------+------------------+--------------+----------------------+------------------+
| H = 1h    |    1247 |       37959 |       26 |          -0.1160 |       0.0213 |               1.0287 |           0.9915 |
| H = 4h    |    1090 |       36569 |       26 |           0.0034 |       0.0616 |               1.7936 |           1.9378 |
| H = 24h   |     679 |        8888 |       19 |           0.9454 |       1.5311 |               3.9783 |           3.7298 |
+-----------+---------+-------------+----------+------------------+--------------+----------------------+------------------+

== 2. o mesmo por TIPO de anomalia ==
+----------------------+------+------------+----------------+------+------------+----------------+
|         tipo         | n_1h | ret_1h_pct | mov_abs_1h_pct | n_4h | ret_4h_pct | mov_abs_4h_pct |
+----------------------+------+------------+----------------+------+------------+----------------+
| VOLUME_SPIKE         |  554 |    -0.0837 |         0.9804 |  491 |     0.0739 |         1.7524 |
| PRICE_ACCELERATION   |  324 |    -0.1029 |         1.0550 |  273 |    -0.1026 |         1.8440 |
| MOMENTUM_SHIFT       |  324 |    -0.1551 |         1.0707 |  283 |    -0.0083 |         1.7405 |
| VOLATILITY_EXPANSION |   45 |    -0.3277 |         1.1323 |   43 |    -0.0528 |         2.2951 |
+----------------------+------+------------+----------------+------+------------+----------------+

== 3. a direcao declarada pelo detector acerta o sinal do retorno? ==
+---------+------+---------------------+------------+------------+
| direcao | n_1h | acerto_sinal_1h_pct | ret_1h_pct | ret_4h_pct |
+---------+------+---------------------+------------+------------+
| down    |  648 |                54.6 |    -0.0816 |     0.0508 |
| up      |  598 |                45.3 |    -0.1530 |    -0.0507 |
| flat    |    1 |                 0.0 |    -0.3422 |     1.5058 |
+---------+------+---------------------+------------+------------+

== 4. quantos eventos perdem horizonte por falta de vela ==
| anomalias | com_vela_no_minuto | com_1h | com_4h | com_24h |
|      1292 |               1292 |   1247 |   1088 |     679 |
```

E o mesmo contraste com intervalo, blocos de **hora**, estimador pareado por mercado idêntico ao da
consulta 03 (`%TEMP%\t346\bootstrap_fwd.py`, 2 000 reamostragens):

```bash
uv run python %TEMP%\t346\bootstrap_fwd.py .claude/state/t346/fwd.csv
```

```
H = 1h | com sinal | blocos= 44 n_anom= 1247 n_base= 37974 | delta=-0.1375pp | IC95=[-0.3759pp; +0.1246pp] | reamostragens=2000
H = 1h | absoluto  | blocos= 44 n_anom= 1247 n_base= 37974 | delta=+0.0374pp | IC95=[-0.1165pp; +0.1980pp] | reamostragens=2000

H = 4h | com sinal | blocos= 41 n_anom= 1093 n_base= 36577 | delta=-0.0615pp | IC95=[-0.6098pp; +0.4927pp] | reamostragens=2000
H = 4h | absoluto  | blocos= 41 n_anom= 1093 n_base= 36577 | delta=-0.1459pp | IC95=[-0.4215pp; +0.1179pp] | reamostragens=2000
```

Esta é a leitura mais limpa da nota, porque **não depende do Lab**: 1 247 eventos contra 37 974
barras de base do mesmo mercado, na mesma janela, sem estratégia no meio.

- **Direção:** não há. O retorno médio 1 h depois da anomalia é −0,116 % contra +0,021 % da base;
  IC95 do contraste `[−0,376 pp; +0,125 pp]`, cruza o zero.
- **Movimento:** também não. O movimento absoluto 1 h depois é 1,029 % contra 0,992 % da base — um
  ganho de **0,037 pp** com IC95 `[−0,117 pp; +0,198 pp]`. Em 4 h o sinal **inverte** (1,79 %
  contra 1,94 %). Uma anomalia não marca sequer uma barra mais movimentada do que a média do mesmo
  mercado.
- **O rótulo de direção do detector é pior que moeda no lado que importa:** anomalias marcadas `up`
  são seguidas de −0,153 % em 1 h e acertam o sinal em **45,3 %** das vezes; as `down` acertam
  54,6 %. Ou seja: o único sinal levemente consistente é *contrário* ao rótulo `up`, e some no
  agregado. Com 598 e 648 eventos isso é medida, não anedota — mas é medida de **ausência**.

---

## VEREDITO (português simples, ≤ 10 linhas)

1. **Não. O Radar hoje não prevê nada — nem o retorno do mercado, nem o resultado do Lab.**
2. Depois de uma anomalia, a próxima hora do mercado é indistinguível de uma hora qualquer do mesmo
   mercado: +0,037 pp de movimento a mais, com intervalo `[−0,12; +0,20]`. Em 4 h fica pior.
3. O rótulo de direção da anomalia acerta 45 % quando diz "sobe". Isso é pior que cara-ou-coroa.
4. O score de oportunidade não ordena nada: correlação de posto **−0,09** com o resultado, e os
   decis pulam para cima e para baixo sem ordem.
5. Nenhum tipo, nenhuma janela (4, 16 ou 96 barras) e nenhum decil sobrevive ao bootstrap por blocos.
6. **E a razão principal é que o Radar mal existe ainda:** 1,8 dia de histórico, 25 de 217 mercados,
   8 % das baselines prontas, 3 detectores desarmados, 8 dos 12 tipos sem uma única linha.
7. O score máximo já gravado é **38** e o primeiro degrau da página é **40** — a lista de
   oportunidades nunca teve um item; a página ranqueia ruído dentro da faixa "nada acontecendo".
8. Só **176** dos 6 283 desfechos do Lab dão para cruzar com o Radar. Isso não é amostra para
   decidir estratégia; é amostra para decidir se vale continuar medindo.
9. **Nada disto diz que a ideia do Radar está errada.** Diz que ela ainda não foi testada.
10. Testar de verdade custa **esperar as baselines maturarem**, não escrever código de estratégia.

### Recomendação: **(b) rebaixar a painel — por 14 dias, com uma condição de reabertura escrita**

Contra a opção (a) — variante gated pelo Radar — há três argumentos, nesta ordem:

1. **Não há parâmetro para isso.** `StrategyContext` não tem campo de Radar e nenhuma versão viva
   tem parâmetro de score ou de anomalia. A variante exigiria **um campo novo no contexto**
   (`radar_gate`), o que muda a assinatura que todas as versões vivas usam, invalida o digest do
   catálogo e obriga a reemitir as versões — custo alto, em cima de 176 observações.
2. **O gate seria míope por construção.** Um `radar_gate` só teria valor em 25 dos 217 mercados;
   nos outros 192 ele responderia "não sei", e uma estratégia que não decide onde o Radar é cego
   perde 88 % da população.
3. **A pergunta é de dado, não de estratégia.** Enquanto 96 % das baselines não passarem o gate, o
   score é uma soma de componentes ausentes com o peso redistribuído. Gatear por ele é gatear pela
   ordem alfabética do bootstrap.

O que fazer, concretamente:

- **Manter o Radar rodando e a página no ar, como painel de observação.** Ele é barato e é a única
  série que enxerga o universo inteiro; desligá-lo joga fora o relógio junto com o aquecimento.
- **Marcar a página com o que ela é hoje.** A faixa `WATCHING/HOT/ENTRY_CANDIDATE` nunca acendeu;
  mostrar degraus que o dado não alcança treina o operador a desconfiar do produto inteiro.
- **Não investir em `radar_gate`, em detector novo nem em ajuste de peso agora.**
- **Condição de reabertura, escrita para não virar "quando der":** repetir **exatamente** estas seis
  consultas quando (i) `feature_baselines` tiver ≥ 60 % das linhas passando o gate da v2 **e**
  (ii) `anomalies` cobrir ≥ 150 mercados **e** (iii) houver ≥ 14 dias de série. Com isso o
  contraste "com/sem anomalia" teria ordem de 3 000 desfechos cobertos e 14 blocos de dia — aí o
  bootstrap do T3.42 responde de verdade e a decisão (a)/(b) se toma com dado.
- **Um item que não espera:** investigar por que `ORDERBOOK_IMBALANCE`, `OPEN_INTEREST_SPIKE` e
  `TRADE_VELOCITY_SPIKE` não produzem linha **sem** aparecerem em `detectors_disarmed`. Os três
  desarmados têm motivo declarado; estes três estão silenciosos sem motivo, e silêncio sem motivo é
  o defeito que este projeto combate por escrito em todo lugar.

---

## CONCERNS

1. **`anomalies.severity` é mutável e não há histórico.** A linha guarda a severidade do fim do
   episódio, então "qual era a severidade quando a decisão foi tomada" **não é respondível pelo
   schema**. Este estudo contornou usando só `detected_at` e `type`, mas isso proíbe para sempre o
   corte mais óbvio ("só anomalias com severidade ≥ 60", que é justamente o gatilho do status
   `ANOMALY` no §5). Sugestão para a Sexta-feira: uma tabela de amostras de severidade (o análogo de
   `opportunity_history` para anomalias) ou `peak_severity`/`severity_at_detection` imutável na
   própria linha. Sem isso, o Radar nunca será auditável retroativamente.
2. **A recomendação (b) apoia-se em ausência de evidência, e ausência de evidência aqui é
   principalmente ausência de dado.** Está escrito assim de propósito, com a condição de reabertura
   quantificada. Se a Astra discordar do desenho, o ponto a atacar é a definição de `coberto`
   (amostra de `opportunity_history` nos 15 min anteriores) — é a única escolha do estudo que muda a
   população de forma material.
3. **Bloco de hora em vez de bloco de dia.** Desvio do T3.42, forçado por só existirem 2 dias. Blocos
   de hora subestimam a dependência intradiária (um choque de 4 h atravessa 4 blocos), então os IC
   de hora são **otimistas** — e ainda assim todos cruzam o zero. A conclusão é robusta ao desvio; a
   direção do viés está declarada.
4. **Pareamento sem hora do dia.** O Q3 pareia por mercado e janela, não por hora do dia. Com 1,8 dia
   não há célula por hora. Se o padrão de anomalias for concentrado em certas horas (e a tabela 1a
   sugere que 2026-09-07 teve 788 e 2026-09-08 teve 499), parte do contraste pode ser hora do dia.
   Reabrir com 14 dias resolve.
5. **`SEM_ANOMALIA` na tabela T3 (n = 23, 1 dia) é a única célula com expectancy positiva do estudo
   inteiro.** Ela não sobrevive ao bootstrap por hora, mas alguém lendo só a tabela pontual pode
   concluir "operar quando o Radar está quieto". Registrado aqui explicitamente para que a leitura
   errada não circule.
6. **Duplicidade de símbolos em `markets`.** `BTCUSDT` e `ZECUSDT` aparecem duas vezes no universo
   monitorado (linhas por exchange). Não afeta nenhum número desta nota (todo join é por
   `market_id`), mas a primeira versão da consulta 06 contava posições por símbolo e produzia
   28 linhas para 25 mercados. Corrigido; fica registrado porque qualquer consulta futura que
   agrupe por `symbol` vai tropeçar no mesmo lugar.
7. **`markets.is_monitored` = 217 e o heartbeat do scanner diz `markets = 200`.** Não investiguei a
   diferença de 17; ela não muda nenhuma conclusão (a cobertura é 25 em qualquer dos dois
   denominadores), mas é uma divergência real entre o que o banco chama de universo e o que o
   scanner acha que é o universo.
