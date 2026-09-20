---
tags: [knowledge, meme, saida, trailing, rug, rent, ata, mesa-real, r64, t4-46, m4]
tema: um dia inteiro da mesa real (24 operações) — o trailing apertado foi o melhor de 52 braços porque os rugs são de um bloco; 75 % do prejuízo do dia é rent de ATA parado
fonte: .claude/state/notes-R64.md (24 posições reais de 19/09/2026 reconstruídas trade a trade + 294 apostas de papel do mesmo dia)
fonte_url:
lido_em: 2026-09-19
evidencia: medição própria — 19 posições com fita (reconstrução fecha a 0,0002 SOL do dia real) + 5 só com fotos de 15 s; grade de 52 regras de saída; contagem de rent nas 39 vendas da mesa
hipotese_testavel: sim
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-19
confiança: "?"
---

# KB-0146 — Trailing apertado e rent de ATA: o que 24 operações reais ensinaram (R64, 19/09/2026)

## O que afirma

1. **Numa curva pump.fun os colapsos são de um bloco.** Em 24 operações reais, 8 moedas estavam ≤ −70 % aos 300 s e 5 posições perderam ≥ 70 % num único segundo/foto (Musepaid ×2, ARGUSACT e KODA drenaram a curva a zero de SOL real; NOOP foi de +40 % a −68 % com 11 carteiras vendendo 30 SOL no mesmo bloco). Um trailing mais largo não "dá espaço para a moeda respirar" — ele pousa depois do bloco. Por isso **o trailing de 10 % armado na entrada + alvo 1,15 foi o melhor de 52 braços** (−0,040 SOL) contra 15/20/30 % (−0,18/−0,19/−0,15), armar depois de +10/+20 % (−0,16/−0,19), alvo 1,30/1,50 (−0,08/−0,14), segurar 300 s (−0,40). Isso contradiz a leitura das 8 da madrugada (KB-0143: trailing 30 % daria +0,05) e mostra que **a largura do trailing é uma aposta sobre a proporção de rugs do dia**, não uma regra de saída.
2. **75 % do prejuízo do dia é rent de ATA parado.** O dia fechou −0,0404 SOL; 0,0303 SOL são as 20 ATAs criadas nas compras (1 513 840 lamports cada) e nunca fechadas: as 24 vendas saíram com `closes_ata = false` porque `MEME_CLOSE_ATA_ON_FULL_SELL` (T4.46) está desligada por padrão. Desde 17/09 são **34 ATAs = 0,0514 SOL** estacionados (recuperáveis fechando as contas). Sem o rent, o dia seria −0,0101 SOL. Cada operação nasce a **−4,6 %** (rent 2,1 % + 1,25 % de taxa na ida + 1,25 % na volta + impacto).
3. **As saídas por trailing de hoje não deixaram dinheiro na mesa.** 12 das 15 tinham MFE ≤ +10,5 % dentro dos 300 s e 9 terminaram ≤ −40 %; só XCrypto, FЕРЕ e NARKY#1 (as três do R62, todas da madrugada) subiram depois (+134/+51/+64 % aos 300 s). Os 8 alvos foram tomados em 7–65 s e 7 dos 8 estavam negativos aos 300 s.
4. **Recompra do mesmo mint depois de uma saída por trailing é má ideia no papel e ambígua no real:** nas 294 apostas de papel do dia, 19 entradas nessa condição deram 0 acertos, −0,338 SOL, R médio −0,58 (geral −0,125); nas 24 reais a pausa de 5/15/60 min tira NARKY#2 (+0,014, alvo em 6 s) e Musepaid#2 (−0,002). Vira EXP-M21.
5. **Manhã ≠ tarde (indício, n = 11/13):** 02–11 h BRT 45 % de acerto, +0,003 SOL, MFE mediano +44 %; 14–20 h 31 %, −0,044 SOL, MFE mediano +8 %, 7 de 13 a ≤ −40 % aos 300 s.

## Onde foi mostrado

Mesa real 19/09/2026, `meme_live_positions` com `entry_at ≥ 03:00 UTC`: 24 posições (`operator/5` 22, `operator/6` 2), 9 alvos (+0,0106 médio), 15 perdas (−0,0090), 1 `creator_dump` (Drillers, +6 % — e a moeda foi a +115 %). Fita `meme_trades` reconstruída a partir das reservas exatas do fill com **ressincronização por foto `solana_rpc`** a cada ~15 s (cura buracos da fita); 5 posições só com fotos (JEANJACKET, LAJAK, MILK, nikita, Cupsey#2) ficam com o resultado real na grade. Baseline simulado −0,0402 vs −0,0404 real. Grade: trailing {10, 15, 20, 30 %} × armar {entrada, +10 %, +20 %} × alvo {nenhum, 1,15, 1,30, 1,50} + sem trailing; atraso 1,5 s (5 s dá a mesma ordem); venda parcial de 50/70 % no alvo também perde (−0,10 a −0,18).

## O que muda para nós

- **Operação, não estratégia:** ligar `MEME_CLOSE_ATA_ON_FULL_SELL=1` (flag do Everton; a primeira venda real com `CloseAccount` é o teste) e fechar as 34 ATAs abertas. É o maior número do dia.
- **Não alargar o trailing nem armá-lo depois** com base nas 8 da madrugada: 24 operações dizem o contrário. A decisão certa só sai de uma população maior; o Lab de papel tem trailing 35 % nos `flow_v2` — comparar por dia, não por amostra.
- **A porta de entrada é onde o dinheiro está:** 12 das 15 saídas por trailing eram moedas que nunca subiram. Retenção dos snipers (T4.66), pausa por mint (EXP-M21) e o horário são hipóteses de entrada.
- `operator/6` (≤ 2 snipers): n = 2, sem diferença mensurável; Musepaid#1 (drenagem a −83 %) passou pelo filtro.

## Ressalvas

n = 24 (um alvo muda o sinal); 5 posições sem fita; fita `swap_api` com buracos (curados por foto, mas a marca entre um buraco e a foto seguinte pode errar); contrafactuais ignoram o nosso impacto e usam atraso uniforme; saídas por evento mantidas como no real; o rent está nas contas, não perdido.

Ligações: [[KB-0143-o-que-antecede-o-dump]] · [[EXP-M21-pausa-por-mint-apos-trailing]] · [[KB-0141-sniper-de-lancamento]] · `.claude/state/notes-R64.md` · `.claude/state/notes-R62.md` · T4.46 (`exit_common.close_ata_on_full_sell`) · T4.66
