---
tags: [knowledge, meme, pumpfun, carteiras, smart-money, leaderboard, seguidores, rea, h-030]
tema: o que a pump.fun publica de graça sobre carteiras lucrativas (quadro de PnL, seguidores, trades por carteira, PnL de holders, competições) depois do upgrade de 02/10, e o que disso o H-030 pode e não pode usar
fonte: releitura de 06/10/2026 — bundle + curl (.claude/state/notes-pumpfun-releitura-2026-10-06.md, 64 unidades de orçamento) e observação passiva via REA (.claude/state/rea-pumpfun-capture-2026-10-06.md); docs/PUMPFUN.md §10
fonte_url: https://pump.fun/leaderboard
lido_em: 2026-10-06
evidencia: medição própria (53 chamadas de API anônimas, 6 quadros de PnL de 100 linhas, 800 trades de uma carteira, 1 competição, 1 POST de leitura do PnL de 5 holders) + leitura do registro tipado de 312 rotas do site + observação passiva do navegador (REA, sem login, duas capturas); sem literatura nova
hipotese_testavel: não (leitura de instrumento; serve ao H-030, à onda de fotos de seguidores e ao desenho do universo observado)
astra: discorda em parte (REQUEST_CHANGES no texto: 9 pontos, todos absorvidos) e concorda com a direção — ver Revisoes-Astra/pumpfun-releitura
status: vivo
owner: exchange-integration-specialist
updated: 2026-10-06
confiança: "?"
tipo: pesquisa
hipotese: H-030 (rascunho)
variavel: quadro de PnL do site (realizado, não realizado, selo de verificação) e seguidores por carteira, em D e em D+1
populacao: 6 quadros de 100 linhas do /pnl-leaderboard lidos às 02:25Z de 06/10/2026 (300 carteiras distintas na união); 1 carteira com 800 trades; 1 competição ao vivo; 5 holders de uma moeda
efeito: —
ic: —
veredito: —
proximo_passo: emenda do desenho das fotos antes da migração 1b (fonte por campo, known_at por resposta, is_verified e created_coins_count só descritivos, sem username) e decisão do Everton/quant-engineer sobre o quadro do site como observação adicional (nunca substituindo o universo da fita); tratar o 404 de GET /coins/{mint} no PumpFunRestClient
classe_de_perda: —
mercado: meme
---

# KB-0185 — O que a pump.fun publica sobre carteiras lucrativas, e por que o quadro de hoje não é ponto no tempo (06/10/2026)

## O que afirma

A pump.fun entrega de graça, sem login, mais sobre carteiras do que o mapa de 12/09 registrava: um quadro de PnL com **seis visões** (3 períodos × `realized`/`combined`, 100 linhas cada, **300 carteiras distintas na união
dessa leitura**), seguidores por carteira (três rotas, **sem data**), **trades por carteira** (`/user-trades/{wallet}`, 200 por página; 800 trades recuperados de uma carteira cobrindo ~10,05 dias), o PnL de holders por moeda
(`POST profile-api /pnl/coin/{mint}/holders`) e o sinal "trades do top-50" por moeda. **Nada disso é ponto no tempo**: o quadro de hoje é o resultado de uma janela que já terminou, é vivo (cada linha foi atualizada a poucos
minutos da leitura), é curado pela pump.fun e, no daily, é em boa parte **marcação**. Serve para uma coisa só: **escolher quem observar daqui para a frente**, com `known_at`, como observação **adicional** ao universo da fita.
Achado de passagem, que não é de carteira: **`GET /coins/{mint}` responde 404** (dois mints; `/coins-v3/{mint}` responde 200), e o `PumpFunRestClient.get_curve_state` ainda aponta para ele. Mapa técnico completo: `docs/PUMPFUN.md` §10.

## Onde foi mostrado (próprio)

Leitura de 06/10/2026 02:22–02:56 UTC (23:22–23:56 BRT de 05/10): 53 chamadas de API + 6 páginas + 5 WebSockets = 64 unidades (acima do "~60": 61 até o pedido do orquestrador, 3 para desfazer um "sumiu" que a Astra apontou), 0 × 429, 0 desafios.

| Medida | Valor |
|---|---|
| Quadro `/pnl-leaderboard`: linhas por visão, paginação | 100 (`limit` teto 100), `offset` sem efeito (98 de 100 iguais) |
| Carteiras distintas nas 6 visões | **300** de 600 linhas na união dessa rodada (não é previsão de candidatas novas por dia); daily ∩ weekly 28, weekly ∩ monthly 42, combined ∩ realized no daily 49 |
| Daily combined: PnL somado realizado / não realizado | 3 597 / **11 760** SOL (77 % marcação); 38 linhas com realizado ≤ 0; **14 com gasto de compra ≈ 0** (não prova "tokens recebidos": pode ser compra anterior à janela, custo ausente ou convenção contábil) |
| Selo `isVerified` nas 100 linhas | **59** (daily), **84** (weekly), 80 (monthly); o site descreve o selo como KOL/influenciador, mas **não está demonstrado que seja o mesmo conjunto do R61**, e o #1 semanal tinha `isVerified` true no quadro e `verified` false no `/overview` |
| Posições de topo com mint `…pump` / fora de Solana (daily combined) | 80 de 254 / 61 |
| `sort=realized`: linhas sem compra / com realizado ≤ 0 | 0 / 0; realizado/gasto mediano 0,29 (daily) |
| #1 semanal (carteira `9BMz..QdLU`) | 27 709 seguidores; PnL +4 043 SOL = **−62 realizado + 4 105 não realizado**; posição com `callout` público, nada vendido |
| `/user-trades/{wallet}` | 4 páginas × 200 = 800 trades em **10,05 dias** (10 d 1 h 11 min), sem duplicata, `nextCursor` ainda presente; retenção mínima, janela completa e outras carteiras não demonstradas; RL 600 |
| Seguidores | `/users/{addr}` (RL 30), `/following/v3/followers/count/{id}` (RL 50 observado; 15 B nessa resposta; só `followers`), `/users/{id}/overview` (RL 60; traz `verified`, `createdCoinsCount`); **sem data nem histórico**; as fontes **não coincidem campo a campo** (27 709 × 27 710 em 2 min, `verified` × `isVerified`) |
| `POST profile-api /pnl/coin/{mint}/holders` (corpo `{holders:[≤ 20]}`, do bundle) | 201 anônimo; 5 carteiras: 3 com realizado, **`has_untrusted_basis` em 3 de 5**, `fee_detail` só em parte; uma carteira com 4,2 M tokens na lista de holders voltou com 0 nove minutos depois |
| Competição `solo-cuptober` | 20 506 participantes, prêmio US$ 50 000 ao #1; o #1 tem **+US$ 682 mil, 100 % não realizado, gasto 0** |
| `GET /coins/{mint}` | **404 "Cannot GET"** em 2 mints; `/coins-v3/{mint}` 200 (a §1.1 #2 do mapa dava 200 em 12/09; o código já registra o 404 desde ~25/09, T4.97b/R80) |
| Taxas (`/docs/fees`) | "Last Updated: 20 May 2026", escada idêntica à de 12/09; taxas on-chain de hoje não verificadas aqui |

Dois métodos, créditos separados. **Bundle + curl** (este agente): o chunk `02i6ywd4i-qb4.js` traz o registro tipado de 312 rotas do BFF, com tetos de `limit` e `summary`; é a fonte de "ausente do mapa de 12/09" (que **não** quer dizer
"nasceu depois"). **Observação passiva via REA** (Chrome headless, sem login; capturas da home + `/leaderboard` — 744 requisições, 4 WebSockets — e da página `/coin/{mint}`; corpos não guardados): a tela de ranking chama `/pnl-leaderboard`,
`/pnl-leaderboard/positions?period` e `/user-positions/{wallet}?mints&updatesLimit` **20 vezes** (uma por trader do topo), `/competitions*`, `/home-feed` anônimo, e abre WebSockets em `prod-v2.nats…` e `unified-prod.nats…` (o mapa de 12/09
tinha `multichain-prod.nats` e `/ws/trenches`). A página de moeda chama `POST profile-api /pnl/coin/{mint}/holders`, `livestream-api` (`/kols`, `/livestream*`, `/clips`, `/bounties/v2/tasks`; resposta **não verificada**) e
`GET /mint-positions/{mint}?sortBy&pageSize`. Os três NATS exigem autenticação (medido); o `trenches` ainda responde anônimo (medido).

## O que a literatura/documentação diz

Documentação do próprio site: `/docs/fees` (20/05/2026, páginas conferem) e `/docs/wallet-login-changes` (a entrada por carteira de navegador foi aposentada em 25/09/2026; endereço, seguidores e callouts não mudam). O registro tipado diz
que o quadro "oculta" carteiras banidas e moedas bloqueadas (curadoria) e que `/user-portfolio` público não aplica o piso de poeira do dono. Literatura sobre seguir carteiras: [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]].

## Como mediríamos aqui

Nada novo a testar: é leitura de instrumento. O quadro entra no H-030 só como **gerador de candidatas observadas**, rotulado como observação adicional: cada resposta guarda fonte, período, ordenação e `received_at`; `known_at` precisa ser anterior à aposta **e ao
corte do retrato que selecionou a candidata** (uma candidata lida às 02:25 não existia para o corte de 00:00); entradas e saídas posteriores do quadro não apagam candidatas já observadas. O desenho diz que toda carteira vista na fita entra no ranking: se só as descobertas
pelo site concorressem ao top-30, mediríamos "C-PnL dentro da seleção da pump.fun", outra população. O critério de escolha segue sendo o C-PnL da nossa fita ([[2026-10-05-seguir-carteiras-lucrativas-aprovado]]).

## Hipótese testável no Lab

Nenhuma nova. A previsão do H-030 (NÃO CONFIRMA) não muda. `top-trader-trades` só pode ser **comparação descritiva pré-declarada** (universo de mints, cadência, deduplicação e recepção congelados antes; sem poder confirmar o H-030; uma operação antiga devolvida hoje não era sinal naquele instante).
`is_verified` e `created_coins_count` na foto são **descritivos, sem alterar elegibilidade nem CONFIRMA**.

## O que muda na operação

- **Nada liga.** Nenhum coletor novo; nenhuma rota nova entrou em produção.
- Para o desenho das fotos (item 7 do §9.6 de `docs/design/seguir-carteiras-lucrativas.md`): **não guardar `username`**; congelar fonte por campo (a contagem barata só cobre `followers`), `known_at` por resposta, tratamento de `degraded[]`/ausência (falha não vira `false` nem zero) e a divergência `verified` × `isVerified`;
  `createdCoinsCount` não equivale à exclusão do criador de um mint. Decisão do desenho, não deste mapa.
- `/user-trades/{wallet}` e `POST /pnl/coin/{mint}/holders` conferem **componentes** do PnL por entidade; não reproduzem o C-PnL, as reservas nem a execução. Antes de chamar de auditoria: intervalo fechado, paginação até a fronteira, casamento por tx + evento/perna (slot sozinho não identifica trade),
  inventário de abertura, `received_at` real no backfill.
- **Código:** `PumpFunRestClient.get_curve_state` ainda chama `GET /coins/{mint}` (404 hoje). Quem usa a rota e o que `/coins-v3/{mint}` entrega é decisão do dono do `hunter_exchanges`/meme-worker; esta tarefa não tocou código.
- Um placar de carteiras que a casa mostre ao Everton nunca soma realizado, marcação e selo (regra de KB-0182 mantida).

## Por que pode falhar

- Cada rota nova foi chamada uma ou duas vezes; os limites são cabeçalhos devolvidos, não um teste de carga. O agrupamento dos contadores (`remaining` leu 59 em toda primeira chamada) não foi decifrado; "50/min" não é capacidade garantida.
- Uma leitura, uma hora (02:25Z, noite de segunda para terça no Brasil): a composição do quadro (14 sem compra, 59 verificados) pode mudar com o dia.
- Só li os 101 chunks que a home lista; `unified-prod.nats…` e `boards/trending` (REA) estão em chunks de rota que não li. O REA não guarda corpos: "(REA)" prova que o navegador chamou a rota, não que um cliente sem navegador a receba.
- Os 5 campos novos do `Coin` coincidem em data com o upgrade de 02/10, mas isso é coincidência; a amostra de 70 moedas não dá diff completo de schema.
- As respostas brutas foram apagadas ao fim (dados pessoais); os agregados estão nas notas com o procedimento, mas não são reproduzíveis a partir de respostas preservadas.

## Segunda opinião (Astra)

[[06-DECISIONS/Revisoes-Astra/pumpfun-releitura|pumpfun-releitura]] — REQUEST_CHANGES no texto (9 pontos: separar estado/bundle/não testado, "nova" × "agora chamada", limites e projeções fortes demais, interpretações causais, universo e `known_at`
do corte, fonte por campo das fotos, reconciliação de `/user-trades`, `top-trader-trades` só descritivo, dados pessoais); todos absorvidos no §10 e aqui. Ela concorda com usar o quadro como pista prospectiva, manter C-PnL como critério e tirar `username`.

## Relacionados

[[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[KB-0142-kol-e-call-antecipam-ou-confirmam]] ·
[[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]] ·
[[EXP-M15-carteiras-vencedoras]] · [[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]] · [[2026-10-05-seguir-carteiras-lucrativas-aprovado]]
