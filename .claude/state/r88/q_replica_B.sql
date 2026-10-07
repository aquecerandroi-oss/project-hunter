-- R88 réplica cega e independente do número de cabeça (B, D_adj a 0,35) — tudo no servidor, sem o código Python
BEGIN READ ONLY;
SET LOCAL statement_timeout='900s';
WITH d AS (
  SELECT p.id pid, p.mint, p.proposed_at, rs.name||'/'||rs.version AS rs, COALESCE(e->'derived', e) AS dv
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id,
       LATERAL jsonb_array_elements(p.reasons) e
  WHERE e->>'feature'='decision_tape' AND p.proposed_at >= '2026-09-24' AND p.proposed_at < '2026-10-07'),
unit AS (  -- proposta mais antiga do par (conjunto, mint) com aposta single
  SELECT * FROM (
    SELECT d.*, b.id bid, b.status, b.outcome_quality, b.pnl_sol, (b.entry->>'sol_spent')::numeric spent,
           row_number() OVER (PARTITION BY d.rs, d.mint ORDER BY d.proposed_at, b.entry_at, b.id) rn
    FROM d JOIN meme_paper_bets b ON b.proposal_id=d.pid AND b.leg='single') z WHERE rn=1),
g AS (  -- guardas da variável (antes de desfecho)
  SELECT * FROM unit WHERE dv->>'reason' IS NULL AND dv->'ledger'->>'reason' IS NULL
    AND (dv->'ledger'->>'wallets')::int >= 10 AND dv->'largest_net_buyer'->>'share_of_real_sol' IS NOT NULL),
big AS (SELECT rs FROM g GROUP BY rs HAVING count(*) >= 30),
m AS (SELECT g.rs, ((dv->'largest_net_buyer'->>'share_of_real_sol')::numeric <= 0.35) AS baixo, pnl_sol/spent AS r
      FROM g JOIN big USING (rs) WHERE status='closed' AND outcome_quality='measured' AND pnl_sol IS NOT NULL),
ps AS (SELECT rs, count(*) n, avg(r) FILTER (WHERE baixo) mb, avg(r) FILTER (WHERE NOT baixo) ma,
              count(*) FILTER (WHERE baixo) nb, count(*) FILTER (WHERE NOT baixo) na FROM m GROUP BY rs),
sup AS (SELECT * FROM ps WHERE nb >= 5 AND na >= 5)
SELECT (SELECT count(*) FROM m) unidades,
       round(sum(n*(mb-ma))/sum(n), 6) AS d_adj,
       round((SELECT avg(r) FILTER (WHERE baixo) - avg(r) FILTER (WHERE NOT baixo) FROM m), 6) AS d_agrupado,
       string_agg(rs||':'||n||'('||nb||'/'||na||')', ' ' ORDER BY rs) conjuntos
FROM sup;
COMMIT;
