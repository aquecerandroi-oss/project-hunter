-- T3.65b q05 -- OS TRES MOTIVOS POR SEMANA, ANTES x DEPOIS DA TRANSICAO, e
-- separados pela VERSAO DO CODIGO que gravou o desfecho.
-- A transicao real de PROMUSDT e 1 h -> 4 h em 2026-08-14 (ultimo assentamento
-- de 1 h as 10:00Z, seguinte as 12:00Z); a aceleracao 4 h -> 1 h foi em
-- 2026-08-11 05:00Z. SAHARA e TAO nao mudaram de cadencia nos 90 dias.
-- O corte de codigo e `updated_at < 2026-09-10 02:00Z` (pre-T3.65: moda da
-- janela inteira) x `>=` (pos-T3.65: moda dos 3 ultimos gaps) -- as coortes de
-- 09/09 19:28-20:16 sao pre, as de 10/09 02:35-04:28 sao pos (q02).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with pop as (
  select m.symbol,
         date_trunc('week', o.entry_ts)::date as semana,
         case when o.updated_at < timestamptz '2026-09-10 02:00+00'
              then 'pre-T3.65' else 'pos-T3.65' end as codigo,
         case when o.entry_ts < timestamptz '2026-08-11 05:00+00' then 'antes'
              when o.entry_ts < timestamptz '2026-08-14 12:00+00' then 'na janela 1h'
              else 'depois' end as fase,
         coalesce(split_part(o.meta->>'r_net_reason', ':', 1), 'ok') as motivo
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
   where o.tracking_state = 'terminal'
     and m.market_type = 'perpetual'
     and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
)
select symbol, fase, codigo,
       count(*)                                                       as terminais,
       count(*) filter (where motivo = 'funding_missing')             as funding_missing,
       count(*) filter (where motivo = 'funding_ambiguous_exit')      as ambiguous_exit,
       count(*) filter (where motivo = 'funding_schedule_unknown')    as schedule_unknown,
       count(*) filter (where motivo = 'ok')                          as ok
  from pop
 group by 1, 2, 3
 order by 1, 2, 3;

-- o mesmo, por semana, so os tres motivos
with pop as (
  select m.symbol,
         date_trunc('week', o.entry_ts)::date as semana,
         coalesce(split_part(o.meta->>'r_net_reason', ':', 1), 'ok') as motivo
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
   where o.tracking_state = 'terminal'
     and m.market_type = 'perpetual'
     and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
     and o.entry_ts >= timestamptz '2026-08-03 00:00+00'
)
select semana,
       count(*)                                                     as terminais,
       count(*) filter (where motivo = 'funding_missing')           as funding_missing,
       count(*) filter (where motivo = 'funding_ambiguous_exit')    as ambiguous_exit,
       count(*) filter (where motivo = 'funding_schedule_unknown')  as schedule_unknown
  from pop
 group by 1
 order by 1;

commit;
