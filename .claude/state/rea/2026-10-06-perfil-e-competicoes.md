# REA — perfil e competições da pump.fun (resumo bruto, 06/10/2026)

Ferramenta: `mcp__rea__capture_browser_scenario`, `mode: launch`, Chrome headless, perfil temporário, sem login. Uma página por cenário, 15 s de espera, eventos `network` + `websockets`.
Brutos (fora do repositório): `~/.claude/projects/C--dev-project-hunter/<sessão>/tool-results/mcp-rea-capture_browser_scenario-1791289665483.txt` (perfil), `...-1791289895705.txt` (/competitions), `...-1791289955722.txt` (/competitions/solo-cuptober, com DOM final). Lidos só por `Grep -o` de URL/método/status; nenhum corpo existe.

## Captura 1 — `/profile/2M2v..ENNZ`
Chamadas de API distintas (frontend-api-v3 e profile-api), sem repetições:
- `GET frontend-api-v3 /auth/disabled-features`; `/auth/my-profile` (401, anônimo)
- `GET /sol-price`
- `GET /pnl-leaderboard?period=weekly&sort=combined&limit=100`; `?period=daily&sort=combined&limit=20`
- `GET /portfolio-summary?user={w}&period=1d`; `GET /portfolio-summary/chart?user={w}&period=1d`
- `GET /user-portfolio/{w}?filter=all&page=0&pageSize=100&sortBy=PNL`; `?filter=open&page=0&pageSize=100&sortBy=POSITION_SIZE`
- `GET /coins-v2/user-created-coins/{w}?limit=1&offset=0`; `?limit=50&offset=0`
- `GET /users/{userId-uuid}/overview`
- `GET /achievements/catalog`; `GET /users/{w}/achievements`
- `GET /callout/list/{w}?limit=100&sortBy=TIMESTAMP&sortOrder=DESC`
- `GET /groups/of/{w}?limit=1` -> 401
- `POST /profiles/verified`; `POST /coins-v2/mints`; `GET /coins/top-tokens/mints?withChains=true`
- `GET profile-api /balance/tokens/{w}?page=1&size=10`; `?page=1&size=200&chain=all`
- `GET profile-api /balance/summary/{w}?multi_chain=true`
- `POST profile-api /wallet-overview` -> 200
Não chamadas: `/users/{address}`, `/following/v3/*`, `/user-trades/{w}`, `/user-positions/{w}`.
WebSockets: `wss://prod-v2.nats.realtime.pump.fun/`, `wss://unified-prod.nats.realtime.pump.fun/`; frames binários enviados (208, 77, 75 bytes), sem texto.
Status: 401 em `auth/my-profile` e `groups/of`; 201 (POSTs), 202/204 (terceiros), 302 (imagens); 0 x 403, 0 x 429, 0 x 5xx. `request-failed ERR_ABORTED` 2 (aborto do navegador). `cdn-cgi/challenge-platform/*` carregado passivamente.

## Captura 2 — `/competitions`
Documento HTTP 200. Chamadas: `pump.fun/api/server-time`, `/api/i18n/en?ns=__all__`, `frontend-api-v3 /auth/disabled-features`, `/auth/my-profile` (401), `/pnl-leaderboard?period=daily&sort=combined&limit=20`. **Nenhuma `/competitions*`.**

## Captura 3 — `/competitions/solo-cuptober`
Documento HTTP 200; DOM final traz "404 / Page not found" (404 mole). Mesmas chamadas da captura 2. Nenhuma `/competitions*`.

## Orçamento
3 páginas; 15 s cada; 0 bloqueios (um 401 esperado por auth/my-profile e um por groups/of). Chamadas de API do site: ~20 distintas no perfil, 5 em cada página de competições (a contagem de requisições totais inclui estáticos e terceiros e não foi somada). Sem HTTP próprio fora das capturas.
