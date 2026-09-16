---
tipo: estudo
tags: [meme, pumpfun, estudo, r10, m4]
owner: astra-quant
status: vivo
data: 2026-09-16
tema: meme
conjunto: operator/5
tarefa: R10
updated: 2026-09-16
fontes:
  - infra/scripts/sql/research/2026-09-16-r10-q01-propostas-do-dia.sql
  - infra/scripts/sql/research/2026-09-16-r10-q02-simulacao-por-proposta.sql
  - infra/scripts/sql/research/2026-09-16-r10-q03-totais-antes-depois-do-teto.sql
  - infra/scripts/sql/research/2026-09-16-r10-q04-ordens-recusadas-e-por-moeda.sql
---

# O que a mesa propôs hoje (16/09) rendeu?

Janela: 16/09 00:00 BRT até 15:33 BRT (última proposta; corte às 15:36 BRT).
Conjunto: `operator/5` (`01994d00-6c1a-7000-8000-000000000011`, `kind = operator`, ativo).

## O que aconteceu, em uma frase

A mesa propôs **35 vezes** hoje e **não abriu nenhuma posição**: 19 propostas
(00:16–10:49) nasceram em modo `paper` e **expiraram** sem decisão; 16 (11:46–15:33)
já em modo `live` foram **recusadas pelo `executor:auto_stage1`**. E — ao contrário do
que o plano supunha — **o laboratório não preencheu nenhuma delas em sombra**:
`meme_paper_bets` não tem uma única linha com `rule_set_id = operator/5` hoje
(as apostas de papel do dia são de `flow_v2`, `moonshot_v0`, `hype_probe_v0`, `organic_v0`,
com `proposal_id` próprio). **Logo, todo o R desta nota é simulado**, não medido.

### Como o R simulado foi calculado

Entrada no `quote` da proposta (preço/mcap da própria foto), série de 15 s enquanto
existe (`age_s ≤ 300`) e de 1 min depois, até `max_hold_s = 1800 s`. Saída, na ordem:
piso −50 %, alvo 3×, trailing 35 % armado a 1,5×, dump do criador (`creator_sold` /
`creator_net_seller`), tempo. Taxa 1,75 % por perna: `k = 0,9825/1,0175`,
`R = (mult·k − 1)/(1 − 0,5·k)` — 3,0× = **+3,67 R**, 0,5× = **−1,00 R**.

> **Caveat que puxa o R para baixo.** A simulação **não** aplica a saída por quebra de
> linha (`exit_on_line_break: true`, 2 fotos), que o conjunto tem. As apostas medidas de
> outros conjuntos nas **mesmas moedas e no mesmo segundo** saíram bem antes por
> `line_broken` (ex.: LAUNCH `flow_v2/5` **−0,08 R**, IndieReach **+0,89 R**, Kite **+0,38 R**,
> onde a simulação marca +3,67 / +3,67 / +3,67). Trate os números abaixo como **teto**.

## Proposta a proposta

| Hora BRT | Símbolo | Progresso | Status | Ordem real (motivo) | Paper | R simulado (saída) |
|---|---|---:|---|---|---|---:|
| 00:16:24 | LAUNCH | 36,7 % | expirada | — | — | **+3,67** (alvo 3×) |
| 00:33:24 | Stability | 71,3 % | expirada | — | — | −1,00 (piso −50 %) |
| 00:33:24 | Stability | 71,1 % | expirada | — | — | −1,00 (piso −50 %) |
| 02:27:25 | ALICE | 90,8 % | expirada | — | — | −1,00 (piso −50 %) |
| 02:27:25 | ALICE | 89,4 % | expirada | — | — | −1,00 (piso −50 %) |
| 02:50:06 | KANYE | 26,5 % | expirada | — | — | −0,70 (dump do criador) |
| 02:54:00 | IndieReach | 53,6 % | expirada | — | — | **+3,67** (alvo 3×) |
| 03:48:13 | NAMEROT | 66,4 % | expirada | — | — | −0,17 (dump do criador) |
| 05:07:33 | Kite | 70,7 % | expirada | — | — | **+3,67** (alvo 3×) |
| 05:07:33 | Kite | 79,1 % | expirada | — | — | +2,80 (tempo 30 min) |
| 06:10:24 | zkPass | 66,0 % | expirada | — | — | −1,00 (piso −50 %) |
| 06:10:24 | zkPass | 76,5 % | expirada | — | — | −1,00 (piso −50 %) |
| 06:18:51 | Bitmaker | 71,3 % | expirada | — | — | +2,56 (fim da série) |
| 06:53:06 | TaskOn | 67,6 % | expirada | — | — | −1,00 (piso −50 %) |
| 07:00:04 | Polkadot | 68,6 % | expirada | — | — | −1,00 (piso −50 %) |
| 07:42:44 | SwissC | 82,4 % | expirada | — | — | −1,00 (piso −50 %) |
| 07:58:51 | Kling | 64,1 % | expirada | — | — | +0,68 (trailing 35 %) |
| 08:49:47 | KORI | 65,4 % | expirada | — | — | +0,19 (fim da série) |
| 10:49:24 | chillin | 94,8 % | expirada | — | — | −1,00 (piso −50 %) |
| 11:46:33 | INCEPT | 26,9 % | rejeitada | recusada (`progress_below_window`) | — | +1,81 (fim da série) |
| 11:46:51 | INCEPT | 41,1 % | rejeitada | recusada (`progress_below_window`) | — | +0,90 (fim da série) |
| 11:47:09 | INCEPT | 47,2 % | rejeitada | recusada (`progress_below_window`) | — | +0,54 (fim da série) |
| 11:47:51 | INCEPT | 60,6 % | rejeitada | recusada (`progress_below_window`) | — | −0,16 (fim da série) |
| 12:07:22 | CGRAM | 58,2 % | rejeitada | recusada (`progress_below_window`) | — | −0,32 (fim da série) |
| 12:52:36 | GREMLIN | 68,3 % | rejeitada | recusada (`progress_above_window`) | — | **+3,67** (alvo 3×) |
| 12:52:36 | GREMLIN | 72,2 % | rejeitada | recusada (`progress_above_window`) | — | **+3,67** (alvo 3×) |
| 12:52:54 | GREMLIN | 72,7 % | rejeitada | recusada (`progress_above_window`) | — | **+3,67** (alvo 3×) |
| 12:53:11 | GREMLIN | 80,7 % | rejeitada | recusada (`progress_above_window`) | — | +2,53 (fim da série) |
| 14:04:41 | SORT | 64,5 % | rejeitada | recusada (`progress_above_window`) | — | −1,00 (piso −50 %) |
| 14:05:00 | SORT | 66,2 % | rejeitada | recusada (`progress_above_window`) | — | −1,00 (piso −50 %) |
| 14:05:22 | SORT | 63,9 % | rejeitada | recusada (`progress_above_window`) | — | −1,00 (piso −50 %) |
| 14:08:23 | steve | 65,1 % | rejeitada | recusada (`progress_above_window`) | — | +0,54 (fim da série) |
| 14:13:46 | RIZZLERS | 84,6 % | rejeitada | recusada (`progress_above_window`) | — | −1,00 (piso −50 %) |
| 14:14:05 | RIZZLERS | 82,1 % | rejeitada | recusada (`progress_above_window`) | — | −1,00 (piso −50 %) |
| 15:33:07 | $casinu | 46,1 % | rejeitada | recusada (`creator_flow_unknown`) | — | −0,70 (dump do criador) |

`fim da série` = a moeda parou de ser observada (migração/curva completa/coletor) antes
dos 30 min; a saída é a última foto disponível.

## Totais

| Recorte | n | R médio | R total | Acertos |
|---|---:|---:|---:|---:|
| **Todas** | 35 | +0,50 | **+17,49** | 15 (43 %) |
| Antes das 15:08 | 34 | +0,54 | +18,20 | 15 (44 %) |
| Depois das 15:08 | 1 | −0,70 | −0,70 | 0 (0 %) |
| Progresso ≤ 50 % | 6 | **+0,92** | +5,51 | 4 (67 %) |
| Progresso > 50 % | 29 | +0,41 | +11,98 | 11 (38 %) |

Por moeda (a primeira proposta de cada mint, que é o que a mesa de fato abriria —
`max_exposure_per_mint_sol = size_sol = 0,05`), as repetições de GREMLIN/SORT/INCEPT
somem e o total cai muito: ver a quebra por motivo abaixo.

## O teto de 50 % tirou dinheiro hoje?

**Tirou, e o número é este:** as 10 propostas recusadas por `progress_above_window`
(limite `0.5` na admissão, valores observados 0,60–0,96) somam **+9,07 R** simulados
(5 acertos em 10). Deduplicando por moeda — 4 moedas: GREMLIN, SORT, steve, RIZZLERS —
sobra **+2,20 R** (2 acertos em 4), e **todo o saldo é uma moeda só**: GREMLIN +3,67 R
contra SORT −1,00 e RIZZLERS −1,00. Com a saída por quebra de linha (não simulada), esse
+2,20 R encolhe mais.

Na faixa que o teto protege (≤ 50 %), o R médio é **maior** (+0,92 vs +0,41) e o acerto é
quase o dobro (67 % vs 38 %) — ou seja, **o teto está certo na direção; hoje ele pagou
caro por uma cauda (GREMLIN) e, por sorte, evitou quatro −1 R**.

### E as 16 ordens reais recusadas?

| Motivo da recusa | Por proposta (n / R total / acertos) | Por moeda (n / R total / acertos) |
|---|---|---|
| `progress_above_window` (teto 50 %) | 10 / **+9,07** / 5 | 4 / **+2,20** / 2 |
| `progress_below_window` | 5 / **+2,78** / 3 | 2 / **+1,49** / 1 |
| `creator_flow_unknown` | 1 / −0,70 / 0 | 1 / −0,70 / 0 |
| **Total das 16** | 16 / **+11,15** / 8 | 7 / **+2,99** / 3 |

**Achado colateral e grave:** as 5 recusas por `progress_below_window` (INCEPT 11:46–11:47,
CGRAM 12:07) trazem `value` como **−541 546**, −554 166, −657 115, −425 330, −505 184 contra
`limit 0.02`, enquanto o `quote` da mesma proposta dizia 26,9 %–58,2 %. Não é o gatilho
funcionando: é o progresso na admissão vindo **absurdamente negativo** (denominador/reservas
errados). Essas 5 ordens (**+2,78 R** simulados) foram perdidas por bug, não por política.

## Conclusão (4 linhas)

1. A mesa propôs 35 vezes e não abriu nada: 19 propostas expiraram em modo paper e 16 foram recusadas na admissão — não há **nenhum** R medido de `operator/5` hoje, só simulado.
2. O dia simulado dá +17,49 R em 35 propostas (43 % de acerto), mas é teto: as apostas medidas nas mesmas moedas saíram por quebra de linha com R muito menor.
3. O teto de 50 % custou **+9,07 R** por proposta / **+2,20 R** por moeda, quase todo em GREMLIN; ao mesmo tempo a faixa ≤ 50 % rende mais por proposta (+0,92 vs +0,41) e acerta mais (67 % vs 38 %) — manter o teto.
4. Prioridade real não é o teto: é o progresso negativo na admissão (5 de 16 recusas, +2,78 R) e o fato de o laboratório não estar sombreando as propostas da mesa — sem sombra, a mesa não tem medida própria.
