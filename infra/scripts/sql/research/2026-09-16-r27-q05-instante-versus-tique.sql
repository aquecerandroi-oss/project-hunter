-- R27 q05 — alinhamento foto x tique: as recusas da porta REAL recalculadas por INSTANTE da
-- serie de 15 s (so os nomes do EntryGate; pedigree fica de fora) contra o contador gravado
-- em meme_lab_ticks por tique. Serve para descobrir qual instante cada tique julgou e se
-- alguma foto ficou sem julgamento (a via rapida so le as_of > last_fast_as_of e > now-45 s).
SET statement_timeout = 240000;
WITH r AS (
  SELECT f.as_of, f.mint,
    array_remove(ARRAY[
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
    ], NULL) AS recusas
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  LEFT JOIN meme_curve_snapshots s ON s.mint=f.mint AND s.observed_at=f.snapshot_observed_at
    AND s.source=f.snapshot_source
  WHERE f.as_of BETWEEN timestamptz '2026-09-16 19:19:10+00' AND timestamptz '2026-09-16 19:21:10+00'
    AND f.features_version='meme_features_15s_v1'
)
SELECT to_char(as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS instante_brt,
  count(*) AS fotos,
  count(*) FILTER (WHERE cardinality(recusas)=0) AS limpas_na_porta,
  sum(cardinality(recusas)) AS recusas_total,
  count(*) FILTER (WHERE 'progress_above_max' = ANY(recusas)) AS progress_above_max,
  count(*) FILTER (WHERE 'mayhem_unknown' = ANY(recusas)) AS mayhem_unknown,
  count(*) FILTER (WHERE 'creator_is_net_seller' = ANY(recusas)) AS creator_is_net_seller,
  count(*) FILTER (WHERE 'participation_above_cap' = ANY(recusas)) AS participation_above_cap,
  count(*) FILTER (WHERE 'snipers_above_max' = ANY(recusas)) AS snipers_above_max
FROM r GROUP BY as_of ORDER BY as_of;

-- o mesmo recorte no contador gravado (so os nomes acima)
SELECT to_char(ticked_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS tique_brt,
  COALESCE(o->>'progress_above_max','0') AS progress_above_max,
  COALESCE(o->>'mayhem_unknown','0') AS mayhem_unknown,
  COALESCE(o->>'creator_is_net_seller','0') AS creator_is_net_seller,
  COALESCE(o->>'participation_above_cap','0') AS participation_above_cap,
  COALESCE(o->>'snipers_above_max','0') AS snipers_above_max
FROM (SELECT ticked_at, (refusals::jsonb)->'operator' AS o FROM meme_lab_ticks
      WHERE ticked_at BETWEEN timestamptz '2026-09-16 19:19:20+00'
        AND timestamptz '2026-09-16 19:21:40+00') q ORDER BY ticked_at;
