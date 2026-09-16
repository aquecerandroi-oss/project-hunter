-- T4.29b — q03: os DOIS tetos juntos, por minuto-moeda na curva (ultimos 7 dias).
--   teto_participacao = 0,01 * curve_volume_1m_sol      (max_participation_pct)
--   teto_impacto      = 0,005 * vsol * 1,0125           (max_price_impact_pct, ver q02)
--   vsol = 30 * 1073000000 / (1073000000 - 793100000 * progresso)
--   admitido = min(teto_participacao, teto_impacto)
-- Universo: idade 0-30 min, nao-Mayhem, minuto ainda na curva, progresso em [0,1],
-- volume do minuto conhecido (sem fita nao ha participacao: o portao recusa).
WITH span AS (
  SELECT greatest(extract(epoch FROM (max(end_time) - min(end_time))) / 86400.0, 0.001) AS dias
  FROM meme_features_1m WHERE end_time >= now() - make_interval(days => 7)
),
base AS (
  SELECT f.mint, f.end_time, f.curve_volume_1m_sol AS vol,
         least(greatest(f.curve_progress_pct, 0), 1)::numeric AS t
  FROM meme_features_1m f
  JOIN meme_tokens t2 ON t2.mint = f.mint
  WHERE f.end_time >= now() - make_interval(days => 7)
    AND f.age_minutes BETWEEN 0 AND 30
    AND f.curve_volume_1m_sol IS NOT NULL
    AND f.curve_progress_pct IS NOT NULL AND f.curve_progress_pct >= 0
    AND coalesce(t2.mayhem_enabled, false) = false
    AND (t2.migrated_at IS NULL OR f.end_time <= t2.migrated_at)
), tet AS (
  SELECT mint, end_time, t, vol,
         0.01 * vol AS teto_part,
         0.005 * (30.0 * 1073000000.0 / (1073000000.0 - 793100000.0 * t)) * 1.0125 AS teto_imp
  FROM base
), adm AS (
  SELECT mint, end_time, t, vol, teto_part, teto_imp, least(teto_part, teto_imp) AS admitido FROM tet
), sz AS (SELECT unnest(ARRAY[0.05,0.10,0.25,0.50,1.0,2.0,5.0,9.8]::numeric[]) AS x)
SELECT sz.x                                                                       AS compra_sol,
       count(*) FILTER (WHERE a.admitido >= sz.x)                                 AS minutos_ambos,
       count(DISTINCT a.mint) FILTER (WHERE a.admitido >= sz.x)                   AS moedas_ambos,
       round((count(DISTINCT a.mint) FILTER (WHERE a.admitido >= sz.x) / (SELECT dias FROM span))::numeric, 1) AS moedas_por_dia,
       count(*) FILTER (WHERE a.teto_part >= sz.x)                                AS minutos_so_participacao,
       count(*) FILTER (WHERE a.teto_imp  >= sz.x)                                AS minutos_so_impacto,
       count(*) FILTER (WHERE a.admitido >= sz.x AND a.t BETWEEN 0.05 AND 0.50)   AS minutos_ambos_janela_5_50,
       count(DISTINCT a.mint) FILTER (WHERE a.admitido >= sz.x AND a.t BETWEEN 0.05 AND 0.50) AS moedas_janela_5_50
FROM sz CROSS JOIN adm a
GROUP BY sz.x ORDER BY sz.x
