-- KB-0099 Q01 — funil da porta operator/5 (E1 braco 2), por dia BRT.
-- Conta moedas DISTINTAS que sobrevivem a cada passo, na ordem de
-- evaluate_entry() (packages/indicators/hunter_indicators/meme/rules.py) e,
-- no fim, o pedigree (pedigree.py). Sobreviver = existir ao menos UMA foto
-- de 15 s, com idade 30-300 s, que satisfaca todos os criterios ate ali.
-- Unidades: meme_features_15s.curve_progress_pct e FRACAO (0-1).
-- Parametros de operator/5 (meme_rule_sets, id ...0011):
--   idade 30-300 s, progresso 5-50 %, participacao <= 1 % de 0,05 SOL
--   (=> curve_volume_60s_sol >= 5), dev <= 10 %, snipers <= 10,
--   fluxo > 0, compradores >= 10, vendas/compras <= 0,6, holders >= 20
--   nao caindo, progresso (ou mcap) subindo, pedigree.
-- Uso: psql -v dia=2026-09-15 -f este-arquivo.sql
SET statement_timeout = 60000;

WITH linhas AS (
  SELECT f.mint, f.as_of,
         f.curve_progress_pct, f.progress_rising, f.mcap_delta_60s,
         f.holders, f.holders_prev, f.holders_rising,
         f.buys_60s, f.sells_60s, f.unique_buyers_60s, f.net_sol_flow_60s,
         f.curve_volume_60s_sol, f.creator_net_seller, f.dev_share, f.snipers,
         t.mayhem_enabled, t.completed_at, t.migrated_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
), c AS (
  SELECT mint,
    (completed_at IS NULL OR completed_at > as_of)
      AND (migrated_at IS NULL OR migrated_at > as_of)          AS c01_curva_viva,
    (mayhem_enabled IS NOT NULL AND NOT mayhem_enabled)          AS c02_nao_mayhem,
    (curve_progress_pct IS NOT NULL
      AND curve_progress_pct >= 0.05 AND curve_progress_pct <= 0.50) AS c03_progresso,
    (creator_net_seller IS FALSE
      OR (creator_net_seller IS NULL AND dev_share IS NOT NULL AND dev_share <= 0.10)) AS c04_criador,
    (curve_volume_60s_sol IS NOT NULL AND curve_volume_60s_sol >= 5) AS c05_participacao,
    (dev_share IS NOT NULL AND dev_share <= 0.10)                AS c06_dev,
    (snipers IS NOT NULL AND snipers <= 10)                      AS c07_snipers,
    (CASE WHEN net_sol_flow_60s IS NOT NULL THEN net_sol_flow_60s > 0
          WHEN mcap_delta_60s IS NOT NULL THEN mcap_delta_60s > 0
          ELSE false END)                                        AS c08_fluxo,
    (unique_buyers_60s IS NOT NULL AND unique_buyers_60s >= 10)  AS c09_compradores,
    (buys_60s IS NOT NULL AND sells_60s IS NOT NULL AND buys_60s > 0
      AND sells_60s::numeric / buys_60s <= 0.6)                  AS c10_razao,
    (holders IS NOT NULL AND holders >= 20)                      AS c11_holders,
    (holders_rising IS NOT NULL
      AND (holders_rising
           OR (holders IS NOT NULL AND holders_prev IS NOT NULL
               AND holders >= holders_prev)))                    AS c12_holders_subindo,
    (progress_rising IS TRUE OR mcap_delta_60s > 0)              AS c13_progresso_subindo
  FROM linhas
), cum AS (
  SELECT mint,
    bool_or(c01_curva_viva) AS s01,
    bool_or(c01_curva_viva AND c02_nao_mayhem) AS s02,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso) AS s03,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador) AS s04,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao) AS s05,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao AND c06_dev) AS s06,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao AND c06_dev AND c07_snipers) AS s07,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao AND c06_dev AND c07_snipers AND c08_fluxo) AS s08,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao AND c06_dev AND c07_snipers AND c08_fluxo
            AND c09_compradores) AS s09,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao AND c06_dev AND c07_snipers AND c08_fluxo
            AND c09_compradores AND c10_razao) AS s10,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao AND c06_dev AND c07_snipers AND c08_fluxo
            AND c09_compradores AND c10_razao AND c11_holders) AS s11,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao AND c06_dev AND c07_snipers AND c08_fluxo
            AND c09_compradores AND c10_razao AND c11_holders
            AND c12_holders_subindo) AS s12,
    bool_or(c01_curva_viva AND c02_nao_mayhem AND c03_progresso AND c04_criador
            AND c05_participacao AND c06_dev AND c07_snipers AND c08_fluxo
            AND c09_compradores AND c10_razao AND c11_holders
            AND c12_holders_subindo AND c13_progresso_subindo) AS s13
  FROM c GROUP BY mint
)
SELECT :'dia' AS dia, passo, moedas,
       round(100.0 * (1 - moedas::numeric / NULLIF(lag(moedas) OVER (ORDER BY ord), 0)), 1)
         AS morte_marginal_pct
FROM (
  SELECT 0 AS ord, '00 universo (foto 15s, idade 30-300 s)' AS passo, count(*) AS moedas FROM cum
  UNION ALL SELECT 1, '01 curva viva (nao completa/migrada)', count(*) FILTER (WHERE s01) FROM cum
  UNION ALL SELECT 2, '02 nao Mayhem (flag lida)',            count(*) FILTER (WHERE s02) FROM cum
  UNION ALL SELECT 3, '03 progresso 5-50 %',                  count(*) FILTER (WHERE s03) FROM cum
  UNION ALL SELECT 4, '04 criador nao vendedor liquido',      count(*) FILTER (WHERE s04) FROM cum
  UNION ALL SELECT 5, '05 participacao <= 1 % (vol60s >= 5 SOL)', count(*) FILTER (WHERE s05) FROM cum
  UNION ALL SELECT 6, '06 dev <= 10 %',                       count(*) FILTER (WHERE s06) FROM cum
  UNION ALL SELECT 7, '07 snipers <= 10',                     count(*) FILTER (WHERE s07) FROM cum
  UNION ALL SELECT 8, '08 fluxo liquido > 0',                 count(*) FILTER (WHERE s08) FROM cum
  UNION ALL SELECT 9, '09 compradores unicos >= 10',          count(*) FILTER (WHERE s09) FROM cum
  UNION ALL SELECT 10, '10 vendas/compras <= 0,6',            count(*) FILTER (WHERE s10) FROM cum
  UNION ALL SELECT 11, '11 holders >= 20',                    count(*) FILTER (WHERE s11) FROM cum
  UNION ALL SELECT 12, '12 holders nao caindo',               count(*) FILTER (WHERE s12) FROM cum
  UNION ALL SELECT 13, '13 progresso (ou mcap) subindo',      count(*) FILTER (WHERE s13) FROM cum
) f
ORDER BY ord;
