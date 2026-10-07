SET statement_timeout='600s';
BEGIN READ ONLY;
-- R89 réplica cega: D_adj, bruto, teto e ausentes calculados no servidor, sem o CSV nem o Python.
WITH base AS (
  SELECT p.mint, p.decided_at,
         (p.reasons->0->'refusals') ? 'mayhem_curve' AS may,
         (SELECT count(*) FROM jsonb_array_elements_text(p.reasons->0->'refusals') x
           WHERE x NOT LIKE 'mayhem\_%' AND x NOT LIKE 'progress\_%') AS n_clean,
         CASE WHEN b.status='closed' AND coalesce(b.outcome_quality,'')<>'indeterminate' AND b.pnl_sol IS NOT NULL
              THEN b.pnl_sol / (b.entry->>'sol_spent')::numeric END AS ret,
         (b.exit->>'real_sol_cap_applied')::boolean AS capped
  FROM meme_proposals p LEFT JOIN meme_paper_bets b ON b.proposal_id=p.id
  WHERE p.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' AND p.reasons->0->>'stratum'='B'
    AND p.decided_at >= '2026-09-23 00:00Z' AND p.decided_at < '2026-10-07 00:00Z'
), cuts AS (
  SELECT percentile_cont(1.0/3) WITHIN GROUP (ORDER BY n_clean) c1, percentile_cont(2.0/3) WITHIN GROUP (ORDER BY n_clean) c2 FROM base
), s AS (
  SELECT b.*, (b.decided_at AT TIME ZONE 'UTC')::date d, floor(extract(hour FROM b.decided_at AT TIME ZONE 'UTC')/6) blk,
         CASE WHEN n_clean <= c1 THEN 0 WHEN n_clean > c2 THEN 2 ELSE 1 END terc
  FROM base b, cuts
), cell AS (
  SELECT d, blk, terc, count(*) FILTER (WHERE may AND ret IS NOT NULL) nm, count(*) FILTER (WHERE NOT may AND ret IS NOT NULL) nn,
         avg(ret) FILTER (WHERE may) mm, avg(ret) FILTER (WHERE NOT may) mn FROM s GROUP BY 1,2,3
)
SELECT (SELECT c1 FROM cuts) c1, (SELECT c2 FROM cuts) c2,
       round(sum(nm*nn::numeric/(nm+nn)*(mn-mm)) / sum(nm*nn::numeric/(nm+nn)), 4) AS d_adj,
       count(*) strata_used
FROM cell WHERE nm>0 AND nn>0;
WITH base AS (
  SELECT (p.reasons->0->'refusals') ? 'mayhem_curve' AS may,
         CASE WHEN b.status='closed' AND coalesce(b.outcome_quality,'')<>'indeterminate' AND b.pnl_sol IS NOT NULL
              THEN b.pnl_sol / (b.entry->>'sol_spent')::numeric END AS ret,
         (b.exit->>'real_sol_cap_applied')::boolean AS capped
  FROM meme_proposals p LEFT JOIN meme_paper_bets b ON b.proposal_id=p.id
  WHERE p.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' AND p.reasons->0->>'stratum'='B'
    AND p.decided_at >= '2026-09-23 00:00Z' AND p.decided_at < '2026-10-07 00:00Z')
SELECT may, count(*) n, count(ret) resolved, round(avg(ret),4) mean_ret,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY ret))::numeric,4) med_ret,
       count(*) FILTER (WHERE capped AND ret IS NOT NULL) capped_exits
FROM base GROUP BY may ORDER BY may;
COMMIT;
