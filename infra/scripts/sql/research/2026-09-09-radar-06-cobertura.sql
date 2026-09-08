-- T3.46 — POR QUE o Radar cobre 26 de 217 mercados: a cobertura e o prefixo
-- alfabetico do universo, nao uma escolha de risco.
--
-- SOMENTE LEITURA. A leitura que fecha o diagnostico do Q1: se os mercados
-- pontuados forem exatamente os primeiros em ordem alfabetica, a cobertura e um
-- bootstrap de baselines que ainda nao terminou de percorrer o universo — e nao
-- um filtro de liquidez, de volume ou de elegibilidade.
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at;

\echo ''
\echo '== 1. os mercados com anomalia, com a posicao alfabetica deles no universo monitorado =='
-- `markets` tem o mesmo simbolo em mais de uma exchange; a posicao e por LINHA
-- (market_id), e a exchange sai na tabela para o par nao parecer duplicata.
with universo as (
  select m.id, m.symbol, e.code as exchange,
         row_number() over (order by m.symbol, e.code) as posicao
    from markets m join exchanges e on e.id = m.exchange_id
   where m.is_monitored
)
select u.posicao, u.symbol, u.exchange,
       (select count(*) from anomalies a where a.market_id = u.id) as anomalias
  from universo u
 where exists (select 1 from anomalies a where a.market_id = u.id)
 order by u.posicao;

\echo ''
\echo '== 2. a cobertura e um prefixo alfabetico? =='
with universo as (
  select m.id, m.symbol, row_number() over (order by m.symbol) as posicao
    from markets m where m.is_monitored
), cob as (
  select u.* from universo u
   where exists (select 1 from anomalies a where a.market_id = u.id)
)
select (select count(*) from universo) as monitorados,
       (select count(*) from cob) as cobertos,
       (select min(posicao) from cob) as primeira_posicao,
       (select max(posicao) from cob) as ultima_posicao,
       (select count(*) from cob where posicao <= 30) as cobertos_no_top30_alfabetico,
       (select count(*) from cob where posicao >= 200) as cobertos_nas_30_ultimas;

\echo ''
\echo '== 3. baselines utilizaveis por mercado (o gate de `opportunity_weights.baseline_gate`) =='
\echo '     v2 exige distinct_days >= 3 e sample_size >= 120'
select count(*) as linhas_baseline,
       count(*) filter (where distinct_days >= 3 and sample_size >= 120) as passam_o_gate,
       round(100.0 * count(*) filter (where distinct_days >= 3 and sample_size >= 120)
             / count(*), 2) as pct,
       count(distinct market_id) as mercados,
       count(distinct market_id) filter (where distinct_days >= 3 and sample_size >= 120)
            as mercados_com_alguma_baseline_valida
  from feature_baselines;

\echo ''
\echo '== 4. os detectores que existem no enum contra os que produziram linha =='
select e.tipo,
       coalesce((select count(*) from anomalies a where a.type::text = e.tipo), 0) as linhas
  from (select unnest(enum_range(null::anomaly_type))::text as tipo) e
 order by 2 desc, 1;

commit;
