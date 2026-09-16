---
tags: [trading, meme, pumpfun, estudo, admissao, risco, execucao, estagio-1, dinheiro-real]
titulo: O que a admissao nova (T4.28g, T4.28h, top-10 30 %) admitiria das 26 ordens de hoje
status: vivo
owner: astra-quant
data: 2026-09-16
updated: 2026-09-16
tarefa: R26
---

# Estudo R26 — o que a admissão nova admitiria das ordens de hoje (16/09/2026)

> Fonte: `meme_live_orders` (as **26** ordens do dia, 11:46–16:58 BRT, 13 mints), `meme_proposals`,
> `meme_risk_snapshots`, `meme_features_1m`, `meme_tokens` na VPS. Consultas em
> `infra/scripts/sql/research/2026-09-16-r26-q0{1..6}-*.sql`. Horas em BRT.
> Mudanças reavaliadas: **(A)** T4.28g — o robô espera até 60 s pelo retrato de risco antes de abrir a
> proposta (commit `747efc6f`, ainda **não** deployado); **(B)** T4.28h — `creator_flow_unknown` passa
> se o `dev_share` medido (≤ 600 s) for ≤ 10 %; **(C)** KB-0109 — teto de `top10_share` a 30 % em vez
> de 25 %. Nenhuma mexe no teto de progresso (50 %), no de bundle (20 %) nem na participação.
> Antecessor: [[03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa|R5]] (16 ordens; hoje são 26).

**A resposta curta, antes da tabela: sob os dados que existem no banco, as três mudanças juntas
admitiriam ZERO das 26 ordens de hoje.** Não porque as checagens sejam duras, mas porque o insumo que
a (A) manda esperar **nunca chegou** nos mints do fim da tarde — e nos mints em que ele chegou, ou
chegou tarde demais para a janela de 60 s, ou veio acima do teto de 20 %.

---

## 1. As 26 ordens reais (Q01, Q02)

| # | hora | símbolo | mint | progresso na proposta | motivo real gravado |
|---|---|---|---|---|---|
| 1 | 11:46:36 | INCEPT | FHcHh1 | 26,88 % | progress_below_window (bug de unidade, T4.28e) |
| 2 | 11:46:55 | INCEPT | FHcHh1 | 41,09 % | progress_below_window |
| 3 | 11:47:18 | INCEPT | FHcHh1 | 47,15 % | progress_below_window |
| 4 | 11:47:55 | INCEPT | FHcHh1 | 60,64 % | progress_below_window |
| 5 | 12:07:27 | CGRAM | 3tAFaZ | 58,19 % | progress_below_window |
| 6 | 12:52:40 | GREMLIN | Gn9U13 | 68,34 % | progress_above_window (0,829) |
| 7 | 12:52:41 | GREMLIN | Gn9U13 | 72,17 % | progress_above_window (0,838) |
| 8 | 12:52:57 | GREMLIN | Gn9U13 | 72,75 % | progress_above_window (0,813) |
| 9 | 12:53:21 | GREMLIN | Gn9U13 | 80,73 % | progress_above_window (0,964) + bundle 39,76 % |
| 10 | 14:04:45 | SORT | 7uwn4T | 64,50 % | progress_above_window (0,652) + volume indisponível |
| 11 | 14:05:07 | SORT | 7uwn4T | 66,19 % | progress_above_window (0,640) + top-10 49,99 % |
| 12 | 14:05:27 | SORT | 7uwn4T | 63,90 % | progress_above_window (0,649) + top-10 49,99 % |
| 13 | 14:08:26 | steve | FLHSaT | 65,06 % | progress_above_window (0,605) + top-10 25,33 % |
| 14 | 14:13:51 | RIZZLERS | 3T4Aue | 84,59 % | progress_above_window (0,813) + participação 0 |
| 15 | 14:14:14 | RIZZLERS | 3T4Aue | 82,07 % | progress_above_window (0,783) — **única recusa** |
| 16 | 15:33:15 | $casinu | Cfsb4v | 46,13 % | creator_flow_unknown + top-10 25,76 % + participação 0 |
| 17 | 16:36:30 | guy | 4Yz9VQ | 47,56 % | progress_above_window (0,543) |
| 18 | 16:36:31 | parasitebe | BVf9r1 | 45,78 % | **creator_flow_unknown + bundle indisponível** |
| 19 | 16:36:32 | parasitebe | BVf9r1 | 47,23 % | **creator_flow_unknown + bundle indisponível** |
| 20 | 16:36:48 | parasitebe | BVf9r1 | 47,23 % | **creator_flow_unknown + bundle indisponível** |
| 21 | 16:37:12 | parasitebe | BVf9r1 | 47,23 % | idem + participação 0 (volume do minuto zero) |
| 22 | 16:41:21 | DRAGON | Cdgczy | 35,22 % | progress_below_window (0,0001) + top-10 desconhecido |
| 23 | 16:50:31 | BRINAA | 66LUgD | 48,61 % | progress_above_window (0,551) + top-10 desconhecido |
| 24 | 16:52:58 | BRINAA | Bazxr9 | 21,65 % | **bundled_share_above_cap (47,41 %)** + top-10 25,13 % + participação 0 |
| 25 | 16:58:14 | gary | 9ZGUWS | 47,43 % | creator_flow_unknown + top-10 desconhecido |
| 26 | 16:58:33 | gary | 9ZGUWS | 46,39 % | progress_above_window (0,509) + top-10 desconhecido |

O valor entre parênteses é o do próprio `admission->'checks'` (fração), que é **maior** que o
progresso da cotação porque o executor relê a curva por RPC 3–10 s depois da mesa, e a curva sobe.

---

## 2. A matriz dos três cenários (Q03, Q06)

Para cada ordem: existiu retrato de risco (`meme_risk_snapshots.bundled_share` não-nulo) até 60 s /
120 s depois da proposta — ou já fresco (≤ 600 s) na decisão — e com que valor.

| hora | mint | retrato (atraso) | bundled | ≤ 20 % e ≤ 60 s? | dev_share (B) | top-10 ≤ 30 % (C) | progresso | particip. |
|---|---|---|---|---|---|---|---|---|
| 11:46:36 | FHcHh1 | +107 s | 0,2131 | não | 0,0096 ok | 0,2115 ok | 26,9 %* | ok |
| 11:46:55 | FHcHh1 | +89 s | 0,2131 | não | ok | ok | 41,1 %* | ok |
| 11:47:18 | FHcHh1 | +71 s | 0,2131 | não | ok | 0,2434 ok | 47,2 %* | ok |
| 11:47:55 | FHcHh1 | **+28 s** | **0,2131** | **não (bundle)** | ok | ok | 60,6 %* ✗ | ok |
| 12:07:27 | 3tAFaZ | +135 s | 0,2071 | não | ok | 0,1995 ok | 58,2 %* ✗ | ok |
| 12:52:40 | Gn9U13 | +27 s | **0,3976** | não (bundle) | ok | 0,2385 ok | 0,829 ✗ | ok |
| 12:52:41 | Gn9U13 | +27 s | 0,3976 | não | ok | ok | 0,838 ✗ | ok |
| 12:52:57 | Gn9U13 | +9 s | 0,3976 | não | ok | ok | 0,813 ✗ | ok |
| 12:53:21 | Gn9U13 | na decisão | 0,3976 | não | ok | 0,2442 ok | 0,964 ✗ | ok |
| 14:04:45 | 7uwn4T | +125 s | 0,0000 | não (janela) | ok | ok | 0,652 ✗ | **0** ✗ |
| 14:05:07 | 7uwn4T | +107 s | 0,0000 | não (janela; sim em 120 s) | ok | **0,4999 ✗** | 0,640 ✗ | ok |
| 14:05:27 | 7uwn4T | +85 s | 0,0000 | não (janela; sim em 120 s) | ok | **0,4999 ✗** | 0,649 ✗ | ok |
| 14:08:26 | FLHSaT | +147 s | **0,2013** | não (janela **e** bundle) | ok | 0,2533 **ok em C** | 0,605 ✗ | ok |
| 14:13:51 | 3T4Aue | na decisão | 0,0202 | **sim** | ok | 0,1832 ok | 0,813 ✗ | **0** ✗ |
| 14:14:14 | 3T4Aue | na decisão | 0,0202 | **sim** | ok | ok | 0,783 ✗ | ok |
| 15:33:15 | Cfsb4v | +90 s | 0,0134 | não (janela; sim em 120 s) | ok | 0,2576 **ok em C** | 0,423 ok | **0** ✗ |
| 16:36:30 | 4Yz9VQ | **nunca** | — | não | ok | 0,2227 ok | 0,543 ✗ | ok |
| 16:36:31 | BVf9r1 | **nunca** | — | **não (é o único bloqueio)** | 0,0000 ok | 0,1678 ok | 0,472 ok | ok |
| 16:36:32 | BVf9r1 | **nunca** | — | **não (é o único bloqueio)** | ok | ok | 0,472 ok | ok |
| 16:36:48 | BVf9r1 | **nunca** | — | **não (é o único bloqueio)** | ok | ok | 0,476 ok | ok |
| 16:37:12 | BVf9r1 | nunca | — | não | ok | ok | 0,482 ok | **0** ✗ |
| 16:41:21 | Cdgczy | nunca | — | não | nulo ✗ | **desconhecido ✗** | 0,0001 ✗ | ok |
| 16:50:31 | 66LUgD | nunca | — | não | nulo ✗ | **desconhecido ✗** | 0,551 ✗ | ok |
| 16:52:58 | Bazxr9 | na decisão | **0,4741** | não (bundle real) | ok | 0,2513 ok em C | 0,163 ok | **0** ✗ |
| 16:58:14 | 9ZGUWS | +70 s | 0,0000 | não (janela; sim em 120 s) | nulo ✗ | **desconhecido ✗** | 0,449 ok | ok |
| 16:58:33 | 9ZGUWS | **+46 s** | **0,0000** | **sim** | nulo ✗ | **desconhecido ✗** | 0,509 ✗ | ok |

\* nas cinco primeiras ordens o `admission` gravou o valor do bug de unidade (−4,2e5 a −6,6e5); uso o
progresso da cotação como o que a admissão pós-T4.28e teria calculado (assunção declarada na §5).

### Contagem

| cenário | ordens admitidas (de 26) | compras distintas |
|---|---|---|
| **(A)** T4.28g sozinho | **0** | 0 |
| **(A+B)** + `creator_flow_unknown` com dev ≤ 10 % | **0** | 0 |
| **(A+B+C)** + top-10 a 30 % | **0** | 0 |
| (A+B+C) com espera de **120 s** em vez de 60 s | **0** | 0 |

**Por que zero, ordem a ordem:** 13 ordens morrem no **progresso** (o teto de 50 % não é tocado por
nenhuma das três mudanças); 6 morrem no **bundle real ou tarde** (0,3976 do GREMLIN, 0,4741 do
BRINAA, 0,2131 do INCEPT, 0,2013 do steve — este último **13 pontos-base** acima do teto); 5 morrem na
**participação zero** (`curve_volume_1m_sol = 0`); 3 (`9ZGUWS`, `Cdgczy`, `66LUgD`) morrem em
`top10_share_unknown`, que o teto de 30 % **não** resolve porque o problema é ausência, não excesso.

**As três ordens que ficam a um passo:** 16:36:31, :32 e :48, do `parasitebe` (BVf9r1) — a mesma
compra reproposta três vezes. Todas as outras 24 checagens passam; o único bloqueio é que **nenhum
retrato de risco foi tirado desse mint, nem antes nem depois** (Q03: atraso nulo em 4 dos 13 mints —
4Yz9VQ, BVf9r1, Cdgczy, 66LUgD). É exatamente o buraco que o **ramo worker** do T4.28g fecha (o
`RiskReader` passa a cobrir mint com proposta `proposed`/`approved` e ordem live pendente) — mas esse
dado **não existe no banco de hoje**, então este estudo não pode afirmar que ele viria ≤ 20 %.

**Taxa-base para o palpite (Q05):** dos **580 mints** lidos pelo `RiskReader` hoje, a primeira leitura
de `bundled_share` ficou **≤ 20 % em 49,3 %** deles (mediana **0,2016**, média 0,2168). O teto de 20 %
cai **em cima da mediana do dia**: é uma moeda ao ar. Logo, a estimativa honesta é **0 a 1 compra** —
1 compra com probabilidade ~0,5, condicionada a o retrato do `parasitebe` sair abaixo de 20 %.

---

## 3. E se essa compra tivesse saído? (Q04)

`parasitebe` (BVf9r1), decisão 16:36:31, base `quote->>'mcap_sol'` = **63,87 SOL**, tamanho
`admission->'sizing'` = **0,05 SOL** (limitante `requested`), unidade de risco = 0,025 SOL (piso −50 %).

| 30 min seguintes | valor |
|---|---|
| mcap pico relativo | **1,055×** (nunca armou o trailing: precisa de 1,5×) |
| mcap mínimo relativo | **0,438×** |
| saída da regra da mesa | **stop no piso**, 3ª barra (~2,5 min depois) |
| múltiplo líquido (taxa 1,75 %/perna) | 0,423 |
| **R simulado** | **−1,155 R** ≈ **−0,029 SOL** |

**A única compra que a admissão nova poderia ter feito hoje teria perdido.**

### As 13 moedas do dia, se a porta fosse escancarada

| mint | símbolo | decisão | pico rel. | mín. rel. | saída | R |
|---|---|---|---|---|---|---|
| FHcHh1 | INCEPT | 11:46:36 | 2,017 | 1,513 | série acabou (2,4 min) | +1,875 |
| 3tAFaZ | CGRAM | 12:07:27 | 0,973 | 0,815 | tempo 30 min | −0,331 |
| Gn9U13 | GREMLIN | 12:52:40 | **3,598** | 1,146 | **alvo 3×** | **+3,792** |
| 7uwn4T | SORT | 14:04:45 | 1,050 | 0,288 | stop | −1,405 |
| FLHSaT | steve | 14:08:26 | 1,606 | 0,800 | série acabou (10,6 min) | +0,553 |
| 3T4Aue | RIZZLERS | 14:13:51 | 1,010 | 0,141 | stop | −1,728 |
| Cfsb4v | $casinu | 15:33:15 | 0,668 | 0,449 | stop | −1,134 |
| 4Yz9VQ | guy | 16:36:30 | 1,179 | 1,179 | série acabou (0,5 min) | +0,275 |
| **BVf9r1** | **parasitebe** | 16:36:31 | 1,055 | 0,438 | **stop** | **−1,155** |
| Cdgczy | DRAGON | 16:41:21 | 0,547 | 0,547 | série acabou (3,6 min) | −0,944 |
| 66LUgD | BRINAA | 16:50:31 | 1,484 | 1,242 | série acabou (3,5 min) | +0,866 |
| Bazxr9 | BRINAA | 16:52:58 | 1,823 | 1,000 | série acabou (1,0 min) | +1,520 |
| 9ZGUWS | gary | 16:58:14 | 1,033 | 0,425 | stop | −1,180 |

Soma **+1,00 R** em 13, média **+0,077 R**. **Não confie nessa soma:** em 9 das 13 a série de 1 min
**acaba 0,5 a 3,6 min depois da decisão** (Q05) — o fold para quando a moeda sai do board. Os
"+1,875" do INCEPT e os "+1,520" do BRINAA são a **última barra observada**, não um desfecho; o viés é
otimista. Contando só os 6 desfechos que **de fato dispararam** alvo ou stop: **−2,81 R em 6 apostas**
(+3,792 do GREMLIN, que graduou 47 s depois da decisão, contra cinco stops).

---

## 4. Conclusão em 4 linhas

1. **O robô vai comprar depois do deploy? Quase nada — e hoje não teria comprado nenhuma vez.** Nas 26
   ordens reais, (A), (A+B) e (A+B+C) admitem **0**; o gargalo passou a ser o teto de progresso de
   50 % (13 ordens), o bundle real ou atrasado (6) e o volume do minuto zero (5), não mais os
   `unavailable`.
2. **Quanto:** o cenário realista é **0 a 1 compra por dia neste ritmo** — a única ordem a um passo
   (`parasitebe`, 3 reproposições) depende de o retrato que o ramo-worker do T4.28g passará a tirar vir
   ≤ 20 %, e o bundled ≤ 20 % acontece em **49,3 %** dos mints (mediana do dia **0,2016**, colada no teto).
3. **Com que resultado:** essa compra teria **perdido −1,155 R (−0,029 SOL em 0,05 SOL)** — pico de
   apenas 1,055× e mínimo de 0,438× em 2,5 min. Nas 13 moedas do dia, os desfechos **resolvidos** somam
   **−2,81 R em 6**; o único ganho real (GREMLIN, +3,79 R) foi recusado por bundle de **39,8 %** — recusa correta.
4. **O que realmente destrava:** a (C) sozinha nunca foi binding hoje (só ajudaria 3 ordens já mortas
   por outra parede) e a (B) só desbloqueia quem o `dev_share` alcança (3 mints ficaram com dev nulo).
   O próximo teto a medir é o **progresso de 50 %** — é ele que mata 13 das 26 —, e depois o
   `curve_volume_1m_sol = 0` na hora da decisão (5 ordens). Sem isso, o deploy compra ~1 vez ao dia.

---

## 5. Assunções numéricas declaradas

- **Progresso das 5 primeiras ordens:** o `admission` gravou o valor do bug de unidade do T4.28e
  (−4,2e5 a −6,6e5). Uso o `quote->>'curve_progress_pct'` da proposta como proxy do que a admissão
  corrigida calcularia. Onde isso mudaria o resultado (ordens 1–3, que passariam na janela 2–50 %), o
  bundled de 0,2131 recusa mesmo assim — a contagem **zero** é robusta a essa assunção.
- **(A) medida como "existe retrato com `bundled_share` não-nulo até 60 s (ou 120 s) depois de
  `proposed_at`, ou já fresco ≤ 600 s na decisão"**. Não simulo o efeito de a espera adiar a compra:
  esperar 60 s numa curva que subiu de 60 % para 96 % em 41 s (R5 §3) **muda o preço e o progresso**, e
  a série do banco não permite reconstruir a admissão nesse instante alternativo.
- **(B) medida como `meme_features_1m.dev_share` não-nulo e ≤ 0,10 na janela de 600 s antes da
  decisão** (a mesma fonte que o `devHoldingsPercent` do retrato). A flag do dono é tratada como ligada.
- **(C)**: `top10_share_above_cap` reavaliado com 0,30; `top10_share_unknown` **continua recusando**
  (é `unavailable`, não excesso).
- **R simulado:** regra da mesa literal (alvo 3×, trailing 35 % armado depois de 1,5×, piso −50 %,
  tempo 30 min, taxa 1,75 %/perna, fill pessimista no mcap **observado** da barra), base =
  `quote->>'mcap_sol'` da proposta que gerou a ordem, série = `meme_features_1m.mcap_sol`,
  R = (múltiplo líquido − 1)/0,5. Uma ordem por mint (a primeira) — as reproposições do mesmo mint em
  segundos não são eventos independentes.
- **Truncamento:** saídas rotuladas "série acabou" são a última barra existente e **superestimam** o R.

## Ligações

[[03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa]] ·
[[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar]] ·
[[09-OPERATIONS/Diario/2026-09-16]] · `.claude/state/notes-T4.28g.md` · `.claude/state/notes-T4.28e.md` ·
`docs/RISK_ENGINE_MEME.md` §3.1/§4 · `services/meme-executor/hunter_meme_executor/{admission,repo}.py`
