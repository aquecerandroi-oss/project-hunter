-- R15 / KB-0106 — snipers x graduacao ORGANICA (refaz o KB-0101 sem as nascidas cheias).
-- Unidade e universo: IDENTICOS ao r7-q01 (KB-0101). Snipers na PRIMEIRA foto de 15s com
-- age_s 30-120 s; Mayhem fora (mayhem_enabled true OU mayhem_mode nao nulo); escopo "todas"
-- e "janela_exec" (curve_progress_pct 0,02-0,50 fracao, tape_reason IS NULL, net_sol_flow_60s > 0).
-- O QUE MUDA: o desfecho.
--   encheu_kb0101 = completed_at IS NOT NULL OR migrated_at IS NOT NULL   (o contador antigo)
--   graduou       = completed_at IS NOT NULL                              (desfecho limpo, KB-0104)
--   organica      = graduou AND NOT nascida_cheia, com "nascida cheia" na definicao do r12-q02:
--                   perna D  completed_at - created_at <= 60 s
--                   perna F  nenhuma linha de 15s com curve_progress_pct < 0,9 entre created_at e completed_at
--   so_d          = graduou AND completed_at - created_at > 60 s  (limite inferior, so perna D)
-- Faixas FINAS para permitir reconstruir as faixas do KB-0101 (0-2 / 3-10 / 11-30 / 31-60 / >60)
-- e tambem os tetos 10 e 25 e os pisos 11 / 16 / 21 sem uma segunda passada no banco.
-- Rodar UM DIA por execucao (regra de leitura da VPS: <= 24 h por consulta).
SET statement_timeout = 60000;

WITH fp AS (
  SELECT DISTINCT ON (f.mint)
         f.mint, f.as_of, f.snipers, f.curve_progress_pct, f.tape_reason, f.net_sol_flow_60s
  FROM meme_features_15s f
  WHERE f.as_of >= :'d0'::timestamptz AND f.as_of < :'d1'::timestamptz
    AND f.age_s BETWEEN 30 AND 120
  ORDER BY f.mint, f.as_of
), b AS (
  SELECT fp.mint, fp.snipers, t.created_at, t.completed_at,
         (t.completed_at IS NOT NULL OR t.migrated_at IS NOT NULL) AS encheu_kb0101,
         (t.completed_at IS NOT NULL) AS graduou,
         CASE WHEN fp.snipers IS NULL THEN '8_desconhecido'
              WHEN fp.snipers <= 2  THEN '0_0a2'
              WHEN fp.snipers <= 10 THEN '1_3a10'
              WHEN fp.snipers <= 15 THEN '2_11a15'
              WHEN fp.snipers <= 20 THEN '3_16a20'
              WHEN fp.snipers <= 25 THEN '4_21a25'
              WHEN fp.snipers <= 30 THEN '5_26a30'
              WHEN fp.snipers <= 60 THEN '6_31a60'
              ELSE '7_mais60' END AS faixa,
         (fp.curve_progress_pct >= 0.02 AND fp.curve_progress_pct <= 0.50
          AND fp.tape_reason IS NULL AND fp.net_sol_flow_60s > 0) AS janela_exec
  FROM fp JOIN meme_tokens t ON t.mint = fp.mint
  WHERE COALESCE(t.mayhem_enabled, false) = false AND t.mayhem_mode IS NULL
), lab AS (
  SELECT b.*,
         (b.graduou AND b.completed_at - b.created_at > interval '60 seconds') AS so_d,
         (b.graduou AND b.completed_at - b.created_at > interval '60 seconds'
          AND EXISTS (SELECT 1 FROM meme_features_15s f
                      WHERE f.mint = b.mint AND f.as_of >= b.created_at AND f.as_of <= b.completed_at
                        AND f.curve_progress_pct IS NOT NULL AND f.curve_progress_pct < 0.9)) AS organica
  FROM b
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
  SELECT lab.*, pk.peak_real_sol, pm.peak_mcap_sol
  FROM lab LEFT JOIN pk ON pk.mint = lab.mint LEFT JOIN pm ON pm.mint = lab.mint
)
SELECT (:'d0'::timestamptz AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt,
       escopo, faixa,
       count(*) AS moedas,
       count(*) FILTER (WHERE peak_real_sol >= 30) AS ate_30sol,
       count(*) FILTER (WHERE encheu_kb0101) AS encheu_kb0101,
       count(*) FILTER (WHERE graduou) AS graduou,
       count(*) FILTER (WHERE so_d) AS grad_so_d,
       count(*) FILTER (WHERE organica) AS grad_organica,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY peak_mcap_sol)::numeric, 1) AS mediana_pico_mcap_sol
FROM (
  SELECT j.*, 'todas' AS escopo FROM j
  UNION ALL
  SELECT j.*, 'janela_exec' AS escopo FROM j WHERE j.janela_exec
) s
GROUP BY 1,2,3
ORDER BY 2,3;
