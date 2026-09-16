-- R14 16/09 17h — o que as 8 do topo fizeram depois (serie de 1 min) e a fatia do maior
-- comprador na fita (meme_trades), o eixo de "forjada" da KB-0103 (>= 35 % = forjada).
-- ATENCAO (pegadinhas de esquema): meme_features_1m usa end_time (nao as_of) e net_sol_flow_1m;
-- meme_trades usa sol_lamports + side (nao sol_amount / is_buy).

-- (a) foto de 1 min mais recente de cada uma
WITH alvo(m6) AS (VALUES ($$9NxLFF$$),($$CN9Pp6$$),($$5pjWRa$$),($$4kFCJ4$$),
                         ($$2hzaTD$$),($$Ei83DQ$$),($$GSPimR$$),($$BXJ9f9$$)),
mm AS (SELECT t.mint, t.symbol FROM meme_tokens t JOIN alvo a ON left(t.mint,6)=a.m6),
dep AS (
  SELECT DISTINCT ON (f.mint) f.mint, f.curve_progress_pct, f.holders, f.top10_share,
         f.net_sol_flow_1m, f.creator_sold, f.mcap_sol, f.end_time
  FROM meme_features_1m f JOIN mm ON mm.mint=f.mint
  WHERE f.end_time >= now() - make_interval(mins => 75)
  ORDER BY f.mint, f.end_time DESC
)
SELECT mm.symbol, left(mm.mint,6), round(dep.curve_progress_pct*100,1), dep.holders,
  round(dep.top10_share*100,1), round(dep.net_sol_flow_1m,2), round(dep.mcap_sol,1),
  dep.creator_sold, to_char(dep.end_time AT TIME ZONE $$America/Sao_Paulo$$, $$HH24:MI$$)
FROM mm LEFT JOIN dep ON dep.mint=mm.mint;

-- (b) fatia do maior comprador (fita de 90 min)
WITH alvo(m6) AS (VALUES ($$9NxLFF$$),($$CN9Pp6$$),($$5pjWRa$$),($$4kFCJ4$$),
                         ($$2hzaTD$$),($$Ei83DQ$$),($$GSPimR$$),($$BXJ9f9$$)),
mm AS (SELECT t.mint, t.symbol FROM meme_tokens t JOIN alvo a ON left(t.mint,6)=a.m6),
tr AS (SELECT r.mint, r.trader, sum(r.sol_lamports)/1e9 AS sol
       FROM meme_trades r JOIN mm ON mm.mint=r.mint
       WHERE r.side=$$buy$$ AND r.block_time >= now() - make_interval(mins => 90)
       GROUP BY 1,2),
tot AS (SELECT mint, sum(sol) AS total, count(*) AS n FROM tr GROUP BY 1),
mx AS (SELECT DISTINCT ON (mint) mint, sol FROM tr ORDER BY mint, sol DESC)
SELECT mm.symbol, left(mm.mint,6), tot.n AS compradores_fita, round(tot.total::numeric,2) AS sol_comprado,
  round(mx.sol::numeric,2) AS maior_sol, round(100*mx.sol/nullif(tot.total,0)::numeric,1) AS maior_pct
FROM mm LEFT JOIN tot ON tot.mint=mm.mint LEFT JOIN mx ON mx.mint=mm.mint
ORDER BY 6 DESC NULLS LAST;

-- (c) a porta calibrada (operator/5 EM VIGOR: holders >= 20, compradores >= 10, sells/buys <= 0,6,
--     snipers <= 25, dev <= 10 %, progresso 5-50 %, sem exigir "subindo") contra a porta anterior
--     (operator/4, aposentada: snipers <= 10, exige holders_rising E progress_rising, progresso 5-100 %)
--     e contra o piso de snipers da KB-0101 (min_snipers >= 11, sem teto).
WITH j AS (
  SELECT f.* FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 60) AND f.age_s BETWEEN 30 AND 300
)
SELECT
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.02 AND 0.50) AS jan_radar,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.02 AND 0.50 AND tape_reason IS NULL) AS com_fita,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.02 AND 0.50 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0) AS fluxo_pos,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10
        AND snipers IS NOT NULL AND snipers <= 25 AND dev_share IS NOT NULL AND dev_share <= 0.10
        AND (sells_60s::numeric/nullif(buys_60s,0)) <= 0.6) AS op5_calibrada,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 1.00 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10
        AND snipers IS NOT NULL AND snipers <= 10 AND dev_share IS NOT NULL AND dev_share <= 0.10
        AND (sells_60s::numeric/nullif(buys_60s,0)) <= 0.6
        AND holders_rising IS TRUE AND progress_rising IS TRUE) AS op4_antiga,
  count(DISTINCT mint) FILTER (WHERE curve_progress_pct BETWEEN 0.05 AND 0.50 AND tape_reason IS NULL
        AND net_sol_flow_60s > 0 AND holders >= 20 AND unique_buyers_60s >= 10
        AND snipers IS NOT NULL AND snipers >= 11 AND dev_share IS NOT NULL AND dev_share <= 0.10
        AND (sells_60s::numeric/nullif(buys_60s,0)) <= 0.6) AS com_piso_11
FROM j;

-- (d) as que a porta calibrada teria proposto, nominais (primeira foto que passa)
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 60) AND f.age_s BETWEEN 30 AND 300
    AND f.curve_progress_pct BETWEEN 0.05 AND 0.50 AND f.tape_reason IS NULL
    AND f.net_sol_flow_60s > 0 AND f.holders >= 20 AND f.unique_buyers_60s >= 10
    AND f.snipers <= 25 AND f.dev_share <= 0.10
    AND (f.sells_60s::numeric/nullif(f.buys_60s,0)) <= 0.6
  ORDER BY f.mint, f.as_of
)
SELECT t.symbol, left(j.mint,6), j.age_s, round(j.curve_progress_pct*100,1), j.holders,
  j.unique_buyers_60s, j.buys_60s, j.sells_60s, round(j.net_sol_flow_60s,2), j.snipers,
  left(t.creator,6),
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=t.creator
     AND t2.created_at >= now() - make_interval(days => 7)),
  t.completed_at IS NOT NULL,
  to_char(j.as_of AT TIME ZONE $$America/Sao_Paulo$$, $$HH24:MI:SS$$)
FROM j JOIN meme_tokens t ON t.mint=j.mint ORDER BY j.as_of;

-- (e) o que a mesa real produziu na mesma hora (meme_proposals usa proposed_at, nao created_at)
SELECT p.mint, t.symbol, p.status, p.refusal,
  to_char(p.proposed_at AT TIME ZONE $$America/Sao_Paulo$$, $$HH24:MI:SS$$)
FROM meme_proposals p LEFT JOIN meme_tokens t ON t.mint=p.mint
WHERE p.proposed_at >= now() - make_interval(mins => 60) ORDER BY p.proposed_at;

-- (f) params em vigor
SELECT id, name, version, status, params::text FROM meme_rule_sets
WHERE name=$$operator$$ ORDER BY version DESC LIMIT 3;
