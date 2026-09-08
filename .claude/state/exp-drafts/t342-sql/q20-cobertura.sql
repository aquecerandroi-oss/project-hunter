begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
select left(split_part(o.meta->>'cohort',':',2),8) as coorte,
       count(*) as emitidos,
       count(*) filter (where o.tracking_state='pending_entry') as pendentes,
       count(*) filter (where o.entry_ts is not null) as entradas,
       count(*) filter (where o.no_entry_reason is not null) as nao_entradas,
       count(*) filter (where o.tracking_state='active') as ativos,
       count(*) filter (where o.result::text='target') as alvo,
       count(*) filter (where o.result::text='stop') as stop,
       count(*) filter (where o.result::text='expired') as expirado,
       count(*) filter (where o.result::text='invalidated') as invalidado,
       count(*) filter (where o.censored_reason is not null) as censurados,
       count(*) filter (where (o.meta->'funding'->>'reason') is not null) as funding_indisponivel,
       count(*) filter (where o.r_multiple is not null) as avaliaveis,
       count(distinct (o.meta->'entry_plan'->>'source_bar_close')::date) as dias
  from signal_outcomes o
 where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968','replay:d570b19a-f6e2-4312-86ed-9394b16ac81a','replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
 group by 1 order by 1;
select left(split_part(o.meta->>'cohort',':',2),8) as coorte,
       round(100.0*count(*) filter (where o.result::text='target')/nullif(count(*) filter (where o.result::text in ('target','stop')),0),1) as taxa_alvo_entre_toques,
       round(100.0*count(*) filter (where o.r_multiple>0)/nullif(count(*) filter (where o.r_multiple is not null),0),1) as taxa_lucro_liquido_pct
  from signal_outcomes o
 where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968','replay:d570b19a-f6e2-4312-86ed-9394b16ac81a','replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
 group by 1 order by 1;
select v.version, jsonb_pretty(v.default_parameters) as parametros
  from strategy_versions v join strategies s on s.id=v.strategy_id
 where s.key='mean_reversion' and v.version in ('v2','v3') order by v.version;
commit;
