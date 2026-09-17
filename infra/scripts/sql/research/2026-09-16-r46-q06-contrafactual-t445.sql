-- R46 q06: contrafactual T4.45 sobre as 9 moedas recusadas por creator_flow_unknown na janela [19:25, 22:25) BRT
-- Parte B (fluxo do criador pela cadeia): aproximado pela fita (meme_trades, trader = criador) -- o que a ATA diria.
-- Parte A (retrato sob demanda): o retrato mais proximo (antes ou depois) da 1a ordem, e o veredito bundle <= 20 % / top10 <= 25 %.
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
WITH o AS (
  SELECT p.mint, min(o.received_at) AS primeira_ordem, count(*) AS ordens, string_agg(DISTINCT o.reason, ',') AS motivos,
    min((p.quote->>'curve_progress_pct')::numeric) AS prog_quote_min
  FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
  WHERE o.received_at >= timestamptz '2026-09-16 19:25-03' AND o.received_at < timestamptz '2026-09-16 22:25-03' AND o.side='buy'
  GROUP BY 1
), ct AS (
  SELECT o.mint, count(*) FILTER (WHERE tr.side='buy') AS cr_buys, count(*) FILTER (WHERE tr.side='sell') AS cr_sells,
    round(sum(tr.sol_lamports) FILTER (WHERE tr.side='buy')/1e9,3) AS cr_buy_sol, round(sum(tr.sol_lamports) FILTER (WHERE tr.side='sell')/1e9,3) AS cr_sell_sol,
    min(tr.block_time) FILTER (WHERE tr.side='sell') AS cr_first_sell,
    min(tr.block_time) AS fita_inicio, count(*) AS fita_n
  FROM o JOIN meme_tokens t ON t.mint=o.mint LEFT JOIN meme_trades tr ON tr.mint=o.mint AND tr.trader=t.creator
    AND tr.block_time >= timestamptz '2026-09-16 19:00-03' AND tr.block_time < timestamptz '2026-09-16 22:30-03'
  GROUP BY 1
), fita AS (
  SELECT o.mint, min(tr.block_time) AS fita_inicio, count(*) AS fita_n, count(DISTINCT tr.trader) FILTER (WHERE tr.side='buy') AS compradores
  FROM o JOIN meme_trades tr ON tr.mint=o.mint AND tr.block_time >= timestamptz '2026-09-16 19:00-03' AND tr.block_time < timestamptz '2026-09-16 22:30-03' GROUP BY 1
), rk AS (
  SELECT DISTINCT ON (o.mint) o.mint, r.observed_at, r.bundled_share, r.top10_share, r.holders, r.snipers, r.dev_share,
    extract(epoch FROM (r.observed_at - o.primeira_ordem))::int AS delta_s
  FROM o JOIN meme_risk_snapshots r ON r.mint=o.mint AND r.observed_at BETWEEN o.primeira_ordem - interval '600 seconds' AND o.primeira_ordem + interval '600 seconds'
  ORDER BY o.mint, abs(extract(epoch FROM (r.observed_at - o.primeira_ordem)))
), ch AS (
  SELECT o.mint, max(c.real_sol_reserves) FILTER (WHERE c.observed_at <= o.primeira_ordem) AS rsol_antes_max,
    max(c.real_sol_reserves) FILTER (WHERE c.observed_at > o.primeira_ordem AND c.observed_at <= o.primeira_ordem + interval '30 minutes') AS rmax30,
    min(c.real_sol_reserves) FILTER (WHERE c.observed_at > o.primeira_ordem AND c.observed_at <= o.primeira_ordem + interval '30 minutes') AS rmin30
  FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at >= timestamptz '2026-09-16 19:00-03' GROUP BY 1
), ent AS (
  SELECT DISTINCT ON (o.mint) o.mint, c.real_sol_reserves AS rsol0 FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at <= o.primeira_ordem AND c.observed_at >= timestamptz '2026-09-16 19:00-03' ORDER BY o.mint, c.observed_at DESC
)
SELECT 'cf' AS q, to_char(o.primeira_ordem AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS primeira_ordem, coalesce(t.symbol,'?') AS symbol, left(o.mint,8) AS mint8,
  o.ordens, o.motivos, round(o.prog_quote_min,1) AS prog_quote_min,
  left(t.creator,6) AS criador, ct.cr_buys, ct.cr_sells, ct.cr_buy_sol, ct.cr_sell_sol,
  coalesce(to_char(ct.cr_first_sell AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS'),'-') AS cr_1a_venda,
  CASE WHEN ct.cr_first_sell IS NOT NULL AND ct.cr_first_sell <= o.primeira_ordem THEN 'vendeu_antes' WHEN ct.cr_first_sell IS NOT NULL THEN 'vendeu_depois' ELSE 'nao_vendeu_na_fita' END AS fluxo_criador,
  to_char(fita.fita_inicio AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS fita_desde, fita.fita_n, fita.compradores,
  round(rk.bundled_share*100,1) AS bundle, round(rk.top10_share*100,1) AS top10, rk.holders AS r_holders, rk.snipers AS r_snipers, round(rk.dev_share*100,1) AS r_dev, rk.delta_s AS retrato_delta_s,
  CASE WHEN rk.mint IS NULL THEN 'sem_retrato_600s'
       WHEN (ct.cr_first_sell IS NOT NULL AND ct.cr_first_sell <= o.primeira_ordem) THEN 'recusa:creator_net_seller'
       WHEN rk.bundled_share > 0.20 THEN 'recusa:bundle'
       WHEN rk.top10_share > 0.25 THEN 'recusa:top10'
       WHEN o.prog_quote_min > 50 THEN 'recusa:progress'
       ELSE 'ADMITIRIA' END AS veredito_t445,
  round(ent.rsol0,3) AS rsol0, round(ch.rmax30,3) AS rmax30, round(ch.rmin30,3) AS rmin30,
  CASE WHEN ch.rmax30 >= 1.5*ent.rsol0 THEN 'subiu>=50%' ELSE '-' END AS subiu, CASE WHEN ch.rmin30 <= 0.5*ent.rsol0 THEN 'caiu>=50%' ELSE '-' END AS caiu
FROM o JOIN meme_tokens t ON t.mint=o.mint LEFT JOIN ct ON ct.mint=o.mint LEFT JOIN fita ON fita.mint=o.mint LEFT JOIN rk ON rk.mint=o.mint LEFT JOIN ch ON ch.mint=o.mint LEFT JOIN ent ON ent.mint=o.mint
ORDER BY o.primeira_ordem;
-- heartbeat do executor (ultimo)
