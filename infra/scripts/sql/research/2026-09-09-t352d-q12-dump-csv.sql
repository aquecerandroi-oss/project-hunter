-- T3.52d q12 — dump por decisao para o bootstrap de blocos de dia (CSV no stdout).
-- Uma linha por desfecho terminal do PAI, com a marca "a filha com portao manteve".
-- Mais as decisoes que so existem na filha (marcadas classe=filha_extra).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
with d as (
  select s.key as familia, sv.version as versao, m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         a.direction::text as lado, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.meta->>'cohort' in (
           'replay:9d99748b-21b9-44a7-8980-32c37b931e6e',
           'replay:5bcfbda1-9365-467e-ad14-583fcfa9ae4b',
           'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd',
           'replay:4a60a3dc-334c-4faa-9790-c321063ff23e')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
), pai as (select * from d where versao in ('v6','v8')),
   filha as (select * from d where versao = 'v11')
select familia, classe, dia, symbol, bar, mantida, r_net, r_bruto from (
  select p.familia, 'pai' as classe, (p.bar at time zone 'UTC')::date::text as dia,
         p.symbol, p.bar,
         case when exists (select 1 from filha f where f.familia = p.familia
                             and f.symbol = p.symbol and f.bar = p.bar and f.lado = p.lado)
              then 1 else 0 end as mantida,
         p.r_net,
         round((p.exit_base - p.p_entry/1.0006)/nullif(p.risk,0), 6) as r_bruto
    from pai p
  union all
  select f.familia, 'filha_extra', (f.bar at time zone 'UTC')::date::text,
         f.symbol, f.bar, 1, f.r_net,
         round((f.exit_base - f.p_entry/1.0006)/nullif(f.risk,0), 6)
    from filha f
   where not exists (select 1 from pai p where p.familia = f.familia
                       and p.symbol = f.symbol and p.bar = f.bar and p.lado = f.lado)
) x order by familia, bar, symbol
\g (format=csv)
commit;
