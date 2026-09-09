-- T3.56 q01 — C5: fracao das decisoes cujo risco declarado supera o teto de stop do
-- paper_v1 (risco/entrada > 3 %), por versao alvo e coorte. Mesma formula da T3.47b q15
-- (risk = meta->'excursions'->>'initial_risk'; entrada = meta->'progress'->>'entry').
-- SOMENTE LEITURA (repeatable read / read only).
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at_utc, now() at time zone 'America/Sao_Paulo' as read_at_brt;

with pop as (
  select s.key || ' ' || sv.version as versao,
         case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
              then 'replay' else 'prospective' end as coorte,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (o.meta->'progress'->>'entry')::numeric as p_entry
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and (s.key, sv.version) in (
          ('volume_anomaly','v1'), ('volume_anomaly','v2'),
          ('momentum','v1'), ('momentum','v2'), ('momentum','v3'), ('momentum','v4'),
          ('momentum','v6'), ('momentum','v10'),
          ('session_orb','v1'), ('trendline_breakout','v1'))
)
select versao, coorte, count(*) as n,
       count(*) filter (where risk is null or p_entry is null or p_entry = 0) as sem_geometria,
       count(*) filter (where risk / nullif(p_entry,0) > 0.03) as acima_do_teto_paper,
       round(100.0 * count(*) filter (where risk / nullif(p_entry,0) > 0.03) / count(*), 1) as pct_acima,
       round(avg(risk / nullif(p_entry,0)) * 100, 3) as stop_medio_pct
  from pop
 group by 1,2 order by 1,2;
commit;
