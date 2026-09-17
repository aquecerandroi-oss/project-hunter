-- R46 q05: piso de snipers (o que ele cortou na janela), estado atual das vivas, veredito das graduadas
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
-- (a) moedas que passaram TUDO menos o piso de snipers (snipers < 21 ou NULL), melhor leitura, desfecho pela cadeia
WITH p AS (
  SELECT f.mint, f.as_of, f.age_s, f.curve_progress_pct, f.holders, f.unique_buyers_60s, f.buys_60s, f.sells_60s, f.snipers, f.snipers_reason, f.dev_share, f.net_sol_flow_60s
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 19:25-03' AND f.as_of < timestamptz '2026-09-16 22:25-03'
    AND f.age_s BETWEEN 30 AND 300 AND t.mayhem_mode IS NULL AND (t.completed_at IS NULL OR t.completed_at > f.as_of)
    AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10 AND f.dev_share IS NOT NULL AND f.dev_share <= 0.10
    AND f.buys_60s > 0 AND f.sells_60s::numeric/f.buys_60s <= 0.6
    AND (f.snipers IS NULL OR f.snipers < 21)
    AND NOT EXISTS (SELECT 1 FROM meme_features_15s g WHERE g.mint=f.mint AND g.as_of >= timestamptz '2026-09-16 19:25-03' AND g.as_of < timestamptz '2026-09-16 22:25-03'
                    AND g.age_s BETWEEN 30 AND 300 AND g.curve_progress_pct BETWEEN 0.05 AND 0.50 AND g.tape_reason IS NULL AND g.net_sol_flow_60s > 0
                    AND g.holders >= 20 AND g.unique_buyers_60s >= 10 AND g.dev_share <= 0.10 AND g.buys_60s > 0 AND g.sells_60s::numeric/g.buys_60s <= 0.6 AND g.snipers BETWEEN 21 AND 1000)
), best AS (SELECT DISTINCT ON (mint) * FROM p ORDER BY mint, unique_buyers_60s DESC, holders DESC),
pk AS (SELECT c.mint, max(c.real_sol_reserves) AS rsol_pico FROM meme_curve_snapshots c JOIN best b ON b.mint=c.mint WHERE c.observed_at >= timestamptz '2026-09-16 19:00-03' GROUP BY 1),
ag AS (SELECT DISTINCT ON (c.mint) c.mint, c.observed_at, c.real_sol_reserves AS rsol_agora, c.complete FROM meme_curve_snapshots c JOIN best b ON b.mint=c.mint WHERE c.observed_at >= timestamptz '2026-09-16 19:00-03' ORDER BY c.mint, c.observed_at DESC),
cr AS (SELECT b.mint, (SELECT count(*) FROM meme_tokens o WHERE o.creator=k.creator AND o.mint<>b.mint AND o.created_at > k.created_at - interval '7 days' AND o.created_at <= k.created_at) AS criador_7d FROM best b JOIN meme_tokens k ON k.mint=b.mint)
SELECT 'so_snipers' AS q, to_char(b.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt, coalesce(k.symbol,'?') AS symbol, left(b.mint,8) AS mint8, b.age_s,
  round(b.curve_progress_pct*100,1) AS prog, b.holders, b.unique_buyers_60s AS compr, b.buys_60s, b.sells_60s, coalesce(b.snipers::text, coalesce(b.snipers_reason,'null')) AS snipers,
  round(b.dev_share*100,2) AS dev, round(b.net_sol_flow_60s,2) AS fluxo, round(pk.rsol_pico,3) AS rsol_pico, round(ag.rsol_agora,3) AS rsol_ult,
  to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS rsol_brt, ag.complete, coalesce(to_char(k.completed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS completou, cr.criador_7d
FROM best b JOIN meme_tokens k ON k.mint=b.mint LEFT JOIN pk ON pk.mint=b.mint LEFT JOIN ag ON ag.mint=b.mint LEFT JOIN cr ON cr.mint=b.mint
ORDER BY b.unique_buyers_60s DESC;
-- (b) estado atual (ultima foto da cadeia, ate agora) das que interessam
WITH m AS (SELECT unnest(ARRAY['4TcftzQvXTwSEfsuWL75LLNQvdennvRsjmCh3VS5pump','GFakEBdgdKDJhsCKauSkKVjHYPqHDBEY7SgJZEJDpump']) AS mint
           UNION SELECT mint FROM meme_tokens WHERE mint LIKE 'ENBTWXHt%' OR mint LIKE 'C8ykWko6%' OR mint LIKE '3U3Y793Z%' OR mint LIKE 'H91rJ7Dc%' OR mint LIKE 'Fyko94e1%' OR mint LIKE 'FMMCvUEN%')
SELECT 'agora' AS q, coalesce(t.symbol,'?') AS symbol, left(m.mint,8) AS mint8,
  (SELECT to_char(c.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS')||' rsol='||round(c.real_sol_reserves,3)||' complete='||c.complete FROM meme_curve_snapshots c WHERE c.mint=m.mint AND c.observed_at >= timestamptz '2026-09-16 19:00-03' ORDER BY c.observed_at DESC LIMIT 1) AS ultima_foto,
  (SELECT count(*) FROM meme_curve_snapshots c WHERE c.mint=m.mint AND c.observed_at >= timestamptz '2026-09-16 19:00-03') AS fotos,
  (SELECT round(max(c.real_sol_reserves),3) FROM meme_curve_snapshots c WHERE c.mint=m.mint AND c.observed_at >= timestamptz '2026-09-16 19:00-03') AS rsol_pico,
  (SELECT to_char(f.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI')||' age='||f.age_minutes||' prog='||round(coalesce(f.curve_progress_pct,0)*100,1)||' holders='||coalesce(f.holders::text,'-')||' compr='||coalesce(f.unique_buyers::text,'-')||' top10='||coalesce(round(f.top10_share*100,1)::text,'-')||' creator_sold='||coalesce(f.creator_sold::text,'-')||' cns='||coalesce(f.creator_net_seller::text,'-') FROM meme_features_1m f WHERE f.mint=m.mint ORDER BY f.end_time DESC LIMIT 1) AS ult_1m,
  coalesce(to_char(t.completed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS completou
FROM m JOIN meme_tokens t ON t.mint=m.mint;
-- (c) trajetoria da LINK e da DOWNIE a cada ~2 min (cadeia)
SELECT 'traj' AS q, coalesce(t.symbol,'?') AS symbol, to_char(date_trunc('minute', c.observed_at) AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS min_brt,
  round(min(c.real_sol_reserves),2) AS rsol_min, round(max(c.real_sol_reserves),2) AS rsol_max, round(max(c.virtual_sol_reserves - c.real_sol_reserves),1) AS invariante, bool_or(c.complete) AS complete
FROM meme_curve_snapshots c JOIN meme_tokens t ON t.mint=c.mint
WHERE (c.mint LIKE '4TcftzQv%' OR c.mint LIKE 'ENBTWXHt%') AND c.observed_at >= timestamptz '2026-09-16 21:40-03'
GROUP BY 1,2,3 ORDER BY 2,3;
-- (d) veredito das graduadas que tiveram leitura na janela do radar
WITH g AS (
  SELECT t.mint FROM meme_tokens t WHERE least(t.completed_at, t.graduated_board_seen_at) >= timestamptz '2026-09-16 19:25-03' AND least(t.completed_at, t.graduated_board_seen_at) < timestamptz '2026-09-16 22:25-03'
), bj AS (
  SELECT DISTINCT ON (g.mint) g.mint,
    CASE WHEN f.tape_reason IS NOT NULL THEN 'sem_fita' WHEN f.net_sol_flow_60s<=0 THEN 'fluxo' WHEN f.holders<20 THEN 'holders' WHEN f.unique_buyers_60s<10 THEN 'compradores'
         WHEN f.buys_60s=0 OR f.sells_60s::numeric/f.buys_60s>0.6 THEN 'razao' WHEN f.snipers IS NULL THEN 'snipers_null' WHEN f.snipers<21 THEN 'snipers<21' WHEN f.snipers>1000 THEN 'snipers>1000'
         WHEN f.dev_share IS NULL THEN 'dev_null' WHEN f.dev_share>0.10 THEN 'dev>10' ELSE 'passa' END AS veredito
  FROM g JOIN meme_features_15s f ON f.mint=g.mint AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
  ORDER BY g.mint, f.unique_buyers_60s DESC NULLS LAST, f.holders DESC NULLS LAST
)
SELECT 'grad_veredito' AS q, coalesce(bj.veredito,'sem_leitura_na_janela') AS veredito, count(*) FROM g LEFT JOIN bj ON bj.mint=g.mint GROUP BY 2 ORDER BY 3 DESC;
-- (e) graduadas: created_at real (criada > 60 s antes de graduar) x instantaneas
SELECT 'grad_idade' AS q,
  count(*) FILTER (WHERE least(t.completed_at, t.graduated_board_seen_at) - t.created_at < interval '60 seconds') AS instantaneas_lt60s,
  count(*) FILTER (WHERE least(t.completed_at, t.graduated_board_seen_at) - t.created_at >= interval '60 seconds' AND least(t.completed_at, t.graduated_board_seen_at) - t.created_at < interval '5 minutes') AS de_1_a_5min,
  count(*) FILTER (WHERE least(t.completed_at, t.graduated_board_seen_at) - t.created_at >= interval '5 minutes' AND least(t.completed_at, t.graduated_board_seen_at) - t.created_at < interval '30 minutes') AS de_5_a_30min,
  count(*) FILTER (WHERE least(t.completed_at, t.graduated_board_seen_at) - t.created_at >= interval '30 minutes') AS acima_30min,
  count(*) FILTER (WHERE t.created_at IS NULL) AS sem_created
FROM meme_tokens t WHERE least(t.completed_at, t.graduated_board_seen_at) >= timestamptz '2026-09-16 19:25-03' AND least(t.completed_at, t.graduated_board_seen_at) < timestamptz '2026-09-16 22:25-03';
-- (f) colunas de meme_trades
SELECT 'cols' AS q, string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='meme_trades';
