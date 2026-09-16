-- KB-0109 Q01 — uma linha por moeda: top10_share na barra de ENTRADA, bundle do
-- retrato de risco (quando existir), graduacao organica e R simulado.
-- Universo = porta atual da mesa (brief R19): primeira foto de 15 s com
--   age_s 30-300 s, curva viva, nao-Mayhem (mayhem_enabled false E mayhem_mode nulo),
--   curve_progress_pct 0,05-0,50 (fracao 0-1), fita presente (tape_reason NULL),
--   fluxo liquido 60 s > 0, dev_share <= 0,10 e snipers >= 21.
-- Entrada = a PRIMEIRA barra de 1 min depois dessa foto (ate :ew minutos) com
--   holders >= 20, unique_buyers >= 10 e sells_1m/buys_1m <= 0,6 (KB-0102 r8-q01).
--   top10_share e lido NESSA barra (o numero que o executor veria).
-- bundle_pre = ultimo meme_risk_snapshots.bundled_share com observed_at <= t_in
--   (sem look-ahead); bundle_1o = o primeiro retrato do mint no dia (descritivo,
--   pode chegar depois da entrada — R5 mediu mediana de +103 s).
-- Saida = metodologia KB-0099/r4-q05 nas barras de 1 min: alvo 3x, trailing 35 %
--   armado depois de 1,5x, piso -50 %, tempo :hz minutos, taxa 1,75 % por perna,
--   stop preenchido no mcap OBSERVADO da barra. R = (multiplo liquido - 1) / 0,5.
-- organica = KB-0104/KB-0106: completed_at nao nulo, > 60 s de vida e ao menos
--   uma foto de 15 s com curve_progress_pct < 0,9 antes da graduacao.
-- Uso: psql -v dia=2026-09-15 -v ew=5 -v hz=30 -At -f este-arquivo.sql
SET statement_timeout = 60000;

WITH foto AS (
  SELECT DISTINCT ON (f.mint)
         f.mint, f.as_of AS t0, f.snipers, f.curve_progress_pct, f.tape_reason,
         f.net_sol_flow_60s, f.dev_share,
         t.mayhem_enabled, t.mayhem_mode, t.completed_at, t.migrated_at, t.created_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
  ORDER BY f.mint, f.as_of
), universo AS (
  SELECT mint, t0, snipers, created_at, completed_at
  FROM foto
  WHERE (completed_at IS NULL OR completed_at > t0)
    AND (migrated_at IS NULL OR migrated_at > t0)
    AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled AND mayhem_mode IS NULL
    AND curve_progress_pct BETWEEN 0.05 AND 0.50
    AND tape_reason IS NULL
    AND net_sol_flow_60s > 0
    AND dev_share IS NOT NULL AND dev_share <= 0.10
    AND snipers IS NOT NULL AND snipers >= 21
), entrada AS (
  SELECT DISTINCT ON (u.mint) u.mint, u.t0, u.snipers, u.created_at, u.completed_at,
         b.end_time AS t_in, b.mcap_sol AS base, b.top10_share, b.holders
  FROM universo u
  JOIN meme_features_1m b ON b.mint = u.mint
   AND b.end_time > u.t0
   AND b.end_time <= u.t0 + make_interval(mins => (:'ew')::int)
  WHERE b.mcap_sol IS NOT NULL AND b.mcap_sol > 0
    AND b.holders >= 20
    AND b.unique_buyers >= 10
    AND b.buys_1m > 0 AND b.sells_1m::numeric / b.buys_1m <= 0.6
  ORDER BY u.mint, b.end_time
), barras AS (
  SELECT e.mint, e.base, s.end_time, s.mcap_sol,
         row_number() OVER (PARTITION BY e.mint ORDER BY s.end_time) AS i,
         max(s.mcap_sol) OVER (PARTITION BY e.mint ORDER BY s.end_time
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS pico_ate_anterior
  FROM entrada e
  JOIN meme_features_1m s ON s.mint = e.mint
   AND s.end_time > e.t_in AND s.end_time <= e.t_in + make_interval(mins => (:'hz')::int)
  WHERE s.mcap_sol IS NOT NULL
), gatilho AS (
  SELECT *,
    CASE WHEN COALESCE(pico_ate_anterior, base) >= 1.5 * base
         THEN greatest(0.65 * COALESCE(pico_ate_anterior, base), 0.5 * base)
         ELSE 0.5 * base END AS nivel_stop
  FROM barras
), saida AS (
  SELECT DISTINCT ON (mint) mint, i,
    CASE WHEN mcap_sol >= 3 * base THEN 3 * base ELSE mcap_sol END AS preco_saida,
    CASE WHEN mcap_sol >= 3 * base THEN 'alvo_3x' ELSE 'stop' END AS motivo
  FROM gatilho
  WHERE mcap_sol >= 3 * base OR mcap_sol <= nivel_stop
  ORDER BY mint, i
), fim AS (
  SELECT DISTINCT ON (mint) mint, mcap_sol AS preco_saida, 'tempo' AS motivo
  FROM gatilho ORDER BY mint, i DESC
)
SELECT :'dia' AS dia, e.mint, e.t_in, e.snipers, e.holders,
       e.top10_share,
       (SELECT r.bundled_share FROM meme_risk_snapshots r
         WHERE r.mint = e.mint AND r.observed_at <= e.t_in
         ORDER BY r.observed_at DESC LIMIT 1) AS bundle_pre,
       (SELECT r.bundled_share FROM meme_risk_snapshots r
         WHERE r.mint = e.mint ORDER BY r.observed_at LIMIT 1) AS bundle_1o,
       (e.completed_at IS NOT NULL
        AND e.completed_at - e.created_at > interval '60 seconds'
        AND EXISTS (SELECT 1 FROM meme_features_15s g
                     WHERE g.mint = e.mint AND g.curve_progress_pct < 0.9
                       AND g.as_of > e.created_at AND g.as_of < e.completed_at)) AS organica,
       COALESCE(s.motivo, f.motivo) AS motivo,
       round((((COALESCE(s.preco_saida, f.preco_saida) / e.base) * 0.9825 * 0.9825 - 1) / 0.5)::numeric, 6) AS r
FROM entrada e
LEFT JOIN saida s ON s.mint = e.mint
LEFT JOIN fim f ON f.mint = e.mint
WHERE COALESCE(s.preco_saida, f.preco_saida) IS NOT NULL;
