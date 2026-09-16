-- R35 16/09 17h52 BRT -- QUEM cada teto admite, janela CONGELADA [16:50:00, 17:50:00) BRT.
-- Reuso literal do r30-q04 (janela congelada; o r30-q03 usava now() e a hora deslizava entre etapas).
-- Cenarios:
--   (I) em vigor: progresso 5-50 %, retrato <= 600 s, bundle <= 20 %, top-10 <= 25 %, creator_sold = false conhecido;
--   (II) encanamento: progresso 5-85 %, retrato <= 600 s, bundle <= 35 %, top-10 <= 30 %, dev <= 10 % (criador desconhecido ok).
-- DESFECHO PELA CADEIA (real_sol_reserves pico/atual) -- KB-0115, nunca mcap_sol nem a fita.
SET statement_timeout = 240000;

CREATE TEMP TABLE r35f_bruto AS
  SELECT DISTINCT ON (f.mint) f.mint, f.as_of, t.symbol, f.holders, f.unique_buyers_60s,
    f.snipers, f.curve_progress_pct, f.net_sol_flow_60s, f.curve_volume_60s_sol,
    f.dev_share, f.buys_60s, f.sells_60s, t.creator, f.age_s, t.created_at
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 16:50-03' AND f.as_of < timestamptz '2026-09-16 17:50-03'
    AND f.age_s BETWEEN 30 AND 300
    AND t.mayhem_mode IS NULL
    AND (t.completed_at IS NULL OR t.completed_at > f.as_of)
    AND (t.migrated_at IS NULL OR t.migrated_at > f.as_of)
    AND f.curve_progress_pct BETWEEN 0.05 AND 0.85
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10
    AND f.snipers IS NOT NULL AND f.snipers >= 21
    AND f.dev_share IS NOT NULL AND f.dev_share <= 0.10
    AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND f.curve_volume_60s_sol IS NOT NULL AND f.curve_volume_60s_sol >= 5
    AND t.creator IS NOT NULL AND t.created_at IS NOT NULL
  ORDER BY f.mint, f.as_of;

CREATE TEMP TABLE r35f AS
  SELECT b.* FROM r35f_bruto b
  WHERE (SELECT count(*) FROM meme_tokens o WHERE o.creator=b.creator AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol=b.symbol AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - interval '24 hours') <= 2;

CREATE TEMP TABLE r35f_ins AS
WITH risco AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.top10_share, r.bundled_share,
    extract(epoch FROM (p.as_of - r.observed_at))::int AS idade_retrato_s
  FROM r35f p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at <= p.as_of
  ORDER BY p.mint, r.observed_at DESC
), cs AS (
  SELECT DISTINCT ON (p.mint) p.mint, f.creator_sold
  FROM r35f p JOIN meme_features_1m f ON f.mint=p.mint AND f.end_time <= p.as_of
  ORDER BY p.mint, f.end_time DESC
)
SELECT p.*, r.top10_share, r.bundled_share, r.idade_retrato_s, cs.creator_sold
FROM r35f p LEFT JOIN risco r ON r.mint=p.mint LEFT JOIN cs ON cs.mint=p.mint;

\echo == (a) funil cumulativo da porta na hora congelada (moedas distintas)
WITH u AS (
  SELECT DISTINCT ON (f.mint) f.mint, f.age_s, f.curve_progress_pct, f.tape_reason, f.net_sol_flow_60s,
    f.holders, f.unique_buyers_60s, f.snipers, f.dev_share, f.buys_60s, f.sells_60s, f.curve_volume_60s_sol
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz '2026-09-16 16:50-03' AND f.as_of < timestamptz '2026-09-16 17:50-03'
    AND f.age_s BETWEEN 30 AND 300
  ORDER BY f.mint, f.as_of
)
SELECT count(*) AS idade,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50) AS prog_5_50,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85) AS prog_5_85,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL) AS com_fita,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
                     AND net_sol_flow_60s > 0) AS fluxo_pos,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
                     AND net_sol_flow_60s > 0 AND holders >= 20) AS holders20,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
                     AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10) AS compr10,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
                     AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10
                     AND buys_60s > 0 AND sells_60s::numeric/buys_60s <= 0.6) AS razao06,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
                     AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10
                     AND buys_60s > 0 AND sells_60s::numeric/buys_60s <= 0.6 AND snipers >= 21) AS snip21,
  count(*) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
                     AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10
                     AND buys_60s > 0 AND sells_60s::numeric/buys_60s <= 0.6 AND snipers >= 21
                     AND dev_share <= 0.10 AND curve_volume_60s_sol >= 5) AS dev_vol
FROM u;

\echo == (b) contagem congelada: porta e admissibilidade nos dois cenarios (+ piso KB-0114 compradores >= 25)
SELECT count(*) FILTER (WHERE curve_progress_pct <= 0.50) AS i_porta,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND idade_retrato_s <= 600) AS i_retrato,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND idade_retrato_s <= 600 AND bundled_share <= 0.20) AS i_bundle20,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND idade_retrato_s <= 600 AND bundled_share <= 0.20
        AND top10_share <= 0.25) AS i_top25,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND idade_retrato_s <= 600 AND bundled_share <= 0.20
        AND top10_share <= 0.25 AND creator_sold = false) AS i_admite,
  count(*) AS ii_porta,
  count(*) FILTER (WHERE idade_retrato_s <= 600) AS ii_retrato,
  count(*) FILTER (WHERE idade_retrato_s <= 600 AND bundled_share <= 0.35) AS ii_bundle35,
  count(*) FILTER (WHERE idade_retrato_s <= 600 AND bundled_share <= 0.35 AND top10_share <= 0.30) AS ii_top30,
  count(*) FILTER (WHERE idade_retrato_s <= 600 AND bundled_share <= 0.35 AND top10_share <= 0.30
        AND dev_share <= 0.10) AS ii_admite,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND unique_buyers_60s >= 25) AS i_porta_kb0114,
  count(*) FILTER (WHERE unique_buyers_60s >= 25) AS ii_porta_kb0114
FROM r35f_ins;

\echo == (c) NOMES: quem tem retrato <= 600 s (os unicos admissiveis em qualquer cenario)
SELECT to_char(as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt, symbol,
  left(mint,6) AS mint6, round(curve_progress_pct*100,1) AS prog, holders,
  unique_buyers_60s AS compr, snipers, round(dev_share*100,2) AS dev,
  round(bundled_share*100,1) AS bundle, round(top10_share*100,1) AS top10,
  idade_retrato_s, creator_sold,
  (curve_progress_pct <= 0.50 AND bundled_share <= 0.20 AND top10_share <= 0.25
     AND creator_sold = false) AS admite_i,
  (bundled_share <= 0.35 AND top10_share <= 0.30 AND dev_share <= 0.10) AS admite_ii
FROM r35f_ins WHERE idade_retrato_s <= 600 ORDER BY as_of;

\echo == (d) DESFECHO PELA CADEIA das admitidas pelo cenario II
WITH adm AS (
  SELECT * FROM r35f_ins WHERE idade_retrato_s <= 600 AND bundled_share <= 0.35
    AND top10_share <= 0.30 AND dev_share <= 0.10
), na AS (
  SELECT DISTINCT ON (a.mint) a.mint, c.real_sol_reserves AS rsol_na_foto, c.mcap_sol AS mcap_na_foto
  FROM adm a JOIN meme_curve_snapshots c ON c.mint=a.mint AND c.observed_at <= a.as_of + interval '30 s'
  ORDER BY a.mint, c.observed_at DESC
), pk AS (SELECT a.mint, max(c.real_sol_reserves) AS rsol_pico FROM adm a
          JOIN meme_curve_snapshots c ON c.mint=a.mint GROUP BY 1),
ag AS (SELECT DISTINCT ON (a.mint) a.mint, c.real_sol_reserves AS rsol_agora, c.mcap_sol AS mcap_agora,
         c.complete, c.mayhem_enabled, c.virtual_sol_reserves-c.real_sol_reserves AS invariante, c.observed_at
       FROM adm a JOIN meme_curve_snapshots c ON c.mint=a.mint ORDER BY a.mint, c.observed_at DESC)
SELECT a.symbol, left(a.mint,6) AS mint6,
  to_char(a.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS hora_brt,
  round(a.curve_progress_pct*100,1) AS prog_na_foto, a.holders, a.unique_buyers_60s AS compr,
  round(a.bundled_share*100,1) AS bundle, round(a.top10_share*100,1) AS top10,
  round(na.rsol_na_foto,3) AS rsol_na_foto, round(pk.rsol_pico,3) AS rsol_pico,
  round(ag.rsol_agora,3) AS rsol_agora,
  round(100*(ag.rsol_agora/nullif(na.rsol_na_foto,0)-1),1) AS delta_vs_entrada_pct,
  round(100*(ag.rsol_agora/nullif(pk.rsol_pico,0)-1),1) AS delta_vs_pico_pct,
  round(ag.mcap_agora,1) AS mcap_agora, ag.complete AS encheu, ag.mayhem_enabled,
  round(ag.invariante,3) AS invariante,
  to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ultima_leitura
FROM adm a LEFT JOIN na ON na.mint=a.mint LEFT JOIN pk ON pk.mint=a.mint LEFT JOIN ag ON ag.mint=a.mint
ORDER BY a.as_of;

\echo == (e) o preco de esperar: quantas na porta 5-85 ganharam retrato DEPOIS e com que atraso
WITH pos AS (
  SELECT DISTINCT ON (p.mint) p.mint, p.symbol, r.bundled_share, r.top10_share,
    extract(epoch FROM (r.observed_at - p.as_of))::int AS atraso_s
  FROM r35f p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at > p.as_of
  ORDER BY p.mint, r.observed_at
)
SELECT count(*) AS com_retrato_posterior,
  count(*) FILTER (WHERE atraso_s <= 60) AS ate_60s,
  count(*) FILTER (WHERE atraso_s <= 120) AS ate_120s,
  count(*) FILTER (WHERE atraso_s <= 120 AND bundled_share <= 0.35) AS ate_120s_e_bundle35,
  count(*) FILTER (WHERE atraso_s <= 120 AND bundled_share <= 0.35 AND top10_share <= 0.30) AS ate_120s_e_top30,
  round(avg(atraso_s)) AS atraso_medio_s
FROM pos;

\echo == (f) cobertura do RiskReader na hora congelada
SELECT count(DISTINCT mint) AS mints, count(*) AS leituras,
  round(avg(bundled_share),4) AS bundle_medio,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY bundled_share)::numeric,4) AS bundle_mediano,
  count(*) FILTER (WHERE bundled_share <= 0.20) AS ate20,
  count(*) FILTER (WHERE bundled_share <= 0.35) AS ate35
FROM meme_risk_snapshots
WHERE observed_at >= timestamptz '2026-09-16 16:50-03' AND observed_at < timestamptz '2026-09-16 17:50-03';
