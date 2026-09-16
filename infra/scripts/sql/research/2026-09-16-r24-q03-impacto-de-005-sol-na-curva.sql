-- KB-0112 Q03 — o impacto REAL de uma compra de 0,05 SOL na bonding curve, em forma
-- fechada (nao le tabela nenhuma). Reuso literal da formula do t429b-q02:
--   impacto = SOL pre-taxa / virtual_sol_reserves ; vsol = V0_sol*V0_tok/(V0_tok - R0*t)
--   V0_sol = 30, V0_tok = 1 073 000 000, R0 = 793 100 000, taxa de curva 1,25 %.
-- Responde: em qual progresso o teto de impacto de 0,5 % (RISK_ENGINE_MEME 3.1) morde
-- uma ordem de 0,05 SOL. Resposta: em nenhum — o maximo possivel e t -> 0.
WITH p AS (SELECT 30.0::numeric v0sol, 1073000000.0::numeric v0tok,
                  793100000.0::numeric r0, 0.0125::numeric fee, 0.05::numeric x),
t AS (SELECT unnest(ARRAY[0.00,0.02,0.05,0.10,0.20,0.30,0.50,0.75,0.95]::numeric[]) AS prog)
SELECT round(100*t.prog, 2) AS progresso_pct,
       round(p.v0sol*p.v0tok/(p.v0tok - p.r0*t.prog), 3) AS vsol,
       round(100 * (p.x/(1+p.fee)) / (p.v0sol*p.v0tok/(p.v0tok - p.r0*t.prog)), 4) AS impacto_pct,
       CASE WHEN (p.x/(1+p.fee)) / (p.v0sol*p.v0tok/(p.v0tok - p.r0*t.prog)) <= 0.005
            THEN $$passa$$ ELSE $$recusa impact_above_cap$$ END AS veredito_teto_05,
       round(0.01 * 5.0, 4) AS part_1pct_em_5sol_de_volume,
       round(p.x / 0.01, 2) AS volume_1m_min_para_teto_1pct,
       round(p.x / 0.005, 2) AS volume_1m_min_para_teto_05pct
FROM p CROSS JOIN t ORDER BY t.prog;
