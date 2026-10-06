---
tags: [knowledge, fontes, rea, pumpfun, carteiras, perfil, competicoes, h-030]
tema: o que a pump.fun carrega na página de PERFIL de um trader e na área de COMPETIÇÕES, e se algo disso pode ser lido como ponto no tempo
fonte: REA capture (3 páginas, Chrome headless, perfil temporário, sem login) — .claude/state/rea/2026-10-06-perfil-e-competicoes.md
fonte_url: https://pump.fun/profile/2M2v..ENNZ
lido_em: 2026-10-06
evidencia: observação passiva do navegador (REA não guarda corpos); nenhuma resposta lida
hipotese: H-030 / EXP-M15
status: vivo
owner: batedor-rea
updated: 2026-10-06
---

# Perfil de trader e competições da pump.fun — o que o site carrega (REA, 06/10/2026)

**Atende:** H-030 / [[EXP-M15-carteiras-vencedoras]] (desenho `docs/design/seguir-carteiras-lucrativas.md`; decisão [[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]]).
**Pergunta:** que dados o site carrega para (1) a página de perfil de um trader e (2) as competições, e algum deles pode ser lido como ponto no tempo (carimbo próprio que dê para fotografar toda noite) para descrever carteiras candidatas (atividade, PnL, seguidores, histórico de posição no ranking)?

**Lido antes (e não repetido aqui):** [[00-HOME]], [[REA]], `docs/PUMPFUN.md` §10, [[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]], `.claude/state/rea-pumpfun-capture-2026-10-06.md`. O que mudou no meu plano: `/user-trades/{wallet}`, `/users/{id}/overview`, `/pnl-leaderboard`, `/competitions*` e `POST /pnl/coin/{mint}/holders` já são HTTP verificada em §10.3; aqui só entra o que a **página de perfil chama e §10 não tinha**.

## Resposta curta

1. **Perfil:** a página de uma carteira (visitante anônimo) chama cerca de **20 rotas distintas** em dois hosts de API (`frontend-api-v3`, `profile-api`). **Oito são novas em relação ao mapa** (carteira truncada `2M2v..ENNZ`): `GET /portfolio-summary?user&period=1d`, `GET /portfolio-summary/chart?user&period=1d`, `GET /user-portfolio/{w}` com `filter`/`sortBy`/`pageSize`, `GET /callout/list/{w}?limit&sortBy=TIMESTAMP&sortOrder=DESC`, `GET /users/{w}/achievements` (+ `GET /achievements/catalog`), `GET /coins-v2/user-created-coins/{w}?limit&offset`, `GET profile-api /balance/tokens/{w}`, e `POST profile-api /wallet-overview` (200 anônimo; estava como "não testada").
2. **Competições:** **não achei página própria utilizável pelo visitante.** `https://pump.fun/competitions` e `https://pump.fun/competitions/solo-cuptober` devolveram HTTP 200, mas a segunda mostra "404 Page not found" no DOM, e **nenhuma das duas chamou `/competitions*`**. A família `/competitions`, `/competitions/{id}` e `/entries/{entry}/highlights` só foi vista na `/leaderboard` (captura anterior). O caminho de interface da competição não foi encontrado; **não tentei adivinhar mais caminhos** (orçamento de 3 páginas esgotado). Para a pergunta (2), o que vale é a `/leaderboard` já capturada e o HTTP de §10.3.
3. **Ponto no tempo:** **nada do que vi tem carimbo próprio demonstrado.** Dois candidatos precisam de leitura verificada de corpo: `portfolio-summary/chart` (nome sugere série; **não sei** se tem pontos datados nem períodos além de `1d`) e `callout/list` (ordenado por `TIMESTAMP`: cada "chamada" pública provavelmente tem data; é lista viva, apagável). O resto é estado de agora. **Só serve para observar daqui para a frente**, pela foto noturna nossa.

## Capturas

| # | Página | Data | Método | Resultado |
|---|---|---|---|---|
| 1 | `https://pump.fun/profile/2M2v..ENNZ` | 06/10/2026 (hora UTC exata não registrada pelo REA no resumo) | REA capture, headless, 15 s, `network` + `websockets` | OK; 0 × 403/429; 0 × 5xx |
| 2 | `https://pump.fun/competitions` | idem | idem | HTTP 200; sem chamada a `/competitions*`; só a casca comum |
| 3 | `https://pump.fun/competitions/solo-cuptober` | idem | idem + DOM final | HTTP 200 com corpo "Page not found" (404 mole); só a casca comum |

Sem `cleanup_incomplete` (um cenário por página). Cloudflare: `cdn-cgi/challenge-platform/*` carregou sozinho (scripts passivos, como na captura anterior); nenhum desafio exibido, nenhum 403/429. 401 apenas onde esperado. Os dois WebSockets `prod-v2.nats…` e `unified-prod.nats…` abriram (frames **binários** de 208, 77 e 75 bytes enviados; REA não decodifica). O mapa já diz que os NATS exigem autenticação.

## Rotas e campos — página de PERFIL

Etiquetas: **observada** = o navegador chamou (REA), **no bundle** = só no registro tipado, **verificada** = li a resposta, **inferência** = deduzi. Aqui só há observada e inferência; parâmetros são nomes de consulta, não conteúdo.

| Rota (host) | Parâmetros | Status | Tag | O que parece ser (inferência) |
|---|---|---|---|---|
| `GET frontend-api-v3 /portfolio-summary` | `user={w}`, `period=1d` | 2xx | observada | **NOVA.** resumo de PnL/valor da carteira num período; só `1d` pedido pela tela padrão (outros períodos? não sei) |
| `GET frontend-api-v3 /portfolio-summary/chart` | `user={w}`, `period=1d` | 2xx | observada | **NOVA.** gráfico do portfólio; **pode ser série datada** (pelo nome), **forma não lida** |
| `GET frontend-api-v3 /user-portfolio/{w}` | `filter=all`, `page=0`, `pageSize=100`, `sortBy=PNL`; e `filter=open`, `sortBy=POSITION_SIZE` | 2xx | observada | posições por PnL e abertas por tamanho; a rota existe em §10.3 (HTTP, 195 KB com `limit=5`), mas **esses parâmetros** são novos |
| `GET frontend-api-v3 /callout/list/{w}` | `limit=100`, `sortBy=TIMESTAMP`, `sortOrder=DESC` | 2xx | observada | **NOVA.** "chamadas" públicas da carteira, **ordenadas por data**; §10.3 só tinha o `callout{}` embutido na posição |
| `GET frontend-api-v3 /users/{w}/achievements` | — | 2xx | observada | **NOVA.** conquistas; não sei se cada uma tem data |
| `GET frontend-api-v3 /achievements/catalog` | — | 2xx | observada | **NOVA.** catálogo global de conquistas |
| `GET frontend-api-v3 /coins-v2/user-created-coins/{w}` | `limit=1&offset=0` e `limit=50&offset=0` | 2xx | observada | **NOVA.** moedas criadas pela carteira |
| `GET frontend-api-v3 /users/{userId}/overview` | `userId` é um UUID, não o endereço | 2xx | observada | já HTTP em §10.3. O UUID **não veio de `/users/{w}`** (essa rota não foi chamada); provavelmente veio da linha do `/pnl-leaderboard`, que traz `userId` |
| `GET frontend-api-v3 /pnl-leaderboard` | `period=weekly&sort=combined&limit=100`; `period=daily&sort=combined&limit=20` | 2xx | observada | a página busca o quadro semanal inteiro e o diário (20), provavelmente para **achar o rank e o `userId` da carteira** |
| `GET frontend-api-v3 /groups/of/{w}` | `limit=1` | **401** | observada | **NOVA, bloqueada.** exige sessão; registrar e deixar |
| `POST profile-api /wallet-overview` | corpo não retido | 200 | observada | estava em "não testada (fora do registro)"; corpo desconhecido; candidata a cartão de cabeçalho do perfil (inferência fraca) |
| `GET profile-api /balance/summary/{w}` | `multi_chain=true` | 2xx | observada | já HTTP em §10.3 |
| `GET profile-api /balance/tokens/{w}` | `page=1&size=10`; `page=1&size=200&chain=all` | 2xx | observada | **NOVA.** saldo por token (holdings atuais), páginas até 200 |
| casca comum: `POST /profiles/verified`, `POST /coins-v2/mints`, `GET /coins/top-tokens/mints?withChains`, `/sol-price`, `/auth/disabled-features`, `/auth/my-profile` | — | 200/201; `/auth/my-profile` **401** | observada | já conhecida |

**Ausentes na carga inicial do perfil (importante):** `GET /users/{address}`, `GET /following/v3/*/count`, `GET /user-trades/{w}` e `GET /user-positions/{w}` **não foram chamadas**. Os seguidores do perfil devem vir de `/users/{userId}/overview` (inferência; §10.3 diz `counts{followers,following}`), e o **histórico de trades da carteira não aparece na carga inicial** (a aba de trades provavelmente carrega ao clicar; **não clicamos**).

## Como o site faz (descrição própria)

**Perfil.** A página é montada a partir do endereço da URL. Ela busca o quadro de PnL (semanal 100 linhas e diário 20), provavelmente para localizar o dono e obter o identificador interno do usuário (`userId`); com ele pede o `overview` (seguidores, selo). Em paralelo, já pelo endereço, pede o resumo e o gráfico do portfólio no período de 1 dia, a lista de posições (todas por PnL; abertas por tamanho), os saldos por token em outro host (`profile-api`), as moedas criadas, as chamadas públicas (callouts) por data e as conquistas. Uma rota de "grupos" só responde com sessão. A atualização depois da carga é, provavelmente, por WebSocket NATS autenticado e não por nova chamada de rota (inferência: não vi repetição de chamada em 15 s).

**Competições.** Nas duas páginas pedidas, nada além da casca comum (hora do servidor, textos i18n, ranking diário de 20 linhas, `auth/*`). A competição aparece dentro de `/leaderboard` (captura anterior: `/competitions`, `/competitions/{id}`, `highlights?limit`). Hipótese de trabalho (inferência): a rota de interface tem outro nome ou só abre por link a partir de `/leaderboard`. As rotas de API estão em §10.3 (HTTP: 2 ao vivo, 20 506 participantes em `solo-cuptober`, prêmio de US$ 50 mil, #1 100 % marcação).

## Ponto no tempo (`known_at`)

| Dado | Carimbo próprio? | Vale como ponto no tempo? |
|---|---|---|
| `portfolio-summary` (1d) | desconhecido | **Não**: estado de agora de uma janela que acabou de passar |
| `portfolio-summary/chart` (1d) | desconhecido (nome sugere série) | **A verificar.** Mesmo com série datada, é recálculo do site (inclui marcação), não retrato do que era conhecível; serve como descrição, não como histórico |
| `user-portfolio` (todas/abertas) | `openedAt`/`tradeCount` em `/user-positions` (§10.2) | Só **foto nossa** noturna |
| `callout/list` | **provável** (ordena por `TIMESTAMP`) | **Condicional:** cada chamada tem data, mas a lista é viva (apagável); só para frente e com `received_at` nosso |
| `achievements` | desconhecido | Não demonstrado |
| `user-created-coins` | provável carimbo de criação por moeda | Idade do criador é derivável, mas **não** substitui a exclusão do criador por mint (KB-0185) |
| `balance/tokens` | não | Foto nossa |
| `pnl-leaderboard` (rank) | `lastRefreshedAtMs` por linha (§10.3) | Só foto nossa; **não há histórico de rank** em nenhuma rota que o navegador chamou |
| competição (`/competitions/{slug}`) | não vi | Só foto nossa |

**Veredito:** **nenhum dado de perfil ou competição é ponto no tempo por si.** Não há histórico de rank, de seguidores nem de PnL reconstruível para antes da primeira foto noturna nossa. As candidatas só podem ser **observadas daqui para a frente**, com `received_at` e `known_at` por resposta, como já está no KB-0185. Nenhum hoje, nenhum ranking de hoje, serve de critério nem de backtest.

## O que muda em relação ao que já sabíamos

- **Novo:** oito rotas de perfil (lista acima); `profile-api POST /wallet-overview` agora observada (200 anônimo).
- **Novo:** `groups/of/{w}` exige sessão (401).
- **Novo e negativo:** não achei página de competições navegável pelo visitante; o desenho não deve prometer "ler a página de competições", e sim as rotas de API de §10.3.
- **Negativo para o H-030:** o perfil **não** chama `/user-trades` na carga; nada de PnL histórico novo. O melhor candidato continua `/user-trades/{w}` (§10.3) e a nossa fita.
- **Não muda:** quadro, seguidor e competição só valem para frente; não guardar `username`.

## Limites e lacunas

- REA não guarda corpos: **todas as rotas acima são "observadas", não "verificadas"**.
- Uma carteira, um horário, 15 s por página, sem clique em abas (trades, seguidores, conquistas não foram abertas), então rotas lazy de aba não apareceram.
- O REA repete eventos na saída; contei rotas distintas. `user-created-coins` com `limit=1` e `limit=50` são duas chamadas distintas do site.
- A não-chamada de `/competitions*` pode ser hidratação lenta ou rota inexistente; só a segunda página mostra texto de 404 no DOM. Que `/competitions` seja a mesma coisa é inferência (mesma casca de chamadas).
- Não guardei `username`, bio, imagem nem o UUID do usuário.

## Para ler corpo (pedido ao orquestrador)

Despachar `exchange-integration-specialist` para **GETs anônimos** (≤ 60 unidades) sobre uma carteira pública, só para ler **a forma** (campos e tipos, sem nomes de usuário): `portfolio-summary/chart` (períodos aceitos e se há pontos datados), `portfolio-summary` (períodos), `callout/list` (carimbos, campos, comportamento de apagado), `achievements` (datas?), `user-created-coins` (carimbo de criação, `limit` máximo), `balance/tokens` (campos). **Não chamar** `POST /wallet-overview` sem autorização do orquestrador (POST; corpo desconhecido) nem `groups/of` (401).

## Reproduzir

`capture_browser_scenario` com `mode: launch`, Chrome em `C:\Program Files\Google\Chrome\Application\chrome.exe`, `headless: true`, `wait_for_timeout 15000`, eventos `network` + `websockets`, uma página por cenário. Resumo bruto: `.claude/state/rea/2026-10-06-perfil-e-competicoes.md`.

## Ligações
[[Fontes REA]] · [[REA]] · [[EXP-M15-carteiras-vencedoras]] · [[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]] · [[2026-10-06-rea-na-pumpfun-apesar-dos-termos]] · [[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]]
