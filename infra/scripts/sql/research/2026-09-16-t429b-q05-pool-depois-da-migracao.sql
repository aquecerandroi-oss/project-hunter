-- T4.29b — q05: o lado migrado. O que o NOSSO banco sabe da pool PumpSwap.
-- Fonte unica: meme_trades com program = pump_amm (a fita do swap-api, T4.11).
-- NAO existe tabela de reservas/liquidez da pool no schema (verificado em
-- information_schema.tables: nenhuma tabela meme_pool*). Logo impacto de preco na
-- pool NAO e calculavel do nosso banco - so participacao sobre a fita (o modelo de
-- packages/indicators/hunter_indicators/meme/pool.py: participacao em 5 min, teto 1 %).
-- Cobertura: a fita da pool so e puxada para os mints que o Lab rastreia, entao a
-- taxa de cobertura abaixo e um limite inferior do mercado, nao a sua medida.
WITH mig AS (
  SELECT mint, migrated_at FROM meme_tokens
  WHERE migrated_at >= now() - make_interval(days => 7)
), tape AS (
  SELECT tr.mint, date_trunc($$minute$$, tr.block_time) AS minuto,
         sum(tr.sol_lamports) / 1e9 AS vol_sol, count(*) AS trades
  FROM meme_trades tr
  JOIN mig ON mig.mint = tr.mint
  WHERE tr.block_time >= now() - make_interval(days => 7)
    AND tr.program = $$pump_amm$$
    AND tr.block_time >= mig.migrated_at
  GROUP BY 1, 2
)
SELECT (SELECT count(*) FROM mig)                                                AS migradas_7d,
       (SELECT count(DISTINCT mint) FROM tape)                                   AS migradas_com_fita_de_pool,
       count(*)                                                                  AS minutos_moeda_pool,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY vol_sol)::numeric, 4)  AS p50_vol_1m_sol,
       round(percentile_cont(0.90) WITHIN GROUP (ORDER BY vol_sol)::numeric, 4)  AS p90,
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY vol_sol)::numeric, 4)  AS p99,
       round(max(vol_sol)::numeric, 4)                                           AS maximo,
       count(*) FILTER (WHERE vol_sol >= 100)                                    AS ge_100,
       count(*) FILTER (WHERE vol_sol >= 200)                                    AS ge_200,
       count(*) FILTER (WHERE vol_sol >= 500)                                    AS ge_500,
       count(*) FILTER (WHERE vol_sol >= 980)                                    AS ge_980
FROM tape
