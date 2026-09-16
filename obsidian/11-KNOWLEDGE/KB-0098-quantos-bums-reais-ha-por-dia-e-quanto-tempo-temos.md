---
tags: [knowledge, nota, meme, pumpfun, bum, tempo, mayhem, base-rate, m4]
tema: memecoin / pump.fun / quantos bums reais há por dia (SOL real na curva, sem Mayhem) e em quanto tempo acontecem
fonte: banco da VPS (meme_curve_snapshots, meme_tokens, meme_features_1m), 13–16/09/2026
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-t427-bum-real-sem-mayhem.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-t427-{picos-sao-mayhem,bum-real-sem-mayhem}.sql; 49 853 moedas não-Mayhem, 3 dias)
hipotese_testavel: sim
astra: não consultada nesta nota (orquestrador, 16/09 02:3x BRT)
confiança: alta
owner: sexta-feira
updated: 2026-09-16
status: vivo
---

# KB-0098 — Quantos "bums" reais há por dia no pump.fun, e quanto tempo temos para agir

**Pergunta do Everton (16/09 01:5x BRT):** "se a tendência move a moeda, a moeda conseguimos lucrar muito" — então quantas moedas
de fato explodem por dia, e em quanto tempo?

## 1. O que NÃO é bum: o SOL virtual do agente Mayhem
Ordenando as moedas dos últimos 3 dias pelo nosso mcap teórico (preço marginal × supply), os 95 "picos" acima de 500 SOL são
**todos** moedas Mayhem (`mayhem_enabled = true`), 76 deles com menos de 20 % da curva vendida. Exemplo KAT (15/09 17:37 BRT):
`virtual_sol_reserves` foi de 23,9 para 1 977 SOL em **60 s** com só 7 % dos tokens fora da curva — o agente injeta SOL
virtual; não houve compradores (5 holders). **Lição:** para medir bum, o número é o **SOL real na curva**
(`real_sol_reserves`), nunca o mcap teórico; Mayhem fica fora por padrão (T4.27 leva isso ao portão, à marca e ao placar).

## 2. Os bums reais (SOL real na curva, moedas não-Mayhem, 13–16/09)
| Medida (3 dias) | Número |
|---|---|
| Moedas não-Mayhem com fotografia | 49 853 |
| Passaram de 10 SOL reais | 8 224 (16,5 %) |
| Passaram de 30 SOL reais | 3 214 (6,4 %) |
| Passaram de 60 SOL reais | 1 842 (3,7 %) |
| Graduaram | 1 942 (3,9 %) |
| Mediana de tempo até 30 SOL / 60 SOL | **1 min / 1 min** |
| Chegaram a 30 SOL **depois** de 3 min de vida | **552 (1,1 %)** ≈ 184/dia |
| Chegaram a 30 SOL depois de 10 min | 198 (0,4 %) ≈ 66/dia |

**Leitura:** a esmagadora maioria dos bums acontece **no primeiro minuto** (bots e bundles no mesmo slot) — ali não há tempo
humano nem de mesa; é o território do sniper, que a porta recusa de propósito. O universo em que **há tempo de agir** é a
célula lenta: ~180 moedas/dia chegam a 30 SOL reais com ≥ 3 min de vida (média 58 min), e ~65/dia com ≥ 10 min.

## 3. O Lab e a célula lenta
Das 552 lentas: **103 graduaram** (18,7 % — contra 3,9 % da população), o Lab **propôs 29** e **apostou em 14** (2,5 %).
Ou seja: a célula onde há tempo e onde a taxa de graduação é 5× a média é exatamente a que os conjuntos atuais
(relógio de 15 s, idade 30–300 s) quase não olham. É a tese da [[05-EXPERIMENTS/EXP-M7-organica-lenta|EXP-M7]] (`organic_v0/1`,
entra 3–30 min, progresso 10–30 %) — que ainda não propôs nada porque exige `snipers ≤ 2`, `holders ≥ 20 subindo` e top-10 ≤ 30 %
lidos no minuto; a próxima medição é **por que** as 552 são recusadas (qual critério corta), antes de mexer em qualquer limiar.

## 4. O que muda amanhã
- T4.27: Mayhem fora do portão, da marca e do placar; `mcap_executable_sol` ao lado do teórico.
- Estudo seguinte (T4.28): o funil de recusas da `organic_v0/1` sobre as 552 lentas de 3 dias — quantas caem por sniper, por
  holders, por top-10, por criador — e um braço irmão pré-registrado com o critério que mais corta relaxado (previsão `descartar`).
- Notícia/evento (T4.26) entra aqui como **o que aponta para a lenta certa antes dos 3 min**, não como substituto da porta.

## Ligações
[[11-KNOWLEDGE/KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · [[11-KNOWLEDGE/KB-0095-pump-fun-rotulos-observados-do-site-da-rest-e-os-limites-on-chain]] · [[05-EXPERIMENTS/EXP-M7-organica-lenta]] · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas]] · [[00-INBOX/Hipoteses-do-plantao]]
