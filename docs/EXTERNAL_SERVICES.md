# Serviços externos e integrações (PASSO 7 e item 80.9)

## 1. Necessários para o MVP

| Serviço | Uso | Plano inicial | Alternativa |
|---|---|---|---|
| Clerk | Auth | Free (10k MAU) | Supabase Auth |
| Neon | PostgreSQL | Launch | Railway Postgres, Supabase, RDS |
| Redis (Railway) ou Upstash (plano fixo) | Cache, streams, pub/sub | pequeno | Fly Redis, ElastiCache |
| Vercel | Frontend | Hobby/Pro | Railway (imagem web) |
| Railway | API e workers | Hobby/Pro | Fly.io, Render, ECS |
| GitHub | Repositório e CI | Free | — |
| Sentry | Erros | Developer | GlitchTip |
| PostHog | Product analytics | Free | — |
| Binance API pública | Market data | sem chave | chave read-only para rate limit maior |
| Bybit API pública | Market data | sem chave | idem |

## 2. Fase 2

| Serviço | Uso |
|---|---|
| Anthropic API | Classificação de notícias, extração de entidades, narrativa, sentimento, resumos. Modelo padrão `claude-opus-5`; `claude-haiku-4-5` para triagem de alto volume se o custo exigir. Structured outputs; sem ferramentas com efeito. |
| Resend (ou Postmark) | E-mail de alertas e convites fora do Clerk |
| Telegram Bot API, Discord Webhooks | Canais de alerta |
| CryptoPanic / NewsAPI / RSS oficiais | Notícias e anúncios |
| CoinGecko | Market cap, categorias, `coingecko_id` para `assets` |
| Coinglass (ou agregação própria) | Liquidações e OI agregados cross-exchange |
| Stripe | Billing (Fase 3) |

## 3. Fase 3

| Serviço | Uso |
|---|---|
| Reddit API, X API | Social |
| Google Trends (pytrends, não oficial) | Interesse de busca |
| Dune / Nansen / Arkham / Glassnode | On-chain e whales |
| Token unlock calendars (TokenUnlocks) | Unlocks |
| OKX, Hyperliquid, Coinbase, Kraken | Exchanges adicionais |
| AWS KMS ou GCP KMS | Cifragem de chaves de exchange |
| Object storage (R2/S3) | Exportações, backtests grandes, fixtures |

## 4. Fase 4

Testnets: Binance Futures Testnet, Bybit Testnet. Sem produção live antes do checklist de `ROADMAP.md`.
