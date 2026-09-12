-- T3.91 / EXP-0029 passo 1 — a distribuição de `dispersion_24h_v1` nos 90 dias, SOMENTE LEITURA,
-- medida ANTES de derivar qualquer variante (preenche os `‹backfill›` da página congelada).
-- Irmão de `2026-09-11-t389-q01-breadth-distribuicao.sql`.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset pager off
\echo '== (1) inventário da série =='
SELECT dispersion_version,
       horizon_minutes,
       count(DISTINCT exchange_id)        AS exchanges,
       count(*)                           AS linhas,
       count(*) FILTER (WHERE usable)     AS usaveis,
       count(*) FILTER (WHERE NOT usable) AS inutilizaveis,
       min(end_time)                      AS primeiro_minuto,
       max(end_time)                      AS ultimo_minuto,
       min(universe_size)                 AS universo_min,
       max(universe_size)                 AS universo_max
FROM market_dispersion
GROUP BY dispersion_version, horizon_minutes
ORDER BY dispersion_version;

\echo '== (2) quantis de dispersion (linhas usáveis, série inteira) =='
SELECT count(*)                                                                      AS n,
       round(avg(dispersion), 6)                                                     AS media,
       round(min(dispersion), 6)                                                     AS minimo,
       round((percentile_cont(0.05) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS p05,
       round((percentile_cont(0.10) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS p10,
       round((percentile_cont(0.25) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS p25,
       round((percentile_cont(0.50) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS p50,
       round((percentile_cont(0.75) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS p75,
       round((percentile_cont(0.90) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS p90,
       round((percentile_cont(0.95) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS p95,
       round(max(dispersion), 6)                                                     AS maximo,
       round(stddev_samp(dispersion), 6)                                             AS desvio
FROM market_dispersion
WHERE dispersion_version = 'dispersion_24h_v1' AND usable;

\echo '== (3) share de MINUTOS usáveis por célula (série inteira) =='
SELECT count(*) AS minutos_usaveis,
       count(*) FILTER (WHERE dispersion >= -0.10 AND dispersion < -0.03) AS a_discordancia,
       round(100.0 * count(*) FILTER (WHERE dispersion >= -0.10 AND dispersion < -0.03) / count(*), 4) AS a_pct,
       count(*) FILTER (WHERE dispersion >= 0.00 AND dispersion < 0.10)   AS b_falseamento,
       round(100.0 * count(*) FILTER (WHERE dispersion >= 0.00 AND dispersion < 0.10) / count(*), 4)   AS b_pct,
       count(*) FILTER (WHERE dispersion >= -0.03 AND dispersion < 0.00)  AS queda_conjunta,
       round(100.0 * count(*) FILTER (WHERE dispersion >= -0.03 AND dispersion < 0.00) / count(*), 4)  AS queda_conjunta_pct,
       count(*) FILTER (WHERE dispersion < -0.10)                         AS extrema_neg,
       round(100.0 * count(*) FILTER (WHERE dispersion < -0.10) / count(*), 4)                         AS extrema_neg_pct,
       count(*) FILTER (WHERE dispersion >= 0.10)                         AS acima_010,
       round(100.0 * count(*) FILTER (WHERE dispersion >= 0.10) / count(*), 4)                         AS acima_010_pct,
       round(100.0 * count(*) FILTER (WHERE dispersion < -0.03) / count(*), 4)                         AS abaixo_m003_pct
FROM market_dispersion
WHERE dispersion_version = 'dispersion_24h_v1' AND usable;

\echo '== (4) histograma em degraus de 0,01 (linhas usáveis) =='
SELECT floor(dispersion / 0.01) * 0.01 AS degrau,
       count(*)                        AS minutos,
       round(100.0 * count(*) / sum(count(*)) OVER (), 4) AS pct
FROM market_dispersion
WHERE dispersion_version = 'dispersion_24h_v1' AND usable
GROUP BY 1 ORDER BY 1;

\echo '== (5) tercis congelados na janela de calibração 2026-06-13..2026-07-31 (descritivo; a série começa em 06-16) =='
SELECT count(*) AS n_calibracao,
       min(end_time) AS de, max(end_time) AS ate,
       round((percentile_cont(1.0/3.0) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS t1,
       round((percentile_cont(2.0/3.0) WITHIN GROUP (ORDER BY dispersion))::numeric, 6) AS t2
FROM market_dispersion
WHERE dispersion_version = 'dispersion_24h_v1' AND usable
  AND end_time >= '2026-06-13 00:00:00+00' AND end_time < '2026-08-01 00:00:00+00';

\echo '== (6) cobertura por dia: minutos gravados, usáveis, cobertura =='
SELECT (end_time AT TIME ZONE 'UTC')::date AS dia,
       count(*)                            AS minutos,
       count(*) FILTER (WHERE usable)      AS usaveis,
       round(min(coverage), 4)             AS cobertura_min,
       round(avg(coverage), 4)             AS cobertura_media,
       min(covered)                        AS cobertos_min,
       max(universe_size)                  AS universo,
       round(avg(dispersion), 4)           AS dispersao_media,
       round(min(dispersion), 4)           AS dispersao_min,
       round(max(dispersion), 4)           AS dispersao_max
FROM market_dispersion
WHERE dispersion_version = 'dispersion_24h_v1'
GROUP BY 1
ORDER BY 1;

\echo '== (6b) dias com cobertura >= 80 % em todos os minutos, e dias completos (1440) =='
SELECT count(*) AS dias,
       count(*) FILTER (WHERE cobertura_min >= 0.80) AS dias_cobertura_ok,
       count(*) FILTER (WHERE minutos = 1440)        AS dias_completos
FROM (
  SELECT (end_time AT TIME ZONE 'UTC')::date AS dia, count(*) AS minutos, min(coverage) AS cobertura_min
  FROM market_dispersion WHERE dispersion_version = 'dispersion_24h_v1'
  GROUP BY 1
) d;

\echo '== (7) as linhas inutilizáveis, nomeadas =='
SELECT reason, count(*) AS minutos, min(end_time) AS de, max(end_time) AS ate
FROM market_dispersion
WHERE dispersion_version = 'dispersion_24h_v1' AND NOT usable
GROUP BY reason ORDER BY 2 DESC;

\echo '== (8) a linha de auditoria do backfill =='
SELECT created_at, actor_type, action, entity_type, metadata::text AS metadata, coalesce(after::text, '') AS after
FROM audit_logs
WHERE action = 'market_dispersion.backfill'
ORDER BY created_at DESC LIMIT 3;

\echo '== (9) as leituras que motivaram H-P18 (10/09 19:10Z e 11/09 11:11Z), na série =='
SELECT end_time, btc_r24h, median_alt_r24h, dispersion, share_below_btc, covered, coverage
FROM market_dispersion
WHERE dispersion_version = 'dispersion_24h_v1'
  AND end_time IN ('2026-09-10 19:10:00+00', '2026-09-11 11:11:00+00', '2026-09-11 12:36:00+00')
ORDER BY end_time;

commit;
