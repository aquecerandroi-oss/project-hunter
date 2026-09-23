SET statement_timeout='600s';
COPY (
WITH d AS (
  SELECT DISTINCT ON (b.mint) b.id AS bet_id, b.mint, pr.proposed_at AS t
  FROM meme_paper_bets b JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
  JOIN meme_proposals pr ON pr.id=b.proposal_id
  WHERE b.entry_at >= '2026-09-12' AND b.status='closed'
    AND b.outcome_quality='measured' AND rs.name='flow_v2'
  ORDER BY b.mint, pr.proposed_at
), s AS (SELECT * FROM d ORDER BY md5(bet_id::text) LIMIT 20)
SELECT s.bet_id, s.mint AS subject, s.t, g.mint, g.as_of, g.computed_at, g.tape_as_of, g.buys_60s, g.progress_delta_60s
FROM s JOIN meme_features_15s g
  ON g.as_of > s.t - interval '150 seconds' AND g.as_of < s.t + interval '60 seconds'
ORDER BY s.bet_id, g.mint, g.as_of
) TO STDOUT WITH CSV HEADER;
