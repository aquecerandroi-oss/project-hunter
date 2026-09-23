---
tags: [knowledge, solana, jupiter, binance, execucao, mapa-de-tokens, latencia, r63, m4]
tema: Binance como fonte de sinal e Solana (Jupiter) como venue de execução — quais mercados existem dos dois lados, quanto custa e quem lidera o preço
fonte: .claude/state/notes-R63.md (markets × lista verificada Jupiter v2 × cotações ida-e-volta × Lab 24 h × amostra de 38 pontos WIF)
fonte_url: https://lite-api.jup.ag/tokens/v2/tag?query=verified
lido_em: 2026-09-19
evidencia: medição própria — 664 ativos-base da `markets` casados com 3 476 tokens verificados da Jupiter e validados por paridade de preço com a Binance; 99 cotações ida-e-volta (0,02 SOL) + 10 em 1 e 5 SOL; 117 sinais e 39 oportunidades do Lab lidos do banco; 38 amostras de 15 s Binance × Jupiter (WIF)
hipotese_testavel: sim
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-19
confiança: "?"
---

# KB-0145 — Binance como sinal, Solana como execução (R63, 19/09/2026)

## O que afirma

**Dos 664 ativos que a Binance nos dá, 90 têm execução real na Solana pela Jupiter (custo ida-e-volta < 1 % em 0,02 SOL), mas só 58 são tokens nativos — o resto é ponte (8) ou "representação" de mcap < 1 M US$ (24), e o símbolo sozinho engana: 54 homônimos verificados pela Jupiter (ADA, MASK, NEIRO, 1000SHIB…) têm preço 90–100 % diferente do da Binance.** O filtro que funciona é paridade de preço (‖Δ‖ ≤ 3 %) + rota + custo, não a tag `verified`. A Binance lidera a pool da Solana por **menos de 15 s** (correlação de retornos 0,63 contemporânea, 0,23 com 15 s de avanço da Binance), e a Jupiter cota **+9 bp** acima do mid da Binance — a vantagem de "ver lá, comprar cá" tem de vir do sinal, não da latência.

## Onde foi mostrado

- `markets` (1 021 linhas: 528 perps Binance, 200 monitorados; 493 spot, 21 monitorados) × `GET lite-api.jup.ag/tokens/v2/tag?query=verified` (3 476 tokens; o `tokens/v1/tagged/verified` devolve 404). Casamento por símbolo com prefixos `1000X`, escolha por maior `liquidity`, exclusão de `stocks/rwa`. Validação: `usdPrice` Jupiter × multiplicador vs `ticker/price` Binance às 12:41 UTC.
- Resultado: 161 casam por símbolo → 54 homônimos falsos, 7 stables/LST, 100 com paridade → 2 sem rota/erro (SONIC, MORPHO), 7 com custo ≥ 1 % (MELANIA 2,98 %, SOON 9,75 %, ZORA 4,07 %, LAYER 3,96 %, S 1,97 %, WET 1,83 %, HUMA 1,02 %) → **90** (84 perps + 6 spot; 52 no radar). Tiers de liquidez Jupiter: A ≥ 1 M US$ (33), B 100 k–1 M (34), C < 100 k (23). Custo mediano em 0,02 SOL: 0,20 % (a taxa das pools — Raydium AMM dá exatamente 0,50 %); em 1 SOL: MET 0,17 %, KMNO 0,02 %, WIF 0,20 %, BNB 0,37 %, RENDER 0,35 %, ARB 0,82 %; em 5 SOL: 0,01–0,54 % nos tier A, ARB 1,17 %.
- Lab às 13:00 UTC: regime `SIDEWAYS` 0,75; 117 sinais em 24 h em 15 mercados, todos `long`, todos `confidence 0,50` (momentum v3 51, mean_reversion v1–v14 63, mean_reversion_h1 3), 91 nos 90 candidatos mas **zero em nativos da Solana** (ZEC 19, ARB 18, UNI 11, TAO 9, SUI/LINK/ETH/DOGE 6, SOL/BNB 5). 39 oportunidades abertas nos 90, máximo 50,0 (BNB), nenhuma `WATCHING`/`HOT`. Top 3 do composto (35 % score long + 20 % ret 60 m + 15 % ret 15 m + 10 % volume 60 m ÷ média h + 20 % sinal long recente − 10 × custo): **MET** (nativo, +2,2 %/+4,9 %, 3,3× volume, oportunidade long 39), **BNB** (Portal, momentum v3 há 3,8 h, oportunidade long 33→50), **DOGE** (representação, momentum v3 às 13:00:02, oportunidade long 29). Só nativos tier A: MET, KMNO (9,8× volume), RENDER.
- 7 dias (12/09→19/09, `agent_signals` × `signal_outcomes`): 700 sinais, todos `long`, em 15 mercados, 10 deles com execução na Solana (ARB, BNB, DOGE, ETH, LINK, SOL, SUI, TAO, UNI, ZEC — nenhum nativo). `momentum v3` = 223 sinais e **Σ R −42,9** (85 alvos, 38 stops, 100 `invalidated` com R negativo; só ARB fica positivo, +0,2); `mean_reversion` v6/v7/v14 = 23 sinais cada e **Σ R +12,6 a +14,9** (UNI +6,9/+7,0, ZEC +3,9, ARB +2,8, TAO +1,3); v10 +12,2 em 48; v1 −1,5 em 33. Em 0,05 SOL (tamanho da mesa spot/1) o custo ida-e-volta dos 52 monitorados tem mediana 0,14 %; ENA 1,02 % cai.
- Amostra WIF 12:49–12:59 UTC, 38 pontos de 15 s (`bookTicker` perp × `quote` 2 USDC→WIF): Δ nível +8,8 bp (mediana +7,9, desvio 4,5); correlação dos retornos por defasagem: −15 s +0,23, 0 s +0,63, +15 s +0,03; faixa de preço nos 10 min só 23 bp (mercado parado — leitura limitada).

## Como mediríamos aqui

- **Já temos:** velas 1 m `is_final` da Binance para os 52 monitorados; `agent_signals`, `opportunities` com `decomposition->'components'`; `quote`/`swap` da Jupiter no executor de memes (T4.63) com marca a cada 1 s e saída por evento; ida-e-volta medida em 1,6 s mediana gatilho→pouso (R62).
- **Falta:** 34 dos 90 (RAY, POPCAT, MEW, TNSR, ME, GOAT, ZEREBRO, ALCH…) não estão no `is_monitored` — sem velas, sem baseline, sem sinal. O `monitor_rank` é por volume 24 h do perp, o que deixa de fora justamente os nativos da Solana com pool funda.
- **Custo assumido para papel:** 0,3 % ida-e-volta (tier A, ≤ 1 SOL) + 0,001 SOL de taxas por perna; slippage real a medir (R62 viu −0,07 % mediano em curva pump.fun, pools aqui são mais fundas).
- **Latência:** repetir a amostra numa hora de movimento (≥ 1 % em 10 min) com 3 tokens (nativo tier A, Portal, representação) e amostragem de 5 s; hoje a Binance lidera em < 15 s e não dá para dizer se é 400 ms ou 10 s.

## Hipótese testável no Lab

- **H1 (EXP a propor, "Binance→Solana"):** braço de papel com universo = 33 nativos tier A do mapa; gatilho = `momentum v3` ou oportunidade `long ≥ 40` no perp da Binance; execução = `quote`+`swap` Jupiter `slippageBps 50`, 0,5 SOL; saída alvo 2 R / stop 1 ATR(15 m) / 4 h. Alvo: expectancy > 0 líquida de 0,3 % por trade em 30 trades; refutação: expectancy ≤ 0 ou taxa de alvo < 35 %.
- **H2:** "a Binance lidera a pool por ≥ 1 vela de 1 m" — refutada nesta amostra (lead < 15 s). Se for confirmada numa hora volátil com pontes de 200 k US$ (BNB), a vantagem seria de execução, mas na direção errada (a pool atrasa e o nosso preço de entrada piora).
- **H3:** sinal `short` do scanner não tem execução na Solana — medir quanto do R do Lab vem de shorts antes de decidir se vale montar o braço (hoje: 0 shorts em 24 h; 21 de 39 oportunidades abertas são short/neutral).

## Por que pode falhar

Símbolo ≠ ativo (54 homônimos verificados). Representações de mcap < 1 M (DOGE, ARB, SUI, UNI, LINK, AVAX, AAVE, ENA…) têm pools de 2026-04 a 2026-09, `devMints 20` e emissor que não identifiquei — risco de desancoragem que a Binance não tem. Cotação ≠ pouso (taxa de prioridade, slippage, `6003 TooLittleSolReceived` da R62). Não há stop na Jupiter: o stop é o executor vigiando. Perp → spot perde alavancagem e ganha funding (longs pagam +0,005–0,010 %/8 h hoje). A amostra de latência é de 10 min num mercado parado. O composto de "força" é meu (pesos arbitrários, ver §3 da R63), não o `OpportunityScorer`. Os sinais do Lab hoje têm `confidence` fixa 0,50 — não discriminam.

## Segunda opinião (Astra)

Pendente.

## Relacionados

[[KB-0143-o-que-antecede-o-dump]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] · [[KB-0133-papel-vs-real-custo-fixo-e-atraso-de-30s]] · [[KB-0135-a-vantagem-nao-esta-na-saida]] · [[Strategy Backlog]] · `.claude/state/notes-R63.md` (mapa completo em JSON no §6)

## Atualização R71 (23/09/2026) — ampliar o mapa da `spot/1` sem afrouxar critério

A pergunta foi quais mercados em que a família `mean_reversion` disparou em 14 dias ainda faltam no mapa. São **68**, e só **6** têm token na Solana que passa no filtro do R63 (paridade ≤ 3 % com a Binance, medida pelo oráculo e pelo preço executável de 0,05 SOL; rota; ida-e-volta < 1 %). **DASHUSDT, o maior buraco (94 sinais da família em 7 d, 11 do v14), não tem representação validada**: os "DASH" da Jupiter são memecoins a −100 %. O mesmo vale para PROM, EGLD, KAS e mais 57: 51 não têm token, 10 têm só homônimo falso, e SOL fica fora por desenho.

A migração `0061_spot_desk_r71` semeia os 6:
- **ligados:** NEAR (wNEAR da **NEAR OmniBridge**, identidade confirmada no contrato `omni.bridge.near`, custo 0,144 %), BTC (**WBTC Portal**, 0,004 %) e ORCA (0,110 %);
- **desligado pela regra:** SLX (tier C);
- **retidos por nome:** XRP (wXRP da Hex Trust com **freeze authority ativa**, que pode impedir a venda do stop) e BIRB (90,9 % do supply nos maiores detentores).

Ganho: **+3 sinais v14 long por semana** sobre os 41 atuais (+7 %). Liberando XRP, +5 (+12 %). DASH valeria +11 e não é executável.

Lição nova: **wrappers com outro ticker (wNEAR, wXRP) escapam do casamento por símbolo exato**. Também não basta paridade, porque oráculo e cotação da Jupiter olham as mesmas pools. A identidade de uma ponte se fecha na fonte: registro da ponte, PDA da mint authority, site do custodiante. E a regra `enabled` não enxerga freeze authority nem concentração de supply.

Detalhes: `.claude/state/notes-R71.md` · revisão da Astra: `.claude/state/astra-review-r71.md`.
