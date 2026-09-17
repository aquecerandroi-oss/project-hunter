-- R41 16/09 21h32 BRT -- janela do executor na ULTIMA HORA CONGELADA [20:30, 21:30) BRT,
-- top 8 por demanda, com holders/compradores/fluxo/snipers/dev/creator_sold/top-10 e o retrato
-- de risco <= 600 s SEM look-ahead (observed_at <= as_of da foto). Desfecho pela CADEIA
-- (real_sol_reserves pico/atual) -- KB-0115. Reuso do r35-q02 (d)+(e) com a janela movida.
SET statement_timeout = 200000;

CREATE TEMP TABLE r41h AS
WITH janela AS (
  SELECT f.* FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz $$2026-09-16 20:30-03$$ AND f.as_of < timestamptz $$2026-09-16 21:30-03$$
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
), melhor AS (
  SELECT DISTINCT ON (j.mint) j.* FROM janela j
  ORDER BY j.mint, j.unique_buyers_60s DESC NULLS LAST, j.net_sol_flow_60s DESC
)
SELECT * FROM melhor ORDER BY unique_buyers_60s DESC NULLS LAST, net_sol_flow_60s DESC LIMIT 10;

SELECT t.symbol, left(m.mint,6) AS mint6, m.age_s, round(m.curve_progress_pct*100,1) AS prog, m.holders,
  m.unique_buyers_60s AS compr, m.buys_60s, m.sells_60s, round(m.net_sol_flow_60s,2) AS fluxo,
  round(m.curve_volume_60s_sol,1) AS vol60, m.snipers, round(m.dev_share*100,2) AS dev,
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=t.creator
     AND t2.created_at >= now() - make_interval(days => 7)) AS criador_7d,
  to_char(m.as_of AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI$$) AS foto
FROM r41h m JOIN meme_tokens t ON t.mint=m.mint
ORDER BY m.unique_buyers_60s DESC NULLS LAST, m.net_sol_flow_60s DESC;

-- (b) retrato <= 600 s sem look-ahead, creator_sold, top-10 de 1 min, fita e desfecho pela cadeia
WITH ret AS (
  SELECT DISTINCT ON (h.mint) h.mint, r.bundled_share, r.top10_share AS top10_ret,
    extract(epoch FROM (h.as_of - r.observed_at))::int AS retrato_idade_s
  FROM r41h h JOIN meme_risk_snapshots r ON r.mint=h.mint AND r.observed_at <= h.as_of
  ORDER BY h.mint, r.observed_at DESC
), um AS (
  SELECT DISTINCT ON (h.mint) h.mint, f.top10_share, f.creator_sold
  FROM r41h h JOIN meme_features_1m f ON f.mint=h.mint AND f.end_time <= h.as_of
  ORDER BY h.mint, f.end_time DESC
), tr AS (
  SELECT x.mint, x.trader, sum(x.sol_lamports)/1e9 AS sol FROM meme_trades x JOIN r41h h ON h.mint=x.mint
  WHERE x.side=$$buy$$ AND x.block_time >= timestamptz $$2026-09-16 20:20-03$$
    AND x.block_time <= h.as_of GROUP BY 1,2
), tot AS (SELECT mint, sum(sol) AS total, count(*) AS n FROM tr GROUP BY 1),
mx AS (SELECT DISTINCT ON (mint) mint, sol FROM tr ORDER BY mint, sol DESC),
pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c
       JOIN r41h h ON h.mint=c.mint GROUP BY 1),
ag AS (SELECT DISTINCT ON (c.mint) c.mint, c.real_sol_reserves AS rsol_agora, c.complete,
         c.virtual_sol_reserves-c.real_sol_reserves AS invariante, c.observed_at
       FROM meme_curve_snapshots c JOIN r41h h ON h.mint=c.mint ORDER BY c.mint, c.observed_at DESC)
SELECT t.symbol, left(h.mint,6) AS mint6, h.unique_buyers_60s AS compr,
  round(ret.bundled_share*100,1) AS bundle_ret, round(ret.top10_ret*100,1) AS top10_ret,
  ret.retrato_idade_s, round(um.top10_share*100,1) AS top10_1m, um.creator_sold,
  tot.n AS compradores_fita, round(mx.sol/nullif(tot.total,0)*100,1) AS maior_comprador_pct,
  round(pk.rsol_pico,3) AS rsol_pico, round(ag.rsol_agora,3) AS rsol_agora,
  round(100*(ag.rsol_agora/nullif(pk.rsol_pico,0)-1),1) AS delta_rsol_pct,
  ag.complete AS encheu, round(ag.invariante,3) AS invariante,
  to_char(ag.observed_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI$$) AS ultima_leitura
FROM r41h h JOIN meme_tokens t ON t.mint=h.mint
LEFT JOIN ret ON ret.mint=h.mint LEFT JOIN um ON um.mint=h.mint
LEFT JOIN tot ON tot.mint=h.mint LEFT JOIN mx ON mx.mint=h.mint
LEFT JOIN pk ON pk.mint=h.mint LEFT JOIN ag ON ag.mint=h.mint
ORDER BY h.unique_buyers_60s DESC NULLS LAST;
