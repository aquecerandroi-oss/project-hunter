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

### T4.7 — Mesa do operador (`/meme/mesa`) — papel, nunca dinheiro real

Contrato congelado com a T4.6: `.claude/state/contrato-T4.6-T4.7-mesa-meme.md` (tabelas,
semântica do laço, rotas, tela). Everton (12/09): "quero dar o aval da compra do meme, quanto de
espera, vender".

**O que a mesa faz.** Rotas sob `/api/v1/orgs/{org}/meme` (VIEWER+ lê, TRADER+ opera — o mesmo
papel da `order-requests`): `GET /desk` (propostas em espera → aprovadas aguardando fotografia →
apostas abertas → histórico, cursor keyset, mais o saldo de papel por conjunto em SOL e a última
cotação SOL/USD **observada pelo laço**, com hora); `POST /proposals/{id}/approve` (os quatro
parâmetros `size_sol`/`target_x`/`trailing_pct`/`max_hold_s` viram `decision`; 409 se não estiver
`proposed` ou se `expires_at` já passou; 422 `exceeds_max_sol_per_bet`); `POST .../reject`;
`POST /proposals/manual` (mint colado → proposta `operator/1` já `approved`, cotada na última
fotografia com taxa 1,75 %; 422 `mint_unknown`/`curve_completed`/`operator_rule_set_missing`);
`POST /bets/{id}/sell-now` e `POST /proposals/{id}/cancel` (uma linha em
`meme_operator_commands`, 202: o laço aplica na **próxima fotografia**). Todo POST exige
`Idempotency-Key` (replay devolve o mesmo resultado; corpo diferente → 409) e grava `audit_logs`.
A API escreve **só** as quatro colunas de decisão de `meme_proposals`, o `INSERT` manual e os
comandos — exatamente o que a `0022_meme_lab` concede ao `hunter_app`; nunca `meme_paper_bets`.

**Tela.** Faixa (saldo por conjunto, US$ pela cotação observada + hora, PnL do dia, laço
vivo/parado/sem leitura), "Propostas" com contagem regressiva e folha de aprovação pré-preenchida
com `suggested`, "Comprar manual", "Abertas" (marca, PnL/R não realizados calculados na API em
`Decimal`, espera restante, **Vender agora** com confirmação em um toque e o aviso "vende na
próxima fotografia, não neste preço"), "Fechadas hoje" (dia de Brasília), "Decididas
recentemente" (recusas nomeadas do laço, ex.: `daily_loss_cap`). Rótulo permanente
"PAPEL — nenhuma transação real; a chave e a flag ao vivo não existem neste processo".
Atualização a cada 5 s. Item "Mesa" sob o Meme Radar na navegação.

**O que a mesa não faz.** Não compra nem vende: registra decisão e intenção; quem preenche e
vende é o laço (T4.6), na fotografia seguinte. Não lê chave, não assina, não conhece
`ENABLE_MEME_LIVE_TRADING`. Não inventa número: sem cotação observada → "US$: sem cotação
observada"; conjunto sem `wallet_max_sol` → "sem saldo inicial"; laço sem carimbo → "laço: sem
leitura", distinto de "laço parado desde …" e de "nenhuma proposta nos últimos N min (laço
vivo)". Emendas ao contrato (vista × tabelas base, chaves do `quote`, idempotência no Redis,
`sell_now_already_pending`) estão no próprio arquivo do contrato; a execução da tarefa em
`.claude/state/notes-T4.7.md`.

### T4.6 — Lab meme contínuo: simular sem parar na curva, em papel (entregue 12/09/2026)

**Escopo entregue:** migração `0022_meme_lab` (`meme_rule_sets`, `meme_proposals`,
`meme_operator_commands`, `meme_paper_bets`, vistas `meme_lab_scoreboard_v1` e `meme_desk_v1`,
semente `meme_paper_v0/1` + `operator/1` — `docs/DATABASE.md` §34); o laço por minuto dentro do
próprio `meme-worker` (`lab.py`, `proposals.py`, `paper_engine.py`, `lab_bets.py`,
`lab_repo*.py`; decisão registrada: sem serviço irmão, porque o laço só lê o que o coletor já
escreveu e fala com um endpoint a mais, `/sol-price`, no máximo uma vez por minuto);
`GET /api/v1/orgs/{org}/meme/lab` (VIEWER+, só leitura); `infra/scripts/meme_diary.py`
(`--dry-run`/`--apply`, `obsidian/09-OPERATIONS/Diario-Meme/<dia>.md`).

**Semântica (contrato `.claude/state/contrato-T4.6-T4.7-mesa-meme.md` §Semântica + Emendas):**

1. A cada minuto fechado (`end_time <= agora − 1 min`), para cada `meme_rule_sets.status='active'`,
   a porta de entrada da T4.5 (`hunter_indicators.meme.rules.evaluate_entry`) corre sobre cada
   linha de `meme_features_1m` (progresso lido como fração e julgado em %; idade em segundos a
   partir de `meme_tokens.created_at`). `research_only` nasce `approved` com `decided_by='rules'`;
   `operator` nasce `proposed` e espera a mesa até `expires_at` (120 s).
2. `approved` preenche **na primeira fotografia com `observed_at > decided_at`** (nunca na que
   motivou); sem fotografia em 3 min → `unfilled` `no_later_snapshot`; tetos por conjunto com recusa
   nomeada (`exceeds_max_sol_per_bet`, `daily_loss_cap` sobre a perda realizada do dia em Brasília,
   `max_open_positions`, `wallet_balance_insufficient`, …). Risco inicial = SOL gasto inteiro.
3. Aposta aberta: cada fotografia nova marca (`mark_sol` = o que uma venda cheia renderia, com 1,75 %;
   `high_water_x`); as regras (`sell_now` do operador acima de todas; depois dump do criador quando a
   feature existir, migração/conclusão, piso 50 %, alvo 2×, trailing 30 % do pico, 900 s) disparam na
   fotografia k e ficam em `exit_intent`; **a venda é na fotografia k+1**; sem k+1 em 3 min →
   `rug_no_snapshot` (fecha a zero, R = −1, `pending_reason` diz a regra que esperava).
4. Carteira por conjunto derivada só das linhas (`wallet_max_sol + Σ pnl − Σ stake aberto`): um
   restart não é um reset. Cotação SOL/USD observada (`/sol-price`, fonte + hora no jsonb) grava
   `sol_usd_at_entry`/`sol_usd_at_exit`; sem cotação, `NULL` com motivo.
5. Nada de zero silencioso: `hb:meme:radar` ganha `lab_last_tick_at`, `lab_gate_refusals` (por
   conjunto, por motivo), contadores; `GET /meme/lab` traz `sources.lab_status` ∈ {alive, stalled,
   never, disabled, heartbeat_missing, redis_unavailable}.

**O que é verdade hoje, e está medido:** com as fontes grátis (`creator_sold` NULL com
`no_holders_reader`, sem feed de trades) **o portão congelado da EXP-M1 recusa toda linha** por
`creator_net_seller_unknown` e `curve_volume_1m_unknown` — a previsão P1 do pré-registro, agora
contada a cada minuto no heartbeat. O laço, portanto, não abre aposta sozinha até um leitor de
holders (T4.2c) e um feed de trades (T4.2b) existirem; a compra hoje entra pela mesa
(`POST /proposals/manual`, T4.7) e o laço faz o resto (fill na fotografia seguinte, marcas, saídas,
`sell_now`). Ligar um portão mais frouxo sem pré-registro está fora de questão (brief item 4).

**Critério de aceite medido (12/09):** unit 23 (motor) + 14 (porta) + 12 (API) + 4 (diário) + 3
(adapter `/sol-price`); testcontainer `test_lab_persistence.py` 12/12 (semente; portão sobre linhas
reais contando recusas; fill na 1.ª fotografia posterior **e** o futuro reescrito não move a
entrada; `unfilled` por `no_later_snapshot`, `exceeds_max_sol_per_bet`, `daily_loss_cap`; expiração e
`cancel`; fechamento por alvo, time stop, migração e `sell_now` — cada um na fotografia seguinte;
`rug_no_snapshot`; vistas; grants como o papel); `test_migrations.py` e `test_schema_privileges.py`
com a `0022` na união. Nenhum módulo importa `packages/risk-core` nem `hunter_core.execution`;
`meme_paper_bets.mode` é `CHECK (mode = 'paper')`.

**Fora do corte (T4.8+):** caminho de assinatura, `ENABLE_MEME_LIVE_TRADING`, venda pós-migração
pelo PumpSwap (hoje a migração fecha contra a fotografia da curva concluída, com a taxa de 1,75 %,
declarado no `exit.trigger`), detector de rug (`rug_signal_unknown` na decisão).

### T4.2c — segundo coletor: boards do site, fita do `swap-api`, risco por consulta (entregue 12/09/2026)

**Escopo entregue:** adaptador `trenches.py`/`trenches_state.py` (WS `/ws/trenches` por board, snapshot +
deltas com versão, backoff `min(1000·2^n, 30000)` ms, ressincronização em retrocesso, contadores),
`indexer_rest.py` (twin `GET /boards/{board}` e `GET /in-memory-coin/{mint}`, 60/60 s declarado),
`swap_api.py` (fita com cursor, 900/60 s), modelos `NormalizedBoardEntry`/`NormalizedRiskSnapshot`/
`NormalizedSwapTrade`; migração `0023_meme_boards_trades` (`meme_board_observations`,
`meme_risk_snapshots`, 15 colunas em `meme_features_1m`, `meme_trades.commitment` anulável —
`docs/DATABASE.md` §35); no worker, `boards.py` (exposição + censura), `trades.py` (prioridade aposta
aberta > `graduating` > `new` > resto; intervalos 10/10/20/60 s; alta-marca por mint), `risk.py`,
`fold.py` (o minuto com as três fontes), `sources.py` (contadores por fonte, heartbeat);
`GET /api/v1/orgs/{org}/meme/sources` (VIEWER+).

**Causa-raiz dos 0 `complete = true` em 1 h (adendo):** o `migrate` do PumpPortal chegava antes do
primeiro poll (43/49 graduações no próprio slot da criação), `migrated = True` expulsava o mint do
conjunto rastreado e `_LOAD_TRACKED` o excluía no restart — a curva concluída nunca era lida, logo nem o
snapshot `complete` nem `completed_at` existiam. O parser não era o culpado: o `/coins/{mint}` de um
graduado real (`frontend_api_v3_coin_graduated_raw.json`) volta `complete: true` com reserva virtual
> 0 e é aceito. Correção: `final_read_pending` mantém o mint até **uma** leitura depois da
conclusão/migração (tier logo após apostas abertas), que grava o snapshot `complete` e `completed_at`;
mints com cotação ≠ SOL são descartados na primeira recusa (`UnsupportedQuote`).

**Não-antecipação (regra única, em `features_tape.py`):** toda coluna nova de `meme_features_1m`
usa só observações com `received_at <= end_time`; o teste de look-ahead prova que uma leitura de
holders ou um trade carimbado dentro do minuto mas recebido depois do fecho não muda a linha.

**O que a EXP-M1 recebe agora:** `creator_sold` e `creator_net_seller` (fita do criador),
`curve_volume_1m_sol`, `buys_1m`/`sells_1m`/`net_sol_flow_1m`, `unique_buyers`, `buy_sell_ratio`
(`no_sells` quando não houve venda), `holders`/`top10_share`/`dev_share`/`snipers` com
`holders_observed_at`/`holders_source`. **Pendência declarada:** `lab_repo.load_gate_rows` ainda
passa `curve_volume_1m_sol=None` e lê `creator_sold` como `creator_net_seller` — dois ajustes de uma
linha em `lab_repo.py`, fora do escopo desta tarefa por regra do brief (não tocar `lab*.py`).

### T4.2d — o que "graduou" quer dizer, o denominador do progresso e a cegueira declarada (entregue 12/09/2026)

**Fatos que a motivaram** (run 5 do plantão, 05:51 BRT; produção 06:04 BRT): `complete = true` da REST
não é graduação (77/140 com `real_sol = 0`, 72/140 fora do board `graduated`); o denominador do
progresso só era escrito de fotografia virgem (117/123 linhas do portão em `progress_unknown`); 8/50 do
board `new` eram `raydium_launchpad`, invisíveis ao `subscribeNewToken`.

**Escopo entregue:** migração `0024_meme_graduation` (`docs/DATABASE.md` §36): quatro estampas separadas
em `meme_tokens` — `rest_complete_seen_at`, `curve_filled_seen_at` (limiar **derivado** de
`/global-params`: `quote.curve_fill_threshold_lamports` = `buy_cost` dos 793,1 M numa curva virgem =
85 005 359 057 lamports), `graduated_board_seen_at`, `pool_created_at`/`pool_created_source` —,
`completed_at` = a mais antiga das quatro **exceto** REST com reserva zero sozinho (redutor
`graduation.earliest_completion`; no banco `LEAST`, trigger só deixa recuar), `progress_denominator_source`
(`observed_virgin` | `global_params`; NULL = `unknown`), backfill a partir das tabelas de evidência, vista
`meme_graduation_matrix_v1` (por dia de Brasília: contagem por sinal, 1/2/3/4 sinais, seis pares que
discordam, "só REST"). Worker: `graduation.py` (redutor, sinais da curva, denominador com guarda Mayhem,
`GlobalParamsStore` — `/global-params` uma vez por hora no orçamento da curva), `curve_rows.py`,
`repo_rows.py`; `boards.py` escreve o board `graduated` sem rastrear e devolve as primeiras aparições;
`risk.py` e `discovery.py` alimentam a pool; `sources.py` conta a cegueira (`blind_share_1h`,
`new_board_entries_1h`, `new_board_non_pump_1h`); `features_version = meme_features_v2` (série quebra no
deploy, `v1` não reescrita). Adaptador: `PumpFunRestClient.get_global_params`. API: sinais no
`MemeTokenOut`, `graduation_matrix` na `overview`, `discovery_blind_share_1h` + explicação em `/meme/sources`.
Web: faixa "Graduação hoje — quatro sinais separados" em `/meme` e bloco "Sinais de conclusão" + marcas
no gráfico em `/meme/{mint}`, discordâncias em âmbar; filtro `completed` = `completed_at`.

**Mayhem, explícito:** a curva Mayhem tem 1 bilhão extra cunhado para o agente e reservas movidas por
`set_mayhem_virtual_params` (a fixture `2sduGq…` tem 822,6 M tokens reais, mais que o inicial do registro);
o registro não descreve essa curva, então o denominador só vem de fotografia virgem e fica `unknown` no
resto — 64 % das criações são Mayhem, logo o portão do Lab continua recusando a maioria delas por
`progress_unknown`; a correção real exige decodificar a conta `mayhem_state` (fora de escopo).

**O que não se faz:** nenhum rastreio de StonkFun/LaunchLab — a fração de cegueira mede, não corrige; a
decisão é do Everton (§8).

### T4.2e — o denominador das curvas Mayhem e a cobertura da fita (entregue 12/09/2026)

**Fatos que a motivaram** (VPS `eeb566c`, 08:35 BRT): 250 linhas por tick, `progress_unknown` em 113 e
`creator_net_seller_unknown`/`curve_volume_1m_unknown` em 109; `progress_denominator_source` NULL em 2 615
mints; nos 3 min anteriores, 77/393 linhas com fita — com ~730 req/min de folga no `swap-api`.

**Denominador Mayhem (sem constante):** quatro chamadas RPC públicas (11:43–11:54 UTC) leram, no mesmo
slot, `bonding_curve` + `MayhemState` + cofre do agente + mint de cinco moedas Mayhem, inclusive a fixture
`2sduGq…`. Resultado (`docs/PUMPFUN-ONCHAIN.md` §3.5): a reserva inicial de uma curva Mayhem **é a do
registro** de `/global-params`; o que passa de 793,1 M é o bilhão do agente vendido líquido para a curva
(`822 644 036,902123 = 793 100 000 + 29 544 036,902123`, até a subunidade). Sem IDL do programa Mayhem
(repositório e conta de IDL on-chain ausentes), o layout de `MayhemState` é **inferido e validado em toda
leitura** por `cofre + líquido_vendido = supply_do_mint − token_total_supply` (5/5); os discriminadores
batem com a convenção Anchor (`sha256("account:MayhemState")[:8]`). Adaptador: `mayhem_state.py` (PDAs
pelas seeds da IDL do Pump, decodificador, `NormalizedMayhemFlow`), `rpc.get_mayhem_flows`
(`getMultipleAccounts`, 25 mints/chamada). Worker: `graduation.mayhem_denominator`, laço `mayhem.py` (uma
vez por minuto, só as Mayhem rastreadas sem denominador), `progress_denominator_source = mayhem_state`
(migração `0025`, um CHECK alargado). A fotografia REST de Mayhem sozinha não reivindica nada (nem
`observed_virgin`), e `curve_filled_seen_at` não é reivindicado para Mayhem. Teste do brief: `4BTP…`
reproduz os 3,43 % do site com 3,4285 % (0,002 pp); `2sduGq…` dá −3,7251 %, que o site trunca em 0 —
guardamos o negativo, `meme_features_v2` continua (mesma fórmula; o denominador é dado do token).

**Cobertura da fita — a causa:** `pull_once` era sequencial: 250 mints × 250–450 ms ≈ 90 s por "ciclo de
10 s"; os tiers de 10 s eram puxados a cada ~90 s, a volta do tier `rest` passava de um minuto e
`swap_api_used_60s` ficava em ~170 de 900 (= 250 ÷ 90 s). A medição foi 3 min depois de um deploy
(reinício zera a cobertura em memória, por desenho: um minuto sem escuta não é um zero). Correção: pulls
concorrentes (`MEME_TRADES_CONCURRENCY`, 8) atrás do bucket de 900/60 s, prioridade inalterada; o que o
teto ainda não alcança vira `tape_reason = not_polled`; um minuto cuja última leitura bem-sucedida tem
mais de 180 s não conta como fita (não é um zero); `covered_since` passa a ser o *receive time* da
primeira página (um pull que cruza o fecho do minuto cobre o minuto seguinte). Bug achado no caminho:
`repo._UPSERT_TOKEN` nunca inseria `mayhem_state`/`mayhem_mode` — o `OR mayhem_state IN (...)` do
`_LOAD_TRACKED` era letra morta; corrigido. Heartbeat: `tape_coverage_pct`, `progress_coverage_pct`,
`fold_minute`, `fold_rows`, `tape_cycle_s`, `tape_covered_mints`, `tape_never_pulled`,
`tape_deferred_60s`, `mayhem_pending`, `mayhem_written_60s`; `GET /meme/sources` expõe todos.
Prova em produção: `infra/scripts/sql/research/2026-09-12-t42e-cobertura.sql` (antes × depois).

### T4.3b — o painel de fontes na tela: `/meme` e `/meme/mesa` (entregue 12/09/2026)

**Por quê:** desde a T4.2c/T4.2e a API expõe `GET /meme/sources`, mas nada disso aparecia na tela — o
Everton perguntava "operável?" sem ter como ver que 43 % das linhas têm progresso e 39 % têm fita.

**O que aparece (brief `.claude/state/brief-T4.3b-painel-de-fontes.md`):** uma faixa "Fontes"
(`components/meme/meme-sources-panel.tsx`; regras puras em `meme-sources-format.ts`, testadas em
`tests/meme-sources-format.test.ts` e `tests/meme-sources-panel.test.tsx`):

- **Um chip por fonte** (as seis do heartbeat: PumpPortal WS, pump.fun REST, Solana RPC, boards do site,
  fita do `swap-api`, risco do indexer; uma fonte nova que o worker relate antes de a tela conhecê-la ganha
  nome legível em vez de sumir). Cor por regra, na ordem: cinza "desligada"/"sem leitura: motivo"
  (`never_observed`, `never_connected`, `heartbeat_missing` em português, nunca o slug); vermelho
  "desconectada"/"com erro · N na hora"/"N erro(s) na hora" (erro na hora vence tudo); âmbar "atrasada há
  N s|min|h" quando `age_s` passa do `stalled_after_s` do próprio radar, ou "orçamento N%" a partir de
  90 % do limite; verde "conectada"/"em dia". Cada chip traz "atraso N.N s · usado/limite req/min" (ou
  "N/min (sem limite declarado)", ou "sem leitura") e o `last_observed_at` em Brasília; o `title` guarda o
  último erro e a testemunha do banco.
- **Três medidores honestos:** *progresso coberto* e *fita coberta* (o `progress_coverage_pct` e o
  `tape_coverage_pct` do último minuto dobrado, com o `fold_minute` como `observed_at`, mais
  "N linha(s) no minuto · N Mayhem sem denominador" e "N de M mints com fita · ciclo N.N s ·
  N adiado(s)/min · N nunca puxado(s)"), e *cegueira da descoberta* (`discovery_blind_share_1h`, com
  "N de M entradas do board new na hora", o `sources_at` como `observed_at` e a frase fixa "moedas de
  outros launchpads que o radar não vê por construção"). Sem número → "sem leitura: motivo", com quatro
  motivos distintos: radar sem heartbeat/parado, nenhum minuto dobrado ainda, minuto dobrado vazio,
  board `new` sem listagem na hora — e, para um worker anterior à T4.2d/T4.2e que não manda o campo,
  "o worker não informou este número". Nunca um 0 %.
- **Estado do radar e do laço:** "radar vivo · heartbeat há N s" ≠ "radar parado desde dd/mm hh:mm"
  (Brasília) ≠ "radar: sem leitura (sem heartbeat do worker | Redis indisponível | o worker subiu, mas o
  radar nunca escreveu seus campos)"; o laço reaproveita o `loopStateLabel` da mesa, medido contra o
  `as_of` da própria API. "N mints rastreados" (ou "rastreados: sem leitura"), gaps e mensagens
  malformadas do último minuto só quando houve alguma, e "consultado em" com o `as_of`.

**Montagem:** `/meme` lê `/meme/sources` e `/meme/lab` no mesmo render que o overview e a lista (mesmo
`AutoRefresh`), painel completo abaixo da faixa de visão geral; `/meme/mesa` lê `/meme/sources` junto com
a mesa (5 s) e mostra a versão de uma linha acima da faixa de PnL e das propostas (o laço já está na faixa
da mesa, por isso a linha não o repete). Cada leitura falha sozinha (`loadMemeSources` nunca lança) e
cai em `SectionUnavailable` sem derrubar o resto da página. Mobile 375: chips quebram em duas colunas,
medidores empilham; dark/light pelos tokens `-soft` dos badges. Playwright/checagem visual com dado real
fica para a sessão logada (o navegador embutido não abre localhost/Clerk).

### T4.2f — cobertura total: a curva de todos os rastreados pela cadeia e o limite real do swap-api (entregue 12/09/2026)

**Fatos que a motivaram** (VPS `8478eef`, 10:00 BRT, depois da T4.2e): `progress_coverage_pct` 43,3 e
`tape_coverage_pct` 38,8; progresso ausente por `not_polled` em 1 267 linhas/15 min (60 req/min de REST não
fotografam 130 curvas por minuto); fita ausente por `rate_limited` em 1 069 linhas/15 min.

**A curva pela cadeia** (`docs/PUMPFUN-ONCHAIN.md` §5.5): `SolanaRpcClient.get_curve_states` (`rpc_curves.py`)
lê 100 PDAs `["bonding-curve", mint]` por `getMultipleAccounts` (467 ms ao vivo; a PDA derivada bateu com a REST
em 140/140) e carimba `observed_at` com o `getBlockTime` do slot (~11 s antes da chegada — a finalidade). O laço
`chain.py` fotografa **todos** os rastreados uma vez por minuto (~4 chamadas RPC/min; o RPC público declara nos
cabeçalhos `rps 250` e `method 10`) e persiste pelo caminho da T4.2d; o poll REST fica só para identidade/
mayhem/fallback (`tracker.needs_rest`); a reconciliação top-K não roda com o laço ligado. Da captura: **16 % das
moedas novas têm quote ≠ SOL** (USDC, `pumpCmXq…`, `Xs…`) — `unsupported_quote`, nomeado; 2 curvas esvaziadas
pelo `migrate` (reservas zero na cadeia; a REST mantém o valor antigo) — `curve_emptied`, o sinal de migração da
própria cadeia; 0 de 79 virgens (toda moeda nasce com a compra do criador). Meta `progress_coverage_pct ≥ 90`:
o que faltar é `unsupported_quote` (≈ 16 % até o mint sair do conjunto), `denominator_unknown` Mayhem (até o laço
da T4.2e escrever) e `insufficient_coverage` (curva ainda não finalizada no primeiro minuto).

**O limite real do swap-api** (medido, `docs/PUMPFUN.md` §2): não é o `x-ratelimit-limit: 1000` — é uma regra do
Cloudflare (erro 1015): **~20 requisições por 60 s por IP**, bloqueio de 60 s, qualquer rota (4 sondas, 115
requisições, 5 × 429). Era isso que os 8 pulls concorrentes da T4.2e disparavam a cada ciclo. Agora:
`MEME_SWAP_API_BUDGET_60S` = 16 (o adaptador recusa > 20), cota exata por ciclo com resto carregado (2, 3, 3, 2,
3, 3), **1 página por mint por minuto** (paginação só para apostas abertas), prioridade aposta aberta >
`graduating` > `new` > jovem > resto, 429 real (`HttpRateLimited` com os cabeçalhos — nunca o bucket próprio) →
mede o que passou no minuto, encolhe para 80 % por 15 min e bloqueia o `retry-after`; `tape_reason`:
`rate_limited` só com 429 real ou dentro do bloqueio, `not_polled` quando o orçamento não alcançou (mesmo se já
coberto antes). **A meta `tape_coverage_pct ≥ 80` não é alcançável por este endpoint a partir de um IP:**
16 pulls/min × 180 s de frescor ÷ 130 ≈ 40 % (a T4.2e mediu 38,8 % — o teto, não um bug); o que muda é zero
apagões de 60 s e a razão honesta em cada linha. Saídas, para decisão: um segundo IP/proxy para a fita, ou
`POST /v1/coins/market-activity/batch` (N mints por requisição, janelas 5m/1h, USD — outra feature, outra versão).

Heartbeat: `chain_cycle_s`, `chain_tracked_mints`, `chain_read_mints`, `chain_calls_60s`, `chain_refused_1h`,
`chain_block_time_missing_60s`, `swap_api_effective_budget_60s`, `swap_api_measured_60s`, `swap_api_429_1h`,
`swap_api_blocked_until`; `GET /meme/sources` expõe todos. Prova: `infra/scripts/sql/research/2026-09-12-t42f-cobertura.sql`
(§7–§10 novos: fotografias por fonte, origem da fotografia dobrada, lacunas com `chain_covered`, fita por minuto).
Env: `MEME_CHAIN_CURVES_ENABLED`, `MEME_REST_MAYHEM_REFRESH_S` (novas); `MEME_SWAP_API_BUDGET_60S` 900 → 16;
`MEME_TRADES_CONCURRENCY` 8 → 2.

### T4.10 — traçado de linhas obrigatório e a sonda de hype (Parte A entregue 12/09/2026)

**Diretiva** (Everton, 12/09 10:5x BRT): "você é obrigado a usar traçamento de linha, e os que não tiver
você vai deixar já semi-comprado por causa do hype". Contrato entre as duas partes:
`.claude/state/brief-T4.10-tracado-de-linhas-e-sonda-de-hype.md`.

**As linhas viram feature, não desenho** (`hunter_indicators.meme.lines`, puro, registrado com
`FeatureDefinition` v1 por coluna): sobre as fotografias da curva dos últimos 15 minutos **recebidas até
o fecho do minuto** — suporte pela reta dos **dois últimos fundos locais** (ponto abaixo dos dois
vizinhos), sua inclinação em SOL/min, `higher_lows`, distância (mcap − suporte)/suporte, extremos da
janela, `breakout_15m` contra a máxima da janela **anterior** (o minuto nunca é a própria referência),
inclinações OLS de ln(mcap) a 5 e 15 min. Nulos nomeados: `too_few_points` (< 5 fotografias),
`no_snapshot`, `flat`, `out_of_range`. `meme_features_v3` (`0026`): 13 colunas com CHECKs escopados a
`line_points IS NOT NULL` — uma linha `v2` não ganha motivo inventado. Provas: `test_meme_lines.py`
(dois fundos 36 → 41 ⇒ suporte 48, distância 0,166667; série exponencial ⇒ inclinação 0,02/min exata;
a fotografia do próprio minuto não é referência do rompimento; uma fotografia recebida 1 s depois do
fecho não muda nada), `test_features_lines.py` (o mesmo dentro do `build_row`, e um board recebido
depois do fecho não é a posição do minuto), `test_lab_lines.py` (contra Postgres: `load_line_points`
recusa `received_at > end_time`).

**O score de hype** (`hunter_indicators.meme.hype`, `hype_score` v1): compras do minuto (min/30 × 0,35),
compradores únicos (min/20 × 0,25), melhor posição em `movers`/`new` (top-10 = 1, top-50 = 0,5 × 0,20),
`has_social` (0,10), snipers ≤ 2 (0,10); decomposição raw/normalizado/peso/contribuição acompanha o
número; `no_tape_no_board` (NULL) e `partial` (ao lado de um número). 15 compras, 10 compradores, posição
3, social, 1 sniper = **0,700000** (`test_meme_hype.py`).

**Dois conjuntos semeados na `0026`, ambos `research_only`, parâmetros congelados no brief:**
`trendline_v0/1` (EXP-M2, [[EXP-M2-a-linha-manda]]: a porta da EXP-M1 com idade ≥ 5 min **e** fundos
ascendentes **e** rompimento **e** distância 0–0,25; 0,05 SOL; saídas 2× / 30 % / 900 s / **linha
rompida** = 2 fotografias seguidas abaixo da reta projetada ao instante da fotografia, `line_broken` na
precedência depois do piso e antes do alvo) e `hype_probe_v0/1` (EXP-M3, [[EXP-M3-sonda-de-hype]]: 30 s
a 5 min, `hype_score ≥ 0,6`, `dev_share ≤ 0,10` ou desconhecido **com motivo**, snipers ≤ 2, criador,
participação ≤ 1 %; **sonda** de 0,01 SOL, 3× / 40 % / 600 s; **escala** para a perna 2 de 0,04 SOL —
aposta separada com `parent_bet_id`, `leg = scale` — só enquanto a sonda está aberta e a porta de
`trendline_v0/1` é satisfeita para o mesmo mint, uma vez por sonda, com a participação julgada com 0,04;
teto de 5 sondas abertas — a perna 2 monta na vaga da sonda). Previsão registrada nas duas páginas:
**`descartar`**; o Lab decide. Suposições declaradas: `max_loss_pct = 50` (o piso da EXP-M1) nos dois,
progresso fora da porta da sonda, `max_exposure_per_mint_sol = 0,05` na sonda.

**O laço** (`proposals_scale.py`, `lab._scale_step`, `paper_fill.py`, `lines_exit.py`): a proposta da
perna 2 nasce aprovada por `rules` com `leg`/`parent_bet_id` no `suggested`; o fill grava as duas colunas
e recusa `scale_without_parent`/`unknown_leg`; a saída `line_broken` reconstrói a sequência de fechos
abaixo da linha a partir da fotografia da última marca (uma para trás — nunca dispara cedo numa
reinicialização). Prova contra Postgres (`test_lab_lines.py`, um container): sonda aberta aos 2 min de
vida (0,01 SOL, sem vigiar linha) → linha nasce aos 6 min (suporte 30,4, `higher_lows`, rompimento) →
perna 2 de 0,04 SOL com `parent_bet_id` = a sonda, vigiando a linha → dois fechos abaixo (29,6 e 28,5
contra 30,9/31,1) → venda `line_broken` na fotografia seguinte; a sonda continua aberta; uma única
proposta de escala jamais escrita.

**API:** `MemeFeaturePointOut` ganha as 13 colunas (`LineReason`/`HypeReason`), `BetOut` ganha `leg` e
`parent_bet_id`, `ExitReason` ganha `max_loss` (já escrito pelo laço desde a T4.6) e `line_broken`.
`apps/web` é a Parte B (paralela). Schema: `docs/DATABASE.md` §38. Notas: `.claude/state/notes-T4.10a.md`.

### T4.13 — o registro completo de cada teste na mesa (entregue 12/09/2026)

**Diretiva** (Everton, 12/09 11:3x BRT): "deixa pronto os testes na mesa colocando tempo de entrada, valor de
entrada, tempo de saída e tudo; vou começar a testar com grana verdadeira". Brief:
`.claude/state/brief-T4.13-registro-de-testes-na-mesa.md`.

**API** (`routers/meme_tests.py`, VIEWER+, só leitura): `GET /api/v1/orgs/{org}/meme/tests?day=&rule_set=&cursor=&limit=`
— uma linha por aposta de papel **do dia Brasília de `entry_at`** (a régua da `meme_lab_scoreboard_v1`), fechada
**e** aberta (aberta com `mark_sol`/`mark_at` como saída provisória, `exit.provisional = true`), com tudo já
derivado no servidor em `Decimal`: entrada (hora, preço marginal antes, preço médio, mcap da fotografia, SOL gasto,
tokens, taxa, atraso decisão→fill), saída (hora, preço marginal após, mcap, SOL recebido, taxa, motivo no vocabulário
fechado `ExitReason` **e** o rótulo em português `EXIT_REASON_PT`, gatilho, regra pendente no rug), duração, PnL SOL,
**PnL US$ = `pnl_sol × sol_usd_at_exit`** (a fórmula da vista do placar; aberta → provisório pela cotação da entrada,
`pnl_usd_basis`; sem cotação → `null` com `pnl_usd_reason`), R, conjunto/perna/`parent_bet_id`, origem/decisor, e
`lab_context` lido de `meme_features_1m` no `(mint, features_end_time)` da proposta preferindo `meme_features_v3`
(linha traçável?, suporte, distância, fundos ascendentes, rompimento, `hype_score`/motivo, criador vendeu?, progresso,
idade, compradores, gatilhos; manual → `manual_no_minute`, minuto sem linha → `no_features_row`). Totais do dia em
SQL sobre o filtro inteiro (apostas, fechadas/abertas, acertos/perdas, PnL SOL realizado e provisório, PnL US$ +
`unpriced_usd`, R somado). `GET .../tests.csv?day=&rule_set=`: UTF-8 com BOM, `;`, CRLF, decimais com vírgula,
datas `dd/mm/aaaa HH:MM:SS` Brasília, `sim`/`não`, 39 colunas (`CSV_COLUMNS`), teto 5 000 linhas.
`GET .../tests/{bet_id}`: a mesma linha + a curva de `entry_at − 5 min` a `saída + 5 min` (≤ 600 fotografias).
**REAL (T4.12, paralela)**: `meme_wallet_positions` lida por `to_regclass` + `SELECT *` sob SAVEPOINT, colunas do
brief lidas com tolerância (`services/meme_tests_real.py`, `kind = real_observed`, conjunto `wallet:<8>`); tabela
ausente → `sources.wallets = "não observada"`, erro de leitura → `"leitura indisponível"`; as linhas reais vêm em
`real_items` (fora do keyset das apostas de papel) e a tela/CSV as intercalam por hora de entrada.

**Web**: aba **"Testes"** em `/meme/mesa` (`?tab=testes`, guias `<Link>` "Mesa · Testes") e rota própria
`/meme/testes?day=&set=&cursor=` — mesma `MemeTestsSection` (`components/meme-tests/*`): rótulo da API, filtro por
dia (input nativo + Hoje/Ontem/←/→ pelo relógio do servidor) e por conjunto (pills), totais, linha de fontes
("Reais: sem carteira observada ainda · contexto do Lab lido de meme_features_v3 · Consultado em …"), tabela densa
13 px com três colunas fixas à esquerda (▸ · hora entrada · moeda) e as demais (conjunto · entrada SOL · saída SOL ·
PnL SOL · PnL US$ · R · motivo · duração) rolando, linha expansível com entrada/saída/cotação/**o que o Lab dizia**;
selo "REAL — observado na cadeia"; `*` em saída/US$ provisórios; 375 px em cartões com `<details>`; ≤ 200 linhas por
página (link "Próxima página" + aviso "exporte o CSV para o dia inteiro"); botão **Exportar CSV** → route handler
`/meme/testes/export?day=` (passa pelo `clerkMiddleware`, pede o token e repassa os bytes/cabeçalhos da API; o caminho
não termina em `.csv` porque o matcher do middleware ignora essa extensão). Ficha `/meme/mesa/aposta/{id}`: stats,
`MemeCurveChart` reaproveitado (aceita `{observed_at, mcap_sol}`) com as marcas "entrada" e "saída"/"marca atual",
ficha completa. `MEME_EXIT_REASONS` do web ganhou `max_loss`/`line_broken` com rótulos (o build de produção quebrou
três vezes por rótulo faltante).

**Provas**: API unit 18 (`test_meme_tests_service.py`: vocabulário exaustivo por `get_args(ExitReason)`, limites
Brasília, fechada/aberta/rug, US$ pela fórmula do placar, contexto do Lab, linhas REAL tolerantes, CSV byte a byte);
integração 13 em testcontainer contra o Alembic head (`test_meme_tests_api.py`: uma fechada **por motivo**, aberta,
manual, sonda+escala, ontem excluído, minuto v3, curva do detalhe, keyset, filtro, 404, CSV byte a byte); web Vitest
44 novos (formatação Brasília com segundos, motivos, totais, link do CSV, tabela/cartões com REAL e expansão).
Notas: `.claude/state/notes-T4.13.md`.

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
