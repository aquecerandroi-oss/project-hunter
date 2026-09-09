-- T3.57b q20 — dia um da `trendline_bounce v1` (EXP-0022): populacao, pareamento por
-- (mercado, barra) contra a `trendline_breakout v1`, terceis de RVOL, cauda esquerda,
-- decomposicao por mercado e por dia. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- ---------------------------------------------------------------- populacao das duas
with pop as (
  select s.key||' '||sv.version as versao,
         case when o.meta->>'cohort' like 'replay:7e498c13%' then 'v2' else 'v1' end as lado_exp,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date as dia,
         o.result::text as motivo, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         f.event_kind, f.relative_volume_15m::numeric as rvol,
         f.atr_pct::numeric as atr_pct, f.line_touches::numeric as touches
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e) agg
    cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, relative_volume_15m text, atr_pct text, line_touches text)
   where o.meta->>'cohort' in ('replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
                               'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
)
select 'A. por mercado' as bloco, versao, symbol, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (partition by versao), 1) as pct_da_versao,
       round(avg(r_net), 4) as exp_liq_r, round(sum(r_net), 3) as soma_r
  from pop group by 1,2,3 order by 2,3;
commit;
