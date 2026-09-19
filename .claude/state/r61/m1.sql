SET statement_timeout='120s';
COPY (
SELECT DISTINCT ON (x.mint) x.mint, x.event_id, x.match_kind, x.matched_at, e.observed_at AS event_at, e.kind, e.confidence, e.symbol_hint, t.created_at, t.completed_at, t.symbol,
  (SELECT max(kol_count) FROM meme_board_observations_2026_09 o WHERE o.mint=x.mint AND o.observed_at > now() - interval '72 hours') AS max_kol
FROM meme_event_matches x JOIN meme_tokens t ON t.mint=x.mint JOIN meme_events e ON e.id=x.event_id
WHERE x.matched_at > now() - interval '72 hours' ORDER BY x.mint, x.matched_at
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
