-- R27 q08 — vazao das duas portas nas ultimas 3 h: a REPLICA do R23 (q04) e a porta REAL
-- (o codigo com os params vigentes de operator/5), moedas distintas e por hora, com o custo
-- de cada criterio que so a porta real tem. Mayhem: o codigo le t.mayhem_enabled (senao o da
-- foto) e RECUSA o desconhecido; a replica usava t.mayhem_mode IS NULL.
SET statement_timeout = 240000;
CREATE TEMP VIEW base AS
  SELECT f.*, t.symbol, t.creator, t.created_at, t.completed_at, t.migrated_at,
         t.mayhem_enabled, t.mayhem_mode, t.mayhem_state, s.mint AS snap_mint,
         s.virtual_sol_reserves, s.virtual_token_reserves, s.mayhem_enabled AS snap_mayhem
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
  LEFT JOIN meme_curve_snapshots s ON s.mint=f.mint AND s.observed_at=f.snapshot_observed_at
    AND s.source=f.snapshot_source
  WHERE f.as_of >= now() - interval '3 hours' AND f.features_version='meme_features_15s_v1';

-- (a) a replica do R23 (sobre a mesma base)
CREATE TEMP VIEW rep AS
  SELECT DISTINCT ON (mint) mint, symbol, as_of, creator, created_at FROM base
  WHERE age_s BETWEEN 30 AND 300 AND mayhem_mode IS NULL
    AND (completed_at IS NULL OR completed_at > as_of) AND (migrated_at IS NULL OR migrated_at > as_of)
    AND curve_progress_pct BETWEEN 0.05 AND 0.50 AND tape_reason IS NULL AND net_sol_flow_60s > 0
    AND holders >= 20 AND unique_buyers_60s >= 10 AND snipers >= 21
    AND dev_share IS NOT NULL AND dev_share <= 0.10
    AND buys_60s > 0 AND sells_60s::numeric/buys_60s <= 0.6
    AND curve_volume_60s_sol IS NOT NULL AND curve_volume_60s_sol >= 5
    AND creator IS NOT NULL AND created_at IS NOT NULL
  ORDER BY mint, as_of;

-- (b) a porta real, sem o pedigree
CREATE TEMP VIEW real_gate AS
  SELECT DISTINCT ON (mint) mint, symbol, as_of, creator, created_at FROM base
  WHERE (completed_at IS NULL OR completed_at > as_of) AND (migrated_at IS NULL OR migrated_at > as_of)
    AND COALESCE(mayhem_enabled, snap_mayhem) = false
    AND created_at IS NOT NULL AND extract(epoch FROM (as_of-created_at)) BETWEEN 30 AND 300
    AND curve_progress_pct IS NOT NULL AND curve_progress_pct*100 BETWEEN 5 AND 50
    AND (creator_net_seller = false OR (creator_net_seller IS NULL AND dev_share IS NOT NULL AND dev_share <= 0.10))
    AND curve_volume_60s_sol IS NOT NULL AND 100*0.05/curve_volume_60s_sol <= 1
    AND dev_share IS NOT NULL AND dev_share <= 0.10
    AND snipers IS NOT NULL AND snipers BETWEEN 21 AND 1000
    AND COALESCE(net_sol_flow_60s, mcap_delta_60s) > 0
    AND unique_buyers_60s >= 10 AND buys_60s > 0 AND sells_60s::numeric/buys_60s <= 0.6
    AND holders >= 20
    AND snap_mint IS NOT NULL AND virtual_sol_reserves IS NOT NULL AND virtual_token_reserves > 0
  ORDER BY mint, as_of;

CREATE TEMP VIEW ped AS
  SELECT g.*,
    (SELECT count(*) FROM meme_tokens o WHERE o.creator=g.creator AND o.mint<>g.mint
       AND o.created_at IS NOT NULL AND o.created_at <= g.created_at
       AND o.created_at > g.created_at - interval '1 hour') AS c1h,
    (SELECT count(*) FROM meme_tokens o WHERE o.symbol=g.symbol AND o.mint<>g.mint
       AND o.created_at IS NOT NULL AND o.created_at <= g.created_at
       AND o.created_at > g.created_at - interval '24 hours') AS s24h,
    (SELECT count(*) FROM meme_tokens o WHERE o.creator=g.creator AND o.mint<>g.mint
       AND o.created_at IS NOT NULL AND o.created_at <= g.created_at
       AND o.created_at > g.created_at - interval '7 days'
       AND EXISTS (SELECT 1 FROM meme_features_1m pf WHERE pf.mint=o.mint AND pf.creator_sold=true
                     AND pf.end_time < g.created_at)) AS dump7d
  FROM real_gate g;

SELECT (SELECT count(*) FROM rep) AS replica_r23_moedas,
       round((SELECT count(*) FROM rep)/3.0,1) AS replica_por_hora,
       (SELECT count(*) FROM real_gate) AS porta_real_sem_pedigree,
       (SELECT count(*) FROM ped WHERE c1h<=1 AND s24h<=2) AS porta_real_com_pedigree,
       round((SELECT count(*) FROM ped WHERE c1h<=1 AND s24h<=2)/3.0,1) AS com_pedigree_por_hora,
       (SELECT count(*) FROM ped WHERE c1h<=1 AND s24h<=2 AND dump7d=0) AS porta_real_final,
       round((SELECT count(*) FROM ped WHERE c1h<=1 AND s24h<=2 AND dump7d=0)/3.0,1) AS real_por_hora,
       (SELECT count(DISTINCT p.mint) FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
          WHERE rs.name='operator' AND p.proposed_at >= now() - interval '3 hours') AS propostas_reais_moedas;

-- quem esta em cada lado (diagnostico da diferenca)
SELECT 'so_na_replica' AS lado, count(*) FROM (SELECT mint FROM rep EXCEPT SELECT mint FROM ped WHERE c1h<=1 AND s24h<=2 AND dump7d=0) x
UNION ALL SELECT 'so_na_porta_real', count(*) FROM (SELECT mint FROM ped WHERE c1h<=1 AND s24h<=2 AND dump7d=0 EXCEPT SELECT mint FROM rep) y
UNION ALL SELECT 'nas_duas', count(*) FROM (SELECT mint FROM rep INTERSECT SELECT mint FROM ped WHERE c1h<=1 AND s24h<=2 AND dump7d=0) z;

-- por que a replica passa e a porta real nao (contagem por criterio, sobre as so_na_replica)
SELECT count(*) FILTER (WHERE b.dump>0) AS repeat_dumper,
       count(*) FILTER (WHERE b.mayhem_desconhecido) AS mayhem_desconhecido,
       count(*) FILTER (WHERE b.sem_foto) AS sem_foto_para_cotacao,
       count(*) FILTER (WHERE b.creator_ns) AS creator_net_seller,
       count(*) FILTER (WHERE b.ped_sujo) AS pedigree_1h_24h
FROM (
  SELECT r.mint,
    (SELECT count(*) FROM meme_tokens o WHERE o.creator=r.creator AND o.mint<>r.mint
       AND o.created_at IS NOT NULL AND o.created_at <= r.created_at
       AND o.created_at > r.created_at - interval '7 days'
       AND EXISTS (SELECT 1 FROM meme_features_1m pf WHERE pf.mint=o.mint AND pf.creator_sold=true
                     AND pf.end_time < r.created_at)) AS dump,
    (SELECT bool_and(COALESCE(b2.mayhem_enabled,b2.snap_mayhem) IS NULL) FROM base b2
       WHERE b2.mint=r.mint AND b2.as_of=r.as_of) AS mayhem_desconhecido,
    (SELECT bool_and(b3.snap_mint IS NULL) FROM base b3 WHERE b3.mint=r.mint AND b3.as_of=r.as_of) AS sem_foto,
    (SELECT bool_or(b4.creator_net_seller) FROM base b4 WHERE b4.mint=r.mint AND b4.as_of=r.as_of) AS creator_ns,
    ((SELECT count(*) FROM meme_tokens o WHERE o.creator=r.creator AND o.mint<>r.mint
        AND o.created_at IS NOT NULL AND o.created_at <= r.created_at
        AND o.created_at > r.created_at - interval '1 hour') > 1) AS ped_sujo
  FROM rep r WHERE r.mint NOT IN (SELECT mint FROM ped WHERE c1h<=1 AND s24h<=2 AND dump7d=0)
) b;
