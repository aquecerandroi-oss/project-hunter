-- R22 q02 — onde o top10_share do retrato estoura 1: por faixa de progresso.
-- Resposta 16/09: 0-10 %: 25/392 · 10-20 %: 53/93 (mediana 1.0977!) · 20-30 %: 27/69
-- · 30-60 %: 2/77 · 60-100 %: 0/19832 · progresso 100: 8/23.
SELECT width_bucket(coalesce(progress_pct, -1), 0, 100, 10) AS faixa,
       count(*) AS n,
       count(*) FILTER (WHERE top10_share > 1) AS gt1,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY top10_share)::numeric, 4) AS med,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY holders)::numeric, 1) AS holders_med,
       round(min(progress_pct), 2), round(max(progress_pct), 2)
FROM meme_risk_snapshots
GROUP BY 1
ORDER BY 1;
