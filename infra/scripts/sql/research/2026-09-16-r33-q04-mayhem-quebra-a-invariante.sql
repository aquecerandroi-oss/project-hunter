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

-- Q04: o UNICO artefato achado. Numa curva pump normal vale a invariante
-- virtual_sol_reserves - real_sol_reserves = 30 SOL (as reservas virtuais iniciais), o que
-- poe o piso da curva vazia em 30/1_073_000_191*1e9 = 27,96 SOL. Nas moedas Mayhem a
-- mecanica reescreve as reservas virtuais, a invariante cai, e mcap_sol/curve_progress_pct
-- deixam de ser comparaveis (chegam a 0,05 SOL e a progresso NEGATIVO).
SELECT c.cohort, count(*) AS linhas,
  count(*) FILTER (WHERE abs((s.virtual_sol_reserves - s.real_sol_reserves) - 30) <= 0.01) AS invariante_ok,
  count(DISTINCT s.mint) FILTER (WHERE abs((s.virtual_sol_reserves - s.real_sol_reserves) - 30) > 0.01) AS mints_que_quebram,
  count(DISTINCT s.mint) AS mints
FROM coh c JOIN meme_curve_snapshots s
  ON s.mint = c.mint AND s.source = 'solana_rpc'
 AND s.observed_at >= timestamptz '2026-09-16 19:00:00+00'
GROUP BY 1 ORDER BY 1;

-- Quem quebra a invariante e Mayhem: os mesmos 22 mints da coorte 'floor'.
SELECT tk.mayhem_enabled, tk.mayhem_mode, count(*) AS mints
FROM coh c JOIN meme_tokens tk ON tk.mint = c.mint
WHERE c.cohort = 'floor' GROUP BY 1,2 ORDER BY 3 DESC;

-- Quantas fotos da coorte 'floor' caem ABAIXO do piso de 27,9 SOL (impossivel numa curva normal).
SELECT count(*) AS mints_abaixo_do_piso,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_tokens tk
                                      WHERE tk.mint = c.mint AND tk.mayhem_enabled)) AS deles_mayhem,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_tokens tk
                                      WHERE tk.mint = c.mint AND tk.completed_at IS NOT NULL)) AS deles_migrados
FROM coh c WHERE c.cohort = 'floor' AND c.last_mcap < 27.9;
