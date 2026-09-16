---
tags: [knowledge, nota, meme, pumpfun, top10, retrato-de-risco, admissao, denominador, mayhem, m5]
tema: por que meme_risk_snapshots.top10_share passa de 1, qual denominador cada fonte usa e qual fonte a admissao real leu nas ordens de hoje
fonte: banco da VPS (meme_risk_snapshots, meme_features_1m, meme_live_orders, meme_proposals), 12-16/09/2026 BRT
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r22-q03-mayhem-explica-o-maior-que-1.sql
lido_em: 2026-09-16
evidencia: medicao propria (SQL em infra/scripts/sql/research/2026-09-16-r22-q0{1..5}-*.sql; 20 486 retratos, 15 565 pares mint-minuto, 24 ordens reais)
hipotese_testavel: sim
astra: nao consultada nesta nota (pesquisa quant, 16/09 ~17h BRT)
confiança: backtest do autor
owner: astra-quant
updated: 2026-09-16
status: vivo
---

# KB-0111 — `top10_share > 1` no retrato de risco: o denominador e qual fonte a admissao usa

**A pergunta que abriu a nota:** o [[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar|KB-0109]] §0 registrou
`meme_risk_snapshots.top10_share = 1,124` — fração acima de 1, denominador suspeito — enquanto `meme_features_1m.top10_share`
fica em 0–1 por CHECK. Se as duas fontes medissem coisas diferentes, o teto de 25 % não significaria a mesma coisa nos dois
lados. **Resposta curta: medem a mesma coisa; o `> 1` é exclusivamente Mayhem; e a admissão real já lê a fonte da mesa.**

## 1. A distribuição (20 486 retratos, 12/09 08:48 – 16/09 16:50 BRT)

| coluna | n com valor | mediana | > 0,5 | **> 1** | máx |
|---|---|---|---|---|---|
| `top10_share` | 20 486 | **0,2580** | 1 274 (6,2 %) | **115 (0,56 %)** | **1,5171** |
| `bundled_share` | 20 486 | 0,0637 | 208 (1,0 %) | **0** | 0,7900 |

`bundled_share` **nunca** passa de 1 — a anomalia é só do top-10. Exemplos (hora BRT, com o campo cru da API):

| BRT | mint | `top10_share` | cru `top10HoldersPercent` | holders | progresso | `dev_share` | mayhem |
|---|---|---|---|---|---|---|---|
| 13/09 06:25 | `8Urn3E` | **1,5171** | `151.7123` | 23 | 100,00 | 0,2995 | `completed` |
| 13/09 06:20 | `8Urn3E` | 1,4858 | `148.5799` | 22 | 100,00 | 0,2995 | `completed` |
| 13/09 06:15 | `8Urn3E` | 1,3183 | `131.8286` | 8 | 43,29 | 0,0855 | `completed` |
| 13/09 01:57 | `2vNP5Y` | 1,3075 | `130.7456` | 5 | 38,77 | 0,0000 | `paused` |

**A API entrega 151,7 %.** O parser (`indexer_rest.py::_opt_fraction`, `Decimal(value) / _HUNDRED`) divide por 100 uma
única vez e está correto — o mesmo `_opt_fraction` produz `dev_share`, `sniper_share` e `bundled_share`, que se comportam.
**Não é bug do parser; é o número da fonte.**

## 2. Quem estoura: Mayhem, e só Mayhem

| `is_mayhem` / `mayhem_state` | n | **> 1** | mediana | mints |
|---|---|---|---|---|
| `true` / `paused` | 80 | **80 (100 %)** | 1,1240 | 8 |
| `true` / `paused` + `mayhemBotCoinSupplied > 0` | 89 | 24 | 0,9961 | 12 |
| `false` / `completed` | 9 | 8 | 1,3706 | 2 |
| `true` / `active` | 4 | 3 | 1,2094 | 4 |
| `false` / `completed` + bot supriu | 3 | 0 | 0,1285 | 3 |
| **`false` / sem estado (a população da mesa)** | **20 319** | **0** | **0,2575** | 2 825 |

**115 de 115 leituras acima de 1 são moedas Mayhem.** Nas 20 319 leituras não-Mayhem o máximo não chega perto de 1.
A leitura mecânica: em Mayhem o bot **injeta oferta** (`mayhemBotCoinSupplied` existe no payload) e o site divide o saldo
do top-10 pelo **`coinCreatedSupply` de criação** (`1000000000000000` sub-unidades em todas as amostras acima, inclusive
nas que dão 151 %) — numerador com oferta nova, denominador congelado no nascimento. Por isso o `dev_share` fica **fixo em
0,2995** enquanto o top-10 do mesmo mint anda de 1,26 a 1,52 em 40 minutos: não é concentração mudando, é o denominador
errado ficando mais errado. A porta da mesa já recusa Mayhem (`mayhem_enabled` false **e** `mayhem_mode` nulo, KB-0109 §0),
então **nenhuma moeda proponível é afetada**.

## 3. Retrato x mesa, mesmo mint e mesmo minuto — a diferença **não** é de denominador

| medida | valor |
|---|---|
| pares mint-minuto com retrato **e** barra de 1 min | **15 565** |
| pares com valor na mesa | 15 475 |
| pares em que o retrato passa de 1 | 84 — **os 84 com `meme_features_1m.top10_share` NULL** |
| erro médio (mesa − retrato, em módulo) | **0,004986** |
| idênticos até 1e-6 | **12 832 (82,9 %)** |
| diferença ≥ 1 p.p. | 1 052 (6,8 %) |

E contra as barras cujo leitor foi o **board** (`t10` do `/ws/trenches`), com tolerância de ±2 min: **55 879 pares**,
mediana **0,2555** (board) x **0,2571** (retrato), diferença média **+0,0033**, **41 977 (75,1 %) iguais** dentro de 0,001.

**Denominador: o mesmo nos dois — a oferta criada inteira (`coinCreatedSupply`), com o cofre da curva fora do numerador.**
A prova está na forma da curva por progresso (q02): mediana **0,0112** com progresso 0–10 % (5 holders), **0,2015** em
20–30 %, **0,2609** em 70–80 %. Uma moeda recém-nascida com **1 holder** marca `0,000103` (mint `Cdgczy`, hoje 16:45 BRT):
se o denominador fosse "tokens fora da curva", esse holder seria ~100 %. O top-10 sobe porque **a oferta sai da curva**,
não porque alguém concentra — o teto de 25 % é, na prática, um teto de **progresso disfarçado**.

As duas fontes divergem em **latência e cobertura**, não em fórmula:
`trenches_ws` escreve 832 348 barras (mediana 0,0023 — o board cobre todo minuto de toda moeda, inclusive as de 1 holder) e
**167 772 leituras (20 %) são recusadas por `out_of_range`**; `indexer_rest:/in-memory-coin` escreve 12 583 barras
(mediana 0,2375, 404 recusas). A recusa é o `share_or_reason` de `features.py`: *"Clamping would invent a number; the
honest value is NULL with its own reason"*. **É por isso que o `> 1` nunca chega na mesa** — ele é filtrado na dobra, não
corrigido.

## 4. Que fonte a admissão usou nas ordens de hoje

**A admissão lê `meme_features_1m`, não o retrato.** O código é explícito (`repo.py::token_context` no commit corrente;
outro agente acabou de movê-lo para `repo_context.py` na árvore de trabalho, **sem mudar a fonte do top-10**):

```python
_FEATURES = text(
    "SELECT end_time, curve_volume_1m_sol, creator_sold, top10_share "
    "FROM meme_features_1m WHERE mint = :mint ORDER BY end_time DESC LIMIT 1")
_RISK = text(  # so o bundled_share, e so dentro de RISK_SNAPSHOT_MAX_AGE_S = 600
    "SELECT bundled_share, observed_at FROM meme_risk_snapshots ...")
```

**24 ordens de compra hoje (16/09 BRT), 23 com o check `top10_share` registrado.** Todos os 23 valores batem com a coluna
da mesa. Confronto com o retrato mais recente `<= received_at`:

| BRT | mint | valor no check (mesa) | retrato disponível | estado do check |
|---|---|---|---|---|
| 12:53:21 | `Gn9U13` | 0,244227 | **0,2442** (12:53:03) | passou — **idêntico** |
| 14:13:51 | `3T4Aue` | 0,183236 | 0,1323 (14:11:50) | passou (passaria nos dois) |
| 14:14:14 | `3T4Aue` | 0,183208 | 0,1323 (14:11:50) | passou (passaria nos dois) |
| 14:05 (×2) | `7uwn4T` | 0,499862 | **sem retrato** | falhou |
| 14:08:26 | `FLHSaT` | 0,253336 | **sem retrato** | falhou |
| 15:33:15 | `Cfsb4v` | 0,257641 | **sem retrato** | falhou |
| 16:41 / 16:50 | `Cdgczy` / `66LUgD` | — | sem retrato | `unavailable` |
| outras 14 | — | 0,167–0,245 | **sem retrato** | passaram |

**Quantas decisões mudariam com a outra fonte: zero — e 20 das 23 virariam recusa por falta de dado.** Nas 3 únicas linhas
com retrato no instante da decisão, os dois números caem do mesmo lado do teto (0,2442 x 0,2442; 0,1323 x 0,1832). Nas
outras 20 o retrato **ainda não existia** (a latência mediana de +103 s do R5/KB-0109 §3), então trocar a fonte transformaria
`passed` em `top10_share_unknown` → recusa. A fonte da mesa não é só a certa por definição: hoje é a **única** que chega a
tempo. Vale registrar que 6 das 11 barras lidas vieram de `trenches_ws` e 5 de `/in-memory-coin` — **as duas fontes já se
misturam dentro da mesma coluna**, e é a §3 que autoriza isso.

## 5. Recomendação (3 linhas)

1. **Manter `meme_features_1m.top10_share` como entrada da admissão** — é a mesma definição da mesa e do KB-0109, então o
   teto de 25/30 % significa a mesma coisa nos dois lados; trocar pelo retrato não mudaria nenhuma decisão de hoje e
   apagaria 20 das 23 por indisponibilidade.
2. **O `> 1` não é bug de parser nem definição diferente: é a oferta injetada pelo Mayhem contra o `coinCreatedSupply`
   congelado** (115/115 dos casos; zero em 20 319 leituras não-Mayhem) — a porta já recusa Mayhem, então **não há o que
   corrigir no `_opt_fraction`**; o que falta é o retrato **declarar** isso, e não o `share_or_reason` descobrir depois.
3. **Duas dívidas que esta nota deixa apontadas:** `holder_denominator_valid=None if token.top10_share is None else True`
   (`admission.py:152`) é **código morto** — a dobra já anulou todo valor inválido, logo `holder_denominator_invalid` é
   inalcançável; e `_FEATURES` **não tem limite de idade** (o `bundled_share` tem 600 s, o top-10 não tem nenhum), então
   uma barra velha pode decidir um teto de risco.

## 6. O que fica em aberto

- **A regra de agregação do site continua não documentada.** Esta nota infere o denominador pela forma (progresso x
  mediana, moeda de 1 holder em 0,0001, `dev_share` fixo com o top-10 andando); ninguém leu a conta do indexador.
- **`out_of_range` em 20 % das leituras de board** (167 772) não foi aberto por causa — Mayhem explica o retrato, mas o
  board tem volume 66x maior e pode ter outra causa junto. **Não medido.**
- **O efeito em decisão vem de 24 ordens de um dia**, com 3 confrontos possíveis. O diagnóstico do §2 é forte; o §4 é
  descritivo, não uma estimativa de impacto.
- A §3 mostra 1 052 pares (6,8 %) com diferença ≥ 1 p.p. entre board e retrato no mesmo minuto — **ruído de instante**,
  pela hipótese, mas perto do teto de 25 % um ponto percentual decide. Medir quantas recusas de fronteira mudam de lado
  conforme o leitor que chegou primeiro é a próxima pergunta.

## Ligações
[[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar|KB-0109]] (o teto, e o achado que abriu esta nota) ·
[[11-KNOWLEDGE/KB-0095-pump-fun-rotulos-observados-do-site-da-rest-e-os-limites-on-chain|KB-0095]] ·
[[03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa|R5 — admissão real]] ·
`docs/RISK_ENGINE_MEME.md` §3.1/§4 check 12 · `docs/DATABASE.md` §35 ·
`infra/scripts/sql/research/2026-09-16-r22-q0{1..5}-*.sql`
