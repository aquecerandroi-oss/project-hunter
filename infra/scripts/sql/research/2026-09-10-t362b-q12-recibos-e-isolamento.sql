-- T3.62b q12 -- RECIBOS das 36 corridas (K4) e ISOLAMENTO das tres coortes.
--
-- Por que os recibos saem de `system_events` e nao de `replay_runs`: a chave
-- `uq_replay_runs_slice` e (run_id, window_from, window_to) e NAO inclui os
-- mercados, com `ON CONFLICT ... DO NOTHING`. Como esta tarefa usa UMA coorte por
-- versao com QUATRO fatias de mercado dentro da mesma janela, so a primeira fatia
-- de cada janela deixa linha duravel -- `replay_runs` mostraria 3 corridas por
-- versao quando o trabalho real foi 12 (CONCERN 1 da notes-T3.62 SS2.3, ainda
-- aberto). O recibo completo esta em `replay_engine`/`replay_run_finished`.
--
-- K4 (`unavailable` > 40 % das barras) so e mensuravel a partir de
-- `evaluations_by_state`, e e por isso que ele vive aqui e nao no q10.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. K4 e o total por versao (o recibo completo das 36 corridas)
select data->>'version_label' as versao,
       left(split_part(data->>'cohort',':',2),8) as coorte,
       count(*)                                   as fatias,
       sum((data->>'bars_evaluated')::bigint)     as barras,
       sum((data->>'errors')::bigint)             as erros,
       sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint,0)) as unavailable,
       round(100.0*sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint,0))
             / sum((data->>'bars_evaluated')::bigint), 3)                      as k4_unavailable_pct,
       sum(coalesce((data->'evaluations_by_state'->>'triggered')::bigint,0))   as triggered,
       max((data->>'signals')::bigint)            as decisoes_cumulativas,
       sum((data->>'outcomes_open')::bigint)      as desfechos_abertos,
       min((data->>'window_from')::timestamptz)   as janela_de,
       max((data->>'window_to')::timestamptz)     as janela_ate,
       count(distinct data->>'markets_digest')    as fatias_de_mercado,
       min(created_at)                            as primeira,
       max(created_at)                            as ultima
  from system_events
 where component='replay_engine' and event='replay_run_finished'
   and data->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                           'replay:fa005985-0b55-4820-904c-8ada589e441c',
                           'replay:da706026-319a-451e-950e-7728ca9ae563')
 group by 1,2 order by 1;

-- 2. corrida a corrida (a prova de que sao 12 fatias por versao, sem buraco)
select data->>'version_label' as versao,
       (data->>'window_from')::date as de, (data->>'window_to')::date as ate,
       left(data->>'markets_digest',6) as fatia,
       data->>'bars_evaluated' as barras, data->>'errors' as erros,
       data->>'outcomes_open' as abertos,
       round((data->>'seconds')::numeric,1) as segundos, created_at as fim
  from system_events
 where component='replay_engine' and event='replay_run_finished'
   and data->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                           'replay:fa005985-0b55-4820-904c-8ada589e441c',
                           'replay:da706026-319a-451e-950e-7728ca9ae563')
 order by 1, 2, 4;

-- 3. ISOLAMENTO: nenhuma decisao destas coortes pode chegar a uma carteira.
--    `research_only` + coorte `replay:` -- a ponte de execucao recusa pelo nome
--    (`cohort_not_live`) e, desde a T3.19b, a decisao nem ganha linha de outbox.
--    `shadow_outbox` nao tem `signal_id` como coluna: a identidade do sinal viaja
--    dentro de `payload`. Por isso o teste e sobre `payload->>'signal_id'`.
select (select count(*) from shadow_outbox so
         where (so.payload->>'signal_id')::uuid in
               (select o.signal_id from signal_outcomes o
                 where o.meta->>'cohort' in (
                                   'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                                   'replay:fa005985-0b55-4820-904c-8ada589e441c',
                                   'replay:da706026-319a-451e-950e-7728ca9ae563'))) as linhas_de_outbox,
       (select count(*) from trade_proposals tp
         where tp.signal_id in (select o.signal_id from signal_outcomes o
                                 where o.meta->>'cohort' in (
                                   'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                                   'replay:fa005985-0b55-4820-904c-8ada589e441c',
                                   'replay:da706026-319a-451e-950e-7728ca9ae563'))) as propostas,
       (select count(*) from signal_outcomes o
         where o.meta->>'cohort' in (
                 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                 'replay:fa005985-0b55-4820-904c-8ada589e441c',
                 'replay:da706026-319a-451e-950e-7728ca9ae563')
           and o.meta->>'purpose' <> 'research_only')                            as fora_de_research_only;

-- 4. o que `replay_runs` guardou de verdade (para o CONCERN ficar MEDIDO, nao dito).
--    A T3.67 acrescentou a coluna `markets_digest` a esta tabela; se ela entrou na
--    chave unica, as 12 fatias de cada versao aparecem aqui e o CONCERN 1 da
--    notes-T3.62 esta fechado. Se so 3 aparecerem, ele continua aberto. A consulta
--    existe para que essa diferenca seja um numero e nao uma suposicao.
select r.cohort, count(*) as linhas_duraveis,
       count(distinct r.markets_digest) as fatias_de_mercado_duraveis,
       sum(r.bars_evaluated) as barras_duraveis,
       sum(array_length(r.markets,1)) as mercados_somados
  from replay_runs r
 where r.cohort in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                    'replay:fa005985-0b55-4820-904c-8ada589e441c',
                    'replay:da706026-319a-451e-950e-7728ca9ae563')
 group by 1 order by 1;

commit;
