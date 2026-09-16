-- R27 q06 — o vetor completo de recusas: replica do codigo sobre o instante 16:20:00 (117
-- fotos) contra o contador gravado no tique 16:20:03 (o tique que julgou esse instante,
-- alinhado em q05). Um nome que so aparece de um lado e a diferenca entre codigo e replica.
SET statement_timeout = 240000;
WITH r AS (
  SELECT f.mint, unnest(array_remove(ARRAY[
      CASE WHEN t.completed_at IS NOT NULL AND t.completed_at <= f.as_of THEN 'curve_complete' END,
      CASE WHEN t.migrated_at IS NOT NULL AND t.migrated_at <= f.as_of THEN 'already_migrated' END,
      CASE WHEN COALESCE(t.mayhem_enabled, s.mayhem_enabled) IS NULL
             AND COALESCE(t.mayhem_state,'')='' THEN 'mayhem_unknown'
           WHEN COALESCE(t.mayhem_enabled, s.mayhem_enabled) THEN 'mayhem_curve' END,
      CASE WHEN t.created_at IS NULL OR t.created_at > f.as_of THEN 'age_unknown'
           WHEN extract(epoch FROM (f.as_of-t.created_at)) < 30 THEN 'age_below_min'
           WHEN extract(epoch FROM (f.as_of-t.created_at)) > 300 THEN 'age_above_max' END,
      CASE WHEN f.curve_progress_pct IS NULL THEN 'progress_unknown'
           WHEN f.curve_progress_pct*100 < 5 THEN 'progress_below_min'
           WHEN f.curve_progress_pct*100 > 50 THEN 'progress_above_max' END,
      CASE WHEN f.creator_net_seller IS NULL
             THEN CASE WHEN f.dev_share IS NOT NULL AND f.dev_share <= 0.10 THEN NULL
                       ELSE 'creator_net_seller_unknown' END
           WHEN f.creator_net_seller THEN 'creator_is_net_seller' END,
      CASE WHEN f.curve_volume_60s_sol IS NULL THEN 'curve_volume_1m_unknown'
           WHEN f.curve_volume_60s_sol <= 0 THEN 'curve_volume_1m_zero'
           WHEN 100*0.05/f.curve_volume_60s_sol > 1 THEN 'participation_above_cap' END,
      CASE WHEN f.dev_share IS NULL THEN 'dev_share_unknown'
           WHEN f.dev_share > 0.10 THEN 'dev_share_above_max' END,
      CASE WHEN f.snipers IS NULL THEN 'snipers_unknown'
           WHEN f.snipers < 21 THEN 'snipers_below_min'
           WHEN f.snipers > 1000 THEN 'snipers_above_max' END,
      CASE WHEN f.net_sol_flow_60s IS NULL AND f.mcap_delta_60s IS NULL
             THEN 'flow_'||COALESCE(f.tape_reason,'unknown')
           WHEN COALESCE(f.net_sol_flow_60s,f.mcap_delta_60s) <= 0 THEN 'flow_not_positive' END,
      CASE WHEN f.unique_buyers_60s IS NULL THEN 'buyers_unknown'
           WHEN f.unique_buyers_60s < 10 THEN 'buyers_below_min' END,
      CASE WHEN f.buys_60s IS NULL OR f.sells_60s IS NULL THEN 'sells_ratio_unknown'
           WHEN f.buys_60s = 0 THEN 'no_buys'
           WHEN f.sells_60s::numeric/f.buys_60s > 0.6 THEN 'sells_ratio_above_max' END,
      CASE WHEN f.holders IS NULL THEN 'holders_'||COALESCE(f.holders_reason,'unknown')
           WHEN f.holders < 20 THEN 'holders_below_min' END
    ], NULL)) AS recusa
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  LEFT JOIN meme_curve_snapshots s ON s.mint=f.mint AND s.observed_at=f.snapshot_observed_at
    AND s.source=f.snapshot_source
  WHERE f.as_of BETWEEN timestamptz '2026-09-16 19:19:55+00' AND timestamptz '2026-09-16 19:20:05+00'
), rep AS (SELECT recusa, count(*) AS n FROM r GROUP BY recusa),
tick AS (SELECT e.k AS recusa, e.v::int AS n FROM meme_lab_ticks t,
   jsonb_each_text((t.refusals::jsonb)->'operator') AS e(k,v)
   WHERE t.ticked_at = (SELECT ticked_at FROM meme_lab_ticks
     WHERE ticked_at >= timestamptz '2026-09-16 19:20:00+00' ORDER BY ticked_at LIMIT 1))
SELECT COALESCE(rep.recusa, tick.recusa) AS recusa,
  COALESCE(rep.n,0) AS replica_do_codigo, COALESCE(tick.n,0) AS gravado_no_tique,
  COALESCE(tick.n,0)-COALESCE(rep.n,0) AS diff
FROM rep FULL JOIN tick ON tick.recusa=rep.recusa ORDER BY abs(COALESCE(tick.n,0)-COALESCE(rep.n,0)) DESC, 1;
