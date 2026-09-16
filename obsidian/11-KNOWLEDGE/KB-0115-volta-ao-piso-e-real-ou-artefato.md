---
tags: [meme, pumpfun, knowledge, curva, dados, mayhem, fita, m4]
data: 2026-09-16
janela_medida: 16:00–17:35 BRT (19:00–20:35 UTC) — a série acaba no relógio da medição
medido_em: 2026-09-16 17:35–17:52 BRT (20:35–20:52 UTC, `date -u` conferido)
fonte: banco da VPS (meme_features_1m, meme_curve_snapshots, meme_trades, meme_tokens) + leitura ao vivo da cadeia por RPC público
sql: infra/scripts/sql/research/2026-09-16-r33-q0{1,2,3,4}-*.sql
script: infra/scripts/research/2026-09-16-r33-curva-ao-vivo.py
owner: astra/quant
status: vivo
confianca: alta para a conclusão principal (a cadeia confirma em 135/135 e em 10/10 ao vivo); média para a cobertura da fita (janela de 3 h truncada em 1 h 35)
updated: 2026-09-16
---

# KB-0115 — a "volta ao piso" de metade das moedas é real ou artefato da série?

> **A pergunta.** A [[03-TRADING/Meme/Candidatas/2026-09-16-17h30-brt|R30]] §4.3 mediu que **997 de
> 2 001 moedas (49,8 %)** terminam a hora com `mcap_sol` entre 27,9 e 28,3 SOL e progresso < 5 %, e
> deixou a ressalva honesta de que não dava para separar "a curva foi vendida de volta ao piso" de
> "a linha de 1 min foi reconstruída do zero". NIKKI perdendo **258 holders em 60 s** era o sintoma.
> Isto contamina todo "desfecho" medido até aqui ([[03-TRADING/Meme/Candidatas/2026-09-16-17h02-brt|R23]],
> R30, [[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]],
> [[11-KNOWLEDGE/KB-0110-saida-por-drawdown-20-na-serie-de-15s|KB-0110]]).
>
> **Honestidade de relógio:** o brief pediu 16:00–19:00 BRT; às 17:35 BRT (20:35 UTC) a série ainda
> não tinha as duas últimas horas. Tudo abaixo é **16:00–17:35 BRT**, 624 moedas com pico ≥ 40 SOL.
>
> **Unidades:** `curve_progress_pct` é fração (0,05 = 5 %); `mcap_sol` em SOL; o piso da curva vazia
> é `30 / 1 073 000 191 × 1e9 = 27,96 SOL` — **e esse piso só vale para curva não-Mayhem** (§4).

## 1. Conclusão em quatro linhas

1. **É real.** Nas **135 moedas** que "voltaram ao piso" (pico de `mcap_sol` ≥ 40 SOL e última foto
   ≤ 28,5 com progresso < 0,05), a cadeia — `meme_curve_snapshots.real_sol_reserves` lido por
   `solana_rpc`, `finalized` — diz **curva vazia em 135 de 135** (100 %): média de **14,41 SOL reais
   no pico → 0,035 SOL na queda**. Dez delas, lidas **ao vivo por RPC agora** (slot 447 615 774+),
   têm entre **0,0014 e 0,14 SOL** na conta da curva. Não é a série que reinicia: é o SOL que sai.
2. **Não é troca de fonte nem falha do leitor de holders.** 110 das 135 já estavam em `solana_rpc`
   antes da queda e continuam nele; as 24 que trocaram (`pumpfun_rest` → `solana_rpc`) têm a
   **mesma** leitura de cadeia (11,33 → 0,018 SOL, 24/24 vazias). `holders` vem de `trenches_ws` em
   130/135 e **não fica NULL na queda** (3 `no_holders_reader` já eram nulos antes).
3. **O artefato existe, mas é outro e é menor: Mayhem.** **22 das 135 (16,3 %)** são moedas
   `mayhem_enabled` — a mecânica Mayhem reescreve as reservas *virtuais*, quebra a invariante
   `virtual_sol − real_sol = 30 SOL` e derruba `mcap_sol` **abaixo** do piso de 27,96 (até 0,05 SOL,
   e `curve_progress_pct` chega a **−0,0859**). **As 22 moedas da coorte com `mcap_sol` < 27,9 são
   exatamente as 22 Mayhem, e nenhuma delas migrou.** Para elas `mcap_sol`/`curve_progress_pct` não
   são comparáveis com os de uma curva normal.
4. **O dado que está mesmo quebrado é a fita.** `meme_trades` explica **5,0 %** do SOL que saiu da
   curva, e **só 21 das 135 (15,6 %)** têm *qualquer* negócio registrado na janela da queda. A fita
   **não pode** ser a fonte de desfecho nem de fluxo; `real_sol_reserves` pode.

## 2. A cadeia versus a série (q01, q02)

| coorte | moedas | pico médio | `mcap` final | `real_sol` no pico | `real_sol` na queda | cadeia diz vazia |
|---|---|---|---|---|---|---|
| **voltou ao piso** | **135** (21,6 %) | 68,1 SOL | 24,95 | **14,41** | **0,035** | **135/135** |
| não voltou | 489 | 128,5 SOL | 110,35 | 15,71 | 5,39 (+6 min) | 20/489 tiveram queda |

O caso que motivou a dúvida, **NIKKI `AYrp8o…`**, linha a linha na mesma conta, mesmo `finalized`:

| `observed_at` | slot | `virtual_sol` | `real_sol` | `mcap_sol` |
|---|---|---|---|---|
| 20:24:09 | 447 612 566 | 66,808 | 36,808 | 138,65 |
| 20:24:24 | 447 612 613 | 72,381 | **42,381** | 162,75 |
| **20:24:40** | 447 612 664 | 30,648 | **0,648** | **29,18** |
| 20:25:29 | 447 612 728 | 30,092 | 0,092 | 28,13 |

**41,7 SOL saíram em 51 slots (~16 s)**, `complete = false`, `total_supply` inalterado,
`virtual_sol − real_sol = 30,000` antes e depois — a invariante da curva **se mantém**. Uma
reconstrução da linha não produziria uma trajetória assim; uma debandada produz.

## 3. A fita não cobre (q02)

Na janela `[pico − 1 min, queda + 3 min]` das 135:

| SOL que saiu da curva (cadeia) | saída líquida na fita | fração explicada | moedas com fita | fita explica ≥ 80 % |
|---|---|---|---|---|
| **14,38 SOL** (média) | **0,72 SOL** | **5,0 %** | **21/135** | **5/135** |

Na vida inteira da NIKKI a fita tem **303 negócios, 19,66 SOL comprados e 21,59 vendidos** — mas a
curva chegou a **42,38 SOL reais**. A fita vê ~**46 %** do que entrou e ~**5 %** do que saiu. O feed
`swap_api` é amostral, não é o livro. Todo número de fluxo / `unique_buyers` / `buy_sell_ratio`
derivado dela é um **piso**, nunca um total — e comparar `net_sol_flow` com o movimento da curva é
inválido.

## 4. Mayhem quebra o piso (q04)

A invariante de uma curva pump normal é `virtual_sol_reserves − real_sol_reserves = 30 SOL`, o que
põe a curva vazia em **27,96 SOL** de `mcap_sol`. Nas fotos `solana_rpc` da janela:

| coorte | linhas | invariante ok | moedas que quebram | moedas |
|---|---|---|---|---|
| voltou ao piso | 2 820 | 2 350 | **22** | 135 |
| não voltou | 9 822 | 5 577 | **205** | 451 |

Na coorte do piso, **as 22 que quebram a invariante são as 22 `mayhem_enabled`** (20 `auto`,
2 `manual`) e **as 22 com `mcap_sol` < 27,9 são exatamente essas** — nenhuma migrada. ANSEM
`HsDJv6…` mostra o efeito: `virtual_sol` de **43,54** (com 0,91 real) às 20:33 e **0,324** (com
0,0011 real) um minuto depois — a leitura ao vivo por RPC confirma `is_mayhem_mode = true` e os
mesmos bytes. **Não é decodificação errada: é a curva Mayhem sendo reescrita pelo programa.**

## 5. Leitura ao vivo da cadeia, agora (10 moedas)

`infra/scripts/research/2026-09-16-r33-curva-ao-vivo.py` deriva o PDA `["bonding-curve", mint]` com o
helper de produção (`hunter_exchanges.pumpfun.tx.bonding_curve_address`), chama `getAccountInfo` no
RPC público e decodifica com `decode_bonding_curve_account`. Slot 447 615 774–447 615 788:

| símbolo | pico na série | `real_sol` ao vivo | lamports na conta | `mcap_sol` ao vivo | Mayhem |
|---|---|---|---|---|---|
| X `E9paxi…` | 258,3 | 0,0264 | 0,0278 | 28,01 | não |
| ANSEM `HsDJv6…` | 226,7 | 0,0011 | 0,0025 | **0,31** | **sim** |
| HODL `3N4gx8…` | 224,4 | 0,0109 | 0,0123 | **0,50** | **sim** |
| KIRKJAK `24xjxm…` | 215,5 | 0,0113 | 0,0127 | **10,81** | **sim** |
| EVOLVE `3DdJUA…` | 196,0 | 0,0000 | 0,0014 | 27,96 | não |
| CINNAMON `Bv8cVB…` | 184,8 | 0,0661 | 0,0675 | 28,08 | não |
| Hii-kun `D81Hqh…` | 169,7 | 0,0141 | 0,0155 | 27,99 | não |
| Deaton `JCVVtP…` | 156,5 | 0,0050 | 0,0064 | **0,05** | **sim** |
| SUNNY `5AWmq8…` | 151,6 | 0,1396 | 0,1410 | 28,22 | não |
| NIKKI `AYrp8o…` | 132,6 | 0,0717 | 0,0731 | 28,09 | não |

**Dez em dez confirmam a série.** A conta da curva de uma moeda que chegou a 258 SOL de `mcap` tem
**0,028 SOL** dentro. O `real_sol` ao vivo bate com a última foto de cada uma (NIKKI: 0,0717 ao vivo
vs 0,0920 às 20:26 — a diferença é quem vendeu depois).

**Achado lateral, para conferir:** em **KIRKJAK** o PDA derivado (`DaHQAr4n…`) **não** é o
`meme_tokens.bonding_curve` gravado pelo REST (`BwWK17cb…`), apesar de o derivado responder com uma
curva Mayhem válida. Nas outras nove bateu. Vale uma consulta própria: moedas Mayhem podem usar
`["bonding-curve-v2", mint]` (`pumpfun/tx.py` já deriva esse PDA) e o REST pode estar mostrando o
outro. Não muda nada desta KB — a conta derivada está vazia de qualquer jeito.

## 6. O que corrigir

1. **`real_sol_reserves` é a fonte de desfecho, não `meme_trades`.** Refazer os desfechos de R23,
   R30, KB-0108 e KB-0110 sobre `max(real_sol_reserves) → min(real_sol_reserves)` da janela. A
   direção das conclusões não muda (a volta ao piso é real), mas a **magnitude do fluxo** muda muito.
2. **Nomear a lacuna da fita.** `tape_source = swap_api` cobre 15,6 % das moedas na queda; o
   `tape_reason` deveria dizer `tape_partial` quando a saída líquida da fita contradiz o Δ de
   `real_sol_reserves` por mais de, digamos, 3×. Hoje a fita *parece* completa e não é.
3. **Mayhem precisa de refusal própria em `mcap_sol`/`curve_progress_pct`.** Um `curve_reason =
   'mayhem_curve_reset'` (ou um `progress_reason` equivalente) quando
   `|virtual_sol − real_sol − 30| > 0,01`, em vez de publicar `mcap_sol = 0,05` e progresso
   **negativo**. Um progresso negativo é um número que a porta não deveria nem ver.
4. **A porta deve excluir Mayhem por enquanto** — 22 das 135 do piso e 205 das 451 do "não voltou"
   têm a curva reescrita; nenhum teto calibrado em curva normal se aplica a elas.

## Ligações

[[03-TRADING/Meme/Candidatas/2026-09-16-17h30-brt|Candidatas R30 (a ressalva que gerou esta KB)]] ·
[[03-TRADING/Meme/Candidatas/2026-09-16-17h02-brt|Candidatas R23]] ·
[[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] ·
[[11-KNOWLEDGE/KB-0110-saida-por-drawdown-20-na-serie-de-15s|KB-0110]] ·
[[11-KNOWLEDGE/KB-0114-compradores-unicos-o-piso-e-o-r|KB-0114]] ·
[[03-TRADING/Meme/README|Meme (catálogo)]] ·
`infra/scripts/sql/research/2026-09-16-r33-q0{1,2,3,4}-*.sql` ·
`infra/scripts/research/2026-09-16-r33-curva-ao-vivo.py`
