-- D-P9 q03 -- COMO SE SAIU (stop / alvo / tempo / invalidacao) E QUANTA
-- DUPLICACAO EXISTE POR TRAS DOS NUMEROS AGREGADOS.
-- Descoberta do q02 que obriga esta consulta: NEARUSDT aparece com 3 pares
-- (market_id, barra) para 2 barras -- ha DUAS linhas de `markets` com o mesmo
-- simbolo (spot e perpetual, ambas monitoradas). Entao "aposta unica" tem duas
-- chaves possiveis e as duas sao reportadas: (market_id, barra) e (ATIVO, barra),
-- esta ultima fundindo spot e perpetuo do mesmo simbolo.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. as 39 decisoes das 21Z por tipo de mercado
with pop as (
  select mk.symbol, mk.market_type::text as tipo, s.key || ' ' || sv.version as versao,
         o.result::text as saida, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and a.emitted_at >= '2026-09-09 21:00:00+00' and a.emitted_at < '2026-09-09 22:00:00+00'
)
select tipo, count(*) n, count(distinct symbol) simbolos,
       round(sum(r_net),4) soma_r, round(avg(r_net),4) media_r,
       count(*) filter (where saida = 'stop') stops,
       count(*) filter (where saida = 'target') alvos,
       count(*) filter (where saida = 'expired') tempo,
       count(*) filter (where saida = 'invalidated') contexto
  from pop group by 1 order by 4;

-- 2. saidas do DIA INTEIRO 09/09 BRT (decisao), por tipo de saida
with pop as (
  select o.result::text as saida, o.r_multiple as r_net,
         extract(epoch from (o.exit_ts - o.entry_ts))/60 as minutos
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
)
select saida, count(*) n, count(r_net) com_r, round(sum(r_net),4) soma_r,
       round(avg(r_net),4) media_r, round(min(r_net),4) pior, round(max(r_net),4) melhor,
       round(avg(minutos)::numeric,1) minutos_medios
  from pop group by 1 order by 4;

-- 3. os que nem entraram (no_entry) no dia -- o denominador escondido
with pop as (
  select o.no_entry_reason, count(*) n
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'no_entry'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
   group by 1
)
select * from pop order by n desc;

-- 4. hora a hora do dia 09/09 BRT: pooled x aposta unica (duas chaves)
with pop as (
  select a.market_id, mk.symbol, a.emitted_at,
         date_bin('15 minutes', (a.supporting_features->>'observation_ts')::timestamptz, timestamptz 'epoch') as barra,
         o.result::text as saida, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
), por_mercado_barra as (
  select extract(hour from emitted_at at time zone 'America/Sao_Paulo')::int h_brt,
         market_id, barra, avg(r_net) r_aposta
    from pop group by 1,2,3
), por_ativo_barra as (
  select extract(hour from emitted_at at time zone 'America/Sao_Paulo')::int h_brt,
         symbol, barra, avg(r_net) r_aposta
    from pop group by 1,2,3
), pooled as (
  select extract(hour from emitted_at at time zone 'America/Sao_Paulo')::int h_brt,
         count(*) n, count(r_net) com_r, sum(r_net) soma_r,
         count(*) filter (where saida = 'stop') stops,
         count(*) filter (where saida = 'target') alvos,
         count(*) filter (where saida = 'expired') tempo,
         100.0*count(*) filter (where r_net > 0)/nullif(count(r_net),0) acerto
    from pop group by 1
)
select p.h_brt, (p.h_brt + 3) % 24 as h_utc, p.n as n_pooled, p.com_r,
       round(p.soma_r,4) soma_r_pooled, round(p.soma_r/nullif(p.com_r,0),4) media_pooled,
       round(p.acerto,1) acerto_pct, p.stops, p.alvos, p.tempo,
       (select count(*) from por_mercado_barra b where b.h_brt = p.h_brt) apostas_mkt,
       round((select sum(r_aposta) from por_mercado_barra b where b.h_brt = p.h_brt),4) soma_r_mkt,
       (select count(*) from por_ativo_barra c where c.h_brt = p.h_brt) apostas_ativo,
       round((select sum(r_aposta) from por_ativo_barra c where c.h_brt = p.h_brt),4) soma_r_ativo
  from pooled p order by p.h_brt;

-- 5. o dia 09/09 BRT por mercado (os dez piores) com duplicacao
with pop as (
  select mk.symbol, mk.market_type::text tipo, a.market_id,
         date_bin('15 minutes', (a.supporting_features->>'observation_ts')::timestamptz, timestamptz 'epoch') as barra,
         sv.version, o.result::text as saida, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
)
select symbol, count(*) n, count(distinct tipo) tipos, count(distinct version) versoes,
       count(distinct (market_id::text || barra::text)) apostas,
       round(sum(r_net),4) soma_r, round(avg(r_net),4) media_r,
       count(*) filter (where saida = 'stop') stops, count(*) filter (where saida='target') alvos
  from pop group by 1 order by 6 nulls last limit 12;

-- 6. o dia 09/09 BRT por versao
with pop as (
  select s.key || ' ' || sv.version as versao, a.market_id,
         o.result::text as saida, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
)
select versao, count(*) n, count(r_net) com_r, round(sum(r_net),4) soma_r,
       round(avg(r_net),4) media_r,
       round(100.0*count(*) filter (where r_net > 0)/nullif(count(r_net),0),1) acerto_pct,
       count(*) filter (where saida = 'stop') stops, count(*) filter (where saida='target') alvos,
       count(*) filter (where saida = 'expired') tempo
  from pop group by 1 order by 4;

commit;
