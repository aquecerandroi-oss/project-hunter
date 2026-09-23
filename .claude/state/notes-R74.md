# R74 — H-011 (onde deve ficar o alvo) e H-012 (tempo máximo curto): nenhum dos dois mexe

**Pergunta (Everton, 23/09/2026 17:5x BRT):** *"manda medir essa do alvo então"* — o pedaço do R72 que
sobreviveu (*"vender o primeiro repique e não voltar"*, +3,44 pp em 62 % das posições) é uma pergunta
sobre **onde fica o alvo**. Acréscimo do coordenador durante o estudo: um segundo eixo, o **tempo
máximo de permanência** (H-012), porque as 4 vitórias reais de 23/09 bateram o alvo aos 190, 24, 2 e
29 s e a única perda (`AIRAA`) caiu aos 36 s.
**Pré-registos:** H-011 e H-012 em `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md`, previsão e refutação
usadas **verbatim**. A H-012 foi escrita na fila **antes** de o eixo do tempo ser simulado.
**Método:** o simulador e o carregador do R72 (`.claude/state/r72/load.py`, `sim.py`), reaproveitados
sem reescrever: relógio de execução = gatilho + 1,6 s, cadeia na ordem de observação (nunca
reordenada por timestamp), a taxa de entrada não cobrada duas vezes, pouso terminal aos 301,6 s.
Custo 2,23 % por ida e volta (R65 §3). **Nenhuma exportação nova**: as do R72 cobrem a população
(corte 23/09 19:31 UTC). Nada foi escrito na VPS.

---

## Resposta curta

**Nenhum alvo da grade é melhor que 1,15×, e nenhum tempo máximo é melhor que 300 s.
Veredito das duas: `REFUTA` pela cláusula literal da fila, nas duas populações.**

- O melhor alvo nas duas populações é **1,08×** — a **borda** da grade (refutação (b)). Nas reais rende
  **+3,05 pp** por SOL sobre o 1,15× (IC 95 % [−0,53, +7,27], p = 0,14), **a 5 s de atraso cai para
  +0,78 pp**, e no papel (463 posições) é **+0,19 pp** (IC [−0,55, +0,96]) e **morre a 5 s** (−0,05 pp,
  refutação (c)). **Nenhum** alvo ou repique tem IC inferior acima de +1 pp (refutação (a)).
- **No papel, a vantagem prevista de +5 pp fica excluída** por todos os IC (maior limite superior: +0,96 pp na grade da fila, +1,11 pp com a extensão 1,50).
  Nas reais não fica (1,08 chega a +7,27 pp) — mas esse ganho vem de 5 posições e **vive inteiro nas
  posições com buracos de fita > 30 s** (+8,15 pp lá, −3,06 pp onde a fita é contínua).
- **O fragmento do R72 evaporou** quando medido sem condicionar ao futuro: a regra que ele de facto
  mediu (vender a +3 % da marca de entrada e não voltar) dá **−0,31 pp** nas reais e +0,34 pp no papel.
  Os +3,44 pp eram a média do subgrupo que **depois** não teve queda — seleção pelo resultado.
- **Quanto fica na mesa hoje:** nas 23 saídas por alvo das reais, o lote ainda chegou a valer, em média,
  **+52 %** do custo a mais do que recebemos (mediana +28 %; 0,73 SOL no total) — **mas isso é um teto
  de oráculo**: trocar essas saídas por segurar até aos 300 s (contados da entrada) dá **−4,5 pp em
  média (mediana −23 pp)** e só é melhor em **39 %** das vezes; e nenhum alvo mais alto da grade
  (1,20 / 1,30 / 1,50) bate o 1,15×. **Nenhuma saída mais tardia que se mediu paga** — o que não prova
  que nenhuma saída intermédia pagaria (Astra). O 1,15× já apanha parte da corrida porque o pouso cai
  1,6 s depois do gatilho (mediana realizada +17,6 %, máximo +80 %).
- **Encurtar o tempo máximo (H-012) reduz parte da cauda, mas sacrifica vitórias e o D médio fica
  negativo:** a 30 s perdem-se **14 das 23** saídas por alvo das reais (57 de 141 no papel) e o D é
  −1,80 pp; as perdas ≥ 50 % descem de 2 para 1 nas reais e de 12 para 7 no papel, mas as quedas precoces
  (reais aos 21 s; papel 7 de 12 antes dos 30 s) ficam.

---

## 1. População e cobertura

| item | reais | papel |
|---|---|---|
| exportadas (R72) | 89 posições fechadas | 545 apostas, uma por mint |
| mints únicos | **78** | 545 |
| resolvíveis (≥ 3 trades da fita **dentro** dos 300 s) | 76 | 463 |
| **uma por mint — a primeira no tempo** (regra congelada, nunca pelo resultado) | **66** | **463** |
| com algum buraco > 30 s na janela | 36 de 66 | 309 de 463 |
| controlo 1,15× idêntico ao `r72.sim.simulate_current` | **66 de 66** | **463 de 463** |

**Desvio declarado face ao R72:** o R72 usou as 76 resolvíveis; a fila pede **uma por mint** e as 76
têm 10 mints repetidos (Astra, ronda 1). Aqui são 66. Os números do controlo não são por isso
comparáveis linha a linha com o R72.

**Fora da população:** as posições de 23/09 depois das 19:31 UTC (16:31 BRT) — entre elas `MMKT` e
`AIRAA`, citadas na motivação — **não estão** na exportação do R72 e não foram reexportadas. O caso
`MMKT` (alvo aos 2 s, realizou +63 %) é o mesmo fenómeno das linhas "realizado nas saídas por alvo" da §4.

## 2. O que foi congelado antes de correr

- **Contraste:** por posição, `D = PnL por SOL(política) − PnL por SOL(1,15×)`, mesma posição, mesmo
  custo, mesmo atraso; recuo de 10 % armado na entrada e 300 s iguais para todas.
- **Grade principal = a da fila:** alvos {1,08 · 1,12 · 1,15 · 1,20 · 1,30} + repique {3, 5, 8} %.
  **1,50 é extensão do brief**, com veredito separado (acrescentá-lo muda o que é "borda" — Astra).
- **Repique (pré-registo verbatim):** queda ≥ X % a partir da máxima corrente, depois recuperação ≥ X %
  a partir do fundo; vende e não volta. Sem prazo N (a fila não o fixa). Diagnóstico à parte: a regra
  que o R72 realmente mediu (`EntryPop`: marca ≥ marca de entrada × (1 + X), sem queda) e o repique
  sem recuo.
- **Estatística:** bootstrap por cluster de mint 10 000 (mesmo estimador do `r72/run.py`, vetorizado);
  permutação por troca de sinal **por mint** 10 000; Holm sobre a família de 8; Wilson para a fração
  ≥ 50 % de perda; perdas graves criadas/evitadas por par.
- **Regra de decisão** (`stats.verdict`): `CONFIRMA` = uma política ≠ 1,15× com D ≥ +0,05, IC inferior
  > 0, vizinho da mesma família com D > 0 (o 1,15× não conta — D = 0 por construção) e D > 0 a 5 s.
  `REFUTA` = (a) nenhum IC inferior > +0,01 **ou** (b) melhor alvo na borda **ou** (c) o D da mesma
  política escolhida a 1,6 s fica ≤ 0 a 5 s. **Refutação tem precedência.** Empate no "melhor" → interior.
  Hipótese inteira: `CONFIRMA` só se as duas populações confirmam.
- **"Na mesa"** é ex post, fora da decisão, e **não entra no veredito**. Sem observação depois do pouso
  é **indisponível**, não zero; saída por tempo não tem futuro dentro da janela.

## 3. H-011 — a grade do alvo (base: 2,23 %, 1,6 s)

**Reais, n = 66** (`r74/out.txt`)

| política | PnL/SOL | ganho | sai pela política | hold med. | pior | ≥ 50 % de perda [Wilson] | criadas/evitadas | D vs 1,15× | IC 95 % | p | Holm |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1,08× | **−0,33 %** | 52 % | 50 % | 26 s | −30,2 % | **0,0 %** [0–5,5] | 0 / 2 | **+3,05 pp** | [−0,53, +7,27] | 0,139 | 0,97 |
| 1,12× | −2,74 % | 38 % | 38 % | 31 s | −61,6 % | 3,0 % [0,8–10,4] | 0 / 0 | +0,64 | [−0,42, +2,36] | 0,757 | 1 |
| **1,15× (atual)** | **−3,38 %** | 36 % | 35 % | 31 s | −61,6 % | 3,0 % [0,8–10,4] | — | 0 | — | — | — |
| 1,20× | −2,04 % | 36 % | 30 % | 33 s | −61,6 % | 3,0 % | 0 / 0 | +1,34 | [**+0,003**, +2,97] | 0,070 | 0,56 |
| 1,30× | −3,09 % | 33 % | 18 % | 42 s | −61,6 % | 3,0 % | 0 / 0 | +0,29 | [−2,75, +3,15] | 0,851 | 1 |
| 1,50× *(ext.)* | −3,44 % | 32 % | 11 % | 45 s | −72,5 % | 4,5 % [1,6–12,5] | 1 / 0 | −0,06 | [−4,78, +4,39] | 0,981 | 1 |
| repique 3 % | −4,01 % | 30 % | 39 % | 28 s | −61,6 % | 3,0 % | 0 / 0 | −0,64 | [−4,06, +2,87] | 0,728 | 1 |
| repique 5 % | −1,68 % | 38 % | 27 % | 38 s | −61,6 % | 3,0 % | 0 / 0 | +1,69 | [−2,17, +6,47] | 0,492 | 1 |
| repique 8 % | −4,17 % | 33 % | 14 % | 40 s | −72,5 % | 4,5 % | 1 / 0 | −0,80 | [−5,74, +4,03] | 0,763 | 1 |

**Papel, n = 463**

| política | PnL/SOL | ganho | sai pela política | hold | pior | ≥ 50 % [Wilson] | cri./evit. | D | IC 95 % | p | Holm |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1,08× | −2,78 % | 43 % | 44 % | 19 s | −91,5 % | 2,4 % [1,3–4,2] | 0 / 1 | +0,19 | [−0,55, +0,96] | 0,626 | 1 |
| 1,12× | −3,06 % | 37 % | 36 % | 23 s | −91,5 % | 2,6 % | 0 / 0 | −0,09 | [−0,49, +0,34] | 0,673 | 1 |
| **1,15×** | **−2,97 %** | 35 % | 30 % | 24 s | −91,5 % | 2,6 % [1,5–4,5] | — | 0 | — | — | — |
| 1,20× | −3,01 % | 33 % | 24 % | 26 s | −91,5 % | 3,0 % | 2 / 0 | −0,05 | [−1,00, +0,94] | 0,929 | 1 |
| 1,30× | −3,63 % | 31 % | 14 % | 29 s | −91,5 % | 3,2 % | 3 / 0 | −0,66 | [−1,84, +0,50] | 0,277 | 1 |
| 1,50× *(ext.)* | −3,38 % | 30 % | 8 % | 31 s | −91,5 % | 3,7 % [2,3–5,8] | 5 / 0 | −0,42 | [−1,94, +1,11] | 0,602 | 1 |
| repique 3 % | −4,45 % | 33 % | 39 % | 21 s | −91,5 % | 2,2 % | 1 / 3 | **−1,49** | [−2,80, −0,20] | 0,022 | 0,18 |
| repique 5 % | −3,50 % | 32 % | 28 % | 24 s | −91,5 % | 2,4 % | 1 / 2 | −0,54 | [−1,98, +0,94] | 0,483 | 1 |
| repique 8 % | −3,97 % | 31 % | 11 % | 30 s | −91,5 % | 3,5 % | 5 / 1 | −1,00 | [−2,66, +0,78] | 0,253 | 1 |

**Todas as políticas perdem em nível** nas duas populações. A melhor das reais (1,08×, −0,33 %) ainda
é negativa: "perder menos" não é um braço lucrativo.

**Patamar × pico.** Nas reais a curva do alvo é **em serra**, não um patamar: +3,05 (1,08), +0,64 (1,12),
0, +1,34 (1,20), +0,29 (1,30), −0,06 (1,50). No papel é **plana à volta de zero** (±0,7 pp). O repique
não é melhor em nenhum X; no papel o de 3 % é **pior** que o controlo (IC inteiro abaixo de zero, não
sobrevive a Holm).

**Quem carrega o 1,08× nas reais:** 27 das 66 posições mudam de resultado; o D médio vem de cinco —
SNORP +0,71, WAVECOREE +0,61, Crabbo +0,51, VOVO +0,44, SOLBUX +0,31 por SOL — moedas que tocaram
1,08× e caíram antes de 1,15×. Do outro lado, FLYJEV −0,33 e CYBER −0,29 (passaram muito do 1,15×).

**Estratos de cobertura (heterogeneidade, não causa):**

| D por maior buraco na janela | 1,08 | 1,12 | 1,20 | 1,30 | 1,50 | rep. 3 | rep. 5 | rep. 8 |
|---|---|---|---|---|---|---|---|---|
| reais, buraco ≤ 30 s (n = 30) | **−3,06** | −0,30 | +2,29 | +3,26 | +5,88 | −2,12 | +3,62 | +3,15 |
| reais, buraco > 30 s (n = 36) | **+8,15** | +1,42 | +0,55 | −2,19 | −5,02 | +0,60 | +0,09 | −4,08 |
| papel, buraco ≤ 30 s (n = 154) | −1,45 | −0,45 | +0,27 | +0,70 | +1,91 | −3,21 | −1,56 | +0,37 |
| papel, buraco > 30 s (n = 309) | +1,01 | +0,09 | −0,21 | −1,34 | −1,58 | −0,63 | −0,02 | −1,69 |

O sinal **inverte-se com a qualidade da fita**, nas duas populações: onde a fita é contínua, alvos
**mais altos** ficam melhores e o 1,08× é pior; onde há buracos, é o contrário. Um buraco esconde o
caminho entre dois pontos, e um alvo baixo "dispara" no primeiro ponto depois do buraco. Não prova
artefacto, mas o único ganho do 1,08× mora nas posições pior observadas.

### Sensibilidade (D e IC 95 %, reais / papel)

| política | 2,23 % · 1,6 s | 2,23 % · **5 s** | 3 % · 1,6 s | 3 % · 5 s |
|---|---|---|---|---|
| 1,08× | +3,05 [−0,53, +7,27] / +0,19 | **+0,78** [−2,31, +4,50] / **−0,05** | +3,04 / +0,19 | +0,78 / −0,05 |
| 1,20× | +1,34 [+0,00, +2,97] / −0,05 | +1,50 [−0,34, +3,63] / −0,47 | +1,33 / −0,05 | +1,49 / −0,47 |
| 1,30× | +0,29 / −0,66 | +0,40 / **−1,42** [−2,63, −0,33] | +0,29 / −0,66 | +0,40 / −1,42 |
| repique 5 % | +1,69 / −0,54 | +0,90 / −0,39 | +1,69 / −0,53 | +0,90 / −0,39 |

(tabela completa em `r74/out.txt`). **O custo quase não mexe no D** — e isso é estrutural, não sorte:
o contraste é uma saída contra uma saída, as duas pagam c/2, e c só escala o produto de ambas. O
**atraso** é o que mexe: o 1,08× perde três quartos do ganho nas reais e o sinal no papel.

### Veredito H-011

| população | grade | rótulo | cláusulas que disparam |
|---|---|---|---|
| reais | fila (1,08–1,30) | **REFUTA** | (a) maior IC inferior +0,003 pp ≤ +1 pp; (b) melhor = 1,08× na borda |
| reais | brief (1,08–1,50) | **REFUTA** | (a); (b) |
| papel | fila | **REFUTA** | (a) maior IC inferior −0,49 pp; (b) 1,08× na borda; (c) 1,08×: +0,19 → −0,05 pp a 5 s |
| papel | brief | **REFUTA** | (a); (b); (c) |

**Cláusula literal e interpretação estatística, lado a lado** (a Astra pediu as duas, sem reinterpretar):
- *Literal:* `REFUTA` nas duas populações, por três cláusulas independentes no papel e duas nas reais.
- *Estatística:* no **papel** a vantagem de +5 pp está **excluída** (nenhum IC superior passa de +0,96 pp
  na grade da fila, +1,11 pp com a extensão 1,50) — aqui a refutação é também económica. Nas **reais**:
  **não confirma vantagem; +5 pp não excluídos a 1,6 s** (IC superior do 1,08× +7,27 pp). O 1,08× está
  na borda, **atenua fortemente** a 5 s (+0,78 pp, IC [−2,31, +4,50] — a cláusula (c), D ≤ 0, **não**
  dispara nas reais), é carregado por 5 moedas e vive nas posições com buracos de fita; o papel, com sete
  vezes mais posições, não o repete. O 1,20× tem o único IC inferior acima de zero (+0,003 pp), mas p
  bruto 0,070 e Holm 0,56 — não é descoberta. Nenhum `CONFIRMA` em nenhuma célula.
- **Nenhum braço de papel é proposto** (só `CONFIRMA` vira sombra).

## 4. Quanto fica na mesa (ex post, fora do veredito)

**Regra atual (1,15×), saídas pelo alvo:**

| | reais (n = 23) | papel (n = 141) |
|---|---|---|
| realizado nessas saídas: mediana | **+17,6 %** (o pouso 1,6 s depois apanha a corrida: máx. +80,4 %) | +18,2 % (máx. +199 %) |
| **teto oráculo** — melhor venda posterior do mesmo lote, até aos 300 s: média / mediana | **+52,3 % / +27,8 %** do custo | +57,8 % / +28,2 % |
| em SOL, somado | **0,728 SOL** (~0,032 por saída) | 4,39 SOL |
| **segurar do pouso até aos 300 s**: média / mediana | **−4,5 pp / −23,1 pp** | −5,3 / −21,5 pp |
| segurar teria sido melhor em | **39 %** | 35 % |
| em SOL, somado | **−0,057 SOL** | −0,268 SOL |

Leitura (corrigida pela Astra — "o alvo não é cedo" ultrapassava o diagnóstico): **substituir as saídas
pelo alvo por segurar até ao fim piorou, em média e em mediana**, e nenhum alvo mais alto da grade paga.
Isto não testa todas as saídas intermédias possíveis; um pico seguido de queda torna "segurar até ao
fim" mau mesmo quando outra saída pagaria. O que fica na mesa existe (um terço do custo, em mediana, de
oráculo), mas é a cauda de poucas moedas que continuam a correr, e nenhuma regra causal da grade o apanha: subir
o alvo para 1,30× ou 1,50× (D ≈ 0 e −0,4 a −0,7 pp no papel) só troca saídas pelo alvo por saídas pelo
recuo. Nas saídas pelo **recuo** o sinal é o inverso — segurar dá +7,6 pp em média nas reais (mediana
−1,5 pp): a média é puxada por recuperações raras.

Nos alvos altos do papel há um sinal descritivo: quem bate 1,30× / 1,50× continua a correr (segurar é
melhor em 51 % / 58 %, mediana +1,3 / +4,5 pp). É **condicional ao resultado** (só as que bateram o alvo
alto) e não vira D incondicional — fica como observação, não como hipótese confirmada.

## 5. A assimetria — mais alvo compra mais cauda?

Sim, e é por isso que a média não chega:

- **Subir o alvo** de 1,15× para 1,50× aumenta a fração de perdas ≥ 50 % de **3,0 % → 4,5 %** nas reais
  (1 criada, 0 evitadas) e de **2,6 % → 3,7 %** no papel (**5 criadas, 0 evitadas**); o pior negócio
  nas reais passa de −61,6 % para −72,5 %. O upside não compensa: D ≈ 0 e negativo no papel.
- **Descer o alvo** para 1,08× evita as duas perdas graves das reais (3,0 % → 0,0 %, Wilson [0; 5,5 %];
  pior −30,2 %) — o único efeito limpo na cauda do estudo. **No papel não se repete** (2,6 % → 2,4 %,
  1 evitada; pior igual, −91,5 %): perdas de 90 % em papel são quedas num único salto que nenhum alvo
  apanha.
- O repique sem recuo (diagnóstico) põe a cauda em 6–12 % nas reais — reconfirma o R72: sem freio, a
  política fica dentro enquanto a moeda morre.

## 6. H-012 — tempo máximo curto (pré-registado antes de correr este eixo)

Linha principal = alvo 1,15× com `max_hold ∈ {30, 60, 120, 300}`; controlo = regra atual (1,15× / 300 s).
Linha secundária (descritiva) = o melhor alvo do eixo do alvo (1,08× nas duas populações).
Elegibilidade medida sempre na janela de 300 s — a população não muda entre células (`hold.txt`).

| max_hold | PnL/SOL reais | D reais [IC 95 %] | p | vitórias cortadas (reais) | ≥ 50 % reais | PnL/SOL papel | D papel [IC] | vitórias cortadas (papel) | ≥ 50 % papel |
|---|---|---|---|---|---|---|---|---|---|
| 30 s | −5,17 % | **−1,80** [−6,03, +2,11] | 0,42 | **14 de 23** (−0,178 SOL) | 1,5 % | −3,29 % | −0,32 [−1,89, +1,06] | **57 de 141** (−0,696 SOL) | 1,5 % |
| 60 s | −2,05 % | +1,32 [−1,26, +4,35] | 0,41 | 7 de 23 | 1,5 % | −2,66 % | +0,30 [−1,04, +1,47] | 27 de 141 | 1,5 % |
| 120 s | −2,58 % | +0,80 [−1,16, +3,55] | 0,67 | 5 de 23 | 1,5 % | −2,63 % | +0,34 [−0,19, +0,97] | 10 de 141 | 2,2 % |
| **300 s (atual)** | −3,38 % | 0 | — | 0 | 3,0 % | −2,97 % | 0 | 0 | 2,6 % |

A 5 s de atraso nada muda de sinal nas reais (60 s: +1,28 pp); no papel o 60 s vai a −0,04 pp.

**Veredito H-012: `REFUTA`** nas duas populações, pela cláusula (a): o maior IC inferior é −1,16 pp
(reais) e −0,19 pp (papel), longe de +1 pp. O melhor valor (60 s nas reais, 120 s no papel) **não** está
na borda, e não morre a 5 s — refuta só por (a), e economicamente também: todos os IC superiores ficam
abaixo de +5 pp (máximo +4,35 pp).

**Porquê:** a ideia "o que não sobe logo não sobe mais" é **metade verdade**. Na história inteira (não
só em 23/09), das 23 saídas por alvo das reais, **9** pousaram até aos 31,6 s, 16 até aos 61,6 s e
18 até aos 121,6 s (quartis 27 / 46 / 106 s) — o dia 23/09 (3 de 4 abaixo de 30 s) foi mais rápido que
o normal. O relógio curto **reduz parte da cauda** — a 30 s as perdas ≥ 50 % descem de 2 para 1 nas
reais e de 12 para 7 no papel (Astra: não confundir isto com ausência de efeito) — mas deixa as quedas
precoces (reais aos 21 s; papel 7 de 12 antes dos 30 s), sacrifica 14 de 23 vitórias e o D médio fica
negativo. Um efeito sobre a cauda sem efeito médio não é o que a H-012 previu.

## 7. Ressalvas (a que importa mais primeiro)

1. **Cobertura e observabilidade, juntas** (ordem da Astra). O dado mais forte do estudo é a inversão do
   1,08×: **−3,06 pp nas 30 posições reais com buraco ≤ 30 s, +8,15 pp nas 36 com buraco > 30 s** (§3).
   Não prova viés causal, mas o ganho agregado depende do estrato pior observado — o modelo usa o último
   estado conhecido até ao pouso, inclusive através de lacunas. E a simulação **assume que a mesa age
   sobre cada estado no seu `block_time`**, porque ao vivo ela vê pela fita **WS**. A fita aqui vem de
   `meme_trades`, cópia por polling com **~44 s de atraso de chegada ao arquivo** (R73) — isso é atraso do
   arquivo, **não** latência medida da mesa WS, e não mexe na ordem do caminho. Os 5 s simulados atrasam
   o **pouso** depois do gatilho; **não simulam atraso de observação**, que poderia mudar ou suprimir
   gatilhos. Se a visão ao vivo atrasar, todas as políticas — controlo incluído — agem tarde.
2. **Reais n = 66**, IC largos (±4 pp no 1,08×); o papel é o árbitro por potência, mas é outra população
   (sem slot na âncora, `observed_at`). Com a dispersão observada (DP do D ≈ 16 pp nas reais, ≈ 8 pp no
   papel), resolver +5 pp com 80 % de potência pede ~80 posições por braço — mas o efeito que o papel
   estima (+0,19 pp) pediria dezenas de milhares; não há braço a propor.
3. **Os dados já tinham sido vistos** (R72 gerou a H-011 com eles). Pré-registar agora não faz disto uma
   amostra independente — um `CONFIRMA` aqui teria precisado de replicação em posições posteriores.
4. `MMKT` e `AIRAA` (23/09 depois das 19:31 UTC) estão fora da exportação.
5. **O custo quase não mexe no contraste** por construção (uma saída contra uma saída); a sensibilidade de
   custo responde a outra pergunta (nível), não ao D.

## 8. Anti-antecipação

`.claude/state/r74/test_r74.py`, **47 testes, todos a passar** (saída em §11):

- a política só lê o caminho por uma `View` presa ao cursor; ler à frente levanta `LookAheadError`;
- **o batoteiro é apanhado:** uma política que espreita o ponto seguinte levanta `LookAheadError`;
- **fuga pelo `reset`** (achado da Astra): o `reset` recebia `P` e podia ler `P["path"]` inteiro; agora
  recebe só dois inteiros do instante da entrada, e um teste espião o prova;
- invariância ao sufixo futuro em 20 séries × 3 políticas × 3 cortes: trocar o futuro não muda nenhuma
  saída cujo pouso é anterior ao corte;
- o controlo 1,15× é **igual ao lamport** ao `r72.sim.simulate_current` (sintético e nas 66 + 463 reais);
- o oráculo (vende no máximo da janela olhando o futuro) ganha sempre: +47,4 % por SOL nas reais contra
  −3,38 % da regra atual — é a distância que a guarda protege;
- valores conhecidos: alvos, repique só depois da queda, recuo armado, queda que cruza mergulho e recuo,
  repique depois dos 300 s não conta, pouso terminal aos 301,6 s / 305 s, "na mesa" indisponível ≠ 0,
  `max_hold` curto corta a vitória tardia e não muda a população, Holm, Wilson, permutação por cluster,
  e as quatro saídas da regra de decisão (confirma no interior, refuta na borda, refuta a 5 s, não
  confirma sem patamar).

## 9. Segunda opinião (Astra)

Chamadas: `bash infra/scripts/astra.sh ask r74 "..."` (**antes** de correr nos dados) e
`... ask r74-veredito "..."` (antes de escrever o veredito). Respostas em
`.claude/state/astra-review-r74.md`, `.claude/state/astra-review-r74-veredito.md` e — da sessão
anterior, que caiu antes de produzir código — `.claude/state/r74/astra-pre-sessao-anterior.md`.

**Ronda 1 (antes de correr) — aceites e aplicados:**

1. **Fuga pelo `reset`.** A política recebia `P` no `reset` e podia ler `P["path"]` inteiro, contornando
   a `View`; ela reproduziu a fuga (saída mudou de 1,6 s para 301,6 s trocando só o futuro). Corrigido:
   o `reset` recebe dois inteiros; teste espião.
2. **Grade principal = a da fila** (1,08–1,30); o 1,50 do brief muda o que é borda, logo é extensão com
   veredito próprio.
3. **Uma por mint** (a fila pede-o; as 76 do R72 tinham 10 mints repetidos) → 66, a primeira no tempo.
4. **Permutação por cluster de mint**, na mesma unidade do bootstrap; **Holm** na família; **Wilson** e
   criadas/evitadas para a cauda.
5. **"Na mesa" indisponível ≠ zero**, estratificado por motivo, com tempo restante; a saída por tempo
   não tem futuro por construção e não é "saída excelente".
6. **(c) congelado** como D ≤ 0 da mesma política escolhida a 1,6 s; IC a atravessar zero a 5 s é
   evidência insuficiente, não desaparecimento. Retirei a exigência extra de IC > 0 a 5 s para
   confirmar, que eu tinha acrescentado e a fila não pede.
7. **Empate no "melhor" → interior**; a regra que o R72 mediu (`EntryPop`) medida em toda a população.
8. **Estratos de cobertura** (buraco ≤ 30 s / > 30 s) — foi daqui que saiu a ressalva número um.

**Ronda 2 (veredito) — três correções de redação, todas aceites:**

1. "O 1,08× morre a 5 s" estava errado **nas reais**: cai para +0,78 pp e a cláusula (c) não dispara lá.
2. "Encurtar o tempo não apanha as perdas" era excessivo: a 30 s as perdas ≥ 50 % descem 2 → 1 e 12 → 7.
3. "O alvo não é cedo" ultrapassava o diagnóstico: o que os números dizem é que **trocar as saídas pelo
   alvo por segurar até ao fim piorou**, e nenhum alvo mais alto paga. O KB foi renomeado para
   *subir o alvo não paga*.

Também aceite: a ordem das ressalvas (cobertura e observabilidade juntas, primeiro), "44 s é atraso do
arquivo, não da mesa WS" e "os 5 s atrasam o pouso, não a observação".

**Rejeitado, com razão:** nada. **Não fiz** o ensaio de degradação sintética da fita (remover blocos em
fitas densas e medir D degradado − D original) que ela sugeriu como nice-to-have na ronda da sessão
anterior — fica como o próximo passo se alguém quiser separar artefacto de efeito no 1,08×.

## 10. Arquivos

`.claude/state/r74/`:

| ficheiro | o que é |
|---|---|
| `policies.py` | motor de saída causal (`View`, `Target`, `FirstPop`, `EntryPop`, `run_exit`, "na mesa") sobre as pernas do R72 |
| `stats.py` | bootstrap por mint, permutação por cluster, Holm, Wilson, regra de decisão congelada |
| `report.py` → `out.txt` | H-011: grade, contraste, estratos, sensibilidade, veredito, diagnóstico |
| `hold.py` → `hold.txt` | H-012: eixo do tempo máximo |
| `test_r74.py` | 47 testes |
| `astra-pre-sessao-anterior.md` | parecer da Astra pedido pela sessão que caiu (guardado antes de ser sobrescrito) |

Reaproveitados sem alteração: `.claude/state/r72/load.py`, `sim.py`, `run.py` (`boot_ci`, no teste),
`test_r72.py` (`_pos`), e as exportações `q1`–`q6`.
Astra: `.claude/state/astra-review-r74.md`, `.claude/state/astra-review-r74-veredito.md`.
KB: `obsidian/11-KNOWLEDGE/KB-0154-subir-o-alvo-nao-paga.md`.

## 11. Saída dos testes

```
$ cd .claude/state/r74 && uv run pytest test_r74.py -p no:cacheprovider -q --rootdir=.
...............................................                          [100%]
47 passed in 2.41s
```
