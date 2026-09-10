-- T3.76 q03 -- A COORTE DE 90 DIAS DA `mean_reversion v10` CORTADA PELO ROTULO
-- QUE O PORTAO USARIA. Somente leitura, zero CPU de replay.
--
-- POR QUE ISTO VEM ANTES DO REPLAY. A EXP-0026 pre-registra tres bracos com
-- portao de regime sobre a `v10` e exige `n >= 100`. Antes de gastar horas de
-- CPU da VPS derivando e replayando, esta consulta mede o **denominador**: das
-- 798 decisoes que a `v10` ja tomou nos mesmos 90 dias e nos mesmos 16 mercados
-- (coorte `replay:c7d138eb-...`, T3.62b), quantas caem em cada rotulo horario
-- do BTC. Esse numero e a expectativa declarada de `n` de cada braco -- e, se
-- ele ja for pequeno, o braco nasce sem poder estatistico e isso tem de estar
-- escrito ANTES do resultado.
--
-- O QUE ELA NAO E. **Nao** substitui o replay dos bracos. `PIPELINE.md` §4b
-- item 11: a filha com portao nao e subconjunto do pai nas DECISOES (o slot
-- dela evolui diferente porque `INELIGIBLE` nao arma a barreira), so nas
-- BARRAS. Este corte e do pai, por rotulo -- e a melhor estimativa de `n`
-- disponivel sem rodar nada, e nada mais que isso.
--
-- A JUNCAO E A REGRA DO PORTAO, NAO A DA HORA QUE CONTEM. `regime_gate` usa a
-- ultima hora FECHADA antes do corte (`end_time <= source_bar_close`,
-- `PIPELINE.md` §4b item 10): uma decisao das 09:45 e cortada pela linha
-- [08:00, 09:00), nunca pela [09:00, 10:00). Reproduzido aqui com um LATERAL
-- para nao depender de aritmetica de truncamento no limite exato da hora.
--
-- EIXO. `r_ex_funding` (`meta ->> 'r_ex_funding'`), nao `r_multiple`: 498 dos
-- 798 desfechos desta coorte sao nulos por `funding_schedule_unknown`
-- (`PIPELINE.md` §4b item 13). O eixo e declarado em toda linha.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

\echo ''
\echo '== 0. a coorte, e quanto dela tem cada eixo =='
with pop as (
  select a.id, a.market_id,
         (a.supporting_features ->> 'observation_ts')::timestamptz as source_bar_close,
         o.result, o.tracking_state,
         o.r_multiple as r_net,
         (o.meta ->> 'r_ex_funding')::numeric as r_ex_funding
    from agent_signals a
    left join signal_outcomes o on o.signal_id = a.id
   where a.supporting_features ->> 'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
)
select count(*) as decisoes,
       count(*) filter (where tracking_state = 'terminal') as terminais,
       count(r_net) as com_r_net,
       count(r_ex_funding) as com_r_ex_funding,
       min(source_bar_close) as primeira_barra,
       max(source_bar_close) as ultima_barra
  from pop;

\echo ''
\echo '== 1. decisoes e desempenho por ROTULO do portao (eixo r_ex_funding) =='
with pop as (
  select a.id, a.market_id,
         (a.supporting_features ->> 'observation_ts')::timestamptz as source_bar_close,
         o.result, o.tracking_state,
         (o.meta ->> 'r_ex_funding')::numeric as r
    from agent_signals a
    left join signal_outcomes o on o.signal_id = a.id
   where a.supporting_features ->> 'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
), j as (
  select pop.*, coalesce(g.regime::text, 'sem_linha') as rotulo
    from pop
    left join lateral (
      select r.regime
        from market_regimes r
       where r.scope = 'btc' and r.classifier_version = 'regime_hourly_v1'
         and r.end_time <= pop.source_bar_close
       order by r.start_time desc
       limit 1
    ) g on true
)
select rotulo,
       count(*)                                                        as decisoes,
       count(r)                                                        as avaliaveis,
       count(distinct date_trunc('day', source_bar_close))              as dias,
       round(avg(r), 4)                                                as media_r,
       round(sum(r), 2)                                                as soma_r,
       round(100.0 * count(*) filter (where result = 'target')
             / nullif(count(*) filter (where result in ('target','stop')), 0), 1) as pct_alvo,
       round(sum(r) filter (where r > 0)
             / nullif(abs(sum(r) filter (where r < 0)), 0), 3)          as pf
  from j
 group by 1 order by 2 desc;

\echo ''
\echo '== 2. o mesmo, agregado nos conjuntos de cada braco da EXP-0026 =='
with pop as (
  select a.id,
         (a.supporting_features ->> 'observation_ts')::timestamptz as source_bar_close,
         (o.meta ->> 'r_ex_funding')::numeric as r
    from agent_signals a
    left join signal_outcomes o on o.signal_id = a.id
   where a.supporting_features ->> 'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
), j as (
  select pop.*, coalesce(g.regime::text, 'sem_linha') as rotulo
    from pop
    left join lateral (
      select r.regime from market_regimes r
       where r.scope = 'btc' and r.classifier_version = 'regime_hourly_v1'
         and r.end_time <= pop.source_bar_close
       order by r.start_time desc limit 1
    ) g on true
), bracos as (
  select 'v15 SIDEWAYS+LOW_VOLATILITY' as braco,
         array['SIDEWAYS','LOW_VOLATILITY'] as allow
  union all select 'v16 SIDEWAYS', array['SIDEWAYS']
  union all select 'v17 HIGH_VOLATILITY (falseamento)', array['HIGH_VOLATILITY']
  union all select 'pai v10 (todas as barras)',
                   array['SIDEWAYS','LOW_VOLATILITY','HIGH_VOLATILITY','BTC_BULL','BTC_BEAR','UNKNOWN','sem_linha']
)
select b.braco,
       count(*)                          as decisoes_do_pai_no_conjunto,
       count(j.r)                        as avaliaveis,
       count(distinct date_trunc('day', j.source_bar_close)) as dias,
       round(avg(j.r), 4)                as media_r,
       round(sum(j.r), 2)                as soma_r
  from bracos b join j on j.rotulo = any (b.allow)
 group by 1 order by 2 desc;

\echo ''
\echo '== 3. por rotulo x janela de 30 dias (a regra "positivo em 2 das 3") =='
with pop as (
  select a.id,
         (a.supporting_features ->> 'observation_ts')::timestamptz as source_bar_close,
         (o.meta ->> 'r_ex_funding')::numeric as r
    from agent_signals a
    left join signal_outcomes o on o.signal_id = a.id
   where a.supporting_features ->> 'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
), j as (
  select pop.*,
         coalesce(g.regime::text, 'sem_linha') as rotulo,
         case when pop.source_bar_close < '2026-07-12 00:00+00' then 'J1'
              when pop.source_bar_close < '2026-08-11 00:00+00' then 'J2'
              else 'J3' end as janela
    from pop
    left join lateral (
      select r.regime from market_regimes r
       where r.scope = 'btc' and r.classifier_version = 'regime_hourly_v1'
         and r.end_time <= pop.source_bar_close
       order by r.start_time desc limit 1
    ) g on true
)
select rotulo, janela, count(*) as decisoes, count(r) as avaliaveis,
       round(avg(r), 4) as media_r, round(sum(r), 2) as soma_r
  from j group by 1, 2 order by 1, 2;

commit;
