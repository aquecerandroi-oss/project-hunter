-- R13/Q04 (KB-0105) — efeito da E2-b no R das apostas de papel MEDIDAS do dia.
-- Universo: meme_paper_bets com status='closed' e outcome_quality='measured', entry_at no dia BRT.
-- Para cada aposta, dois carimbos da E2-b:
--   (i) flag_hist  = encheu <= 60 s do mint OU maior comprador >= 35 % de TODO o SOL comprado na subida
--                    (so existe se a moeda encheu; e' o carimbo retrospectivo, igual ao do rotulo);
--   (ii) flag_live = maior comprador >= 35 % do SOL comprado DO MINT ATE entry_at — a unica perna
--                    legivel no instante da decisao (a perna do tempo de enchimento, se ja verdadeira,
--                    implicaria curva cheia e a mesa nem compraria: `curve_complete`).
-- R e' r_multiple (ja em R). Somas em R, sem converter para SOL/BRL.
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
),
tr_hist AS (
  SELECT b.id, tr.trader, sum(tr.sol_lamports) / 1e9 AS sol
  FROM b JOIN meme_trades tr ON tr.mint = b.mint AND tr.side = 'buy'
   AND tr.block_time >= b.created_at - interval '1 minute'
   AND tr.block_time <= coalesce(b.completed_at, b.entry_at) + interval '1 minute'
  GROUP BY 1, 2
),
hist AS (
  SELECT id, count(*) AS compradores_subida, sum(sol) AS sol_subida,
         max(sol) / nullif(sum(sol), 0) AS fatia_do_maior_hist
  FROM tr_hist GROUP BY 1
),
m AS (
  SELECT b.id, b.mint, b.r_multiple, b.encheu_60s,
         l.fatia_do_maior_live, l.compradores_ate_entrada, l.sol_ate_entrada,
         h.fatia_do_maior_hist, h.compradores_subida,
         (b.encheu_60s OR coalesce(h.fatia_do_maior_hist, 0) >= 0.35) AS flag_hist,
         (coalesce(l.fatia_do_maior_live, 0) >= 0.35) AS flag_live
  FROM b LEFT JOIN live l ON l.id = b.id LEFT JOIN hist h ON h.id = b.id
)
SELECT grupo, marcada, n,
       round(soma_r, 3) AS soma_r, round(media_r, 3) AS media_r,
       ganhadoras, round(melhor_r, 3) AS melhor_r, round(pior_r, 3) AS pior_r
FROM (
  SELECT 'flag_hist (retrospectivo)' AS grupo, flag_hist::text AS marcada, count(*) AS n,
         sum(r_multiple) AS soma_r, avg(r_multiple) AS media_r,
         count(*) FILTER (WHERE r_multiple > 0) AS ganhadoras,
         max(r_multiple) AS melhor_r, min(r_multiple) AS pior_r
  FROM m GROUP BY 1, 2
  UNION ALL
  SELECT 'flag_live (>= 35 % ate a entrada)', flag_live::text, count(*),
         sum(r_multiple), avg(r_multiple), count(*) FILTER (WHERE r_multiple > 0),
         max(r_multiple), min(r_multiple)
  FROM m GROUP BY 1, 2
  UNION ALL
  SELECT 'TOTAL', 'todas', count(*), sum(r_multiple), avg(r_multiple),
         count(*) FILTER (WHERE r_multiple > 0), max(r_multiple), min(r_multiple)
  FROM m
) x ORDER BY grupo, marcada;
