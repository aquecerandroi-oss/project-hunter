-- R9/Q02 (KB-0103) — (i) o que a porta do laboratorio recusou de fato em 3 d (meme_proposals.refusal),
-- (ii) a fita real (meme_trades) das graduadas: compradores unicos distintos e SOL comprado ate encher,
-- separando "instantanea" (carimbo de conclusao <= 60 s do mint) de "lenta".
-- Nota: lab_gate_refusals nao e' historico; a unica trilha persistida e' meme_proposals.refusal.
SET statement_timeout = 240000;

-- (i) vocabulario de recusa efetivamente gravado, 3 d
SELECT 'refusal' AS bloco, coalesce(p.refusal, '(sem refusal)') AS chave, count(*) AS n
FROM meme_proposals p
WHERE p.proposed_at >= now() - interval '3 days'
GROUP BY 1, 2 ORDER BY n DESC;

-- (ii) a fita das graduadas (so onde meme_trades tem cobertura)
WITH g AS (
  SELECT t.mint, t.created_at, t.completed_at,
         (extract(epoch FROM t.completed_at - t.created_at) <= 60) AS instantanea
  FROM meme_tokens t
  WHERE t.created_at >= (date '2026-09-14' AT TIME ZONE 'America/Sao_Paulo')
    AND t.created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
    AND t.completed_at IS NOT NULL
),
fita AS (
  SELECT g.mint, g.instantanea,
         count(DISTINCT tr.trader) FILTER (WHERE tr.side = 'buy') AS compradores,
         count(*) FILTER (WHERE tr.side = 'buy') AS n_buys,
         sum(tr.sol_lamports) FILTER (WHERE tr.side = 'buy') / 1e9 AS sol_comprado
  FROM g JOIN meme_trades tr ON tr.mint = g.mint
   AND tr.block_time >= g.created_at - interval '1 minute'
   AND tr.block_time <= g.completed_at + interval '1 minute'
  GROUP BY 1, 2
)
SELECT 'fita' AS bloco, instantanea::text AS chave, count(*) AS n,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY compradores) AS med_compradores,
       percentile_disc(0.9) WITHIN GROUP (ORDER BY compradores) AS p90_compradores,
       round(percentile_disc(0.5) WITHIN GROUP (ORDER BY sol_comprado)::numeric, 2) AS med_sol,
       count(*) FILTER (WHERE compradores <= 5) AS ate_5_compradores
FROM fita GROUP BY 1, 2;
