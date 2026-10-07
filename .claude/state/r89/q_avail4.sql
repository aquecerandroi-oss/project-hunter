SET statement_timeout='300s';
BEGIN READ ONLY;
-- 7. sonda de recusadas: Mayhem (na recusa e no token) × estrato × nº de outras recusas; status sem desfecho
WITH pb AS (
  SELECT b.id, b.mint, b.status, b.outcome_quality oq, b.leg, p.decided_at, p.reasons->0 blk, t.mayhem_enabled me
  FROM meme_paper_bets b JOIN meme_proposals p ON p.id=b.proposal_id LEFT JOIN meme_tokens t ON t.mint=b.mint
  WHERE b.rule_set_id='01994d00-6c1a-7000-8000-00000000001c'
)
SELECT (blk->'refusals') ? 'mayhem_curve' may_ref, (blk->'refusals') ? 'mayhem_unknown' may_unk, coalesce(me::text,'null') tok,
       blk->>'stratum' st, blk->>'inclusion_probability' p, jsonb_array_length(blk->'refusals') nref,
       count(*) n, count(DISTINCT mint) mints, count(*) FILTER (WHERE status='closed') closed,
       count(*) FILTER (WHERE status='closed' AND coalesce(oq,'')<>'indeterminate') resolved,
       count(*) FILTER (WHERE status='unfilled') unfilled, count(*) FILTER (WHERE status='open') open_,
       count(DISTINCT date_trunc('day',decided_at)) days, min(decided_at) a, max(decided_at) z
FROM pb GROUP BY 1,2,3,4,5,6 ORDER BY 1 DESC,4,6;
COMMIT;
