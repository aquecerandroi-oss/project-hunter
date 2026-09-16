-- R15 / KB-0106 — tetos e pisos de snipers com o desfecho ORGANICO.
-- Mesma unidade/janela do r15-q01 (e do r7-q01/q02). Aqui a pergunta e a REGRA:
-- para cada candidato a max_snipers / min_snipers, quantas moedas passam (denominador do
-- "por moeda proposta") e quantas dessas graduaram ORGANICAMENTE.
-- "organica" = completed_at IS NOT NULL AND completed_at - created_at > 60 s AND existe
--              ao menos uma linha de 15 s com curve_progress_pct < 0,9 entre created_at e completed_at
--              (definicao de "nascida cheia" do r12-q02 / KB-0104, negada).
-- A coluna *_kb0101 repete o contador antigo (completed_at OR migrated_at, sem limpeza) lado a lado.
-- Rodar UM DIA por execucao (regra de leitura da VPS: <= 24 h por consulta); somar os dias fora do banco.
SET statement_timeout = 60000;

WITH fp AS (
  SELECT DISTINCT ON (f.mint)
         f.mint, f.snipers, f.curve_progress_pct, f.tape_reason, f.net_sol_flow_60s
  FROM meme_features_15s f
  WHERE f.as_of >= :'d0'::timestamptz AND f.as_of < :'d1'::timestamptz
    AND f.age_s BETWEEN 30 AND 120
  ORDER BY f.mint, f.as_of
), b AS (
  SELECT fp.mint, fp.snipers, t.created_at, t.completed_at,
         (t.completed_at IS NOT NULL OR t.migrated_at IS NOT NULL) AS encheu_kb0101,
         (fp.curve_progress_pct >= 0.02 AND fp.curve_progress_pct <= 0.50
          AND fp.tape_reason IS NULL AND fp.net_sol_flow_60s > 0) AS janela_exec
  FROM fp JOIN meme_tokens t ON t.mint = fp.mint
  WHERE COALESCE(t.mayhem_enabled, false) = false AND t.mayhem_mode IS NULL
), lab AS (
  SELECT b.*,
         (b.completed_at IS NOT NULL
          AND b.completed_at - b.created_at > interval '60 seconds'
          AND EXISTS (SELECT 1 FROM meme_features_15s f
                      WHERE f.mint = b.mint AND f.as_of >= b.created_at AND f.as_of <= b.completed_at
                        AND f.curve_progress_pct IS NOT NULL AND f.curve_progress_pct < 0.9)) AS organica
  FROM b
), s AS (
  SELECT lab.*, 'todas' AS escopo FROM lab
  UNION ALL
  SELECT lab.*, 'janela_exec' AS escopo FROM lab WHERE lab.janela_exec
), tetos(teto) AS (VALUES (2),(5),(10),(15),(20),(25),(30),(40),(60),(100000))
SELECT (:'d0'::timestamptz AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt,
       s.escopo, tetos.teto,
       count(*) FILTER (WHERE s.snipers <= tetos.teto) AS dentro,
       count(*) FILTER (WHERE s.snipers <= tetos.teto AND s.organica) AS dentro_org,
       count(*) FILTER (WHERE s.snipers <= tetos.teto AND s.encheu_kb0101) AS dentro_kb0101,
       count(*) FILTER (WHERE s.snipers > tetos.teto) AS fora,
       count(*) FILTER (WHERE s.snipers > tetos.teto AND s.organica) AS fora_org,
       count(*) FILTER (WHERE s.snipers > tetos.teto AND s.encheu_kb0101) AS fora_kb0101
FROM s CROSS JOIN tetos
WHERE s.snipers IS NOT NULL
GROUP BY 1,2,3 ORDER BY 2,3;
