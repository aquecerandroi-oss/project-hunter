-- EXP-M26 F — 2/3: para cada 1.ª oportunidade (mint, T) da porta pura de C: as fotos que a guarda
-- de cobertura de R1 lê (repo_lines._LINE_POINTS: observed_at em (T - 16 min, T], received_at <= T)
-- e o pedigree que o laço lê (lab_repo_fast._PEDIGREE, as duas contagens de PEDIGREE_V1).
-- Somente leitura. Os pares (mint, T) são preenchidos por f_funil.py fase1.
COPY (
WITH p(mint, t) AS (VALUES
--PARES--
)
SELECT 'ponto' AS tipo, s.mint, s.observed_at, s.received_at, s.mcap_sol,
       NULL::bigint AS creator_prior_mints_1h, NULL::bigint AS symbol_dup_24h
FROM p JOIN meme_curve_snapshots s ON s.mint = p.mint
  AND s.observed_at > p.t - interval '16 minutes' AND s.observed_at <= p.t AND s.received_at <= p.t
UNION ALL
SELECT 'pedigree', t.mint, NULL, NULL, NULL,
       CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE (
         SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - make_interval(secs => 3600)) END,
       CASE WHEN t.symbol IS NULL OR t.created_at IS NULL THEN NULL ELSE (
         SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - make_interval(secs => 86400)) END
FROM p JOIN meme_tokens t ON t.mint = p.mint
ORDER BY 1, 2, 3, 4
) TO STDOUT WITH (FORMAT csv, HEADER true);
