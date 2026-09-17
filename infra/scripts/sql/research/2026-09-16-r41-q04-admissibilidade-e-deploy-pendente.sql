-- R41 16/09 21h32 BRT -- porta do executor na hora CONGELADA [20:30, 21:30) BRT e quantas o
-- executor admitiria com o PACOTE DO DEPLOY PENDENTE (T4.28g: esperar o retrato ate 60/120 s).
-- Cenario I = tetos em vigor (prog 5-50 %, bundle <= 20 %, top-10 <= 25 %, creator_sold = false).
-- Cenario ESPERA = os mesmos tetos, mas aceitando o retrato que chega ATE 60 s / 120 s DEPOIS da
-- foto (e por isso a foto so pode ser decidida com esse atraso -- nao e look-ahead de preco,
-- e espera explicita). Reuso do r35-q03. Desfecho pela cadeia -- KB-0115.
SET statement_timeout = 200000;

CREATE TEMP TABLE r41f_bruto AS
  SELECT DISTINCT ON (f.mint) f.mint, f.as_of, t.symbol, f.holders, f.unique_buyers_60s,
    f.snipers, f.curve_progress_pct, f.net_sol_flow_60s, f.curve_volume_60s_sol,
    f.dev_share, f.buys_60s, f.sells_60s, t.creator, f.age_s, t.created_at
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= timestamptz $$2026-09-16 20:30-03$$ AND f.as_of < timestamptz $$2026-09-16 21:30-03$$
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

CREATE TEMP TABLE r41f AS
  SELECT b.* FROM r41f_bruto b
  WHERE (SELECT count(*) FROM meme_tokens o WHERE o.creator=b.creator AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - make_interval(hours => 1)) <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol=b.symbol AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - make_interval(hours => 24)) <= 2;

-- (a) funil cumulativo da porta na hora congelada (moedas distintas)
WITH u AS (
  SELECT DISTINCT ON (f.mint) f.mint, f.age_s, f.curve_progress_pct, f.tape_reason, f.net_sol_flow_60s,
    f.holders, f.unique_buyers_60s, f.snipers, f.dev_share, f.buys_60s, f.sells_60s, f.curve_volume_60s_sol
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz $$2026-09-16 20:30-03$$ AND f.as_of < timestamptz $$2026-09-16 21:30-03$$
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

-- (b) porta e retrato: o que ja existe (<= 600 s antes) x o que CHEGA depois (deploy pendente)
WITH antes AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.bundled_share, r.top10_share,
    extract(epoch FROM (p.as_of - r.observed_at))::int AS idade_s
  FROM r41f p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at <= p.as_of
  ORDER BY p.mint, r.observed_at DESC
), depois AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.bundled_share, r.top10_share,
    extract(epoch FROM (r.observed_at - p.as_of))::int AS atraso_s
  FROM r41f p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at > p.as_of
  ORDER BY p.mint, r.observed_at
)
SELECT count(*) AS na_porta_5_85,
  count(*) FILTER (WHERE p.curve_progress_pct <= 0.50) AS na_porta_5_50,
  count(a.mint) AS com_retrato_antes,
  count(a.mint) FILTER (WHERE a.idade_s <= 600) AS retrato_antes_600s,
  count(d.mint) AS com_retrato_depois,
  count(d.mint) FILTER (WHERE d.atraso_s <= 60) AS depois_ate_60s,
  count(d.mint) FILTER (WHERE d.atraso_s <= 120) AS depois_ate_120s,
  count(d.mint) FILTER (WHERE d.atraso_s <= 60 AND d.bundled_share <= 0.20) AS d60_bundle20,
  count(d.mint) FILTER (WHERE d.atraso_s <= 120 AND d.bundled_share <= 0.20) AS d120_bundle20,
  count(d.mint) FILTER (WHERE d.atraso_s <= 120 AND d.bundled_share <= 0.20 AND d.top10_share <= 0.25) AS d120_b20_t25,
  count(d.mint) FILTER (WHERE d.atraso_s <= 120 AND d.bundled_share <= 0.20 AND d.top10_share <= 0.25
                          AND p.curve_progress_pct <= 0.50) AS d120_b20_t25_prog50,
  round(avg(d.atraso_s)) AS atraso_medio_s,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY d.atraso_s)::numeric) AS atraso_p50_s
FROM r41f p LEFT JOIN antes a ON a.mint=p.mint LEFT JOIN depois d ON d.mint=p.mint;

-- (c) NOMES da porta com o retrato que chega ate 120 s depois: quem o deploy admitiria
WITH depois AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.bundled_share, r.top10_share,
    extract(epoch FROM (r.observed_at - p.as_of))::int AS atraso_s
  FROM r41f p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at > p.as_of
  ORDER BY p.mint, r.observed_at
), cs AS (
  SELECT DISTINCT ON (p.mint) p.mint, f.creator_sold
  FROM r41f p JOIN meme_features_1m f ON f.mint=p.mint AND f.end_time <= p.as_of
  ORDER BY p.mint, f.end_time DESC
), pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c
          JOIN r41f p ON p.mint=c.mint GROUP BY 1),
ag AS (SELECT DISTINCT ON (c.mint) c.mint, c.real_sol_reserves AS rsol_agora, c.complete
       FROM meme_curve_snapshots c JOIN r41f p ON p.mint=c.mint ORDER BY c.mint, c.observed_at DESC)
SELECT to_char(p.as_of AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt, p.symbol,
  left(p.mint,6) AS mint6, round(p.curve_progress_pct*100,1) AS prog, p.holders,
  p.unique_buyers_60s AS compr, p.snipers, round(d.bundled_share*100,1) AS bundle,
  round(d.top10_share*100,1) AS top10, d.atraso_s, cs.creator_sold,
  (p.curve_progress_pct <= 0.50 AND d.bundled_share <= 0.20 AND d.top10_share <= 0.25) AS admite_apos_espera,
  round(pk.rsol_pico,3) AS rsol_pico, round(ag.rsol_agora,3) AS rsol_agora,
  round(100*(ag.rsol_agora/nullif(pk.rsol_pico,0)-1),1) AS delta_pct, ag.complete AS encheu
FROM r41f p JOIN depois d ON d.mint=p.mint LEFT JOIN cs ON cs.mint=p.mint
  LEFT JOIN pk ON pk.mint=p.mint LEFT JOIN ag ON ag.mint=p.mint
WHERE d.atraso_s <= 120 ORDER BY p.as_of;

-- (d) cobertura do RiskReader na hora congelada
SELECT count(DISTINCT mint) AS mints, count(*) AS leituras,
  round(avg(bundled_share),4) AS bundle_medio,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY bundled_share)::numeric,4) AS bundle_mediano,
  count(*) FILTER (WHERE bundled_share <= 0.20) AS ate20,
  count(*) FILTER (WHERE bundled_share <= 0.35) AS ate35
FROM meme_risk_snapshots
WHERE observed_at >= timestamptz $$2026-09-16 20:30-03$$ AND observed_at < timestamptz $$2026-09-16 21:30-03$$;
