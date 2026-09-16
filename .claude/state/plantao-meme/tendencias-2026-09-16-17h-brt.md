# Plantão meme — o que mudou desde 16:1x BRT (16/09/2026, corrida das 17h BRT)

Medido 16/09/2026 **16:38–16:42 BRT (19:38–19:42 UTC, `date -u` conferido)**, só por `curl` em APIs públicas, sem
navegador e sem WebSearch. **baha.com e X não foram lidos** (baha só pelo Chrome do Everton; X bloqueado): todo
"post"/"anúncio" abaixo é `reported`/`rumor`. Nota de relógio: os dois extratos anteriores foram rotulados "16h" e
"17h" mas mediram **15:39–15:58** e **16:04–16:12 BRT**; este mede 16:38–16:42 BRT — o intervalo real desde a última
leitura é de ~30 min. Não repete os extratos anteriores: só o delta. SOL = US$ 97,89 (pump.fun `sol-price`, 19:38 UTC).

## Fontes desta corrida

| fonte | URL | resultado |
|---|---|---|
| DexScreener boosts / profiles | `token-boosts/top/v1`, `token-profiles/latest/v1` | 200 · 10 + 11 Solana |
| DexScreener pares | `tokens/v1/solana/{mints}` em **13 lotes de ≤ 10** (126 mints: 23 do extrato anterior + boosts/perfis + 100 do pump.fun top/ao vivo) | 200 × 13, 116 tokens com par |
| DexScreener busca | `latest/dex/search?q=` paid, usepaid, argus, zcash, zec, privacy, wotf, wofi, token2049, fed, "x money", elon, zcat, "anonymous cat", xcat, xdoge, trailcam | 200 × 17 |
| pump.fun | `coins?sort=market_cap` (50), `coins/currently-live` (50), `coins?sort=created_timestamp` (50), `sol-price` | 200 |
| CoinGecko trending | `search/trending` | 200 (15 moedas) |
| RSS CoinDesk (com `-L`; a URL crua devolve 308) / Cointelegraph / Decrypt / The Block | — | 200; 4 itens novos desde 18:15 UTC |

## 1. O que mudou nas narrativas (16:1x → 16:4x BRT)

### N1 — PAID / UsePaid: a mãe esfria, os derivados **reviveram** e a onda trocou de nome para `X*`

| símbolo | mint | 16:1x BRT (extrato anterior) | **16:4x BRT (agora)** | leitura |
|---|---|---|---|---|
| `PAID` | `98kfF7rmsg1QDUEoCqNE7g7M1FdrTt92TEp2CLzypump` | mcap 9,8 M · 1 h 1,02 M · 24 h 59,0 M · −3,7 % 1 h | mcap **8,6 M** · 1 h **920 k** · 24 h 58,3 M · −4,0 % 1 h · 3 618 c × 2 755 v/h | esfriando devagar (−12 % de mcap em 30 min); r0,15 — volume real |
| `PAIDLON` | `AowPHdsFTZNTa7JDGFUCRpyGa4niTS9GBG26CNWtpump` | 432 k · 268 k · **−28 % 1 h** ("virou") | **1,35 M** · 316 k · **+184 % 1 h** · 8 455 c × 1 790 v/h · boost 100 | **reviveu 3×** — o "virou" das 16:1x era um vale; segunda perna com 4,7 compras por venda |
| `PAIDDOGE` | `52qkNpgTHcjuDYhKVcg6rJS4uYYtJHpDRcJoSdKqpump` | 491 k · 871 k (1.ª hora) · +292 % | 509 k · **711 k/h** · 24 h 1,14 M · +21 % 1 h · **boost 500** (subiu de perfil para boost máximo) · 7 226 c/h | segura o nível com o maior giro/mcap da amostra (1,4× por hora) |
| **`XCat`** (novo) | `GFFVbGwi4g5YaJ6V1iLUrVQvgpZ5eM5NRWwS3uuVpump` | — | criado **16:08 BRT** · mcap 195 k · **500 k na 1.ª hora** · +174 % · 12 895 c × 1 585 v/h · site + X `@thexcatsol` · "The Official XCat of Solana — #1 Meme on XMoney" | derivado de 2.ª geração: nomeia a **marca** (X Money), não o produto (UsePaid) |
| **`XDOGE`** (novo) | `7ecXbJWyEoieJtGiGuq5yDmkrWogo6wAzZHVteg2pump` | — | criado **16:15 BRT** · mcap 228 k · **446 k na 1.ª hora** · +192 % · 6 326 c × 2 083 v/h · site + X `@xdogecoinsol` · boost 30 | idem; par PumpSwap em < 25 min |
| **`X`** "X Coin" (novo) | `4XcoQqV6kY46Zcofew9yGoYhy7znTuz4cnAUFcytpump` | — | criado **16:30 BRT** · ainda na curva · mcap 30 k · 60 k em 8 min · +1 004 % · X `@xcoinpayments` · "post the $X CA and cashtag on X and get rewarded through X's native pay" | a descrição já é o pitch de "pagamento pelo X" sem citar UsePaid |
| `ELON` "Elon Coin" | `GY9mZfyPpxXxBXBxS2hB2XjhP3kfUsywTvgveozxpump` | não visto (só o `ELON` `eqUv…` do viveiro) | **24 h: US$ 15,3 M** · mcap 1,31 M · 1 h 172 k · −13 % 1 h · +8 642 % 24 h · par 15/09 16:26 BRT · só link de busca no X | a moeda "Elon" grande do dia era esta, não a do viveiro; já em queda — registro, não entrada |
| `XPAY` | `4ffcz9…pump` | rug −97,6 % | **US$ 0 na última hora** | morta |
| `musepaid`, `XPAID`, `Paid BTC`, `PAID HYPE`, `PAID` (clones) | `BAGDQY…`, `2qmjxX…`, `Geg5xw…`, `G1J1db…` | — | −95 %, −70 %, e duas nascidas 16:37 BRT com US$ 1–3 k | os clones com **nome do produto** (`PAID*`) morrem; os com **nome da marca** (`X*`) pegam |

**Leitura:** em ~4 h a narrativa migrou "produto → marca": `PAIDLON`/`PAIDDOGE` (via UsePaid) seguem vivos, mas a leva
das 16:08–16:30 BRT chama-se `XCat`/`XDOGE`/`X` e vende "pagamento nativo do X". Nas 50 criações mais novas do
pump.fun (16:36:58–16:38:34 BRT, 50 em 96 s) ainda nascem `Paid BTC` e `PAID HYPE` — a fábrica de `PAID*` não parou,
só não paga mais. Busca `x money`: 22 pares, todos mortos (US$ 0/h) — o dinheiro está nos `X*` novos, não nos `XMONEY` velhos.

### N2 — Viveiro "fundo/instituição": segunda leva de rugs em 30 min e clone novo de US$ 643 M nominal

| símbolo | mint | 16:1x BRT | **16:4x BRT** | leitura |
|---|---|---|---|---|
| `WWR` World Water Reserve | `KrvPY4SS1TYv8c8dLu25K8Wn8NTLTAur9kCJkvKpump` | 27,7 M · viveiro r82 | **US$ 2 k · −99,99 % 1 h** · 236 k de saída/h | rug em < 30 min após aparecer no extrato — a "fábrica renomeada" tem a mesma vida útil |
| `WOFI` | `Fxnc2ieCdBJsHT4DRsQ13rV1mBEZ8uEmDz2gx7Npump` | viveiro (16h) | **US$ 6 k · −100 %** · 976 k de saída/h | rug |
| `KIBA` | `NBVhtL…pump` | −100 % (já) | 2 k; ainda 729 k/h de saída; pump.fun **ainda não exibe** este mint no top-50 | consumado |
| `WOTF` principal | `8MUcwPafbMA432mTgRFM4vjD7kbKcmEiwjdpzmN8pump` | 32,4 M · −65 % 1 h | 32,9 M · −65,5 % 1 h · 207 k/h · 24 h 3,51 M | sem mudança em 30 min (a queda foi antes) |
| **`WOFI`** (novo) | `YuEFCTBvg8WgiZrgTS59fZMSKmXtSeVGS2qV6m4pump` | — | criado **16:32 BRT** · **US$ 643 M nominal** · liq 2,1 M · **1,04 M de volume em 6 min** · 278 c × 19 v · +1 592 479 % · sem social | **viveiro** (KB-0103: encheu no minuto do mint; 15 compras por venda = concentração) — já é o #2 do top-50 da pump.fun |
| `WOFI` | `Cf7ng2…pump` (o "novo" das 16:1x) | 343 M · 0,3 h | 411 M · 890 k · 3 597 c × 1 329 v/h | de pé; 6.º clone `WOFI` |
| **`WOTF`** (novo) | `8EoRx3DZxK8vbq8wMkY32QpBfcwnb9dUutq2ZoaTpump` | — | criado **15:56 BRT** · 9,4 M · 121 k/h · 2 068 c × 94 v · r77 | 7.º clone `WOTF`; menor que os irmãos |
| `FAIR`, `USDF` | `QbPr1p…`, `B6Jt8b…` | r83 / r90 | 16,3 M / 17,6 M · **7–8 k/h** · r81 / r88 | de pé, sem giro — próximos da lista |
| `NTDA` ×2, `ECTF` ×2, `ELON` `eqUv…`, `WOTF` `NnLz…`/`RAwq…`/`Cjeh…` | — | viveiro | +3 a +9 % 1 h · 13–67 k/h · 2 700 c × ≤ 70 v/h | o padrão "2 700 compras × 60 vendas por hora" repete em todos: bots comprando de si |

Top-50 por mcap da pump.fun às 16:4x BRT: `WOTF` ×6, `WOFI` ×5, `NTDA` ×4, `ECTF` ×2, `DANGR` ×2, `USDF` ×2 — 21 dos 50
lugares. Atualiza o evento 11 (16:1x); **não é evento novo**.

### N3 — ARGUS / Arc: esfriou e **continua sem clone na Solana**
`ARGUS` (Arc): CoinGecko trending **#2 ainda**, mas +754,7 % 24 h (era +840,7 %), mcap US$ 24,1 M (era 26,5 M), vol 19,9 M
(era 21,3 M), rank 741 (era 704). Busca `argus` na DexScreener: **0 pares Solana** (igual às 16:1x). A previsão "clones em
< 1 h" **falhou por 90 min** — a marca Arc não atravessou para o pump.fun (nem `arc` AI Rig Complex mexeu: −0,3 % 1 h,
15 k/h). `ARCH` viveiro r91, 16 k/h. Nas 50 criações mais novas, nenhum nome com "argus"/"arc". **Rebaixar de "vigilância" para "registro".**

### N4 — ZEC / privacidade: o vencedor na Solana já existe e chama-se `ZCAT`
`ZEC` segue #1 do trending (+13,0 % 24 h, era +19,3 %; vol US$ 2,03 B). ZEC embrulhado na Solana
(`A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS`): 893 k/h na Orca + 539 k/h na Meteora (era 907 k/h somado) — estável.
**Novo:** CoinGecko trending **#13 = `ZCAT` "Anonymous Cat"** (+14,7 %, mcap US$ 100 M, vol 6,5 M) — mint Solana
`HcRLc9VDgjLeK154xDawfb1dmVJ98DoSqcwTHGqiDeJR`, 10,8 d de idade, 246 k/h no maior par, **−12 % 1 h**. É o meme
"privacidade" da Solana, já grande e em correção: não é entrada, é o pai que os clones `ZCAT`/`ZEC` vão copiar
(busca `zcat`: 26 pares, os outros mortos). `privacy`: 5 pares, US$ 0/h. Reforço de narrativa nas notícias: CoinDesk 19:07
UTC — **hackers da Revolut exigem US$ 3 M em Monero** (privacidade como tema do dia, de novo).

### N5 — Animais / cassino / post viral (o fluxo pequeno e real)
| símbolo | mint | 16:1x | **16:4x** | leitura |
|---|---|---|---|---|
| `casinu` | `2eMoMqs194VxPHSWtCCzkBGqwCUbD4ZcqhecoGuh4tTp` | 70 k ("caiu à metade") | **247 k · +77 % 1 h** · 272 k/h · 2 230 c × 1 651 v · boost 500 | reviveu 3,5× — mesmo padrão do `PAIDLON`: o "morreu em 40 min" das 16:1x foi vale |
| **`TRAILCAM`** "Trail Cams" (novo) | `9CPbeeJrNiAAbjAoGhH2QJMDZdBMdMTNWfAJTmTfEoAG` + `6CRDK6pa7PxxSJSptihof8Pcc6WVtsCVTg2KvdSEw7ra` | — | criados **16:10 BRT** · na curva · 14–17 k · **122 k + 138 k na 1.ª hora** · 1 425 c × 1 332 v · perfil aponta para um post de `@esotericpigeon` (status `2100301308288770531`) · **5 clones** em 30 min | `viral_post` de conta pequena: muito giro, mcap pequeno — o post não foi lido |
| `CATE` | `Ai66LH…` | 264 k/h | 364 k/h · +2,3 % 1 h · 24 h 5,87 M | segue o maior orgânico (r12) |
| `STONKLANA` | `DFNnZi…` | 61 k | 107 k · +182 % 1 h · 92 k/h · sem social | subiu; Raydium |
| `SEEKER` "Cat on Seeker" | `Hp1HufH5vfQH17pFgKuvHypyKt38sR3JYrkEx5dpkBQR` | — | 106 k · +104 % 1 h · 32 k/h · 16 d · perfil novo (Solana Mobile) | gato + marca real (Seeker); pequeno |
| `CUBE` | `5aQEnoivZDVdVjrXCDkayj4LFVcvbP9GR8gULiNUpump` | — | 16:28 BRT · na curva · 8 k · 66 k em 12 min · −16 % · site `yourcube.fun` | produto físico ("meme na sua mesa"); já caindo |
| `PONS` clone | `14qE3v…` | 429 k · +949 % · 0,1 h | **US$ 2 k · −95,8 %** | morreu em 30 min — o clone-do-trending não segura |
| `PRAXIS` | `9FjBTD…` | 16 k | 15 k · −65 % 1 h | morta |
| `blindcat`, `feg`, `Holdoween`, `DFC` | — | — | 86 k · 87 k · 231 k · 439 k; 11–13 k/h; ±4 % | flat; nada mudou |

### N7 — Política / macro / TOKEN2049: continua zero
`fed` 6 pares (US$ 0–3 k/h), `token2049` 1 par (US$ 0/h). Sem mudança.

## 2. Top 8 Solana por volume real na última hora (16:4x BRT; excluídos os rugs em saída e os viveiros)

`r` = mcap ÷ vol 24 h. Rugs em saída (`KIBA` 729 k/h, `WWR` 236 k/h, `WOFI Fxnc` 976 k/h) e viveiros (`WOFI` `YuEF…` 1,04 M,
`WOFI` `Cf7n…` 890 k) têm mais "volume" que metade desta lista — ficam fora por serem saída ou forja, não demanda.

| # | símbolo | mint | idade | mcap | vol 1 h | c/v 1 h | narrativa | marca |
|---|---|---|---|---|---|---|---|---|
| 1 | `PAID` | `98kfF7rmsg1QDUEoCqNE7g7M1FdrTt92TEp2CLzypump` | 24,3 h | US$ 8,63 M | **920 k** | 3 618/2 755 | UsePaid (mãe) | real, r0,15; graduada (fora da mesa, T4.18) |
| 2 | `ZEC` (embrulhado) | `A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS` | 334 d | — | **893 k** (Orca) + 539 k (Meteora) | 945/1 430 | privacidade / ZEC #1 | não é meme; termômetro |
| 3 | `PAIDDOGE` | `52qkNpgTHcjuDYhKVcg6rJS4uYYtJHpDRcJoSdKqpump` | 1,3 h | 509 k | **711 k** | 7 226/4 465 | UsePaid derivado | real (r0,45); boost 500; site+X+TG |
| 4 | `XCat` | `GFFVbGwi4g5YaJ6V1iLUrVQvgpZ5eM5NRWwS3uuVpump` | 0,5 h | 195 k | **500 k** | 12 895/1 585 | X Money (2.ª geração) | real (r0,4); site+X |
| 5 | `XDOGE` | `7ecXbJWyEoieJtGiGuq5yDmkrWogo6wAzZHVteg2pump` | 0,4 h | 228 k | **446 k** | 6 326/2 083 | X Money (2.ª geração) | real (r0,5); site+X; boost 30 |
| 6 | `CATE` | `Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump` | 52 d | 72,3 M | **364 k** | 832/779 | animal | real (r12); referência |
| 7 | `PAIDLON` | `AowPHdsFTZNTa7JDGFUCRpyGa4niTS9GBG26CNWtpump` | 4,8 h | 1,35 M | **316 k** | 8 455/1 790 | UsePaid derivado | real (r0,9); boost 100; +184 % 1 h |
| 8 | `casinu` | `2eMoMqs194VxPHSWtCCzkBGqwCUbD4ZcqhecoGuh4tTp` | 1,3 h | 247 k | **272 k** | 2 230/1 651 | cassino-cão | real (r0,6); boost 500 |

Logo abaixo: `WOTF` `8MUc…` 207 k/h (saída, −65 %), `ELON` `GY9m…` 172 k/h (−13 %), `ANSEM` 127 k/h (+3,7 %), `TRAILCAM` ×2
122–138 k/h (na curva), `STONKLANA` 92 k/h. **Seis dos oito são a mesma narrativa (UsePaid/X Money)** — concentração de
tema como a das 16h, agora com nomes de 2.ª geração.

## 3. Notícias das últimas 2 h (17:40–19:42 UTC) e agenda de hoje à noite / amanhã (BRT)

| hora (BRT) | fonte | item | meme em 24 h? |
|---|---|---|---|
| 16:07 | CoinDesk | **Hackers da Revolut exigem US$ 3 M em Monero** e ameaçam vender dados de clientes | **médio-baixo**: reforça "privacidade" (ZEC #1, `ZCAT` #13); `REVOLUT`/`MONERO` como meme de hack duram horas (padrão HBO Max das 16h) |
| 16:25 | Cointelegraph | "Here's what happened in crypto today" (resumo) | não |
| 16:19 | Cointelegraph | **UK FCA** publica guia de autorização cripto antes da janela de setembro | não |
| 15:53 | Decrypt | Bitcoin Core: atualização em outubro | não (já nas 16:1x) |
| 14:54 | CoinDesk | Fed +25 bp (já registrado) | não |
| 14:34 | CoinDesk | **Celsius processa a BitMEX em US$ 495 M** pelas liquidações de 2020 | não (contencioso antigo) |
| 15:01 | Cointelegraph | Câmara aprova reforma tributária cripto 38–5 (já registrado) | não |

The Block: nenhum item novo depois de 18:06 UTC. **Nenhuma** notícia das quatro redações tem gatilho de meme em 24 h
além do Revolut/Monero; o fluxo de hoje continua vindo de produto (UsePaid → X Money) e de posts, não de redação.

**Agenda (BRT):** hoje **22:00** — TOKEN2049 Singapura dia 2 abre (fuso +8; palco de anúncios madrugada/manhã BRT);
17/09 **manhã** — ETHSpain Barcelona; 17/09 — EBC12 dia 2; 18/09 — triple witching EUA. Sem hora nova nas fontes
headless (RSS não traz calendário; WebSearch não usado nesta corrida). Cronograma dos claims da UsePaid segue não público.

## 4. Três termos de vigilância (próximas 2 h)

| termo | por quê (medido agora) |
|---|---|
| **`X*` + "X Money" / "X's native pay" / "XMoney" na descrição** (`XCat`, `XDOGE`, `X`) | a 2.ª geração da narrativa mais rica do dia: 3 nascimentos em 22 min (16:08–16:30 BRT), 446–500 k na 1.ª hora, 6–13 mil compras/h, site + handle; os `PAID*` novos morrem (`musepaid` −95 %, `XPAID` −70 %) — o nome que paga agora é o da **marca** |
| **`PAIDLON` / `PAIDDOGE` / `casinu` — segunda perna** | os três "virados/mortos" das 16:1x reviveram 3× em 30 min (+184 %, +21 % com 711 k/h, +77 %): a leitura "virou" em 40 min é ruído; vigiar o segundo vale (se houver) e o pico da 2.ª perna |
| **`ZCAT` / `ZEC` / `MONERO` / "privacy"** | ZEC #1 e `ZCAT` #13 do trending; embrulhado 1,4 M/h na Solana; notícia Revolut/Monero às 16:07 BRT; clones ainda ausentes (`privacy` US$ 0/h) — se nascer, nasce com este nome |

**Rebaixado:** `ARGUS` (0 pares na Solana 90 min depois da previsão; esfriando na Arc). **Não vigiar (medido):** `CLARITY`,
`WARSH`, `FED`, `TOKEN2049` (US$ 0/h); `WOTF`/`WOFI`/`NTDA`/`ECTF`/`WWR`/`FAIR`/`USDF` só como exclusão (KB-0103).

## 5. Linhas `meme_event.py add` — só eventos NOVOS (13–15; dry-run; `--apply` na VPS; sem `--mint`, mint em `--notes`)

Os eventos 9–12 (16:1x BRT) não se repetem; o viveiro (11) só ganha a nota "WWR e WOFI Fxnc −100 %; WOFI YuEF US$ 643 M
nominal às 16:32 BRT" (atualização, não evento).

```bash
# 13. X Money, 2.a geracao: XCat / XDOGE / X Coin nascem em 22 min com "XMoney" / "X's native pay" na descricao; 446-500 k na 1.a hora
uv run python infra/scripts/meme_event.py add --kind narrative \
  --title "X Money 2.a geracao: XCat (16:08 BRT, US$ 500 k/1.a h), XDOGE (16:15, 446 k), X Coin (16:30) com 'XMoney'/'X native pay' na descricao; clones PAID* novos morrem" \
  --url "https://api.dexscreener.com/token-profiles/latest/v1" --symbol XCAT \
  --confidence rumor --source dexscreener_profile --observed-at 2026-09-16T19:40:00Z \
  --notes '{"mints":{"XCat":"GFFVbGwi4g5YaJ6V1iLUrVQvgpZ5eM5NRWwS3uuVpump","XDOGE":"7ecXbJWyEoieJtGiGuq5yDmkrWogo6wAzZHVteg2pump","X":"4XcoQqV6kY46Zcofew9yGoYhy7znTuz4cnAUFcytpump"},"vol1h_usd":{"XCat":500026,"XDOGE":445738,"X":59750},"mcap_usd":{"XCat":195297,"XDOGE":227625,"X":30190},"buys1h":{"XCat":12895,"XDOGE":6326},"handles":["thexcatsol","xdogecoinsol","xcoinpayments"],"parent_event":"9 (UsePaid/PAID)","signature":"xmoney|x money|x.s native pay|xpay na descricao","dead_siblings":{"musepaid":"BAGDQYgsBFvUpXoVhBKJjjYsfHMDMDS6kAB5tgZFpump","XPAID":"2qmjxXhKSXNVyjVMCcynw6uf4mtBvnH4M7VLH3oXY9Qz"}}' --recorded-by sexta-feira

# 14. Post viral de conta pequena -> 5 clones "Trail Cams" em 30 min (post nao lido; link no perfil DexScreener)
uv run python infra/scripts/meme_event.py add --kind viral_post \
  --title "Trail Cams: post de @esotericpigeon (status 2100301308288770531) gera 5 clones TRAILCAM em 30 min; 122 k + 138 k na 1.a hora, mcap 14-17 k, ainda na curva" \
  --url "https://x.com/esotericpigeon/status/2100301308288770531" --handle esotericpigeon --symbol TRAILCAM \
  --confidence rumor --source dexscreener_profile --observed-at 2026-09-16T19:40:00Z \
  --notes '{"mints":["9CPbeeJrNiAAbjAoGhH2QJMDZdBMdMTNWfAJTmTfEoAG","6CRDK6pa7PxxSJSptihof8Pcc6WVtsCVTg2KvdSEw7ra"],"clones":5,"created_utc":"19:10","vol1h_usd":[121153,137805],"mcap_usd":[13867,17063],"buys_sells_1h":"1425/1332","post_read":false}' --recorded-by sexta-feira

# 15. Revolut: hackers exigem US$ 3 M em Monero (CoinDesk 19:07 UTC) — reforco da narrativa privacidade (ZEC #1, ZCAT #13)
uv run python infra/scripts/meme_event.py add --kind incident \
  --title "Hackers da Revolut exigem US$ 3 M em Monero e ameacam vender dados de clientes; privacidade e o tema do dia (ZEC #1 trending +13 %, ZCAT #13 +15 %)" \
  --url "https://www.coindesk.com/" --symbol XMR \
  --confidence reported --source plantao --observed-at 2026-09-16T19:07:00Z \
  --notes '{"rss":"coindesk 19:07 UTC","related":{"ZCAT_solana":"HcRLc9VDgjLeK154xDawfb1dmVJ98DoSqcwTHGqiDeJR","wrapped_zec":"A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS"},"expect":"clones MONERO/REVOLUT/PRIVACY no pump.fun; duracao de horas (padrao HBO Max)","parent_event":"12 (ZEC #1)"}' --recorded-by sexta-feira
```

## Ligações
`obsidian/02-MARKET/Eventos/2026-09-16-17h-brt.md` (versão do vault) · `.claude/state/plantao-meme/tendencias-2026-09-16-17h.md`
(corrida anterior, medida 16:04–16:12 BRT) · `.claude/state/plantao-meme/eventos-2026-09-16-16h.md` (15:39–15:58 BRT) ·
`obsidian/11-KNOWLEDGE/KB-0100-*.md`, `KB-0103-*.md` · `obsidian/00-INBOX/Hipoteses-do-plantao.md` (M-P50) · brutos em
`%LOCALAPPDATA%\Temp\claude\p17brt\` (não versionados)
