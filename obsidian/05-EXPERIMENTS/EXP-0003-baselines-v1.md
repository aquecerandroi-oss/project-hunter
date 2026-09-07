---
tags: [experimento, baselines, m2, mercado]
updated: 2026-09-07
status: aberto
---

# EXP-0003 — baselines por ativo e hora (M2), e o que elas destravam

> Aberto em **2026-09-07** pela T2.8 (`docs/plans/M2.md`), com a reserva do ID feita em
> 2026-09-05 e registrada em [[Experiments Index]], `docs/plans/SHADOW-LAB.md` (item 11) e
> `docs/plans/M2.md`. Hipótese e Protocolo abaixo são **congelados**; avaliações são
> **acrescentadas** e datadas, nunca reescritas. Relatório do milestone:
> `docs/reports/M2.md`.

**Este experimento é de outro tipo que o [[EXP-0001-momentum-v1]] e o
[[EXP-0002-volume-anomaly-v1]].** Não mede uma estratégia contra o mercado: mede um **instrumento**
— o arquivo de baselines por (mercado, feature, hora UTC) do M2 — e o que ele destrava rio abaixo
(anomalias, estágio, regime, score). Por isso as métricas em R e de carteira do
[[_TEMPLATE-EXP|template]] são **não aplicáveis** aqui, e estão marcadas assim em vez de
preenchidas com um número que não significaria nada. As regras que continuam valendo integralmente
são as do protocolo geral: SQL colado, `as_of` e `read_at` separados, todo número com denominador,
limiar editorial, e nada é ativado automaticamente.

## Hipótese (congelada)

Baselines por (mercado, feature, hora UTC), construídas por bootstrap sobre candles persistidas e
mantidas por refresh horário, **amadurecem rápido o bastante para o Radar do M2 produzir score,
estágio e anomalias com dado real** — isto é: um número materialmente maior que zero das 27 features
registradas passa o portão de maturidade (≥ 3 dias distintos **e** ≥ 120 observações) num número
materialmente maior que zero dos 200 mercados monitorados, em dias e não em semanas.

O ponto que a hipótese tenta refutar é o mais provável: que o bootstrap sobre candles cubra só a
metade "de barra" do vetor de features e deixe **tape, livro e derivativos** — que são metade do
peso do score — dependentes de uma semana de coleta ao vivo, tornando o Radar aritmeticamente
incapaz de chegar a HOT durante todo o M2.

## Protocolo (congelado — nunca editar)

- **Instrumento:** `hunter_indicators.baselines` (T2.3, `72cfe72`) escrito pelo
  `services/scanner-worker` (T2.5, `551d542`, e sucessoras até `9ceb389`).
- **Versões carimbadas em cada leitura:** `features = a2b12fcdbd8431a1d5b731191007c1ae9b3e6542e08be176aa8a507b090cac51`
  · `scorer = opportunity_v1` · `weights = v2` · `normalization = mad_piecewise_v1@v2` ·
  `components = components_v1` · `stage = v2` · `regime = regime_v0` · `quality_policy = quality_v1`.
- **Estatística:** mediana e MAD **exatas**, ambas em `Decimal`, sobre janela semiaberta
  `[window_start, window_end)` de 7 dias, 420 observações esperadas por bucket
  (mercado, feature, hora UTC).
- **Imutabilidade:** `feature_baselines` só recebe INSERT. Cada revisão carrega
  `available_at`, `window_start/end`, `sample_size`, `expected_size`, `distinct_days`, `coverage`,
  `source` (`bootstrap` | `live`), `sampling`, `input_fingerprint`.
- **Corte causal duplo, aplicado pelo leitor:** `available_at <= as_of` **E**
  `window_end < observation_ts`. Nenhuma leitura deste experimento pode usar revisão publicada
  depois do seu `as_of`.
- **Portão de maturidade (o gate desta medição):** `distinct_days >= 3` **E** `sample_size >= 120`,
  exatamente como a decisão conjunta do M2 fixou. O portão é do **leitor**, nunca um booleano
  congelado na linha.
- **Revisão vigente:** para cada (mercado, feature, hora) vale a de maior `available_at` dentro do
  corte — `DISTINCT ON (market_id, feature, hour_of_day) … ORDER BY available_at DESC`.
- **População:** os mercados `is_monitored` da Binance USDS-M perpétuos USDT (200), nos dois
  ambientes, **contados separadamente** — a VPS e o stack local são bancos e coortes distintos e
  não se somam nem se continuam.
- **Métricas primárias:** revisões vigentes · buckets utilizáveis · fração utilizável ·
  mercados com ≥ 1 bucket utilizável, por feature · buckets com `MAD = 0` · cobertura média.
- **Métricas secundárias (o que a baseline destrava):** anomalias por tipo e status · componentes
  disponíveis por oportunidade e o **teto aritmético de score** que eles implicam contra os
  limiares ativos de `opportunity_weights` · distribuição de `stage` em `opportunity_history` ·
  rótulo e motivo do regime vigente.
- **Limiar editorial:** abaixo de **3 dias distintos de série viva por feature medida** o `Result`
  desta página só pode ser `inconclusivo` para a hipótese principal. Fatos já decididos por
  aritmética (como um teto de score) são registrados como fato, não como conclusão do experimento.
- **Nada é ativado:** nenhuma avaliação desta página altera peso, limiar ou `strategy_version`.
  Reparametrizar é ato auditado e é decisão do Everton.
- **Data de início da coleta:** bootstrap a partir de **2026-09-06** (T2.5b); série de
  `feature_snapshots` ao vivo na VPS a partir de **2026-09-06T18:17:00Z**.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-07 — `as_of = 2026-09-07T03:30:00Z`, `read_at = 2026-09-07T03:24:49Z`

**Ambiente:** VPS de produção (`hunter-postgres-1`), head `0005_baseline_lock_grant`, 200 mercados
monitorados, `scanner-worker` no ar há 4 h, Postgres há 28 h. Números do stack local ao lado, como
segunda população — **não** como continuação da série.

**Nota de leitura, dura:** `as_of` congela a população (`available_at <= as_of`); `read_at` é
quando as linhas foram lidas. `anomalies` e `opportunities` avançam **no lugar** — a leitura abaixo
não é reconstruível depois, exatamente como já está registrado para o Shadow Lab.

**SQL usado** (`docker exec -i hunter-postgres-1 psql -U hunter -d hunter -f -`):

```sql
-- A. população de baselines com o corte causal e o portão do leitor
with latest as (
  select distinct on (market_id, feature, hour_of_day)
         market_id, feature, hour_of_day, sample_size, distinct_days, coverage, source, mad
  from feature_baselines
  where available_at <= timestamptz '2026-09-07T03:30:00Z'
  order by market_id, feature, hour_of_day, available_at desc
)
select count(*) as revisoes_vigentes,
       count(*) filter (where distinct_days >= 3 and sample_size >= 120) as utilizaveis,
       count(distinct market_id) as mercados,
       count(distinct feature) as features,
       count(*) filter (where mad = 0) as mad_zero,
       round(avg(coverage),4) as cobertura_media
from latest;

-- B. utilizáveis por feature (o resultado que decide a hipótese)
with latest as (
  select distinct on (market_id, feature, hour_of_day)
         market_id, feature, hour_of_day, sample_size, distinct_days, source
  from feature_baselines
  where available_at <= timestamptz '2026-09-07T03:30:00Z'
  order by market_id, feature, hour_of_day, available_at desc
)
select feature, count(*) as buckets,
       count(*) filter (where distinct_days >= 3 and sample_size >= 120) as utilizaveis,
       count(distinct market_id) filter (where distinct_days >= 3 and sample_size >= 120)
         as mercados_utilizaveis
from latest group by 1 order by 3 desc;

-- C/D/E/F/G: anomalias, oportunidades, estágios, componentes e snapshots
-- (consultas completas no corpo desta avaliação, abaixo)
```

**Saída real, A — a população:**

```
 revisoes_vigentes | utilizaveis | mercados | features | mad_zero | cobertura_media
-------------------+-------------+----------+----------+----------+-----------------
             88746 |        4944 |      211 |       27 |     1521 |          0.2032
```

**Saída real, B — utilizáveis por feature** (27 linhas, agrupadas aqui pelo que a coluna
`mercados_utilizaveis` diz; a saída bruta preserva a ordem por `utilizaveis desc`):

| Feature | Buckets | Utilizáveis | Mercados utilizáveis |
|---|---|---|---|
| `return_15m` · `volume_acceleration` · `return_5m` · `return_1m` | 4.946–4.948 | 436 cada | **29** |
| `return_1h` | 4.940 | 421 | 29 |
| `relative_volume_5m` | 4.928 | 406 | 26 |
| `atr_14_pct` · `momentum_acceleration` · `momentum_15m` · `return_4h` | 4.906–4.907 | 374 cada | **18** |
| `breakout_strength_20` | 4.889 | 362 | 18 |
| `relative_volume_15m` | 4.884 | 350 | 18 |
| `relative_volume_1h` · `distance_from_24h_high` · `distance_from_24h_low` | 4.372 cada | 55 cada | 14 |
| `return_1h_live` · `return_1m_live` · `return_5m_live` · `return_15m_live` | 1.495–1.788 | **0** | **0** |
| `open_interest_change_1h` · `open_interest_change_4h` · `funding_rate` | 1.558–1.800 | **0** | **0** |
| `spread_pct` · `orderbook_imbalance_20` | 1.798 cada | **0** | **0** |
| `trade_velocity_1m` · `buy_pressure_5m` · `sell_pressure_5m` | 393–398 | **0** | **0** |

**Saída real, C — anomalias:**

```
     type     |  status  | count | sev_min | sev_max |           primeira            |            ultima
--------------+----------+-------+---------+---------+-------------------------------+-------------------------------
 VOLUME_SPIKE | resolved |    12 |     0.0 |    18.6 | 2026-09-07 02:24:01.934013+00 | 2026-09-07 03:10:07.941234+00
 VOLUME_SPIKE | active   |     3 |     0.0 |   100.0 | 2026-09-07 03:01:04.047864+00 | 2026-09-07 03:15:04.253552+00
```

**Saída real, D — oportunidades:**

```
 status  | stage | count | score_min | score_max |           primeira            |            ultima
---------+-------+-------+-----------+-----------+-------------------------------+----------------------------
 EXPIRED | NONE  |     8 |      0.00 |      0.87 | 2026-09-07 02:40:20.385375+00 | 2026-09-07 03:23:24.884+00
 NORMAL  | NONE  |     3 |      0.00 |      1.98 | 2026-09-07 03:02:04.872924+00 | 2026-09-07 03:24:45.920226+00
 ANOMALY | NONE  |     1 |     10.00 |     10.00 | 2026-09-07 03:01:04.047864+00 | 2026-09-07 03:24:45.920226+00
```

**Saída real, E — estágios já publicados:**

```
 stage | count
-------+-------
 NONE  |   299
```

**Saída real, F — disponibilidade por componente, sobre as 12 oportunidades:**

```
      componente       | disponivel | indisponivel |          motivos
-----------------------+------------+--------------+---------------------------
 agent_consensus       |         12 |            0 |
 anomalies             |         12 |            0 |
 volume                |         12 |            0 |
 external_intelligence |          0 |           12 | {feature_not_implemented}
 liquidity             |          0 |           12 | {no_usable_input}
 market_regime         |          0 |           12 | {regime_unknown}
 momentum              |          0 |           12 | {no_usable_input}
 order_flow            |          0 |           12 | {no_usable_input}
 derivatives           |          0 |           12 | {no_usable_input}
```

**Saída real, G — série viva:**

```
 snapshots | mercados |        primeiro        |         ultimo
-----------+----------+------------------------+------------------------
    108688 |      212 | 2026-09-06 18:17:00+00 | 2026-09-07 03:24:00+00
```

#### Cobertura (contagens completas, com denominador)

| Medida | Valor | Denominador |
|---|---|---|
| Revisões vigentes no corte | **88.746** | — |
| Buckets utilizáveis | **4.944** | 88.746 → **5,57 %** |
| Mercados com ao menos uma revisão | 211 | 200 monitorados (+ 11 de troca de universo no dia) |
| Mercados com bucket utilizável, no melhor caso | **29** | 200 → **14,5 %** |
| Features com ≥ 1 bucket utilizável | **12** | 27 → **44,4 %** |
| Features com **zero** buckets utilizáveis | **15** | 27 |
| Buckets com `MAD = 0` | 1.521 | 88.746 → 1,71 % |
| Cobertura média das janelas | **0,2032** | 1,0 = 420 observações/bucket |
| `feature_snapshots` ao vivo | 108.688 sobre 212 mercados | janela de **9 h 07 min** |
| Fonte das revisões (leitura separada) | `bootstrap` 77.687 em 206 mercados · `live` 25.876 em 211 mercados | 103.563 no total (sem corte) |

#### Métricas (com denominador explícito)

| Métrica | Valor | Denominador | Observação |
|---|---|---|---|
| Fração de buckets utilizáveis | **5,57 %** | revisões vigentes | portão `≥ 3 dias distintos E ≥ 120 obs.` |
| Fração de features utilizáveis | **44,4 %** | 27 features registradas | as 15 restantes são tape, livro, derivativos e `_live` |
| Alcance máximo por mercado | **14,5 %** | 200 monitorados | 29 mercados, na melhor feature |
| Componentes de score disponíveis | **3 de 9** | 12 oportunidades, 12/12 iguais | pesos disponíveis somam **0,25** |
| **Teto aritmético de score hoje** | **25,00 de 100** | `0,20 × 100 + 0,05 × 100` | limiares ativos: `watching_min 40`, `hot_min 75`, `entry_candidate_min 80` |
| Estágio ≠ `NONE` | **0** | 299 amostras de `opportunity_history` | — |
| Tipos de anomalia que dispararam | **1** | 10 registrados (8 armados, 2 desarmados com motivo) | só `VOLUME_SPIKE` |
| Regime classificado ≠ `UNKNOWN` | **0** | 1 linha em `market_regimes` | motivos: `trend_input_unavailable`, breadth `coverage = 0`, `volatility_warmup` (146 de 480 amostras, 7 de 20 dias) |
| Taxa de alvo / lucro / expectancy em R / PF / MFE-MAE | **não aplicável** | — | este experimento mede um instrumento, não uma estratégia; não há entrada, saída nem R |
| PnL de carteira / Max Drawdown de carteira | **não aplicável** | — | não há carteira aqui |

**População local, como segunda amostra** (mesmo `as_of`, `read_at = 2026-09-07T03:24Z`, stack de
desenvolvimento com 4 shards e head `0006`): 73.051 revisões vigentes, **8.028 utilizáveis
(10,99 %)**, 212 mercados, 27 features, 2.154 com `MAD = 0`, cobertura média 0,2129; 128.786
snapshots sobre 216 mercados desde 2026-09-06T15:35Z; 18 anomalias, todas `VOLUME_SPIKE`; 14
oportunidades, todas `EXPIRED`/`NONE`, score 0,00 a 2,32. A fração utilizável é o dobro da VPS
porque o local teve o backfill de setembro rodando mais tempo — e o padrão qualitativo é
**idêntico**: as mesmas 15 features com zero.

- **Dias distintos de série viva:** **1** (a série começa em 2026-09-06T18:17Z).
- **Versão da métrica / proveniência:** `baseline_gate_v1` sobre `feature_baselines`,
  `feature_snapshots`, `anomalies`, `opportunities`, `opportunity_history`, `market_regimes`;
  todos os números lidos por `psql` em modo somente-leitura.
- **Result:** **inconclusivo** para a hipótese principal — 1 dia distinto de série viva contra os
  3 que o próprio portão exige. Não é possível afirmar nem refutar "amadurecem em dias e não em
  semanas" com uma janela de 9 h 07 min.
- **Conclusion:** três coisas ficam decididas por aritmética, não por opinião, e independem da
  próxima leitura. **(1)** O bootstrap sobre candles cobre exatamente a metade "de barra" do vetor:
  12 das 27 features têm bucket utilizável, e as 15 que não têm são precisamente tape
  (`trade_velocity_1m`, `buy_pressure_5m`, `sell_pressure_5m`), livro (`spread_pct`,
  `orderbook_imbalance_20`), derivativos (`funding_rate`, `open_interest_change_1h/4h`) e as
  `_live` — o `historical_source_unavailable` que a T2.3 declarou está confirmado em produção.
  **(2)** Com 3 componentes disponíveis somando peso 0,25, o score não pode passar de **25,00**,
  contra a linha de **40** do WATCHING: **nenhum mercado pode ser HOT hoje**, e os dois com status
  `ANOMALY` chegaram lá pela rota da severidade (`anomaly_severity_min = 60`), não por pontuação.
  **(3)** O motor está correto ao dizer isso: cada componente ausente carrega o próprio motivo,
  nenhum peso foi redistribuído para maquiar o número, e a confiança caiu para **0,0714** em vez de
  fingir certeza. A parte da hipótese que já está **refutada na prática** é a segunda metade dela
  — a que eu escrevi esperando refutar: tape, livro e derivativos **de fato** dependem de coleta
  ao vivo e são metade do peso do score.
- **Achado que a leitura de hoje acrescenta, e que não é warm-up:** na VPS,
  `mkt:binance:coverage.covered_until` estava em **2026-09-07T02:34:57Z** contra um relógio de
  **03:19:20Z** — **44 minutos congelado**. Enquanto o carimbo não anda, as features de tape se
  recusam sozinhas (`insufficient_coverage`) e **nenhuma baseline de tape amadurece**: o relógio
  dos 3 dias nem começou a correr para elas. O heartbeat do scanner declara
  `coverage = unproven`; o do Shadow Lab conta `{"unavailable": 63.793}` avaliações. Registrado em
  [[Open Bugs]] como HIGH aberto — é o bloqueio nº 1 deste experimento, e a razão pela qual a
  próxima avaliação pode não medir nada de novo se ninguém o fechar antes.
- **Next Action:** **(a)** fechar o HIGH da cobertura congelada na VPS antes de qualquer outra
  coisa; **(b)** repetir esta avaliação, com o mesmo SQL e um `as_of` novo, em **2026-09-09 ou
  2026-09-10** — a primeira data em que a série viva pode ter 3 dias distintos e as 15 features
  mudas podem passar o portão; **(c)** se na segunda avaliação as 15 continuarem em zero com a
  cobertura andando, isso deixa de ser warm-up e vira defeito, e o experimento terá refutado a
  hipótese com número. **Nada é reparametrizado por causa desta página** — nem peso, nem limiar,
  nem `strategy_version`.

### Avaliação de <próxima data>

<acrescente uma seção nova; não edite a anterior>

## Relacionadas

[[Experiments Index]] · [[Features]] · [[Anomalies]] · [[Market Collector]] · [[Open Bugs]] ·
[[Architecture Decisions]] · [[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] ·
[[EXP-0004-politicas-de-saida]] · [[Diario/2026-09-07]]

## Fontes

`docs/plans/M2.md` (T2.8 e a decisão conjunta) · `docs/reports/M2.md` (relatório e parecer do M2) ·
`.claude/state/t25-proof.md` (as sete provas operacionais do scanner) ·
`.claude/state/notes-T2.2.md`, `notes-T2.3.md`, `notes-T2.4.md`, `notes-T2.5.md` ·
`.claude/state/dialogue-M2.md`
