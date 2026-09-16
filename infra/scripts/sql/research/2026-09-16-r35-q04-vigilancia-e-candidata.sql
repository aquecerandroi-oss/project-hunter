-- R35 16/09 17h54 BRT -- (1) casamentos do viveiro com os termos de vigilancia do plantao
-- (02-MARKET/Eventos/2026-09-16-18h30-brt: HYPED/DONO, XCEO/XDOGE, ILY/LUV; baha: GROK, MAYDAY/plane)
-- e (2) a serie da unica candidata viva na porta agora, pela CADEIA (real_sol_reserves) -- KB-0115.
SET statement_timeout = 240000;

\echo == (a) casamentos por termo de vigilancia entre as moedas nascidas hoje (contagem e demanda)
WITH termos(termo, padrao) AS (VALUES
  ('HYPED','hyped'), ('DONO','dono'), ('XCEO','xceo'), ('XDOGE','xdoge'),
  ('ILY','ily'), ('LUV','luv'), ('GROK','grok'), ('MAYDAY','mayday'), ('plane','plane')
), tok AS (
  SELECT t.mint, t.symbol, t.name, t.created_at, t.creator, t.completed_at, t.migrated_at
  FROM meme_tokens t WHERE t.created_at >= timestamptz '2026-09-16 00:00-03'
), casos AS (
  SELECT x.termo, k.* FROM termos x JOIN tok k
    ON lower(k.symbol) = x.padrao OR lower(k.symbol) LIKE x.padrao||'%'
       OR lower(coalesce(k.name,'')) LIKE '%'||x.padrao||'%'
)
SELECT c.termo, count(*) AS moedas_hoje,
  count(*) FILTER (WHERE c.created_at >= timestamptz '2026-09-16 16:50-03') AS na_ultima_hora,
  count(*) FILTER (WHERE c.completed_at IS NOT NULL) AS encheram,
  count(*) FILTER (WHERE c.migrated_at IS NOT NULL) AS migraram
FROM casos c GROUP BY 1 ORDER BY 2 DESC;

\echo == (b) as moedas dos termos que ENTRARAM na janela do radar hoje (melhor foto por moeda)
WITH termos(termo, padrao) AS (VALUES
  ('HYPED','hyped'), ('DONO','dono'), ('XCEO','xceo'), ('XDOGE','xdoge'),
  ('ILY','ily'), ('LUV','luv'), ('GROK','grok'), ('MAYDAY','mayday'), ('plane','plane')
), tok AS (
  SELECT x.termo, t.mint, t.symbol, t.name, t.created_at, t.creator
  FROM termos x JOIN meme_tokens t
    ON (lower(t.symbol) = x.padrao OR lower(t.symbol) LIKE x.padrao||'%'
        OR lower(coalesce(t.name,'')) LIKE '%'||x.padrao||'%')
  WHERE t.created_at >= timestamptz '2026-09-16 00:00-03' AND t.mayhem_mode IS NULL
), melhor AS (
  SELECT DISTINCT ON (k.mint) k.termo, k.mint, k.symbol, k.name, k.creator, f.as_of,
    f.curve_progress_pct, f.holders, f.unique_buyers_60s, f.buys_60s, f.sells_60s,
    f.net_sol_flow_60s, f.curve_volume_60s_sol, f.snipers, f.dev_share
  FROM tok k JOIN meme_features_15s f ON f.mint=k.mint
  WHERE f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.85
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
  ORDER BY k.mint, f.unique_buyers_60s DESC NULLS LAST, f.net_sol_flow_60s DESC
), pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c
          JOIN melhor m ON m.mint=c.mint GROUP BY 1),
ag AS (SELECT DISTINCT ON (c.mint) c.mint, c.real_sol_reserves AS rsol_agora, c.mcap_sol,
         c.complete, c.observed_at FROM meme_curve_snapshots c JOIN melhor m ON m.mint=c.mint
       ORDER BY c.mint, c.observed_at DESC)
SELECT m.termo, m.symbol, left(m.mint,6) AS mint6,
  to_char(m.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS melhor_foto,
  round(m.curve_progress_pct*100,1) AS prog, m.holders, m.unique_buyers_60s AS compr,
  m.buys_60s, m.sells_60s, round(m.net_sol_flow_60s,2) AS fluxo,
  round(m.curve_volume_60s_sol,1) AS vol60, m.snipers, round(m.dev_share*100,2) AS dev,
  round(pk.rsol_pico,3) AS rsol_pico, round(ag.rsol_agora,3) AS rsol_agora,
  round(100*(ag.rsol_agora/nullif(pk.rsol_pico,0)-1),1) AS delta_rsol_pct,
  round(ag.mcap_sol,1) AS mcap_agora, ag.complete AS encheu,
  to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ultima_leitura
FROM melhor m LEFT JOIN pk ON pk.mint=m.mint LEFT JOIN ag ON ag.mint=m.mint
ORDER BY m.unique_buyers_60s DESC NULLS LAST LIMIT 25;

\echo == (c) TOKTIP 2oiz6g -- a candidata viva: serie da CADEIA (real_sol_reserves)
SELECT to_char(observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt, slot,
  round(virtual_sol_reserves,3) AS vsol, round(real_sol_reserves,3) AS rsol,
  round(virtual_sol_reserves-real_sol_reserves,3) AS invariante, round(mcap_sol,1) AS mcap,
  complete, source, commitment, mayhem_enabled
FROM meme_curve_snapshots WHERE mint LIKE '2oiz6g%' ORDER BY observed_at DESC LIMIT 12;

\echo == (d) TOKTIP: retrato de risco, 15 s recente e fita (compradores e maior comprador)
SELECT to_char(observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
  round(bundled_share*100,1) AS bundle, round(top10_share*100,1) AS top10
FROM meme_risk_snapshots WHERE mint LIKE '2oiz6g%' ORDER BY observed_at DESC LIMIT 5;

SELECT to_char(as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt, age_s,
  round(curve_progress_pct*100,1) AS prog, holders, unique_buyers_60s AS compr,
  buys_60s, sells_60s, round(net_sol_flow_60s,2) AS fluxo, round(curve_volume_60s_sol,1) AS vol60,
  snipers, round(dev_share*100,2) AS dev
FROM meme_features_15s WHERE mint LIKE '2oiz6g%' ORDER BY as_of DESC LIMIT 6;

WITH tr AS (SELECT trader, sum(sol_lamports)/1e9 AS sol FROM meme_trades
            WHERE mint LIKE '2oiz6g%' AND side='buy' GROUP BY 1)
SELECT count(*) AS compradores, round(sum(sol),2) AS sol_comprado,
  round(max(sol)/nullif(sum(sol),0)*100,1) AS maior_comprador_pct FROM tr;

\echo == (e) criador da TOKTIP: quantas moedas em 7 d e o que fizeram
SELECT left(t.creator,8) AS criador,
  (SELECT count(*) FROM meme_tokens o WHERE o.creator=t.creator
     AND o.created_at >= now() - make_interval(days => 7)) AS moedas_7d,
  to_char(t.created_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS criada_brt,
  t.completed_at IS NOT NULL AS encheu, t.migrated_at IS NOT NULL AS migrou, t.mayhem_mode
FROM meme_tokens t WHERE t.mint LIKE '2oiz6g%';
