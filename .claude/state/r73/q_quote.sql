SET statement_timeout='60s';
SELECT 'quote', jsonb_pretty(quote) FROM meme_proposals WHERE quote IS NOT NULL ORDER BY decided_at DESC NULLS LAST LIMIT 1;
SELECT 'paper_entry', jsonb_pretty(entry) FROM meme_paper_bets WHERE entry IS NOT NULL ORDER BY entry_at DESC LIMIT 1;
SELECT 'rule_sets', name||'/'||version||' kind='||kind||' status='||status||' params='||params::text FROM meme_rule_sets ORDER BY created_at;
