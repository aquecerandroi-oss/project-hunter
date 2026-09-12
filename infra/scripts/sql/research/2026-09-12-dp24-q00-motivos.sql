-- D-P24 q00 -- CATALOGO dos motivos REAIS de saida das 542 decisoes da mae
-- (`mean_reversion v1`, coorte `replay:fa005985-0b55-4820-904c-8ada589e441c`,
-- a mesma coorte congelada da T3.62b e do D-P23).
--
-- DIAGNOSTICO. A pergunta do D-P24 e descritiva: o movimento bruto adicional
-- entre +80 e +240 min que o D-P23 mediu (media pareada +0,3007 ATR, IC 95 %
-- [+0,0071; +0,5820]) se acumula nas decisoes que sairam por TIME-STOP -- onde
-- um horizonte mais longo poderia toca-lo -- ou nas que sairam por STOP, onde
-- ele nunca poderia ser tocado porque a posicao ja estava fechada? Nada aqui
-- diz o que outra politica de saida TERIA rendido.
--
-- Este arquivo nao mede nada: ele **declara a populacao** e checa o que a
-- leitura vai supor. Cinco checagens, cada uma fechando um jeito de errar:
--   §1 o motivo canonico (o vocabulario do brief) sobre `signal_outcomes.result`
--      + `tracking_state`, com n, dias e primeira/ultima entrada por grupo;
--   §2 `result` (coluna) contra `meta->'progress'->>'result'` (envelope): o
--      D-P23 leu o SEGUNDO, este le o PRIMEIRO, e se os dois discordassem em
--      uma linha a decomposicao mudaria de grupo sem que ninguem visse;
--   §3 duracao real por grupo e `m_saida` (o minuto em que a vela da saida
--      fecha, contado da entrada) -- e o que particiona as janelas de excursao
--      em "antes" e "depois" da saida;
--   §4 cobertura de velas: a barra de entrada, os endpoints de +80 e +240 e os
--      240 minutos do caminho. Cobertura declarada, nunca suposta;
--   §5 direcao e horizonte declarado (a leitura e long-only e o Delta de 240 min
--      so faz sentido se o horizonte da versao for 14 400 s em todas).
--
-- CONVENCOES (as mesmas do D-P23, `2026-09-11-dp23-q01-curva-mtm.sql`):
--   * BASE = `candles.open` da barra de entrada (`open_time = entry_ts`), NAO
--     `virtual_entry` (que ja carrega 6 bps de spread+slippage, `pricing.py:47`);
--   * o ponto de +h min e o `close` da vela de 1 min que FECHA em `entry_ts + h`,
--     isto e, `open_time = entry_ts + (h-1) min`;
--   * vela obrigatoriamente `is_final` e `timeframe = '1m'` (PIPELINE §2);
--   * a juncao viaja por `agent_signals.market_id`, nunca por `markets.symbol`:
--     `markets` tem DUAS linhas por simbolo na binance (perpetuo e spot,
--     PIPELINE §1d item 3) e juntar por simbolo DOBRA cada decisao -- o defeito
--     achado e corrigido no D-P23.
--
-- `m_saida` = (exit_ts - entry_ts)/1min. `exit_ts` e `open_time` da barra de
-- saida quando a saida acontece no OPEN dela e `close_time` quando e intrabar
-- (`walker.py:_close`), entao `antes = [1, m_saida]` e `depois = [m_saida+1, 240]`
-- e uma particao que nunca atribui a barra de saida uma ordem intrabar que o
-- OHLC nao mostra (MUST-FIX 2 da Astra).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';

\echo '== §1 motivo canonico do brief: n, dias, primeira/ultima entrada =='
with d as (
  select o.signal_id,
         o.result::text                                           as result,
         o.tracking_state::text                                   as tracking_state,
         o.entry_ts,
         o.exit_ts,
         (o.entry_ts at time zone 'UTC')::date                    as dia,
         a.market_id
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
     and s.key = 'mean_reversion' and sv.version = 'v1'
     and o.tracking_state::text = 'terminal'
)
select case
         when tracking_state <> 'terminal' then 'other'
         when result = 'stop'        then 'stop'
         when result = 'target'      then 'target'
         when result = 'expired'     then 'time-stop'
         when result = 'invalidated' then 'context-lost'
         else 'other'
       end                                                        as motivo,
       result,
       tracking_state,
       count(*)                                                   as n,
       count(distinct dia)                                        as dias,
       count(distinct market_id)                                  as mercados,
       min(entry_ts at time zone 'UTC')                           as primeira_entrada,
       max(entry_ts at time zone 'UTC')                           as ultima_entrada
  from d
 group by 1, 2, 3
 order by n desc;

\echo '== §1b o mesmo, sem o filtro `terminal`: nada pode estar escondido =='
select o.tracking_state::text                                     as tracking_state,
       o.result::text                                             as result,
       count(*)                                                   as n
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
   and s.key = 'mean_reversion' and sv.version = 'v1'
 group by 1, 2 order by n desc;

\echo '== §2 a coluna `result` contra o envelope `meta.progress.result` =='
select count(*)                                                                as n,
       count(*) filter (
         where o.result::text <> coalesce(o.meta->'progress'->>'result', '')
       )                                                                       as discordam,
       count(*) filter (where o.exit_ts is null)                               as exit_ts_nulo,
       count(*) filter (where o.entry_ts is null)                              as entry_ts_nulo,
       count(*) filter (where date_trunc('minute', o.exit_ts) <> o.exit_ts)    as exit_ts_fora_do_minuto
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
   and s.key = 'mean_reversion' and sv.version = 'v1'
   and o.tracking_state::text = 'terminal';

\echo '== §3 duracao real e m_saida por motivo (particao das janelas) =='
with d as (
  select case o.result::text
           when 'stop' then 'stop' when 'target' then 'target'
           when 'expired' then 'time-stop' when 'invalidated' then 'context-lost'
           else 'other' end                                       as motivo,
         (extract(epoch from (o.exit_ts - o.entry_ts)) / 60.0)::int as m_saida
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
     and s.key = 'mean_reversion' and sv.version = 'v1'
     and o.tracking_state::text = 'terminal'
)
select motivo, count(*) as n,
       min(m_saida)                                                        as minimo,
       round(percentile_cont(0.25) within group (order by m_saida)::numeric, 1) as p25,
       round(percentile_cont(0.50) within group (order by m_saida)::numeric, 1) as p50,
       round(percentile_cont(0.75) within group (order by m_saida)::numeric, 1) as p75,
       max(m_saida)                                                        as maximo,
       count(*) filter (where m_saida <= 80)                               as saiu_ate_80,
       count(*) filter (where m_saida > 80 and m_saida < 240)              as saiu_entre_80_e_240,
       count(*) filter (where m_saida >= 240)                              as saiu_em_240_ou_depois
  from d group by 1 order by n desc;

\echo '== §4 cobertura de velas: entrada, +80, +240 e os 240 minutos do caminho =='
with d as (
  select o.signal_id, o.entry_ts, a.market_id
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
     and s.key = 'mean_reversion' and sv.version = 'v1'
     and o.tracking_state::text = 'terminal'
), cob as (
  select d.signal_id,
         exists (select 1 from candles c
                  where c.market_id = d.market_id and c.timeframe = '1m' and c.is_final
                    and c.open_time = d.entry_ts)                   as tem_entrada,
         exists (select 1 from candles c
                  where c.market_id = d.market_id and c.timeframe = '1m' and c.is_final
                    and c.open_time = d.entry_ts + interval '79 min') as tem_80,
         exists (select 1 from candles c
                  where c.market_id = d.market_id and c.timeframe = '1m' and c.is_final
                    and c.open_time = d.entry_ts + interval '239 min') as tem_240,
         (select count(*) from candles c
           where c.market_id = d.market_id and c.timeframe = '1m' and c.is_final
             and c.open_time >= d.entry_ts
             and c.open_time <  d.entry_ts + interval '240 min')      as minutos_finais
    from d
)
select count(*)                                            as n,
       count(*) filter (where tem_entrada)                 as com_barra_de_entrada,
       count(*) filter (where tem_80)                       as com_endpoint_80,
       count(*) filter (where tem_240)                      as com_endpoint_240,
       count(*) filter (where minutos_finais = 240)         as com_240_minutos_completos,
       min(minutos_finais)                                  as minimo_de_minutos,
       sum(240 - minutos_finais)                            as minutos_faltando_no_total
  from cob;

\echo '== §5 direcao, horizonte declarado e ATR presente =='
select a.direction::text                                    as direcao,
       a.expected_holding_s                                 as horizonte_s,
       count(*)                                             as n,
       count(*) filter (
         where (a.supporting_features->'atr'->>'value') is null
      )                                                     as sem_atr,
       count(*) filter (
         where (a.supporting_features->'atr'->>'value')::numeric <= 0
      )                                                     as atr_nao_positivo
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
   and s.key = 'mean_reversion' and sv.version = 'v1'
   and o.tracking_state::text = 'terminal'
 group by 1, 2 order by n desc;

\echo '== §6 a(s) decisao(oes) NAO terminal(is) da coorte: por que nao tem Delta =='
select o.tracking_state::text                               as tracking_state,
       o.result::text                                       as result,
       o.no_entry_reason,
       o.censored_reason,
       (o.entry_ts is null)                                 as sem_entry_ts,
       count(*)                                             as n
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
   and s.key = 'mean_reversion' and sv.version = 'v1'
   and o.tracking_state::text <> 'terminal'
 group by 1, 2, 3, 4, 5 order by n desc;

commit;
