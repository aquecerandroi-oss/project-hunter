-- D-P9 q02 -- OS -34 R DA HORA 21Z (18 BRT) DE 09/09, ABERTOS.
-- O q01 localizou o fato: a hora de DECISAO 21:00Z de 09/09 soma -34,02 R em
-- 39 decisoes, 35 com R liquido, com taxa de acerto 0,0 %. Aqui ele e aberto por
-- mercado, por versao, e por APOSTA UNICA -- (mercado, barra de 15 min da
-- observacao) -- para separar "muitas perdas" de "a mesma perda contada por
-- varias versoes". A barra e date_bin('15 min', observation_ts): a ultima
-- barra fechada que a decisao leu (docs/PIPELINE.md 9b item 1).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. a lista inteira das decisoes das 21Z
with pop as (
  select s.key as familia, sv.version as versao, mk.symbol as mercado,
         a.emitted_at, (a.supporting_features->>'observation_ts')::timestamptz as obs_ts,
         o.entry_ts, o.exit_ts, o.result::text as saida,
         o.virtual_entry, o.virtual_stop, o.exit_price,
         o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_ex,
         o.meta->>'r_net_reason' as r_net_reason,
         extract(epoch from (o.exit_ts - o.entry_ts))/60 as minutos
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
select mercado, familia || ' ' || versao as versao,
       to_char(emitted_at at time zone 'America/Sao_Paulo','HH24:MI:SS') as decisao_brt,
       to_char(obs_ts at time zone 'America/Sao_Paulo','HH24:MI') as barra_obs_brt,
       to_char(entry_ts at time zone 'America/Sao_Paulo','HH24:MI:SS') as entrada_brt,
       to_char(exit_ts at time zone 'America/Sao_Paulo','DD HH24:MI:SS') as saida_brt,
       round(minutos::numeric,1) as min_no_trade, saida,
       virtual_entry, virtual_stop, exit_price,
       round(r_net,4) r_net, round(r_ex,4) r_ex, r_net_reason
  from pop order by mercado, versao;

-- 2. por mercado
with pop as (
  select mk.symbol as mercado, sv.version, a.market_id,
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
     and a.emitted_at >= '2026-09-09 21:00:00+00' and a.emitted_at < '2026-09-09 22:00:00+00'
)
select mercado, count(*) n_pooled, count(distinct version) versoes,
       count(distinct (market_id::text || barra::text)) apostas_unicas,
       count(r_net) com_r, round(sum(r_net),4) soma_r, round(avg(r_net),4) media_r,
       count(*) filter (where saida = 'stop') stops,
       count(*) filter (where saida = 'target') alvos,
       count(*) filter (where saida = 'expired') tempo
  from pop group by 1 order by 6 nulls last;

-- 3. por versao
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
     and a.emitted_at >= '2026-09-09 21:00:00+00' and a.emitted_at < '2026-09-09 22:00:00+00'
)
select versao, count(*) n, count(distinct market_id) mercados, count(r_net) com_r,
       round(sum(r_net),4) soma_r, round(avg(r_net),4) media_r,
       count(*) filter (where saida = 'stop') stops,
       count(*) filter (where saida = 'target') alvos,
       count(*) filter (where saida = 'expired') tempo
  from pop group by 1 order by 5;

-- 4. apostas unicas: quantas versoes por (mercado, barra de 15 min)
with pop as (
  select mk.symbol as mercado, a.market_id,
         date_bin('15 minutes', (a.supporting_features->>'observation_ts')::timestamptz, timestamptz 'epoch') as barra,
         s.key || ' ' || sv.version as versao, o.result::text as saida, o.r_multiple as r_net
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
), apostas as (
  select mercado, barra, count(*) versoes, string_agg(versao, ',' order by versao) quais,
         count(r_net) com_r, round(sum(r_net),4) soma_r, round(avg(r_net),4) media_r,
         count(*) filter (where saida = 'stop') stops
    from pop group by 1, 2
)
select mercado, to_char(barra at time zone 'America/Sao_Paulo','DD/MM HH24:MI') barra_brt,
       versoes, quais, com_r, soma_r, media_r, stops
  from apostas order by media_r nulls last;

-- 5. o placar da hora: pooled vs unico
with pop as (
  select a.market_id,
         date_bin('15 minutes', (a.supporting_features->>'observation_ts')::timestamptz, timestamptz 'epoch') as barra,
         o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and a.emitted_at >= '2026-09-09 21:00:00+00' and a.emitted_at < '2026-09-09 22:00:00+00'
), por_aposta as (
  select market_id, barra, avg(r_net) r_aposta, count(*) versoes from pop group by 1, 2
)
select (select count(*) from pop) as decisoes_pooled,
       (select round(sum(r_net),4) from pop) as soma_r_pooled,
       (select count(*) from por_aposta) as apostas_unicas,
       (select round(sum(r_aposta),4) from por_aposta) as soma_r_unica,
       (select round(avg(versoes),2) from por_aposta) as versoes_por_aposta;

commit;
