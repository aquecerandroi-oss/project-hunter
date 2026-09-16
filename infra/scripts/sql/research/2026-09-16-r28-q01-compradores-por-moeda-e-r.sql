-- KB-0114 Q01 — uma linha por moeda da COORTE DE 344 (a porta atual sem participacao),
-- com unique_buyers/snipers/holders da barra de ENTRADA e o R simulado.
-- Reuso LITERAL do r24-q01 (KB-0112) / r19-q01 (KB-0109): mesma foto, mesmo universo,
-- mesma entrada (holders >= 20, unique_buyers >= 10, sells/buys <= 0,6), mesma saida
-- (KB-0099/r4-q05: alvo 3x, trailing 35 % armado depois de 1,5x, piso -50 %, 30 min,
-- 1,75 % por perna, R = (multiplo liquido - 1)/0,5). A UNICA coisa nova e o recorte
-- por piso de compradores, aplicado DEPOIS, sobre esta mesma coorte.
-- Uso: psql -v dia=2026-09-15 -v ew=5 -v hz=30 -At -f este-arquivo.sql
--   (por -c: troque :'dia' por $$AAAA-MM-DD$$ e :ew/:hz pelos numeros)
SET statement_timeout = 60000;

WITH foto AS (
  SELECT DISTINCT ON (f.mint)
         f.mint, f.as_of AS t0, f.snipers, f.curve_progress_pct, f.tape_reason,
         f.net_sol_flow_60s, f.curve_volume_60s_sol, f.dev_share,
         t.mayhem_enabled, t.mayhem_mode, t.completed_at, t.migrated_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE $$America/Sao_Paulo$$
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE $$America/Sao_Paulo$$
    AND f.age_s BETWEEN 30 AND 300
  ORDER BY f.mint, f.as_of
), universo AS (
  SELECT mint, t0, snipers, curve_volume_60s_sol AS vol_60s_foto
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
  SELECT DISTINCT ON (u.mint) u.mint, u.t0, u.snipers, u.vol_60s_foto,
         b.end_time AS t_in, b.mcap_sol AS base, b.curve_progress_pct AS prog_in,
         b.curve_volume_1m_sol AS vol_1m, b.net_sol_flow_1m AS flow_1m,
         b.unique_buyers AS buyers_1m, b.holders, b.buys_1m, b.sells_1m
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
    CASE WHEN mcap_sol >= 3 * base THEN $$alvo_3x$$ ELSE $$stop$$ END AS motivo
  FROM gatilho
  WHERE mcap_sol >= 3 * base OR mcap_sol <= nivel_stop
  ORDER BY mint, i
), fim AS (
  SELECT DISTINCT ON (mint) mint, mcap_sol AS preco_saida, $$tempo$$ AS motivo
  FROM gatilho ORDER BY mint, i DESC
)
SELECT :'dia' AS dia, e.mint, e.t_in, e.snipers, e.holders, e.buyers_1m,
       e.buys_1m, e.sells_1m,
       round(e.prog_in::numeric, 4)  AS prog_in,
       round(e.vol_1m::numeric, 4)   AS vol_1m,
       round(e.flow_1m::numeric, 4)  AS flow_1m,
       COALESCE(s.motivo, f.motivo) AS motivo,
       round((((COALESCE(s.preco_saida, f.preco_saida) / e.base) * 0.9825 * 0.9825 - 1) / 0.5)::numeric, 6) AS r
FROM entrada e
LEFT JOIN saida s ON s.mint = e.mint
LEFT JOIN fim f ON f.mint = e.mint
WHERE COALESCE(s.preco_saida, f.preco_saida) IS NOT NULL;
