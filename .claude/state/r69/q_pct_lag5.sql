SET statement_timeout='900s';
COPY (
WITH d AS (
  SELECT DISTINCT ON (b.mint)
         b.id AS bet_id, b.mint, pr.proposed_at AS t, b.entry_at, b.pnl_sol,
         (b.params->>'size_sol')::numeric AS size_sol,
         rs.name||'/'||rs.version AS arm, b.high_water_x,
         b.exit_intent->>'reason' AS exit_reason
  FROM meme_paper_bets b JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
  JOIN meme_proposals pr ON pr.id = b.proposal_id
  WHERE b.entry_at >= '2026-09-12' AND b.status='closed'
    AND b.outcome_quality='measured' AND rs.name='flow_v2'
  ORDER BY b.mint, pr.proposed_at
),
subj AS (
  SELECT d.*, f.as_of AS subj_as_of, f.age_s, f.curve_progress_pct, f.progress_delta_60s,
         f.mcap_sol, f.mcap_delta_60s, f.buys_60s, f.sells_60s,
         (f.sells_60s::numeric / NULLIF(f.buys_60s,0)) AS sell_buy,
         f.unique_buyers_60s, f.net_sol_flow_60s, f.curve_volume_60s_sol,
         f.snipers, f.dev_share,
         ('x'||substr(md5(d.mint||'seed42'),1,8))::bit(32)::bigint AS rnd1,
         ('x'||substr(md5(d.mint||'seed77'),1,8))::bit(32)::bigint AS rnd2
  FROM d CROSS JOIN LATERAL (
    SELECT g.* FROM meme_features_15s g
    WHERE g.mint = d.mint AND g.as_of <= d.t - interval '5 seconds' AND g.computed_at <= d.t - interval '5 seconds'
      AND (g.tape_as_of IS NULL OR g.tape_as_of <= g.as_of)
      AND g.as_of > d.t - interval '180 seconds'
    ORDER BY g.as_of DESC LIMIT 1
  ) f
),
coh AS (
  SELECT s.bet_id, c.mint AS cmint, c.age_s AS c_age, c.curve_progress_pct AS c_prog,
         c.progress_delta_60s AS c_dprog, c.mcap_sol AS c_mcap, c.mcap_delta_60s AS c_dmcap,
         c.buys_60s AS c_buys, c.sells_60s AS c_sells,
         (c.sells_60s::numeric / NULLIF(c.buys_60s,0)) AS c_sb,
         c.unique_buyers_60s AS c_ub, c.net_sol_flow_60s AS c_flow,
         c.curve_volume_60s_sol AS c_vol, c.snipers AS c_snip, c.dev_share AS c_dev,
         ('x'||substr(md5(c.mint||'seed42'),1,8))::bit(32)::bigint AS c_rnd1,
         ('x'||substr(md5(c.mint||'seed77'),1,8))::bit(32)::bigint AS c_rnd2
  FROM subj s CROSS JOIN LATERAL (
    SELECT DISTINCT ON (g.mint) g.*
    FROM meme_features_15s g
    WHERE g.as_of <= s.t - interval '5 seconds' AND g.as_of > s.t - interval '125 seconds'
      AND g.computed_at <= s.t - interval '5 seconds' AND g.mint <> s.mint
      AND (g.tape_as_of IS NULL OR g.tape_as_of <= g.as_of)
    ORDER BY g.mint, g.as_of DESC
  ) c
),
p AS (
  SELECT s.bet_id, count(*) AS cohort_n,
    avg(CASE WHEN k.c_age < s.age_s THEN 1.0 WHEN k.c_age = s.age_s THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_age IS NOT NULL AND s.age_s IS NOT NULL) AS p_age,
    avg(CASE WHEN k.c_prog < s.curve_progress_pct THEN 1.0 WHEN k.c_prog = s.curve_progress_pct THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_prog IS NOT NULL AND s.curve_progress_pct IS NOT NULL) AS p_prog,
    avg(CASE WHEN k.c_dprog < s.progress_delta_60s THEN 1.0 WHEN k.c_dprog = s.progress_delta_60s THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_dprog IS NOT NULL AND s.progress_delta_60s IS NOT NULL) AS p_dprog,
    avg(CASE WHEN k.c_mcap < s.mcap_sol THEN 1.0 WHEN k.c_mcap = s.mcap_sol THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_mcap IS NOT NULL AND s.mcap_sol IS NOT NULL) AS p_mcap,
    avg(CASE WHEN k.c_dmcap < s.mcap_delta_60s THEN 1.0 WHEN k.c_dmcap = s.mcap_delta_60s THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_dmcap IS NOT NULL AND s.mcap_delta_60s IS NOT NULL) AS p_dmcap,
    avg(CASE WHEN k.c_buys < s.buys_60s THEN 1.0 WHEN k.c_buys = s.buys_60s THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_buys IS NOT NULL AND s.buys_60s IS NOT NULL) AS p_buys,
    avg(CASE WHEN k.c_sells < s.sells_60s THEN 1.0 WHEN k.c_sells = s.sells_60s THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_sells IS NOT NULL AND s.sells_60s IS NOT NULL) AS p_sells,
    avg(CASE WHEN k.c_sb < s.sell_buy THEN 1.0 WHEN k.c_sb = s.sell_buy THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_sb IS NOT NULL AND s.sell_buy IS NOT NULL) AS p_sb,
    avg(CASE WHEN k.c_ub < s.unique_buyers_60s THEN 1.0 WHEN k.c_ub = s.unique_buyers_60s THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_ub IS NOT NULL AND s.unique_buyers_60s IS NOT NULL) AS p_ub,
    avg(CASE WHEN k.c_flow < s.net_sol_flow_60s THEN 1.0 WHEN k.c_flow = s.net_sol_flow_60s THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_flow IS NOT NULL AND s.net_sol_flow_60s IS NOT NULL) AS p_flow,
    avg(CASE WHEN k.c_vol < s.curve_volume_60s_sol THEN 1.0 WHEN k.c_vol = s.curve_volume_60s_sol THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_vol IS NOT NULL AND s.curve_volume_60s_sol IS NOT NULL) AS p_vol,
    avg(CASE WHEN k.c_snip < s.snipers THEN 1.0 WHEN k.c_snip = s.snipers THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_snip IS NOT NULL AND s.snipers IS NOT NULL) AS p_snip,
    avg(CASE WHEN k.c_dev < s.dev_share THEN 1.0 WHEN k.c_dev = s.dev_share THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_dev IS NOT NULL AND s.dev_share IS NOT NULL) AS p_dev,
    avg(CASE WHEN k.c_rnd1 < s.rnd1 THEN 1.0 WHEN k.c_rnd1 = s.rnd1 THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_rnd1 IS NOT NULL AND s.rnd1 IS NOT NULL) AS p_rnd1,
    avg(CASE WHEN k.c_rnd2 < s.rnd2 THEN 1.0 WHEN k.c_rnd2 = s.rnd2 THEN 0.5 ELSE 0.0 END) FILTER (WHERE k.c_rnd2 IS NOT NULL AND s.rnd2 IS NOT NULL) AS p_rnd2,
    count(*) FILTER (WHERE k.c_flow > 0) AS coh_pos_flow,
    count(*) FILTER (WHERE k.c_flow IS NOT NULL AND s.net_sol_flow_60s IS NOT NULL) AS coh_flow_n,
    percentile_disc(0.5) WITHIN GROUP (ORDER BY k.c_prog) FILTER (WHERE k.c_age BETWEEN 60 AND 300) AS coh_med_prog_60_300,
    count(*) FILTER (WHERE k.c_age BETWEEN 60 AND 300) AS coh_young_n,
    percentile_disc(0.5) WITHIN GROUP (ORDER BY k.c_buys) AS coh_med_buys
  FROM subj s JOIN coh k ON k.bet_id = s.bet_id
  GROUP BY s.bet_id
)
SELECT s.bet_id, s.mint, s.t, s.entry_at, s.arm, s.pnl_sol, s.size_sol, s.high_water_x, s.exit_reason,
       s.subj_as_of, s.age_s, s.curve_progress_pct, s.progress_delta_60s, s.mcap_sol,
       s.mcap_delta_60s, s.buys_60s, s.sells_60s, s.sell_buy, s.unique_buyers_60s,
       s.net_sol_flow_60s, s.curve_volume_60s_sol, s.snipers, s.dev_share,
       p.cohort_n, p.p_age, p.p_prog, p.p_dprog, p.p_mcap, p.p_dmcap, p.p_buys, p.p_sells,
       p.p_sb, p.p_ub, p.p_flow, p.p_vol, p.p_snip, p.p_dev, p.p_rnd1, p.p_rnd2,
       p.coh_pos_flow, p.coh_flow_n, p.coh_med_prog_60_300, p.coh_young_n, p.coh_med_buys
FROM subj s JOIN p ON p.bet_id = s.bet_id
ORDER BY s.t
) TO STDOUT WITH CSV HEADER;
