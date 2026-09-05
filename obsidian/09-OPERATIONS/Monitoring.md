---
tags: [operacoes, monitoramento, observabilidade]
updated: 2026-09-05
status: parcial
---

# Monitoring

## O que existe hoje

- **`/health`** — liveness do processo `api` (e de `HEALTH_PORT` nos workers, quando existirem).
- **`/ready`** — checa Postgres e Redis alcançáveis, com timeout configurável (`READY_CHECK_TIMEOUT_S`) e branch testado de banco fora do ar.
- **`/metrics`** — exposto, protegido por token (`METRICS_TOKEN`); vazio em staging/produção desativa o endpoint (404) em vez de expor métricas sem autenticação.
- **Logs estruturados** — JSON via `structlog` (nunca `print`), com `request_id`, `org_id`, `role`. Regra de lint (`quality/no-direct-console` no TS) força uso de `@/lib/logger` no frontend.
- **Sentry** — inicializado atrás de env (`SENTRY_DSN`); sem chave = desligado. `release` planejado para ser o SHA do commit quando houver deploy real.
- **Auditoria** — `audit_logs` (append-only, RLS, particionado mensalmente) já existe e é gravado por `@audited` nos serviços que mutam dados de tenant no M0 (orgs, workspaces, membros, convites).

## Observabilidade do market-worker (validada na T1.6, 2026-09-05)

Tudo abaixo foi lido de um worker rodando contra a Binance ao vivo; a prova está em `.claude/state/t16-proof.md`.

- **Heartbeat por exchange** — `hb:market:{exchange}` em Redis, **implementado e verificado**: `ws_state`, `subscriptions`, `markets_monitored`, `reconnects`, `open_gaps`, `last_event_at`, `ts` e, desde a T1.6, `dropped_events`. É o que `GET /api/v1/system/workers` e `GET /api/v1/system/market-status` leem — **não** a tabela `worker_heartbeats`, que continua vazia e sem produtor (a página anterior desta base dizia o contrário).
- **`dropped_events`** — contador de eventos WS que o `BoundedEventQueue` descartou por fila cheia. Antes da T1.6 ele era incrementado no adaptador e **nunca lido por nada**; hoje vai para o hash do heartbeat e para `market_dropped_events_total{exchange}`. Na primeira medição real marcou **256.733 descartes em 75 s** com 200 mercados. É o sinal de que a ingestão está perdendo dado — sem ele, a degradação era invisível.
- **`/metrics` do worker** (porta `HEALTH_PORT`, 8001) — real e populado: `market_snapshot_stale_fields_total{field}`, `market_snapshot_skipped_no_data_total`, `market_ingestion_gaps{exchange,status}`, `market_persistence_drops_total`, `market_persistence_loss_reports_dropped_total`, `market_liquidation_duplicates_total`, `market_publish_failures_total`, `hunter_worker_errors_total{role}` e, novos na T1.6, `market_dropped_events_total{exchange}` e `market_system_event_record_failures_total{event}`.
- **`system_events`** — gravado de verdade. Numa corrida de 1h50 com apagões induzidos: 686 `persistence_drop`, 44 `ws_state_changed`, 40 `ws_reconnected`, 36 `adapter_reconnect`, 34 `persistence_lag`, 5 `connection_watchdog`, 1 `ws_disconnected` (critical). Confirma o contrato "fila descarta **com métrica**".
- **`/ready` do worker** — checa `database`, `redis`, `ingestion`, `persistence` e `partitions`, e devolve 503 quando qualquer um reprova. **Cuidado medido:** o servidor de saúde divide o event loop com a ingestão, então sob carga plena a latência do próprio `/ready` variou de 0,01 s a 24,79 s. O healthcheck do Compose foi para `timeout: 30s`, `interval: 15s`, `retries: 5` por causa disso — com os 3 s anteriores ele dava sequências de quatro falsos negativos.

### Buraco de operação conhecido (T1.7/ops)

`restart: unless-stopped` só cobre **morte de processo**. Quando o worker fica vivo-e-parado, o healthcheck detecta corretamente e **ninguém age**: Docker Compose puro não reinicia por healthcheck. Foi observado na T1.6 (worker a 0,2 % de CPU, `/ready` 503, zero ingestão, 19 minutos sem uma linha de log). A causa daquele caso foi corrigida (timeouts no cliente Redis), mas o buraco estrutural continua: falta um `autoheal` ou um watchdog que mate o processo depois de N minutos de `/ready` reprovado.

## O que é planejado, ainda sem implementação

- **Watchdog / staleness** — `/system` mostrando latência, último dado, conexões WS por exchange (M1); heartbeat por exchange `hb:market:{exchange}` com `stale` se `last_event_at` > 10 s (M1).
- **Alarmes mínimos**: worker `stale` > 60 s, lag de stream > 5.000, erro de exchange > 10/min, partição faltando, taxa de erro do Sentry — todos dependem de dado real fluindo pelos streams, que ainda não existem.
- **Métricas específicas do pipeline**: eventos por stream (produzidos, consumidos, lag), latência por exchange, gaps de candle, propostas aprovadas/rejeitadas por check, fills simulados, erro por worker — nenhuma tem produtor ainda.
- **PostHog** (product analytics) — inicializado atrás de env, mas a lista de eventos de `docs/PRODUCT.md` §6 (`user_signed_up`, `portfolio_created`, etc.) ainda não está instrumentada em todo o fluxo — só o essencial de auth/onboarding do M0.

## Relacionadas

[[Deployment]] · [[Infrastructure]] · [[Environment Variables]]

## Fontes

`docs/ARCHITECTURE.md` §11, `docs/DEPLOYMENT.md` §5, `docs/SECURITY.md` §5, `.env.example`
