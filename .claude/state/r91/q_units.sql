-- R91 passo 3a — lista de unidades CEGA (sem pnl, exit, outcome_quality, high_water_x, status)
-- unidade = proposta mais antiga do par (conjunto, mint) que gerou aposta de papel single; nunca trocada
BEGIN READ ONLY;
SET LOCAL statement_timeout='900s';
COPY (
WITH f AS (
  SELECT p.id AS proposal_id, p.mint, p.proposed_at, p.features_end_time, rs.name||'/'||rs.version AS rs,
         COALESCE(p.reasons->0->>'series', '1m') AS series, x.e AS fl
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  JOIN LATERAL (SELECT e FROM jsonb_array_elements(p.reasons) e WHERE e->>'feature'='flow' LIMIT 1) x ON true
  WHERE jsonb_typeof(p.reasons)='array' AND rs.name IN ('operator','flow_v2','recuo_v1','recuo_ctrl_v1')
    AND p.proposed_at < '2026-10-07 00:00:00+00')
SELECT DISTINCT ON (f.rs, f.mint)
       f.rs, f.mint, f.proposal_id, f.proposed_at, f.features_end_time, f.series,
       b.id AS bet_id, b.entry_at, b.leg,
       f.fl->>'holders_rising' AS holders_rising, f.fl->>'holders_reason' AS holders_reason,
       f.fl->>'progress_rising' AS progress_rising,
       b.entry->'snapshot'->>'mayhem_enabled' AS snap_mayhem, t.mayhem_enabled::text AS tok_mayhem,
       m.holders_rising::text AS f15_holders_rising, m.progress_rising::text AS f15_progress_rising,
       (m.mint IS NOT NULL) AS f15_row
FROM f JOIN meme_paper_bets b ON b.proposal_id=f.proposal_id AND b.leg='single'
LEFT JOIN meme_tokens t ON t.mint=f.mint
LEFT JOIN meme_features_15s m ON m.mint=f.mint AND m.as_of=f.features_end_time AND f.series='meme_features_15s_v1'
ORDER BY f.rs, f.mint, f.proposed_at, b.entry_at, b.id
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
