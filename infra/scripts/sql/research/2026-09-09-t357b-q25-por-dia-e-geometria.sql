-- T3.57b q25 — decomposicao por dia (o que sobra sem regime, C4) e a geometria das
-- linhas que dispararam (`line_touches`), nas duas versoes. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select case when o.meta->>'cohort' like 'replay:7e498c13%' then 'v2 bounce' else 'v1 breakout' end as versao,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date as dia,
         o.r_multiple as r_net,
         f.line_touches::numeric as touches, f.atr_pct::numeric as atr_pct,
         f.event_kind
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e) agg
    cross join lateral jsonb_to_record(agg.j) as f(
      line_touches text, atr_pct text, event_kind text)
   where o.meta->>'cohort' in ('replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
                               'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text='terminal' and o.r_multiple is not null
)
select versao, dia, count(*) as n, round(avg(r_net),4) as exp_r, round(sum(r_net),3) as soma_r
  from pop where versao='v2 bounce' group by 1,2 order by 2;

;
with pop as (
  select case when o.meta->>'cohort' like 'replay:7e498c13%' then 'v2 bounce' else 'v1 breakout' end as versao,
         o.r_multiple as r_net, f.line_touches::numeric as touches,
         f.atr_pct::numeric as atr_pct, f.event_kind
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e) agg
    cross join lateral jsonb_to_record(agg.j) as f(
      line_touches text, atr_pct text, event_kind text)
   where o.meta->>'cohort' in ('replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
                               'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text='terminal' and o.r_multiple is not null
)
select versao, event_kind, count(*) as n,
       round(avg(touches),2) as touches_medio, min(touches) as touches_min, max(touches) as touches_max,
       round(avg(atr_pct),5) as atr_pct_medio
  from pop group by 1,2 order by 1,2;
commit;
