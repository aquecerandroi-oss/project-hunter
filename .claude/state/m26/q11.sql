WITH f AS (
  SELECT f.*, extract(epoch FROM f.end_time - t.created_at) AS age_s, t.mayhem_enabled, t.mayhem_state
  FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.end_time >= '2026-09-12 15:04+00' AND f.end_time < '2026-09-20 01:24+00' AND f.features_version='meme_features_v3'
)
SELECT mint, end_time, age_s, curve_progress_pct, creator_net_seller, curve_volume_1m_sol, mayhem_enabled, mayhem_state, distance_to_support_pct
FROM f WHERE age_s BETWEEN 300 AND 600 AND curve_progress_pct BETWEEN 0.02 AND 0.5 AND higher_lows AND breakout_15m
  AND distance_to_support_pct BETWEEN 0 AND 0.25 AND creator_net_seller = false AND curve_volume_1m_sol >= 5;
SELECT g.as_of, g.refusal, g.value, g."limit" FROM meme_gate_refusals_by_mint g JOIN meme_rule_sets r ON r.id=g.rule_set_id
WHERE r.name='trendline_v0' LIMIT 5;
SELECT count(*) FROM meme_gate_refusals_by_mint g JOIN meme_rule_sets r ON r.id=g.rule_set_id WHERE r.name='trendline_v0';
SELECT min(as_of) FROM meme_gate_refusals_by_mint;
