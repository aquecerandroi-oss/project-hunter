-- R23 16/09 16h50 BRT — a porta EM VIGOR (meme_rule_sets operator/5: min_holders 20,
-- min_unique_buyers 10, max_sells_to_buys 0,6, min_snipers 21, max_snipers 1000,
-- progresso 5-50 % (coluna e FRACAO 0-1), dev <= 10 %, fluxo positivo, participacao
-- <= 1 % com 0,05 SOL (=> curve_volume_60s_sol >= 5), SEM exigir "subindo", pedigree)
-- replicada sobre meme_features_15s da ultima hora, e quantas dessas o EXECUTOR
-- admitiria (top-10 <= 25 %, creator_sold conhecido, retrato de risco
-- (meme_risk_snapshots) com <= 600 s de idade na hora da foto).
-- Rodado na VPS: docker exec -i <pg> psql -U hunter -d hunter -F "|" -At < este-arquivo
SET statement_timeout = 240000;

-- base comum: primeira foto de 15 s de cada moeda que passa os criterios do rule set,
-- pedigree calculado so sobre as candidatas (barato).
CREATE TEMP VIEW r23_bruto AS
  SELECT DISTINCT ON (f.mint) f.mint, f.as_of, t.symbol, f.holders, f.unique_buyers_60s,
    f.snipers, f.curve_progress_pct, f.net_sol_flow_60s, f.curve_volume_60s_sol,
    f.dev_share, f.buys_60s, f.sells_60s, t.creator, f.age_s, t.created_at
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300
    AND t.mayhem_mode IS NULL
    AND (t.completed_at IS NULL OR t.completed_at > f.as_of)
    AND (t.migrated_at IS NULL OR t.migrated_at > f.as_of)
    AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10
    AND f.snipers IS NOT NULL AND f.snipers >= 21
    AND f.dev_share IS NOT NULL AND f.dev_share <= 0.10
    AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND f.curve_volume_60s_sol IS NOT NULL AND f.curve_volume_60s_sol >= 5
    AND t.creator IS NOT NULL AND t.created_at IS NOT NULL
  ORDER BY f.mint, f.as_of;

CREATE TEMP VIEW r23_passa AS
  SELECT b.* FROM r23_bruto b
  WHERE (SELECT count(*) FROM meme_tokens o WHERE o.creator=b.creator AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol=b.symbol AND o.mint<>b.mint
           AND o.created_at IS NOT NULL AND o.created_at <= b.created_at
           AND o.created_at > b.created_at - interval '24 hours') <= 2;

-- (a) vazao: moedas distintas que passam a porta na ultima hora e por minuto
SELECT count(*) AS moedas_na_hora, round(count(*)::numeric/60,2) AS por_minuto,
       count(DISTINCT date_trunc('minute', as_of)) AS minutos_com_pelo_menos_uma,
       (SELECT count(*) FROM r23_bruto) AS antes_do_pedigree
FROM r23_passa;

-- (b) nominais + insumos de admissao
WITH risco AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.top10_share, r.observed_at,
    extract(epoch FROM (p.as_of - r.observed_at))::int AS idade_retrato_s
  FROM r23_passa p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at <= p.as_of
  ORDER BY p.mint, r.observed_at DESC
), cs AS (
  SELECT DISTINCT ON (p.mint) p.mint, f.creator_sold, f.top10_share AS top10_1m
  FROM r23_passa p JOIN meme_features_1m f ON f.mint=p.mint AND f.end_time <= p.as_of
  ORDER BY p.mint, f.end_time DESC
)
SELECT to_char(p.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
  p.symbol, left(p.mint,6), p.age_s, round(p.curve_progress_pct*100,1) AS prog,
  p.holders, p.unique_buyers_60s, p.buys_60s, p.sells_60s,
  round(p.net_sol_flow_60s,2) AS fluxo, round(p.curve_volume_60s_sol,1) AS vol60s,
  p.snipers, round(r.top10_share*100,1) AS top10_retrato, r.idade_retrato_s,
  round(cs.top10_1m*100,1) AS top10_1m, cs.creator_sold,
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=p.creator
     AND t2.created_at >= now() - make_interval(days => 7)) AS criador_7d,
  (SELECT completed_at IS NOT NULL FROM meme_tokens t3 WHERE t3.mint=p.mint) AS encheu
FROM r23_passa p LEFT JOIN risco r ON r.mint=p.mint LEFT JOIN cs ON cs.mint=p.mint
ORDER BY p.as_of;

-- (c) funil de admissao do executor sobre as que passam a porta
WITH risco AS (
  SELECT DISTINCT ON (p.mint) p.mint, r.top10_share,
    extract(epoch FROM (p.as_of - r.observed_at))::int AS idade_retrato_s
  FROM r23_passa p JOIN meme_risk_snapshots r ON r.mint=p.mint AND r.observed_at <= p.as_of
  ORDER BY p.mint, r.observed_at DESC
), cs AS (
  SELECT DISTINCT ON (p.mint) p.mint, f.creator_sold
  FROM r23_passa p JOIN meme_features_1m f ON f.mint=p.mint AND f.end_time <= p.as_of
  ORDER BY p.mint, f.end_time DESC
)
SELECT count(*) AS passam_a_porta,
  count(*) FILTER (WHERE r.idade_retrato_s IS NOT NULL AND r.idade_retrato_s <= 600) AS retrato_ate_600s,
  count(*) FILTER (WHERE r.top10_share IS NOT NULL) AS com_top10,
  count(*) FILTER (WHERE r.top10_share IS NOT NULL AND r.top10_share <= 0.25) AS top10_ate_25,
  count(*) FILTER (WHERE cs.creator_sold IS NOT NULL) AS creator_sold_conhecido,
  count(*) FILTER (WHERE r.idade_retrato_s IS NOT NULL AND r.idade_retrato_s <= 600
                    AND r.top10_share IS NOT NULL AND r.top10_share <= 0.25
                    AND cs.creator_sold IS NOT NULL AND cs.creator_sold = false) AS admitiria
FROM r23_passa p LEFT JOIN risco r ON r.mint=p.mint LEFT JOIN cs ON cs.mint=p.mint;

-- (d) custo de cada criterio isolado na ultima hora (cumulativo, moedas distintas)
WITH j AS (
  SELECT f.* FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= now() - make_interval(mins => 60) AND f.age_s BETWEEN 30 AND 300
    AND t.mayhem_mode IS NULL
)
SELECT count(DISTINCT mint) AS idade_30_300,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50) AS prog_5_50,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50
        AND tape_reason IS NULL) AS com_fita,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50
        AND tape_reason IS NULL AND net_sol_flow_60s > 0) AS fluxo_pos,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50
        AND tape_reason IS NULL AND net_sol_flow_60s > 0 AND holders >= 20) AS holders20,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50
        AND tape_reason IS NULL AND net_sol_flow_60s > 0 AND holders >= 20
        AND unique_buyers_60s >= 10) AS compr10,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50
        AND tape_reason IS NULL AND net_sol_flow_60s > 0 AND holders >= 20
        AND unique_buyers_60s >= 10 AND buys_60s > 0
        AND sells_60s::numeric/buys_60s <= 0.6) AS razao06,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50
        AND tape_reason IS NULL AND net_sol_flow_60s > 0 AND holders >= 20
        AND unique_buyers_60s >= 10 AND buys_60s > 0
        AND sells_60s::numeric/buys_60s <= 0.6 AND snipers >= 21) AS snipers21,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50
        AND tape_reason IS NULL AND net_sol_flow_60s > 0 AND holders >= 20
        AND unique_buyers_60s >= 10 AND buys_60s > 0
        AND sells_60s::numeric/buys_60s <= 0.6 AND snipers >= 21
        AND dev_share IS NOT NULL AND dev_share <= 0.10) AS mais_dev,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50
        AND tape_reason IS NULL AND net_sol_flow_60s > 0 AND holders >= 20
        AND unique_buyers_60s >= 10 AND buys_60s > 0
        AND sells_60s::numeric/buys_60s <= 0.6 AND snipers >= 21
        AND dev_share IS NOT NULL AND dev_share <= 0.10
        AND curve_volume_60s_sol >= 5) AS mais_participacao
FROM j;
