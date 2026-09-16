-- T4.29b — q06: o teto de impacto MEDIDO nas reservas observadas (nao derivado do progresso).
-- impacto = sol_pre_taxa / virtual_sol_reserves (ver q02), logo o teto de impacto de 0,5 %
-- admite uma compra de X SOL (total, taxa 1,25 % incluida) exatamente quando
--   virtual_sol_reserves >= X / (1,0125 * 0,005).
-- Universo: meme_curve_snapshots das ultimas 48 h (tabela grande: janela curta de proposito),
-- moedas NAO-Mayhem. As reservas estao em SOL/tokens humanos nesta tabela (nao lamports).
-- A coluna real_sol_reserves das linhas com vsol alto responde se aquela profundidade e
-- dinheiro de comprador ou SOL virtual injetado (KB-0098 secao 5).
SELECT count(*)                                                              AS fotos,
       count(DISTINCT mint)                                                  AS moedas,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY virtual_sol_reserves)::numeric, 3) AS vsol_p50,
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY virtual_sol_reserves)::numeric, 3) AS vsol_p99,
       round(max(virtual_sol_reserves)::numeric, 3)                          AS vsol_max,
       count(*) FILTER (WHERE virtual_sol_reserves >= 0.05/(1.0125*0.005))   AS adm_005,
       count(*) FILTER (WHERE virtual_sol_reserves >= 0.25/(1.0125*0.005))   AS adm_025,
       count(*) FILTER (WHERE virtual_sol_reserves >= 1.0/(1.0125*0.005))    AS adm_1,
       count(DISTINCT mint) FILTER (WHERE virtual_sol_reserves >= 1.0/(1.0125*0.005)) AS moedas_adm_1,
       count(*) FILTER (WHERE virtual_sol_reserves >= 9.8/(1.0125*0.005))    AS adm_98,
       round(max(real_sol_reserves) FILTER (WHERE virtual_sol_reserves >= 1.0/(1.0125*0.005))::numeric, 3) AS real_sol_max_nos_adm_1,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY real_sol_reserves)
             FILTER (WHERE virtual_sol_reserves >= 1.0/(1.0125*0.005))::numeric, 3) AS real_sol_p50_nos_adm_1
FROM meme_curve_snapshots
WHERE observed_at >= now() - make_interval(days => 2)
  AND coalesce(mayhem_enabled, false) = false
