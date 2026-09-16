-- R34 q02 — cobertura da fita por IDADE da moeda, casando moeda a moeda.
-- Para cada mint: SOL da cadeia (|delta real_sol_reserves| entre fotos <= 60 s) e SOL da fita
-- (meme_trades, program = pump) no mesmo balde de idade. A razao so faz sentido casada:
-- o agregado por hora compara conjuntos de moedas diferentes.
\set d0 '2026-09-15 03:00+00'
\set d1 '2026-09-16 03:00+00'
SET statement_timeout = 60000;
WITH tok AS (
  SELECT mint, created_at FROM meme_tokens WHERE created_at IS NOT NULL
), s AS (
  SELECT c.mint, c.observed_at, c.real_sol_reserves,
         lag(c.real_sol_reserves) OVER (PARTITION BY c.mint ORDER BY c.observed_at) AS prev,
         lag(c.observed_at)       OVER (PARTITION BY c.mint ORDER BY c.observed_at) AS prev_at
  FROM meme_curve_snapshots c
  WHERE c.observed_at >= timestamptz :'d0' AND c.observed_at < timestamptz :'d1'
), chain AS (
  SELECT s.mint,
         CASE WHEN extract(epoch FROM s.observed_at - t.created_at) < 60 THEN '1 0-60s'
              WHEN extract(epoch FROM s.observed_at - t.created_at) < 300 THEN '2 60-300s'
              WHEN extract(epoch FROM s.observed_at - t.created_at) < 1800 THEN '3 300-1800s'
              ELSE '4 >1800s' END AS idade,
         sum(abs(s.real_sol_reserves - s.prev)) AS chain_sol
  FROM s JOIN tok t USING (mint)
  WHERE s.prev IS NOT NULL AND s.observed_at - s.prev_at <= interval '60 seconds'
  GROUP BY 1, 2
), tape AS (
  SELECT m.mint,
         CASE WHEN extract(epoch FROM m.block_time - t.created_at) < 60 THEN '1 0-60s'
              WHEN extract(epoch FROM m.block_time - t.created_at) < 300 THEN '2 60-300s'
              WHEN extract(epoch FROM m.block_time - t.created_at) < 1800 THEN '3 300-1800s'
              ELSE '4 >1800s' END AS idade,
         sum(m.sol_lamports) / 1e9 AS tape_sol, count(*) AS n
  FROM meme_trades m JOIN tok t USING (mint)
  WHERE m.block_time >= timestamptz :'d0' AND m.block_time < timestamptz :'d1' AND m.program = 'pump'
  GROUP BY 1, 2
), j AS (
  SELECT coalesce(c.mint, p.mint) AS mint, coalesce(c.idade, p.idade) AS idade,
         coalesce(c.chain_sol, 0) AS chain_sol, coalesce(p.tape_sol, 0) AS tape_sol, coalesce(p.n, 0) AS n
  FROM chain c FULL OUTER JOIN tape p ON p.mint = c.mint AND p.idade = c.idade
)
SELECT idade,
       count(*) FILTER (WHERE chain_sol > 0) AS moedas_com_cadeia,
       count(*) FILTER (WHERE n > 0) AS moedas_com_fita,
       round(100.0 * count(*) FILTER (WHERE n > 0) / nullif(count(*) FILTER (WHERE chain_sol > 0), 0), 1) AS pct_moedas_com_fita,
       round(sum(chain_sol), 0) AS cadeia_sol,
       round(sum(tape_sol), 0) AS fita_sol,
       round(100 * sum(tape_sol) / nullif(sum(chain_sol), 0), 1) AS cobertura_sol_pct,
       round(100 * sum(tape_sol) FILTER (WHERE n > 0) / nullif(sum(chain_sol) FILTER (WHERE n > 0), 0), 1) AS cobertura_sol_pct_so_cobertas,
       round((100 * percentile_cont(0.5) WITHIN GROUP (ORDER BY tape_sol / nullif(chain_sol, 0)) FILTER (WHERE n > 0 AND chain_sol > 0))::numeric, 1) AS mediana_cobertura_pct_cobertas
FROM j GROUP BY 1 ORDER BY 1;
