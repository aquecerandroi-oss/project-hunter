-- T3.59c q11 — pareamento por (mercado, barra de origem, lado) entre cada braco da
-- EXP-0023 e o pai dele. Metodo da T3.52d q11 (PIPELINE §4b item 11: a filha NAO e
-- subconjunto das DECISOES do pai, so das BARRAS). SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with d as (
  select s.key as familia, sv.version as versao, m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         a.direction::text as lado, o.r_multiple as r_net
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
    ('H1 mean_reversion v12 vs v10','mean_reversion','v10','v12'),
    ('C1 mean_reversion v13 vs v10','mean_reversion','v10','v13'),
    ('H2 momentum v12 vs v11','momentum','v11','v12'),
    ('C2 momentum v13 vs v11','momentum','v11','v13')
  ) as t(braco, fam, pai, filha)
), pai as (
  select x.braco, d.symbol, d.bar, d.lado, d.r_net
    from arms x join d on d.familia = x.fam and d.versao = x.pai
), filha as (
  select x.braco, d.symbol, d.bar, d.lado, d.r_net
    from arms x join d on d.familia = x.fam and d.versao = x.filha
)
select coalesce(p.braco, f.braco) as braco,
       case when p.bar is not null and f.bar is not null then '1 nos dois'
            when p.bar is not null then '2 so no pai (removida pela janela)'
            else '3 so na filha (o slot divergiu)' end as classe,
       count(*) as n,
       round(avg(p.r_net), 4) as exp_pai_r,
       round(avg(f.r_net), 4) as exp_filha_r,
       count(*) filter (where p.r_net is not null and f.r_net is not null
                          and abs(p.r_net - f.r_net) > 1e-9) as divergem_no_r
  from pai p
  full outer join filha f
    on f.braco = p.braco and f.symbol = p.symbol and f.bar = p.bar and f.lado = p.lado
 group by 1,2 order by 1,2;
commit;
