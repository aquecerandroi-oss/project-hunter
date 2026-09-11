-- T3.89 / EXP-0027 passo 1 — a distribuição de `breadth_v2` nos 90 dias, SOMENTE LEITURA,
-- medida ANTES de derivar qualquer variante (as previsões congeladas da página saem daqui).
\pset pager off
\echo '== (1) inventário da série =='
SELECT breadth_version,
       window_minutes,
       count(*)                          AS linhas,
       count(*) FILTER (WHERE usable)    AS usaveis,
       count(*) FILTER (WHERE NOT usable) AS inutilizaveis,
       min(end_time)                     AS primeiro_minuto,
       max(end_time)                     AS ultimo_minuto,
       min(universe_size)                AS universo_min,
       max(universe_size)                AS universo_max
FROM market_breadth
GROUP BY breadth_version, window_minutes
ORDER BY breadth_version;

\echo '== (2) quantis de breadth_v2.value (linhas usáveis, série inteira) =='
SELECT count(*)                                                        AS n,
       round(avg(value), 6)                                            AS media,
       round(min(value), 6)                                            AS minimo,
       round((percentile_cont(0.05) WITHIN GROUP (ORDER BY value))::numeric, 6) AS p05,
       round((percentile_cont(0.10) WITHIN GROUP (ORDER BY value))::numeric, 6) AS p10,
       round((percentile_cont(0.25) WITHIN GROUP (ORDER BY value))::numeric, 6) AS p25,
       round((percentile_cont(0.50) WITHIN GROUP (ORDER BY value))::numeric, 6) AS p50,
       round((percentile_cont(0.75) WITHIN GROUP (ORDER BY value))::numeric, 6) AS p75,
       round((percentile_cont(0.90) WITHIN GROUP (ORDER BY value))::numeric, 6) AS p90,
       round((percentile_cont(0.95) WITHIN GROUP (ORDER BY value))::numeric, 6) AS p95,
       round((percentile_cont(0.99) WITHIN GROUP (ORDER BY value))::numeric, 6) AS p99,
       round(max(value), 6)                                            AS maximo
FROM market_breadth
WHERE breadth_version = 'breadth_v2' AND usable;

\echo '== (3) as faixas pré-registradas: share de minutos por braço (série inteira) =='
SELECT count(*)                                                                    AS minutos_usaveis,
       count(*) FILTER (WHERE value >= 0.10 AND value < 0.60)                       AS braco_a,
       round(100.0 * count(*) FILTER (WHERE value >= 0.10 AND value < 0.60) / count(*), 4) AS braco_a_pct,
       count(*) FILTER (WHERE value >= 0.60 AND value <= 1.00)                      AS braco_b,
       round(100.0 * count(*) FILTER (WHERE value >= 0.60 AND value <= 1.00) / count(*), 4) AS braco_b_pct,
       count(*) FILTER (WHERE value < 0.10)                                         AS fora_baixo,
       round(100.0 * count(*) FILTER (WHERE value < 0.10) / count(*), 4)            AS fora_baixo_pct,
       count(*) FILTER (WHERE value > 0.90)                                         AS acima_090,
       round(100.0 * count(*) FILTER (WHERE value > 0.90) / count(*), 4)            AS acima_090_pct
FROM market_breadth
WHERE breadth_version = 'breadth_v2' AND usable;

\echo '== (3b) o mesmo, restrito à janela em que as duas coortes podem coexistir (>= 2026-06-14) =='
SELECT count(*)                                                                    AS minutos_usaveis,
       round(100.0 * count(*) FILTER (WHERE value >= 0.10 AND value < 0.60) / count(*), 4) AS braco_a_pct,
       round(100.0 * count(*) FILTER (WHERE value >= 0.60 AND value <= 1.00) / count(*), 4) AS braco_b_pct,
       round(100.0 * count(*) FILTER (WHERE value < 0.10) / count(*), 4)            AS fora_baixo_pct
FROM market_breadth
WHERE breadth_version = 'breadth_v2' AND usable
  AND end_time >= '2026-06-14 00:00:00+00' AND end_time < '2026-09-10 00:00:00+00';

\echo '== (4) histograma dos 17 degraus possíveis (16 mercados => passos de 0,0625) =='
SELECT round(value, 4) AS valor,
       count(*)        AS minutos,
       round(100.0 * count(*) / sum(count(*)) OVER (), 4) AS pct
FROM market_breadth
WHERE breadth_version = 'breadth_v2' AND usable
GROUP BY round(value, 4)
ORDER BY valor;

\echo '== (5) tercis congelados na janela de calibração 2026-06-13..2026-07-31 (descritivo) =='
SELECT count(*) AS n_calibracao,
       round((percentile_cont(1.0/3.0) WITHIN GROUP (ORDER BY value))::numeric, 6) AS t1,
       round((percentile_cont(2.0/3.0) WITHIN GROUP (ORDER BY value))::numeric, 6) AS t2
FROM market_breadth
WHERE breadth_version = 'breadth_v2' AND usable
  AND end_time >= '2026-06-13 00:00:00+00' AND end_time < '2026-08-01 00:00:00+00';

\echo '== (6) cobertura por dia: minutos gravados, usáveis e cobertura média =='
SELECT (end_time AT TIME ZONE 'UTC')::date AS dia,
       count(*)                            AS minutos,
       count(*) FILTER (WHERE usable)      AS usaveis,
       round(min(coverage), 4)             AS cobertura_min,
       round(avg(coverage), 4)             AS cobertura_media,
       min(covered)                        AS cobertos_min,
       max(universe_size)                  AS universo
FROM market_breadth
WHERE breadth_version = 'breadth_v2'
GROUP BY 1
ORDER BY 1;

\echo '== (7) as linhas inutilizáveis, nomeadas =='
SELECT reason, count(*) AS minutos, min(end_time) AS de, max(end_time) AS ate
FROM market_breadth
WHERE breadth_version = 'breadth_v2' AND NOT usable
GROUP BY reason ORDER BY 2 DESC;
