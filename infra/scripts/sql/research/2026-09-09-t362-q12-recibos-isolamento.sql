-- T3.62 q12 — recibos das 32 corridas e a prova de isolamento das quatro coortes
-- de 16 mercados: cobertura de R (K5), nenhuma linha em shadow_outbox, nenhuma
-- em trade_proposals. SOMENTE LEITURA.
--
-- NOTA DE LEITURA (achado da T3.62): `replay_runs` tem chave unica
-- (run_id, window_from, window_to) e `ON CONFLICT DO NOTHING`. Como esta tarefa
-- usou UMA coorte por versao com QUATRO fatias de mercado dentro da MESMA
-- janela, so a primeira fatia de cada janela deixou linha durável — as outras 24
-- corridas vivem em `system_events` (`replay_run_finished`) e nos JSONL.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

\echo '--- 1. replay_runs (so a 1a fatia de cada janela sobrevive; ver nota) ---'
select left(split_part(r.cohort, ':', 2), 8) as coorte,
       sv.version as ver,
       (r.window_from)::date as de, (r.window_to)::date as ate,
       cardinality(r.markets) as mkts,
       r.bars_evaluated as bars,
       r.signals as sig_cumulativo,
       r.outcomes_resolved as out_res,
       r.outcomes_open as aberto,
       round(r.seconds::numeric, 1) as seg,
       r.errors as err
  from replay_runs r
  join strategy_versions sv on sv.id = r.strategy_version_id
 where r.cohort in (
         'replay:85418f7a-bc4f-4417-ae84-4311ec1d1375',
         'replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755',
         'replay:3684ac55-49a8-4ffb-a670-d4c7419d9870',
         'replay:99fdba70-d6a9-452f-950e-324ea35828b0')
 order by r.started_at;

\echo '--- 2. as 32 corridas em system_events (o recibo completo) ---'
select sv.version as ver,
       (e.data->>'market_count')::int as mkts,
       (e.data->>'bars_evaluated')::int as bars,
       (e.data->>'signals')::int as sig_cum,
       (e.data->>'errors')::int as err,
       (e.data->>'seconds')::numeric as seg,
       left(e.data->'markets'->>0, 24) as primeiro_mercado,
       (e.data->>'window_from')::date as de,
       e.created_at
  from system_events e
  join strategy_versions sv on sv.id = (e.data->>'strategy_version_id')::uuid
 where e.component = 'replay_engine' and e.event = 'replay_run_finished'
   and e.data->>'cohort' in (
         'replay:85418f7a-bc4f-4417-ae84-4311ec1d1375',
         'replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755',
         'replay:3684ac55-49a8-4ffb-a670-d4c7419d9870',
         'replay:99fdba70-d6a9-452f-950e-324ea35828b0')
 order by e.created_at;

\echo '--- 3. cobertura de R (K5) e populacao por versao ---'
select sv.version as ver,
       count(*) as sinais,
       count(*) filter (where o.tracking_state::text = 'terminal') as terminais,
       count(*) filter (where o.r_multiple is not null) as com_r,
       round(100.0 * count(*) filter (where o.r_multiple is not null) / count(*), 2) as cobertura_r_pct,
       count(distinct a.market_id) as mercados,
       count(distinct (a.emitted_at)::date) as dias
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
 where o.meta->>'cohort' in (
         'replay:85418f7a-bc4f-4417-ae84-4311ec1d1375',
         'replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755',
         'replay:3684ac55-49a8-4ffb-a670-d4c7419d9870',
         'replay:99fdba70-d6a9-452f-950e-324ea35828b0')
 group by 1 order by 1;

\echo '--- 4. isolamento: nada saiu para execucao ---'
select (select count(*) from shadow_outbox x
         join signal_outcomes o on o.signal_id = (x.payload->>'signal_id')::uuid
        where o.meta->>'cohort' in (
              'replay:85418f7a-bc4f-4417-ae84-4311ec1d1375',
              'replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755',
              'replay:3684ac55-49a8-4ffb-a670-d4c7419d9870',
              'replay:99fdba70-d6a9-452f-950e-324ea35828b0')) as linhas_de_outbox,
       (select count(*) from trade_proposals p
         join signal_outcomes o on o.signal_id = p.signal_id
        where o.meta->>'cohort' in (
              'replay:85418f7a-bc4f-4417-ae84-4311ec1d1375',
              'replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755',
              'replay:3684ac55-49a8-4ffb-a670-d4c7419d9870',
              'replay:99fdba70-d6a9-452f-950e-324ea35828b0')) as propostas;
commit;
