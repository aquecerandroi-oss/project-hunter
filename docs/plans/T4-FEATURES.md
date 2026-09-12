# T4-FEATURES — o que separa uma moeda que corre de um rug/bundle (catálogo para o T4.2)

**Status:** pesquisa concluída em 2026-09-12 (T4.0e), sem código, sem commit. Alimenta o desenho do
T4.2 (`docs/plans/T4-MEME-RADAR.md` §6) e a fila de hipóteses (`obsidian/00-INBOX/Hipoteses-do-plantao.md`,
H-P31…H-P35 e D-P36 — H-P29, H-P30, D-P25 e o painel da H-P28 já estavam na fila pelo run 13 do plantão, commit 57b8f47, e não são duplicados aqui).
**Origem:** Everton, 2026-09-12 — "mapear o pump.fun por completo — vamos operar nele"; intenção de
estratégia: comprar cedo na bonding curve, vender em ROI alto.
**Método:** só fontes primárias (arXiv/SSRN, relatórios de Solidus/Chainalysis/Elliptic, documentação
pública das ferramentas, chamadas reais às APIs públicas sem login). Cada número abaixo tem URL e hora de
leitura em Brasília em `.claude/state/notes-T4.0e.md`. Nenhum número foi inventado; o que não foi
encontrado está dito como não encontrado. Horários BRT = UTC−3.

> **Ressalva que vale para o documento inteiro.** Todos os papers de 2026 medem o pump.fun em janelas
> curtas e regimes distintos (set–out/2025; mai–jun/2026; jun/2026; jan/2024–jan/2026 em amostra de 1 %).
> As taxas-base variam por um fator de ~5× entre eles **por método e por regime**, não só por época. Nada
> aqui vira constante no código do T4.2: o radar mede a própria taxa, com a mesma retenção para graduados e
> não graduados (decisão 2 do plano, revisão da Astra).

---

## 1. O que a literatura primária de 2025–2026 mede (e como)

### 1.1 Tabela das fontes

| Fonte (lida 12/09/2026, BRT) | Amostra e janela | Como observou | O que define "sucesso"/"falha" | Números-chave | Limitação declarada |
|---|---|---|---|---|---|
| Kamat, *Pump.fun Graduation Regime Windows* — arXiv 2607.02823 (v3 "Corrected", corrigenda v1.3 de 11/08 e v1.4 de 13/08/2026), lido 02:20–02:22 | 832 941 mints com desfecho, 2026-05-08 → 2026-06-10 (34 dias); dataset RED-PUMP-2026-v1 (Zenodo 10.5281/zenodo.20633486, CC-BY-4.0) | polling de `GET /coins?sort=created_timestamp&order=DESC&limit=50` da própria API do pump.fun; na primeira detecção grava mint, timestamps, mcap inicial em SOL e três booleanos de metadata (Twitter/X, site, Telegram) | graduação = curva atinge o limiar (~85 SOL reais sobre 30 virtuais) e migra para o PumpSwap | taxa agrupada **0,198 %** (Wilson 95 % [0,189; 0,208]); regime estável 29 d **0,207 %**; KM: mediana **1,66 min** até graduar, p90 2,80 min, máx 5,98 min; Cox: Telegram HR **5,40** [4,73; 6,17], log(1+mcap inicial) HR **4,51**, Twitter 1,30, site 1,19, log(descrição) 1,05, concordância 0,858; com Telegram 1,485 % vs sem 0,166 % (**8,94×**); 0 canais 0,110 % vs 3 canais 1,919 % (**17,4×**); Q4 de mcap inicial (> 31,04 SOL) 0,634 % | "the collector's effective visibility window was approximately six minutes, not 24 hours, and every rate reported is a fast-regime rate and a lower bound on the true 24-hour equivalent"; tentativa de corrigir graduações tardias por mcap alto foi **retirada** (100 mints verificados: nenhum graduou — `market_cap` da API reflete reservas virtuais) |
| Kamat, *Coordinated Sniper Cohorts on Pump.fun* — arXiv 2607.02795 (v3, 03/08/2026; abs lido 02:23, PDF lido 02:32–02:35) | 1 578 333 observações de comprador em 166 098 lançamentos, 13,38 dias (2026-06-11 21:43Z → 06-25 06:52Z); catálogo RED-COHORT-2026-v1 | primeiros **10 eventos de compra** por lançamento (linhas, não carteiras distintas) dentro da janela da curva; grafo de coocorrência com aresta se dois endereços aparecem juntos nos 10 primeiros, **peso ≥ 3** coocorrências (limiar declarado conservador), union-find nos componentes | não mede graduação como desfecho; desfecho = contagem de compradores e SOL de entrada nos primeiros 30 min, com as compras da própria coorte **excluídas** | **1 012** coortes persistentes (2–12 carteiras, 2 965 endereços; mediana 2 carteiras; rank médio mediano 3,55 ou melhor); PSM 1:1 (caliper 0,2 dp, dez covariáveis de qualidade do lançamento): +**16,1 %** compradores [13,0; 19,4] em 5 419 pares; SOL de entrada **+6,3 % [−0,5; +15,1] (nulo)**; contraste ingênuo +130,9 % (≈ metade é contaminação aritmética); **382/5 419 (7,0 %)** dos lançamentos tratados tiveram zero comprador não-coorte em 30 min; placebo por atividade enviesado (mediana +189,6 %, acima do real em 100/100 sementes) | o texto avisa: "Nothing about the residual +16.1% requires an 'informed order flow' interpretation"; coortes tratadas diferem dos controles em mcap inicial, presença social e hora do dia |
| Marino, Naviglio, Tarantelli, Lillo, *Predicting the success of new crypto-tokens: the Pump.fun case* — arXiv 2602.14860v1 (16/02/2026), lido 02:23–02:24 e 02:29 | **655 770** tokens, 2025-09-01 → 10-01; 243 123 criadores; 2 600 790 traders | parsing on-chain dos programas Pump.fun e PumpSwap | graduação = 115 SOL na curva (85 reais + 30 virtuais), ≈ US$ 69 000 de mcap | **4 338 graduados (≈ 0,63 %)**; mediana **4,4 min** / ≈ 457 passos até graduar; "Fast accumulation of liquidity through a small number of trades is the strongest predictor of graduation"; parcela de bots (tx direta ao programa sem passar pelo front-end) **negativa** além de níveis intermediários de vSol; "top creators" **não** melhoram a previsão; **92,22 %** (169 938 de 184 282 tokens com ≥ 30 swaps) têm ≥ 1 evento de dump (Shewhart, mediana-MAD, violação de 4σ no log-retorno); "selling strictly before graduation is more profitable than selling immediately after graduation"; breakeven do buy-and-hold: **p(vSol) > vSol²/115²**, e "p_std(vSol) lies below the breakeven curve, hence it is not possible to make profits with a buy-and-hold strategy based only on vSol" | features construídas "using only information available up to the current point on the bonding curve" (não-antecipação explícita); proxy de bot é imperfeito; ignora gas e taxas; suporte estatístico pequeno para "top creator" |
| Hu, Tekin, Xu, Liu (Georgia Tech), *MemeTrans* / **MELT** — arXiv 2602.13480 (v1 13/02, v2 21/05/2026), lidos 02:20–02:22 (v1) e 02:31 (abs v2) | **41 470** memecoins que **completaram** a curva e migraram (pump.fun → Raydium), dez/2024 → mar/2025; 30,8 M tx pré-migração + 187,7 M pós | traces on-chain tipados (compra, venda, transferência, bundle) | alto risco = `min_price_ratio < 0,3` nos **20 min** após a migração (preço mínimo / preço de migração), mais detector de ciclos venda-compra (`pred_score ≥ 0,7`) | **84,13 %** de alto risco; **36,5 %** do supply em contas coordenadas (abs v2); os 10/20 primeiros compradores de tokens de alto risco detêm **17 e 19 pp** a mais do supply; bundling eleva a concentração em 24/9/6 % (alto/médio/baixo risco); MLP AUPRC 0,5729, F1 macro 0,6981; grupos mais preditivos: atividade de mercado e estatísticas de bundle; "reducing financial loss by 56.1 %" numa estratégia de seleção | só tokens **graduados** (seleção por sucesso por construção — não serve de taxa-base para a curva) |
| Szwajcok, Tsuchiya, Liu, Soska, Payer, Christin, *Meme Coin Factories* — arXiv 2609.10246v1 (09/09/2026), lido 02:23–02:24 e 02:27–02:30 | 15,2 M moedas em 730 dias (2024-01-14 → 2026-01-14); amostra aleatória de 1 % = 152 171 moedas / 49,97 M tx; amostra de 5 dias = 149 028 moedas | on-chain; clusters de criador por até **3 saltos** de financiamento (excluindo serviços rotulados) | graduação; wash trading WT1 = "same address buys and sells same amount within single transaction" | graduação **1,02 %** na amostra; wash trading em **8,26 %** das moedas, **17 %** das tx de negociação, 1,32 % do volume; moedas com ≥ 10 001 tx têm **50,31 %** de wash; dobrar tx de wash → **+19 %** nas chances de graduar (2,0 % vs 0,90 %); top 1 % dos clusters criam **58,6 %** das moedas (3 saltos; 52,99 % em 1 salto); **4 402** dumps coordenados (mediana 7 remetentes); ≥ 1,5 M (> 10 %) de cópias — originais graduam **9,20 %** vs cópias **0,86 %**; 3,5 M (23,5 %) criadas após post social; 14 repos de bots de comentário; mints sem sufixo `pump` (interação direta) 26,5 % nas cópias vs 13,7 % nos originais | análise transacional só na amostra de 1 %; cópia detectada por hash exato de IPFS; não executou o software MMaaS |
| Li, Kuznetsov, Yanovich, Nott-Whaley, Vodolazov, *Catching the Rug* — arXiv 2608.20271v1 (20/08/2026), lido 02:29–02:30 | **6,4 M** memecoins Solana, 2024-11-30 → 2025-06-30 (pump.fun 6,3 M; Raydium 98 k) | on-chain, **primeiros 5 min** de negociação | rug = `MDD < −99 %` (TVL) **ou** `Idle > 80 %` do tempo de vida sem volume, avaliado em **1 h** pós-lançamento | "Over 80 % of Memecoins experience rug pulls"; teste pump.fun: 438 354 rugs vs 97 119 não-rugs; XGBoost F1 0,781 / MCC 0,356 / AUCPRC 0,756 (pump.fun), 0,80 com fusão; transferência Raydium→pump.fun colapsa (MCC ≈ 0); 23 features só de fluxo (contagens, razões compra/venda, preços, tempos) | "Results are not yet sufficient for real-world deployment"; sem resolução de entidades de bundle nem features de wash |
| Mancino, *The Memecoin Phenomenon* — arXiv 2512.11850v3 (18/12/2025), lido 02:20–02:22 | Q4/2024, pump.fun, via Dune | consultas Dune | graduação = retirada da curva para Raydium | pico de 69 046 mints/dia (71,1 % da Solana); graduação "peaks at less than 2 %"; 40–67,4 % das tx de DEX | sem sobrevivência, sem criador, sem concentração |
| Kamat, *Hour-Aware Adaptive Risk Management…* — arXiv 2606.08232v3 (03/08/2026), abs lido 02:31 | 190 trades reais, 2026-03-29 → 04-12 | deploy próprio | — | win rate **40,5 %**, retorno médio por trade **+0,62 %**, acumulado +117,7 %, assimetria −1,21, curtose 6,61; **"Removing the top three trades (1.6 percent of sample) flips cumulative return unprofitable"**; de 48 eventos ≥ 6 h, 27 (56,25 %) atingiram drawdown de 50 % | n = 190; efeito de hora "directional and non-confirmatory" (p = 0,5634) |
| Solidus Labs, *2025 Rug Pull Report* (maio/2025), lido 02:20–02:22 | > 7 M tokens do pump.fun com ≥ 5 trades, jan/2024 → mar/2025; 388 k pools Raydium | liquidez SOL restante após cada instrução; queimas de LP em ordem cronológica | "pump-and-dump" = cai abaixo de **US$ 1 000** de liquidez; soft rug Raydium = ≥ 90 % da liquidez retirada | **98,6 %** dos tokens do pump.fun; só **97 000** mantêm > US$ 1 000; Raydium **~93 % (361 k pools)**; maior rug US$ 1,9 M; mediana ≈ US$ 2 832; 25 % abaixo de US$ 732 | denominador do 98,6 % não é explícito; a seção "What is wash trading" contém texto placeholder ("Lorem ipsum") — **não há análise de wash** |
| Chainalysis, *Crypto Market Manipulation 2025* (29/01/2025), lido 02:25–02:26 | 2 063 519 tokens lançados em 2024 | heurística: endereço adicionou e depois removeu ≥ **65 %** da liquidez (≥ US$ 1 000), pool inativa, pool com > 100 tx | pump-and-dump suspeito | **74 037 (3,59 %)** dos tokens; ~94 % das pools "rugadas" pelo criador da pool; vida média 6,23 d, mediana 0; wash US$ 2,57 bi (limite superior) | **Ethereum, BNB e Base — não cobre Solana/pump.fun**; "tracks patterns of behavior and not intent" |
| Chainalysis, *2026 Crypto Crime Report* (landing lida 02:29) | — | — | — | conteúdo atrás de download; os "US$ 17 bi em golpes / US$ 2,8 bi em rug pulls" circulam só em fontes secundárias | **não confirmado em página primária** |
| Elliptic, blog de detecção de rug pull (28/11/2025, lido 02:32) e *State of Crypto Scams 2025* (PDF, lido 02:34–02:35) | — | Elliptic Investigator "can automatically identify smart contracts with activity patterns consistent with rug pull scams" | — | só estudos de caso ($HAWK, $LIBRA); "memecoin-based rug-pulls" citados como tendência | **sem limiares, sem contagens, sem pump.fun** |
| TRM Labs (busca restrita a trmlabs.com, 02:32) | — | — | — | nenhum relatório específico de pump.fun/lançamentos; só o blog "Tracing $TRUMP" | não encontrado |

### 1.2 Taxa-base de graduação e o método por trás de cada número

| Número | Janela | Método | Comparável com os outros? |
|---|---|---|---|
| 0,63 % | set–out/2025 | on-chain completo (Marino) | sim — é o mais limpo |
| 0,198 % (limite inferior) | mai–jun/2026 | polling da API com janela efetiva de ~6 min (Kamat) | **não** sem ajuste — só captura graduações em ≤ 6 min |
| 1,02 % | jan/2024 → jan/2026 | amostra de 1 % on-chain (Szwajcok) | sim, mas mistura dois anos e regimes |
| < 2 % | Q4/2024 | Dune (Mancino) | ordem de grandeza |
| 9,20 % vs 0,86 % | idem Szwajcok | originais vs cópias | mostra que "taxa de graduação" depende do subconjunto |

Conclusão operacional: a taxa-base **não é uma constante**; o T4.2 mede a sua (série diária com
`available_at`, mesma retenção para graduados e não), e a H-P27 (regime do BTC) já está na fila.

### 1.3 Bundlers e snipers — prevalência medida

- Kamat 2607.02795: 1 012 coortes persistentes em 13,4 dias; 2 965 endereços; o efeito **causal** de
  coordenação sobre compradores externos é +16,1 % em contagem e **nulo em SOL**; 7,0 % dos lançamentos
  "tratados" não recebem nenhum comprador externo em 30 min. Leitura para nós: **sniper ≠ sinal de que a
  moeda corre**; é sinal de que alguém está operando a moeda.
- MELT: os 10 primeiros compradores dos tokens de alto risco (pós-migração) detêm **17 pp** a mais do
  supply; 36,5 % do supply em contas coordenadas.
- Marino: parcela de bots (tx direta ao programa) é **negativa** para graduação em níveis intermediários.
- Nenhuma fonte primária publica "X % dos lançamentos são bundled" com definição de bundle igual à das
  ferramentas (mesma tx / mesmo slot / mesmo financiador). Fica para o T4.2 medir.

### 1.4 Wash trading

Só Szwajcok mede no pump.fun (WT1 = compra e venda do mesmo montante pelo mesmo endereço **na mesma
tx**): 8,26 % das moedas, 17 % das tx, 1,32 % do volume; associação **positiva** com graduação (+19 % nas
chances por duplicação) — o que é coerente com "volume falso atrai comprador real", não com "wash =
moeda ruim". Solidus não analisa (placeholder); Chainalysis não cobre Solana.

### 1.5 Dumps do criador — o que existe e o que **não** existe

- Marino: 92,22 % dos tokens com ≥ 30 swaps têm ≥ 1 dump (queda de 4σ no log-retorno) — **não é
  específico do criador**; é "alguém vendeu forte".
- Szwajcok: dump coordenado (vários remetentes → um endereço que vende), 4 402 casos na amostra de 1 %;
  clusters de criador por financiamento: top 1 % = 58,6 % das moedas — identidade por carteira única
  subestima o criador em ~11×.
- **Não encontrado em fonte primária:** a parcela de lançamentos em que o criador é vendedor líquido nos
  primeiros N minutos, nem o timing típico da venda do criador. É medida do T4.2 (F-B3, H-P33).

### 1.6 Concentração de holders — limiares "que predizem falha"

Nenhum paper publica um limiar validado do tipo "top-10 > X % ⇒ rug". O que existe: diferenças de
17–19 pp entre alto e baixo risco (MELT, pós-migração); regras de ferramenta (rugcheck: top-10 > 50 %
= `warn`; um único holder com parcela grande = `danger`; Mobula: snipers > 20 % combinados ou rede de
bundlers com 10+ carteiras = "red flag"). Os limiares de guias de terceiros (top-10 > 30 %, dev > 5 %)
são **secundários e sem validação** — não entram como regra; entram como tercis fixados na janela de
calibração do T4.2 (§5).

### 1.7 Curvas de sobrevivência

- Tempo até graduar: mediana 1,66 min (Kamat, regime rápido) e 4,4 min (Marino, on-chain completo).
- Tempo até "morrer": Li — > 80 % "rugadas" em 1 h pela definição MDD ≥ 99 % ∨ ocioso ≥ 80 %; MELT —
  84,13 % abaixo de 30 % do preço de migração em 20 min (só graduados); Kamat 2606 — 27/48 (56,25 %) dos
  eventos ≥ 6 h chegaram a −50 %.
- **Não encontrado:** curva "tempo até −90 %" no pump.fun em fonte primária. A única série de "morte"
  com método é secundária (chainplay.gg via Dune, ~2024: 15 % morrem no 1.º dia, 31 % em 7 d, 98 % em 3
  meses, "morto" = volume 24 h < 10 % do pico) — citada só para contexto, não como número.

### 1.8 Sinais sociais na literatura

Kamat 2607.02823: Telegram na metadata multiplica a graduação (regime rápido) por 8,94×; três canais,
17,4×. Szwajcok: 23,5 % das moedas nascem depois de um post; há 14 repositórios de bots de comentário —
**o sinal social é manipulável por construção**. Nenhuma fonte mede replies/livestream do próprio
pump.fun como preditor.

---

## 2. Heurísticas das ferramentas — definições exatas quando publicadas

| Ferramenta (lida 12/09) | Métrica | Definição publicada (verbatim quando há) | Limiar publicado | Acesso |
|---|---|---|---|---|
| **rugcheck.xyz** — Swagger `api.rugcheck.xyz/swagger/doc.json` (02:23) + chamadas reais `GET /v1/tokens/{mint}/report/summary` (02:22:02) e `/report` (02:29) | `risks[]` com `name`, `value`, `description`, `score`, `level`; `score`; `score_normalised` (0–100, maior = mais risco, segundo o próprio site); `lpLockedPct`; relatório completo com `topHolders[]{address, owner, amount, uiAmount, pct, insider}`, `totalHolders`, `graphInsidersDetected`, `insiderNetworks`, `creator`, `creatorBalance`, `creatorTokens`, `knownAccounts` (rótulos), `mintAuthority`, `freezeAuthority`, `transferFee`, `tokenMeta.mutable`, `markets[].lp.lpLockedPct`, `launchpad`, `deployPlatform`, `rugged`, `detectedAt`, `events`, `lockers` | observado ao vivo: `"Single holder ownership"` (value `51.17%`, score 5116, `danger`, "One user holds a large amount of the token supply") e `"High holder concentration"` (score 1011, `warn`, "The top 10 users hold more than 50% token supply") | top-10 > 50 % (do texto da regra); o limiar do `danger` por holder único não é publicado | público sem chave: `/report`, `/report/summary`, `/insiders/graph`, `/insiders/networks`, `/stats/*`; com chave: `bulk`, `lockers`, `verify`. Rate limit não documentado — não presumir |
| **GMGN** — `docs.gmgn.ai/index/featured-icon-definition` e `/meme-coin-trading` ("Last updated May 2026"), 02:20–02:22 | Dev; Sniper; Bundled; Insider/Rat; Fresh wallet; Phishing wallet; Smart money; KOL; Top holder; Blue chip | Dev = "Token creator"; Sniper = "Wallet who buys in earlier blocks after pool created"; Bundled = "A single account combines multiple wallets' txs into one tx bundle, processed in the same block"; Insider/Rat = "Wallet who has insider information and owns token earlier"; Fresh wallet = "Newly created wallet"; Holder concentration = "percentage of token supply held by the top N wallets, typically reported as 'top 10' and 'top 50'"; Dev sell = "A sale by the deployer wallet… Treated as a strong negative signal" | nenhum limiar como regra (os "10 %" da página são exemplos de tela) | site/app; sem API pública documentada nessas páginas |
| **Axiom** — `docs.axiom.trade/axiom/finding-tokens/pulse`, 02:20–02:22 | Top 10 Holders %; Dev Holding %; Snipers %; Insiders %; Bundle %; Holders; Pro Traders | Snipers % = "the percentage of early buyers (snipers)"; Insiders % = "percentage held by insiders (private sales, team members)"; Bundle % = "percentage of supply held in bundle wallets"; Dev Holding % = "percentage of supply held by developers" | nenhum | terminal; sem API pública nessas páginas |
| **BullX Neo** — `bullx.gitbook.io/bullx-neo-docs/trading-terminal/analytics`, 02:23–02:24 | Insider wallets; Sniper wallets; Bot users; Top 10 %; Holders; LP burned (Audit) | Insider = "Wallets that were sent tokens without buying them"; Sniper = "A wallet that bought the token very early", painel cobre os **primeiros 70 compradores**; Bot user = "A wallet from trading bots like BullX, Trojan, etc." | nenhum | terminal |
| **Mobula** — `docs.mobula.io/almanac/detecting-snipers-bundlers`, 02:20–02:22 | `snipersHoldingsPercentage`, `bundlersHoldingsPercentage`, `labels[]`, `taggedHolders`, `taggedHoldingsPercentage` | Sniper = "purchases tokens within the first few blocks (typically 0-3 blocks) after a token launches"; sinais: proximidade de bloco, posição na tx, idade da carteira, "funded just before the launch"; Bundler = "coordinates multiple wallets to buy in the same block or even the same transaction"; sinais: mesma tx, financiador comum, mesmo bloco, montantes parecidos, cluster ≥ 3 carteiras | "Multiple sniper wallets holding > 20% combined"; "Large bundler networks (10+ wallets)" | API keyed |
| **Solana Tracker** — `docs.solanatracker.io/guides/pumpfun` (02:23) e `solanatracker.io/data-api` (02:25) | risco 1–10 "built from 20+ on-chain factors"; salas WS `sniper:{token}`, `bundlers:{token}`, `insider:{token}`, `dev_holding:{token}`, `holders:{token}`, `top10:{token}`; `GET /deployer/{wallet}?launchpad=pumpfun` | definições não publicadas nessas páginas | não | chave obrigatória; Free **2,5 k req/mês, 3 req/s**, sem WS; Advanced € 50/mês (200 k); Premium € 397/mês para Datastream |
| **Photon** — gitbook `pies-organization.gitbook.io/photon-trading` (02:23–02:26) | filtros do Memescope (holders, progresso da curva, dev holding %, aviso de snipers) só anunciados no X | **nenhuma definição publicada** nas páginas abertas | — | terminal |
| **pump.fun (próprio)** — chamadas reais 02:23–02:29 | `is_banned`, `nsfw`, `verified`, `hide_banner`, `boost_mode` (`NONE`/`COMPLETED` observados), `mayhem_state`, `security_verdict` | **sem documentação**; `security_verdict` apareceu no detalhe de uma moeda às 02:00 (notas A4.1b) e **não** apareceu no detalhe de outra às 02:27 — campo condicional de semântica desconhecida | — | `frontend-api-v3`, 60 req/60 s por IP |

Armadilha observada ao vivo (rugcheck, 02:22, mint Mayhem `5JcKY…pump`): o "Single holder ownership
51,17 %" corresponde a um holder com `uiAmount` 1 023 312 494 — mais do que o supply-base de 1 bilhão,
ou seja, é a curva/vault do Mayhem (supply 2 bilhões), não uma carteira. **Nenhuma ferramenta genérica
exclui a bonding curve, o vault Mayhem, o pool PumpSwap ou os endereços de burn por padrão** — o T4.2 faz
essa exclusão (critério de aceite já escrito no plano) e nunca herda o número pronto de terceiros.

---

## 3. Reputação do criador/dev — sinais e onde cada um é exposto

| Sinal | Como obter | Custo | Status na literatura |
|---|---|---|---|
| Compra inicial do dev (SOL e parcela do supply) | PumpPortal `subscribeNewToken` (grátis) — payload real gravado em `packages/exchange-adapters/tests/fixtures/pumpfun/pumpportal_ws_a41_live.json`: `initialBuy` (tokens), `solAmount` (SOL), `traderPublicKey` (criador), `vSolInBondingCurve`, `marketCapSol`, `is_mayhem_mode`, `pool`; on-chain: `CreateEvent` + primeiro `TradeEvent` do criador (T4.0d) | zero adicional | Kamat: HR 4,51 por log(1+mcap inicial); Q4 (> 31,04 SOL) gradua 0,634 % (regime rápido) |
| Lançamentos anteriores da mesma carteira e desfecho | on-chain: `getSignaturesForAddress(creator)` + filtro de instruções `create` (grátis, ~1 chamada por 1 000 assinaturas + 1 `getTransaction` por candidata); rugcheck `creatorTokens` (veio `null` na moeda testada — forma quando existe não observada); Solana Tracker `/deployer/{wallet}` (chave); Bitquery "all tokens created by a specific address" (chave); `frontend-api-v3`: o literal `user-created-coins` existe no bundle JS, mas `GET /coins/user-created-coins/{wallet}` devolveu **404 "Cannot GET"** às 02:27 — rota provavelmente por `userId` de perfil, não por carteira; não mapeada | baixo a médio (cresce com o histórico da carteira) | Marino: "top creators… does not improve predictive performance relative to baseline" (suporte pequeno); Szwajcok: identidade por carteira única subestima ~11× |
| Fonte de financiamento da carteira do criador | Helius `GET /v1/wallet/{address}/funded-by` (`funder`, `funderName`, `funderType`, `amount`, `timestamp`) — **só plano pago** (Free devolve 403), só o **primeiro** transfer de SOL, "historical data is only available for wallets created after this feature was deployed" (data não publicada); on-chain: assinatura mais antiga da carteira + `getTransaction` (2+ chamadas), rótulo de exchange precisa de lista própria (rugcheck expõe `knownAccounts` com rótulos no relatório) | médio | Mobula lista "funded just before the launch" como sinal de sniper; Szwajcok usa saltos de financiamento para agrupar criadores |
| Tempo entre financiamento e lançamento; idade da carteira | derivado: `blockTime` da primeira assinatura vs `blockTime` do `create` | idem | sem número primário sobre pump.fun |
| Cluster de criador (financiador comum) | on-chain, 1–3 saltos (Szwajcok) | alto (grafo) | top 1 % dos clusters = 52,99 % (1 salto) → 58,6 % (3 saltos) das moedas |
| Mayhem ligado na criação | PumpPortal `is_mayhem_mode`; API `mayhem_state` / `mayhem{state, mode}`; on-chain via programa Mayhem (T4.0d) | zero | H-P28 já na fila |

---

## 4. Sinais sociais — o que se mede sem login, e o que não

Medido ao vivo em `frontend-api-v3.pump.fun` (02:23–02:29 BRT; 19 requisições no total, sob 60/min):

| Sinal | Onde | Estado observado hoje |
|---|---|---|
| `reply_count` | listagem `/coins?…` e detalhe `/coins/{mint}` | presente (0 nas duas amostras) — contagem, sem conteúdo |
| conteúdo das replies | `GET /replies/{mint}` | **404 "Cannot GET"** — rota não é essa no v3; não medível hoje sem mapear (T4.0c) |
| `is_currently_live`, `num_participants`, `livestream_title`, `thumbnail`, `playlist_url*`, `livestream_ban_expiry` | `/coins/currently-live` e detalhe | presentes; `num_participants` = 3 e 2 nas duas leituras de uma live |
| `twitter`, `telegram`, `website` | detalhe e listagem | **chaves condicionais**: o detalhe da moeda live trouxe `twitter`/`website` vazios e **nenhuma** chave `telegram`; a listagem mais nova (02:29) não trouxe nenhuma das três. A leitura estável é o JSON do `uri` on-chain (convenção dos SDKs; a confirmar no T4.1) |
| King of the Hill | `GET /coins/king-of-the-hill` | **404** com `"Coin not found for mint: king-of-the-hill"` (a rota cai em `/coins/{mint}`); `king_of_the_hill_timestamp` ausente da listagem e do detalhe; **0 ocorrências** de `king_of_the_hill`/`king-of-the-hill` nos 40 chunks JS da home (02:27–02:30). Tratar como **indisponível no v3 hoje**; não prova ausência em outro host |
| `ath_market_cap`, `ath_market_cap_timestamp`, `last_trade_timestamp` | listagem/detalhe | presentes — úteis como rótulo (máximo atingido), **nunca** como feature no minuto t |
| `boost_mode`, `verified`, `is_banned`, `nsfw`, `hide_banner`, `security_verdict` | listagem/detalhe | presentes, sem documentação; `security_verdict` condicional |
| Mayhem | `/coins/mayhem-mode?mayhemState=`, `/mayhem/overview` | confirmados na A4.1b |

**Não medível sem login/chave:** membros e atividade de grupos Telegram (exige API/conta), seguidores e
engajamento no X, identidade dos espectadores da live, Discord, "dex paid"/"CTO" de terceiros. O
`reply_count` e os bots de comentário (14 repos, Szwajcok) tornam qualquer contagem social um sinal
manipulável — entra como feature, nunca como filtro.

---

## 5. Catálogo de features para o T4.2

Regras transversais (valem para todas as linhas):

1. **Não-antecipação.** `feature(mint, t)` usa só eventos com `block_time ≤ t` **e** `available_at ≤ t +
   latência declarada`; campos da API HTTP carregam `observed_at` e entram só a partir dele. Histórico do
   criador usa só lançamentos criados antes de `t`. Rótulos (§5.E) são calculados em `t + H` e nunca
   vazam para a esquerda.
2. **Ausência ≠ zero.** Feature sem cobertura recebe `null` com motivo (`not_subscribed`,
   `insufficient_coverage`, `rate_limited`, `unsupported_quote`) — MUST-FIX 1 da Astra.
3. **Exclusões de holders:** curva, vault/agente Mayhem (`BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`),
   pool PumpSwap pós-migração, burn. Trades do agente Mayhem saem das métricas orgânicas.
4. **Tercis fixados na janela de calibração** (mesma regra da EXP-0027): limiares calculados sobre a
   primeira janela de coleta, nunca recalculados; a leitura descritiva usa a janela seguinte.
5. **Custo** é por mint e por minuto de snapshot, na fonte grátis quando existe; "trades" só existem para
   a população coberta (WS pago 0,01 SOL/10 k eventos **ou** decodificação on-chain do T4.0d).

Legenda de fonte: **OC** on-chain (RPC/decoder), **PP** PumpPortal WS, **API** `frontend-api-v3`,
**K** provedor com chave.

### A. Curva e fluxo (por mint, por minuto)

| ID | Feature | Definição | Fonte | Custo | Conhecido no minuto t? | Hipótese |
|---|---|---|---|---|---|---|
| F-A1 | `curve_progress_pct` | `1 − real_token_reserves / initial_real_token_reserves` | OC/PP/API | zero | sim (estado da curva no último trade ≤ t) | H-P29, D-P36 |
| F-A2 | `swaps_to_progress_{10,25,50}` | número de trades até o progresso cruzar X % (Marino: "trading intensity… cumulative number of swaps… up to the moment a given vSol threshold is first reached") | OC/PP (trades) | precisa de trades | sim, se o cruzamento ocorreu ≤ t; senão `null` | **H-P29** |
| F-A3 | `unique_buyers_{1,5}m` | carteiras distintas com `side=buy` na janela, excluindo criador e agente Mayhem | trades | trades | sim | H-P35 |
| F-A4 | `buy_sell_ratio_{1,5}m` (contagem e notional, duas colunas) | Li 2608.20271: `buy_sell_cnt_ratio`, `buy_sell_value_ratio` | trades | trades | sim | painel |
| F-A5 | `sol_inflow_{5,30}m` | SOL líquido entrado (compras − vendas) excluindo coorte/criador | trades | trades | sim | H-P35 |
| F-A6 | `price_change_first3_slots` | variação do preço marginal da criação até o 3.º slot (Li: `price_change_first_to_3_blocks`) | OC | trades | sim após 3 slots | painel |
| F-A7 | `largest_buy_share_5m` | maior compra única / supply | trades | trades | sim | H-P35 |
| F-A8 | `time_to_first_sell_s` | segundos entre criação e primeira venda (Li: `first_sell_time`) | trades | trades | sim se já ocorreu; senão censurado, **não** `null` — coluna `first_sell_seen: false` | H-P33 |
| F-A9 | `wash_tx_share_WT1` | fração de tx em que o mesmo endereço compra e vende o mesmo montante na mesma tx (Szwajcok WT1) — exige múltiplos eventos por tx, logo a PK de `meme_trades` precisa do índice de instrução (MUST-FIX 2) | OC | trades + índice de instrução | sim | **H-P30** |
| F-A10 | `direct_program_share` | fração de trades cuja tx não passa pelo front-end (Marino `isBot`); proxy: programa invocado diretamente vs via roteador — **definição a fechar com o T4.0d** | OC (`getTransaction`) | alto (1 chamada por tx) | sim | painel |

### B. Criador

| ID | Feature | Definição | Fonte | Custo | Conhecido no minuto t? | Hipótese |
|---|---|---|---|---|---|---|
| F-B1 | `dev_initial_buy_sol` | `solAmount` do evento de criação | PP/OC | zero | sim, no minuto 0 | **H-P31** |
| F-B2 | `dev_initial_supply_pct` | `initialBuy / total_supply` | PP/OC | zero | sim | H-P31 |
| F-B3 | `creator_net_sol_{5,10,60}m`, `creator_sold_any` | SOL líquido do criador (vendas − compras) na janela; `creator_sold_any` distingue **venda** de **transferência** (fixture obrigatória do T4.2) | trades + transferências | trades | sim; `null(not_subscribed)` fora da cobertura | **H-P33** |
| F-B4 | `creator_prior_launches_n` | lançamentos da mesma carteira antes de `created_at` | OC (`getSignaturesForAddress`) | 1 chamada/1 000 assinaturas + 1 por candidata | sim (só passado) | **H-P32** |
| F-B5 | `creator_prior_graduation_rate` | graduados / F-B4, com `null` se F-B4 = 0 | OC | idem | sim | H-P32 |
| F-B6 | `creator_wallet_age_s` | `created_at − blockTime(primeira assinatura)` | OC | 1–2 chamadas | sim | painel |
| F-B7 | `creator_funding_to_launch_s` | `created_at − blockTime(primeiro transfer de SOL recebido)` | OC (ou Helius pago) | 2+ chamadas | sim | painel |
| F-B8 | `creator_funder_class` | `cex_labeled` / `unlabeled` / `fresh_chain` (financiador também com < 24 h) — lista de rótulos própria; `null` se não resolvido | OC + rótulos | médio | sim | painel |
| F-B9 | `creator_cluster_id` | componente por financiador comum (1 salto primeiro; 3 saltos depois) | OC | alto | sim, só com histórico ≤ t | H-P32 (adendo) |
| F-B10 | `is_mayhem` | `is_mayhem_mode` (PP) / `mayhem_state` (API) / flag on-chain | PP/API/OC | zero | sim | H-P28 |

### C. Holders e coordenação

| ID | Feature | Definição | Fonte | Custo | Conhecido no minuto t? | Hipótese |
|---|---|---|---|---|---|---|
| F-C1 | `top10_share_ex_curve` | parcela dos 10 maiores owners excluindo curva/vault/pool/burn | OC (`getTokenLargestAccounts` → 20 contas; agregar por owner) | 1 chamada/snapshot | sim (estado ≤ t) | painel; H-P35 |
| F-C2 | `top1_share_ex_curve` | idem, maior holder | OC | idem | sim | painel |
| F-C3 | `holders_n` | owners com saldo > 0 (contas de token via `getProgramAccounts` é caro — usar contagem incremental dos trades quando coberto; senão `null`) | OC/trades | médio | sim | painel |
| F-C4 | `first10_buyers_supply_pct_t` | supply detido em `t` pelos 10 primeiros eventos de compra (definição Kamat: eventos, não carteiras) | trades + saldos | trades | sim | **H-P35** |
| F-C5 | `same_slot_buyers_n` | compradores distintos no slot da criação e nos 3 slots seguintes (Mobula: 0–3 blocos) | OC | trades | sim após 3 slots | H-P35 |
| F-C6 | `bundle_flag` | ≥ 2 compradores distintos na **mesma tx** da criação, ou ≥ 3 carteiras no mesmo slot com o mesmo financiador (Mobula; Szwajcok) | OC | trades (+ financiador: 1 chamada por carteira) | sim | H-P35 |
| F-C7 | `cohort_hit` | algum dos 10 primeiros compradores pertence a uma coorte persistente construída **nos nossos próprios dados** (pares com ≥ 3 coocorrências nos 10 primeiros, union-find — regra de Kamat 2607.02795), catálogo congelado por semana e usado só na semana seguinte | trades | baixo (grafo semanal) | sim, com catálogo da semana anterior | H-P35 |
| F-C8 | `fresh_wallet_share_first10` | fração dos 10 primeiros compradores cuja primeira assinatura tem < 24 h (GMGN "Fresh wallet"; Mobula "wallet age") | OC | 1 chamada por carteira (10/mint) | sim | painel |
| F-C9 | `insider_transfer_share` | supply recebido por transferência sem compra (BullX "Insider") | OC (transferências SPL) | médio | sim | painel |

### D. Metadata e front-end (best effort)

| ID | Feature | Definição | Fonte | Custo | Conhecido no minuto t? | Hipótese |
|---|---|---|---|---|---|---|
| F-D1 | `has_twitter`, `has_telegram`, `has_website` | booleanos lidos do JSON do `uri` on-chain no minuto 0 (fallback: chaves da API quando existirem, com `observed_at`) | OC (1 GET IPFS) / API | 1 GET | sim | **H-P28(a) painel** |
| F-D2 | `description_len` | comprimento da descrição (Kamat HR 1,05) | OC/API | idem | sim | H-P28(a) painel |
| F-D3 | `reply_count_t` | `reply_count` da API com `observed_at` | API | 1 req/mint (orçamento 60/min → só subconjunto) | só a partir de `observed_at` | painel |
| F-D4 | `is_live_t`, `num_participants_t` | idem | API | idem | idem | painel |
| F-D5 | `boost_mode_t`, `verified`, `is_banned`, `nsfw`, `security_verdict` | campos não documentados, gravados crus com rótulo `source=frontend_api_v3` | API | idem | idem | nenhuma até haver semântica |
| F-D6 | `copycat_flag` | `name`+`symbol` já vistos nos últimos 7 dias na nossa base (Szwajcok usa nome, símbolo, descrição e hash IPFS) | base própria | zero | sim | **H-P34** |
| F-D7 | `vanity_pump_suffix` | mint termina em `pump` (26,5 % das cópias vs 13,7 % dos originais não terminam) | OC | zero | sim | painel |

### E. Rótulos (desfechos — calculados em `t + H`, nunca features)

| ID | Rótulo | Definição | Fonte |
|---|---|---|---|
| L-1 | `graduated_{1h,24h,7d}` | `complete=true` e `real_token_reserves=0` até `t+H`; `migrated_at` separado | OC/PP |
| L-2 | `time_to_graduation_s` | censurado à direita se não graduou (`graduated=false`, não `null`) | OC/PP |
| L-3 | `max_multiple_{5m,1h,24h}` | máximo do preço **marginal** da curva / preço marginal na entrada de referência (§6) | OC/trades |
| L-4 | `rug_1h` | `MDD ≤ −99 %` do preço marginal **ou** ocioso ≥ 80 % do tempo de vida (Li) — duas colunas separadas antes de qualquer OU | trades |
| L-5 | `min_price_ratio_20m_post_migration` | MELT (só graduados; rótulo de segunda fase) | OC (PumpSwap) |
| L-6 | `creator_net_seller_10m` | rótulo-painel (H-P33) — o mesmo dado de F-B3 usado como desfecho, nunca no mesmo teste como feature | trades |

---

## 6. O que a literatura diz sobre "comprar cedo e vender no ROI alto"

**Honestamente: nenhuma fonte primária publica a probabilidade de uma moeda recém-criada atingir k× em
1 h ou 24 h com método.** O que existe:

- Marino et al. (2602.14860): a curva empírica `P(grad | ∃x: x > vSol)` só aparece em figura (sem tabela
  numérica) e, para o buy-and-hold ingênuo, "p_std(vSol) lies below the breakeven curve, hence it is not
  possible to make profits with a buy-and-hold strategy based only on vSol". Regra de breakeven publicada:
  `p(vSol) > vSol²/115²`. Ou seja: entrar mais cedo dá múltiplo maior **se** graduar, e a probabilidade
  de graduar não compensa em média. O paper não modela saídas antes da graduação.
- Kamat 2606.08232 (190 trades reais): win rate 40,5 %, média +0,62 % por trade, e "Removing the top
  three trades (1.6 percent of sample) flips cumulative return unprofitable" — a cauda direita é tudo.
- Kamat 2607.02795: "a token's first thirty minutes of activity largely determine whether it accumulates
  the buyer momentum necessary to graduate".
- Li 2608.20271: > 80 % "rugadas" em 1 h pela definição deles; MELT: 84,13 % dos **graduados** caem abaixo
  de 30 % do preço de migração em 20 min.

Aritmética minha (não da fonte), a partir da curva confirmada em T4.0 §3 (`x·y = k`, 30 SOL e 1,073 bi
tokens virtuais) e do limiar de 115 SOL virtuais citado por Marino — o T4.0d, com o `Global` lido ao
vivo, é a autoridade final: o preço marginal cresce com `vSol²`, logo o múltiplo sobre o preço inicial
é `(vSol/30)²`. **2× ⇔ vSol ≈ 42,4 SOL (≈ 12,4 SOL reais); 3× ⇔ ≈ 52,0; 5× ⇔ ≈ 67,1; 10× ⇔ ≈ 94,9;
graduação ⇔ ≈ 14,7×.** Sem taxas (1,25 % na curva, duas vezes) e sem o slippage da própria venda —
"ROI alto" no preço marginal não é ROI realizável (mesmo aviso do plano §4).

A **H-P29(ii)** (Astra, run 13) já substitui essa parábola pela régua geral `p > (I−F)/(S−F)` — com o 1,25 % nas
duas pontas o limiar multiplica por 1,0254767, `S` sai da reserva disponível na saída e só existe depois da
migração — e o painel D-P36 abaixo existe para dar `S` e `F` **medidos**, não deduzidos.

### Como o T4.2 vai medir isto nos nossos dados (protocolo D-P36, painel descritivo)

1. **Coorte = todas as criações** observadas numa janela fixada antes (≥ 30 dias), com a mesma retenção
   para graduados e não graduados. **Pré-requisito duro:** cobertura de trades para a coorte inteira
   (decoder on-chain do T4.0d ou WS pago) — assinar trades só das moedas "promissoras" é seleção por sucesso
   no denominador, e o painel nasce viciado.
2. **Regras de entrada simuladas, escritas antes:** primeiro trade após `t0 + 30 s`; progresso ≥ 5 %;
   ≥ 10 %; ≥ 25 %. Preço de entrada = preço da curva **para o nosso tamanho** (fórmula da curva, não o
   marginal), + 1,25 % de taxa.
3. **Desfechos:** para k ∈ {1,5; 2; 3; 5; 10} e H ∈ {5 min; 1 h; 24 h}, fração da coorte cujo preço
   **realizável** (saída do nosso tamanho pela curva, − 1,25 %) atinge k× dentro de H; separadamente, o
   drawdown máximo antes de atingir k×; `unknown` explícito quando a cobertura acaba antes de H.
4. **Régua:** blocos de dia inteiro (20 000 reamostragens, semente fixada no pré-registro), IC 95 %
   sobre cada célula, Holm sobre a família (k × H × regra de entrada); n mínimo 100 avaliáveis **e** 30
   dias por célula; nenhuma célula é escolhida depois de olhar; o painel **não emite veredito** — só a
   próxima hipótese pode.
5. **Cenários de falha nomeados:** (i) a fração que atinge 2× em 5 min pode ser dominada por bundles que
   compram de si mesmos (F-C6/F-C7 como colunas de decomposição, não de filtro); (ii) o preço realizável
   depende do tamanho — reportar em três tamanhos (0,1 / 0,5 / 2 SOL) e nunca extrapolar; (iii) regime:
   comparar com a série diária de graduação (H-P27).

---

## 7. Hipóteses — o que já estava na fila (run 13, Astra) e o que esta rodada acrescenta

Enquanto esta pesquisa corria, o plantão (run 13, commit `57b8f47`) registrou na fila: **D-P25** (janela de
visibilidade efetiva do coletor — o caso de falha dos corrigenda de Kamat), **H-P29** (velocidade: nº de
trades até a primeira passagem por cada nível de vSol, mais a pergunta de política com a régua
`p > (I−F)/(S−F)` e custos nas duas pontas), **H-P30** (WT1 por estratos de intensidade e idade), a
**H-P27 reescrita** (volatilidade antecedente do BTC) e o **painel de reforço da H-P28** (presença social na
criação, cohort de sniper nos 30 min, `min_price_ratio_20m`). **Nada disso é duplicado aqui**: as features
F-A2, F-A9, F-D1/F-D2 e F-C7 do catálogo alimentam essas linhas. Esta rodada acrescenta o que faltava:

| ID | Uma frase | Features | Fonte-mãe |
|---|---|---|---|
| H-P31 | compra inicial do criador (quartis fixados) separa conclusão 24 h **e** drawdown pós-pico — dois desfechos, Holm; Mayhem em estrato próprio | F-B1, F-B2 | Kamat 2607.02823 (HR 4,51; Q4 0,634 %) |
| H-P32 | (falseamento, com margem de equivalência) histórico do criador por carteira **não** separa conclusão 24 h; adendo por cluster de financiamento (1 salto) | F-B4, F-B5, F-B9 | Marino; Szwajcok |
| H-P33 | taxa-base do "criador vendedor líquido em 5/10/60 min" (ninguém publica) e associação com L-1/L-4; venda ≠ transferência | F-B3, F-A8 | lacuna documentada em §1.5 |
| H-P34 | cópia de nome+símbolo nos 7 dias anteriores ⇒ conclusão 24 h menor; coluna do mesmo criador | F-D6 | Szwajcok (9,20 % vs 0,86 %) |
| H-P35 | coordenação nos 10 primeiros eventos de compra ⇒ **mais** compradores em 30 min, **não** mais SOL líquido, **pior** drawdown 24 h — estende o painel H-P28(b) com o desfecho que ele não tem | F-C4–F-C6, F-A3, F-A5, F-A7 | Kamat 2607.02795; MELT; Mobula |
| D-P36 | painel k× **realizável** por regra de entrada, horizonte e tamanho (§6) — a tabela descritiva que a H-P29(ii) precisa para `S` e `F` | L-3, F-A1 | Marino (breakeven); Kamat 2606.08232; Li 2608.20271 |

## 8. O que este documento **não** fechou

- Rotas de replies, top holders e "coins by creator" no `frontend-api-v3` (404 nas rotas de 2024/2025;
  os literais `user-created-coins`, `holders`, `livestream` existem no bundle) — mapa do T4.0c.
- Semântica de `security_verdict`, `boost_mode`, `verified` — sem documentação primária.
- Custo por mint da decodificação on-chain completa (trades + transferências + holders) — T4.0d.
- Nenhuma fonte primária para: parcela de criadores vendedores líquidos em N min; curva "tempo até
  −90 %" na curva; base-rate de k× em 1 h/24 h. Todas viram medições do T4.2 (H-P33, L-4, D-P36).
- Chainalysis 2026 e Elliptic 2025: sem número específico de pump.fun em página primária aberta.
