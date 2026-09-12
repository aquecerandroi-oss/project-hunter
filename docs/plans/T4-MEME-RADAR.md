# Meme Radar — monitoramento de pump.fun (T4)

**Status:** desenho para aprovação antes de codar (mudança de escopo: nova classe de ativo,
nova fonte de dados on-chain, fora de qualquer contrato de execução existente).
**Origem:** Everton, 2026-09-12 — meme coins são o alvo real; pedido explícito é **monitorar**
o mercado pump.fun ("Meme Radar"), **sem execução on-chain nesta fatia**.
**Pesquisa:** `.claude/state/notes-T4.0.md` lista toda URL aberta com data/hora de leitura
(Brasília). Nenhum número deste documento foi inventado — o que não foi confirmado ao vivo está
marcado como "não confirmado" abaixo e nas notas.

**Revisão da Astra (12/09) aplicada:** os números de provedores/taxas/critério de graduação, os
critérios de aceite de T4.1–T4.3 e a seção 8 abaixo foram corrigidos a partir de
`.claude/state/astra-review-t40-plano-meme-radar.md` (commit b648ee7) — marcados inline onde
alteram um número ou critério do desenho original. O parecer dela mantém o veredito "não
liberaria T4.1 ainda"; os pontos de MUST-FIX 2 (dedupe por índice de instrução/finalidade da tx)
e MUST-FIX 3 (procedência completa em tokens/snapshots, `available_at`, versões, checkpoints
duráveis, testes de restart/backfill) **não foram fechados nesta rodada** — ver §8b.

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
| RPC Solana público (`api.mainnet-beta.solana.com`) | Leitura genérica de contas/transações/logs | Grátis | ~100 req/10s por IP (~10 req/s) **e também 40 chamadas por método/10s** (limite adicional por tipo de chamada, achado da revisão da Astra), documentado como "só para experimentação" | Baixa para produção — a própria Solana desaconselha | solana.com/docs/references/clusters, confirmado/complementado por `.claude/state/astra-review-t40-plano-meme-radar.md:17`, 2026-09-12 |
| Helius (RPC + Geyser gerenciado) | RPC dedicado, webhooks; **Geyser/gRPC só a partir do tier Business** | Free: chave grátis; Developer **US$49/mês**; Business **US$499/mês** (necessário para gRPC) | Free: **1.000.000 créditos/mês** (não é limite de req/s, ao contrário do que este documento dizia antes da revisão); Developer: **10.000.000 créditos/mês, 50 RPC/s** | Alta (provedor especializado em Solana) | helius.dev/docs/billing/plans, via `.claude/state/astra-review-t40-plano-meme-radar.md:18`, 2026-09-12 |
| QuickNode | RPC dedicado | Trial de **1 mês** grátis; Build **US$49/mês** (US$34/mês com cobrança anual) | Trial: **10M créditos/mês, 15 req/s** | Confirmado via pricing oficial pela revisão da Astra — deixa de ser "incerta" | quicknode.com/pricing, via `.claude/state/astra-review-t40-plano-meme-radar.md:18`, 2026-09-12 |
| Triton One | RPC/Geyser dedicado | Pago/enterprise (não pesquisado a fundo) | Não pesquisado | Não avaliada | não aberto nesta rodada |
| Bitquery (Pump.fun API) | Trades com preço/mcap USD, OHLCV até 1s, criação em tempo real, progresso da curva, holders, top traders | Chave obrigatória; trial 7 dias (1.000 pontos, 100 créditos MCP, 2 streams, **17 stream-minutos/0,2GB**); Pro **US$99/mês**, Scale **US$299/mês** (histórico adicional cobrado à parte) | 30/90/240 req/min conforme plano (Personal/Pro/Scale); **Personal não inclui streaming** — só Pro/Scale cobrem o que o radar precisaria | Alta para quem já paga — cobertura ampla e documentada | bitquery.io/pricing, via `.claude/state/astra-review-t40-plano-meme-radar.md:19`, 2026-09-12 |
| Dune / Moralis | Analytics/API sobre pump.fun | Ambas keyed/pagas | Não pesquisado nesta rodada | Não avaliada | não aberto nesta rodada |

**Ressalvas da revisão da Astra sobre esta tabela:** um único GET/conexão de teste não prova
quota estável por IP nem SLA — os números marcados "testado ao vivo" acima são amostra pontual,
não garantia contratual; guardar endpoint/resposta datados para qualquer decisão de capacidade.
A documentação pública do PumpPortal mostra conexão feita **com chave**: o teste "grátis" deste
documento não comprova que o acesso anônimo (sem chave) tem a mesma quota/comportamento — tratar
a linha do PumpPortal acima como confiabilidade média-alta **condicionada** a isso, não como fato
fechado. Fontes: `pumpportal.fun/data-api/real-time/`, `solana.com/docs/references/clusters`,
via `.claude/state/astra-review-t40-plano-meme-radar.md:17`.

**Decisão proposta para T4.1 (ver §8 "Decisões para o Everton"):** WS PumpPortal (grátis, os dois
eventos que importam para o radar) + RPC Solana **próprio, com chave** (Helius Free como primeiro
corte — **1.000.000 créditos/mês**, não um limite de req/s: cada chamada RPC consome créditos
variáveis por método; cobre leitura de estado de curva sob demanda, não polling constante de
milhares de tokens simultâneos) para confirmar e enriquecer o que o WS manda, nunca o público sem
chave em produção. Subir para Developer (US$49/mês, 10M créditos/50 RPC/s) é decisão a tomar só
se a medição do ensaio no tier Free justificar (§8, decisão 3). `frontend-api-v3.pump.fun` como
fonte **complementar e best-effort** (60 req/60s, domínio não documentado oficialmente) — nunca
fonte única de nada que o scanner decida.

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
ponto é `sol_reserves_virtuais / token_reserves_virtuais`, mas essa razão só é comparável entre
chamadas se as reservas estiverem em **unidades normalizadas** (SOL e tokens já divididos pelas
casas decimais, não lamports/menor unidade crua) — e mesmo normalizado é o preço **marginal no
ponto atual**, não o preço médio que uma venda real executaria (a curva tem slippage, §4).
`market_cap` que a própria API devolve já faz essa conta multiplicada pelo `total_supply`.

**Critério de graduação, corrigido pela revisão da Astra (12/09):** a condição observável e
estável é `real_token_reserves = 0` **e** `complete = true` no estado da curva — não um limiar de
SOL acumulado. Os números "~85 SOL acumulados / ~US$ 69.000 de market cap" citados por fontes
secundárias **não são um limiar universal vigente comprovado** e não devem virar constante no
código. A **migração** (`migrate`) é uma **instrução separada** da **conclusão** da curva:
completar (`complete=true`, `real_token_reserves=0`) e migrar para o PumpSwap são dois eventos
distintos que T4.1 precisa capturar como tais, nunca fundidos num único estado. Fonte:
`github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md`, via
`.claude/state/astra-review-t40-plano-meme-radar.md:21`.

Na graduação: "a curva é fechada e o pool inteiro é migrado atomicamente para o PumpSwap"
(`pump.fun/docs/bonding-curve`) — hoje a maior parte do fluxo vai para PumpSwap, não Raydium
(mudança desde o lançamento do PumpSwap em 2025, confirmada por fonte secundária de 2026-06-10).
Taxa de negociação na curva: **1,25%** total, dividida entre criador e protocolo — confirmado.
Depois da migração, a taxa no PumpSwap **não é um valor fixo de 0,30%** — correção da revisão da
Astra: pools canônicos variam por capitalização de mercado e pelo par de quote, **de 1,25% até
0,30%** conforme o tier; existem pares cotados em USDC além de SOL. Fonte: `pump.fun/docs/fees`,
via `.claude/state/astra-review-t40-plano-meme-radar.md:20`. T4.1 deve ler a taxa efetiva do pool
no momento da migração, nunca hardcodar um percentual único.

## 4. Números do mercado (com data de leitura — ver notas §6 para a ressalva de volatilidade)

- Tokens criados/dia: citado em ~30.000–52.000/dia ao longo de 2026 (média ~38 mil em uma janela
  de 29 dias, ago–set/2026); pico de ~42.000/dia citado num artigo de 10/06/2026.
- Taxa de graduação: **<2%** histórico acumulado (Solana Compass, 10/06/2026); medições pontuais
  variam muito ao longo do ano (0,198% em mai–jun — **correção da revisão da Astra:** esse número
  vem de uma janela de cobertura efetiva de ~6 minutos no preprint original e é um **limite
  inferior** da taxa de graduação em 24h, não uma estimativa comparável às demais sem ajuste; ver
  preprint corrigido `arxiv.org/abs/2607.02823`, via
  `.claude/state/astra-review-t40-plano-meme-radar.md:22` —, ~0,26% em meados de junho, >1% em
  janeiro, 2,7% em início de setembro/2026) — **é uma métrica volátil por regime de mercado, não
  uma constante**; o Meme Radar deve medir a própria taxa continuamente, não herdar um número de
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
  initial_real_token_reserves numeric                -- capturado no evento de criação; denominador fixo
                                                       -- do progresso (§3), nunca recalculado depois
  total_supply            numeric
  complete            boolean                     -- graduou? NULL = ainda não observado; nunca
                                                    -- DEFAULT false (desconhecido ≠ não graduado —
                                                    -- correção da revisão da Astra, MUST-FIX 2).
                                                    -- Critério: real_token_reserves = 0 E complete =
                                                    -- true (§3); migração é evento separado, ver
                                                    -- migrated_at abaixo.
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
  -- PENDENTE (MUST-FIX 2 da revisão da Astra, não fechado nesta rodada — ver §8b): esta chave
  -- perde trades distintos dentro da mesma transação; precisa de índice de instrução/evento na
  -- PK, além de finalidade da tx e quote/decimals explícitos antes de T4.1 ser liberado.

meme_snapshots   -- PARTITION BY RANGE (ts), 1 linha/minuto/mint, mesmo padrão de `market_snapshots`
  mint                    text NOT NULL
  ts                      timestamptz NOT NULL     -- fechamento do minuto
  price                   numeric
  market_cap              numeric
  curve_progress_pct      numeric                  -- 1 − real_token_reserves/initial_real_token_reserves
                                                     -- (§3, correção da Astra) — NÃO mais
                                                     -- real_sol_reserves/limiar de SOL observado
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
  T4.1 entrega o encanamento pronto para ligá-lo por token quando o Everton decidir (ver §8,
  decisão "quais features primeiro").
- Enriquecimento por RPC (leitura de conta da bonding curve para reservas atuais) usa o
  provedor decidido em §8 — nunca o RPC público sem chave em produção (§2).
- Parsing de eventos: usar a IDL oficial (`pump-fun/pump-public-docs`) como referência de
  verdade; `chainstacklabs/pumpfun-bonkfun-bot` (985 estrelas, ativo em 2026-08) como leitura de
  implementação de referência para os discriminadores de evento (create/buy/sell/migração) —
  **não copiar código dele**, só usar como confirmação de formato ao lado da IDL.
- Testes: fixtures gravadas de mensagens WS reais (payload de `subscribeNewToken`/
  `subscribeMigration`) e de uma resposta de conta de curva via RPC; cenários obrigatórios
  espelhando `EXCHANGE_INTEGRATION.md` §6: mensagem malformada, reconexão com gap, evento de
  migração antes do evento de criação ter sido visto (a curva pode já existir antes do adapter
  subir).

**Critério de aceite (expandido pela revisão da Astra, 12/09):**

- `pytest` do pacote roda offline com fixtures cobrindo: mensagem malformada, reconexão com gap,
  evento de migração antes da criação ter sido vista, **duplicatas de evento**, **múltiplos
  trades numa mesma transação** (dedupe hoje é por assinatura/tempo e perde eventos distintos —
  a chave de dedupe precisa incluir índice de instrução/evento dentro da tx, ver §5/§8b),
  **atraso** entre `ts` do bloco e `received_at`, **finalidade** da tx (`confirmed`/`finalized`)
  e **gaps recuperáveis vs. irrecuperáveis** (declarados, nunca silenciados).
- IDL fixada por versão (não "latest" implícito) — mudança de IDL upstream não pode quebrar o
  parsing silenciosamente.
- Heartbeat da conexão WS separado de "há atividade": conexão viva sem eventos novos não é o
  mesmo que conexão caída.
- Orçamento de chamadas RPC compartilhado com qualquer outro consumidor do mesmo provedor
  (evitar dois processos estourando a mesma cota sem saber um do outro).
- Tratamento explícito de 429/quota excedida: backoff declarado, nunca silêncio.
- Um teste `-m live` opcional conecta no WS real e recebe pelo menos um `subscribeNewToken`
  dentro de 60 s — isso prova **conectividade, não cobertura**; cobertura (nenhum evento perdido
  numa janela) exige o `CoverageTracker`/reconciliação contra uma segunda fonte (RPC backfill),
  não só esse teste de 60 s.
- Nenhum código deste pacote é importado por `execution-worker`, `risk-core` ou qualquer caminho
  que crie ordem.

### T4.2 — Storage + features do scanner

**Escopo:** consumidor que grava `meme_tokens`/`meme_trades`, gera `meme_snapshots` por minuto
(mesmo padrão de agregação de `market-worker`/`scanner-worker` para candles/features, mas para
mint em vez de símbolo de exchange). Calcula `curve_progress_pct`, `unique_buyers_1m`,
`buy_sell_ratio_1m`, `top10_holder_share_pct` (via RPC — leitura de holders da mint),
`creator_sold` (compara wallet do criador contra `side=sell` em `meme_trades`).
`unique_buyers_1m`, `buy_sell_ratio_1m` e `creator_sold` dependem de `meme_trades` populado para
aquele mint — e `meme_trades` só existe para o subconjunto com `subscribeTokenTrade` ligado ou
backfill via RPC (§8, decisão 1). Para um mint fora desse subconjunto essas três colunas ficam
`null` com motivo (`not_subscribed`), **nunca** `0`/`false` implícito — a revisão da Astra aponta
essa confusão (ausência de feed lida como "ninguém comprou" ou "dev não vendeu") como o erro mais
grave do desenho original (MUST-FIX 1).

**Critério de aceite (expandido pela revisão da Astra, 12/09):** para um mint observado por ≥ 30
minutos em ambiente de teste (fixture gravada, não produção):

- `meme_snapshots` tem uma linha por minuto **ou um nulo com motivo explícito**
  (`not_subscribed`, `insufficient_coverage`, `rate_limited`, `unsupported_quote` — mesmo
  vocabulário do critério de aceite de T4.3) — minuto ausente sem marcação não é aceitável, mas
  "sem buraco algum" também não é uma garantia honesta de um feed de terceiro; o que se testa é
  que todo minuto tem linha OU nulo justificado, nunca silêncio.
- `curve_progress_pct` é calculado como `1 − real_token_reserves/initial_real_token_reserves`
  (§3, correção da Astra) e bate com o evento de trade mais recente daquele minuto — **não** mais
  `real_sol_reserves / limiar observado`.
- `top10_holder_share_pct` agrega holders **por proprietário (owner)**, não por conta de token
  isolada, e **exclui** a conta da bonding curve, o pool PumpSwap pós-migração e endereços de
  burn — do contrário o próprio programa aparece como "top holder" e o número mente.
- `creator_sold` distingue **transferência de venda**: uma transferência de tokens do criador sem
  contrapartida em SOL não é `side=sell` em `meme_trades`; o teste cobre esse caso com fixture
  dedicada.
- Teste de mudança de `initial_real_token_reserves` por mint (denominador), de disponibilidade
  temporal (quando um dado chegou vs. quando devia existir) e de retenção — **mesma janela para
  mints graduados e não graduados** (§8, decisão 2) — não só o cenário feliz de 30 minutos
  contínuos.
- O job de partição (`infra/scripts/create_partitions.py`, mesma convenção de `candles`/
  `market_snapshots`) cria a partição do mês corrente para as duas tabelas particionadas antes do
  primeiro insert.

### T4.3 — API + web "Meme Radar"

**Escopo:** endpoint(s) read-only em `apps/api` para listar tokens recentes, ordenar por
`curve_progress_pct`/volume/idade, ver a série de `meme_snapshots` de um mint; tela nova em
`apps/web` ("Meme Radar") — lista + gráfico de progresso da curva, sem nenhum botão de
compra/venda (não é feature deste corte).

**Critério de aceite (expandido pela revisão da Astra, 12/09):**

- Tela carrega com dado real do ambiente de desenvolvimento (mesmo padrão de "sempre polido,
  checado no navegador com dado real" — `frontend-always-polished`).
- Mostra claramente que é **só monitoramento** (rótulo explícito na UI) — mas o rótulo sozinho
  não basta como critério de aceite: a API e a tela também expõem, por linha/ponto, **fonte**
  (`pumpportal_ws` | `rpc_backfill`), **instante observado vs. disponível** (`ts` do evento vs.
  `received_at`/`available_at`), **atraso**, **universo selecionado** (quais mints estão cobertos
  e por quê) e **intervalo coberto com gaps explícitos** — não um gráfico que finge continuidade
  onde há buraco.
- Distingue **zero real** de dado ausente: a API usa estados nomeados (`not_subscribed`,
  `insufficient_coverage`, `rate_limited`, `unsupported_quote`) em vez de devolver `0`/`null`
  indistinto quando não há cobertura — há teste cobrindo cada um desses estados na API e na tela,
  não só o caminho feliz.
- Endpoint responde em paginação (não um `SELECT *` sem limite numa tabela que cresce ~40 mil
  linhas novas de token por dia).

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

**Revisão da Astra (12/09) aplicada — ordem e números seguem a recomendação dela em "O QUE EU
FARIA DIFERENTE"**, não a ordem original deste documento. Ver
`.claude/state/astra-review-t40-plano-meme-radar.md`.

1. **Quais features primeiro.** Começar por **descoberta** (`subscribeNewToken`) +
   **conclusão/migração** (`subscribeMigration`) + **reservas/progresso sob demanda via RPC** —
   as três não têm custo por evento no PumpPortal. Trades (compradores únicos, razão
   compra/venda, venda do criador) exigem `subscribeTokenTrade`, que é **pago: 0,01 SOL por
   10.000 eventos**, sem mensalidade estimável antes de medir volume real de eventos — por isso
   T4.1/T4.2 entregam o encanamento pronto, mas ligam trades **apenas num subconjunto explícito**
   de mints (ex.: acima de X% de progresso na curva), nunca para todos os ~30–50 mil tokens/dia.
   Para qualquer mint fora do subconjunto, as colunas dependentes de trade ficam `null` com
   motivo, nunca `0`/`false` implícito (§6, T4.2). Fonte: `pumpportal.fun/data-api/real-time/`.

2. **Retenção de armazenamento.** Manter a **mesma janela de retenção para mints graduados e não
   graduados**. A proposta original deste documento — reter tudo por 30 dias e depois só os
   graduados (`complete=true`) — foi **rejeitada pela revisão da Astra**: selecionar por sucesso
   depois do fato elimina os controles (os que não graduaram) e cria sobrevivência seletiva no
   próprio dado histórico, contaminando qualquer análise futura sobre o que diferencia um rug de
   uma graduação. A duração exata da janela ainda não está dimensionada — depende de replay e
   bytes medidos em produção, número que este documento não tem e não deve inventar; T4.2 não
   implementa poda por `complete` enquanto essa medição não existir.

3. **Provedor de RPC pago/keyed.** Helius **Free — US$0/mês** (1.000.000 créditos/mês, chave
   grátis) para um **ensaio limitado**, cobrindo leitura de estado de curva sob demanda no volume
   inicial de teste. Subir para **Developer — US$49/mês** (10.000.000 créditos/mês, 50 RPC/s)
   **só se a medição do ensaio justificar** — não é decisão a tomar antes de rodar T4.1 no tier
   grátis e medir consumo real. gRPC/Geyser gerenciado só existe a partir do tier **Business,
   US$499/mês**, fora de cogitação nesta fase (T4.1 usa RPC de leitura simples, não streaming
   Geyser). **Ter uma chave paga não garante capacidade sob pico de mercado** (créditos e RPC/s
   são tetos compartilhados com o resto do consumo do projeto) — antes de contratar qualquer tier
   pago, aprovar explicitamente um **teto de consumo** e uma **política de degradação** (o que o
   radar faz quando o teto é atingido: enfileirar, descartar com log, ou pausar enriquecimento
   por RPC e continuar só com WS). Decisão do Everton, não default implícito do código. Fonte:
   `helius.dev/docs/billing/plans`.

Fontes dos números acima, todas citadas e datadas em
`.claude/state/astra-review-t40-plano-meme-radar.md` (12/09/2026): `helius.dev/docs/billing/plans`,
`quicknode.com/pricing`, `bitquery.io/pricing`, `pumpportal.fun/data-api/real-time/`.

## 8b. Pendências da revisão da Astra não fechadas nesta rodada (T4.0b)

Esta rodada (T4.0b) aplicou os números com URL comprobatória, os critérios de aceite listados por
ela para T4.1–T4.3 e a reordenação da seção 8. **Não fechou** os itens abaixo do parecer completo
(`.claude/state/astra-review-t40-plano-meme-radar.md`), que continuam bloqueando a liberação de
T4.1 até uma próxima revisão do desenho de dados:

- **MUST-FIX 2 (parcial):** `meme_trades` ainda deduplica por `(signature, ts)` — falta índice de
  instrução/evento na chave, finalidade da tx e quote/decimals explícitos (marcado inline em §5).
- **MUST-FIX 3:** procedência completa em `meme_tokens`/`meme_snapshots`, campo `available_at`
  explícito nas três tabelas, versionamento de schema/IDL, checkpoints e gaps duráveis
  (persistidos, não só em memória do processo), e testes de restart/backfill contra
  `docs/DATABASE.md` §1/§4 e recuperação/rate limit contra `docs/EXCHANGE_INTEGRATION.md` §6 —
  nenhum desses foi desenhado nesta rodada.

O veredito da Astra permanece: **não liberar T4.1 para codar** até esses dois pontos serem
fechados num novo desenho (T4.0c ou equivalente).

## Adendo 2026-09-12 02:3x BRT — Mayhem Mode (lido em `pump.fun/docs/mayhem-mode`, "Last Updated 12 November 2025")

O "Examinador de Mayhem" que o Everton mostrou (screener com estados AGENTE ATIVO / FEZ UMA PAUSA / TERMINOU, modo Manual, MCAP, volume, tendência) lista moedas com **Mayhem Mode**: um agente de IA **do próprio pump.fun** que, nas primeiras 24 h de uma moeda criada com o modo ligado, cunha 1 000 000 000 de tokens extras (supply total 2 000 000 000) e **compra e vende em random walk com probabilidades iguais**, sob tetos de SOL comprado, SOL vendido e trades por intervalo; às 24 h queima o que não vendeu; não paga taxa de protocolo; se for vendedor líquido, holders podem ficar sem liquidez na curva (na PumpSwap sempre há saída). A doc diz que o usuário não liga o modo pelo app (beta, permissionless on-chain); o screener de hoje mostra "Modo Manual" — **não documentado nessa versão da doc; pesquisar** (T4.1b).

Endereços públicos (fonte: a própria doc, rodapé): carteira do agente `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`; recebedor de taxa das moedas Mayhem `GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS`; programa Mayhem `MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e`. Canal técnico: `t.me/pump_tech_updates`.

**Implicações para o radar (obrigatórias):**
1. `meme_tokens.mayhem_enabled` (lido na criação) e `mayhem_agent_state` (ativo/pausa/terminou, se a API expuser) são features de primeira classe.
2. Todo trade cuja carteira seja a do agente é marcado `is_mayhem_agent=true` e **sai** de "compradores únicos", "razão compra/venda" e "volume orgânico" — o volume e a variância das 24 h Mayhem são injetados por construção.
3. Hipótese pré-registrável (H-P28): taxa de graduação e retorno 24 h→7 d de moedas Mayhem vs não-Mayhem, com o mesmo denominador e a mesma retenção (sem seleção por sucesso).
4. Não é "análise pronta": é o adversário/ruído que o radar precisa filtrar antes de qualquer sinal virar candidata.
