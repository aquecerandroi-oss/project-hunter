-- T4.29b — q02: o teto de impacto na curva, em forma fechada (nao le tabela nenhuma).
--
-- FORMULA (derivada de packages/exchange-adapters/hunter_exchanges/pumpfun/quote.py):
--   buy_cost: s = floor(a*vsol/(vtok-a)) + 1  ->  produto constante vsol*vtok = k
--   impacto (preco medio do fill / preco marginal anterior - 1) = a/(vtok-a) = s/vsol
--   ou seja: IMPACTO = SOL PRE-TAXA DA COMPRA / RESERVA VIRTUAL DE SOL.
--   Com a taxa da curva (1,25 % = 95 bps protocolo + 30 bps criador), o total que sai da
--   carteira e s*(1+fee), entao o teto em SOL total = max_impact * vsol * (1 + fee)
--   -- exatamente o cap impact de packages/risk-core/hunter_risk_meme/sizing.py.
--
-- Estado da curva padrao (GlobalParams do registro 2025-07-18, docs/PUMPFUN-ONCHAIN.md 1.2):
--   V0_sol = 30 SOL, V0_tok = 1 073 000 000, R0 = 793 100 000, taxa 1,25 %.
--   progresso t = 1 - real_token/R0  ->  vtok = V0_tok - R0*t ; vsol = V0_sol*V0_tok/vtok
--   real_sol = vsol - 30 ; graduacao em t = 1: vsol = 115,005359057, real_sol = 85,005359057.
-- Logo o real_sol NECESSARIO para uma compra de X SOL ficar sob um teto de impacto p e
--   real_sol >= X / (1,0125 * p) - 30, e o progresso minimo correspondente e
--   t = (V0_tok - V0_sol*V0_tok/vsol) / R0.
WITH params AS (SELECT 30.0::numeric v0sol, 1073000000.0::numeric v0tok,
                       793100000.0::numeric r0, 0.0125::numeric fee),
size AS (SELECT unnest(ARRAY[0.05,0.10,0.25,0.50,1.0,2.0,5.0,9.8]::numeric[]) AS x),
cap  AS (SELECT unnest(ARRAY[0.005,0.01,0.05]::numeric[]) AS p),
need AS (SELECT s.x, c.p, pr.*, s.x / ((1 + pr.fee) * c.p) AS vsol_need
         FROM size s CROSS JOIN cap c CROSS JOIN params pr)
SELECT x                                      AS compra_sol,
       p                                      AS teto_impacto,
       round(vsol_need, 2)                    AS vsol_necessario,
       round(vsol_need - v0sol, 2)            AS real_sol_necessario,
       CASE WHEN vsol_need <= v0sol THEN 0
            WHEN vsol_need > v0sol*v0tok/(v0tok-r0) THEN NULL
            ELSE round(100*(v0tok - v0sol*v0tok/vsol_need)/r0, 2) END AS progresso_min_pct,
       CASE WHEN vsol_need <= v0sol THEN $$cabe em qualquer curva$$
            WHEN vsol_need > v0sol*v0tok/(v0tok-r0) THEN $$IMPOSSIVEL na curva$$
            ELSE $$so acima do progresso indicado$$ END AS veredito
FROM need ORDER BY x, p
