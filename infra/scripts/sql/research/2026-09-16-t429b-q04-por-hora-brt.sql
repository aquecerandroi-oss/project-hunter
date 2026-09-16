-- T4.29b — q04: os minutos-moeda admissiveis por HORA DE BRASILIA (America/Sao_Paulo).
-- Mesmos tetos e mesmo universo da q03. Colunas: quantos minutos-moeda daquela hora
-- admitem 0,05 / 0,10 / 0,25 / 0,50 SOL sob AMBOS os tetos, e quantos teriam volume
-- para 1 SOL e 9,8 SOL SO pelo teto de participacao (o de impacto ja os recusa).
WITH base AS (
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
), adm AS (
  SELECT mint, extract(hour FROM end_time AT TIME ZONE $$America/Sao_Paulo$$)::int AS hora_brt,
         vol, 0.01 * vol AS teto_part,
         least(0.01 * vol,
               0.005 * (30.0 * 1073000000.0 / (1073000000.0 - 793100000.0 * t)) * 1.0125) AS admitido
  FROM base
)
SELECT hora_brt,
       count(*)                                        AS minutos_moeda,
       count(*) FILTER (WHERE admitido >= 0.05)        AS adm_005,
       count(*) FILTER (WHERE admitido >= 0.10)        AS adm_010,
       count(*) FILTER (WHERE admitido >= 0.25)        AS adm_025,
       count(*) FILTER (WHERE admitido >= 0.50)        AS adm_050,
       count(*) FILTER (WHERE teto_part >= 1.0)        AS volume_para_1sol,
       count(*) FILTER (WHERE teto_part >= 9.8)        AS volume_para_98sol
FROM adm GROUP BY hora_brt ORDER BY hora_brt
