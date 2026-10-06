# REA — leitura passiva da pump.fun (06/10/2026)

Ferramenta: `mcp__rea__capture_browser_scenario`.
- Chrome headless, perfil temporário do REA, sem login e sem cookies.
- Roteiro: home, espera de 8 s, depois `/leaderboard`, espera de 8 s.
- O REA não retém os corpos das respostas. Do lado do observado, a pump.fun disparou um desafio Cloudflare (`/cdn-cgi/challenge-platform`) que não precisou de nada nosso.
- Resultado bruto: `~/.claude/projects/.../tool-results/mcp-rea-capture_browser_scenario-1791254705987.txt`, com 1 743 eventos, 744 requisições e 4 websockets.

## Hosts mais chamados
`pump.fun` (361), `socialimages.pump.fun` (125), `frontend-api-v3.pump.fun` (53), `pump.mypinata.cloud` (51), `images.pump.fun` (43), `solana-mainnet.pump.fun` (6, RPC próprio), `swap-api.pump.fun` (3), `advanced-indexer.pump.fun` (1). Terceiros: LaunchDarkly, Google Analytics, AppsFlyer, lantern-echo.

## Chamadas de API vistas
**Home:**
- `GET advanced-indexer /boards/trending` (tier, surface, platform, limit, chains, offset, ranking, window)
- `GET frontend-api-v3 /home-feed` (pageSize, chain, platform)
- `GET /pnl-leaderboard` (period, sort, limit)
- `GET /coins/top-tokens/mints?withChains`
- `GET /auth/disabled-features`, `GET /auth/my-profile`
- `POST /coins-v2/mints`, `/profiles/verified`, `/users/batch`
- `POST swap-api /v1/coins/market-activity/batch`
- `POST pump.fun /api/relay/rpc/tokens/batch`
- `POST solana-mainnet.pump.fun/<uuid>` (RPC)

**`/leaderboard`:**
- `GET /pnl-leaderboard` (period, sort, limit)
- `GET /pnl-leaderboard/positions?period` (novo no uso; no mapa de 12/09 ele aparecia só no bundle)
- `GET /user-positions/{wallet}?mints&updatesLimit`, chamado 20× (as posições de cada trader do topo)
- `GET /competitions`, `GET /competitions/{id}`, `GET /competitions/{id}/entries/{entry}/highlights?limit` (família **nova**, ausente do mapa de 12/09)
- `POST pump.fun /api/profiles/generated-media`

## WebSockets (mudaram desde 12/09)
`wss://prod-v2.nats.realtime.pump.fun/` e `wss://unified-prod.nats.realtime.pump.fun/`. O mapa de 12/09 tinha `multichain-prod.nats.realtime.pump.fun` e `advanced-indexer .../ws/trenches`.

## Leitura para o H-030
- **O que a tela de ranking mostra:** a lista dos traders do topo **com as posições atuais de cada um** (`/user-positions` com `updatesLimit`). É uma fonte barata de carteiras candidatas a observar daqui para a frente.
- **Cuidado:** não é ponto no tempo. O ranking de hoje só vale para escolher quem observar.
- **`/competitions`:** competição de traders com "highlights". Pode valer como outra lista de candidatos; a forma ainda não foi lida.

## Segunda leitura: página de moeda (`/coin/{mint}`, 06/10)
A captura só da página de moeda funcionou. As capturas com navegação perfil → moeda falharam três vezes no Windows com `cleanup_incomplete` (`browser_transport`); o `rea doctor` está OK. Bruto: `tool-results/mcp-rea-capture_browser_scenario-1791255084859.txt`.

Hosts **novos** em relação ao mapa de 12/09:
- `profile-api.pump.fun`: `POST /pnl/coin/{mint}/holders`, chamado 3×. **PnL dos holders de uma moeda.** Muito relevante para o H-030: diz quem lucra em cada moeda. Corpo não retido; falta ler a forma.
- `livestream-api.pump.fun`: `/kols`, `/livestream?mintId`, `/livestream/history`, `/livestream/is-approved-creator`, `/clips/{mint}`, `/bounties/v2/tasks`.
- `blockchain-swap.pump.fun`: `/supported/coin-create-mints`.

`frontend-api-v3`:
- `GET /mint-positions/{mint}?sortBy&pageSize[&withThesis]`: posições na moeda, ordenadas. No mapa antigo constava só no bundle; agora a página chama.
- `GET /users/{wallet}`: o perfil do criador; os seguidores vêm daqui.
- `/coins-v3/{mint}`, `/coins-v2/{mint}/mayhem-state`, `/token-holders/{mint}/count`, `/global-params/{ts}`, `/sol-price`, `GET /profiles/verified`.

`swap-api`:
- `GET /v1/coins/{mint}/ath`
- `GET /v1/coins/{mint}/market-activity`
- `POST /v1/coins/{mint}/trades/batch`
- `GET /v2/coins/{mint}/candles?interval&limit&currency&createdTs&program&chainId` (candles v2)

`advanced-indexer`: `GET /in-memory-coin/{mint}`.

`solana-mainnet.pump.fun/<uuid>`: 43 POST. É o RPC próprio do site.
