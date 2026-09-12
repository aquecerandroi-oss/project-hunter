-- D-P24 q01 -- DUMP (CSV) de UMA LINHA POR DECISAO das 542 da mae, com o motivo
-- REAL de saida, os dois pontos do Delta (+80 e +240 min) nas duas unidades e os
-- extremos de FECHAMENTO das quatro janelas de excursao.
--
-- DIAGNOSTICO. A medida principal e `Delta_i = ret_i(240) - ret_i(80)`
-- (MUST-FIX 1 da Astra: MFE nao decompoe o achado do D-P23 -- uma trajetoria
-- pode bater +5 ATR aos 60 min, estar em +3 aos 80 e terminar em -1 aos 240,
-- MFE enorme e contribuicao NEGATIVA). As excursoes viajam como coluna
-- AUXILIAR, e so.
--
-- CONVENCOES (as mesmas do D-P23; ver o cabecalho do q00 deste dia):
--   1. BASE = `candles.open` da barra de entrada (`open_time = entry_ts`), nao
--      `virtual_entry` -- a leitura e BRUTA, sem os 6 bps de `pricing.py:47`;
--   2. o ponto de +h min e o `close` da vela de 1 min que FECHA em
--      `entry_ts + h`, isto e, `open_time = entry_ts + (h-1) min`;
--   3. unidades: o ATR CONGELADO da propria decisao
--      (`agent_signals.supporting_features->'atr'->>'value'`) e o % do preco de
--      entrada. As duas viajam porque o ATR e um denominador POR DECISAO: um
--      grupo com ATR% menor mostra Delta em ATR maior sem que o preco tenha
--      andado mais (`atr_pct` viaja para que isso seja verificavel);
--   4. vela obrigatoriamente `is_final` e `timeframe = '1m'` (PIPELINE §2);
--   5. juncao por `agent_signals.market_id`, nunca por `markets.symbol`
--      (`markets` tem duas linhas por simbolo na binance -- o defeito do D-P23);
--   6. long-only (542/542, q00 §5), entao nao ha multiplicacao por direcao.
--
-- AS QUATRO JANELAS DE EXCURSAO (MUST-FIX 2 da Astra). Com `m` = o minuto em
-- que a vela FECHA, contado da entrada, e `m_saida = (exit_ts-entry_ts)/1min`:
--   * `[1, 80]`   e `[1, 240]`  -- desde a entrada, os dois horizontes do Delta;
--   * `[1, m_saida]`            -- ANTES da saida real;
--   * `[m_saida+1, 240]`        -- DEPOIS da saida real. Esta e a janela que a
--     Astra exigiu: "MFE desde a entrada pode refletir so uma alta ANTERIOR ao
--     stop". Para as 45 saidas por time-stop ela e VAZIA por construcao
--     (`m_saida = 240`), e vazia e o que ela tem de ser -- nunca zero.
-- A particao e exaustiva e disjunta, e nunca atribui a barra de saida uma ordem
-- intrabar que o OHLC nao mostra: saida no OPEN carimba `exit_ts = open_time`
-- (o fechamento daquela barra ja e "depois"), saida intrabar carimba
-- `exit_ts = close_time` (aquela barra e "antes") -- `walker.py:_close`.
-- O que viaja aqui sao os `close` EXTREMOS das janelas, nao um MFE de `high`:
-- a leitura e de FECHAMENTOS, e o nome das colunas diz isso.
--
-- O consumidor deste CSV (`.claude/state/exp-drafts/dp24/analise.py`) recalcula
-- TUDO a partir do caminho minuto a minuto do q02 e compara com estas colunas:
-- duas implementacoes independentes da mesma definicao.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format unaligned
\pset fieldsep ','
\pset tuples_only off

with base as (
  select o.signal_id,
         a.market_id,
         mk.symbol                                               as mercado,
         a.direction::text                                       as direcao,
         o.entry_ts,
         o.exit_ts,
         (o.entry_ts at time zone 'UTC')::date                   as dia,
         (extract(epoch from (o.exit_ts - o.entry_ts)) / 60.0)::int as m_saida,
         case o.result::text
           when 'stop' then 'stop' when 'target' then 'target'
           when 'expired' then 'time-stop' when 'invalidated' then 'context-lost'
           else 'other' end                                      as motivo,
         (a.supporting_features->'atr'->>'value')::numeric        as atr,
         c.open                                                  as entry_open
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
    join markets mk           on mk.id = a.market_id
    join candles c            on c.market_id = a.market_id and c.timeframe = '1m'
                             and c.is_final and c.open_time = o.entry_ts
   where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
     and s.key = 'mean_reversion' and sv.version = 'v1'
     and o.tracking_state::text = 'terminal'
), caminho as (
  select b.signal_id,
         ((extract(epoch from (c.open_time - b.entry_ts)) / 60.0)::int + 1) as m,
         c.close
    from base b
    join candles c on c.market_id = b.market_id and c.timeframe = '1m' and c.is_final
                  and c.open_time >= b.entry_ts
                  and c.open_time <  b.entry_ts + interval '240 min'
), ex as (
  select p.signal_id,
         count(*)                                                       as n_minutos,
         max(p.close) filter (where p.m <= 80)                          as max_close_80,
         min(p.close) filter (where p.m <= 80)                          as min_close_80,
         max(p.close)                                                   as max_close_240,
         min(p.close)                                                   as min_close_240,
         count(*)     filter (where p.m <= b.m_saida)                   as n_antes,
         max(p.close) filter (where p.m <= b.m_saida)                   as max_close_antes,
         min(p.close) filter (where p.m <= b.m_saida)                   as min_close_antes,
         count(*)     filter (where p.m >  b.m_saida)                   as n_depois,
         max(p.close) filter (where p.m >  b.m_saida)                   as max_close_depois,
         min(p.close) filter (where p.m >  b.m_saida)                   as min_close_depois
    from caminho p join base b on b.signal_id = p.signal_id
   group by p.signal_id
)
select b.signal_id                                               as decisao,
       b.mercado,
       b.direcao,
       b.dia,
       (b.entry_ts at time zone 'UTC')                           as entrada_utc,
       (b.exit_ts  at time zone 'UTC')                           as saida_utc,
       b.motivo,
       b.m_saida,
       b.entry_open,
       b.atr,
       round(100 * b.atr / b.entry_open, 6)                      as atr_pct,
       p80.close                                                 as preco_80,
       p240.close                                                as preco_240,
       round((p80.close  - b.entry_open) / b.atr, 8)             as ret80_atr,
       round((p240.close - b.entry_open) / b.atr, 8)             as ret240_atr,
       round(100 * (p80.close  - b.entry_open) / b.entry_open, 8) as ret80_pct,
       round(100 * (p240.close - b.entry_open) / b.entry_open, 8) as ret240_pct,
       e.n_minutos,
       e.max_close_80, e.min_close_80,
       e.max_close_240, e.min_close_240,
       e.n_antes,  e.max_close_antes,  e.min_close_antes,
       e.n_depois, e.max_close_depois, e.min_close_depois
  from base b
  join ex e on e.signal_id = b.signal_id
  left join lateral (
    select c.close from candles c
     where c.market_id = b.market_id and c.timeframe = '1m' and c.is_final
       and c.open_time = b.entry_ts + interval '79 min'
  ) p80 on true
  left join lateral (
    select c.close from candles c
     where c.market_id = b.market_id and c.timeframe = '1m' and c.is_final
       and c.open_time = b.entry_ts + interval '239 min'
  ) p240 on true
 order by b.entry_ts, b.mercado;

commit;
