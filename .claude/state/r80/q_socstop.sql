SELECT max(social_observed_at) last_social, max(first_seen_at) FILTER (WHERE first_seen_source='pumpfun_rest') last_rest_first,
  (SELECT max(observed_at) FROM meme_curve_snapshots WHERE source='pumpfun_rest' AND observed_at > now()-interval '3 days') last_rest_snap,
  (SELECT max(observed_at) FROM meme_curve_snapshots WHERE observed_at > now()-interval '1 day') last_any_snap
FROM meme_tokens WHERE created_at > '2026-09-24';
SELECT date_trunc('hour', social_observed_at) h, count(*) FROM meme_tokens WHERE social_observed_at > '2026-09-25 12:00Z' GROUP BY 1 ORDER BY 1;
