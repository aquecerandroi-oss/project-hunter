-- KB-0114 Q03 — redundancia: "compradores >= X ja implica holders >= 20?"
-- Universo = mesmo da q01 (porta sem participacao, snipers >= 21). Barras candidatas =
-- TODAS as barras de 1 min nos 5 min seguintes a foto, SEM o filtro de holders e SEM o
-- de compradores: e a unica forma de ver a implicacao sem circularidade (na coorte da
-- q01 holders >= 20 vale por construcao). Uma linha por piso de compradores.
-- Uso: psql -v dia=2026-09-15 -v ew=5 -At -f este-arquivo.sql
SET statement_timeout = 60000;
WITH foto AS (
  SELECT DISTINCT ON (f.mint) f.mint, f.as_of AS t0, f.snipers, f.curve_progress_pct,
         f.tape_reason, f.net_sol_flow_60s, f.dev_share,
         t.mayhem_enabled, t.mayhem_mode, t.completed_at, t.migrated_at
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE $$America/Sao_Paulo$$
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE $$America/Sao_Paulo$$
    AND f.age_s BETWEEN 30 AND 300
  ORDER BY f.mint, f.as_of
), universo AS (
  SELECT mint, t0, snipers FROM foto
  WHERE (completed_at IS NULL OR completed_at > t0)
    AND (migrated_at IS NULL OR migrated_at > t0)
    AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled AND mayhem_mode IS NULL
    AND curve_progress_pct BETWEEN 0.05 AND 0.50
    AND tape_reason IS NULL AND net_sol_flow_60s > 0
    AND dev_share IS NOT NULL AND dev_share <= 0.10
    AND snipers IS NOT NULL AND snipers >= 21
), barras AS (
  SELECT u.mint, u.snipers, b.unique_buyers, b.holders
  FROM universo u
  JOIN meme_features_1m b ON b.mint = u.mint
   AND b.end_time > u.t0 AND b.end_time <= u.t0 + make_interval(mins => (:'ew')::int)
  WHERE b.mcap_sol IS NOT NULL AND b.mcap_sol > 0
    AND b.unique_buyers IS NOT NULL AND b.holders IS NOT NULL
    AND b.buys_1m > 0 AND b.sells_1m::numeric / b.buys_1m <= 0.6
), pisos AS (SELECT unnest(ARRAY[10,15,20,25,30,40,60]) AS piso)
SELECT :'dia' AS dia, p.piso,
       count(*) AS barras_com_compradores_no_piso,
       count(*) FILTER (WHERE b.holders >= 20) AS tambem_holders_20,
       round(100.0 * count(*) FILTER (WHERE b.holders >= 20) / nullif(count(*),0), 1) AS pct_holders_20,
       round(100.0 * count(*) FILTER (WHERE b.holders >= 40) / nullif(count(*),0), 1) AS pct_holders_40,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY b.holders) AS mediana_holders,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY b.snipers) AS mediana_snipers
FROM pisos p JOIN barras b ON b.unique_buyers >= p.piso
GROUP BY p.piso ORDER BY p.piso;
