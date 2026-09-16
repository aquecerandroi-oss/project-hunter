-- R5 / Q04 — estimativa do que o executor recusaria a seguir: para cada mint
-- que o conjunto `operator` propos nas ultimas 24 h, o insumo existia no
-- instante da proposta? (mesmas janelas de frescor do executor: risco <= 600 s,
-- features <= 120 s para volume/top10; creator_sold sem janela, como em repo.py)
WITH p AS (
    SELECT DISTINCT ON (p.mint) p.mint, p.proposed_at
    FROM meme_proposals p
    JOIN meme_rule_sets rs ON rs.id = p.rule_set_id
    WHERE rs.name = 'operator'
      AND p.proposed_at >= now() - make_interval(hours => 24)
    ORDER BY p.mint, p.proposed_at
),
f AS (
    SELECT p.mint,
           EXISTS (SELECT 1 FROM meme_risk_snapshots r
                   WHERE r.mint = p.mint AND r.bundled_share IS NOT NULL
                     AND r.observed_at <= p.proposed_at
                     AND r.observed_at >= p.proposed_at - make_interval(secs => 600)) AS bundled,
           EXISTS (SELECT 1 FROM meme_features_1m x
                   WHERE x.mint = p.mint AND x.creator_sold IS NOT NULL
                     AND x.end_time <= p.proposed_at)                                 AS creator,
           EXISTS (SELECT 1 FROM meme_features_1m x
                   WHERE x.mint = p.mint AND x.top10_share IS NOT NULL
                     AND x.top10_share <= 0.25
                     AND x.end_time <= p.proposed_at
                     AND x.end_time >= p.proposed_at - make_interval(secs => 120))    AS top10,
           EXISTS (SELECT 1 FROM meme_features_1m x
                   WHERE x.mint = p.mint AND x.curve_volume_1m_sol > 0
                     AND x.end_time <= p.proposed_at
                     AND x.end_time >= p.proposed_at - make_interval(secs => 120))    AS volume
    FROM p
)
SELECT count(*)                                                          AS mints,
       count(*) FILTER (WHERE bundled)                                   AS bundled_ok,
       count(*) FILTER (WHERE creator)                                   AS creator_ok,
       count(*) FILTER (WHERE top10)                                     AS top10_ok,
       count(*) FILTER (WHERE volume)                                    AS volume_ok,
       count(*) FILTER (WHERE bundled AND creator AND top10 AND volume)   AS todas_4,
       count(*) FILTER (WHERE creator AND top10 AND volume)               AS sem_bundled,
       count(*) FILTER (WHERE bundled AND top10 AND volume)               AS sem_creator,
       count(*) FILTER (WHERE top10 AND volume)                           AS so_top10_e_volume
FROM f;
