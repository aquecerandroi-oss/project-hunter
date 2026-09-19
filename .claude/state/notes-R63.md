# R63 — Binance como sinal, Solana como execução: quais dos nossos mercados existem na Jupiter e o que o Lab diz deles agora

**Data:** 2026-09-19, `as_of` 10:0x BRT (13:00 UTC). **Pergunta (Everton, 10:1x BRT):** usar a Binance como fonte de sinal e comprar na Solana pela nossa carteira via Jupiter. (1) Quais ativos-base da tabela `markets` existem como SPL com liquidez real na Jupiter — mapa `binance_symbol → solana_mint` pela lista verificada, cotação ida-e-volta de 0,02 SOL, ficar só com custo < 1 %; (2) estado do Lab para esses mercados (sinais 24 h, oportunidades, velas 1 m 60 min); (3) top 3 por força de sinal agora; (4) ressalvas perp × spot e quem lidera, Binance ou DEX.

**Resposta curta.** Dos 664 ativos-base da `markets` (200 perps monitorados + 21 spot monitorados + 801 não monitorados), **161 têm um token com o mesmo símbolo na lista verificada da Jupiter, mas 54 são homônimos falsos** (ADA, AVA, MASK, CLANKER, NEIRO, 1000SHIB… com preço 90–100 % diferente do da Binance) — a paridade de preço com a Binance é o filtro que separa, não o símbolo. Sobram **100 com o mesmo preço (± 3 %)**; 7 são stablecoins/LST (fora), 2 sem rota/erro (SONIC, MORPHO), 7 custam ≥ 1 % na ida-e-volta (MELANIA 2,98 %, SOON 9,75 %, ZORA 4,07 %, LAYER 3,96 %, S 1,97 %, WET 1,83 %, HUMA 1,02 %). **Ficam 90 mercados (84 perps + 6 só spot; 52 estão no radar de 200)**, em três classes: **nativos da Solana** (58: SOL, WIF, BONK, JUP, RAY, JTO, PYTH, ORCA, RENDER, W, TNSR, POPCAT, MEW, PUMP, TRUMP, FARTCOIN, PENGU, MET, KMNO, USELESS…), **ponte oficial Portal/Wormhole** (8: ETH, WBTC, BNB, SPX, AUDIO, AIXBT, BAT) e **"representações" recentes de mcap < 1 M** (24: DOGE, ARB, SUI, UNI, LINK, AVAX, AAVE, ENA, PEPE, INJ… — emissor não identificado, pools de 2026-04 a 2026-09, `devMints` = 20; o preço segue a Binance por arbitragem, mas a liquidez é de 40–660 k US$). Custo ida-e-volta em 0,02 SOL: mediana **0,20 %** (é a taxa das pools; Raydium AMM dá exatamente 0,50 %), 1–3 saltos. **HNT não está na `markets`** (sem par na Binance) — sai da lista do Everton.

**Lab agora (13:00 UTC):** regime global `SIDEWAYS` (0,75); 117 sinais em 24 h em 15 mercados, **todos `long`, todos `confidence = 0,50`** (momentum v3 = 51, mean_reversion v1–v14 = 63, mean_reversion_h1 = 3); 91 deles caem em 10 dos nossos 90 candidatos (ZEC 19, ARB 18, UNI 11, TAO 9, SUI/LINK/ETH/DOGE 6, SOL/BNB 5) — **nenhum sinal em token nativo da Solana** nas 24 h. Oportunidades abertas nos 90: 39 (max score 50,0 BNB; nenhuma `WATCHING`/`HOT` — o piso é 40 e só BNB 50,0 e ENA 45,8 passam, ambas `ANOMALY`).

**Top 3 por força de sinal agora** (composto: 35 % score da oportunidade se `long`, 20 % retorno 60 m, 15 % retorno 15 m, 10 % volume 60 m ÷ média horária, 20 % sinal `long` do Lab por recência, −10 × custo ida-e-volta):

| # | base | mint | símbolo Binance | preço | ret 15 m / 60 m | vol 60 m ÷ média h | último sinal do Lab | oportunidade | ida-e-volta Jupiter (0,02 / 1 / 5 SOL) |
|---|---|---|---|---:|---:|---:|---|---|---:|
| 1 | **MET** (Meteora, nativo, liq. 4,0 M US$) | `METvsvVRapdj9cFLzq4Tr43xK4tAjQfwX76z3n6mWQL` | METUSDT perp | 0,2727 US$ | **+2,21 % / +4,92 %** | **3,30×** | nenhum em 24 h | long · 39,2 · ANOMALY · DEVELOPING (momentum 8,9 + volume 10,0) | −0,01 % / 0,17 % / 0,47 % |
| 2 | **BNB** (Portal, liq. 198 k US$) | `9gP2kCy3wA1ctvYWQk75guqXuHfrEomqydHLtcTCqiLa` | BNBUSDT perp | 773,8 US$ | +0,62 % / +0,68 % | 1,10× | momentum v3 long há 3,8 h (5 em 24 h) | long · 32,6→50,0 · ANOMALY · DEVELOPING | 0,20 % / 0,37 % / 0,54 % |
| 3 | **DOGE** (representação, liq. 658 k US$, mcap Solana 870 k) | `DoGEV7LASBkQbibMc5k5vKnTZoMg423GpJ5QtJEGfm7R` | DOGEUSDT perp | 0,08898 US$ | +0,84 % / +0,67 % | 0,96× | **momentum v3 long há 0 h (13:00:02 UTC)** (6 em 24 h) | long · 28,6 · ANOMALY | 0,22 % / 0,22 % / 0,22 % |

Só com **nativos da Solana e liquidez ≥ 1 M US$** (o que eu compraria com 1–5 SOL sem pensar na ponte): **MET**, **KMNO** (Kamino: +0,69 % / +1,16 %, volume 60 m **9,8×** a média, sem oportunidade nem sinal, ida-e-volta 0,02 % mesmo com 5 SOL) e **RENDER** (+0,56 % / +1,75 %, 1,98×, oportunidade long 17,8, mas liquidez de só 215 k US$ na Solana — 0,48 % em 5 SOL); JELLYJELLY (8,3× volume) e ZEC (5,9 M US$ de liquidez, 8 sinais mean_reversion long há 1,8 h, preço −0,5 % em 60 m) ficam logo atrás.

**Ressalvas (§5).** (a) Todo sinal do Lab é de **perp** e só `long`; comprar spot na Solana perde funding (hoje +0,005–0,010 %/8 h — pagaríamos como long em perp, então spot é *melhor* nisso), não tem alavancagem nem stop na exchange (o stop vira uma venda pela Jupiter, com o mesmo 0,2–0,5 % de custo e a latência de pouso de 1,6 s mediana medida na R62), e o preço "spot" na DEX é a pool, não o índice. (b) **Amostra de 38 pontos (15 s) de WIF, 12:49–12:59 UTC**: a cotação Jupiter (2 USDC → WIF) ficou **+8,8 bp** acima do mid da Binance (mediana +7,9, min +0,5, max +20,8; é meia-taxa da pool + spread); a correlação dos retornos de 15 s é **0,63 contemporânea, 0,23 com a Binance 15 s à frente, 0,03 com a DEX à frente** — a Binance lidera, mas por **menos de 15 s** (entre 1 slot de 400 ms e 1 vela de 1 m não se resolve com esta amostra; a faixa do WIF foi só 23 bp nos 10 min, o que limita a leitura). Em outras palavras: quando a nossa vela 1 m `is_final` fecha na Binance, a pool da Solana já está lá; a vantagem de "ver na Binance e comprar na Solana" tem de vir do **sinal**, não da latência de preço.

## 1. Dados e cobertura

| item | valor |
|---|---|
| `markets` | 1 021 linhas (`q1.sql`): binance perp 528 (200 `is_monitored`), binance spot 493 (21 monitorados); 664 ativos-base distintos |
| lista verificada Jupiter | `GET https://lite-api.jup.ag/tokens/v2/tag?query=verified` → 3 476 tokens (o `tokens/v1/tagged/verified` da pergunta devolve **404** — foi desligado; o v2 traz `liquidity`, `mcap`, `usdPrice`, `holderCount`, `audit`, `stats24h`). 92 símbolos duplicados dentro da própria lista (ex.: TRUMP × MAGA (Wormhole), WEN meme × WEN ação tokenizada) — escolhi o de maior `liquidity` e excluí tags `stocks/rwa/xstocks/equities/prestocks` |
| casamento | por símbolo (case-insensitive), com os prefixos da Binance (`1000BONK` → BONK ×1000, `1000000MOG` → MOG); **validação por preço**: `usdPrice` Jupiter × multiplicador vs `ticker/price` Binance (perp; spot se não houver perp), 12:41 UTC — aceito se ‖Δ‖ ≤ 3 % |
| cotações | `GET https://lite-api.jup.ag/swap/v1/quote` (`slippageBps=50`), 0,02 SOL → token (`outAmount`) e `outAmount` → SOL; custo = 1 − SOL de volta ÷ 0,02; `priceImpactPct` e `routePlan` de cada perna; 12:42–12:47 UTC; 99 tokens, 2 erros (SONIC `NO_ROUTES_FOUND`; MORPHO 3 tentativas sem resposta na volta). Para SOL a ida-e-volta é SOL→USDC→SOL. Para os 10 primeiros repeti com 1 e 5 SOL (`quotes_big.json`) |
| Lab | `agent_signals` (24 h) × `strategy_versions` × `strategies` (`q3.sql`); `opportunities` abertas com `decomposition->'components'` (`q7.sql`); `candles_1m_2026_09` com `is_final`, últimas 24 h (`q2.sql`): preço = último fechamento final, ret 15/60 m contra o fechamento ≥ 15/60 min antes, volume = Σ `quote_volume` 60 min ÷ (Σ 24 h ÷ 24); regime e pesos ativos (`q5.sql`). Tudo `SELECT`, `statement_timeout = 60 s` |
| amostra de latência | `sample.py`: a cada 15 s, `fapi/v1/ticker/bookTicker WIFUSDT` (mid) e `quote` 2 USDC → WIF; 38 pontos, 12:49:30–12:58:45 UTC; latência HTTP 0,30–0,46 s Binance, 0,15–0,20 s Jupiter |
| onde está | os artefatos ficaram no scratchpad da sessão (`markets.tsv`, `verified.json`, `mapping_final.json`, `quotes.json`, `quotes_big.json`, `rank.json`, `sample_wif.json`, `q1–q7.sql`, `quote.py`, `sample.py`); o mapa completo está no §2 e no bloco JSON do §6 desta nota |

## 2. Mapa `binance_symbol → solana_mint` — os 90 que passam (paridade de preço + rota + custo < 1 %)

Tier de liquidez Jupiter: **A ≥ 1 M US$** (33), **B 100 k–1 M** (34), **C < 100 k** (23 — só para tamanhos de 0,02–0,2 SOL; com 1 SOL o impacto passa de 0,5 %). "Δ preço" = `usdPrice` Jupiter ÷ preço Binance − 1 às 12:41 UTC. Ordenado por liquidez.

| base | perp Binance | spot Binance | radar | mint | tipo | liq. Jupiter (US$) | mcap Solana (US$) | Δ preço Jup−Bin | ida-e-volta 0,02 SOL | saltos |
|---|---|---|---|---|---|---:|---:|---:|---:|---|
| SOL | SOLUSDT | SOLUSDT | sim | `So11111111111111111111111111111111111111112` | nativo | 892.241.412 | 65.579.995.168 | -0,06 % | -0,008 % | 1/1 |
| WBTC | — | WBTCUSDT | não | `3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh` | ponte (Portal/Wormhole) | 37.569.757 | 201.290.222 | -0,03 % | +0,013 % | 1/1 |
| PUMP | PUMPUSDT | PUMPUSDT | sim | `pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn` | nativo | 37.048.689 | 1.959.549.702 | +0,55 % | -0,020 % | 1/3 |
| TRUMP | TRUMPUSDT | TRUMPUSDT | sim | `6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN` | nativo | 33.303.910 | 561.252.550 | -0,01 % | +0,015 % | 2/3 |
| ETH | ETHUSDT | ETHUSDT | sim | `7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs` | ponte (Portal/Wormhole) | 23.113.927 | 113.397.743 | +0,06 % | -0,011 % | 2/1 |
| RAY | — | RAYUSDT | não | `4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R` | nativo | 17.887.853 | 488.315.409 | -0,06 % | -0,064 % | 3/1 |
| BOME | BOMEUSDT | BOMEUSDT | sim | `ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82` | nativo | 17.073.819 | 66.934.310 | -0,11 % | +0,066 % | 1/2 |
| ARC | ARCUSDT | — | não | `61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump` | nativo | 14.563.697 | 66.923.770 | -0,45 % | +0,299 % | 3/1 |
| MEW | MEWUSDT | — | não | `MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5` | nativo | 9.468.610 | 37.406.391 | -0,32 % | +0,499 % | 1/1 |
| WIF | WIFUSDT | WIFUSDT | sim | `EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm` | nativo | 6.475.681 | 212.973.752 | -0,18 % | +0,030 % | 2/1 |
| FARTCOIN | FARTCOINUSDT | — | sim | `9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump` | nativo | 6.230.340 | 161.362.233 | -0,14 % | -0,060 % | 1/2 |
| ZEC | ZECUSDT | ZECUSDT | sim | `A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS` | nativo | 5.852.605 | 157.226.715 | +0,09 % | -0,009 % | 2/3 |
| HYPE | HYPEUSDT | — | sim | `98sMhvDwXj1RQi5c5Mndm3vPe9cBqPrbLaufMXFNMh5g` | nativo | 5.637.051 | 65.628.126 | -0,05 % | -0,028 % | 2/2 |
| JUP | JUPUSDT | JUPUSDT | sim | `JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN` | nativo | 4.894.798 | 918.619.750 | +0,02 % | -0,035 % | 3/2 |
| TRX | TRXUSDT | TRXUSDT | sim | `GbbesPbaYh5uiAZSYNXTc7w9jty1rpg3P9L4JeN4LkKc` | nativo | 4.528.222 | 16.873.419 | -0,18 % | +0,002 % | 3/3 |
| POPCAT | POPCATUSDT | — | não | `7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr` | nativo | 4.517.436 | 48.672.590 | -0,12 % | +0,145 % | 1/1 |
| USELESS | USELESSUSDT | — | sim | `Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk` | nativo | 4.163.905 | 271.083.120 | -0,07 % | +0,105 % | 1/2 |
| MET | METUSDT | METUSDT | sim | `METvsvVRapdj9cFLzq4Tr43xK4tAjQfwX76z3n6mWQL` | nativo | 3.966.654 | 148.490.901 | +0,95 % | -0,008 % | 1/2 |
| PNUT | PNUTUSDT | PNUTUSDT | sim | `2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump` | nativo | 3.570.015 | 53.235.355 | +0,12 % | +0,500 % | 1/1 |
| SPX | SPXUSDT | — | sim | `J3NKxxXZcnNiMjKw9hYb2K4LUxgwB6t1FtPtQVsv3KFr` | ponte (Portal/Wormhole) | 3.063.768 | 40.669.539 | -0,20 % | +0,266 % | 2/1 |
| JELLYJELLY | JELLYJELLYUSDT | — | não | `FeR8VBqNRSUD5NtXAj2n3j1dAHkZHfyDktKuLXD4pump` | nativo | 2.686.256 | 57.664.101 | -0,40 % | +0,119 % | 1/1 |
| PENGU | PENGUUSDT | PENGUUSDT | sim | `2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv` | nativo | 2.462.435 | 610.287.257 | -0,13 % | -0,100 % | 2/3 |
| KMNO | KMNOUSDT | KMNOUSDT | não | `KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS` | nativo | 2.159.104 | 160.015.735 | +0,10 % | +0,024 % | 2/2 |
| PIPPIN | PIPPINUSDT | — | não | `Dfh5DzRgSvvCFDoYc2ciTkMrbDfRKybA4SoFbPmApump` | nativo | 2.071.112 | 18.121.379 | -0,37 % | +0,095 % | 2/2 |
| VIRTUAL | VIRTUALUSDT | VIRTUALUSDT | sim | `3iQL8BFS2vE7mww4ehAqQHAsbmRNCrPxizWAT2Zfyr9y` | nativo | 1.965.238 | 19.085.429 | -0,28 % | +0,465 % | 1/1 |
| GOAT | GOATUSDT | — | não | `CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump` | nativo | 1.675.203 | 16.824.239 | -0,45 % | +0,345 % | 1/1 |
| ZEREBRO | ZEREBROUSDT | — | não | `8x5VqbHA8D7NkD52uNuS5nnt3PwA8pLD34ymskeSo2Wn` | nativo | 1.586.054 | 32.062.784 | -0,16 % | +0,500 % | 1/1 |
| ALCH | ALCHUSDT | — | não | `HNg5PYJmtqcmzXrv6S9zP1CDKk5BgDuyFBxbvNApump` | nativo | 1.546.922 | 41.039.375 | -0,14 % | +0,500 % | 1/1 |
| BAN | BANUSDT | — | não | `9PR7nCP9DpcUotnDPVLUBUZKu5WAYkwrCUx9wDnSpump` | nativo | 1.492.003 | 64.984.254 | -0,41 % | +0,500 % | 1/1 |
| MOODENG | MOODENGUSDT | — | sim | `ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY` | nativo | 1.467.197 | 45.153.251 | -0,04 % | +0,500 % | 1/1 |
| 1000BONK | 1000BONKUSDT | — | sim | `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` | nativo | 1.396.700 | 265.179.523 | -0,08 % | +0,100 % | 1/1 |
| BONK | — | BONKUSDT | não | `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` | nativo | 1.396.700 | 265.179.523 | -0,21 % | +0,103 % | 1/2 |
| BIRB | BIRBUSDT | — | não | `G7vQWurMkMMm2dU3iZpXYFTHT9Biio4F4gZCrwFpKNwG` | nativo | 1.251.653 | 18.613.502 | +0,11 % | +0,024 % | 2/3 |
| GRIFFAIN | GRIFFAINUSDT | — | não | `KENJSUYLASHUMfHyy5o4Hp2FdNqZg1AsUPhfH2kYvEP` | nativo | 973.945 | 14.461.720 | -0,37 % | +0,500 % | 1/1 |
| CHILLGUY | CHILLGUYUSDT | — | sim | `Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump` | nativo | 835.488 | 14.686.997 | -0,19 % | +0,500 % | 1/1 |
| SWARMS | SWARMSUSDT | — | não | `74SBV4zDXxTRgv1pEMoECskKBkZHc2yGPnc7GYVepump` | nativo | 775.512 | 8.041.119 | -0,09 % | +0,500 % | 1/1 |
| ACT | ACTUSDT | ACTUSDT | não | `GJAFwWjJ3vnTsrQVabjBVK2TYB1YtRCQXRDfDgUnpump` | nativo | 755.486 | 10.001.577 | +0,01 % | +0,044 % | 1/2 |
| SKR | SKRUSDT | — | sim | `SKRbvo6Gf7GondiT3BbTfuRDPqLWei4j2Qy2NPGZhW3` | nativo | 710.757 | 136.900.579 | +0,16 % | +0,200 % | 1/1 |
| XMR | XMRUSDT | — | sim | `WXMRyRZhsa19ety5erZhHg4N3xj3EVN92u94422teJp` | nativo | 706.659 | 1.295.094 | -0,50 % | +0,092 % | 1/2 |
| 1000PEPE | 1000PEPEUSDT | — | sim | `PEPEqnuuCDbBC89p1u9vpnP1KQ2oj1xTcQBsjt9X55m` | representação (mcap < 1 M) | 682.888 | 840.426 | +0,51 % | +0,112 % | 3/1 |
| PEPE | — | PEPEUSDT | não | `PEPEqnuuCDbBC89p1u9vpnP1KQ2oj1xTcQBsjt9X55m` | representação (mcap < 1 M) | 682.888 | 840.426 | +0,41 % | +0,115 % | 2/1 |
| DOGE | DOGEUSDT | DOGEUSDT | sim | `DoGEV7LASBkQbibMc5k5vKnTZoMg423GpJ5QtJEGfm7R` | representação (mcap < 1 M) | 658.314 | 870.231 | +0,34 % | +0,220 % | 3/3 |
| LIT | LITUSDT | — | sim | `EicWvteVi2fWepEzS3FYWsnuPoP6caZfjnKqNvydLjCH` | nativo | 611.445 | 3.724.143 | -0,26 % | +0,093 % | 2/2 |
| TAO | TAOUSDT | TAOUSDT | sim | `taoC6xyv2v8tDLcev4uaGUgV4vdQsWJrGft2kcBRrBY` | nativo | 525.855 | 2.296.419 | -0,16 % | +0,264 % | 2/1 |
| ARX | ARXUSDT | — | sim | `ARXwZkNAtzPfdcoqQiduJn8EPv9fKiDfGn2KyggyDrFs` | nativo | 470.012 | 42.329.976 | -0,54 % | +0,407 % | 2/2 |
| AUDIO | — | AUDIOUSDT | não | `9LzCMqDgTKYz9Drzqnpgee3SGa89up3a247ypMj2xrqM` | ponte (Portal/Wormhole) | 454.562 | 614.835 | -0,49 % | +0,066 % | 1/3 |
| PYTH | PYTHUSDT | PYTHUSDT | sim | `HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3` | nativo | 409.809 | 477.606.310 | +0,08 % | +0,027 % | 1/2 |
| DOOD | DOODUSDT | — | não | `DvjbEsdca43oQcw2h3HW1CT7N3x5vRcr3QrvTUHnXvgV` | nativo | 341.033 | 17.847.914 | -0,57 % | +0,492 % | 2/3 |
| JTO | JTOUSDT | JTOUSDT | sim | `jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL` | nativo | 330.199 | 239.854.074 | +0,20 % | +0,426 % | 3/3 |
| 2Z | 2ZUSDT | 2ZUSDT | não | `J6pQQ3FAcJQeWPPGppWRb4nM8jU3wLyYbRrLh7feMfvd` | nativo | 321.012 | 174.499.420 | +0,15 % | +0,015 % | 2/2 |
| UNI | UNIUSDT | UNIUSDT | sim | `uniHfuPhEQSrtpzXpJZDCSq53yaejKKpNhFUiKoHKHV` | representação (mcap < 1 M) | 310.102 | 604.039 | -0,63 % | +0,353 % | 2/2 |
| INJ | INJUSDT | INJUSDT | sim | `1NJMqVM4PadjuzYmeB7zV7q7DV8oB3ExaQCd9x6KsLz` | representação (mcap < 1 M) | 294.770 | 630.253 | -0,01 % | +0,350 % | 2/3 |
| ARB | ARBUSDT | ARBUSDT | sim | `ARBzQTYDCW2KnVEjs1Mc81LekB1ibVFZKbSVmorkoT9d` | representação (mcap < 1 M) | 242.283 | 306.654 | +0,98 % | +0,083 % | 3/2 |
| RENDER | RENDERUSDT | RENDERUSDT | sim | `rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof` | nativo | 215.119 | 783.062.390 | -0,27 % | +0,175 % | 2/1 |
| ORCA | ORCAUSDT | ORCAUSDT | não | `orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE` | nativo | 208.746 | 88.171.565 | -0,05 % | +0,212 % | 1/2 |
| BNB | BNBUSDT | BNBUSDT | sim | `9gP2kCy3wA1ctvYWQk75guqXuHfrEomqydHLtcTCqiLa` | ponte (Portal/Wormhole) | 198.037 | 973.304 | -0,09 % | +0,205 % | 2/1 |
| LINK | LINKUSDT | LINKUSDT | sim | `LinkhB3afbBKb2EQQu7s7umdZceV3wcvAUJhQAfQ23L` | representação (mcap < 1 M) | 194.255 | 375.794 | +0,02 % | -0,162 % | 3/3 |
| ME | MEUSDT | MEUSDT | não | `MEFNBXixkEbait3xn9bkm8WsJzXtVsaJEn4c8Sam21u` | nativo | 168.436 | 42.808.324 | -0,09 % | +0,104 % | 2/2 |
| BIO | BIOUSDT | BIOUSDT | sim | `bioJ9JTqW62MLz7UKHU69gtKhPpGi1BQhccj2kmSvUJ` | nativo | 160.696 | 5.186.486 | +0,53 % | -0,021 % | 1/2 |
| MON | MONUSDT | — | sim | `CrAr4RRJMBVwRsZtT62pEhfA9H5utymC2mVx8e7FreP2` | nativo | 156.608 | 1.263.968 | +0,07 % | +0,270 % | 1/1 |
| BMT | BMTUSDT | BMTUSDT | não | `FQgtfugBdpFN7PZ6NdPrZpVLDBrPGxXesi4gVu3vErhY` | nativo | 149.730 | 10.133.335 | +0,12 % | +0,522 % | 2/3 |
| PONS | PONSUSDT | — | sim | `poNSfquKq512ApeYjVghwViSun4x1MhCqHVH2Paq4jN` | nativo | 132.548 | 1.115.287 | -0,78 % | +0,146 % | 2/2 |
| W | WUSDT | WUSDT | sim | `85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ` | nativo | 125.757 | 71.453.006 | -0,40 % | +0,513 % | 1/3 |
| FLUID | FLUIDUSDT | — | não | `DuEy8wWrzCUun5ZbbG9hkVqXqqicpTQw8gB7nEAzpCHQ` | representação (mcap < 1 M) | 118.945 | 588.226 | -0,97 % | +0,599 % | 1/1 |
| AAVE | AAVEUSDT | AAVEUSDT | sim | `AavE1kKKnesPw4MuRJmJ9jZs9QzEE8CPxQ3ViczUDfc1` | representação (mcap < 1 M) | 108.344 | 507.283 | +0,30 % | +0,029 % | 2/2 |
| SLX | SLXUSDT | — | não | `SLXdx4BUt2v9uJQNzWqSfzTJ9UKLUDsvxHFMEEdrfgq` | nativo | 104.597 | 65.801.623 | -0,48 % | +0,038 % | 3/3 |
| CHIP | CHIPUSDT | CHIPUSDT | sim | `chipCAT7vi5CZtbZsn9z7iMPXvFwyAnKz3QFu8XVuHm` | representação (mcap < 1 M) | 100.035 | 533.968 | -0,45 % | +0,088 % | 3/3 |
| ENA | ENAUSDT | ENAUSDT | sim | `72QvBVwpxqmheEPfaCwWSWqEFsUy3rhWt6JhQBMNTwD1` | representação (mcap < 1 M) | 75.551 | 250.489 | +0,27 % | +0,515 % | 3/3 |
| SUI | SUIUSDT | SUIUSDT | sim | `suifhC9gU1VbJAPYPTBkHJyyyStKGLLYPVDTmPoqbvA` | representação (mcap < 1 M) | 74.790 | 737.312 | -0,19 % | +0,175 % | 3/1 |
| AIXBT | AIXBTUSDT | AIXBTUSDT | não | `14zP2ToQ79XWvc7FQpm4bRnp9d6Mp1rFfsUW3gpLcRX` | ponte (Portal/Wormhole) | 69.456 | 272.069 | +0,36 % | +0,508 % | 1/1 |
| DRIFT | DRIFTUSDT | — | sim | `DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7` | nativo | 68.014 | 11.232.040 | -0,23 % | +0,383 % | 1/3 |
| AVAX | AVAXUSDT | AVAXUSDT | sim | `avaxGHCq3T7hoxd73oY2KY9hJSTaeMibXvHy5KNzh5D` | representação (mcap < 1 M) | 62.513 | 150.281 | +0,02 % | +0,469 % | 3/3 |
| CAKE | CAKEUSDT | CAKEUSDT | sim | `4qQeZ5LwSz6HuupUu8jCtgXyW1mYQcNbFAW1sWZp89HL` | representação (mcap < 1 M) | 61.979 | 379.174 | -0,26 % | +0,091 % | 1/3 |
| BILL | BILLUSDT | — | não | `Bi11Je4MH3PpyCNiuTAepRbsA5U6DK3DJy79ZFthddX` | representação (mcap < 1 M) | 58.391 | 66.234 | -0,81 % | +0,584 % | 3/3 |
| GRASS | GRASSUSDT | — | sim | `Grass7B4RdKfBCjTKgSqnXkqjwiGvQyFbuSCUJr3XXjs` | nativo | 55.789 | 344.982.218 | -0,00 % | +0,484 % | 1/1 |
| STRK | STRKUSDT | STRKUSDT | sim | `HsRpHQn6VbyMs5b5j5SV6xQ2VvpvvCCzu19GjytVSCoz` | representação (mcap < 1 M) | 49.227 | 685.407 | -1,22 % | +0,400 % | 1/3 |
| TNSR | TNSRUSDT | TNSRUSDT | não | `TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6` | nativo | 47.946 | 26.974.204 | +0,08 % | +0,341 % | 3/2 |
| CHZ | CHZUSDT | CHZUSDT | sim | `6eftxVbSAunVEoxUWdGhPdxg5UdsJ8Wkwy5w5YFuxouw` | representação (mcap < 1 M) | 45.128 | 218.629 | -0,19 % | +0,483 % | 3/2 |
| IO | IOUSDT | IOUSDT | não | `BZLbGTNCSFfoth2GYDtwr7e4imWzpR5jqcUuGEwr646K` | nativo | 42.890 | 56.511.121 | -0,49 % | +0,474 % | 3/3 |
| MEGA | MEGAUSDT | MEGAUSDT | sim | `megaA5QDK1qLXtjpvg9oCFMvxT9d5BCMrVTBddnM5kV` | representação (mcap < 1 M) | 42.123 | 71.874 | -1,87 % | +0,467 % | 3/3 |
| WLFI | WLFIUSDT | WLFIUSDT | sim | `WLFinEv6ypjkczcS83FZqFpgFZYwQXutRbxGe7oC16g` | nativo | 37.937 | 46.011.729 | -0,67 % | +0,873 % | 1/3 |
| PSG | — | PSGUSDT | não | `5eyib4qghYGHNh7VvxSFGYLFJSanjq9hug9fR52kksnm` | representação (mcap < 1 M) | 29.801 | 300.526 | -1,00 % | +0,580 % | 3/2 |
| 1000CAT | 1000CATUSDT | 1000CATUSDT | não | `3joMReCCSESngJEpFLoKR2dNcChjSRCDtybQet5uSpse` | representação (mcap < 1 M) | 19.576 | 119.713 | +0,31 % | +0,522 % | 1/1 |
| APE | APEUSDT | APEUSDT | não | `C1MHyoTJpRTeS9AQCyspNVu2EWAYCZwmJ1jNkEArFP1f` | representação (mcap < 1 M) | 15.416 | 57.092 | +0,21 % | +0,091 % | 1/1 |
| BAT | BATUSDT | BATUSDT | não | `EPeUFDgHRxs9xxEPVaL6kfGQvCon7jmAWKVUHuux1Tpz` | ponte (Portal/Wormhole) | 11.781 | 143.266 | -1,51 % | +0,818 % | 2/1 |
| GALA | GALAUSDT | GALAUSDT | sim | `eEUiUs4JWYZrp72djAGF1A8PhpR6rHphGeGN7GbVLp6` | representação (mcap < 1 M) | 11.748 | 143.057 | -0,19 % | +0,515 % | 1/1 |
| WCT | WCTUSDT | WCTUSDT | não | `WCTk5xWdn5SYg56twGj32sUF3W4WFQ48ogezLBuYTBY` | representação (mcap < 1 M) | 9.711 | 556.307 | +0,54 % | +0,699 % | 1/1 |
| PRL | PRLUSDT | — | não | `PERLEQKUNUp1dgFZ8EvyXHdN9d6ZQqfGxALDvfs6pDs` | nativo | 6.772 | 119.875.726 | +0,57 % | +0,257 % | 3/2 |
| DYM | DYMUSDT | DYMUSDT | não | `AjnUVPffPT91gBS7KADzXgpdTPFrjJURHrKWAa1fQbHH` | representação (mcap < 1 M) | 2.481 | 12.147 | -2,07 % | +0,682 % | 2/2 |
| GMT | GMTUSDT | GMTUSDT | não | `7i5KKsX2weiTkry7jA4ZwSuXGhs5eJBEjY8vVxR4pfRx` | nativo | 2.367 | 12.305.040 | -0,77 % | +0,512 % | 3/2 |

## 2a. Mesa spot/1 — os 52 mercados monitorados pelo Lab com execução na Jupiter (ida-e-volta de 0,05 SOL, 13:10–13:12 UTC)

Endereços: lista verificada da Jupiter (`tokens/v2/tag?query=verified`, 12:40 UTC), confirmados por paridade de preço com a Binance (Δ ≤ 3 %). **ENA passa de 1 % em 0,05 SOL** (ponte fina) — cai da mesa. Tier: A ≥ 1 M US$ de liquidez, B 100 k–1 M, C < 100 k. "nativo" = token emitido na Solana com o mesmo preço da Binance; **ZEC, XMR, TRX, HYPE, TAO, LIT, BNB, ETH não têm cadeia-mãe na Solana** — são emissões de terceiros ou Portal, com paridade mantida por arbitragem (o rótulo "nativo" nesses casos vem só da ausência de "Wormhole/Portal" no nome).

| símbolo Binance | rank | base | mint (verificado) | tipo | tier | liq. Jupiter (US$) | ida-e-volta 0,05 SOL | impacto compra/venda | saltos | rota (compra) | sinais 24 h | oportunidade |
|---|---:|---|---|---|---|---:|---:|---:|---|---|---:|---|
| ETHUSDT | 2 | ETH | `7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs` | ponte Portal/Wormhole | A | 23.113.927 | **-0,004 %** | +0,00 / +0,02 % | 3/2 | PancakeSwap + AlphaQ + GoonFi V2 | 6 | — |
| ZECUSDT | 3 | ZEC | `A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS` | nativo | A | 5.852.605 | **+0,050 %** | +0,32 / +0,13 % | 2/2 | 1DEX + Byreal | 19 | — |
| SOLUSDT | 4 | SOL | `So11111111111111111111111111111111111111112` | nativo | A | 892.241.412 | **-0,000 %** | +0,01 / +0,00 % | 1/1 | HumidiFi | 5 | — |
| HYPEUSDT | 8 | HYPE | `98sMhvDwXj1RQi5c5Mndm3vPe9cBqPrbLaufMXFNMh5g` | nativo | A | 5.637.051 | **-0,005 %** | +0,00 / +0,00 % | 1/2 | PancakeSwap | 0 | — |
| UNIUSDT | 9 | UNI | `uniHfuPhEQSrtpzXpJZDCSq53yaejKKpNhFUiKoHKHV` | representação (mcap < 1 M) | B | 310.102 | **+0,193 %** | +0,20 / +0,01 % | 3/2 | Raydium CLMM + ZeroFi + Denali | 11 | short 29 ANOMALY |
| BNBUSDT | 10 | BNB | `9gP2kCy3wA1ctvYWQk75guqXuHfrEomqydHLtcTCqiLa` | ponte Portal/Wormhole | B | 198.037 | **+0,254 %** | +0,18 / +0,08 % | 1/2 | Whirlpool | 5 | long 33 ANOMALY |
| DOGEUSDT | 11 | DOGE | `DoGEV7LASBkQbibMc5k5vKnTZoMg423GpJ5QtJEGfm7R` | representação (mcap < 1 M) | B | 658.314 | **+0,140 %** | +0,16 / +0,00 % | 2/1 | Quantum + Manifest | 6 | long 29 ANOMALY |
| SUIUSDT | 11 | SUI | `suifhC9gU1VbJAPYPTBkHJyyyStKGLLYPVDTmPoqbvA` | representação (mcap < 1 M) | C | 74.790 | **+0,198 %** | +0,02 / +0,18 % | 1/2 | Whirlpool | 6 | long 18 NORMAL |
| ENAUSDT | 13 | ENA | `72QvBVwpxqmheEPfaCwWSWqEFsUy3rhWt6JhQBMNTwD1` | representação (mcap < 1 M) | C | 75.551 | **+1,018 %** | +0,53 / +0,49 % | 3/2 | Raydium CLMM + ZeroFi + Meteora DLMM | 0 | short 23 ANOMALY |
| AVAXUSDT | 15 | AVAX | `avaxGHCq3T7hoxd73oY2KY9hJSTaeMibXvHy5KNzh5D` | representação (mcap < 1 M) | C | 62.513 | **+0,398 %** | +0,25 / +0,15 % | 3/2 | Whirlpool + TesseraV + Meteora DLMM | 0 | long 28 ANOMALY |
| ARBUSDT | 17 | ARB | `ARBzQTYDCW2KnVEjs1Mc81LekB1ibVFZKbSVmorkoT9d` | representação (mcap < 1 M) | B | 242.283 | **+0,372 %** | +1,11 / +0,00 % | 3/2 | Raydium CLMM + DefiTuna + Raydium CLMM | 18 | long 22 NORMAL |
| 1000PEPEUSDT | 19 | 1000PEPE | `PEPEqnuuCDbBC89p1u9vpnP1KQ2oj1xTcQBsjt9X55m` | representação (mcap < 1 M) | B | 682.888 | **+0,342 %** | +0,23 / +0,10 % | 2/1 | Byreal + Manifest | 0 | long 21 NORMAL |
| TAOUSDT | 26 | TAO | `taoC6xyv2v8tDLcev4uaGUgV4vdQsWJrGft2kcBRrBY` | nativo | B | 525.855 | **+0,236 %** | +0,24 / +0,00 % | 2/2 | Whirlpool + Scorch | 9 | short 10 NORMAL |
| LINKUSDT | 27 | LINK | `LinkhB3afbBKb2EQQu7s7umdZceV3wcvAUJhQAfQ23L` | representação (mcap < 1 M) | B | 194.255 | **+0,319 %** | +0,33 / +0,00 % | 2/2 | GoonFi V2 + Denali | 6 | neutral 18 ANOMALY |
| STRKUSDT | 28 | STRK | `HsRpHQn6VbyMs5b5j5SV6xQ2VvpvvCCzu19GjytVSCoz` | representação (mcap < 1 M) | C | 49.227 | **+0,486 %** | +0,23 / +0,24 % | 1/1 | Meteora DLMM | 0 | short 24 ANOMALY |
| AAVEUSDT | 30 | AAVE | `AavE1kKKnesPw4MuRJmJ9jZs9QzEE8CPxQ3ViczUDfc1` | representação (mcap < 1 M) | B | 108.344 | **+0,135 %** | +0,14 / +0,00 % | 3/2 | Whirlpool + ZeroFi + Denali | 0 | neutral 16 ANOMALY |
| XMRUSDT | 35 | XMR | `WXMRyRZhsa19ety5erZhHg4N3xj3EVN92u94422teJp` | nativo | B | 706.659 | **+0,153 %** | +0,28 / +0,00 % | 1/2 | Meteora DLMM | 0 | neutral 15 NORMAL |
| PUMPUSDT | 36 | PUMP | `pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn` | nativo | A | 37.048.689 | **+0,035 %** | +0,22 / +0,00 % | 1/2 | Meteora DLMM | 0 | — |
| INJUSDT | 38 | INJ | `1NJMqVM4PadjuzYmeB7zV7q7DV8oB3ExaQCd9x6KsLz` | representação (mcap < 1 M) | B | 294.770 | **+0,251 %** | +0,00 / +0,29 % | 3/3 | Scorch + ZeroFi + Denali | 0 | neutral 18 ANOMALY |
| TRUMPUSDT | 39 | TRUMP | `6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN` | nativo | A | 33.303.910 | **+0,051 %** | +0,06 / +0,00 % | 1/2 | Scorch | 0 | neutral 11 ANOMALY |
| PONSUSDT | 43 | PONS | `poNSfquKq512ApeYjVghwViSun4x1MhCqHVH2Paq4jN` | nativo | B | 132.548 | **+0,021 %** | +0,00 / +0,06 % | 3/2 | Raydium CLMM + ZeroFi + Denali | 0 | short 12 ANOMALY |
| LITUSDT | 44 | LIT | `EicWvteVi2fWepEzS3FYWsnuPoP6caZfjnKqNvydLjCH` | nativo | B | 611.445 | **+0,135 %** | +0,00 / +1,31 % | 1/2 | Scorch | 0 | short 19 NORMAL |
| USELESSUSDT | 46 | USELESS | `Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk` | nativo | A | 4.163.905 | **+0,109 %** | +0,00 / +0,24 % | 3/2 | Raydium CLMM + Scorch + HumidiFi | 0 | short 12 ANOMALY |
| PENGUUSDT | 54 | PENGU | `2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv` | nativo | A | 2.462.435 | **+0,005 %** | +0,00 / +0,13 % | 3/2 | Raydium CLMM + DefiTuna + HumidiFi | 0 | — |
| TRXUSDT | 66 | TRX | `GbbesPbaYh5uiAZSYNXTc7w9jty1rpg3P9L4JeN4LkKc` | nativo | A | 4.528.222 | **-0,012 %** | +0,00 / +0,00 % | 3/2 | Meteora DLMM + Meteora DLMM + GoonFi V2 | 0 | long 21 ANOMALY |
| JUPUSDT | 76 | JUP | `JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN` | nativo | A | 4.894.798 | **+0,027 %** | +0,00 / +0,08 % | 1/2 | Whirlpool | 0 | long 18 ANOMALY |
| FARTCOINUSDT | 79 | FARTCOIN | `9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump` | nativo | A | 6.230.340 | **+0,047 %** | +0,03 / +0,09 % | 2/1 | 1DEX + HumidiFi | 0 | — |
| WIFUSDT | 82 | WIF | `EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm` | nativo | A | 6.475.681 | **+0,082 %** | +0,06 / +0,03 % | 1/1 | Whirlpool | 0 | — |
| 1000BONKUSDT | 86 | 1000BONK | `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` | nativo | A | 1.396.700 | **-0,003 %** | +0,00 / +0,10 % | 1/3 | Whirlpool | 0 | neutral 18 NORMAL |
| JTOUSDT | 87 | JTO | `jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL` | nativo | B | 330.199 | **+0,010 %** | +0,22 / +0,00 % | 3/3 | Whirlpool + Bonkswap + TesseraV | 0 | short 12 NORMAL |
| VIRTUALUSDT | 93 | VIRTUAL | `3iQL8BFS2vE7mww4ehAqQHAsbmRNCrPxizWAT2Zfyr9y` | nativo | A | 1.965.238 | **+0,601 %** | +0,43 / +0,17 % | 1/1 | Meteora | 0 | neutral 8 NORMAL |
| RENDERUSDT | 94 | RENDER | `rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof` | nativo | B | 215.119 | **+0,095 %** | +0,09 / +0,00 % | 1/2 | PancakeSwap | 0 | long 18 NORMAL |
| CHIPUSDT | 97 | CHIP | `chipCAT7vi5CZtbZsn9z7iMPXvFwyAnKz3QFu8XVuHm` | representação (mcap < 1 M) | B | 100.035 | **+0,025 %** | +0,00 / +0,19 % | 3/2 | Mercurial + Raydium + Denali | 0 | short 21 ANOMALY |
| CAKEUSDT | 100 | CAKE | `4qQeZ5LwSz6HuupUu8jCtgXyW1mYQcNbFAW1sWZp89HL` | representação (mcap < 1 M) | C | 61.979 | **+0,038 %** | +0,00 / +0,00 % | 1/3 | PancakeSwap | 0 | long 16 NORMAL |
| WLFIUSDT | 110 | WLFI | `WLFinEv6ypjkczcS83FZqFpgFZYwQXutRbxGe7oC16g` | nativo | C | 37.937 | **+0,593 %** | +0,11 / +0,48 % | 1/2 | Raydium CLMM | 0 | — |
| MONUSDT | 116 | MON | `CrAr4RRJMBVwRsZtT62pEhfA9H5utymC2mVx8e7FreP2` | nativo | B | 156.608 | **+0,027 %** | +0,22 / +0,00 % | 2/2 | Whirlpool + Denali | 0 | — |
| GALAUSDT | 119 | GALA | `eEUiUs4JWYZrp72djAGF1A8PhpR6rHphGeGN7GbVLp6` | representação (mcap < 1 M) | C | 11.748 | **+0,539 %** | +0,31 / +0,23 % | 1/1 | Raydium CLMM | 0 | long 13 NORMAL |
| METUSDT | 125 | MET | `METvsvVRapdj9cFLzq4Tr43xK4tAjQfwX76z3n6mWQL` | nativo | A | 3.966.654 | **+0,039 %** | +0,00 / +0,10 % | 3/2 | Raydium CLMM + ZeroFi + Meteora DLMM | 0 | long 39 ANOMALY |
| BOMEUSDT | 127 | BOME | `ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82` | nativo | A | 17.073.819 | **+0,088 %** | +0,28 / +0,00 % | 1/2 | Scorch | 0 | short 5 NORMAL |
| DRIFTUSDT | 128 | DRIFT | `DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7` | nativo | C | 68.014 | **+0,185 %** | +0,00 / +0,84 % | 3/1 | Meteora DLMM + Whirlpool + Raydium CLMM | 0 | — |
| PYTHUSDT | 134 | PYTH | `HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3` | nativo | B | 409.809 | **+0,101 %** | +0,02 / +0,08 % | 1/1 | Whirlpool | 0 | long 23 ANOMALY |
| WUSDT | 137 | W | `85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ` | nativo | B | 125.757 | **+0,007 %** | +0,00 / +0,02 % | 3/2 | Whirlpool + Whirlpool + Whirlpool | 0 | — |
| SPXUSDT | 150 | SPX | `J3NKxxXZcnNiMjKw9hYb2K4LUxgwB6t1FtPtQVsv3KFr` | ponte Portal/Wormhole | A | 3.063.768 | **+0,389 %** | +0,00 / +0,52 % | 1/1 | Whirlpool | 0 | short 13 ANOMALY |
| ARXUSDT | 163 | ARX | `ARXwZkNAtzPfdcoqQiduJn8EPv9fKiDfGn2KyggyDrFs` | nativo | B | 470.012 | **+0,458 %** | +0,36 / +0,03 % | 3/3 | Whirlpool + ZeroFi + Byreal | 0 | short 19 ANOMALY |
| MEGAUSDT | 175 | MEGA | `megaA5QDK1qLXtjpvg9oCFMvxT9d5BCMrVTBddnM5kV` | representação (mcap < 1 M) | C | 42.123 | **+0,486 %** | +0,59 / +0,00 % | 2/2 | GoonFi V2 + Meteora DLMM | 0 | neutral 5 NORMAL |
| CHZUSDT | 178 | CHZ | `6eftxVbSAunVEoxUWdGhPdxg5UdsJ8Wkwy5w5YFuxouw` | representação (mcap < 1 M) | C | 45.128 | **+0,491 %** | +0,21 / +0,28 % | 2/2 | GoonFi V2 + Meteora DLMM | 0 | — |
| SKRUSDT | 187 | SKR | `SKRbvo6Gf7GondiT3BbTfuRDPqLWei4j2Qy2NPGZhW3` | nativo | B | 710.757 | **+0,125 %** | +0,06 / +0,07 % | 2/2 | Whirlpool + HumidiFi | 0 | neutral 21 ANOMALY |
| PNUTUSDT | 193 | PNUT | `2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump` | nativo | A | 3.570.015 | **+0,500 %** | +0,40 / +0,12 % | 1/1 | Raydium | 0 | neutral 16 ANOMALY |
| MOODENGUSDT | 195 | MOODENG | `ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY` | nativo | A | 1.467.197 | **+0,500 %** | +0,36 / +0,14 % | 1/1 | Raydium | 0 | neutral 16 ANOMALY |
| BIOUSDT | 196 | BIO | `bioJ9JTqW62MLz7UKHU69gtKhPpGi1BQhccj2kmSvUJ` | nativo | B | 160.696 | **+0,149 %** | +0,34 / +0,00 % | 1/2 | Raydium CLMM | 0 | short 11 NORMAL |
| CHILLGUYUSDT | 198 | CHILLGUY | `Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump` | nativo | B | 835.488 | **+0,501 %** | +0,63 / +0,00 % | 1/1 | Raydium | 0 | — |
| GRASSUSDT | 199 | GRASS | `Grass7B4RdKfBCjTKgSqnXkqjwiGvQyFbuSCUJr3XXjs` | nativo | C | 55.789 | **+0,592 %** | +0,30 / +0,30 % | 1/1 | Whirlpool | 0 | — |

Custo mediano em 0,05 SOL: **0,14 %**; 41 de 52 abaixo de 0,4 %; acima de 0,5 %: ENA 1,02, VIRTUAL 0,60, WLFI 0,59, GRASS 0,59, GALA 0,54, CHILLGUY/PNUT/MOODENG 0,50 (Raydium AMM 0,25 % por perna).


**Excluídos, para registro.** *Homônimos falsos (54)*: AVA, SC, RIF, NEIRO, MASK, STAR, FIGHT, FOGO, LUNA, CLANKER, 1000SHIB/SHIB, RAD, MIRA, PIXEL, AI, ALL, CC, ADA, G, STABLE, ACE, BTW, BRETT, NOM, IQ, ALT, MANA, HYPER, BABY, 1000CHEEMS, HOLO, ARIA, 1000000MOG, UAI, NEO, LYN, ANIME, GAS, ROSE, REZ, TURTLE, DODO, HOME, ASTR, GRAM, COW, IN, SUPER, PLAY, DYDX, ADX, LIGHT, PORTAL (Δ preço de −52 % a +42 000 %). *Custo ≥ 1 %*: MELANIA 2,98 %, SOON 9,75 %, ZORA 4,07 %, LAYER 3,96 %, S 1,97 %, WET 1,83 %, HUMA 1,02 %. *Sem rota*: SONIC. *Erro*: MORPHO. *Fora de escopo*: USDC, USD1, USDE, USDS, FDUSD, USDP, BNSOL. *Sem par na Binance*: HNT (não está na `markets`); TNSR e MEW estão (perps não monitorados). *Não casaram por símbolo* (503 ativos): BTC (na Solana é WBTC/cbBTC — o WBTC spot casou), XRP, LTC, DOT, etc. — só existem como ponte sem liquidez ou não existem.

## 3. Estado do Lab nos 90 (velas até 12:59 UTC; sinais e oportunidades às 13:00 UTC)

Regime global `SIDEWAYS` 0,75 desde 12:31 UTC. Pesos `opportunity_weights v2`: volume 0,20, momentum 0,20, order_flow 0,15, liquidity 0,10, derivatives 0,10, market_regime 0,10, anomalies 0,05 (agent_consensus e external_intelligence 0). Só 56 dos 90 têm velas 1 m (os 52 monitorados + spot de ETH/SOL/BNB/…); os 34 perps não monitorados (RAY, POPCAT, MEW, TNSR, ME, GOAT, ZEREBRO, ALCH, BAN, MELANIA…) **não têm dado nenhum no banco** — o radar não os olha.

**Sinais 24 h (`agent_signals`, 13:00 UTC anterior → 13:00 UTC):** 117 no total em 15 mercados; nos candidatos: ZEC 19, ARB 18, UNI 11, TAO 9, SUI 6, LINK 6, ETH 6, DOGE 6, SOL 5, BNB 5. Estratégias: `momentum v3` (rompimento 15 m: fechamento acima da máxima dos 20 anteriores) 51, `mean_reversion v1/v2/v3/v6/v7/v8/v10/v14` (15 m, fechamento a −1,5…−2,5 desvios da média de 20) 63, `mean_reversion_h1 v1` 3. **Todos `long`, todos `confidence 0,5000`, todos `status = active`, nenhum ligado a uma `opportunity_id`.** Os mais recentes: ARB mean_reversion_h1 13:00:04, DOGE momentum v3 13:00:02, ZEC mean_reversion ×8 versões 11:15, DOGE momentum 10:45, LINK/TAO momentum 10:30, DOGE mean_reversion_h1 10:00, SUI momentum 10:00, BNB/TAO momentum 09:15.

**Ranking completo (56 com velas):**

| # | base | mercado | tier | preço (1 m final) | ret 15 m | ret 60 m | vol 60 m / média h 24 h | oportunidade (dir · score · status) | último sinal do Lab (24 h) | ida-e-volta 0,02 SOL | força |
|---:|---|---|---|---:|---:|---:|---:|---|---|---:|---:|
| 1 | MET | METUSDT perp | A | 0,2727 | +2,21 % | +4,92 % | 3,30× | long · 39,2 · ANOMALY · DEVELOPING | — | -0,01 % | 58,7 |
| 2 | BNB | BNBUSDT perp | B | 773,76 | +0,62 % | +0,68 % | 1,10× | long · 32,6 · ANOMALY · DEVELOPING | momentum v3 long há 3,8 h (5 em 24 h) | +0,20 % | 55,9 |
| 3 | DOGE | DOGEUSDT perp | B | 0,08898 | +0,84 % | +0,67 % | 0,96× | long · 28,6 · ANOMALY | momentum v3 long há 0,0 h (6 em 24 h) | +0,22 % | 54,9 |
| 4 | ARB | ARBUSDT perp | B | 0,21068 | +1,04 % | -0,50 % | 0,87× | long · 21,7 · NORMAL | mean_reversion_h1 v1 long há 0,0 h (18 em 24 h) | +0,08 % | 50,7 |
| 5 | SUI | SUIUSDT perp | C | 0,8511 | +0,09 % | -1,41 % | 1,63× | long · 17,9 · NORMAL · DEVELOPING | momentum v3 long há 3,0 h (6 em 24 h) | +0,17 % | 43,2 |
| 6 | LINK | LINKUSDT perp | B | 12,528 | +0,10 % | +0,06 % | 0,69× | neutral · 18,4 · ANOMALY | momentum v3 long há 2,5 h (6 em 24 h) | -0,16 % | 40,5 |
| 7 | ZEC | ZECUSDT perp | A | 1534,24 | -0,01 % | -0,54 % | 0,56× | — | mean_reversion v10 long há 1,8 h (19 em 24 h) | -0,01 % | 37,5 |
| 8 | AVAX | AVAXUSDT perp | C | 9,348 | +1,70 % | +0,32 % | 1,80× | long · 28,4 · ANOMALY | — | +0,47 % | 37,3 |
| 9 | RENDER | RENDERUSDT perp | B | 1,627 | +0,56 % | +1,75 % | 1,98× | long · 17,8 · NORMAL · DEVELOPING | — | +0,18 % | 37,2 |
| 10 | KMNO | KMNOUSDT perp | A | 0,02792 | +0,69 % | +1,16 % | 9,83× | — | — | +0,02 % | 34,6 |
| 11 | TAO | TAOUSDT perp | B | 265,49 | +0,05 % | -1,01 % | 1,25× | short · 10,1 · NORMAL | momentum v3 long há 2,5 h (9 em 24 h) | +0,26 % | 34,4 |
| 12 | ETH | ETHUSDT perp | A | 2641,01 | +0,09 % | +0,10 % | 0,32× | — | momentum v3 long há 4,5 h (6 em 24 h) | -0,01 % | 31,3 |
| 13 | JELLYJELLY | JELLYJELLYUSDT perp | A | 0,05826 | +0,62 % | +0,48 % | 8,31× | — | — | +0,12 % | 31,0 |
| 14 | SOL | SOLUSDT perp | A | 111,75 | +0,02 % | -0,11 % | 0,34× | — | mean_reversion v10 long há 8,0 h (5 em 24 h) | -0,01 % | 30,4 |
| 15 | CHILLGUY | CHILLGUYUSDT perp | B | 0,014824 | +0,54 % | +1,95 % | 2,11× | — | — | +0,50 % | 28,7 |
| 16 | 1000PEPE | 1000PEPEUSDT perp | B | 0,0038251 | +0,30 % | +0,33 % | 0,60× | long · 21,4 · NORMAL | — | +0,11 % | 28,5 |
| 17 | CAKE | CAKEUSDT perp | C | 2,4452 | +0,52 % | -0,13 % | 1,02× | long · 16,1 · NORMAL | — | +0,09 % | 27,8 |
| 18 | TRX | TRXUSDT perp | A | 0,33804 | -0,02 % | +0,06 % | 0,67× | long · 21,4 · ANOMALY | — | +0,00 % | 27,3 |
| 19 | W | WUSDT perp | B | 0,011169 | +1,46 % | +1,53 % | 0,65× | — | — | +0,51 % | 26,9 |
| 20 | ARX | ARXUSDT perp | B | 0,204 | -0,24 % | +3,92 % | 2,21× | short · 18,9 · ANOMALY · DEVELOPING | — | +0,41 % | 26,7 |
| 21 | PYTH | PYTHUSDT perp | B | 0,0606 | +0,03 % | -0,41 % | 0,59× | long · 23,0 · ANOMALY | — | +0,03 % | 26,0 |
| 22 | STRK | STRKUSDT perp | C | 0,04669 | +0,09 % | +4,29 % | 1,42× | short · 24,2 · ANOMALY · DEVELOPING | — | +0,40 % | 25,0 |
| 23 | JUP | JUPUSDT perp | A | 0,2775 | +0,14 % | -0,54 % | 0,53× | long · 17,6 · ANOMALY | — | -0,03 % | 24,4 |
| 24 | TRUMP | TRUMPUSDT perp | A | 2,054 | +0,05 % | +0,20 % | 0,68× | neutral · 11,0 · ANOMALY | — | +0,01 % | 20,5 |
| 25 | ORCA | ORCAUSDT perp | B | 1,464 | -0,41 % | -0,07 % | 0,66× | long · 13,9 · ANOMALY | — | +0,21 % | 20,2 |
| 26 | PENGU | PENGUUSDT perp | A | 0,007962 | +0,03 % | -0,01 % | 0,71× | — | — | -0,10 % | 19,9 |
| 27 | WIF | WIFUSDT perp | A | 0,2137 | -0,14 % | +0,47 % | 0,56× | — | — | +0,03 % | 19,9 |
| 28 | GALA | GALAUSDT perp | C | 0,001918 | -0,21 % | +0,37 % | 0,77× | long · 12,6 · NORMAL | — | +0,52 % | 19,5 |
| 29 | USELESS | USELESSUSDT perp | A | 0,27151 | -0,73 % | +1,67 % | 0,82× | short · 11,6 · ANOMALY | — | +0,11 % | 19,4 |
| 30 | ENA | ENAUSDT perp | C | 0,19654 | -1,02 % | +2,75 % | 1,88× | short · 23,1 · ANOMALY | — | +0,51 % | 19,2 |
| 31 | IO | IOUSDT perp | C | 0,1435 | +0,00 % | +0,91 % | 0,91× | — | — | +0,47 % | 18,8 |
| 32 | HYPE | HYPEUSDT perp | A | 92,48 | -0,16 % | -0,01 % | 0,63× | — | — | -0,03 % | 18,8 |
| 33 | AAVE | AAVEUSDT perp | B | 142,49 | -0,06 % | -0,17 % | 0,65× | neutral · 15,5 · ANOMALY | — | +0,03 % | 18,5 |
| 34 | JTO | JTOUSDT perp | B | 0,4603 | +0,57 % | +0,74 % | 0,47× | short · 11,9 · NORMAL | — | +0,43 % | 18,3 |
| 35 | 1000BONK | 1000BONKUSDT perp | A | 0,00301 | -0,07 % | -0,03 % | 0,65× | neutral · 17,6 · NORMAL | — | +0,10 % | 18,2 |
| 36 | BOME | BOMEUSDT perp | A | 0,0009733 | -0,09 % | -0,02 % | 0,65× | short · 4,8 · NORMAL | — | +0,07 % | 17,8 |
| 37 | PUMP | PUMPUSDT perp | A | 0,004149 | -0,43 % | -0,14 % | 0,84× | — | — | -0,02 % | 17,7 |
| 38 | UNI | UNIUSDT perp | B | 9,062 | -0,86 % | -0,44 % | 0,55× | short · 29,1 · ANOMALY | momentum v3 long há 4,5 h (11 em 24 h) | +0,35 % | 17,6 |
| 39 | FARTCOIN | FARTCOINUSDT perp | A | 0,1614 | -0,19 % | -0,37 % | 0,41× | — | — | -0,06 % | 16,7 |
| 40 | VIRTUAL | VIRTUALUSDT perp | A | 0,6804 | -0,07 % | +0,07 % | 1,11× | neutral · 8,1 · NORMAL | — | +0,47 % | 16,4 |
| 41 | MEGA | MEGAUSDT perp | C | 0,04099 | +0,17 % | +0,42 % | 0,34× | neutral · 5,5 · NORMAL | — | +0,47 % | 16,2 |
| 42 | MON | MONUSDT perp | B | 0,0249 | -0,08 % | -0,08 % | 0,53× | — | — | +0,27 % | 15,9 |
| 43 | CHZ | CHZUSDT perp | C | 0,01519 | +0,07 % | -0,13 % | 0,96× | — | — | +0,48 % | 15,8 |
| 44 | PNUT | PNUTUSDT perp | A | 0,05326 | +0,06 % | +0,26 % | 0,49× | neutral · 15,8 · ANOMALY | — | +0,50 % | 15,3 |
| 45 | SKR | SKRUSDT perp | B | 0,019515 | -0,03 % | -0,54 % | 0,49× | neutral · 20,7 · ANOMALY | — | +0,20 % | 15,2 |
| 46 | BIO | BIOUSDT perp | B | 0,02803 | -0,14 % | -1,41 % | 1,32× | short · 11,5 · NORMAL | — | -0,02 % | 14,8 |
| 47 | DRIFT | DRIFTUSDT perp | C | 0,01573 | -0,06 % | +0,19 % | 0,18× | — | — | +0,38 % | 14,6 |
| 48 | MOODENG | MOODENGUSDT perp | A | 0,04563 | +0,00 % | -0,28 % | 0,78× | neutral · 16,4 · ANOMALY · DEVELOPING | — | +0,50 % | 14,2 |
| 49 | XMR | XMRUSDT perp | B | 583,76 | -0,27 % | -1,08 % | 0,41× | neutral · 14,6 · NORMAL | — | +0,09 % | 13,0 |
| 50 | GRASS | GRASSUSDT perp | C | 0,3443 | -0,23 % | -0,26 % | 0,44× | — | — | +0,48 % | 12,1 |
| 51 | WLFI | WLFIUSDT perp | C | 0,05902 | +0,09 % | -0,02 % | 0,71× | — | — | +0,87 % | 11,5 |
| 52 | SPX | SPXUSDT perp | A | 0,4897 | -0,57 % | -0,55 % | 0,58× | short · 13,3 · ANOMALY | — | +0,27 % | 10,1 |
| 53 | INJ | INJUSDT perp | B | 7,564 | -0,76 % | -1,91 % | 1,29× | neutral · 17,6 · ANOMALY | — | +0,35 % | 8,1 |
| 54 | LIT | LITUSDT perp | B | 5,0805 | -1,34 % | -1,60 % | 1,06× | short · 18,7 · NORMAL | — | +0,09 % | 5,3 |
| 55 | PONS | PONSUSDT perp | B | 0,6329 | -1,03 % | -4,25 % | 1,47× | short · 12,0 · ANOMALY · DEVELOPING | — | +0,15 % | 4,0 |
| 56 | CHIP | CHIPUSDT perp | B | 0,04373 | -1,86 % | -2,15 % | 0,87× | short · 20,8 · ANOMALY · DEVELOPING | — | +0,09 % | 1,7 |
## 3a. Sinais dos últimos 7 dias nesses mercados (`agent_signals` × `signal_outcomes`, 12/09 13:00 → 19/09 13:00 UTC)

No período o Lab emitiu **700 sinais, todos `long`, em 15 mercados**; 10 desses 15 estão na mesa (os outros 5 — BTC, XRP, LTC, DOT, HBAR ou similares — não têm execução na Solana). Resultado = `signal_outcomes.result` (alvo / stop / expirado / aberto) e R médio/soma dos fechados.

| mercado | estratégia | versão | n | primeiro | último | alvo | stop | expirado | aberto | R médio | Σ R |
|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| ARBUSDT | mean_reversion | v1 | 10 | 09-12 17:00 | 09-19 01:45 | 3 | 7 | 0 | 0 | -0,404 | -4,04 |
| ARBUSDT | mean_reversion | v10 | 7 | 09-12 17:00 | 09-18 22:45 | 1 | 2 | 4 | 0 | -0,017 | -0,12 |
| ARBUSDT | mean_reversion | v14 | 7 | 09-14 21:30 | 09-19 01:45 | 4 | 2 | 1 | 0 | 0,394 | 2,76 |
| ARBUSDT | mean_reversion | v2 | 8 | 09-14 21:30 | 09-19 01:45 | 3 | 5 | 0 | 0 | -0,206 | -1,65 |
| ARBUSDT | mean_reversion | v3 | 8 | 09-14 21:30 | 09-19 01:45 | 3 | 5 | 0 | 0 | -0,206 | -1,65 |
| ARBUSDT | mean_reversion | v6 | 7 | 09-14 21:30 | 09-19 01:45 | 4 | 2 | 1 | 0 | 0,394 | 2,76 |
| ARBUSDT | mean_reversion | v7 | 7 | 09-14 21:30 | 09-19 01:45 | 3 | 2 | 2 | 0 | 0,284 | 1,99 |
| ARBUSDT | mean_reversion | v8 | 9 | 09-12 17:00 | 09-19 01:45 | 4 | 4 | 1 | 0 | 0,056 | 0,50 |
| ARBUSDT | mean_reversion_h1 | v1 | 1 | 09-19 13:00 | 09-19 13:00 | 0 | 0 | 0 | 1 | — | — |
| ARBUSDT | momentum | v3 | 23 | 09-13 04:00 | 09-18 20:30 | 10 | 2 | 0 | 0 | 0,010 | 0,22 |
| BNBUSDT | momentum | v3 | 14 | 09-14 02:30 | 09-19 09:15 | 6 | 3 | 0 | 0 | -0,338 | -4,74 |
| DOGEUSDT | mean_reversion | v10 | 4 | 09-14 22:45 | 09-19 05:00 | 1 | 0 | 3 | 0 | 0,171 | 0,68 |
| DOGEUSDT | mean_reversion_h1 | v1 | 1 | 09-19 10:00 | 09-19 10:00 | 1 | 0 | 0 | 0 | 1,117 | 1,12 |
| DOGEUSDT | momentum | v3 | 19 | 09-13 14:15 | 09-19 13:00 | 5 | 3 | 1 | 1 | -0,420 | -7,56 |
| ETHUSDT | mean_reversion | v10 | 4 | 09-16 13:45 | 09-19 00:00 | 1 | 0 | 3 | 0 | 0,125 | 0,50 |
| ETHUSDT | momentum | v3 | 20 | 09-14 03:00 | 09-19 08:30 | 10 | 2 | 0 | 0 | -0,051 | -0,97 |
| LINKUSDT | mean_reversion | v10 | 4 | 09-14 23:45 | 09-19 00:15 | 2 | 0 | 2 | 0 | 0,718 | 2,87 |
| LINKUSDT | momentum | v3 | 22 | 09-13 16:45 | 09-19 10:30 | 10 | 2 | 1 | 0 | -0,040 | -0,87 |
| SOLUSDT | mean_reversion | v10 | 3 | 09-14 22:45 | 09-19 05:00 | 0 | 0 | 3 | 0 | -0,339 | -1,02 |
| SOLUSDT | mean_reversion_h1 | v1 | 1 | 09-15 06:00 | 09-15 06:00 | 0 | 1 | 0 | 0 | -1,158 | -1,16 |
| SOLUSDT | momentum | v3 | 21 | 09-14 03:15 | 09-18 19:30 | 7 | 3 | 0 | 0 | -0,316 | -6,63 |
| SUIUSDT | mean_reversion | v1 | 2 | 09-14 22:15 | 09-19 06:30 | 0 | 2 | 0 | 0 | -1,176 | -2,35 |
| SUIUSDT | mean_reversion | v10 | 6 | 09-12 13:30 | 09-19 06:30 | 1 | 1 | 4 | 0 | 0,251 | 1,51 |
| SUIUSDT | mean_reversion | v8 | 2 | 09-14 22:15 | 09-19 06:30 | 1 | 1 | 0 | 0 | -0,079 | -0,16 |
| SUIUSDT | momentum | v3 | 24 | 09-13 01:30 | 09-19 10:00 | 7 | 5 | 0 | 0 | -0,303 | -6,97 |
| TAOUSDT | mean_reversion | v1 | 2 | 09-18 12:30 | 09-18 19:00 | 2 | 0 | 0 | 0 | 0,949 | 1,90 |
| TAOUSDT | mean_reversion | v10 | 4 | 09-12 13:30 | 09-18 19:00 | 2 | 0 | 2 | 0 | 0,621 | 2,49 |
| TAOUSDT | mean_reversion | v14 | 1 | 09-18 12:30 | 09-18 12:30 | 1 | 0 | 0 | 0 | 1,353 | 1,35 |
| TAOUSDT | mean_reversion | v2 | 1 | 09-18 12:30 | 09-18 12:30 | 1 | 0 | 0 | 0 | 1,281 | 1,28 |
| TAOUSDT | mean_reversion | v6 | 1 | 09-18 12:30 | 09-18 12:30 | 1 | 0 | 0 | 0 | 1,353 | 1,35 |
| TAOUSDT | mean_reversion | v7 | 1 | 09-18 12:30 | 09-18 12:30 | 1 | 0 | 0 | 0 | 1,389 | 1,39 |
| TAOUSDT | mean_reversion | v8 | 2 | 09-18 12:30 | 09-18 19:00 | 2 | 0 | 0 | 0 | 1,099 | 2,20 |
| TAOUSDT | mean_reversion_h1 | v1 | 1 | 09-14 14:00 | 09-14 14:00 | 1 | 0 | 0 | 0 | 1,018 | 1,02 |
| TAOUSDT | momentum | v3 | 26 | 09-13 02:45 | 09-19 10:30 | 11 | 7 | 0 | 0 | -0,252 | -6,56 |
| UNIUSDT | mean_reversion | v1 | 9 | 09-12 18:30 | 09-18 23:00 | 5 | 3 | 1 | 0 | 0,234 | 2,11 |
| UNIUSDT | mean_reversion | v10 | 8 | 09-12 18:30 | 09-18 23:00 | 1 | 0 | 7 | 0 | 0,456 | 3,65 |
| UNIUSDT | mean_reversion | v14 | 7 | 09-12 18:30 | 09-18 23:00 | 5 | 0 | 2 | 0 | 0,981 | 6,87 |
| UNIUSDT | mean_reversion | v2 | 7 | 09-12 18:30 | 09-18 23:00 | 5 | 1 | 1 | 0 | 0,642 | 4,50 |
| UNIUSDT | mean_reversion | v3 | 5 | 09-15 03:30 | 09-18 23:00 | 4 | 1 | 0 | 0 | 0,615 | 3,07 |
| UNIUSDT | mean_reversion | v6 | 7 | 09-12 18:30 | 09-18 23:00 | 5 | 0 | 2 | 0 | 0,981 | 6,87 |
| UNIUSDT | mean_reversion | v7 | 7 | 09-12 18:30 | 09-18 23:00 | 5 | 0 | 2 | 0 | 0,997 | 6,98 |
| UNIUSDT | mean_reversion | v8 | 8 | 09-12 18:30 | 09-18 23:00 | 5 | 0 | 3 | 0 | 0,813 | 6,50 |
| UNIUSDT | mean_reversion_h1 | v1 | 2 | 09-13 11:00 | 09-15 20:00 | 1 | 1 | 0 | 0 | 0,017 | 0,03 |
| UNIUSDT | momentum | v3 | 27 | 09-12 15:15 | 09-19 08:30 | 9 | 7 | 0 | 0 | -0,200 | -5,40 |
| ZECUSDT | mean_reversion | v1 | 10 | 09-14 12:00 | 09-19 11:15 | 5 | 4 | 0 | 1 | 0,103 | 0,93 |
| ZECUSDT | mean_reversion | v10 | 8 | 09-14 12:00 | 09-19 11:15 | 1 | 0 | 6 | 1 | 0,274 | 1,64 |
| ZECUSDT | mean_reversion | v14 | 8 | 09-14 13:15 | 09-19 11:15 | 5 | 2 | 0 | 1 | 0,561 | 3,92 |
| ZECUSDT | mean_reversion | v2 | 9 | 09-14 13:15 | 09-19 11:15 | 5 | 3 | 0 | 1 | 0,265 | 2,12 |
| ZECUSDT | mean_reversion | v3 | 7 | 09-14 23:15 | 09-19 11:15 | 4 | 2 | 0 | 1 | 0,463 | 2,78 |
| ZECUSDT | mean_reversion | v6 | 8 | 09-14 13:15 | 09-19 11:15 | 5 | 2 | 0 | 1 | 0,561 | 3,92 |
| ZECUSDT | mean_reversion | v7 | 8 | 09-14 13:15 | 09-19 11:15 | 4 | 0 | 3 | 1 | 0,324 | 2,27 |
| ZECUSDT | mean_reversion | v8 | 8 | 09-14 12:00 | 09-19 11:15 | 4 | 3 | 0 | 1 | 0,290 | 2,03 |
| ZECUSDT | mean_reversion_h1 | v1 | 3 | 09-15 21:00 | 09-18 18:00 | 2 | 1 | 0 | 0 | 0,624 | 1,87 |
| ZECUSDT | momentum | v3 | 27 | 09-13 01:30 | 09-19 01:00 | 10 | 4 | 1 | 0 | -0,126 | -3,39 |

**Por estratégia (soma nos 10 mercados):**

| estratégia | versão | n | alvo | stop | Σ R |
|---|---|---:|---:|---:|---:|
| momentum | v3 | 223 | 85 | 38 | -42,87 |
| mean_reversion | v10 | 48 | 10 | 3 | +12,20 |
| mean_reversion | v1 | 33 | 15 | 16 | -1,45 |
| mean_reversion | v8 | 29 | 16 | 8 | +11,07 |
| mean_reversion | v2 | 25 | 14 | 9 | +6,25 |
| mean_reversion | v14 | 23 | 15 | 4 | +14,90 |
| mean_reversion | v6 | 23 | 15 | 4 | +14,90 |
| mean_reversion | v7 | 23 | 13 | 2 | +12,63 |
| mean_reversion | v3 | 20 | 11 | 8 | +4,20 |
| mean_reversion_h1 | v1 | 9 | 5 | 3 | +2,88 |

Leitura: **momentum v3 é a fonte de volume (223 sinais em 7 d nos 10 mercados) e é negativa em 9 dos 10 mercados (Σ R −42,9; 85 alvos × 38 stops, mas 100 dos 223 terminaram `invalidated` com R negativo — o R médio dos fechados vai de +0,01 em ARB a −0,42 em DOGE)**; as `mean_reversion` v6/v7/v14 em UNI/ZEC/TAO/ARB são as únicas com Σ R positiva consistente (UNI +6,9/+7,0/+6,9; ZEC +3,9; ARB +2,8). Nenhum sinal em 7 d nos nativos da Solana (MET, WIF, JUP, PYTH, JTO, BONK, PUMP…) — a mesa spot/1, se ligada hoje com os sinais que existem, compraria DOGE/ARB/SUI/UNI/LINK/BNB via ponte/representação e ETH/SOL/ZEC/TAO nativos-ou-ponte.


Leitura: o composto favorece MET (único com momentum forte + volume 3× + oportunidade long > 35), depois os "majors" com sinal do Lab (BNB, DOGE, ARB, SUI, LINK) que só existem na Solana como ponte ou representação de 75–660 k US$ de liquidez. Nativos da Solana com movimento agora: MET, KMNO (9,8× volume), JELLYJELLY (8,3×), RENDER (+1,75 %), CHILLGUY (+1,95 %), W (+1,5 %), USELESS (+1,7 % mas −0,7 % nos 15 m, oportunidade short). Nenhum dos 33 nativos tier A tem sinal do Lab nas 24 h — as estratégias ativas (momentum v3 / mean_reversion) disparam onde há 20 velas de 15 m com fechamento acima da máxima ou 2 desvios abaixo da média, e hoje isso aconteceu nos majors.

## 4. Custo de execução por tamanho (ida-e-volta, Jupiter, 13:03 UTC)

| base | 0,02 SOL | 1 SOL | 5 SOL | saltos (1 SOL) | rota (compra) |
|---|---:|---:|---:|---|---|
| MET | −0,01 % | 0,17 % | 0,47 % | 3/2 | Meteora DLMM |
| DOGE | 0,22 % | 0,22 % | 0,22 % | 1/3 | Meteora DLMM ×2 + Whirlpool |
| BNB | 0,20 % | 0,37 % | 0,54 % | 1/1 | HumidiFi + Whirlpool |
| ARB | 0,08 % | 0,82 % | **1,17 %** | 2/2 | Raydium CLMM + HumidiFi + Denali |
| KMNO | 0,02 % | 0,02 % | 0,07 % | 2/2 | GoonFi V2 + Whirlpool |
| RENDER | 0,18 % | 0,35 % | 0,48 % | 3/1 | 1DEX + Raydium CLMM |
| SUI | 0,17 % | 0,26 % | 0,41 % | 1/2 | Scorch + Byreal |
| ZEC | −0,01 % | 0,07 % | 0,01 % | 2/2 | BisonFi + GoonFi V2 |
| JELLYJELLY | 0,12 % | 0,51 % | 0,54 % | 1/1 | Raydium |
| WIF | 0,03 % | 0,20 % | 0,54 % | 1/1 | Byreal + Whirlpool |

Negativo = a ida e a volta acharam pools diferentes com preços ligeiramente desalinhados (arbitragem de 1 bp, não lucro real). O `quote` não inclui taxa de prioridade (~0,0001–0,001 SOL por transação) nem o slippage real do pouso — a R62 mediu −0,07 % mediano e −7,4 % no pior caso em curva pump.fun; aqui as pools são fundas e o pior deve ser bem menor. Regra de bolso: **0,25 % por ida-e-volta em tier A com 1 SOL; 0,5 % com 5 SOL; tier C só com ≤ 0,2 SOL.**

## 5. Ressalvas: perp como sinal, spot como execução

1. **Direção.** Na Solana só compramos (`long`); 21 das 39 oportunidades abertas nos candidatos são `short` ou `neutral` e o Lab não emitiu nenhum `short` em 24 h — hoje não perdemos nada, mas o scanner produz short (ARX, UNI, LIT, PONS, CHIP, 1000BONK…) que não tem execução.
2. **Funding e alavancagem.** Os perps dos 10 com sinal pagam funding +0,005–0,010 %/8 h (longs pagam) — spot na Solana **não paga**, o que favorece o spot em posições de horas. Sem alavancagem, o `R` do Lab (stop ≈ 1 ATR de 15 m ≈ 0,5–1,5 % nos majors) vira 0,5–1,5 % do capital por trade; para bater os 0,25–0,5 % de ida-e-volta o alvo precisa ser ≥ 2–3 R, não o 1 R que o momentum v3 usa.
3. **Stop.** Não existe stop na Jupiter: o executor tem de vigiar (o `event_exits_eval` da T4.63 já faz isso para memes com marca a cada 1 s) e vender por `quote`+`swap` — 1,6 s mediana gatilho→pouso (R62), sem garantia de preço além do `slippageBps`.
4. **Preço.** A vela 1 m da Binance (`is_final`) fecha e a pool já reflete: correlação contemporânea 0,63 em 15 s, lead da Binance 0,23 a +15 s, 0,03 no sentido inverso; nível Jupiter +8,8 ± 4,5 bp acima do mid (WIF, 38 pontos, 10 min, faixa de 23 bp — amostra curta e mercado parado, refazer numa hora volátil). Para ETH/BNB/DOGE via ponte, quem mantém a paridade são arbitradores; um pico de 1 % na Binance pode demorar mais para chegar a uma pool de 200 k US$ — e é exatamente isso que faz o preço de entrada ser pior, não melhor.
5. **Ponte e representação.** ETH/WBTC/BNB (Portal) são oficiais mas com 0,2–37 M US$ de liquidez; DOGE/ARB/SUI/UNI/LINK/AVAX/AAVE/ENA (mcap 0,1–0,9 M na Solana, pools abertos entre 2026-04 e 2026-09, `devMints 20`, emissor não verificado por mim) têm risco de desancoragem que a Binance não tem — não colocar tamanho neles até identificar o emissor.
6. **Cobertura.** 34 dos 90 (RAY, POPCAT, MEW, TNSR, ME, GOAT, ZEREBRO, ALCH…) não estão nos 200 do radar: sem velas, sem baseline, sem sinal. Se a tese é "Binance sinaliza, Solana executa", os nativos da Solana com perp na Binance deviam entrar no `is_monitored` (é `monitor_rank` por volume 24 h; POPCAT 4,5 M e MEW 9,5 M US$ de liquidez na Jupiter ficam de fora porque o perp gira pouco).

## 6. O mapa em JSON (`binance_symbol → solana_mint`, os 90; `1000BONKUSDT`/`1000PEPEUSDT` = 1 000 tokens por unidade Binance)

```json
{
 "SOLUSDT": "So11111111111111111111111111111111111111112",
 "WBTCUSDT": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
 "PUMPUSDT": "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn",
 "TRUMPUSDT": "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",
 "ETHUSDT": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",
 "RAYUSDT": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
 "BOMEUSDT": "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82",
 "ARCUSDT": "61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump",
 "MEWUSDT": "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5",
 "WIFUSDT": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
 "FARTCOINUSDT": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
 "ZECUSDT": "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS",
 "HYPEUSDT": "98sMhvDwXj1RQi5c5Mndm3vPe9cBqPrbLaufMXFNMh5g",
 "JUPUSDT": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
 "TRXUSDT": "GbbesPbaYh5uiAZSYNXTc7w9jty1rpg3P9L4JeN4LkKc",
 "POPCATUSDT": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
 "USELESSUSDT": "Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk",
 "METUSDT": "METvsvVRapdj9cFLzq4Tr43xK4tAjQfwX76z3n6mWQL",
 "PNUTUSDT": "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump",
 "SPXUSDT": "J3NKxxXZcnNiMjKw9hYb2K4LUxgwB6t1FtPtQVsv3KFr",
 "JELLYJELLYUSDT": "FeR8VBqNRSUD5NtXAj2n3j1dAHkZHfyDktKuLXD4pump",
 "PENGUUSDT": "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv",
 "KMNOUSDT": "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS",
 "PIPPINUSDT": "Dfh5DzRgSvvCFDoYc2ciTkMrbDfRKybA4SoFbPmApump",
 "VIRTUALUSDT": "3iQL8BFS2vE7mww4ehAqQHAsbmRNCrPxizWAT2Zfyr9y",
 "GOATUSDT": "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",
 "ZEREBROUSDT": "8x5VqbHA8D7NkD52uNuS5nnt3PwA8pLD34ymskeSo2Wn",
 "ALCHUSDT": "HNg5PYJmtqcmzXrv6S9zP1CDKk5BgDuyFBxbvNApump",
 "BANUSDT": "9PR7nCP9DpcUotnDPVLUBUZKu5WAYkwrCUx9wDnSpump",
 "MOODENGUSDT": "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY",
 "1000BONKUSDT": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
 "BONKUSDT": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
 "BIRBUSDT": "G7vQWurMkMMm2dU3iZpXYFTHT9Biio4F4gZCrwFpKNwG",
 "GRIFFAINUSDT": "KENJSUYLASHUMfHyy5o4Hp2FdNqZg1AsUPhfH2kYvEP",
 "CHILLGUYUSDT": "Df6yfrKC8kZE3KNkrHERKzAetSxbrWeniQfyJY4Jpump",
 "SWARMSUSDT": "74SBV4zDXxTRgv1pEMoECskKBkZHc2yGPnc7GYVepump",
 "ACTUSDT": "GJAFwWjJ3vnTsrQVabjBVK2TYB1YtRCQXRDfDgUnpump",
 "SKRUSDT": "SKRbvo6Gf7GondiT3BbTfuRDPqLWei4j2Qy2NPGZhW3",
 "XMRUSDT": "WXMRyRZhsa19ety5erZhHg4N3xj3EVN92u94422teJp",
 "1000PEPEUSDT": "PEPEqnuuCDbBC89p1u9vpnP1KQ2oj1xTcQBsjt9X55m",
 "PEPEUSDT": "PEPEqnuuCDbBC89p1u9vpnP1KQ2oj1xTcQBsjt9X55m",
 "DOGEUSDT": "DoGEV7LASBkQbibMc5k5vKnTZoMg423GpJ5QtJEGfm7R",
 "LITUSDT": "EicWvteVi2fWepEzS3FYWsnuPoP6caZfjnKqNvydLjCH",
 "TAOUSDT": "taoC6xyv2v8tDLcev4uaGUgV4vdQsWJrGft2kcBRrBY",
 "ARXUSDT": "ARXwZkNAtzPfdcoqQiduJn8EPv9fKiDfGn2KyggyDrFs",
 "AUDIOUSDT": "9LzCMqDgTKYz9Drzqnpgee3SGa89up3a247ypMj2xrqM",
 "PYTHUSDT": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
 "DOODUSDT": "DvjbEsdca43oQcw2h3HW1CT7N3x5vRcr3QrvTUHnXvgV",
 "JTOUSDT": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
 "2ZUSDT": "J6pQQ3FAcJQeWPPGppWRb4nM8jU3wLyYbRrLh7feMfvd",
 "UNIUSDT": "uniHfuPhEQSrtpzXpJZDCSq53yaejKKpNhFUiKoHKHV",
 "INJUSDT": "1NJMqVM4PadjuzYmeB7zV7q7DV8oB3ExaQCd9x6KsLz",
 "ARBUSDT": "ARBzQTYDCW2KnVEjs1Mc81LekB1ibVFZKbSVmorkoT9d",
 "RENDERUSDT": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
 "ORCAUSDT": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
 "BNBUSDT": "9gP2kCy3wA1ctvYWQk75guqXuHfrEomqydHLtcTCqiLa",
 "LINKUSDT": "LinkhB3afbBKb2EQQu7s7umdZceV3wcvAUJhQAfQ23L",
 "MEUSDT": "MEFNBXixkEbait3xn9bkm8WsJzXtVsaJEn4c8Sam21u",
 "BIOUSDT": "bioJ9JTqW62MLz7UKHU69gtKhPpGi1BQhccj2kmSvUJ",
 "MONUSDT": "CrAr4RRJMBVwRsZtT62pEhfA9H5utymC2mVx8e7FreP2",
 "BMTUSDT": "FQgtfugBdpFN7PZ6NdPrZpVLDBrPGxXesi4gVu3vErhY",
 "PONSUSDT": "poNSfquKq512ApeYjVghwViSun4x1MhCqHVH2Paq4jN",
 "WUSDT": "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ",
 "FLUIDUSDT": "DuEy8wWrzCUun5ZbbG9hkVqXqqicpTQw8gB7nEAzpCHQ",
 "AAVEUSDT": "AavE1kKKnesPw4MuRJmJ9jZs9QzEE8CPxQ3ViczUDfc1",
 "SLXUSDT": "SLXdx4BUt2v9uJQNzWqSfzTJ9UKLUDsvxHFMEEdrfgq",
 "CHIPUSDT": "chipCAT7vi5CZtbZsn9z7iMPXvFwyAnKz3QFu8XVuHm",
 "ENAUSDT": "72QvBVwpxqmheEPfaCwWSWqEFsUy3rhWt6JhQBMNTwD1",
 "SUIUSDT": "suifhC9gU1VbJAPYPTBkHJyyyStKGLLYPVDTmPoqbvA",
 "AIXBTUSDT": "14zP2ToQ79XWvc7FQpm4bRnp9d6Mp1rFfsUW3gpLcRX",
 "DRIFTUSDT": "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7",
 "AVAXUSDT": "avaxGHCq3T7hoxd73oY2KY9hJSTaeMibXvHy5KNzh5D",
 "CAKEUSDT": "4qQeZ5LwSz6HuupUu8jCtgXyW1mYQcNbFAW1sWZp89HL",
 "BILLUSDT": "Bi11Je4MH3PpyCNiuTAepRbsA5U6DK3DJy79ZFthddX",
 "GRASSUSDT": "Grass7B4RdKfBCjTKgSqnXkqjwiGvQyFbuSCUJr3XXjs",
 "STRKUSDT": "HsRpHQn6VbyMs5b5j5SV6xQ2VvpvvCCzu19GjytVSCoz",
 "TNSRUSDT": "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6",
 "CHZUSDT": "6eftxVbSAunVEoxUWdGhPdxg5UdsJ8Wkwy5w5YFuxouw",
 "IOUSDT": "BZLbGTNCSFfoth2GYDtwr7e4imWzpR5jqcUuGEwr646K",
 "MEGAUSDT": "megaA5QDK1qLXtjpvg9oCFMvxT9d5BCMrVTBddnM5kV",
 "WLFIUSDT": "WLFinEv6ypjkczcS83FZqFpgFZYwQXutRbxGe7oC16g",
 "PSGUSDT": "5eyib4qghYGHNh7VvxSFGYLFJSanjq9hug9fR52kksnm",
 "1000CATUSDT": "3joMReCCSESngJEpFLoKR2dNcChjSRCDtybQet5uSpse",
 "APEUSDT": "C1MHyoTJpRTeS9AQCyspNVu2EWAYCZwmJ1jNkEArFP1f",
 "BATUSDT": "EPeUFDgHRxs9xxEPVaL6kfGQvCon7jmAWKVUHuux1Tpz",
 "GALAUSDT": "eEUiUs4JWYZrp72djAGF1A8PhpR6rHphGeGN7GbVLp6",
 "WCTUSDT": "WCTk5xWdn5SYg56twGj32sUF3W4WFQ48ogezLBuYTBY",
 "PRLUSDT": "PERLEQKUNUp1dgFZ8EvyXHdN9d6ZQqfGxALDvfs6pDs",
 "DYMUSDT": "AjnUVPffPT91gBS7KADzXgpdTPFrjJURHrKWAa1fQbHH",
 "GMTUSDT": "7i5KKsX2weiTkry7jA4ZwSuXGhs5eJBEjY8vVxR4pfRx"
}
```

## 7. Amostra Binance × Jupiter (WIF, 15 s, 12:49–12:59 UTC)

Correlação dos retornos de 15 s (Binance em t vs Jupiter em t+k): k = −45 s −0,07 · −30 s −0,16 · −15 s +0,23 · **0 s +0,63** · +15 s +0,03 · +30 s −0,22 · +45 s 0,00 (n = 34–37). Nível: Jupiter − Binance mid = +8,8 bp em média (mediana +7,9, desvio 4,5, min +0,5, max +20,8); alinhar a Jupiter 1–3 amostras atrás piora o erro (9,5 → 11,1 bp), ou seja, não há atraso mensurável de ≥ 15 s.

| hora UTC | Binance perp mid | Jupiter (2 USDC→WIF) | Δ (bp) | slot |
|---|---:|---:|---:|---:|
| 12:49:30 | 0,21365 | 0,21387 | +10,3 | 448412442 |
| 12:49:45 | 0,21375 | 0,21387 | +5,6 | 448412498 |
| 12:50:00 | 0,21375 | 0,21386 | +5,3 | 448412553 |
| 12:50:15 | 0,21365 | 0,21384 | +9,0 | 448412612 |
| 12:50:30 | 0,21355 | 0,21386 | +14,5 | 448412669 |
| 12:50:45 | 0,21355 | 0,21388 | +15,2 | 448412725 |
| 12:51:00 | 0,21365 | 0,21396 | +14,6 | 448412781 |
| 12:51:15 | 0,21355 | 0,21390 | +16,5 | 448412838 |
| 12:51:30 | 0,21355 | 0,21380 | +11,6 | 448412892 |
| 12:51:45 | 0,21355 | 0,21383 | +13,0 | 448412945 |
| 12:52:00 | 0,21345 | 0,21380 | +16,5 | 448413002 |
| 12:52:15 | 0,21355 | 0,21383 | +13,1 | 448413058 |
| 12:52:30 | 0,21355 | 0,21385 | +14,2 | 448413116 |
| 12:52:45 | 0,21365 | 0,21382 | +7,8 | 448413170 |
| 12:53:00 | 0,21365 | 0,21378 | +6,2 | 448413228 |
| 12:53:15 | 0,21365 | 0,21382 | +7,9 | 448413281 |
| 12:53:30 | 0,21385 | 0,21399 | +6,6 | 448413339 |
| 12:53:45 | 0,21385 | 0,21403 | +8,3 | 448413395 |
| 12:54:00 | 0,21385 | 0,21401 | +7,7 | 448413450 |
| 12:54:15 | 0,21385 | 0,21386 | +0,5 | 448413506 |
| 12:54:30 | 0,21355 | 0,21356 | +0,6 | 448413564 |
| 12:54:45 | 0,21345 | 0,21371 | +12,1 | 448413620 |
| 12:55:00 | 0,21385 | 0,21404 | +9,1 | 448413677 |
| 12:55:15 | 0,21385 | 0,21402 | +7,9 | 448413732 |
| 12:55:30 | 0,21385 | 0,21402 | +7,8 | 448413789 |
| 12:55:45 | 0,21395 | 0,21402 | +3,4 | 448413846 |
| 12:56:00 | 0,21395 | 0,21407 | +5,4 | 448413902 |
| 12:56:15 | 0,21355 | 0,21399 | +20,8 | 448413958 |
| 12:56:30 | 0,21355 | 0,21373 | +8,4 | 448414014 |
| 12:56:45 | 0,21355 | 0,21365 | +4,9 | 448414072 |
| 12:57:00 | 0,21355 | 0,21362 | +3,4 | 448414131 |
| 12:57:15 | 0,21345 | 0,21361 | +7,6 | 448414188 |
| 12:57:30 | 0,21345 | 0,21364 | +8,7 | 448414245 |
| 12:57:45 | 0,21345 | 0,21368 | +10,7 | 448414302 |
| 12:58:00 | 0,21355 | 0,21367 | +5,5 | 448414360 |
| 12:58:15 | 0,21365 | 0,21372 | +3,3 | 448414414 |
| 12:58:30 | 0,21355 | 0,21366 | +5,3 | 448414470 |
| 12:58:45 | 0,21365 | 0,21378 | +6,0 | 448414526 |

## 8. Próximo passo sugerido

- **T4.xx (proposta):** braço de papel "Binance→Solana" no executor: universo = os 33 tier A nativos deste mapa; gatilho = `momentum v3`/oportunidade `long ≥ 40` no perp da Binance; execução = `quote`+`swap` Jupiter com `slippageBps 50`, tamanho 0,5 SOL, saída por alvo 2 R / stop 1 ATR(15 m) / 4 h; custo assumido 0,3 % ida-e-volta + 0,001 SOL de taxas. Refutação: expectancy ≤ 0 em 30 trades.
- Antes disso, incluir RAY/POPCAT/MEW/TNSR/ME/GOAT no `is_monitored` (hoje sem velas) e repetir a amostra de latência numa hora de movimento (≥ 1 % em 10 min), com 3 tokens (um nativo tier A, um Portal, uma representação).
- Ficha de conhecimento: `obsidian/11-KNOWLEDGE/KB-0145-binance-como-sinal-solana-como-execucao.md`.
