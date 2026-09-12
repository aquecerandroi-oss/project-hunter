# Notas de pesquisa — T4.0c: mapa completo da superfície off-chain da pump.fun

Sessão: **12/09/2026, 02:18–02:41 BRT** (UTC−3; os timestamps abaixo foram convertidos do `Date`
do servidor/`date -u` local). Agente de pesquisa; sem código em `packages/`, sem commit, sem `.env`,
sem login, sem chave. Todas as chamadas em primeiro plano com `timeout` explícito. Conteúdo de
página tratado como dado. Entregável principal: `docs/PUMPFUN.md`. Brief: `brief-T4.0c-mapa-api-pumpfun.md`.

**Desvio operacional registrado:** o scratchpad da sessão tem caminho > 260 caracteres e o Python
do `uv` no Windows não conseguiu abrir arquivos nele (`FileNotFoundError` em `open()`); copiei a
árvore de trabalho para `C:/Users/evert/AppData/Local/Temp/t40c/` (curto) e trabalhei de lá. Por
esse mesmo erro a **primeira** conexão ao WS do PumpPortal (02:25:39–02:26:10 BRT) rodou 30 s mas
perdeu a gravação; a segunda (02:27:24–02:27:55) é a registrada — foram 2 conexões no total.

## 1. Cronologia e orçamento

| hora BRT | ação | resultado |
|---|---|---|
| 02:18:36 | `GET https://pump.fun/` (HTML, 1,78 MB) | 200; 94 chunks `_next/static/chunks/*.js` listados; CSP mostra `wss://*.pump.fun`, `*.helius-rpc.com`, `*.jito.wtf`, `*.livekit.cloud` |
| 02:18:46 | `GET https://pump.fun/docs/fees` | 200; "Last Updated: 20 May 2026" |
| 02:19:01–02:19:10 | `pumpportal.fun/local-trading-api/trading-api/`, `/data-api/real-time/`, `/pricing/`, `/` | 200, 200, **404**, 200 |
| 02:19:25–02:20:03 | download dos 94 chunks (6,9 MB) | ok |
| 02:20:21–02:20:50 | `pumpportal.fun/trading-api/setup/`, `/data-api/` (404), `/local-trading-api/` (404), `/fees/`, `/trading-api/`, `/FAQ/` | 200/404/404/200/200/200 |
| 02:23:03–02:23:43 | HTML de `pump.fun/coin/{mint}`, `/advanced` (308), `/live`, `/board` (308), `/mayhem`, `/docs/bonding-curve`, `/docs/fees`; +33 chunks novos (total 127) | ok |
| ~02:24 | WebSearch ×2 (listas comunitárias) → `github.com/BankkRoll/pumpfun-apis` | — |
| 02:25:39–02:26:10 | WS PumpPortal (1.ª conexão, gravação perdida) | — |
| 02:27:24–02:27:55 | WS PumpPortal `wss://pumpportal.fun/api/data` sem chave, 30 s | conectado 0,64 s; 2 confirmações; **6 `create`**; 0 migrações |
| 02:27:57 | `raw.githubusercontent.com/BankkRoll/pumpfun-apis/main/README.md`, `INDEX.md` (404 na raiz), `api.github.com/repos/…` (96 estrelas, push 2026-06-17) | ok |
| 02:28:02–02:28:58 | **lote 1** `frontend-api-v3` (#1–15) | ver §3 |
| 02:30:08–02:30:54 | lote 1 `swap-api` + profile/livestream/advanced-api-v2/indexer (#101–112) | ver §3 |
| 02:32:28 | capturas comunitárias (`captures/2026-06-17/INDEX.md` etc.) via raw GitHub | 200 |
| 02:32:41–02:33:22 | **lote 2** `frontend-api-v3` (#16–26) | ver §3 |
| 02:33:30–02:34:06 | lote 2 `swap-api` + indexer HTTP (#113–122) | ver §3 |
| 02:34:13 | NATS `wss://multichain-prod.nats.realtime.pump.fun` — só leitura do `INFO` | `auth_required: true` |
| ~02:34 | WebSearch (king of the hill / graduação nas docs) | só fontes secundárias; doc oficial não publica número |
| 02:35:55–02:36:26 | WS `wss://advanced-indexer.pump.fun/ws/trenches` board `movers`, 30 s | 3 snapshots + 50 deltas (418 patches), 180 470 bytes |
| 02:36:29–02:37:10 | **paginação de estatísticas** `frontend-api-v3 /coins` offsets 70…630 (#27–35) | 9×70 itens |
| 02:37:18–02:37:31 | RPC proxy `getHealth`, `blockchain-swap` (2), `fun-block` (#123–126) | ver §3 |
| 02:39:00–02:39:23 | lote 3 `swap-api` (caps/retenção, #127–132) | ver §3 |
| 02:39:31 | `pump.fun/docs` (índice), `/docs/pumpswap` e `/docs/how-to-create-a-coin` (páginas genéricas, sem conteúdo próprio) | 200 |
| 02:40:22–02:40:43 | **lote 3** `frontend-api-v3` (#36–40) | ver §3 |
| 02:40:48 | `pump.fun/docs/create-coin` | 200 (sem "Last Updated" visível) |

**Totais por host:** `frontend-api-v3` **40** (limite do brief: ≤ 40; ≥ 2,5 s entre chamadas;
nunca menos de 58 de `x-ratelimit-remaining`), `swap-api` 22, `advanced-indexer` 3 (+1 WS),
`blockchain-swap` 2, `advanced-api-v2` 1, `fun-block` 1, `livestream-api` 1, `profile-api` 1,
`solana-mainnet.pump.fun` 1 (`getHealth`). Sem 429 em nenhuma chamada.

## 2. Descoberta no bundle (127 chunks)

Constantes em `0._.d6~ioidd~.js` (módulo `38279`):
`CLIENT="https://frontend-api-v3.pump.fun"`, `PROFILE="https://profile-api.pump.fun"`,
`PUMP_SWAP=SWAP_API="https://swap-api.pump.fun"`; getters em `0iayht~_nxlo0.js`:
`getAdvancedClientServerUrl→advanced-api-v2`, `getAdvancedIndexerUrl→advanced-indexer`,
`getBlockchainApiServiceUrl→blockchain-swap`, `getBlockchainClientUrl→fun-block`,
`getLivestreamServiceUrl→livestream-api`, `getPumpSwapClientServerUrl(v)→swap-api/{v}`.
Rotas construídas (todas listadas em `docs/PUMPFUN.md` §1–§3). WS: `0_necq9.81y_e.js` monta
`${indexer}/ws/trenches?subscription=…` e envia `{event:"subscribe",data:{board,tier:"web",platform:"WEB",surface:"WEB",…}}`;
`0685.ev70u139.js` usa `wss://multichain-prod.nats.realtime.pump.fun` para `useMultichainTradeEventSubscription`;
`03f3_bmg_u.b..js` abre `socket.io` em `livechatUrl` com `auth:{origin,timestamp,token,deviceId}`.
Boards: `PRO_SCREENER_BOARDS=["new","graduating","graduated","movers"]`. Retry do cliente HTTP do
site (ky): `statusCodes:[408,413,429,500,502,503,504]`, `afterStatusCodes:[413,429,503]`, 2 tentativas.
Chave de RPC do site embutida: `https://solana-mainnet.pump.fun/<uuid>` (não usar).
Hosts citados só na lista comunitária (não vistos no bundle nem chamados): `volatility-api-v2`,
`clips-api`, `market-api`, `pump-fe.helius-rpc.com`.

## 3. Log de chamadas HTTP (hora BRT; cursores redigidos)

Os corpos ficaram no diretório de trabalho curto; abaixo só código, tamanho e limite. Mints e
carteiras são identificadores públicos de ativos/contas da própria API, mantidos para reprodução.

| hora BRT | nome | URL | HTTP | bytes | rate limit |
|---|---|---|---|---|---|
| 02:28:02 | coins_list_limit1000 | `https://frontend-api-v3.pump.fun/coins?offset=0&limit=1000&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 129714 B | limite 60/60s |
| 02:28:07 | coins_detail | `https://frontend-api-v3.pump.fun/coins/BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump` | 200 | 1983 B | sem cabeçalho x-ratelimit |
| 02:28:10 | coins_v3_detail | `https://frontend-api-v3.pump.fun/coins-v3/BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump?includeLiveStreamInfo=true` | 200 | 1804 B | limite 60/60s |
| 02:28:14 | sol_price | `https://frontend-api-v3.pump.fun/sol-price` | 200 | 75 B | limite 50/60s |
| 02:28:17 | great_coins | `https://frontend-api-v3.pump.fun/coins/great-coins` | 200 | 8538 B | limite 20/60s |
| 02:28:21 | top_tokens_mints | `https://frontend-api-v3.pump.fun/coins/top-tokens/mints` | 200 | 23279 B | limite 60/60s |
| 02:28:25 | coins_similar | `https://frontend-api-v3.pump.fun/coins/similar?mint=BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump&limit=5&offset=0&includeNsfw=false` | 200 | 9490 B | limite 20/60s |
| 02:28:29 | mayhem_top_coins | `https://frontend-api-v3.pump.fun/mayhem/top-coins?window=24h` | 200 | 5128 B | limite 60/60s |
| 02:28:32 | mayhem_top_traders | `https://frontend-api-v3.pump.fun/mayhem/top-traders?window=24h` | 200 | 8373 B | limite 60/60s |
| 02:28:36 | pnl_leaderboard | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=24h&limit=5` | 400 | 205 B | limite 60/60s |
| 02:28:40 | users_creator | `https://frontend-api-v3.pump.fun/users/2CtDrkiHnoqx9eqARCZCxtygMhAYmPPXD8AA59EdcC7Z` | 200 | 418 B | limite 30/60s |
| 02:28:43 | coins_v2_user_created | `https://frontend-api-v3.pump.fun/coins-v2/user-created-coins/2CtDrkiHnoqx9eqARCZCxtygMhAYmPPXD8AA59EdcC7Z?limit=10&offset=0` | 200 | 17219 B | limite 60/60s |
| 02:28:47 | king_of_the_hill | `https://frontend-api-v3.pump.fun/coins/king-of-the-hill?includeNsfw=true` | 404 | 181 B | sem cabeçalho x-ratelimit |
| 02:28:51 | coins_latest | `https://frontend-api-v3.pump.fun/coins/latest` | 404 | 144 B | sem cabeçalho x-ratelimit |
| 02:28:55 | candlesticks | `https://frontend-api-v3.pump.fun/candlesticks/BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump?offset=0&limit=10&timeframe=5` | 404 | 287 B | sem cabeçalho x-ratelimit |
| 02:30:08 | swap_candles | `https://swap-api.pump.fun/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/candles?createdTs=1789184732000&interval=1m&limit=60` | 200 | 13306 B | limite 1000/60s |
| 02:30:12 | swap_line_chart | `https://swap-api.pump.fun/v1/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/line-chart?createdTs=1789184732000&timeframe=1w&width=72` | 200 | 5824 B | limite 1000/60s |
| 02:30:16 | swap_market_activity | `https://swap-api.pump.fun/v1/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/market-activity` | 200 | 958 B | limite 1000/60s |
| 02:30:21 | swap_first_trade | `https://swap-api.pump.fun/v1/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/first-trade` | 200 | 657 B | limite 1000/60s |
| 02:30:24 | swap_mayhem_stats | `https://swap-api.pump.fun/v1/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/mayhem-stats` | 200 | 98 B | limite 1000/60s |
| 02:30:28 | swap_fee_sharing_totals | `https://swap-api.pump.fun/v2/fee-sharing/account/2CtDrkiHnoqx9eqARCZCxtygMhAYmPPXD8AA59EdcC7Z/totals` | 200 | 894 B | limite 1000/60s |
| 02:30:32 | swap_creators_unified_totals | `https://swap-api.pump.fun/v2/creators/unified-totals` | 404 | 195 B | sem cabeçalho x-ratelimit |
| 02:30:35 | swap_root | `https://swap-api.pump.fun/v1` | 200 | 12 B | limite 1000/60s |
| 02:30:39 | profile_balance_summary | `https://profile-api.pump.fun/balance/summary` | 404 | 78 B | sem cabeçalho x-ratelimit |
| 02:30:43 | livestream_root | `https://livestream-api.pump.fun/livestream/playlist-map` | 404 | 86 B | sem cabeçalho x-ratelimit |
| 02:30:46 | advanced_root | `https://advanced-api-v2.pump.fun/` | 530 | 17 B | sem cabeçalho x-ratelimit |
| 02:30:50 | indexer_root | `https://advanced-indexer.pump.fun/` | 200 | 12 B | sem cabeçalho x-ratelimit |
| 02:32:41 | coins_list_limit100_p0 | `https://frontend-api-v3.pump.fun/coins?offset=0&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 133053 B | limite 60/60s |
| 02:32:45 | coins_complete_true | `https://frontend-api-v3.pump.fun/coins?offset=0&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true&complete=true` | 200 | 136834 B | limite 60/60s |
| 02:32:49 | top_holders | `https://frontend-api-v3.pump.fun/coins/top-holders/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK?shape=web` | 200 | 4204 B | limite 60/60s |
| 02:32:52 | token_holders_count | `https://frontend-api-v3.pump.fun/token-holders/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/count` | 200 | 114 B | limite 60/60s |
| 02:32:56 | coins_v2_mayhem_state | `https://frontend-api-v3.pump.fun/coins-v2/972Nb7AeTYPT3Q4z8ENQwTkYsdL4LgVu6F9oRTSvpump/mayhem-state` | 200 | 127 B | limite 60/60s |
| 02:32:59 | coins_v2_mints_post | `https://frontend-api-v3.pump.fun/coins-v2/mints` | 201 | 3890 B | limite 30/60s |
| 02:33:03 | pnl_leaderboard_daily | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=daily&limit=5` | 200 | 6537 B | limite 60/60s |
| 02:33:07 | user_positions | `https://frontend-api-v3.pump.fun/user-positions/2CtDrkiHnoqx9eqARCZCxtygMhAYmPPXD8AA59EdcC7Z?limit=5&offset=0` | 400 | 292 B | limite 600/60s |
| 02:33:10 | replies_legacy | `https://frontend-api-v3.pump.fun/replies/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK?limit=5&offset=0` | 404 | 251 B | sem cabeçalho x-ratelimit |
| 02:33:14 | trades_latest_legacy | `https://frontend-api-v3.pump.fun/trades/latest` | 404 | 139 B | sem cabeçalho x-ratelimit |
| 02:33:18 | metas_current_legacy | `https://frontend-api-v3.pump.fun/metas/current` | 404 | 139 B | sem cabeçalho x-ratelimit |
| 02:33:30 | swap_trades | `https://swap-api.pump.fun/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/trades?limit=30` | 200 | 19012 B | limite 1000/60s |
| 02:33:34 | swap_trades_cursor | `https://swap-api.pump.fun/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/trades?limit=5&cursor=` | 200 | 3255 B | limite 1000/60s |
| 02:33:37 | swap_ath | `https://swap-api.pump.fun/v1/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/ath?currency=USD` | 200 | 34 B | limite 1000/60s |
| 02:33:40 | swap_market_activity_pump | `https://swap-api.pump.fun/v1/coins/BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump/market-activity?program=pump` | 200 | 906 B | limite 1000/60s |
| 02:33:43 | swap_market_activity_batch | `https://swap-api.pump.fun/v1/coins/market-activity/batch` | 201 | 729 B | limite 1000/60s |
| 02:33:47 | swap_candles_limit1000 | `https://swap-api.pump.fun/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/candles?createdTs=1789184732000&interval=1m&limit=1000` | 200 | 24185 B | limite 1000/60s |
| 02:33:51 | swap_candles_5m | `https://swap-api.pump.fun/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/candles?createdTs=1789184732000&interval=5m&limit=5` | 200 | 1114 B | limite 1000/60s |
| 02:33:55 | swap_trades_batch_post | `https://swap-api.pump.fun/v1/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/trades/batch` | 201 | 6548 B | limite 1000/60s |
| 02:33:58 | indexer_boards_movers | `https://advanced-indexer.pump.fun/boards/movers` | 200 | 27522 B | sem cabeçalho x-ratelimit |
| 02:34:02 | indexer_in_memory_coin | `https://advanced-indexer.pump.fun/in-memory-coin/BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump` | 200 | 1712 B | sem cabeçalho x-ratelimit |
| 02:36:29 | coins_page_off70 | `https://frontend-api-v3.pump.fun/coins?offset=70&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 131549 B | limite 60/60s |
| 02:36:33 | coins_page_off140 | `https://frontend-api-v3.pump.fun/coins?offset=140&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 131350 B | limite 60/60s |
| 02:36:38 | coins_page_off210 | `https://frontend-api-v3.pump.fun/coins?offset=210&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 136182 B | limite 60/60s |
| 02:36:42 | coins_page_off280 | `https://frontend-api-v3.pump.fun/coins?offset=280&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 132644 B | limite 60/60s |
| 02:36:47 | coins_page_off350 | `https://frontend-api-v3.pump.fun/coins?offset=350&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 126667 B | limite 60/60s |
| 02:36:51 | coins_page_off420 | `https://frontend-api-v3.pump.fun/coins?offset=420&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 134619 B | limite 60/60s |
| 02:36:56 | coins_page_off490 | `https://frontend-api-v3.pump.fun/coins?offset=490&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 131894 B | limite 60/60s |
| 02:37:01 | coins_page_off560 | `https://frontend-api-v3.pump.fun/coins?offset=560&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 134304 B | limite 60/60s |
| 02:37:05 | coins_page_off630 | `https://frontend-api-v3.pump.fun/coins?offset=630&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 | 135558 B | limite 60/60s |
| 02:37:18 | rpc_proxy_gethealth | `POST https://solana-mainnet.pump.fun/<uuid-do-site>` corpo `{"jsonrpc":"2.0","id":1,"method":"getHealth"}` | 200 | 38 B | sem cabeçalho x-ratelimit |
| 02:37:21 | bswap_supported_mints | `https://blockchain-swap.pump.fun/supported/coin-create-mints` | 200 | 30771 B | sem cabeçalho x-ratelimit |
| 02:37:24 | bswap_swap_build_empty | `https://blockchain-swap.pump.fun/transactions/swap-build` | 422 | 97 B | sem cabeçalho x-ratelimit |
| 02:37:27 | funblock_donate_configs | `https://fun-block.pump.fun/donate/charities/search?term=a&limit=1` | 400 | 104 B | sem cabeçalho x-ratelimit |
| 02:39:00 | swap_trades_limit1000 | `https://swap-api.pump.fun/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/trades?limit=1000` | 400 | 242 B | limite 1000/60s |
| 02:39:03 | swap_old_first_trade | `https://swap-api.pump.fun/v1/coins/69LjZUUzxj3Cb3Fxeo1X4QpYEQTboApkhXTysPpbpump/first-trade` | 200 | 659 B | limite 1000/60s |
| 02:39:07 | swap_old_candles_1d | `https://swap-api.pump.fun/v2/coins/69LjZUUzxj3Cb3Fxeo1X4QpYEQTboApkhXTysPpbpump/candles?createdTs=0&interval=1d&limit=1000` | 400 | 311 B | limite 1000/60s |
| 02:39:10 | swap_old_candles_1m | `https://swap-api.pump.fun/v2/coins/69LjZUUzxj3Cb3Fxeo1X4QpYEQTboApkhXTysPpbpump/candles?createdTs=0&interval=1m&limit=1000` | 200 | 219095 B | limite 1000/60s |
| 02:39:14 | swap_old_candles_1h | `https://swap-api.pump.fun/v2/coins/69LjZUUzxj3Cb3Fxeo1X4QpYEQTboApkhXTysPpbpump/candles?createdTs=0&interval=1h&limit=1000` | 200 | 222696 B | limite 1000/60s |
| 02:39:19 | swap_candles_bad_interval | `https://swap-api.pump.fun/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/candles?createdTs=0&interval=7s&limit=5` | 400 | 308 B | limite 1000/60s |
| 02:40:22 | search_unrestricted_live | `https://frontend-api-v3.pump.fun/coins/search-unrestricted?offset=0&limit=5&sort=market_cap&order=DESC&includeNsfw=false&currentlyLive=true` | 200 | 15180 B | sem cabeçalho x-ratelimit |
| 02:40:26 | global_params_ts | `https://frontend-api-v3.pump.fun/global-params/1789184732000` | 200 | 390 B | limite 50/60s |
| 02:40:30 | user_positions_mints | `https://frontend-api-v3.pump.fun/user-positions/2CtDrkiHnoqx9eqARCZCxtygMhAYmPPXD8AA59EdcC7Z?mints=BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump` | 200 | 541 B | limite 600/60s |
| 02:40:35 | coins_sort_market_cap | `https://frontend-api-v3.pump.fun/coins?offset=0&limit=5&sort=market_cap&order=DESC&includeNsfw=false` | 200 | 9416 B | limite 60/60s |
| 02:40:39 | coins_search_term | `https://frontend-api-v3.pump.fun/coins?offset=0&limit=3&sort=market_cap&order=DESC&includeNsfw=false&searchTerm=pepe` | 200 | 5683 B | limite 60/60s |

## 4. Formas redigidas das respostas (nomes e tipos; sem valores longos)

`str(n)` = string de n caracteres; listas mostram o número de itens e a união de chaves dos 20
primeiros. Páginas de paginação (`coins_page_off*`) têm a mesma forma de `coins_list_limit100_p0`.

### advanced_root (530 17 text/plain; charset=UTF-8)
```
error code: 1016

```

### bswap_supported_mints (200 30771 application/json)
```
["<95 itens>",{"mint":"str(43)","decimals":"int","symbol":"str","ticker":"str","image_url":"str(129)","minimum_sol_buy":"null","minimum_usdc_buy":"null","price_usd":"float","market_cap_usd":"float","liquidity_usd":"float"}]
```

### bswap_swap_build_empty (422 97 text/plain; charset=utf-8)
```
Failed to deserialize the JSON body into the target type: missing field `mint` at line 1 column 2
```

### candlesticks (404 287 application/json; charset=utf-8)
```
{"statusCode":"int","timestamp":"str(24)","path":"str(88)","message":"str(99)","error":"str"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":404,"timestamp":"2026-09-12T05:28:55.456Z","path":"/candlesticks/BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump?offset=0&limit=10&timeframe=5","message":"Cannot GET /candlesticks/BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump?offset=0&limit=10&timeframe=5","error":"Not Found"}

### coins_complete_true (200 136834 application/json; charset=utf-8)
```
["<70 itens>",{"mint":"str(43)","initialized":"bool","name":"str","symbol":"str","description":"str(27)","image_uri":"str(108)","metadata_uri":"str(67)","twitter":"str(26)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str(33)","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","inverted":"bool","is_banned":"bool","pump_swap_pool":"str(44)","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","quote_token_program":"str(43)","username":"str","usd_market_cap":"float","telegram":"str","mayhem_state":"str","profile_image":"str(118)","banner_uri":"str(80)","video_uri":"str"}]
```

### coins_detail (200 1983 application/json; charset=utf-8)
```
{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","description":"str(35)","image_uri":"str(86)","metadata_uri":"str(60)","twitter":"str(24)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str(22)","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","is_banned":"bool","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","quote_token_program":"str(43)","security_verdict":{"verdict":"str","scope":"str","reasons":["<1 itens>","str"],"decided_by":"str","provider":"str","version":"int","updated_at":"int","source":"str"},"usd_market_cap":"float"}
```

### coins_latest (404 144 application/json; charset=utf-8)
```
{"statusCode":"int","timestamp":"str(24)","path":"str","message":"str(31)","error":"str"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":404,"timestamp":"2026-09-12T05:28:51.830Z","path":"/coins/latest","message":"Coin not found for mint: latest","error":"Not Found"}

### coins_list_limit1000 (200 129714 application/json; charset=utf-8)
```
["<70 itens>",{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","description":"str(35)","image_uri":"str(86)","metadata_uri":"str(60)","twitter":"str(24)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str(22)","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","is_banned":"bool","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","quote_token_program":"str(43)","username":"str","usd_market_cap":"float","mayhem_state":"str","profile_image":"str(126)","banner_uri":"str(80)"}]
```

### coins_list_limit100_p0 (200 133053 application/json; charset=utf-8)
```
["<70 itens>",{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","description":"str","image_uri":"str(80)","metadata_uri":"str(80)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(43)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str(70)","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","is_banned":"bool","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","quote_token_program":"str(43)","username":"str","profile_image":"str(145)","usd_market_cap":"float","mayhem_state":"str","twitter":"str(54)"}]
```

### coins_search_term (200 5683 application/json; charset=utf-8)
```
["<3 itens>",{"mint":"str(43)","initialized":"bool","name":"str","symbol":"str","image_uri":"str(182)","metadata_uri":"str(67)","twitter":"str","telegram":"str","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","inverted":"bool","is_banned":"bool","pump_swap_pool":"str(44)","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","quote_token_program":"str(43)","username":"str","usd_market_cap":"float"}]
```

### coins_similar (200 9490 application/json; charset=utf-8)
```
["<5 itens>",{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","description":"str","image_uri":"str(67)","metadata_uri":"str(67)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","is_banned":"bool","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","last_reply":"int","reply_count":"int","is_currently_live":"bool","hide_banner":"bool","program":"str","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","boost_mode":"str","verified":"bool","usd_market_cap":"float","twitter":"str(24)","website":"str(22)","ath_market_cap":"float","ath_market_cap_timestamp":"int","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","market_cap_quote":"float","quote_token_program":"str(43)","security_verdict":{"verdict":"str","scope":"str","reasons":["<1 itens>","str"],"decided_by":"str","provider":"str","version":"int","updated_at":"int","source":"str"}}]
```

### coins_sort_market_cap (200 9416 application/json; charset=utf-8)
```
["<5 itens>",{"mint":"str(43)","initialized":"bool","name":"str","symbol":"str","image_uri":"str(182)","metadata_uri":"str(67)","twitter":"str","telegram":"str","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","inverted":"bool","is_banned":"bool","pump_swap_pool":"str(44)","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","quote_token_program":"str(43)","username":"str","usd_market_cap":"float"}]
```

### coins_v2_mayhem_state (200 127 application/json; charset=utf-8)
```
{"mint":"str(44)","state":"str","mode":"str","pause_reason":"str(23)"}
```

### coins_v2_mints_post (201 3890 application/json; charset=utf-8)
```
["<2 itens>",{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","description":"str(35)","image_uri":"str(86)","metadata_uri":"str(60)","twitter":"str(24)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str(22)","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","is_banned":"bool","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","quote_token_program":"str(43)","security_verdict":{"verdict":"str","scope":"str","reasons":["<1 itens>","str"],"decided_by":"str","provider":"str","version":"int","updated_at":"int","source":"str"},"usd_market_cap":"float","platform":"str"}]
```

### coins_v2_user_created (200 17219 application/json; charset=utf-8)
```
{"limit":"int","offset":"int","count":"int","coins":["<10 itens>",{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","image_uri":"str(86)","metadata_uri":"str(42)","twitter":"str(60)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str(71)","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","is_banned":"bool","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(43)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","usd_market_cap":"float","description":"str(35)","platform":"str","quote_token_program":"str(43)"}]}
```

### coins_v3_detail (200 1804 application/json; charset=utf-8)
```
{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","description":"str(35)","image_uri":"str(86)","metadata_uri":"str(60)","twitter":"str(24)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str(22)","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","is_banned":"bool","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(32)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","quote_token_program":"str(43)","usd_market_cap":"float"}
```

### funblock_donate_configs (400 104 application/json; charset=utf-8)
```
{"message":["<1 itens>","str(49)"],"error":"str","statusCode":"int"}
```
resposta de erro (crua, sem dados pessoais): {"message":["term must be longer than or equal to 2 characters"],"error":"Bad Request","statusCode":400}

### global_params_ts (200 390 application/json; charset=utf-8)
```
{"slot":"int","signature":"str(88)","initial_virtual_token_reserves":"int","initial_virtual_sol_reserves":"int","initial_virtual_quote_reserves":"int","initial_real_token_reserves":"int","token_total_supply":"int","fee_basis_points":"int","timestamp":"int"}
```

### great_coins (200 8538 application/json; charset=utf-8)
```
["<5 itens>",{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","image_uri":"str(100)","metadata_uri":"str(64)","twitter":"str(57)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","is_banned":"bool","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","platform":"str","token_program":"str(43)","quote_mint":"str(43)","base_decimals":"int","quote_decimals":"int","pool_address":"str(44)","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","security_verdict":{"verdict":"str","scope":"str","reasons":["<1 itens>","str"],"decided_by":"str","provider":"str","version":"int","updated_at":"int","source":"str"},"usd_market_cap":"float","description":"str(247)","website":"str","inverted":"bool","banner_uri":"str(80)","pump_swap_pool":"str(44)","is_cashback_enabled":"bool","quote_token_program":"str(43)","canonical_pool_liquidity_usd":"float"}]
```

### indexer_boards_movers (200 27522 application/json; charset=utf-8)
```
{"board":"str","version":"int","serverTs":"int","entries":["<30 itens>",{"m":"str(44)","c":"str","n":"str","t":"str","i":"str(100)","mc":"float","v":"float","vUsd":"float","p":"float","v5":"float","v15":"float","v1h":"float","v24h":"float","vUsd5":"float","vUsd15":"float","vUsd1h":"float","vUsd24h":"float","tx5":"int","age":"int","kol":"int","sn":"int","mh":"bool","hs":"bool","pg":"str","pl":"str","gd":"int","ath":"float","bc":"int","sc":"int","txc":"int","nh":"int","t10":"int","dh":"int","tw":"bool","ws":"bool","tg":"bool","cb":"bool","dw":"str(44)","lv":"bool","np":"int","ic":"bool","so":"int","bo":"int","pa":"str","ih":"bool","tf":"float","tfUsd":"float","desc":"str(247)","rid":"str(36)"}]}
```

### indexer_in_memory_coin (200 1712 application/json; charset=utf-8)
```
{"mint":"str(44)","chain":"str","name":"str","ticker":"str","dev":"str(44)","program":"str","platform":"str","creationTime":"int","quoteMint":"str(32)","pair":"str","marketCapUsd":"float","volumeSol":"float","volumeUsd":"float","progress":"float","graduationDate":"int","athMarketCapUsd":"float","currentMarketPrice":"int","sniperCount":"int","numKolsTraded":"int","txCount":"int","buyCount":"int","sellCount":"int","priorityFeeSol":"float","priorityFeeUsd":"float","builderTipSol":"int","builderTipUsd":"int","tradingAppFeeSol":"int","tradingAppFeeUsd":"int","builderTipSolV2":"float","builderTipUsdV2":"float","tradingAppFeeSolV2":"float","tradingAppFeeUsdV2":"float","txFeeSolV2":"float","txFeeUsdV2":"float","feeSeedSol":"int","feeSeedUsd":"int","isMayhemMode":"bool","mayhemState":"null","mayhemMode":"null","mayhemBotCoinSupplied":"int","isCashbackEnabled":"bool","isCurrentlyLive":"bool","numLiveParticipants":"int","isCharity":"bool","isNsfw":"bool","isBanned":"bool","imageUrl":"str(104)","description":"str(35)","videoUri":"str","hasSocial":"bool","hasTwitter":"bool","hasWebsite":"bool","hasTelegram":"bool","twitterReuseCount":"int","telegramReuseCount":"int","websiteReuseCount":"int","numHolders":"int","top10HoldersPercent":"float","devHoldingsPercent":"int","snipersOwnedPercent":"int","bundlerOwnedPercentageV2":"int","coinCreatedSupply":"int","lastRecommendedAt":"int","totalFees":"float","totalFeesUSD":"float"}
```

### indexer_root (200 12 text/html; charset=utf-8)
```
Hello World!
```

### king_of_the_hill (404 181 application/json; charset=utf-8)
```
{"statusCode":"int","timestamp":"str(24)","path":"str(40)","message":"str(41)","error":"str"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":404,"timestamp":"2026-09-12T05:28:48.060Z","path":"/coins/king-of-the-hill?includeNsfw=true","message":"Coin not found for mint: king-of-the-hill","error":"Not Found"}

### livestream_root (404 86 application/json; charset=utf-8)
```
{"message":"str(35)","error":"str","statusCode":"int"}
```
resposta de erro (crua, sem dados pessoais): {"message":"Cannot GET /livestream/playlist-map","error":"Not Found","statusCode":404}

### mayhem_top_coins (200 5128 application/json; charset=utf-8)
```
{"window":"str","items":["<50 itens>",{"rank":"int","mint":"str(44)","netUsdDeployed":"float"}],"updatedAt":"int"}
```

### mayhem_top_traders (200 8373 application/json; charset=utf-8)
```
{"window":"str","items":["<50 itens>",{"rank":"int","address":"str(44)","realisedPnlUsd":"float","winRate":"float","volumeUsd":"float","tradeCount":"int"}],"updatedAt":"int"}
```

### metas_current_legacy (404 139 application/json; charset=utf-8)
```
{"statusCode":"int","timestamp":"str(24)","path":"str","message":"str(25)","error":"str"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":404,"timestamp":"2026-09-12T05:33:18.470Z","path":"/metas/current","message":"Cannot GET /metas/current","error":"Not Found"}

### pnl_leaderboard (400 205 application/json; charset=utf-8)
```
{"statusCode":"int","timestamp":"str(24)","path":"str(35)","message":["<1 itens>","str(66)"],"error":"str"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":400,"timestamp":"2026-09-12T05:28:36.919Z","path":"/pnl-leaderboard?period=24h&limit=5","message":["period must be one of the following values: daily, weekly, monthly"],"error":"Bad Request"}

### pnl_leaderboard_daily (200 6537 application/json; charset=utf-8)
```
{"entries":["<5 itens>",{"rank":"int","walletAddress":"str(44)","pnlSol":"float","pnlUsd":"float","pnlPercent":"float","buySpendSol":"float","lastRefreshedAtMs":"int","realizedPnlSol":"float","realizedPnlUsd":"float","unrealizedPnlSol":"float","unrealizedPnlUsd":"float","positionsCount":"int","topPositions":["<3 itens>",{"mint":"str(44)","chainId":"int","symbol":"str","name":"str","imageUri":"str(69)"}],"username":"str","profileImage":"str(126)","xUsername":"null","isVerified":"bool","verifiedBadgeVisible":"bool","userId":"str(36)"}],"periodType":"int","periodLabel":"str","windowStartSec":"int"}
```

### profile_balance_summary (404 78 application/json; charset=utf-8)
```
{"message":"str(27)","error":"str","statusCode":"int"}
```
resposta de erro (crua, sem dados pessoais): {"message":"Cannot GET /balance/summary","error":"Not Found","statusCode":404}

### replies_legacy (404 251 application/json; charset=utf-8)
```
{"statusCode":"int","timestamp":"str(24)","path":"str(70)","message":"str(81)","error":"str"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":404,"timestamp":"2026-09-12T05:33:11.201Z","path":"/replies/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK?limit=5&offset=0","message":"Cannot GET /replies/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK?limit=5&offset=0","error":"Not Found"}

### rpc_proxy_gethealth (200 38 application/json)
```
{"jsonrpc":"str","result":"str","id":"int"}
```

### search_unrestricted_live (200 15180 application/json; charset=utf-8)
```
["<5 itens>",{"mint":"str(44)","initialized":"bool","name":"str","symbol":"str","description":"str(118)","image_uri":"str(80)","metadata_uri":"str(80)","twitter":"str(33)","bonding_curve":"str(44)","associated_bonding_curve":"str(44)","creator":"str(44)","created_timestamp":"int","complete":"bool","virtual_sol_reserves":"int","virtual_token_reserves":"int","total_supply":"int","website":"str(31)","show_name":"bool","last_trade_timestamp":"int","market_cap":"float","nsfw":"bool","inverted":"bool","banner_uri":"str(80)","is_banned":"bool","pump_swap_pool":"str(44)","real_sol_reserves":"int","real_token_reserves":"int","updated_at":"int","livestream_ban_expiry":"int","last_reply":"int","reply_count":"int","is_currently_live":"bool","ath_market_cap":"float","ath_market_cap_timestamp":"int","hide_banner":"bool","program":"str","token_program":"str(43)","quote_mint":"str(43)","base_decimals":"int","quote_decimals":"int","is_cashback_enabled":"bool","chain_id":"str(39)","multichain_family":"int","protocol":"str","total_supply_str":"str","market_cap_usd":"float","virtual_quote_reserves":"int","real_quote_reserves":"int","market_cap_quote":"float","boost_mode":"str","verified":"bool","usd_market_cap":"float","thumbnail":"str(101)","thumbnail_updated_at":"int","num_participants":"int","volume_1h_usd":"int","playlist_url":"str(128)","playlist_url_high":"str(128)","playlist_url_low":"str(128)","vod_playlist_url":"str(128)","playlist_status":"str","playlist_updated_at":"str(24)","recommendation_id":"str(36)","recommendation_rank":"int","telegram":"str(28)","pool_address":"str(44)","quote_token_program":"str(43)","security_verdict":{"verdict":"str","scope":"str","reasons":["<1 itens>","str"],"decided_by":"str","provider":"str","version":"int","updated_at":"int","source":"str"}}]
```

### sol_price (200 75 application/json; charset=utf-8)
```
{"solPrice":"float","asOfTimestamp":"int","stale":"bool"}
```

### swap_ath (200 34 application/json; charset=utf-8)
```
{"athMarketCap":"float"}
```

### swap_candles (200 13306 application/json; charset=utf-8)
```
["<60 itens>",{"timestamp":"int","open":"str(30)","high":"str(30)","low":"str(30)","close":"str(30)","volume":"str(23)"}]
```

### swap_candles_5m (200 1114 application/json; charset=utf-8)
```
["<5 itens>",{"timestamp":"int","open":"str(30)","high":"str(30)","low":"str(30)","close":"str(30)","volume":"str(22)"}]
```

### swap_candles_bad_interval (400 308 application/json; charset=utf-8)
```
{"statusCode":"int","message":"str(133)","error":"str","path":"str(94)"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":400,"message":"{\"message\":[\"interval must be one of : 1s, 15s, 30s, 1m, 5m, 15m, 30m, 1h, 4h, 6h, 12h, 24h\"],\"error\":\"Bad Request\",\"statusCode\":400}","error":"BadRequestException","path":"/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/candles?createdTs=0&interval=7s&limit=5"}

### swap_candles_limit1000 (200 24185 application/json; charset=utf-8)
```
["<109 itens>",{"timestamp":"int","open":"str(30)","high":"str(30)","low":"str(30)","close":"str(30)","volume":"str(22)"}]
```

### swap_creators_unified_totals (404 195 application/json; charset=utf-8)
```
{"statusCode":"int","message":"str(89)","error":"str","path":"str(27)"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":404,"message":"{\"message\":\"Cannot GET /v2/creators/unified-totals\",\"error\":\"Not Found\",\"statusCode\":404}","error":"NotFoundException","path":"/v2/creators/unified-totals"}

### swap_fee_sharing_totals (200 894 application/json; charset=utf-8)
```
{"shareholderClaimedByQuoteMint":["<3 itens>",{"quoteMintAddress":"str(32)","atomic":"str","quote":"str","usd":"str"}],"shareholderUnclaimedByQuoteMint":[],"shareholderTotalEarnedByQuoteMint":["<3 itens>",{"quoteMintAddress":"str(32)","atomic":"str","quote":"str","usd":"str"}],"shareholderClaimedUSD":"str","shareholderClaimedSOL":"str","shareholderUnclaimedUSD":"str","shareholderUnclaimedSOL":"str","shareholderTotalEarnedUSD":"str","shareholderTotalEarnedSOL":"str","mintCount":"int"}
```

### swap_first_trade (200 657 application/json; charset=utf-8)
```
{"slotIndexId":"str(26)","tx":"str(88)","timestamp":"str(24)","userAddress":"str(44)","type":"str","program":"str","priceUsd":"str(30)","priceSol":"str(30)","amountUsd":"str(21)","amountSol":"str(29)","baseAmount":"str","quoteAmount":"str","fillPriceUsd":"str(47)","fillPriceSol":"str(49)","isDevBuy":"bool"}
```

### swap_line_chart (200 5824 application/json; charset=utf-8)
```
["<108 itens>",{"time":"int","price":"float"}]
```

### swap_market_activity (200 958 application/json; charset=utf-8)
```
{"5m":{"numTxs":"int","volumeUSD":"float","numUsers":"int","numBuys":"int","numSells":"int","buyVolumeUSD":"float","sellVolumeUSD":"float","numBuyers":"int","numSellers":"int","priceChangePercent":"float"},"1h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","numBuys":"int","numSells":"int","buyVolumeUSD":"float","sellVolumeUSD":"float","numBuyers":"int","numSellers":"int","priceChangePercent":"float"},"6h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","numBuys":"int","numSells":"int","buyVolumeUSD":"float","sellVolumeUSD":"float","numBuyers":"int","numSellers":"int","priceChangePercent":"float"},"24h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","numBuys":"int","numSells":"int","buyVolumeUSD":"float","sellVolumeUSD":"float","numBuyers":"int","numSellers":"int","priceChangePercent":"float"}}
```

### swap_market_activity_batch (201 729 application/json; charset=utf-8)
```
{"8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK":{"5m":{"numTxs":"int","volumeUSD":"float","numUsers":"int","priceChangePercent":"float"},"1h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","priceChangePercent":"float"},"24h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","priceChangePercent":"float"}},"BwnxzfgFyX3mth7RKMUghunKRDJqgykUXe2bVZwGpump":{"5m":{"numTxs":"int","volumeUSD":"float","numUsers":"int","priceChangePercent":"float"},"1h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","priceChangePercent":"float"},"24h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","priceChangePercent":"float"}}}
```

### swap_market_activity_pump (200 906 application/json; charset=utf-8)
```
{"5m":{"numTxs":"int","volumeUSD":"float","numUsers":"int","numBuys":"int","numSells":"int","buyVolumeUSD":"float","sellVolumeUSD":"float","numBuyers":"int","numSellers":"int","priceChangePercent":"float"},"1h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","numBuys":"int","numSells":"int","buyVolumeUSD":"float","sellVolumeUSD":"float","numBuyers":"int","numSellers":"int","priceChangePercent":"float"},"6h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","numBuys":"int","numSells":"int","buyVolumeUSD":"float","sellVolumeUSD":"float","numBuyers":"int","numSellers":"int","priceChangePercent":"float"},"24h":{"numTxs":"int","volumeUSD":"float","numUsers":"int","numBuys":"int","numSells":"int","buyVolumeUSD":"float","sellVolumeUSD":"float","numBuyers":"int","numSellers":"int","priceChangePercent":"float"}}
```

### swap_mayhem_stats (200 98 application/json; charset=utf-8)
```
{"buyCount":"int","sellCount":"int","totalBuyVolumeSol":"str","totalSellVolumeSol":"str","netSolDeployed":"str"}
```

### swap_old_candles_1d (400 311 application/json; charset=utf-8)
```
{"statusCode":"int","message":"str(133)","error":"str","path":"str(97)"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":400,"message":"{\"message\":[\"interval must be one of : 1s, 15s, 30s, 1m, 5m, 15m, 30m, 1h, 4h, 6h, 12h, 24h\"],\"error\":\"Bad Request\",\"statusCode\":400}","error":"BadRequestException","path":"/v2/coins/69LjZUUzxj3Cb3Fxeo1X4QpYEQTboApkhXTysPpbpump/candles?createdTs=0&interval=1d&limit=1000"}

### swap_old_candles_1h (200 222696 application/json; charset=utf-8)
```
["<1000 itens>",{"timestamp":"int","open":"str(30)","high":"str(30)","low":"str(30)","close":"str(30)","volume":"str(27)"}]
```

### swap_old_candles_1m (200 219095 application/json; charset=utf-8)
```
["<1000 itens>",{"timestamp":"int","open":"str(30)","high":"str(30)","low":"str(30)","close":"str(30)","volume":"str(22)"}]
```

### swap_old_first_trade (200 659 application/json; charset=utf-8)
```
{"slotIndexId":"str(22)","tx":"str(87)","timestamp":"str(24)","userAddress":"str(44)","type":"str","program":"str","priceUsd":"str(46)","priceSol":"str(49)","amountUsd":"str(26)","amountSol":"str","baseAmount":"str","quoteAmount":"str","fillPriceUsd":"str(47)","fillPriceSol":"str(49)","isDevBuy":"bool"}
```

### swap_root (200 12 text/html; charset=utf-8)
```
Hello World!
```

### swap_trades (200 19012 application/json; charset=utf-8)
```
{"trades":["<30 itens>",{"slotIndexId":"str(26)","tx":"str(88)","timestamp":"str(24)","userAddress":"str(44)","type":"str","program":"str","priceUsd":"str(30)","priceSol":"str(30)","amountUsd":"str","amountSol":"str(30)","baseAmount":"str","quoteAmount":"str","fillPriceUsd":"str(45)","fillPriceSol":"str(46)"}],"pagination":{"nextCursor":"str(40)","hasMore":"bool","limit":"int"}}
```

### swap_trades_batch_post (201 6548 application/json; charset=utf-8)
```
{"2XwmK62bxyFkVrz2zSf7zfEdrKJ3tiGXzCqvPM6inkj3":["<13 itens>",{"slotIndexId":"str(26)","tx":"str(88)","timestamp":"str(24)","userAddress":"str(44)","type":"str","isBondingCurve":"bool","priceUSD":"str(30)","priceSOL":"str(30)","amountUSD":"str","amountSOL":"str(29)","baseAmount":"str","quoteAmount":"str"}]}
```

### swap_trades_cursor (200 3255 application/json; charset=utf-8)
```
{"trades":["<5 itens>",{"slotIndexId":"str(26)","tx":"str(88)","timestamp":"str(24)","userAddress":"str(44)","type":"str","program":"str","priceUsd":"str(30)","priceSol":"str(30)","amountUsd":"str","amountSol":"str(30)","baseAmount":"str","quoteAmount":"str","fillPriceUsd":"str(45)","fillPriceSol":"str(47)"}],"pagination":{"nextCursor":"str(40)","hasMore":"bool","limit":"int"}}
```

### swap_trades_limit1000 (400 242 application/json; charset=utf-8)
```
{"statusCode":"int","message":"str(89)","error":"str","path":"str(72)"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":400,"message":"{\"message\":[\"limit must not be greater than 100\"],\"error\":\"Bad Request\",\"statusCode\":400}","error":"BadRequestException","path":"/v2/coins/8WgQ9XpJYCfnwmSmMTdVioUuxxwnMdYuRvSn9osXSTNK/trades?limit=1000"}

### token_holders_count (200 114 application/json; charset=utf-8)
```
{"mint":"str(44)","chain":"str","networkId":"int","holderCount":"int"}
```

### top_holders (200 4204 application/json; charset=utf-8)
```
{"topHolders":["<50 itens>",{"address":"str(44)","amount":"float"}],"totalHolders":"int"}
```

### top_tokens_mints (200 23279 application/json; charset=utf-8)
```
["<502 itens>","str(43)"]
```

### trades_latest_legacy (404 139 application/json; charset=utf-8)
```
{"statusCode":"int","timestamp":"str(24)","path":"str","message":"str(25)","error":"str"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":404,"timestamp":"2026-09-12T05:33:14.859Z","path":"/trades/latest","message":"Cannot GET /trades/latest","error":"Not Found"}

### user_positions (400 292 application/json; charset=utf-8)
```
{"statusCode":"int","timestamp":"str(24)","path":"str(77)","message":["<3 itens>","str(36)"],"error":"str"}
```
resposta de erro (crua, sem dados pessoais): {"statusCode":400,"timestamp":"2026-09-12T05:33:07.652Z","path":"/user-positions/2CtDrkiHnoqx9eqARCZCxtygMhAYmPPXD8AA59EdcC7Z?limit=5&offset=0","message":["each value in mints must be a string","mints must contain no more than 200 elements","mints should not be empty"],"error":"Bad Request"}

### user_positions_mints (200 541 application/json; charset=utf-8)
```
{"positions":["<1 itens>",{"coinMint":"str(44)","chainId":"int","isExited":"bool","walletAddress":"str(44)","amountHeld":"int","pnlUsd":"float","pnlPercentage":"float","costBasisAmount":"int","costBasisUsd":"int","amountBoughtUsd":"float","amountBought":"float","callout":"null","hasTransfers":"bool","likelyLost":"bool","valueUsd":"int","tokenPriceUsd":"float","realizedPnlUsd":"float","updatedAt":"str(24)"}]}
```

### users_creator (200 418 application/json; charset=utf-8)
```
{"address":"str(44)","userId":"str(36)","is_pump_user":"bool","username":"str","profile_image":"null","header_image_url":"null","kind":"str","member_count":"int","last_username_update_timestamp":"null","following":"int","followers":"int","bio":"null","x_username":"null","canonical_svm_wallet":"str(44)","group_badges":[]}
```


### Valores numéricos citados no documento (crus)

- `sol_price`: `{"solPrice":101.49009519217667,"asOfTimestamp":1789190893999,"stale":false}`
- `global_params_ts` (`/global-params/1789184732000`): `{"slot":354155511,"signature":"<88 chars>","initial_virtual_token_reserves":1073000000000000,"initial_virtual_sol_reserves":30000000000,"initial_virtual_quote_reserves":4292000000,"initial_real_token_reserves":793100000000000,"token_total_supply":1000000000000000,"fee_basis_points":95,"timestamp":1752856476446}`
- `token_holders_count`: `{"mint":"8WgQ9…STNK","chain":"solana","networkId":1399811149,"holderCount":1058}`; `top_holders.totalHolders`: 1055
- `coins_v2_mayhem_state`: `{"mint":"972N…pump","state":"paused","mode":"auto","pause_reason":"below_initial_buy_floor"}`
- `swap_ath`: `{"athMarketCap":333792.7312445948}`; `swap_mayhem_stats`: `{"buyCount":0,"sellCount":0,"totalBuyVolumeSol":"0","totalSellVolumeSol":"0","netSolDeployed":"0"}`
- `swap_trades.pagination`: `{"nextCursor":"<slotIndexId>-<ms>","hasMore":true,"limit":30}`; `limit=1000` → 400 `limit must not be greater than 100`
- candles: `interval=1d`/`7s` → 400 `interval must be one of : 1s, 15s, 30s, 1m, 5m, 15m, 30m, 1h, 4h, 6h, 12h, 24h`; coin antiga (`69Lj…pump`, first-trade 2025-04-24T20:14:58Z): `1m&limit=1000` → 1000 candles de 1789027440000 a 1789190400000; `1h&limit=1000` → 1000 candles de 1783501200000 a 1789189200000; coin de 2 h (`8WgQ…STNK`): `1m&limit=1000` → 109 candles
- `indexer_boards_movers`: `{"board":"movers","version":0,"serverTs":1789191239339,"entries":[30]}`
- `indexer_in_memory_coin` (coin com 5 min): `progress:3.5, graduationDate:0, sniperCount:0, marketCapUsd:2991.89, volumeSol:6.09`
- `rpc_proxy_gethealth`: `{"jsonrpc":"2.0","result":"ok","id":1}`
- `bswap_swap_build_empty` (POST `{}`): 422 `Failed to deserialize the JSON body into the target type: missing field 'mint' at line 1 column 2`
- `advanced_root`: 530 `error code: 1016`; `swap_root`/`indexer_root`: `Hello World!`
- `pnl_leaderboard` com `period=24h`: 400 `period must be one of the following values: daily, weekly, monthly`
- `user_positions` sem `mints`: 400 `each value in mints must be a string; mints must contain no more than 200 elements; mints should not be empty`
- rotas v1 em v3: `/coins/king-of-the-hill` e `/coins/latest` → 404 `Coin not found for mint: …`; `/candlesticks/{mint}`, `/replies/{mint}`, `/trades/latest`, `/metas/current` → 404 `Cannot GET …`

### Estatísticas da amostra (10 páginas, 02:32:41 + 02:36:29–02:37:10 BRT)

```
pages 10 raw items 700 unique mints 653
created span (min): 40.6 oldest age (min): 45.2 newest age (min): 4.6
creation rate (coins/min over span): 16.1
complete: {False: 619, True: 34}
mayhem_state: {None: 391, 'paused': 201, 'completed': 47, 'active': 11, 'enabled': 3}
is_currently_live: {False: 652, True: 1}; nsfw: {False: 637, True: 16}; is_banned: {False: 653}
program/protocol: pump 653
quote_mint: SOL 579, USDC(EPjF…) 17, None 10, XsbE… 6, XsqE… 4, 3NZ9… 4, …
boost_mode: {NONE: 627, COMPLETED: 21, IN_PROGRESS: 5}
real_sol_reserves>0: {True: 587, False: 66}; last_trade_timestamp: {True: 603, False: 50}
website/twitter/telegram: 162 / 248 / 12; verified: 0; is_cashback_enabled: 106
usd_market_cap: min 1 p10 212 p25 1404 median 2841 p75 2966 p90 4822 p99 7088635 max 718310231
  [0,4k): 551  [4k,5k): 44  [5k,7k): 24  [7k,10k): 9  [10k,20k): 5  [20k,50k): 1  [50k,+): 19
real_sol_reserves SOL: median 0.0 p75 0.01 p90 0.248 p99 85.005 max 205.464
curve progress (SOL-quoted, n 579): median 0 % p90 12.84 % max 100 %
creators unique 252; top creator 35 coins; "Deployed using" in description: 40
complete=true listing (70): all created < 1.66 h ago; 44 within 1 h; pool_address set 70/70;
  usd_market_cap min 0 / median 2522 / max 715342864
sort=market_cap top 5 (usd): 925002420, 719665015, 469049024, 393276104, 345801471 (all complete)
search-unrestricted currentlyLive top 5 (usd): 42877, 41732, 15432, 7228, 5785
```

## 5. WebSockets — saída crua redigida

### 5.1 PumpPortal (02:27:24–02:27:55 BRT, sem chave)

```
connected t=0.64s resp_headers={'server': 'nginx/1.22.1', 'date': 'Sat, 12 Sep 2026 05:27:25 GMT', 'connection': 'upgrade', 'upgrade': 'websocket', 'sec-websocket-accept': 'saRxg3C9mlrDhZKZT2NDqyA47Tg='}
closed after t=30.01s
counts: {"Successfully subscribed to token creation events.": 1, "Subscribed to 'migration' events.": 1, "create": 6} first_at: {"Successfully subscribed to token creation events.": 0.76, "Subscribed to 'migration' events.": 0.89, "create": 3.73}
sample[Successfully subscribed to token creation events.] shape: {"message": "str(len=49)"}
sample[Subscribed to 'migration' events.] shape: {"message": "str(len=33)"}
sample[create] shape: {"signature": "str(len=88)", "mint": "str(len=43)", "traderPublicKey": "str(len=44)", "txType": "str:create", "initialBuy": "float:8780451.425543", "solAmount": "float:0.247518046", "bondingCurveKey": "str(len=44)", "vTokensInBondingCurve": "float:1064219548.574457", "vSolInBondingCurve": "float:30.247518045612992", "marketCapSol": "float:28.422253740903496", "name": "str:Co-Caine", "symbol": "str:COKE", "uri": "str(len=67)", "is_mayhem_mode": "bool:False", "pool": "str:pump"}
```

### 5.2 advanced-indexer `/ws/trenches` (02:35:55–02:36:26 BRT, board movers)

```
connected t=0.72s url=wss://advanced-indexer.pump.fun/ws/trenches?subscription=%7B%22board%22%3A%22movers%22%2C%22tier%22%3A%22web%22%2C%22fil...
closed after t=30.01s bytes=180470
counts: {"snapshot": 3, "delta": 50} patch_ops: {"update": 418}
sample[snapshot] shape: {"type": "str", "board": "str", "version": "int", "serverTs": "int", "entries": ["<5 items>", {"m": "str(44)", "c": "str", "n": "str", "t": "str", "i": "str(100)", "mc": "float", "v": "float", "vUsd": "float", "p": "float", "v5": "float", "v15": "float", "v1h": "float", "v24h": "float", "vUsd5": "float", "vUsd15": "float", "vUsd1h": "float", "vUsd24h": "float", "tx5": "int", "age": "int", "kol": "int", "sn": "int", "mh": "bool", "hs": "bool", "pg": "str", "pl": "str", "gd": "int", "ath": "float", "bc": "int", "sc": "int", "txc": "int", "nh": "int", "t10": "int", "dh": "int", "tw": "bool", "ws": "bool", "tg": "bool", "cb": "bool", "dw": "str(44)", "lv": "bool", "np": "int", "ic": "bool", "so": "int", "bo": "int", "pa": "str", "ih": "bool", "tf": "float", "tfUsd": "float", "desc": "str(247)"}]}
sample[delta] shape: {"type": "str", "board": "str", "baseVersion": "int", "version": "int", "serverTs": "int", "patches": ["<15 items>", {"op": "str", "mint": "str(43)", "fields": {"mc": "float", "v": "float", "vUsd": "float", "v5": "float", "v15": "float", "v1h": "float", "tx5": "int", "v24h": "float", "vUsd24h": "float", "bc": "int", "sc": "int", "txc": "int", "nh": "int", "tf": "float", "tfUsd": "float", "rid": "str(36)"}}]}
```

### 5.3 NATS (02:34:13 BRT, só INFO)

```
connected 0.78 s
INFO: {"server_name": "nats-8559c65b", "version": "2.12.11", "proto": 1, "headers": true, "auth_required": true, "max_payload": 524288, "client_ip": "<redacted>", "connect_urls": ["10.0.x.x:9222" x8]}
```

## 6. Páginas oficiais — texto extraído

### 6.1 `https://pump.fun/docs/fees` (lido 02:18:46 BRT)

```
Last Updated: 20 May 2026
The following are fees charged by the pump.fun platform when you use the pump.fun platform:
Action | Fee |
Create a coin | 0 SOL / 0 USDC |
When a coin graduates from the pump.fun platform to PumpSwap* | 0.015 SOL |
On every trade the creator receives some portion of the total fees. This is referred to as the "Creator fee" and is applicable for all coins that were present on the bonding curve or PumpSwap from the date of May 13th 2025. The fee that goes to the pump.fun platform is referred to as the "Protocol fee". A portion of the fees also goes back to the pool in the form of liquidity - this is referred to as the "LP fee".
As of May 21, 2026, token creators can use USDC as the paired token for their launched token instead of SOL. The fees for USDC tokens varies slightly from the fees for SOL tokens. Both sets of fees are described here.
The bonding curve fees are as follows for both USDC and SOL tokens:
Creator fee | Protocol fee | LP fee | Total fee |
0.300% | 0.95% | 0% | 1.25% |
Coins that launched on the pump.fun platform and have graduated have an associated pool on PumpSwap. This pool is referred to as the "canonical pool". PumpSwap fees for canonical pools vary depending on the SOL or USDC priced market cap of a coin. The market cap is calculated as the current price of the token in SOL or USDC multiplied by 1 billion tokens. The fee schedule for SOL denominated tokens is as follows:
Market cap | Creator fee | Protocol fee | LP fee | Total fees |
0 - 420 SOL | 0.300% | 0.930% | 0.020% | 1.250% |
420 - 1470 SOL | 0.950% | 0.050% | 0.200% | 1.200% |
1470 - 2460 SOL | 0.900% | 0.050% | 0.200% | 1.150% |
2460 - 3440 SOL | 0.850% | 0.050% | 0.200% | 1.100% |
3440 - 4420 SOL | 0.800% | 0.050% | 0.200% | 1.050% |
4420 - 9820 SOL | 0.750% | 0.050% | 0.200% | 1.000% |
9820 - 14740 SOL | 0.700% | 0.050% | 0.200% | 0.950% |
14740 - 19650 SOL | 0.650% | 0.050% | 0.200% | 0.900% |
19650 - 24560 SOL | 0.600% | 0.050% | 0.200% | 0.850% |
24560 - 29470 SOL | 0.550% | 0.050% | 0.200% | 0.800% |
29470 - 34380 SOL | 0.500% | 0.050% | 0.200% | 0.750% |
34380 - 39300 SOL | 0.450% | 0.050% | 0.200% | 0.700% |
39300 - 44210 SOL | 0.400% | 0.050% | 0.200% | 0.650% |
44210 - 49120 SOL | 0.350% | 0.050% | 0.200% | 0.600% |
49120 - 54030 SOL | 0.300% | 0.050% | 0.200% | 0.550% |
54030 - 58940 SOL | 0.275% | 0.050% | 0.200% | 0.525% |
58940 - 63860 SOL | 0.250% | 0.050% | 0.200% | 0.500% |
63860 - 68770 SOL | 0.225% | 0.050% | 0.200% | 0.475% |
68770 - 73681 SOL | 0.200% | 0.050% | 0.200% | 0.450% |
73681 - 78590 SOL | 0.175% | 0.050% | 0.200% | 0.425% |
78590 - 83500 SOL | 0.150% | 0.050% | 0.200% | 0.400% |
83500 - 88400 SOL | 0.125% | 0.050% | 0.200% | 0.375% |
88400 - 93330 SOL | 0.100% | 0.050% | 0.200% | 0.350% |
93330 - 98240 SOL | 0.075% | 0.050% | 0.200% | 0.325% |
98240 SOL and up | 0.050% | 0.050% | 0.200% | 0.300% |
For USDC denominated tokens, the fee schedule is as follows:
Market cap | Creator fee | Protocol fee | LP fee | Total fees |
0 - 59000 USDC | 0.300% | 0.930% | 0.020% | 1.250% |
59000 - 100000 USDC | 0.950% | 0.050% | 0.200% | 1.200% |
100000 - 200000 USDC | 0.950% | 0.050% | 0.200% | 1.200% |
200000 - 300000 USDC | 0.950% | 0.050% | 0.200% | 1.200% |
300000 - 400000 USDC | 0.900% | 0.050% | 0.200% | 1.150% |
400000 - 500000 USDC | 0.900% | 0.050% | 0.200% | 1.150% |
500000 - 600000 USDC | 0.850% | 0.050% | 0.200% | 1.100% |
600000 - 700000 USDC | 0.850% | 0.050% | 0.200% | 1.100% |
700000 - 800000 USDC | 0.800% | 0.050% | 0.200% | 1.050% |
800000 - 900000 USDC | 0.800% | 0.050% | 0.200% | 1.050% |
900000 - 1000000 USDC | 0.750% | 0.050% | 0.200% | 1.000% |
1000000 - 2000000 USDC | 0.750% | 0.050% | 0.200% | 1.000% |
2000000 - 3000000 USDC | 0.700% | 0.050% | 0.200% | 0.950% |
3000000 - 4000000 USDC | 0.650% | 0.050% | 0.200% | 0.900% |
4000000 - 5000000 USDC | 0.600% | 0.050% | 0.200% | 0.850% |
5000000 - 6000000 USDC | 0.550% | 0.050% | 0.200% | 0.800% |
6000000 - 7000000 USDC | 0.500% | 0.050% | 0.200% | 0.750% |
7000000 - 8000000 USDC | 0.450% | 0.050% | 0.200% | 0.700% |
8000000 - 9000000 USDC | 0.400% | 0.050% | 0.200% | 0.650% |
9000000 - 10000000 USDC | 0.350% | 0.050% | 0.200% | 0.600% |
10000000 - 11000000 USDC | 0.300% | 0.050% | 0.200% | 0.550% |
11000000 - 12000000 USDC | 0.280% | 0.050% | 0.200% | 0.530% |
12000000 - 13000000 USDC | 0.250% | 0.050% | 0.200% | 0.500% |
13000000 - 14000000 USDC | 0.230% | 0.050% | 0.200% | 0.480% |
14000000 - 15000000 USDC | 0.200% | 0.050% | 0.200% | 0.450% |
15000000 - 16000000 USDC | 0.180% | 0.050% | 0.200% | 0.430% |
16000000 - 17000000 USDC | 0.150% | 0.050% | 0.200% | 0.400% |
17000000 - 18000000 USDC | 0.130% | 0.050% | 0.200% | 0.380% |
18000000 - 19000000 USDC | 0.100% | 0.050% | 0.200% | 0.350% |
19000000 - 20000000 USDC | 0.080% | 0.050% | 0.200% | 0.330% |
20000000 USDC and up | 0.050% | 0.050% | 0.200% | 0.300% |
For all other PumpSwap pools that are non-canonical the fees are as follows:
Creator fee | Protocol fee | LP fee | Total fee |
0% | 0.05% | 0.25% | 0.3% |
Note that none of the pump.fun frontend services (the pump.fun web app, pump.fun/advanced, and the pump.fun mobile app*) charge any fees in addition to those above. If you access the pump.fun platform or smart contracts via another interface or platform, you may incur additional fees charged by those interfaces or platforms.
*Pump.fun is modifying some of its fees for some mobile users. Some users may experience fee increases of up to .1% on certain transactions. These additional fees may be paid to coin creators, or coin fee owners if there has been a community take over with respect to that coin, or may be paid back to the user or the referrer of the user. The Creator Fee portion of the fees may also be paid to charities, if the token creator opts into this feature. See our charitable token terms for additional information.
These fees may not be separately stated in the total transaction cost. These fees do not include fees charged by third parties which the pump.fun platform does not control, such as fees charged by wallet software or fees charged by the blockchain network (i.e. "gas" fees). The fees applicable to any transaction are determined pump.fun smart contracts, and although these fees are displayed by the pump.fun web or mobile app as accurately as possible, there is no guarantee that the transaction fee(s) listed in the web or mobile app will exactly match those charged by the smart contract. The pump.fun platform may change these fees at any time, without notice.

```

### 6.2 `https://pump.fun/docs/bonding-curve` (02:23 BRT; sem "Last Updated" visível)

Frases usadas no documento: "a deterministic pricing function that quotes a buy and sell price from
on-chain reserves. There is no orderbook, no market-makers, and no off-chain matching."; "constant-product
AMM"; "Once a coin's market cap on the bonding curve hits the graduation threshold, the curve is closed and
the entire liquidity pool is migrated atomically to PumpSwap."; "Graduation is automatic and irreversible.
There's no human step."; "The bonding curve charges a 1.25% total trading fee, split between the coin's
creator and the protocol." A página não publica o número do limiar nem as reservas virtuais.

### 6.3 `https://pump.fun/docs/create-coin` (02:40:48 BRT)

"Anyone can launch a coin in under a minute. There's no liquidity to seed, no presale, and no team
allocation. Coins are immediately tradable on a transparent bonding curve, and graduate to PumpSwap once
they reach the market-cap threshold."; "There is no fee to create a coin on Pump.fun."; "Name, symbol, and
image are immutable. They're part of the SPL token metadata."

### 6.4 PumpPortal (02:19–02:20 BRT) — trechos exatos

- `/local-trading-api/trading-api/`: "To get a transaction for signing and sending with a custom RPC, send a POST request to https://pumpportal.fun/api/trade-local"; campos `publicKey, action, mint, amount, denominatedInSol, slippage, priorityFee, pool`; "If your parameters are valid, you will receive a serialized transaction in response."
- `/trading-api/` (Lightning): `POST https://pumpportal.fun/api/trade?api-key=…`; campos extras `skipPreflight` (default "true"), `jitoOnly`; resposta = assinatura ou erros.
- `/fees/`: "Effective May 1, 2026: Trading data is only available to users who subscribe with a PumpPortal API key."; "There is no charge for data received from the subscribeNewToken and subscribeMigration methods."; "every 10000 trades streamed will incur a 0.01 SOL charge"; "We take a 0.5% fee on each Local trade."; "We take a 1% fee on each Lightning trade."; "The above fees do not include Solana network fees, or any fees charged by the Pump.fun bonding curve."
- `/data-api/real-time/`: métodos `subscribeNewToken` (Free), `subscribeMigration` (Free), `subscribeTokenTrade`, `subscribeAccountTrade` (Metered at 0.01 SOL per 10000 events), `unsubscribe*`; "requires a PumpPortal API key and linked wallet funded with at least 0.02 SOL"; "PLEASE ONLY USE ONE WEBSOCKET CONNECTION AT A TIME".
- `/FAQ/`: "Trading and other endpoints are limited at 25 requests per second."; "Don't send over 200 subscription messages per second. Don't subscribe to over 5000 addresses in a single message."; "bans expire every hour"; "Data from the PumpPortal websocket is at the 'processed' commitment level, and will typically be less than 100 msec delayed behind gRPC data if you run a server in New York."; "We only provide live trading data at this time"; "PumpPortal Local Transactions are signed by your code on your device, PumpPortal never has access to your wallet."; livestream/chat: "this data is not onchain, so it is only accessible from the Pump.fun site directly."
- `/pricing/`: **404** (não existe página de preços separada).

### 6.5 Lista comunitária `github.com/BankkRoll/pumpfun-apis` (02:27:57 e 02:32:28 BRT)

README: "Total Documented Endpoints: 483"; captura HAR de 2026-06-17 com 120 endpoints; afirma "Most
APIs require JWT authentication via Authorization: Bearer <JWT>" — **contradito pelas medições**: as
rotas de leitura testadas responderam 200 sem token. Os arquivos da captura rotulam tudo como
`advanced-api-v2.pump.fun` (host morto hoje, 530/1016) — artefato do `har2api`. As rotas v1
(`/coins/king-of-the-hill`, `/coins/latest`, `/candlesticks`, `/trades/latest`, `/replies`, `/metas`)
da pasta `endpoints/` não existem em v3 (404 medido). Útil como lista de nomes, não como contrato.

## 7. O que ficou de fora / não medido

- 429 e banimento acima de 60/60 s (não testado de propósito). ETag/304. `Origin` obrigatório ou não
  (sempre enviado aqui; em A4.1b as rotas responderam sem ele).
- Boards `new`/`graduating`/`graduated` do indexer (só `movers` chamado — mesma forma esperada).
- `profile-api` (saldos/PnL/holders-PnL), `livestream-api` POST, `POST /v2/creators/unified-totals`,
  `POST /coins/{mint}/ath/batch`, `POST /transactions/swap-build` com corpo válido (não quis montar
  uma transação real), `GET /coins-v3/{mint}` com livestream real.
- Retenção de candles além dos 1 000 mais recentes (sem parâmetro de janela conhecido).
- WS `trenches` com `filters`; `subscribeMigration` não produziu evento em 30 s.
