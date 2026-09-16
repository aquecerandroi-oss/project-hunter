-- R26 / Q05 — (a) taxa-base do bundled_share na PRIMEIRA leitura do dia, para
-- estimar o que o retrato traria nos 4 mints que hoje nunca foram lidos;
-- (b) truncamento da serie de 1 min: a saida 'tempo_30m' do Q04 e, nas moedas
-- de vida curta, a ULTIMA barra existente, nao a barra dos 30 min.
\pset pager off
WITH primeira AS (
  SELECT DISTINCT ON (mint) mint, observed_at, bundled_share
  FROM meme_risk_snapshots
  WHERE observed_at >= date_trunc('day', now() AT TIME ZONE 'America/Sao_Paulo')
          AT TIME ZONE 'America/Sao_Paulo'
    AND bundled_share IS NOT NULL
  ORDER BY mint, observed_at
)
SELECT count(*) AS mints_lidos_hoje,
       count(*) FILTER (WHERE bundled_share <= 0.20) AS ate_20pct,
       round(100.0 * count(*) FILTER (WHERE bundled_share <= 0.20) / count(*), 1) AS pct_ate_20,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY bundled_share)::numeric, 4) AS mediana,
       round(avg(bundled_share), 4) AS media
FROM primeira;

-- (b) quantas barras de 1 min existem depois da decisao e ate onde a serie vai
SELECT left(o.mint,6) AS mint, o.symbol,
       to_char(o.t0 AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS decisao_brt,
       round(extract(epoch FROM (SELECT max(f.end_time) FROM meme_features_1m f
                                 WHERE f.mint = o.mint) - o.t0) / 60.0, 1) AS serie_ate_min,
       (SELECT count(*) FROM meme_features_1m f WHERE f.mint = o.mint
          AND f.end_time > o.t0 AND f.end_time <= o.t0 + interval '30 minutes') AS barras_30m,
       to_char(t.completed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS graduou_brt
FROM (SELECT DISTINCT ON (o.admission->>'mint') o.admission->>'mint' AS mint,
             o.received_at AS t0, t.symbol
      FROM meme_live_orders o LEFT JOIN meme_tokens t ON t.mint = o.admission->>'mint'
      ORDER BY o.admission->>'mint', o.received_at) o
JOIN meme_tokens t ON t.mint = o.mint
ORDER BY o.t0;
