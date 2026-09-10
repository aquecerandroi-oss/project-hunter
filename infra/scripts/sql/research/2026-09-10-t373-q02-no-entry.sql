-- T3.73 q02 -- O DENOMINADOR ESCONDIDO: SINAIS QUE NUNCA VIRARAM ENTRADA
-- (`tracking_state = 'no_entry'`), POR MOTIVO E POR DIA UTC, DESDE 2026-09-01.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. por dia UTC de decisao: emitidos, no_entry e a fracao
select date_trunc('day', a.emitted_at)::date as dia,
       count(*) as sinais,
       count(*) filter (where o.tracking_state = 'no_entry') as no_entry,
       round(100.0 * count(*) filter (where o.tracking_state = 'no_entry') / nullif(count(*),0), 1) as pct_no_entry,
       count(*) filter (where o.tracking_state = 'terminal') as terminais,
       count(*) filter (where o.tracking_state = 'censored') as censurados,
       count(*) filter (where o.tracking_state in ('pending_entry','active')) as abertos
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where o.meta->>'cohort' = 'prospective'
   and a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1 order by 1;

-- 2. motivo do no_entry por dia
select date_trunc('day', a.emitted_at)::date as dia,
       coalesce(o.no_entry_reason, '(nulo)') as motivo,
       count(*) as n
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where o.meta->>'cohort' = 'prospective'
   and o.tracking_state = 'no_entry'
   and a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1, 2 order by 1, 3 desc;

-- 3. motivo do no_entry por versao (total da janela)
select s.key || ' ' || sv.version as versao,
       coalesce(o.no_entry_reason, '(nulo)') as motivo,
       count(*) as n
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where o.meta->>'cohort' = 'prospective'
   and o.tracking_state = 'no_entry'
   and a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1, 2 order by 3 desc limit 30;

-- 4. o atraso que `late:delay` mede: decisao -> abertura da barra escolhida
select coalesce(o.no_entry_reason, '(nulo)') as motivo,
       count(*) as n,
       min(o.meta->>'entry_bar_open') as menor_barra,
       max(o.meta->>'entry_bar_open') as maior_barra
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where o.meta->>'cohort' = 'prospective'
   and o.tracking_state = 'no_entry'
   and a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1 order by 2 desc;

commit;
