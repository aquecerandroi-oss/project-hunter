-- T3.57b q21 — pareamento por (mercado, barra) entre `trendline_bounce v1` (v2 do
-- experimento) e `trendline_breakout v1`, mais terceis de RVOL, cauda esquerda e a
-- leitura condicionada nos episodios que a v1 encerrou por `invalidated`.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with pop as (
  select case when o.meta->>'cohort' like 'replay:7e498c13%' then 'v2' else 'v1' end as lado_exp,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date as dia,
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
), v2 as (select * from pop where lado_exp='v2'),
   v1 as (select * from pop where lado_exp='v1')
select 'B. pareamento' as bloco,
       case when a.bar is not null and b.bar is not null then '1 nas duas'
            when b.bar is not null then '2 so na v1 (mae)'
            else '3 so na v2 (filha)' end as classe,
       count(*) as n,
       round(avg(b.r_net), 4) as exp_v1_r,
       round(avg(a.r_net), 4) as exp_v2_r,
       round(avg(a.r_net - b.r_net), 4) as delta_pareado_r
  from v2 a full outer join v1 b on a.symbol=b.symbol and a.bar=b.bar
 group by 1,2 order by 2;
commit;
