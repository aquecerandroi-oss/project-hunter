-- R22 q03 — a explicacao: 115 de 115 leituras com top10_share > 1 sao Mayhem.
-- Resposta 16/09:
--   true|paused|bot=f    n=80    gt1=80  med=1.1240  (8 mints)
--   true|paused|bot=t    n=89    gt1=24  med=0.9961 (12 mints)
--   false|completed|f    n=9     gt1=8   med=1.3706  (2 mints)
--   true|active|f        n=4     gt1=3   med=1.2094  (4 mints)
--   false|(sem estado)   n=20319 gt1=0   med=0.2575 (2825 mints)  <-- a populacao da mesa
--   false|completed|t    n=3     gt1=0   med=0.1285  (3 mints)
SELECT coalesce(is_mayhem::text, 'null') AS may,
       coalesce(mayhem_state, '-') AS estado,
       (coalesce((raw->>'mayhemBotCoinSupplied')::numeric, 0) > 0) AS bot_supriu,
       count(*) AS n,
       count(*) FILTER (WHERE top10_share > 1) AS gt1,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY top10_share)::numeric, 4) AS med,
       count(DISTINCT mint) AS mints
FROM meme_risk_snapshots
GROUP BY 1, 2, 3
ORDER BY gt1 DESC;
