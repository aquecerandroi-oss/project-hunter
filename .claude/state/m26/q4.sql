WITH b AS (
  SELECT o.board, o.mint, o.observed_at, o.age_s, o.progress_pct, o.graduated_at, o.market_cap_usd, o.volume_5m_sol,
         extract(epoch FROM o.observed_at - t.created_at)/60.0 AS age_min_tok
  FROM meme_board_observations o LEFT JOIN meme_tokens t ON t.mint = o.mint
  WHERE o.observed_at >= '2026-09-25 00:00+00' AND o.observed_at < '2026-09-26 00:00+00'
)
SELECT board,
  CASE WHEN age_min_tok IS NULL THEN 'z unknown' WHEN age_min_tok < 5 THEN 'a <5' WHEN age_min_tok < 15 THEN 'b 5-15' WHEN age_min_tok < 30 THEN 'c 15-30'
       WHEN age_min_tok < 60 THEN 'd 30-60' WHEN age_min_tok < 120 THEN 'e 60-120' WHEN age_min_tok < 240 THEN 'f 120-240' ELSE 'g >4h' END AS age,
  count(*) AS obs, count(DISTINCT mint) AS mints,
  round(avg((graduated_at IS NULL)::int),3) AS on_curve,
  percentile_disc(0.5) WITHIN GROUP (ORDER BY progress_pct) AS prog_p50,
  percentile_disc(0.5) WITHIN GROUP (ORDER BY volume_5m_sol) AS vol5m_p50
FROM b GROUP BY 1,2 ORDER BY 1,2;
SELECT count(*) FILTER (WHERE age_s IS NOT NULL) AS with_age_s, count(*) FROM meme_board_observations WHERE observed_at >= '2026-09-25' AND observed_at < '2026-09-26';
SELECT min(observed_at), max(observed_at) FROM meme_board_observations WHERE board='new';
