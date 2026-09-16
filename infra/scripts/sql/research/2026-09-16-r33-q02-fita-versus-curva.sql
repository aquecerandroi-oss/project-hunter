-- Coorte comum das quatro consultas da R33 (16/09/2026, 19:00-22:00 UTC = 16:00-19:00 BRT;
-- na pratica a serie acaba as 20:35 UTC = 17:35 BRT, o relogio da medicao).
-- "voltou ao piso" = pico de mcap_sol >= 40 SOL e a ULTIMA foto com mcap_sol <= 28,5 e
-- curve_progress_pct < 0,05 (fracao). drop_time = a primeira foto <= 28,5 depois do pico.
SET statement_timeout = 60000;
CREATE TEMP TABLE coh AS
WITH w AS (
  SELECT mint, end_time, mcap_sol, curve_progress_pct
  FROM meme_features_1m
  WHERE end_time >= timestamptz '2026-09-16 19:00:00+00'
    AND end_time <  timestamptz '2026-09-16 22:00:00+00'
    AND mcap_sol IS NOT NULL
), agg AS (
  SELECT mint, max(mcap_sol) AS peak FROM w GROUP BY mint HAVING max(mcap_sol) >= 40
), pk AS (
  SELECT DISTINCT ON (w.mint) w.mint, w.end_time AS peak_t, w.mcap_sol AS peak
  FROM w JOIN agg USING (mint) ORDER BY w.mint, w.mcap_sol DESC, w.end_time
), lst AS (
  SELECT DISTINCT ON (mint) mint, end_time AS last_t, mcap_sol AS last_mcap,
         curve_progress_pct AS last_prog
  FROM w ORDER BY mint, end_time DESC
), d AS (
  SELECT DISTINCT ON (w.mint) w.mint, w.end_time AS drop_time, w.mcap_sol AS drop_mcap
  FROM w JOIN pk ON pk.mint = w.mint
  WHERE w.end_time > pk.peak_t AND w.mcap_sol <= 28.5
  ORDER BY w.mint, w.end_time
)
SELECT pk.mint, pk.peak, pk.peak_t, l.last_t, l.last_mcap, l.last_prog, d.drop_time, d.drop_mcap,
       CASE WHEN l.last_mcap <= 28.5 AND l.last_prog < 0.05 THEN 'floor' ELSE 'no_floor' END AS cohort
FROM pk JOIN lst l USING (mint) LEFT JOIN d USING (mint);
CREATE INDEX ON coh (mint);

-- Q02: o SOL que saiu da curva (cadeia, meme_curve_snapshots.real_sol_reserves lido por
-- solana_rpc) versus o SOL que a fita (meme_trades) registra saindo, na janela
-- [pico - 1 min, queda + 3 min]. Se a "volta ao piso" fosse artefato da serie, a cadeia
-- nao mostraria a curva vazia; se a fita cobrisse, frac_explicada ficaria perto de 1.
WITH rs AS (
  SELECT c.mint, c.peak_t, c.drop_time,
    (SELECT max(s.real_sol_reserves) FROM meme_curve_snapshots s
      WHERE s.mint = c.mint AND s.source = 'solana_rpc'
        AND s.observed_at BETWEEN c.peak_t - interval '60 seconds'
                              AND c.peak_t + interval '60 seconds') AS rs_pico,
    (SELECT min(s.real_sol_reserves) FROM meme_curve_snapshots s
      WHERE s.mint = c.mint AND s.source = 'solana_rpc'
        AND s.observed_at BETWEEN c.drop_time - interval '60 seconds'
                              AND c.drop_time + interval '120 seconds') AS rs_queda
  FROM coh c WHERE c.cohort = 'floor' AND c.drop_time IS NOT NULL
), tr AS (
  SELECT c.mint,
    sum(CASE WHEN t.side = 'sell' THEN t.sol_lamports ELSE 0 END)/1e9 AS vendido,
    sum(CASE WHEN t.side = 'buy'  THEN t.sol_lamports ELSE 0 END)/1e9 AS comprado,
    count(t.*) AS n_trades
  FROM coh c LEFT JOIN meme_trades t ON t.mint = c.mint
    AND t.block_time >= c.peak_t - interval '60 seconds'
    AND t.block_time <  c.drop_time + interval '3 minutes'
  WHERE c.cohort = 'floor' AND c.drop_time IS NOT NULL GROUP BY 1
)
SELECT count(*) AS mints,
  count(*) FILTER (WHERE tr.n_trades > 0) AS com_fita,
  count(*) FILTER (WHERE rs.rs_queda <= 0.5) AS cadeia_diz_vazia,
  round(avg(rs.rs_pico),2) AS real_sol_no_pico,
  round(avg(rs.rs_queda),3) AS real_sol_na_queda,
  round(avg(rs.rs_pico - rs.rs_queda),2) AS sol_que_saiu_da_curva,
  round(avg(tr.vendido - tr.comprado),2) AS saida_liquida_na_fita,
  round(sum(tr.vendido - tr.comprado)/NULLIF(sum(rs.rs_pico - rs.rs_queda),0),3) AS frac_explicada,
  count(*) FILTER (WHERE (tr.vendido - tr.comprado) >= 0.8*(rs.rs_pico - rs.rs_queda)) AS n_fita_explica_80pct
FROM rs LEFT JOIN tr USING (mint);

-- O caso NIKKI, linha a linha: 42,38 -> 0,65 SOL reais em 16 s (51 slots), mesma conta,
-- mesmo commitment; e a fita da vida inteira da moeda, para comparar.
SELECT s.observed_at, s.slot, s.source, s.commitment,
       round(s.virtual_sol_reserves,3) AS vsol, round(s.real_sol_reserves,4) AS rsol,
       round(s.mcap_sol,2) AS mcap
FROM meme_curve_snapshots s
WHERE s.mint = 'AYrp8o5erJicGEHUHQfPZ4oF47sj3uBvzfQBtUdCpump'
  AND s.observed_at BETWEEN timestamptz '2026-09-16 20:24:00+00'
                        AND timestamptz '2026-09-16 20:26:30+00'
ORDER BY s.observed_at;

SELECT sum(CASE WHEN side = 'buy' THEN sol_lamports ELSE 0 END)/1e9 AS comprado_vida_toda,
       sum(CASE WHEN side = 'sell' THEN sol_lamports ELSE 0 END)/1e9 AS vendido_vida_toda,
       count(*) AS n_trades, min(block_time) AS t0, max(block_time) AS t1
FROM meme_trades WHERE mint = 'AYrp8o5erJicGEHUHQfPZ4oF47sj3uBvzfQBtUdCpump';
