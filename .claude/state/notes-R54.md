# R54 — Balanço do estágio 1 (5 compras reais) × o papel da mesma noite

Medido em **17/09/2026 10:10–10:20 BRT** (13:10–13:20 UTC, `date -u` conferido). Janela "últimas 14 h" = **20:10 BRT 16/09 → 10:10 BRT 17/09**. Banco da VPS (`hunter-postgres-1`), só SELECT. SQL em `scratchpad/q1..q9.sql` (copiados abaixo em resumo). Horários em Brasília (UTC−3).

## 0. Carteira — o número certo

| leitura | valor | fonte |
|---|---|---|
| antes da TAXCOIN (21:31 16/09) | 0,7174 SOL | `admission.checks.wallet_cap` da ordem de compra |
| início do dia do kill switch (00:00 BRT 17/09) | 0,7077 SOL | `meme_live_kill_switch.day_start_sol_equity` |
| leitura "0,6452" (06:00:59) | **com DOPEY aberta** (0,0515 fora) e antes do gasto da PlanB | admission da PlanB |
| depois da PlanB (06:09:34), derivado | **≈ 0,6725 SOL** = 0,7174 − 0,0449 (5 PnL) − ~0,00001 (tx falha INMATE) | derivado, não lido |
| perda do dia (kill switch, desde 00:00 BRT) | **0,0352 SOL** (Catbyte+RAMEN+DOPEY+PlanB); a TAXCOIN é de 16/09 | soma de `pnl_sol` |

Os 5 fechamentos somam **−0,0449 SOL** (−0,867 R). O "0,0625" era delta de leituras com posição aberta, não perda realizada.

## 1. As 5 posições reais — o que aconteceu e qual saída teria pago

Parâmetros reais de saída (`meme_live_positions.params`, iguais nas 5): `target_x 3`, `trailing_pct 35`, `max_hold_s 1800`, `size_sol 0.05`, `decided_by executor:auto_stage1`. Defaults do `hunter_risk_meme` (`limits.py`): `target_multiple 2.0`, `trailing_from_peak_pct 0.30`, `time_stop_s 900` — **não** foram usados (o executor lê `target_x/trailing_pct/max_hold_s` do conjunto, `exits.py:_params`). `docs/RISK_ENGINE_MEME.md` §6 confirma. **O executor real só conhece 4 regras**: `creator_dump` (venda do criador vista na cadeia `creator_sold_seen_at` **ou** `creator_sold` da fita de 1 min), alvo, trailing **desarmado desde a entrada** (`trailing_arm_x` do conjunto é ignorado) e tempo. **Não existe no real** `line_broken`, `max_loss` nem braço do trailing — que existem no papel (`hunter_indicators/meme/exits.py`).

| moeda | entrada | prog. na cota → na entrada (15 s) | saída | motivo | R | pico (marca líq.) | o que a fita mostra |
|---|---|---|---|---|---|---|---|
| TAXCOIN | 16/09 21:31:28 | 23,2 % (vinha de **67 % a −58 s**) | 21:32:16 (+48 s) | creator_dump (cadeia, 21:32:12) | −0,185 | +0 % (entrada) | criador vendeu **6,74 + 1,13 + 0,86 + 1,20 SOL entre −53 s e −25 s**, antes da compra; `creator_initial_tokens` NULL → `creator_behaviour` passou com "1". Depois da saída o preço foi a **2,2–2,6× o de entrada em +4/+5 min** (fita; série acaba em +302 s) |
| Catbyte | 03:08:15 | 14,5 % (vinha de **81,5 % a −33 s**) | 03:09:07 (+52 s) | creator_dump (fita 1 min, atrasada) | −0,070 | −5,0 % (+15 s) | criador vendeu **todos os 44 037 884 tokens iniciais a −23 s** (2,91 SOL); `creator_net_seller` do fold de 15 s só virou `t` em 03:08:45; a admissão passou (`creator_behaviour 1`, `creator_flow` null porque a fita "tinha valor") |
| RAMEN | 03:28:29 | 24,5 → 25,1 % | 03:35:05 (+396 s) | trailing 35 % | −0,143 | **+34,2 % a +328 s (03:33:57)** | caiu a 11 % em 40 s, voltou a 42,8 % aos +330 s, trailing disparou a −14 %; criador só comprou (0,02 SOL ×7). Mesmo criador da PlanB (`BvgE1K…`) |
| DOPEY | 05:59:33 | 35,7 % (vinha de **50,6 % a −109 s**) | 06:29:33 (+1800 s) | time_stop | −0,351 | −5,4 % (+2 s) | 40 vendas × 19 compras no minuto anterior (fluxo −9,5 SOL); a cota (08:59:02Z) → fill (08:59:33Z) já perdeu 21 % (950 k → 1 209 k tokens); curva morta a 3,7 % a partir de +2,5 min |
| PlanB | 06:01:00 | 14,0 → 12,1 % | 06:09:34 (+514 s) | creator_dump tentativa 2 (1ª: `blockhash_expired_never_landed` às 06:08:37) | −0,118 | **+31,2 % (tique 5 s) / +27,5 % (15 s) a +138 s (06:03:18)** | criador comprou 0,99 SOL a +25 s e **vendeu 100 %** às 06:08:35 (`creator_sold_fraction 1.0`); a tentativa 1 teria rendido o mesmo (0,0454) |

Em **4 das 5** a mesa comprou **logo depois de uma queda de progresso** (TAXCOIN 67→23 %, Catbyte 81→14 %, DOPEY 51→36 %, PlanB 20→12 %) — o `operator/5` desligou em 16/09 16:14 `require_progress_rising`, `progress_or_mcap_rising`, `require_holders_rising` (KB-0099). Em **2 das 5** o criador tinha esvaziado a posição **antes** da compra e a porta não viu (baseline NULL na TAXCOIN; fold de 15 s atrasado na Catbyte).

### Saídas alternativas (mesmas 5 entradas; marca = venda total líquida de 1,25 % + 0,000009 SOL sobre `meme_curve_snapshots` em baldes de 15 s; reproduz o real: −0,0452 simulado × −0,0449 real)

| regra | total SOL | R | quem muda |
|---|---|---|---|
| **real** (creator_dump / trailing 35 desarmado / 30 min) | **−0,0449** | −0,87 | — |
| alvo +25 % (resto igual) | **−0,0034** | −0,07 | RAMEN +0,0139 (+247 s), PlanB +0,0142 (+138 s) |
| alvo +30 % | −0,0202 (série 15 s) / **≈ +0,0016** se o tique de 5 s (high_water 0,0676 = +31,2 %) contar na PlanB | −0,39 / +0,03 | RAMEN +0,0176 (+328 s); PlanB depende do tique |
| trailing 15 % do pico (desde a entrada ou armado a +10 %: igual) | −0,0251 | −0,49 | RAMEN +0,0049, PlanB +0,0015 |
| trailing 20 % do pico | −0,0309 | −0,60 | RAMEN +0,0006, PlanB 0,0 |
| só primeira venda do criador (cadeia +10 s) + 30 min | ≤ −0,0515 | ≤ −1,0 | Catbyte/RAMEN sem venda do criador depois da entrada → série acaba (−17 %, −17 %) antes dos 30 min |
| S4 / EXP-M11 (recuo 20 % só depois de 1,5×) | ≤ −0,0464 | ≤ −0,90 | ninguém chegou a 1,5×; RAMEN fica até a série acabar |
| stop −10 % + real | −0,0409 | −0,79 | corta TAXCOIN/RAMEN/DOPEY mais cedo, perde menos na DOPEY (−0,012) |
| conjunto de saída **do papel** (`line_break` 2 fotos, `max_loss 50`, trailing armado a 1,5×) — `operator/5` em papel nas mesmas 5 | **−0,0242** (−0,483 R): TAXCOIN −0,090, Catbyte −0,040, RAMEN −0,240, DOPEY −0,341, **PlanB +0,228** | −0,48 | `meme_paper_bets` do `operator/5` |

**Nenhuma regra de saída deixa as 5 no azul.** A única que chega perto é "alvo +25 %" (2 de 5 pagam), e ela vive de RAMEN e PlanB terem tocado +34 %/+31 % por 15–60 s. As 3 restantes nunca ficaram positivas depois da entrada. O problema destas 5 é a **entrada**, não a saída.

Caveat: as séries (fotos e fita) **param 4–9 min depois do fechamento** (o radar larga a moeda): "segurar mais" não é avaliável para TAXCOIN (+302 s), Catbyte (+234 s), RAMEN (+429 s), PlanB (+540 s).

## 2. Por que flow_v2/2 e /5 ganharam em papel e operator/5 e flow_v2/6 perderam

Papel na janela (14 h): flow_v2/2 **+0,1351** (53 apostas, 24 vitórias), flow_v2/5 **+0,1085** (45/20), flow_v2/3 +0,052 (38/17), flow_v2/1 +0,043 (6/3), hype_probe +0,018, moonshot +0,012; **operator/5 −0,0374 (6/1)**, flow_v2/7 −0,053 (7/0), **flow_v2/6 −0,072 (10/0)**.

### Diff de parâmetros (`meme_rule_sets.params`)

| param | flow_v2/2 | flow_v2/5 | flow_v2/6 (E2-b) | flow_v2/7 | **operator/5** |
|---|---|---|---|---|---|
| `min_snipers` | — | — | **21** | **21** | **21** (16/09 16:24, KB-0102) |
| `max_snipers` | 10 | 10 | 1000 | 1000 | 1000 |
| `max_progress_pct` | 100 | 100 | **50** | **50** | **50** (16/09 15:08, decisão A) |
| `require_progress_rising` / `progress_or_mcap_rising` | true / true | true / true | false / true | false / true | **false / false** |
| `require_holders_rising` / `holders_rising_or_flat` | true / true | true / true | false / true | false / true | **false / false** |
| `pedigree_e2b` / `exclude_mayhem` | — | — | true / true | true / true | — |
| `pedigree_repeat_dumper` | — | true | true | true | true |
| `min_unique_buyers` | 10 | 10 | 10 | **25** | 10 |
| `max_open_positions` / `ttl_s` | 5 / — | 5 / — | 5 / — | 5 / — | **2 / 180** |
| saídas (papel) | line_break, max_loss 50, trailing 35 armado 1,5× | idem | idem | idem | idem **no papel**; no real só 4 regras |

Comum a todos: `min_holders 20`, `min_progress_pct 5`, `max_sells_to_buys 0.6`, `max_hold_s 1800`, `max_age_s 300`, `max_dev_share 0.10`, `require_creator_not_net_seller`.

### As entradas do flow_v2/5 e o que o operator/5 fez com elas

Snipers na foto de entrada das **45** apostas do flow_v2/5: **0 a 10 em todas** (nenhuma ≥ 21). Progresso na entrada: 26 de 45 **acima de 50 %** — e é lá que está o lucro (prog > 50 %: 26 apostas, 12 vitórias, **+0,122 SOL**; prog ≤ 50 %: 19, 8, −0,014). Pelo `meme_gate_refusals_by_mint` (só grava proposta ou quase-proposta com **exatamente uma** recusa — `lab_fast.py` T4.43):

| vencedora flow_v2/5 | entrada | R | snipers | prog. | operator/5 disse |
|---|---|---|---|---|---|
| Ghosty | 08:27 | +1,91 | 2 | 57 % | `snipers_below_min` (2 < 21) — e prog > 50 |
| FLOCK | 03:28 | +1,33 | 3 | 32 % | `snipers_below_min` (3 < 21) |
| MAYOR | 08:06 | +0,68 | 0 | 62 % | sem linha (≥ 2 recusas: snipers **e** progresso) |
| 401K | 04:57 | +0,63 | 9 | 76 % | sem linha (snipers e progresso) |
| ASPCAT | 04:58 | +0,60 | 6 | 70 % | sem linha (snipers e progresso) |
| STACK | 02:21 | +0,60 | 7 | 51 % | `snipers_below_min` (7) |
| PAIDSEM | 09:01 | +0,39 | 8 | 82 % | sem linha (snipers e progresso) |
| CASHOUT | 05:07 | +0,30 | 1 | 66 % | sem linha (snipers e progresso) |
| Gato | 07:30 | +0,28 | 0 | 33 % | `snipers_below_min` (0) |
| BPAD | 20:22 | +0,28 | 7 | 53 % | antes do log (02:41Z) |
| MONKES | 08:50 | +0,24 | 6 | 44 % | `snipers_below_min` (6) |
| VIRUS | 07:42 | +0,17 | 0 | 62 % | sem linha (snipers e progresso) |
| GAMBLER 03:16 +0,14 (5) · AltLayer 04:45 +0,14 (7, 71 %) · FOPSY 09:01 +0,11 (2) · bob 03:11 +0,05 (4) · RINA +0,03 (7, 60 %) · lup +0,03 (1) · Arcane +0,02 (5, 59 %) · STAND +0,02 (6) | | | | | `snipers_below_min` em 6 delas; as outras sem linha |

**Resposta:** é o **piso de snipers 21** (0 de 45 entradas do flow_v2/5 passam; 90 quase-propostas do operator/5 na noite morreram só nele) **e** o **teto de progresso 50 %** (129 recusas `progress_above_max`; 26 das 45 entradas e 8 das 10 maiores vencedoras estão acima). Não é o `max_sells_to_buys` (igual nos dois), não é o `max_hold` (igual) e não é o pedigree E2-b (só flow_v2/6-7; lá o que mais recusa é `e2b_top_buyer_unknown` 75 e `progress_above_max` 70). O operator/5 **não propôs nenhuma** das 20 vencedoras. Ao mesmo tempo, ele **aceitou** o que o flow_v2/5 recusa: curva caindo (sem `progress_rising`), holders caindo, e — pelo buraco do baseline — criador que já vendeu.

flow_v2/6 e /7 (0 vitórias em 17): mesma porta do operator/5 (snipers ≥ 21, prog ≤ 50) mais E2-b; 3 das 5 moedas reais (Catbyte, DOPEY, PlanB) também entraram lá em papel e perderam. Os "snipers ≥ 21" desta noite (BALLSACKDORKL, KABO, Amber, INMATE, MOTIONCAT, SNOZ, Kate) foram todos negativos.

## 3. Papel × real — quanto da vantagem sobrevive

Custos reais medidos nas 5 (`entry`/`exit` JSON): compra 0,05 → programa (0,04938 curva + 0,95 % + 0,30 % criador) + **rent da ATA 0,001514** (não devolvido: `MEME_CLOSE_ATA_ON_FULL_SELL` OFF) + rede 0,000009 = **0,051523 gasto**; venda: bruto × (1 − 1,25 %) − 0,000009. Ida e volta ≈ **0,0028 SOL (5,4 % do tamanho)**. O papel cobra `fee_pct 1.75` nas duas pontas (3,5 %), sem rent, sem rede — **o papel é mais pessimista na taxa (+0,0005/aposta a favor do real) e omite o rent (−0,0015/aposta contra o real)**.

Cota → fill real: 19–38 s; tokens recebidos **acima** da cota em 4 de 5 (+6,1 %, +5,4 %, −0,3 %, **+27,2 %** DOPEY, +9,0 %) — "slippage a favor" que é o sintoma de comprar enquanto o preço cai. Já as entradas do flow_v2/5 são em curva subindo: com o **mesmo atraso de 30 s** a marca dos tokens do papel fica em média **+2,8 % mais cara** (mediana 0,0 %; 23/45 pioram; soma **0,061 SOL** nas 45) — e a piora concentra nas vencedoras. O papel preenche na 1ª foto após a decisão (0–16 s, mediana ~6 s).

| flow_v2/5, 45 apostas | SOL |
|---|---|
| papel como está | **+0,1085** |
| − atraso de 30 s (0,061) + taxa 1,25 % em vez de 1,75 % (+0,0225) | ≈ +0,070 |
| … e rent da ATA não devolvido (−0,0675) | **≈ +0,002 (zero)** |
| … com ATA fechada (T4.46 ON) | **≈ +0,068** |
| sem as 3 maiores (Ghosty +0,095, FLOCK +0,067, MAYOR +0,034) | **−0,0875** |

Mesmo raciocínio no flow_v2/2: +0,135 → ≈ +0,087 (ATA fechada) ou ≈ +0,008 (ATA aberta); sem as 3 maiores −0,061.

## 4. "Se a mesa fosse flow_v2/5 hoje" — ver Obsidian `Balanco-2026-09-17-estagio-1.md` §4.

Números-chave: 45 apostas / 20 vitórias / +0,1085 (papel, 20:10–10:10). Na **janela real da mesa** (21:31 16/09 → 06:10 17/09): **27 apostas, 10 vitórias, −0,039 SOL** (o lucro veio das 08:00–09:20 BRT: 4/4, +0,143 — depois da 5ª compra real). `max_open 2` não limita (45/45). Cap diário 0,15 **líquido** não dispara; **bruto** (só perdas) disparava às 05:05 com 24 apostas e +0,0035. Primeiras 5 apostas do flow_v2/5 (o teto do estágio 1): **1 vitória, −0,035 SOL** — o mesmo desenho da mesa real. Curva de capital: mínimo acumulado −0,087, pior drawdown −0,101 antes de virar. `meme_paper_bets.outcome_quality = measured` em 45/45.

## SQL (resumo; arquivos completos no scratchpad q1–q9)

- q1: `meme_live_positions` ⋈ `meme_tokens` ⋈ `meme_proposals` ⋈ `meme_rule_sets`, `entry_at > now() − 14 h` (params, entry/exit JSON, quote).
- q2: `meme_rule_sets.params` dos 9 conjuntos; `meme_paper_bets` agregadas e listadas por conjunto; `meme_live_orders` das 5; status das propostas `operator/5`.
- q3: `meme_features_15s` (entrada −120 s … saída +60 s); `meme_curve_snapshots` em baldes de 15 s; kill switch; `meme_gate_refusals_by_mint` ±5 min das vencedoras.
- q4: foto de entrada (snipers/holders/progresso) das 45 do flow_v2/5 + recusas; split snipers × progresso; ordens falhas.
- q5: `meme_rule_set_param_history` do operator/5; vendas do criador (`meme_trades.trader = meme_tokens.creator`); apostas de papel do operator/5; carteira nas admissões.
- q6/q7: fotos até +1860 s e fita por minuto (preço) — insumo do `sim.py`; q8/q9: `creator_flow` das admissões, `decision_to_fill_s`, custo de latência (marca a +20…45 s ÷ marca da foto de entrada).

## Caveats

1. Uma noite, 5 trades reais, 45 apostas de papel; o resultado do papel é 3 apostas (Ghosty, FLOCK, MAYOR). Sem elas, todos os conjuntos são negativos.
2. Séries (fotos e fita) param 4–9 min depois do fechamento das reais: alternativas "segurar mais" não avaliáveis.
3. Marca simulada em baldes de 15 s; o executor decide em tiques de 5 s (PlanB +31,2 % no tique × +27,5 % na foto).
4. O log de recusas por moeda grava só proposta ou quase-proposta (1 recusa): moedas com ≥ 2 recusas não aparecem — "sem linha" foi inferido pelos valores da foto (snipers < 21 e prog > 50).
5. Papel: sem impacto de preço além da fórmula da curva, sem falha de blockhash, sem `ttl`, sem cap de 5 trades; e **com** três regras de saída que o executor real não tem.
6. Carteira final (≈ 0,6725) é derivada das fills, não lida na cadeia.
