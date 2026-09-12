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
| `wss://multichain-prod.nats.realtime.pump.fun` | NATS — eventos de trade multichain (EVM) | `auth_required: true` no `INFO` | — | vivo, fechado |
| `socket.io` (`livechatUrl`, vindo da config do servidor, não do bundle estático) | chat da livestream | token de auth no payload | — | não conectado (não é feed de trades) |
| `frontend-api.pump.fun` (v1) / `frontend-api-v2` | domínios antigos dos tutoriais | — | — | 530/1016 (T4.0); v2 "deprecated" na lista comunitária |

## 1. Inventário — `frontend-api-v3.pump.fun`

Legenda: **RL** = `x-ratelimit-limit` devolvido (janela `x-ratelimit-reset: 60`); "—" = sem
cabeçalho. **Auth** = "não" quando a chamada anônima devolveu 200. Formas completas (nomes e tipos)
em `notes-T4.0c.md` §4; aqui vai o resumo.

### 1.1 Chamados ao vivo (24 rotas distintas, 40 requisições)

| # | Método e path | Query observada (bundle) | Auth | HTTP | RL | Forma (resumo) |
|---|---|---|---|---|---|---|
| 1 | `GET /coins` | `offset, limit, sort, order, includeNsfw[, complete=true][, searchTerm][, creator][, tokenizedAgent=true][, isCharity=true][, deviceId, sessionId]` | não | 200 | 60 | `[Coin]` — 54 campos (§1.3). **Cap de 70 itens por página**: `limit=100` e `limit=1000` devolvem 70. `offset` funciona (paginei até 630). `sort=created_timestamp` e `sort=market_cap` confirmados; `complete=true` filtra graduadas; `searchTerm=pepe` busca por nome |
| 2 | `GET /coins/{mint}` | — | não | 200 | — | `Coin` + `security_verdict{verdict,scope,reasons[],decided_by,provider,version,updated_at,source}` |
| 3 | `GET /coins-v3/{mint}` | `includeLiveStreamInfo=bool` | não | 200 | 60 | `Coin` (mesmos campos; sem `security_verdict` nesta amostra) |
| 4 | `GET /sol-price` | — | não | 200 | 50 | `{solPrice: float, asOfTimestamp: int(ms), stale: bool}` |
| 5 | `GET /coins/great-coins` | (`?…` opcional) | não | 200 | 20 | `[Coin]` (5) — "trending"; inclui coins EVM (`mint` 0x…), `canonical_pool_liquidity_usd`, `pump_swap_pool`, `inverted` |
| 6 | `GET /coins/top-tokens/mints` | — | não | 200 | 60 | `[str]` (502 mints; começa em wSOL; inclui tokens fora do pump) |
| 7 | `GET /coins/similar` | `mint, limit=5, offset=0, includeNsfw` | não | 200 | 20 | `[Coin]` |
| 8 | `GET /mayhem/top-coins` | `window=24h` | não | 200 | 60 | `{window, items[50]{rank, mint, netUsdDeployed}, updatedAt}` |
| 9 | `GET /mayhem/top-traders` | `window=24h` | não | 200 | 60 | `{window, items[50]{rank, address, realisedPnlUsd, winRate, volumeUsd, tradeCount}, updatedAt}` |
| 10 | `GET /pnl-leaderboard` | `period ∈ {daily, weekly, monthly}, sort?, limit?` | não | 200 (400 com `period=24h`) | 60 | `{entries[]{rank, walletAddress, pnlSol, pnlUsd, pnlPercent, buySpendSol, realizedPnl*, unrealizedPnl*, positionsCount, topPositions[]{mint, chainId, symbol, name, imageUri}, username, userId…}, periodType, periodLabel, windowStartSec}` |
| 11 | `GET /users/{address}` | — | não | 200 | 30 | `{address, userId, is_pump_user, username, profile_image, kind, member_count, following, followers, bio, x_username, canonical_svm_wallet, group_badges[]}` |
| 12 | `GET /coins-v2/user-created-coins/{address}` | `limit=10, offset=0` | não | 200 | 60 | `{limit, offset, count, coins[Coin]}` |
| 13 | `GET /coins/top-holders/{mint}` | `shape=web` | não | 200 | 60 | `{topHolders[50]{address, amount(float, unidades UI)}, totalHolders: int}` |
| 14 | `GET /token-holders/{mint}/count` | — | não | 200 | 60 | `{mint, chain, networkId, holderCount}` |
| 15 | `GET /coins-v2/{mint}/mayhem-state` | — | não | 200 | 60 | `{mint, state ∈ active/paused/completed, mode ∈ auto/manual, pause_reason}` (ex.: `below_initial_buy_floor`) |
| 16 | `POST /coins-v2/mints` | corpo `{mints[], includeNsfw, include_nsfw}` | não | 201 | 30 | `[Coin]` (lote de metadados; o site usa `credentials:"include"`, mas anônimo funcionou) |
| 17 | `GET /user-positions/{wallet}` | `mints=<mint>[,…]` obrigatório (≤ 200; 400 sem ele) | não | 200 | **600** | `{positions[]{coinMint, chainId, isExited, walletAddress, amountHeld, pnlUsd, pnlPercentage, costBasisAmount, costBasisUsd, amountBoughtUsd, amountBought, callout, hasTransfers, likelyLost, valueUsd, tokenPriceUsd, realizedPnlUsd, updatedAt}}` |
| 18 | `GET /coins/search-unrestricted` | `offset, limit, sort, order, includeNsfw, currentlyLive=true[, tokenizedAgent][, isCharity]`; `sort` também aceita `featured`, `livestream_num_participants` (bundle) | não | 200 | — | `[Coin]` + campos de live: `num_participants, playlist_url(_high/_low), playlist_status, thumbnail, vod_playlist_url, volume_1h_usd, recommendation_id/rank, last_reply, inverted, pump_swap_pool, banner_uri` |
| 19 | `GET /global-params/{created_timestamp_ms}` | path = timestamp da criação da coin | não | 200 | 50 | `{slot, signature, initial_virtual_token_reserves, initial_virtual_sol_reserves, initial_virtual_quote_reserves, initial_real_token_reserves, token_total_supply, fee_basis_points, timestamp}` — **parâmetros iniciais da curva vigentes naquele instante** (§4.2) |
| 20 | `GET /coins/mayhem-mode` | `limit=60, mayhemState?` | não | 200 (A4.1b) | — | `[Coin]` com `mayhem_state` |
| 21 | `GET /mayhem/overview` | — | não | 200 (A4.1b) | — | `{activeCoins, coinsCreated{24h,7d}, coinsCreatedByMode{auto,manual}{24h,7d}, updatedAt}` |
| 22 | `GET /coins/king-of-the-hill` | `includeNsfw` | — | **404** `Coin not found for mint: king-of-the-hill` | — | rota v1 morta: o router v3 trata como `/coins/{mint}` |
| 23 | `GET /coins/latest`, `GET /candlesticks/{mint}`, `GET /replies/{mint}`, `GET /trades/latest`, `GET /metas/current` | (v1) | — | **404** | — | rotas v1/v2 documentadas pela comunidade **não existem** em v3 |

### 1.2 Vistos no bundle, não chamados (precisam de cookie de sessão, são escrita, ou não cabem no orçamento)

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

### 1.3 O objeto `Coin` (54 campos observados em `/coins`, `/coins/{mint}`, `/coins-v3`, `/coins-v2/mints`)

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
| 4 | `POST /v1/coins/market-activity/batch` | `{addresses[], intervals[], metrics[]}` | 201 | 1000 | `{mint: {intervalo: {métrica}}}` — **lote**, ideal para varredura |
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
IP só (a T4.2e mediu 38,8 %). `POST /v1/coins/market-activity/batch` (rota 4: N mints numa requisição, janelas
5m/1h/6h/24h, USD) é a saída para uma feature de janela maior, não para a fita do minuto.

## 3. Superfícies em tempo real

### 3.1 WS do site: `wss://advanced-indexer.pump.fun/ws/trenches` (boards do screener)

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

### 3.2 NATS multichain: `wss://multichain-prod.nats.realtime.pump.fun`

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

### 4.1 Taxas — `https://pump.fun/docs/fees`, **"Last Updated: 20 May 2026"**

| Ação | Taxa |
|---|---|
| Criar coin | 0 SOL / 0 USDC |
| Graduação para PumpSwap | 0,015 SOL |
| **Bonding curve** (SOL e USDC) | criador **0,300 %** + protocolo **0,95 %** + LP 0 % = **1,25 %** |
| **PumpSwap, pool canônico, quote SOL** — por market cap (preço × 1 bi de tokens) | 0–420 SOL: 0,300/0,930/0,020 = **1,250 %**; 420–1 470: 0,950/0,050/0,200 = 1,200 %; 1 470–2 460: 1,150 %; 2 460–3 440: 1,100 %; 3 440–4 420: 1,050 %; 4 420–9 820: 1,000 %; 9 820–14 740: 0,950 %; 14 740–19 650: 0,900 %; 19 650–24 560: 0,850 %; 24 560–29 470: 0,800 %; 29 470–34 380: 0,750 %; 34 380–39 300: 0,700 %; 39 300–44 210: 0,650 %; 44 210–49 120: 0,600 %; 49 120–54 030: 0,550 %; 54 030–58 940: 0,525 %; 58 940–63 860: 0,500 %; 63 860–68 770: 0,475 %; 68 770–73 681: 0,450 %; 73 681–78 590: 0,425 %; 78 590–83 500: 0,400 %; 83 500–88 400: 0,375 %; 88 400–93 330: 0,350 %; 93 330–98 240: 0,325 %; **≥ 98 240 SOL: 0,050/0,050/0,200 = 0,300 %** (criador/protocolo/LP; a partir da 2.ª faixa protocolo 0,05 % e LP 0,20 % fixos, só o criador decresce) |
| PumpSwap, pool canônico, quote USDC | mesma escada em USDC: 0–59 000 USDC 1,250 %; 59 000–300 000 1,200 %; … ; ≥ 20 000 000 USDC 0,300 % (tabela completa em `notes-T4.0c.md` §5) |
| PumpSwap, pools **não canônicos** | criador 0 % + protocolo 0,05 % + LP 0,25 % = 0,30 % |

Notas da página: creator fee vale para coins presentes na curva/PumpSwap desde 13/05/2025; USDC
como quote desde 21/05/2026; app móvel pode cobrar até +0,1 %; "The pump.fun platform may change
these fees at any time, without notice." O `fee_basis_points: 95` de `/global-params` bate com o
0,95 % de protocolo na curva.

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
| Holders por coin | **Parcial**: top 50 por quantidade + `totalHolders` (`/coins/top-holders`), `holderCount`, `top10HoldersPercent`/`devHoldingsPercent`/`bundlerOwnedPercentageV2` (indexer, sem definição). Lista completa e PnL por holder (`profile-api POST /pnl/coin/{mint}/holders`) não testados/rota de sessão | RPC `getTokenLargestAccounts` (20) / `getProgramAccounts` por mint, ou Helius DAS / Bitquery (chave) |
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
