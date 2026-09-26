SELECT name||'/'||version AS rs, status, kind, created_at, retired_at, params FROM meme_rule_sets WHERE name LIKE 'trendline%' OR name LIKE 'hype%';
\d meme_gate_refusals_by_mint
