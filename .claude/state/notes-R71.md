# R71 — Ampliar o mapa da mesa `spot/1`: quais mercados sinalizados pelo Lab existem mesmo na Solana

**Data:** 2026-09-23, medições entre 19:30 e 19:50 UTC (16:3x–16:5x BRT). **Pergunta (Everton, 16:5x BRT):** metade dos sinais da mesa `spot/1` cai em mercados fora do mapa (`spot_desk_markets`, 50 linhas, 35 ligadas). Mapear DASH, PROM, NEAR e XRP — e, com o escopo ampliado ("aumente o máximo que der, sem afrouxar critério"), **todo** mercado em que a família `mean_reversion` disparou ≥ 1 vez em 14 dias e que não está no mapa.

**Resposta curta.** A lista de candidatos é grande (**68 símbolos**), mas só **6** deles têm token na Solana que passe no filtro. Dos outros 62, SOLUSDT fica fora por desenho e **61 não têm nenhuma representação validada**: 51 não têm token com aquele símbolo na lista verificada da Jupiter, e 10 têm só homônimo falso (a armadilha dos 54 do R63 §2). **O maior buraco continua aberto: DASHUSDT.** São 121 sinais da família em 14 dias, 94 em 7, e 11 do `mean_reversion/v14` (a versão que a mesa consome) em 7 dias. Não encontramos DASH validado na Solana: os dois "DASH" da busca aberta da Jupiter são memecoins não verificadas, a 0,00026 US$ contra 58,38 US$ na Binance (−100 %). O mesmo vale para PROMUSDT (72 sinais em 14 d; o único PROM é uma memecoin a 0,0000032 US$), EGLD, KAS, BR, PIEVERSE e mais 55.

Os 6 que passam entram pela migração **`0061_spot_desk_r71`**:
- **3 nascem ligados:** NEARUSDT, BTCUSDT e ORCAUSDT.
- **1 nasce desligado pela regra do R63/0057:** SLXUSDT (tier C).
- **2 nascem desligados por decisão explícita desta pesquisa:** XRPUSDT e BIRBUSDT, por riscos que a regra econômica não enxerga (§4).

Nenhum critério foi afrouxado. A regra `enabled` é literalmente a da `0057` (`tier <> 'C' AND ida-e-volta <= 0,4 %`). As duas retenções são **restrição a mais**, e cada uma se desfaz com um comando do `infra/scripts/spot_desk_markets.py --enable`.

**Quanto isso rende por semana (§5):** hoje os 35 mercados ligados recebem **41 sinais `mean_reversion/v14 long` por semana** (61 em 14 dias, em 10 mercados distintos). As linhas ligadas por esta migração acrescentam **+3 sinais/semana**, todos de NEARUSDT (BTC e ORCA não tiveram nenhum v14 no período), ou seja **+7 %**. Liberando XRPUSDT, o ganho sobe para **+5/semana (+12 %)**. Para comparar: só DASH valeria **+11/semana (+27 %)**, e é justamente o que não dá para executar.

## 1. Método (o do R63, sem desconto)

| etapa | como |
|---|---|
| candidatos | Postgres do VPS, **somente SELECT**: `agent_signals × strategy_versions × strategies × markets`, `st.key LIKE 'mean_reversion%'`, `emitted_at >= now() - 14 dias`, `NOT EXISTS` em `spot_desk_markets` → **68 símbolos** (73 linhas, contando perp e spot do mesmo símbolo). Versões ativas da família: v1, v2, v3, v6, v7, v8, v10, v14 e `mean_reversion_h1/v1` |
| lista verificada | `GET https://lite-api.jup.ag/tokens/v2/tag?query=verified` (23/09, 19:35 UTC, **3 591 tokens**), sem as tags `stocks/rwa/xstocks/equities/prestocks`. Casamento por símbolo exato **e** por apelidos de wrapper (prefixos `W`/`SOL`/`X`/`P`, sufixos `W`/`SOL`/`E`/`WH`…). Foi assim que apareceram `wNEAR` e `wXRP`, que o casamento exato do R63 teria perdido |
| identidade | **paridade de preço contra a Binance, medida duas vezes, com duas leituras**: (a) preço-oráculo da Jupiter (`price/v3`) contra `fapi/v1/ticker/price` no mesmo instante; (b) **preço executável**: `swap/v1/quote` de 0,05 SOL → token, convertido pelo `SOLUSDT` da Binance lido no mesmo instante (inclui meia-taxa da pool). Corte do R63: ‖Δ‖ ≤ 3 %. A tag `verified` sozinha não vale nada. Ressalva da Astra: as duas leituras se complementam, mas não são independentes, porque o `price/v3` também vem de swaps e pode olhar as mesmas pools da cotação. Por isso a identidade dos wrappers foi fechada na fonte (§4) |
| custo | ida-e-volta SOL → token → SOL pela `lite-api` (`slippageBps=50`) em **0,02 / 0,05 / 0,2 SOL**. Custo = 1 − SOL de volta ÷ SOL de ida, gravado como **fração**. É cotação: não prova que as duas transações pousariam |
| revisão | a Astra (`.claude/state/astra-review-r71.md`) revisou a evidência de identidade de **cada** mint **antes** da semente, com leitura on-chain (RPC) e registros oficiais |

## 2. A tabela de medição — os 6 que passam

Sinais: `família 14 d / 7 d` conta qualquer versão de `mean_reversion`. `v14 long` é o que a mesa consome de fato (`spot_repo._CANDIDATES`: `st.key = 'mean_reversion' AND v.version = :version AND direction = 'long' AND d.enabled`).

| símbolo | sinais família 14 d / 7 d | v14 long 14 d / 7 d | mint | Δ paridade (oráculo · executável ×2) | ida-e-volta 0,02 / 0,05 / 0,2 SOL | liquidez Jupiter | kind | tier | enabled | por quê |
|---|---:|---:|---|---:|---:|---:|---|---|---|---|
| **NEARUSDT** | 120 / 32 | 10 / 3 | `3ZLekZYq2qkZiSpnSvabjit34tUkjSwD1JFuW9as9wBG` | +0,44 % · −0,02 % / +0,20 % | 0,074 % / **0,144 %** / 0,126 % | 1.955.016 US$ | ponte | A | **sim** | identidade fechada na NEAR OmniBridge; tier A; custo 0,14 % |
| **XRPUSDT** | 44 / 25 | 4 / 2 | `6UpQcMAb5xMzxc7ZfPaVMgx3KqsvKZdT5U718BzD5We2` | +0,34 % · +0,38 % / +0,44 % | 0,311 % / **0,312 %** / 0,324 % | 1.025.805 US$ | ponte | A | **não** | passa na regra, mas fica **retido**: freeze authority ativa do custodiante (§4) |
| **BIRBUSDT** | 17 / 0 | 2 / 0 | `G7vQWurMkMMm2dU3iZpXYFTHT9Biio4F4gZCrwFpKNwG` | −0,14 % · −0,15 % / −0,08 % | 0,009 % / **0,012 %** / 0,027 % | 1.262.831 US$ | nativo | A | **não** | passa na regra, mas fica **retido**: 90,9 % do supply nos maiores detentores (§4) |
| **SLXUSDT** | 7 / 0 | 1 / 0 | `SLXdx4BUt2v9uJQNzWqSfzTJ9UKLUDsvxHFMEEdrfgq` | −0,77 % · −0,34 % / −0,25 % | −0,046 % / **0,073 %** / 0,111 % | 93.126 US$ | nativo | C | **não** | **regra**: tier C (< 100 k US$); custo baixo não compensa |
| **BTCUSDT** | 3 / 2 | 0 / 0 | `3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh` | −0,04 % · −0,01 % / −0,02 % | 0,011 % / **0,004 %** / 0,004 % | 39.144.617 US$ | ponte | A | **sim** | WBTC (Portal), a linha mais líquida do mapa inteiro |
| **ORCAUSDT** | 1 / 0 | 0 / 0 | `orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE` | −0,29 % · +0,15 % / +0,36 % | 0,055 % / **0,110 %** / 0,188 % | 343.934 US$ | nativo | B | **sim** | nativo da Solana, custo 0,11 % |

Os seis são 1:1 com a unidade da Binance (nenhum tem prefixo `1000`). `decimals` fica `NULL` na semente: o executor lê o mint uma vez e grava de volta, como nas 50 linhas da `0057`.

**Prova de identidade por mint** (Astra conferiu cada uma antes da semente):
- **NEAR:** chamadas de leitura ao `omni.bridge.near`. `get_token_id("sol:3ZLek…")` devolve `wrap.near`, e `get_token_address(Sol, "wrap.near")` devolve o mesmo mint. A mint authority `FvULaw…NYds` é a PDA `authority` do programa oficial `bridge_token_factory` (`dahPEoZG…`, bump 255). Por isso o rótulo é `ponte` (OmniBridge), não `representacao`.
- **XRP:** o mint completo aparece no HTML oficial de `hextrust.com/services/wrapping/wxrp`.
- **BTC:** WBTC (Portal) está no registro oficial da Wormhole contra o WBTC da Ethereum (`0x2260fac5…`, decimals 8). A mint authority `BCD75R…YMV7` é a PDA do token bridge Wormhole, a mesma de 37 tokens verificados (ETH, SPX, AUDIO, BNB, AIXBT…).
- **ORCA:** o mint aparece na governança oficial da Orca.
- **BIRB e SLX:** são os mesmos mints do R63 §2, corroborados por anúncios de listagem (BigONE, Gate). Não achamos confirmação direta nos canais do próprio projeto.
- Alternativa descartada para BTC: cbBTC (`cbbtcf3a…`, Coinbase, 29,8 M US$, custo igual). Mesma qualidade de identidade, mas freeze authority ativa. A troca é de risco (dependência da Coinbase contra WBTC + Portal), não de identidade.

**Snapshot on-chain (Astra, `getMultipleAccounts`, `finalized`, slot 449806922).** Os seis são mints SPL clássicos (82 bytes, sem extensões Token-2022). Decimals, mint authority e freeze authority de cada um:

| mint | decimals | mint authority | freeze authority |
|---|---:|---|---|
| NEAR | 9 | `FvULaw…NYds` | null |
| XRP | 6 | `E5GXVz…156o` | **`E5GXVz…156o`** |
| WBTC | 8 | `BCD75R…YMV7` | null |
| BIRB | 6 | null | null |
| ORCA | 6 | `GwH3Hi…x4PV` | null |
| SLX | 6 | null | null |

## 3. Os 62 que não entram (61 sem representação validada + SOL por desenho) — isso é o resultado, não uma falha

| grupo | quantos | exemplos (sinais da família em 14 d) |
|---|---:|---|
| **nenhum token verificado com esse símbolo (nem wrapper)** | 51 | **DASHUSDT (121)**, **PROMUSDT (72)**, EGLD (36), BR (25), PIEVERSE (23), KAS (22), SAHARA (22), FF (18), AKE/LSK/MINA/VVV (16), LA/PHA (15), ETHFI/KAT (14), FLOCK (12), CFG/RAYSOL/TRUTH/VET (9), ALGO/ARK/B2/BTR/CKB/DODOX/KAVA/ORDER/PHAROS/SENT/SOPH/STBL/XAN/XTZ/XVG/ZEN/ZEST/ZK (8), HEMI/SIREN/VTHO (7), COMP/PENDLE/POL (3), 0G/ATOM (2), AERO/DOT/EPIC/STX (1) |
| **homônimo falso** (o token existe, mas a paridade fica fora de ±3 %) | 10 | BTW (−99,99 %), RE, EDGE, ANIME, MIRA, NOM, PORTAL, UAI, ZAMA, STABLE: todas memecoins com o mesmo ticker |
| **fora por desenho** | 1 | SOLUSDT (23 sinais): tem paridade (−0,05 %), mas comprar SOL com SOL não é posição, e a `0057` já o excluiu |

A prova documental do caso DASH (o que mais dói): a busca aberta `tokens/v2/search?query=DASH` devolve **2** tokens com o símbolo exato, nenhum verificado. São `8RWFpyz9…pump`, a 0,00026 US$, e `6ExSckXc…`, a 0,0000034 US$, contra 58,38 US$ na Binance. A frase certa não é "não existe DASH na Solana". É **"não encontramos representação validada nesta busca"**, e sem representação validada a mesa não compra.

## 4. As duas retenções (restrição a mais, nunca afrouxamento)

A regra `enabled` da `0057` só olha **tier e custo**. Ela não sabe quem pode congelar o token nem quem segura o supply. Nos dois casos abaixo a regra diria "liga", e esta pesquisa diz "ainda não".

- **XRPUSDT: freeze authority ativa.** A identidade é boa. O **risco é de saída**: `E5GXVz…156o` é ao mesmo tempo mint authority e **freeze authority**. Uma conta de token congelada não transfere; o stop da mesa dispara e a venda não acontece. A emissão e o resgate da Hex Trust são restritos a participantes institucionais, então a carteira da mesa não tem resgate direto. Manter desligado custa **2 sinais por semana**. Para ligar, Everton precisa aceitar explicitamente que uma posição pode ficar imobilizada.
- **BIRBUSDT: concentração.** Mint e freeze revogadas, identidade igual à do R63, custo ótimo (0,012 %). Mas 90,9 % do supply está nos maiores detentores, sem separar pool, custódia e vesting. Se boa parte for saldo livre de poucos controladores, uma venda concentrada esvazia a liquidez antes do stop. Manter desligado hoje custa **zero**: 0 sinais em 7 dias, e o mercado está `is_monitored = false`.

Nenhum `tier` ou custo foi alterado para produzir esses `false` (a Astra alertou exatamente contra isso). A retenção está numa constante nomeada, `HELD_FOR_REVIEW_0061`, com o motivo escrito ao lado e repetido na coluna `note` da linha.

**Risco de concentração de ponte (registrado, não bloqueia):**
- NEAR entra por um emissor que já assina duas linhas do mapa: ZEC e STRK têm a mesma mint authority. STRK nasceu desligado na `0057` (tier C).
- BTC entra pela mesma PDA da Wormhole que assina ETH, SPX, AUDIO e BNB.
- A própria OmniBridge depende da Wormhole para verificar entradas vindas da Solana, então os dois grupos não são independentes.

Resultado: símbolos diferentes podem perder a âncora no mesmo evento. Vale acompanhar a exposição agregada por ponte ou custodiante.

## 5. Quanto a ampliação acrescenta (o número que justifica o trabalho)

| linha | sinais `v14 long` por semana | comentário |
|---|---:|---|
| mapa atual (35 ligados) | **41** | 61 em 14 dias, em 10 mercados distintos |
| + NEARUSDT (ligado agora) | **+3** | 10 em 14 dias; +7,3 % sobre a base |
| + BTCUSDT, ORCAUSDT (ligados agora) | **+0** | nenhum v14 no período. Entram pelo custo baixíssimo e pela liquidez, para quando dispararem (BTC teve 2 sinais v10/h1 em 7 d, que a mesa não consome) |
| + XRPUSDT (se Everton aceitar o risco de congelamento) | **+2** | total de +5 por semana, +12 % |
| + BIRBUSDT (se a concentração for explicada) | **+1** | 2 em 14 dias |
| **DASHUSDT: impossível** | (+11) | 27 % de sinal que a mesa não tem como executar na Solana |
| **PROMUSDT: impossível** | (+3) | idem |

Se a mesa passasse a consumir a família inteira, e não só a v14, as linhas ligadas agora somariam cerca de 34 sinais por semana (NEAR 32, BTC 2). Mas essa é outra decisão, e não é o que o executor faz hoje.

## 6. Entrega

- Migração **`0061_spot_desk_r71`** (`infra/migrations/versions/0061_spot_desk_r71.py`, DDL em `infra/migrations/ddl/spot_desk_r71.py`), sobre a `0060_meme_refused_probe_arm`. Não muda o esquema: são seis `INSERT` com `ON CONFLICT (binance_symbol) DO NOTHING`, `note` preenchida com a evidência de identidade de cada mint, e `updated_by = 'migration:0061_spot_desk_r71'`.
- O downgrade **recusa** enquanto um `spot_orders` ou um `spot_positions` citar um dos seis (§17.7), com `LOCK` antes da contagem. Fora isso, remove **exatamente os seis**; as 50 linhas da `0057` não aparecem no `DELETE`.
- Teste: `packages/core/tests/integration/test_migration_0061.py`, com 7 casos em Postgres real via testcontainers:
  - cadeia e slug da revisão;
  - constante da semente: 6 linhas, mints base58, nenhuma repetindo a `0057`, `enabled` = regra da `0057` ∧ não retida;
  - números medidos: mint, kind, tier, liquidez e custo como fração;
  - 56 linhas e 38 ligadas depois do upgrade, com **cada mint do banco conferido contra a constante**;
  - insert repetido não sobrescreve linha de operador;
  - `alembic check`;
  - downgrade recusado sob ordem e sob posição, e removendo só os seis quando está livre.
- `HEAD_REVISION` de `packages/core/tests/integration/test_migrations.py` passou para `0061_spot_desk_r71` (**número tomado: 0061**).

```
$ uv run pytest packages/core/tests/integration/test_migration_0061.py -v -p no:randomly
.......                                                                  [100%]
7 passed in 38.97s
```

## 7. Artefatos

Os scripts e JSONs da medição ficaram no scratchpad da sessão: `candidates.tsv`, `verified.json`, `match.py`/`matched.json`, `parity.py`/`parity.json`, `parity3.py`/`parity3.json`, `roundtrip.py`/`roundtrip.json`. Os números que importam estão nas tabelas acima e na constante `SPOT_DESK_SEED_0061`. No VPS, tudo foi `SELECT`; nada foi escrito lá.
