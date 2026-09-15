---
tags: [knowledge, nota, plantao, meme, pumpfun, holder-rewards, programa, upgrade, instrumento]
tema: memecoin / pump.fun / `is_holder_reward` passou a ser exposto fora da cadeia (REST `/coins`, boards `hr`, indexer `isHolderReward`) com os primeiros positivos observados, e o programa da curva foi reimplantado de novo em 15/09/2026 ≈ 07:34 BRT (segunda fronteira de `program_version`)
fonte: `frontend-api-v3.pump.fun` (`/coins` 70 mais novas, `/coins/mayhem-mode?limit=60`, `/coins/{mint}` ×10); `advanced-indexer.pump.fun` (`boards/{movers,graduating,graduated}`, `in-memory-coin` ×6); `api.rugcheck.xyz` ×2; `api.dexscreener.com` (`tokens/v1` 50 graduadas, `orders/v1` ×5); RPC público da Solana (`getAccountInfo` do `ProgramData` em base64 com `dataSlice`, `getBlockTime`); `pump.fun/coin/{mint}` ×2 (texto SSR)
fonte_url: https://frontend-api-v3.pump.fun/coins?sort=created_timestamp&order=DESC&limit=70&includeNsfw=true
lido_em: 2026-09-15
evidencia: medição própria (plantão T4.64, run 19, lane 3, 16:19:32–16:29:36 BRT; 30 GETs a hosts pump.fun, brutos em `.claude/state/plantao-meme/raw-lane19/`) + fato on-chain (slot e hora do bloco do deploy, lidos 16:25:03–16:26:58 BRT); o flag é da REST/indexer com `received_at` nosso — o byte `is_holder_reward` da `BondingCurve` não foi lido em moeda nenhuma; conteúdo do segundo upgrade não lido; recortes de 50/60/70 condicionados ao board — descrição, não taxa
hipotese_testavel: sim
astra: ver seção Astra (run 19; parecer em `.claude/state/astra-review-plantao-meme-20260915-1616.md`)
status: vivo
owner: sexta-feira
updated: 2026-09-15
confiança: "?"
---

# KB-0096 — pump.fun: `is_holder_reward` na REST (primeiros positivos) e o segundo deploy do programa em 15/09/2026

**Plantão T4.64, run 19, lane 3 (16:16–16:4x BRT), primeiro run após dois dias suspensos.** Rascunho: `.claude/state/plantao-meme/2026-09-15-1616-lane3.md` (§A, §B, itens 1–2). Brutos:
`.claude/state/plantao-meme/raw-lane19/` (`06_coins_newest70_trim.json`, `07_coins_mayhem_mode60_trim.json`, `08_is_holder_reward_census.json`, `09_holder_reward_boards_extract.json`, `03–05_boards_*`,
`31_rugcheck_hr_*`, `48_dexscreener_orders_hr5.json`, `53_rpc_programdata_trim.json`, `55_rpc_blocktime_447228373.json`). Continua a [[KB-0094-pump-fun-upgrade-de-12-09-2026-holder-rewards-e-bonding-curve-v2|KB-0094]]
(que registrou a chave **ausente** em 270/270 linhas em 12/09) e a [[KB-0095-pump-fun-rotulos-observados-do-site-da-rest-e-os-limites-on-chain|KB-0095]] (camadas template / valor visto / semântica validada).

## O fato medido

| o quê | valor | como/onde | lido em (BRT) |
|---|---|---|---|
| chave `is_holder_reward` na listagem `/coins` (70 mais novas, 58 chaves; 12/09: 55 chaves, sem ela) | **true 7 / false 63** | `https://frontend-api-v3.pump.fun/coins?sort=created_timestamp&order=DESC&limit=70&includeNsfw=true` | 16:19:37 |
| os 7 positivos | 5 × "BARRON" ("OFFICIAL BARRON COIN/Token"; 8 BARRON nas 70, 5/8 HR), " " (`7GBR4kzP…`), "Slingoor" (`sM4Vfzju…`); criadas 16:17:29–16:18:04; **7 criadores distintos**; quote `6p6xgHyF…` ×3, `DJTu7vi8…` ×2 (pares custom), SOL nativo ×2; `twitter` post 6/7 (3 apontam `x.com/0xalank/status/2099940298738598226`); `mayhem_state` ausente 7/7; mcap US$ 2,8–5,1 k | idem | 16:19:37 |
| chave `hr` nos boards do indexer (nova; run 15 tinha 48 chaves sem ela) | movers **7/50** (GIGADOG #18 mc 114 k, CAT #36 mc 122 k, REPLYGUY, BARRON ×2, " ", birds) · graduating **5/50** · graduated **10/50** | `https://advanced-indexer.pump.fun/boards/{movers,graduating,graduated}?offset=0&limit=50` | 16:19:32–35 |
| chave `isHolderReward` no `in-memory-coin` (66 chaves; 12/09: 65) | false 6/6 servidas | `https://advanced-indexer.pump.fun/in-memory-coin/{mint}` | 16:19:40–52 |
| `/coins/mayhem-mode?limit=60` e `/coins/{mint}` ×10 (Mayhem frescas) | false 60/60 e 10/10 — **nenhuma Mayhem é HR nesta amostra** | `frontend-api-v3` | 16:19:38; 16:19:53–16:20:06 |
| graduadas HR (10/50; todas `pg=pump`, `pa=SOL`, 0 Mayhem) | `gd − criada`: 4 ≤ 60 s · 4 (60 s, 5 min] · 2 > 5 min; medianas `t10` **21,7 %** · `bo` 1,14 · `sn` 41 · `nh` 286 · mc US$ 6 721 — não-HR pump (34): 5,2 % · 0,11 · 24 · 157 · US$ 2 533; DEX Screener `info` 5/10 vs 10/34, boosts 0/10 vs 4/34; 2/10 do criador `6ePbEv…` | board `graduated` + `api.dexscreener.com/tokens/v1/solana/{50}` | 16:19:35; 16:29:25–27 |
| pedidos pagos nas HR graduadas | MEME COIN tokenProfile aprovado 15:35:26 (`gd` 15:31:18) + CTO 15:49:37; **Clarity 14:37:46 com `gd` 15:06:53 (carimbo 29 min antes do pool)**; CCOIN 16:07:14 (`gd` 15:47:22); THOM, NAY vazios | `api.dexscreener.com/orders/v1/solana/{mint}` | 16:29:28–33 |
| ferramentas sem vocabulário | rugcheck (GIGADOG, CHINESE): 0 menções a reward/holder/cashback, riscos vazios, score 1, `topHolders` 10 primeiros **com pool** 31,6 % / 54,5 %; DEX Screener: nenhuma chave | `api.rugcheck.xyz/v1/tokens/{mint}/report` | 16:29:35–36 |
| rótulo da página | "Rewards → creator" em DOOM e FAK U; **nenhuma página de moeda HR aberta** (orçamento) — "Rewards → holders" segue não visto | `https://pump.fun/coin/{mint}` (texto SSR) | 16:23:13–16 |
| **segundo deploy do programa da curva** `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | `ProgramData` `B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu` → **slot 447 228 373**, autoridade de upgrade presente (contexto 447 328 953) | `getAccountInfo(base64, dataSlice 0..45)` em `https://api.mainnet-beta.solana.com` — o `jsonParsed` devolveu 13,98 MB e foi descartado | 16:25:03 |
| hora do bloco do deploy | `getBlockTime(447228373)` = 1789468472 = **2026-09-15 10:34:32Z ≈ 07:34:32 BRT** (estimativa do bloco) | RPC | 16:26:58 |
| coerência com a fronteira anterior | 447 228 373 − 446 462 760 = 765 613 slots; a 187–191 slots/min medidos hoje ≈ 67–68 h; 12/09 12:24 → 15/09 07:34 = 67,2 h | `getRecentPerformanceSamples` | 16:21:41 |

Denominadores: 70 + 60 + 10 linhas REST (observações repetidas de mints, não ensaios), 150 entradas de board (3 × 50, condicionadas), 6 imc, 2 rugcheck, 2 páginas. Nada disto é taxa-base de "moedas HR por criação" — o denominador de criações continua ausente (KB-0091).

## Observação, intervalo de introdução e validações pendentes (must-fixes 1, 2 e 4 da Astra)

- **Observado:** a chave existe e tem positivos **na lista `/coins` (7/70) e nos boards (`hr`: 7/50, 5/50, 10/50)**; no imc as 6 respostas válidas foram `false` (+ 4 × 404) e os 10 detalhes eram Mayhem `false`. **Presença da chave ≠ positivos ≠ concordância.**
- **Intervalo de introdução:** o flag foi **observado pela primeira vez em 15/09 16:19 BRT**; a introdução está situada **entre as leituras de 12/09 18:45 (ausente em 270/270) e 15/09 16:19** — não é datada, e **não se sabe se coincidiu com o deploy** das 07:34.
- **Último deploy observado:** `ProgramData.slot` informa o último deploy, **não exclui upgrades intermediários** entre 12/09 12:24 e 15/09 07:34; as duas fronteiras conhecidas delimitam **pelo menos três períodos**.
- **Pendente:** validação prospectiva do flag contra o byte da `BondingCurve` (mesmos mints, decoder validado, tolerância temporal, classes ausente/erro/desconhecido; concordância entre APIs pode ser origem compartilhada; cobertura por fonte incluindo moedas nunca servidas) — M-D9 ampliada (adenda M-D13).

## O que muda para o Meme Radar (regra de casa)

1. **A exposição de M-P34 tornou-se observável fora da cadeia** — como flag da REST/indexer com `received_at` nosso, **não** como o byte da `BondingCurve`. Entra como "observado na REST/board/imc", com fonte, endpoint, `received_at` e `program_version`,
   classes `true` / `false` / **ausente** / **erro** / **desconhecido** separadas ("ausente" não é `false`). A coleta bruta começa já (Astra); a validação contra o byte on-chain é M-D9 + adenda M-D13, e M-D9 (rótulo da página) passa a ter positivos na REST contra os quais medir.
2. **`program_version` (M-D8) tem duas fronteiras conhecidas desde hoje:** 446 462 760 (≈ 12/09 12:24:04) e **447 228 373 (≈ 15/09 07:34:32, último deploy observado)** — pelo menos três períodos, intermediárias possíveis. Decoders de `TradeEvent`/`BondingCurve` (T4.2g/T4.12/T4.14)
   precisam de re-teste com eventos posteriores a 07:34 (**primeira da ordem da Astra**); o conteúdo do upgrade não foi lido.
3. Observação exata sobre os positivos: **5 BARRON entre 7, com 7 identificadores de criador distintos**, 5/7 com par custom (M-D1/Custom Pairs) — repetição de símbolo no recorte não mede `symbol_dup_24h` nem identidade econômica; qualquer braço de M-P34 controla quote **pelo mint**
   com sobreposição entre braços, agrupa clones/criadores e confirma em período posterior — M-P39 pergunta, aos 5 min, se sobra informação.
4. Ferramentas públicas não ajudam aqui: rugcheck e DEX Screener não têm o conceito; o `topHolders` do rugcheck inclui o pool (31,6/54,5 % com pool vs ex-pool — a régua de concentração do Radar deve declarar qual usa; M-D2). "21,7 % vs 5,2 %" é descrição de 10 vs 34 graduadas com composições diferentes.

## Hipótese testável

**M-D13** (diagnóstico de fonte, linha própria vinculada a M-D9/M-P34/M-D8) e **M-P39** (exploratória, prospectiva; previsão: sem ganho incremental) — linhas em [[00-INBOX/Hipoteses-do-plantao]].

## Por que pode falhar

O flag da REST pode ser derivado de metadata e não do byte on-chain (por isso M-D13); pode aparecer com atraso variável por fonte (lista × detalhe × board × imc); os 7 positivos vêm de 3 minutos de criação e de um cluster de clones — nada generaliza; o segundo deploy pode ser
correção sem mudança de layout (ou não) — sem ler IDL/docs não se sabe; `getBlockTime` é estimativa; a REST pode voltar a esconder a chave.

## Astra
Parecer do run 19 (`.claude/state/astra-review-plantao-meme-20260915-1616.md`, 16:39:20–16:41:33 BRT): "registraria a KB-0096 agora, após as correções textuais, como **novidade observada de contrato e último deploy observado**; a validação prospectiva fica explicitamente pendente" — é o que esta
nota é. Ordem: M-D8 → validar HR (M-D9 ampliada; M-D13 como adenda) → Mayhem em M-D11; coleta bruta de HR em paralelo. Must-fixes 1, 2, 4, 5 aplicados aqui; 3, 6, 7 nas linhas e na nota do dia [[02-MARKET/Meme/2026-09-15]] (seção "Run 19"). Pede adendos em KB-0094 (nova fronteira, sem presumir conteúdo)
e KB-0095 (`buy_zero_amount`; ausência do objeto `mayhem` por endpoint) — fora dos caminhos desta lane, ficam para o orquestrador.

## Adendo — T4.8c (15/09/2026, engenharia de integração): a cadeia lida, o conteúdo do upgrade e a leitura do byte on-chain

Captura só-leitura no RPC público, 16:53–17:21 BRT, fixtures `t48c_*` em
`packages/exchange-adapters/tests/fixtures/pumpfun/`; comandos em `.claude/state/notes-T4.8c.md`;
detalhe em `docs/PUMPFUN-ONCHAIN.md` §6d. Nenhum `sendTransaction`.

- **Conteúdo do upgrade, agora lido:** desta vez a conta da IDL on-chain *foi* republicada (o deploy de
  12/09 tinha deixado ela intocada) — 40 → 47 instruções, `TradeEvent` 32 → 34 campos nomeados; o
  on-chain só alcançou o que a IDL `main` do GitHub já mostrava. `buy`/`sell` legados e o `TradeEvent`
  continuam byte a byte iguais (paridade provada com um `buy` e um `sell` reais de hoje); taxas no
  mesmo tier (95/30 bps). Uma instrução nova (`sell_v2`) apareceu no roteador do site.
- **`is_holder_reward` tem byte confirmado na `BondingCurve` — e não é estado novo.** Depois de
  `quote_mint`: `creator_fee_bps: u64`, `can_edit_creator_fee: bool`, `is_holder_reward: bool` (offset
  124). Confirmado `true` na cadeia para `7qSzmCMq…pump` ("COFFEE SHOP", a mesma moeda que a REST
  reporta `is_holder_reward: true` na listagem lida por esta tarefa) e `false` numa moeda de controle
  da mesma listagem. **Isto corrige a moldura do achado original:** o byte **já existia desde pelo
  menos 12/09** (a captura do T4.2f daquele dia já tinha 45/100 contas no layout estendido, uma com
  `creator_fee_bps` não-zero) — inclusive nas próprias moedas de referência da T4.8/T4.8b, paradas
  desde 12/09, que já estão nesse layout ao serem relidas hoje. O decodificador deste pacote
  simplesmente nunca olhava além do byte 115. **O que mudou de fato foi a REST/indexer passarem a
  expor o valor** (o próprio achado desta KB) — não o byte on-chain nascer agora. O mecanismo exato
  (alocação na criação vs. realloc posterior) não foi determinado dentro do orçamento de RPC da tarefa.
- **Simulação mainnet pelo caminho do executor** (`sigVerify=false`, nunca enviada): `buy` ok numa
  moeda clássica (103 096 CU), numa `is_holder_reward = true` (104 600 CU) e numa Mayhem (87 286 CU);
  `sell` ok na clássica (62 037 CU) e na Mayhem (49 556 CU). **Venda de moeda HR não obtida:** a
  candidata mais barata ainda não tinha comprador real na cadeia (só *snipers* falhos); a segunda
  candidata (maior *market cap*) é cotada num token custom — `build.py` a recusou por nome
  (`unsupported_quote`) antes de simular, o mesmo guarda que a T4.8b já tinha para moedas USDC.
- **Continua não estabelecido:** um `holder_rewards`/`holder_rewards_bps` não-zero no `TradeEvent` —
  os dois fills reais de hoje (nenhum numa moeda HR) leram 0, como todos os de 12/09. A validação
  prospectiva do flag contra o byte (M-D9/M-D13) segue pendente, agora com a leitura on-chain provada
  e disponível como referência.

## Ligações
[[02-MARKET/Meme/2026-09-15]] · [[00-INBOX/Hipoteses-do-plantao]] · [[KB-0094-pump-fun-upgrade-de-12-09-2026-holder-rewards-e-bonding-curve-v2]] · [[KB-0095-pump-fun-rotulos-observados-do-site-da-rest-e-os-limites-on-chain]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · [[KB-0093-dex-paid-e-boost-o-que-custam-e-o-que-medem]] · [[README-meme]]
