-- R7 / KB-0101 — snipers x graduacao com n grande.
-- Unidade: UMA MOEDA (mint). Snipers lidos na PRIMEIRA foto de 15s com age_s 30-120 s
-- (meme_features_15s.snipers; NULL => faixa "desconhecido", motivo em snipers_reason).
-- Mayhem fora (meme_tokens.mayhem_enabled true OU mayhem_mode nao nulo).
-- Escopo "todas" = todas as moedas com primeira foto; "janela_exec" = a mesma foto com
-- progresso 0,02-0,50 (curve_progress_pct e fracao 0-1), fita presente (tape_reason IS NULL)
-- e fluxo positivo (net_sol_flow_60s > 0) -- o universo que a mesa de fato ve.
-- Desfechos: (a) pico de real_sol_reserves >= 30 SOL; (b) encheu a curva
-- (meme_tokens.completed_at ou migrated_at); (c) mediana do pico de mcap_sol (teorico,
-- dentro da janela rastreada de ate 300 s).
-- Rodar um dia por vez:  psql -v d0='2026-09-14 00:00-03' -v d1='2026-09-15 00:00-03' -f ...
-- (a janela de fotos da curva vai ate d1 + 1 dia para pegar o pico de quem nasceu tarde).
SET statement_timeout = 60000;

WITH fp AS (
  SELECT DISTINCT ON (f.mint)
         f.mint, f.as_of, f.snipers, f.snipers_reason,
         f.curve_progress_pct, f.tape_reason, f.net_sol_flow_60s
  FROM meme_features_15s f
  WHERE f.as_of >= :'d0'::timestamptz AND f.as_of < :'d1'::timestamptz
    AND f.age_s BETWEEN 30 AND 120
  ORDER BY f.mint, f.as_of
), b AS (
  SELECT fp.*,
         (t.completed_at IS NOT NULL OR t.migrated_at IS NOT NULL) AS encheu,
         CASE WHEN fp.snipers IS NULL THEN '5_desconhecido'
              WHEN fp.snipers <= 2  THEN '0_0a2'
              WHEN fp.snipers <= 10 THEN '1_3a10'
              WHEN fp.snipers <= 30 THEN '2_11a30'
              WHEN fp.snipers <= 60 THEN '3_31a60'
              ELSE '4_mais60' END AS faixa,
         (fp.curve_progress_pct >= 0.02 AND fp.curve_progress_pct <= 0.50
          AND fp.tape_reason IS NULL AND fp.net_sol_flow_60s > 0) AS janela_exec
  FROM fp JOIN meme_tokens t ON t.mint = fp.mint
  WHERE COALESCE(t.mayhem_enabled, false) = false AND t.mayhem_mode IS NULL
), pk AS (
  SELECT b.mint, max(cs.real_sol_reserves) AS peak_real_sol
  FROM b JOIN meme_curve_snapshots cs ON cs.mint = b.mint
  WHERE cs.observed_at >= :'d0'::timestamptz
    AND cs.observed_at < :'d1'::timestamptz + interval '1 day'
  GROUP BY 1
), pm AS (
  SELECT b.mint, max(f.mcap_sol) AS peak_mcap_sol
  FROM b JOIN meme_features_15s f ON f.mint = b.mint
  WHERE f.as_of >= :'d0'::timestamptz AND f.as_of < :'d1'::timestamptz + interval '1 day'
  GROUP BY 1
), j AS (
  SELECT b.*, pk.peak_real_sol, pm.peak_mcap_sol
  FROM b LEFT JOIN pk ON pk.mint = b.mint LEFT JOIN pm ON pm.mint = b.mint
)
SELECT (:'d0'::timestamptz AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt,
       escopo, faixa,
       count(*) AS moedas,
       count(*) FILTER (WHERE peak_real_sol >= 30) AS ate_30sol,
       round(100.0 * count(*) FILTER (WHERE peak_real_sol >= 30) / NULLIF(count(*),0), 2) AS pct_30sol,
       count(*) FILTER (WHERE encheu) AS encheu,
       round(100.0 * count(*) FILTER (WHERE encheu) / NULLIF(count(*),0), 2) AS pct_encheu,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY peak_mcap_sol)::numeric, 1) AS mediana_pico_mcap_sol
FROM (
  SELECT j.*, 'todas' AS escopo FROM j
  UNION ALL
  SELECT j.*, 'janela_exec' AS escopo FROM j WHERE j.janela_exec
) s
GROUP BY 1,2,3
ORDER BY 2,3;
