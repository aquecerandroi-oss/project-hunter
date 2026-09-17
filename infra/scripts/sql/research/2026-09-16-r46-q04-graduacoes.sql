-- R46 q04: graduacoes na janela [19:25, 22:25) BRT e o que o radar tinha delas
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
WITH g AS (
  SELECT t.mint, t.symbol, t.name, t.creator, t.created_at, t.completed_at, t.graduated_board_seen_at, t.mayhem_mode,
    least(t.completed_at, t.graduated_board_seen_at) AS grad_at
  FROM meme_tokens t
  WHERE least(t.completed_at, t.graduated_board_seen_at) >= timestamptz '2026-09-16 19:25-03'
    AND least(t.completed_at, t.graduated_board_seen_at) < timestamptz '2026-09-16 22:25-03'
)
SELECT 'grad_total' AS q, count(*) AS graduadas, count(*) FILTER (WHERE created_at IS NOT NULL) AS com_created,
  count(*) FILTER (WHERE mayhem_mode IS NOT NULL) AS mayhem,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_features_15s f WHERE f.mint=g.mint)) AS com_serie_15s,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_features_1m f WHERE f.mint=g.mint AND f.end_time > timestamptz '2026-09-16 15:00-03')) AS com_serie_1m,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_proposals p WHERE p.mint=g.mint)) AS com_proposta,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (grad_at - created_at))/60)::numeric,1) AS idade_mediana_min
FROM g;
WITH g AS (
  SELECT t.mint, t.symbol, t.name, t.creator, t.created_at, t.completed_at, t.graduated_board_seen_at, t.mayhem_mode,
    least(t.completed_at, t.graduated_board_seen_at) AS grad_at
  FROM meme_tokens t
  WHERE least(t.completed_at, t.graduated_board_seen_at) >= timestamptz '2026-09-16 19:25-03'
    AND least(t.completed_at, t.graduated_board_seen_at) < timestamptz '2026-09-16 22:25-03'
), s15 AS (
  SELECT g.mint, count(*) AS n15, min(f.as_of) AS first15, max(f.as_of) AS last15, max(f.age_s) AS max_age,
    max(f.holders) AS max_holders, max(f.unique_buyers_60s) AS max_compr, max(f.snipers) AS max_snipers, min(f.snipers) AS min_snipers,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6 AND f.snipers BETWEEN 21 AND 1000 AND f.dev_share<=0.10) AS passou_porta,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s>0 AND f.holders>=20 AND f.unique_buyers_60s>=10 AND f.buys_60s>0 AND f.sells_60s::numeric/f.buys_60s<=0.6 AND f.dev_share<=0.10) AS passou_sem_snipers,
    bool_or(f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50) AS na_janela,
    count(*) FILTER (WHERE f.tape_reason IS NULL) AS n_com_fita,
    count(*) FILTER (WHERE f.snipers IS NULL) AS n_snipers_null,
    count(*) FILTER (WHERE f.dev_share IS NULL) AS n_dev_null
  FROM g JOIN meme_features_15s f ON f.mint=g.mint GROUP BY 1
), s1 AS (
  SELECT g.mint, count(*) AS n1m, max(f.holders) AS max_holders_1m, max(f.unique_buyers) AS max_compr_1m
  FROM g JOIN meme_features_1m f ON f.mint=g.mint AND f.end_time > timestamptz '2026-09-16 15:00-03' GROUP BY 1
), bestj AS (
  SELECT DISTINCT ON (g.mint) g.mint, f.as_of, f.age_s, f.curve_progress_pct, f.holders, f.unique_buyers_60s, f.buys_60s, f.sells_60s, f.snipers, f.dev_share, f.net_sol_flow_60s, f.tape_reason,
    CASE WHEN f.tape_reason IS NOT NULL THEN 'sem_fita' WHEN f.net_sol_flow_60s<=0 THEN 'fluxo' WHEN f.holders<20 THEN 'holders' WHEN f.unique_buyers_60s<10 THEN 'compradores'
         WHEN f.buys_60s=0 OR f.sells_60s::numeric/f.buys_60s>0.6 THEN 'razao' WHEN f.snipers IS NULL THEN 'snipers_null' WHEN f.snipers<21 THEN 'snipers<21' WHEN f.snipers>1000 THEN 'snipers>1000'
         WHEN f.dev_share IS NULL THEN 'dev_null' WHEN f.dev_share>0.10 THEN 'dev>10' ELSE 'passa' END AS veredito
  FROM g JOIN meme_features_15s f ON f.mint=g.mint AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
  ORDER BY g.mint, f.unique_buyers_60s DESC NULLS LAST, f.holders DESC NULLS LAST
), pr AS (
  SELECT g.mint, count(p.id) AS propostas, string_agg(DISTINCT rs.name||'/'||rs.version||':'||p.status||':'||coalesce(p.refusal,'-'), ' ; ') AS props,
    string_agg(DISTINCT coalesce(o.status||':'||coalesce(o.reason,'-'),''), ',') AS ordens
  FROM g LEFT JOIN meme_proposals p ON p.mint=g.mint LEFT JOIN meme_rule_sets rs ON rs.id=p.rule_set_id LEFT JOIN meme_live_orders o ON o.proposal_id=p.id GROUP BY 1
), cr AS (
  SELECT g.mint, (SELECT count(*) FROM meme_tokens o WHERE o.creator=g.creator AND o.mint<>g.mint AND o.created_at > g.created_at - interval '7 days' AND o.created_at <= g.created_at) AS criador_7d FROM g
)
SELECT 'grad' AS q, to_char(g.grad_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS grad_brt, coalesce(g.symbol,'?') AS symbol, left(g.mint,8) AS mint8,
  coalesce(to_char(g.created_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS criada_brt,
  round(extract(epoch FROM (g.grad_at - g.created_at))/60,1) AS idade_min,
  CASE WHEN g.completed_at IS NOT NULL AND g.graduated_board_seen_at IS NOT NULL THEN 'ambos' WHEN g.completed_at IS NOT NULL THEN 'completed' ELSE 'board' END AS sinal,
  coalesce(g.mayhem_mode,'-') AS mayhem,
  coalesce(s15.n15,0) AS n15, s15.max_age, s15.max_holders, s15.max_compr, s15.min_snipers, s15.max_snipers, s15.n_com_fita, s15.n_snipers_null,
  coalesce(s15.na_janela,false) AS na_janela, coalesce(s15.passou_porta,false) AS passou_porta, coalesce(s15.passou_sem_snipers,false) AS passou_sem_snipers,
  coalesce(s1.n1m,0) AS n1m, s1.max_holders_1m, s1.max_compr_1m,
  to_char(bj.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS melhor_brt, round(bj.curve_progress_pct*100,1) AS prog, bj.holders, bj.unique_buyers_60s AS compr, bj.buys_60s, bj.sells_60s, bj.snipers, round(bj.dev_share*100,1) AS dev, round(bj.net_sol_flow_60s,2) AS fluxo, coalesce(bj.veredito,'sem_leitura_na_janela') AS veredito,
  cr.criador_7d, coalesce(pr.propostas,0) AS propostas, coalesce(pr.props,'-') AS props, coalesce(nullif(pr.ordens,''),'-') AS ordens
FROM g LEFT JOIN s15 ON s15.mint=g.mint LEFT JOIN s1 ON s1.mint=g.mint LEFT JOIN bestj bj ON bj.mint=g.mint LEFT JOIN pr ON pr.mint=g.mint LEFT JOIN cr ON cr.mint=g.mint
ORDER BY g.grad_at;
