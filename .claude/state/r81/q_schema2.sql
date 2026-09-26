SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_tokens' ORDER BY ordinal_position;
SELECT now();
SELECT count(*) FILTER (WHERE r->>'feature'='line') line_blocks, count(DISTINCT pr.id) props
FROM meme_proposals pr, jsonb_array_elements(pr.reasons) r WHERE pr.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%';
SELECT DISTINCT r->>'feature' f FROM meme_proposals pr, jsonb_array_elements(pr.reasons) r WHERE pr.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%' AND pr.decided_at > now()-interval '2 days';
SELECT min(end_time), max(end_time), count(*) FROM meme_features_1m WHERE end_time > now()-interval '30 days';
