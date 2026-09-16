-- R22 q01 — distribuicao de top10_share e bundled_share em meme_risk_snapshots
-- (o retrato de risco, /in-memory-coin). Resposta 16/09/2026 16:5x BRT:
-- 20486|20486|115|1274|0.2580|1.5171|20486|0|208|0.0637|0.7900|12/09 11:48Z|16/09 19:50Z
SELECT count(*) AS n,
       count(top10_share) AS n_t10,
       count(*) FILTER (WHERE top10_share > 1) AS t10_gt1,
       count(*) FILTER (WHERE top10_share > 0.5) AS t10_gt05,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY top10_share)::numeric, 4) AS t10_med,
       round(max(top10_share), 4) AS t10_max,
       count(bundled_share) AS n_bun,
       count(*) FILTER (WHERE bundled_share > 1) AS bun_gt1,
       count(*) FILTER (WHERE bundled_share > 0.5) AS bun_gt05,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY bundled_share)::numeric, 4) AS bun_med,
       round(max(bundled_share), 4) AS bun_max,
       min(observed_at), max(observed_at)
FROM meme_risk_snapshots;

-- exemplos (mint/hora BRT) das leituras acima de 1, com o campo cru da API
SELECT left(mint, 6), to_char(observed_at AT TIME ZONE 'America/Sao_Paulo', 'DD/MM HH24:MI'),
       round(top10_share, 4), holders, round(dev_share, 4), round(sniper_share, 4),
       round(bundled_share, 4), round(progress_pct, 2),
       raw->>'top10HoldersPercent', raw->>'coinCreatedSupply'
FROM meme_risk_snapshots
WHERE top10_share > 1
ORDER BY top10_share DESC
LIMIT 10;
