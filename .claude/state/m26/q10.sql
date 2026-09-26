SELECT percentile_disc(array[0.5,0.9,0.99]) within group (order by extract(epoch from computed_at - end_time)) AS fold_delay_s, count(*)
FROM meme_features_1m WHERE end_time > now() - interval '6 hours' AND features_version='meme_features_v3';
SELECT r.name||'/'||r.version rs, count(*) FILTER (WHERE b.status='open') open_now
FROM meme_rule_sets r LEFT JOIN meme_paper_bets b ON b.rule_set_id=r.id WHERE r.status='active' GROUP BY 1 ORDER BY 1;
