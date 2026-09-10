-- T3.62b q00 -- catalogo vivo da familia mean_reversion ANTES de qualquer escrita.
-- O brief da T3.62b nomeia v10, v1 e v2 (a T3.62 mediu v6/v10/v8/v2), entao a
-- primeira pergunta e "a v1 existe, esta ativa, e qual e a diferenca de parametro
-- para a v2 e a v10?". Sem isso o contraste seria sobre codigo e nao sobre parametro.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. as versoes da familia, com os parametros que decidem a porta de entrada e o stop
select sv.version,
       sv.status::text  as estado,
       sv.purpose::text as proposito,
       sv.default_parameters->>'atr_pct_min'   as atr_pct_min,
       sv.default_parameters->>'stop_atr'      as stop_atr,
       sv.default_parameters->>'target_atr'    as alvo1,
       sv.default_parameters->>'target2_atr'   as alvo2,
       sv.default_parameters->>'atr_timeframe' as atr_tf,
       sv.default_parameters->>'atr_bars'      as atr_bars,

       coalesce(sv.eligibility_policy::text, '-') as politica,
       right(sv.code_ref, 16) as code_ref_sufixo,
       left(sv.changelog, 70) as changelog,
       sv.activated_at
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key = 'mean_reversion'
 order by (regexp_replace(sv.version, '\D', '', 'g'))::int;


-- 2. quantas decisoes cada versao ja tem, por coorte: separa a populacao antiga
--    (T3.62, 31 d) da nova desta tarefa. A coorte vive em signal_outcomes.meta.
select sv.version,
       left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
       count(*)                as decisoes,
       min(a.emitted_at)::date as primeiro_dia,
       max(a.emitted_at)::date as ultimo_dia
  from signal_outcomes o
  join agent_signals a       on a.id = o.signal_id
  join strategy_versions sv  on sv.id = a.strategy_version_id
  join strategies s          on s.id = sv.strategy_id
 where s.key = 'mean_reversion'
 group by 1, 2
 order by (regexp_replace(sv.version, '\D', '', 'g'))::int, 5 desc;

commit;
