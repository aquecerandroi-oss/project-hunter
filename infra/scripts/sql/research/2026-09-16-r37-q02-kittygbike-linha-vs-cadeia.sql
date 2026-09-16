-- R37 (T4.40) — O caso KITTYGBIKE: a linha de 15 s (37,7 %) contra as fotos da curva.
-- Janela: 16/09 20:30–20:45 UTC (17:30–17:45 BRT).
\echo == linhas de 15 s ==
SELECT f.as_of, f.snapshot_observed_at, f.snapshot_source, f.snapshots_120s,
       f.curve_progress_pct, f.mcap_sol, f.progress_reason, f.window_reason
FROM meme_features_15s f
JOIN meme_tokens t ON t.mint = f.mint
WHERE t.symbol = 'KITTYGBIKE'
  AND f.as_of >= timestamptz '2026-09-16 20:34:00+00'
  AND f.as_of <  timestamptz '2026-09-16 20:38:00+00'
ORDER BY f.as_of;
\echo == fotos da curva ==
SELECT s.observed_at, s.received_at, s.source, s.real_sol_reserves, s.real_token_reserves,
       s.mcap_sol, t.initial_real_token_reserves,
       round((1 - s.real_token_reserves / nullif(t.initial_real_token_reserves,0))::numeric, 6) AS prog_calc
FROM meme_curve_snapshots s
JOIN meme_tokens t ON t.mint = s.mint
WHERE t.symbol = 'KITTYGBIKE'
  AND s.observed_at >= timestamptz '2026-09-16 20:33:00+00'
  AND s.observed_at <  timestamptz '2026-09-16 20:38:00+00'
ORDER BY s.observed_at;
