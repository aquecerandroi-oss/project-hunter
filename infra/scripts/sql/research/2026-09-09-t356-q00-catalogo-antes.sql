-- T3.56 q00 — o catalogo ANTES de qualquer escrita: roster inteiro por purpose/status,
-- o que o `--deprecate` encontraria em cada uma das dez versoes a aposentar (incluindo a
-- linha `paper`), a populacao medida de cada uma (n e expectancia liquida por coorte) e o
-- retrato dos acompanhamentos abertos, para comparar depois.
-- SOMENTE LEITURA (repeatable read / read only). Nada aqui escreve.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at_utc, now() at time zone 'America/Sao_Paulo' as read_at_brt;

\echo ''
\echo '== 1. roster inteiro (purpose x status) =='
select s.key || ' ' || sv.version as versao,
       sv.status, sv.purpose,
       to_char(sv.activated_at, 'YYYY-MM-DD HH24:MI:SS') as ativada_utc,
       to_char(sv.deprecated_at, 'YYYY-MM-DD HH24:MI:SS') as aposentada_utc,
       left(coalesce(sv.changelog, ''), 60) as changelog_inicio
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 order by s.key, (regexp_replace(sv.version, '\D', '', 'g'))::int;

\echo ''
\echo '== 2. contagem por status x purpose =='
select sv.status, sv.purpose, count(*) as versoes
  from strategy_versions sv
 group by 1,2 order by 1,2;

\echo ''
\echo '== 3. as dez alvos: o que --deprecate iria encontrar =='
select s.key || ' ' || sv.version as versao, sv.purpose, sv.status,
       (select count(*) from shadow_episodes e
         where e.strategy_version_id = sv.id and e.open_outcome_signal_id is not null) as slots_abertos,
       (select count(distinct p.id) from positions p
          join orders o on o.proposal_id = (p.metadata->>'proposal_id')::uuid
          join trade_proposals tp on tp.id = o.proposal_id
          join agents ag on ag.id = tp.agent_id
         where ag.strategy_version_id = sv.id
           and p.status <> 'closed' and not p.is_residual) as posicoes_abertas,
       (select count(*) from agent_signals a where a.strategy_version_id = sv.id) as sinais,
       substring(coalesce(sv.changelog,'') from 'derived_from=(v[0-9]+)') as derivada_de,
       substring(coalesce(sv.changelog,'') from 'params_hash=([0-9a-f]{12})') as params_hash_no_changelog
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where (s.key, sv.version) in (
        ('volume_anomaly','v1'), ('volume_anomaly','v2'),
        ('momentum','v1'), ('momentum','v2'), ('momentum','v3'), ('momentum','v4'),
        ('momentum','v6'), ('momentum','v10'),
        ('session_orb','v1'), ('trendline_breakout','v1'))
 order by s.key, (regexp_replace(sv.version, '\D', '', 'g'))::int;

\echo ''
\echo '== 4. a razao medida: n e expectancia liquida por versao x coorte (desfecho terminal, r_multiple nao nulo) =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
              then 'replay' else 'prospective' end as coorte,
         o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
)
select versao, coorte, count(*) as n,
       round(avg(r_net), 4) as exp_liquida_r,
       round(sum(r_net), 2) as soma_r
  from pop
 group by 1,2 order by 1,2;

\echo ''
\echo '== 5. acompanhamentos ABERTOS agora, por versao (o retrato para comparar depois) =='
select s.key || ' ' || sv.version as versao, sv.status, m.symbol,
       o.tracking_state::text as estado, coalesce(o.result::text,'-') as resultado,
       coalesce(a.supporting_features->>'cohort','-') as coorte,
       to_char(o.tracked_until, 'YYYY-MM-DD HH24:MI:SS') as acompanhado_ate,
       to_char(o.updated_at,    'YYYY-MM-DD HH24:MI:SS') as atualizado_em,
       to_char(a.expires_at,    'YYYY-MM-DD HH24:MI:SS') as expira_em
  from shadow_episodes e
  join strategy_versions sv on sv.id = e.strategy_version_id
  join strategies s on s.id = sv.strategy_id
  join markets m on m.id = e.market_id
  left join signal_outcomes o on o.signal_id = e.open_outcome_signal_id
  left join agent_signals a on a.id = e.open_outcome_signal_id
 where e.open_outcome_signal_id is not null
 order by 1, m.symbol;

\echo ''
\echo '== 6. changelog inteiro das alvos derivadas (o prefixo de linhagem que precisa sobreviver) =='
select s.key || ' ' || sv.version as versao, length(coalesce(sv.changelog,'')) as tamanho, sv.changelog
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where (s.key, sv.version) in (
        ('volume_anomaly','v1'), ('volume_anomaly','v2'),
        ('momentum','v1'), ('momentum','v2'), ('momentum','v3'), ('momentum','v4'),
        ('momentum','v6'), ('momentum','v10'),
        ('session_orb','v1'), ('trendline_breakout','v1'))
 order by s.key, (regexp_replace(sv.version, '\D', '', 'g'))::int;
commit;
