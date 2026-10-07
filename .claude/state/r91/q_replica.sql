-- R91 réplica CEGA e independente do número principal (D_adj de H e de P, primário), toda no servidor:
-- refaz unidades, estratos, suporte, pesos e médias a partir das tabelas, sem a lista congelada nem o Python.
BEGIN READ ONLY;
SET LOCAL statement_timeout='900s';
WITH f AS (
  SELECT p.id pid, p.mint, p.proposed_at, rs.name||'/'||rs.version rs, x.e fl
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  JOIN LATERAL (SELECT e FROM jsonb_array_elements(p.reasons) e WHERE e->>'feature'='flow' LIMIT 1) x ON true
  WHERE jsonb_typeof(p.reasons)='array' AND rs.name IN ('operator','flow_v2','recuo_v1','recuo_ctrl_v1')
    AND p.proposed_at < '2026-10-07 00:00:00+00'),
u AS (
  SELECT DISTINCT ON (f.rs, f.mint) f.*, b.status, b.outcome_quality, b.pnl_sol, (b.entry->>'sol_spent')::numeric sol_spent,
         b.entry->'snapshot'->>'mayhem_enabled' may
  FROM f JOIN meme_paper_bets b ON b.proposal_id=f.pid AND b.leg='single'
  ORDER BY f.rs, f.mint, f.proposed_at, b.entry_at, b.id),
s AS (
  SELECT u.*, u.rs || CASE WHEN u.rs='operator/5' AND u.proposed_at >= '2026-09-16 19:14:49.908897+00'
                            AND u.proposed_at < '2026-09-18 13:38:32.73237+00' THEN '|nada' ELSE '' END stratum
  FROM u LEFT JOIN meme_tokens t ON t.mint=u.mint
  WHERE COALESCE(u.may,'') <> 'true' AND COALESCE(t.mayhem_enabled,false) = false),
v AS (
  SELECT 'H' var, stratum, fl->>'holders_rising' val, status, outcome_quality, pnl_sol, sol_spent FROM s
  UNION ALL SELECT 'P', stratum, fl->>'progress_rising', status, outcome_quality, pnl_sol, sol_spent FROM s),
sup AS (  -- suporte antes dos desfechos: >= 5 unidades com aposta em cada braço
  SELECT var, stratum FROM v WHERE val IN ('true','false') GROUP BY 1,2
  HAVING count(*) FILTER (WHERE val='true') >= 5 AND count(*) FILTER (WHERE val='false') >= 5),
g AS (
  SELECT v.var, v.stratum,
         count(*) FILTER (WHERE val='true') nt, count(*) FILTER (WHERE val='false') nf,
         avg(pnl_sol/sol_spent) FILTER (WHERE val='true') mt, avg(pnl_sol/sol_spent) FILTER (WHERE val='false') mf
  FROM v JOIN sup USING (var, stratum)
  WHERE status='closed' AND outcome_quality='measured' AND pnl_sol IS NOT NULL AND sol_spent > 0 AND val IN ('true','false')
  GROUP BY 1,2)
SELECT var, count(*) estratos, sum(nt) n_true, sum(nf) n_false,
       round(sum(nt*nf::numeric/(nt+nf)*(mt-mf)) / sum(nt*nf::numeric/(nt+nf)), 6) d_adj,
       round(sum(nt*nf::numeric/(nt+nf)*mt) / sum(nt*nf::numeric/(nt+nf)), 6) nivel_true
FROM g WHERE nt > 0 AND nf > 0 GROUP BY 1 ORDER BY 1;
COMMIT;
