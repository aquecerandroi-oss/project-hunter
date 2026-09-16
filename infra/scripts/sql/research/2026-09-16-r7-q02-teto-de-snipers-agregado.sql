-- R7 / KB-0101 — o teto de snipers agregado (5 dias, 12-16/09/2026).
-- Mesma definicao de unidade e de janela do q01. Aqui a pergunta e o TETO:
-- para cada candidato a max_snipers, quantas moedas passam (denominador do "por moeda
-- proposta") e quantas dessas encheram a curva -- dentro e FORA do teto.
SET statement_timeout = 60000;

WITH fp AS (
  SELECT DISTINCT ON (f.mint)
         f.mint, f.as_of, f.snipers, f.curve_progress_pct, f.tape_reason, f.net_sol_flow_60s
  FROM meme_features_15s f
  WHERE f.as_of >= timestamptz '2026-09-12 00:00-03' AND f.as_of < timestamptz '2026-09-17 00:00-03'
    AND f.age_s BETWEEN 30 AND 120
  ORDER BY f.mint, f.as_of
), b AS (
  SELECT fp.mint, fp.snipers,
         (t.completed_at IS NOT NULL OR t.migrated_at IS NOT NULL) AS encheu,
         (fp.curve_progress_pct >= 0.02 AND fp.curve_progress_pct <= 0.50
          AND fp.tape_reason IS NULL AND fp.net_sol_flow_60s > 0) AS janela_exec
  FROM fp JOIN meme_tokens t ON t.mint = fp.mint
  WHERE COALESCE(t.mayhem_enabled, false) = false AND t.mayhem_mode IS NULL
), s AS (
  SELECT b.*, 'todas' AS escopo FROM b
  UNION ALL
  SELECT b.*, 'janela_exec' AS escopo FROM b WHERE b.janela_exec
), tetos(teto) AS (VALUES (2),(5),(10),(15),(20),(30),(40),(60),(100000))
SELECT s.escopo, tetos.teto,
       count(*) FILTER (WHERE s.snipers <= tetos.teto) AS dentro,
       count(*) FILTER (WHERE s.snipers <= tetos.teto AND s.encheu) AS dentro_encheu,
       round(100.0 * count(*) FILTER (WHERE s.snipers <= tetos.teto AND s.encheu)
             / NULLIF(count(*) FILTER (WHERE s.snipers <= tetos.teto),0), 3) AS pct_dentro,
       count(*) FILTER (WHERE s.snipers > tetos.teto) AS fora,
       count(*) FILTER (WHERE s.snipers > tetos.teto AND s.encheu) AS fora_encheu,
       round(100.0 * count(*) FILTER (WHERE s.snipers > tetos.teto AND s.encheu)
             / NULLIF(count(*) FILTER (WHERE s.snipers > tetos.teto),0), 3) AS pct_fora
FROM s CROSS JOIN tetos
WHERE s.snipers IS NOT NULL
GROUP BY 1,2 ORDER BY 1,2;
