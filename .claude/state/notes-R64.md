# R64 — O que o dia 19/09 ensinou à mesa real de memes (24 operações)

**Data:** 2026-09-19, `as_of` 23:0x BRT. **Pergunta (Everton, 22:3x BRT):** "a mesa real está tomando forma — o que hoje ensinou?" Regras do dia: alvo 1,15×, trailing 10 % armado na entrada, `max_hold` 300 s, saída por evento ligada; `operator/5` (22 operações) e `operator/6` (2). Método = R62 (reconstrução da fita `meme_trades` a partir das reservas exatas do fill; `.claude/state/r62/` reutilizado; código novo em `.claude/state/r64/`).

**Resposta curta.** Dia **−0,0404 SOL** em 24 operações (9 alvos +0,0106 médio, 15 perdas −0,0090 médio, acerto 37,5 %). Três lições, por ordem de dinheiro:

1. **0,0303 SOL do prejuízo do dia (75 %) é rent de ATA estacionado, não perda de mercado.** As 24 vendas saíram com `closes_ata = false` (a T4.46 existe, mas `MEME_CLOSE_ATA_ON_FULL_SELL` está desligada por padrão e ninguém a ligou); nenhuma das 39 vendas da mesa desde 17/09 teve reembolso. Há **34 ATAs abertas = 0,0514 SOL parados** (recuperáveis: fechar as contas devolve o rent). Sem o rent, o dia teria sido **−0,0101 SOL**; as taxas de protocolo + criador foram 0,0388 SOL (1,25 %/perna × 48 pernas) e a rede 0,0023.
2. **A regra atual (trailing 10 % da entrada + alvo 1,15) foi a melhor das 52 combinações da grade nas 24** — o oposto do que as 8 da madrugada sugeriam (R62). Motivo: hoje o dinheiro **não** ficou na mesa nas saídas por trailing — 12 das 15 saídas por trailing eram moedas mortas (MFE < +11 %, e 9 delas ≤ −40 % aos 300 s; 5 posições (4 moedas) perderam ≥ 70 % **num único bloco/foto de 15 s**: ARGUSACT, Musepaid ×2 e KODA drenaram a curva a zero de SOL real; NOOP foi de +40 % a −68 % num segundo). Trailing mais largo (15/20/30 %) segura a moeda através do bloco do dump e custa **−0,11 a −0,15 SOL** a mais; armar depois de +10/+20 % custa −0,12; segurar até os 300 s daria **−0,40 SOL**. Só XCrypto, FЕРЕ e NARKY#1 (as 3 do R62) foram "dinheiro na mesa" — e são da madrugada.
3. **Manhã ≠ tarde.** 02–11 h BRT: 11 operações, 5 alvos, **+0,0033 SOL**, MFE mediano +44 %. 14–20 h BRT: 13 operações, 4 alvos, **−0,0438 SOL**, MFE mediano +8 %, 7 de 13 a ≤ −40 % aos 300 s. Com n = 11/13 é indício, não regra; mas as moedas da tarde não subiram nem para quem segurou.

Recompra do mesmo mint depois de trailing (Musepaid, 25 s depois): nas 24 a pausa por mint **custa** 0,0124 SOL (tira NARKY#2 +0,0142 e Musepaid#2 −0,0018); nas 294 apostas de papel de hoje, as 19 entradas após uma saída por trailing no mesmo mint deram **0 acertos em 19, −0,338 SOL, R médio −0,58** (vs −0,125 geral). É a regra testável do dia: **EXP-M21** (pausa por mint de 5 min após trailing, medida em papel por 3 dias).

## 1. Dados e cobertura

| item | valor |
|---|---|
| posições | `meme_live_positions`, `entry_at ≥ 2026-09-19 03:00 UTC` → **24**, todas `closed` (`q2.sql`, `pos24.csv`); `operator/5` 22, `operator/6` 2 (JEANJACKET, Musepaid#1) |
| fita | `meme_trades` das 20 moedas, entrada −15 min → saída +10 min: 6 592 trades (`q4.sql`, `trades.csv`); **16 moedas com fita depois da entrada**; 4 sem nenhuma (JEANJACKET, LAJAK, MILK, nikita) e Cupsey#2 sem fita (para às 05:48:06 BRT, R62) |
| fotos | `meme_curve_snapshots` (`solana_rpc` 639 com slot, `pumpfun_rest` 47 sem slot), cadência ~15 s (`q5.sql`, `snaps.csv`) |
| reconstrução | `load.py`: reservas exatas do fill de compra → cada trade da fita soma/subtrai; **cada foto `solana_rpc` com slot ≥ último trade aplicado ressincroniza as reservas** (cura buracos da fita: shitcoin tinha um de 1,5 SOL, Drillers começa 3 min depois da entrada). Nossos próprios trades depois da entrada são ignorados (caminho "segurar", como no R62). Marca = líquido de vender tudo × (1 − 1,25 %). Nas 5 posições só com fotos (`photos`), MFE/MAE são **piso** (15 s) e o `high_water_sol` do executor é reportado ao lado |
| baseline | simulação da regra real sobre a reconstrução (atraso 1,5 s; as 5 sem fita ficam com o resultado real): **−0,0402 SOL vs −0,0404 real** — a reconstrução reproduz o dia |
| apostas de papel | `meme_paper_bets` fechadas com `entry_at ≥ 03:00 UTC`: 294 apostas / 114 mints / 10 conjuntos (`q7.sql`, `bets.csv`) |
| rent | `q8.sql`/`q9.sql`: `intent->>'closes_ata'`, `fill->>'ata_rent_refund_lamports'`, `fill->>'ata_rent_lamports'` |

## 2. Pergunta 1 — as 24, uma a uma (horas BRT; % sobre o gasto; MFE/MAE dentro dos 300 s no caminho "segurar"; `hw` = pico visto pelo executor até a saída)

| # | moeda | entrada | set | saída | PnL % | PnL SOL | s | MFE % (s) | MFE até a saída | hw (db) | MAE % (s) | marca aos 300 s | fonte |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | XCrypto | 02:54:06 | 5 | trailing | −2,4 | −0,0017 | 27 | **+137,9** (281) | +11,9 | +11,9 | −6,7 (99) | **+134,4** | fita |
| 2 | EQUITITTY | 04:03:24 | 5 | trailing | −24,5 | −0,0171 | 15 | −4,6 (0) | −4,6 | −7,1 | −71,2 (299) | −71,2 | fita |
| 3 | FЕРЕ | 05:11:39 | 5 | trailing | −13,7 | −0,0098 | 10 | **+54,5** (234) | −1,6 | −1,6 | −13,7 (11) | **+50,8** | fita |
| 4 | Cupsey#1 | 05:45:44 | 5 | target | +18,3 | +0,0132 | 40 | +65,3 (76) | +13,5 | +20,1 | −35,6 (268) | −35,6 | fita (até 05:48; depois fotos) |
| 5 | Cupsey#2 | 05:48:41 | 5 | trailing | −10,8 | −0,0075 | 28 | +1,0 (11) | +1,0 | +2,2 | −62,2 (193) | −62,2 | fotos |
| 6 | CYBER | 07:57:47 | 5 | target | +26,7 | +0,0060 | 34 | +43,9 (39) | +26,9 | +37,9 | −35,6 (287) | −35,6 | fita |
| 7 | NARKY#1 | 08:21:53 | 5 | trailing | −4,6 | −0,0033 | 31 | **+137,6** (250) | +7,3 | +7,3 | −15,0 (44) | **+64,0** | fita |
| 8 | NARKY#2 | 08:24:53 | 5 | target | +20,3 | +0,0142 | 7 | +22,0 (70) | +19,7 | +20,4 | −39,3 (204) | −20,9 | fita |
| 9 | shitcoin | 10:11:41 | 5 | trailing | −31,1 | −0,0090 | 21 | −7,7 (0) | −7,7 | −16,5 | −52,3 (284) | −52,3 | fita (buraco de 1,5 SOL curado por foto) |
| 10 | KODA#1 | 10:57:04 | 5 | target | +14,3 | +0,0103 | 12 | **+139,3** (257) | +14,1 | +17,0 | −80,2 (290) | −79,0 | fita |
| 11 | KODA#2 | 11:00:10 | 5 | target | +11,6 | +0,0083 | 65 | +16,1 (71) | +12,0 | +15,0 | −90,7 (135) | −90,7 | fita |
| 12 | LAJAK | 14:03:22 | 5 | trailing | −7,7 | −0,0054 | 33 | +0,2 (8) | +0,2 | +3,1 | −46,0 (160) | −46,0 | fotos |
| 13 | ARGUSACT | 14:17:56 | 5 | trailing | −13,3 | −0,0095 | 23 | +8,0 (19) | +8,0 | +8,0 | −83,7 (148) | −83,7 | fita |
| 14 | Musepaid#1 | 14:28:06 | **6** | trailing | −14,9 | −0,0107 | 9 | +9,0 (50) | −3,2 | −3,2 | −83,5 (121) | −83,5 | fita |
| 15 | Musepaid#2 | 14:28:40 | 5 | trailing | −2,5 | −0,0018 | 25 | +10,5 (16) | +10,5 | +10,5 | −83,2 (87) | −83,2 | fita |
| 16 | WIFTIGRINO | 14:41:29 | 5 | target | +16,5 | +0,0118 | 44 | +43,0 (299) | +13,7 | +16,5 | −4,6 (0) | **+39,5** | fita |
| 17 | CHARLI | 15:20:42 | 5 | trailing | −14,9 | −0,0107 | 38 | +4,4 (163) | −4,6 | −4,6 | −23,3 (84) | −10,7 | fita |
| 18 | nikita | 15:25:14 | 5 | trailing | −29,2 | −0,0208 | 8 | −4,6 (0) | −4,6 | −5,7 | −43,3 (105) | −39,1 | fotos |
| 19 | Drillers | 16:52:23 | 5 | creator_dump | +6,2 | +0,0045 | 11 | **+115,0** (271) | −4,6 | +7,5 | −5,7 (1) | **+85,2** | fita (começa 3 min depois; fotos antes) |
| 20 | BASK | 16:55:28 | 5 | trailing | −5,2 | −0,0023 | 36 | +7,2 (32) | +7,2 | +7,2 | −43,9 (104) | −42,5 | fita |
| 21 | NOOP | 17:24:38 | 5 | target | +16,7 | +0,0121 | 63 | +40,2 (126) | +16,8 | +16,8 | −73,3 (132) | −73,2 | fita |
| 22 | GTA | 20:13:48 | 5 | trailing | −10,4 | −0,0075 | 105 | +1,9 (56) | +1,9 | +1,9 | −23,0 (136) | −23,0 | fita |
| 23 | JEANJACKET | 20:33:01 | **6** | target | +24,4 | +0,0148 | 37 | +24,8 (51) | +3,0 | **+34,6** | −24,8 (7) | −8,1 | fotos |
| 24 | MILK | 20:42:38 | 5 | trailing | −25,1 | −0,0183 | 7 | −4,6 (0) | −4,6 | −8,7 | −70,4 (139) | −70,3 | fotos |
| | **total** | | | | | **−0,0404** | med. 28 | | | | med. −43 | **−0,3998** | |

Leitura: a marca de entrada já é **−4,6 %** (rent da ATA 2,1 % + taxa 1,25 % + impacto ~0,2 % + a taxa da venda 1,25 %). "Segurar até os 300 s" daria **−0,40 SOL**: 5 moedas ≥ +30 % (XCrypto, FЕРЕ, NARKY#1, WIFTIGRINO, Drillers), **12 ≤ −40 %, 8 ≤ −70 %**. 12 das 24 tocaram +15 % dentro dos 300 s; 8 foram alvos; das 15 saídas por trailing só 3 (XCrypto, FЕРЕ, NARKY#1) tocaram +15 % depois — as outras 12 tiveram MFE ≤ +10,5 % e 9 delas terminaram ≤ −40 %. Os colapsos são de **um segundo**: NOOP +40 % → −68 % com 11 carteiras vendendo 30 SOL no mesmo bloco (17:26:46); Musepaid, ARGUSACT e KODA drenaram a curva a 30 SOL virtuais (zero real) numa foto de 15 s; EQUITITTY é a cascata do R62.

Tempo até o alvo: 7, 12, 34, 37, 40, 44, 63, 65 s. Nenhum alvo ficou positivo aos 300 s exceto WIFTIGRINO (+39,5 %) — tomar o alvo foi certo em 7 de 8 (KODA#1 chegou a +139 % antes de ir a −79 %, mas o rug foi num bloco).

## 3. Pergunta 2 — grade de saídas nas 24 (`grid.py`; atraso gatilho → pouso 1,5 s; 1,25 % de taxa; saída por evento mantida; as 5 sem fita ficam com o resultado real em todos os braços)

Ranking por soma de PnL SOL (52 braços: trailing {10, 15, 20, 30 %} × armar {entrada, +10 %, +20 %} × alvo {nenhum, 1,15, 1,30, 1,50} + 4 de referência sem trailing):

| # | braço | total SOL | acertos | saídas |
|---|---|---|---|---|
| **1** | **trailing 10 % / entrada / alvo 1,15 (= regra atual)** | **−0,0402** | 9 | trailing 11 · alvo 7 · evento 1 · real 5 |
| 2 | trailing 10 % / entrada / alvo 1,30 | −0,0773 | 8 | Cupsey#1 +0,020 e KODA#1 +0,015 a mais; NARKY#2 −0,008 e **KODA#2 −0,076** (rug antes de 1,30) |
| 3 | trailing 10 % / entrada / alvo 1,50 | −0,1399 | 7 | |
| 4 | trailing 30 % / entrada / alvo 1,15 | −0,1479 | 12 | XCrypto, FЕРЕ, NARKY#1 viram alvos (+0,060), mas Musepaid ×2 −0,104, ARGUSACT −0,035, EQUITITTY −0,009 |
| 5 | trailing 30 % / entrada / alvo 1,30 | −0,1611 | 10 | |
| 6 | trailing 10 % / armar em +10 % / alvo 1,15 | −0,1632 | 10 | sem stop antes de +10 %: EQUITITTY −0,032, ARGUSACT −0,050, Musepaid#1 −0,049 |
| 7 | trailing 15 % / entrada / alvo 1,15 | −0,1758 | 9 | Musepaid ×2 −0,104 (a saída a −2,5/−15 % virou −83 %) |
| 8 | trailing 20 % / entrada / alvo 1,15 | −0,1875 | 10 | |
| 15 | sem trailing / alvo 1,15 | −0,1938 | 12 | |
| 52 | sem trailing / sem alvo (só 300 s) | −0,3341 | 6 | |

Marginais (média dos braços): trailing 10 % −0,221, 15 % −0,289, 20 % −0,288, 30 % −0,231; armar na entrada −0,220, em +10 % −0,280, em +20 % −0,271; alvo 1,15 −0,177, 1,30 −0,211, 1,50 −0,259, nenhum −0,382. **Sensibilidade com 5 s de atraso:** mesma ordem — regra atual −0,0346 (1.º), depois 10 %/1,50 −0,133, 10 %/1,30 −0,134, 30 %/1,15 −0,167, 15 %/1,15 −0,171. Variante extra (`split.py`): vender 50 % no alvo e deixar o resto com trailing 10/20/30/50 % → −0,142/−0,155/−0,162/−0,176; vender 70 % → −0,10 a −0,12. Também perde: o resto fica dentro do bloco do rug (KODA ×2, NOOP).

O que muda em relação ao R62: nas 8 da madrugada o trailing largo ganhava (+0,05 SOL com 30 %) porque XCrypto/FЕРЕ/NARKY#1 subiram depois; nas 24, os mesmos 3 continuam a valer +0,060, mas a tarde trouxe 5 drenagens num bloco onde o stop apertado saiu a −2…−15 % e o largo sai a −83 %. **A largura do trailing não é uma regra de saída — é uma aposta sobre a proporção de rugs no dia.** Hoje a proporção foi 8 em 24 (≤ −70 % aos 300 s).

## 4. Pergunta 3 — por hora, por conjunto, por motivo

| hora BRT | n | alvos | PnL SOL | MFE mediano | segurar 300 s |
|---|---|---|---|---|---|
| 02 | 1 | 0 | −0,0017 | +138 % | +0,096 |
| 04 | 1 | 0 | −0,0171 | −5 % | −0,050 |
| 05 | 3 | 1 | −0,0042 | +55 % | −0,033 |
| 07 | 1 | 1 | +0,0060 | +44 % | −0,008 |
| 08 | 2 | 1 | +0,0109 | +138 % | +0,032 |
| 10 | 2 | 1 | +0,0013 | +139 % | −0,072 |
| 11 | 1 | 1 | +0,0083 | +16 % | −0,065 |
| **02–11** | **11** | **5 (45 %)** | **+0,0033** | **+44 %** | −0,100 (5 a ≤ −40 %) |
| 14 | 5 | 1 | −0,0156 | +9 % | −0,182 |
| 15 | 2 | 0 | −0,0315 | +4 % | −0,036 |
| 16 | 2 | 1 | +0,0022 | +115 % | +0,043 |
| 17 | 1 | 1 | +0,0121 | +40 % | −0,053 |
| 20 | 3 | 1 | −0,0109 | +2 % | −0,073 |
| **14–20** | **13** | **4 (31 %)** | **−0,0438** | **+8 %** | −0,300 (7 a ≤ −40 %) |

Por motivo: **alvo** 8/8, +0,0905 SOL, MFE mediano +43 % (segurar: −0,199 — 6 dos 8 colapsaram depois); **trailing** 0/15, −0,1355, MFE mediano +4,4 % (segurar: −0,262; 3 subiram, 12 morreram); **creator_dump** 1/1, +0,0045 (Drillers: saiu a +6 % aos 11 s e a moeda foi a +115 % — o evento do criador estava errado nesta; segurar daria +0,062).

Por conjunto: `operator/5` 22 op., 8 alvos (36 %), −0,0446 SOL, MFE mediano +16 %; `operator/6` 2 op., 1 alvo, +0,0041, MFE +9 % (Musepaid#1: pico −3,2 % até a saída, depois drenagem a −83 %) e +24,8 % em fotos / **+34,6 % no executor** (JEANJACKET, alvo em 37 s). Com n = 2 não há diferença mensurável de MFE entre ≤ 2 snipers e o resto; Musepaid#1 é exatamente o tipo de moeda que o filtro devia evitar e não evitou.

## 5. Pergunta 4 — recompra do mesmo mint

Musepaid: `operator/6` entrou 14:28:06, trailing a −14,9 % às 14:28:15 (gatilho 14:28:15,4); `operator/5` recomprou às **14:28:40 (25 s depois)**, saiu a −2,5 % às 14:29:05; a curva foi a zero real às 14:29:41. A 2.ª entrada perdeu pouco por sorte de timing, não por tese.

| pausa por mint depois de trailing | nas 24 reais | nas 294 apostas de papel de hoje (todos os conjuntos) |
|---|---|---|
| 5 min | pula NARKY#2 (+0,0142, alvo em 6 s) e Musepaid#2 (−0,0018) → **−0,0124 SOL** | pula **19 entradas: 0 acertos, −0,338 SOL, R médio −0,58** (geral −0,125); só no mesmo conjunto: 4 entradas, −0,081 |
| 15 min | idem | idem (todas as recompras foram em < 5 min) |
| 60 min | idem | idem |
| depois de qualquer saída (alvo/trailing/evento), 5 min | pula Cupsey#2, NARKY#2, KODA#2, Musepaid#2 → −0,0131 SOL | 54 entradas, 9 acertos, −0,476 SOL, R médio −0,28 |

As duas populações discordam por causa de NARKY#2: a mesa real alcançou o alvo em 6 s; os espelhos de papel no mesmo mint (moonshot 08:24:16, operator/5-papel 08:25:04, hype_probe 08:25:16) perderam todos. Nas outras recompras (EQUITITTY, Cupsey, Musepaid, WIFTIGRINO) papel e real perderam. A pausa é uma regra de **entrada** barata e mensurável — EXP-M21.

## 6. O que hoje ensinou

Com 24 operações, 9 alvos e −0,040 SOL, o dia não decide nada sobre esperança de retorno: um alvo a mais ou a menos muda o sinal. O que ele mostra com clareza é **estrutura de custo**: cada operação nasce a −4,6 % e 0,030 dos −0,040 SOL do dia é rent de ATA que ficou estacionado porque a T4.46 está desligada — não é mercado, é operação. Sobre saídas, o dia contradiz a leitura da madrugada (R62): o trailing de 10 % armado na entrada foi o melhor de 52 braços porque a tarde trouxe cinco drenagens num único bloco, e qualquer stop mais largo pousa depois do bloco; "dinheiro na mesa" só existiu em três moedas, todas da madrugada. Onde há lição de mercado é na **entrada**: 12 das 15 saídas por trailing eram moedas que nunca subiram (MFE ≤ +10 %) e 9 morreram; a tarde (14–20 h) teve 31 % de acerto e MFE mediano +8 % contra 45 % e +44 % da manhã. O próximo passo testável é a pausa por mint depois de trailing (0/19 no papel, um alvo perdido no real) — EXP-M21, em papel, 3 dias, sem tocar na mesa; e o passo operacional é ligar `MEME_CLOSE_ATA_ON_FULL_SELL=1` (flag do Everton, primeira venda real é o teste) e fechar as 34 ATAs abertas (0,0514 SOL).

## 7. Ressalvas

- **n = 24** e 5 delas só com fotos de 15 s (MFE/MAE são piso; na grade ficam com o resultado real — JEANJACKET, por exemplo, teria sido −24 % com trailing 10 % nas fotos e foi +24,4 % de verdade porque o executor viu o pico no frame). A reconstrução das 19 com fita reproduz o dia (−0,0402 vs −0,0404), mas 5 moedas fora da grade tiram poder das comparações.
- Fita = `swap_api` por REST com buracos (shitcoin 1,5 SOL, Drillers 3 min, KODA#1 sem a nossa compra); as fotos `solana_rpc` com slot curam os buracos a cada ~15 s, mas entre um buraco e a foto seguinte a marca pode estar errada.
- Contrafactuais ignoram o nosso impacto (0,07 SOL em curvas de 30–100 SOL virtuais) e usam atraso uniforme (1,5 s; 5 s não muda a ordem). Saídas por evento (T4.63) mantidas como no real (Drillers).
- Rent: 1 513 840 lamports por ATA nova (não há ATA nova na 2.ª entrada do mesmo mint); o `payer_delta` das 24 vendas = `sell_net` (nenhum reembolso). O rent está **nas contas**, não perdido: fechar as 34 ATAs devolve 0,0514 SOL.
- Hora do dia: 11 vs 13 operações; não é regra, é o que hoje mostrou.
- Nada foi escrito na VPS; só `SELECT` via `docker exec hunter-postgres-1 psql`.

## 8. Arquivos

`.claude/state/r64/`: `q0–q9.sql` (esquemas, posições, fita, fotos, ordens, apostas, rent), `pos24.csv`, `positions.csv`, `trades.csv`, `snaps.csv`, `orders.csv`, `bets.csv`, `load.py` (reconstrução com ressincronização por foto), `metrics.py` → `metrics.txt`/`metrics.json` (Q1, Q3, Q4), `grid.py` → `grid.txt`/`grid.json` (Q2), `split.py` → `split.txt` (venda parcial). KB: `obsidian/11-KNOWLEDGE/KB-0146-trailing-apertado-e-rent-de-ata.md`; EXP: `obsidian/05-EXPERIMENTS/EXP-M21-pausa-por-mint-apos-trailing.md`.
