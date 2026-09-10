-- D-P9 q00 -- CATALOGO E REPRODUCAO DO FATO.
-- Antes de decompor -34 R e preciso provar que os numeros do brief existem no
-- banco e com qual definicao: qual coorte, qual coluna de R, e qual dia (o da
-- DECISAO, o da ENTRADA ou o da SAIDA) devolve -31,08 R em 420 desfechos.
-- A familia do brief: mean_reversion v1,v2,v3,v6,v7,v8,v10,v14 + mean_reversion_h1 v1.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at, current_setting('TimeZone') as tz;

-- 1. catalogo das versoes vivas da familia (parametros que mudam a geometria)
select s.key,
       sv.version,
       sv.status::text  as estado,
       sv.purpose::text as proposito,
       sv.default_parameters->>'atr_timeframe' as atr_tf,
       sv.default_parameters->>'stop_atr'      as stop_atr,
       sv.default_parameters->>'target_atr'    as alvo1,
       sv.default_parameters->>'target2_atr'   as alvo2,
       sv.default_parameters->>'max_holding_s' as max_holding_s,
       sv.default_parameters->>'atr_pct_min'   as atr_pct_min,
       right(sv.code_ref, 12) as code_ref
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key in ('mean_reversion','mean_reversion_h1')
 order by s.key, (regexp_replace(sv.version,'\D','','g'))::int;

-- 2. populacao prospectiva por dia de DECISAO / ENTRADA / SAIDA (familia inteira)
with pop as (
  select a.id, a.emitted_at, o.entry_ts, o.exit_ts, o.result::text as result,
         o.tracking_state::text as st, o.r_multiple,
         (o.meta->>'r_ex_funding')::numeric as r_ex
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where s.key in ('mean_reversion','mean_reversion_h1')
     and o.meta->>'cohort' = 'prospective'
)
select 'decisao' as eixo, (emitted_at at time zone 'UTC')::date as dia,
       count(*) n, count(r_multiple) com_r,
       round(sum(r_multiple),4) soma_r, round(avg(r_multiple),4) media_r,
       round(sum(r_ex),4) soma_r_ex
  from pop where st = 'terminal' group by 2
union all
select 'entrada', (entry_ts at time zone 'UTC')::date,
       count(*), count(r_multiple), round(sum(r_multiple),4), round(avg(r_multiple),4), round(sum(r_ex),4)
  from pop where st = 'terminal' and entry_ts is not null group by 2
union all
select 'saida', (exit_ts at time zone 'UTC')::date,
       count(*), count(r_multiple), round(sum(r_multiple),4), round(avg(r_multiple),4), round(sum(r_ex),4)
  from pop where st = 'terminal' and exit_ts is not null group by 2
 order by 1, 2;

-- 3. o mesmo, restrito as versoes nomeadas no brief, por dia de SAIDA
with pop as (
  select sv.version, s.key, a.emitted_at, o.entry_ts, o.exit_ts,
         o.tracking_state::text as st, o.r_multiple
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
)
select (exit_ts at time zone 'UTC')::date as dia_saida_utc,
       count(*) n, round(sum(r_multiple),4) soma_r, round(avg(r_multiple),4) media_r,
       count(*) filter (where r_multiple > 0) ganhos,
       round(100.0*count(*) filter (where r_multiple > 0)/nullif(count(r_multiple),0),1) acerto_pct
  from pop where st='terminal' and exit_ts is not null
 group by 1 order by 1;

-- 4. o mesmo por dia de DECISAO (para escolher o eixo do brief)
with pop as (
  select sv.version, s.key, a.emitted_at, o.exit_ts,
         o.tracking_state::text as st, o.r_multiple
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
)
select (emitted_at at time zone 'UTC')::date as dia_decisao_utc,
       count(*) n, round(sum(r_multiple),4) soma_r, round(avg(r_multiple),4) media_r
  from pop where st='terminal'
 group by 1 order by 1;

commit;
