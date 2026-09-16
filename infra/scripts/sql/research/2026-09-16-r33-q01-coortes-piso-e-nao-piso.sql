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
SELECT cohort, count(*) AS mints, count(drop_time) AS com_queda,
       round(avg(peak),1) AS pico_medio, round(avg(last_mcap),2) AS mcap_final_medio,
       round(avg(last_prog)::numeric,4) AS prog_final_medio
FROM coh GROUP BY 1 ORDER BY 1;

-- As 30 de cada lado (amostra pedida pelo brief), ordenadas por pico.
(SELECT 'floor' AS coorte, c.mint, tk.symbol, round(c.peak,1) AS pico, c.peak_t, c.drop_time,
        round(c.last_mcap,2) AS mcap_final, round(c.last_prog::numeric,4) AS prog_final, tk.mayhem_enabled
 FROM coh c LEFT JOIN meme_tokens tk ON tk.mint = c.mint
 WHERE c.cohort = 'floor' ORDER BY c.peak DESC LIMIT 30)
UNION ALL
(SELECT 'no_floor', c.mint, tk.symbol, round(c.peak,1), c.peak_t, c.drop_time,
        round(c.last_mcap,2), round(c.last_prog::numeric,4), tk.mayhem_enabled
 FROM coh c LEFT JOIN meme_tokens tk ON tk.mint = c.mint
 WHERE c.cohort = 'no_floor' ORDER BY c.peak DESC LIMIT 30);
