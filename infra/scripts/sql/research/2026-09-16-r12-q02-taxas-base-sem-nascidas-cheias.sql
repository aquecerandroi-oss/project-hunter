-- R12/Q02 (KB-0104) — taxas-base da KB-0098 §6 recalculadas SEM as graduacoes nascidas cheias.
-- Lado a lado: coluna "_orig" = como a KB-0098 contou; coluna sem sufixo = tirando as nascidas cheias
-- (rotulo D OR F da Q01) do numerador de "encheu/graduou" e da graduacao da celula lenta.
-- Patamares reais: 10 / 30 / 85 SOL de real_sol_reserves (85,005 = limiar de graduacao do registro).
-- Populacao: meme_tokens nao-Mayhem criadas no dia BRT, com pelo menos uma foto de curva.
SET statement_timeout = 60000;
WITH nm AS (
  SELECT t.mint, t.created_at, t.completed_at,
         (t.created_at AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt
  FROM meme_tokens t
  WHERE t.created_at >= (date '2026-09-12' AT TIME ZONE 'America/Sao_Paulo')
    AND t.created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
    AND coalesce(t.mayhem_enabled, false) = false
), r AS (
  SELECT nm.mint, nm.created_at, nm.completed_at, nm.dia_brt,
         max(cs.real_sol_reserves) AS pico_sol,
         min(cs.observed_at) FILTER (WHERE cs.real_sol_reserves >= 10) AS at_10,
         min(cs.observed_at) FILTER (WHERE cs.real_sol_reserves >= 30) AS at_30,
         min(cs.observed_at) FILTER (WHERE cs.real_sol_reserves >= 85) AS at_85
  FROM nm JOIN meme_curve_snapshots cs ON cs.mint = nm.mint
  GROUP BY 1,2,3,4
), lab AS (
  SELECT r.*,
    (r.completed_at IS NOT NULL) AS graduou,
    (r.completed_at IS NOT NULL AND (
        r.completed_at - r.created_at <= interval '60 seconds'
        OR NOT EXISTS (SELECT 1 FROM meme_features_15s f
                        WHERE f.mint = r.mint AND f.as_of >= r.created_at AND f.as_of <= r.completed_at
                          AND f.curve_progress_pct IS NOT NULL AND f.curve_progress_pct < 0.9))
    ) AS nascida_cheia,
    (r.at_30 IS NOT NULL AND r.at_30 - r.created_at >= interval '3 minutes') AS lenta
  FROM r
)
SELECT dia_brt,
  count(*) AS moedas,
  count(*) FILTER (WHERE pico_sol >= 10) AS ge10_orig,
  count(*) FILTER (WHERE pico_sol >= 10 AND NOT nascida_cheia) AS ge10,
  count(*) FILTER (WHERE pico_sol >= 30) AS ge30_orig,
  count(*) FILTER (WHERE pico_sol >= 30 AND NOT nascida_cheia) AS ge30,
  count(*) FILTER (WHERE pico_sol >= 85) AS ge85_orig,
  count(*) FILTER (WHERE pico_sol >= 85 AND NOT nascida_cheia) AS ge85,
  count(*) FILTER (WHERE graduou) AS grad_orig,
  count(*) FILTER (WHERE graduou AND NOT nascida_cheia) AS grad_organica,
  round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM at_30 - created_at)/60)
        FILTER (WHERE at_30 IS NOT NULL))::numeric, 2) AS med_min_30_orig,
  round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM at_30 - created_at)/60)
        FILTER (WHERE at_30 IS NOT NULL AND NOT nascida_cheia))::numeric, 2) AS med_min_30,
  count(*) FILTER (WHERE lenta) AS lentas_orig,
  count(*) FILTER (WHERE lenta AND NOT nascida_cheia) AS lentas,
  count(*) FILTER (WHERE lenta AND graduou) AS lentas_grad_orig,
  count(*) FILTER (WHERE lenta AND graduou AND NOT nascida_cheia) AS lentas_grad_organica
FROM lab GROUP BY 1 ORDER BY 1;
