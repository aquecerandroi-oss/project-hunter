---
tipo: estudo
tags: [meme, pumpfun, mesa, balanco, estagio-1, saida, papel-vs-real, r54, m4]
data: 2026-09-17
janela_medida: 20:10 BRT 16/09 – 10:10 BRT 17/09 (últimas 14 h); mesa real 21:31 16/09 – 06:29 17/09
medido_em: 2026-09-17 10:10–10:20 BRT (13:10–13:20 UTC, `date -u` conferido)
fonte: banco da VPS (meme_live_positions, meme_live_orders, meme_paper_bets, meme_rule_sets, meme_rule_set_param_history, meme_gate_refusals_by_mint, meme_features_15s, meme_curve_snapshots, meme_trades, meme_live_kill_switch)
sql: .claude/state/notes-R54.md (resumo) + scratchpad q1–q9
owner: sexta-feira
tarefa: R54
status: vivo
confianca: alta para os 5 desfechos reais (fills da cadeia) e para os motivos de recusa gravados; média para as saídas alternativas (marca em baldes de 15 s, séries param 4–9 min após o fechamento); baixa para qualquer projeção (5 trades reais, 45 apostas de papel, uma noite, 3 apostas fazem o lucro)
updated: 2026-09-17
---

# Balanço do estágio 1 — 17/09/2026 (R54)

> **Só números.** Esta página não recomenda mexer na mesa real. Detalhe, SQL e caveats em `.claude/state/notes-R54.md`.
> **Relógio:** medição 10:10–10:20 BRT; BRT = UTC−3. Deploy `43862e67` às 23:41 BRT de 16/09 (02:41Z).

## 1. Os 5 trades reais (estágio 1 completo: 5 compras, 5 perdas)

Carteira: **0,7174 SOL antes da TAXCOIN → ≈ 0,6725 depois da PlanB** (derivado dos fills; a leitura "0,6452" das 06:00:59 era com a DOPEY aberta). Perda realizada: **−0,0449 SOL (−0,87 R)**; perda do dia do kill switch (desde 00:00 BRT): **0,0352**.

| moeda | entrada BRT | prog. cota → 15 s | saída | motivo | R | pico | o que a fita mostra |
|---|---|---|---|---|---|---|---|
| TAXCOIN | 16/09 21:31:28 | 23 % (vinha de **67 %** a −58 s) | +48 s | creator_dump (cadeia 21:32:12) | −0,185 | 0 % | criador vendeu **~10 SOL entre −53 s e −25 s** (antes da compra); `creator_initial_tokens` NULL → porta passou. Depois da saída: 2,2–2,6× o preço de entrada em +4/+5 min |
| Catbyte | 03:08:15 | 14,5 % (vinha de **81,5 %** a −33 s) | +52 s | creator_dump (fita 1 min) | −0,070 | −5 % | criador vendeu **100 % dos tokens iniciais a −23 s**; fold de 15 s só marcou `creator_net_seller` 30 s depois da compra |
| RAMEN | 03:28:29 | 24,5 → 25,1 % | +396 s | trailing 35 % | −0,143 | **+34 % a +328 s** | caiu a 11 % em 40 s, voltou a 43 % aos +330 s, trailing cortou a −14 % |
| DOPEY | 05:59:33 | 35,7 % (vinha de **50,6 %** a −109 s) | +1800 s | time_stop | −0,351 | −5 % | 40 vendas × 19 compras no minuto anterior; cota → fill perdeu 21 %; curva morta a 3,7 % desde +2,5 min |
| PlanB | 06:01:00 | 14 → 12 % | +514 s | creator_dump, tent. 2 (1ª expirou) | −0,118 | **+31 % a +138 s** | criador (o mesmo da RAMEN) comprou 0,99 SOL a +25 s e vendeu **100 %** às 06:08:35 |

Em **4 de 5** a compra veio logo depois de uma queda de progresso; em **2 de 5** o criador já tinha esvaziado antes da compra. As regras de tendência (`progress_rising`, `holders_rising`) foram desligadas no `operator/5` em 16/09 16:14.

### Saída real × alternativas (mesmas 5 entradas; marca líquida sobre as fotos de 15 s; a simulação reproduz o real)

Parâmetros reais: `target_x 3`, `trailing_pct 35` (**desarmado desde a entrada**), `max_hold_s 1800`; o executor real **não tem** `line_break`, `max_loss` nem braço do trailing (só o papel tem).

| regra | total SOL | R | paga em |
|---|---|---|---|
| **real** | **−0,0449** | −0,87 | — |
| alvo +25 % | **−0,0034** | −0,07 | RAMEN +0,014, PlanB +0,014 |
| alvo +30 % | −0,020 (foto 15 s) / ≈ +0,002 (tique 5 s na PlanB) | −0,39 / +0,03 | RAMEN +0,018 (+ PlanB?) |
| trailing 15 % do pico | −0,025 | −0,49 | RAMEN +0,005, PlanB +0,002 |
| trailing 20 % do pico | −0,031 | −0,60 | RAMEN +0,001 |
| só 1ª venda do criador + 30 min | ≤ −0,052 | ≤ −1,0 | ninguém (séries acabam) |
| S4 / EXP-M11 (dd20 só depois de 1,5×) | ≤ −0,046 | ≤ −0,90 | ninguém chegou a 1,5× |
| stop −10 % | −0,041 | −0,79 | DOPEY perde menos |
| saídas **do papel** (`operator/5` em papel nas mesmas 5) | **−0,024** | −0,48 | PlanB +0,228 (line_break a +193 s) |

**Nenhuma saída deixa as 5 no azul.** TAXCOIN, Catbyte e DOPEY nunca ficaram positivas depois da entrada.

## 2. Por que o papel ganhou (flow_v2/2 e /5) e a mesa perdeu (operator/5, flow_v2/6)

Papel na janela: flow_v2/2 **+0,135** (53 apostas, 24 vitórias) · flow_v2/5 **+0,109** (45/20) · flow_v2/3 +0,052 · flow_v2/1 +0,043 · hype_probe +0,018 · moonshot +0,012 · **operator/5 −0,037 (6/1)** · flow_v2/7 −0,053 (7/0) · **flow_v2/6 −0,072 (10/0)**.

O que separa os dois grupos (`meme_rule_sets.params`):

| | flow_v2/2 · /5 | operator/5 · flow_v2/6 · /7 |
|---|---|---|
| snipers | ≤ 10 | **≥ 21** (operator/5 desde 16/09 16:24, KB-0102) |
| progresso máx. | 100 % | **50 %** (operator/5 desde 16/09 15:08) |
| tendência exigida | progresso ↑ e holders ↑/= | **não** (operator/5); parcial (v6/v7) |
| resto | igual: holders ≥ 20, buyers ≥ 10 (v7: 25), sells/buys ≤ 0,6, hold 30 min, idade ≤ 300 s |

Fato medido: **as 45 entradas do flow_v2/5 tinham 0–10 snipers — nenhuma passa o piso 21**; 26 delas tinham progresso > 50 % e é lá que está o lucro (**+0,122 SOL** acima de 50 % × −0,014 abaixo). O `operator/5` viu e recusou por `snipers_below_min` 11 das 20 vencedoras (Ghosty +1,91 com 2 snipers, FLOCK +1,33 com 3, STACK, Gato, MONKES, GAMBLER, FOPSY, bob, lup, STAND) e as outras 9 (MAYOR, 401K, ASPCAT, PAIDSEM, CASHOUT, VIRUS, AltLayer, RINA, Arcane) caíram em **duas** recusas (snipers **e** progresso > 50) — por isso nem aparecem no log. Não é `max_sells_to_buys`, não é o `max_hold`, não é o E2-b (esse só existe em v6/v7). Ao contrário: o que o `operator/5` aceitou (curva caindo, criador já vendido) é o que o flow_v2/5 recusa. Os 7 "snipers ≥ 21" da noite (v6/v7) foram **0 de 7** positivos.

## 3. Papel × real — quanto sobra da vantagem

Ida e volta real (medida nas 5): taxa 1,25 % × 2 + rede + **rent da ATA 0,0015 não devolvido** (flag T4.46 OFF) ≈ **0,0028 SOL/aposta (5,4 %)**. Papel: 1,75 % × 2 = 0,00175 e nada mais — mais pessimista na taxa, cego ao rent. Fill real 19–38 s depois da cota; no flow_v2/5 (curvas subindo) um atraso de 30 s custa **+2,8 % em média** (mediana 0 %, 23/45 pioram, **0,061 SOL** nas 45).

| flow_v2/5 (45 apostas) | SOL |
|---|---|
| papel | **+0,109** |
| com atraso 30 s e taxa real, **ATA fechada** | **≈ +0,07** |
| idem, ATA **não** fechada (hoje) | **≈ 0,00** |
| sem Ghosty, FLOCK e MAYOR | **−0,088** |

## 4. Se a mesa fosse flow_v2/5 hoje — o que teria acontecido

| leitura | apostas | vitórias | PnL |
|---|---|---|---|
| papel inteiro, 20:10 → 10:10 | 45 | 20 | **+0,109** |
| só a janela em que a mesa real operou (21:31 → 06:10) | 27 | 10 | **−0,039** |
| das 08:00 às 09:20 (depois da 5ª compra real) | 4 | 4 | **+0,143** |
| primeiras 5 apostas (o teto do estágio 1) | 5 | 1 | **−0,035** |
| com `max_open 2` (o da mesa) | 45 | 20 | +0,109 (não limita) |
| com cap diário 0,15 **bruto** (só perdas) | 24 | 10 | +0,004 (pararia às 05:05) |
| curva de capital | mínimo acumulado **−0,087**, pior recuo **−0,101** antes de virar | | |

**Risco desta leitura:** (1) 3 apostas fazem o resultado — sem elas, −0,088; (2) uma noite, uma janela de mercado (o R53 já mostrou a madrugada como a pior faixa); (3) papel sem impacto de preço, sem falha de blockhash, sem rent, com 3 regras de saída que o executor real não executa (`line_break` fechou 24 das 45); (4) séries param minutos depois do fechamento — "segurar mais" não é avaliável; (5) a mesa com as **mesmas primeiras 5** teria fechado o estágio 1 em −0,035, quase o mesmo desenho do real.

## Ligações

[[03-TRADING/Meme/Balanco-2026-09-16-mesa-real]] · [[05-EXPERIMENTS/EXP-M11-saida-drawdown-20-apos-1p5x]] · [[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] · [[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] · [[11-KNOWLEDGE/KB-0110-saida-por-drawdown-20-na-serie-de-15s]] · [[11-KNOWLEDGE/KB-0113-ate-onde-as-series-acompanham-uma-aposta]] · R53 (`.claude/state/notes-R53.md`)
