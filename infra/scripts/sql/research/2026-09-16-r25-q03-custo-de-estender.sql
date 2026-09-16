-- KB-0113 Q03 — (a) quao velha era a ultima observacao quando a aposta fechou por tempo;
-- (b) sanidade da fita de pool (meme_trades.program); (c) o custo em linhas/dia de estender
-- a cobertura: volume atual das duas series e quantos mints teriam de ser seguidos por aposta.
-- Uso: psql -v dia=2026-09-15 -At -F "|" -f este-arquivo.sql
SET statement_timeout = 120000;

WITH d AS (
  SELECT (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo' AS ini,
         ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo' AS fim
), b AS (
  SELECT pb.id, pb.mint, pb.entry_at, pb.exit_at, pb.mark_stale_s, pb.mark_source,
         COALESCE(pb.exit ->> 'reason', 'sem_reason') AS exit_reason,
         EXTRACT(epoch FROM pb.exit_at - pb.entry_at)::int AS hold_s
  FROM meme_paper_bets pb CROSS JOIN d
  WHERE pb.status = 'closed' AND pb.exit_at >= d.ini AND pb.exit_at < d.fim
), stale AS (
  SELECT b.*,
    EXTRACT(epoch FROM b.exit_at - (SELECT max(f.end_time) FROM meme_features_1m f
        WHERE f.mint = b.mint AND f.end_time <= b.exit_at
          AND f.end_time > b.exit_at - interval '6 hours'
          AND f.mcap_sol IS NOT NULL AND f.mcap_sol > 0))::int AS idade_ultima_1m_s
  FROM b
)
SELECT 'A_idade_da_ultima_obs' AS bloco, exit_reason AS k, count(*)::text AS c1,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY idade_ultima_1m_s)::text AS c2,
       percentile_disc(0.9) WITHIN GROUP (ORDER BY idade_ultima_1m_s)::text AS c3,
       max(idade_ultima_1m_s)::text AS c4,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY hold_s)::text AS c5
FROM stale GROUP BY exit_reason
UNION ALL
SELECT 'B_fita_pool', COALESCE(program, 'null'), count(*)::text,
       count(DISTINCT mint)::text, '', '', ''
FROM meme_trades CROSS JOIN d
WHERE block_time >= d.ini AND block_time < d.fim
GROUP BY program
UNION ALL
SELECT 'C_volume_serie', '15s', count(*)::text, count(DISTINCT mint)::text,
       round(count(*)::numeric / NULLIF(count(DISTINCT mint), 0), 1)::text, '', ''
FROM meme_features_15s CROSS JOIN d WHERE as_of >= d.ini AND as_of < d.fim
UNION ALL
SELECT 'C_volume_serie', '1m', count(*)::text, count(DISTINCT mint)::text,
       round(count(*)::numeric / NULLIF(count(DISTINCT mint), 0), 1)::text, '', ''
FROM meme_features_1m CROSS JOIN d WHERE end_time >= d.ini AND end_time < d.fim
UNION ALL
SELECT 'D_apostas_e_propostas', 'apostas_abertas_no_dia', count(*)::text,
       count(DISTINCT mint)::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM exit_at - entry_at))::text,
       '', ''
FROM meme_paper_bets CROSS JOIN d
WHERE entry_at >= d.ini AND entry_at < d.fim
UNION ALL
SELECT 'D_apostas_e_propostas', 'propostas_no_dia', count(*)::text,
       count(DISTINCT mint)::text, '', '', ''
FROM meme_proposals CROSS JOIN d
WHERE proposed_at >= d.ini AND proposed_at < d.fim
ORDER BY 1, 2;
