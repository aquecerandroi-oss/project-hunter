-- R35 16/09 17h56 BRT -- o instante da decisao: quem esta na porta AGORA (3 min) e como esta
-- a unica candidata viva, pela CADEIA (real_sol_reserves) -- KB-0115.
SET statement_timeout = 120000;

\echo == (a) na porta agora (3 min, prog 5-85, porta operator/5) + cadeia + retrato + fita
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.*, t.symbol, t.creator FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 3)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.85
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10 AND f.snipers >= 21
    AND f.dev_share <= 0.10 AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND f.curve_volume_60s_sol >= 5
  ORDER BY f.mint, f.as_of DESC
), r AS (
  SELECT DISTINCT ON (s.mint) s.mint, s.bundled_share, s.top10_share, s.observed_at
  FROM meme_risk_snapshots s JOIN j ON j.mint=s.mint AND s.observed_at <= j.as_of
  ORDER BY s.mint, s.observed_at DESC
), ag AS (
  SELECT DISTINCT ON (c.mint) c.mint, c.real_sol_reserves AS rsol, c.mcap_sol,
    c.virtual_sol_reserves-c.real_sol_reserves AS invariante, c.observed_at
  FROM meme_curve_snapshots c JOIN j ON j.mint=c.mint ORDER BY c.mint, c.observed_at DESC
), pk AS (SELECT c.mint, max(c.real_sol_reserves) AS pico FROM meme_curve_snapshots c
          JOIN j ON j.mint=c.mint GROUP BY 1)
SELECT to_char(j.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS foto, j.symbol,
  left(j.mint,6) AS mint6, round(j.curve_progress_pct*100,1) AS prog, j.holders,
  j.unique_buyers_60s AS compr, j.buys_60s, j.sells_60s, round(j.net_sol_flow_60s,2) AS fluxo,
  j.snipers, round(j.dev_share*100,2) AS dev,
  round(r.bundled_share*100,1) AS bundle, round(r.top10_share*100,1) AS top10,
  extract(epoch FROM (j.as_of-r.observed_at))::int AS retrato_idade_s,
  round(pk.pico,3) AS rsol_pico, round(ag.rsol,3) AS rsol_agora, round(ag.mcap_sol,1) AS mcap,
  round(ag.invariante,3) AS invariante,
  to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS ultima_leitura
FROM j LEFT JOIN r ON r.mint=j.mint LEFT JOIN ag ON ag.mint=j.mint LEFT JOIN pk ON pk.mint=j.mint
ORDER BY j.unique_buyers_60s DESC NULLS LAST;

\echo == (b) TOKTIP 2oiz6g: ultimas leituras da cadeia
SELECT to_char(observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
  round(real_sol_reserves,3) AS rsol, round(virtual_sol_reserves-real_sol_reserves,3) AS invariante,
  round(mcap_sol,1) AS mcap, complete
FROM meme_curve_snapshots WHERE mint LIKE '2oiz6g%' ORDER BY observed_at DESC LIMIT 5;

\echo == (c) as 4 moedas da mesa desde 17:25: cadeia agora
WITH m(mint6) AS (VALUES ('5nCEDZ'),('yemWGA'),('HWZ6LQ'),('2oiz6g'))
SELECT left(c.mint,6) AS mint6, t.symbol,
  to_char(max(c.observed_at) AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS ultima_leitura,
  round(max(c.real_sol_reserves),3) AS rsol_pico,
  round((SELECT z.real_sol_reserves FROM meme_curve_snapshots z WHERE z.mint=c.mint
         ORDER BY z.observed_at DESC LIMIT 1),3) AS rsol_agora
FROM meme_curve_snapshots c JOIN m ON c.mint LIKE m.mint6||'%'
JOIN meme_tokens t ON t.mint=c.mint GROUP BY 1,2, c.mint ORDER BY 2;
