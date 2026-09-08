-- T3.48 (complemento) — três perguntas que a primeira consulta deixou abertas:
--   (a) por que a carteira paper apareceu SEM perfil de risco na consulta 2;
--   (b) quem, de fato, pode gerar entrada nessa carteira hoje (`agents`);
--   (c) quantas posições simultâneas o Lab pediria — o teto de 5 posições e o de
--       1 % de risco agregado (= 4 entradas a 0,25 %, 2 a 0,50 %) mordem ou não?
--
-- SOMENTE LEITURA (repeatable read read only). Executável sozinho.
-- Concorrência: contagem por varredura de eventos (+1 em `entry_ts`, −1 em
-- `exit_ts`) sobre os desfechos fechados — é o número de posições que a versão
-- teria mantido ABERTAS ao mesmo tempo se toda decisão virasse entrada.
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at, now() at time zone 'America/Sao_Paulo' as read_at_brasilia;

\echo ''
\echo '== A. perfis de risco existentes e a ligação da carteira =='
select rp.id, rp.preset::text, rp.organization_id,
       rp.limits->>'risk_per_trade_pct' as risk_per_trade_pct,
       rp.limits->>'max_aggregate_planned_risk_pct' as max_agg,
       rp.limits->>'max_concurrent_positions' as max_pos,
       rp.limits->>'max_stop_distance_pct' as max_stop_dist,
       rp.limits->>'min_stop_distance_pct' as min_stop_dist,
       rp.limits->>'warning_size_multiplier' as ks_mult
  from risk_profiles rp order by rp.preset::text;

\echo ''
select p.id, p.name, p.type::text, p.risk_profile_id, p.organization_id, p.is_arena
  from portfolios p where p.deleted_at is null;

\echo ''
\echo '== B. agentes: quem pode gerar entrada nessa carteira hoje =='
select a.id, a.name, a.status::text, a.portfolio_id,
       s.key || ' ' || sv.version as versao, sv.purpose::text,
       a.capital_allocation_pct, a.max_open_positions
  from agents a
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 order by a.name;

\echo ''
\echo '== C. concorrência que o Lab pediria: máximo de posições simultâneas por versão =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         o.entry_ts, o.exit_ts
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and o.entry_ts is not null and o.exit_ts is not null and o.exit_ts >= o.entry_ts
), ev as (
  select versao, coorte, entry_ts as t, 1 as delta from pop
  union all
  select versao, coorte, exit_ts  as t, -1      from pop
), acc as (
  select versao, coorte, t,
         sum(delta) over (partition by versao, coorte order by t, delta desc
                          rows between unbounded preceding and current row) as abertas
    from ev
)
select versao, coorte, max(abertas) max_simultaneas,
       round(avg(abertas), 2) media_simultaneas,
       round(100.0 * count(*) filter (where abertas > 5) / count(*), 1) pct_do_tempo_acima_de_5,
       round(100.0 * count(*) filter (where abertas > 4) / count(*), 1) pct_do_tempo_acima_de_4,
       round(100.0 * count(*) filter (where abertas > 2) / count(*), 1) pct_do_tempo_acima_de_2
  from acc group by 1, 2 having count(*) >= 20 order by 3 desc;

\echo ''
\echo '== D. ritmo de decisão das versões vivas nas últimas 24 h (prospectivo) =='
select s.key || ' ' || sv.version as versao, sv.purpose::text, sv.status::text,
       count(*) as sinais_24h,
       count(distinct a.market_id) as mercados,
       min(a.emitted_at) as de, max(a.emitted_at) as ate
  from agent_signals a
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where a.emitted_at > now() - interval '24 hours'
 group by 1, 2, 3 order by 4 desc;

commit;
