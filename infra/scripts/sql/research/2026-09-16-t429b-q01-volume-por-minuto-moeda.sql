-- T4.29b — q01: distribuicao do volume ORGANICO de 1 min na curva, por minuto-moeda.
-- Universo: meme_features_1m (uma linha por mint por minuto fechado), idade 0-30 min,
-- moeda NAO-Mayhem (o SOL virtual do agente nao e comprador - KB-0098), e o minuto
-- acontecendo AINDA NA CURVA (antes de migrated_at, quando houve migracao).
-- Janela: ultimos 7 dias (a serie so existe desde 2026-09-12 07:30Z; o divisor por dia
-- usa o VAO MEDIDO, nao 7 - ver coluna dias_medidos).
-- Os patamares 100/200/500/980 SOL sao o volume necessario para comprar 1/2/5/9,8 SOL
-- com o teto de participacao de 1 % (docs/RISK_ENGINE_MEME.md 3.1, max_participation_pct=0.01).
-- Rodado pelo caminho de leitura auditado (ssh hunter-vps -> docker exec postgres psql -Atc).
WITH span AS (
  SELECT greatest(extract(epoch FROM (max(end_time) - min(end_time))) / 86400.0, 0.001) AS dias
  FROM meme_features_1m WHERE end_time >= now() - make_interval(days => 7)
),
m AS (
  SELECT f.mint, f.end_time, f.curve_volume_1m_sol AS v
  FROM meme_features_1m f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.end_time >= now() - make_interval(days => 7)
    AND f.age_minutes BETWEEN 0 AND 30
    AND f.curve_volume_1m_sol IS NOT NULL
    AND coalesce(t.mayhem_enabled, false) = false
    AND (t.migrated_at IS NULL OR f.end_time <= t.migrated_at)
)
SELECT round((SELECT dias FROM span)::numeric, 3)                            AS dias_medidos,
       count(*)                                                             AS minutos_moeda,
       count(DISTINCT mint)                                                 AS moedas,
       round((count(*) / (SELECT dias FROM span))::numeric, 0)               AS minutos_por_dia,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY v)::numeric, 4)   AS p50,
       round(percentile_cont(0.90) WITHIN GROUP (ORDER BY v)::numeric, 4)   AS p90,
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY v)::numeric, 4)   AS p99,
       round(percentile_cont(0.999) WITHIN GROUP (ORDER BY v)::numeric, 4)  AS p999,
       round(max(v)::numeric, 4)                                            AS maximo,
       count(*) FILTER (WHERE v >= 100)                                     AS ge_100,
       count(*) FILTER (WHERE v >= 200)                                     AS ge_200,
       count(*) FILTER (WHERE v >= 500)                                     AS ge_500,
       count(*) FILTER (WHERE v >= 980)                                     AS ge_980
FROM m
