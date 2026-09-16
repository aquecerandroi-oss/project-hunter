---
tipo: estudo
tags: [meme, pumpfun, mesa, balanco, admissao, recusa, cadeia, encanamento, r39, m4]
data: 2026-09-16
janela_medida: 11:46:36–19:28:44 BRT (todas as ordens de `meme_live_orders` do dia)
medido_em: 2026-09-16 19:33–19:50 BRT (22:33–22:50 UTC, `date -u` conferido)
fonte: banco da VPS (meme_live_orders, meme_proposals, meme_curve_snapshots, meme_features_15s, meme_risk_snapshots, meme_tokens)
sql: infra/scripts/sql/research/2026-09-16-r39-q0{1,2,3,4}-*.sql
owner: sexta-feira
tarefa: R39
status: vivo
confianca: alta para os desfechos (cadeia, `real_sol_reserves`, 58/58 com fotos) e para os motivos de recusa (gravados pelo admissor); média para o R simulado (preço = `mcap_sol` da foto de 15 s, sem impacto de preço, saída marcada na foto e não no gatilho); baixa para qualquer taxa projetada (n = 29 moedas de um único dia)
updated: 2026-09-16
---

# Balanço do dia da mesa real — 16/09/2026 (R39)

> **Honestidade de relógio:** medição real **19:33–19:50 BRT** (`date -u` = 22:33–22:50 UTC,
> BRT = UTC−3). A janela de 30 min de **9 ordens** (as de 19:09 em diante) **ainda não tinha
> fechado** quando eu medi — está marcado linha a linha.
>
> **Método do desfecho:** tudo pela cadeia, `meme_curve_snapshots.real_sol_reserves`, nunca por
> `mcap_sol` nem pela fita — [[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]].
> A invariante `virtual_sol − real_sol = 30` foi conferida em **todas** as linhas de todas as 29
> moedas: **30,000 em todas**, nenhuma Mayhem no conjunto. A única linha que quebra a invariante
> (115,005) é a da **GREMLIN depois de graduar**, o que é o comportamento esperado de uma curva
> concluída.
>
> **Classificação de cada recusa** (pela cronologia dos gatilhos na cadeia, dentro de 30 min):
> **boa** = a curva perdeu ≥ 50 % do SOL real; **ruim** = subiu ≥ 50 % e não tinha perdido 50 %
> antes; **neutra** = nenhum dos dois; **sem dado** = sem fotos (não aconteceu: 58/58 têm cadeia);
> **graduou** = `complete = true` — aqui o `real_sol` vai a zero por **migração**, não por
> esvaziamento, e tratar isso como "boa" seria mentira.

## 1. O dia inteiro da mesa, ordem a ordem

**58 ordens em `meme_live_orders`, 29 moedas distintas, das 11:46:36 às 19:28:44 BRT. Todas
`refused`, todas `buy`, todas `mode = live`, zero assinaturas, zero fills.** A carteira não gastou
um lamport hoje. As 58 ordens vêm de 58 propostas `operator/5` `rejected`; na mesma janela a mesa de
**papel** encheu 54 ordens em 16 moedas (conjuntos `flow_v2`/`moonshot`/`hype_probe`), o que mostra
que o problema não é falta de fluxo: é a porta do executor.

Colunas: `prog` = progresso na proposta como a **feature de 15 s** o viu / como o **admissor** o viu
(os dois divergem, §2c). `rsol` em SOL reais na curva. `mín`/`máx` = extremos da cadeia nos 30 min
seguintes. `saída` = gatilho da simulação da §2d.

| # | hora BRT | símbolo | mint | prog 15 s / admissor | motivo real da recusa | rsol na ordem | mín 30 min | máx 30 min | desfecho | saída | R |
|---:|---|---|---|---|---|---:|---:|---:|---|---|---:|
| 1 | 11:46:36 | INCEPT | `FHcHh1…` | 41,1 % / **−5,4×10⁵** | `progress_below_window` | 13,087 | 2,556 | 24,471 | **ruim** | trailing35 | −0,87 |
| 2 | 11:46:55 | INCEPT | `FHcHh1…` | 47,1 % / **−5,5×10⁵** | `progress_below_window` | 16,049 | 2,556 | 24,471 | **ruim** | piso50 | −1,00 |
| 3 | 11:47:18 | INCEPT | `FHcHh1…` | 44,8 % / **−6,6×10⁵** | `progress_below_window` | 11,641 | 2,556 | 24,471 | **ruim** | trailing35 | −0,79 |
| 4 | 11:47:55 | INCEPT | `FHcHh1…` | 60,6 % / **−4,3×10⁵** | `progress_below_window` | 23,174 | 2,556 | 24,112 | boa | piso50 | −1,23 |
| 5 | 12:07:27 | CGRAM | `3tAFaZ…` | 58,2 % / **−5,1×10⁵** | `progress_below_window` | 17,524 | 18,343 | 21,930 | neutra | fim_serie | +0,10 |
| 6 | 12:52:40 | **GREMLIN** | `Gn9U13…` | 72,2 % / 82,9 % | `progress_above_window` | 34,893 | 0,000 | **74,767** | **graduou** | **alvo3x** | **+3,67** |
| 7 | 12:52:41 | GREMLIN | `Gn9U13…` | 72,2 % / 83,8 % | `progress_above_window` | 34,893 | 0,000 | 74,767 | **graduou** | alvo3x | +3,67 |
| 8 | 12:52:57 | GREMLIN | `Gn9U13…` | 72,8 % / 81,3 % | `progress_above_window` | 45,199 | 0,000 | 74,767 | **graduou** | fim_serie | +2,43 |
| 9 | 12:53:21 | GREMLIN | `Gn9U13…` | 96,5 % / 96,4 % | `progress_above_window` | 74,767 | 0,000 | 0,000 | **graduou** | fim_serie | +0,32 |
| 10 | 14:04:45 | SORT | `7uwn4T…` | 64,5 % / 65,2 % | `progress_above_window` | 28,738 | 0,782 | 27,650 | boa | piso50 | −1,39 |
| 11 | 14:05:07 | SORT | `7uwn4T…` | 63,9 % / 64,0 % | `progress_above_window` | 26,853 | 0,782 | 27,650 | boa | piso50 | −1,35 |
| 12 | 14:05:27 | SORT | `7uwn4T…` | 64,7 % / 64,9 % | `progress_above_window` | 27,650 | 0,782 | 27,650 | boa | piso50 | −1,37 |
| 13 | 14:08:26 | steve | `FLHSaT…` | 65,1 % / 60,5 % | `progress_above_window` | 25,587 | 21,674 | 43,239 | **ruim** | fim_serie | +0,73 |
| 14 | 14:13:51 | RIZZLERS | `3T4Aue…` | 84,6 % / 81,3 % | `progress_above_window` | 46,267 | 0,038 | 50,442 | boa | piso50 | −1,64 |
| 15 | 14:14:14 | RIZZLERS | `3T4Aue…` | 82,1 % / 78,3 % | `progress_above_window` | 41,152 | 0,038 | 50,442 | boa | piso50 | −1,60 |
| 16 | 15:33:15 | $casinu | `Cfsb4v…` | 38,3 % / 42,3 % | `creator_flow_unknown` | 11,847 | 0,486 | 14,630 | boa | fim_serie | −0,94 |
| 17 | 16:36:30 | guy | `4Yz9VQ…` | 54,2 % / 54,3 % | `progress_above_window` | 20,104 | 16,374 | 20,225 | neutra | fim_serie | −0,33 |
| 18 | 16:36:31 | parasitebe | `BVf9r1…` | 47,2 % / 47,2 % | `creator_flow_unknown` | 16,090 | 0,001 | 16,621 | boa | piso50 | −1,14 |
| 19 | 16:36:32 | parasitebe | `BVf9r1…` | 47,2 % / 47,2 % | `creator_flow_unknown` | 16,090 | 0,001 | 16,621 | boa | piso50 | −1,14 |
| 20 | 16:36:48 | parasitebe | `BVf9r1…` | 47,2 % / 47,6 % | `creator_flow_unknown` | 16,090 | 0,001 | 16,621 | boa | piso50 | −1,14 |
| 21 | 16:37:12 | parasitebe | `BVf9r1…` | 47,2 % / 48,2 % | `creator_flow_unknown` | 16,619 | 0,001 | 16,621 | boa | piso50 | −1,16 |
| 22 | 16:41:21 | DRAGON | `Cdgczy…` | 0,1 % / 0,01 % | `progress_below_window` | **0,003** | 0,003 | 0,003 | neutra¹ | fim_serie | −0,07 |
| 23 | 16:50:31 | BRINAA | `66LUgD…` | 51,6 % / 55,1 % | `progress_above_window` | 20,371 | 22,173 | 27,047 | neutra | fim_serie | +0,46 |
| 24 | 16:52:58 | **BRINAA** | `Bazxr9…` | 21,6 % / 16,2 % | **`bundled_share_above_cap`** (47,4 %) | 4,218 | 18,223 | 20,456 | **ruim** | fim_serie | **+1,77** |
| 25 | 16:58:14 | gary | `9ZGUWS…` | 47,4 % / 44,9 % | `creator_flow_unknown` | 15,655 | 0,108 | 19,280 | boa | piso50 | −1,12 |
| 26 | 16:58:33 | gary | `9ZGUWS…` | 46,4 % / 50,9 % | `progress_above_window` | 18,112 | 0,108 | 19,280 | boa | piso50 | −1,20 |
| 27 | 17:14:40 | SOLAMI | `9B5EqA…` | 28,2 % / 31,6 % | `creator_flow_unknown` | 8,610 | 0,003 | 9,173 | boa | fim_serie | −0,81 |
| 28 | 17:15:00 | SOLAMI | `9B5EqA…` | 30,2 % / 31,7 % | `creator_flow_unknown` | 9,145 | 0,003 | 9,173 | boa | fim_serie | −0,84 |
| 29 | 17:30:26 | ZIPPY | `5nCEDZ…` | 30,8 % / 38,0 % | `creator_flow_unknown` | 11,704 | 0,239 | 13,573 | boa | fim_serie | −0,95 |
| 30 | 17:30:44 | ZIPPY | `5nCEDZ…` | 38,0 % / 38,0 % | `creator_flow_unknown` | 11,704 | 0,239 | 13,573 | boa | fim_serie | −0,95 |
| 31 | 17:31:02 | ZIPPY | `5nCEDZ…` | 38,0 % / 39,8 % | `creator_flow_unknown` | 12,499 | 0,239 | 13,573 | boa | fim_serie | −0,99 |
| 32 | 17:35:29 | KITTYGBIKE | `yemWGA…` | 0,9 % / 0,06 % | `progress_below_window` | **0,014** | 0,014 | 0,014 | neutra¹ | fim_serie | −0,07 |
| 33 | 17:42:36 | YOLO | `HWZ6LQ…` | 10,8 % / 5,0 % | **`bundled_share_above_cap`** (40,8 %) | 1,614 | 1,570 | 10,440 | **ruim** | trailing35 | +0,01 |
| 34 | 17:47:32 | **TOKTIP** | `2oiz6g…` | 40,6 % / 40,7 % | `bundled_share_unmeasurable` | 12,930 | 15,221 | **39,866** | **ruim** | trailing35 | **+0,99** |
| 35 | 17:47:50 | TOKTIP | `2oiz6g…` | 40,8 % / 53,5 % | `progress_above_window` | 19,610 | 19,744 | 39,866 | **ruim** | trailing35 | +0,26 |
| 36 | 18:21:27 | CLARITYLES | `Gic6AE…` | 29,1 % / 28,2 % | `creator_flow_unknown` | 8,326 | 0,012 | 7,907 | boa | fim_serie | −0,79 |
| 37 | 18:21:44 | CLARITYLES | `Gic6AE…` | 28,2 % / 0,47 % | `progress_below_window` | **0,104** | 0,012 | 0,012 | boa¹ | fim_serie | −0,08 |
| 38 | 18:42:41 | KYLE | `6w89Uw…` | 48,5 % / **1,70 %** | `progress_below_window` | 15,570 | 0,015 | 0,330 | boa | piso50 | −1,11 |
| 39 | 18:42:42 | KYLE | `6w89Uw…` | 48,5 % / **1,68 %** | `progress_below_window` | 15,570 | 0,015 | 0,330 | boa | piso50 | −1,11 |
| 40 | 19:00:30 | GiftPad | `AGPTBp…` | 0,2 % / 0,08 % | `progress_below_window` | **0,041** | 0,001 | 0,017 | boa¹ | fim_serie | −0,07 |
| 41 | 19:05:38 | BYFD | `5RMJdD…` | 38,7 % / 40,4 % | `creator_flow_unknown` | 12,542 | 0,064 | 15,447 | boa | piso50 | −1,00 |
| 42 | 19:05:39 | BYFD | `5RMJdD…` | 38,7 % / 41,3 % | `creator_flow_unknown` | 12,542 | 0,064 | 15,447 | boa | piso50 | −1,00 |
| 43 | 19:05:40 | SCHEMECOIN | `7JfHoh…` | 46,1 % / 47,2 % | `creator_flow_unknown` | 15,483 | 0,297 | 29,847 | **ruim** | piso50 | −1,10 |
| 44 | 19:05:58 | BYFD | `5RMJdD…` | 41,3 % / 42,7 % | `creator_flow_unknown` | 13,162 | 0,064 | 15,447 | boa | piso50 | −1,02 |
| 45 | 19:05:59 | SCHEMECOIN | `7JfHoh…` | 48,6 % / 55,7 % | `progress_above_window` | 16,835 | 0,297 | 29,847 | **ruim** | piso50 | −1,15 |
| 46 | 19:06:42 | BYFD | `5RMJdD…` | 45,0 % / 45,6 % | `creator_flow_unknown` | 15,447 | 0,064 | 15,357 | boa | piso50 | −1,11 |
| 47 | 19:06:43 | BYFD | `5RMJdD…` | 45,0 % / 45,8 % | `creator_flow_unknown` | 15,447 | 0,064 | 15,357 | boa | piso50 | −1,11 |
| 48 | 19:07:02 | BYFD | `5RMJdD…` | 46,0 % / **0,51 %** | `progress_below_window` | 15,357 | 0,064 | 0,113 | boa | piso50 | −1,11 |
| 49 | 19:07:48 | Kitler | `EQBUzt…` | 1,7 % / 0,72 % | `progress_below_window` | **0,160** | 0,000 | 0,160 | boa¹ | fim_serie | −0,09 |
| 50 | 19:09:32 | EDSHEERUN | `5Bq1kL…` | 45,5 % / 44,5 % | `creator_flow_unknown` | 14,700 | 14,688 | 21,233 | neutra² | fim_serie | +0,29 |
| 51 | 19:09:53 | EDSHEERUN | `5Bq1kL…` | 44,5 % / 45,3 % | `creator_flow_unknown` | 15,083 | 15,667 | 21,233 | neutra² | fim_serie | +0,26 |
| 52 | 19:09:54 | EDSHEERUN | `5Bq1kL…` | 44,5 % / 44,7 % | `creator_flow_unknown` | 15,083 | 15,667 | 21,233 | neutra² | fim_serie | +0,26 |
| 53 | 19:15:39 | AAS | `5N92cQ…` | 36,5 % / 21,9 % | `creator_flow_unknown` | 8,340 | 1,454 | 3,785 | boa² | fim_serie | −0,68 |
| 54 | 19:15:40 | AAS | `5N92cQ…` | 36,5 % / 21,9 % | `creator_flow_unknown` | 8,340 | 1,454 | 3,785 | boa² | fim_serie | −0,68 |
| 55 | 19:19:11 | vibes | `AENAeN…` | 46,7 % / 3,8 % | `creator_flow_unknown` | **0,856** | 0,001 | 0,389 | boa¹˒² | fim_serie | −0,17 |
| 56 | 19:27:26 | INTRA | `9Pyqyg…` | 39,1 % / **2,09 %** | `creator_flow_unknown` | 15,341 | 0,566 | 0,566 | boa² | piso50 | −1,08 |
| 57 | 19:27:44 | INTRA | `9Pyqyg…` | 45,8 % / 2,51 % | `creator_flow_unknown` | **0,566** | 0,566 | 0,566 | neutra¹˒² | fim_serie | −0,07 |
| 58 | 19:28:44 | INUFLATION | `2DTthP…` | 39,2 % / 2,10 % | `creator_flow_unknown` | **0,434** | 0,001 | 0,472 | boa¹˒² | fim_serie | −0,12 |

¹ **base já vazia**: a curva tinha menos de 1 SOL real no instante da ordem (0,003 a 0,86 SOL) —
qualquer variação de 50 % sobre essa base é ruído; a recusa é correta por razão trivial (não havia
o que comprar). São 8 ordens.
² **janela ainda aberta às 19:33 BRT** (faltavam de 35 s a 1 187 s de cadeia): 9 ordens, todas do
último quarto de hora.

## 2. Totais

### 2a. A mesa, em números

| item | valor |
|---|---|
| ordens em `meme_live_orders` (11:46:36 → 19:28:44 BRT) | **58** |
| moedas distintas | **29** |
| ordens `refused` | **58 / 58 (100 %)** |
| ordens com assinatura / com fill | **0 / 0** |
| propostas `operator/5` no período (todas `rejected`, todas viraram ordem) | 58 |
| propostas de **papel** no mesmo período (para contraste) | 54 `filled` em 16 moedas |
| ordens com **retrato de risco** (`meme_risk_snapshots`) na hora da decisão | **5 / 58 (8,6 %)** — 4 moedas |
| ordens em que o admissor tinha um **`bundled_share`** para julgar | **5 / 58** (as mesmas) |

### 2b. Recusas por motivo

| motivo (`meme_live_orders.reason`) | ordens | moedas | o que é |
|---|---:|---:|---|
| `creator_flow_unknown` | **27** | **13** | dado ausente: não se sabe se o criador vendeu |
| `progress_above_window` | 15 | 6 | valor acima do teto de 50 % |
| `progress_below_window` | 13 | 7 | valor abaixo do piso de 2 % |
| `bundled_share_above_cap` | 2 | 2 | valor acima do teto de 20 % (47,4 % e 40,8 %) |
| `bundled_share_unmeasurable` | 1 | 1 | dado ausente: sem retrato de bundle |

**28 das 58 recusas (48 %) são por dado ausente**, não por risco medido. As outras 30 são por valor,
mas **13 delas dependem de um número de progresso que a própria cadeia desmente** (§2c).

### 2c. O progresso de que o admissor recusou 13 ordens não existe na cadeia

Das **13 recusas por `progress_below_window`**:

- **8 ordens (4 moedas: INCEPT, CGRAM, KYLE, BYFD) foram recusadas por "progresso abaixo de 2 %"
  com 11,6 a 23,2 SOL reais na curva.** Em INCEPT e CGRAM o valor lido pelo admissor é
  **negativo da ordem de −5×10⁵** (−541 546, −554 167, −657 115, −425 331, −505 185 — não é erro de
  digitação); em KYLE é **1,70 %** e em BYFD **0,51 %** — esta última **19 s depois** de o mesmo
  admissor ler **45,8 %** na mesma moeda.
- **5 ordens (DRAGON, KITTYGBIKE, CLARITYLES 18:21:44, GiftPad, Kitler) foram recusadas com razão:**
  a cadeia mostra **0,003 a 0,16 SOL reais** — curvas vazias. Aqui quem mentiu foi a **feature de
  15 s**, que dizia 28,2 % (CLARITYLES) e 1,7 % (Kitler) sobre curvas mortas — é a generalização do
  caso KITTYGBIKE da [[03-TRADING/Meme/Candidatas/2026-09-16-17h56-brt|R35]].

Ou seja: **as duas leituras de progresso erram, em direções opostas, no mesmo dia** — e a porta em
vigor recusa por causa das duas. O atraso estrutural da série de 15 s já está medido em
[[11-KNOWLEDGE/KB-0117-o-progresso-da-serie-de-15s-esta-atrasado|KB-0117]] (20,7 s p50, erro > 50 %
do SOL real em 9 % das linhas) e explica o segundo grupo. **O primeiro grupo é outro defeito, do
lado do admissor, e não está explicado por atraso nenhum**: nenhuma defasagem produz −5×10⁵ %, nem
faz o mesmo admissor ler 45,8 % e 0,51 % na mesma moeda com 19 s de diferença. Continua vivo às
19:28 BRT.

### 2d. Boas, ruins, neutras

Contando **por moeda** (a primeira ordem de cada uma — comprar a mesma moeda 4 vezes em 40 s é
artefato de repique do radar, não decisão):

| desfecho | moedas | ordens |
|---|---:|---:|
| **boa** (curva perdeu ≥ 50 % do SOL real) | **16** | 35 |
| **ruim** (subiu ≥ 50 % sem perder 50 % antes) | **6** | 10 |
| **neutra** | **6** | 9 |
| **graduou** (`complete`; migrou, não esvaziou) | **1** (GREMLIN) | 4 |
| **sem dado** | **0** | 0 |

**A porta acertou em 16 das 29 e errou em 7** (as 6 ruins + a GREMLIN, a única moeda do dia que
encheu a curva: 74,767 SOL reais e migração às 12:53:29, **8 segundos depois** da quarta recusa por
`progress_above_window`).

### 2e. O R que o robô teria feito comprando todas

Regra da mesa (`alvo_3x_trailing_35_apos_1_5x_tempo_30m v1`): alvo 3×, trailing 35 % armado a 1,5×,
tempo 30 min, piso −50 %, taxa **1,75 %/perna**. Preço = `mcap_sol` da foto da cadeia; entrada na
última foto ≤ hora da ordem (defasagem de 0 a 16 s). Convenção de R idêntica à do estudo R10:
`k = 0,9825/1,0175`, `R = (mult·k − 1)/(1 − 0,5·k)` — o piso −50 % vale exatamente **−1,00 R** e
3,0× vale **+3,67 R**.

| leitura | soma | média | positivas | negativas |
|---|---:|---:|---:|---:|
| **por moeda** (1 compra em cada uma das 29) | **−7,51 R** | −0,26 R | 8 moedas, **+8,03 R** | 21 moedas, **−15,54 R** |
| **por ordem** (as 58, como o robô de fato tentou) | **−23,54 R** | −0,41 R | 14 ordens, +15,21 R | 44 ordens, −38,75 R |

Gatilhos de saída nas 58: **piso −50 % em 24**, fim da série em 27, trailing em 5, alvo 3× em 2.

R por moeda (soma de **todas** as ordens daquela moeda, que é o que o robô teria feito de verdade):

| moeda | ordens | R | | moeda | ordens | R |
|---|---:|---:|---|---|---:|---:|
| **GREMLIN** `Gn9U13…` | 4 | **+10,08** | | ZIPPY `5nCEDZ…` | 3 | −2,89 |
| **BRINAA** `Bazxr9…` | 1 | **+1,77** | | gary `9ZGUWS…` | 2 | −2,32 |
| TOKTIP `2oiz6g…` | 2 | +1,25 | | SCHEMECOIN `7JfHoh…` | 2 | −2,26 |
| EDSHEERUN `5Bq1kL…` | 3 | +0,81 | | KYLE `6w89Uw…` | 2 | −2,21 |
| steve `FLHSaT…` | 1 | +0,74 | | SOLAMI `9B5EqA…` | 2 | −1,64 |
| BRINAA `66LUgD…` | 1 | +0,46 | | AAS `5N92cQ…` | 2 | −1,35 |
| CGRAM `3tAFaZ…` | 1 | +0,10 | | INTRA `9Pyqyg…` | 2 | −1,15 |
| YOLO `HWZ6LQ…` | 1 | +0,01 | | $casinu `Cfsb4v…` | 1 | −0,94 |
| BYFD `5RMJdD…` | 6 | **−6,37** | | CLARITYLES `Gic6AE…` | 2 | −0,87 |
| parasitebe `BVf9r1…` | 4 | −4,59 | | guy `4Yz9VQ…` | 1 | −0,33 |
| SORT `7uwn4T…` | 3 | −4,10 | | vibes `AENAeN…` | 1 | −0,17 |
| INCEPT `FHcHh1…` | 4 | −3,89 | | INUFLATION `2DTthP…` | 1 | −0,12 |
| RIZZLERS `3T4Aue…` | 2 | −3,25 | | Kitler / GiftPad / DRAGON / KITTYGBIKE (curvas já vazias) | 1 cada | −0,09 / −0,07 / −0,07 / −0,07 |

**Soma das 58 = −23,54 R.** Os três maiores buracos (BYFD, parasitebe, SORT) são exatamente as
moedas em que o radar repicou 3–6 vezes na mesma curva em segundos: **o repique multiplica o
prejuízo** e é um defeito de engenharia, não de tese.

Três ressalvas que puxam esse número para lados opostos e precisam ser ditas:

1. **GREMLIN pós-graduação.** Depois de migrar, o `mcap_sol` vem do `pumpfun_rest` (410,88) e não
   da curva. Forçando a saída na **última foto na curva** (340,98 = 2,61×), a moeda dá **+7,49 R**
   nas 4 ordens em vez de +10,08, e o total do dia cai de −23,54 para **−26,13 R**. A conclusão não
   muda; o sinal do dia fica ainda mais negativo.
2. **A saída está otimista.** Piso e trailing são marcados no `mcap` **observado** da foto de 15 s,
   que já passou do gatilho; uma venda real na curva sairia pior. Não há impacto de preço no
   modelo (bilhete de 0,05 SOL numa curva de 30+ SOL é desprezível, T4.29b), mas há a latência.
3. **`fim_serie` em 27 das 58.** A cadeia para de seguir a moeda quando ela morre; a saída vai na
   última foto disponível (mediana ~3 min, não 30). É o dado honesto que existe, não uma saída
   melhor que a regra.

Em dinheiro, com o bilhete de **0,05 SOL** por ordem (o tamanho que a mesa usa nas notas de
candidatas; o `intent` das ordens recusadas está vazio, então **isto é uma suposição minha**), 1 R
≈ 0,0259 SOL: o dia inteiro valeria **−0,61 SOL** por ordem, **−0,19 SOL** por moeda. A mesa não
ficou pobre por não comprar; ficou **de fora**, que é diferente.

## 3. A mesma leitura só para a janela de encanamento

Janela de encanamento = progresso **5–85 %**, bundle **≤ 35 %**, top-10 **≤ 30 %**, criador
desconhecido ok se dev ≤ 10 % (a mesma da R30/R35). Aplicada sobre os valores que o **próprio
admissor** viu, com o retrato de risco (`observed_at ≤ received_at`, sem look-ahead) como segunda
fonte.

| leitura | ordens admitidas | moedas | desfechos | R (por moeda) |
|---|---:|---:|---|---:|
| **(A) estrita** — exige retrato na hora | **2** | **1** | 1 boa | **−1,64 R** |
| **(B) frouxa** — bundle/top-10 ausentes passam | 36 | 17 | 10 boas, 3 ruins, 3 neutras, 1 graduou | **−5,75 R** |

**(A) A janela de encanamento compraria uma única moeda no dia inteiro: RIZZLERS `3T4Aue…`, às
14:13:51** (progresso 81,3 %, bundle **2,02 %**, top-10 18,3 %, dev 0 %, retrato de 121 s).
Resultado pela cadeia: **46,27 → 0,038 SOL reais (−99,9 %)** em menos de 3 min; a simulação sai no
piso, **−1,64 R**. A recusa foi boa.

O que trava as outras **não é teto nenhum: é a falta do bundle**. **39 das 58 ordens estavam com
progresso dentro de 5–85 %**, e **36 delas (92 %) não tinham `bundled_share` nenhum** para julgar —
o admissor tinha top-10 em quase todas (de outra fonte), mas bundle só nas **5** ordens com retrato
de risco na hora. Das 3 com bundle: RIZZLERS ×2 (2,02 %, admitida) e BRINAA `Bazxr9…` (47,4 %,
reprovada nos dois cenários) — e a BRINAA foi a **segunda recusa mais cara do dia (+1,77 R)**:
aqui o teto de bundle custou dinheiro, com 4,2 → 20,5 SOL reais nos 30 min seguintes.

**(B)** Deixando o dado ausente passar, a janela compraria 17 moedas e perderia **−5,75 R**. Ela
pegaria a GREMLIN (+3,67 R) — mas **só por ignorância**: às 12:53:21, quando o retrato da GREMLIN
finalmente chegou, ele dizia **bundle 39,76 %**, acima do teto de 35 %. **A janela de encanamento
recusaria a única moeda que graduou hoje assim que tivesse o dado dela.** Também pegaria TOKTIP
(+0,99) e steve (+0,73), e em troca compraria 10 moedas que esvaziaram a curva.

## 4. Conclusão, quatro linhas, sem suavizar

1. **A mesa real passou o dia inteiro sem comprar nada — 58 ordens, 29 moedas, 100 % recusadas — e
   isso, hoje, foi lucro: comprar todas daria −7,51 R por moeda (−23,54 R pelas 58 ordens, −26,13 R
   se a GREMLIN sair na curva). 16 recusas foram boas, 6 ruins e 1 (GREMLIN) foi um erro caro.**
2. **Mas ela acertou pelo motivo errado: 28 das 58 recusas (48 %) são por dado ausente
   (`creator_flow_unknown` em 27) e 13 das 30 restantes se apoiam num progresso que a cadeia
   desmente — 8 ordens recusadas por "abaixo de 2 %" tinham 11,6 a 23,2 SOL reais na curva, uma
   delas com o número −5×10⁵.** Uma porta que acerta por bug não é uma porta.
3. **Afrouxar os tetos não resolve: a janela de encanamento compraria 1 moeda no dia (RIZZLERS,
   −1,64 R) e, na versão frouxa, 17 moedas por −5,75 R — e recusaria a GREMLIN assim que o retrato
   dela chegasse (bundle 39,8 %). O gargalo é o retrato de risco: 5 ordens em 58 (8,6 %) tinham um,
   e 36 ordens com progresso na janela tinham bundle ausente.** Continua sendo o T4.28g, terceira
   rodada seguida.
4. **O que dá dinheiro hoje não está na porta, está no repique e na graduação: 1 moeda em 29 encheu
   a curva (+3,67 R sozinha, +10,08 R nas quatro ordens) e três moedas repicadas (BYFD, parasitebe,
   SORT) sozinhas custariam −15,06 R por comprar a mesma curva morta 3 a 6 vezes em segundos.**
   Antes de discutir teto, é preciso **um retrato por decisão** e **uma decisão por moeda**.

## Ligações

[[03-TRADING/Meme/Candidatas/2026-09-16-17h56-brt|Candidatas R35 (17:25–17:55)]] ·
[[03-TRADING/Meme/Candidatas/2026-09-16-17h30-brt|Candidatas R30]] ·
[[03-TRADING/Meme/Estudo-2026-09-16-o-que-a-mesa-propos-hoje-rendeu|R10 (mesma convenção de R, desfecho por `mcap`)]] ·
[[03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa|R5 (o que a admissão recusa)]] ·
[[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115 (desfecho pela cadeia)]] ·
[[11-KNOWLEDGE/KB-0117-o-progresso-da-serie-de-15s-esta-atrasado|KB-0117 (atraso do progresso de 15 s)]] ·
[[11-KNOWLEDGE/KB-0114-compradores-unicos-o-piso-e-o-r|KB-0114]] ·
[[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar|KB-0109]] ·
[[03-TRADING/Meme/README|Meme (catálogo)]] ·
`infra/scripts/sql/research/2026-09-16-r39-q0{1,2,3,4}-*.sql`
