-- T3.75 q02 -- O RAIO DE ALCANCE DE `recompute_funding.py`, ANTES DE ALGUEM RODA-LO.
-- O script de re-liquidacao (`infra/scripts/recompute_funding.py`) NAO tem filtro de
-- coorte nem `--limit`: a consulta dele e "todo `signal_outcomes` terminal com
-- `r_multiple IS NULL` e `meta.funding.reason` nao nulo", uma transacao por linha.
-- Quem for rodar precisa saber quantas linhas sao e de quem elas sao -- as tres
-- coortes da T3.62b sao uma fracao disso. Esta consulta so conta; nao escreve nada.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. o universo exato que `_CANDIDATES_SQL` selecionaria, por motivo
select split_part(o.meta->'funding'->>'reason', ':', 1) as motivo,
       count(*)                                          as candidatos,
       min(o.exit_ts)                                    as primeiro_desfecho,
       max(o.exit_ts)                                    as ultimo_desfecho
  from signal_outcomes o
 where o.tracking_state = 'terminal'
   and o.r_multiple is null
   and o.meta ? 'funding'
   and o.meta->'funding'->>'reason' is not null
 group by 1
 order by 2 desc;

-- 2. os mesmos candidatos, separando as tres coortes da T3.62b do resto
with coorte(rotulo, cohort) as (
  values ('v10', 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'),
         ('v1',  'replay:fa005985-0b55-4820-904c-8ada589e441c'),
         ('v2',  'replay:da706026-319a-451e-950e-7728ca9ae563')
)
select coalesce(c.rotulo, case
         when a.supporting_features->>'cohort' like 'replay:%' then 'outro replay'
         else 'sombra viva'
       end)      as origem,
       count(*)  as candidatos
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  left join coorte c on c.cohort = a.supporting_features->>'cohort'
 where o.tracking_state = 'terminal'
   and o.r_multiple is null
   and o.meta ? 'funding'
   and o.meta->'funding'->>'reason' is not null
 group by 1
 order by 2 desc;

-- 3. os que ficariam de fora por falta de insumo gravado (o `SKIPPED` do script)
select count(*) as sem_insumo_para_recomputar
  from signal_outcomes o
 where o.tracking_state = 'terminal'
   and o.r_multiple is null
   and o.meta ? 'funding'
   and o.meta->'funding'->>'reason' is not null
   and (o.meta->'progress' is null
        or o.meta->'assumed_costs' is null
        or o.entry_ts is null
        or o.exit_ts is null);

commit;
