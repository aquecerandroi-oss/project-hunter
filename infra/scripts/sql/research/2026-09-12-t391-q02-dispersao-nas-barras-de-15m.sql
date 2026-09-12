-- T3.91 / EXP-0029 passo 1 (b) — o portão lê a linha cujo `end_time` é EXATAMENTE o
-- `source_bar_close`, e a grade de decisão de `mean_reversion v10` é de 15 min: a
-- previsão de "share de barras elegíveis" (e a checagem de população §2 da página) é
-- medida sobre os fechamentos múltiplos de 15 min da janela de replay, não sobre todos os
-- minutos. Janela do replay: 2026-06-16 (início da série) → 2026-09-11 (exclusivo), isto é,
-- fechamentos em (2026-06-16 00:00Z; 2026-09-11 00:00Z]. SOMENTE LEITURA, antes de derivar.
-- Irmão de `2026-09-11-t389-q02-breadth-nas-barras-de-15m.sql`.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset pager off
\echo '== (1) share por célula nos fechamentos de 15 min (janela do replay: 2026-06-16..2026-09-11) =='
WITH grade AS (
  SELECT g AS bar_close
  FROM generate_series('2026-06-16 00:15:00+00'::timestamptz, '2026-09-11 00:00:00+00'::timestamptz, interval '15 min') g
), j AS (
  SELECT grade.bar_close, md.dispersion, md.usable
  FROM grade
  LEFT JOIN market_dispersion md
         ON md.dispersion_version = 'dispersion_24h_v1' AND md.end_time = grade.bar_close
)
SELECT count(*)                                                                       AS barras_15m,
       count(*) FILTER (WHERE usable)                                                 AS com_linha_usavel,
       count(*) FILTER (WHERE usable AND dispersion >= -0.10 AND dispersion < -0.03)  AS a_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion >= -0.10 AND dispersion < -0.03) / count(*), 4) AS a_pct,
       count(*) FILTER (WHERE usable AND dispersion >= 0.00 AND dispersion < 0.10)    AS b_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion >= 0.00 AND dispersion < 0.10) / count(*), 4)   AS b_pct,
       count(*) FILTER (WHERE usable AND dispersion >= -0.03 AND dispersion < 0.00)   AS queda_conjunta_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion >= -0.03 AND dispersion < 0.00) / count(*), 4)  AS queda_conjunta_pct,
       count(*) FILTER (WHERE usable AND dispersion < -0.10)                          AS extrema_neg_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion < -0.10) / count(*), 4)                         AS extrema_neg_pct,
       count(*) FILTER (WHERE usable AND dispersion >= 0.10)                          AS acima_010_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion >= 0.10) / count(*), 4)                         AS acima_010_pct,
       count(*) FILTER (WHERE usable IS DISTINCT FROM true)                           AS sem_linha_usavel,
       round(100.0 * count(*) FILTER (WHERE usable IS DISTINCT FROM true) / count(*), 4)                          AS sem_linha_pct
FROM j;

\echo '== (2) o mesmo por janela de 30 dias (as três da régua: J1 06-16..07-16, J2 07-16..08-15, J3 08-15..09-11) =='
WITH grade AS (
  SELECT g AS bar_close
  FROM generate_series('2026-06-16 00:15:00+00'::timestamptz, '2026-09-11 00:00:00+00'::timestamptz, interval '15 min') g
), j AS (
  SELECT grade.bar_close, md.dispersion, md.usable
  FROM grade
  LEFT JOIN market_dispersion md
         ON md.dispersion_version = 'dispersion_24h_v1' AND md.end_time = grade.bar_close
)
SELECT CASE
         WHEN bar_close <= '2026-07-16 00:00:00+00' THEN 'J1 2026-06-16..07-16 (30 d)'
         WHEN bar_close <= '2026-08-15 00:00:00+00' THEN 'J2 2026-07-16..08-15 (30 d)'
         ELSE                                            'J3 2026-08-15..09-11 (27 d)'
       END AS janela,
       count(*) AS barras_15m,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion >= -0.10 AND dispersion < -0.03) / count(*), 4) AS a_pct,
       count(*) FILTER (WHERE usable AND dispersion >= -0.10 AND dispersion < -0.03)  AS a_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion >= 0.00 AND dispersion < 0.10) / count(*), 4)   AS b_pct,
       count(*) FILTER (WHERE usable AND dispersion >= 0.00 AND dispersion < 0.10)    AS b_barras,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion >= -0.03 AND dispersion < 0.00) / count(*), 4)  AS queda_conjunta_pct,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion < -0.10) / count(*), 4)                         AS extrema_neg_pct,
       round(100.0 * count(*) FILTER (WHERE usable AND dispersion >= 0.10) / count(*), 4)                         AS acima_010_pct,
       round(100.0 * count(*) FILTER (WHERE usable IS DISTINCT FROM true) / count(*), 4)                          AS sem_linha_pct,
       round(avg(dispersion), 6) AS dispersao_media
FROM j
GROUP BY 1 ORDER BY 1;

\echo '== (3) dias distintos com ao menos uma barra de 15 min em cada braço (projeção de "dias" da condição 2) =='
WITH grade AS (
  SELECT g AS bar_close
  FROM generate_series('2026-06-16 00:15:00+00'::timestamptz, '2026-09-11 00:00:00+00'::timestamptz, interval '15 min') g
), j AS (
  SELECT grade.bar_close, md.dispersion, md.usable
  FROM grade
  LEFT JOIN market_dispersion md
         ON md.dispersion_version = 'dispersion_24h_v1' AND md.end_time = grade.bar_close
)
SELECT count(DISTINCT (bar_close AT TIME ZONE 'UTC')::date) FILTER (WHERE usable AND dispersion >= -0.10 AND dispersion < -0.03) AS dias_a,
       count(DISTINCT (bar_close AT TIME ZONE 'UTC')::date) FILTER (WHERE usable AND dispersion >= 0.00 AND dispersion < 0.10)   AS dias_b,
       count(DISTINCT (bar_close AT TIME ZONE 'UTC')::date) AS dias_total
FROM j;

commit;
