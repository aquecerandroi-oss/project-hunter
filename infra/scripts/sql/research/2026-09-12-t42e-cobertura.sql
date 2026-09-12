-- T4.2e -- COBERTURA do progresso e da fita nas linhas que o portao da EXP-M1 le
-- (`meme_features_1m`, versao `meme_features_v2`), ANTES x DEPOIS do deploy.
--
-- DIAGNOSTICO. Em 12/09/2026 08:35 BRT (VPS eeb566c, hb:meme:radar) o laco
-- avaliava 250 linhas por tick e recusava `progress_unknown` em 113 e
-- `creator_net_seller_unknown`/`curve_volume_1m_unknown` em 109. Os dois motivos
-- sao colunas desta tabela: `progress_reason IS NOT NULL` e
-- `tape_reason IS NOT NULL` (a fita e uma so para as quatro colunas do minuto,
-- `ck_meme_features_1m_tape_is_null_with_a_reason`). O orquestrador roda este
-- arquivo uma vez ANTES do deploy da T4.2e e outra DEPOIS (>= 5 min depois do
-- restart, para o laco da fita ter dado uma volta completa), e compara.
--
-- O que cada secao fecha:
--   §1 por minuto fechado (ultimos 15 min): linhas, com progresso, com fita,
--      com `creator_net_seller`, e as fracoes -- o mesmo numero que o heartbeat
--      publica como `progress_coverage_pct`/`tape_coverage_pct`;
--   §2 os MOTIVOS: `progress_reason` e `tape_reason` por valor, nos ultimos 15 min
--      (`not_polled` na fita = o orcamento nao alcancou o mint no ciclo);
--   §3 o denominador em `meme_tokens`: contagem por `progress_denominator_source`
--      (NULL = unknown), separando Mayhem (`mayhem_state IS NOT NULL` ou
--      `mayhem_enabled`) de padrao -- e a mesma contagem so nos mints criados nas
--      ultimas 24 h (os rastreados);
--   §4 progresso NEGATIVO: linhas Mayhem cujo `curve_progress_pct < 0` (a curva
--      segura mais tokens que o inicial porque o agente vendeu liquido -- o site
--      mostra 0, nos guardamos o numero) -- para saber quantas o portao recusa
--      por `progress_below_min` em vez de `progress_unknown`;
--   §5 o instante do primeiro `mayhem_state` escrito (prova de que o laco rodou)
--      e o ritmo (denominadores Mayhem por minuto, ultimos 30 min).
--
-- CONVENCOES: horarios em UTC (a VPS grava UTC; Brasilia = UTC - 3, apresentacao
-- e do leitor); `end_time` e o fecho do minuto; nada aqui escreve.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';

\echo '== §0 versao do esquema e do worker (alembic + heartbeat nao entra aqui) =='
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

\echo '== §2b motivos da fita ausente, ultimos 15 min (not_polled = orcamento nao alcancou) =='
select coalesce(f.tape_reason, '(tem fita)')            as tape_reason,
       count(*)                                        as linhas,
       count(distinct f.mint)                          as mints
  from meme_features_1m f
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 2 desc;

\echo '== §2c fita presente mas creator desconhecido (creator_net_seller NULL com fita) =='
select count(*)                                                        as linhas_com_fita_sem_creator,
       count(distinct f.mint)                                          as mints
  from meme_features_1m f
  join meme_tokens t on t.mint = f.mint
 where f.features_version = 'meme_features_v2'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
   and f.tape_reason is null and f.creator_net_seller is null and t.creator is null;

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

\echo '== §5 o laco Mayhem rodou? primeiro/ultimo denominador mayhem_state e ritmo (30 min) =='
select count(*)                                                        as mints_mayhem_state,
       min(t.updated_at)                                               as primeiro_updated_at,
       max(t.updated_at)                                               as ultimo_updated_at
  from meme_tokens t
 where t.progress_denominator_source = 'mayhem_state';

select date_trunc('minute', t.updated_at)                              as minuto,
       count(*)                                                        as denominadores_mayhem
  from meme_tokens t
 where t.progress_denominator_source = 'mayhem_state'
   and t.updated_at >= now() - interval '30 min'
 group by 1 order by 1 desc;

\echo '== §6 lacunas do orcamento da curva e da fita, ultimos 15 min (meme_ingest_gaps) =='
select g.stream, g.reason, count(*) as gaps,
       sum((g.detail->>'skipped')::int)                                as skipped_total
  from meme_ingest_gaps g
 where g.gap_end >= now() - interval '15 min'
 group by 1, 2 order by 3 desc;

commit;
