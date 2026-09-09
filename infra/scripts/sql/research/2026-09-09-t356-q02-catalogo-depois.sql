-- T3.56 q02 — o catalogo DEPOIS das sete aposentadorias: roster por purpose/status,
-- as linhas escritas (deprecated_at desta janela), a prova de que o prefixo de linhagem
-- sobreviveu (semantica de append da T3.47c), os system_events da janela e o estado dos
-- acompanhamentos abertos das versoes aposentadas (eles precisam continuar andando).
-- SOMENTE LEITURA (repeatable read / read only).
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at_utc, now() at time zone 'America/Sao_Paulo' as read_at_brt;

\echo ''
\echo '== 1. roster inteiro DEPOIS (purpose x status) =='
select s.key || ' ' || sv.version as versao, sv.status, sv.purpose,
       to_char(sv.deprecated_at, 'YYYY-MM-DD HH24:MI:SS') as aposentada_utc,
       to_char(sv.deprecated_at at time zone 'America/Sao_Paulo', 'HH24:MI:SS') as aposentada_brt
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 order by sv.status, s.key, (regexp_replace(sv.version, '\D', '', 'g'))::int;

\echo ''
\echo '== 2. contagem por status x purpose =='
select sv.status, sv.purpose, count(*) as versoes
  from strategy_versions sv group by 1,2 order by 1,2;

\echo ''
\echo '== 3. quem continua viva (o roster que o strategy-worker vai carregar) =='
select s.key || ' ' || sv.version as versao, sv.purpose,
       to_char(sv.activated_at, 'YYYY-MM-DD HH24:MI:SS') as ativada_utc
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where sv.status = 'active'
 order by s.key, (regexp_replace(sv.version, '\D', '', 'g'))::int;

\echo ''
\echo '== 4. T3.47c: o prefixo de linhagem sobreviveu em cada linha escrita agora? =='
select s.key || ' ' || sv.version as versao,
       length(sv.changelog) as tamanho,
       left(sv.changelog, 46) as prefixo_ainda_no_inicio,
       (sv.changelog ~ '\[deprecated 2026-09-09T1[45]:') as tag_t356,
       (substring(sv.changelog from 'derived_from=(v[0-9]+)')) as derived_from_ainda_legivel,
       (substring(sv.changelog from 'params_hash=([0-9a-f]{12})')) as params_hash_ainda_legivel
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where sv.deprecated_at >= timestamptz '2026-09-09 14:50:00+00'
 order by sv.deprecated_at;

\echo ''
\echo '== 5. system_events da janela (o rastro auditado, inclusive as recusas) =='
select level, event, left(message, 92) as mensagem,
       to_char(created_at, 'HH24:MI:SS') as utc
  from system_events
 where created_at >= timestamptz '2026-09-09 14:54:00+00'
   and component = 'activate_strategy_version'
 order by created_at;

\echo ''
\echo '== 6. os acompanhamentos abertos das versoes aposentadas: continuam andando? =='
select s.key || ' ' || sv.version as versao, sv.status, m.symbol,
       o.tracking_state::text as estado, coalesce(o.result::text,'-') as resultado,
       to_char(o.tracked_until, 'YYYY-MM-DD HH24:MI:SS') as acompanhado_ate,
       to_char(o.updated_at,    'YYYY-MM-DD HH24:MI:SS') as atualizado_em,
       to_char(now() - o.updated_at, 'HH24:MI:SS') as ha_quanto_tempo,
       to_char(a.expires_at,    'YYYY-MM-DD HH24:MI:SS') as expira_em
  from shadow_episodes e
  join strategy_versions sv on sv.id = e.strategy_version_id
  join strategies s on s.id = sv.strategy_id
  join markets m on m.id = e.market_id
  left join signal_outcomes o on o.signal_id = e.open_outcome_signal_id
  left join agent_signals a on a.id = e.open_outcome_signal_id
 where e.open_outcome_signal_id is not null
   and sv.status = 'deprecated'
 order by 1, m.symbol;

\echo ''
\echo '== 7. a linha paper (momentum v3): exposicao que o script recusou =='
select s.key || ' ' || sv.version as versao, sv.purpose, sv.status,
       (select count(*) from shadow_episodes e
         where e.strategy_version_id = sv.id and e.open_outcome_signal_id is not null) as slots_abertos,
       (select count(distinct p.id) from positions p
          join orders o on o.proposal_id = (p.metadata->>'proposal_id')::uuid
          join trade_proposals tp on tp.id = o.proposal_id
          join agents ag on ag.id = tp.agent_id
         where ag.strategy_version_id = sv.id
           and p.status <> 'closed' and not p.is_residual) as posicoes_abertas,
       (select to_char(min(a2.expires_at),'YYYY-MM-DD HH24:MI:SS') from shadow_episodes e
          join agent_signals a2 on a2.id = e.open_outcome_signal_id
         where e.strategy_version_id = sv.id and e.open_outcome_signal_id is not null) as primeiro_a_expirar,
       (select to_char(max(a2.expires_at),'YYYY-MM-DD HH24:MI:SS') from shadow_episodes e
          join agent_signals a2 on a2.id = e.open_outcome_signal_id
         where e.strategy_version_id = sv.id and e.open_outcome_signal_id is not null) as ultimo_a_expirar
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where s.key = 'momentum' and sv.version = 'v3';
commit;
