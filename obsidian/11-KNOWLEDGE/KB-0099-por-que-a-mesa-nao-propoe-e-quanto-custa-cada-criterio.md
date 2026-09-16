---
tags: [knowledge, nota, meme, pumpfun, porta, funil, operator, calibracao, m4]
tema: memecoin / pump.fun / por que a mesa (operator/5) quase não propõe — custo marginal de cada critério e uma porta calibrada para o estágio 1
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_tokens, meme_proposals, meme_rule_sets), 15–16/09/2026 BRT
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r4-q01-funil-por-criterio.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r4-q01..q06; 47 017 moedas distintas na janela da porta, 2 dias)
hipotese_testavel: sim
astra: não consultada nesta nota (medição; a calibração vai à mesa antes de virar conjunto)
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-16
status: vivo
---

# KB-0099 — Por que a mesa não propõe, e quanto custa cada critério

**O fato que abriu a nota (16/09):** a mesa (`operator/5`, porta E1 braço 2) ficou de 15:33 a 16:40 BRT sem propor nada, e o
heartbeat contou 1 137 recusas na janela (holders 127, compradores 112, fluxo 108, sem compras 103, volume zero 99,
progresso 98, progresso não subindo 90, símbolo clonado 69…). A pergunta do Everton é a certa: **qual critério mata o quê,
e o que a gente perde ao afrouxar cada um?**

Método: reconstruí a porta inteira em SQL sobre a série de 15 s (`meme_features_15s`, idade 30–300 s), com os parâmetros
lidos de `meme_rule_sets` (`operator/5`, id `…0011`): idade 30–300 s, progresso 5–50 %, participação ≤ 1 % de 0,05 SOL
(⇒ `curve_volume_60s_sol ≥ 5`), dev ≤ 10 %, snipers ≤ 10, fluxo > 0, ≥ 10 compradores/min, vendas/compras ≤ 0,6,
holders ≥ 20 não caindo, progresso (ou mcap) subindo, pedigree. "Sobreviver a um passo" = existir **uma foto de 15 s** que
satisfaz todos os critérios até ali. **A reconstrução é um piso**: no dia 16/09 a mesa propôs 22 moedas distintas e a minha
conta dá 6 — o worker lê algumas features por caminhos extras (bit de Mayhem da foto da cadeia, leituras avulsas de
holders/snipers) que a série gravada não tem. As proporções valem; os absolutos são conservadores.

## 1. O funil, na ordem da porta, e a taxa marginal de morte

| # | Critério | 15/09 moedas | morte marginal | 16/09 moedas | morte marginal |
|---|---|---|---|---|---|
| 00 | universo (foto 15 s, idade 30–300 s) | 30 899 | — | 16 118 | — |
| 01 | curva viva (não completa/migrada) | 30 886 | 0,0 % | 16 109 | 0,1 % |
| 02 | não Mayhem (flag lida) | 21 223 | **31,3 %** | 9 896 | **38,6 %** |
| 03 | progresso 5–50 % | 6 754 | **68,2 %** | 3 329 | **66,4 %** |
| 04 | criador não vendedor líquido | 6 508 | 3,6 % | 3 260 | 2,1 % |
| 05 | participação ≤ 1 % (vol 60 s ≥ 5 SOL) | 3 802 | **41,6 %** | 759 | **76,7 %** |
| 06 | dev ≤ 10 % | 3 799 | 0,1 % | 759 | 0,0 % |
| 07 | snipers ≤ 10 | 1 669 | **56,1 %** | 325 | **57,2 %** |
| 08 | fluxo líquido > 0 | 1 552 | 7,0 % | 293 | 9,8 % |
| 09 | compradores únicos ≥ 10 | 904 | **41,8 %** | 159 | **45,7 %** |
| 10 | vendas/compras ≤ 0,6 | 591 | 34,6 % | 99 | 37,7 % |
| 11 | holders ≥ 20 | 209 | **64,6 %** | 34 | **65,7 %** |
| 12 | holders não caindo | 194 | 7,2 % | 31 | 8,8 % |
| 13 | progresso (ou mcap) subindo | **139** | 28,4 % | **24** | 22,6 % |
| 14 | pedigree (`creator_serial`/`symbol_clone`) | **44** | **68,3 %** | **6** | **75,0 %** |

(16/09 é dia parcial: a série vai até 15:59 BRT. Não há buraco de coleta — a cobertura horária da série de 15 s é contínua,
de 794 a 1 810 moedas distintas por hora.)

**O custo de cada critério sem depender da ordem** (quantas moedas passariam se **só aquele** fosse solto, todos os outros
mantidos — `2026-09-16-r4-q02`):

| Critério solto | 15/09 (base 139) | 16/09 (base 24) |
|---|---|---|
| snipers ≤ 10 | 367 (**+228**) | 66 (**+42**) |
| holders ≥ 20 | 335 (**+196**) | 59 (**+35**) |
| progresso 5–50 % | 209 (+70) | 57 (+33) |
| vendas/compras ≤ 0,6 | 199 (+60) | 37 (+13) |
| **progresso/mcap subindo** | 194 (+55) | 31 (+7) |
| participação (vol ≥ 5 SOL) | 153 (+14) | 28 (+4) |
| **holders não caindo** | 151 (+12) | 28 (+4) |
| compradores ≥ 10 | 142 (+3) | 24 (+0) |
| fluxo > 0 · dev · criador · Mayhem · curva | +0 a +2 | +0 |

**A hipótese do brief está meio certa e meio errada.** Depois da barra de holders/compradores, os dois que mais matam são
mesmo os "subindo" — mas não em pé de igualdade: **`require_progress_rising` corta 28,4 % / 22,6 %** dos que chegam lá
(+55 e +7 moedas soltas) e **`require_holders_rising` corta só 7,2 % / 8,8 %** (+12 e +4). No conjunto inteiro, os dois
grandes carrascos não são os "subindo": são **`max_snipers = 10`** e **`min_holders = 20`**, seguidos do pedigree
(que sozinho mata 68–75 % do que sobrou). O `flow_not_positive` e o `no_buys` do heartbeat aparecem grandes porque a porta
avalia **todos** os critérios de cada foto e soma todas as recusas — não são mortes marginais.

## 2. O que as moedas fizeram depois: os "subindo" não separam vencedora de perdedora

Coorte **A** = passou os 13 critérios; coorte **B** = só morreu nos "subindo" (12 e/ou 13, nada mais). Base = `mcap_sol` da
foto de entrada; futuro na série de minuto (`meme_features_1m`) — a de 15 s **para aos 300 s de idade** e não serve de futuro
(a primeira versão desta medida mediu 5, 15 e 30 min com o mesmo número; era esse o motivo).

| Coorte (15/09 + 16/09) | n | ≥ 1,5× em 5 min | ≥ 1,5× em 30 min | ≥ 3× em 30 min | queda ≥ 50 % em 30 min | múltiplo máx. mediano |
|---|---|---|---|---|---|---|
| A — passa tudo | 162 | 31 (19,1 %) | 37 (**22,8 %**) | 14 (**8,6 %**) | 14 (**8,6 %**) | 1,07 |
| B — só morreu nos "subindo" | 77 | 20 (26,0 %) | 22 (**28,6 %**) | 10 (**13,0 %**) | 19 (**24,7 %**) | 1,02 |

**Os dois critérios "subindo" não selecionam vencedoras.** A coorte que eles cortam tem taxa de 3× **maior** (13,0 % contra
8,6 %) e taxa de ruína **três vezes maior** (24,7 % contra 8,6 %). Eles são um filtro de **drawdown**, não de vantagem — e
com uma perna de saída que já tem piso de −50 % e trailing, filtrar drawdown na entrada é pagar caro por um seguro que já
existe. Honestidade estatística: com n = 77 e n = 162, a diferença 13,0 % × 8,6 % é de **uma** sigma; o que a medida
sustenta é "não separam", não "cortar melhora".

## 3. Porta calibrada para o estágio 1, com o R medido (não ajustado a olho)

Simulei a perna de saída de `operator/5` (0,05 SOL, alvo 3×, trailing 35 % depois de 1,5×, tempo 10 min, piso −50 %, taxa
1,75 % por perna, saída de stop preenchida no mcap **observado** da barra, granularidade de 1 min) sobre cada porta
(`2026-09-16-r4-q05`). 1 R = 0,5 do tamanho (o piso é a unidade de risco).

| Porta (todas com pedigree) | candidatos 15/09 → 16/09 | R médio | R total | acerto |
|---|---|---|---|---|
| `operator/5` como está | 44 → 6 | +0,011 → +0,423 | +0,50 → +2,54 | 29,5 % → 33,3 % |
| sem os dois "subindo" | 76 → 13 | +0,009 → +0,262 | +0,68 → +3,41 | 28,0 % → 38,5 % |
| **+ snipers ≤ 25 (proposta)** | **170 → 30** | **+0,082 → +0,271** | **+13,93 → +8,13** | 29,6 % → 40,0 % |
| + holders ≥ 12 | 281 → 45 | **−0,059** → +0,023 | −16,57 → +1,04 | 23,8 % → 33,3 % |
| + progresso 3–80 %, razão 0,8, compradores 8, vol 3 | 444 → 106 | −0,019 → **−0,146** | −8,28 → −15,43 | 28,6 % → 30,2 % |
| a anterior sem pedigree | 998 → 261 | −0,051 → −0,149 | −50,93 → −38,42 | 28,4 % → 27,6 % |

**Proposta:** `operator/5` com **`require_holders_rising: false`, `require_progress_rising: false` e `max_snipers: 25`** —
e **nada mais mexido**: holders ≥ 20, compradores ≥ 10, vendas/compras ≤ 0,6, volume ≥ 5 SOL/min, dev ≤ 10 % e pedigree
**ficam**, porque cada afrouxamento adicional medido virou R negativo. Cadência medida em 13–22 BRT: **71 candidatos em
10 h no dia 15/09 = 7,1/hora** (dentro do alvo de 5–10); no dia 16/09, seco, dá 2/hora — a variância entre dias é maior
que a distância até a meta, então a porta não deve ser recalibrada por causa de um dia ruim.

**A expectativa honesta de R.** +0,08 a +0,27 R por aposta, e **tudo vem da cauda**: das 169 apostas de 15/09, 16 saíram no
alvo 3× (+3,79 R cada = +60,7 R) e as outras 153 somam **−46,8 R** (−0,31 R por aposta). Sem as 16 caudas, a porta é
perdedora. Em SOL: 70 apostas/dia × 0,05 SOL × 0,082 R × 0,5 ≈ **0,14 SOL/dia** no dia bom — duas ordens de grandeza abaixo
da [[11-KNOWLEDGE/KB-0090-a-meta-em-dinheiro|meta de R$ 9 mil/dia]] com esse tamanho de aposta. O que essa porta entrega é
**fluxo de amostra** para o estágio 1, não lucro; o lucro depende de tamanho e de uma cauda mais frequente (a célula lenta
da [[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]], o evento da T4.26).

**Limites declarados desta medição:** (i) sem impacto/slippage além da taxa e sem teto de participação na saída — a
[[11-KNOWLEDGE/KB-0088-o-teto-de-participacao-nos-motores-de-backtest|KB-0088]] diz que isso corta cauda, e a cauda é
**toda** a vantagem aqui; (ii) saída em barras de 1 min, enquanto a mesa real decide a cada 15 s; (iii) sem TTL, dedup por
mint nem cooldown de recusa, que reduzem a contagem real de propostas; (iv) entrada no mcap da foto, sem atraso de decisão
([[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]); (v) dois dias, um deles parcial. Qualquer braço
novo nasce **pré-registrado como `descartar`** e é a medição prospectiva que decide.

## 4. Unidades (a armadilha que quase estragou esta nota)

`meme_features_15s.curve_progress_pct` é **fração 0–1**; `meme_proposals.quote->>'curve_progress_pct'` é **porcentagem**
(conferido na mesma foto: `0.410918` na série ⇄ `41.0918` na proposta). A porta de 5–50 % se escreve
`BETWEEN 0.05 AND 0.50` na série de 15 s e `BETWEEN 5 AND 50` na proposta. Registrado em `docs/DATABASE.md` §33.5a.

## Ligações
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos]] · [[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout]] ·
[[11-KNOWLEDGE/KB-0088-o-teto-de-participacao-nos-motores-de-backtest]] · [[05-EXPERIMENTS/EXP-M7-organica-lenta]] ·
`docs/plans/T4-MEME-RADAR.md` · `packages/indicators/hunter_indicators/meme/rules_criteria.py`
