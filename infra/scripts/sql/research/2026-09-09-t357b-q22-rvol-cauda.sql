-- T3.57b q22 — terceis de RVOL dentro da populacao da v2, cauda esquerda das duas e a
-- leitura condicionada nos episodios que a v1 encerrou por `invalidated`. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with pop as (
  select case when o.meta->>'cohort' like 'replay:7e498c13%' then 'v2' else 'v1' end as lado_exp,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.result::text as motivo, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         f.event_kind, f.relative_volume_15m::numeric as rvol
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e) agg
    cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, relative_volume_15m text)
   where o.meta->>'cohort' in ('replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
                               'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
), v2 as (
  select *, ntile(3) over (order by rvol) as tercil from pop where lado_exp='v2'
)
select 'C. tercil de RVOL na v2' as bloco, tercil, count(*) as n,
       round(min(rvol),3) as rvol_min, round(max(rvol),3) as rvol_max,
       round(avg(rvol),3) as rvol_medio,
       round(avg(r_net),4) as exp_liq_r, round(sum(r_net),3) as soma_r,
       round(100.0*count(*) filter (where r_net>0)/count(*),1) as acerto_pct
  from v2 group by 1,2 order by 2;

with pop as (
  select case when o.meta->>'cohort' like 'replay:7e498c13%' then 'v2' else 'v1' end as lado_exp,
         m.symbol, (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.result::text as motivo, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
   where o.meta->>'cohort' in ('replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
                               'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
)
select 'D. cauda esquerda' as bloco, lado_exp, count(*) as n,
       round((percentile_cont(0.10) within group (order by r_net))::numeric, 4) as p10_r,
       round(avg(r_net) filter (where r_net < 0), 4) as media_das_perdedoras,
       round(min(r_net), 4) as pior_r,
       count(*) filter (where r_net < 0) as n_perdedoras,
       round(avg((exit_base - p_entry/1.0006)/nullif(risk,0) - r_exf), 4) as pedagio_r
  from pop group by 1,2 order by 2;

-- E. leitura condicionada: nas barras em que a v1 saiu por `invalidated`, qual o R da v2
with pop as (
  select case when o.meta->>'cohort' like 'replay:7e498c13%' then 'v2' else 'v1' end as lado_exp,
         m.symbol, (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.result::text as motivo, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
   where o.meta->>'cohort' in ('replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
                               'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
), v1inv as (select * from pop where lado_exp='v1' and motivo='invalidated')
select 'E. onde a v1 invalidou' as bloco, count(*) as n_v1_invalidadas,
       count(b.bar) as n_com_par_na_v2,
       round(avg(a.r_net),4) as exp_v1_r,
       round(avg(b.r_net),4) as exp_v2_r,
       round(avg(b.r_net - a.r_net) filter (where b.bar is not null),4) as delta_pareado_r
  from v1inv a left join pop b
    on b.lado_exp='v2' and b.symbol=a.symbol and b.bar=a.bar;
commit;
