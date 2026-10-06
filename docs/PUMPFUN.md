# pump.fun — mapa da superfície de dados off-chain

**Status:** referência do projeto para este venue (T4.0c). Tudo abaixo foi **medido ao vivo em
12/09/2026, 02:18–02:41 BRT**, com `curl`/`websockets` sem chave, sem login e sem cookie de sessão
(só `User-Agent` de navegador, `Accept: application/json`, `Origin: https://pump.fun`). Nada foi
inventado: cada endpoint traz o código HTTP que voltou e a forma (nomes/tipos) do JSON; o log
completo de chamadas, com hora de Brasília e respostas cruas redigidas, está em
`.claude/state/notes-T4.0c.md`. Números "documentados" citam a página oficial e a data
"Last Updated" dela; números "observados" são amostra pontual desta sessão, não SLA.

**Orçamento respeitado:** 40 requisições ao `frontend-api-v3` (limite medido 60/60 s por IP e por
grupo de endpoint), espaçadas ≥ 2,5 s; 22 ao `swap-api` (limite medido 1000/60 s); 1 conexão de
30 s ao WS do site (`/ws/trenches`); 2 conexões de 30 s ao WS do PumpPortal (a primeira perdeu a
gravação por erro local de caminho; a segunda é a registrada); 1 handshake de leitura ao NATS.

Fontes da descoberta: HTML público de `https://pump.fun/` (+ `/coin/{mint}`, `/live`, `/mayhem`,
`/docs/*`), 127 chunks `_next/static/chunks/*.js` baixados e varridos por literais de URL/`fetch`,
lista comunitária `github.com/BankkRoll/pumpfun-apis` (96 estrelas, push 2026-06-17, captura HAR
de 120 endpoints) e as páginas oficiais `pump.fun/docs/fees`, `/docs/bonding-curve`,
`/docs/create-coin`, `/docs/mayhem-mode` e `pumpportal.fun` (docs Docusaurus).

## 0. Mapa de hosts (o que o site usa, lido do bundle)

| Host | Papel (constante no bundle) | Chave? | Limite observado | Estado em 12/09 |
|---|---|---|---|---|
| `frontend-api-v3.pump.fun` | `CLIENT` — metadados, listagens, social, mayhem, PnL, posições | Não para GET público; rotas sociais/escrita usam cookie (`credentials:"include"`) | `x-ratelimit-limit` **por grupo de endpoint**: 20, 30, 50, 60 ou 600 por 60 s (§1) | vivo |
| `swap-api.pump.fun` | `PUMP_SWAP`/`SWAP_API` — trades, candles, atividade de mercado, ATH, fee-sharing | Não | `x-ratelimit-limit: 1000`, reset ≤ 60 s; o `remaining` cai mais do que as minhas chamadas (contador compartilhado ou por rota) | vivo |
| `advanced-indexer.pump.fun` | `getAdvancedIndexerUrl` — boards do screener ("trenches"), coin em memória, **WS de boards** | Não | sem cabeçalho de rate limit | vivo |
| `profile-api.pump.fun` | `PROFILE` — saldos, PnL por token/carteira, PnL de holders, transações | rotas com id de carteira; não testadas além de um 404 no caminho nu | vivo (404 em `/balance/summary` sem id) |
| `livestream-api.pump.fun` | `getLivestreamServiceUrl` — `POST /livestream/playlist-map {mints[]}` | Não testado com POST | vivo (404 no GET) |
| `blockchain-swap.pump.fun` | `getBlockchainApiServiceUrl` — **construtor de transações do site** (`/transactions/swap-build`), `/supported/coin-create-mints`, `/coins/sign-create-tx` | Não | sem cabeçalho | vivo |
| `fun-block.pump.fun` | `getBlockchainClientUrl` — doações/caridade (`/donate/*`) | cookie | — | vivo (400 de validação) |
| `advanced-api-v2.pump.fun` | `getAdvancedClientServerUrl` — ainda referenciado no bundle | — | — | **HTTP 530, Cloudflare 1016** (origem morta). A lista comunitária rotula todas as capturas com este host — artefato da ferramenta HAR, não use |
| `solana-mainnet.pump.fun/<uuid>` | RPC Solana do próprio site (HTTPS e WSS), chave embutida no bundle | chave do site | não medido | `getHealth` → `ok`. **Não é para uso de terceiros**: é a cota do site |
| `wss://multichain-prod.nats.realtime.pump.fun` | NATS — eventos de trade multichain (EVM) | `auth_required: true` no `INFO` | — | vivo, fechado (ver §10: hoje também `prod-v2` e `unified-prod`) |
| `socket.io` (`livechatUrl`, vindo da config do servidor, não do bundle estático) | chat da livestream | token de auth no payload | — | não conectado (não é feed de trades) |
| `frontend-api.pump.fun` (v1) / `frontend-api-v2` | domínios antigos dos tutoriais | — | — | 530/1016 (T4.0); v2 "deprecated" na lista comunitária |

## 1. Inventário — `frontend-api-v3.pump.fun`

Legenda: **RL** = `x-ratelimit-limit` devolvido (janela `x-ratelimit-reset: 60`); "—" = sem
cabeçalho. **Auth** = "não" quando a chamada anônima devolveu 200. Formas completas (nomes e tipos)
em `notes-T4.0c.md` §4; aqui vai o resumo.

### 1.1 Chamados ao vivo (24 rotas distintas, 40 requisições)

| # | Método e path | Query observada (bundle) | Auth | HTTP | RL | Forma (resumo) |
|---|---|---|---|---|---|---|
| 1 | `GET /coins` | `offset, limit, sort, order, includeNsfw[, complete=true][, searchTerm][, creator][, tokenizedAgent=true][, isCharity=true][, deviceId, sessionId]` | não | 200 | 60 | `[Coin]` — 54 campos (§1.3). **Cap de 70 itens por página**: `limit=100` e `limit=1000` devolvem 70. `offset` funciona (paginei até 630). `sort=created_timestamp` e `sort=market_cap` confirmados; `complete=true` filtra graduadas; `searchTerm=pepe` busca por nome (ver §10: +5 campos no `Coin`, `chain_id` CAIP-2) |
| 2 | `GET /coins/{mint}` | — | não | 200 | — | `Coin` + `security_verdict{verdict,scope,reasons[],decided_by,provider,version,updated_at,source}` (ver §10: **404 em 06/10**; `/coins-v3/{mint}` responde 200) |
| 3 | `GET /coins-v3/{mint}` | `includeLiveStreamInfo=bool` | não | 200 | 60 | `Coin` (mesmos campos; sem `security_verdict` nesta amostra) |
| 4 | `GET /sol-price` | — | não | 200 | 50 | `{solPrice: float, asOfTimestamp: int(ms), stale: bool}` |
| 5 | `GET /coins/great-coins` | (`?…` opcional) | não | 200 | 20 | `[Coin]` (5) — "trending"; inclui coins EVM (`mint` 0x…), `canonical_pool_liquidity_usd`, `pump_swap_pool`, `inverted` |
| 6 | `GET /coins/top-tokens/mints` | — | não | 200 | 60 | `[str]` (502 mints; começa em wSOL; inclui tokens fora do pump) |
| 7 | `GET /coins/similar` | `mint, limit=5, offset=0, includeNsfw` | não | 200 | 20 | `[Coin]` |
| 8 | `GET /mayhem/top-coins` | `window=24h` | não | 200 | 60 | `{window, items[50]{rank, mint, netUsdDeployed}, updatedAt}` |
| 9 | `GET /mayhem/top-traders` | `window=24h` | não | 200 | 60 | `{window, items[50]{rank, address, realisedPnlUsd, winRate, volumeUsd, tradeCount}, updatedAt}` (ver §10: também `window=7d`) |
| 10 | `GET /pnl-leaderboard` | `period ∈ {daily, weekly, monthly}, sort?, limit?` | não | 200 (400 com `period=24h`) | 60 | `{entries[]{rank, walletAddress, pnlSol, pnlUsd, pnlPercent, buySpendSol, realizedPnl*, unrealizedPnl*, positionsCount, topPositions[]{mint, chainId, symbol, name, imageUri}, username, userId…}, periodType, periodLabel, windowStartSec}` (ver §10: `sort` realized/unrealized/combined, `limit` ≤ 100, sem `offset`) |
| 11 | `GET /users/{address}` | — | não | 200 | 30 | `{address, userId, is_pump_user, username, profile_image, kind, member_count, following, followers, bio, x_username, canonical_svm_wallet, group_badges[]}` (ver §10: +5 campos) |
| 12 | `GET /coins-v2/user-created-coins/{address}` | `limit=10, offset=0` | não | 200 | 60 | `{limit, offset, count, coins[Coin]}` |
| 13 | `GET /coins/top-holders/{mint}` | `shape=web` | não | 200 | 60 | `{topHolders[50]{address, amount(float, unidades UI)}, totalHolders: int}` (ver §10: superada por `top-holders-v2`) |
| 14 | `GET /token-holders/{mint}/count` | — | não | 200 | 60 | `{mint, chain, networkId, holderCount}` |
| 15 | `GET /coins-v2/{mint}/mayhem-state` | — | não | 200 | 60 | `{mint, state ∈ active/paused/completed, mode ∈ auto/manual, pause_reason}` (ex.: `below_initial_buy_floor`) |
| 16 | `POST /coins-v2/mints` | corpo `{mints[], includeNsfw, include_nsfw}` | não | 201 | 30 | `[Coin]` (lote de metadados; o site usa `credentials:"include"`, mas anônimo funcionou) |
| 17 | `GET /user-positions/{wallet}` | `mints=<mint>[,…]` obrigatório (≤ 200; 400 sem ele) | não | 200 | **600** | `{positions[]{coinMint, chainId, isExited, walletAddress, amountHeld, pnlUsd, pnlPercentage, costBasisAmount, costBasisUsd, amountBoughtUsd, amountBought, callout, hasTransfers, likelyLost, valueUsd, tokenPriceUsd, realizedPnlUsd, updatedAt}}` (ver §10: +`openedAt`, `tradeCount`) |
| 18 | `GET /coins/search-unrestricted` | `offset, limit, sort, order, includeNsfw, currentlyLive=true[, tokenizedAgent][, isCharity]`; `sort` também aceita `featured`, `livestream_num_participants` (bundle) | não | 200 | — | `[Coin]` + campos de live: `num_participants, playlist_url(_high/_low), playlist_status, thumbnail, vod_playlist_url, volume_1h_usd, recommendation_id/rank, last_reply, inverted, pump_swap_pool, banner_uri` |
| 19 | `GET /global-params/{created_timestamp_ms}` | path = timestamp da criação da coin | não | 200 | 50 | `{slot, signature, initial_virtual_token_reserves, initial_virtual_sol_reserves, initial_virtual_quote_reserves, initial_real_token_reserves, token_total_supply, fee_basis_points, timestamp}` — **parâmetros iniciais da curva vigentes naquele instante** (§4.2) |
| 20 | `GET /coins/mayhem-mode` | `limit=60, mayhemState?` | não | 200 (A4.1b) | — | `[Coin]` com `mayhem_state` |
| 21 | `GET /mayhem/overview` | — | não | 200 (A4.1b) | — | `{activeCoins, coinsCreated{24h,7d}, coinsCreatedByMode{auto,manual}{24h,7d}, updatedAt}` |
| 22 | `GET /coins/king-of-the-hill` | `includeNsfw` | — | **404** `Coin not found for mint: king-of-the-hill` | — | rota v1 morta: o router v3 trata como `/coins/{mint}` |
| 23 | `GET /coins/latest`, `GET /candlesticks/{mint}`, `GET /replies/{mint}`, `GET /trades/latest`, `GET /metas/current` | (v1) | — | **404** | — | rotas v1/v2 documentadas pela comunidade **não existem** em v3 |

### 1.2 Vistos no bundle, não chamados (precisam de cookie de sessão, são escrita, ou não cabem no orçamento) (ver §10: várias foram lidas na releitura de 06/10)

`POST /profiles/verified {ids[]}`, `POST /users/batch`, `GET /users/search-v2?…`, `GET /users/mention-candidates`,
`GET /users/{id}/mutual-followers`, `GET|POST|DELETE /following/*`, `/following/v3/{following|followers}/count/{id}`,
`GET /followed-holders/{mint}`, `GET /following-positions/alerts`, `GET /home-feed[/new[/count]]`,
`GET /mint-positions/{mint}`, `GET /pnl-leaderboard/positions`, `GET /pnl-leaderboard/projected-rank`,
`GET /user-portfolio/{addr}`, `POST /user-portfolio/non-spam/{addr}`, `/bookmarks*`, `GET /coins/bookmarks/{id}`,
`/callout/*` (create, list/{mint}, top/{mint}, user/{addr}/mint/{mint}, {id}/replies, like, repost),
`GET /creator-rewards-tos`, `GET /payouts`, `GET /payouts/leaderboard`, `POST /share-video/replay`,
`GET /twitter/tweet`, `GET /auth/disabled-features`, `GET /intercom/hmac`, `GET /portfolio-summary`,
`GET /notifications`, `/moderation`, `/leaderboard`, `GET /coin-narrative/by-mints` (captura comunitária),
`POST /wallet-overview`, `POST /x/public-handles`, `GET /kols`, `GET /livestream[/history|/is-approved-creator]`.
Nenhum deles é necessário para radar ou execução.

### 1.3 O objeto `Coin` (54 campos observados em `/coins`, `/coins/{mint}`, `/coins-v3`, `/coins-v2/mints`) (ver §10: 59 chaves, +5)

```
mint, initialized, name, symbol, description, image_uri, metadata_uri, twitter?, website?, telegram?,
bonding_curve, associated_bonding_curve, creator, created_timestamp(ms), complete,
virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, real_token_reserves,
virtual_quote_reserves, real_quote_reserves, total_supply, total_supply_str, base_decimals, quote_decimals,
quote_mint, quote_token_program, token_program, program ("pump"), protocol ("pump"), chain_id, multichain_family,
pool_address, pump_swap_pool?, market_cap, market_cap_usd, market_cap_quote, usd_market_cap,
ath_market_cap, ath_market_cap_timestamp, last_trade_timestamp, reply_count, last_reply?,
nsfw, is_banned, hide_banner, show_name, verified, is_currently_live, livestream_ban_expiry,
is_cashback_enabled, boost_mode (NONE|IN_PROGRESS|COMPLETED), mayhem_state? (active|paused|completed|enabled),
username?, profile_image?, banner_uri?, video_uri?, inverted?, platform?, security_verdict? (só no detalhe)
```

**Ausente em v3:** `king_of_the_hill_timestamp` (a UI ainda referencia o campo num componente,
mas nenhuma das 700+ linhas devolvidas o trouxe) e `raydium_pool`. **Unidades:** reservas em
lamports / menor unidade (6 decimais); `usd_market_cap` já em USD; `total_supply_str` é string
porque o inteiro excede 2^53 em JS.

### 1.4 Regras de uso medidas

- Rate limit **por grupo de endpoint, por IP**, janela de 60 s: `/coins*` 60; `/sol-price` e
  `/global-params` 50; `/coins/great-coins` e `/coins/similar` **20**; `/users` e `POST /coins-v2/mints`
  30; `/user-positions` 600. `/coins/{mint}` e `/coins/search-unrestricted` não devolvem cabeçalho.
  Não testei o comportamento acima do limite (429/ban) — risco de banir o IP da sessão.
- Cloudflare: `cf-cache-status: DYNAMIC` em tudo — sem cache de borda; sem desafio JS para estes GETs.
- `Origin`/`Referer` de `pump.fun` foram enviados em todas as chamadas; em A4.1b as mesmas rotas
  responderam 200 sem eles — não são obrigatórios para as rotas públicas testadas lá.
- Paginação de `/coins`: cap de 70 por página; a lista "mais novas" muda a cada segundo, então
  páginas por `offset` se sobrepõem (700 linhas → 653 mints únicos em 41 s). Dedupe por `mint`.

## 2. Inventário — `swap-api.pump.fun` (trades, candles, atividade)

| # | Método e path | Query/corpo (bundle) | HTTP | RL | Forma |
|---|---|---|---|---|---|
| 1 | `GET /v2/coins/{mint}/candles` | `createdTs(ms), interval ∈ {1s,15s,30s,1m,5m,15m,30m,1h,4h,6h,12h,24h}, limit ≤ 1000` | 200 (400 com intervalo inválido: mensagem lista os 12 valores) | 1000 | `[{timestamp(ms), open, high, low, close, volume}]` — **preços em USD e volume em USD como strings decimais**; só candles com trade (esparso); devolve os **N mais recentes**, sem parâmetro conhecido de "até"/cursor |
| 2 | `GET /v1/coins/{mint}/line-chart` | `createdTs, timeframe=1w, width=72` | 200 | 1000 | `[{time(ms), price}]` (108 pontos) |
| 3 | `GET /v1/coins/{mint}/market-activity` | `[program=pump]` | 200 | 1000 | `{5m,1h,6h,24h}` × `{numTxs, volumeUSD, numUsers, numBuys, numSells, buyVolumeUSD, sellVolumeUSD, numBuyers, numSellers, priceChangePercent}` |
| 4 | `POST /v1/coins/market-activity/batch` | `{addresses[] (1–50), intervals[] ⊆ {1m,5m,1h,6h,24h}, metrics[]}` | 201 (400 com > 50 endereços: `addresses must contain no more than 50 elements`; 400 com 0) | 1000 (+ Cloudflare) | `{mint: {intervalo: {numTxs, volumeUSD, numUsers, numBuys, numSells, buyVolumeUSD, sellVolumeUSD, numBuyers, numSellers, priceChangePercent} \| null}}` — **lote**; as 10 métricas aceitas; janela sem trade = `null`; USD em floats; sem carimbo próprio (o `Date` da resposta é o fim das janelas). **T4.2g: a fita do minuto** (`meme_market_activity_1m`, migração `0032`) |
| 5 | `GET /v2/coins/{mint}/trades` | `limit ≤ 100 (400 acima), cursor, program?, minSolAmount?, minUsdAmount?, chainId?, userAddress?, createdTs?` | 200 | 1000 | `{trades[]{slotIndexId, tx, timestamp(ISO), userAddress, type buy/sell, program (pump, raydium_cpmm, raydium_launchpad…), priceUsd, priceSol, amountUsd, amountSol, baseAmount, quoteAmount, fillPriceUsd, fillPriceSol}, pagination{nextCursor, hasMore, limit}}` — cursor `slotIndexId-timestamp` |
| 6 | `POST /v1/coins/{mint}/trades/batch` | `{userAddresses[], program, createdTs}` | 201 | 1000 | `{wallet: [trade + isBondingCurve]}` — histórico por carteira na coin (base de `creator_sold`) |
| 7 | `GET /v1/coins/{mint}/first-trade` | — | 200 | 1000 | trade + `isDevBuy: bool`; existe para coin de abril/2025 (histórico profundo) |
| 8 | `GET /v1/coins/{mint}/ath` | `currency=USD[, program]` | 200 | 1000 | `{athMarketCap}` |
| 9 | `GET /v1/coins/{mint}/mayhem-stats` | — | 200 | 1000 | `{buyCount, sellCount, totalBuyVolumeSol, totalSellVolumeSol, netSolDeployed}` |
| 10 | `GET /v2/fee-sharing/account/{addr}/totals` | — | 200 | 1000 | totais de creator rewards por quote mint (claimed/unclaimed/earned em atomic/quote/usd, `mintCount`) |
| 11 | `GET /v2/creators/unified-totals` | — | 404 no GET (captura comunitária: **POST** com `addresses`) | — | não testado como POST |
| 12 | `GET /v1` | — | 200 `Hello World!` | 1000 | raiz |

Não chamados: `GET /v1/fee-sharing/account/{addr}/shares?limit&cursor`, `GET /v2/fee-sharing/account/{addr}/coins`,
`POST /v2/creators/unified-charts`, `POST /v1/coins/ath/batch`, `/coins/{mint}/ath?…&program=`.

**Limite real medido (T4.2f, 12/09/2026 10:36–10:48 BRT; 4 sondas, 115 requisições, 5 × 429 — fixture
`packages/exchange-adapters/tests/fixtures/pumpfun/t42f_swap_api_ratelimit_probes.json`):** a coluna RL = 1000
acima é o `x-ratelimit-limit` do backend (janela de 60 s; `remaining` ≈ 900 em toda resposta 200) e **não é o que
recusa**. Quem recusa é uma regra de rate limiting do **Cloudflare** (erro 1015: `server: cloudflare`,
`retry-after: 60`, sem nenhum `x-ratelimit-*` na 429, corpo JSON `"title": "Error 1015: You are being rate
limited"`, `"retry_after": 30`): **~20 requisições por 60 s por IP, qualquer rota** — cortes na 20.ª, 20.ª, 23.ª e
24.ª requisição da janela a 0,85–6 req/s, na 28.ª numa rajada de 16 req/s (contadores distribuídos do CF) e, com
40 mints distintos a 1,2 req/s, na 24.ª; a 0,85 req/s só 8 das 22 aceitas caíram nos 10 s anteriores, logo a
janela não é de 10 s. Uma violação bloqueia **todas** as requisições do IP por 60 s (recuperação com 200 após 60 s
nas 5 vezes). Era isso que os 8 pulls concorrentes da T4.2c/T4.2e disparavam a cada ciclo. O adaptador
(`hunter_exchanges/pumpfun/swap_api.py`) gasta **16/60 s** (`MEME_SWAP_API_BUDGET_60S`; recusa capacidade
acima de 20) em cota exata por ciclo, e uma 429 real (`HttpRateLimited`, com os cabeçalhos) encolhe o orçamento
para 80 % do que passou no minuto anterior e bloqueia o `retry-after`. Aritmética honesta: 16 pulls/min × 180 s
de frescor ÷ ~130 rastreados ≈ **40 % de cobertura da fita por minuto** — o teto deste endpoint a partir de um
IP só (a T4.2e mediu 38,8 %). A saída foi a rota 4, medida na T4.2g.

**O lote medido (T4.2g, 12/09/2026 17:24–17:25 BRT; 5 requisições espaçadas 4 s, 3 × 201, 2 × 400 — fixtures
`packages/exchange-adapters/tests/fixtures/pumpfun/t42g_market_activity_batch_{raw,50_raw,probes}.json`):**
`POST /v1/coins/market-activity/batch` aceita **no máximo 50 endereços por requisição** (140 e 100 → 400 com
`addresses must contain no more than 50 elements`; lista vazia → `at least 1 elements`), **todas as 10 métricas**
(`numBuys`, `numSells`, `buyVolumeUSD`, `sellVolumeUSD`, `numBuyers`, `numSellers` incluídas — o screener do site
só pede 4) e ecoa as janelas `1m`, `5m`, `1h`, `6h`, `24h` como chaves. **Uma janela sem trade vem `null`**, não
um objeto de zeros: em 50 moedas de 7 h de idade, `24h` veio preenchida em 50, `6h` em 7 e `1h`/`5m`/`1m` em
nenhuma. Volumes em **USD** (floats; o adaptador decodifica com `parse_float=Decimal`). A resposta não carrega
carimbo próprio: `observed_at` = o cabeçalho `Date` (segundo inteiro), o fim das janelas. 50 moedas custaram
982 ms e 17 KB, **uma requisição do mesmo orçamento do Cloudflare** — com ~130 rastreados, 3 requisições/min
cobrem o conjunto inteiro e a fita por mint fica com 13 (apostas abertas e `graduating` primeiro).
**Não provado pela sonda:** um bloco `1m` não-nulo numa moeda operando agora (a 5.ª requisição foi gasta numa
lista vazia por erro da sonda); o worker só escreve zero para um `null` de `1m` num ciclo em que alguma moeda
teve o `1m` preenchido (`activity_live_1m` no heartbeat), e conta o resto como escuro (`activity_dark_60s`).
O lote não diz **quem** negociou (`unique_buyers` conta o criador; `creator_net_seller` fica `no_trade_feed`) nem
fala em SOL (o worker converte com a cotação de `/sol-price` que tinha, guardada ao lado: `sol_usd`,
`sol_usd_observed_at`; sem cotação com < 5 min, `no_sol_quote`). Adaptador:
`hunter_exchanges/pumpfun/market_activity.py` (`NormalizedMarketActivity`, `ActivityBatch`, `parse_activity_batch`)
e `SwapApiClient.market_activity_batch`; worker: `services/meme-worker/hunter_meme_worker/activity.py`.

## 3. Superfícies em tempo real

### 3.1 WS do site: `wss://advanced-indexer.pump.fun/ws/trenches` (boards do screener) (ver §10)

- URL: `/ws/trenches?subscription=<JSON url-encoded {board, tier:"web", filterKey}>`; depois de abrir,
  o cliente envia `{"event":"subscribe","data":{"board":"movers","tier":"web","platform":"WEB","surface":"WEB"[, filters, userId, sessionId, deviceId]}}`.
- Boards (`PRO_SCREENER_BOARDS` no bundle): **`new`, `graduating`, `graduated`, `movers`**. O mesmo
  board existe em HTTP: `GET https://advanced-indexer.pump.fun/boards/{board}?offset&limit[&hasTwitter&hasTelegram&hasAnySocial&includeMayhem&marketCapFrom&marketCapTo…]`
  (testado `movers` → 200, 30 entradas).
- Mensagens medidas (1 conexão, 30 s, board `movers`, 180 KB): `{"type":"snapshot","board","version","serverTs","entries":[…]}`
  ×3 e `{"type":"delta","board","baseVersion","version","serverTs","patches":[{"op":"update"|"add"|"remove"|"move","mint","fields":{…},"idx"}]}`
  ×50 (418 patches). Entrada do board (chaves curtas): `m` mint, `c` chain, `n` nome, `t` ticker, `i` imagem,
  `mc` mcap USD, `v/vUsd` volume, `v5/v15/v1h/v24h` (+`vUsd*`), `tx5`, `age`, `kol`, `sn` (snipers), `mh` (mayhem),
  `hs` (tem social), `pg` programa, `pl` plataforma, `gd` data de graduação, `ath`, `bc/sc/txc` (buys/sells/txs),
  `nh` holders, `t10` top-10 %, `dh` dev %, `tw/ws/tg` sociais, `cb` cashback, `dw` dev wallet, `lv` live,
  `np` participantes, `ic`, `so`, `bo`, `pa`, `ih`, `tf/tfUsd` (fees), `desc`, `rid`.
- Cliente do site: aplica patches a cada 1 s; reconexão com backoff `min(1000·2^n, 30000)` ms.
- **Não é feed por trade**: é o estado agregado por coin de um board (top N). Serve como radar
  push (novas, perto de graduar, graduadas, "movers") sem chave e sem polling.
- `GET https://advanced-indexer.pump.fun/in-memory-coin/{mint}` → 200 com 65 campos, entre eles
  `progress`, `graduationDate`, `sniperCount`, `numKolsTraded`, `numHolders`, `top10HoldersPercent`,
  `devHoldingsPercent`, `snipersOwnedPercent`, `bundlerOwnedPercentageV2`, `twitterReuseCount`,
  `isMayhemMode`, `mayhemState`, `priorityFeeSol`, `totalFees`. **Black box** (não documentado), mas
  é a fonte mais rica de features de risco de rug publicamente acessível.

**O que gravamos (T4.2c, migração `0023_meme_boards_trades`, medido ao vivo em 12/09/2026
05:55–06:03 BRT, fixtures `trenches_{new,graduating,graduated,movers}.json`):**

- a assinatura que responde com snapshot é `{"board":…,"tier":"web","filterKey":"default"}` na URL
  mais o evento `subscribe`; `serverTs` é ms; `age` é **segundos** desde a criação; `t10`/`dh` são
  **percentuais com decimais** (77,3048 = 77,3 %); `pa` é o ativo de cotação (`SOL`); `c` é a chain
  (`movers` mistura `eip155:*`); `pg` é o programa (`pump`, `raydium_launchpad`, `pons`); `p` é o
  progresso da curva em % (100 quando graduada); `add` traz `idx` e a entrada inteira, `remove` só o
  mint; `ms` aparece só quando há Mayhem;
- **a versão é por board e salta**: no `graduating` o snapshot 3137948 foi seguido por deltas
  `baseVersion` 3137954, 3137976… (mudanças fora do top-N não são enviadas). O cliente aceita salto
  **para a frente** (conta em `version_gaps`) e ressincroniza (fecha e reassina, snapshot novo) em
  retrocesso, versão que não avança ou patch de mint que o espelho não tem;
- `meme_board_observations`: **uma linha por mint por board por minuto fechado** (bucket pelo nosso
  `received_at`; `observed_at` = último `serverTs` do board no minuto; `mint_updated_at` = último
  patch do mint), com posição, contadores de patches, os campos acima com nomes longos, `extra` (chaves
  não interpretadas: `ic`, `so`, `bo`, `ih`, `rid`) e o **intervalo de exposição**:
  `first_seen_in_board_at`/`last_seen_in_board_at`, `left_board_at` só com `remove` visto,
  `exposure_censored = true` quando o mint some no snapshot de uma reconexão (A4.0g §2);
- `meme_risk_snapshots`: o objeto inteiro de `/in-memory-coin` em `raw jsonb` mais `holders`,
  `top10_share`, `dev_share`, `snipers`, `sniper_share`, `bundled_share`, `progress_pct`; ≤ 1 leitura
  por mint por 5 min, só para mints com aposta paper aberta ou no board `graduating`;
- `meme_trades` passa a ter produtor: `swap-api /v2/coins/{mint}/trades` (`source = 'swap_api'`),
  900/60 s de orçamento (o limite medido 1000 menos 10 %), cursor `slotIndexId-timestamp(ms)`,
  `slot` = os 12 primeiros dígitos do `slotIndexId` (**verificado** contra `getTransaction`:
  `000446373814…` → slot 446373814, `blockTime` = `timestamp`), só linhas `program = pump` com
  cotação SOL exata em lamports; `commitment`, `outer_ix_index`, `inner_ix_index` e `is_mayhem_agent`
  ficam `NULL` (a resposta não os traz); `event_index` = ordinal do trade dentro da mesma tx no lote.

### 3.2 NATS multichain: `wss://multichain-prod.nats.realtime.pump.fun` (ver §10: hoje há 3 hosts NATS)

Handshake lido (só `INFO`, sem `CONNECT`): servidor NATS 2.12.11, `auth_required: true`,
`max_payload: 524288`. O bundle usa para `useMultichainTradeEventSubscription` (trades de coins
**EVM**). Fechado sem credenciais — não é fonte para nós.

### 3.3 socket.io (livechat)

`io(livechatUrl, {path:"/socket.io/", transports:["websocket"], auth:{origin, timestamp, token, deviceId}})`;
`livechatUrl` vem de `apiClientsConfig` do servidor (não está no bundle estático). Só chat de
livestream; o PumpPortal confirma no FAQ que livestream/chat "is not onchain, so it is only accessible
from the Pump.fun site directly". Não conectado.

**Conclusão:** o site **não expõe** um WS público de trades por coin em Solana. A trilha de trades
em tempo real é `swap-api /v2/coins/{mint}/trades` por polling (1000/min) ou PumpPortal/Geyser.

### 3.4 PumpPortal — `wss://pumpportal.fun/api/data` (lido em 12/09/2026 02:19 BRT)

- Medido **sem chave** (`?api-key` omitido): conectou em 0,64 s; `subscribeNewToken` → `{"message":"Successfully subscribed to token creation events."}`;
  `subscribeMigration` → `{"message":"Subscribed to 'migration' events."}`; em 30 s chegaram **6 eventos `txType:"create"`**
  e nenhuma migração. Forma do `create`: `{signature, mint, traderPublicKey, txType, initialBuy, solAmount, bondingCurveKey,
  vTokensInBondingCurve, vSolInBondingCurve, marketCapSol, name, symbol, uri, is_mayhem_mode, pool}`.
- Documentação (`/data-api/real-time/`): métodos `subscribeNewToken` (Free), `subscribeMigration` (Free),
  `subscribeTokenTrade` e `subscribeAccountTrade` ("Metered at 0.01 SOL per 10000 events"; `keys:[…]`);
  `unsubscribe*` correspondentes. "Subscribing to tokens or accounts requires a PumpPortal API key and linked
  wallet funded with at least 0.02 SOL." "PLEASE ONLY USE ONE WEBSOCKET CONNECTION AT A TIME".
- `/fees/`: "Effective May 1, 2026: Trading data is only available to users who subscribe with a PumpPortal API key."
  "every 10000 trades streamed will incur a 0.01 SOL charge to the wallet linked to their API key."
  A página `/pricing/` **não existe** (404) — o preço do feed pago é este.
- FAQ (limites e latência): "Trading and other endpoints are limited at 25 requests per second."; WS:
  "Don't send over 200 subscription messages per second. Don't subscribe to over 5000 addresses in a single
  message."; "bans expire every hour"; dados no nível de commitment "processed", "typically be less than
  100 msec delayed behind gRPC data if you run a server in New York"; "We only provide live trading data
  at this time, you would need to pull historical data from an RPC or other source."

### 3.5 PumpPortal — Local Trading API (`POST https://pumpportal.fun/api/trade-local`)

Citações exatas de `/local-trading-api/trading-api/` e `/fees/` (12/09/2026 02:19 BRT):

> "To get a transaction for signing and sending with a custom RPC, send a POST request to
> https://pumpportal.fun/api/trade-local"
>
> "Your request body must contain the following options: publicKey : Your wallet public key; action :
> "buy" or "sell"; mint : The contract address of the token you want to trade; amount : The amount of SOL
> or tokens to trade. If selling, amount can be a percentage of tokens in your wallet (ex. amount: "100%");
> denominatedInSol : "true" if amount is SOL, "false" if amount is tokens; slippage : The percent slippage
> allowed; priorityFee : Amount to use as priority fee; pool : (optional) Currently 'pump', 'raydium',
> 'pump-amm', 'launchlab', 'raydium-cpmm', 'bonk', and 'auto' are supported options. Default is 'pump'."
>
> "If your parameters are valid, you will receive a serialized transaction in response."
>
> "We take a 0.5% fee on each Local trade. (Note: the fee is calculated before any slippage, so the actual
> fee amount may not be exactly 0.5% of the final trade value.)" — e para a Lightning API
> (`POST /api/trade?api-key=`): "We take a 1% fee on each Lightning trade." "The above fees do not include
> Solana network fees, or any fees charged by the Pump.fun bonding curve."
>
> FAQ: "PumpPortal Local Transactions are signed by your code on your device, PumpPortal never has access
> to your wallet."

O que isso significa para nós: o corpo da resposta é uma `VersionedTransaction` serializada
(exemplo oficial: `VersionedTransaction.from_bytes(response.content)`), assinada localmente com a
nossa keypair e enviada ao **nosso** RPC. Nenhuma chave sai da máquina, mas: (a) a transação é
montada por um terceiro — precisa ser **simulada e inspecionada** (programas invocados, contas,
valor) antes de assinar; (b) custa 0,5 % por trade **além** de 1,25 % da curva; (c) `pool:"auto"`
resolve onde o token está (curva ou PumpSwap) ao custo de até 100 ms; (d) não há chave para
`trade-local` — a Lightning API (chave + carteira custodiada com AES-256 dentro da própria chave) é
a que nunca usaremos. Alternativas sem taxa de terceiro: o construtor do próprio site
(`POST https://blockchain-swap.pump.fun/transactions/swap-build`, corpo com `mint` obrigatório —
422 `missing field 'mint'` com `{}` —, resposta com `quote{amount_out{ui,atomic}, min_amount_out,
slippage_bps, insufficient_funds, price_impact, network_fees, network_fee_denomination sol|usdc,
clamped_amount_in}` e `transaction` base58) — sem taxa adicional segundo `docs/fees` ("none of the
pump.fun frontend services … charge any fees in addition") mas igualmente não documentado; ou montar
a instrução `buy`/`sell` localmente com a IDL oficial (`pump-fun/pump-public-docs`), como o
`chainstacklabs/pumpfun-bonkfun-bot` faz (T4.0 §7). Os parâmetros da curva para cotar localmente
vêm de `/global-params/{ts}` (§4.2) e do estado da `bonding_curve` on-chain.

## 4. Taxas, ciclo de vida e estatísticas ao vivo

### 4.1 Taxas — `https://pump.fun/docs/fees`, **"Last Updated: 20 May 2026"** (ver §10: relida em 06/10, igual)

| Ação | Taxa |
|---|---|
| Criar coin | 0 SOL / 0 USDC |
| Graduação para PumpSwap | 0,015 SOL |
| **Bonding curve** (SOL e USDC) | criador **0,300 %** + protocolo **0,95 %** + LP 0 % = **1,25 %** |
| **PumpSwap, pool canônico, quote SOL** — por market cap (preço × 1 bi de tokens) | 0–420 SOL: 0,300/0,930/0,020 = **1,250 %**; 420–1 470: 0,950/0,050/0,200 = 1,200 %; 1 470–2 460: 1,150 %; 2 460–3 440: 1,100 %; 3 440–4 420: 1,050 %; 4 420–9 820: 1,000 %; 9 820–14 740: 0,950 %; 14 740–19 650: 0,900 %; 19 650–24 560: 0,850 %; 24 560–29 470: 0,800 %; 29 470–34 380: 0,750 %; 34 380–39 300: 0,700 %; 39 300–44 210: 0,650 %; 44 210–49 120: 0,600 %; 49 120–54 030: 0,550 %; 54 030–58 940: 0,525 %; 58 940–63 860: 0,500 %; 63 860–68 770: 0,475 %; 68 770–73 681: 0,450 %; 73 681–78 590: 0,425 %; 78 590–83 500: 0,400 %; 83 500–88 400: 0,375 %; 88 400–93 330: 0,350 %; 93 330–98 240: 0,325 %; **≥ 98 240 SOL: 0,050/0,050/0,200 = 0,300 %** (criador/protocolo/LP; a partir da 2.ª faixa protocolo 0,05 % e LP 0,20 % fixos, só o criador decresce) |
| PumpSwap, pool canônico, quote USDC | mesma escada em USDC: 0–59 000 USDC 1,250 %; 59 000–300 000 1,200 %; … ; ≥ 20 000 000 USDC 0,300 % (tabela completa em `notes-T4.0c.md` §5) |
| PumpSwap, pools **não canônicos** | criador 0 % + protocolo 0,05 % + LP 0,25 % = 0,30 % |
| **Aluguel da ATA do memecoin** (R43/T4.46, não documentado pela página) | **1 513 840 lamports** por moeda comprada — Token-2022, 170 bytes com `immutableOwner`, `createIdempotent` na própria compra; classic SPL seria 2 039 280 (165 bytes). Recuperável: T4.46 fecha a ATA (`CloseAccount`) quando a venda esvazia o saldo — **só com `MEME_CLOSE_ATA_ON_FULL_SELL=1` no `.env` da VPS** (desligado por padrão; decisão do Everton). |
| **Aluguel do `user_volume_accumulator`** (R43, não documentado) | **1 346 200 lamports**, **uma vez por carteira** (PDA `["user_volume_accumulator", wallet]`), pago na primeira compra. Não recuperável sem derrubar o cashback (`close_user_volume_accumulator`, `docs/PUMPFUN-ONCHAIN.md`). |

Notas da página: creator fee vale para coins presentes na curva/PumpSwap desde 13/05/2025; USDC
como quote desde 21/05/2026; app móvel pode cobrar até +0,1 %; "The pump.fun platform may change
these fees at any time, without notice." O `fee_basis_points: 95` de `/global-params` bate com o
0,95 % de protocolo na curva. O aluguel das duas linhas acima **não é taxa do programa** — é rent
do runtime da Solana, cobrado pela criação das contas, e a compra paga do próprio bolso do
comprador junto com a curva (`sol_spent_lamports` inclui os dois; `wallet_fills`/`FillRecord`
rotulam `ata_rent_lamports`/`account_rent_lamports` separado, T4.46).

### 4.2 Ciclo de vida como a pump.fun descreve (docs, 12/09/2026)

1. **Criar** (`/docs/create-coin`, sem "Last Updated" visível): "Anyone can launch a coin in under
   a minute. There's no liquidity to seed, no presale, and no team allocation. Coins are immediately
   tradable on a transparent bonding curve, and graduate to PumpSwap once they reach the market-cap
   threshold." Nome/símbolo/imagem são imutáveis (metadata SPL). Quote pode ser SOL ou USDC (fees
   doc); a listagem mostra também outros `quote_mint` (§4.3).
2. **Curva** (`/docs/bonding-curve`): "constant-product AMM … Two virtual reserves (SOL and the coin's
   supply)"; "Every buy moves the price up. Every sell moves the price down."; "There is no orderbook,
   no market-makers, and no off-chain matching." Parâmetros iniciais **observados** em
   `/global-params/1789184732000` (registro de 18/07/2025, slot 354155511):
   `initial_virtual_token_reserves = 1 073 000 000 000 000`, `initial_virtual_sol_reserves = 30 000 000 000`
   (30 SOL), `initial_virtual_quote_reserves = 4 292 000 000` (4 292 USDC, curvas em USDC),
   `initial_real_token_reserves = 793 100 000 000 000`, `token_total_supply = 1 000 000 000 000 000`.
   Progresso da curva = `1 − real_token_reserves / initial_real_token_reserves`.
3. **Completar** (`complete = true` e `real_token_reserves = 0`): pela matemática dos parâmetros,
   vender os 793,1 M tokens leva a reserva virtual de SOL de 30 para 30·1073/279,9 ≈ **115,0 SOL**,
   ou seja ~**85 SOL reais** captados — **derivado dos parâmetros, não documentado**; coincide com o
   observado (p99 de `real_sol_reserves` = 85,005 SOL na amostra; a coin completa "WOTF" tinha
   `virtual_sol_reserves = 115 005 359 057`). A doc só diz "hits the graduation threshold".
4. **Migrar → PumpSwap**: "the curve is closed and the entire liquidity pool is migrated atomically to
   PumpSwap … Graduation is automatic and irreversible. There's no human step." Custa 0,015 SOL
   (fees). O `Coin` ganha `pool_address`/`pump_swap_pool`; trades passam a vir com `program`
   `pump_amm`/`raydium_*` no `swap-api`. Completar e migrar são instruções distintas (T4 §3).
5. **King of the hill**: **não existe mais na superfície pública** — rota 404 e campo ausente
   (§1.1 #22, §1.3). Só resta o board `movers`/`graduating` do indexer como "destaque".
6. **Mayhem Mode** (`/docs/mayhem-mode`, "Last Updated 12 November 2025", ver A4.1b): estados
   `active/paused/completed` (+ `enabled` visto na listagem), modo `auto/manual`, `pause_reason`.

#### 4.2.1 O que graduar quer dizer para nós (T4.2d, 12/09/2026)

O `complete = true` da REST **não é graduação**: no run 5 do plantão (05:51 BRT), das 140 moedas
"completas" 77 tinham `real_sol_reserves = 0` (47 Mayhem, mcap mediano US$ 9,57) e 72 não estavam no
board `graduated`; das 68 que estavam, 31 também mostravam reserva zero, porque a curva migrada esvazia
para a pool. A fixture real `frontend_api_v3_coin_graduated_raw.json` é exatamente isso: `complete: true`,
`real_sol_reserves: 0`, `real_token_reserves: 0`, `pump_swap_pool` preenchido. O radar guarda **quatro
sinais separados** em `meme_tokens` (`docs/DATABASE.md` §36) e só o mais antigo deles vira
`completed_at`, com uma exceção declarada — o `complete` da REST com reserva zero não conta sozinho:

| sinal | de onde | rótulo na tela |
|---|---|---|
| `rest_complete_seen_at` | 1.ª fotografia REST/RPC com `complete = true` | "REST diz completa" |
| `curve_filled_seen_at` | 1.ª fotografia com `real_sol_reserves ≥ 85,005 SOL` — o limiar é `buy_cost` dos `initial_real_token_reserves` numa curva virgem, com os parâmetros de `/global-params/{criação}` e o arredondamento do programa (`floor(a·vsol/(vtok−a)) + 1`), nunca uma constante | "curva cheia (≥ 85 SOL)" |
| `graduated_board_seen_at` | 1.ª presença no board `graduated` do indexer | "no board graduated" |
| `pool_created_at` (+ fonte) | o `gd` do indexer (board ou `/in-memory-coin`) ou o `migrate` do PumpPortal, o que chegar primeiro | "pool criada" |

A matriz de concordância dos quatro por dia de Brasília (`meme_graduation_matrix_v1`) é o painel do
diagnóstico M-D1/M-D2: quantos mints têm 1/2/3/4 sinais, quais pares discordam, quantos são "só REST".

**Denominador do progresso.** `1 − real_token_reserves / initial_real_token_reserves` precisa do
inicial. Até a T4.2d ele só era escrito de uma fotografia virgem (`real_sol_reserves = 0`), e um mint
descoberto depois da primeira compra nunca ganhava denominador (117/123 linhas do portão do Lab em
`progress_unknown` às 06:04 BRT). Agora uma curva **padrão** vista no meio da vida toma o
`initial_real_token_reserves` do registro de `/global-params/{criação}` (`progress_denominator_source =
global_params`); a fotografia virgem continua valendo mais (`observed_virgin`). **Mayhem é tratado à
parte e nunca toma o registro**: o agente cunha 1 bilhão de tokens extra e `set_mayhem_virtual_params`
move as reservas — a fixture `2sduGq…` (Mayhem pausada, `frontend_api_v3_coin_by_mint_response_raw.json`)
tem 822,6 M tokens reais na curva, mais que os 793,1 M do registro, e 1 102,5 M virtuais com 3,08 SOL
virtuais. Nem a conta `Global` (25 campos, T4.0d) nem `/global-params` trazem um parâmetro de reserva
Mayhem; o campo certo vive na conta `mayhem_state`. **T4.2e decodificou essa conta** (`MayhemState`,
`docs/PUMPFUN-ONCHAIN.md` §3.5): a reserva inicial de uma curva Mayhem **é a do registro**; os 822,6 M
são `793 100 000 + 29 544 036,902123` de tokens que o **agente** vendeu líquido para a curva, do bilhão
cunhado só para ele (supply do mint 2 B contra `token_total_supply` 1 B da curva). O worker lê, uma vez
por minuto e 25 mints por chamada RPC, as quatro contas de cada Mayhem rastreada sem denominador, fecha
a identidade `cofre + líquido = supply − supply_da_curva` e só então escreve o inicial do registro com
`progress_denominator_source = mayhem_state` (`0025`). Uma fotografia REST de Mayhem sozinha não
reivindica nada (nem `observed_virgin`: a fixture estava a 1 lamport com 29,5 M do agente dentro).
O progresso pode ficar **negativo** (o site trunca em 0; nós guardamos) e `curve_filled_seen_at` não é
reivindicado para Mayhem (o agente move o SOL virtual).

**Cegueira declarada.** A descoberta ouve só o programa `pump` (`subscribeNewToken` + boards com
`pg = pump`); 8/50 do board `new` às 05:51 BRT eram `raydium_launchpad` (StonkFun). O worker conta por
hora as entradas do board `new` fora do programa e expõe a fração em `GET /meme/sources`
(`discovery_blind_share_1h`) e no heartbeat (`blind_share_1h`) — mede a cegueira, não a corrige; rastrear
outros launchpads é decisão do Everton.

### 4.3 Estatísticas ao vivo (10 requisições a `/coins?sort=created_timestamp&order=DESC`, 02:32–02:37 BRT)

Amostra: 700 linhas → **653 mints únicos**, criados entre **01:52 e 02:32 BRT** (janela de 40,6 min;
**16,1 coins/min ≈ 23 mil/dia** se extrapolado — é uma madrugada de sexta, não uma média). Não é
"últimas 24 h": com cap de 70/página e 10 chamadas, 24 h (~23–40 mil coins) estão fora do orçamento.

| Métrica | Valor observado |
|---|---|
| `complete = true` (graduou em < 45 min de vida) | **34 / 653 = 5,2 %** — quase todas com `boost_mode`/bundling; não é a taxa de graduação de 24 h |
| `mayhem_state` | ausente 391 (59,9 %), `paused` 201 (30,8 %), `completed` 47 (7,2 %), `active` 11 (1,7 %), `enabled` 3 |
| `boost_mode` | NONE 627, COMPLETED 21, IN_PROGRESS 5 |
| `quote_mint` | SOL (`1111…`) 579 (88,7 %), USDC 17, `null` 10, outros tokens 47 |
| teve alguma compra (`real_sol_reserves > 0`) | 587 (89,9 %); `last_trade_timestamp` presente em 603 |
| `real_sol_reserves` (SOL) | mediana 0,000; p75 0,01; p90 0,25; **p99 85,0**; máx 205,5 |
| progresso da curva (SOL-quoted, n = 579) | mediana 0 %; p90 12,8 %; máx 100 % |
| `usd_market_cap` | mín 1; p10 212; p25 1 404; **mediana 2 841**; p75 2 966; p90 4 822; p99 7,09 M; máx 718 M (valor não validado — coin com < 45 min) |
| faixas de `usd_market_cap` | < 4 k: **551 (84,4 %)**; 4–5 k: 44; 5–7 k: 24; 7–10 k: 9; 10–20 k: 5; 20–50 k: 1; ≥ 50 k: 19 |
| `is_currently_live` / `nsfw` / `is_banned` / `verified` | 1 / 16 / 0 / 0 |
| criadores únicos | 252 (o mais ativo criou 35 coins em 40 min); 40 descrições "Deployed using j7tracker" |
| sociais | website 162, twitter 248, telegram 12 |

Listagem `complete=true` (70 graduadas mais novas por criação): todas criadas há < 1,66 h, **44 na
última hora** (limite inferior de graduações/hora naquele instante), todas com `pool_address`;
`usd_market_cap` das graduadas: mín 0, mediana 2 522, máx 715 M — muitas graduam e despejam.
`/mayhem/overview` (A4.1b): 10 705 coins Mayhem em 24 h (8 614 auto, 2 091 manual). Topo por
`sort=market_cap`: 925 M, 720 M, 469 M, 393 M, 346 M USD, todas `complete`.

## 5. O que NÃO é público (e o que exigiria on-chain ou provedor com chave)

| Necessidade | Situação medida | Alternativa |
|---|---|---|
| Holders por coin | **Parcial**: top 50 por quantidade + `totalHolders` (`/coins/top-holders`; ver §10: `top-holders-v2`, `holder-stats`), `holderCount`, `top10HoldersPercent`/`devHoldingsPercent`/`bundlerOwnedPercentageV2` (indexer, sem definição). Lista completa e PnL por holder (`profile-api POST /pnl/coin/{mint}/holders`) não testados/rota de sessão | RPC `getTokenLargestAccounts` (20) / `getProgramAccounts` por mint, ou Helius DAS / Bitquery (chave) |
| Histórico de trades | Paginado por cursor de 100 (`swap-api`), `first-trade` de abril/2025 existe → profundidade parece completa, mas **sem garantia de retenção documentada**; sem filtro por intervalo de tempo além de `createdTs`/cursor | Backfill próprio por `getSignaturesForAddress` da bonding curve + decodificação com a IDL |
| Candles | 12 intervalos, ≤ 1 000 por chamada, **só os N mais recentes** (nenhum parâmetro `to/before` no bundle); 1 m × 1 000 cobriu 45 h numa coin antiga (esparso), 1 h × 1 000 cobriu julho→setembro; retenção real desconhecida | Reconstruir de trades ou provedor OHLCV (Bitquery até 1 s) |
| Trades em tempo real por coin (Solana) | **Não há WS público** do site: `trenches` é agregado por board; NATS exige auth (e é EVM); socket.io é chat | PumpPortal `subscribeTokenTrade` (0,01 SOL/10 k eventos, chave + ≥ 0,02 SOL) ou Geyser/`logsSubscribe` próprio |
| King of the hill | rota e campo removidos em v3 | não há |
| Critério numérico de graduação | não publicado; ~85 SOL derivado de `/global-params` + observado | ler `BondingCurve` on-chain (`complete`, `real_token_reserves`) |
| Trades do agente Mayhem separados dos orgânicos | só `mayhem-stats` agregado | decodificar por operação/CPI (A4.1b §5.2) |
| Comportamento acima do rate limit (429/ban) | não testado de propósito | — |
| ETag/304 (lista comunitária) | não medido | — |
| Chat/livestream | socket.io com token; não é on-chain | não relevante |

## 6. Leitura para o radar e para a execução

- **Radar (push, sem chave):** (1) `wss://advanced-indexer.pump.fun/ws/trenches` nos boards `new`,
  `graduating`, `graduated`, `movers` (snapshot + deltas a cada segundo, com holders, top-10 %, dev %,
  snipers, sociais, fees); (2) `POST swap-api /v1/coins/market-activity/batch` + `GET /v2/coins/{mint}/trades`
  (1000/min, buys/sells/usuários por janela e fita de trades com cursor); (3) `GET advanced-indexer
  /in-memory-coin/{mint}` + `frontend-api-v3 /coins/top-holders/{mint}` e `/user-positions/{creator}?mints=`
  para as features de rug (`creator_sold` sai de `trades/batch` por carteira). `frontend-api-v3 /coins`
  continua sendo a descoberta lenta (60/min, 70/página) — PumpPortal `subscribeNewToken` (grátis,
  6 eventos em 30 s) é a descoberta rápida.
- **Execução:** (1) cotar localmente com `/global-params/{ts}` + estado da curva (RPC próprio) e montar
  `buy`/`sell` com a IDL oficial — sem taxa de terceiro; (2) `POST blockchain-swap.pump.fun/transactions/swap-build`
  como construtor de referência (mesmo caminho do site, sem taxa adicional declarada, não documentado);
  (3) PumpPortal `trade-local` só como fallback consciente de +0,5 % e de transação montada por terceiro.
  Em qualquer caminho: simular antes de assinar, nunca a Lightning API.
- **Maior lacuna:** ausência de feed público por trade em tempo real para Solana — a fita ao vivo custa
  (PumpPortal por evento) ou exige Geyser/RPC próprio; e o sinal "king of the hill" deixou de existir.

## 7. Comparação com `EXCHANGE_INTEGRATION.md`

Nada aqui é orderbook: não há bid/ask, `depth`, `bookTicker`. O equivalente de `NormalizedTrade`
é o trade do `swap-api` (`tx`, `slotIndexId`, `type`, `priceSol/priceUsd`, `baseAmount/quoteAmount`,
`userAddress`); o de `NormalizedCandle` são os candles USD do `swap-api` (esparsos, strings decimais);
o de `NormalizedTicker` é `market-activity` (janelas 5m/1h/6h/24h). `ts` = `timestamp` do bloco;
`received_at` = hora local. Fixtures gravadas desta sessão (formas e respostas redigidas) estão em
`.claude/state/notes-T4.0c.md` para os testes offline de um futuro adapter.

## 8. PumpSwap (venda pós-migração) — T4.29a, 2026-09-16

**Escopo: só `sell`.** Este projeto nunca compra na PumpSwap (`docs/RISK_ENGINE_MEME.md` §1) — o
pacote `hunter_exchanges/pumpswap/` existe inteiramente para dar à posição que migrou uma porta de
saída real, no lugar da recusa nomeada `pumpswap_sell_not_implemented` que existia até esta tarefa.

### 8.1 Fonte da IDL, em ordem de atualidade

1. **A conta de IDL Anchor do próprio programa on-chain** — `getAccountInfo` em
   `5fLnXNNoZcZt9Qku6HARM3un3Ttm2cGsR7gN9Zp1R7h3` (derivada por
   `createWithSeed(find_program_address([], pAMMBay...), "anchor:idl", pAMMBay...)`, a mesma receita
   que T4.2e usou para o Mayhem), lida ao vivo em 16/09/2026 no slot 447585704, descomprimida
   (discriminador de 8 bytes + autoridade de 32 + comprimento u32 + corpo zlib — formato padrão de
   conta de IDL do Anchor) e salva em `tests/fixtures/pumpswap/t429a_idl_pump_amm_onchain.json`,
   **sha256 `e16ac8008908911575241a25cad33bed8d2da2153f0d726790065fd467b90ff4`**.
2. **`pump-fun/pump-public-docs` no GitHub, `idl/pump_amm.json`**, commit `main` no momento da leitura
   (`81091419e4457566469d4e2a27f64ed84d42419c`, 16/09/2026), sha256
   `2091433899b07d003d98118ae6cd3c628960fd393b40710b6e15bce6d0e7f2d1` — **está à frente** da conta
   on-chain (tem `boost_authority`/`boost_enabled` em `GlobalConfig`,
   `creator_fee_configurable`/`max_configurable_creator_fee_bps`, e em `Pool` tem
   `virtual_quote_reserves`/`creator_fee_bps`/`can_edit_creator_fee`/`is_holder_reward`), o mesmo
   padrão de "IDL do GitHub correu na frente da conta on-chain" que T4.8/T4.8c já achou para o
   programa Pump. O adaptador decodifica pela **conta on-chain** (é o que as transações reais checam
   hoje), com o mesmo mecanismo de layout curto/estendido de `hunter_exchanges.pumpfun.decode` para
   `BondingCurve`.

Também consultado, sem chave, sem alterar a cadeia: o repositório da versão mais antiga
`9c82f61cb711b044a17f770ab8ce9f9bdf78f333` (sha256 `6b5c7ec4e5ef9742fa99dc57b0d75b1031b379bba02a7e1b3c5a4cad68d77e56`)
para confirmar que o `GlobalConfig`/`Pool`/`sell` já existiam nesse formato antes.

### 8.2 Descoberta do pool sem RPC, verificada contra 3 mints migrados reais

O pool canônico de um mint migrado é derivado, nunca precisa de uma leitura extra para "achá-lo":
`pool_authority = PDA(["pool-authority", mint], PUMP_PROGRAM_ID)` (semente lida da própria IDL do
programa Pump, instrução `migrate`/`migrate_v2`, `pool_authority`); `pool = PDA(["pool", u16_le(0),
pool_authority, mint, WSOL_MINT], PUMPSWAP_PROGRAM_ID)` — índice `0` porque a migração sempre cria o
pool canônico. Verificado ao vivo, 16/09/2026, contra 3 mints migrados recentes obtidos de
`frontend-api-v3.pump.fun /coins?complete=true` (fonte pública, sem chave):

| mint | pool derivado | `pool_address` da REST | bate |
|---|---|---|---|
| `9tiUg9bDHpEgE3rQU8kmdMJMvMfwM81ph6WuyTapump` | `2KJ15ekBMtR2FW2esGeJrptrYLx6V9v5KEeuD8imKEz6` | idem | sim |
| `DHcQCSZ2U8QTjNWWwyuqfJbBTLCZyvtFkSeYhEYGpump` (Mayhem) | `8EpQ5ihpebcsns3DdEDoiu1WXu4GJZY9o9kSjbXAgArE` | idem | sim |
| `5RFwNs16ShCeSNQY9Kf5iR5esbEMsnYm7PbWGQAwpump` | `F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ` | idem (também a fixture `frontend_api_v3_coin_graduated_raw.json` do pacote `pumpfun`) | sim |

As 3 contas `Pool` lidas (`tests/fixtures/pumpswap/t429a_rpc_pools_raw.json`, slot 447585957) têm
**301 bytes** cada — os 245 bytes que a IDL on-chain declara mais os 26 bytes dos 4 campos que só o
IDL do GitHub `main` já nomeia (`virtual_quote_reserves` i128 + `creator_fee_bps` u64 +
`can_edit_creator_fee`/`is_holder_reward` bool), mais 30 bytes reservados/não interpretados —
`decode.py` lê os dois layouts sem adivinhar.

**Correção a `docs/PUMPFUN-ONCHAIN.md` §2.2:** essa seção, lendo um exemplo estático, dizia "hoje
`virtual_quote_reserves=0` em todo pool". Duas das três contas lidas ao vivo nesta tarefa têm
`virtual_quote_reserves` **não-zero** (17 584 505 289 e 17 584 505 291 lamports; só o pool Mayhem das
três leu 0) — o campo não é adormecido, e `quote.py` nunca assume que é zero
(`effective_quote_reserves = pool_quote_token_account.amount + Pool.virtual_quote_reserves`).

**Achado extra, não previsto no brief:** o lado *base* de pelo menos um pool real
(`F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ`) é um mint **Token-2022**, não o programa de token
clássico — `pumpswap_exit.py` lê o dono real da conta do mint a cada venda em vez de presumir o
token clássico.

### 8.3 Fórmula da cotação de venda

Produto constante, no mesmo molde da bonding curve (`hunter_exchanges.pumpfun.quote.sell_proceeds`):

```
efetivo_quote = pool_quote_token_account.amount + Pool.virtual_quote_reserves
bruto = floor(base_amount_in × efetivo_quote / (pool_base_token_account.amount + base_amount_in))
taxa_lp = ceil(bruto × lp_fee_bps / 10_000)
taxa_protocolo = ceil(bruto × protocol_fee_bps / 10_000)
taxa_criador = ceil(bruto × coin_creator_fee_bps / 10_000)
líquido = bruto − taxa_lp − taxa_protocolo − taxa_criador
```

As três taxas em basis points vêm de `GlobalConfig` (`lp_fee_basis_points`,
`protocol_fee_basis_points`, `coin_creator_fee_basis_points`), **lidas ao vivo a cada venda, nunca uma
constante** — no pool `F5Mk…`, 20 + 5 + 5 = 30 bps. **Não confirmado contra um fill real da PumpSwap**
(nenhuma carteira com posição migrada nesta tarefa): a forma do produto constante é a documentada
(`PUMP_SWAP_README.md`), mas o arredondamento exato do programa não foi verificado byte a byte como
foi feito para a bonding curve em T4.8 (duas transações reais). Exemplo por extenso, com os números
do pool `F5Mk…` no slot 447586178, em `hunter_exchanges/pumpswap/quote.py`.

### 8.4 A instrução `sell` e o unwrap de WSOL

21 contas na ordem exata da IDL, discriminador `33e685a4017f83ad` — **idêntico** ao `sell` legado da
bonding curve (discriminadores Anchor são `sha256("global:<nome>")[:8]`, então dois programas com uma
instrução de mesmo nome colidem; só o `program_id` da instrução diferencia, o mesmo achado que
`docs/PUMPFUN-ONCHAIN.md` §2.3 já tinha para o `buy`). Args: `base_amount_in: u64,
min_quote_amount_out: u64`. **O lado quote de todo pool é SOL empacotado (WSOL), nunca SOL nativo**:
a venda credita a ATA de WSOL do usuário, então o executor sempre acrescenta `CreateIdempotent` (se a
ATA não existir) antes e `CloseAccount` (o "unwrap") depois — o padrão oficial `@solana/spl-token` de
embrulhar/desembrulhar, nunca deixando WSOL parado na carteira.

### 8.5 O que o executor mudou

`services/meme-executor/hunter_meme_executor/pumpswap_exit.py` (novo): uma posição `migrated` é lida
pelo `ChainReader.pool()` (novo em `chain.py`); sem pool, `pumpswap_pool_not_found` (recusa nomeada,
nunca um retry silencioso); com pool, `pumpswap_build.build_pumpswap_sell` monta e
`verify_pumpswap_sell_message` verifica byte a byte (mesma disciplina §9.1 do `verify.py` da curva),
`simulateTransaction` sempre antes de assinar, o mesmo `MemeSubmitter`/journal/idempotência/kill
switch do caminho da curva. A confirmação de um fill tenta decodificar um `SellEvent` real
(`hunter_exchanges/pumpswap/sell_event.py`, disciplina idêntica a `trade_event.py`) e, quando não há
um para decodificar, usa o delta de saldo SOL do pagador (que já reflete o unwrap) — nunca um número
inventado.

### 8.6 O que está provado e o que não está

**Provado, offline, com dados reais:** decodificação de `GlobalConfig` e `Pool` contra 3 pools reais
lidos ao vivo; derivação do pool canônico sem RPC extra, verificada contra os mesmos 3 mints;
montagem da instrução `sell` com contas na ordem da IDL; round-trip completo
construir→serializar→verificar da mensagem (incluindo o unwrap de WSOL); todas as PDAs auxiliares
(`event_authority`, `fee_config` — a entrada própria da PumpSwap no programa Pump Fees, confirmada
viva —, `coin_creator_vault_*`) verificadas contra endereços reais.

**Não provado:** nenhuma venda foi simulada na mainnet (`simulateTransaction`) nem enviada — esta
tarefa não tem uma carteira com uma posição migrada de verdade para simular contra (ao contrário de
T4.8/T4.8b/T4.8c, que sempre acharam uma carteira real na cadeia para impersonar via
`sigVerify=false`; a tentativa aqui esbarrou no rate limit de `getTokenLargestAccounts` — o mesmo
que T4.8b/T4.8c já documentaram — e o comprador achado via `getSignaturesForAddress` do pool não
tinha saldo do token no momento da leitura). O que o dono deve rodar na VPS para fechar essa lacuna,
com RPC próprio e a carteira real: um script `--simulate-only` (no mesmo molde de
`.claude/state/tmp/t48c_simulate.py`) que: lê uma posição `migrated` real da tabela
`meme_live_positions`, chama `ChainReader.pool(mint)`, monta a venda com `pumpswap_build
.build_pumpswap_sell` e chama `rpc.simulate_transaction(..., sig_verify=False)` — sem nunca chamar
`send_transaction`. Também não confirmados: o arredondamento exato do produto constante contra um
fill real, e o layout do `SellEvent` (inferido da IDL, nunca decodificado de uma transação real).

## 9. A conta da curva em moedas Mayhem — R36, 2026-09-16

`meme_tokens.bonding_curve` **não é confiável em moeda Mayhem**: 13 615 das 112 108 linhas de 7 dias
que têm o campo gravam o *mesmo* endereço, `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`, em 13 615
mints distintos (todas `mayhem_enabled`) — é o PDA `["sol-vault"]` do programa Mayhem
(`mayhem_state.mayhem_pdas`), na mainnet dono System Program e zero byte de dado, não a curva de
ninguém. A curva real é o PDA por mint (`3aYHwMeo…` → `Ck72XTyT…`, dono `6EF8rrec…`,
`is_mayhem_mode=true`), que é o que o executor deriva e usa tanto na leitura (`ChainReader.curve`)
quanto nas contas de `buy`/`sell` — portanto o executor lê e compra na conta certa. **Nunca** trocar
essa derivação por "usar `meme_tokens.bonding_curve` quando existir" (pinado em
`services/meme-executor/tests/test_mayhem_curve_account.py`); quem precisa do campo — o
`reconcile_once` do radar — deve validar dono/discriminador ou derivar o PDA.

### 9.1 Feito — o radar também deriva agora, e os 13 615 já foram (T4.39, `0047_meme_bonding_curve_raw`)

A recomendação da §9 acima ("`reconcile_once` deve validar dono/discriminador ou derivar o PDA") virou
código: `hunter_exchanges.pumpfun.normalize.parse_new_token` deriva `bonding_curve_address(mint)`
(`pumpfun/pdas.py`, extraído de `tx.py`) e grava **sempre** o PDA derivado em `bonding_curve` — nunca
mais o `bondingCurveKey` cru do frame. Quando o frame discordava do PDA (as moedas Mayhem contaminadas
com o sol-vault, e só elas: R36 mediu 0/100 divergências fora de Mayhem), o valor original sobrevive em
`bonding_curve_raw` (coluna nova, `0047`) — auditoria, nunca lido para derivar endereço nenhum — e
`discovery._handle` conta (`hunter_meme_token_bonding_curve_replaced_total{mayhem_enabled}`) e loga
(`meme_token_bonding_curve_replaced`) a substituição no instante em que ela vira linha durável.
`hunter_meme_worker.collect.reconcile_once` parou de ler `tracked.bonding_curve` — deriva o PDA do mint
a cada tique, o mesmo que o executor já fazia — então o efeito colateral que a §9 media (RPC gasto lendo
o sol-vault e falhando fechado para 13 615 mints) parou na origem, não só na leitura.

Os 13 615 já gravados foram reparados por `infra/scripts/meme_repair_bonding_curve.py` — auditado,
*dry-run* por padrão, candidato é toda linha cujo `bonding_curve` discorda do PDA derivado do próprio
mint (nunca o endereço fixo do sol-vault), `--apply` exige `--reason` e deixa uma linha em
`system_events` com a contagem por `mayhem_enabled`. Ver `docs/DATABASE.md` §55 para o esquema, o
gatilho de escrita única estendido e o downgrade recusado enquanto alguma linha carregar um valor em
`bonding_curve_raw`.

## 10. Releitura de 06/10/2026

**Status:** releitura da superfície pública depois do upgrade dos programas de 02/10 (pedido do Everton: "leia o
pump.fun por inteiro"). Medido entre **02:22 e 02:56 UTC de 06/10/2026** (23:22–23:56 BRT de 05/10), no mesmo método
da T4.0c e com a mesma disciplina: sem login, sem cookie, sem chave, `GET` anônimo (mais três `POST` de leitura: dois do
lote da §2 #4 e um de PnL de holders, §10.3), ≥ 1 s entre chamadas, nenhum desafio contornado, nenhum cabeçalho
falsificado. Notas cruas, o log de todas as chamadas e as formas completas:
`.claude/state/notes-pumpfun-releitura-2026-10-06.md`. Síntese e leitura para o H-030:
[[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]]; revisão da Astra:
[[06-DECISIONS/Revisoes-Astra/pumpfun-releitura|pumpfun-releitura]].

**Quatro tipos de evidência, nunca misturados nesta seção.** **HTTP** = chamei e li a resposta. **Bundle** = o registro tipado
de rotas do site diz (não é uma chamada). **REA** = o navegador chamou (não prova que um cliente sem navegador receba a
mesma resposta). **Não testado** = nada disso.

**Dois métodos, créditos separados.**
1. **Leitura do bundle + chamadas `curl`/`websockets`** (este agente): **53 chamadas de API** (`frontend-api-v3` 44, `profile-api` 4,
   `swap-api` 3, `advanced-indexer` 2), 6 páginas HTML e 5 conexões WS de leitura = **64 unidades**, acima do "~60" pedido: 61 até a
   segunda captura do REA (a 61.ª leu a forma de `POST /pnl/coin/{mint}/holders` a pedido do orquestrador) e 3 a mais para
   desfazer uma afirmação "sumiu" que a revisão da Astra apontou (`GET /coins/{mint}`, §10.2); além de 101 chunks JS estáticos, fora da conta.
   Códigos das 53: 200 × 44, 201 × 3, 400 × 1, 401 × 3, 404 × 2. **Nenhum 429, nenhum 403, nenhum desafio Cloudflare.** Limite do método:
   só li os chunks que a home lista; chunks de rota carregados depois (`/leaderboard`, screener) ficaram de fora.
2. **Observação passiva via REA** (Chrome headless sem login, duas capturas: home + `/leaderboard` — 744 requisições, 4 WebSockets — e
   `/coin/{mint}`, feitas pelo orquestrador; `.claude/state/rea-pumpfun-capture-2026-10-06.md`). Não guarda corpos. Itens só dele levam "(REA)".

### 10.1 O que mudou desde 12/09, em uma página

- **O mapa tem um contrato escrito agora (bundle).** Um chunk do site (`02i6ywd4i-qb4.js`) traz o registro tipado de **312 rotas** do BFF
  (178 GET, 102 POST, 21 DELETE, 6 PATCH, 5 PUT) com `summary`, `query` e `response` (zod), inclusive os tetos de `limit`. Em 12/09 só
  tínhamos literais de URL. "Ausente do mapa de 12/09" abaixo quer dizer isso, **não** que a rota tenha nascido depois: não sei desde quando existe.
- **`GET /coins/{mint}` saiu do ar (HTTP).** Respondeu **404 "Cannot GET"** em dois mints (a §1.1 #2 dava 200 em 12/09). `GET /coins-v3/{mint}` responde 200 (RL 60).
  Confirma o que o código já registra ("a rota por mint que dá 404 desde ~25/09", T4.97b/R80, `services/meme-worker/hunter_meme_worker/collect.py`); `PumpFunRestClient.get_curve_state` ainda aponta para ela.
- **O quadro de PnL tem `sort` e tetos medidos (HTTP + bundle).** `sort ∈ {realized, unrealized, combined}`; `limit` teto 100 e `offset` sem efeito. Há rotas públicas por carteira que o mapa
  de 12/09 não tinha (`/user-trades/{wallet}`, `/users/{id}/overview`, `/pnl-leaderboard/top-trader-trades/{mint}`, profile-api `/v4/pnl/*`) e rotas que ele só listava no bundle e que agora foram **chamadas**
  (`/following/v3/*/count`, `/mint-positions/{mint}`, `/pnl-leaderboard/positions`, `POST profile-api /pnl/coin/{mint}/holders`). Detalhe em 10.3.
- **`Coin`: cinco campos antes não registrados foram observados** em 70 itens de `/coins` (`updated_at`, `is_holder_reward`, `transfer_fee_bps`, `transfer_hook_program`, `depth`) e `chain_id` veio em CAIP-2
  (`solana:5eykt4…`). Seis chaves de 12/09 não apareceram nesta amostra (a referência antiga mistura quatro rotas): **não é um diff completo de schema**. O teto de 70 por página continua.
  `is_holder_reward` casa com o `Pool.is_holder_reward` que o IDL do GitHub já mostrava (§8.1) e com a aba "Holder rewards" do site; ligar isso ao upgrade de 02/10 é **coincidência de data**, não prova.
- **Em tempo real (HTTP + REA).** Os handshakes anônimos de `prod-v2.nats.realtime.pump.fun` (NATS 2.12.15, `max_payload` 8 192), `unified-prod.nats.realtime.pump.fun` (visto pelo REA; NATS 2.12.11, 524 288)
  e `multichain-prod.nats.realtime.pump.fun` (igual a 12/09) exigem `auth` (`auth_required: true`, 3 de 3 medidos). O bundle descreve `POST /nats/token` ("JWT de usuário por 1 h", dependente de sessão, atrás de uma
  flag escura); **não o chamei** e ele não é fonte para nós. O `wss://advanced-indexer.pump.fun/ws/trenches` **ainda responde anônimo** (15 s: 1 snapshot + 26 deltas); a entrada tem as chaves `hr` e `lp` a mais.
  O REA não viu o trenches nas páginas que abriu (o screener não foi aberto); isso não prova que ele saiu.
- **Taxas: as páginas conferem.** `/docs/fees` ainda diz **"Last Updated: 20 May 2026"** e a escada SOL/USDC confere linha a linha com a §4.1; PumpPortal `/fees/` também. As taxas **on-chain** de hoje não foram relidas aqui.
- **Login da web (documentação do site):** a entrada por carteira de navegador foi aposentada em **25/09/2026 15:00 UTC** (e-mail, Google, Apple, GitHub via Privy). Endereço, posições, callouts e seguidores permanecem. Irrelevante para nós (não fazemos login).
- **`/mayhem/overview`** tem `agentVolumeUsd`, `distinctTraders` e o modo `party` (355 moedas em 24 h) a mais; `coinsCreated` 24 h = 10 226 (12/09: 10 705; é conteúdo, não interface).

### 10.2 Tabela de diferenças

Colunas: **estado** (mudou / igual / ausente do mapa de 12/09 / no mapa só como bundle / saiu do ar / bloqueada / não testada), **evidência** (HTTP, bundle, REA), código e limite (`x-ratelimit-limit`, janela 60 s) quando houve chamada.

| Estado | Rota | Evidência e código | RL | Nota |
|---|---|---|---|---|
| **saiu do ar** | `GET /coins/{mint}` (§1.1 #2) | HTTP **404** "Cannot GET" (2 mints) | — | substituta: `GET /coins-v3/{mint}` HTTP 200, RL 60; confirma R80 |
| **mudou (campos novos observados)** | `GET /coins?limit=100` | HTTP 200, **70** itens | 60 | + `updated_at, is_holder_reward, transfer_fee_bps, transfer_hook_program, depth`; `chain_id` CAIP-2 |
| **mudou** | `GET /pnl-leaderboard` | HTTP 200 | 60 | `sort` (valores caracterizados), `limit` ≤ 100, `offset` sem efeito; 3 períodos |
| **mudou** | `GET /users/{address}` | HTTP 200 | 30 | + `is_banned, header_image_url, avatar_decoration, last_username_update_timestamp, canonical_evm_wallet`; ainda público |
| **mudou** | `GET /user-positions/{wallet}?mints=` | HTTP 200 | 600 | + `openedAt`, `tradeCount`; `callout{…}` quando a carteira publicou um |
| **mudou** | `advanced-indexer /in-memory-coin/{mint}` | HTTP 200, **67** campos (65) | — | + `isHolderReward`, `isMultiplayer`, `mayhemBotCoinSupplied`, `builderTip*`, `tradingAppFee*`, `txFeeSolV2` (a lista de 12/09 era parcial) |
| **mudou** | `wss://…/ws/trenches` | HTTP/WS responde anônimo | — | entrada com `hr`, `lp` a mais |
| **igual (forma)** | `GET /mayhem/overview`, `GET /mayhem/top-traders?window=24h\|7d`, `GET /sol-price` | HTTP 200 | 60 / 60 / 50 | `overview` ganhou 3 campos; o #1 de 24 h em `top-traders` tem PnL = volume e 5 999 trades (perfil de robô/agente) |
| **igual** | `POST swap-api /v1/coins/market-activity/batch` | HTTP 201 | 1 000 (CF ~20) | duas moedas pump ativas voltaram preenchidas; **um mint sem sufixo `pump` voltou `null` em toda janela** (o sufixo não foi validado como classificador de programa) |
| **ausente do mapa de 12/09** | `GET /user-trades/{wallet}` | HTTP 200 | **600** | trades **por carteira**, 200 por página, cursor; ver 10.3 |
| **ausente do mapa de 12/09** | `GET /users/{id}/overview` | HTTP 200 | 60 | seguidores, seguindo, `verified`, `createdCoinsCount`; ver 10.3 |
| **ausente do mapa de 12/09** | `GET /pnl-leaderboard/top-trader-trades/{mint}` | HTTP 200 | 120 | trades do top-50 de qualquer período naquela moeda |
| **ausente do mapa de 12/09** | `GET /coins/top-holders-v2/{mint}` | HTTP 200 | 60 | holders com `isDev`, `isSniper`, `isBundler`, `enteredAt` |
| **ausente do mapa de 12/09** | `GET /coins/holder-stats/{mint}` | HTTP 200 | 60 | % top-10, dev, snipers, bundlers, taxas totais (nulos num mint fora do programa pump) |
| **ausente do mapa de 12/09** | `GET /trades/{chainId}/{address}` | HTTP 200 | 600 | fita **por moeda**, `blockId` = slot, `before/after`; sem filtro por carteira |
| **ausente do mapa de 12/09** | `GET /competitions`, `/competitions/{slug}` | HTTP 200 | 60 | competições com prêmio; 100 linhas; ver 10.3 |
| **ausente do mapa de 12/09** | `GET /fees/holder-rewards` | HTTP 200 | 600 | livro de holder rewards (123 429 moedas, 360 427 carteiras distintas pagas) |
| **ausente do mapa de 12/09** | `profile-api /balance/summary/{w}`, `/v4/pnl/token/{w}/{m}`, `/v4/pnl/{w}/trades` | HTTP 200 | sem cabeçalho | PnL por carteira e por moeda (o `balance/summary` nu era 404 em 12/09, sem id) |
| **ausente do mapa de 12/09** | `GET /coins/perps`, `GET /changelog` | HTTP 200 | 60 | perpétuos HyperCore (fora do nosso escopo); `changelog` vazio hoje |
| **no mapa só como bundle, agora chamada** | `GET /following/v3/{followers,following}/count/{id}` | HTTP 200 `{count}` | 50 | contagem barata |
| **no mapa só como bundle, agora chamada** | `GET /pnl-leaderboard/positions?period=`, `GET /mint-positions/{mint}` | HTTP 200 (e REA) | 60 / 60 | posições do topo; holders com PnL e `callout`, 50 por página; a página de moeda chama `/mint-positions/{mint}?sortBy&pageSize[&withThesis]` (REA) |
| **no mapa como "não testada", agora chamada** | `POST profile-api /pnl/coin/{mint}/holders` | HTTP **201** anônimo (e REA 3×) | sem cabeçalho | corpo `{holders:[≤ 20 carteiras]}` (bundle); PnL de cada carteira **naquela moeda**; ver 10.3 |
| **ausente do mapa (REA)** | `GET advanced-indexer /boards/trending` (`ranking`, `window`, `chains`), `GET /home-feed` (anônima), `GET /competitions/{id}/entries/{entry}/highlights?limit`, `POST pump.fun/api/relay/rpc/tokens/batch` | só REA | — | não chamadas por mim; forma não lida |
| **ausente do mapa (REA)** | `livestream-api` (`/kols`, `/livestream`, `/livestream/history`, `/livestream/is-approved-creator`, `/clips/{mint}`, `/bounties/v2/tasks`), `blockchain-swap /supported/coin-create-mints` | só REA | — | chamadas pelo navegador em outro host; **resposta não verificada** (o `livestream-api` deu 404 no caminho nu em 12/09) |
| **bloqueada** | `GET /users/{address}/trader-stats`, `/social-stats`, `GET /coin-activity/{mint}` | HTTP **401** | 30 / 30 / 20 | exigem sessão; registrado e deixado |
| **bloqueada** | NATS (3 hosts) | HTTP/WS `auth_required: true` | — | só li o `INFO`; `POST /nats/token` só no bundle, **não chamado** |
| **não testada (substituída no bundle)** | `/coins/top-holders/{mint}`, `/following/{id}`, `/following/v2/*` | só bundle ("superseded") | — | por `top-holders-v2` e `/following/v3/*` |
| **não testada (fora do registro)** | `POST /wallet-overview`, `POST /x/public-handles`, `GET /kols`, `GET /livestream*`, `GET /coin-narrative/by-mints`, `GET /leaderboard` | ausentes do registro tipado; nenhuma chamada | — | podem viver em outro contrato; **não** é prova de que saíram |
| **não testada** | `king-of-the-hill`, `/coins/latest`, `/candlesticks/*`, `/replies/*`, `/trades/latest`, `/metas/current` | 404 em 12/09; nada em 06/10 | — | não re-testadas |
| **não testada** | `advanced-api-v2`, `livestream-api` (GET), `fun-block`, `blockchain-swap`, `solana-mainnet.pump.fun` | — | — | sem orçamento; o bundle ainda os cita |
| **parcial** | `GET /candles/{chainId}/{address}` | HTTP **400** | 600 | o parâmetro é `res` ∈ {1s,15s,30s,1m,5m,15m,1h,4h,1d}; não explorado |

### 10.3 O que é público sobre carteiras (para o H-030), com forma e limite medidos

**Quadro de PnL — `GET /pnl-leaderboard?period=daily|weekly|monthly&sort=realized|unrealized|combined&limit≤100`** (HTTP; RL 60). Teto de 100
linhas (bundle: "default and ceiling 100"; HTTP: `limit=200` → 100). `offset` não tem efeito (daily `limit=100&offset=100`: mesmo #1, 98 de 100
carteiras iguais; a diferença é refresh). Campos: `rank, walletAddress, pnlSol, pnlUsd, pnlPercent, buySpendSol, realizedPnlSol/Usd, unrealizedPnlSol/Usd,
positionsCount, topPositions[3], lastRefreshedAtMs, isVerified, verifiedBadgeVisible, userId` (+ nome e imagem, que não guardamos). Os três `windowStartSec` observados terminam
em 02:00 UTC (daily 05/10, weekly 29/09, monthly 06/09, lidos às 02:25 UTC de 06/10); **uma leitura não distingue âncora fixa de janela móvel arredondada**. Cada linha foi atualizada a poucos minutos da leitura: o quadro é **vivo**, não um retrato diário.
Seis quadros lidos nessa leitura (3 períodos × `combined` e `realized`) = 600 linhas = **300 carteiras distintas na união daquela rodada** (não é previsão de candidatas novas por dia: as mesmas carteiras reaparecem; o `sort=realized` não é o `combined`
com outro nome: 49 de 100 em comum no daily). O que os números dizem:

| quadro (100 linhas) | realizado Σ / não realizado Σ (SOL) | `isVerified` | `buySpendSol` ≈ 0 | `topPositions` de mint `…pump` | fora de Solana |
|---|---|---|---|---|---|
| daily combined | 3 597 / **11 760** | 59 | **14** | 80 / 254 | 61 |
| weekly combined | 24 581 / 26 593 | 84 | 2 | 95 / 265 | 37 |
| monthly combined | 106 170 / 76 769 | 80 | 1 | 86 / 252 | 34 |
| daily realized | 6 107 / 378 | 60 | 0 | 109 / 247 | 25 |
| weekly / monthly realized | — | 81 / 77 | 0 / 0 | 106 / 256; 90 / 252 | 19; 35 |

- **A maior parte do PnL de "hoje" é marcação:** no daily combined, 77 % do PnL somado é não realizado (mediana por carteira 0,78), 38 das 100 linhas têm realizado ≤ 0 e 14 têm gasto de compra ≈ 0.
  `buySpendSol ≈ 0` **não prova** "tokens recebidos": pode ser compra anterior à janela, custo ausente ou outra convenção contábil. No `sort=realized` essas linhas somem (0 sem compra, 0 com realizado ≤ 0), mas é um quadro de **sobreviventes de um
  dia** (realizado/gasto mediano 0,29 no daily).
- **O quadro não é só pump nem só Solana:** de 254 posições de topo no daily combined, só 80 têm mint `…pump` e 61 são de outras cadeias (EVM). É preciso filtrar para swaps do programa pump/PumpSwap.
- **Metade ou mais é "verificado":** 59–84 de 100. O registro tipado descreve `POST /profiles/verified` como "Verified (KOL/influencer badge)"; **não está demonstrado que seja o mesmo conjunto que o R61 mediu** ([[KB-0142-kol-e-call-antecipam-ou-confirmam]]), e o
  campo diverge entre rotas: o #1 semanal tinha `isVerified = true` no quadro (02:25 UTC) e `verified = false` no `/users/{id}/overview` (02:31 UTC).
- **O quadro é curado (bundle):** rotas de moderação escondem carteiras banidas e moedas bloqueadas (`/pnl-leaderboard/ban`, `/blocklist/mints/*`).
- Exemplo de leitura (não é recomendação): o #1 semanal (`9BMz..QdLU`) tem 27 709 seguidores, `following` 0, PnL +4 043 SOL dos quais **−62 realizado e +4 105 não realizado**, gasto de 3 228 SOL, 45 posições, e uma posição
  com `callout` (uma "chamada" pública da moeda) em que custo = quantidade (nada vendido, realizado 0). Pela definição do KB-0182, isso é marcação.

**Competições — `GET /competitions`, `GET /competitions/{slug}?limit≤100`** (HTTP; RL 60). Hoje 2 ao vivo (`solo-cuptober`, `squad-cuptober`, 03–10/10) e 2 passadas (`test-…`).
`solo-cuptober`: **20 506 participantes**, prêmio de US$ 50 000 ao #1 (US$ 100 000 no total, `prizeCopy`), e o #1 tem **+US$ 682 mil, realizado 0, `buySpendSol` 0, 65 posições** (100 % marcação). Cada entrada
traz `walletAddress`. É lista de candidatos **sob incentivo de prêmio** (viés provável; não medido).

**Seguidores — público, sem data (HTTP).** `GET /users/{address}` (RL 30) devolve `followers` e `following`; `GET /following/v3/followers/count/{id}` e `/following/v3/following/count/{id}`
(RL 50 observado) devolvem `{"count":n}` (15 e 11 B nessas duas respostas); `GET /users/{id}/overview` (RL 60) traz `counts{followers,following}`, `verified`, `banned`, `createdCoinsCount` e `degraded[]`. **Nenhuma tem carimbo de data nem histórico.** As fontes
**não são equivalentes campo a campo**: a contagem não traz `following`, `is_pump_user`, verificação nem criação de moedas; e na mesma carteira o `/users` deu 27 709 (02:29 UTC) e o `/overview` 27 710 (02:31 UTC), por drift de leitura, e `verified` divergiu do quadro (acima). 50/min é o
cabeçalho observado, não capacidade garantida. `/users/{address}/trader-stats` e `/social-stats` pedem sessão (**401**).

**Trades por carteira — `GET /user-trades/{wallet}`** (HTTP; RL 600; só Solana). `limit` 1–200 (padrão 50), `cursor` (chave `micros:uuid`), `mint`, `types=trades|transfers`. Linha:
`tx, isBuy, timestamp (ISO, segundos), amountUsd, amountSol, baseAmount, priceUsd, mint, chainId, walletAddress, userId, slotIndexId` (12 primeiros dígitos = slot; **slot sozinho não identifica um trade**: usar tx + evento/perna). Formulação sustentada: **800 trades recuperados de uma carteira
em quatro páginas de 200, cobrindo ~10,05 dias (10 d 1 h 11 min: 06/10 00:47Z → 25/09 23:36Z), sem duplicata e com `nextCursor` ainda presente**. Não demonstra janela completa, retenção mínima nem cobertura uniforme de carteiras. Não traz programa/venue nem taxa.
Alternativas por carteira: `profile-api GET /v4/pnl/{wallet}/trades?mint=` (uma moeda, `legCount`, `poolAddress`), `GET /v4/pnl/token/{wallet}/{mint}`, `GET /balance/summary/{wallet}` (sem cabeçalho de limite) e `swap-api /v2/coins/{mint}/trades?userAddress=` (por moeda; entra no limite de ~20/60 s do Cloudflare da §2).

**PnL de holders por moeda — `POST profile-api /pnl/coin/{mint}/holders`** (HTTP 201 anônimo, sem cabeçalho de limite; achado da segunda captura do REA, forma lida por mim). Corpo, como o site o monta (bundle): `{"holders":["<carteira>", …]}`, em lotes de **20**. Chamei uma vez com 5 carteiras públicas do
`top-holders-v2` da mesma moeda. Resposta: `{success, data[]{wallet, mint, unrealized{cost_basis{sol,usd}, pnl{sol,usd}, pnl_mark{sol,usd}, percentage{sol,usd}, amount_held}|null, realized{pnl, percentage, avg_buy_price, avg_sell_price, amount_sold, total_in, total_out}|null,
total_buy_spend{sol,usd}, total_buy_amount, last_slot_index_id, has_transfers, has_untrusted_basis, fee{sol,usd}, fee_detail{base, priority, tip, ui, ata_rent, protocol, cashback}}, errors[]}`. Nas 5: 3 com realizado, 1 aberta (−99,6 % sobre 23,5 SOL), 1 linha sem dado; **`has_untrusted_basis = true` em 3 de 5**;
`fee_detail` preenchido só em parte. É a única rota pública que devolve **realizado e custo por carteira e por moeda** para uma lista que *nós* escolhemos, mas o recorte é do site, `amount_held` divergiu da lista de holders lida 9 min antes (4,2 M tokens → 0) e a conta não é a nossa FIFO.

**Sinal do próprio site — `GET /pnl-leaderboard/top-trader-trades/{mint}`** (HTTP; RL 120, `limit` ≤ 500, `to` em ms, cursor): trades, em todas as carteiras, de contas que estão no **top-50 de qualquer período**.
Devolve `boardsBuiltAtMs` (a idade do quadro). Como o top-50 é o quadro vivo, uma operação antiga devolvida hoje **não era sinal disponível naquele instante**. É primo do sinal que o KB-0142 mediu (selo KOL: comprar 20 s depois deu R −0,071); **não** foi medido como tal.

**Outras (HTTP).** `GET /mayhem/top-traders?window=24h|7d` (50 itens; só moedas Mayhem). `GET /coins/top-holders-v2/{mint}` marca cada holder com `isDev`/`isSniper`/`isBundler`. `GET /trades/{chainId}/{address}` é a fita por moeda com slot exato e `before/after`, **sem filtro por carteira**.
`GET /user-portfolio/{wallet}` devolveu 200 posições com `limit=5` (195 KB). `GET /fees/holder-rewards?limit=3` devolveu 3 moedas e totais globais.

### 10.4 O que o H-030 pode usar, o que não pode, e o aviso de olhar o futuro

**Pode usar (com as condições da revisão da Astra):**
- **Gerar candidatas observadas para frente, não escolher.** Cada resposta guarda fonte, período, ordenação e `received_at`; entradas e saídas posteriores do quadro **não apagam** candidatas já observadas. `known_at` anterior à aposta **não basta**: a candidata descoberta às 02:25 não existia
  para o corte econômico de 00:00, então também precisa ser anterior ao corte do retrato que a selecionou. **Atenção ao universo:** o desenho diz que toda carteira vista na fita entra no ranking; se só as descobertas pelo site concorrerem ao top-30, o experimento passa a medir "C-PnL dentro da seleção da pump.fun", outra população,
  mesmo sem olhar o futuro. A lista do site deve ser **observação adicional** (rotulada como tal), nunca substituir o universo da fita; os controles continuam vindo da fita inteira.
- **Foto de seguidores.** A contagem barata (`followers/count`, 50/min observado) só cobre `followers`; `following`, `is_pump_user`, verificação e criação exigem `/users` (30/min) ou `/overview` (60/min), e as fontes não coincidem campo a campo. Antes de coletar, congelar fonte por campo, `known_at` **por resposta** (não o horário da primeira chamada
  quando combinar fontes), tratamento de `degraded[]`/ausência (falha não vira `false` nem zero) e a divergência `verified` × `isVerified`. `is_verified` e `created_coins_count` entram **descritivos, sem alterar elegibilidade nem CONFIRMA**; `createdCoinsCount` não equivale à exclusão do criador de um mint. **Não guardar `username`.**
- **Auditoria parcial por carteira.** `/user-trades/{wallet}` e `POST /pnl/coin/{mint}/holders` conferem **componentes** do PnL por entidade da nossa fita, não reproduzem o C-PnL, as reservas nem a execução. Antes de tratar como auditoria: intervalo fechado de comparação, paginação até a fronteira, detecção de cursor repetido, lacunas e eventos tardios;
  casamento por tx + evento/perna, mint, carteira, lado e quantidade; inventário de abertura (dez dias não recuperam uma compra antiga vendida hoje); carteiras de cada entidade na versão do corte; `received_at` real no backfill, nunca o horário antigo do trade.
- **Medir, sem decidir.** `top-trader-trades` pode ser registrado prospectivamente **como comparação descritiva pré-declarada** (universo de mints, cadência, deduplicação, composição do top, `boardsBuiltAtMs`, `generatedAtMs`, recepção local congelados antes), **sem poder confirmar o H-030**; se alguém quiser hipótese confirmatória sobre o site, precisa de protocolo
  próprio e tratamento prévio da multiplicidade. Escolher os mints depois de ver sucesso é outra seleção.

**Não pode usar:**
- **Histórico de quadro.** Nenhum quadro, seguidor ou `top-trader-trades` tem versão passada: não há como reconstruir o quadro de 06/09 a 05/10. Só vale para frente, a partir da primeira foto arquivada.
- **Ranking de hoje como critério ou como backtest.** O quadro de um dia ordena por resultado **até aquele dia** (inclui marcação, linhas sem custo e a curadoria da pump.fun). Uma carteira que aparece hoje apareceu *porque* ganhou; usar o quadro de hoje para escolher quem seguir e medir o ganho de ontem é olhar o futuro. O `sort=realized` também é viés de sobrevivência de uma janela.
- **Seguidor com histórico.** Nem `/users` nem as contagens têm data: só a foto noturna nossa é ponto no tempo.
- **`trader-stats`, `social-stats`, `coin-activity`, alertas de quem se segue, NATS:** exigem sessão ou autenticação.
- **Descobrir o universo pelo site.** O quadro tem 100 linhas por período e nenhuma paginação; competição é população sob prêmio; Mayhem é um nicho. O universo completo só sai da nossa fita do programa inteiro.

**Aviso de olhar o futuro, em uma frase:** um quadro lido **hoje** é o resultado de uma janela que já terminou (e `lastRefreshedAtMs` mostra que ainda se mexe), então só pode alimentar "quem observar a partir de agora", e cada uso precisa de um `known_at` anterior à aposta **e ao corte
do retrato**, como já está escrito para os seguidores ([[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]]).

### 10.5 Limites desta releitura

- Não li os chunks de rota que a home não lista (o `unified-prod.nats…` e `boards/trending` do REA não estão nos 101 que li). Não sei se o `trenches` ainda é usado pelo screener; sei que responde anônimo.
- Cada rota nova foi chamada **uma vez** (às vezes duas); nada de teste de carga nem de 429 de propósito. Os limites são os cabeçalhos devolvidos; `remaining` leu 59 (ou 599, 119) em toda primeira chamada, mesmo 2–3 s depois de outra do mesmo caminho: **não concluí como os contadores se agrupam**.
- Retenção de `/user-trades` e de `/trades/{chainId}/{address}` não foi encontrada. Os agregados (300 carteiras, 800 trades, 77 %) estão nas notas com o procedimento, mas as respostas brutas **não** foram preservadas (ver abaixo).
- Não re-testei os hosts `advanced-api-v2`, `livestream-api`, `fun-block`, `blockchain-swap`, nem a regra de ~20 requisições por 60 s do Cloudflare no `swap-api` (T4.2f): o nosso tráfego a esse host foi 3 chamadas.
- Os 5 campos novos do `Coin` e o upgrade de 02/10 são coincidência de data. Não houve diff completo de schema.
- **Dados pessoais:** as respostas trouxeram nome de usuário, biografia e handle de X de pessoas. As respostas brutas ficaram numa pasta temporária **fora do repositório** durante a análise e **foram apagadas ao fim** (só restaram cabeçalhos e o log); no repositório há só endereços públicos truncados e agregados.
  Na próxima leitura, sanitizar antes de qualquer persistência.
