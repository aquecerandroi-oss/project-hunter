-- R30 16/09 17h25 BRT -- QUEM cada teto admite, com a janela CONGELADA num instante fixo
-- (o r30-q03 usa now() e a view e reavaliada a cada consulta: a hora desliza entre as etapas).
-- Janela congelada: [16:25:00, 17:25:00) BRT. Cenarios:
--   (I) atual: progresso 5-50 %, retrato <= 600 s, bundle <= 20 %, top-10 <= 25 %, creator_sold conhecido = false;
--   (II) encanamento: progresso 5-85 %, retrato <= 600 s, bundle <= 35 %, top-10 <= 30 %, dev <= 10 % (criador desconhecido ok).
SET statement_timeout = 240000;

CREATE TEMP TABLE r30f_bruto AS
  SELECT DISTINCT ON (f.mint) f.mint, f.as_of, t.symbol, f.holders, f.unique_buyers_60s,
    f.snipers, f.curve_progress_pct, f.net_sol_flow_60s, f.curve_volume_60s_sol,
    f.dev_share, f.buys_60s, f.sells_60s, t.creator, f.age_s, t.created_at
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 16:25-03' AND f.as_of < timestamptz '2026-09-16 17:25-03'
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

CREATE TEMP TABLE r30f AS
  SELECT b.* FROM r30f_bruto b
  WHERE (SELECT count(*) FROM meme_tokens o WHERE o.creator=b.creator AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol=b.symbol AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - interval '24 hours') <= 2;

CREATE TEMP TABLE r30f_ins AS
WITH risco AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.top10_share, r.bundled_share,
    extract(epoch FROM (p.as_of - r.observed_at))::int AS idade_retrato_s
  FROM r30f p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at <= p.as_of
  ORDER BY p.mint, r.observed_at DESC
), cs AS (
  SELECT DISTINCT ON (p.mint) p.mint, f.creator_sold
  FROM r30f p JOIN meme_features_1m f ON f.mint=p.mint AND f.end_time <= p.as_of
  ORDER BY p.mint, f.end_time DESC
)
SELECT p.*, r.top10_share, r.bundled_share, r.idade_retrato_s, cs.creator_sold
FROM r30f p LEFT JOIN risco r ON r.mint=p.mint LEFT JOIN cs ON cs.mint=p.mint;

\echo == (a) contagem congelada: porta e admissibilidade nos dois cenarios
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
        AND dev_share <= 0.10) AS ii_admite
FROM r30f_ins;

\echo == (b) NOMES: quem tem retrato <= 600 s (os unicos admissiveis em qualquer cenario)
SELECT to_char(as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt, symbol,
  left(mint,6) AS mint6, round(curve_progress_pct*100,1) AS prog, holders,
  unique_buyers_60s AS compr, snipers, round(dev_share*100,2) AS dev,
  round(bundled_share*100,1) AS bundle, round(top10_share*100,1) AS top10,
  idade_retrato_s, creator_sold,
  (curve_progress_pct <= 0.50 AND bundled_share <= 0.20 AND top10_share <= 0.25
     AND creator_sold = false) AS admite_i,
  (bundled_share <= 0.35 AND top10_share <= 0.30 AND dev_share <= 0.10) AS admite_ii
FROM r30f_ins WHERE idade_retrato_s <= 600 ORDER BY as_of;

\echo == (c) o que as admitidas pelo cenario II fizeram depois (1 min: na foto vs agora)
WITH adm AS (
  SELECT * FROM r30f_ins WHERE idade_retrato_s <= 600 AND bundled_share <= 0.35
    AND top10_share <= 0.30 AND dev_share <= 0.10
), na AS (
  SELECT DISTINCT ON (a.mint) a.mint, b.mcap_sol, b.curve_progress_pct, b.holders
  FROM adm a JOIN meme_features_1m b ON b.mint=a.mint AND b.end_time <= a.as_of + interval '60 s'
  ORDER BY a.mint, b.end_time DESC
), ag AS (
  SELECT DISTINCT ON (a.mint) a.mint, b.mcap_sol, b.curve_progress_pct, b.holders, b.top10_share, b.end_time
  FROM adm a JOIN meme_features_1m b ON b.mint=a.mint ORDER BY a.mint, b.end_time DESC
)
SELECT a.symbol, left(a.mint,6) AS mint6,
  to_char(a.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS hora_brt,
  round(na.mcap_sol,1) AS mcap_na_foto, round(ag.mcap_sol,1) AS mcap_agora,
  round(100*(ag.mcap_sol/nullif(na.mcap_sol,0)-1),1) AS delta_pct,
  round(na.curve_progress_pct*100,1) AS prog_na_foto, round(ag.curve_progress_pct*100,1) AS prog_agora,
  na.holders AS holders_na_foto, ag.holders AS holders_agora,
  round(ag.top10_share*100,1) AS top10_agora,
  (SELECT completed_at IS NOT NULL FROM meme_tokens t WHERE t.mint=a.mint) AS encheu,
  to_char(ag.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ultima_foto
FROM adm a LEFT JOIN na ON na.mint=a.mint LEFT JOIN ag ON ag.mint=a.mint ORDER BY a.as_of;

\echo == (d) o preco de esperar: quantas na porta 5-85 ganharam retrato DEPOIS e com que atraso
WITH pos AS (
  SELECT DISTINCT ON (p.mint) p.mint, p.symbol, r.bundled_share, r.top10_share,
    extract(epoch FROM (r.observed_at - p.as_of))::int AS atraso_s
  FROM r30f p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at > p.as_of
  ORDER BY p.mint, r.observed_at
)
SELECT count(*) AS com_retrato_posterior,
  count(*) FILTER (WHERE atraso_s <= 60) AS ate_60s,
  count(*) FILTER (WHERE atraso_s <= 120) AS ate_120s,
  count(*) FILTER (WHERE atraso_s <= 120 AND bundled_share <= 0.35) AS ate_120s_e_bundle35,
  round(avg(atraso_s)) AS atraso_medio_s
FROM pos;
