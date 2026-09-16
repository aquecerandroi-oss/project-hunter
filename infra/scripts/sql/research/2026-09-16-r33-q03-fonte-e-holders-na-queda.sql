-- Coorte comum das quatro consultas da R33 (16/09/2026, 19:00-22:00 UTC = 16:00-19:00 BRT;
-- na pratica a serie acaba as 20:35 UTC = 17:35 BRT, o relogio da medicao).
-- "voltou ao piso" = pico de mcap_sol >= 40 SOL e a ULTIMA foto com mcap_sol <= 28,5 e
-- curve_progress_pct < 0,05 (fracao). drop_time = a primeira foto <= 28,5 depois do pico.
SET statement_timeout = 60000;
CREATE TEMP TABLE coh AS
WITH w AS (
  SELECT mint, end_time, mcap_sol, curve_progress_pct
  FROM meme_features_1m
  WHERE end_time >= timestamptz '2026-09-16 19:00:00+00'
    AND end_time <  timestamptz '2026-09-16 22:00:00+00'
    AND mcap_sol IS NOT NULL
), agg AS (
  SELECT mint, max(mcap_sol) AS peak FROM w GROUP BY mint HAVING max(mcap_sol) >= 40
), pk AS (
  SELECT DISTINCT ON (w.mint) w.mint, w.end_time AS peak_t, w.mcap_sol AS peak
  FROM w JOIN agg USING (mint) ORDER BY w.mint, w.mcap_sol DESC, w.end_time
), lst AS (
  SELECT DISTINCT ON (mint) mint, end_time AS last_t, mcap_sol AS last_mcap,
         curve_progress_pct AS last_prog
  FROM w ORDER BY mint, end_time DESC
), d AS (
  SELECT DISTINCT ON (w.mint) w.mint, w.end_time AS drop_time, w.mcap_sol AS drop_mcap
  FROM w JOIN pk ON pk.mint = w.mint
  WHERE w.end_time > pk.peak_t AND w.mcap_sol <= 28.5
  ORDER BY w.mint, w.end_time
)
SELECT pk.mint, pk.peak, pk.peak_t, l.last_t, l.last_mcap, l.last_prog, d.drop_time, d.drop_mcap,
       CASE WHEN l.last_mcap <= 28.5 AND l.last_prog < 0.05 THEN 'floor' ELSE 'no_floor' END AS cohort
FROM pk JOIN lst l USING (mint) LEFT JOIN d USING (mint);
CREATE INDEX ON coh (mint);

-- Q01: tamanho das duas coortes e o que a serie diz do desfecho.

-- Q03: a queda coincide com uma troca de leitor? o holders zera por falha?
-- snapshot_source no minuto anterior vs no minuto da queda.
SELECT coalesce(prev_src,'(sem linha)') AS fonte_antes,
       coalesce(drop_src,'(sem linha)') AS fonte_na_queda, count(*) AS mints
FROM (
  SELECT c.mint,
    (SELECT f.snapshot_source FROM meme_features_1m f
      WHERE f.mint = c.mint AND f.end_time = c.drop_time - interval '1 minute') AS prev_src,
    (SELECT f.snapshot_source FROM meme_features_1m f
      WHERE f.mint = c.mint AND f.end_time = c.drop_time) AS drop_src
  FROM coh c WHERE c.cohort = 'floor' AND c.drop_time IS NOT NULL) x
GROUP BY 1,2 ORDER BY 3 DESC;

-- A cadeia diz a mesma coisa nos dois subgrupos (quem ja vinha de solana_rpc e quem trocou)?
WITH s AS (
  SELECT c.mint, c.peak_t, c.drop_time,
    (SELECT f.snapshot_source FROM meme_features_1m f
      WHERE f.mint = c.mint AND f.end_time = c.drop_time - interval '1 minute') AS prev_src,
    (SELECT max(x.real_sol_reserves) FROM meme_curve_snapshots x
      WHERE x.mint = c.mint AND x.source = 'solana_rpc'
        AND x.observed_at BETWEEN c.peak_t - interval '60 seconds'
                              AND c.peak_t + interval '60 seconds') AS rs_pico,
    (SELECT min(x.real_sol_reserves) FROM meme_curve_snapshots x
      WHERE x.mint = c.mint AND x.source = 'solana_rpc'
        AND x.observed_at BETWEEN c.drop_time - interval '60 seconds'
                              AND c.drop_time + interval '120 seconds') AS rs_queda
  FROM coh c WHERE c.cohort = 'floor' AND c.drop_time IS NOT NULL)
SELECT coalesce(prev_src,'(sem linha)') AS fonte_antes, count(*) AS mints,
       round(avg(rs_pico),2) AS real_sol_no_pico, round(avg(rs_queda),3) AS real_sol_na_queda,
       count(*) FILTER (WHERE rs_queda <= 0.5) AS cadeia_diz_vazia
FROM s GROUP BY 1 ORDER BY 2 DESC;

-- holders no minuto da queda: quem leu, com que motivo, e o delta.
SELECT f.holders_source, f.holders_reason, f.snapshot_source, count(*) AS linhas,
       round(avg(f.holders),1) AS holders_medio
FROM coh c JOIN meme_features_1m f ON f.mint = c.mint AND f.end_time = c.drop_time
WHERE c.cohort = 'floor' GROUP BY 1,2,3 ORDER BY linhas DESC;

SELECT round(avg(h_antes),1) AS holders_antes, round(avg(h_queda),1) AS holders_na_queda,
       count(*) FILTER (WHERE h_queda IS NULL) AS n_nulos, count(*) AS n
FROM (SELECT c.mint,
  (SELECT f.holders FROM meme_features_1m f
    WHERE f.mint = c.mint AND f.end_time = c.drop_time - interval '1 minute') AS h_antes,
  (SELECT f.holders FROM meme_features_1m f
    WHERE f.mint = c.mint AND f.end_time = c.drop_time) AS h_queda
 FROM coh c WHERE c.cohort = 'floor' AND c.drop_time IS NOT NULL) y;
