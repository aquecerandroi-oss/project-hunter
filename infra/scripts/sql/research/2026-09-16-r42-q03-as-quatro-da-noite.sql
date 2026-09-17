-- KB-0118 Q03 — as 4 moedas da noite de 16/09 (R41): drawdown de
-- real_sol_reserves na hora da PRIMEIRA ordem (pico nos ultimos 300 s) e o
-- que a curva fez nos 30 min seguintes. Horas e prefixos de mint vindos da
-- rodada R41 (obsidian/03-TRADING/Meme/Candidatas/2026-09-16-21h40-brt.md).
SET statement_timeout = 60000;
WITH ordens(prefixo, t_ordem) AS (VALUES
  ('7fWspN%', '2026-09-16 19:48:43-03'::timestamptz),
  ('H91rJ7%', '2026-09-16 20:45:48-03'::timestamptz),
  ('Fyko94%', '2026-09-16 21:14:13-03'::timestamptz),
  ('7s4dKm%', '2026-09-16 21:31:28-03'::timestamptz)
), alvo AS (
  SELECT t.mint, t.symbol, o.t_ordem
  FROM ordens o JOIN meme_tokens t ON t.mint LIKE o.prefixo
), curva AS (
  SELECT a.mint, c.observed_at, c.real_sol_reserves
  FROM alvo a JOIN meme_curve_snapshots c ON c.mint = a.mint
   AND c.observed_at >= a.t_ordem - interval '300 seconds' AND c.observed_at <= a.t_ordem
  WHERE c.real_sol_reserves IS NOT NULL
), pico AS (
  SELECT DISTINCT ON (mint) mint, real_sol_reserves AS rsol_pico, observed_at AS t_pico
  FROM curva ORDER BY mint, real_sol_reserves DESC, observed_at DESC
), atual AS (
  SELECT DISTINCT ON (mint) mint, real_sol_reserves AS rsol_atual, observed_at AS t_atual
  FROM curva ORDER BY mint, observed_at DESC
), depois AS (
  SELECT a.mint, max(c.real_sol_reserves) AS rsol_max_30m, min(c.real_sol_reserves) AS rsol_min_30m
  FROM alvo a JOIN meme_curve_snapshots c ON c.mint = a.mint
   AND c.observed_at > a.t_ordem AND c.observed_at <= a.t_ordem + interval '30 minutes'
  GROUP BY a.mint
)
SELECT a.symbol, to_char(a.t_ordem AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS ordem_brt,
       round(p.rsol_pico,3) AS rsol_pico,
       to_char(p.t_pico AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_pico,
       round(a2.rsol_atual,3) AS rsol_na_ordem,
       round(100.0*(1 - a2.rsol_atual/NULLIF(p.rsol_pico,0)),1) AS dd_pct,
       round(extract(epoch FROM a.t_ordem - p.t_pico)::numeric,0) AS t_pico_s,
       round(d.rsol_max_30m,3) AS rsol_max_30m, round(d.rsol_min_30m,3) AS rsol_min_30m,
       round(d.rsol_max_30m/NULLIF(a2.rsol_atual,0),2) AS multiplo_max_rsol
FROM alvo a LEFT JOIN pico p ON p.mint=a.mint LEFT JOIN atual a2 ON a2.mint=a.mint
LEFT JOIN depois d ON d.mint=a.mint ORDER BY a.t_ordem;
