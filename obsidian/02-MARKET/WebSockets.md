---
tags: [mercado, websocket, m1]
updated: 2026-09-05
status: planejado
---

# WebSockets

Duas camadas distintas de WebSocket no sistema — nenhuma das duas está ligada a dados reais de mercado hoje.

## 1. WS de mercado (exchange → market-worker) — planejado, M1

- **Binance:** até 1024 streams por conexão; plano é usar no máximo 200 símbolos × 5 streams = 1000 por conexão (1 conexão por 200 símbolos); reconectar antes das 24 h de vida da conexão.
- **Bybit:** `subscribe` em lotes de 10 args; heartbeat `ping` a cada 20 s.
- **Reconexão:** backoff exponencial 1 s → 60 s com jitter; ao reconectar, snapshot REST do book e verificação de gaps de candle.
- **Book local:** reconstruído a partir de snapshot + diffs (Binance) ou snapshot/delta (Bybit); checagem de sequência; ressincronização ao detectar salto.
- **Heartbeat:** `hb:market:{exchange}` com `last_event_at`; `/system` mostrará `stale` se > 10 s.

## 2. WS da aplicação (api → browser) — infraestrutura existe, sem dado real ainda

O `apps/web` já tem um hook `useRealtime(channel)` planejado com reconexão e fallback para polling de 5 s se a conexão cair, e o `api` já implementa autenticação de WebSocket: token enviado na primeira mensagem (`auth`), nunca na query string; conexão fechada se não autenticar em 5 s; revalidação periódica da associação do principal (`WS_REVALIDATE_INTERVAL_S`); limites de handshake por IP (`WS_HANDSHAKES_PER_MINUTE`) e de conexões vivas por principal (`WS_MAX_CONNECTIONS_PER_PRINCIPAL`), com fechamento por código de aplicação `4429`/`4403`. Isso já está implementado no M0 (auth/tenancy), mas os canais de dado real (`rt:market:*`, `rt:radar`, `rt:org:{id}:portfolio:*`, `rt:org:{id}:risk`, `rt:system`) não têm nada publicando neles ainda — dependem do market-worker (M1) e dos demais workers.

O `api` assina só os canais que algum cliente pediu, com autorização por organização, e reenvia com throttling (250 ms preços, 1 s radar, imediato risk events) — throttling planejado, sem tráfego real hoje.

## Relacionadas

[[Market Collector]] · [[Exchange Adapters]] · [[Data Flow]]

## Fontes

`docs/EXCHANGE_INTEGRATION.md` §4, `docs/ARCHITECTURE.md` §5, `docs/SECURITY.md` §1 e §5
