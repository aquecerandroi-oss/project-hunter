-- D-P23 q00 -- CATALOGO das duas coortes antes de medir qualquer curva.
--
-- Diagnostico puro (sem regua causal): a curva de movimento do preco DEPOIS da
-- entrada, medida BRUTA a partir do OPEN da barra de entrada (correcao da Astra:
-- `virtual_entry` ja contem spread+slippage -- `pricing.py:47`, 6 bps), em
-- unidades do ATR congelado da propria decisao
-- (`agent_signals.supporting_features->'atr'->>'value'`, `mean_reversion_v1.py:294`).
--
-- Este arquivo NAO mede nada: ele conta o que existe, para que a cobertura da
-- medicao seja declarada e nao suposta.
--   §1 as duas coortes: n terminal, n com `entry_ts`, n com ATR, direcao
--   §2 direcao (a leitura e long-only por construcao -- se aparecer short, a
--      medicao muda de forma, entao isso e conferido e nao assumido)
--   §3 a janela de cada coorte e os mercados
--   §4 a barra de entrada existe em `candles` 1m `is_final`? (o denominador de
--      todo horizonte comeca aqui)
--   §5 os pares (mercado, dia) que a irma de 5 min negociou -- o recorte de
--      comparacao do brief
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';

\echo '== §1 as duas coortes =='
select o.meta->>'cohort'                                    as coorte,
       s.key || ' ' || sv.version                           as versao,
       count(*)                                             as terminais,
       count(o.entry_ts)                                    as com_entry_ts,
       count((a.supporting_features->'atr'->>'value'))       as com_atr,
       count(*) filter (where (a.supporting_features->'atr'->>'value')::numeric > 0) as atr_positivo,
       min(o.entry_ts)                                      as primeira_entrada,
       max(o.entry_ts)                                      as ultima_entrada,
       count(distinct a.market_id)                          as mercados,
       count(distinct (o.entry_ts at time zone 'UTC')::date) as dias
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where o.meta->>'cohort' in ('replay:fa005985-0b55-4820-904c-8ada589e441c',
                             'replay:92c8d080-6009-4a59-9868-31282b1bd493')
   and o.tracking_state::text = 'terminal'
 group by 1, 2
 order by 1;

\echo '== §2 direcao (long-only e conferido, nao assumido) =='
select o.meta->>'cohort' as coorte, a.direction::text as direcao, count(*)
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where o.meta->>'cohort' in ('replay:fa005985-0b55-4820-904c-8ada589e441c',
                             'replay:92c8d080-6009-4a59-9868-31282b1bd493')
   and o.tracking_state::text = 'terminal'
 group by 1, 2 order by 1, 2;

\echo '== §3 horizonte declarado por versao (expected_holding_s) =='
select o.meta->>'cohort' as coorte,
       a.expected_holding_s as horizonte_s,
       count(*)
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where o.meta->>'cohort' in ('replay:fa005985-0b55-4820-904c-8ada589e441c',
                             'replay:92c8d080-6009-4a59-9868-31282b1bd493')
   and o.tracking_state::text = 'terminal'
 group by 1, 2 order by 1, 2;

\echo '== §4 a barra de entrada existe como vela 1m is_final? =='
select o.meta->>'cohort'                          as coorte,
       count(*)                                   as decisoes,
       count(c.open)                              as com_open_da_barra_de_entrada,
       count(*) filter (where c.open is not null
                          and abs(o.virtual_entry / (c.open * 1.0006) - 1) > 1e-9)
                                                  as open_inconsistente_com_virtual_entry
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  left join candles c on c.market_id = a.market_id
                     and c.timeframe = '1m' and c.is_final
                     and c.open_time = o.entry_ts
 where o.meta->>'cohort' in ('replay:fa005985-0b55-4820-904c-8ada589e441c',
                             'replay:92c8d080-6009-4a59-9868-31282b1bd493')
   and o.tracking_state::text = 'terminal'
 group by 1 order by 1;

\echo '== §5 o recorte de comparacao: pares (mercado, dia) da irma de 5 min =='
with irma as (
  select distinct mk.symbol as mercado, (o.entry_ts at time zone 'UTC')::date as dia
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets mk      on mk.id = a.market_id
   where o.meta->>'cohort' = 'replay:92c8d080-6009-4a59-9868-31282b1bd493'
     and o.tracking_state::text = 'terminal'
), mae as (
  select mk.symbol as mercado, (o.entry_ts at time zone 'UTC')::date as dia
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets mk      on mk.id = a.market_id
   where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
     and o.tracking_state::text = 'terminal'
)
select (select count(*) from irma)                                  as pares_da_irma,
       (select count(distinct mercado) from irma)                   as mercados_da_irma,
       (select count(distinct dia) from irma)                       as dias_da_irma,
       (select count(*) from mae)                                   as decisoes_da_mae,
       (select count(*) from mae m join irma i
          on i.mercado = m.mercado and i.dia = m.dia)               as mae_em_par_exato,
       (select count(*) from mae m
         where m.mercado in (select mercado from irma)
           and m.dia     in (select dia from irma))                 as mae_em_mercado_e_dia;

commit;
