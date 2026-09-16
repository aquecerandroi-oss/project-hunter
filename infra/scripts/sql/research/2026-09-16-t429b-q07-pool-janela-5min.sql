-- T4.29b — q07: a pool pelo modelo que o proprio projeto usa para precificar a saida
-- (packages/indicators/hunter_indicators/meme/pool.py): participacao sobre o volume
-- em SOL dos ULTIMOS 5 MINUTOS da fita pump_amm, teto de 1 %.
-- Logo, para uma ordem de X SOL ficar em 1 % e preciso 100*X SOL em 5 min:
--   0,05 -> 5 SOL/5min ; 1 -> 100 ; 2 -> 200 ; 5 -> 500 ; 9,8 -> 980.
-- Universo: moedas com migrated_at nos ultimos 7 dias, fita depois da migracao.
-- Cobertura parcial por desenho (so mints rastreados) - limite inferior, nao medida do mercado.
WITH mig AS (
  SELECT mint, migrated_at FROM meme_tokens WHERE migrated_at >= now() - make_interval(days => 7)
), tape AS (
  SELECT tr.mint, tr.block_time, tr.sol_lamports / 1e9 AS sol
  FROM meme_trades tr JOIN mig ON mig.mint = tr.mint
  WHERE tr.block_time >= now() - make_interval(days => 7)
    AND tr.program = $$pump_amm$$ AND tr.block_time >= mig.migrated_at
), w AS (
  SELECT mint, block_time,
         sum(sol) OVER (PARTITION BY mint ORDER BY block_time
                        RANGE BETWEEN make_interval(mins => 5) PRECEDING AND CURRENT ROW) AS vol5m
  FROM tape
)
SELECT count(*)                                                            AS trades,
       count(DISTINCT mint)                                                AS moedas,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY vol5m)::numeric, 3) AS vol5m_p50,
       round(percentile_cont(0.90) WITHIN GROUP (ORDER BY vol5m)::numeric, 3) AS p90,
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY vol5m)::numeric, 3) AS p99,
       round(max(vol5m)::numeric, 3)                                       AS maximo,
       count(*) FILTER (WHERE vol5m >= 5)                                  AS cabe_005_sol,
       count(*) FILTER (WHERE vol5m >= 100)                                AS cabe_1_sol,
       count(DISTINCT mint) FILTER (WHERE vol5m >= 100)                    AS moedas_1_sol,
       count(*) FILTER (WHERE vol5m >= 200)                                AS cabe_2_sol,
       count(*) FILTER (WHERE vol5m >= 500)                                AS cabe_5_sol,
       count(*) FILTER (WHERE vol5m >= 980)                                AS cabe_98_sol,
       count(DISTINCT mint) FILTER (WHERE vol5m >= 980)                    AS moedas_98_sol
FROM w
