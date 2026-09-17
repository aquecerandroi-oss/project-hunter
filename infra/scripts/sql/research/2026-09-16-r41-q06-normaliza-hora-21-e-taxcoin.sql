-- R41 16/09 21h37 BRT -- normaliza a hora 21 (parcial) e fecha o caso TAXCOIN:
-- (a) minutos decorridos da hora 21 e as taxas por minuto ja normalizadas;
-- (b) retrato de risco e fita da TAXCOIN na hora da compra (sem look-ahead).
SET statement_timeout = 200000;

SELECT to_char(now() AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS agora_brt,
  round(extract(epoch FROM (now() - timestamptz $$2026-09-16 21:00-03$$))/60.0,2) AS min_da_hora_21,
  (SELECT count(*) FROM meme_tokens WHERE created_at >= timestamptz $$2026-09-16 21:00-03$$) AS criadas_21,
  (SELECT count(DISTINCT f.mint) FROM meme_features_15s f
     JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
     WHERE f.as_of >= timestamptz $$2026-09-16 21:00-03$$ AND f.age_s BETWEEN 30 AND 300
       AND f.curve_progress_pct BETWEEN 0.02 AND 0.50 AND f.tape_reason IS NULL
       AND f.net_sol_flow_60s > 0) AS janela_21,
  (SELECT count(*) FROM meme_proposals WHERE proposed_at >= timestamptz $$2026-09-16 21:00-03$$
     AND mode = $$live$$) AS propostas_live_21,
  (SELECT count(*) FROM meme_tokens WHERE completed_at >= timestamptz $$2026-09-16 21:00-03$$) AS graduadas_21;

-- (b) TAXCOIN: retrato de risco e fita ate o instante da compra (21:31:28 BRT)
SELECT to_char(s.observed_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  round(s.bundled_share*100,2) AS bundle_pct, round(s.top10_share*100,2) AS top10_pct,
  round(s.dev_share*100,2) AS dev_pct
FROM meme_risk_snapshots s
WHERE s.mint = $$7s4dKmpvQxNy5CwDpsy9SKw3JVoFGRYNd6F8mr4GAxi8$$
ORDER BY s.observed_at;

SELECT count(DISTINCT trader) AS compradores_fita, count(*) AS trades,
  round(sum(sol_lamports)/1e9,3) AS sol_comprado,
  round(max(por_trader)/nullif(sum(sol_lamports)/1e9,0)*100,1) AS maior_comprador_pct
FROM meme_trades x
CROSS JOIN LATERAL (SELECT max(s) AS por_trader FROM (
  SELECT sum(sol_lamports)/1e9 AS s FROM meme_trades y
  WHERE y.mint = x.mint AND y.side = $$buy$$
    AND y.block_time <= timestamptz $$2026-09-16 21:31:28-03$$ GROUP BY y.trader) z) m
WHERE x.mint = $$7s4dKmpvQxNy5CwDpsy9SKw3JVoFGRYNd6F8mr4GAxi8$$ AND x.side = $$buy$$
  AND x.block_time <= timestamptz $$2026-09-16 21:31:28-03$$;

-- (c) features de 15 s da TAXCOIN em volta da compra
SELECT to_char(f.as_of AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  f.age_s, round(f.curve_progress_pct*100,1) AS prog, f.holders, f.unique_buyers_60s AS compr,
  f.buys_60s, f.sells_60s, round(f.net_sol_flow_60s,2) AS fluxo,
  round(f.curve_volume_60s_sol,1) AS vol60, f.snipers, round(f.dev_share*100,2) AS dev
FROM meme_features_15s f WHERE f.mint = $$7s4dKmpvQxNy5CwDpsy9SKw3JVoFGRYNd6F8mr4GAxi8$$
ORDER BY f.as_of;
