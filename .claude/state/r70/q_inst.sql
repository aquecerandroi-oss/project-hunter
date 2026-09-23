SET statement_timeout='600s';
COPY (
WITH d AS (
  SELECT DISTINCT ON (b.mint) b.mint, pr.proposed_at AS t
  FROM meme_paper_bets b JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
  JOIN meme_proposals pr ON pr.id = b.proposal_id
  WHERE b.entry_at >= '2026-09-12' AND b.status='closed'
    AND b.outcome_quality='measured' AND rs.name='flow_v2'
  ORDER BY b.mint, pr.proposed_at
)
SELECT d.mint, d.t, f.as_of, f.computed_at, f.tape_as_of
FROM d CROSS JOIN LATERAL (
  SELECT g.as_of, g.computed_at, g.tape_as_of FROM meme_features_15s g
  WHERE g.mint = d.mint AND g.as_of <= d.t AND g.computed_at <= d.t
    AND (g.tape_as_of IS NULL OR g.tape_as_of <= g.as_of)
    AND g.as_of > d.t - interval '180 seconds'
  ORDER BY g.as_of DESC LIMIT 1
) f
) TO STDOUT WITH (FORMAT csv, HEADER);
