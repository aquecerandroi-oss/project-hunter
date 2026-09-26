SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_tokens' ORDER BY ordinal_position;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_risk_snapshots' ORDER BY ordinal_position;
SELECT min(created_at), max(created_at), count(*) FROM meme_tokens;
SELECT count(*) FILTER (WHERE twitter IS NOT NULL) tw, count(*) FILTER (WHERE social_observed_at IS NOT NULL) soc_obs, count(*) FILTER (WHERE uri IS NOT NULL) uri, count(*) FILTER (WHERE twitter_reuse_count IS NOT NULL) reuse, count(*) FROM meme_tokens WHERE created_at >= '2026-09-23';
