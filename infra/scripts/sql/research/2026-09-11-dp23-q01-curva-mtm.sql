-- D-P23 q01 -- DUMP (CSV, formato longo) da curva de movimento do preco DEPOIS
-- da entrada, para as duas coortes. Uma linha por (decisao, horizonte).
--
-- DIAGNOSTICO, sem regua causal e sem stop/alvo: mede quanto o preco andou a
-- partir da entrada, nao o que a operacao ganhou.
--
-- DEFINICAO EXATA (as tres escolhas que a Astra fixou, `astra-review-plantao-20260911-0935.md`
-- MUST-FIX 3):
--   1. BASE = `candles.open` da barra de entrada (`open_time = signal_outcomes.entry_ts`),
--      NAO `virtual_entry`: a entrada virtual ja carrega spread+slippage
--      (`pricing.py:47`, `cost_bps = spread/2 + slippage = 6 bps`), e uma curva
--      construida sobre ela ja nasce com a friccao de entrada dentro. Conferido
--      no q00 §4: `virtual_entry = open x 1.0006` nas 915 decisoes, a 1e-9.
--   2. PONTO em +h min = `close` da vela de 1 min que FECHA em `entry_ts + h min`,
--      isto e, a vela cujo `open_time = entry_ts + (h-1) min`. Usar a vela que
--      ABRE em `entry_ts + h` acrescentaria um minuto ao horizonte (cenario de
--      falha nomeado pela Astra).
--   3. UNIDADE = o ATR congelado DA PROPRIA DECISAO,
--      `agent_signals.supporting_features->'atr'->>'value'` (preco absoluto;
--      `mean_reversion_v1.py:294`) -- 15 m/97 barras na mae, 5 m na irma. Nao e
--      um ATR recalculado agora.
--   4. Toda a populacao e `long` (q00 §2), entao `direcao x` e `x(+1)` e a
--      coluna `direcao` viaja no CSV para que isso seja verificavel.
--   5. Vela obrigatoriamente `is_final` e `timeframe = '1m'`. Ausencia sai
--      VAZIA -- nunca preenchida com o preco anterior, nunca com zero. A
--      cobertura por horizonte e declarada pelo consumidor do CSV.
--
-- Horizontes: a uniao do brief (5,10,15,30,60,80,120,240) com a linha do INBOX
-- (5,15,30,60,80,120,180,240) = 5,10,15,30,60,80,120,180,240 para a mae
-- (horizonte 14 400 s = 240 min) e 5,10,15,30,60,80 para a irma (4 800 s = 80 min).
--
-- `no_recorte_par` / `no_recorte_mercado_dia`: os dois recortes de comparacao do
-- brief -- as decisoes da mae nos MESMOS pares (mercado, dia) da irma (o
-- estrito) e nos mesmos mercados E nos mesmos dias (o largo). Viajam no CSV
-- para que o recorte nao exija uma segunda consulta com outra fronteira.
-- NOTA DE METODO (defeito achado e corrigido na primeira passada): `markets`
-- tem DUAS linhas por simbolo na binance (perpetuo e spot, `market_type` --
-- PIPELINE.md §1d item 3), entao juntar por `mk.symbol` DOBRA cada decisao
-- (14 526 linhas em vez de 7 116). A juncao viaja por `agent_signals.market_id`,
-- a identidade que a decisao realmente carrega.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format unaligned
\pset fieldsep ','
\pset tuples_only off

with decisao as (
  select o.signal_id,
         o.meta->>'cohort'                                      as coorte,
         s.key || ' ' || sv.version                             as versao,
         a.market_id                                            as market_id,
         mk.symbol                                              as mercado,
         a.direction::text                                      as direcao,
         o.entry_ts                                             as entry_ts,
         (o.entry_ts at time zone 'UTC')::date                  as dia,
         (a.supporting_features->'atr'->>'value')::numeric      as atr,
         a.expected_holding_s                                   as horizonte_s,
         coalesce(o.meta->'progress'->>'result', '')             as saida_real,
         o.exit_ts                                              as exit_ts
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
    join markets mk           on mk.id = a.market_id
   where o.meta->>'cohort' in ('replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:92c8d080-6009-4a59-9868-31282b1bd493')
     and o.tracking_state::text = 'terminal'
), pares_irma as (
  select distinct mercado, dia from decisao
   where coorte = 'replay:92c8d080-6009-4a59-9868-31282b1bd493'
), base as (
  select d.*,
         c.open as entry_open,
         exists (select 1 from pares_irma p where p.mercado = d.mercado and p.dia = d.dia)
                                                                as no_recorte_par,
         (d.mercado in (select mercado from pares_irma)
          and d.dia   in (select dia from pares_irma))           as no_recorte_mercado_dia
    from decisao d
    join candles c  on c.market_id = d.market_id and c.timeframe = '1m'
                   and c.is_final and c.open_time = d.entry_ts
)
select b.coorte,
       b.versao,
       b.signal_id                                              as decisao,
       b.mercado,
       b.direcao,
       b.dia,
       (b.entry_ts at time zone 'UTC')                          as entrada_utc,
       b.horizonte_s,
       b.saida_real,
       b.no_recorte_par,
       b.no_recorte_mercado_dia,
       b.entry_open,
       b.atr,
       h.h                                                      as horizonte_min,
       px.close                                                 as preco,
       case when px.close is null then ''
            else round((px.close - b.entry_open) / b.atr, 8)::text end as ret_atr
  from base b
  cross join (values (5),(10),(15),(30),(60),(80),(120),(180),(240)) as h(h)
  left join lateral (
    select c.close
      from candles c
     where c.market_id = b.market_id and c.timeframe = '1m' and c.is_final
       and c.open_time = b.entry_ts + make_interval(mins => h.h - 1)
  ) px on true
 where h.h * 60 <= b.horizonte_s
 order by b.coorte, b.entry_ts, b.mercado, h.h;

commit;
