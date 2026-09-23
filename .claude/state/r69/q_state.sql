SET statement_timeout='1800s';
COPY (
WITH b AS (
  SELECT generate_series(timestamptz '2026-09-12 12:00:00+00',
                         timestamptz '2026-09-23 15:00:00+00',
                         interval '5 minutes') AS t0
),
coh AS (
  SELECT b.t0, c.mint, c.age_s, c.curve_progress_pct, c.net_sol_flow_60s, c.buys_60s, c.mcap_sol
  FROM b CROSS JOIN LATERAL (
    SELECT DISTINCT ON (g.mint) g.*
    FROM meme_features_15s g
    WHERE g.as_of <= b.t0 AND g.as_of > b.t0 - interval '120 seconds'
      AND g.computed_at <= b.t0
      AND (g.tape_as_of IS NULL OR g.tape_as_of <= g.as_of)
    ORDER BY g.mint, g.as_of DESC
  ) c
),
st AS (
  SELECT t0, count(*) AS live_n,
         avg(CASE WHEN net_sol_flow_60s > 0 THEN 1.0 ELSE 0.0 END)
           FILTER (WHERE net_sol_flow_60s IS NOT NULL) AS frac_pos_flow,
         count(*) FILTER (WHERE net_sol_flow_60s IS NOT NULL) AS flow_n,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY curve_progress_pct)
           FILTER (WHERE age_s BETWEEN 60 AND 300) AS med_prog_60_300,
         count(*) FILTER (WHERE age_s BETWEEN 60 AND 300) AS young_n,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY buys_60s) AS med_buys,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY age_s) AS med_age
  FROM coh GROUP BY t0
),
births AS (
  SELECT b.t0, count(*) AS n FROM b JOIN meme_tokens tk
    ON tk.first_seen_at >= b.t0 - interval '5 minutes' AND tk.first_seen_at < b.t0
  GROUP BY b.t0
),
grads AS (
  SELECT b.t0, count(*) AS n FROM b JOIN meme_tokens tk
    ON tk.graduated_board_seen_at >= b.t0 - interval '1 hour' AND tk.graduated_board_seen_at < b.t0
  GROUP BY b.t0
)
SELECT b.t0, coalesce(st.live_n,0) AS live_n, st.frac_pos_flow, coalesce(st.flow_n,0) AS flow_n,
       st.med_prog_60_300, coalesce(st.young_n,0) AS young_n, st.med_buys, st.med_age,
       coalesce(births.n,0)/5.0 AS births_min, coalesce(grads.n,0) AS grads_h
FROM b LEFT JOIN st ON st.t0=b.t0 LEFT JOIN births ON births.t0=b.t0 LEFT JOIN grads ON grads.t0=b.t0
ORDER BY b.t0
) TO STDOUT WITH CSV HEADER;
