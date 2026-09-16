-- R37 (T4.40) — A linha de 15 s contra a cadeia na população: o SOL real da foto que a linha
-- carrega (join por mint + snapshot_observed_at) contra a leitura RPC mais próxima de as_of
-- (janela +/- 30 s). Fração de linhas com erro relativo > 50 %. 16/09 19:00-21:00 UTC.
WITH f AS (
    SELECT as_of, mint, snapshot_observed_at, snapshot_source, curve_progress_pct
    FROM meme_features_15s
    WHERE as_of >= timestamptz '2026-09-16 19:00:00+00'
      AND as_of <  timestamptz '2026-09-16 21:00:00+00'
      AND snapshot_observed_at IS NOT NULL
), linha AS (
    SELECT f.*, s.real_sol_reserves AS rsol_linha
    FROM f
    JOIN LATERAL (
        SELECT real_sol_reserves FROM meme_curve_snapshots c
        WHERE c.mint = f.mint AND c.observed_at = f.snapshot_observed_at
        ORDER BY c.received_at DESC LIMIT 1
    ) s ON TRUE
), cadeia AS (
    SELECT linha.*, t.real_sol_reserves AS rsol_cadeia, t.observed_at AS cadeia_at
    FROM linha
    LEFT JOIN LATERAL (
        SELECT c.real_sol_reserves, c.observed_at FROM meme_curve_snapshots c
        WHERE c.mint = linha.mint AND c.source = 'solana_rpc'
          AND c.observed_at >= linha.as_of - interval '30 seconds'
          AND c.observed_at <= linha.as_of + interval '30 seconds'
        ORDER BY abs(extract(epoch FROM (c.observed_at - linha.as_of))) LIMIT 1
    ) t ON TRUE
)
SELECT snapshot_source                                                   AS fonte,
       count(*)                                                          AS linhas,
       count(*) FILTER (WHERE rsol_cadeia IS NULL)                       AS sem_cadeia,
       count(*) FILTER (WHERE rsol_cadeia IS NOT NULL
             AND abs(rsol_linha - rsol_cadeia) > 0.5 * greatest(rsol_cadeia, 0.000000001)) AS erro_acima_50pct,
       round(100.0 * count(*) FILTER (WHERE rsol_cadeia IS NOT NULL
             AND abs(rsol_linha - rsol_cadeia) > 0.5 * greatest(rsol_cadeia, 0.000000001))
             / nullif(count(*) FILTER (WHERE rsol_cadeia IS NOT NULL), 0), 2)              AS pct,
       count(*) FILTER (WHERE rsol_cadeia IS NOT NULL AND rsol_linha > 2 * rsol_cadeia)    AS linha_otimista
FROM cadeia
GROUP BY 1 ORDER BY 2 DESC;
