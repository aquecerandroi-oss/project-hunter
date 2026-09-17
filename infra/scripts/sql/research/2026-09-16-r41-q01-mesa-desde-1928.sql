-- R41 16/09 21h32 BRT -- a mesa desde 19:28:44 BRT (fim do balanco R39): propostas, ordens reais,
-- motivo da recusa e DESFECHO PELA CADEIA (meme_curve_snapshots.real_sol_reserves), nunca mcap_sol
-- nem a fita -- KB-0115. Reuso do r35-q01 (corte movido) + classificacao boa/ruim/neutra do r39-q02.
-- Unidades: curve_progress_pct e FRACAO 0-1. Horas em America/Sao_Paulo (BRT = UTC-3).
SET statement_timeout = 200000;

-- (a) ordens reais desde 19:28:45 BRT + prog da feature de 15 s e do admissor
WITH o AS (
  SELECT o.id, o.received_at, o.side, o.status, o.reason, o.tx_signature, o.admission, p.mint
  FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
  WHERE o.received_at > timestamptz $$2026-09-16 19:28:44-03$$
), chk AS (
  SELECT o.id,
    max(CASE WHEN c->>$$name$$=$$curve_progress$$ THEN (c->>$$value$$)::numeric END) AS prog_adm,
    max(CASE WHEN c->>$$name$$=$$bundled_share$$ THEN (c->>$$value$$)::numeric END) AS bundle_adm,
    max(CASE WHEN c->>$$name$$=$$top10_share$$   THEN (c->>$$value$$)::numeric END) AS top10_adm
  FROM o, LATERAL jsonb_array_elements(o.admission->$$checks$$) c GROUP BY 1
), f AS (
  SELECT DISTINCT ON (o.id) o.id, x.curve_progress_pct, x.holders, x.unique_buyers_60s,
         x.snipers, x.net_sol_flow_60s
  FROM o JOIN meme_features_15s x ON x.mint=o.mint AND x.as_of <= o.received_at
  ORDER BY o.id, x.as_of DESC
), ent AS (
  SELECT DISTINCT ON (o.id) o.id, c.real_sol_reserves AS rsol0,
         c.virtual_sol_reserves - c.real_sol_reserves AS inv0
  FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at <= o.received_at
  ORDER BY o.id, c.observed_at DESC
), w AS (
  SELECT o.id, c.observed_at, c.real_sol_reserves AS rsol, c.complete
  FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint
   AND c.observed_at > o.received_at AND c.observed_at <= o.received_at + make_interval(mins => 30)
), ag AS (
  SELECT id, count(*) AS n, min(rsol) AS rmin, max(rsol) AS rmax, bool_or(complete) AS graduou
  FROM w GROUP BY 1
), ev AS (
  SELECT w.id, min(CASE WHEN w.rsol <= 0.5*e.rsol0 THEN w.observed_at END) AS t_queda50,
         min(CASE WHEN w.rsol >= 1.5*e.rsol0 THEN w.observed_at END) AS t_alta50
  FROM w JOIN ent e ON e.id=w.id GROUP BY 1
)
SELECT to_char(o.received_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  coalesce(t.symbol,$$?$$) AS symbol, left(o.mint,6) AS mint6, o.status,
  coalesce(o.reason,$$-$$) AS motivo, coalesce(o.tx_signature,$$-$$) AS tx,
  round(f.curve_progress_pct*100,1) AS prog15s, round(chk.prog_adm*100,2) AS prog_adm,
  round(chk.bundle_adm*100,2) AS bundle_adm, f.holders, f.unique_buyers_60s AS compr,
  f.snipers, round(f.net_sol_flow_60s,2) AS fluxo,
  round(ent.rsol0,3) AS rsol_na_ordem, round(ent.inv0,3) AS invariante,
  coalesce(ag.n,0) AS fotos_30m, round(ag.rmin,3) AS rsol_min30, round(ag.rmax,3) AS rsol_max30,
  coalesce(to_char(ev.t_queda50 AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$),$$-$$) AS t_queda50,
  coalesce(to_char(ev.t_alta50  AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$),$$-$$) AS t_alta50,
  coalesce(ag.graduou,false) AS graduou,
  extract(epoch FROM (o.received_at + make_interval(mins => 30) - now()))::int AS janela_restante_s
FROM o LEFT JOIN meme_tokens t ON t.mint=o.mint
  LEFT JOIN chk ON chk.id=o.id LEFT JOIN f ON f.id=o.id LEFT JOIN ent ON ent.id=o.id
  LEFT JOIN ag ON ag.id=o.id LEFT JOIN ev ON ev.id=o.id
ORDER BY o.received_at;
