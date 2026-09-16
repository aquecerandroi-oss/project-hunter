-- R34 q04 — cobertura da fita por BOARD (new/graduating/movers/graduated) no dia BRT.
-- Uma moeda pode aparecer em mais de um board; contamos por (board, mint).
\set d0 '2026-09-15 03:00+00'
\set d1 '2026-09-16 03:00+00'
SET statement_timeout = 60000;
WITH b AS (
  SELECT DISTINCT board, mint FROM meme_board_observations
  WHERE observed_at >= timestamptz :'d0' AND observed_at < timestamptz :'d1'
), t AS (
  SELECT mint, sum(sol_lamports) / 1e9 AS tape_sol, count(*) AS n
  FROM meme_trades
  WHERE block_time >= timestamptz :'d0' AND block_time < timestamptz :'d1' AND program = 'pump'
  GROUP BY 1
), c AS (
  SELECT mint, count(*) AS fotos FROM meme_curve_snapshots
  WHERE observed_at >= timestamptz :'d0' AND observed_at < timestamptz :'d1'
  GROUP BY 1
)
SELECT b.board,
       count(*) AS moedas_no_board,
       count(c.mint) AS com_fotos_de_curva,
       count(t.mint) AS com_fita,
       round(100.0 * count(t.mint) / count(*), 1) AS pct_com_fita,
       round(sum(t.tape_sol)::numeric, 0) AS fita_sol,
       sum(t.n) AS negocios
FROM b LEFT JOIN t ON t.mint = b.mint LEFT JOIN c ON c.mint = b.mint
GROUP BY 1 ORDER BY 2 DESC;
