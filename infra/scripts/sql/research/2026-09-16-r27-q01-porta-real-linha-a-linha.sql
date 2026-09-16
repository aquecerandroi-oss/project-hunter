-- R27 16/09 — a porta REAL (codigo: proposals.evaluate_gate + rules.evaluate_entry +
-- rules_criteria + pedigree) aplicada linha a linha da serie de 15 s as tres moedas que
-- passaram a replica do R23 e NAO viraram proposta: Kintsugi, Grammuh, HANNAH.
-- Ordem dos criterios = ordem do codigo. Unidades: curve_progress_pct e FRACAO;
-- a porta compara progresso em PERCENTO (fracao*100) contra min 5 / max 50.
-- operator/5: min_age 30, max_age 300, prog 5-50, participacao <= 1 % com 0,05 SOL,
-- max_dev_share 0,10, min_snipers 21, max_snipers 1000, require_positive_flow,
-- min_unique_buyers 10, max_sells_to_buys 0,6, min_holders 20,
-- require_creator_not_net_seller + creator_unknown_allowed_if_dev_measured,
-- exclude_mayhem (default), pedigree_exclusions + pedigree_repeat_dumper.
SET statement_timeout = 240000;
\set k 'BiCp7NhzPJBMFeSaqzUuw6mW93n3uUj6ErreumShpump'
\set g 'FLz2Hvyi6mKracWNxo1tRsA9P1Ge7izjNd6ZKXco686M'
\set h 'DgFP1AyHaBEpxqw2dE8SsADDw7oLxMaFd26mC6Y5FngP'

SELECT to_char(f.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
  t.symbol, f.age_s,
  round(f.curve_progress_pct*100,2) AS prog_pct,
  f.holders, f.unique_buyers_60s AS compr, f.buys_60s, f.sells_60s,
  round(f.net_sol_flow_60s,2) AS fluxo, round(f.curve_volume_60s_sol,2) AS vol60,
  f.snipers, f.dev_share, f.creator_net_seller AS creator_ns, f.tape_reason,
  -- refusals na ordem do codigo
  array_remove(ARRAY[
    CASE WHEN t.completed_at IS NOT NULL AND t.completed_at <= f.as_of THEN 'curve_complete' END,
    CASE WHEN t.migrated_at IS NOT NULL AND t.migrated_at <= f.as_of THEN 'already_migrated' END,
    CASE WHEN COALESCE(t.mayhem_enabled, s.mayhem_enabled) IS NULL
           AND COALESCE(t.mayhem_state,'') = '' THEN 'mayhem_unknown'
         WHEN COALESCE(t.mayhem_enabled, s.mayhem_enabled) THEN 'mayhem_curve' END,
    CASE WHEN t.created_at IS NULL OR t.created_at > f.as_of THEN 'age_unknown'
         WHEN extract(epoch FROM (f.as_of - t.created_at)) < 30 THEN 'age_below_min'
         WHEN extract(epoch FROM (f.as_of - t.created_at)) > 300 THEN 'age_above_max' END,
    CASE WHEN f.curve_progress_pct IS NULL THEN 'progress_unknown'
         WHEN f.curve_progress_pct*100 < 5 THEN 'progress_below_min'
         WHEN f.curve_progress_pct*100 > 50 THEN 'progress_above_max' END,
    CASE WHEN f.creator_net_seller IS NULL
           THEN CASE WHEN f.dev_share IS NOT NULL AND f.dev_share <= 0.10
                     THEN NULL ELSE 'creator_net_seller_unknown' END
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
         WHEN COALESCE(f.net_sol_flow_60s, f.mcap_delta_60s) <= 0 THEN 'flow_not_positive' END,
    CASE WHEN f.unique_buyers_60s IS NULL THEN 'buyers_unknown'
         WHEN f.unique_buyers_60s < 10 THEN 'buyers_below_min' END,
    CASE WHEN f.buys_60s IS NULL OR f.sells_60s IS NULL THEN 'sells_ratio_unknown'
         WHEN f.buys_60s = 0 THEN 'no_buys'
         WHEN f.sells_60s::numeric/f.buys_60s > 0.6 THEN 'sells_ratio_above_max' END,
    CASE WHEN f.holders IS NULL THEN 'holders_'||COALESCE(f.holders_reason,'unknown')
         WHEN f.holders < 20 THEN 'holders_below_min' END,
    CASE WHEN f.snapshot_observed_at IS NULL OR s.mint IS NULL THEN 'no_snapshot_for_quote' END
  ], NULL) AS recusas_da_porta_real
FROM meme_features_15s f
JOIN meme_tokens t ON t.mint = f.mint
LEFT JOIN meme_curve_snapshots s ON s.mint=f.mint AND s.observed_at=f.snapshot_observed_at
  AND s.source=f.snapshot_source
WHERE f.mint IN (:'k', :'g', :'h')
  AND f.features_version = 'meme_features_15s_v1'
ORDER BY t.symbol, f.as_of;
