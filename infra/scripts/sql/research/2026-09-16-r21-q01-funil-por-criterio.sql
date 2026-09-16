-- R21 - funil da porta do operator (rule set "operator" v5, clock 15s) sobre
-- meme_features_15s desde 16:17 BRT de 16/09/2026 (boot da porta calibrada).
-- A ordem replica hunter_indicators.meme.rules:evaluate_entry mais as
-- exclusoes de pedigree aplicadas em proposals.evaluate_gate (pedigree antes
-- dos criterios do set). Cada linha do funil e cumulativa (AND dos anteriores).
-- Parametros lidos de meme_rule_sets (kind=operator, status=active):
--   age 30..300 s | progress 5..50 % (a coluna e fracao 0-1) |
--   max_participation_pct 1 com size 0.05 SOL -> curve_volume_60s_sol >= 5 |
--   max_dev_share 0.10 (unknown refusa) | snipers 21..1000 |
--   fluxo positivo | min_unique_buyers 10 | sells/buys <= 0.6 | min_holders 20 |
--   exclude_mayhem (default true) | pedigree_exclusions + pedigree_repeat_dumper.
WITH janela AS (
  SELECT f.*, t.created_at, t.completed_at, t.migrated_at, t.creator, t.symbol,
         t.mayhem_enabled, t.mayhem_state
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 16:17-03'
    AND f.features_version = 'meme_features_15s_v1'
), ped AS (
  SELECT t.mint,
    CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE (
      SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
        AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
        AND o.created_at > t.created_at - interval '1 hour') END AS creator_prior_mints_1h,
    CASE WHEN t.symbol IS NULL OR t.created_at IS NULL THEN NULL ELSE (
      SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
        AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
        AND o.created_at > t.created_at - interval '24 hours') END AS symbol_dup_24h,
    CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE (
      SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
        AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
        AND o.created_at > t.created_at - interval '7 days'
        AND (EXISTS (SELECT 1 FROM meme_features_1m pf WHERE pf.mint = o.mint
                       AND pf.creator_sold = true AND pf.end_time < t.created_at)
          OR EXISTS (SELECT 1 FROM meme_paper_bets pb WHERE pb.mint = o.mint
                       AND pb.creator_sold_seen_at IS NOT NULL
                       AND pb.creator_sold_seen_at < t.created_at)
          OR EXISTS (SELECT 1 FROM meme_paper_bets pb2 WHERE pb2.mint = o.mint
                       AND pb2.exit ->> 'reason' = 'creator_dump'
                       AND pb2.exit_at < t.created_at))) END AS creator_prior_dump_count
  FROM meme_tokens t WHERE t.mint IN (SELECT DISTINCT mint FROM janela)
), p AS (
  SELECT j.mint, j.as_of,
    (j.completed_at IS NULL AND j.migrated_at IS NULL) AS c00_viva,
    (pd.creator_prior_mints_1h IS NOT NULL AND pd.creator_prior_mints_1h <= 1
     AND pd.symbol_dup_24h IS NOT NULL AND pd.symbol_dup_24h <= 2
     AND coalesce(pd.creator_prior_dump_count, 0) = 0) AS c01_pedigree,
    (j.mayhem_enabled IS NOT NULL AND j.mayhem_enabled = false) AS c02_nao_mayhem,
    (j.age_s IS NOT NULL AND j.age_s >= 30 AND j.age_s <= 300) AS c03_idade,
    (j.curve_progress_pct IS NOT NULL AND j.curve_progress_pct >= 0.05
     AND j.curve_progress_pct <= 0.50) AS c04_progresso,
    (j.creator_net_seller = false
     OR (j.creator_net_seller IS NULL AND j.dev_share IS NOT NULL AND j.dev_share <= 0.10))
      AS c05_criador,
    (j.curve_volume_60s_sol IS NOT NULL AND j.curve_volume_60s_sol >= 5) AS c06_participacao,
    (j.dev_share IS NOT NULL AND j.dev_share <= 0.10) AS c07_dev_share,
    (j.snipers IS NOT NULL AND j.snipers >= 21 AND j.snipers <= 1000) AS c08_snipers,
    (coalesce(j.net_sol_flow_60s > 0, j.mcap_delta_60s > 0, false)) AS c09_fluxo,
    (j.unique_buyers_60s IS NOT NULL AND j.unique_buyers_60s >= 10) AS c10_compradores,
    (j.buys_60s IS NOT NULL AND j.sells_60s IS NOT NULL AND j.buys_60s > 0
     AND j.sells_60s::numeric / j.buys_60s <= 0.6) AS c11_sells_buys,
    (j.holders IS NOT NULL AND j.holders >= 20) AS c12_holders
  FROM janela j LEFT JOIN ped pd ON pd.mint = j.mint
), acc AS (
  SELECT mint,
    c00_viva AS a00,
    c00_viva AND c01_pedigree AS a01,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AS a02,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AS a03,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso AS a04,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso
      AND c05_criador AS a05,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso
      AND c05_criador AND c06_participacao AS a06,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso
      AND c05_criador AND c06_participacao AND c07_dev_share AS a07,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso
      AND c05_criador AND c06_participacao AND c07_dev_share AND c08_snipers AS a08,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso
      AND c05_criador AND c06_participacao AND c07_dev_share AND c08_snipers
      AND c09_fluxo AS a09,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso
      AND c05_criador AND c06_participacao AND c07_dev_share AND c08_snipers
      AND c09_fluxo AND c10_compradores AS a10,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso
      AND c05_criador AND c06_participacao AND c07_dev_share AND c08_snipers
      AND c09_fluxo AND c10_compradores AND c11_sells_buys AS a11,
    c00_viva AND c01_pedigree AND c02_nao_mayhem AND c03_idade AND c04_progresso
      AND c05_criador AND c06_participacao AND c07_dev_share AND c08_snipers
      AND c09_fluxo AND c10_compradores AND c11_sells_buys AND c12_holders AS a12
  FROM p
)
SELECT passo, linhas, moedas FROM (
  SELECT 0 AS ord, '00 janela (todas as linhas 15s)' AS passo, count(*) AS linhas,
         count(DISTINCT mint) AS moedas FROM acc
  UNION ALL SELECT 1, '01 viva (nao completa/migrada)', count(*) FILTER (WHERE a00),
         count(DISTINCT mint) FILTER (WHERE a00) FROM acc
  UNION ALL SELECT 2, '02 pedigree (serial/clone/dumper)', count(*) FILTER (WHERE a01),
         count(DISTINCT mint) FILTER (WHERE a01) FROM acc
  UNION ALL SELECT 3, '03 nao mayhem', count(*) FILTER (WHERE a02),
         count(DISTINCT mint) FILTER (WHERE a02) FROM acc
  UNION ALL SELECT 4, '04 idade 30-300 s', count(*) FILTER (WHERE a03),
         count(DISTINCT mint) FILTER (WHERE a03) FROM acc
  UNION ALL SELECT 5, '05 progresso 5-50 %', count(*) FILTER (WHERE a04),
         count(DISTINCT mint) FILTER (WHERE a04) FROM acc
  UNION ALL SELECT 6, '06 criador nao vendedor', count(*) FILTER (WHERE a05),
         count(DISTINCT mint) FILTER (WHERE a05) FROM acc
  UNION ALL SELECT 7, '07 participacao <= 1 % (vol60s >= 5 SOL)', count(*) FILTER (WHERE a06),
         count(DISTINCT mint) FILTER (WHERE a06) FROM acc
  UNION ALL SELECT 8, '08 dev_share <= 0.10 (unknown refusa)', count(*) FILTER (WHERE a07),
         count(DISTINCT mint) FILTER (WHERE a07) FROM acc
  UNION ALL SELECT 9, '09 snipers 21-1000', count(*) FILTER (WHERE a08),
         count(DISTINCT mint) FILTER (WHERE a08) FROM acc
  UNION ALL SELECT 10, '10 fluxo positivo', count(*) FILTER (WHERE a09),
         count(DISTINCT mint) FILTER (WHERE a09) FROM acc
  UNION ALL SELECT 11, '11 compradores unicos >= 10', count(*) FILTER (WHERE a10),
         count(DISTINCT mint) FILTER (WHERE a10) FROM acc
  UNION ALL SELECT 12, '12 sells/buys <= 0.6', count(*) FILTER (WHERE a11),
         count(DISTINCT mint) FILTER (WHERE a11) FROM acc
  UNION ALL SELECT 13, '13 holders >= 20 (sobreviventes)', count(*) FILTER (WHERE a12),
         count(DISTINCT mint) FILTER (WHERE a12) FROM acc
) f ORDER BY ord;
