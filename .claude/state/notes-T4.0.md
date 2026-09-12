# Notas de pesquisa — T4.0 Meme Radar (pump.fun)

Sessão de pesquisa em 2026-09-12, madrugada (BRT = UTC−3). Todas as urls abaixo foram
efetivamente abertas (WebSearch/WebFetch/curl) nesta sessão; os dois `curl` diretos contra
`frontend-api*.pump.fun` têm timestamp exato do cabeçalho `Date` do servidor (convertido para
BRT). Os demais foram lidos entre ~01:20 e ~01:40 BRT do mesmo dia — não guardo timestamp por
chamada individual do WebSearch/WebFetch, só a janela da sessão.

## 1. Programa Solana / IDL oficial

- https://docs.solanatracker.io/guides/pumpfun-program — lido 2026-09-12 ~01:22 BRT. Programa
  da bonding curve: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` (atenção à caixa: `EF8rr`
  minúsculo). Programa do PumpSwap AMM: `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`.
- https://github.com/pump-fun/pump-public-docs — lido 2026-09-12 ~01:36 BRT (via API do GitHub,
  `pushed_at`). Repo oficial da pump.fun com o IDL público; 450 estrelas, último push
  2026-07-15T18:22:33Z. É a fonte que os SDKs de terceiros vendorizam (ver §5).
- https://pump.fun/docs/bonding-curve — lido 2026-09-12 ~01:25 BRT. Confirma curva de produto
  constante (`x*y=k`, reservas virtuais de SOL e do supply do token), taxa total de negociação de
  **1,25%** dividida entre criador e protocolo, e que na graduação "the curve is closed and the
  entire liquidity pool is migrated atomically to PumpSwap" — a página NÃO publica os números
  exatos de reserva virtual nem o limiar de graduação (isso veio da API ao vivo, §2).

## 2. `frontend-api*.pump.fun` — testado ao vivo, não só lido

- `https://frontend-api.pump.fun/coins?...` — testado com `curl` em 2026-09-12 04:37:04 UTC
  (01:37:04 BRT). Resposta: **HTTP 530, Cloudflare error code 1016** (erro de DNS/origem — a
  Cloudflare não encontra o host de origem). Este domínio antigo, muito citado em tutoriais de
  2024/2025, parece **desativado ou substituído** hoje.
- `https://frontend-api-v3.pump.fun/coins?offset=0&limit=1&sort=created_timestamp&order=DESC` —
  testado com `curl` em 2026-09-12 04:37:07 UTC (01:37:07 BRT). Resposta: **HTTP 200**, JSON
  direto, **sem exigir cookie/challenge JS** para este GET simples (só recebeu `set-cookie:
  __cf_bm`/`_cfuvid` de telemetria da Cloudflare, não um desafio bloqueante). Cabeçalhos de rate
  limit presentes: `x-ratelimit-limit: 60`, `x-ratelimit-remaining: 59`, `x-ratelimit-reset: 60`
  — ou seja, **60 requisições por janela de 60 s por IP**, sem chave. Não testei volume maior
  nem se a Cloudflare bloqueia depois de estourar (não quis arriscar banimento de IP da sessão).
  Corpo confirma os números da curva de um token real (mint `AFbdSsy2ZW3eoTsWfkKMgpzC7VUA3EbY36RfM1i6ymPM`):
  `virtual_sol_reserves=30000000000` (30 SOL em lamports), `virtual_token_reserves=1073000000000000`
  (1,073 bilhão de tokens, 6 casas decimais), `total_supply=1000000000000000` (1 bilhão de
  tokens), `real_token_reserves=793100000000000` (793,1 milhões de tokens — bate com "~200M
  reservados para o pool" citado em blogs de terceiros), `complete=false`, `market_cap`/
  `market_cap_usd` calculados pela própria API. **Não é documentação oficial publicada, é uma
  chamada real que fiz e o corpo que voltou** — não uso isso como número "documentado", uso como
  "observado ao vivo em 2026-09-12".

## 3. PumpPortal — WS de dados

- https://pumpportal.fun/data-api/real-time/ — lido 2026-09-12 ~01:24 BRT. URL de conexão
  `wss://pumpportal.fun/api/data?api-key=your-api-key-here`. Métodos: `subscribeNewToken`
  (criação, **grátis**), `subscribeMigration` (migração para PumpSwap, **grátis**),
  `subscribeTokenTrade` (trades de tokens específicos, **cobrado**: 0,01 SOL por 10.000 eventos),
  `subscribeAccountTrade` (trades de contas específicas, mesma cobrança). Os dois métodos pagos
  exigem chave PumpPortal com carteira vinculada com saldo mínimo de 0,02 SOL. Aviso explícito:
  não abrir uma conexão WS por token/conta — usar uma única conexão e mandar todos os
  `subscribe*` nela; abrir várias conexões pode levar a banimento por hora.
- https://solanacompass.com/projects/pumpportal — lido 2026-09-12 ~01:24 BRT (contexto geral do
  projeto, sem números novos de limite).

## 4. RPC Solana

- https://www.helius.dev/blog/top-solana-rpcs-helius-vs-other-node-providers — lido 2026-09-12
  ~01:33 BRT. Free tier da Helius: **10 requisições/segundo**, acesso a devnet, indicado para
  protótipos/projetos pequenos — precisa de chave (conta grátis).
- (agregado de várias páginas na mesma busca, sem abrir cada uma individualmente) dRPC lidera
  free tier em CU/mês (50M), Alchemy em seguida (30M), GetBlock com o maior RPS grátis (60) —
  citado apenas como panorama, não usei número específico de nenhuma dessas no plano sem abrir a
  página primária.
- Busca "Solana public mainnet RPC rate limit" — lido 2026-09-12 ~01:34 BRT. O endpoint público
  `api.mainnet-beta.solana.com` é documentado como limitado a ~100 requisições/10 s por IP
  (~10 req/s), "para experimentação", explicitamente não recomendado para produção — fonte:
  https://solana.com/docs/references/clusters (referenciada pelo resumo da busca; página oficial
  da Solana).
- https://www.quicknode.com/blog/x402-free-tier (e páginas irmãs na mesma busca) — lido
  2026-09-12 ~01:35 BRT. QuickNode: free tier citado como 10M créditos de API/mês, 15 req/s,
  sem cartão de crédito — precisa de chave (conta grátis); uma fonte alternativa da mesma busca
  descreve o "free" como um trial de 7 dias, não permanente — **contraditório entre fontes
  secundárias, não confirmei na página de pricing oficial da QuickNode; marcar como incerto no
  plano**.
- Triton One: não encontrei página própria com números de free tier nesta sessão (não abri
  nenhuma página específica da Triton) — **não afirmar nada sobre a Triton no plano além de
  "existe, é paga/enterprise, não pesquisada a fundo"**.

## 5. Provedores de dados keyed/pagos

- https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/Pump-Fun-API/ — lido 2026-09-12 ~01:31
  BRT. Exige token de acesso (conta em account.bitquery.io, "sem etapa de aprovação"). Trial
  grátis de 7 dias: 1.000 pontos de API, 100 créditos MCP, 2 streams simultâneos. Limites pagos:
  30 req/min (Personal), 90 (Pro), 240 (Scale), customizado (Enterprise). Cobre trades com
  preço/mcap/supply por linha, OHLCV até granularidade de 1 s, criação de tokens em tempo real
  (metadata, supply, endereço do dev), progresso da bonding curve, holders, top traders,
  liquidez, taxas do criador.
- Dune e Moralis: **não abri páginas específicas nesta sessão** — não incluo números de limite
  delas no plano; cito apenas como "existem, são pagas/keyed, não abertas nesta rodada" (regra
  de nunca inventar números).

## 6. Números do mercado (com data de leitura)

- https://solanacompass.com/news/pumpfun-launched-42000-tokens-in-one-day-fewer-than-2-will-ever-reach-a-dex
  — publicado 2026-06-10 19:19 UTC, lido 2026-09-12 ~01:28 BRT. "~42.000 tokens novos em 24h";
  "menos de 2% de todos os tokens da pump.fun já graduaram da bonding curve para uma DEX";
  "tokens que graduam agora migram principalmente para o PumpSwap, DEX própria da pump.fun
  lançada no início de 2025, em vez de exclusivamente para o Raydium" (mudança estrutural desde
  2025 — **atenção**: a página oficial `pump.fun/docs/bonding-curve` também confirma migração
  para PumpSwap hoje, não Raydium).
- Busca "pump.fun tokens created per day graduation rate 2026" — lido 2026-09-12 ~01:27 BRT,
  resumo agregando várias fontes que não abri individualmente: 5/ago a 2/set/2026, entre 30.663
  e 52.438 tokens novos/dia (média ~38.268/dia); abril/2026 ~30.000/dia; taxa de graduação em
  início de setembro/2026 medida em 2,7%; entre 8/mai e 10/jun/2026, taxa agrupada de 0,198%;
  meados de junho/2026 caiu para ~0,26% (queda de 80% em três meses); fim de janeiro/2026 subiu
  acima de 1%. **Não abri cada uma dessas páginas-fonte individualmente — é um resumo do motor de
  busca; uso no plano como "citado, faixa ampla e volátil ao longo de 2026", não como número
  único confiável.** A página do Solana Compass (acima, aberta de fato) é a única com número que
  confirmei diretamente: <2% de graduação histórica acumulada, ~42.000 tokens/dia num pico.
- Busca "PumpSwap AMM trading fee percentage LP" — lido 2026-09-12 ~01:30 BRT. Taxa total por
  trade no PumpSwap: **0,30%**, dividida em LP 0,20% + protocolo 0,05% + criador do token 0,05%;
  uma fonte da mesma busca menciona que a taxa de LP pode variar de 0,02% a 0,20% por faixa de
  market cap para tokens graduados — **não abri a página primária dessa variação, então o plano
  cita só a taxa base 0,30% com a ressalva de que pode escalonar**.

## 7. Projetos open-source (GitHub, estrelas e último commit confirmados via API)

Consultas feitas via `api.github.com/search/repositories` e `api.github.com/repos/...` em
2026-09-12 ~01:36–01:39 BRT (timestamps `pushed_at` vêm da própria API do GitHub, não
estimados):

| repo | estrelas | último push | linguagem | observação |
|---|---|---|---|---|
| `chainstacklabs/pumpfun-bonkfun-bot` | 985 | 2026-08-24T08:22:50Z | Python | "trading and sniping bot not relying on any 3rd party APIs" — decodifica eventos on-chain direto (Geyser/logsSubscribe/blockSubscribe), IDL vendorizada do repo oficial pump-fun (commit `9c82f61`), trata `CreateEvent`, `buy_v2`/`sell_v2`, estado da bonding curve e migração para PumpSwap. **Candidato com a decodificação mais limpa e mais bem mantida** dos que abri. |
| `pump-fun/pump-public-docs` | 450 | 2026-07-15T18:22:33Z | — | IDL oficial, fonte que os outros vendorizam |
| `rckprtr/pumpdotfun-sdk` | 821 | 2025-04-11T01:55:46Z | TypeScript | mais estrelas, mas **parado há ~17 meses** (antes da consolidação do PumpSwap) — não recomendo como base |
| `nirholas/pump-fun-sdk` | 121 | 2026-09-12T00:47:19Z | TypeScript | ativo (push no próprio dia), cobre criação/curva/migração AMM/taxas escalonadas/MCP server; menos estrelas que o chainstack mas mantido |
| `nirholas/solana-launchpad-ui` | 15 | 2026-09-07T06:18:04Z | HTML | irrelevante para o adapter |
| `0xfnzero/sol-shred-sdk` | 15 | 2026-08-31T01:54:55Z | Rust | decodificador genérico de programas Solana, não específico de pump.fun |

Conclusão de leitura: `chainstacklabs/pumpfun-bonkfun-bot` (985 estrelas, ativo em agosto/2026)
é a melhor referência para a decodificação de eventos (create/buy/sell/complete-migrate) porque
lê direto do programa (Geyser/logs) com a IDL oficial, sem depender de nenhuma API de terceiro —
exatamente o padrão "ler onchain quando possível" que o projeto já segue para exchanges (Binance
lê REST/WS oficiais, nunca um agregador).

## 8. O que eu NÃO confirmei e por isso não vai como número fechado no plano

- Rate limit de produção do `frontend-api-v3.pump.fun` além de 60 req/60s por IP (não testei
  estourar o limite).
- Números de free tier da Triton One (não abri página própria).
- Pricing exato de Dune/Moralis para pump.fun (não abri).
- A cadência exata "tokens/dia" e "% de graduação" tem fontes conflitantes por período do ano —
  o plano cita como faixa e aponta a data de cada leitura, nunca um número único como "verdade
  atual".
