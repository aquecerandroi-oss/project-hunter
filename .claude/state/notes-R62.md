# R62 — O que antecede o dump? As 8 posições reais da madrugada de 19/09 (regra do Everton) e a regra "vender na primeira venda grande"

**Data:** 2026-09-19, `as_of` 09:3x BRT. **Pergunta (09:1x BRT):** para as 8 posições reais desde 00:00 BRT, montar a linha do tempo completa; nas 3 perdas, houve UMA venda grande (≥ 5 % do `real_sol`) ou de carteira inicial ANTES do gatilho do trailing? Nos 3 alvos, quanto tempo até +15 % e quanto ficou na mesa? Gatilho → envio → pouso e slippage por saída? Regra numérica para a T4.69 ("primeira venda ≥ X % ou de carteira inicial ≥ Y tokens ⇒ vender com pânico") e efeito nas 8.

**Resposta curta.** A "venda grande" existe em 5 das 7 posições com fita — mas ela **é** o gatilho do trailing, não o antecede: a saída por evento (T4.63) disparou **0,9–1,5 s** depois do bloco da venda grande em XCrypto, FЕРЕ e NARKY#1, e em EQUITITTY a venda de 8,9 % foi seguida, no mesmo segundo, por 14 vendas idênticas de 0,13 SOL (bundle) que fizeram a nossa 1.ª tentativa falhar (`6003 TooLittleSolReceived`, 5 %) e o pouso vir 5 s depois, a −24,5 %. Regra "vender na primeira venda ≥ X %": com X = 5 % salva EQUITITTY (−11,8 % em vez de −24,5 %) mas mata Cupsey#1 (+18 → −11 %) e CYBER (+27 → −4 %): **−0,0185 SOL** nas 8; com X ≥ 10 % não muda nada (+0,0006 SOL). Na população de 82 entradas de papel das últimas 24 h com fita, nenhum X (5–20 %), soma em 3 s, cascata de N carteiras ou "carteira inicial ≥ Y" melhora a média (−0,24 % → entre −0,91 % e +0,04 %). Depois de uma venda ≥ 5 % do `real_sol` o preço 60 s depois (5–20 % do `real_sol`) está abaixo do nosso fill em **50–54 %** dos casos (n = 1 357) — moeda ao ar; vendas ≥ 20 % são seguidas de **repique** (mediana +9,8 %). **Recomendação: não ligar a T4.69 como regra de saída.** O dinheiro nas 8 está em outro lugar: (a) o trailing de 10 % armado na entrada tirou-nos de XCrypto (−2 %), NARKY#1 (−5 %) e FЕРЕ (−14 %) que chegaram a **+139 %, +139 % e +55 %** dentro dos 5 min; (b) o precursor real do colapso de Cupsey foi a **saída em bloco das 5 carteiras iniciais em 1 s** (08:47:21 BRT-3, 4,2 SOL ≈ 19 % do `real_sol`), que a fita já tinha gravado **33 s antes** da entrada de Cupsey#2 — é o `early_retention_pct` da T4.66, um portão de **entrada**, não de saída.

## 1. Dados e cobertura

| item | valor |
|---|---|
| posições | `meme_live_positions` com `entry_at ≥ 2026-09-19 03:00 UTC` → 8, todas `closed`, params `{size 0,07, target 1,15, trailing 10 %, max_hold 300, decided_by executor:auto_stage1}` (`q1.sql`) |
| ordens | `meme_live_orders` (`q2.sql`): 16 confirmadas (8 buy + 8 sell) + 1 sell `failed onchain_error 6003` (EQUITITTY) + 1 buy `blockhash_expired_never_landed` (FЕРЕ 2.ª tentativa 08:14:45 UTC) + 20 `refused` |
| fita (`meme_trades`, `source = swap_api`) | 5 783 trades nas 6 moedas; **backfill por REST**: `received_at − block_time` = 48–65 s (não é tempo real). **Cupsey: a fita acaba em 08:48:06 UTC — antes da entrada de Cupsey#2 (08:48:41)**; para ela só as fotos de 15 s. Cupsey#1 tem lacuna (reconstrução das reservas na saída difere 0,49 SOL; nas outras 6, diferença 0,000–0,0015 SOL — a fita está completa entre entrada e saída) |
| fotos (`meme_curve_snapshots`, `solana_rpc`) | 777 linhas; cadência ~15 s enquanto fixada |
| marcas por frame do executor | **não persistidas**: `event_exits_eval._write_mark` só atualiza `mark_sol/mark_at/high_water_sol` da própria linha (`UPDATE`, throttle 1 s, forçado no pico e no frame que dispara); o heartbeat guarda contadores. A linha carrega o **último** valor — o pico (`high_water_sol`) bate com o pico reconstruído da fita nas 6 (0,0801 vs 0,08005 em XCrypto etc.) |
| reconstrução | a partir do `fill` da compra (`virtual_sol/token_reserves_after`, exatos), cada trade da fita soma/subtrai `sol_lamports`/`token_amount` (`analyze.py`); marca = `quote_sell` dos nossos tokens × (1 − 1,25 %); `real_sol = virtual_sol − 30`; carteira inicial = 10 primeiros compradores distintos desde o nascimento (criador incluído) |
| população de papel | `meme_paper_bets` fechadas com `entry_at ≥ now − 24 h`: 293 apostas / 84 mints; agrupadas por (mint, minuto de entrada) → 111 entradas, 82 com fita ≤ 5 s da entrada (`q8/q9.sql`, `pop.py`); reservas por trade a partir de `price` (k = 30 × 1,073 G constante) — precisão ±2 % na fração |

## 2. As 8 linhas do tempo (horas em BRT; "marca" = líquido de vender tudo; `real` = SOL real na curva)

### 2.1 XCrypto — −2,4 % (trailing) · depois graduou

| t | evento |
|---|---|
| 02:54:06.27 | ordem recebida; **fill de compra no bloco 02:54:06** (slot 448318665), 0,0716 SOL → 1,432 G tokens, `real` 9,45; marca 0,0683 |
| 02:54:07 | venda 0,42 SOL (4,5 %) |
| 02:54:10–23 | 7 compras (0,04–1,0 SOL); marca sobe a **0,0801** (pico, +11,8 %) às 02:54:23 |
| **02:54:30** | **897GsV vende 1,90 SOL = 15,1 % do `real`** (35 M tokens; comprou 1,0 SOL às 02:54:10 — não é carteira inicial) → marca 0,0727; + EZbw9M 0,40 e omegoM 0,39 → **0,0699 = −12,7 % do pico** |
| 02:54:31.26 | **gatilho `trailing`** (evento; 1,26 s depois do bloco); simulado 31.44 |
| 02:54:33 | **venda pousa** (slot 448318764): 0,0708 bruto / **0,0698 líquido** (cotação no gatilho 0,0699 → slippage −0,06 %) |
| 02:54:34.98 | `settled_at` (gatilho → settle 3,7 s) |
| 02:54:33–52 | 8dtx2t vende 7,8 %; depois 12 compras: marca de quem segurou 0,0892 às 02:54:52 (**+25 % do gasto**) |
| 02:58:47 | máximo dentro dos 5 min: **0,1709 (+139 %)**; ao fim dos 5 min 0,1689; graduou às 04:03 (0,5124) |

### 2.2 EQUITITTY — −24,5 % (trailing, 2 tentativas)

| t | evento |
|---|---|
| 04:00:24 | 1.ª proposta recusada (`top10_share_unknown`) |
| 04:03:24.25 | ordem; **fill no bloco 04:03:24**, 0,0700 SOL → 559 M tokens, `real` 32,4 (curva já em 62 SOL virtuais, 4,5 min de vida); marca 0,0667 — **no mesmo segundo e nos 3 seguintes, 9 vendas** (0,05–0,48 SOL): entramos dentro de uma onda de venda; pico gravado 0,0650 (1.ª marca) |
| **04:03:30** | **7QBQLN vende 1,82 SOL = 5,8 %** (15,9 M tokens) → marca 0,0609 (−13 % do gasto; 0,937 do pico — não dispara) |
| **04:03:33** | **5Ta9XC vende 2,71 SOL = 8,9 %** (25 M) → 0,0571; **no mesmo segundo** 5vbBW8, 67LwNG, Egqa7m, AFUXTp, B7V1va, EorGEb (1,13 SOL) e às :34 **ETSxXT, HkPhW8, H5TrUt, BxyYZc, H3Rwxe, 61fsvQ, 2pqfUX (7 carteiras × 0,131–0,136 SOL — bundle)** + 5kWsuR → marca **0,0515** |
| 04:03:34.17 | **gatilho `trailing`** (1,17 s depois do bloco :33); simulado 34.33; 1.ª tentativa `min_sol_output` 0,0542 (cotação 0,0571 × 0,95) |
| 04:03:36.65 | **falha on-chain `6003 TooLittleSolReceived`** (a curva já valia < 0,0542) — taxa paga; backoff |
| 04:03:39.28 | 2.ª tentativa (cotação 0,0526); pousa no bloco **04:03:39**: **0,0528 líquido** (−7,4 % vs cotação da 1.ª tentativa) |
| 04:03:40.76 | settled (gatilho → settle **6,6 s**) |
| 04:03:54–55 | **2ksQ77 (carteira inicial n.º 4) vende 2,81 SOL = 11 %**, 6M3ur1 (inicial n.º 9) vende; 7QBQLN vende mais 6 % → 0,0418 |
| 04:08:24 | fim dos 5 min: 0,0202 (**−71 %**); máximo pós-saída 0,0578 |

### 2.3 FЕРЕ — −13,7 % (trailing)

| t | evento |
|---|---|
| 08:11:39.88 (UTC) = 05:11:39.88 | ordem; **fill no bloco 05:11:39**, 0,0716 SOL → 921 M tokens, `real` 19,2; marca 0,0683 |
| 05:11:40–42 | 3 compras; pico **0,0704** às 05:11:42 |
| **05:11:44** | **2AqFJz (carteira inicial n.º 5) vende 2,96 SOL = 14,8 % do `real`** (40,5 M tokens, tudo o que tinha) → marca **0,0623 = −11,5 % do pico** |
| 05:11:45.52 | **gatilho `trailing`** (1,5 s depois do bloco); simulado 45.65; cotação 0,0623 |
| 05:11:49 | **venda pousa** (3,5 s depois do simulado — pouso lento com taxa de prioridade no piso 100 k µlamports): **0,0617 líquido** (−0,94 %) |
| 05:11:51.39 | settled (gatilho → settle **5,9 s**) |
| 05:12:22 | 22vL22 (inicial n.º 2) vende 2,95 SOL (13,6 %) — e a moeda **sobe**: 0,0672 |
| 05:15:33 | máximo dentro dos 5 min **0,1109 (+55 %)**; fim dos 5 min 0,1058 (+48 %); máximo às 05:27 0,2446 |
| 05:14:45 | 2.ª proposta FЕРЕ: compra `blockhash_expired_never_landed` |

### 2.4 Cupsey#1 — +18,3 % (alvo)

| t | evento |
|---|---|
| 05:45:41.77 | ordem; **fill no bloco 05:45:44** (2,2 s), 0,0721 SOL → 1,30 G tokens, `real` 11,5; marca 0,0688 |
| 05:45:54 / 05:45:56 | **DjiJKV vende 0,84 SOL = 7,3 %**; **Dggd6X vende 0,57 SOL = 5,3 %** → marca 0,0640 (−11 % do gasto). Trailing não dispara (pico = marca de entrada; 0,0640/0,0688 = 0,93) |
| 05:46:00–24 | compras; marca cruza 1,15 × gasto = 0,0829 no bloco **05:46:24** (**40 s** da entrada) |
| 05:46:24.84 | **gatilho `target`**; simulado 25.01; cotação 0,0818 |
| 05:46:24 | venda pousa no **mesmo segundo** (preço subiu enquanto pousava): **0,0852 líquido (+4,1 % vs cotação)**; settled 26.34 (1,5 s) |
| 05:46:47 / 05:47:01 | vendas de 14 % e 7,3 % absorvidas; **máximo 0,1196 às 05:47:00 (+40 % acima da nossa venda; +66 % do gasto)** |
| **05:47:21** | **saída em bloco das carteiras iniciais**: 4CUEXz, 91GvZz, A5mMDT, 6Jzyqc, GGiqYV (iniciais 1, 2, 3, 9, 10) — **10 vendas de 0,37–0,51 SOL no mesmo segundo, 4,2 SOL ≈ 19 % do `real`** → 0,0993. `received_at` da fita: **08:48:07 UTC = 05:48:07** |
| 05:48:06 | **a fita para** (última linha da moeda) |

### 2.5 Cupsey#2 — −10,8 % (trailing) · sem fita; só fotos de 15 s

| t | evento |
|---|---|
| 05:48:40.23 | ordem (**33 s depois de a fita gravar a saída em bloco das iniciais**); **fill no bloco 05:48:41**, 0,0700 SOL → 869 M tokens, `real` 20,65; marca ~0,0681 |
| 05:48:50 / :52 (fotos) | `real` 20,63 → **21,55** (pico gravado 0,0716) |
| 05:49:08 (foto) | `real` **19,25** (−2,3 SOL = −10,7 % em ≤ 16 s — uma ou várias vendas; sem fita) |
| 05:49:09.91 | **gatilho `trailing`**; cotação 0,0626; pousa no bloco 05:49:09: **0,0625 líquido** (−0,07 %); settled 11.37 (1,45 s) |
| 05:49:24 / :39 / 05:51:54 | `real` 13,2 → 7,1 → **1,5 SOL**: rug em 3 min. Sair a −10,8 % foi o melhor desfecho possível a partir da entrada |

### 2.6 CYBER — +26,7 % (alvo)

| t | evento |
|---|---|
| 07:57:42.57 | ordem; **fill no bloco 07:57:47** (4,4 s!), **0,0223 SOL** (tamanho reduzido pelo sizing: `sol_final 0,0207`) → 436 M tokens, `real` 8,9; marca 0,0202 |
| 07:57:52 / :54 | HWsmJ1 (inicial n.º 3) vende 0,06; **DU5mNJ vende 0,83 SOL = 8,5 %** → marca 0,0203 (= entrada; trailing não dispara) |
| 07:57:57–58:20 | 13 compras; marca cruza 1,15 × gasto no bloco **07:58:20** (**33 s**) |
| 07:58:21.57 | **gatilho `target`**; simulado 21.76; pousa no bloco 07:58:21: **0,0282 líquido** (−0,16 % vs cotação 0,0283); settled 23.08 (1,5 s) |
| 07:58:26 | máximo **0,0321 (+14 % acima da venda; +44 % do gasto)** |
| 07:58:30–37 | GvvAxe 8 %, 9RhxCR 8,5 %, iniciais 6/8/9/10, nya666 7,5 % → 0,0241; fim dos 5 min **0,0144 (−35 %)** |

### 2.7 NARKY#1 — −4,6 % (trailing)

| t | evento |
|---|---|
| 08:21:52.94 | ordem; **fill no bloco 08:21:53**, 0,0726 SOL → 1,277 G tokens, `real` 12,1; marca 0,0693 |
| 08:21:58 | 2YVvtk (inicial n.º 6) vende 0,36 SOL (2,9 %) |
| 08:22:00–20 | compras; pico **0,0779** às 08:22:20 |
| **08:22:23** | 2YVvtk vende 0,13; **GvvAxe vende 0,97 SOL = 7,5 %** (comprou 08:22:05) → marca **0,0691 = −11,3 % do pico**; :24 2YVvtk vende 0,10 |
| 08:22:24.28 | **gatilho `trailing`** (1,3 s depois do bloco); pousa no bloco 08:22:24: **0,0693 líquido** (+0,16 %); settled 25.79 (1,5 s) |
| 08:22:33–38 | 5tnGX9 9,5 %, 8dtx2t 7,4 %, Dggd6X 9 %, HPtU9B (inicial n.º 4) 5,2 % → 0,0619 — e a moeda **sobe** depois |
| 08:26:03 | máximo dentro dos 5 min **0,1731 (+139 %)**; fim dos 5 min 0,1206 (+66 %) |

### 2.8 NARKY#2 — +20,3 % (alvo)

| t | evento |
|---|---|
| 08:24:53.13 | ordem; **fill no bloco 08:24:53**, 0,0699 SOL → 630 M tokens, `real` 29,4; marca 0,0681 |
| 08:24:54–59 | 6 compras (uma de 3,9 SOL); marca cruza 1,15 × gasto no bloco **08:24:59** (**6 s**) |
| 08:25:00.50 | **gatilho `target`**; simulado 00.87; pousa no bloco 08:25:00: **0,0841 líquido** (+0,54 % vs cotação 0,0836); settled 02.26 (1,8 s) |
| 08:25:03 / :13 | GvvAxe vende 2,15 SOL (6 %), Dggd6X 2,03 (7 %) → 0,0631 |
| 08:26:03 | máximo **0,0855 (+1,7 % acima da venda)**; fim dos 5 min **0,0545 (−22 %)** |

## 3. Pergunta 1 — houve UMA venda grande antes do gatilho nas perdas?

| posição | venda(s) ≥ 5 % ou de carteira inicial antes do gatilho | s antes do gatilho | disparou o trailing? | "sair nela" (pouso +2 s) teria dado |
|---|---|---|---|---|
| EQUITITTY | **7QBQLN 5,8 %** às 04:03:30 (não inicial); **5Ta9XC 8,9 %** às 04:03:33 (não inicial) + bundle de 7 × 0,13 SOL | 4,2 s / 1,2 s | a de 8,9 % sim | na de 5,8 %: **0,0617 = −11,8 %** (vs −24,5 %); na de 8,9 %: 0,0522 = −25,4 % (igual) |
| FЕРЕ | **2AqFJz, inicial n.º 5, 14,8 %** (40,5 M tokens) às 05:11:44 | 1,5 s | **sim — é o gatilho** | 0,0623 = −12,9 % (vs −13,7 %: +0,0006 SOL; a perda é a própria venda, não o atraso) |
| Cupsey#2 | sem fita; fotos: −2,3 SOL entre 05:48:52 e 05:49:08 | ≤ 16 s | sim (foto de 05:49:08 → gatilho 05:49:09,9) | não mensurável; o precursor real foi **80 s antes da entrada** (bloco das iniciais, §2.4) |
| XCrypto | 897GsV 15,1 % às 02:54:30 (não inicial) | 1,3 s | sim | 0,0699 = −2,3 % (igual) |
| NARKY#1 | GvvAxe 7,5 % às 08:22:23 (não inicial); 2YVvtk inicial n.º 6 vendeu 2,9 % 25 s antes | 1,3 s | sim | igual (−4,6 %) |

Nas 3 perdas a venda grande **e** o gatilho são o mesmo instante: a saída por evento já reage à venda ≈ 1,2–1,5 s depois do bloco (`received_at` do WS − `block_time`). Não há "antes" a ganhar, exceto a venda de 5,8 % de EQUITITTY — cujo limiar (5 %) destrói dois alvos (§6).

Vendas ≥ 5 % **absorvidas** (a moeda subiu depois): Cupsey#1 (7,3 % e 5,3 % a +10 s → alvo 30 s depois; máx +66 %), CYBER (8,5 % a +7 s → alvo 27 s depois), XCrypto (15,1 % → +139 % em 4 min), NARKY#1 (7,5 %, 9,5 %, 9 % → +139 %), FЕРЕ (14,8 % e 13,6 % de iniciais → +55 %). Uma venda grande **isolada** não distingue dump de sacudida.

## 4. Pergunta 2 — os 3 alvos

| posição | entrada → +15 % (marca) | gatilho → settle | líquido | máximo depois (5 min) | dinheiro na mesa | marca ao fim dos 5 min |
|---|---|---|---|---|---|---|
| Cupsey#1 | **40 s** (05:45:44 → 05:46:24) | 1,50 s | 0,0852 (+18,3 %) | **0,1196 às 05:47:00 (+40 % acima; +66 % do gasto)** | +0,0344 SOL | 0,0948 (+32 %) — e rug 4 min depois |
| CYBER | **33 s** (07:57:47 → 07:58:20) | 1,51 s | 0,0282 (+26,7 %) | 0,0321 às 07:58:26 (+14 %; +44 %) | +0,0039 SOL | **0,0144 (−35 %)** |
| NARKY#2 | **6 s** (08:24:53 → 08:24:59) | 1,76 s | 0,0841 (+20,3 %) | 0,0855 às 08:26:03 (+1,7 %) | +0,0014 SOL | **0,0545 (−22 %)** |

Tomar o alvo foi correto em 2 de 3 (CYBER e NARKY#2 estavam negativas 5 min depois); Cupsey#1 deixou 0,034 SOL. O dinheiro grande na mesa está nas **saídas por trailing**: XCrypto −2 % → +139 %, NARKY#1 −5 % → +139 %, FЕРЕ −14 % → +55 % dentro dos 5 min (§7).

## 5. Pergunta 3 — a lacuna de execução

`submitted_at` é escrito junto com `settled_at` quando o envio já volta `confirmed` (`journal_db.py`: `coalesce(submitted_at, now)` no mesmo `UPDATE`), então o instante real do envio não está no banco; uso `simulated_at` (+ ~50 ms de assinatura) como envio. `block_time` tem resolução de 1 s e costuma ficar **antes** do gatilho (relógio do slot), por isso o pouso é lido por `settled_at`.

| posição | motivo | gatilho → simulado | simulado → settled | **gatilho → settled** | cotação no gatilho (líq.) | fill líq. | slippage |
|---|---|---|---|---|---|---|---|
| XCrypto | trailing | 0,18 s | 3,55 s | **3,73 s** | 0,0699 | 0,0698 | −0,06 % |
| EQUITITTY | trailing (2 tent.) | 0,17 s | 6,42 s (falha 6003 + backoff 2,6 s + 2.ª) | **6,59 s** | 0,0571 | 0,0528 | **−7,41 %** |
| FЕРЕ | trailing | 0,13 s | 5,74 s | **5,87 s** | 0,0623 | 0,0617 | −0,94 % |
| Cupsey#1 | target | 0,17 s | 1,33 s | **1,50 s** | 0,0818 | 0,0852 | **+4,14 %** |
| Cupsey#2 | trailing | 0,16 s | 1,30 s | **1,45 s** | 0,0626 | 0,0625 | −0,07 % |
| CYBER | target | 0,19 s | 1,32 s | **1,51 s** | 0,0283 | 0,0282 | −0,16 % |
| NARKY#1 | trailing | 0,19 s | 1,33 s | **1,51 s** | 0,0691 | 0,0693 | +0,16 % |
| NARKY#2 | target | 0,37 s | 1,40 s | **1,76 s** | 0,0836 | 0,0841 | +0,54 % |
| **mediana** | | **0,17 s** | **1,36 s** | **1,64 s** | | | **−0,07 %** |

Gatilho → simulado é estável (0,13–0,37 s). O pouso é bimodal: 1,3 s em 5 casos; **3,6–5,7 s** em XCrypto e FЕРЕ (taxa de prioridade no piso, `p75_micro_lamports = 0` nas amostras) e 6,6 s em EQUITITTY pela falha de 5 %. Entrada: `received_at` → bloco 0–4,4 s (CYBER 4,4 s, Cupsey#1 2,2 s).

O que a tolerância de pânico (15 %) teria mudado em EQUITITTY: a 1.ª tentativa teria pousado às 04:03:35–36 com a marca em 0,0517–0,0530 ⇒ ≈ **−25 %**, igual ao que saiu 5 s depois. A cascata (20 vendas em 2 s) era mais rápida que qualquer envio.

## 6. Pergunta 4 — a regra da T4.69, numericamente

Simulação (`sim.py`, L = 2 s do bloco da venda ao pouso; sensibilidade L = 1 e 3 s dá o mesmo quadro): "primeira venda ≥ X % do `real_sol` (ou de carteira inicial ≥ Y tokens) ⇒ vender", só enquanto a posição está aberta; fill = marca depois de todos os trades até `t + L`. `*` = a regra mudou a saída.

| regra | total 8 (SOL) | Δ vs real (−0,0063) | XCrypto | EQUITITTY | FЕРЕ | Cupsey#1 | Cupsey#2 | CYBER | NARKY#1 | NARKY#2 |
|---|---|---|---|---|---|---|---|---|---|---|
| ≥ 3–4 % | −0,0278 | **−0,0215** | −6,6 %* | −11,8 %* | −12,9 %* | −11,1 %* | −10,8 % | −3,9 %* | −4,6 % | +20,3 % |
| **≥ 5 %** | −0,0248 | **−0,0185** | −2,3 %* | **−11,8 %*** | −12,9 %* | **−11,1 %*** | −10,8 % | **−3,9 %*** | −4,6 % | +20,3 % |
| ≥ 6–7 % | −0,0343 | −0,0280 | −2,3 %* | −25,4 %* | −12,9 %* | −11,1 %* | −10,8 % | −3,9 %* | −4,6 % | +20,3 % |
| ≥ 8 % | −0,0131 | −0,0068 | −2,3 %* | −25,4 %* | −12,9 %* | +18,3 % | −10,8 % | −3,9 %* | −4,6 % | +20,3 % |
| ≥ 10–12 % | −0,0056 | +0,0006 | −2,3 %* | −24,5 % | −12,9 %* | +18,3 % | −10,8 % | +26,7 % | −4,6 % | +20,3 % |
| ≥ 15 % | −0,0062 | 0,0000 | −2,3 %* | −24,5 % | −13,7 % | +18,3 % | −10,8 % | +26,7 % | −4,6 % | +20,3 % |
| soma 3 s ≥ 10–12 % | −0,0274 | −0,0211 | −2,3 %* | −25,4 %* | −12,9 %* | −11,1 %* | −10,8 % | +26,7 % | −4,6 % | +20,3 % |
| inicial ≥ 5 M tokens | −0,0033 | +0,0030 | −2,4 % | −24,5 % | −12,9 %* | +18,3 % | −10,8 % | +26,7 % | −1,3 %* | +20,3 % |
| inicial ≥ 10–30 M | −0,0057 | +0,0006 | −2,4 % | −24,5 % | −12,9 %* | +18,3 % | −10,8 % | +26,7 % | −4,6 % | +20,3 % |
| ≥ 10 % **ou** inicial ≥ 20 M | −0,0056 | +0,0006 | idem ≥ 10 % | | | | | | | |

O melhor da grade é +0,003 SOL (inicial ≥ 5 M, um caso de −4,6 % → −1,3 %) — ruído. Nada com X < 10 % sobrevive a Cupsey#1 e CYBER.

**População (82 entradas de papel com fita, 24 h; regra do Everton simulada na fita, L = 2 s; `pop.py`):**

| regra adicionada | média | mediana | acerto | p10 | p90 | saídas |
|---|---|---|---|---|---|---|
| nenhuma (alvo 15 %, trailing 10 %, 5 min) | **−0,24 %** | −2,48 % | 46 % | −24,5 % | +21,6 % | alvo 34 · trailing 40 · censurada 8 |
| venda ≥ 5 % | −0,80 % | −2,77 % | 41 % | −20,6 % | +21,2 % | venda 42 · alvo 27 · trailing 11 |
| venda ≥ 8 % | −0,91 % | −2,48 % | 45 % | −24,5 % | +21,3 % | venda 27 |
| venda ≥ 10 % | −0,35 % | −2,48 % | 45 % | −24,5 % | +21,6 % | venda 16 |
| venda ≥ 12–20 % | −0,24 % | −2,48 % | 46 % | −24,5 % | +21,6 % | venda 3–9 |
| soma em 3 s ≥ 15 % | +0,04 % | −2,48 % | 46 % | −24,5 % | +21,6 % | venda 19 |
| cascata ≥ 4 carteiras em 2 s, soma ≥ 5 % | +0,04 % | −2,48 % | 45 % | −24,5 % | +21,6 % | cascata 14 |
| cascata ≥ 6 carteiras em 2 s | −0,24 a −0,30 % | | | | | cascata 2–4 |
| inicial ≥ 5 / 10 / 20 M tokens | −0,39 / −0,44 / −0,44 % | −2,48 % | 44–46 % | | | 20 / 15 / 6 |

O p10 (−24,5 %) **não se move** com nenhuma regra: as perdas grandes são cascatas de vendas pequenas ou a própria venda grande, nunca "uma venda grande e depois a queda".

**Condicional — o que acontece 60 s depois de uma venda grande** (todas as vendas nos primeiros 10 min de vida das 84 moedas, `real_sol ≥ 3`; preço 60 s depois vs preço 2 s depois = nosso fill; `cond.py`):

| fração do `real_sol` | n | mediana Δ60 s | média | P(queda) | P(< −10 %) | P(> +10 %) |
|---|---|---|---|---|---|---|
| 2–5 % | 1 940 | −0,4 % | +3,4 % | 51 % | 37 % | 33 % |
| 5–8 % | 642 | −0,1 % | +6,8 % | 50 % | 32 % | 33 % |
| 8–12 % | 419 | −1,4 % | +6,3 % | 54 % | 34 % | 34 % |
| 12–20 % | 296 | −1,2 % | +6,9 % | 54 % | 31 % | 31 % |
| **≥ 20 %** | 123 | **+9,8 %** | **+22,1 %** | **36 %** | 14 % | 50 % |

Uma venda grande é moeda ao ar para os 60 s seguintes; as maiores (≥ 20 %) são seguidas de repique. **Não há X.**

**Recomendação para a T4.69:** não implementar "vender na primeira venda ≥ X % / de carteira inicial ≥ Y" como saída. Se for ligada mesmo assim, X ≥ 12 % e Y ≥ 20 M tokens (efeito nulo nas 8 e na população — não faz mal, não faz bem). O que os mesmos dados apontam:

1. **Entrada, não saída:** a saída em bloco das carteiras iniciais (Cupsey 05:47:21: 5 iniciais, 10 vendas, 19 % do `real` em 1 s) precedeu o colapso em 2 min e estava na fita 33 s antes de Cupsey#2 comprar. É o `early_retention_pct`/`quick_flip_share_30s` da T4.66 (não implantada) — ligar como **portão de entrada** e medir.
2. **Trailing:** nas 8, o trailing de 10 % armado na entrada custou XCrypto, NARKY#1 e FЕРЕ. Simulação na mesma fita (`var8.py`, baseline simulado da regra atual +0,0012 SOL): trailing 20 % → +0,0105; 30 % → +0,0498; sem trailing (só alvo + 5 min) → +0,0291. Na população de 82: trailing 10/15/20/30 %/nenhum dá média −0,24/−0,12/**+0,01**/−0,93/−1,46 % e acerto 46/49/51/55/57 % — a largura muda a forma (mais acertos, cauda esquerda mais longa: p10 −24,5 → −46,7 %), não a esperança. Amostra de 8 é favorável (3 alvos); não decidir por ela.
3. **Execução:** a falha `6003` de EQUITITTY custou 5 s, mas o pouso com pânico daria o mesmo −25 %; os pousos de 3,6–5,7 s (XCrypto, FЕРЕ) com taxa no piso não custaram preço (−0,06 %, −0,94 %). Slippage mediano −0,07 %: a execução **não** é o problema desta noite.

## 7. Ressalvas

- Fita = `swap_api` por REST, `received_at` 48–65 s depois do bloco: serve para análise, **não** para uma regra em tempo real — o executor teria de julgar pelos `TradeEvent` do `logsSubscribe` que já recebe (T4.63), o que dá ~1,2–1,5 s do bloco à decisão.
- Cupsey#2 sem fita (a fita da moeda para às 05:48:06); Cupsey#1 com lacuna (reservas na saída diferem 0,49 SOL, ~1 %). As outras 6 fecham a 0,0015 SOL.
- Marcas por frame do executor não são persistidas — o pico da linha (`high_water_sol`) bate com a fita nas 6 verificáveis; o resto da trajetória é reconstruído.
- Contrafactuais ignoram o nosso próprio impacto (0,07 SOL em curvas de 9–32 SOL de `real_sol`: 0,2–0,8 %) e usam L = 2 s uniforme; com L = 1 e 3 s a ordenação das regras não muda.
- População: 82 entradas em 24 h de um laboratório que já roda perto de zero; a regra do Everton simulada na fita dá −0,24 % de média. As 8 reais (+3 alvos em 8) são amostra favorável.
- `sol_final` de CYBER = 0,0207 (sizing por participação) — a única posição menor que 0,07.

## 8. SQL e código

`.claude/state/r62/`: `q1.sql` (posições), `q2.sql` (ordens com `intent.exit_reason`, `min_sol_output`, `priority_fee`, `fill`), `q3.sql` (cobertura por mint), `q4–q6.sql` (fita, fotos, 15 s), `q7–q9.sql` (apostas de papel + fita), `analyze.py` (reconstrução e linhas do tempo → `out1.txt`), `sim.py` (grade X/Y nas 8 → `sim2.txt`), `pop.py` (população), `cond.py` (condicional), `post.py` (pós-saída), `var8.py` (larguras de trailing), `positions.json`.

```sql
-- as 8 posições (q1.sql)
SELECT p.id, p.mint, t.symbol, p.entry_at, p.exit_at, p.tokens, p.sol_spent_lamports, p.sol_received_lamports,
       p.pnl_sol, p.r_multiple, p.high_water_sol, p.mark_sol, p.mark_at, p.params, p.exit_intent, p.exit, p.entry
FROM meme_live_positions p LEFT JOIN meme_tokens t USING (mint)
WHERE p.entry_at >= '2026-09-19 03:00:00+00' ORDER BY p.entry_at;

-- ordens e carimbos (q2.sql)
SELECT o.proposal_id, t.symbol, o.side, o.attempt, o.status, o.reason, o.received_at, o.simulated_at, o.submitted_at, o.settled_at,
       o.intent->>'exit_reason', o.intent->>'min_sol_output', o.intent->'priority_fee', o.fill->>'sell_net_lamports', o.fill->>'block_time'
FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id JOIN meme_tokens t ON t.mint = p.mint
WHERE o.received_at >= '2026-09-19 03:00:00+00' ORDER BY o.received_at;

-- fita de uma moeda (q4.sql)
SELECT block_time, received_at, slot, signature, event_index, trader, side, sol_lamports, token_amount, price
FROM meme_trades WHERE mint = :mint AND block_time >= :t0 AND block_time < :t1 ORDER BY slot, signature, event_index;
```
