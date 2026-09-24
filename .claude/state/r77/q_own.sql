SET statement_timeout='120s';
COPY (
SELECT p.id::text AS position_id, p.mint, p.entry::text AS entry_json, p.exit::text AS exit_json
FROM meme_live_positions p WHERE p.status='closed' ORDER BY p.entry_at
) TO STDOUT WITH (FORMAT csv, HEADER);
