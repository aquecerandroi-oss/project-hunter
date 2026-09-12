-- T4.2f -- COBERTURA do progresso e da fita nas linhas que o portao da EXP-M1 le
-- (`meme_features_1m`, versao `meme_features_v2`), ANTES x DEPOIS do deploy.
-- Reaproveita o da T4.2e (§1-§6, inalterados) e acrescenta o que a T4.2f muda:
--
--   §7 a FOTOGRAFIA POR FONTE, por minuto (ultimos 15 min): quantas linhas de
--      `meme_curve_snapshots` vieram da cadeia (`solana_rpc`) e da REST, quantos
--      mints distintos cada uma alcancou, e o atraso mediano `received_at -
--      observed_at` da cadeia (= a finalidade: ~11 s medidos ao vivo);
--   §8 a origem da fotografia que o fold usou (`snapshot_source`) e a fracao
--      com progresso por origem -- a prova de que o progresso agora vem da cadeia;
--   §9 as lacunas do orcamento REST com `chain_covered` (o plano restrito nao
--      gera lacuna pelos mints deixados para a cadeia);
--   §10 a fita depois do limite real: `tape_reason` por valor a cada minuto
--      (`rate_limited` deve cair a zero -- so existe com 429 real; `not_polled`
--      e o que o orcamento de ~16/min nao alcanca) e o ritmo de `meme_trades`
--      por minuto (received_at), que nao pode passar de ~16 pulls/min.
--
-- DIAGNOSTICO (T4.2e em producao, 12/09 10:00 BRT, VPS 8478eef): progress_coverage_pct
-- 43,3 / tape_coverage_pct 38,8; progresso ausente por `not_polled` 1 267 linhas/15 min
-- (o poll REST de 60/min nao alcanca 130 mints); fita ausente por `rate_limited`
-- 1 069/15 min. A T4.2f le a curva de TODOS os rastreados pela cadeia (2 chamadas
-- `getMultipleAccounts`/min) e mede o limite real do swap-api: Cloudflare 1015,
-- ~20 req/60 s por IP, bloqueio de 60 s -- o teto aritmetico da fita com 130 mints
-- e frescor de 180 s e ~40 %, e este arquivo e o que mostra o numero honesto.
--
-- CONVENCOES: horarios em UTC (a VPS grava UTC; Brasilia = UTC - 3, apresentacao
-- e do leitor); `end_time` e o fecho do minuto; nada aqui escreve.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';

\echo '== §0 versao do esquema =='
select version_num as alembic_head from alembic_version;

\echo '== §1 cobertura por minuto fechado, ultimos 15 min (o que o portao le) =='
select f.end_time,
       count(*)                                                        as linhas,
       count(*) filter (where f.progress_reason is null)               as com_progresso,
       count(*) filter (where f.tape_reason is null)                   as com_fita,
       count(*) filter (where f.creator_net_seller is not null)        as com_creator_net_seller,
       round(100.0 * count(*) filter (where f.progress_reason is null) / count(*), 1)
                                                                       as progress_coverage_pct,
       round(100.0 * count(*) filter (where f.tape_reason is null) / count(*), 1)
                                                                       as tape_coverage_pct,
       count(*) filter (where f.coverage > 0)                          as com_fotografia
  from meme_features_1m f
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 1 desc;

\echo '== §1b o mesmo, agregado: ANTES x DEPOIS e uma linha so =='
select count(distinct f.end_time)                                      as minutos,
       count(*)                                                        as linhas,
       round(100.0 * count(*) filter (where f.progress_reason is null) / count(*), 1)
                                                                       as progress_coverage_pct,
       round(100.0 * count(*) filter (where f.tape_reason is null) / count(*), 1)
                                                                       as tape_coverage_pct,
       round(100.0 * count(*) filter (where f.creator_net_seller is not null) / count(*), 1)
                                                                       as creator_net_seller_pct
  from meme_features_1m f
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min';

\echo '== §2a motivos do progresso ausente, ultimos 15 min =='
select coalesce(f.progress_reason, '(tem progresso)') as progress_reason,
       count(*)                                        as linhas,
       count(distinct f.mint)                          as mints
  from meme_features_1m f
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 2 desc;

\echo '== §2b motivos da fita ausente, ultimos 15 min (rate_limited so com 429 real) =='
select coalesce(f.tape_reason, '(tem fita)')            as tape_reason,
       count(*)                                        as linhas,
       count(distinct f.mint)                          as mints
  from meme_features_1m f
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 2 desc;

\echo '== §3a denominador em meme_tokens, por fonte x Mayhem (toda a tabela) =='
select coalesce(t.progress_denominator_source, 'unknown')              as fonte,
       (t.mayhem_state is not null or t.mayhem_enabled is true)         as mayhem,
       count(*)                                                        as mints
  from meme_tokens t
 group by 1, 2 order by 2, 3 desc;

\echo '== §3b o mesmo so nos mints criados nas ultimas 24 h (o conjunto rastreavel) =='
select coalesce(t.progress_denominator_source, 'unknown')              as fonte,
       (t.mayhem_state is not null or t.mayhem_enabled is true)         as mayhem,
       count(*)                                                        as mints
  from meme_tokens t
 where coalesce(t.created_at, t.first_seen_at) >= now() - interval '24 hours'
 group by 1, 2 order by 2, 3 desc;

\echo '== §4 progresso negativo (Mayhem com o agente vendedor liquido), ultimos 15 min =='
select count(*)                                                        as linhas_negativas,
       count(distinct f.mint)                                          as mints,
       round(min(f.curve_progress_pct) * 100, 2)                       as minimo_pct,
       round(percentile_cont(0.5) within group (order by f.curve_progress_pct)::numeric * 100, 2)
                                                                       as mediana_pct
  from meme_features_1m f
  join meme_tokens t on t.mint = f.mint
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
   and f.curve_progress_pct < 0;

\echo '== §5 o laco Mayhem: denominadores mayhem_state escritos e ritmo (30 min) =='
select count(*)                                                        as mints_mayhem_state,
       min(t.updated_at)                                               as primeiro_updated_at,
       max(t.updated_at)                                               as ultimo_updated_at
  from meme_tokens t
 where t.progress_denominator_source = 'mayhem_state';

\echo '== §6 lacunas do orcamento da curva e da fita, ultimos 15 min (meme_ingest_gaps) =='
select g.stream, g.reason, count(*) as gaps,
       sum((g.detail->>'skipped')::int)                                as skipped_total
  from meme_ingest_gaps g
 where g.gap_end >= now() - interval '15 min'
 group by 1, 2 order by 3 desc;

\echo '== §7 fotografias por fonte e por minuto, ultimos 15 min (a cadeia le TODOS?) =='
select date_trunc('minute', s.observed_at)                             as minuto,
       s.source,
       count(*)                                                        as fotografias,
       count(distinct s.mint)                                          as mints,
       count(*) filter (where s.slot is not null)                      as com_slot,
       round(percentile_cont(0.5) within group
             (order by extract(epoch from (s.received_at - s.observed_at)))::numeric, 1)
                                                                       as atraso_mediano_s
  from meme_curve_snapshots s
 where s.observed_at >= date_trunc('minute', now()) - interval '15 min'
 group by 1, 2 order by 1 desc, 2;

\echo '== §7b o mesmo agregado: mints distintos por fonte nos 15 min e chamadas/min da cadeia =='
select s.source,
       count(*)                                                        as fotografias,
       count(distinct s.mint)                                          as mints,
       count(distinct date_trunc('minute', s.observed_at))             as minutos,
       count(distinct s.slot) filter (where s.slot is not null)        as slots_distintos
  from meme_curve_snapshots s
 where s.observed_at >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 2 desc;

\echo '== §8 origem da fotografia que o fold usou, e a fracao com progresso por origem =='
select coalesce(f.snapshot_source, '(sem fotografia)')                 as snapshot_source,
       count(*)                                                        as linhas,
       count(*) filter (where f.progress_reason is null)               as com_progresso,
       round(100.0 * count(*) filter (where f.progress_reason is null) / count(*), 1)
                                                                       as progress_pct
  from meme_features_1m f
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 2 desc;

\echo '== §9 lacunas do poll REST com o plano restrito (chain_covered no detail) =='
select g.reason,
       coalesce(g.detail->>'chain_covered', '(antes da T4.2f)')        as chain_covered,
       count(*)                                                        as gaps,
       sum((g.detail->>'skipped')::int)                                as skipped_total,
       max((g.detail->>'tracked')::int)                                as tracked_max
  from meme_ingest_gaps g
 where g.stream = 'curve_poll'
   and g.gap_end >= now() - interval '15 min'
 group by 1, 2 order by 3 desc;

\echo '== §10 a fita por minuto: motivos e o ritmo de pulls (received_at de meme_trades) =='
select f.end_time,
       count(*) filter (where f.tape_reason is null)                   as com_fita,
       count(*) filter (where f.tape_reason = 'not_polled')            as not_polled,
       count(*) filter (where f.tape_reason = 'rate_limited')          as rate_limited,
       count(*) filter (where f.tape_reason = 'no_trade_feed')         as no_trade_feed
  from meme_features_1m f
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 1 desc;

select date_trunc('minute', t.received_at)                             as minuto,
       count(distinct (t.mint, date_trunc('second', t.received_at)))   as pulls_aprox,
       count(distinct t.mint)                                          as mints,
       count(*)                                                        as trades
  from meme_trades t
 where t.source = 'swap_api'
   and t.received_at >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 1 desc;

commit;
