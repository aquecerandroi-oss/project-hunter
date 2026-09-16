-- R27 q02 — (a) o pedigree EXATO do codigo (creator 1 h, simbolo 24 h, dumper 7 d) para as
-- tres moedas; (b) a cobertura da via rapida: cada tique do Lab (meme_lab_ticks, cadencia
-- 15 s, janela lab_fast_backlog_s = 45 s) na janela de cada moeda, com o buraco entre tiques
-- consecutivos — um buraco > 45 s descarta as fotos daquele intervalo para sempre.
SET statement_timeout = 240000;
\set k 'BiCp7NhzPJBMFeSaqzUuw6mW93n3uUj6ErreumShpump'
\set g 'FLz2Hvyi6mKracWNxo1tRsA9P1Ge7izjNd6ZKXco686M'
\set h 'DgFP1AyHaBEpxqw2dE8SsADDw7oLxMaFd26mC6Y5FngP'

-- (a) pedigree, na letra de lab_repo_fast._PEDIGREE
SELECT t.symbol,
  (SELECT count(*) FROM meme_tokens o WHERE o.creator=t.creator AND o.mint<>t.mint
     AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
     AND o.created_at > t.created_at - interval '1 hour') AS creator_prior_mints_1h,
  (SELECT count(*) FROM meme_tokens o WHERE o.symbol=t.symbol AND o.mint<>t.mint
     AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
     AND o.created_at > t.created_at - interval '24 hours') AS symbol_dup_24h,
  (SELECT count(*) FROM meme_tokens o WHERE o.creator=t.creator AND o.mint<>t.mint
     AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
     AND o.created_at > t.created_at - interval '7 days'
     AND (EXISTS (SELECT 1 FROM meme_features_1m pf WHERE pf.mint=o.mint
                    AND pf.creator_sold = true AND pf.end_time < t.created_at)
          OR EXISTS (SELECT 1 FROM meme_paper_bets pb WHERE pb.mint=o.mint
                       AND pb.creator_sold_seen_at IS NOT NULL
                       AND pb.creator_sold_seen_at < t.created_at)
          OR EXISTS (SELECT 1 FROM meme_paper_bets pb2 WHERE pb2.mint=o.mint
                       AND pb2.exit->>'reason'='creator_dump' AND pb2.exit_at < t.created_at))
  ) AS creator_prior_dump_count_7d,
  (SELECT count(*) FROM meme_tokens o WHERE o.creator=t.creator AND o.mint<>t.mint
     AND o.created_at IS NOT NULL AND o.created_at > t.created_at - interval '7 days') AS criador_7d_total
FROM meme_tokens t WHERE t.mint IN (:'k', :'g', :'h');

-- (b) tiques do Lab na janela das tres moedas (BRT), com o buraco desde o tique anterior
WITH tq AS (
  SELECT ticked_at, rows_evaluated, proposals,
    extract(epoch FROM (ticked_at - lag(ticked_at) OVER (ORDER BY ticked_at)))::numeric(8,1) AS gap_s,
    (refusals::jsonb) -> 'operator' AS recusas_operator
  FROM meme_lab_ticks WHERE ticked_at >= timestamptz '2026-09-16 19:17:00+00'
    AND ticked_at <= timestamptz '2026-09-16 19:42:00+00'
)
SELECT to_char(ticked_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
  gap_s, rows_evaluated, proposals,
  (SELECT sum(v::int) FROM jsonb_each_text(COALESCE(recusas_operator,'{}'::jsonb)) AS e(k2,v)) AS recusas_operator_total
FROM tq ORDER BY ticked_at;

-- (c) os maiores buracos entre tiques nas ultimas 3 h (a via rapida perde tudo alem de 45 s)
WITH tq AS (
  SELECT ticked_at,
    extract(epoch FROM (ticked_at - lag(ticked_at) OVER (ORDER BY ticked_at)))::numeric(8,1) AS gap_s
  FROM meme_lab_ticks WHERE ticked_at >= now() - interval '3 hours'
)
SELECT count(*) AS tiques, count(*) FILTER (WHERE gap_s > 45) AS buracos_acima_de_45s,
  round(avg(gap_s),1) AS gap_medio_s, max(gap_s) AS gap_max_s,
  round(sum(gap_s) FILTER (WHERE gap_s > 45)::numeric,0) AS segundos_perdidos
FROM tq;
