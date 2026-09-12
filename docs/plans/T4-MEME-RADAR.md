# Meme Radar — monitoramento de pump.fun (T4)

**Status:** desenho para aprovação antes de codar (mudança de escopo: nova classe de ativo,
nova fonte de dados on-chain, fora de qualquer contrato de execução existente).
**Origem:** Everton, 2026-09-12 — meme coins são o alvo real; pedido explícito é **monitorar**
o mercado pump.fun ("Meme Radar"), **sem execução on-chain nesta fatia**.
**Pesquisa:** `.claude/state/notes-T4.0.md` lista toda URL aberta com data/hora de leitura
(Brasília). Nenhum número deste documento foi inventado — o que não foi confirmado ao vivo está
marcado como "não confirmado" abaixo e nas notas.

## 0. Por que isto não é "mais uma exchange"

`docs/EXCHANGE_INTEGRATION.md` e `docs/RISK_ENGINE.md` descrevem um mundo com orderbook, ticks
regulados por uma exchange e `RiskLimits`/`evaluate()` que só sabem avaliar **entradas SPOT**
contra liquidez de um book real (`MarketLiquidity.asks[]`, `spread_pct`, `MarketSpec.max_leverage
= 1`). pump.fun não tem orderbook: o preço é uma função determinística de duas reservas virtuais
numa curva de bonding (§3). Isso não é um detalhe de implementação — é a razão pela qual esta
fatia é **só leitura**: não existe hoje um `MarketLiquidity`/`MarketSpec` que descreva
honestamente "profundidade" numa curva, e forçar um adapter de execução aqui replicaria, no pior
lugar possível, o mesmo erro que o Risk Engine já baniu no book SPOT (D1: nunca inventar um
número que o insumo não tem). T4.1–T4.3 abaixo **não tocam** `packages/risk-core`,
`hunter_core.execution` nem `services/execution-worker`. Quando (e se) o Everton pedir execução
on-chain, é uma decisão de arquitetura nova, com o `risk-engine-guardian` como revisor
obrigatório desde o primeiro desenho — não uma extensão deste plano.

## 1. Objetivo

Dar ao Everton e à Astra visibilidade contínua do mercado pump.fun — criação de tokens,
progresso da bonding curve, migração para PumpSwap, features de risco de rug/wash — na mesma
disciplina do resto do projeto: eventos normalizados, sem campo cru vazando sem rótulo,
fixtures gravadas, reconexão com gap declarado. Sem ordem, sem carteira, sem `RiskDecision`.
Serve para (a) o plantão de mercado (T3.64) ter uma fonte nova de hipóteses testáveis sobre
memecoins, e (b) preparar terreno de dados para uma decisão futura e separada sobre execução.

## 2. Fontes — tabela de custo/chave/limite/confiabilidade

| Fonte | O que dá | Chave/custo | Limite observado ou documentado | Confiabilidade | Leitura |
|---|---|---|---|---|---|
| Programa on-chain `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` (bonding curve) + `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` (PumpSwap) | Verdade de base: toda criação/compra/venda/migração é uma instrução deste programa | Grátis (é o próprio ledger) | Nenhum limite próprio — o limite é do RPC/Geyser que você usa para ler o programa (linha abaixo) | Alta — é a fonte primária, sem intermediário | docs.solanatracker.io/guides/pumpfun-program, 2026-09-12 |
| `frontend-api.pump.fun` (domínio antigo, citado em tutoriais 2024/2025) | — | — | **Testado ao vivo agora: HTTP 530, erro Cloudflare 1016 (DNS de origem não resolve)** | **Nula hoje — parece desativado/substituído** | curl direto, 2026-09-12 01:37 BRT |
| `frontend-api-v3.pump.fun` (domínio atual) | Metadados do token, estado da curva (`virtual_sol_reserves`, `virtual_token_reserves`, `real_token_reserves`, `complete`, `market_cap`), listagens | Grátis, sem chave para GET simples | **Testado ao vivo: 60 req/60s por IP** (cabeçalho `x-ratelimit-*`); sem desafio JS/cookie bloqueante para este endpoint | Média — é a API que o próprio site usa, mas não documentada publicamente e pode mudar sem aviso (o domínio anterior já mudou) | curl direto, 2026-09-12 01:37 BRT |
| PumpPortal WS (`wss://pumpportal.fun/api/data`) | `subscribeNewToken` e `subscribeMigration` em tempo real; `subscribeTokenTrade`/`subscribeAccountTrade` por token/conta | `subscribeNewToken`/`subscribeMigration` **grátis**; os outros dois **0,01 SOL por 10.000 eventos**, exige chave + carteira com ≥ 0,02 SOL | Uma conexão só (várias conexões simultâneas podem levar a banimento por hora) | Média-alta — é a integração mais citada e ativamente mantida por terceiros para este fim | pumpportal.fun/data-api/real-time/, 2026-09-12 01:24 BRT |
| RPC Solana público (`api.mainnet-beta.solana.com`) | Leitura genérica de contas/transações/logs | Grátis | ~100 req/10s por IP (~10 req/s), documentado como "só para experimentação" | Baixa para produção — a própria Solana desaconselha | solana.com/docs/references/clusters (via busca), 2026-09-12 01:34 BRT |
| Helius (RPC + Geyser gerenciado) | RPC dedicado, webhooks, Geyser | Free tier com chave grátis; planos pagos acima | Free: **10 req/s** | Alta (provedor especializado em Solana) | helius.dev/blog, 2026-09-12 01:33 BRT |
| QuickNode | RPC dedicado | Free tier com chave grátis (**não confirmado se é permanente ou trial de 7 dias — fontes secundárias conflitam**) | Uma fonte cita 10M créditos/mês + 15 req/s; outra descreve como trial de 7 dias | Incerta até checar a página de pricing oficial | busca agregada, 2026-09-12 01:35 BRT — **não confirmado, ver notas §4** |
| Triton One | RPC/Geyser dedicado | Pago/enterprise (não pesquisado a fundo) | Não pesquisado | Não avaliada | não aberto nesta rodada |
| Bitquery (Pump.fun API) | Trades com preço/mcap USD, OHLCV até 1s, criação em tempo real, progresso da curva, holders, top traders | Chave obrigatória; trial 7 dias (1.000 pontos, 100 créditos MCP, 2 streams); pago depois | 30/90/240 req/min conforme plano (Personal/Pro/Scale) | Alta para quem já paga — cobertura ampla e documentada | docs.bitquery.io, 2026-09-12 01:31 BRT |
| Dune / Moralis | Analytics/API sobre pump.fun | Ambas keyed/pagas | Não pesquisado nesta rodada | Não avaliada | não aberto nesta rodada |

**Decisão proposta para T4.1 (ver §6 "decisões para o Everton"):** WS PumpPortal (grátis, os dois
eventos que importam para o radar) + RPC Solana **próprio, com chave** (Helius free tier como
primeiro corte — 10 req/s cobre leitura de estado de curva sob demanda, não polling de 200
tokens/segundo) para confirmar e enriquecer o que o WS manda, nunca o público sem chave em
produção. `frontend-api-v3.pump.fun` como fonte **complementar e best-effort** (60 req/60s,
domínio não documentado oficialmente) — nunca fonte única de nada que o scanner decida.

## 3. A curva de bonding — o que foi confirmado ao vivo (não só lido em blog)

Curva de produto constante (`x * y = k`), onde `x` = reserva virtual de SOL e `y` = reserva
virtual do token (`pump.fun/docs/bonding-curve`, 2026-09-12). Números **observados numa chamada
real** a `frontend-api-v3.pump.fun` em 2026-09-12 01:37 BRT, para um token recém-criado
(`complete=false`):

```
virtual_sol_reserves   = 30 000 000 000 lamports  = 30 SOL
virtual_token_reserves = 1 073 000 000 000 000     = 1 073 000 000 tokens (6 casas decimais)
total_supply            = 1 000 000 000 000 000     = 1 000 000 000 tokens
real_token_reserves     =   793 100 000 000 000     =   793 100 000 tokens
real_sol_reserves       = 0 (nenhuma compra ainda)
```

Isso confirma os números citados por terceiros (30 SOL / 1,073 bi tokens virtuais iniciais,
~200M tokens "reservados" — aqui exatos em 1B − 793,1M = 206,9M). O preço marginal em qualquer
ponto é `sol_reserves_virtuais / token_reserves_virtuais`; `market_cap` que a própria API
devolve já faz essa conta multiplicada pelo `total_supply`. **Limiar de graduação**: citado por
múltiplas fontes secundárias como ~85 SOL acumulados / ~US$ 69.000 de market cap — **não
confirmei esse número numa chamada ao vivo contra um token perto de graduar**, então o plano o
trata como "referência de mercado, a validar no T4.1 lendo o campo `complete`/estado real da
curva no momento da migração", não como constante fixada no código sem verificação.

Na graduação: "a curva é fechada e o pool inteiro é migrado atomicamente para o PumpSwap"
(`pump.fun/docs/bonding-curve`) — hoje a maior parte do fluxo vai para PumpSwap, não Raydium
(mudança desde o lançamento do PumpSwap em 2025, confirmada por fonte secundária de 2026-06-10).
Taxa de negociação na curva: **1,25%** total, dividida entre criador e protocolo. Depois da
migração, PumpSwap cobra **0,30%** por trade (0,20% LP + 0,05% protocolo + 0,05% criador do
token) — uma fonte secundária menciona faixas de 0,02%–0,20% de LP por tier de market cap, não
confirmada na página primária.

## 4. Números do mercado (com data de leitura — ver notas §6 para a ressalva de volatilidade)

- Tokens criados/dia: citado em ~30.000–52.000/dia ao longo de 2026 (média ~38 mil em uma janela
  de 29 dias, ago–set/2026); pico de ~42.000/dia citado num artigo de 10/06/2026.
- Taxa de graduação: **<2%** histórico acumulado (Solana Compass, 10/06/2026); medições pontuais
  variam muito ao longo do ano (0,198% em mai–jun, ~0,26% em meados de junho, >1% em janeiro,
  2,7% em início de setembro/2026) — **é uma métrica volátil por regime de mercado, não uma
  constante**; o Meme Radar deve medir a própria taxa continuamente, não herdar um número de
  blog.
- Tempo de vida típico: não encontrei uma fonte primária com distribuição de tempo até
  abandono/graduação/rug — fica como métrica a produzir pelo próprio `meme_snapshots` (T4.2),
  não a citar de terceiros.
- "Market cap" na curva é **sempre teórico**: `preço_marginal_no_ponto_atual × total_supply`,
  nunca o valor que se conseguiria realmente extrair vendendo tudo de uma vez (a curva tem
  slippage embutido — vender uma fração grande do supply move o preço na própria curva, o mesmo
  problema de "profundidade" que motivou o §0).

## 5. Modelo de dados proposto (Postgres)

Convenções seguidas de `docs/DATABASE.md` §1 (não lido por completo nesta rodada — usei os
padrões já visíveis no arquivo: particionamento `PARTITION BY RANGE` para séries temporais de
alto volume, `Decimal`/`numeric` para preço, criação de partição com antecedência via
`infra/scripts/create_partitions.py`, retenção com poda). Estas tabelas são **globais** (dado de
mercado on-chain, não por tenant) — mesma categoria de `candles`/`market_snapshots` (§4 do
DATABASE.md), não de `portfolios`/`positions` (que são por tenant).

```
meme_tokens
  mint                text PRIMARY KEY            -- endereço da mint, é a chave natural
  name                text
  symbol              text
  creator             text
  created_at          timestamptz NOT NULL
  uri                 text                        -- metadata off-chain (IPFS), rótulo explícito
  program             text NOT NULL               -- 'pump' | outro, se o radar crescer além do pump.fun
  virtual_sol_reserves    numeric
  virtual_token_reserves  numeric
  real_sol_reserves       numeric
  real_token_reserves     numeric
  total_supply            numeric
  complete            boolean NOT NULL DEFAULT false   -- graduou?
  migrated_at         timestamptz
  pool_address        text                        -- pool PumpSwap pós-migração
  bonding_curve       text                        -- endereço da conta da curva
  last_seen_at        timestamptz NOT NULL        -- último evento observado; alimenta o "stale" do /system

meme_trades   -- PARTITION BY RANGE (ts), por mês, mesmo padrão de `candles`/`liquidations`
  signature   text NOT NULL                       -- assinatura da tx Solana, dedupe natural
  mint        text NOT NULL
  side        text NOT NULL                       -- 'buy' | 'sell', o taker da curva
  sol_amount     numeric NOT NULL
  token_amount   numeric NOT NULL
  price          numeric NOT NULL                 -- sol_amount/token_amount no evento, nunca recalculado depois
  wallet         text NOT NULL
  ts             timestamptz NOT NULL             -- horário do bloco/tx, nunca o received_at
  received_at    timestamptz NOT NULL
  source         text NOT NULL                    -- 'pumpportal_ws' | 'rpc_backfill', rastreável (padrão EXCHANGE_INTEGRATION.md §2)
  PRIMARY KEY (signature, ts)                      -- ts na PK por causa do particionamento por RANGE

meme_snapshots   -- PARTITION BY RANGE (ts), 1 linha/minuto/mint, mesmo padrão de `market_snapshots`
  mint                    text NOT NULL
  ts                      timestamptz NOT NULL     -- fechamento do minuto
  price                   numeric
  market_cap              numeric
  curve_progress_pct      numeric                  -- real_sol_reserves / limiar de graduação observado
  unique_buyers_1m        integer
  buy_sell_ratio_1m       numeric                  -- contagem, não notional — declarar qual no código
  top10_holder_share_pct  numeric                  -- concentração, sinal clássico de rug
  creator_sold            boolean                  -- o criador vendeu da própria posição?
  PRIMARY KEY (mint, ts)
```

Nenhum campo cru da API/WS vaza sem rótulo — `source` em `meme_trades` cumpre o mesmo papel que
`metadata` rotulado no `NormalizedMarket` (`EXCHANGE_INTEGRATION.md` §2). `meme_snapshots` é o
equivalente do `feature_snapshots` do resto do projeto (DATABASE.md §4): granularidade de
minuto, série derivada, nunca fonte primária.

## 6. As três primeiras tarefas

### T4.1 — Adapter (PumpPortal WS + Solana RPC leitura)

**Escopo:** pacote novo `packages/exchange-adapters/hunter_exchanges/pumpfun/` (mesma família de
`hunter_exchanges`, mesma fronteira: só este pacote fala o dialeto pump.fun/Solana, devolve
modelos normalizados próprios — `NormalizedMemeTokenCreated`, `NormalizedMemeTrade`,
`NormalizedMemeMigration`). Segue a estrutura já vista em `binance_spot/` (`ws.py` cliente,
`normalize.py` funções puras raw→normalizado, `rest.py` para chamadas de enriquecimento via RPC,
fixtures gravadas em `testing/fixtures/`).

- Cliente WS assina `subscribeNewToken` e `subscribeMigration` (grátis) numa única conexão,
  com o mesmo padrão de reconexão/backoff de `binance/connection.py` (exponencial, jitter,
  contador de gerações de conexão para o `CoverageTracker` saber que houve gap).
- `subscribeTokenTrade` fica **fora do escopo do T4.1** por padrão (é pago por evento) —
  T4.1 entrega o encanamento pronto para ligá-lo por token quando o Everton decidir (ver §7,
  decisão "quais features primeiro").
- Enriquecimento por RPC (leitura de conta da bonding curve para reservas atuais) usa o
  provedor decidido em §7 — nunca o RPC público sem chave em produção (§2).
- Parsing de eventos: usar a IDL oficial (`pump-fun/pump-public-docs`) como referência de
  verdade; `chainstacklabs/pumpfun-bonkfun-bot` (985 estrelas, ativo em 2026-08) como leitura de
  implementação de referência para os discriminadores de evento (create/buy/sell/migração) —
  **não copiar código dele**, só usar como confirmação de formato ao lado da IDL.
- Testes: fixtures gravadas de mensagens WS reais (payload de `subscribeNewToken`/
  `subscribeMigration`) e de uma resposta de conta de curva via RPC; cenários obrigatórios
  espelhando `EXCHANGE_INTEGRATION.md` §6: mensagem malformada, reconexão com gap, evento de
  migração antes do evento de criação ter sido visto (a curva pode já existir antes do adapter
  subir).

**Critério de aceite:** `pytest` do pacote roda offline com fixtures; um teste `-m live`
opcional conecta no WS real e recebe pelo menos um `subscribeNewToken` dentro de 60 s (tokens
novos aparecem a um ritmo de vários por minuto — não deve dar timeout); nenhum código deste
pacote é importado por `execution-worker`, `risk-core` ou qualquer caminho que crie ordem.

### T4.2 — Storage + features do scanner

**Escopo:** consumidor que grava `meme_tokens`/`meme_trades`, gera `meme_snapshots` por minuto
(mesmo padrão de agregação de `market-worker`/`scanner-worker` para candles/features, mas para
mint em vez de símbolo de exchange). Calcula `curve_progress_pct`, `unique_buyers_1m`,
`buy_sell_ratio_1m`, `top10_holder_share_pct` (via RPC — leitura de holders da mint),
`creator_sold` (compara wallet do criador contra `side=sell` em `meme_trades`).

**Critério de aceite:** para um mint observado por ≥ 30 minutos em ambiente de teste (fixture
gravada, não produção), `meme_snapshots` tem uma linha por minuto sem buraco, `curve_progress_pct`
bate com o `real_sol_reserves` observado no evento de trade mais recente daquele minuto, e o job
de partição (`infra/scripts/create_partitions.py`, mesma convenção de `candles`/
`market_snapshots`) cria a partição do mês corrente para as duas tabelas particionadas antes do
primeiro insert.

### T4.3 — API + web "Meme Radar"

**Escopo:** endpoint(s) read-only em `apps/api` para listar tokens recentes, ordenar por
`curve_progress_pct`/volume/idade, ver a série de `meme_snapshots` de um mint; tela nova em
`apps/web` ("Meme Radar") — lista + gráfico de progresso da curva, sem nenhum botão de
compra/venda (não é feature deste corte).

**Critério de aceite:** tela carrega com dado real do ambiente de desenvolvimento (mesmo padrão
de "sempre polido, checado no navegador com dado real" — `frontend-always-polished`), mostra
claramente que é **só monitoramento** (rótulo explícito na UI, não deixar ambíguo que dá para
operar dali), e o endpoint responde em paginação (não um `SELECT *` sem limite numa tabela que
cresce ~40 mil linhas novas de token por dia).

## 7. Riscos — honestos, sem suavizar

- **Rugs e bundlers:** um criador pode comprar sua própria curva com várias wallets
  (bundling) para simular demanda antes de largar em cima de compradores reais; `creator_sold`
  e `top10_holder_share_pct` são sinais, não provas — nenhuma feature aqui detecta um bundler
  sofisticado com certeza.
- **Wash trading:** contagem de "unique buyers" e "buy/sell ratio" são facilmente manipuláveis
  por quem controla várias wallets — tratar como sinal fraco, nunca como filtro binário de
  "token legítimo".
- **Instabilidade de API:** o próprio domínio principal (`frontend-api.pump.fun`) mudou e o
  antigo está morto **hoje** (§2) — qualquer integração que dependa de um endpoint HTTP não
  documentado oficialmente pode quebrar sem aviso. O WS do PumpPortal é de terceiro, não da
  pump.fun — mesma classe de risco.
- **Rate limit sem chave:** 60 req/60s por IP no `frontend-api-v3` não sustenta polling de
  milhares de mints; por isso o desenho depende do WS (empurra eventos) e do RPC com chave
  para enriquecimento sob demanda, não de polling da API HTTP como fonte primária.
- **Preço na curva não é book de CEX:** não há bid/ask, não há profundidade real — o "preço" é
  uma função de duas reservas virtuais, e o "market cap" é sempre teórico (§4). Qualquer
  comparação com os conceitos de `MarketLiquidity`/`spread_pct` do resto do projeto é enganosa
  se não for explicitada.
- **Fora da doutrina do Risk Engine:** `RISK_ENGINE.md` v2.5 é inteiramente sobre entradas e
  saídas SPOT com `MarketSpec.max_leverage = 1` e liquidez de book real. Nada neste plano cria
  `EntryProposal`/`ExitProposal` para um mint pump.fun — o motor de risco **não tem hoje**
  nenhum insumo que descreva honestamente liquidez de bonding curve, e não é escopo deste
  documento inventar um. Monitoramento apenas.

## 8. Decisões para o Everton

1. **Provedor de RPC pago/keyed: sim ou não, e qual?** Recomendação do pesquisador: Helius free
   tier (10 req/s, com chave grátis) para começar — cobre enriquecimento sob demanda, não
   polling maciço. Se o volume de tokens simultâneos monitorados crescer, é decisão futura subir
   de tier (custo real, não descoberto nesta pesquisa).
2. **Retenção de armazenamento:** quantos meses de `meme_trades`/`meme_snapshots` manter? Dado
   um volume de ~30–50 mil tokens/dia e <3% de graduação, a maioria dos mints morre em minutos/
   horas — proposta: reter granularidade completa por 30 dias e, depois, só os mints que
   graduaram (`complete=true`) por período mais longo, descartando o ruído de tokens que nunca
   saíram do zero. Precisa de decisão explícita antes do T4.2 criar a política de partição.
3. **Quais features primeiro:** T4.1/T4.2 cobrem criação + migração (grátis) e trades via RPC
   sob demanda; ligar `subscribeTokenTrade` do PumpPortal (pago, 0,01 SOL/10k eventos) dá trade
   a trade em tempo real para os tokens que o Everton quiser acompanhar de perto — mas não
   escala para todos os ~40 mil tokens/dia sem custo relevante. Perguntar: começar só com
   criação+migração+RPC sob demanda (grátis, mais lento) ou já pagar pelo trade feed de um
   subconjunto (ex.: só tokens que passam de X% de progresso na curva)?
