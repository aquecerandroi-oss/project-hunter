# Plantão meme — tendências em movimento na Solana (16/09/2026, corrida das 17h BRT)

Lido 16/09/2026 16:04–16:12 BRT (19:04–19:12 UTC), só por `curl`/WebSearch em APIs públicas, sem navegador.
**baha.com e X não foram lidos** (baha só pelo Chrome do Everton; X bloqueado) — todo "post"/"anúncio" abaixo é
`reported`/`rumor`. Esta corrida **não repete** o extrato das 16h (`eventos-2026-09-16-16h.md`, lido 15:39–15:58
BRT): só o que mudou em ~40 min e o que aquele extrato não viu. SOL = US$ 98,62 (pump.fun `sol-price`, 19:04 UTC).

## Fontes desta corrida

| fonte | URL | resultado |
|---|---|---|
| DexScreener boosts / profiles | `token-boosts/top/v1`, `token-profiles/latest/v1` | 200 · 10 + 13 Solana (21 mints) |
| DexScreener pares | `tokens/v1/solana/{mints}` — **lotes de 30 dão `000` (conexão cai); lotes de 10 passam** | 200 × 16 lotes (171 mints: 21 boosts/profiles + 150 pump.fun) |
| DexScreener busca | `latest/dex/search?q=` x money, warsh, clarity, token2049, paid, usepaid, circle arc, fed hike, argus, zcash | 200 |
| pump.fun | `coins?sort=market_cap` (50), `coins/currently-live` (50), `coins?sort=created_timestamp` (50), `sol-price` | 200 |
| CoinGecko trending | `search/trending` | 200 (15 moedas) |
| RSS CoinDesk / Cointelegraph / Decrypt / The Block | — | 200; **só 2 itens novos depois de 18:10 UTC** (ambos Decrypt) |
| WebSearch | usepaid.app; calendário 17/09; Argus | 3 consultas |

## 1. Narrativas movendo agora (ordenado por volume de 24 h real, não por mcap)

Marca **viveiro** = mcap ≥ 100× o volume de 24 h, sem twitter/site, ≥ 2 clones do mesmo símbolo (KB-0100 §2: os
únicos "graduados" das casadas de hoje eram 8 clones deste tipo, todos em 85,0 SOL cravados — não perseguir).
`r` = mcap ÷ volume 24 h. Idade = do par (DexScreener) ou do mint (pump.fun).

### N1 — **UsePaid / X Money** (a onda "Elon" das 16h tem outro nome: é `PAID`)
Fato novo desta corrida: a busca `paid` devolve **`PAID` (UsePaid)**, mint `98kfF7rmsg1QDUEoCqNE7g7M1FdrTt92TEp2CLzypump`
— **US$ 59,0 M de volume em 24 h, US$ 1,02 M na última hora, 4 670 compras × 2 947 vendas/h, mcap US$ 9,8 M,
liq US$ 422 k, +24 782 % em 24 h**, par PumpSwap criado 15/09 16:22 BRT (graduou), site `usepaid.app`, X `@UsePaid`.
O que é (WebSearch, usepaid.app/capital-flow): pareia um token do pump.fun a **qualquer handle do X**; o serviço lê o
handle na descrição da moeda, reclama as taxas de criador no cronograma, converte em dólar (Kraken) e paga na conta
**X Money** do handle; **20 % de cada claim compra e queima `PAID`**. Ou seja: `PAIDLON` ("Paid Elon"), `PAIDDOGE`
e o "Fees to @sopersone via UsePaid" de `CrowBrain` são **derivados de um produto**, não de um post do Elon — o
gatilho da onda das 16h estava mal atribuído (fica corrigido aqui; o post do Elon continua não visto).

| símbolo | mint | mcap | vol 24 h / 1 h | variação | idade | leitura |
|---|---|---|---|---|---|---|
| `PAID` | `98kfF7rmsg1QDUEoCqNE7g7M1FdrTt92TEp2CLzypump` | US$ 9,8 M | 59,0 M / 1,02 M | −3,7 % 1 h · +24 782 % 24 h | 24 h | mãe da narrativa; r6 — volume real, PumpSwap; **fora da mesa** (graduada; T4.18) |
| `PAIDLON` | `AowPHdsFTZNTa7JDGFUCRpyGa4niTS9GBG26CNWtpump` | US$ 432 k | 1,31 M / 268 k | **−28 % 1 h** · +484 % 24 h | 4,3 h | virou: pico entre 15:42 e 16:04 BRT; vendendo |
| `PAIDDOGE` | `52qkNpgTHcjuDYhKVcg6rJS4uYYtJHpDRcJoSdKqpump` | US$ 491 k | 871 k (**tudo na 1.ª hora**) | +292 % 1 h | **0,7 h** | perfil DexScreener novo; site + X + TG; o derivado da vez |
| `XPAY` | `4ffcz9n3Cao8jVEnb3CxHQUKqCqU5cPrJBtaYryRpump` | US$ 1,8 k | 285 k / 285 k | **−97,6 %** | 0,8 h | "XPay on Sol": rug em < 1 h com perfil pago |
| `PAID` (clones) | `HH7FnpNWdRgbKx4jWBgjdfzrMxuTM37Xim6nbhmSqaBD`, `4umQ4kpfFpATPgUS8zTMdxUh5jzPqxarYJxyp6epLXjh` | 66 k / 17 k | 1,47 M / 273 k (24 h; 1 h = 0) | — | 19 h | 25 pares "UsePaid" na busca — viveiro de clones já esgotado |
| `XMoney` | `AmqcxdBoocNAAoDc9PLokLtdqEC8yDSEgekMnR9omoon` | 5 k | 29 k / 14 k | −93 % 1 h | 12 h | 22 pares "X Money": todos mortos |

### N2 — **Viveiro "fundo/instituição" — começou a desabar (novidade), e mudou de roupa**
| símbolo | mint | mcap | vol 24 h / 1 h | variação | idade | leitura |
|---|---|---|---|---|---|---|
| `WOTF` (o "principal" das 16h) | `8MUcwPafbMA432mTgRFM4vjD7kbKcmEiwjdpzmN8pump` | US$ 32,4 M (era ~650 M nominal no clone `NnLz…`) | **3,69 M** / 219 k | **−65,5 % 1 h · −93,4 % 24 h** | 29,5 h | o maior volume do viveiro é a **saída** |
| `KIBA` | `NBVhtLhFrCjghFE5EhmtA8pZKtzZFAr3frur8iBpump` | **US$ 2 k** (pump.fun ainda mostra 283 M) | 2,00 M / 764 k | **−100 %** | 16 h | rug consumado; a API da pump.fun segue exibindo o mcap forjado |
| `WOTF` `NnLz…`, `ELON` `eqUv…`, `ECTF` `JGLw…`, `WOFI` `Fxnc…`, `NTDA` `7C1G…` | (ver extrato das 16h) | 182–672 M nominais | 0,6–1,9 M / 63–114 k | +7…+21 % 1 h; +10⁵–10⁶ % 24 h | 4–24 h | **viveiro** r 300–345 — ainda de pé |
| `WOFI` novo | `Cf7ng2asfjXWDHVBvMbtbwdrHcx6sHF6p3tWVFqNpump` | 343 M nominal | 776 k / 776 k | +841 896 % | **0,3 h** | **viveiro** r442; 5.º clone `WOFI` |
| `WWR` World Water Reserve | `KrvPY4SS1TYv8c8dLu25K8Wn8NTLTAur9kCJkvKpump` | 27,7 M | 339 k / 31 k | +68 320 % 24 h | 6,3 h | **viveiro** r82 — nome novo, mesma fábrica |
| `FAIR` Federal AI Reserve | `QbPr1ponxN4J7ozvkdh1dNzqc4zgdkE1RGygHeKpump` | 16,5 M | 199 k / 7,5 k | +40 753 % | 6,0 h | **viveiro** r83 |
| `USDF` United States Dividend Fund | `B6Jt8byfoWUB4dD5ZpZnxSp4SSfksycpaJZkVkPpump` | 17,6 M | 196 k / 6,8 k | +43 416 % | 5,8 h | **viveiro** r90 |
Contagem de clones nas 150 moedas pump.fun lidas: `WOTF` ×6, `WOFI` ×5, `NTDA` ×4, `ECTF` ×2, `DANGR` ×2. O top-50
por mcap da pump.fun continua **inútil como radar** (KB-0100 §2; regra E2 `symbol_clone`).

### N3 — **Arc / Circle** (a marca do dia agora tem um vencedor — na própria Arc, não na Solana)
| símbolo | onde | mcap | vol 24 h | variação | leitura |
|---|---|---|---|---|---|
| `ARGUS` | **Arc (Circle)**, via Fomo App — CoinGecko trending #2 (rank 704) | US$ 26,5 M | 21,3 M | **+840,7 % 24 h** | "early top-performer" citado por influenciadores da Arc (WebSearch); **0 pares `ARGUS` na Solana** às 19:1x UTC — clones são a próxima hora |
| `arc` AI Rig Complex | Solana `61V8vBaqAGMpgDQi4JcAwo1dmBGHsyhzodcPqnEVpump` | 73,5 M | 1,41 M / 30 k | −0,6 % 1 h · −6 % 24 h | a "confusão de ticker" das 16h não virou fluxo: flat |
| `ARCH` Archemist | `78wEDQEYQZSFHuyntdeo3qnLuedn17Z76ZVaUdawpump` | 39,9 M | 429 k / 16 k | +99 296 % 24 h | **viveiro** r93 |
| `BLUES` "Blues on Arc" | `BLuEgQHNqF8YtGQhY3Ruvqiq1m2w1mgS9uMY9hhdZtrr` | 124 k | 213 k / 51 | −0,9 % | 22 h; morto |

### N4 — **Animais / cassino** (o molde clássico; fluxo pequeno mas real)
| símbolo | mint | mcap | vol 24 h / 1 h | variação | idade | leitura |
|---|---|---|---|---|---|---|
| `CATE` | `Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump` | US$ 72,0 M | **5,69 M** / 264 k | +2,8 % 1 h · +6,3 % 24 h | 52 d | maior volume orgânico da amostra (r13, liq 2,8 M); referência, não entrada |
| `casinu` | `2eMoMqs194VxPHSWtCCzkBGqwCUbD4ZcqhecoGuh4tTp` | 70 k (era 145 k às 15:42) | 238 k / 238 k | +78 % 1 h | 0,8 h (par) | boost 500 + perfil; **caiu à metade em 40 min** apesar do boost |
| `blindcat` | `2kq7mEiemD5LmbzkMrxiJ98i5N3MBngeD7Hpsg8owZLy` | 88 k | 103 k / 14 k | +10 % 1 h · +91 % 24 h | 4,4 h | animal-com-história (TikTok); segue subindo devagar |
| `feg` | `58NKqgGPUgEPNq5ergdiiUBw9rGPcnX37wUTLYe2nKut` | 93 k | 383 k / 14 k | +19 % 1 h | 30 h | ao vivo (5 espectadores) |
| `BPCATE`, `$CAT`, `BUOYCAT`, `RAT` | — | — | — | — | — | ×2 clones cada nas criações mais novas (satélites de CATE) |

### N5 — **IA / agentes** (muito perfil pago, pouco dinheiro)
`SQUADAI` `GurGmtPpqf3ghLjPBsbYJHdWZ6k7bDaB2sha9Ycspump` (boost 100; sem par com volume), `boby` `bobyR5BDzjtHeTuBZw62yjX324F2dGaCihyRMa3VZoh`
(US$ 33 k, vol 22 k, boost 50), `ASTREUS` `HYwLkDxZBqKt7AaTDy92qGqHFfSfTXWXbU4Y8VSxsons` (10 k, 36 k, +219 % 6 h, ao vivo),
`SNGLRTY` (12 k), `$AGI` "agistonk" `Bif5dwRhkTiRRKtQcfprR9c4sNUN2f7kfbBFHt7H68Zi` (perfil); os grandes (`ALCH` 34 M,
`ZEREBRO` 29 M, `GOAT` 15 M) estão flat (±3 %). Nada para o radar.

### N6 — **Launchpads / "clone do que está trending"**
`PONS` `14qE3v4uwW8BX43TSaXDHtVwW3A8bAwFue4aKdHLpump` — US$ 429 k, vol 34 k, **+949 %**, **0,1 h**, X `@ponsdotfamily`:
copia o nome do `PONS` real (CoinGecko trending #7, mcap US$ 423 M, −10 %). `STONKLANA` `DFNnZi7mLegSKFhipUa964Z1DdLRKmggTr1vUhtwH6Bi`
(61 k, +61 %, 0,4 h, sem social). Padrão: nome que aparece no trending do CoinGecko ganha clone no pump.fun em < 1 h.

### N7 — **Política / macro: zero dinheiro** (confirma KB-0100)
Busca `clarity`: 13 pares, os maiores com US$ 93 k / 65 k de volume em 24 h e **US$ 0 na última hora**, mcap US$ 2–3 k
("clarity act petition", "Post Nut Clarity"). Busca `warsh`: 10 pares, mcap US$ 2,7 k, dois criados há 0,4 h já
mortos ("Kevin Warshing Machine"). Busca `fed hike`: 1 par, US$ 390. `TOKEN2049`: 1 par, US$ 2,3 k. A notícia macro
gera **criações**, não volume — a régua de KB-0100 §1 vale para hoje inteiro.

### N8 — **Outros com volume real**
`Holdoween` `BxftAowY2dVa2h9KMqDTPk4oMxzU9k6uVbZuoorXpump` (253 k, 217 k, +13 % 1 h, +562 % 24 h — a sazonal segue);
`DFC` (494 k, 234 k, −34 % 6 h); `TROLL` (42 M, 947 k, flat); `PRAXIS` `9FjBTDubXmk7VWKhk7MN5yFiNgnLxQuhRE2dp49nHxu4`
(**16 k**, era 49 k — −59 % 6 h; morreu); `SCANNOR` (perfil pago, −92 % em 0,6 h); `BLUE` "BLUE CHIP" (−65 % em 0,6 h);
ao vivo com mais gente: `ECD` "Blood Cancer Fundraiser" (32 espectadores, mcap US$ 3 k, 0,2 h — caridade, não meme).
CoinGecko trending fora da Solana: `ZEC` #1 (+19,3 %, vol US$ 2,1 B; o ZEC embrulhado na Solana `A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS`
fez US$ 11,0 M em 24 h e US$ 907 k na última hora), `ARGUS` #2, `TRUMP` #3, `LIT` #5, `PENGU` #6, `PONS` #7, `SYN` +130 %, `LSK` +89 %.

## 2. Novidades desde 16h (só o novo)

**Notícias das últimas 2 h (RSS, 18:10–19:12 UTC):** só 2 itens novos nas 4 redações, ambos Decrypt —
(a) 18:15 UTC "Fed hikes rates for the first time since 2023, Bitcoin spikes" (já no extrato das 16h como link do
Fed; sem meme); (b) 18:53 UTC "Bitcoin Core software update aims for speed and security patches" — lançamento em
outubro, zero potencial de meme em 24 h. CoinDesk, Cointelegraph e The Block: **nenhum item novo** depois de 18:10 UTC.
As novidades de verdade vieram das APIs, não das redações:
1. **UsePaid é o gatilho** (N1): produto que roteia taxa de criador do pump.fun para o X Money de qualquer handle, com
   queima de `PAID` — `PAID` fez US$ 59 M em 24 h. Potencial de meme em 24 h: **alto** (cada handle famoso vira um
   "PAID<nome>"; `PAIDDOGE` nasceu 16:2x BRT). Confiança: `reported` (site + busca; post do X não visto).
2. **`ARGUS` +840 % na Arc** (N3): a marca grande do dia tem um vencedor na própria cadeia — e **zero clones na
   Solana** até 19:1x UTC. Potencial de meme em 24 h: **médio-alto** para clones `ARGUS` no pump.fun.
3. **O viveiro começou a desabar** (N2): `WOTF` principal −93 % em 24 h com US$ 3,7 M de saída, `KIBA` −100 %;
   e a fábrica trocou de nome (`WWR`, `FAIR`, `USDF`). Não é oportunidade; é a confirmação da armadilha, com data.
4. **`PRAXIS` e `casinu` (as duas "vivas" das 16h) viraram:** −59 % e −52 % de mcap em 40 min. Boost 500 não segurou.
5. **`ZEC` é o #1 do trending CoinGecko (+19 %)**: narrativa "privacidade" fora da Solana; clones `ZCASH` no
   pump.fun são o reflexo esperado (busca `zcash`: 19 pares na Solana, todos o ZEC embrulhado — ainda sem clone meme).

**Agendado para 17/09 (BRT):** nada novo confirmado nas fontes headless além do calendário já registrado às 16h:
TOKEN2049 Singapura dia 2 (a partir de **16/09 22:00 BRT**, fuso +8 → palco de anúncios madrugada/manhã BRT);
ETHSpain Barcelona (**17/09, manhã BRT**); EBC12 dia 2 (17/09). WebSearch de calendário para 17/09 devolveu só
índices (Coindar/CryptoRank), sem item datado — **sem hora nova para registrar**. Cronograma dos claims da UsePaid
("on a schedule") não é público nas fontes lidas.

## 3. Três termos de vigilância para o radar (próximas horas)

| termo (símbolo / descrição) | por quê |
|---|---|
| **`PAID*` / `UsePaid` / "via UsePaid" na descrição** | a narrativa com mais dinheiro real hoje (US$ 59 M em `PAID`); derivados nascem a cada hora (`PAIDLON` 11:5x, `PAIDDOGE` 16:2x BRT); a descrição com handle do X é a **assinatura do produto** — e é o que o casamento de KB-0100 §0 leria (`name ~* 'paid'` + `twitter`) |
| **`ARGUS`** | +840 % na Arc, trending #2 no CoinGecko, **0 pares na Solana** às 19:1x UTC — a única narrativa quente do dia ainda sem clone; a primeira leva chega em < 1 h (padrão `PONS`: 0,1 h) |
| **`ZEC` / `ZCASH` / "privacy"** | #1 do trending CoinGecko (+19 %, US$ 2,1 B); ZEC embrulhado fez US$ 907 k na última hora na Solana; clones meme ainda ausentes — mesmo padrão do `ARGUS` |

Termos que **não** valem vigilância hoje (medido): `CLARITY`, `WARSH`, `FED`/`HIKE`, `TOKEN2049` (todos com US$ 0 na
última hora); `WOTF`/`WOFI`/`NTDA`/`WWR`/`FAIR`/`USDF` (viveiro — só como regra de exclusão).

## 4. Linhas `meme_event.py add` — só eventos NOVOS (dry-run; `--apply` na VPS; sem `--mint`, mint em `--notes`)

```bash
# 9. UsePaid / PAID: o produto por tras da onda "Paid Elon" (corrige a atribuicao do evento 4 das 16h)
uv run python infra/scripts/meme_event.py add --kind brand_launch \
  --title "UsePaid: taxas de criador do pump.fun pagas no X Money de qualquer handle, 20 % queima PAID; PAID US$ 59 M vol 24 h, +24 782 %; derivados PAIDLON/PAIDDOGE" \
  --url "https://usepaid.app/capital-flow" --handle UsePaid --symbol PAID \
  --confidence reported --source plantao --observed-at 2026-09-16T19:06:00Z \
  --notes '{"mint":"98kfF7rmsg1QDUEoCqNE7g7M1FdrTt92TEp2CLzypump","mcap_usd":9819569,"vol24_usd":58964312,"vol1h_usd":1023888,"buys1h":4670,"pair":"pumpswap","derivatives":{"PAIDLON":"AowPHdsFTZNTa7JDGFUCRpyGa4niTS9GBG26CNWtpump","PAIDDOGE":"52qkNpgTHcjuDYhKVcg6rJS4uYYtJHpDRcJoSdKqpump"},"corrects":"evento 4 (16h): gatilho era UsePaid, nao post do Elon","signature":"handle do X na descricao + via UsePaid"}' --recorded-by sexta-feira

# 10. ARGUS +840 % na Arc (Circle) — trending #2 CoinGecko; zero clones na Solana as 19:1x UTC
uv run python infra/scripts/meme_event.py add --kind narrative \
  --title "ARGUS (Arc/Circle, Fomo App) +840 % em 24 h, mcap US$ 26,5 M, vol US$ 21,3 M; trending #2 CoinGecko; sem par ARGUS na Solana ainda" \
  --url "https://www.coingecko.com/en/coins/argus" --symbol ARGUS \
  --confidence confirmed --source plantao --observed-at 2026-09-16T19:04:00Z \
  --notes '{"chain":"arc","cg_rank":704,"chg24_pct":840.7,"solana_pairs_at_obs":0,"expect":"clones ARGUS no pump.fun em < 1 h","parent_event":"3 (Circle Arc mainnet)"}' --recorded-by sexta-feira

# 11. Viveiro "fundo/instituicao" desabando: WOTF -93 % com US$ 3,7 M de saida, KIBA -100 %; fabrica trocou de nome (WWR, FAIR, USDF)
uv run python infra/scripts/meme_event.py add --kind incident \
  --title "Viveiro 'fundo/instituicao' desabando: WOTF (8MUc) -65 % 1 h / -93 % 24 h com US$ 3,69 M de volume; KIBA -100 % (pump.fun ainda mostra US$ 283 M); novos nomes WWR/FAIR/USDF" \
  --url "https://api.dexscreener.com/tokens/v1/solana/8MUcwPafbMA432mTgRFM4vjD7kbKcmEiwjdpzmN8pump" --symbol WOTF \
  --confidence confirmed --source plantao --observed-at 2026-09-16T19:06:00Z \
  --notes '{"action":"avoid","mints":{"WOTF":"8MUcwPafbMA432mTgRFM4vjD7kbKcmEiwjdpzmN8pump","KIBA":"NBVhtLhFrCjghFE5EhmtA8pZKtzZFAr3frur8iBpump","WWR":"KrvPY4SS1TYv8c8dLu25K8Wn8NTLTAur9kCJkvKpump","FAIR":"QbPr1ponxN4J7ozvkdh1dNzqc4zgdkE1RGygHeKpump","USDF":"B6Jt8byfoWUB4dD5ZpZnxSp4SSfksycpaJZkVkPpump"},"clones":{"WOTF":6,"WOFI":5,"NTDA":4},"updates":"evento 8 (16h)"}' --recorded-by sexta-feira

# 12. ZEC #1 do trending CoinGecko (+19 %); narrativa privacidade sem clone meme na Solana ainda
uv run python infra/scripts/meme_event.py add --kind narrative \
  --title "Zcash #1 do trending CoinGecko: +19,3 % em 24 h, vol US$ 2,1 B; ZEC embrulhado na Solana fez US$ 11 M/24 h e US$ 907 k na ultima hora; sem clone meme ainda" \
  --url "https://api.coingecko.com/api/v3/search/trending" --symbol ZEC \
  --confidence confirmed --source plantao --observed-at 2026-09-16T19:04:00Z \
  --notes '{"wrapped_zec_solana":"A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS","vol24_usd":11046026,"vol1h_usd":906537,"expect":"clones ZCASH/PRIVACY no pump.fun"}' --recorded-by sexta-feira
```

## Ligações
`obsidian/02-MARKET/Eventos/2026-09-16-17h.md` (versão do vault) · `.claude/state/plantao-meme/eventos-2026-09-16-16h.md`
(corrida anterior) · `obsidian/11-KNOWLEDGE/KB-0100-evento-move-moeda-primeira-medida-16-09.md` · `obsidian/00-INBOX/Hipoteses-do-plantao.md`
(M-P49) · brutos desta corrida em `%LOCALAPPDATA%\Temp\claude\p17\` (não versionados)
