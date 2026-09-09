# T3.46b — três detectores do Radar produziam zero sem motivo declarado

**Owner:** quant-engineer · **Data:** 2026-09-08 (Brasília) · **Base:** `main` @ `402c56b` ·
**Nada foi commitado.** Árvore compartilhada: outros agentes têm mudanças em voo nela.

Leituras da VPS: **21:24 → 21:57 de Brasília (00:24 → 00:57 UTC do dia 09)**, todas em
`begin transaction isolation level repeatable read read only`, primeiro plano, nenhuma acima de
40 s. Redis apenas com `hgetall`/`get`. Nenhum container foi parado, recriado ou alterado.

---

## STATUS

**DONE.** Os três detectores foram diagnosticados com número, a causa de cada um está isolada, e o
silêncio acabou: depois desta mudança **nenhum dos doze `AnomalyType` pode ficar mudo sem motivo**,
porque o motivo passa a ser lido do próprio veredito que o detector já produzia e ninguém publicava.
Duas ressalvas honestas estão em CONCERNS — a principal é que **nenhum dos três vai emitir hoje**, e
eu digo exatamente quando cada um pode emitir, com data e hora, para a previsão ser conferível.

---

## 1. DIAGNÓSTICO, COM EVIDÊNCIA

### 1.1 O que o banco diz (linhas por tipo, série inteira)

```bash
ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" \
  < infra/scripts/sql/research/2026-09-09-t346b-01-detectores-mudos.sql
```

```
== 1. anomalias por tipo (toda a serie) ==
+---------------------------+--------+----------+-------------------------------+
|           type            | linhas | mercados |           primeira            |
+---------------------------+--------+----------+-------------------------------+
| VOLUME_SPIKE              |    620 |       26 | 2026-09-07 02:24:01.934013+00 |
| MOMENTUM_SHIFT            |    354 |       20 | 2026-09-07 03:45:04.325126+00 |
| PRICE_ACCELERATION        |    352 |       20 | 2026-09-07 03:46:08.333561+00 |
| VOLATILITY_EXPANSION      |     51 |       13 | 2026-09-07 03:45:04.325126+00 |
| ORDERBOOK_IMBALANCE       |      0 |        0 |                               |
| OPEN_INTEREST_SPIKE       |      0 |        0 |                               |
| FUNDING_ANOMALY           |      0 |        0 |                               |
| LIQUIDATION_CLUSTER       |      0 |        0 |                               |
| CROSS_EXCHANGE_DIVERGENCE |      0 |        0 |                               |
| TRADE_VELOCITY_SPIKE      |      0 |        0 |                               |
| SOCIAL_SPIKE              |      0 |        0 |                               |
| WHALE_ACTIVITY            |      0 |        0 |                               |
+---------------------------+--------+----------+-------------------------------+
```

Heartbeat no mesmo minuto (`redis-cli hgetall hb:scanner:a589720a71fb:1`, 21:24 BRT):

```
markets                       200
baselines_usable            12052
baselines_under_construction 101718
anomalies_open                 27
detectors_disarmed  CROSS_EXCHANGE_DIVERGENCE:single_exchange_until_m1b=200,
                    FUNDING_ANOMALY:funding_unavailable=197,
                    LIQUIDATION_CLUSTER:feature_not_implemented=200
baselines_state     "bootstrapping 1000FLOKIUSDT (4/200)"
```

`OPEN_INTEREST_SPIKE` **não** aparece como desarmado — ou seja, está armado nos 200 mercados
(`detector_roster` rearmou porque `DerivHistory` tem leituras). `ORDERBOOK_IMBALANCE` e
`TRADE_VELOCITY_SPIKE` nunca foram desarmáveis por construção. Os três estavam **armados e mudos**.
`SOCIAL_SPIKE` e `WHALE_ACTIVITY` estavam pior: **fora do roster**, e um tipo fora do roster não
produz avaliação nenhuma, logo não consegue nem se declarar.

### 1.2 A feature é calculada? (`feature_snapshots`, últimas 24 h)

```bash
ssh hunter-vps "... -f -" < infra/scripts/sql/research/2026-09-09-t346b-03-features-vivas.sql
```

```
== 1. qualidade por feature na ultima hora (feature_snapshots -> values) ==
+-------------------------+--------+-------+----------+-------------+-------------+
|         feature         | linhas |  ok   | degraded | unavailable | mercados_ok |
+-------------------------+--------+-------+----------+-------------+-------------+
| open_interest_change_1h |  12002 | 11851 |        0 |         151 |         200 |
| trade_velocity_1m       |  12002 | 11758 |        0 |         244 |         201 |
| orderbook_imbalance_20  |  12002 |   281 |        0 |       11721 |         100 |
| spread_pct              |  12002 |   281 |        0 |       11721 |         100 |
| relative_volume_5m      |  12002 | 11850 |        0 |         152 |         198 |
+-------------------------+--------+-------+----------+-------------+-------------+

== 2. motivo da indisponibilidade, por feature (ultima hora) ==
+-------------------------+-----------------------+-------+
|         feature         |        motivo         |   n   |
+-------------------------+-----------------------+-------+
| orderbook_imbalance_20  | after_cut             | 11717 |
| spread_pct              | after_cut             | 11717 |
| open_interest_change_1h | warmup                |    81 |
| open_interest_change_1h | missing_input         |    70 |
| trade_velocity_1m       | insufficient_coverage |   243 |
+-------------------------+-----------------------+-------+

== 3. distribuicao dos valores (ultima hora, quality=ok) ==
| open_interest_change_1h | 11851 | min -0.031988 | p50 -0.000044 | p99 0.036700 | max 0.147043 |
| orderbook_imbalance_20  |   281 | min -0.699641 | p50  0.049919 | p99 0.655149 | max 0.789156 |
| trade_velocity_1m       | 11758 | min  0.000000 | p50  0.516667 | p99 16.031   | max 32.716667|
```

**Primeira separação: dois detectores enxergam, um não enxerga.** `trade_velocity_1m` e
`open_interest_change_1h` têm valor bom em 98 % dos minutos, em 200 mercados. `orderbook_imbalance_20`
está indisponível em **97,7 %** dos minutos, sempre pelo mesmo motivo: `after_cut`.

### 1.3 Por que o livro é `after_cut` — a corrida está medida

O snapshot de livro no Redis carrega o **relógio da exchange** (`ts` do `depth`) e a avaliação corta
em `as_of = covered_until` (a prova de cobertura do coletor, `PIPELINE.md` §2). `decode_book` recusa
o snapshot quando `ts > as_of` — e isso é **correto**: usar um livro carimbado depois do próprio
corte é antecipação, ainda que de milissegundos. Oito leituras pareadas (21:41 BRT):

```
book ts                             covered_until                        delta
2026-09-09T00:41:14.068000+00:00    2026-09-09T00:41:14.130847+00:00     -63 ms (livro antes: usável)
2026-09-09T00:41:17.595000+00:00    2026-09-09T00:41:17.593201+00:00      +2 ms (livro depois: recusado)
2026-09-09T00:41:25.153000+00:00    2026-09-09T00:41:25.034415+00:00    +119 ms
2026-09-09T00:41:32.224000+00:00    2026-09-09T00:41:32.172377+00:00     +52 ms
2026-09-09T00:41:37.765000+00:00    2026-09-09T00:41:37.532669+00:00    +232 ms
2026-09-09T00:41:40.789000+00:00    2026-09-09T00:41:40.389047+00:00    +400 ms
2026-09-09T00:41:43.813000+00:00    2026-09-09T00:41:43.916780+00:00    -104 ms (usável)
2026-09-09T00:41:47.847000+00:00    2026-09-09T00:41:47.788980+00:00     +58 ms
```

Não é um bug do detector nem do cálculo do desequilíbrio: é uma corrida sub-segundo entre dois
carimbos que o `market-worker` escreve de forma independente. O livro ganha na maioria das vezes, e
a feature de livro deixa de existir. **A consequência não é só do Radar:** `spread_pct` cai junto, e
os dois alimentam os componentes *Liquidity* e *Order Flow* do score de oportunidade (§5).

### 1.4 A baseline passa o portão? (o que realmente cala os outros dois)

```bash
ssh hunter-vps "... -f -" < infra/scripts/sql/research/2026-09-09-t346b-05-corte-causal.sql
```

Esta consulta reproduz o detector em SQL **sob o corte causal exato** do `BaselineProjection`
(`available_at <= observation_ts` **e** `window_end < observation_ts`, escolhendo a revisão vencedora
com o mesmo `DISTINCT ON` do `select_projection`), sobre as 6 h anteriores:

```
== 3. reproducao sob o corte causal, ultimas 6 h ==
+-------------------------+--------------+--------+---------+-------+---------------+
|         feature         | com_baseline | usavel | imatura | fires | mercados_fire |
+-------------------------+--------------+--------+---------+-------+---------------+
| relative_volume_5m      |        54470 |   6487 |   47983 |   960 |            23 |
| atr_14_pct              |        43401 |   5406 |   37995 |  1505 |             9 |
| momentum_15m            |        43212 |   5391 |   37821 |   513 |            18 |
| momentum_acceleration   |        43212 |   5391 |   37821 |   479 |            16 |
| open_interest_change_1h |        61794 |      0 |   61794 |     0 |             0 |
| trade_velocity_1m       |        58889 |      0 |   58889 |     0 |             0 |
| orderbook_imbalance_20  |         1286 |      0 |    1286 |     0 |             0 |
+-------------------------+--------------+--------+---------+-------+---------------+

== 4. anomalias abertas nas ultimas 6 h (o que o scanner de fato gravou) ==
| VOLUME_SPIKE 124 (23 mercados) | PRICE_ACCELERATION 81 (16) | MOMENTUM_SHIFT 71 (18) |
| VOLATILITY_EXPANSION 8 (7) |
```

A reprodução bate com a realidade em ordem de grandeza nos quatro que emitem (23 mercados previstos
contra 23 gravados no `VOLUME_SPIKE`; 18 contra 18 no `MOMENTUM_SHIFT`) — o que valida o método — e
diz **zero** para os três calados: em ~60 mil avaliações de 6 h, **nenhuma** teve baseline utilizável.

**A causa é estrutural, não aleatória.** As quatro features que emitem têm baseline de fonte
`bootstrap`; as três caladas, não:

```
== 5. features com baseline, por fonte (out-01) ==
bootstrap (15): atr_14_pct, breakout_strength_20, distance_from_24h_high/low, momentum_15m,
                momentum_acceleration, relative_volume_5m/15m/1h, return_1m/5m/15m/1h/4h,
                volume_acceleration
live      (24): as de cima (menos as de 24 h) + buy/sell_pressure_5m, funding_rate,
                open_interest_change_1h/4h, orderbook_imbalance_20, spread_pct, trade_velocity_1m,
                return_*_live
```

O bootstrap replaya **velas persistidas**, e velas não reproduzem livro, fita nem histórico de
derivativos — é a exclusão declarada em `baselines/bootstrap.py`
(`historical_source_unavailable`, `semantic_equivalence_unproven`). Então as três features caladas
dependem **só** do refresh horário ao vivo. E o refresh horário recalcula **apenas o balde da hora
que acabou de fechar**:

```
== buckets que passam o portao da v2, por feature e hora (leitura de 21:57 BRT / 00:57 UTC) ==
+-------------------------+-------------+----------+-------------------------------+
|         feature         | hour_of_day | mercados |         publicado_em          |
+-------------------------+-------------+----------+-------------------------------+
| trade_velocity_1m       |          18 |      157 | 2026-09-08 19:01:34.797773+00 |
| trade_velocity_1m       |          19 |      157 | 2026-09-08 20:01:52.040927+00 |
| open_interest_change_1h |          19 |      157 | 2026-09-08 20:01:52.040927+00 |
| open_interest_change_1h |          20 |      157 | 2026-09-08 21:02:02.337908+00 |
| open_interest_change_1h |          21 |      157 | 2026-09-08 22:01:58.528465+00 |
| open_interest_change_1h |          22 |      156 | 2026-09-08 23:02:30.553108+00 |
| open_interest_change_1h |          23 |      156 | 2026-09-09 00:00:35.907083+00 |
| orderbook_imbalance_20  |     (nenhum bucket passa o portao em nenhuma hora)      |
+-------------------------+-------------+----------+-------------------------------+

== buckets utilizaveis para a HORA CORRENTE (hour_of_day = 0), por feature ==
atr_14_pct 23 | breakout_strength_20 23 | momentum_15m 23 | momentum_acceleration 23 |
relative_volume_5m 23 | relative_volume_15m 23 | return_* 23 | relative_volume_1h 20 | ...
(trade_velocity_1m, open_interest_change_1h e orderbook_imbalance_20: ZERO)
```

**Aqui está a resposta inteira.** Uma revisão publicada às `HH:01` descreve o balde da hora `HH-1`,
e um balde de hora `H` só serve observações cuja `hour_of_day` é `H` — ou seja, **as do dia
seguinte**. Os primeiros baldes maduros de `trade_velocity_1m` nasceram às 16:01 de Brasília de hoje
(19:01 UTC) para a hora 18 UTC; a próxima vez que existirá uma observação na hora 18 UTC é
**amanhã**. Enquanto isso, os quatro detectores que emitem usam baselines de `bootstrap`, cujo
`window_end` está no passado e que por isso servem qualquer hora imediatamente.

Não é defeito: é a consequência aritmética de um refresh por balde horário somado a uma série de
**2,28 dias** (`feature_snapshots` começa em 2026-09-06 15:17 BRT). Mas era invisível, e é isso que
esta tarefa conserta.

### 1.5 Previsão conferível (o teste desta nota)

| detector | primeira janela em que **pode** emitir | mercados elegíveis |
|---|---|---|
| `TRADE_VELOCITY_SPIKE` | **2026-09-09, 15:00–17:00 BRT** (18:00–20:00 UTC) | até 157 |
| `OPEN_INTEREST_SPIKE` | **2026-09-09, 16:00–21:00 BRT** (19:00–24:00 UTC) | até 157 |
| `ORDERBOOK_IMBALANCE` | ~**2026-09-13**, e 4× mais esparso (ver 1.6) | ~236, poucos baldes cada |

Se em 2026-09-09 depois das 17:00 BRT a tabela `anomalies` continuar com zero linhas de
`TRADE_VELOCITY_SPIKE`, **este diagnóstico está errado** e o próximo passo é instrumentar
`evaluate_detector` no processo, não repetir SQL.

### 1.6 O livro alcança o portão algum dia?

```bash
ssh hunter-vps "... -f -" < infra/scripts/sql/research/2026-09-09-t346b-06-livro-teto.sql
```

```
== 1. janela realmente preenchida ==
primeira 2026-09-06 18:17 UTC | ultima 2026-09-09 00:56 UTC | dias_de_serie 2.28

== 2. disponibilidade de orderbook_imbalance_20 (24 h) ==
pct_ok_global 7.72 | mercados_com_algum_ok 235 | mercados 235

== 3. por mercado: faixa de taxa de ok x sample_size ja alcancado ==
faixa 0-10%  : 194 mercados (0,5% a 9,9%)  sample_max 61
faixa 10-20% :  36 mercados (10,1% a 17,2%) sample_max 63
faixa 20-30% :   5 mercados (20,2% a 24,3%) sample_max 56

== 4. buckets de livro que passariam se a taxa de hoje valer 7 dias ==
buckets 8480 | passam_hoje 0 | passariam_em_7d 2160 | mercados_em_7d 236

== 5. controle ==
open_interest_change_1h  10545 buckets | passam_hoje 2307 | passariam_em_7d 10271
trade_velocity_1m         9407 buckets | passam_hoje  539 | passariam_em_7d  8870
relative_volume_5m       13213 buckets | passam_hoje 4817 | passariam_em_7d 11566
```

Extrapolando linearmente a taxa medida para uma janela de 7 dias cheia (**é extrapolação, está
declarada como tal**): 2 160 de 8 480 baldes de livro passariam — **25 %**, contra 94 % da fita e
97 % do OI. `ORDERBOOK_IMBALANCE` portanto **não** está permanentemente bloqueado, mas nasce
estruturalmente ~4× mais esparso que os irmãos, e a causa disso é a corrida de carimbo da §1.3, não
o mercado.

---

## 2. O CONSERTO

Escolhi a segunda opção do brief — **o heartbeat declara o motivo** — e não a primeira (fazer o
detector emitir), por um motivo que o próprio diagnóstico impõe: **não há nada para consertar no
detector.** Os três estão certos. Dois esperam baseline (a espera é aritmética e tem data), e o
terceiro esbarra num contrato de cobertura que vive no `market-worker`, fora do escopo deste brief e
cuja "correção" ingênua — aceitar um livro carimbado depois do corte — seria antecipação.

O que mudou, em três peças:

**(a) O roster passa a cobrir os doze tipos.** `SOCIAL_SPIKE` e `WHALE_ACTIVITY` entram registrados e
desarmados com `feature_not_implemented`, apontando para as features que a ingestão deles teria de
criar (`social_mention_velocity`, `whale_net_flow_1h`). Estar fora do roster era a pior forma de
silêncio: sem avaliação, sem linha no heartbeat, e a faixa do Radar os pintava como "silencioso sem
motivo" para sempre. Nenhuma versão existente mudou de significado; `DETECTOR_VERSION` continua `v1`
porque nenhum limiar e nenhuma fórmula foram tocados — dois detectores novos ganharam identidade
própria (`SOCIAL_SPIKE@v1`, `WHALE_ACTIVITY@v1`) e não podem disparar enquanto `enabled=False`.

**(b) `detectors_disarmed` deixa de ser só "capacidade do deploy".** Antes, o campo vinha de
`deriv.disarmed_reasons(roster)`, que só sabia de **uma** das formas de calar (o deploy não tem a
evidência). Agora vem de `hunter_indicators.anomalies.silence.silence_reasons`, que lê o **veredito
que `evaluate_detector` já produzia e ninguém publicava**. Nada novo é calculado — é a regra que
importa: um segundo diagnóstico teria liberdade para discordar da decisão que diz explicar.
Vocabulário publicado: `baselines_under_construction`, `baseline_absent`,
`baseline_version_mismatch`, `baseline_without_dispersion`, `data_degraded`, `no_data`,
`feature_not_in_vector` e `feature_*` para o que falhou do lado da entrada (`feature_after_cut`,
`feature_warmup`, `feature_insufficient_coverage`, …). Os motivos de capacidade que já existiam
passam **inalterados** (`funding_unavailable`, `deriv_history_unavailable`,
`single_exchange_until_m1b`, `feature_not_implemented`), porque um detector desarmado carrega a
própria frase e repeti-la com outra palavra daria dois nomes a um fato.

**(c) Duas coisas que este módulo deliberadamente NÃO reporta.** Uma avaliação `ok` nunca entra,
qualquer que seja a severidade: severidade 0 é **resposta** ("o mercado está normal"), não ausência
de resposta, e transformá-la em alarme treinaria o operador a ignorar a faixa. E um detector com
anomalia `active` também não entra, mesmo com a leitura do minuto cega: ele está produzindo, e o
`AnomalyAction.HOLD` existe exatamente para isso — rotulá-lo de "em aquecimento" esconderia um
episódio vivo.

Efeito prático quando o orquestrador subir esta versão: o campo sai de 3 entradas para 12, e a faixa
de cobertura do Radar (T3.46c) fica **sem nenhum detector na classe "silencioso sem motivo"**.

A string abaixo é uma **projeção aritmética, não uma medição** — a VPS ainda roda a versão antiga.
Ela sai de três números medidos hoje às 21:57 BRT: (i) 200 mercados perpétuos; (ii) para a hora
corrente (0 UTC) existem **23** baldes utilizáveis das features de bootstrap, logo 200 − 23 = 177
mercados sem baseline madura nelas — e dos 23, os que estiverem com anomalia aberta ou com leitura
crível saem da lista, então 177 é **piso**, não valor exato; (iii) o livro está `after_cut` em
97,7 % das leituras, ou seja ~195 dos 200 num instante qualquer, e os ~5 restantes caem em
`baselines_under_construction` porque nenhum balde de livro passa o portão:

```
CROSS_EXCHANGE_DIVERGENCE:single_exchange_until_m1b=200,
FUNDING_ANOMALY:funding_unavailable=197,
LIQUIDATION_CLUSTER:feature_not_implemented=200,
MOMENTUM_SHIFT:baselines_under_construction=177,
OPEN_INTEREST_SPIKE:baselines_under_construction=200,
ORDERBOOK_IMBALANCE:feature_after_cut=195,
PRICE_ACCELERATION:baselines_under_construction=177,
SOCIAL_SPIKE:feature_not_implemented=200,
TRADE_VELOCITY_SPIKE:baselines_under_construction=200,
VOLATILITY_EXPANSION:baselines_under_construction=177,
VOLUME_SPIKE:baselines_under_construction=177,
WHALE_ACTIVITY:feature_not_implemented=200
```

A conferência depois do deploy é direta: `redis-cli hgetall hb:scanner:*` tem de trazer os doze
tipos, e `ORDERBOOK_IMBALANCE` tem de aparecer com `feature_after_cut` na esmagadora maioria dos
mercados. Se vier diferente, a §1 está errada em algum ponto e o número dirá qual.

**(d) A tela acompanha.** `apps/web/components/radar/radar-coverage-format.ts` já renderizava motivo
desconhecido como `motivo técnico: <código>`; as vinte palavras novas ganharam frase em português
(D19: nada de `snake_case` na tela), com teste.

---

## 3. OS 17 MERCADOS (concern 7 da T3.46) — resolvido, sem conserto

`markets.is_monitored = 217` e o heartbeat do scanner diz `markets = 200`. Não há divergência:

```
== 7b. is_monitored por exchange e tipo ==
+---------+-------------+-------------+-------+
|  code   | market_type | monitorados | total |
+---------+-------------+-------------+-------+
| binance | perpetual   |         200 |   528 |
| binance | spot        |          17 |   487 |
+---------+-------------+-------------+-------+
```

217 = **200 perpétuos + 17 spot**. O scanner lê o universo por
`registry.load_universe`, que filtra `Market.market_type == MarketType.PERPETUAL` — os 17 spot são o
**caminho de dados SPOT** do `PIPELINE.md` §1d (preço de execução do wallet, coletado pelo
`market-worker-spot`), que nunca teve Radar por desenho. Os dois números estão certos e medem coisas
diferentes; o erro foi do denominador de quem comparou (eu, na T3.46). **Não há conserto a fazer** —
o que havia era uma frase, e ela está aqui e na T3.46b. A nota da T3.46 fica com o concern 7 marcado
como respondido por esta.

---

## 4. PROVA

### Testes novos

```bash
uv run pytest packages/indicators/tests/unit/test_anomaly_silence.py -q
```
```
...........                                                              [100%]
11 passed in 6.73s
```

```bash
uv run pytest services/scanner-worker/tests/test_detector_silence.py -q -p no:randomly
```
```
...                                                                      [100%]
3 passed in 7.05s
```

O segundo arquivo reproduz **a forma que a VPS mede** (fita e OI com valor bom, baseline viva com
`sample_size=61`/`distinct_days=2`, livro em `after_cut`) e vai até a string publicada no Redis,
afirmando que `set(entries) == {todos os doze AnomalyType}`.

### Suítes afetadas

```bash
uv run pytest packages/indicators/tests/unit -q
```
```
990 passed in 29.24s
```

```bash
uv run pytest services/scanner-worker/tests -q -p no:randomly \
  --ignore=.../test_load.py --ignore=.../test_baseline_loop.py --ignore=.../test_beta_job.py \
  --ignore=.../test_regime_job.py --ignore=.../test_bootstrap.py --ignore=.../test_baseline_refresh.py
```
```
102 passed in 66.79s (0:01:06)
```

Testcontainers, **um arquivo por invocação, dois arquivos no total** (regra do brief):

```bash
uv run pytest services/scanner-worker/tests/test_pipeline.py -q -p no:randomly
```
```
........                                                                 [100%]
8 passed in 7.33s
```

```bash
uv run pytest services/scanner-worker/tests/test_persistence.py -q -p no:randomly
```
```
........                                                                 [100%]
8 passed in 40.54s
```

Consumidores do vocabulário (API e web):

```bash
uv run pytest apps/api/tests/unit/test_radar_coverage_service.py -q
```
```
............                                                             [100%]
12 passed in 0.68s
```

```bash
cd apps/web && npx vitest run tests/radar-coverage-format.test.ts
```
```
 Test Files  1 passed (1)
      Tests  21 passed (21)
   Duration  6.92s
```

### Portões

```bash
uv run ruff check services packages
```
```
All checks passed!
```

```bash
uv run ruff format --check services/scanner-worker packages/indicators
```
```
212 files already formatted
```

```bash
uv run pyright services/scanner-worker packages/indicators
```
```
0 errors, 0 warnings, 0 informations
```

```bash
uv run python infra/scripts/check_file_size.py
```
```
scanned 580 files; 0 over budget, 0 grandfathered
```

```bash
cd apps/web && npx tsc --noEmit && npx eslint components/radar/radar-coverage-format.ts tests/radar-coverage-format.test.ts
```
```
(sem saída — limpo)
```

**Ressalva de árvore compartilhada:** `uv run ruff format --check` sobre a árvore inteira acusa
**6 arquivos**, todos de outro agente em voo e nenhum meu (`infra/scripts/backfill_funding.py`,
`infra/scripts/request_backfill.py`, `infra/scripts/tests/test_request_backfill.py`,
`packages/core/tests/unit/test_settings.py`,
`services/market-worker/hunter_market_worker/funding_announce.py`,
`services/market-worker/tests/test_funding_backfill.py`). O mesmo vale para 9 erros de `pyright` em
`apps/api/tests/integration/test_lab_signals_pagination_api.py`, arquivo que não toquei. Não mexi em
nenhum deles.

---

## 5. ARQUIVOS

### Código (nada commitado)

| arquivo | o quê |
|---|---|
| `packages/indicators/hunter_indicators/anomalies/silence.py` | **novo.** O vocabulário do silêncio: `silence_reason` / `silence_reasons`, puros |
| `packages/indicators/hunter_indicators/anomalies/detectors.py` | `SOCIAL_SPIKE` e `WHALE_ACTIVITY` registrados e desarmados (`feature_not_implemented`) |
| `packages/indicators/hunter_indicators/anomalies/__init__.py` | reexporta a quarta camada |
| `services/scanner-worker/hunter_scanner_worker/evaluate.py` | `Evaluation.anomaly_evaluations` — os vereditos saem do passo puro |
| `services/scanner-worker/hunter_scanner_worker/scanner.py` | `market.disarmed` passa a vir de `silence_reasons`, depois da avaliação |
| `services/scanner-worker/hunter_scanner_worker/deriv.py` | `disarmed_reasons` removida (ficou sem chamador em produção; o docstring diz por quê) |
| `docs/PIPELINE.md` | §3, um parágrafo |
| `apps/web/components/radar/radar-coverage-format.ts` | frases em português para os motivos novos |

### Testes

- `packages/indicators/tests/unit/test_anomaly_silence.py` (novo, 11 casos)
- `services/scanner-worker/tests/test_detector_silence.py` (novo, 3 casos)
- `packages/indicators/tests/unit/test_anomaly_detectors.py` (o roster virou "os oito armados" + "todo tipo do enum tem detector")
- `apps/web/tests/radar-coverage-format.test.ts` (as classes novas não podem sair em `snake_case`)

### Consultas e saídas cruas

- `infra/scripts/sql/research/2026-09-09-t346b-01-detectores-mudos.sql`
- `infra/scripts/sql/research/2026-09-09-t346b-02-snapshots-e-severidade.sql`
- `infra/scripts/sql/research/2026-09-09-t346b-03-features-vivas.sql`
- `infra/scripts/sql/research/2026-09-09-t346b-04-severidade-reproduzida.sql`
- `infra/scripts/sql/research/2026-09-09-t346b-05-corte-causal.sql`
- `infra/scripts/sql/research/2026-09-09-t346b-06-livro-teto.sql`
- `.claude/state/t346b/out-01.txt` … `out-07.txt`

---

## 6. CONCERNS

1. **Nenhum dos três emite hoje, e a entrega não faz nenhum emitir.** O que a entrega faz é acabar
   com o silêncio mudo. Se a expectativa era ver linha de `TRADE_VELOCITY_SPIKE` amanhã de manhã,
   a resposta honesta é: **15:00 de Brasília de 09/09** é o mais cedo possível, e a razão está na
   §1.4. Registrado como previsão falseável de propósito.
2. **A extrapolação do livro (§1.6) é linear e de 2,28 dias para 7.** Se a taxa de `after_cut` piorar
   com mais mercados ou com carga, o número cai. Ela está aqui porque a alternativa era dizer
   "eventualmente" — e "eventualmente" é o que esta tarefa combate.
3. **A corrida de carimbo do livro (§1.3) não foi consertada e o conserto não é do scanner.** Ela
   custa hoje 97,7 % das leituras de `orderbook_imbalance_20` **e de `spread_pct`**, o que atinge os
   componentes *Liquidity* e *Order Flow* do score de oportunidade — provavelmente parte da razão de
   o score nunca ter passado de 38 (T3.46). Duas saídas possíveis, ambas no `market-worker`/coverage:
   carimbar `covered_until` **depois** da escrita do livro no mesmo ciclo de coalescência, ou dar às
   features de livro uma tolerância declarada (como o checkpoint de ATR já tem). **Recomendo abrir
   tarefa própria**; não fiz nada aqui porque o escopo do brief é `services/scanner-worker/**` e
   `packages/indicators/anomalies/**`, e porque a mudança certa é uma decisão de contrato, não um
   ajuste.
4. **Cardinalidade da métrica.** `hunter_scanner_detectors_disarmed{type,reason}` sai de ~3 séries
   para no máximo 12 × ~15 = 180. `_DISARMED_SEEN` já zera as que somem, então não vaza; mas é um
   aumento real e fica declarado.
5. **O campo do heartbeat cresce de ~120 para ~600 caracteres.** Nenhum consumidor tem limite (o
   parser da API é `split(",")`), mas quem ler `hgetall` na mão vai ver uma linha longa.
6. **`market.disarmed` mudou de significado, não só de conteúdo.** Antes era "capacidade que falta
   no deploy" (estável por horas); agora é "por que este detector não produziu **neste ciclo**", que
   oscila com o dado. O nome do campo continua `detectors_disarmed` por compatibilidade com a API e
   com a faixa do Radar — mas "desarmado" agora inclui "cego neste minuto". Se isso incomodar na
   revisão, o caminho limpo é um campo novo (`detectors_mute`) e deixar `detectors_disarmed` só com
   as capacidades; custa uma mudança no schema da API e na faixa, e eu não a fiz por conta própria.
7. **Não foi validado contra a VPS depois do deploy.** A VPS segue rodando `7e9d59c`; nada foi
   commitado nem publicado. A contagem de `anomalies` por tipo depois do deploy é o passo que fecha
   a prova, e ela depende do orquestrador.
