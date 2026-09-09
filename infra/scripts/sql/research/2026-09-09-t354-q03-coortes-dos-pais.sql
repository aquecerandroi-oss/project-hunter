-- T3.54 q03 — as coortes de replay ja existentes dos pais (mean_reversion v6,
-- momentum v8) e a janela/mercados de cada uma: e contra elas que as variantes
-- de 1 h serao pareadas. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select s.key||' '||sv.version as versao,
       'replay:'||left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
       count(*) as n,
       count(*) filter (where o.tracking_state::text = 'terminal') as terminais,
       min(a.emitted_at)::date as primeiro_dia,
       max(a.emitted_at)::date as ultimo_dia,
       count(distinct m.symbol) as mercados,
       string_agg(distinct m.symbol, ',' order by m.symbol) as simbolos
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
  join markets m on m.id = a.market_id
 where s.key in ('mean_reversion', 'momentum')
   and sv.version in ('v6', 'v8')
   and o.meta->>'cohort' like 'replay:%'
 group by 1, 2
 order by 1, 5;
commit;
