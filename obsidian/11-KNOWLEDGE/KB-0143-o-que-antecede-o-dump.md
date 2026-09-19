---
tags: [knowledge, meme, saida, trailing, dump, fita, executor, r62, t4-69, m4]
tema: o que antecede o dump numa curva pump.fun — a venda grande é o gatilho, não o aviso
fonte: .claude/state/notes-R62.md (8 posições reais de 19/09/2026 + 82 entradas de papel com fita)
fonte_url:
lido_em: 2026-09-19
evidencia: medição própria — 8 posições reais reconstruídas trade a trade + população de 82 entradas de papel (24 h) + 3 420 vendas nos primeiros 10 min de 84 moedas
hipotese_testavel: sim
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-19
confiança: "?"
---

# KB-0143 — O que antecede o dump: a venda grande é o gatilho, não o aviso (R62, 19/09/2026)

## O que afirma

Numa curva pump.fun, **uma venda grande isolada (≥ 5 % do SOL real da curva, ou de uma das 10 primeiras carteiras) não antecede a queda — ela é a queda**, e o que vem 60 s depois é moeda ao ar. "Vender na primeira venda grande" não melhora a regra do Everton (alvo +15 %, trailing 10 % armado na entrada, 5 min) nem nas 8 posições reais da madrugada de 19/09 nem em 82 entradas de papel das últimas 24 h. O que precedeu um colapso de verdade (Cupsey) foi a **saída em bloco das carteiras iniciais num único segundo** — sinal de **entrada** (retenção dos snipers, T4.66), não de saída.

## Onde foi mostrado

Mesa real, 19/09/2026 00:00–08:30 BRT, 8 posições (0,07 SOL, `executor:auto_stage1`, saída por evento ligada): XCrypto −2,4 %, EQUITITTY −24,5 %, FЕРЕ −13,7 %, Cupsey#1 +18,3 %, Cupsey#2 −10,8 %, CYBER +26,7 %, NARKY#1 −4,6 %, NARKY#2 +20,3 %; total **−0,0063 SOL**. Fita `meme_trades` (`swap_api`, 48–65 s de atraso — serve para análise, não para regra) reconstruída a partir das reservas exatas do fill de compra; a reconstrução fecha a 0,0015 SOL na saída em 6 de 7 (Cupsey#2 sem fita; Cupsey#1 com lacuna de 0,49 SOL).

**A venda grande e o gatilho são o mesmo instante.** Em XCrypto (897GsV, 15,1 % do `real_sol`), FЕРЕ (carteira inicial n.º 5, 14,8 %, 5 s depois da nossa compra) e NARKY#1 (GvvAxe, 7,5 %) a saída por evento disparou 1,2–1,5 s depois do bloco da venda grande — era ela que cruzava os −10 % do pico. Em EQUITITTY a venda de 8,9 % (04:03:33) veio com **14 vendas idênticas de 0,13 SOL de 14 carteiras no mesmo segundo** (bundle): a 1.ª tentativa (5 %) falhou `6003 TooLittleSolReceived`, a 2.ª pousou 5 s depois a −24,5 %; com pânico (15 %) teria pousado a ≈ −25 % do mesmo jeito. A venda de 5,8 % de 3 s antes teria dado −11,8 % — mas o mesmo limiar de 5 % vende Cupsey#1 a −11 % (fechou +18 %) e CYBER a −4 % (fechou +27 %).

**Grade nas 8** (pouso 2 s depois do bloco da venda): X = 3–4 % → −0,0215 SOL; **X = 5 % → −0,0185**; 6–7 % → −0,0280; 8 % → −0,0068; **≥ 10 % → +0,0006 (nada muda)**; "carteira inicial ≥ 5/10/20 M tokens" → +0,0030/+0,0006/+0,0006. **População** (82 entradas de papel com fita; regra do Everton simulada na fita dá média −0,24 %, acerto 46 %): venda ≥ 5 % −0,80 %; ≥ 8 % −0,91 %; ≥ 10 % −0,35 %; ≥ 12–20 % −0,24 %; soma em 3 s ≥ 15 % +0,04 %; cascata ≥ 4 carteiras em 2 s +0,04 %; inicial ≥ 5/10/20 M −0,39/−0,44/−0,44 %. O p10 (−24,5 %) não se move com nenhuma.

**Condicional (3 420 vendas nos primeiros 10 min, `real_sol ≥ 3`; preço 60 s depois vs 2 s depois):** 2–5 % do `real_sol` P(queda) 51 %; 5–8 % 50 %; 8–12 % 54 %; 12–20 % 54 %; **≥ 20 % 36 % — mediana +9,8 %, média +22 %** (a venda gigante é seguida de repique, porque os compradores a absorvem).

**Cupsey — o precursor que existiu.** Pico 05:47:00 (+66 % do nosso gasto, 36 s depois de vendermos no alvo); **05:47:21: 5 das 10 carteiras iniciais vendem em 10 ordens no mesmo segundo, 4,2 SOL ≈ 19 % do `real_sol`**; a fita gravou isso às 05:48:07; Cupsey#2 comprou às 05:48:41 (33 s depois); `real_sol` 21,5 → 19,2 (−10,7 %) → 7,1 → 1,5 SOL em 3 min (rug). O trailing tirou-nos a −10,8 % — o melhor desfecho possível a partir daquela entrada; a entrada é que não devia ter acontecido.

**Onde ficou o dinheiro nas 8.** Não na execução: gatilho → settle mediana **1,64 s** (0,17 s até simular + 1,36 s de envio/confirmação; 3,6–5,9 s em 2 casos com taxa de prioridade no piso; 6,6 s em EQUITITTY pela falha), slippage mediano **−0,07 %** (−7,4 % em EQUITITTY, +4,1 % em Cupsey#1). Nos alvos: +15 % em 40 s, 33 s e 6 s; deixado na mesa 0,034/0,004/0,001 SOL, e 2 dos 3 estavam negativos 5 min depois. **No trailing de 10 % armado na entrada**: XCrypto (−2 %), NARKY#1 (−5 %) e FЕРЕ (−14 %) chegaram a **+139 %, +139 % e +55 %** dentro dos 5 min. Na mesma fita, trailing 20 % → +0,0105 SOL, 30 % → +0,0498, sem trailing → +0,0291 (baseline simulado +0,0012); na população, 10/15/20/30 %/nenhum dá −0,24/−0,12/+0,01/−0,93/−1,46 % de média com acerto 46→57 % e p10 −24,5 → −46,7 %: a largura muda a forma, não a esperança.

## Como mediríamos aqui

- **Já medido:** fração da venda = `sol_lamports ÷ (virtual_sol_reserves − 30 SOL)` antes do trade; carteira inicial = 10 primeiros compradores desde o nascimento; marca = `quote_sell` líquido (1,25 %). Código em `.claude/state/r62/` (`analyze.py`, `sim.py`, `pop.py`, `cond.py`).
- **Em tempo real** a única fonte com latência de 1–1,5 s é o `logsSubscribe` da curva que o executor já lê (T4.63); a fita REST chega 50–65 s depois.
- Para a **entrada**: `early_retention_pct`, `quick_flip_share_30s`, `new_wallets_30s` da T4.66 (`hunter_indicators.meme.crowd`), ainda não implantados — Cupsey#2 é o caso de teste.

## Hipótese testável no Lab

- **H1 (refutada nesta amostra):** "sair na primeira venda ≥ X % do `real_sol` ou de carteira inicial ≥ Y tokens melhora a esperança da regra do Everton". Nenhum X em 3–20 %, nenhum Y em 5–30 M, nenhuma soma em 3 s nem cascata de N carteiras melhora a média nas 8 ou nas 82. Se a T4.69 for construída mesmo assim: X ≥ 12 %, Y ≥ 20 M (efeito nulo, não negativo).
- **H2 (a propor):** braço de papel com o portão de entrada `min_early_retention_pct ≥ 0,70` + `max_quick_flip_share_30s ≤ 0,20` (T4.66) — alvo: recusar entradas como Cupsey#2 sem perder Cupsey#1/CYBER/NARKY#2; refutação: acerto e R médio iguais ao braço sem o portão em 7 dias.
- **H3 (a propor):** trailing 20 % em vez de 10 % no mesmo braço — alvo: média ≥ +0,5 % com p10 ≥ −30 %; refutação: p10 piora sem ganho de média (o que a população de 82 sugere).

## Por que pode falhar

Oito posições reais (3 alvos em 8) é amostra favorável; a população de papel roda perto de zero e uma regra que não muda a esperança lá pode mudar noutra semana. A fita tem lacunas (Cupsey) e a fração da venda na população vem do `price` (±2 %). Contrafactuais ignoram o nosso impacto (0,2–0,8 %) e assumem pouso 2 s depois do bloco (ordem das regras estável com 1 e 3 s). "Carteira inicial" é a regra dos 10 primeiros compradores (o `create_slot` não chega ao estado — T4.66 §5).

## Segunda opinião (Astra)

Pendente.

## Relacionados

[[KB-0139-saida-por-evento]] · [[KB-0135-a-vantagem-nao-esta-na-saida]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] · [[KB-0118-nao-entrar-depois-da-queda]] · [[KB-0138-explosao-de-compradores-nao-tem-vantagem]] · [[KB-0141-sniper-de-lancamento]] · [[Strategy Backlog]] · EXP-M19 (T4.66, subida com gente atrás)
