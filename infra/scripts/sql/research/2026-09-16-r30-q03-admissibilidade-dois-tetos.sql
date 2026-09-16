-- R30 16/09 17h20 BRT -- a porta EM VIGOR replicada na ultima hora e a admissibilidade sob
-- DOIS conjuntos de tetos:
--   (I) tetos atuais do executor: progresso 5-50 %, bundle <= 20 %, top-10 <= 25 %,
--       creator_flow tem de ser conhecido (creator_sold nao-nulo);
--   (II) "janela de encanamento" proposta: progresso <= 85 %, bundle <= 35 %, top-10 <= 30 %,
--       criador desconhecido ok desde que dev_share <= 10 %.
-- Em ambos o retrato de risco (meme_risk_snapshots) precisa existir com <= 600 s na foto.
-- Reuso do r23-q04. Unidades: curve_progress_pct FRACAO 0-1. Horas em America/Sao_Paulo.
SET statement_timeout = 240000;

\echo == (0) rule set em vigor
SELECT id, name, version, is_active, params::text FROM meme_rule_sets
WHERE is_active ORDER BY name, version;

-- porta de features (identica nos dois cenarios, exceto o teto de progresso)
CREATE TEMP VIEW r30_bruto AS
  SELECT DISTINCT ON (f.mint) f.mint, f.as_of, t.symbol, f.holders, f.unique_buyers_60s,
    f.snipers, f.curve_progress_pct, f.net_sol_flow_60s, f.curve_volume_60s_sol,
    f.dev_share, f.buys_60s, f.sells_60s, t.creator, f.age_s, t.created_at
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= now() - make_interval(mins => 60)
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

CREATE TEMP VIEW r30_passa AS
  SELECT b.* FROM r30_bruto b
  WHERE (SELECT count(*) FROM meme_tokens o WHERE o.creator=b.creator AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol=b.symbol AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - interval '24 hours') <= 2;

\echo == (a) vazao da porta: cenario I (prog 5-50) e cenario II (prog 5-85)
SELECT count(*) FILTER (WHERE curve_progress_pct <= 0.50) AS porta_i_5_50,
       count(*) AS porta_ii_5_85,
       count(*) FILTER (WHERE unique_buyers_60s >= 25 AND curve_progress_pct <= 0.50) AS porta_i_compr25,
       count(*) FILTER (WHERE unique_buyers_60s >= 25) AS porta_ii_compr25,
       (SELECT count(*) FROM r30_bruto WHERE curve_progress_pct <= 0.50) AS antes_pedigree_i,
       (SELECT count(*) FROM r30_bruto) AS antes_pedigree_ii
FROM r30_passa;

\echo == (b) as moedas que passam a porta (5-85) + insumos de admissao
WITH risco AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.top10_share, r.bundled_share,
    extract(epoch FROM (p.as_of - r.observed_at))::int AS idade_retrato_s
  FROM r30_passa p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at <= p.as_of
  ORDER BY p.mint, r.observed_at DESC
), riscoq AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.bundled_share AS bundle_qualquer,
    extract(epoch FROM (r.observed_at - p.as_of))::int AS atraso_s
  FROM r30_passa p JOIN meme_risk_snapshots r ON r.mint=p.mint
  ORDER BY p.mint, r.observed_at
), cs AS (
  SELECT DISTINCT ON (p.mint) p.mint, f.creator_sold, f.top10_share AS top10_1m
  FROM r30_passa p JOIN meme_features_1m f ON f.mint=p.mint AND f.end_time <= p.as_of
  ORDER BY p.mint, f.end_time DESC
)
SELECT to_char(p.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
  p.symbol, left(p.mint,6) AS mint6, p.age_s, round(p.curve_progress_pct*100,1) AS prog,
  p.holders, p.unique_buyers_60s AS compr, p.buys_60s, p.sells_60s,
  round(p.net_sol_flow_60s,2) AS fluxo, round(p.curve_volume_60s_sol,1) AS vol60,
  p.snipers, round(p.dev_share*100,2) AS dev,
  round(r.top10_share*100,1) AS top10_ret, round(r.bundled_share*100,1) AS bundle_ret,
  r.idade_retrato_s, round(riscoq.bundle_qualquer*100,1) AS bundle_qualquer,
  riscoq.atraso_s, round(cs.top10_1m*100,1) AS top10_1m, cs.creator_sold,
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=p.creator
     AND t2.created_at >= now() - make_interval(days => 7)) AS criador_7d,
  (SELECT completed_at IS NOT NULL FROM meme_tokens t3 WHERE t3.mint=p.mint) AS encheu
FROM r30_passa p LEFT JOIN risco r ON r.mint=p.mint
     LEFT JOIN riscoq ON riscoq.mint=p.mint LEFT JOIN cs ON cs.mint=p.mint
ORDER BY p.as_of;

\echo == (c) admissibilidade: cenario I (atual) e cenario II (encanamento)
WITH risco AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.top10_share, r.bundled_share,
    extract(epoch FROM (p.as_of - r.observed_at))::int AS idade_retrato_s
  FROM r30_passa p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at <= p.as_of
  ORDER BY p.mint, r.observed_at DESC
), cs AS (
  SELECT DISTINCT ON (p.mint) p.mint, f.creator_sold
  FROM r30_passa p JOIN meme_features_1m f ON f.mint=p.mint AND f.end_time <= p.as_of
  ORDER BY p.mint, f.end_time DESC
), base AS (
  SELECT p.*, r.top10_share, r.bundled_share, r.idade_retrato_s, cs.creator_sold
  FROM r30_passa p LEFT JOIN risco r ON r.mint=p.mint LEFT JOIN cs ON cs.mint=p.mint
)
SELECT
  count(*) FILTER (WHERE curve_progress_pct <= 0.50) AS i_porta,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND idade_retrato_s <= 600) AS i_com_retrato,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND idade_retrato_s <= 600
        AND bundled_share <= 0.20) AS i_bundle20,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND idade_retrato_s <= 600
        AND bundled_share <= 0.20 AND top10_share <= 0.25) AS i_top25,
  count(*) FILTER (WHERE curve_progress_pct <= 0.50 AND idade_retrato_s <= 600
        AND bundled_share <= 0.20 AND top10_share <= 0.25
        AND creator_sold IS NOT NULL AND creator_sold = false) AS i_admite,
  count(*) AS ii_porta,
  count(*) FILTER (WHERE idade_retrato_s <= 600) AS ii_com_retrato,
  count(*) FILTER (WHERE idade_retrato_s <= 600 AND bundled_share <= 0.35) AS ii_bundle35,
  count(*) FILTER (WHERE idade_retrato_s <= 600 AND bundled_share <= 0.35
        AND top10_share <= 0.30) AS ii_top30,
  count(*) FILTER (WHERE idade_retrato_s <= 600 AND bundled_share <= 0.35
        AND top10_share <= 0.30 AND dev_share <= 0.10) AS ii_admite
FROM base;

\echo == (d) cobertura do retrato de risco na ultima hora
SELECT count(DISTINCT mint) AS mints_com_retrato_1h,
  count(*) AS linhas,
  round(avg(bundled_share)::numeric,4) AS bundle_medio,
  round((percentile_cont(0.5) WITHIN GROUP (ORDER BY bundled_share))::numeric,4) AS bundle_mediano,
  count(*) FILTER (WHERE bundled_share <= 0.20) AS ate_20,
  count(*) FILTER (WHERE bundled_share <= 0.35) AS ate_35
FROM meme_risk_snapshots WHERE observed_at >= now() - make_interval(mins => 60);

\echo == (e) funil cumulativo da porta na ultima hora (prog 5-50 vs 5-85)
WITH j AS (
  SELECT f.* FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= now() - make_interval(mins => 60) AND f.age_s BETWEEN 30 AND 300
    AND t.mayhem_mode IS NULL
)
SELECT count(DISTINCT mint) AS idade_30_300,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50) AS prog_5_50,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85) AS prog_5_85,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL) AS com_fita,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0) AS fluxo_pos,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20) AS holders20,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10) AS compr10,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 25) AS compr25,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10 AND buys_60s > 0
        AND sells_60s::numeric/buys_60s <= 0.6) AS razao06,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10 AND buys_60s > 0
        AND sells_60s::numeric/buys_60s <= 0.6 AND snipers >= 21) AS snipers21,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.85 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10 AND buys_60s > 0
        AND sells_60s::numeric/buys_60s <= 0.6 AND snipers >= 21 AND dev_share <= 0.10
        AND curve_volume_60s_sol >= 5) AS mais_dev_e_vol
FROM j;
