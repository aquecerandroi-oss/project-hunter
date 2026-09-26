SET statement_timeout='300s';
SELECT k, count(*) FROM (SELECT jsonb_object_keys(raw) k FROM meme_risk_snapshots WHERE observed_at > now() - interval '2 hours' LIMIT 20000) s GROUP BY k ORDER BY 2 DESC;
SELECT raw FROM meme_risk_snapshots WHERE observed_at > now() - interval '1 hour' AND raw::text ILIKE '%twitter%' LIMIT 2;
SELECT min(observed_at), count(*) FROM meme_risk_snapshots;
