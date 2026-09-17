-- R46 q01: top 10 da janela congelada [19:25, 22:25) BRT pela porta operator/5 sobre meme_features_15s
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
CREATE TEMP TABLE r46_pass AS
  SELECT f.mint, f.as_of, f.age_s, f.curve_progress_pct, f.holders, f.holders_prev, f.unique_buyers_60s,
         f.buys_60s, f.sells_60s, f.snipers, f.dev_share, f.net_sol_flow_60s, f.curve_volume_60s_sol,
         f.creator_net_seller, f.creator_net_seller_reason
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 19:25-03' AND f.as_of < timestamptz '2026-09-16 22:25-03'
    AND f.age_s BETWEEN 30 AND 300
    AND t.mayhem_mode IS NULL
    AND (t.completed_at IS NULL OR t.completed_at > f.as_of)
    AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10
    AND f.snipers BETWEEN 21 AND 1000
    AND f.dev_share IS NOT NULL AND f.dev_share <= 0.10
    AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND coalesce(f.curve_volume_60s_sol,0) > 0;
-- (a) funil de moedas distintas na janela
WITH u AS (
  SELECT f.mint, bool_or(f.age_s BETWEEN 30 AND 300) AS idade,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50) AS prog,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0) AS fluxo,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20) AS h20,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10) AS b10,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6) AS r06,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6 AND f.snipers BETWEEN 21 AND 1000) AS s21,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6 AND f.snipers BETWEEN 21 AND 1000 AND f.dev_share<=0.10) AS dev
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz '2026-09-16 19:25-03' AND f.as_of < timestamptz '2026-09-16 22:25-03'
  GROUP BY 1)
SELECT 'funil' AS q, count(*) FILTER (WHERE idade) AS idade, count(*) FILTER (WHERE prog) AS prog_5_50,
  count(*) FILTER (WHERE fluxo) AS fluxo_pos, count(*) FILTER (WHERE h20) AS holders20,
  count(*) FILTER (WHERE b10) AS compr10, count(*) FILTER (WHERE r06) AS razao06,
  count(*) FILTER (WHERE s21) AS snipers21, count(*) FILTER (WHERE dev) AS dev10 FROM u;
-- (b) top 10 por demanda (max compradores unicos numa leitura que passou), com trajetoria
WITH agg AS (
  SELECT mint, count(*) AS n_pass, min(as_of) AS first_pass, max(as_of) AS last_pass,
    max(unique_buyers_60s) AS max_compr, max(holders) AS max_holders
  FROM r46_pass GROUP BY 1
), best AS (
  SELECT DISTINCT ON (p.mint) p.* FROM r46_pass p ORDER BY p.mint, p.unique_buyers_60s DESC, p.holders DESC
), top AS (
  SELECT a.*, b.as_of AS best_at, b.age_s, b.curve_progress_pct AS prog_best, b.holders AS holders_best,
    b.unique_buyers_60s AS compr_best, b.buys_60s, b.sells_60s, b.snipers, b.dev_share, b.net_sol_flow_60s,
    b.curve_volume_60s_sol, b.creator_net_seller, b.creator_net_seller_reason
  FROM agg a JOIN best b ON b.mint=a.mint ORDER BY a.max_compr DESC, a.max_holders DESC LIMIT 10
), l1 AS (
  SELECT DISTINCT ON (t.mint) t.mint, f.end_time, f.curve_progress_pct, f.holders, f.unique_buyers, f.buy_sell_ratio, f.top10_share, f.creator_sold, f.age_minutes
  FROM top t JOIN meme_features_1m f ON f.mint=t.mint AND f.end_time < timestamptz '2026-09-16 22:25-03'
  ORDER BY t.mint, f.end_time DESC
), l10 AS (
  SELECT DISTINCT ON (t.mint) t.mint, f.end_time, f.curve_progress_pct, f.holders, f.unique_buyers
  FROM top t JOIN l1 ON l1.mint=t.mint JOIN meme_features_1m f ON f.mint=t.mint AND f.end_time <= l1.end_time - interval '10 minutes'
  ORDER BY t.mint, f.end_time DESC
), l15 AS (
  SELECT DISTINCT ON (t.mint) t.mint, f.as_of, f.curve_progress_pct, f.holders, f.unique_buyers_60s, f.age_s
  FROM top t JOIN meme_features_15s f ON f.mint=t.mint AND f.as_of < timestamptz '2026-09-16 22:25-03'
  ORDER BY t.mint, f.as_of DESC
), pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c JOIN top t ON t.mint=c.mint
          WHERE c.observed_at >= timestamptz '2026-09-16 19:00-03' GROUP BY 1),
ag AS (SELECT DISTINCT ON (c.mint) c.mint, c.observed_at, c.real_sol_reserves AS rsol_agora, c.complete
       FROM meme_curve_snapshots c JOIN top t ON t.mint=c.mint WHERE c.observed_at >= timestamptz '2026-09-16 19:00-03'
       ORDER BY c.mint, c.observed_at DESC),
cr AS (SELECT t.mint, (SELECT count(*) FROM meme_tokens o WHERE o.creator=k.creator AND o.mint<>t.mint AND o.created_at > k.created_at - interval '7 days' AND o.created_at <= k.created_at) AS criador_7d
       FROM top t JOIN meme_tokens k ON k.mint=t.mint),
pr AS (SELECT t.mint, count(p.id) AS propostas, string_agg(DISTINCT rs.name||'/'||rs.version, ',') AS rule_sets,
              string_agg(DISTINCT coalesce(o.status||':'||coalesce(o.reason,'-'),'sem_ordem'), ',') AS ordens
       FROM top t LEFT JOIN meme_proposals p ON p.mint=t.mint AND p.proposed_at >= timestamptz '2026-09-16 19:25-03'
       LEFT JOIN meme_rule_sets rs ON rs.id=p.rule_set_id LEFT JOIN meme_live_orders o ON o.proposal_id=p.id GROUP BY 1)
SELECT 'top10' AS q, k.symbol, k.name, left(t.mint,8) AS mint8, t.mint,
  to_char(k.created_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS criada_brt,
  coalesce(to_char(k.completed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS completou_brt,
  t.n_pass, to_char(t.first_pass AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS primeira_pass,
  to_char(t.last_pass AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS ultima_pass,
  to_char(t.best_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS melhor_brt, t.age_s,
  round(t.prog_best*100,1) AS prog_melhor, t.holders_best, t.compr_best, t.buys_60s, t.sells_60s, t.snipers,
  round(t.dev_share*100,2) AS dev_pct, round(t.net_sol_flow_60s,2) AS fluxo, round(t.curve_volume_60s_sol,1) AS vol60,
  coalesce(t.creator_net_seller::text, coalesce(t.creator_net_seller_reason,'null')) AS cns,
  to_char(l15.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS ult15_brt, l15.age_s AS ult15_age,
  round(l15.curve_progress_pct*100,1) AS ult15_prog, l15.holders AS ult15_holders, l15.unique_buyers_60s AS ult15_compr,
  to_char(l1.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ult1m_brt, l1.age_minutes,
  round(l1.curve_progress_pct*100,1) AS ult1m_prog, l1.holders AS ult1m_holders, l1.unique_buyers AS ult1m_compr,
  round(l1.top10_share*100,1) AS top10, l1.creator_sold,
  to_char(l10.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS m10_brt, round(l10.curve_progress_pct*100,1) AS m10_prog,
  l10.holders AS m10_holders, l10.unique_buyers AS m10_compr,
  round(pk.rsol_pico,3) AS rsol_pico, round(ag.rsol_agora,3) AS rsol_agora,
  to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS rsol_brt, ag.complete,
  cr.criador_7d, pr.propostas, coalesce(pr.rule_sets,'-') AS rule_sets, coalesce(pr.ordens,'-') AS ordens
FROM top t JOIN meme_tokens k ON k.mint=t.mint LEFT JOIN l1 ON l1.mint=t.mint LEFT JOIN l10 ON l10.mint=t.mint
  LEFT JOIN l15 ON l15.mint=t.mint LEFT JOIN pk ON pk.mint=t.mint LEFT JOIN ag ON ag.mint=t.mint
  LEFT JOIN cr ON cr.mint=t.mint LEFT JOIN pr ON pr.mint=t.mint
ORDER BY t.max_compr DESC, t.max_holders DESC;
-- (c) quantas passaram ao todo e quantas tiveram proposta
SELECT 'pass_total' AS q, count(DISTINCT p.mint) AS moedas_passaram, count(*) AS leituras,
  count(DISTINCT p.mint) FILTER (WHERE EXISTS (SELECT 1 FROM meme_proposals x WHERE x.mint=p.mint AND x.proposed_at >= timestamptz '2026-09-16 19:25-03')) AS com_proposta
FROM r46_pass p;
