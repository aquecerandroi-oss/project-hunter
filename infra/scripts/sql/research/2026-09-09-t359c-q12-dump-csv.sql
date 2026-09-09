-- T3.59c q12 — dump por decisao para o bootstrap de blocos de dia (CSV no stdout).
-- Uma linha por desfecho terminal do PAI de cada braco, com a marca "a filha com a
-- janela manteve", mais as decisoes que so existem na filha (classe=filha_extra).
-- Metodo identico ao da T3.52d q12. SOMENTE LEITURA.
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
           'replay:71c76d86-ceb0-4d48-b3be-88c3c055061e',
           'replay:4a60a3dc-334c-4faa-9790-c321063ff23e',
           'replay:4ed2ec88-c4cd-4fa2-aeb9-eb432fd271dd',
           'replay:29bc81bf-26ea-4255-a9cb-46bab6d7c99f',
           'replay:fbb65b47-d8dc-4abb-b64f-0ef1f24faf3e',
           'replay:9a48a940-5957-4b07-a9c4-4d4521adc907')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
), arms as (
  select * from (values
    ('H1','mean_reversion','v10','v12'),
    ('C1','mean_reversion','v10','v13'),
    ('H2','momentum','v11','v12'),
    ('C2','momentum','v11','v13')
  ) as t(braco, fam, pai, filha)
), pai as (
  select x.braco, d.* from arms x join d on d.familia = x.fam and d.versao = x.pai
), filha as (
  select x.braco, d.* from arms x join d on d.familia = x.fam and d.versao = x.filha
)
select braco, classe, dia, symbol, bar, mantida, r_net, r_bruto from (
  select p.braco, 'pai' as classe, (p.bar at time zone 'UTC')::date::text as dia,
         p.symbol, p.bar,
         case when exists (select 1 from filha f where f.braco = p.braco
                             and f.symbol = p.symbol and f.bar = p.bar and f.lado = p.lado)
              then 1 else 0 end as mantida,
         p.r_net,
         round((p.exit_base - p.p_entry/1.0006)/nullif(p.risk,0), 6) as r_bruto
    from pai p
  union all
  select f.braco, 'filha_extra', (f.bar at time zone 'UTC')::date::text,
         f.symbol, f.bar, 1, f.r_net,
         round((f.exit_base - f.p_entry/1.0006)/nullif(f.risk,0), 6)
    from filha f
   where not exists (select 1 from pai p where p.braco = f.braco
                       and p.symbol = f.symbol and p.bar = f.bar and p.lado = f.lado)
) x order by braco, bar, symbol
\g (format=csv)
commit;
