-- =====================================================================================
-- T3.57 q00 — viabilidade de K1 para o portao de RVOL da `trendline_bounce_v1`
--   populacao: as 47 decisoes da coorte `replay:d78c14d1-b4c5-424a-8f31-a43100744bb4`
--   (T3.34c, `trendline_breakout v1`), das quais 42 sao repique (`event_kind = 'bounce'`)
--
-- PERGUNTA UNICA: quantas decisoes sobreviveriam a `rvol >= L` para alguns L?
-- O limiar 1,0 ja estava escolhido por principio quando esta consulta rodou
-- (`.claude/state/notes-T3.57.md` §"Ordem dos atos"). A coluna de R vai junto por
-- honestidade de procedencia, NAO como criterio de escolha.
--
-- SOMENTE LEITURA.
-- =====================================================================================
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

with pop as (
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
       o.result::text                                          as motivo,
       o.r_multiple                                            as r_net,
       f.event_kind, f.line_kind,
       f.relative_volume_15m::numeric                          as rvol
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m       on m.id = a.market_id
  cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e
  ) agg
  cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, line_kind text, relative_volume_15m text)
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
)
, bounces as (select * from pop where event_kind = 'bounce')
select 'todos os repiques' as faixa, count(*) as n,
       round(avg(rvol), 4) as rvol_medio, round(min(rvol), 4) as rvol_min,
       round(avg(r_net), 4) as r_liq_medio, count(distinct bar::date) as dias
  from bounces
union all
select 'rvol >= ' || l::text, count(*),
       round(avg(rvol), 4), round(min(rvol), 4), round(avg(r_net), 4), count(distinct bar::date)
  from (values (0.8),(0.9),(1.0),(1.1),(1.25),(1.5)) as t(l)
  join bounces on bounces.rvol >= t.l
 group by l
 order by 1;

-- a distribuicao inteira, para nao esconder a forma atras de seis cortes
with pop as (
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
       o.result::text                                          as motivo,
       o.r_multiple                                            as r_net,
       f.event_kind,
       f.relative_volume_15m::numeric                          as rvol
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m       on m.id = a.market_id
  cross join lateral (
      select jsonb_object_agg(e->>'name', e->>'value') as j
        from jsonb_array_elements(a.supporting_features->'features') e
  ) agg
  cross join lateral jsonb_to_record(agg.j) as f(
      event_kind text, relative_volume_15m text)
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
)
select round(rvol, 4) as rvol, symbol, motivo, round(r_net, 4) as r_net
  from pop where event_kind = 'bounce' order by rvol;

commit;
