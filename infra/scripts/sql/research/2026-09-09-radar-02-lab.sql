-- T3.46 Q2 — o Radar separa os desfechos do Lab? (anomalia recente e score de
-- oportunidade na decisao vs. expectancy/acerto/PF dos mesmos desfechos)
--
-- SOMENTE LEITURA (repeatable read read only). Executavel sozinho. O bloco
-- `pop`/`rad` e repetido de proposito em cada consulta (convencao de
-- `2026-09-08-00-base.sql`): cada bloco tem de ser auditavel sozinho, e uma
-- transacao read only nao pode criar tabela temporaria.
--
-- DECOMPOSICAO DO R (contrato de `hunter_strategy_worker/pricing.py`):
--   r_gross = (exit_base - open_cru)/risk   (sem custo) ; open_cru = p_entry/1.0006
--   r_net   = signal_outcomes.r_multiple    (custo + funding)
--
-- O CORTE (anti-antecipacao). O instante da decisao e
-- `agent_signals.supporting_features->>'decision_at'` — o fechamento da barra que
-- decidiu, nao o relogio de parede. Toda leitura do Radar e estritamente ANTERIOR
-- ou IGUAL a ele: `anomalies.detected_at <= decision_at` e
-- `opportunity_history.ts <= decision_at`. Nada aqui olha o futuro do sinal.
--
-- "N BARRAS" — SUPOSICAO DECLARADA. O brief pede 4/16/96 barras. As versoes vivas
-- decidem em 5 min e 15 min, entao "barra" nao e unica. Fixei **barra = 15 min**
-- para as tres janelas (60 min, 240 min, 1440 min) e uso a MESMA janela para todas
-- as versoes: uma janela em minutos e comparavel entre estrategias, uma janela em
-- barras nao e.
--
-- COBERTURA — a razao de este arquivo ter duas metades. O `scanner-worker` so
-- pontuou 26 dos 217 mercados monitorados (Q1). Fora deles, "sem anomalia" quer
-- dizer "ninguem estava olhando", nao "nao houve anomalia" — e um contraste que
-- misture os dois mede cobertura, nao previsao. Por isso `coberto` e definido por
-- prova positiva: existe amostra de `opportunity_history` daquele mercado nos 15
-- minutos anteriores a decisao (`score_dec is not null`). As tabelas 3 a 7 rodam
-- so sobre `coberto`; a tabela 8 mostra o que a contaminacao faria.
--
-- SEVERIDADE — o que esta consulta NAO usa. `anomalies.severity` e mutavel (o §3
-- atualiza a linha enquanto o episodio dura), entao a severidade lida hoje e a do
-- fim do episodio, que e informacao POSTERIOR a decisao. Usar isso como filtro
-- seria antecipacao. So entram aqui campos imutaveis: `detected_at` e `type`.
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura e janela do Radar =='
select now() as read_at,
       (select min(detected_at) from anomalies) as radar_de,
       (select max(detected_at) from anomalies) as radar_ate,
       (select min(ts) from opportunity_history) as score_de,
       (select max(ts) from opportunity_history) as score_ate;

\echo ''
\echo '== 1. populacao: quanto do Lab cai na janela do Radar, e quanto e coberto =='
with pop as (
  select o.signal_id, a.market_id, m.symbol,
         s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         (a.supporting_features->>'decision_at')::timestamptz as decision_at,
         o.result::text as resultado, o.r_multiple as r_net,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and (a.supporting_features->>'decision_at')::timestamptz
         >= (select min(detected_at) from anomalies)
), rad as (
  select p.*,
         case when p.risk > 0 then (p.exit_base - p.p_entry / 1.0006) / p.risk end as r_gross,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '60 minutes')   as anom_4b,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '240 minutes')  as anom_16b,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '1440 minutes') as anom_96b,
         (select string_agg(distinct an.type::text, ',') from anomalies an
           where an.market_id = p.market_id and an.detected_at <= p.decision_at
             and an.detected_at > p.decision_at - interval '240 minutes')        as tipos_16b,
         (select oh.score from opportunity_history oh
            join opportunities op on op.id = oh.opportunity_id
           where op.market_id = p.market_id and oh.ts <= p.decision_at
             and oh.ts > p.decision_at - interval '15 minutes'
           order by oh.ts desc limit 1)                                          as score_dec
    from pop p
)
select coorte, count(*) as desfechos,
       count(*) filter (where score_dec is not null) as cobertos,
       round(100.0 * count(*) filter (where score_dec is not null) / count(*), 1) as pct_coberto,
       count(distinct market_id) as mercados,
       count(distinct market_id) filter (where score_dec is not null) as mercados_cobertos,
       min(decision_at) as de, max(decision_at) as ate
  from rad group by 1 order by 1;

\echo ''
\echo '== 2. o mesmo corte por versao =='
with pop as (
  select o.signal_id, a.market_id, m.symbol,
         s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         (a.supporting_features->>'decision_at')::timestamptz as decision_at,
         o.result::text as resultado, o.r_multiple as r_net,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and (a.supporting_features->>'decision_at')::timestamptz
         >= (select min(detected_at) from anomalies)
), rad as (
  select p.*,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '240 minutes')  as anom_16b,
         (select oh.score from opportunity_history oh
            join opportunities op on op.id = oh.opportunity_id
           where op.market_id = p.market_id and oh.ts <= p.decision_at
             and oh.ts > p.decision_at - interval '15 minutes'
           order by oh.ts desc limit 1)                                          as score_dec
    from pop p
)
select versao, coorte, count(*) n,
       count(*) filter (where score_dec is not null) cobertos,
       count(*) filter (where anom_16b) com_anom_16b
  from rad group by 1, 2 order by 3 desc;

\echo ''
\echo '== 3. COM anomalia x SEM anomalia, so onde o Radar estava olhando (pooled) =='
with pop as (
  select o.signal_id, a.market_id, m.symbol,
         s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         (a.supporting_features->>'decision_at')::timestamptz as decision_at,
         o.result::text as resultado, o.r_multiple as r_net,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and (a.supporting_features->>'decision_at')::timestamptz
         >= (select min(detected_at) from anomalies)
), rad as (
  select p.*,
         case when p.risk > 0 then (p.exit_base - p.p_entry / 1.0006) / p.risk end as r_gross,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '60 minutes')   as anom_4b,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '240 minutes')  as anom_16b,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '1440 minutes') as anom_96b,
         (select oh.score from opportunity_history oh
            join opportunities op on op.id = oh.opportunity_id
           where op.market_id = p.market_id and oh.ts <= p.decision_at
             and oh.ts > p.decision_at - interval '15 minutes'
           order by oh.ts desc limit 1)                                          as score_dec
    from pop p
)
select janela, tem_anomalia, n, dias, exp_bruto, exp_liquido, acerto_pct, pf, soma_r from (
  select '4b (60min)' as janela, anom_4b as tem_anomalia, 1 as ord,
         count(*) n, count(distinct decision_at::date) dias,
         round(avg(r_gross), 4) exp_bruto, round(avg(r_net), 4) exp_liquido,
         round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1) acerto_pct,
         round(coalesce(sum(r_net) filter (where r_net > 0), 0)
               / nullif(abs(sum(r_net) filter (where r_net < 0)), 0), 3) pf,
         round(sum(r_net), 2) soma_r
    from rad where score_dec is not null group by 2
  union all
  select '16b (240min)', anom_16b, 2, count(*), count(distinct decision_at::date),
         round(avg(r_gross), 4), round(avg(r_net), 4),
         round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1),
         round(coalesce(sum(r_net) filter (where r_net > 0), 0)
               / nullif(abs(sum(r_net) filter (where r_net < 0)), 0), 3),
         round(sum(r_net), 2)
    from rad where score_dec is not null group by 2
  union all
  select '96b (1440min)', anom_96b, 3, count(*), count(distinct decision_at::date),
         round(avg(r_gross), 4), round(avg(r_net), 4),
         round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1),
         round(coalesce(sum(r_net) filter (where r_net > 0), 0)
               / nullif(abs(sum(r_net) filter (where r_net < 0)), 0), 3),
         round(sum(r_net), 2)
    from rad where score_dec is not null group by 2
) x order by ord, tem_anomalia;

\echo ''
\echo '== 4. o mesmo por versao (janela 16b), so coberto =='
with pop as (
  select o.signal_id, a.market_id, m.symbol,
         s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         (a.supporting_features->>'decision_at')::timestamptz as decision_at,
         o.result::text as resultado, o.r_multiple as r_net,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and (a.supporting_features->>'decision_at')::timestamptz
         >= (select min(detected_at) from anomalies)
), rad as (
  select p.*,
         case when p.risk > 0 then (p.exit_base - p.p_entry / 1.0006) / p.risk end as r_gross,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '240 minutes')  as anom_16b,
         (select oh.score from opportunity_history oh
            join opportunities op on op.id = oh.opportunity_id
           where op.market_id = p.market_id and oh.ts <= p.decision_at
             and oh.ts > p.decision_at - interval '15 minutes'
           order by oh.ts desc limit 1)                                          as score_dec
    from pop p
)
select versao, anom_16b as tem, count(*) n,
       round(avg(r_gross), 4) exp_bruto, round(avg(r_net), 4) exp_liquido,
       round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1) acerto_pct,
       round(coalesce(sum(r_net) filter (where r_net > 0), 0)
             / nullif(abs(sum(r_net) filter (where r_net < 0)), 0), 3) pf
  from rad where score_dec is not null group by 1, 2 order by 1, 2;

\echo ''
\echo '== 5. por TIPO de anomalia nos 240 min (coberto; um desfecho pode ter varios) =='
with pop as (
  select o.signal_id, a.market_id, m.symbol,
         s.key || ' ' || sv.version as versao,
         (a.supporting_features->>'decision_at')::timestamptz as decision_at,
         o.result::text as resultado, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and (a.supporting_features->>'decision_at')::timestamptz
         >= (select min(detected_at) from anomalies)
), rad as (
  select p.*,
         (select string_agg(distinct an.type::text, ',') from anomalies an
           where an.market_id = p.market_id and an.detected_at <= p.decision_at
             and an.detected_at > p.decision_at - interval '240 minutes')        as tipos_16b,
         (select oh.score from opportunity_history oh
            join opportunities op on op.id = oh.opportunity_id
           where op.market_id = p.market_id and oh.ts <= p.decision_at
             and oh.ts > p.decision_at - interval '15 minutes'
           order by oh.ts desc limit 1)                                          as score_dec
    from pop p
)
select tipo, count(*) n, round(avg(r_net), 4) exp_liquido,
       round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1) acerto_pct,
       round(sum(r_net), 2) soma_r
  from (select unnest(string_to_array(coalesce(tipos_16b, 'SEM_ANOMALIA'), ',')) as tipo,
               r_net, resultado from rad where score_dec is not null) t
 group by 1 order by 2 desc;

\echo ''
\echo '== 6. decis do score na decisao — monotonico? (so coberto) =='
\echo '== 6b. Spearman entre score e r_net; 7. top 25% do score contra o resto =='
with pop as (
  select o.signal_id, a.market_id, m.symbol,
         s.key || ' ' || sv.version as versao,
         (a.supporting_features->>'decision_at')::timestamptz as decision_at,
         o.result::text as resultado, o.r_multiple as r_net,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and (a.supporting_features->>'decision_at')::timestamptz
         >= (select min(detected_at) from anomalies)
), rad as (
  select p.*,
         case when p.risk > 0 then (p.exit_base - p.p_entry / 1.0006) / p.risk end as r_gross,
         (select oh.score from opportunity_history oh
            join opportunities op on op.id = oh.opportunity_id
           where op.market_id = p.market_id and oh.ts <= p.decision_at
             and oh.ts > p.decision_at - interval '15 minutes'
           order by oh.ts desc limit 1)                                          as score_dec
    from pop p
), d as (
  select *, ntile(10) over (order by score_dec) as decil,
            ntile(4)  over (order by score_dec) as quartil
    from rad where score_dec is not null
), rk as (
  select rank() over (order by score_dec) rs, rank() over (order by r_net) rr from d
)
select 'decil ' || decil::text as faixa, count(*) n,
       round(min(score_dec), 2) score_min, round(max(score_dec), 2) score_max,
       round(avg(r_gross), 4) exp_bruto, round(avg(r_net), 4) exp_liquido,
       round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1) acerto_pct,
       round(sum(r_net), 2) soma_r,
       null::numeric as spearman
  from d group by decil
union all
select case when quartil = 4 then 'Q4 top 25%' else 'Q1-Q3 (75%)' end, count(*),
       round(min(score_dec), 2), round(max(score_dec), 2),
       round(avg(r_gross), 4), round(avg(r_net), 4),
       round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1),
       round(sum(r_net), 2), null::numeric
  from d group by 1
union all
select 'SPEARMAN score x r_net', count(*), null, null, null, null, null, null,
       round(corr(rs, rr)::numeric, 4)
  from rk
order by 1;

\echo ''
\echo '== 8. CONTAMINACAO DE COBERTURA: o mesmo contraste sem exigir cobertura (NAO usar) =='
with pop as (
  select o.signal_id, a.market_id,
         (a.supporting_features->>'decision_at')::timestamptz as decision_at,
         o.result::text as resultado, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and (a.supporting_features->>'decision_at')::timestamptz
         >= (select min(detected_at) from anomalies)
), rad as (
  select p.*,
         exists (select 1 from anomalies an where an.market_id = p.market_id
                  and an.detected_at <= p.decision_at
                  and an.detected_at >  p.decision_at - interval '240 minutes') as anom_16b
    from pop p
)
select anom_16b as tem_anomalia, count(*) n, round(avg(r_net), 4) exp_liquido,
       round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1) acerto_pct
  from rad group by 1 order by 1;

commit;
