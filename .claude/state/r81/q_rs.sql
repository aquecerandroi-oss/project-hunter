\pset format unaligned
SELECT name||'/'||version, kind, status, params::text FROM meme_rule_sets WHERE name IN ('flow_v2','operator','recuo_v1','recuo_ctrl_v1') ORDER BY 1;
