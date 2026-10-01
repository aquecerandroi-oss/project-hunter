**RESUMO**

Astra, como auditora de dados do Lab: **o histórico exige filtros de qualidade antes de sustentar conclusões de pesquisa.**

Janela: **01/09/2026 00:00 ≤ instante < 01/10/2026 00:00 UTC**, os últimos 30 dias completos. Leituras realizadas em 01/10, aproximadamente **02:58–03:04 UTC**. Os desfechos refletem seu estado na leitura, não uma reconstrução do estado à meia-noite.

| Medida | Resultado |
|---|---:|
| Sinais prospectivos | 11.462 |
| Sinais de replay | 1.395 |
| Sinais sem outcome | 0 |
| Outcomes `pending_entry` / `active` / `censored` | 0 / 0 / 0 |
| Terminais sem resultado líquido | **289**: 233 prospectivos + 56 replay |
| Sinais spot no histórico | **340**, em 18 símbolos também presentes em perpétuos |
| Mesma versão/coorte/símbolo/barra em ambos os tipos | **179 decisões, 358 linhas** |
| Perpétuos com os 30 dias completos | **16 dos 20** |
| Dias completos de mercado | **524 de 600** |
| Candles finais encontrados / esperados | **766.134 / 864.000** |
| Minutos ausentes | **97.866**, incluindo **11.624 em buracos internos** |

O top 20 foi escolhido pelo **`volume_24h_usd` vigente na leitura**, entre perpétuos ativos. Portanto, é uma auditoria retrospectiva do **top atual**, não dos líderes históricos de cada dia.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhuma escrita no banco, migração, commit ou leitura de `.env`.

Memória consultada: [00-HOME](C:/dev/project-hunter/obsidian/00-HOME.md), [Market Collector](<C:/dev/project-hunter/obsidian/02-MARKET/Market Collector.md>), [Strategies](C:/dev/project-hunter/obsidian/03-TRADING/Strategies.md), [Experiments Index](<C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments Index.md>) e a [decisão sobre o universo de pesquisa](C:/dev/project-hunter/obsidian/06-DECISIONS/2026-09-10-universo-de-pesquisa-90-dias.md).

**TESTES — consultas e saídas reais**

Usei SSH e `psql -f -` para enviar SQL pela entrada padrão, após uma tentativa inicial com `-c` falhar na interpretação das aspas:

```text
ssh -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=yes hunter-vps \
  'cd /opt/project-hunter && bash infra/vps/compose.sh exec -T postgres \
  psql -X -A -v ON_ERROR_STOP=1 -U hunter -d hunter -f -'
```

Todas as medições foram executadas dentro deste invólucro:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '8s';
SET LOCAL lock_timeout = '1s';
SET LOCAL TIME ZONE 'UTC';
SET LOCAL max_parallel_workers_per_gather = 0;
SET LOCAL jit = off;

-- Consulta.
COMMIT;
```

Confirmação real:

```text
read_at|read_only
2026-10-01 03:02:53.62183+00|on
```

Executei e inspecionei **`EXPLAIN`, sem `ANALYZE`, antes de cada consulta de medição**. Os históricos foram acessados por índices e janelas delimitadas. Houve `Seq Scan` nos pequenos catálogos `markets`, `strategies` e `strategy_versions`, não varredura integral das tabelas históricas.

Trechos reais dos planos:

```text
Bitmap Index Scan on ix_agent_signals_version_emitted
  Index Cond: ((strategy_version_id = v.id)
    AND (emitted_at >= '2026-09-01 00:00:00+00'::timestamp with time zone)
    AND (emitted_at < '2026-10-01 00:00:00+00'::timestamp with time zone))

Index Scan using pk_signal_outcomes on signal_outcomes
  Index Cond: (signal_id = a.id)

Bitmap Index Scan on candles_1m_2026_09_pkey
  Index Cond: ((market_id = "*VALUES*".column1)
    AND (timeframe = '1m'::candle_timeframe)
    AND (open_time >= d.day)
    AND (open_time < (d.day + '1 day'::interval))
    AND (open_time >= '2026-09-01 00:00:00+00'::timestamp with time zone)
    AND (open_time < '2026-10-01 00:00:00+00'::timestamp with time zone))

Index Only Scan using ix_ingestion_gaps_status_detected on ingestion_gaps
  Index Cond: ((status = "*VALUES*".column1)
    AND (detected_at >= '2026-09-01 00:00:00+00'::timestamp with time zone)
    AND (detected_at < '2026-10-01 00:00:00+00'::timestamp with time zone))
```

**1. Sinais por dia, estratégia, versão e família de coorte**

SQL executado, com formatação compactada:

```sql
WITH daily AS (
  SELECT s.key, v.version, a.day, a.cohort, a.n
  FROM strategy_versions v
  JOIN strategies s ON s.id = v.strategy_id
  CROSS JOIN LATERAL (
    SELECT emitted_at::date AS day,
           COALESCE(
             split_part(supporting_features->>'cohort', ':', 1),
             'missing'
           ) AS cohort,
           count(*) AS n
    FROM agent_signals
    WHERE strategy_version_id = v.id
      AND emitted_at >= '2026-09-01 00:00Z'
      AND emitted_at <  '2026-10-01 00:00Z'
    GROUP BY 1, 2
    OFFSET 0
  ) a
  ORDER BY a.day, s.key, v.version, a.cohort
)
SELECT key, version, cohort, sum(n) total,
       string_agg(
         to_char(day, 'DD') || ':' || n,
         ',' ORDER BY day
       ) day_count
FROM daily
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
```

Saída real. `08:65` significa **65 sinais no dia 08/09**. Dias omitidos têm zero linhas para aquela combinação. `replay` agrega os identificadores de execução dessa família; não representa uma amostra independente única.

```text
key|version|cohort|total|day_count
breakout|v2|replay|1|06:1
mean_reversion|v1|prospective|473|08:65,09:148,10:59,11:12,12:7,13:1,14:13,15:7,16:3,17:10,18:12,19:13,20:3,21:14,22:15,23:17,24:8,25:19,26:12,27:12,28:1,29:12,30:10
mean_reversion|v1|replay|91|01:11,02:3,03:16,04:8,05:14,06:16,07:6,08:9,09:8
mean_reversion|v10|prospective|385|09:118,10:54,11:12,12:8,13:1,14:15,15:4,16:5,17:15,18:13,19:17,20:5,21:16,22:14,23:12,24:10,25:20,26:13,27:12,28:2,29:10,30:9
mean_reversion|v10|replay|186|01:22,02:9,03:33,04:19,05:35,06:35,07:17,08:7,09:9
mean_reversion|v11|prospective|23|09:23
mean_reversion|v12|replay|1|06:1
mean_reversion|v13|replay|1|06:1
mean_reversion|v14|prospective|242|09:41,10:52,11:9,12:3,14:8,15:4,16:2,17:7,18:9,19:9,20:3,21:11,22:11,23:16,24:7,25:15,26:7,27:9,28:1,29:9,30:9
mean_reversion|v15|replay|44|01:11,03:1,06:13,07:8,08:7,09:4
mean_reversion|v16|replay|32|01:11,03:1,07:9,08:7,09:4
mean_reversion|v17|replay|20|03:11,04:9
mean_reversion|v18|replay|64|01:2,02:3,03:12,04:6,05:10,06:12,07:5,08:7,09:7
mean_reversion|v19|replay|41|01:7,03:6,04:4,05:10,06:4,07:2,08:4,09:4
mean_reversion|v2|prospective|366|08:19,09:131,10:54,11:10,12:4,14:8,15:6,16:2,17:7,18:11,19:10,20:3,21:11,22:12,23:17,24:7,25:16,26:8,27:10,28:1,29:9,30:10
mean_reversion|v2|replay|94|01:12,02:6,03:10,04:10,05:17,06:14,07:10,08:7,09:8
mean_reversion|v3|prospective|290|08:12,09:111,10:51,11:6,12:3,14:4,15:4,16:2,17:7,18:10,19:7,20:1,21:8,22:10,23:13,24:3,25:13,26:5,27:5,28:1,29:8,30:6
mean_reversion|v4|prospective|6|08:6
mean_reversion|v5|prospective|6|08:6
mean_reversion|v6|prospective|333|08:8,09:124,10:52,11:9,12:3,14:8,15:4,16:2,17:7,18:9,19:9,20:3,21:11,22:11,23:16,24:7,25:15,26:7,27:9,28:1,29:9,30:9
mean_reversion|v6|replay|41|01:4,02:3,03:5,04:6,05:10,06:7,07:6
mean_reversion|v7|prospective|322|08:8,09:119,10:52,11:8,12:3,14:8,15:3,16:2,17:7,18:9,19:9,20:3,21:11,22:10,23:15,24:7,25:14,26:7,27:8,28:1,29:9,30:9
mean_reversion|v7|replay|1|05:1
mean_reversion|v8|prospective|385|08:4,09:141,10:57,11:10,12:6,13:1,14:11,15:5,16:3,17:9,18:10,19:12,20:3,21:14,22:13,23:16,24:8,25:18,26:11,27:11,28:1,29:12,30:9
mean_reversion|v8|replay|72|01:9,02:3,03:16,04:8,05:16,06:13,07:7
mean_reversion_h1|v1|prospective|118|09:18,10:16,13:1,14:2,15:5,18:3,19:13,20:11,21:4,22:9,23:15,24:2,25:2,26:5,27:4,28:6,29:2
mean_reversion_h1|v1|replay|54|01:8,02:1,03:1,04:17,05:2,06:11,07:14
mean_reversion_m5|v1|replay|104|01:5,02:10,03:14,04:23,05:12,06:15,07:8,08:5,09:12
momentum|v1|prospective|963|06:391,07:460,08:112
momentum|v10|prospective|235|09:235
momentum|v10|replay|61|01:6,02:7,03:17,04:5,05:7,06:12,07:7
momentum|v11|replay|125|03:24,04:38,05:47,06:16
momentum|v12|replay|2|05:2
momentum|v13|replay|3|05:3
momentum|v2|prospective|676|08:378,09:298
momentum|v2|replay|139|01:12,02:14,03:52,04:10,05:18,06:16,07:17
momentum|v3|prospective|1831|08:357,09:381,10:268,11:37,12:12,13:28,14:65,15:13,16:55,17:51,18:82,19:29,20:39,21:79,22:41,23:30,24:55,25:50,26:32,27:33,28:33,29:32,30:29
momentum|v4|prospective|319|08:132,09:187
momentum|v4|replay|3|03:2,05:1
momentum|v5|prospective|1|08:1
momentum|v6|prospective|327|08:37,09:290
momentum|v6|replay|59|01:6,02:7,03:21,04:5,05:6,06:7,07:7
momentum|v7|prospective|11|08:11
momentum|v7|replay|56|01:6,02:7,03:19,04:5,05:6,06:7,07:6
momentum|v8|prospective|351|08:12,09:339
momentum|v8|replay|56|01:6,02:7,03:19,04:5,05:6,06:7,07:6
session_orb|v1|prospective|72|09:72
session_orb|v1|replay|1|06:1
sweep_reclaim|v1|prospective|1|09:1
sweep_reclaim|v1|replay|10|01:1,02:1,03:2,05:2,06:1,07:3
trendline_bounce|v1|prospective|1|09:1
trendline_bounce|v1|replay|2|02:2
trendline_breakout|v1|prospective|154|08:22,09:132
trendline_breakout|v1|replay|5|01:1,02:2,03:2
volume_anomaly|v1|prospective|2152|06:846,07:1173,08:133
volume_anomaly|v2|prospective|1419|08:795,09:624
volume_anomaly|v2|replay|26|01:4,02:4,03:8,04:4,05:2,06:4
(57 rows)
```

Essas contagens usam `emitted_at`, que o escritor preenche com `decision_at`; em replay isso é tempo da decisão simulada, não necessariamente a data em que o replay foi executado. Referência: [persist.py:93](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:93).

**2. Outcomes, pendências e indisponibilidade por motivo**

A população foi buscada por versão e período; cada outcome, pela chave primária:

```sql
WITH a AS MATERIALIZED (
  SELECT a.*
  FROM strategy_versions v
  CROSS JOIN LATERAL (
    SELECT id, market_id, strategy_version_id, emitted_at,
           expires_at, expected_holding_s, supporting_features
    FROM agent_signals
    WHERE strategy_version_id = v.id
      AND emitted_at >= '2026-09-01 00:00Z'
      AND emitted_at <  '2026-10-01 00:00Z'
    OFFSET 0
  ) a
)
SELECT
  COALESCE(split_part(a.supporting_features->>'cohort', ':', 1),
           'missing') cohort,
  m.market_type,
  COALESCE(o.tracking_state::text, 'missing_outcome') state,
  o.result,
  o.no_entry_reason,
  o.censored_reason,
  split_part(o.meta->>'r_net_reason', ':', 1) r_net_reason,
  count(*) n,
  count(*) FILTER (WHERE o.r_multiple IS NOT NULL) r_known
FROM a
JOIN markets m ON m.id = a.market_id
LEFT JOIN LATERAL (
  SELECT * FROM signal_outcomes WHERE signal_id = a.id OFFSET 0
) o ON true
GROUP BY 1,2,3,4,5,6,7
ORDER BY 1,2,3,4,5,6,7;
```

Saída real. Campos vazios são `NULL`; `funding_missing` foi agregado pela família do motivo, sem o timestamp individual:

```text
cohort|market_type|state|result|no_entry_reason|censored_reason|r_net_reason|n|r_known
prospective|spot|no_entry|open|geometry|||23|0
prospective|spot|no_entry|open|late:delay|||184|0
prospective|spot|terminal|target|||funding_schedule_unknown|34|0
prospective|spot|terminal|stop|||funding_schedule_unknown|36|0
prospective|spot|terminal|expired|||funding_schedule_unknown|2|0
prospective|spot|terminal|invalidated|||funding_schedule_unknown|61|0
prospective|perpetual|no_entry|open|geometry|||72|0
prospective|perpetual|no_entry|open|late:delay|||1743|0
prospective|perpetual|no_entry|open|late:missed_open|||4|0
prospective|perpetual|terminal|target|||funding_ambiguous_exit|6|0
prospective|perpetual|terminal|target|||funding_missing|16|0
prospective|perpetual|terminal|target||||2766|2766
prospective|perpetual|terminal|stop|||funding_ambiguous_exit|6|0
prospective|perpetual|terminal|stop|||funding_missing|29|0
prospective|perpetual|terminal|stop||||2660|2660
prospective|perpetual|terminal|expired|||funding_missing|11|0
prospective|perpetual|terminal|expired||||842|842
prospective|perpetual|terminal|invalidated|||funding_missing|32|0
prospective|perpetual|terminal|invalidated||||2935|2935
replay|perpetual|no_entry|open|geometry|||2|0
replay|perpetual|terminal|target|||funding_ambiguous_exit|2|0
replay|perpetual|terminal|target|||funding_schedule_unknown|15|0
replay|perpetual|terminal|target||||290|290
replay|perpetual|terminal|stop|||funding_schedule_unknown|11|0
replay|perpetual|terminal|stop||||346|346
replay|perpetual|terminal|expired|||funding_schedule_unknown|1|0
replay|perpetual|terminal|expired||||424|424
replay|perpetual|terminal|invalidated|||funding_schedule_unknown|27|0
replay|perpetual|terminal|invalidated||||277|277
(29 rows)
```

Também executei a reconciliação dos totais sobre a mesma CTE `a`, substituindo o `SELECT` final por:

```sql
SELECT split_part(a.supporting_features->>'cohort', ':', 1) cohort,
       count(*) signals,
       count(*) FILTER (WHERE o.signal_id IS NULL) missing_outcome,
       count(*) FILTER (WHERE o.tracking_state='pending_entry') pending_entry,
       count(*) FILTER (WHERE o.tracking_state='active') active,
       count(*) FILTER (WHERE o.tracking_state='no_entry') no_entry,
       count(*) FILTER (WHERE o.tracking_state='censored') censored,
       count(*) FILTER (WHERE o.tracking_state='terminal') terminal,
       count(*) FILTER (
         WHERE o.tracking_state='terminal' AND o.r_multiple IS NULL
       ) terminal_net_unavailable,
       count(*) FILTER (WHERE o.r_multiple IS NOT NULL) net_known
FROM a
LEFT JOIN LATERAL (
  SELECT * FROM signal_outcomes WHERE signal_id=a.id OFFSET 0
) o ON true
GROUP BY 1 ORDER BY 1;
```

```text
cohort|signals|missing_outcome|pending_entry|active|no_entry|censored|terminal|terminal_net_unavailable|net_known
prospective|11462|0|0|0|2026|0|9436|233|9203
replay|1395|0|0|0|2|0|1393|56|1337
(2 rows)
```

**Não confundir `result=open` com pendência:** aqui existem **2.028 `no_entry`**, todos com `result=open`, mas nenhum acompanhamento pendente.

**Limitação:** isso mede indisponibilidade dos **sinais existentes**. Não mede os 30 dias de avaliações `unavailable` que impediram a emissão. Há caminhos que retornam `UNAVAILABLE` antes de persistir sinal; os contadores de avaliação e heartbeat não constituem, nessas tabelas, um histórico diário por motivo. Referências: [decide.py:142](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:142), [metrics.py:50](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/metrics.py:50), [consumer_health.py:30](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer_health.py:30) e [heartbeat.py:70](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/heartbeat.py:70). **Esse número não foi medido; não é zero.**

**3. Cobertura diária dos 20 perpétuos**

Seleção executada:

```sql
SELECT id, symbol, exchange_id, volume_24h_usd, monitor_rank, is_monitored
FROM markets
WHERE market_type='perpetual' AND status='active'
ORDER BY volume_24h_usd DESC NULLS LAST, id
LIMIT 20;
```

Os 20 retornaram `is_monitored=t`, com ranks 1–20, nesta ordem:

```text
BTCUSDT ETHUSDT SOLUSDT ZECUSDT QNTUSDT HYPEUSDT XRPUSDT NEARUSDT
MOVRUSDT DOGEUSDT SUIUSDT ENAUSDT WLDUSDT PUMPUSDT SOONUSDT ARKUSDT
BNBUSDT UNIUSDT 1000PEPEUSDT LINKUSDT
```

Congelei os IDs retornados para que uma atualização do ranking não mudasse a população entre consultas:

```sql
WITH top(id,symbol) AS (
  VALUES
  ('01a073bb-9bab-7704-b083-6ce85d7b72ad'::uuid,'BTCUSDT'),
  ('01a073bb-9bac-72b1-a560-acda32ff5816'::uuid,'ETHUSDT'),
  ('01a073bb-9bd4-7e13-9813-3acbc5b927fc'::uuid,'SOLUSDT'),
  ('01a073bb-9bb7-72ad-9c9b-63f84a60f8fd'::uuid,'ZECUSDT'),
  ('01a073bb-9c14-70b1-9cea-48c392de060d'::uuid,'QNTUSDT'),
  ('01a073bb-9d05-7651-8140-9eaca3ae6945'::uuid,'HYPEUSDT'),
  ('01a073bb-9bae-7d9c-9f80-68983761b3c8'::uuid,'XRPUSDT'),
  ('01a073bb-9bd9-73d2-b14b-3222b61e78ce'::uuid,'NEARUSDT'),
  ('01a073bb-9c56-73f4-86e7-b680f3fa3c59'::uuid,'MOVRUSDT'),
  ('01a073bb-9bc8-7290-abcd-1c2440bf9eff'::uuid,'DOGEUSDT'),
  ('01a073bb-9c29-7ae1-ac44-adc1632b76d2'::uuid,'SUIUSDT'),
  ('01a073bb-9c6a-79fe-9e0c-fcc12e2b9459'::uuid,'ENAUSDT'),
  ('01a073bb-9c30-7ab6-b87c-1d9aed220832'::uuid,'WLDUSDT'),
  ('01a073bb-9d17-7763-b544-67bb9e0f83b3'::uuid,'PUMPUSDT'),
  ('01a073bb-9d00-7b3b-a11b-a73e099fe6f4'::uuid,'SOONUSDT'),
  ('01a073bb-9c39-7477-a7c8-39f09a5cba3e'::uuid,'ARKUSDT'),
  ('01a073bb-9bb9-7fcf-9bdf-fd974c9c35e1'::uuid,'BNBUSDT'),
  ('01a073bb-9bd5-7390-808e-95f403dd0a9d'::uuid,'UNIUSDT'),
  ('01a073bb-9c2a-7c47-ab71-74c53fd80599'::uuid,'1000PEPEUSDT'),
  ('01a073bb-9bb2-76e1-bdba-ee95a3cfbb45'::uuid,'LINKUSDT')
), daily AS (
  SELECT t.symbol,d.day::date,
         c.n,c.nonfinal,c.rest,c.late_5m,c.first_bar,c.last_bar
  FROM top t
  CROSS JOIN generate_series(
    '2026-09-01 00:00Z'::timestamptz,
    '2026-09-30 00:00Z',interval '1 day'
  ) d(day)
  CROSS JOIN LATERAL (
    SELECT count(*) FILTER (WHERE is_final) n,
           count(*) FILTER (WHERE NOT is_final) nonfinal,
           count(*) FILTER (WHERE is_final AND source='rest') rest,
           count(*) FILTER (
             WHERE is_final
               AND received_at > open_time+interval '6 minutes'
           ) late_5m,
           min(open_time) FILTER (WHERE is_final) first_bar,
           max(open_time) FILTER (WHERE is_final) last_bar
    FROM candles
    WHERE market_id=t.id AND timeframe='1m'
      AND open_time>=d.day AND open_time<d.day+interval '1 day'
      AND open_time>='2026-09-01 00:00Z'
      AND open_time<'2026-10-01 00:00Z'
  ) c
  ORDER BY d.day,t.symbol
)
SELECT symbol,
       count(*) FILTER (WHERE n=1440) complete_days,
       count(*) FILTER (WHERE n<1440) incomplete_days,
       sum(n) final_candles,
       sum(1440-n) missing_minutes,
       sum(nonfinal) nonfinal,
       sum(rest) rest,
       sum(late_5m) late_5m,
       COALESCE(string_agg(
         to_char(day,'DD')||':'||n,',' ORDER BY day
       ) FILTER (WHERE n<1440),'-') incomplete_day_counts
FROM daily GROUP BY symbol ORDER BY symbol;
```

Saída real. **Todo dia não listado em `incomplete_day_counts` tem 1.440 candles finais.** `late_5m` significa recebimento mais de cinco minutos depois do fechamento nominal; inclui backfill, não apenas falha durante operação ao vivo.

```text
symbol|complete_days|incomplete_days|final_candles|missing_minutes|nonfinal|rest|late_5m|incomplete_day_counts
1000PEPEUSDT|30|0|43200|0|0|7216|7122|-
ARKUSDT|18|12|28459|14741|0|5059|5008|01:0,02:0,03:0,04:0,05:0,06:0,07:0,08:0,09:982,21:431,22:0,23:1126
BNBUSDT|30|0|43200|0|0|7217|7121|-
BTCUSDT|30|0|43200|0|0|7220|7121|-
DOGEUSDT|30|0|43200|0|0|7215|7121|-
ENAUSDT|30|0|43200|0|0|7227|7121|-
ETHUSDT|30|0|43200|0|0|7224|7121|-
HYPEUSDT|30|0|43200|0|0|7217|7122|-
LINKUSDT|30|0|43200|0|0|7225|7123|-
MOVRUSDT|12|18|25338|17862|0|8973|8901|01:0,02:0,03:0,04:0,05:0,06:0,07:1079,09:1102,10:0,11:823,15:936,16:692,18:956,19:0,20:0,21:208,23:1162,24:1100
NEARUSDT|30|0|43200|0|0|7220|7123|-
PUMPUSDT|30|0|43200|0|0|7222|7122|-
QNTUSDT|9|21|13739|29461|0|2840|2824|01:0,02:0,03:0,04:0,05:0,06:0,07:0,08:0,09:0,10:0,11:0,12:0,13:0,14:0,15:0,16:0,17:0,18:0,19:0,20:0,21:779
SOLUSDT|30|0|43200|0|0|7222|7122|-
SOONUSDT|5|25|7398|35802|0|1504|1496|01:0,02:0,03:0,04:0,05:0,06:0,07:0,08:0,09:0,10:0,11:0,12:0,13:0,14:0,15:0,16:0,17:0,18:0,19:0,20:0,21:0,22:0,23:0,24:0,25:198
SUIUSDT|30|0|43200|0|0|7216|7122|-
UNIUSDT|30|0|43200|0|0|7220|7125|-
WLDUSDT|30|0|43200|0|0|7225|7123|-
XRPUSDT|30|0|43200|0|0|7225|7125|-
ZECUSDT|30|0|43200|0|0|7228|7126|-
(20 rows)
```

**4. Buracos efetivos na série**

Aprofundei apenas os quatro mercados incompletos. As bordas artificiais permitem identificar também ausência no começo e no fim da janela:

```sql
WITH top(id,symbol) AS (
  VALUES
  ('01a073bb-9c39-7477-a7c8-39f09a5cba3e'::uuid,'ARKUSDT'),
  ('01a073bb-9c56-73f4-86e7-b680f3fa3c59'::uuid,'MOVRUSDT'),
  ('01a073bb-9c14-70b1-9cea-48c392de060d'::uuid,'QNTUSDT'),
  ('01a073bb-9d00-7b3b-a11b-a73e099fe6f4'::uuid,'SOONUSDT')
), bars AS (
  SELECT t.symbol,c.open_time
  FROM top t
  CROSS JOIN LATERAL (
    SELECT open_time
    FROM candles
    WHERE market_id=t.id AND timeframe='1m' AND is_final
      AND open_time>='2026-09-01 00:00Z'
      AND open_time<'2026-10-01 00:00Z'
    OFFSET 0
  ) c
), edges AS (
  SELECT symbol,open_time,
         lead(open_time,1,'2026-10-01 00:00Z'::timestamptz)
           OVER (PARTITION BY symbol ORDER BY open_time) next_time
  FROM bars
  UNION ALL
  SELECT t.symbol,'2026-08-31 23:59Z'::timestamptz,
         COALESCE(min(b.open_time),'2026-10-01 00:00Z')
  FROM top t LEFT JOIN bars b USING(symbol)
  GROUP BY t.symbol
)
SELECT symbol,
       open_time+interval '1 minute' missing_from,
       next_time missing_until_exclusive,
       extract(epoch FROM next_time-open_time)/60-1 missing_minutes
FROM edges
WHERE next_time>open_time+interval '1 minute'
ORDER BY symbol,open_time;
```

```text
symbol|missing_from|missing_until_exclusive|missing_minutes
ARKUSDT|2026-09-01 00:00:00+00|2026-09-09 07:38:00+00|11978.000000000000
ARKUSDT|2026-09-21 07:11:00+00|2026-09-23 05:14:00+00|2763.0000000000000000
MOVRUSDT|2026-09-01 00:00:00+00|2026-09-07 06:01:00+00|9001.0000000000000000
MOVRUSDT|2026-09-09 18:22:00+00|2026-09-11 10:17:00+00|2395.0000000000000000
MOVRUSDT|2026-09-15 15:36:00+00|2026-09-16 12:28:00+00|1252.0000000000000000
MOVRUSDT|2026-09-18 15:56:00+00|2026-09-21 20:32:00+00|4596.0000000000000000
MOVRUSDT|2026-09-23 19:22:00+00|2026-09-24 05:40:00+00|618.0000000000000000
QNTUSDT|2026-09-01 00:00:00+00|2026-09-21 11:01:00+00|29461.000000000000
SOONUSDT|2026-09-01 00:00:00+00|2026-09-25 20:42:00+00|35802.000000000000
(9 rows)
```

Os cinco intervalos internos somam **11.624 minutos**. Os quatro prefixos somam **86.242 minutos**. Não atribuo automaticamente esses prefixos a uma pane: podem envolver início de cobertura ou elegibilidade do universo. Também não os trato como comprovadamente anteriores à listagem.

**5. Registro operacional de gaps**

Consulta global limitada aos gaps **detectados em setembro** — essa população difere da consulta anterior, que mede minutos ausentes em setembro:

```sql
SELECT st.status,g.n,g.first_detected,g.last_detected
FROM (VALUES
  ('open'),('failed'),('unrecoverable'),('recovered')
) st(status)
CROSS JOIN LATERAL (
  SELECT count(*) n,
         min(detected_at) first_detected,
         max(detected_at) last_detected
  FROM ingestion_gaps
  WHERE status=st.status
    AND detected_at>='2026-09-01 00:00Z'
    AND detected_at<'2026-10-01 00:00Z'
) g
ORDER BY 1;
```

```text
status|n|first_detected|last_detected
failed|0||
open|23|2026-09-06 01:08:55.756942+00|2026-09-07 03:45:58.060132+00
recovered|40616|2026-09-05 22:41:13.868947+00|2026-09-30 23:35:49.189374+00
unrecoverable|262|2026-09-08 04:34:48.160436+00|2026-09-08 15:35:43.625+00
(4 rows)
```

Detalhamento dos não recuperados:

```sql
SELECT m.market_type,m.is_monitored,g.status,
       count(*) gaps,count(DISTINCT g.market_id) markets,
       min(g.gap_start) first_gap,max(g.gap_end) last_gap,
       min(g.attempts) min_attempts,max(g.attempts) max_attempts
FROM (
  SELECT *
  FROM ingestion_gaps
  WHERE status IN ('open','unrecoverable')
    AND detected_at>='2026-09-01 00:00Z'
    AND detected_at<'2026-10-01 00:00Z'
  OFFSET 0
) g
JOIN markets m ON m.id=g.market_id
GROUP BY 1,2,3 ORDER BY 1,2,3;
```

```text
market_type|is_monitored|status|gaps|markets|first_gap|last_gap|min_attempts|max_attempts
perpetual|f|open|23|3|2026-08-29 19:00:00+00|2026-09-06 14:29:00+00|0|0
perpetual|f|unrecoverable|38|1|2026-08-30 07:21:00+00|2026-09-06 07:20:00+00|1|5
perpetual|t|unrecoverable|224|8|2026-08-08 03:32:00+00|2026-09-06 06:44:00+00|0|5
(3 rows)
```

Para os 20 mercados congelados, também executei, reutilizando a CTE `top` da consulta 3:

```sql
SELECT t.symbol,g.status,count(*) n,
       min(g.gap_start) first_gap,max(g.gap_end) last_gap,
       max(g.attempts) max_attempts
FROM top t
CROSS JOIN LATERAL (
  SELECT *
  FROM ingestion_gaps
  WHERE market_id=t.id AND timeframe='1m'
    AND gap_start<'2026-10-01 00:00Z'
    AND gap_end>='2026-09-01 00:00Z'
  OFFSET 0
) g
GROUP BY 1,2 ORDER BY 1,2;
```

Todas as 20 linhas retornaram `status=recovered`. Exemplos reais dos mercados incompletos:

```text
ARKUSDT|recovered|33|2026-09-09 07:38:00+00|2026-09-25 16:19:00+00|1
MOVRUSDT|recovered|40|2026-09-07 06:01:00+00|2026-09-29 16:26:00+00|1
QNTUSDT|recovered|10|2026-09-21 11:01:00+00|2026-09-25 16:19:00+00|1
SOONUSDT|recovered|11|2026-09-25 20:42:00+00|2026-09-30 05:16:00+00|1
```

Isso **não prova falsidade dos registros recuperados**: prova que o cadastro de gaps não enumera toda ausência encontrada na série.

**6. Mistura spot/perpétuo**

Reutilizando exatamente a CTE `a` da consulta 2, executei:

```sql
, x AS (
  SELECT a.*,m.exchange_id,m.symbol,m.market_type
  FROM a JOIN markets m ON m.id=a.market_id
)
SELECT symbol,
       count(*) FILTER (WHERE market_type='spot') spot,
       count(*) FILTER (WHERE market_type='perpetual') perp,
       count(DISTINCT strategy_version_id) versions,
       min(emitted_at) first_signal,max(emitted_at) last_signal
FROM x
GROUP BY exchange_id,symbol
HAVING bool_or(market_type='spot')
   AND bool_or(market_type='perpetual')
ORDER BY spot DESC,symbol;
```

Saída real:

```text
symbol|spot|perp|versions|first_signal|last_signal
ZECUSDT|72|370|27|2026-09-01 08:45:02+00|2026-09-30 10:45:05.113267+00
NEARUSDT|71|426|26|2026-09-01 08:00:02+00|2026-09-30 20:45:02.678452+00
XRPUSDT|25|278|30|2026-09-01 03:45:02+00|2026-09-30 12:45:13.163393+00
PROMUSDT|23|307|27|2026-09-02 03:15:02+00|2026-09-30 21:30:01.77881+00
MARSCOINUSDT|21|28|9|2026-09-07 00:40:04.912264+00|2026-09-10 19:30:12.375058+00
ETHUSDT|14|191|21|2026-09-01 03:45:02+00|2026-09-30 12:45:13.169569+00
DOGEUSDT|13|321|32|2026-09-01 03:45:02+00|2026-09-30 15:00:04.17752+00
BTCUSDT|12|54|8|2026-09-03 19:30:02+00|2026-09-30 12:45:02.783921+00
BNBUSDT|11|79|9|2026-09-03 16:00:02+00|2026-09-30 12:45:01.356922+00
SOLUSDT|11|309|27|2026-09-01 03:45:02+00|2026-09-30 12:45:13.159821+00
SUIUSDT|9|233|25|2026-09-01 08:45:02+00|2026-09-30 16:15:00.956022+00
HOLOUSDT|7|18|7|2026-09-09 13:35:10.661028+00|2026-09-09 17:16:09.762702+00
UNIUSDT|7|351|24|2026-09-01 08:35:02+00|2026-09-30 14:45:02.893101+00
SOPHUSDT|6|60|17|2026-09-06 04:30:12.924503+00|2026-09-10 22:00:15.357219+00
PUMPUSDT|3|45|12|2026-09-06 03:45:06.006431+00|2026-09-09 16:46:13.91104+00
WLDUSDT|3|30|5|2026-09-06 05:45:25.402894+00|2026-09-08 15:31:07.012622+00
ZKCUSDT|2|30|9|2026-09-06 05:05:08.171114+00|2026-09-09 08:04:56.934237+00
ARBUSDT|1|378|25|2026-09-01 02:15:02+00|2026-09-30 14:45:02.670193+00
(18 rows)
```

Para distinguir coexistência legítima de decisões sobre a mesma barra, usei a mesma CTE `a` e:

```sql
, groups AS (
  SELECT m.exchange_id,m.symbol,a.strategy_version_id,
         a.supporting_features->>'cohort' cohort,
         a.supporting_features->>'observation_ts' bar,
         count(*) n
  FROM a JOIN markets m ON m.id=a.market_id
  WHERE a.supporting_features->>'observation_ts' IS NOT NULL
  GROUP BY 1,2,3,4,5
  HAVING bool_or(m.market_type='spot')
     AND bool_or(m.market_type='perpetual')
)
SELECT count(*) shared_decisions,
       sum(n) signal_rows,
       count(DISTINCT symbol) symbols
FROM groups;
```

```text
shared_decisions|signal_rows|symbols
179|358|17
(1 row)
```

A primeira tentativa usou a chave JSON `source_bar_close` e retornou zero; descartei esse resultado após conferir que o envelope chama esse campo de **`observation_ts`**, conforme [envelope.py:128](C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:128).

Os sinais spot medidos estão entre **08 e 09/09**. O código local atual restringe novas decisões a perpétuos, em [decision_market_type.py:14](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decision_market_type.py:14) e [consumer.py:132](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:132). Portanto, o achado confirmado é **contaminação histórica**, não prova de que a emissão spot continua acontecendo.

**MUST-FIX — antes de usar esses dados para concluir uma pesquisa**

| Gravidade | Problema comprovado | Cenário concreto de conclusão errada |
|---|---|---|
| **ALTA** | **340 sinais spot**, com **179 decisões presentes nos dois tipos**. | Um teste agrupado apenas por símbolo conta observações correlacionadas como independentes e declara confiança maior do que possui. Os 133 terminais spot ainda distorcem a cobertura de resultado líquido. |
| **ALTA** | **Cinco buracos internos**, somando **11.624 minutos**, em ARK e MOVR. | Um replay atravessa a lacuna, não vê um stop tocado no trecho ausente e conclui que a operação sobreviveu até o alvo posterior. Exigir continuidade ou censurar a trajetória. |
| **ALTA** | **289 terminais sem `R_net`**, por funding desconhecido, ausente ou ambíguo. | Converter `NULL` em zero altera expectancy; excluir silenciosamente altera a população. Uma versão pode parecer superior apenas por ter mais resultados sem preço líquido. |
| **ALTA** | **2.028 não entradas**, incluindo **1.927 por `late:delay`** e quatro por `late:missed_open`. | Um teste usa a abertura ideal mesmo quando o sinal chegou tarde, ou interpreta `result=open` como posição pendente. Conclui executabilidade e frequência que o histórico não demonstra. |
| **ALTA para validação operacional** | **132.189 candles recebidos mais de cinco minutos após o fechamento**, incluindo backfill. | A série completa hoje é usada como prova de que o sinal era calculável naquele minuto ao vivo. O teste confunde reconstrução histórica com disponibilidade contemporânea. |
| **MÉDIA** | **86.242 minutos ausentes nos prefixos**, mais seleção pelo top 20 atual. | O pesquisador chama a amostra de “30 dias dos maiores mercados” e compara frequências sem ajustar o tempo efetivamente observado nem a seleção retrospectiva. |
| **MÉDIA** | Gaps registrados não equivalem à cobertura; há **23 abertos sem tentativa**, em três mercados atualmente não monitorados. | Um teste aceita “sem gaps abertos no universo atual” como certificado de histórico completo e libera séries que continuam contendo lacunas. |
| **MÉDIA — lacuna desta auditoria** | Indisponibilidade **anterior à emissão** não foi quantificada nos 30 dias. | A queda de sinais é atribuída a seletividade ou mudança de regime quando poderia decorrer de contexto indisponível. Zero sinais não demonstra zero oportunidades. |

A leitura histórica por versão/coorte do resumo local não filtra tipo de mercado, conforme [lab_summary.py:113](C:/dev/project-hunter/apps/api/hunter_api/repositories/lab_summary.py:113). Isso torna a separação histórica spot/perpétuo especialmente relevante.

**NICE-TO-HAVE**

Publicar por experimento a cobertura de minutos, resultados líquidos disponíveis e avaliações impedidas por motivo, sempre com denominador e janela.

**O QUE EU FARIA DIFERENTE**

Antes de comparar estratégias, congelaria a população por **versão + coorte completa + `market_id`**, exigiria continuidade das janelas e apresentaria separadamente cobertura reconstruída e disponibilidade ao vivo. Preservaria os registros históricos contaminados, identificando-os explicitamente na leitura.

**CONCORDO COM**

Manter `R_net` desconhecido como `NULL`, separar replay de prospectivo e auditar continuidade diretamente nos candles. Os totais de sinais e outcomes reconciliaram sem órfãos na janela.

**OBSIDIAN**

- **Market Collector** — registrar cobertura dos 20 mercados, nove intervalos ausentes e diferença entre cadastro de gaps e série efetiva.
- **Experiments Index** — acrescentar avaliação datada com 11.462 prospectivos, 1.395 replays e cobertura dos outcomes.
- **Strategies** — documentar a população spot histórica e as 179 decisões presentes nos dois tipos.
- **Open Bugs** — registrar os buracos internos e os 23 gaps abertos sem tentativa, sem atribuir causa ainda não demonstrada.
- **Revisões da Astra — Auditoria de dados do Lab, 2026-10-01** — preservar este SQL, saídas, janela e limites da medição.