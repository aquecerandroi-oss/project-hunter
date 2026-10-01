-- EXP-M26 F (funil de viabilidade, sem desfecho) — 1/3: superconjunto das linhas que a porta pura
-- de grafico_ctrl_v1/1 pode deixar passar. O filtro SQL é FROUXO (idade 899–7201 s, progresso
-- 4–91 %, volume >= 6,9 SOL); a porta exata é a do código de R1 (evaluate_entry), em f_funil.py.
-- completed_at/migrated_at: os CONHECIDOS no computed_at da linha (histórico 0067, ordem do id),
-- nunca a linha corrente quando há histórico; Mayhem: o estado corrente (como o laço lê).
-- Somente leitura.
COPY (
SELECT f.mint, f.end_time, f.computed_at, t.created_at,
       f.curve_progress_pct, f.progress_reason, f.mcap_sol, f.creator_net_seller,
       f.curve_volume_1m_sol, f.higher_lows, f.breakout_15m, f.distance_to_support_pct,
       f.line_reason, f.line_points, f.mcap_slope_15m,
       t.mayhem_enabled, t.mayhem_state,
       (s.virtual_sol_reserves IS NOT NULL AND s.virtual_token_reserves > 0) AS snapshot_ok,
       st.completed_at_k, st.migrated_at_k, st.via
FROM meme_features_1m f
JOIN meme_tokens t ON t.mint = f.mint
LEFT JOIN meme_curve_snapshots s ON s.mint = f.mint
  AND s.observed_at = f.snapshot_observed_at AND s.source = f.snapshot_source
LEFT JOIN LATERAL (
  SELECT
    COALESCE(
      (SELECT h.new_value FROM meme_token_state_history h WHERE h.mint = f.mint
         AND h.column_name = 'completed_at' AND h.recorded_at <= f.computed_at ORDER BY h.id DESC LIMIT 1),
      (SELECT h.old_value FROM meme_token_state_history h WHERE h.mint = f.mint
         AND h.column_name = 'completed_at' AND h.recorded_at > f.computed_at ORDER BY h.id LIMIT 1),
      CASE WHEN NOT EXISTS (SELECT 1 FROM meme_token_state_history h WHERE h.mint = f.mint
                              AND h.column_name = 'completed_at') THEN t.completed_at END
    ) AS completed_at_k,
    COALESCE(
      (SELECT h.new_value FROM meme_token_state_history h WHERE h.mint = f.mint
         AND h.column_name = 'migrated_at' AND h.recorded_at <= f.computed_at ORDER BY h.id DESC LIMIT 1),
      (SELECT h.old_value FROM meme_token_state_history h WHERE h.mint = f.mint
         AND h.column_name = 'migrated_at' AND h.recorded_at > f.computed_at ORDER BY h.id LIMIT 1),
      CASE WHEN NOT EXISTS (SELECT 1 FROM meme_token_state_history h WHERE h.mint = f.mint
                              AND h.column_name = 'migrated_at') THEN t.migrated_at END
    ) AS migrated_at_k,
    CASE WHEN EXISTS (SELECT 1 FROM meme_token_state_history h WHERE h.mint = f.mint) THEN 'history'
         WHEN t.created_at >= '2026-09-28 04:24:42Z' THEN 'sem_mudanca'
         ELSE 'anterior_ao_historico' END AS via
) st ON true
WHERE f.features_version = 'meme_features_v3'
  AND f.end_time >= '2026-09-27 06:00Z' AND f.end_time < '2026-10-01 00:00Z'
  AND t.created_at IS NOT NULL
  AND f.end_time - t.created_at BETWEEN interval '899 s' AND interval '7201 s'
  AND f.curve_progress_pct BETWEEN 0.04 AND 0.91
  AND f.curve_volume_1m_sol >= 6.9
ORDER BY f.end_time, f.mint
) TO STDOUT WITH (FORMAT csv, HEADER true);
