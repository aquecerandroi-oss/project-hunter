---
tags: [knowledge, meme, custo, rent, ata, gate, entrada, buys-1m, mesa-real, r65, m4]
tema: 87 operações reais em 6 dias — 72 % do prejuízo é custo (e 33 % é rent de ATA parado); das 13 variáveis de decisão testadas nenhuma sobrevive à correção de múltiplas comparações, e `buys_1m` é a única pista
fonte: .claude/state/notes-R65.md (87 posições reais 16–21/09/2026, fita reconstruída + decomposição de custo por ordem)
fonte_url:
lido_em: 2026-09-22
evidencia: medição própria — 87 posições fechadas, 174 ordens confirmadas com fill decomposto ao lamport (86 de 87 reconciliam exato), 22 868 trades de fita, 2 938 fotos de 15 s; bootstrap por cluster de mint e de dia (10 000), permutação (10 000), Benjamini-Hochberg FDR 10 %
hipotese_testavel: sim
astra: revisto — 8 correções aceites, 1 discordância registada (ver §7 do R65)
status: vivo
owner: sexta-feira
updated: 2026-09-22
confiança: "?"
---

# KB-0147 — Custo é o prejuízo; `buys_1m` é a única pista de entrada (R65, 16–21/09/2026)

## O que afirma

1. **Em 87 operações reais (−0,3473 SOL, 0 de 6 dias verdes), 72 % do prejuízo é custo, não escolha de moeda.** O preço tirou apenas **−0,0952 SOL** (bruto da curva, −1,6 % por aposta de 0,07); as taxas e o rent tiraram **−0,2492**: pump.fun −0,0971, criador −0,0307, rede −0,0079 e **rent de ATA −0,1135**. Cada operação nasce a **−4,09 % do tamanho** (pump.fun 1,59 % + criador 0,50 % + rede 0,13 % + rent 1,86 %); **sem o rent, −2,23 %**. Com alvo +15 % isso move o acerto de equilíbrio de ~27 % para ~19 % — a mesa fez 26 % (23 alvos em 87).
2. **O rent de ATA é 32,7 % do prejuízo acumulado e não é perda de mercado — é dinheiro parado.** 75 das 87 compras criaram ATA (1 513 840 lamports cada) e **nenhuma das 87 vendas pediu reembolso** (`intent.closes_ata = false` em todas). Confirma e quantifica o KB-0146 num horizonte 3,6× maior: o que lá eram 0,0514 SOL em 34 contas, aqui são **0,1135 SOL** em 75.
3. **Nenhuma variável de decisão separa os 23 alvos dos 46 trailing de forma que sobreviva a correção de múltiplas comparações.** Testadas 13 (idade, progresso da curva, SOL real, `buys_1m`, `sells_1m`, vendas/compras, compradores únicos, snipers, fluxo líquido em SOL, delta de mcap 60 s, `dev_share`, fluxo por comprador, hora BRT) em terços nas 87 e em mediana nos 69 alvo/trailing, com bootstrap (10 000), permutação (10 000) e Benjamini-Hochberg FDR 10 %. **O p mais baixo é 0,046 contra um limiar BH de 0,0077.** Em particular **snipers (p 0,52) e `dev_share` (p 0,67) — dois filtros em que a mesa confia — não separam nada**, e a "manhã melhor que a tarde" do KB-0146 não se confirmou (p 0,27).
4. **A única pista é `buys_1m` (compras no minuto anterior à decisão), e na direção contrária à intuição: lançamento mais disputado dá pior.** Metade `≤ 25` compras/min: 34 % de alvos, **MFE mediano +28,1 %**; metade `> 25`: 20 % de alvos, MFE mediano +8,2 %. Diferença +0,0057 SOL/operação, IC 95 % por bootstrap de **cluster de mint** [−0,00034, +0,01207], P(dif ≤ 0) = 3,2 %; estável em direção ao tirar um dia de cada vez (+0,0036 a +0,0066). `unique_buyers_1m` e `mcap_delta_60s` contam a mesma história e são quase colineares — é um achado, não três. **O corte foi escolhido olhando para estes dados: crédito zero como estimativa de lucro futuro.**
5. **No horizonte de 300 s com alvo +15 %, o destino alvo-vs-trailing é dominado por segundos de timing, não pelas features de entrada.** Dez mints foram comprados por duas ou três propostas com 19–190 s de diferença; **em 8 desses grupos um lado saiu por alvo e o outro por trailing** — ANT (+0,0185 / −0,0150 com 61 s de diferença), BLEP, Aura (19 s), DVD, TANK, Cupsey, NARKY, Paidichi. O que a entrada pode mover é a *distribuição* (MFE mediano 3,4× maior), não o resultado de cada aposta.
6. **As saídas por trailing continuam a ser moedas que nunca subiram, não saídas prematuras.** MFE mediano dos 46 trailing: **+7,6 %**; dos 23 alvos: +46,7 %. Confirma o KB-0146 com 46 casos em vez de 15 — **não há motivo nestes dados para alargar o trailing.**
7. **`creator_dump` (14 ops, −0,0998 SOL) é cara-ou-coroa com n = 14.** **0 de 14 tinham `creator_net_seller = true` na entrada** e só 2 tinham `dev_share > 0` — o sinal não existia na decisão. Mediana de 52 s entre entrada e gatilho. Em 5 de 14 a moeda subiu forte depois da saída (PS +117 %, Drillers +115 %, RIB +83 %, Catbyte +85 %) e em 6 de 14 continuou a cair. Não mexer.
8. **`operator/6` vs `operator/5` é indistinguível:** −0,00524 vs −0,00357 SOL/operação, p de permutação **0,64** com n = 22 e 65. Os pares no mesmo mint mostram os dois conjuntos a comprar as mesmas moedas e a trocar de destino por segundos.

## Onde foi mostrado

Mesa real de memecoins, 16–21/09/2026, VPS (leitura `SELECT`/`COPY`). `meme_live_positions` com `status='closed'`: **87** (`operator/5` 65, `operator/6` 22); 174 ordens confirmadas + 9 vendas falhadas. Decomposição de custo lida de `meme_live_orders.fill` (`fee`, `creator_fee`, `network_fee_lamports`, `ata_rent_lamports`, `sol_amount`) — **86 das 87 reconciliam ao lamport** contra `pnl_sol`; a exceção é TAXCOIN (a primeira operação de sempre, 16/09), com 2 860 040 lamports em `unexplained_lamports` porque o parser daquela data ainda não separava o rent. Features na decisão lidas de `meme_proposals.reasons`. Fita `meme_trades` reconstruída a partir das reservas exatas do fill com ressincronização por foto `solana_rpc` (método R62/R64); 74 das 87 com fita, **13 só com fotos de 15 s (MFE/MAE são piso)**.

**Atenção:** as 87 **não** correram a mesma regra. 72 com `0,07 SOL / alvo 1,15× / 300 s / trailing 10 %` (só 19, 20 e 21/09; −0,2038 SOL), 12 com `0,05 / 3× / 1800 s / trailing 35 %` (16–18/09), 2 com `1,3× / trailing 20 %`, 1 com `3× / 1800 s`. **A regra atual tem 3 dias, não 6.** Restrita às 72, o corte `buys_1m ≤ 25` dá +0,0353 SOL (37 ops, 3 dias positivos, 3 sem operação) contra −0,1115 com o rent devolvido; o p de permutação sobe para 0,10.

## O que muda para nós

- **P0, operacional:** ligar `MEME_CLOSE_ATA_ON_FULL_SELL=1` e fechar as ATAs abertas. Recupera 0,1135 SOL já gastos e corta 1,86 pp do custo de cada operação futura. Refutação: abandonar se, nas primeiras 20 vendas com `closes_ata = true`, menos de 18 trouxerem `ata_rent_refund_lamports > 0`, ou se a taxa de vendas falhadas passar de 15 % (já há 9 falhas em 96).
- **P1, entrada, em sombra:** recusar `buys_1m` acima do **percentil 50 móvel de 3 dias** (não congelar "25"). 3 dias com braço de controlo em paralelo. Abandonar se o MFE mediano do braço baixo não ficar ≥ 10 pp acima do alto, ou se o PnL líquido médio do braço baixo for negativo em 2 dos 3 dias, ou se produzir < 5 entradas/dia. Desfecho principal é **PnL líquido**; MFE é secundário.
- **Não mexer:** regra de saída (trailing 10 % na entrada + 1,15× + 300 s continua a melhor de 52 braços do KB-0146), tamanho 0,07, `concurrent_positions ≤ 2`, `creator_dump`, escolha entre `operator/5` e `/6`, filtros de snipers e `dev_share`, hora do dia.
- **Para o futuro:** com 26 % de acerto e alvo +15 %, **o custo é o que decide se a mesa empata**. Qualquer proposta de "melhorar a estratégia" que não baixe o custo por operação ou não suba o acerto acima de ~19 % (pós-rent) é conversa.

## Ressalvas

n por balde 29–35; **6 dias de um único regime**; 13 das 87 só com fotos de 15 s; a fita tem buracos e as moedas que morreram mais depressa têm menos fita (sobrevivência); o caminho "segurar" ignora os nossos trades mas ressincroniza com fotos que já contêm a nossa venda, e a ordem intra-slot é por assinatura, não por execução; os contrafactuais filtram posições e reaproveitam o PnL realizado — **não re-simulam saídas**; o corte `buys_1m` foi escolhido nestes dados entre 13 variáveis. A mesa parou 21/09 12:08 BRT por rate-limit de RPC; 22/09 não tem dados.

## Relacionado

`obsidian/11-KNOWLEDGE/KB-0146-trailing-apertado-e-rent-de-ata.md` (o rent e a grade de saídas, n = 24) · `KB-0143` · `.claude/state/notes-R64.md` · `.claude/state/notes-R62.md` · `obsidian/05-EXPERIMENTS/EXP-M21`, `EXP-M22`
