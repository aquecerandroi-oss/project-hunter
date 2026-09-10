-- D-P9 q01 -- O DIA EM BRASILIA E A HORA DA DECISAO / ENTRADA / SAIDA.
-- O q00 mostrou que nenhum recorte por DATA UTC devolve -31,08 R em 420
-- desfechos. Duas suspeitas testadas aqui: (a) o dia do brief e o de BRASILIA
-- (UTC-3), que puxa as horas 00-03Z do dia seguinte para dentro; (b) a hora
-- 21Z e de DECISAO, e boa parte das saidas dela cai no dia seguinte.
-- A populacao (CTE `pop`) e repetida em cada statement de proposito: uma
-- transacao READ ONLY nao cria view temporaria, e um CTE vale um statement so.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1/2/3. dia em Brasilia por eixo, e a hora (UTC e BRT) da decisao e da saida
with pop as (
  select a.id as signal_id, s.key as familia, sv.version as versao,
         mk.symbol as mercado, a.market_id, a.emitted_at,
         o.entry_ts, o.exit_ts, o.result::text as saida,
         o.tracking_state::text as estado,
         o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_ex
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
)
select 'A dia BRT - decisao' as bloco,
       (emitted_at at time zone 'America/Sao_Paulo')::date::text as chave,
       null::int as h_utc, null::int as h_brt,
       count(*) n, count(r_net) com_r, round(sum(r_net),4) soma_r,
       round(avg(r_net),4) media_r, round(sum(r_ex),4) soma_r_ex,
       round(100.0*count(*) filter (where r_net>0)/nullif(count(r_net),0),1) acerto_pct
  from pop group by 2
union all
select 'B dia BRT - entrada', (entry_ts at time zone 'America/Sao_Paulo')::date::text,
       null, null, count(*), count(r_net), round(sum(r_net),4), round(avg(r_net),4),
       round(sum(r_ex),4), round(100.0*count(*) filter (where r_net>0)/nullif(count(r_net),0),1)
  from pop where entry_ts is not null group by 2
union all
select 'C dia BRT - saida', (exit_ts at time zone 'America/Sao_Paulo')::date::text,
       null, null, count(*), count(r_net), round(sum(r_net),4), round(avg(r_net),4),
       round(sum(r_ex),4), round(100.0*count(*) filter (where r_net>0)/nullif(count(r_net),0),1)
  from pop where exit_ts is not null group by 2
union all
select 'D hora da DECISAO', (emitted_at at time zone 'UTC')::date::text,
       extract(hour from emitted_at at time zone 'UTC')::int,
       extract(hour from emitted_at at time zone 'America/Sao_Paulo')::int,
       count(*), count(r_net), round(sum(r_net),4), round(avg(r_net),4),
       round(sum(r_ex),4), round(100.0*count(*) filter (where r_net>0)/nullif(count(r_net),0),1)
  from pop where emitted_at >= '2026-09-08' and emitted_at < '2026-09-10' group by 2,3,4
union all
select 'E hora da SAIDA', (exit_ts at time zone 'UTC')::date::text,
       extract(hour from exit_ts at time zone 'UTC')::int,
       extract(hour from exit_ts at time zone 'America/Sao_Paulo')::int,
       count(*), count(r_net), round(sum(r_net),4), round(avg(r_net),4),
       round(sum(r_ex),4), round(100.0*count(*) filter (where r_net>0)/nullif(count(r_net),0),1)
  from pop where exit_ts >= '2026-09-08' and exit_ts < '2026-09-11' group by 2,3,4
 order by 1,2,3;

-- 4. o que ainda esta aberto (o brief foi escrito por volta de 03:45Z de 10/09)
with pop as (
  select a.emitted_at, o.tracking_state::text as estado, o.result::text as saida,
         o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
)
select estado, saida, count(*) n, count(r_net) com_r,
       round(sum(r_net),4) soma_r, min(emitted_at) de, max(emitted_at) ate
  from pop group by 1,2 order by 1,2;

commit;
