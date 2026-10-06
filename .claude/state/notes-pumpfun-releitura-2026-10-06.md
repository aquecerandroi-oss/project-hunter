# Notas de pesquisa — releitura da superfície pública da pump.fun (06/10/2026)

Sessão: **05/10/2026 23:22 BRT a 23:56 BRT** (02:22–02:56 UTC do dia 06). Agente `exchange-integration-specialist`.
Brief: reler "por inteiro" a superfície pública depois do upgrade dos programas (02/10) e atualizar `docs/PUMPFUN.md`
(§10). Método da T4.0c (`notes-T4.0c.md`): HTML + bundle `curl`, hosts e rotas por varredura, GET anônimo, ≥ 1 s
entre chamadas. Sem login, sem cookie, sem `.env`, sem POST além de três de leitura (dois do lote `market-activity/batch` e um `POST profile-api /pnl/coin/{mint}/holders` com corpo copiado do bundle, a pedido do orquestrador), sem desafio contornado, sem cabeçalho falsificado (só `User-Agent` de navegador,
`Accept: application/json`, `Origin: https://pump.fun`). Nenhuma resposta bloqueada por Cloudflare (nenhum 403, nenhum
429, nenhum desafio nas chamadas feitas).

Dois métodos separados, com créditos separados:
1. **Leitura do bundle + chamadas `curl`/`websockets` (este agente).**
2. **Observação passiva via REA** (Chrome headless sem login, home + `/leaderboard`, feita pelo orquestrador;
   `rea-pumpfun-capture-2026-10-06.md`; o REA não guarda corpos de resposta). O que só vem do REA está marcado "(REA)".

Dados pessoais: guardo só endereços públicos de carteira (truncados) e números agregados. `username`, `bio`,
`x_username`, imagens e o texto de `callout.thesis` foram lidos durante a análise e **não** foram copiados para o repositório. Os corpos brutos ficaram numa pasta temporária fora do repo
(`C:/Users/evert/AppData/Local/Temp/pf0610/api/`) e **foram apagados ao fim da sessão** (restam cabeçalhos e o log). Os agregados do §3 foram calculados por scripts locais sobre esses corpos (contagens, somas, medianas; somas em `float` do JSON do site, só para descrever, não são contabilidade): união por `walletAddress` das 6 visões; soma de `realizedPnlSol`/`unrealizedPnlSol`; contagem de `isVerified`, `buySpendSol ≤ 0,0001`, sufixo `pump` e `chainId ≠ 1399811149` em `topPositions`; extremos de `timestamp` e duplicatas de `tx` nas 4 páginas de `/user-trades`.

## 1. Orçamento usado

| item | quantidade |
|---|---|
| chamadas de API (`frontend-api-v3` 41, `profile-api` 4 (1 é o `POST /pnl/coin/{mint}/holders`), `swap-api` 3 (2 são o POST de lote), `advanced-indexer` 2) | **53** (os 3 últimos: `/coins/{mint}` × 2 e `/coins-v3/{mint}`, para desfazer a afirmação "sumiu" apontada pela Astra) |
| páginas HTML (home, `/docs/fees`, `/docs`, `/docs/wallet-login-changes`, `pumpportal.fun/fees/`, `fees.pump.fun` → 301 não seguido) | **6** |
| conexões WebSocket de leitura (trenches 15 s, PumpPortal 12 s, 3 handshakes NATS só de leitura do `INFO`) | **5** |
| **total do orçamento (HTTP + WS)** | **64** (acima do "~60": a 61.ª foi o POST de PnL de holders, pedido do orquestrador; 62–64 re-testaram `/coins/{mint}`) |
| fora do orçamento: 101 chunks JS estáticos (`/_next/static/chunks/*`, 7,2 MB, 0,4 s entre arquivos) | 101 |

Códigos HTTP das 53 chamadas de API: 200 × 44, 201 × 3, 400 × 1 (`/candles` com parâmetro errado), 401 × 3, 404 × 2 (`GET /coins/{mint}`, ver §3b)
(`trader-stats`, `social-stats`, `coin-activity`). **Nenhum 429.** Menor `x-ratelimit-remaining` visto: 19 (grupo de limite 20).

## 2. Bundle (método 1)

- Home: **1 975 795 B** (12/09: 1,78 MB). Build `dpl_7iR8o3zdwj1ctLihS5LVB4BcGZBH`, Turbopack, **101 chunks** listados no HTML
  da home (12/09: 94 na home, 127 no total com as outras páginas). **Limite do método:** só li os chunks que a home lista; chunks
  de rota carregados sob demanda (`/leaderboard`, screener) não entraram. É por isso que `unified-prod.nats…` e
  `boards/trending` (vistos pelo REA) **não** aparecem na minha varredura: não estão na home.
- **Achado de método:** o chunk `02i6ywd4i-qb4.js` carrega o **registro tipado de rotas** do BFF (`defineRoutes`, zod):
  **312 rotas** (178 GET, 102 POST, 21 DELETE, 6 PATCH, 5 PUT), cada uma com `summary`, `query` e `response`. Em 12/09 só tínhamos
  literais de URL; agora há contrato escrito pela própria pump.fun, incluindo teto de `limit` e descrições de privacidade
  (ex.: "`/user-portfolio` público nunca serve o piso de poeira do dono"). Lista completa: `routes_registry.tsv` (temp);
  as rotas relevantes estão no §10 do mapa.
- Hosts no bundle além dos de 12/09: `prod-v2.nats.realtime.pump.fun`, `fees.pump.fun` (painel de receita; 301), `swap.pump.fun`,
  `app.pump.fun`, `join.pump.fun` (AppsFlyer), `clips.pump.fun`/`clip.pump.fun` (CDN), `images.pump.fun`, `mobile-resources.pump.fun`,
  `privy.pump.fun`, `privy-wallet.pump.fun`, `pump.mypinata.cloud`, `pump-prod-tg2x8veh.livekit.cloud`. Getter novo
  `getAdvancedIndexerRestUrl` (com sessão vai por `/api/indexer`). `advanced-api-v2.pump.fun` continua constante no bundle
  (não rechamado; era 530/1016 em 12/09).
- NATS: o bundle descreve `POST /nats/token` ("1 h bearer user JWT", escopo `followingFeed.user.<uid>`, `positions.<wallet>` …),
  **escuro** atrás da flag `natsTokenMint` (404 `NATS_AUTH_DISABLED`) e diz "mantenha as credenciais estáticas de assinante".
  Ou seja: o cliente carrega credenciais estáticas. **Não as extraí nem usei** (autenticação). Só li o `INFO` dos servidores.
- CSP (cabeçalho da home) lista hosts de terceiros (`*.padre.gg`, `*.launchdarkly.com`, `*.hel.io`, `*.moonpay.com`,
  `*.quiknode.pro`, `*.nozomi.temporal.xyz`, `api.relay.link` …). Em 12/09 só anotei 4 padrões, então **não há diff** possível.
- `/docs/wallet-login-changes`: "Browser-wallet sign-in is being retired on September 25, 2026 (15:00 UTC)": a web passa a
  entrar por e-mail/Google/Apple/GitHub (Privy). "Your wallet address, positions, callouts, followers and username are
  unchanged." Nav nova: "Holder rewards (New)", "Terminal", "$PUMP".
- `/docs/fees`: **"Last Updated: 20 May 2026"**, igual a 12/09; a escada SOL (1,250 % → 0,300 %) e USDC conferem com §4.1;
  nenhuma linha nova. `pumpportal.fun/fees/`: igual ("Effective May 1, 2026").
- `GET /changelog` (60/min) → `{"entries":[]}`. `GET /app-banner` não chamado.

## 3. Rotas, formas e limites

Log completo das chamadas (endereços truncados) no fim. Formas (nomes/tipos):

**`GET /pnl-leaderboard`** (RL 60/60 s): query `period ∈ {daily,weekly,monthly}`, **`sort ∈ {realized,unrealized,combined}`**,
`positionsLimit`, `limit` ("default and ceiling 100"). **`offset` é ignorado** (daily `limit=100&offset=100`: mesmo rank 1, 98/100
carteiras iguais; a diferença é o refresh do quadro). Resposta: `{entries[], periodType (3 daily, 1 weekly, 2 monthly),
periodLabel ("24h"/"7d"/"30d"), windowStartSec}`. Entrada: `rank:int, walletAddress, pnlSol, pnlUsd, pnlPercent, buySpendSol,
lastRefreshedAtMs:int, realizedPnlSol/Usd, unrealizedPnlSol/Usd, positionsCount:int, topPositions[]{mint, chainId, symbol, name,
imageUri}, username, profileImage, xUsername, isVerified:bool, verifiedBadgeVisible:bool, userId`. `windowStartSec`: daily
2026-10-05T02:00Z, weekly 2026-09-29T02:00Z, monthly 2026-09-06T02:00Z, lidos às 02:25Z de 06/10 (os três terminam em 02:00Z; uma leitura não distingue âncora fixa de janela móvel arredondada).
`lastRefreshedAtMs` por linha cai a poucos minutos da leitura: o quadro é **vivo**, não congelado. O `chainId` de Solana é
`1399811149` (Codex); aparecem 1, 56, 4663, 8453, 999 (EVM).

Seis quadros lidos (3 períodos × `combined` e `realized`), 100 linhas cada, 600 linhas, **300 carteiras distintas na união daquela rodada** (não é previsão de candidatas novas por dia):

| quadro | realizado Σ (SOL) | não realizado Σ (SOL) | linhas com realizado ≤ 0 | `isVerified` | `buySpendSol` ≈ 0 | realizado/gasto, mediana | `topPositions` com mint `…pump` | `topPositions` fora de Solana |
|---|---|---|---|---|---|---|---|---|
| daily combined | 3 597 | 11 760 | 38 | 59 | 14 | 0,223 (n 79) | 80 / 254 | 61 |
| weekly combined | 24 581 | 26 593 | 18 | 84 | 2 | 0,193 (n 98) | 95 / 265 | 37 |
| monthly combined | 106 170 | 76 769 | 12 | 80 | 1 | 0,210 (n 99) | 86 / 252 | 34 |
| daily realized | 6 107 | 378 | 0 | 60 | 0 | 0,291 (n 100) | 109 / 247 | 25 |
| weekly realized | — | — | 0 | 81 | 0 | 0,265 (n 100) | 106 / 256 | 19 |
| monthly realized | — | — | 0 | 77 | 0 | 0,218 (n 100) | 90 / 252 | 35 |

(Linhas com `realizedPnlSol ≤ 0` em daily combined: 100 − 62 positivas = 38; weekly 100 − 82 = 18; monthly 100 − 88 = 12.)
Sobreposição: daily ∩ weekly 28, daily ∩ monthly 18, weekly ∩ monthly 42, daily combined ∩ daily realized 49. União dos seis: 300.
No daily combined a mediana da fração não realizada do PnL é 0,78 (58 de 100 linhas têm não realizado > realizado). No daily
combined, #1 (`215n..gQjP`): pnlSol +1 343, realizado −46, não realizado +1 389, 251 posições, gasto 92 SOL. Weekly #1
(`9BMz..QdLU`): pnlSol +4 043, realizado −62, não realizado +4 105, 45 posições, gasto 3 228 SOL.

**`GET /users/{address}`** (RL 30/60 s, público, sem cookie): `address, userId, is_pump_user, is_banned, username, profile_image,
header_image_url, avatar_decoration, kind, member_count, last_username_update_timestamp, following:int, followers:int, bio,
x_username, canonical_svm_wallet, canonical_evm_wallet, group_badges[]`. **Novos desde 12/09:** `is_banned, header_image_url,
avatar_decoration, last_username_update_timestamp, canonical_evm_wallet`. Duas carteiras do quadro: followers 27 709 / following 0,
e followers 30 843 / following 38. **Nenhum carimbo de data nos seguidores** (só o valor de agora).
**`GET /following/v3/followers/count/{id}`** e **`/following/v3/following/count/{id}`** (RL 50 no cabeçalho): `{"count":int}`
(15 B e 11 B nessas respostas, contra 904 B do `/users`; "grupo próprio" **não** foi demonstrado). **`GET /users/{id}/overview`** (RL 60/60 s): `{address, profile{…igual ao /users}, isPumpUser,
counts{followers,following}, verified, achievementBadgeIds[], banned, createdCoinsCount:int, degraded[]}`.
**`GET /users/{address}/trader-stats`** e **`/social-stats`**: **401** (precisam de sessão) → bloqueadas; `GET /coin-activity/{mint}`: 401.

**`GET /user-trades/{id}`** (RL 600/60 s, **público**, id = carteira): query `mint, chainId, cursor, limit (1–200; padrão 50), types
(trades|transfers)`. Resposta `{trades[], traders[], nextCursor}`; trade: `tx, isBuy:bool, timestamp (ISO, segundos), amountUsd, baseAmount,
priceUsd, mint, chainId, walletAddress, userId, slotIndexId, amountSol`. Cursor `"<micros>:<uuid>"`. **Quatro páginas de 200 (800
trades) sem duplicata, de 06/10 00:47Z até 25/09 23:36Z (10 d 1 h 11 min = 10,05 dias)** e `nextCursor` ainda presente; retenção mínima, janela completa e cobertura de outras carteiras **não** demonstradas. 0,4–0,8 s por página. Sem campo de programa/venue; Solana apenas ("Solana-only today").
**`profile-api`** (sem cabeçalho de limite): `GET /balance/summary/{wallet}` → `{success, data{total_value, native_balance,
native_lamports, wrapped_sol_balance, sol_price, token_count, dust_count, dust_value_usd, hidden_count, hidden_value_usd,
last_update_ts, portfolioPnL{total_cost_basis_usd, total_unrealized_usd, total_percentage}}}`; `GET /v4/pnl/token/{wallet}/{mint}` →
`{success, data{mint, cost_basis_usd/sol, unrealized_pnl_usd/sol(_mark), percentage_usd/sol, realized_pnl_usd/sol (null), last_slot_index_id,
amount_held …}}`; `GET /v4/pnl/{wallet}/trades?mint=&limit=` → `{trades[]{tx, slotIndexId, timestamp, type, mint, baseAmount, amountSol,
amountUsd, legCount, poolAddress}, pagination}`.
**`GET /user-positions/{wallet}?mints=`** (RL 600): +`openedAt`, +`tradeCount` (novos), +`callout{…}` quando a carteira publicou um
"callout" naquela moeda. **`GET /user-portfolio/{wallet}`** (RL 60): 195 KB; `limit=5` devolveu **200** posições (`token_count` do `balance/summary` dizia 139 tokens); posições com `potentialSpam`,
`dustFloorFiltered`, `isNative`; inclui EVM. **`GET /portfolio-summary`** não chamado.
**`GET /pnl-leaderboard/top-trader-trades/{mint}`** (RL 120/60 s): "trades de contas no top-50 de qualquer período, em todas as carteiras
delas"; query `to (ms), cursor, limit ≤ 500`; resposta `{mint, traders[]{…, bestRank, periods[], tradingWallets[], tradeCount}, trades[]
(mesma forma do user-trades), boardsBuiltAtMs, generatedAtMs, page{nextCursor,to,limit}}`.
**`GET /pnl-leaderboard/positions?period=daily|weekly`** (RL 60): `{entries[]{rank, walletAddress, coinMint, pnlUsd, pnlPercentage,
amountHeld, isExited, costBasisAmount/Usd, amountBought(Usd), realizedPnlUsd, avgEntryMcapUsd, callout{…}, leaderboardPnlUsd, heldValueSol,
valueUsd, lastRefreshedAtMs, username…, userId}], periodLabel, windowStartSec, totalRanked}`.
**`GET /mint-positions/{mint}`** (RL 60): 50 por página, `{positions[]{userName…, amountHeld, pnlUsd, realizedPnlUsd, costBasisUsd, callout,
lowQuality}, totalCount, hasMore}` (holders com PnL).
**`GET /mayhem/top-traders?window=24h|7d`** (RL 60): 50 itens `{rank, address, realisedPnlUsd, winRate, volumeUsd, tradeCount}`; o #1 de 24h tem
`realisedPnlUsd == volumeUsd`, `winRate 1`, 5 999 trades (perfil de robô/agente, não de pessoa).
**`GET /competitions`** (RL 60): `{upcoming[], live[], past[≤50]}`; competição: `id, slug, kind (person|group), title, description,
prizeCopy, prizes[]{rankFrom, rankTo, amount}, registrationOpensAt, registrationClosesAt, startsAt, endsAt, minMembers, maxMembers,
maxEntries, entriesCount, participants, joinable, phase, isFinal, top[], winners[]`. Hoje: 2 ao vivo (`solo-cuptober` e `squad-cuptober`,
03/10–10/10 14:00Z), 2 passadas (nomes `test-…`). `solo-cuptober`: **20 506 participantes**, prêmio total 100 000 (US$ 50 000 ao #1, "prizeCopy"),
até 25 000 inscrições. **`GET /competitions/{idOrSlug}?limit=`** (RL 60): `{competition{…}, leaderboard{builtAtMs, startSec, endSec, totalRanked,
isFinal, entries[]{entryId, participantId, kind, rank, pnlUsd, realizedPnlUsd, unrealizedPnlUsd, buySpendSol, memberCount, membersFresh,
struck, lastRefreshedAtMs, positionsCount, topPositions[], walletAddress, username, profileImageUrl, isVerified, verifiedBadgeVisible}}}`;
teto de 100 linhas. O #1 de hoje: pnlUsd +682 125, realizado 0, não realizado 100 %, `buySpendSol` 0, 65 posições.
**`GET /coins/top-holders-v2/{mint}`** (RL 60): `{topHolders[]{address, amount, isDev, isSniper, isBundler, enteredAt}, totalHolders}` (flags novas
por holder; `enteredAt` null na amostra). **`GET /coins/holder-stats/{mint}`** (RL 60): `{mint, totalHolders, top10HoldersPercent,
devHoldingsPercent, snipersHoldingsPercent, bundlersHoldingsPercent, totalFeesSol, asOf}` (nulos para uma moeda que não é do programa pump).
**`GET /trades/{chainId}/{address}`** (RL 600; chainId CAIP-2 `solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp`): fita **por moeda**, `limit ≤ 100`,
`before/after` (`ordinalKey`), `kinds`, `minUsd`, `pool`; linha `{ordinalKey "<slot>-<txIndex>-<eventIndex>-<blockTimeMs>", blockId (slot),
txIndex, eventIndex, blockTimeMs, txId, legIndex, late, isBackfill, side, kind, venue ("pump_amm"), pool{chainId,address}, trader{address},
baseAmount{raw,decimals}, quoteAmount{raw,decimals}, quote{id}, priceUsd, priceQuote, quotePriceUsd, valueUsd, valueNative}`;
`aggregates{buys,sells,buyVolumeUsd,sellVolumeUsd,netBase,asOf}`, `source ("indexed")`. Vazia para uma moeda fora do índice; **não filtra por
carteira**. **`GET /candles/{chainId}/{address}`**: 400 com `res` inválido (valores: 1s, 15s, 30s, 1m, 5m, 15m, 1h, 4h, 1d), não explorado.
**`GET /fees/holder-rewards`** (RL 600): `{generatedAt, coins[]{mint, holderRewardsPda, …, isGraduated, quoteMintAddress, accrued, payouts}, next,
quotes{}, totals{coinCount 123 429, payingCount 64 551, accruedUsdNow ≈ 15,76 M, walletsRewardedDistinct 360 427, payoutCount 7 114 795},
matchingCount, offset, byQuote[]}` (com `limit=3` devolveu 3 moedas e os `totals` globais: 91 KB por causa de `quotes`/`byQuote`, **não** é prova de que `limit` seja ignorado). **`GET /coins/perps`**:
30 itens de perpétuos HyperCore (Hyperliquid), irrelevante para nós.

**Coin** (`GET /coins?limit=100` → 70 itens, teto igual a 12/09): 59 chaves distintas na amostra; **novas**: `updated_at` (segundos), `is_holder_reward`
(bool), `transfer_fee_bps` (int, 0 em 70/70), `transfer_hook_program` (string vazia), `depth` (0). Chaves de 12/09 não vistas nesta
amostra de 70 moedas (todas opcionais ou só de detalhe): `inverted, last_reply, platform, pump_swap_pool, security_verdict, video_uri`.
`chain_id` agora vem em CAIP-2 (`solana:5eykt4…`). Na amostra: `program`/`protocol` = pump nas 70; `quote_mint` SOL 62, `Xsc9qv…` 5, USDC 1, `pumpCm…` (o PUMP) 1,
null 1; `mayhem_state` ausente 51, active 10, paused 7, completed 2; `complete` 0; `is_cashback_enabled` 0/70. Janela de criação 141 s.
**`GET /mayhem/overview`**: novos `agentVolumeUsd{24h,7d}`, `distinctTraders{24h,7d}`, e o modo `party` em `coinsCreatedByMode` (auto 7 553, manual 2 318,
party 355 em 24 h); `coinsCreated` 10 226 / 89 541 (24 h / 7 d; 12/09: 10 705 em 24 h); `activeCoins` 119.
`GET /sol-price`: mesma forma. **swap-api** `POST /v1/coins/market-activity/batch`: 201, mesmas janelas; respeita o subconjunto de métricas pedido; um mint **sem sufixo `pump`** voltou `null` em toda janela (o sufixo não foi validado como classificador de programa); duas moedas pump ativas voltaram 1m/5m/1h/24h preenchidos.
`GET /v2/coins/{mint}/trades?userAddress=` funciona (filtro por carteira dentro de uma moeda). `advanced-indexer`: `/boards/movers?limit=3` → 3 entradas
(o `limit` vale; o quadro mistura `eip155:8453`); `/in-memory-coin/{mint}` → **67 campos** (65 em 12/09), entre eles `isHolderReward`, `isMultiplayer`,
`mayhemBotCoinSupplied`, `builderTip*`, `tradingAppFee*`, `txFeeSolV2`.

## 4. WebSockets (método 1)

| host | resultado |
|---|---|
| `wss://advanced-indexer.pump.fun/ws/trenches` (board `graduating`, 15 s) | **ainda responde anônimo**: 1 `snapshot` (30 entradas) + 26 `delta`, 61 290 B. Chaves da entrada: as de §3.1 mais **`hr`** e **`lp`** (novas) |
| `wss://pumpportal.fun/api/data` (`subscribeNewToken`, 12 s) | ack + 7 `create`, mesmas chaves; ainda grátis para criação/migração |
| `wss://prod-v2.nats.realtime.pump.fun` | NATS **2.12.15**, `auth_required: true`, `max_payload 8192` (novo host) |
| `wss://multichain-prod.nats.realtime.pump.fun` | NATS 2.12.11, `auth_required: true`, `max_payload 524288` (igual a 12/09) |
| `wss://unified-prod.nats.realtime.pump.fun` (host do REA) | NATS 2.12.11, `auth_required: true`, `max_payload 524288` |

## 5. Observação passiva via REA (método 2, 06/10 ~02:25Z)

Chrome headless, perfil temporário, sem login, home + 8 s + `/leaderboard` + 8 s; 744 requisições, 4 websockets; corpos não retidos.
Do que o navegador **chamou** (não necessariamente o que responde a um cliente sem navegador):
- home: `GET advanced-indexer /boards/trending` (query `tier, surface, platform, limit, chains, offset, ranking, window`), `GET /home-feed`
  (`pageSize, chain, platform`; **anônimo**), `GET /pnl-leaderboard` (`period, sort, limit`), `GET /coins/top-tokens/mints?withChains`,
  `GET /auth/disabled-features`, `GET /auth/my-profile`, `POST /coins-v2/mints`, `/profiles/verified`, `/users/batch`, `POST swap-api /v1/coins/market-activity/batch`,
  `POST pump.fun /api/relay/rpc/tokens/batch`, `POST solana-mainnet.pump.fun/<uuid>` (RPC do site);
- `/leaderboard`: `/pnl-leaderboard`, **`/pnl-leaderboard/positions?period`** (em 12/09 só existia no bundle), **`/user-positions/{wallet}?mints&updatesLimit` × 20**
  (as posições dos traders do topo), **`/competitions`**, **`/competitions/{id}`**, **`/competitions/{id}/entries/{entry}/highlights?limit`** (família nova), `POST /api/profiles/generated-media`;
- WebSockets: **`wss://prod-v2.nats.realtime.pump.fun`** e **`wss://unified-prod.nats.realtime.pump.fun`** (em 12/09 o mapa tinha `multichain-prod.nats` e `/ws/trenches`).
  Eles vão autenticados no navegador; o `INFO` anônimo dos três exige `auth`.
- Um desafio Cloudflare (`/cdn-cgi/challenge-platform`) disparou na sessão do navegador; **minhas chamadas `curl` não receberam nenhum desafio**.
Esta leitura confirma por tráfego real o que o bundle sugeria: a tela de ranking é montada com `/pnl-leaderboard` + `/user-positions` por carteira do topo.
Não consegui reconciliar sozinho por que o `unified-prod` não aparece nos 101 chunks da home (hipótese: chunk de rota, ou build diferente; não verificado).

### 3b. Achados que contradizem o mapa de 12/09

- **`GET /coins/{mint}` → 404** `{"statusCode":404,"message":"Cannot GET /coins/<mint>","error":"Not Found"}` em dois mints (`Bj7C..pump`, `5bPP..pump`; 02:55:50Z e 02:56:11Z). `GET /coins-v3/{mint}` do segundo mint → 200 (RL 60, 2 053 B). O código já sabe (`collect.py`: "by-mint route that 404s since ~25/09", T4.97b/R80), mas `PumpFunRestClient.get_curve_state` ainda chama `/coins/{mint}`.
- **`verified` diverge entre rotas** para a mesma carteira: quadro (`isVerified` true, 02:25Z) × `/users/{id}/overview` (`verified` false, 02:31Z). `followers` 27 709 (`/users` 02:29Z, e `followers/count`) × 27 710 (`/overview` 02:31Z).
- Revisão da Astra (`.claude/state/astra-review-pumpfun-releitura.md`): 9 pontos; os de redação foram absorvidos no §10 (estados HTTP/bundle/REA/não testado, "nova" → "ausente do mapa de 12/09", limite de `holder-rewards` retirado, "grupo próprio" retirado, 15 B por resposta, 300 = união da rodada, 10,05 dias).

### 5b. Segunda captura do REA: página `/coin/{mint}` (06/10)

Capturas com navegação perfil → moeda falharam 3 vezes (`cleanup_incomplete`); só a da página de moeda funcionou. Hosts **novos** em relação a 12/09: `profile-api.pump.fun` `POST /pnl/coin/{mint}/holders` (3 chamadas),
`livestream-api.pump.fun` (`/kols`, `/livestream?mintId`, `/livestream/history`, `/livestream/is-approved-creator`, `/clips/{mint}`, `/bounties/v2/tasks`), `blockchain-swap.pump.fun /supported/coin-create-mints`.
`frontend-api-v3`: `GET /mint-positions/{mint}?sortBy&pageSize[&withThesis]`, `GET /users/{wallet}` (perfil do criador), `/coins-v3`, `/coins-v2/{mint}/mayhem-state`, `/token-holders/{mint}/count`, `/global-params/{ts}`,
`/sol-price`, `GET /profiles/verified`. `swap-api`: `/v1/coins/{mint}/ath`, `/market-activity`, `POST /trades/batch`, `/v2/coins/{mint}/candles?interval&limit&currency&createdTs&program&chainId`. `solana-mainnet.pump.fun/<uuid>`: 43 POST (RPC do site).

**Forma lida por mim (a pedido):** o corpo vem do bundle (`chunks/0kos9xaalfk~-.js`, hook `useTopHoldersProfilePnl`): `fetch(PROFILE+"/pnl/coin/"+mint+"/holders", {method:"POST", body: JSON.stringify({holders: <até 20 carteiras>})})`,
uma requisição por lote de 20. Chamei **uma vez**, com 5 carteiras públicas do `top-holders-v2` da mesma moeda (as mesmas que o site usa): **201**, 5 205 B, sem cabeçalho de limite. Forma:
`{success, data[]{wallet, mint, unrealized{cost_basis{sol,usd}, pnl{sol,usd}, pnl_mark{sol,usd}, percentage{sol,usd}, amount_held}|null, realized{pnl{sol,usd}, percentage{sol,usd}, avg_buy_price{sol,usd}, avg_sell_price, amount_sold, total_in, total_out}|null,
total_buy_spend{sol,usd}, total_buy_amount, last_slot_index_id, has_transfers, has_untrusted_basis, fee{sol,usd}, fee_detail{base, priority, tip, ui, ata_rent, protocol, cashback}}, errors[]}`.
As 5 linhas: (1) aberta, 23,5 SOL gastos, −99,6 %, `has_untrusted_basis` true; (2) realizada, 44,6 SOL gastos, realizado −6,79 SOL (−15,2 %), `untrusted` true, `fee_detail.protocol` só; (3) tudo `null`; (4) realizada, 0,17 SOL gastos, `untrusted` false,
`fee_detail` com `base/priority/tip/ata_rent`; (5) realizada, 37,2 SOL gastos, `untrusted` true. `amount_held` da linha (2) é 0 enquanto o `top-holders-v2` lido 9 min antes dava 4,2 M tokens: ou ela vendeu nesses minutos ou as duas fontes têm atrasos diferentes (não resolvido).

## 6. Rotas do registro tipado que o mapa de 12/09 não tinha (GET públicos candidatos; só as marcadas "chamada" foram testadas)

`/user-trades/{id}` (chamada), `/users/{id}/overview` (chamada), `/users/{address}/trader-stats` (401), `/social-stats` (401), `/callout-stats`, `/achievements`, `/streak`,
`/users/streaks/leaderboard`, `/portfolio-summary` (+ `/balances`, `/chart`), `/pnl-leaderboard/{groups, follow-suggestions, onboarding-suggestions, positions (chamada), top-trader-trades/{mint} (chamada), projected-rank}`,
`/mint-positions/{mint}` (chamada), `/replay`, `/trades/{chainId}/{address}` (chamada), `/candles/{chainId}/{address}[/line]` (400), `/coins/holder-stats/{mint}` (chamada), `/coins/top-holders-v2/{mint}` (chamada),
`/coins/boards/{board}`, `/coins/hot-coin`, `/coins/currently-live`, `/coins/search-v2`, `/coins/search-quote-facets`, `/search/resolve`, `/coins/raw/{mint}`, `/coins-v2/{mint}`, `/coins/perps` (chamada),
`/fees/{coin,creator,shareholder,holder-rewards (chamada),me}`, `/competitions*` (chamada), `/groups/*`, `/payouts/leaderboard`, `/mayhem/{mint}/top-traders`, `/following/v3/{followers,following}[/search]/{id}`, `/followed-holders/*` (sessão),
`/following-positions/alerts` (sessão, publica no NATS `alertsFeed.user.<uid>`), `/changelog` (chamada), `/app-banner`, `/health`, `/check/{address}` (triagem de carteira).
Moderação (só leitura de existência): `POST /pnl-leaderboard/ban`, `/pnl-leaderboard/blocklist/mints/*`: o quadro **oculta** carteiras banidas e moedas na lista de bloqueio, ou seja, é curado pela pump.fun.
**Documentadas em 12/09 e não achadas no registro tipado** (podem viver em outro contrato ou ter saído; não re-testadas): `POST /wallet-overview`, `POST /x/public-handles`, `GET /kols`, `GET /livestream*`,
`GET /coin-narrative/by-mints`, `GET /leaderboard`, `GET /replies/*`. Rota bare `GET /coins/{mint}` também não está no registro (existem `/coins/raw/{mint}`, `/coins-v2/{mint}`, `/coins-v3/{address}`); não re-testada.
**Marcadas "superseded" pelo próprio registro:** `/coins/top-holders/{mint}` (→ v2), `/following/{userId}` e `/following/v2/*` (→ `/following/v3/*`).

## 7. Log das chamadas (hora UTC; endereços truncados; HTTP, bytes, segundos; limite = `x-ratelimit-limit / remaining / reset`)

| hora UTC | nome | chamada | HTTP bytes s | limite (x-ratelimit) |
|---|---|---|---|---|
| 02:25:20Z | lb_daily | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=daily` | 200 118586 0.325171 | 60 / resta 59 / 60 s |
| 02:25:23Z | lb_weekly_l200 | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=weekly&limit=200` | 200 119980 0.336887 | 60 / resta 59 / 60 s |
| 02:25:25Z | lb_monthly | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=monthly&limit=5` | 200 6407 0.206888 | 60 / resta 59 / 60 s |
| 02:29:50Z | lb_offset100 | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=daily&limit=100&offset=100` | 200 118252 0.301166 | 60 / resta 59 / 60 s |
| 02:29:52Z | users_w1 | `https://frontend-api-v3.pump.fun/users/9BMz..QdLU` | 200 904 0.235264 | 30 / resta 29 / 60 s |
| 02:29:54Z | fol_cnt_w1 | `https://frontend-api-v3.pump.fun/following/v3/followers/count/9BMz..QdLU` | 200 15 0.218502 | 50 / resta 49 / 60 s |
| 02:29:57Z | fing_cnt_w1 | `https://frontend-api-v3.pump.fun/following/v3/following/count/9BMz..QdLU` | 200 11 0.360759 | 50 / resta 49 / 60 s |
| 02:29:59Z | users_w2 | `https://frontend-api-v3.pump.fun/users/6rq8..cMhe` | 200 822 0.255991 | 30 / resta 29 / 60 s |
| 02:30:01Z | usertrades_w1 | `https://frontend-api-v3.pump.fun/user-trades/9BMz..QdLU?limit=5` | 200 2837 0.326542 | 600 / resta 599 / 60 s |
| 02:30:03Z | traderstats_w1 | `https://frontend-api-v3.pump.fun/users/9BMz..QdLU/trader-stats` | 401 156 0.233376 | 30 / resta 29 / 60 s |
| 02:30:05Z | socialstats_w1 | `https://frontend-api-v3.pump.fun/users/9BMz..QdLU/social-stats` | 401 156 0.201099 | 30 / resta 29 / 60 s |
| 02:30:35Z | usertrades_w1_l200 | `https://frontend-api-v3.pump.fun/user-trades/9BMz..QdLU?limit=200` | 200 97588 0.416375 | 600 / resta 599 / 60 s |
| 02:30:39Z | usertrades_w1_p2 | `https://frontend-api-v3.pump.fun/user-trades/9BMz..QdLU?limit=200&cursor=1791025691000000:00000000-0000-0997-4279-7ed0c18d24f5` | 200 97499 0.791058 | 600 / resta 599 / 60 s |
| 02:30:55Z | userpos_w1 | `https://frontend-api-v3.pump.fun/user-positions/9BMz..QdLU?mints=F4K2..ZtB6` | 200 2751 0.294814 | 600 / resta 599 / 60 s |
| 02:30:58Z | userportfolio_w1 | `https://frontend-api-v3.pump.fun/user-portfolio/9BMz..QdLU?limit=5` | 200 194988 0.592906 | 60 / resta 59 / 60 s |
| 02:31:01Z | toptradertrades | `https://frontend-api-v3.pump.fun/pnl-leaderboard/top-trader-trades/F4K2..ZtB6?limit=5` | 200 3108 0.229168 | 120 / resta 119 / 60 s |
| 02:31:03Z | mayhem_toptraders_24h | `https://frontend-api-v3.pump.fun/mayhem/top-traders?window=24h` | 200 8264 0.211363 | 60 / resta 59 / 60 s |
| 02:31:05Z | lb_positions_daily | `https://frontend-api-v3.pump.fun/pnl-leaderboard/positions?period=daily&limit=5` | 200 7563 0.257994 | 60 / resta 59 / 60 s |
| 02:31:07Z | mintpositions | `https://frontend-api-v3.pump.fun/mint-positions/F4K2..ZtB6?limit=5` | 200 57086 0.334437 | 60 / resta 59 / 60 s |
| 02:31:09Z | overview_w1 | `https://frontend-api-v3.pump.fun/users/9BMz..QdLU/overview` | 200 1237 0.259533 | 60 / resta 59 / 60 s |
| 02:31:37Z | lb_monthly_full | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=monthly&limit=100` | 200 118196 0.541297 | 60 / resta 59 / 60 s |
| 02:31:40Z | mayhem_toptraders_7d | `https://frontend-api-v3.pump.fun/mayhem/top-traders?window=7d` | 200 8393 0.239066 | 60 / resta 59 / 60 s |
| 02:31:59Z | lb_daily_realized | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=daily&sort=realized&limit=100` | 200 118016 0.228837 | 60 / resta 59 / 60 s |
| 02:32:13Z | lb_weekly_realized | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=weekly&sort=realized&limit=100` | 200 118308 0.228998 | 60 / resta 59 / 60 s |
| 02:32:16Z | lb_monthly_realized | `https://frontend-api-v3.pump.fun/pnl-leaderboard?period=monthly&sort=realized&limit=100` | 200 118567 0.247544 | 60 / resta 59 / 60 s |
| 02:33:10Z | prof_balance_summary | `https://profile-api.pump.fun/balance/summary/9BMz..QdLU` | 200 462 0.337142 | sem cabeçalho |
| 02:33:13Z | prof_pnl_token | `https://profile-api.pump.fun/v4/pnl/token/9BMz..QdLU/F4K2..ZtB6` | 200 1081 0.218929 | sem cabeçalho |
| 02:33:18Z | prof_pnl_trades | `https://profile-api.pump.fun/v4/pnl/9BMz..QdLU/trades?mint=F4K2..ZtB6&limit=5` | 200 2094 0.217571 | sem cabeçalho |
| 02:33:20Z | swap_trades_userAddress | `https://swap-api.pump.fun/v2/coins/F4K2..ZtB6/trades?limit=5&userAddress=9BMz..QdLU` | 200 3285 1.126228 | 1000 / resta 946 / 28 s |
| 02:33:36Z | coins_list70 | `https://frontend-api-v3.pump.fun/coins?offset=0&limit=100&sort=created_timestamp&order=DESC&includeNsfw=true` | 200 138800 0.433837 | 60 / resta 59 / 60 s |
| 02:33:39Z | mayhem_overview | `https://frontend-api-v3.pump.fun/mayhem/overview` | 200 310 0.255857 | 60 / resta 59 / 60 s |
| 02:33:41Z | sol_price | `https://frontend-api-v3.pump.fun/sol-price` | 200 63 0.214927 | 50 / resta 49 / 60 s |
| 02:33:43Z | holder_stats | `https://frontend-api-v3.pump.fun/coins/holder-stats/F4K2..ZtB6` | 200 230 0.336391 | 60 / resta 59 / 60 s |
| 02:33:45Z | coin_activity | `https://frontend-api-v3.pump.fun/coin-activity/F4K2..ZtB6` | 401 151 0.197441 | 20 / resta 19 / 60 s |
| 02:33:48Z | trades_chain | `https://frontend-api-v3.pump.fun/trades/solana:5eyk..Kvdp/F4K2..ZtB6?limit=3` | 200 166 0.222407 | 600 / resta 599 / 60 s |
| 02:33:50Z | coins_perps | `https://frontend-api-v3.pump.fun/coins/perps` | 200 16696 0.235122 | 60 / resta 59 / 60 s |
| 02:40:08Z | swap_batch_post | `POST https://swap-api.pump.fun/v1/coins/market-activity/batch` | 201 91 0.341205 | 1000 / resta 994 / 60 s |
| 02:40:11Z | indexer_movers | `https://advanced-indexer.pump.fun/boards/movers?limit=3` | 200 2892 0.370350 | sem cabeçalho |
| 02:40:34Z | swap_batch_post2 | `POST https://swap-api.pump.fun/v1/coins/market-activity/batch` | 201 1027 0.231367 | 1000 / resta 996 / 23 s |
| 02:40:36Z | indexer_inmem | `https://advanced-indexer.pump.fun/in-memory-coin/Bj7C..pump` | 200 1736 0.391387 | sem cabeçalho |
|  | docs/fees | `https://docs/fees` | 200 1952466 | sem cabeçalho |
|  | docs | `https://docs` | 200 1803120 | sem cabeçalho |
|  | docs/wallet-login-changes | `https://docs/wallet-login-changes` | 200 1876573 | sem cabeçalho |
| 02:43:16Z | trades_chain_pump | `https://frontend-api-v3.pump.fun/trades/solana:5eyk..Kvdp/Bj7C..pump?limit=3` | 200 2784 0.298276 | 600 / resta 599 / 60 s |
| 02:43:20Z | candles_chain | `https://frontend-api-v3.pump.fun/candles/solana:5eyk..Kvdp/Bj7C..pump?limit=3` | 400 283 0.255599 | 600 / resta 599 / 60 s |
| 02:43:23Z | changelog | `https://frontend-api-v3.pump.fun/changelog` | 200 14 0.210764 | 60 / resta 59 / 60 s |
| 02:43:25Z | fees_holder_rewards | `https://frontend-api-v3.pump.fun/fees/holder-rewards?limit=3` | 200 90973 0.409886 | 600 / resta 599 / 60 s |
| 02:43:28Z | top_holders_v2 | `https://frontend-api-v3.pump.fun/coins/top-holders-v2/Bj7C..pump` | 200 7432 0.325385 | 60 / resta 59 / 60 s |
| 02:43:59Z | usertrades_w1_p3 | `https://frontend-api-v3.pump.fun/user-trades/9BMz..QdLU?limit=200&cursor=1790875019000000:00000000-0000-0994-34b6-bd1f89577300` | 200 97228 0.654915 | 600 / resta 599 / 60 s |
| 02:44:03Z | usertrades_w1_p4 | `https://frontend-api-v3.pump.fun/user-trades/9BMz..QdLU?limit=200&cursor=1790592376000000:00000000-0000-098e-7b49-3a2e493e6800` | 200 97544 0.549221 | 600 / resta 599 / 60 s |
|  | pumpportal.fun/fees/ | `https://pumpportal.fun/fees/` | 200 12438 | sem cabeçalho |
|  | fees.pump.fun | `https://fees.pump.fun` | 301 167 | sem cabeçalho |
| 02:47:16Z | competitions | `https://frontend-api-v3.pump.fun/competitions` | 200 25928 0.227983 | 60 / resta 59 / 60 s |
| 02:47:27Z | competition_solo | `https://frontend-api-v3.pump.fun/competitions/solo-cuptober?limit=5` | 200 10802 0.264080 | 60 / resta 59 / 60 s |
| 02:52:37Z | prof_pnl_coin_holders | `POST https://profile-api.pump.fun/pnl/coin/Bj7C..pump/holders` | 201 5205 0.253413 | sem cabeçalho |
| 02:55:50Z | coins_mint_bare | `https://frontend-api-v3.pump.fun/coins/Bj7C..pump` | 404 213 0.545283 | sem cabeçalho |
| 02:56:11Z | coins_mint_bare2 | `https://frontend-api-v3.pump.fun/coins/5bPP..pump` | 404 213 0.643337 | sem cabeçalho |
| 02:56:14Z | coins_v3_mint | `https://frontend-api-v3.pump.fun/coins-v3/5bPP..pump` | 200 2053 0.304394 | 60 / resta 59 / 60 s |

