-- R13/Q05 (KB-0105) — uma linha por aposta MEDIDA do dia, com os insumos da E2-b lidos ate a entrada
-- (fatia do maior comprador, compradores, SOL) e o R realizado. Serve para a sensibilidade do limiar
-- de concentracao no R (25/35/45 %) e para checar a base: quantos compradores a fita ja tinha na entrada.
SET statement_timeout = 240000;
WITH b AS (
  SELECT pb.id, pb.mint, pb.entry_at, pb.r_multiple, t.created_at, t.completed_at,
         (t.completed_at IS NOT NULL
          AND extract(epoch FROM t.completed_at - t.created_at) <= 60) AS encheu_60s
  FROM meme_paper_bets pb
  JOIN meme_tokens t ON t.mint = pb.mint
  WHERE pb.entry_at >= timestamptz '2026-09-12 00:00:00-03'
    AND pb.entry_at <  timestamptz '2026-09-13 00:00:00-03'
    AND pb.status = 'closed' AND pb.outcome_quality = 'measured'
),
tr_live AS (
  SELECT b.id, tr.trader, sum(tr.sol_lamports) / 1e9 AS sol
  FROM b JOIN meme_trades tr ON tr.mint = b.mint AND tr.side = 'buy'
   AND tr.block_time >= b.created_at - interval '1 minute' AND tr.block_time <= b.entry_at
  GROUP BY 1, 2
),
live AS (
  SELECT id, count(*) AS compradores_ate_entrada, sum(sol) AS sol_ate_entrada,
         max(sol) / nullif(sum(sol), 0) AS fatia_do_maior_live
  FROM tr_live GROUP BY 1
)
SELECT b.id, b.mint, round(extract(epoch FROM b.entry_at - b.created_at)::numeric, 0) AS idade_na_entrada_s,
       (b.completed_at IS NOT NULL) AS graduou, b.encheu_60s,
       l.compradores_ate_entrada, round(l.sol_ate_entrada::numeric, 2) AS sol_ate_entrada,
       round(l.fatia_do_maior_live::numeric, 4) AS fatia_live, b.r_multiple
FROM b LEFT JOIN live l ON l.id = b.id ORDER BY b.entry_at;
