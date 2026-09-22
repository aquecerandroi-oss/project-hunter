SET statement_timeout='60s';
\echo == reasons ==
SELECT jsonb_pretty(pr.reasons) FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id WHERE p.status='closed' ORDER BY p.entry_at DESC LIMIT 1;
\echo == quote ==
SELECT jsonb_pretty(pr.quote) FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id WHERE p.status='closed' ORDER BY p.entry_at DESC LIMIT 1;
\echo == tables ==
SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'meme%' ORDER BY 1;
