-- R12/Q04 (KB-0104) — variante conservadora: tira do numerador SO as graduadas da perna D
-- (completed_at - created_at <= 60 s), sem a perna F. E o limite inferior honesto do efeito:
-- a perna F mistura "o radar nunca a viu" (falta de cobertura) com "nasceu cheia".
SET statement_timeout = 60000;
WITH nm AS (
  SELECT t.mint, t.created_at, t.completed_at,
         (t.created_at AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt,
         (t.completed_at IS NOT NULL AND t.completed_at - t.created_at <= interval '60 seconds') AS d60
  FROM meme_tokens t
  WHERE t.created_at >= (date '2026-09-12' AT TIME ZONE 'America/Sao_Paulo')
    AND t.created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
    AND coalesce(t.mayhem_enabled, false) = false
), r AS (
  SELECT nm.mint, nm.created_at, nm.completed_at, nm.dia_brt, nm.d60,
         max(cs.real_sol_reserves) AS pico_sol,
         min(cs.observed_at) FILTER (WHERE cs.real_sol_reserves >= 30) AS at_30
  FROM nm JOIN meme_curve_snapshots cs ON cs.mint = nm.mint
  GROUP BY 1,2,3,4,5
)
SELECT dia_brt, count(*) AS moedas,
  count(*) FILTER (WHERE pico_sol >= 10 AND NOT d60) AS ge10_sem_d,
  count(*) FILTER (WHERE pico_sol >= 30 AND NOT d60) AS ge30_sem_d,
  count(*) FILTER (WHERE completed_at IS NOT NULL AND NOT d60) AS grad_sem_d,
  round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM at_30 - created_at)/60)
        FILTER (WHERE at_30 IS NOT NULL AND NOT d60))::numeric, 2) AS med_min_30_sem_d,
  count(*) FILTER (WHERE at_30 IS NOT NULL AND at_30 - created_at >= interval '3 minutes' AND NOT d60) AS lentas_sem_d,
  count(*) FILTER (WHERE at_30 IS NOT NULL AND at_30 - created_at >= interval '3 minutes'
                     AND completed_at IS NOT NULL AND NOT d60) AS lentas_grad_sem_d
FROM r GROUP BY 1 ORDER BY 1;
