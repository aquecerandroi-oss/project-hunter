-- T3.59c/T3.57b q30 — as portas K por coorte: cobertura de R (K5), sinais x desfechos,
-- dias distintos, e a identidade do pedagio. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with sig as (
  select a.supporting_features->>'cohort' as cohort,
         s.key||' '||sv.version as versao, count(*) as emitidos
    from agent_signals a
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where a.supporting_features->>'cohort' in (
     'replay:4ed2ec88-c4cd-4fa2-aeb9-eb432fd271dd','replay:29bc81bf-26ea-4255-a9cb-46bab6d7c99f',
     'replay:fbb65b47-d8dc-4abb-b64f-0ef1f24faf3e','replay:9a48a940-5957-4b07-a9c4-4d4521adc907',
     'replay:7e498c13-d79b-4466-8ff8-30550d75c21e')
   group by 1,2
), out as (
  select o.meta->>'cohort' as cohort,
         count(*) as desfechos,
         count(*) filter (where o.tracking_state::text='terminal') as terminais,
         count(*) filter (where o.r_multiple is not null) as com_r,
         count(distinct (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date) as dias,
         count(distinct a.market_id) as mercados
    from signal_outcomes o join agent_signals a on a.id = o.signal_id
   where o.meta->>'cohort' in (
     'replay:4ed2ec88-c4cd-4fa2-aeb9-eb432fd271dd','replay:29bc81bf-26ea-4255-a9cb-46bab6d7c99f',
     'replay:fbb65b47-d8dc-4abb-b64f-0ef1f24faf3e','replay:9a48a940-5957-4b07-a9c4-4d4521adc907',
     'replay:7e498c13-d79b-4466-8ff8-30550d75c21e')
   group by 1
)
select sig.versao, left(split_part(sig.cohort,':',2),8) as coorte,
       sig.emitidos, out.desfechos, out.terminais, out.com_r, out.dias, out.mercados,
       round(100.0*out.com_r/nullif(sig.emitidos,0),1) as cobertura_r_pct
  from sig join out on out.cohort = sig.cohort
 order by 1;

-- identidade do pedagio na trendline_bounce: 0,002 / (risco_atr * ATR%)
with pop as (
  select (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
   where o.meta->>'cohort' = 'replay:7e498c13-d79b-4466-8ff8-30550d75c21e'
     and o.tracking_state::text='terminal' and o.r_multiple is not null
)
select 'pedagio medido x identidade' as bloco, count(*) as n,
       round(avg((exit_base - p_entry/1.0006)/nullif(risk,0) - r_exf), 4) as pedagio_medido_r,
       round(avg(0.002 * p_entry / nullif(risk,0)), 4) as identidade_0002_sobre_risco,
       round((percentile_cont(0.5) within group (order by
              (exit_base - p_entry/1.0006)/nullif(risk,0) - r_exf))::numeric, 4) as pedagio_p50_r,
       round(max((exit_base - p_entry/1.0006)/nullif(risk,0) - r_exf), 4) as pedagio_max_r
  from pop;
commit;
