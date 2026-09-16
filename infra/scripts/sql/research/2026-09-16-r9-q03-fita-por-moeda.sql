-- R9/Q03 (KB-0103) — uma linha por graduada COM cobertura de fita (meme_trades): compradores unicos
-- distintos ate encher, SOL comprado, e a concentracao (maior comprador). Serve de RÓTULO para Q04:
-- "organica" = encheu com muitos compradores distintos; "forjada" = muito SOL para poucas carteiras.
SET statement_timeout = 240000;
WITH g AS (
  SELECT t.mint, t.created_at, t.completed_at
  FROM meme_tokens t
  WHERE t.created_at >= (date '2026-09-14' AT TIME ZONE 'America/Sao_Paulo')
    AND t.created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
    AND t.completed_at IS NOT NULL
),
tr AS (
  SELECT g.mint, tr.trader, sum(tr.sol_lamports) / 1e9 AS sol
  FROM g JOIN meme_trades tr ON tr.mint = g.mint
   AND tr.block_time >= g.created_at - interval '1 minute'
   AND tr.block_time <= g.completed_at + interval '1 minute'
   AND tr.side = 'buy'
  GROUP BY 1, 2
)
SELECT mint, count(*) AS compradores, round(sum(sol)::numeric, 3) AS sol_comprado,
       round((max(sol) / nullif(sum(sol), 0))::numeric, 4) AS fatia_do_maior
FROM tr GROUP BY 1;
