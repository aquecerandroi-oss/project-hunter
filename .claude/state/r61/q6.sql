SET statement_timeout='60s';
SELECT e.id, e.observed_at, e.source, e.kind, e.confidence, e.symbol_hint, e.handle_hint, left(e.title,60), (SELECT count(*) FROM meme_event_matches x WHERE x.event_id=e.id) AS n_match, (SELECT count(*) FILTER (WHERE match_kind='avoid') FROM meme_event_matches x WHERE x.event_id=e.id) AS n_avoid
FROM meme_events e WHERE e.observed_at > now() - interval '96 hours' ORDER BY e.observed_at;
SELECT match_kind, count(*), count(DISTINCT mint) FROM meme_event_matches WHERE matched_at > now() - interval '72 hours' GROUP BY 1;
-- latency matched_at - created_at, and event observed_at - created_at
SELECT match_kind,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM x.matched_at - t.created_at)) AS med_match_lag_s,
  percentile_cont(0.1) WITHIN GROUP (ORDER BY extract(epoch FROM x.matched_at - t.created_at)) AS p10_match_lag_s,
  percentile_cont(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM x.matched_at - t.created_at)) AS p90_match_lag_s,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM t.created_at - e.observed_at)) AS med_created_after_event_s,
  count(*) FILTER (WHERE t.created_at < e.observed_at) AS coin_before_event
FROM meme_event_matches x JOIN meme_tokens t ON t.mint=x.mint JOIN meme_events e ON e.id=x.event_id WHERE x.matched_at > now() - interval '72 hours' GROUP BY 1;
