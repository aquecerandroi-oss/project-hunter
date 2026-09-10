-- D-P9 q06 -- O DIA 08/09 (o "+32 R") COM A MESMA DECOMPOSICAO, E A TABELA DE
-- DEFINICOES CANDIDATAS.
-- Nenhum recorte testado ate aqui devolve exatamente "-31,08 R em 420 desfechos"
-- (09/09) nem "+32 R" (08/09). Entao o bloco 1 mede varias definicoes candidatas
-- lado a lado nos dois dias, para que o leitor saiba QUAL numero e qual.
-- Os blocos 2-4 repetem, para 08/09, exatamente o que o q03 fez para 09/09.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. definicoes candidatas, dois dias
with base as (
  select s.key as familia, sv.version, a.emitted_at, o.exit_ts,
         o.tracking_state::text as estado, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_ex
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
), rot as (
  select *,
         (emitted_at at time zone 'America/Sao_Paulo')::date as dia_dec_brt,
         (emitted_at at time zone 'UTC')::date                as dia_dec_utc,
         (exit_ts   at time zone 'America/Sao_Paulo')::date    as dia_sai_brt,
         (exit_ts   at time zone 'UTC')::date                  as dia_sai_utc,
         (familia = 'mean_reversion' and version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
           or (familia = 'mean_reversion_h1' and version = 'v1') as no_brief,
         familia like 'mean_reversion%' as familia_toda
    from base
)
select 'A familia do brief / decisao BRT'  as definicao, dia_dec_brt as dia,
       count(*) n, count(r_net) com_r, round(sum(r_net),4) soma_r
  from rot where no_brief and estado='terminal' and dia_dec_brt between '2026-09-08' and '2026-09-09' group by 2
union all
select 'B familia do brief / decisao UTC', dia_dec_utc, count(*), count(r_net), round(sum(r_net),4)
  from rot where no_brief and estado='terminal' and dia_dec_utc between '2026-09-08' and '2026-09-09' group by 2
union all
select 'C familia do brief / saida UTC', dia_sai_utc, count(*), count(r_net), round(sum(r_net),4)
  from rot where no_brief and estado='terminal' and dia_sai_utc between '2026-09-08' and '2026-09-09' group by 2
union all
select 'D mean_reversion* toda / decisao UTC', dia_dec_utc, count(*), count(r_net), round(sum(r_net),4)
  from rot where familia_toda and estado='terminal' and dia_dec_utc between '2026-09-08' and '2026-09-09' group by 2
union all
select 'E mean_reversion* toda / decisao BRT', dia_dec_brt, count(*), count(r_net), round(sum(r_net),4)
  from rot where familia_toda and estado='terminal' and dia_dec_brt between '2026-09-08' and '2026-09-09' group by 2
union all
select 'F TODAS as familias / decisao UTC', dia_dec_utc, count(*), count(r_net), round(sum(r_net),4)
  from rot where estado='terminal' and dia_dec_utc between '2026-09-08' and '2026-09-09' group by 2
union all
select 'G TODAS as familias / decisao BRT', dia_dec_brt, count(*), count(r_net), round(sum(r_net),4)
  from rot where estado='terminal' and dia_dec_brt between '2026-09-08' and '2026-09-09' group by 2
union all
select 'H familia do brief / r_ex_funding / decisao UTC', dia_dec_utc, count(*), count(r_ex), round(sum(r_ex),4)
  from rot where no_brief and estado='terminal' and dia_dec_utc between '2026-09-08' and '2026-09-09' group by 2
 order by 1, 2;

-- 2. 08/09 BRT hora a hora (mesmo formato do q03 bloco 4)
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
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-08'
), por_mercado_barra as (
  select extract(hour from emitted_at at time zone 'America/Sao_Paulo')::int h_brt,
         market_id, barra, avg(r_net) r_aposta from pop group by 1,2,3
), pooled as (
  select extract(hour from emitted_at at time zone 'America/Sao_Paulo')::int h_brt,
         count(*) n, count(r_net) com_r, sum(r_net) soma_r,
         count(*) filter (where saida='stop') stops,
         count(*) filter (where saida='target') alvos,
         count(*) filter (where saida='expired') tempo,
         100.0*count(*) filter (where r_net>0)/nullif(count(r_net),0) acerto
    from pop group by 1
)
select p.h_brt, (p.h_brt + 3) % 24 as h_utc, p.n n_pooled, p.com_r,
       round(p.soma_r,4) soma_r_pooled, round(p.soma_r/nullif(p.com_r,0),4) media_pooled,
       round(p.acerto,1) acerto_pct, p.stops, p.alvos, p.tempo,
       (select count(*) from por_mercado_barra b where b.h_brt = p.h_brt) apostas,
       round((select sum(r_aposta) from por_mercado_barra b where b.h_brt = p.h_brt),4) soma_r_aposta
  from pooled p order by p.h_brt;

-- 3. 08/09 BRT por mercado (melhores e piores)
with pop as (
  select mk.symbol, a.market_id,
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
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-08'
)
select symbol, count(*) n, count(distinct version) versoes,
       count(distinct (market_id::text || barra::text)) apostas,
       round(sum(r_net),4) soma_r, round(avg(r_net),4) media_r,
       count(*) filter (where saida='stop') stops, count(*) filter (where saida='target') alvos
  from pop group by 1 order by 5 desc nulls last;

-- 4. 08/09 BRT por versao e por tipo de saida
with pop as (
  select s.key || ' ' || sv.version as versao, o.result::text as saida, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-08'
)
select versao, count(*) n, count(r_net) com_r, round(sum(r_net),4) soma_r,
       round(avg(r_net),4) media_r,
       round(100.0*count(*) filter (where r_net>0)/nullif(count(r_net),0),1) acerto_pct,
       count(*) filter (where saida='stop') stops, count(*) filter (where saida='target') alvos,
       count(*) filter (where saida='expired') tempo
  from pop group by 1 order by 4 desc;

commit;
