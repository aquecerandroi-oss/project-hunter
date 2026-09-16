# Plantão meme — o que mudou desde 17:25 BRT (16/09/2026, corrida 18h05)

Medido 16/09/2026 **18:00–18:06 BRT (21:00–21:06 UTC, `date -u` conferido; o nome do arquivo é a hora medida)**.
Intervalo desde a corrida anterior ("18h30", medida 17:19–17:23 BRT) e desde a leitura do baha (17:25 BRT): **~40 min**.
Só `urllib` em APIs públicas, sem navegador e sem WebSearch. **baha.com e X não foram lidos**: todo "post"/"anúncio"
abaixo é `reported`/`rumor`. Não repete os extratos anteriores: só o delta. SOL = US$ 98,25 (pump.fun `sol-price`, 21:02 UTC).

## Fontes desta corrida

| fonte | URL | resultado |
|---|---|---|
| DexScreener boosts / profiles | `token-boosts/top/v1`, `token-profiles/latest/v1` | 200 · 9 + 9 Solana |
| DexScreener pares | `tokens/v1/solana/{mints}` em **6 lotes de ≤ 10** (55 mints: top-8 e vigilância anteriores + novos das buscas/perfis/pump.fun) | 200 × 6, 53 com par |
| DexScreener busca | `latest/dex/search?q=` **48 + 37 termos** (xceo, xdoge, xcat, paid, hyped, dono, ily, luv, grok, mayday, plane, crash, c-17, kc-135, emergency, token2049, x money, elon, atkins, warsh, fed, southwest, streamlabs, usehyped, casinu, inutility, useless, manlet, wofi, argus, zcat, drv, fomo, toktip, tip, stream, spacex, memory, dream, xai, ethspain, singapore, nikki, frog, pad, cate, there is no meme, x ceo; 2.ª leva: toly, banger, kylie, clap, ishowspeed, speed, pokemon, there is no narrative, trabzon, starlink, backpack, rogue, openai, hugging, clarity, lame duck, dexerto, 34%, insider, notnow, streamer, donation, tip fees, ihy, ilu, i love you, anonymous, zcinu, …) | 200 × 85 |
| pump.fun | `coins?sort=market_cap` (50), `coins/currently-live` (50), `coins?sort=created_timestamp` (**150**, 2 fotos), `coins/{mint}` ×12 (2 × 404: mints Meteora), `sol-price` | 200 |
| CoinGecko trending | `search/trending` | 200 (15 moedas) |
| RSS CoinDesk (`-L`) / Cointelegraph / Decrypt / The Block | — | 200; **2 itens novos** desde 20:23 UTC |

## 1. O que mudou nas narrativas (17:25 → 18:0x BRT)

### N1 — Família X*/X Money: **as três gerações morreram**; a família UsePaid (`PAID*`) subiu; o único `GROK` vivo é uma moeda UsePaid "Fees to @grok"

| símbolo | mint | 17:2x BRT | **18:0x BRT (agora)** | leitura |
|---|---|---|---|---|
| `XDOGE` (2.ª ger., "vencedor" das 17:2x) | `7ecXbJWyEoieJtGiGuq5yDmkrWogo6wAzZHVteg2pump` | 300–329 k · 1,04 M/h · +200 % | **US$ 2,1 k · liq 2,4 k · −99,4 % 1 h** · 782 k/h de saída · 9 705 c × 9 545 v | **rug** 40 min depois de ser "o vencedor" — site + handle não protegeram, como no `XCat` |
| `XCEO` (3.ª ger., "personagem") | `AfMYNK2xf6rGVwf7w4iR5e8MnX4JiYGrx5THdg9Dpump` | 108–141 k · 6–7 c/v | **US$ 1,8 k · −98,5 % 1 h** · 242 k/h de saída · 4 928 c × 4 627 v | **rug** em < 1 h; a razão 6–7 c/v da 1.ª meia hora não previu nada |
| `XCat` (1.ª ger.) | `GFFVbGwi4g5YaJ6V1iLUrVQvgpZ5eM5NRWwS3uuVpump` | 2 k (rug) | 2 k · 15/h · 0 c × 301 v | consumado |
| `X` ×6 | `4XcoQq…` e irmãs | 3 k (curva) | idem | nunca saíram da curva |
| **`PAID`** (mãe UsePaid) | `98kfF7rmsg1QDUEoCqNE7g7M1FdrTt92TEp2CLzypump` | 8,51 M · 822 k/h · −12 % | **10,3–10,6 M** · **874–884 k/h** · 24 h 55,3 M · **+12 a +14 % 1 h** · 2 942 c × 2 869 v | virou: **+22 % em 40 min**; r0,19 |
| `PAIDDOGE` | `52qkNpgTHcjuDYhKVcg6rJS4uYYtJHpDRcJoSdKqpump` | 572 k · 483 k/h · −1 % | **821 k** · 497 k/h · **+66 % 1 h** · 6 053 c × 4 784 v · boost 500 | 2.ª perna |
| `PAIDLON` | `AowPHdsFTZNTa7JDGFUCRpyGa4niTS9GBG26CNWtpump` | 1,47 M · +56 % | **736 k** · 303 k/h · **−38 % 1 h** · 8 533 c × 1 486 v | devolveu a perna (pico ~17:3x) |
| **`GROK` "Grok Coin"** | `5A6CJfJfgupDh5J2s26NUisY5xwC6BpDAndDiye7tS5a` | (não medida) | criada **15/09 17:10 BRT** · descrição "**Fees to @grok**" · site `usepaid.app/t/cqryrcge` · X `x.com/grok` · mcap **102–104 k** · **162 k/h** · **+387 a +463 % 1 h** · 944 c × 785 v · liq 28 k | é a reação "GROK pós-baha" que dava para medir: **não nasceu moeda nova** com volume (135 `GROK` hoje, 0 na mesa); a que se mexeu é uma UsePaid de ontem que roteia taxa para @grok |
| `ELON` "Elon Coin" | `GY9mZfyPpxXxBXBxS2hB2XjhP3kfUsywTvgveozxpump` | 1,30 M · 137 k/h · −19,5 % | **2,06–2,21 M** · 359 k/h · **+50 a +67 % 1 h** · 1 863 c × 1 624 v · 24 h 15,4 M | virou junto com `PAID` (+70 % em 40 min); `CLAP` "Everyone claps for Elon" ×3 (21:01 UTC) a US$ 1–2 k |
| `KYLIE` "KYLIE COIN" (novo, 21:01:40 UTC) | `DVPUvLAoFjw5MRRhkYKtV8VuQyfHc1GiuLBivTHuNi4N` | — | "Payment to @KylieJenner. Fees to @kyliejenner" · site `usepaid.app/t/zk5hv453` · 2,9 k | UsePaid virou **ferramenta** de lançamento "taxa para celebridade" (`GROK`, `KYLIE`) — atualiza o evento 9, não é evento novo |

**Leitura:** o que a corrida anterior chamou de "vencedor" (`XDOGE`) e de "3.ª geração" (`XCEO`) morreu em ≤ 40 min; **0 de 3
gerações X\*** sobreviveu, todas com site + handle. Enquanto isso a família **produto** (`PAID` +22 %, `PAIDDOGE` +66 %, `ELON`
+70 %) virou para cima na mesma janela em que o Dow fechou −900 (baha 17:25). A notícia SpaceXAI/Grok (baha) **não gerou
moeda nova com volume**; o `GROK` que subiu é uma UsePaid de ontem. Atualiza os eventos 13 (X*) e 9 (UsePaid) e o evento
baha "Grok memória"; **não é evento novo**.

### N2 — Produto "taxa para streamer": **`DONO` ganhou (×13), `HYPED` colapsou (−88 %)** — o M-P54 acertou a mãe com giro 20× e errou a com giro 10×

| símbolo | mint | 17:2x BRT | **18:0x BRT (agora)** | leitura |
|---|---|---|---|---|
| **`DONO`** (mãe, dono.you) | `9HB7uiNQeWTGG1tkuGaMQLhdt9Lg6vmJ4vtLJc1Wpump` | 52–86 k · 593–618 k/h · c/v 1,09 | **803–920 k** · liq 81–87 k · **1,65–1,79 M/h** · 24 h 2,24 M · **+808 % 1 h** · **11 425 c × 9 409 v** · pump.fun mcap 909 k | **maior volume real da Solana na hora**; ×13 em 40 min; r0,36; c/v ainda 1,2 |
| `DONO` 2.ª mint (mesmo handle/site, outro criador `2EaWBQ…`) | `EmFbxtejRXZrZFtNChFVgrunrzkFAQdmZv1Lc5N4pump` | — | criada **17:51:10 BRT** · graduou · **299–331 k** · liq 44 k · 64 k/h · **4 945 c × 4 636 v** · +630 % | mesmo molde da `Hyped` `22sGuG…` (2.ª mint oficial?) que morreu −99,5 %; a vigiar |
| `DONO` clone | `63bRB7qzqp4aYQWv27zbB87ATX2tqLo39aYSi846DSng` | 21 k · liq 0 | 21 k · liq 0 · 230 k/h | fantasma |
| `DONO` clones Meteora ×3 + `9Eiw1T…` | — | −100 % | −100 % / −99,9 % | mortos |
| **`HYPED`** (mãe, usehyped.app) | `G2KDX81e31T6pZbkrJLPKAXqKcd8VoE3UEp83rRtpump` | 324 k · 6,35 M/h · giro 19,6× | **72–73 k · −88 % 1 h** · 900 k/h · 6 862 c × 6 025 v · liq 26 k | colapsou **−78 % em 100 min** — exatamente o que o M-P54 previa para giro ≥ 10× |
| `Hyped` 2.ª mint | `22sGuG5aT5Wac2zxkiADSsHdTfEVt4rFn3EzYdiLpump` | 297–319 k · 5,5 c/v | **1,9 k · −99,5 %** · 229 k/h de saída | rug |
| `HYPED` clones fantasmas | `Hh4QQE…` (liq **US$ 49**), `8Qx8av…` (liq 0), `E1AojAk…` (mcap 2,54 M, liq **US$ 65**) | 1,35–1,48 M/h | **1,41 M/h · 1,12 M/h · 149 k/h** | somam 2,7 M/h de "volume" com < US$ 100 de liquidez — o fantasma continua |
| `HYPED` novo | `DZfDnVyPRiHBsMbsFYZf5CZs33xRuUQJKizBpgwMVXAy` (Meteora, 17:40 BRT) | — | 547–558 k · liq 21 k · 127–146 k/h · 2 880 c × 1 467 v | clone com liquidez de verdade; sem social |
| `TOKTIP` (candidata das 17:46, Candidatas 17h56) | `2oiz6gE2N4mEqSnVoLCcWtHRgHYm3hS8kQ2qJqTSpump` | 151 k (pico 17:52) | **3,5 k** · 54 k/h · 771 c × 609 v | morta, como a descarga de 10 SOL em 15 s já dizia |

**Leitura (honesta):** o M-P54 dizia "mãe com giro ≥ 10× colapsa ≥ 70 % em ≤ 2 h". `HYPED` (19,6×) **colapsou −78 %**: acerto.
`DONO` (618 k ÷ 62 k = **10×**, c/v 1,09) **subiu ×13**: erro. Com c/v ≈ 1 nas duas, o que as separou **não foi o giro** — foi
(a) a **família de clones**: os clones `HYPED` sem liquidez somavam mais "volume" que a mãe (4 × 0,9–1,5 M/h com liq < US$ 100),
os clones `DONO` morreram −100 % na 1.ª hora; e (b) o **volume absoluto** da 1.ª hora (6,35 M vs 618 k). Vira a hipótese
**M-P55** (INBOX). Atualiza o evento 16; **não é evento novo**.

### N3 — `ILY` "there is no meme": 2.ª onda de clones com volume real, a frase virou **molde** ("there is no narrative / no stocks / no inu"); o `LUV` de caixa alta é uma **ação tokenizada** (Southwest, "Backpack Securities"), não meme

| símbolo | mint | criado (BRT) | mcap | vol 1 h | c/v 1 h | leitura |
|---|---|---|---|---|---|---|
| **`LUV`** | `LUV9GB51PNZNRyzzyYK3rtqFfvDvWtRiXZ34wVq2HrX` | 17:05 (Raydium) | 251–261 k · liq 92–99 k | **1,25–1,29 M/h** | 7 977 c × 7 737 v | nome do token: **"Southwest Airlines Co. - Backpack Securities"** — é (ou se diz) ação tokenizada `$LUV`; −30 % 1 h; **sai do funil de meme**; explica a co-rajada "Southwest/Starlink WIFI" das 17:1x |
| **`ILY`** (2.ª onda, vencedora até agora) | `BKvMvSYuwX7rhRZgR26Ejk4k84RNt8CZnew2xV1VJCcX` | **17:41** (PumpSwap) | **41–52 k** · liq 40–45 k | **924 k → 1,05 M/h** | 4 222–4 465 c × 1 737–1 921 v | +394 a +516 % 1 h; **giro 20× o mcap** (régua M-P54: suspeito) |
| `ILY` fantasma | `FsVBGBn54yaYz4LqzxWXCFRFCuogyBkd1ioMS82T26Dt` | 17:42 (Meteora) | 92 k · liq **US$ 50** | 1,19 M/h | 4 894 c × 2 150 v | volume sem liquidez |
| `ILY` (mais nova) | `FjP8DwXCyqATz1668S46N9gm86FUEZExZEg5xmxavG1s` | **17:55** (Meteora) | 66–121 k · liq 36–49 k | 386 → 589 k/h | 2 036 c × 1 252 v | +1 200 % em 10 min; giro 9× |
| `ILY` | `29QCwk3jS6V6eQoJRZ5KAdS6fLvCenJaTW18KnAUgiyS` | 17:34 (Raydium) | 24–29 k | 213 k/h | 1 463 c × 1 191 v | −45 % 1 h |
| `ILY` forjada (evento 17) | `6LDU8HoZ3oAJ2hxvYADh8boWmEZV3sfyUb5TyC5Rpump` | 17:18 (encheu no minuto) | 124–138 k | 139 k/h | 1 158 c × 1 056 v | **−69 % 1 h** — a forjada caiu, como a KB-0103 diz |
| `ILY` FluxBeam | `BvzonSZ2…`, `5F9Hsu…` | 17:44 / 18:01 | 660 k / 212 k "nominal" · liq = mcap | 4 k / 0,7 k | 144 c × **0 v** / 25 × 0 | forjadas (liq nominal, zero vendas) |
| `ily` `@grok12_john` | `9tr7cj1XSEztEFK5zZpivjhKS1s1eWK4sN1PWqcKpump` | 17:15 | 2,8 k | 14 k | — | −99,7 % (Candidatas 17h56: 200 compradores, devolveu 36,7 SOL) |
| `ILY` "there is no meme" | `CBufshjEPb7hMJEMqDiSLnFEDHGJCNo4YYos94fQ6o9d` | 17:53 (Raydium) | 62 k · liq 20 k | 22 k | 166 × 108 | site `oldschoolpump.fun` + status `2100327266790375572` (não lido) |
| **paródias do molde** | `IHY` "there is no narrative" `FxnLSM…` (21:01 UTC), `ihy` "there is no narrative i hate you" `CCGnrr…`, `IHY` "there is no meme, I hate you" `AEHeMy…`, `ily` "there is no stocks, i love you" `7gJsGH…`, `LUV` "There Is No Ceiling, I Luv U" ×2, **`ZINU`** "there is no inu, no socials, zec rewards" `HuDwEgKxqBLNKHBSFiVh8o5tdfzSBmhKochDqRFYCzVf` (StonkFun, 17:53, **95 k · 64 k/h · 501 c × 367 v**, perfil DexScreener) + clone `ZCINU` | 17:2x–18:02 | 2–95 k | 0,7–64 k | — | a frase virou **template** e cruzou com o ZCAT (`ZINU`) |

**Leitura:** a rajada das 17:15–17:21 (28 clones) teve **2.ª onda** com liquidez real (`BKvMvS…` 1,05 M/h, `FjP8Dw…` 589 k/h),
mas as duas têm giro de 9–20× o mcap e mcap ≤ 120 k — o padrão `HYPED`, não o `DONO`. A forjada (`6LDU`) caiu −69 %.
O `LUV` que estava no top-8 anterior como "frase viral" é, pelo nome, **ação tokenizada da Southwest** — se sai do funil, o
"caixa alto sem social" fica explicado. O gatilho da frase **continua não lido** (post `@thedevrrrrrrr`; agora também status
`2100327266790375572`). Atualiza o evento 17; **não é evento novo**.

### N4 — **NOVO** — `ISHOWSPEED`/`SPEED`: 16 pares em < 3 h, 3 com 150–530 k/h, cruzando com a narrativa "taxa para streamer"

| símbolo | mint | criado (BRT) | mcap | vol 1 h | c/v 1 h | leitura |
|---|---|---|---|---|---|---|
| **`SPEED`** "ISHOWSPEED" | `8bFvxaMqvf3kxNtuZwgiD4Sw8iqj6SWGonn3wvRwLMgY` | **17:37** (PumpSwap) | **159 k** · liq 32 k | **526 k** | **4 370 c × 3 587 v** | +291 % 1 h; sem site/handle; r0,3 |
| `SPEED` | `FcDCPsm6omSRL87XYVnauf89bUbLpTKqqGDU7GdgePK9` | 17:50 | 13 k · liq 21 k | 220 k | 2 768 c × 960 v | +47 % |
| `SPEED` | `5BND2qjQMnm3jsnrsegiUA6Si3yNaNxX1N6qVbr12QG7` | **18:00** (Meteora) | 111–123 k · liq 47–50 k | 156–167 k | 854–947 c × 252–274 v | +1 200–1 350 % em 5 min; 3,4 c/v |
| `speed` | `7grU4BDCa8a4YMyQfiEq6SFqLq54ZwpqB27q3v5oiikY` | 16:5x | 90 k · **liq 0** | 210 k | 969 × 434 | fantasma |
| `SPEED` | `9nrUsqcEPptS3gXQ1RJdHza1wQtAjuP6wqKWW2gdMBkh` | 16:3x | 5 k | 40 k (24 h 553 k) | — | **−82 % 1 h**: a 1.ª onda já morreu |
| `SPEED` pump.fun ×5 | `oYzWNe…` (−87 %), `C7DZ29…`, `4Tdoz…`, `9CMbjW…` ("ISHOWSPEED BLOWING UP", 21:01 UTC), … | 16:5x–18:01 | 1–3 k | 0,7–7 k | — | ruído |
| ligação com `DONO` | clone `DONO` `FxauBC…`/`CAkQYq…` (18:00 BRT) | — | 2,8 k | — | — | descrição: **"yes lets give speed $100"** — a tese "taxa para streamer" apontou para o Speed |

**Leitura:** 16 pares `ISHOWSPEED` em < 3 h (11 na busca `speed`), com **três** de liquidez real e volume de 150–530 k/h,
nenhum com site/handle, e a 1.ª onda (16:3x) já −82 %. O gatilho (live/evento do IShowSpeed?) **não foi lido** — só a
descrição "BLOWING UP" e o clone `DONO` "give speed $100". É o cruzamento **streamer-meme × app de taxa para streamer**.
**Evento novo 18** (`viral_post`, `rumor`).

### N5 — MAYDAY / avião militar (baha 17:25): **não virou moeda nem notícia**
`mayday` **0 pares**; `plane` 1 ("This will fly", US$ 0); `crash` 1 ("Helicopter", 2 h, US$ 0); `c-17`, `kc-135`, `emergency`: 0.
Nenhuma das 4 redações cripto mencionou o avião até 21:05 UTC (não é o assunto delas; baha não relido). Sem sinal de que virou
acidente. **Rebaixar de "observar 2 h" para registro**; se virar acidente, o ticker aparece na próxima corrida.

### N6 — Viveiro "fundo/instituição": **2.º rug `WOFI` do dia** e um `WOFI` novo a 746 M nominal em 34 min
| símbolo | mint | 17:2x | **18:0x** | leitura |
|---|---|---|---|---|
| **`WOFI`** (novo, #1 do top-50) | `9HXERDkXzAN8PiipookZAr7Wt99ENP1Z8tHT7Fvrpump` | — | criado **17:32 BRT** · graduou · **741–746 M nominal** · liq 2,28 M · **1,16 M/h** · 2 123 c × 1 331 v · +1 825 701 % | mesma fábrica (4.º `WOFI` do dia no top-50); c/v 1,6 desta vez, não 31:1 — mudou a assinatura, não o molde |
| `WOFI` `Cf7n…` | `Cf7ng2asfjXWDHVBvMbtbwdrHcx6sHF6p3tWVFqNpump` | 436–438 M · +17 % | **US$ 1,7 k · −100 %** · 903 k/h de saída · 1 229 c × 2 477 v | **2.º rug `WOFI` do dia** (depois do `Fxnc…`) |
| `WOFI` `YuEF…` | `YuEFCTBvg8WgiZrgTS59fZMSKmXtSeVGS2qV6m4pump` | 674 M · 1,09 M/h | 695 M · 61 k/h · 3 088 c × 63 v | giro acabou; 49:1 |
| `WOFI` `6AUU…` (Raydium) | `6AUUVNHE8et7kswzpcqV75rLgLABQDUegWJqQHPBUmrS` | 25 M · 89 k/h | 25,2 M · 164 k/h · 1 339 c × 1 168 v | de pé |
| `MANLET` | `5zWpGv4stDyPAeRTU6jPq45r7NzGRLMJ8RzBhP71pump` | 24,7 M · 201 k/h | 25,8 M · **22 k/h** · 3 186 c × 125 v | flat, 25:1 |
| `FM` "Fomo Market" | `tHrxWrwCRGSPJk9zzxxXcWsfnU1Kg6fCaJGPiYdpump` | 40–84 k | **2,9 k · −93 %** | forjada morreu (KB-0103) |

Top-50 por mcap às 18:0x: `WOFI` ×6, `WOTF` ×5, `NTDA` ×4, `ECTF` ×2, `DANGR` ×2, `USDF` ×2 + `MANLET`, `COINISM`, `TNT`, `USWR`,
`USGR`, `GOAF`, `FAIR` = **~27 de 50** (era 21 + 5). Atualiza o evento 11; **não é evento novo**.

### N7 — ZEC / privacidade: `ZCAT` **voltou** ao trending (#11) e cruzou com o molde "there is no meme" (`ZINU`)
- CoinGecko trending 18:0x: #1 `ARGUS` (+604 %, mcap 19,8 M — caindo de 24,1 → 21,5 → 19,8 M), **#2 `DRV`** (+38 %, subiu de #4), #3 `TRUMP`,
  **#4 `ZEC`** (+17,6 %, vol 2,15 B), **#5 `ARB` (+11 %, novo)**, #6 `BTC`, **#7 `NEAR` (+11 %, novo)**, **#8 `LSK` Lisk (+81 %, novo)**, #9 `PONS` (−11,5 %),
  #10 `HYPE`, **#11 `ZCAT` (+9,7 %, voltou)**, #12 `ENA`, #13 `PENGU`, **#14 `BR` Bedrock (+150 %, novo)**, #15 `ARC`. Saíram: `LIT`, `STONK`, `USELESS`.
- `ZCAT` `HcRLc9…`: 102–107 M, **+9 a +13 % 1 h** (era −8,5 %), 137 k Meteora + 93 k Raydium; `5XZCAT` (3 d) 208 k · 68 k/h · +121 %;
  **`ZINU`** "Anonymous Inu — there is no inu, no socials, zec rewards" `HuDwEg…` (StonkFun, 17:53 BRT) 95 k · 64 k/h · 501 c × 367 v (perfil DexScreener) + `ZCINU` clone (21:01 UTC).
- ZEC embrulhado `A7bdiY…`: 367 k/h (era 637 k), +2 %. `REVOLUT`/`monero`/`privacy`: **nada novo** (CoinDesk 19:07 UTC confirmou o pedido de US$ 3 M em Monero; 0 moedas em 2 h). `ARGUS`: 0 pares Solana (3 h).

### N8 — Animais / posts pequenos / o resto
| símbolo | mint | 17:2x | **18:0x** | leitura |
|---|---|---|---|---|
| `casinu` | `2eMoMqs194VxPHSWtCCzkBGqwCUbD4ZcqhecoGuh4tTp` | 202–205 k · 369 k/h | 204–206 k · 283–296 k/h · **+6 % 1 h** · 4 052 c × 1 823 v · boost **600** | flat (segurou o vale); boost subiu 500 → 600 |
| `INUTILITY` | `FkDqBb1Vz6iZH9aSD5RBV5ctPQGrF2Ye6NVJ4sXncYMF` | 176–202 k · 337–346 k/h | **228–233 k** · 260–265 k/h · **+175 a +188 % 1 h** (trailing) · 1 133–1 189 c × 939–963 v | de pé; `USELESS` saiu do trending |
| `CATE` | `Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump` | 74,7 M · 490 k/h | **76,7–77,8 M** · 408–418 k/h · +4,8 % | orgânico do dia segue |
| `PAD` "Poor Autistic Degen" (novo, 17:49) | `9u8Y7jbGJHdFzwhzQ6Vbu8qCdKAA2ZEV1WfTt26Ypump` | — | 3,5 k (curva) · **101 k/h** · 1 560 c × 1 417 v | cluster "pad" continua (`pad` `C4Dtzu…` 94 k/h, −47 %) |
| `NIKKI` | `GxoppHqopqWPHAMzAw9QsbjyPzRwHUG5TNzvcjB7pump` | — | 17:20 · 8,6 k (curva) · 48 k/h · +208 % | a "NIKKI" do cenário II da KB-0115 é outra (`AYrp8o…`, 2,8 k) |
| `pillfly` (perfil) | `CwZn8XcUKZnSHWPDnk2BYvcG4McETwzzYqgj139Wpump` | — | 17:55 · 66 k · 44 k/h · site + X | pequeno |
| `LIFE3` (perfil) | `3tNhMJ3sQA4VdYZDpw7HEiJ4Sc8UNGk8LmHce5N1cvYH` | — | 16:4x · 28 k · 10 k/h · "SPCXX, TSLAX, NVDAX" | narrativa "ação tokenizada" também aqui (ver `LUV`) |
| posts pequenos (21:00–21:05 UTC, 150 moedas em 296 s = **30,4/min**) | `BANGER` ×2 ← post `@toly` `2100329222330102240`; `BROS` ×5 ← `@wearetheretail`; `CLAP` ×3 "Everyone claps for Elon"; `Trabzon` ×5; `34%` ×3 ("clubman34%"); `notnow.fun` ×3; `@bountypackclub` ×7; `Clarity Cat`, `clarity cow` (16 k/h); `Pokemon Unite` "relaunch Switch 2" | — | todos ≤ 8 k; **1 de 150 nasceu cheia** (`FLOOR` `2yHjnj…`, FloorFunPad) | ruído; o post do toly não gerou nada acima de 3 k |
| `FED`/`WARSH`/`ATKINS`/`TOKEN2049`/`ETHSPAIN` | — | US$ 0–3 k | idem (`FED` `5Ng8zE…` −92 %) | continua zero |

## 2. Top 8 Solana por volume real na última hora (18:0x BRT; excluídos rugs em saída, fantasmas sem liquidez e viveiro)

`r` = mcap ÷ vol 24 h. Fora: `HYPED` `Hh4Q…` 1,41 M/h (liq US$ 49), `ILY` `FsVBGB…` 1,19 M (liq US$ 50), `WOFI` `9HXERD…` 1,16 M (viveiro),
`HYPED` `8Qx8…` 1,12 M (liq 0), `WOFI` `Cf7n…` 903 k (saída, −100 %), `HYPED` `G2KDX…` 900 k (saída, −88 %), `XDOGE` 782 k (saída, −99,4 %),
`XCEO` 242 k (−98,5 %), `DONO` `63bR…` 230 k (liq 0), `Hyped` `22sG…` 229 k (−99,5 %), `speed` `7grU…` 210 k (liq 0), `FM` 129 k (−93 %).

| # | símbolo | mint | idade | mcap | vol 1 h | c/v 1 h | narrativa | marca |
|---|---|---|---|---|---|---|---|---|
| 1 | **`DONO`** | `9HB7uiNQeWTGG1tkuGaMQLhdt9Lg6vmJ4vtLJc1Wpump` | 2,2 h | US$ 803–920 k | **1,65–1,79 M** | 11 425/9 409 | produto: taxa → streamer (dono.you) | real (r0,36); site + X; +808 % 1 h; graduada (fora da mesa, T4.18) |
| 2 | `LUV` | `LUV9GB51PNZNRyzzyYK3rtqFfvDvWtRiXZ34wVq2HrX` | 1,0 h | 251–261 k | **1,25–1,29 M** | 7 977/7 737 | **ação tokenizada** "Southwest — Backpack Securities" (pelo nome) | não é meme; Raydium, liq 99 k, sem social; −30 % 1 h |
| 3 | `ILY` | `BKvMvSYuwX7rhRZgR26Ejk4k84RNt8CZnew2xV1VJCcX` | 0,4 h | 41–52 k | **0,92–1,05 M** | 4 465/1 921 | frase "there is no meme, ily" (2.ª onda) | **suspeito**: giro 20× o mcap (padrão `HYPED`); liq 45 k; +516 % |
| 4 | `PAID` | `98kfF7rmsg1QDUEoCqNE7g7M1FdrTt92TEp2CLzypump` | 26 h | 10,3–10,6 M | **874–884 k** | 2 942/2 869 | UsePaid (mãe) | real (r0,19); **+12 a +14 % 1 h**; graduada |
| 5 | `ILY` | `FjP8DwXCyqATz1668S46N9gm86FUEZExZEg5xmxavG1s` | 0,2 h | 66–121 k | **386–589 k** | 2 036/1 252 | idem (3.ª mint com liquidez) | suspeito: giro 9×; +1 200 % em 10 min |
| 6 | **`SPEED`** | `8bFvxaMqvf3kxNtuZwgiD4Sw8iqj6SWGonn3wvRwLMgY` | 0,5 h | 159 k | **526 k** | 4 370/3 587 | IShowSpeed (novo, N4) | real (r0,3); sem social; +291 % |
| 7 | `PAIDDOGE` | `52qkNpgTHcjuDYhKVcg6rJS4uYYtJHpDRcJoSdKqpump` | 2,7 h | 821 k | **497 k** | 6 053/4 784 | UsePaid × Doge | real (r0,45); +66 % 1 h; boost 500; site + X + TG |
| 8 | `CATE` | `Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump` | 52 d | 76,7 M | **408–418 k** | 675/822 | animal | real (r12); referência |

Logo abaixo: `ZEC` embrulhado 367 k, `ELON` 359 k (+67 %), `PAIDLON` 303 k (−38 %), `casinu` 283–296 k (+6 %), `INUTILITY` 260 k (+188 %),
`SPEED` `FcDC…` 220 k, `ILY` `29QC…` 214 k (−45 %), `GROK` 162 k (+387 %), `SPEED` `5BND…` 156–167 k (+1 300 %), `HYPED` `DZfD…` 146 k, `ILY` `6LDU` 139 k (−69 %),
`ZCAT` 137 k Meteora + 93 k Raydium (+9–13 %), `PAD` 101 k, `pad` 94 k, `ZINU` 64 k, `DONO` `EmFb…` 64 k.
**Três dos oito são "taxa para streamer/UsePaid"** (`DONO`, `PAID`, `PAIDDOGE`), dois são a frase `ILY`, um é streamer (`SPEED`) — e o `LUV`
sai da conta de meme. Trocou o "vencedor" de tema (HYPED → DONO), não o tema.

## 3. Notícias das últimas 2 h (19:00–21:06 UTC) e agenda de hoje à noite / 17/09 (BRT)

| hora (BRT) | fonte | item | meme em 24 h? |
|---|---|---|---|
| **17:51** | Cointelegraph | **Clarity Act pode ter nova chance na sessão "lame-duck"**, diz advogado de política (novo) | não — `clarity cow` `AAq9pt…` 16 k/h (curva), `Clarity Cat` 21:01 UTC a 3 k; `lame duck`: 0 |
| **17:31** | Decrypt | **Agentes de IA "rebeldes" da OpenAI sondaram o Hugging Face 2 meses antes do hack** (novo) | não — `rogue`/`openai`/`hugging`: 0 pares novos; potencial "AI rogue agent" ainda sem moeda |
| 17:02 | The Block | BTC/ETH oscilam após alta de 25 bp; Warsh mira a inflação (já nas 17:2x) | não (`WARSH` ×2 a 2,7 k) |
| 16:43 | Decrypt | Warsh: Trump "só meio certo" (já registrado) | não |
| 16:07 | CoinDesk | Revolut/Monero US$ 3 M (evento 15; confirmado no RSS às 19:07 UTC) | **não em 2 h** (0 moedas) |
| 15:01 | Cointelegraph | Comitê tributário da Câmara aprova reforma cripto 38–5 | não |

CoinDesk sem item novo depois de 19:07 UTC; The Block depois de 20:02; Decrypt 20:31 e Cointelegraph 20:51 são os únicos novos.
**Nenhuma** das 2 notícias novas virou moeda; o fluxo de 18:0x veio de **um app** (`DONO`), **uma frase** (`ILY`) e **um streamer** (`SPEED`).
Trending CoinGecko: 4 entradas novas de mid-cap (`ARB`, `NEAR`, `LSK` +81 %, `BR` +150 %) — nenhuma com paródia Solana; `ZCAT` voltou.

**Agenda (BRT):** hoje **22:00** — **TOKEN2049 Singapura dia 2** abre (fuso +8; anúncios entre a madrugada e a manhã de 17/09 BRT;
`token2049` 1 par, US$ 0; `singapore` 2 pares velhos); **17/09 manhã** — ETHSpain Barcelona (0 pares) e EBC12 dia 2; 17/09 — pós-Fed (dado
de moradia/pedidos de auxílio 09:30 BRT, sem meme); 18/09 — triple witching EUA. `usehyped.app` / `dono.you` sem data pública (sites não lidos);
claims da UsePaid seguem sem cronograma público.

## 4. Três termos de vigilância (próximas 2 h)

| termo | por quê (medido agora) |
|---|---|
| **`DONO` / `dono.you` / "gift fees" / 2.ª mint `EmFbxte…`** | vencedora da narrativa de produto (803–920 k, 1,79 M/h, +808 %); vigiar (a) se segura > 500 k na próxima hora com c/v 1,2 ou faz o `XDOGE` (−99 % em 40 min); (b) se a 2.ª mint (`EmFb…`, mesmo handle, outro criador) repete a `Hyped` `22sG…` (−99,5 %); (c) clones novos com liquidez real (`DZfD…` do `HYPED` tem 21 k) |
| **`ISHOWSPEED` / `SPEED`** | 16 pares em < 3 h, 3 com liq real e 150–530 k/h, todos sem social, 1.ª onda já −82 %; gatilho não lido — se aparecer uma mint com handle/site, é a mãe; cruza com `DONO` ("give speed $100") |
| **`ILY` / "there is no …" (molde) / `ZINU`** | 2.ª onda com liquidez (`BKvMvS…` 1,05 M/h a 52 k; `FjP8Dw…` 589 k/h a 66–121 k), giro 9–20× = padrão `HYPED`; o molde já gerou `IHY`/"no stocks"/`ZINU` (95 k, cruzando com ZCAT) — teste ao vivo do M-P55: se as `ILY` com irmã fantasma (`FsVBGB…` 1,19 M/h, liq 50) colapsarem e a `ZINU` (sem fantasma) segurar, a hipótese ganha um ponto |

**Rebaixado:** família `X*` (3 de 3 gerações mortas — `XCat`, `XDOGE`, `XCEO` a −98/−99 %), `HYPED` (mãe −88 %, só clones fantasmas),
`MAYDAY`/avião (0 moedas, sem notícia), `GROK` (só a UsePaid de ontem, 162 k/h — registro), `LUV` (ação tokenizada, sai do funil),
`TOKTIP` (morta). **Não vigiar (medido):** `ARGUS` (0 pares, 3 h), `FED`/`WARSH`/`CLARITY`/`TOKEN2049`/`ETHSPAIN` (≤ 16 k), `pad`/`PAD`/`NIKKI` (curva),
posts `@toly`/`@wearetheretail` (≤ 3 k); `WOFI`/`WOTF`/`NTDA`/`ECTF`/`MANLET`/`FM` só como exclusão (KB-0103).

## 5. Linhas `meme_event.py add` — só evento NOVO (18; dry-run; `--apply` na VPS; sem `--mint`, mint em `--notes`)

Os eventos 9, 11, 13, 15, 16, 17 e os três do baha (SEC/Atkins, Grok memória, avião) **não se repetem**; ganham nota:
9 → "UsePaid como ferramenta: GROK Coin 'Fees to @grok' (usepaid.app/t/cqryrcge) +387 % 18:0x; KYLIE 'Fees to @kyliejenner' 21:01Z";
11 → "WOFI 9HXERD 17:32 BRT 746 M nominal 1,16 M/h; WOFI Cf7n −100 % (2.º rug WOFI); FM −93 %";
13 → "XDOGE −99,4 % e XCEO −98,5 % às 18:0x — 3 de 3 gerações X* mortas; PAID +12 %, ELON +67 %";
15 → "0 moedas em 2 h após confirmação CoinDesk 19:07Z; ZCAT voltou ao trending #11; ZINU 'zec rewards' 95 k";
16 → "DONO 9HB7ui 803–920 k, 1,79 M/h, +808 % (×13); HYPED G2KDX −88 %; Hyped 22sG −99,5 %; DONO 2.ª mint EmFbxte 17:51 BRT 331 k; TOKTIP 3,5 k";
17 → "2.ª onda ILY: BKvMvS 1,05 M/h a 52 k, FjP8Dw 589 k/h; 6LDU forjada −69 %; LUV9GB = 'Southwest Airlines Co. - Backpack Securities' (ação tokenizada, sai do funil); molde 'there is no …' → IHY/ZINU";
baha-Grok → "sem moeda nova; GROK Coin 5A6CJf (UsePaid, 15/09) 162 k/h +387 %"; baha-avião → "MAYDAY 0, plane/crash US$ 0, sem notícia nas 4 redações até 21:05Z".

```bash
# 18. ISHOWSPEED: 16 pares SPEED em < 3 h (17:37–18:01 BRT), 3 com liquidez real e 150–530 k/h, nenhum com social; 1.ª onda (16:3x) já −82 %; cruza com DONO ("yes lets give speed $100")
uv run python infra/scripts/meme_event.py add --kind viral_post \
  --title "ISHOWSPEED: 16 pares SPEED em < 3 h, 3 com liquidez real (8bFvxa 526 k/h a 159 k, +291 %; FcDCPs 220 k/h; 5BND2q 167 k/h +1 300 % em 5 min), todos sem site/handle; 1.a onda 9nrUsq -82 %; clone DONO 'yes lets give speed $100'; gatilho nao lido" \
  --symbol SPEED --confidence rumor --source plantao --observed-at 2026-09-16T21:05:00Z \
  --tickers SPEED,ISHOWSPEED --keywords ishowspeed,speed \
  --notes '{"mints":{"SPEED_lead":"8bFvxaMqvf3kxNtuZwgiD4Sw8iqj6SWGonn3wvRwLMgY","SPEED_2":"FcDCPsm6omSRL87XYVnauf89bUbLpTKqqGDU7GdgePK9","SPEED_3":"5BND2qjQMnm3jsnrsegiUA6Si3yNaNxX1N6qVbr12QG7","speed_ghost":"7grU4BDCa8a4YMyQfiEq6SFqLq54ZwpqB27q3v5oiikY","SPEED_wave1_dead":"9nrUsqcEPptS3gXQ1RJdHza1wQtAjuP6wqKWW2gdMBkh"},"pairs_lt3h":16,"vol1h_usd":{"SPEED_lead":526453,"SPEED_2":219782,"SPEED_3":167417,"speed_ghost":210304},"mcap_usd":{"SPEED_lead":158853,"SPEED_2":12633,"SPEED_3":122568},"liq_usd":{"SPEED_lead":32434,"SPEED_2":21137,"SPEED_3":49622,"speed_ghost":0},"buys_sells_1h":{"SPEED_lead":"4370/3587","SPEED_2":"2768/960","SPEED_3":"947/274"},"created_brt":{"SPEED_lead":"17:37","SPEED_2":"17:50","SPEED_3":"18:00"},"socials":"none on the 3 with liquidity","cross_narrative":"DONO clone FxauBC/CAkQYq description: yes lets give speed $100 (evento 16)","description_seen":"ISHOWSPEED BLOWING UP (9CMbjW, 21:01Z)","trigger_read":false,"sources":["https://api.dexscreener.com/latest/dex/search?q=ishowspeed","https://api.dexscreener.com/latest/dex/search?q=speed","https://frontend-api-v3.pump.fun/coins?sort=created_timestamp&order=DESC&limit=50"]}' \
  --recorded-by sexta-feira
```

## Ligações
`obsidian/02-MARKET/Eventos/2026-09-16-18h05-brt.md` (versão do vault) · `.claude/state/plantao-meme/tendencias-2026-09-16-18h30-brt.md`
(corrida anterior, medida 17:19–17:23 BRT) · `.claude/state/plantao-meme/baha-2026-09-16-1725.md` (baha 17:25 BRT) ·
`obsidian/03-TRADING/Meme/Candidatas/2026-09-16-17h56-brt.md` §4–§5 (vigilância 0 de 6; TOKTIP) · `obsidian/11-KNOWLEDGE/KB-0103-*.md`, `KB-0115-*.md` ·
`obsidian/00-INBOX/Hipoteses-do-plantao.md` (M-P55) · brutos em `%LOCALAPPDATA%\Temp\claude\p18\` (não versionados)
