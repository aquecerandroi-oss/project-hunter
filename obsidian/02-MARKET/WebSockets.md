---
tags: [mercado, websocket, m1]
updated: 2026-09-05
status: implementado
---

# WebSockets

Duas camadas distintas de WebSocket no sistema.

## 1. WS de mercado (exchange → market-worker) — **Binance implementado** (commit `97c36ff`, T1.2 + T1.2b); Bybit planejado

- **Duas rotas, não uma** (aviso oficial da Binance): `wss://fstream.binance.com/public/stream` para `@depth20` e `@bookTicker`; `wss://fstream.binance.com/market/stream` para `@aggTrade`, `@kline_1m`, `@markPrice@1s` e `@forceOrder`. Com 200 símbolos: 400 streams na rota public e 800 na market. Rotas conferidas contra a doc oficial e, de forma independente, contra `ccxt` e `python-binance`.
- **Limite de 1024 streams por conexão** (streams, não símbolos): asserido no código em cada ponto que altera grupos — levanta erro em vez de truncar. Grupos de até 200 símbolos por conexão.
- **`@depth20` sem sufixo**, tratado como substituição integral do snapshot top 20: sem livro local, sem acumulação de deltas, níveis ausentes do snapshot novo somem. Reconciliação de profundidade pelo REST.
- **Assinaturas incrementais:** `update_subscriptions(added, removed, channels)` recalcula o universo e manda só o diff (JSON-RPC `SUBSCRIBE`/`UNSUBSCRIBE` com `id` e ACK), preservando as assinaturas dos símbolos que ficaram; `UNSUBSCRIBE` vai antes de `SUBSCRIBE` para o transitório nunca passar de 1024. Diff que chega no meio do handshake é reconciliado por catch-up. ACK de erro (ou ACK que não chega) derruba os nomes do estado e reinicia **só** aquela conexão.
- **Reconexão:** backoff exponencial 1 s → 60 s com jitter; `recv()` com deadline, então a rotação anterior às 24 h dispara mesmo em socket silencioso e um socket ocioso/meio-aberto é detectado dentro do adapter; `restart_connection(key)` reinicia uma conexão sem derrubar as outras.
- **Prova de vida:** `ConnectionState` só avança `last_data_event_*` com frame de dado bem-formado — ACK de controle e payload malformado (inclusive `bookTicker` vazio) não contam e não zeram o backoff.
- **Contrapressão:** `BoundedEventQueue` limita a fila interna do adapter e **nunca** descarta um kline final; sob saturação o produtor espera em vez de estourar memória.
- **Bybit:** `subscribe` em lotes de 10 args; heartbeat `ping` a cada 20 s — ainda planejado (M1b, mesmo contrato).
- **Heartbeat:** `hb:market:{exchange}` com `last_event_at`; `/system` mostra `stale` se > 10 s.

Limitações conhecidas aceitas no M1 (cenário de falha em `docs/plans/M1.md`): rotação sem sobreposição — a conexão fecha e só então a substituta abre, deixando um buraco do tamanho do handshake a cada ~23,5 h por conexão; janela de ~31 s para detectar leitor morto; fila limitada por itens, não por bytes/idade.

## 2. WS da aplicação (api → browser) — infraestrutura existe, sem dado real ainda

O `apps/web` já tem um hook `useRealtime(channel)` planejado com reconexão e fallback para polling de 5 s se a conexão cair, e o `api` já implementa autenticação de WebSocket: token enviado na primeira mensagem (`auth`), nunca na query string; conexão fechada se não autenticar em 5 s; revalidação periódica da associação do principal (`WS_REVALIDATE_INTERVAL_S`); limites de handshake por IP (`WS_HANDSHAKES_PER_MINUTE`) e de conexões vivas por principal (`WS_MAX_CONNECTIONS_PER_PRINCIPAL`), com fechamento por código de aplicação `4429`/`4403`. Isso já está implementado no M0 (auth/tenancy), mas os canais de dado real (`rt:market:*`, `rt:radar`, `rt:org:{id}:portfolio:*`, `rt:org:{id}:risk`, `rt:system`) não têm nada publicando neles ainda — dependem do market-worker (M1) e dos demais workers.

O `api` assina só os canais que algum cliente pediu, com autorização por organização, e reenvia com throttling (250 ms preços, 1 s radar, imediato risk events) — throttling planejado, sem tráfego real hoje.

## Relacionadas

[[Market Collector]] · [[Exchange Adapters]] · [[Data Flow]]

## Fontes

`docs/EXCHANGE_INTEGRATION.md` §4, `docs/ARCHITECTURE.md` §5, `docs/SECURITY.md` §1 e §5
