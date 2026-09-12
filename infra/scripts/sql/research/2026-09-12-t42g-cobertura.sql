-- T4.2g -- COBERTURA da fita nas linhas que a porta le (`meme_features_1m`, versao
-- `meme_features_v3`, e a serie de 15 s `meme_features_15s_v1`), ANTES x DEPOIS do deploy
-- da fita por lote (`POST /v1/coins/market-activity/batch`, migracao `0032_meme_activity`).
--
-- DIAGNOSTICO (T4.2f, medido): a fita por mint (`/v2/coins/{mint}/trades`) e limitada
-- pelo Cloudflare a ~20 req/60 s por IP -- 16 pulls/min x 180 s de frescor / ~130
-- rastreados = ~40 % de `tape_coverage_pct` no maximo; a porta `flow_v2/1` recusava
-- ~100 de ~110 moedas jovens por tick como `buyers_unknown`/`sells_ratio_unknown`/
-- `flow_not_polled`. O lote conta 50 moedas por requisicao (teto do validador, medido
-- em 12/09 20:24 UTC): 3 requisicoes/min cobrem o conjunto inteiro dentro do mesmo
-- orcamento, e cada linha passa a dizer de onde veio a fita (`tape_source`).
--
-- O que cada secao fecha:
--   §1 por minuto fechado (ultimos 15 min): linhas, com fita, com fita POR FONTE
--      (`swap_api_trades` x `activity_1m`), com `creator_net_seller` -- o mesmo numero
--      que o heartbeat publica como `tape_coverage_pct` e `tape_activity_pct`;
--   §1b o mesmo, agregado: ANTES x DEPOIS numa linha so (meta: tape_coverage_pct >= 90);
--   §2 os MOTIVOS da fita ausente por valor (`not_polled` deve cair; `no_sol_quote`
--      e o lote sem cotacao SOL/USD com < 5 min -- deve ser raro);
--   §3 a serie de 15 s: cobertura da fita por fonte nos ultimos 15 min -- e a que a
--      porta `flow_v2/1` le; `tape_as_of` mostra quantos segundos antes do instante a
--      janela do lote terminou (mediana e p95);
--   §4 a tabela do lote: linhas por minuto e por janela (`1m`/`5m`), quantas nao-nulas
--      e quantas zeros declarados (`empty`), o carimbo (`end_time` = Date da resposta)
--      contra `received_at`, e se a janela `1m` veio VIVA (nao-nula em alguma moeda):
--      a prova em producao do que a sonda de 12/09 nao alcancou;
--   §5 a cotacao: idade de `sol_usd_observed_at` em relacao a `end_time`;
--   §6 o orcamento do swap-api: requisicoes/min ao host = `meme_trades` (pulls por
--      minuto, aproximado pelos mints distintos com trades recebidos) + chamadas do lote
--      (ceil(moedas/50) por minuto) -- nunca acima de ~16;
--   §7 as recusas do portao no `meme_lab_ticks` (T4.15): `buyers_unknown`,
--      `sells_ratio_unknown`, `flow_*` por tick, ultimos 30 min -- ANTES x DEPOIS.
--
-- CONVENCOES: horarios em UTC (a VPS grava UTC; Brasilia = UTC - 3, apresentacao
-- e do leitor); `end_time` e o fecho do minuto; nada aqui escreve.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';

\echo '== §0 versao do esquema =='
select version_num as alembic_head from alembic_version;

\echo '== §1 cobertura da fita por minuto fechado e por fonte, ultimos 15 min =='
select f.end_time,
       count(*)                                                        as linhas,
       count(*) filter (where f.tape_reason is null)                   as com_fita,
       count(*) filter (where f.tape_source = 'swap_api_trades')       as fita_por_mint,
       count(*) filter (where f.tape_source = 'activity_1m')           as fita_por_lote,
       count(*) filter (where f.creator_net_seller is not null)        as com_creator_net_seller,
       round(100.0 * count(*) filter (where f.tape_reason is null) / count(*), 1)
                                                                       as tape_coverage_pct,
       round(100.0 * count(*) filter (where f.tape_source = 'activity_1m') / count(*), 1)
                                                                       as tape_activity_pct
  from meme_features_1m f
 where f.features_version = 'meme_features_v3'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
 group by 1 order by 1 desc;

\echo '== §1b o mesmo, agregado: ANTES x DEPOIS numa linha so (meta >= 90) =='
select count(distinct f.end_time)                                      as minutos,
       count(*)                                                        as linhas,
       round(100.0 * count(*) filter (where f.tape_reason is null) / count(*), 1)
                                                                       as tape_coverage_pct,
       round(100.0 * count(*) filter (where f.tape_source = 'swap_api_trades') / count(*), 1)
                                                                       as tape_trades_pct,
       round(100.0 * count(*) filter (where f.tape_source = 'activity_1m') / count(*), 1)
                                                                       as tape_activity_pct,
       round(100.0 * count(*) filter (where f.creator_net_seller is not null) / count(*), 1)
                                                                       as creator_net_seller_pct
  from meme_features_1m f
 where f.features_version = 'meme_features_v3'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min';

\echo '== §2 motivos da fita ausente, ultimos 15 min =='
select f.tape_reason, count(*) as linhas
  from meme_features_1m f
 where f.features_version = 'meme_features_v3'
   and f.end_time >= date_trunc('minute', now()) - interval '15 min'
   and f.tape_reason is not null
 group by 1 order by 2 desc;

\echo '== §3 serie de 15 s: fita por fonte e atraso da janela do lote, ultimos 15 min =='
select count(*)                                                        as linhas,
       round(100.0 * count(*) filter (where f.tape_reason is null) / count(*), 1)
                                                                       as tape_coverage_pct,
       count(*) filter (where f.tape_source = 'swap_api_trades')       as fita_por_mint,
       count(*) filter (where f.tape_source = 'activity_1m')           as fita_por_lote,
       percentile_cont(0.5) within group (order by extract(epoch from f.as_of - f.tape_as_of))
         filter (where f.tape_source = 'activity_1m')                  as lote_atraso_s_p50,
       percentile_cont(0.95) within group (order by extract(epoch from f.as_of - f.tape_as_of))
         filter (where f.tape_source = 'activity_1m')                  as lote_atraso_s_p95
  from meme_features_15s f
 where f.features_version = 'meme_features_15s_v1'
   and f.as_of >= now() - interval '15 min';

\echo '== §3b serie de 15 s: motivos da fita ausente =='
select f.tape_reason, count(*) as linhas
  from meme_features_15s f
 where f.features_version = 'meme_features_15s_v1'
   and f.as_of >= now() - interval '15 min'
   and f.tape_reason is not null
 group by 1 order by 2 desc;

\echo '== §4 a tabela do lote por minuto e janela: a janela 1m veio VIVA? =='
select date_trunc('minute', a.end_time)                                as minuto,
       a.window_name,
       count(*)                                                        as linhas,
       count(*) filter (where not a.empty)                             as nao_nulas,
       count(*) filter (where a.empty)                                 as zeros_declarados,
       count(distinct a.mint)                                          as mints,
       round(avg(extract(epoch from a.received_at - a.end_time))::numeric, 2)
                                                                       as recebido_apos_carimbo_s,
       round(avg(extract(epoch from date_trunc('minute', a.end_time) + interval '1 min'
                                   - a.end_time))::numeric, 1)         as fim_antes_do_minuto_s
  from meme_market_activity_1m a
 where a.end_time >= now() - interval '15 min'
 group by 1, 2 order by 1 desc, 2;

\echo '== §5 a cotacao SOL/USD usada pelo lote: idade e ausencia =='
select count(*)                                                        as linhas,
       count(*) filter (where a.sol_usd is null)                       as sem_cotacao,
       round(avg(extract(epoch from a.end_time - a.sol_usd_observed_at))::numeric, 1)
                                                                       as idade_media_s,
       max(extract(epoch from a.end_time - a.sol_usd_observed_at))     as idade_max_s
  from meme_market_activity_1m a
 where a.end_time >= now() - interval '15 min' and a.window_name = '1m';

\echo '== §6 orcamento do swap-api por minuto: pulls da fita + chamadas do lote (<= ~16) =='
with pulls as (
  select date_trunc('minute', t.received_at) as minuto, count(distinct t.mint) as mints_com_fita
    from meme_trades t
   where t.source = 'swap_api' and t.received_at >= now() - interval '15 min'
   group by 1
), lote as (
  select date_trunc('minute', a.received_at) as minuto, ceil(count(distinct a.mint) / 50.0) as chamadas
    from meme_market_activity_1m a
   where a.received_at >= now() - interval '15 min' and a.window_name = '1m'
   group by 1
)
select coalesce(p.minuto, l.minuto)                                    as minuto,
       coalesce(p.mints_com_fita, 0)                                   as pulls_da_fita_aprox,
       coalesce(l.chamadas, 0)                                         as chamadas_do_lote,
       coalesce(p.mints_com_fita, 0) + coalesce(l.chamadas, 0)         as total_aprox
  from pulls p full outer join lote l on l.minuto = p.minuto
 order by 1 desc;

\echo '== §7 recusas do portao por tick (meme_lab_ticks), ultimos 30 min: buyers/sells/flow =='
select date_trunc('minute', k.ticked_at)                               as minuto,
       sum((r.value->>'buyers_unknown')::int)                          as buyers_unknown,
       sum((r.value->>'sells_ratio_unknown')::int)                     as sells_ratio_unknown,
       sum((r.value->>'flow_not_polled')::int)                         as flow_not_polled,
       sum((r.value->>'flow_no_trade_feed')::int)                      as flow_no_trade_feed,
       sum((r.value->>'flow_not_positive')::int)                       as flow_not_positive,
       sum((r.value->>'buyers_below_min')::int)                        as buyers_below_min,
       sum((r.value->>'sells_ratio_above_max')::int)                   as sells_ratio_above_max
  from meme_lab_ticks k, jsonb_each(k.refusals) r
 where k.ticked_at >= now() - interval '30 min'
 group by 1 order by 1 desc;

rollback;
