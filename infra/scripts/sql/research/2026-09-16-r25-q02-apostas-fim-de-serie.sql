-- KB-0113 Q02 — As apostas de papel FECHADAS em 15/09 (BRT): quantas fecharam por tempo/limite
-- na ULTIMA barra que existia da serie ("fim da serie" disfarcado de saida por tempo), e como o
-- fechamento diario as classificou (outcome_quality). Um dia por execucao.
-- Uso: psql -v dia=2026-09-15 -At -F "|" -f este-arquivo.sql
SET statement_timeout = 120000;

WITH dia AS (
  SELECT (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo' AS ini,
         ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo' AS fim
), b AS (
  SELECT pb.id, pb.mint, pb.mode, pb.entry_at, pb.exit_at, pb.r_multiple,
         pb.outcome_quality, pb.outcome_quality_reason, pb.mark_source,
         COALESCE(pb.exit ->> 'reason', 'sem_reason') AS exit_reason,
         t.completed_at, t.migrated_at
  FROM meme_paper_bets pb
  JOIN meme_tokens t ON t.mint = pb.mint
  CROSS JOIN dia d
  WHERE pb.status = 'closed' AND pb.exit_at >= d.ini AND pb.exit_at < d.fim
), ult AS (
  SELECT b.id,
         (SELECT max(f.end_time) FROM meme_features_1m f
           WHERE f.mint = b.mint AND f.end_time >= b.entry_at - interval '5 minutes'
             AND f.end_time <= b.exit_at + interval '35 minutes'
             AND f.mcap_sol IS NOT NULL AND f.mcap_sol > 0) AS last_1m,
         (SELECT max(f.as_of) FROM meme_features_15s f
           WHERE f.mint = b.mint AND f.as_of >= b.entry_at - interval '5 minutes'
             AND f.as_of <= b.exit_at + interval '35 minutes'
             AND f.mcap_sol IS NOT NULL AND f.mcap_sol > 0) AS last_15s
  FROM b
), j AS (
  SELECT b.*, u.last_1m, u.last_15s,
         EXTRACT(epoch FROM b.exit_at - b.entry_at)::int AS hold_s,
         EXTRACT(epoch FROM u.last_1m - b.exit_at)::int AS depois_1m_s,
         EXTRACT(epoch FROM GREATEST(u.last_1m, COALESCE(u.last_15s, u.last_1m)) - b.exit_at)::int AS depois_s
  FROM b JOIN ult u ON u.id = b.id
)
SELECT 'A_por_motivo' AS bloco, exit_reason AS k, count(*)::text AS c1,
       round(avg(r_multiple)::numeric, 3)::text AS c2,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY hold_s)::text AS c3,
       count(*) FILTER (WHERE outcome_quality = 'indeterminate')::text AS c4,
       count(*) FILTER (WHERE COALESCE(depois_s, -1) <= 90)::text AS c5,
       count(*) FILTER (WHERE COALESCE(depois_s, -1) <= 90
                          AND outcome_quality = 'measured')::text AS c6
FROM j GROUP BY exit_reason
UNION ALL
SELECT 'B_fim_de_serie', CASE WHEN COALESCE(depois_s, -1) <= 90 THEN 'fecho_na_ultima_barra'
                             ELSE 'serie_continuava' END,
       count(*)::text, round(avg(r_multiple)::numeric, 3)::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY hold_s)::text,
       count(*) FILTER (WHERE outcome_quality = 'indeterminate')::text,
       count(*) FILTER (WHERE exit_reason IN ('time_stop', 'time', 'timeout'))::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY COALESCE(depois_s, -1))::text
FROM j GROUP BY 2
UNION ALL
SELECT 'C_qualidade', outcome_quality || '/' || COALESCE(outcome_quality_reason, 'sem_motivo'),
       count(*)::text, round(avg(r_multiple)::numeric, 3)::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY hold_s)::text, '', '', ''
FROM j GROUP BY 2
ORDER BY 1, 2;
