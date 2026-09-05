---
tags: [operacoes, env, configuracao]
updated: 2026-09-05
status: implementado
---

# Environment Variables

Tabela completa a partir de `.env.example` (raiz do repo). Este arquivo é só um exemplo — nunca commitar valores reais. `HUNTER_MASTER_KEY`, `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`, `AUTH_SECRET`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BINANCE_API_SECRET`, `BYBIT_API_SECRET` e qualquer outra chave/segredo desta lista são **segredo, nunca no repo** — vivem só em env do provedor (Railway/Fly secrets) ou KMS em produção. Ver [[../06-DECISIONS/Architecture Decisions]] e `docs/SECURITY.md` §4.

## Ambiente

| Variável | Default no exemplo | Propósito |
|---|---|---|
| `HUNTER_ENV` | `development` | `development \| staging \| production` |
| `HUNTER_ROLE` | `all` | `api \| market \| scanner \| strategy \| execution \| analytics \| all` |
| `LOG_LEVEL` | `INFO` | Nível de log estruturado |
| `WEB_ORIGIN` | `http://localhost:3000` | Allowlist de CORS (uma ou mais origens) |
| `API_URL` | `http://localhost:8000` | Usado pelo web server-side |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | URL pública da API |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000/ws` | URL pública do WebSocket |
| `API_PORT` | `8000` | Porta HTTP do processo `api` |
| `HEALTH_PORT` | `8001` | Porta de `/health`, `/ready`, `/metrics` nos workers |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Allowlist exata do middleware CORS |
| `RATE_LIMIT_PER_MINUTE` | `120` | Limite por endereço (superfície não autenticada) |
| `RATE_LIMIT_PER_MINUTE_PRINCIPAL` | `600` | Limite por principal autenticado |
| `READY_CHECK_TIMEOUT_S` | `3.0` | Timeout por dependência em `/ready` |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | IP confiável para `X-Forwarded-For` |
| `METRICS_TOKEN` | (vazio) | Se definido, `/metrics` exige Bearer; vazio em staging/prod desativa `/metrics` (404) — **segredo, nunca no repo** |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Limite de corpo em `/api/*` |
| `JWKS_REFRESH_COOLDOWN_S` | `60` | Intervalo mínimo entre refetches do JWKS |
| `JWKS_MAX_STALE_S` | `86400` | Tempo que o JWKS em cache continua válido sem refetch bem-sucedido |
| `WS_REVALIDATE_INTERVAL_S` | `60` | Intervalo de revalidação de um WebSocket aberto |
| `WS_HANDSHAKES_PER_MINUTE` | `30` | Handshakes `/ws` por endereço por minuto |
| `WS_MAX_CONNECTIONS_PER_PRINCIPAL` | `5` | Conexões `/ws` vivas por principal, por processo |
| `WEBHOOK_CLAIM_STALE_S` | `300` | Janela para redelivery retomar um claim de webhook inacabado |

## Banco e cache

| Variável | Default no exemplo | Propósito |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://hunter:hunter@localhost:5432/hunter` | Conexão principal (pooler) — **segredo em prod** |
| `DATABASE_URL_MIGRATIONS` | `postgresql://hunter:hunter@localhost:5432/hunter` | Conexão direta (sem pooler) para Alembic — **segredo em prod** |
| `REDIS_URL` | `redis://localhost:6379/0` | Conexão Redis — **segredo em prod** |
| `DB_POOL_SIZE` | `5` | Tamanho do pool do engine assíncrono |
| `DB_MAX_OVERFLOW` | `5` | Conexões extras além do pool sob carga |

## Auth (Clerk) — obrigatórias em staging/production

| Variável | Default | Propósito |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | (vazio) | Pública por design (browser) |
| `CLERK_SECRET_KEY` | (vazio) | **Segredo, nunca no repo** |
| `CLERK_WEBHOOK_SECRET` | (vazio) | **Segredo, nunca no repo** |
| `CLERK_JWKS_URL` | (vazio) | `https://<instance>.clerk.accounts.dev/.well-known/jwks.json` |
| `CLERK_ISSUER` | (vazio) | Issuer esperado no JWT |

## Segredos de aplicação

| Variável | Default | Propósito |
|---|---|---|
| `AUTH_SECRET` | (vazio) | Assinatura de tokens internos (tickets WS, convites) — **segredo, nunca no repo** |
| `HUNTER_MASTER_KEY` | (vazio) | Dev: base64 de 32 bytes; prod: KMS — **segredo, nunca no repo** |
| `KMS_KEY_ID` | (vazio) | Prod, Fase 3 |

## Observabilidade e produto

| Variável | Default | Propósito |
|---|---|---|
| `SENTRY_DSN` | (vazio) | Semi-público; sem valor = Sentry desligado |
| `SENTRY_ENVIRONMENT` | `development` | Ambiente reportado ao Sentry |
| `NEXT_PUBLIC_POSTHOG_KEY` | (vazio) | Pública por design |
| `NEXT_PUBLIC_POSTHOG_HOST` | `https://us.i.posthog.com` | Host do PostHog |

## LLM (Fase 2 — schema de env já existe, uso ainda desligado)

| Variável | Default | Propósito |
|---|---|---|
| `ANTHROPIC_API_KEY` | (vazio) | **Segredo, nunca no repo** |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Modelo padrão Anthropic |
| `OPENAI_API_KEY` | (vazio) | **Segredo, nunca no repo** (ADR 0002) |
| `OPENAI_MODEL` | `gpt-6-astra` | Modelo padrão OpenAI |
| `LLM_PROVIDER` | `anthropic` | `anthropic \| openai` |
| `LLM_MODEL` | (vazio) | Vazio = padrão do provedor |

## Exchanges (opcionais no MVP)

| Variável | Default | Propósito |
|---|---|---|
| `BINANCE_API_KEY` | (vazio) | Só eleva rate limit de dados públicos |
| `BINANCE_API_SECRET` | (vazio) | **Segredo, nunca no repo** |
| `BYBIT_API_KEY` | (vazio) | Só eleva rate limit de dados públicos |
| `BYBIT_API_SECRET` | (vazio) | **Segredo, nunca no repo** |

Nunca com permissão de trade/saque — chaves de sistema são só para dados públicos.

## Feature flags de sistema

| Variável | Default | Propósito |
|---|---|---|
| `ENABLE_LIVE_TRADING` | `false` | Trava live trading até a Fase 4, sem exceções |
| `ENABLE_SOCIAL_INTELLIGENCE` | `false` | Fase 2/3 |
| `ENABLE_ONCHAIN` | `false` | Fase 3 |
| `ENABLE_STRIPE` | `false` | Fase 3 |
| `ENABLE_LLM_ANALYSIS` | `false` | Fase 2 |
| `ENABLE_ARENA` | `false` | M6 |
| `ENABLE_BACKTESTS` | `false` | M6 |
| `SYSTEM_KILL_SWITCH` | `ACTIVE` | `ACTIVE \| WARNING \| TRADING_DISABLED \| EMERGENCY` |

## Dimensionamento

| Variável | Default | Propósito |
|---|---|---|
| `MARKET_UNIVERSE_SIZE` | `200` | Mercados monitorados por exchange (M1) |
| `BOOK_DEPTH` | `25` | Profundidade do book mantida em hot state |
| `TICK_COALESCE_MS` | `250` | Coalescência de ticks |
| `FEATURE_THROTTLE_MS` | `1000` | Throttle do Feature Engine por símbolo |
| `RADAR_PUSH_MS` | `1000` | Throttle de push do radar |
| `RETENTION_CANDLES_1M_DAYS` | `90` | Retenção de candles de 1 minuto |
| `RETENTION_FEATURE_SNAPSHOTS_DAYS` | `14` | Retenção de snapshots de features |

## Relacionadas

[[Deployment]] · [[Monitoring]] · [[Architecture Decisions]]

## Fontes

`.env.example`, `docs/SECURITY.md` §4 e §8
