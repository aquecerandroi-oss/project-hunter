-- R22 q04 — mesmo mint, mesmo minuto: o top10_share do retrato x o de meme_features_1m.
-- Resposta 16/09: 15565 pares | 15475 com valor na mesa | 84 pares com retrato > 1
--   | 84 desses com features NULL | erro medio 0.004986 | 12832 identicos (1e-6) | 1052 diferem >= 1 pp
WITH r AS (
    SELECT mint,
           date_trunc('minute', observed_at) + interval '1 minute' AS et,
           avg(top10_share) AS t10r
    FROM meme_risk_snapshots
    GROUP BY 1, 2
)
SELECT count(*) AS pares,
       count(f.top10_share) AS com_valor_na_mesa,
       count(*) FILTER (WHERE r.t10r > 1) AS retrato_gt1,
       count(*) FILTER (WHERE r.t10r > 1 AND f.top10_share IS NULL) AS retrato_gt1_mesa_null,
       round(avg(abs(f.top10_share - r.t10r)), 6) AS erro_medio,
       count(*) FILTER (WHERE f.top10_share IS NOT NULL AND abs(f.top10_share - r.t10r) < 0.000001) AS identicos,
       count(*) FILTER (WHERE f.top10_share IS NOT NULL AND abs(f.top10_share - r.t10r) >= 0.01) AS dif_1pp
FROM r
JOIN meme_features_1m f ON f.mint = r.mint AND f.end_time = r.et;

-- a mesma medida, mas contra as barras cuja leitura veio do BOARD (t10 do /ws/trenches):
-- 55879 pares | mediana board 0.2555 x retrato 0.2571 | dif media +0.0033 | 41977 iguais (< 0.001)
WITH r AS (
    SELECT mint, date_trunc('minute', observed_at) + interval '1 minute' AS et,
           avg(top10_share) AS t10r
    FROM meme_risk_snapshots GROUP BY 1, 2
), b AS (
    SELECT mint, end_time, top10_share AS t10b
    FROM meme_features_1m
    WHERE holders_source = 'trenches_ws' AND top10_share IS NOT NULL
)
SELECT count(*) AS pares,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY b.t10b)::numeric, 4) AS med_board,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY r.t10r)::numeric, 4) AS med_retrato,
       round(avg(r.t10r - b.t10b), 4) AS dif_media,
       count(*) FILTER (WHERE r.t10r > b.t10b) AS retrato_maior,
       count(*) FILTER (WHERE abs(r.t10r - b.t10b) < 0.001) AS iguais
FROM r JOIN b ON b.mint = r.mint
   AND b.end_time BETWEEN r.et - interval '2 minutes' AND r.et + interval '2 minutes';

-- quem alimenta a coluna da mesa, e quantas leituras sao recusadas por out_of_range
-- Resposta: trenches_ws 832348 linhas (664576 com valor, 167772 out_of_range, mediana 0.0023)
--           indexer_rest:/in-memory-coin 12583 (12179 com valor, 404 out_of_range, mediana 0.2375)
SELECT holders_source, count(*), count(top10_share) AS com_valor,
       count(*) FILTER (WHERE top10_share_reason = 'out_of_range') AS out_of_range,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY top10_share)::numeric, 4) AS med
FROM meme_features_1m
WHERE holders_source IS NOT NULL OR top10_share_reason IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC;
