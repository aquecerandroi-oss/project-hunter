-- R88 réplica independente (A, D_adj no limiar congelado 0,12216842020537061)
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
WITH d AS (
  SELECT p.id pid, p.mint, p.proposed_at, rs.name||'/'||rs.version AS rs, e
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id, LATERAL jsonb_array_elements(p.reasons) e
  WHERE e->>'feature'='pedigree_e2b' AND p.proposed_at < '2026-10-07'),
unit AS (SELECT * FROM (SELECT d.*, b.status, b.outcome_quality, b.pnl_sol, (b.entry->>'sol_spent')::numeric spent,
          row_number() OVER (PARTITION BY d.rs, d.mint ORDER BY d.proposed_at, b.entry_at, b.id) rn
          FROM d JOIN meme_paper_bets b ON b.proposal_id=d.pid AND b.leg='single') z WHERE rn=1),
m AS (SELECT rs, ((e->>'top_buyer_share')::numeric <= 0.1221684202053706200) baixo, pnl_sol/spent r FROM unit
      WHERE (e->>'buyers')::int >= 10 AND e->>'top_buyer_share' IS NOT NULL AND status='closed' AND outcome_quality='measured'),
ps AS (SELECT rs, count(*) n, avg(r) FILTER (WHERE baixo) mb, avg(r) FILTER (WHERE NOT baixo) ma,
       count(*) FILTER (WHERE baixo) nb, count(*) FILTER (WHERE NOT baixo) na FROM m GROUP BY rs)
SELECT (SELECT count(*) FROM m) unidades, round(sum(n*(mb-ma))/sum(n), 6) d_adj,
       string_agg(rs||':'||n||'('||nb||'/'||na||')', ' ' ORDER BY rs) conjuntos
FROM ps WHERE nb >= 5 AND na >= 5;
COMMIT;
