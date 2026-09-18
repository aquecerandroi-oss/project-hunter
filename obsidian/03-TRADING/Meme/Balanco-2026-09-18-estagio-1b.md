---
tipo: estudo
tags: [meme, pumpfun, mesa, balanco, estagio-1b, blockhash, t445, criador, papel-vs-real, r56, m4]
data: 2026-09-18
janela_medida: 13:42 BRT 17/09 (liberação do max_trades, meme_gates.json) – 09:02 BRT 18/09; mesa real 17:38 17/09 – 08:38 18/09
medido_em: 2026-09-18 09:02–09:40 BRT (12:02–12:40 UTC, `date -u` conferido)
fonte: banco da VPS (meme_live_positions, meme_live_orders, meme_proposals, meme_tokens, meme_paper_bets, meme_rule_sets, meme_features_15s, meme_features_1m, meme_curve_snapshots, meme_trades, meme_live_kill_switch, meme_ingest_gaps) + código do executor (submit.py, exits.py, chain.py, config.py, creator_flow.py, refusal_cooldown.py) + IDL do programa pump
sql: .claude/state/notes-R56.md (resumo) + scratchpad q0–q14
owner: sexta-feira
tarefa: R56
status: vivo
confianca: alta para os 6 desfechos reais, as 3 falhas de envio e os motivos de recusa (fills e JSON da admissão); média para o destino das moedas recusadas (fotos de 15 s até a série acabar, 3–5 min); baixa para qualquer projeção (6 fills, 1 vitória que só existiu porque uma venda não pousou)
updated: 2026-09-18
---

# Balanço do estágio 1b — 18/09/2026 (R56)

> **Só números.** Detalhe, SQL, linhas de código e caveats em `.claude/state/notes-R56.md`.
> **Relógio:** BRT = UTC−3. As horas das compras no diário de 18/09 ("soly 14:38 … FAMILY 05:39") estão **3 h adiantadas**; as certas (block_time das fills) estão abaixo. A liberação (`max_trades 1000`) foi às **13:42**; a 1.ª compra às **17:38**.

## 1. As 7 compras (6 fills) — e o acumulado

| moeda | fill BRT | progresso: 60 s antes → no fill | SOL real da curva: máx. 90 s antes → no fill | criador | saída | R | SOL |
|---|---|---|---|---|---|---|---|
| soly | 17/09 17:38:38 | 37 % → **2,9 %** (cota da proposta a −20 s dizia 31 %) | **11,4 → 0,65 (−94 %)** | não tinha vendido (cadeia); vendeu a +39 s | creator_dump +86 s | −0,08 | −0,0039 |
| **PS** | 18:00:03 | 68 % → 33 % → **voltou a 49 % a +55 s** | 29,9 → 10,05 (−66 %) | não tinha vendido; **vendeu 100 % a +54 s** | creator_dump, **3.ª tentativa**, +117 s | **+0,66** | **+0,0339** |
| COVER | 19:47:20 | 91 % → **5 %** | **61,9 → 1,7 (−97 %)** | **já tinha vendido 20,1 SOL 52 s antes** — a cadeia recusou a 1.ª ordem, a fita (atrasada 38 s) liberou a 2.ª | creator_dump +45 s | −0,08 | −0,0041 |
| === | 19:48:21 | 39 % → **15 %** (cota a −21 s: 37 %) | 12,2 → 4,1 (−66 %) | não comprou (base 0) | time_stop 30 min | −0,24 | −0,0126 |
| HALFIN | 18/09 03:40:40 | 56 % → 33 % | 21,1 → 10,25 (−51 %) | não tinha vendido; vendeu a +24 s, visto a +31 s | creator_dump +33 s | −0,05 | −0,0026 |
| Punch | 05:18:12 | 86 % → **7 %** | **52,4 → 1,6 (−97 %)** | não comprou (base 0) | time_stop 30 min | −0,06 | −0,0029 |
| FAMILY | 08:38:35 | 47 % → 31 % | 16,05 → 13,1 (−18 %) | não tinha vendido | **compra não pousou** (`blockhash_expired_never_landed`) | — | 0 |

| | compras | vitórias | SOL | R | custos (taxa+rede+rent) |
|---|---|---|---|---|---|
| estágio 1 (R54) | 5 | 0 | −0,0449 | −0,87 | ≈ 0,014 |
| **estágio 1b** | 7 (6 fills) | **1** | **+0,0078** | **+0,15** | **0,0169** (rent da ATA = 0,0091, não devolvido) |
| **acumulado** | 12 (11 fills) | 1 | **−0,0371** | **−0,72** | ≈ 0,031 |

Sem a PS, o 1b é **−0,0261 (−0,51 R)**. Escopo restante **0,152 de 0,72** (3 compras). Carteira lida na última admissão: **0,680 SOL**. Rent parado em 11 ATAs: ≈ 0,0165 SOL (T4.46 continua OFF: `closes_ata: false` nas 6 vendas).

**Entrada depois da queda: 7 de 7** (KB-0118). Em 6 a curva perdeu ≥ 50 % do SOL real nos 90 s antes do fill; em 3, 94–97 %. Duas quedas foram **entre a cota e o fill** (20 s) e a admissão aprovou porque `curve_progress` só olha a janela 2–50 % no instante — não compara com a cota nem com o pico. As duas `time_stop` nunca se recuperaram.

## 2. PS — o que fez a única vitória

Entrou no reset (caiu de 68 % a 33 % e voltou a subir — a célula "queda que já parou" da KB-0118, +0,566 R em n=17), com o retrato de risco **lido na hora** (T4.45-A: `bundled 0,070`, `top10 0,184`) e o criador conferido **na cadeia** (T4.45-B: saldo = inicial). A saída foi `creator_dump` correta (ATA do criador zerou a +54 s; a fita nunca viu essa venda).

| venda | quando | desfecho | líquido esperado |
|---|---|---|---|
| 1 | 18:00:57 | **não pousou** (prioridade 0,000004 SOL, enviada 1 vez, sem reenvio) | 0,0686 (+33 %) |
| 2 | 18:01:54 | **`Custom 6003` = `TooLittleSolReceived`** (slippage 1 % numa curva que caiu 14 % num segundo) | 0,0790 |
| 3 | 18:02:00 | confirmada | **0,0854 (+66 %)** |

**As falhas renderam +0,0168 SOL** (o preço subiu 24 % nesses 63 s); a venda saiu 2,9 % abaixo do pico. Em papel, o `operator/5` saiu da PS às 18:01:13 com **+0,0105**. A vitória real é uma falha com sorte.

## 3. As falhas de envio — diagnóstico e as duas correções mais baratas

3 `blockhash_expired_never_landed` em 30 h (PlanB 17/09 06:08, PS 18:00, FAMILY 18/09 08:38): **2 dos 15 envios do 1b não pousaram (13 %)**, mais 1 morto na simulação (6003). Não é o blockhash (lido ≈ 1 s antes de assinar, `confirmed`, 150 blocos): é **taxa de prioridade de 4 000 lamports (0,000004 SOL; a doutrina permite 0,002 — 500× de folga) + `maxRetries: 0` + nenhum reenvio da mesma tx assinada durante os 30 s de confirmação** — a regra 3 da §9.4 da doutrina ("retentativa reusa o mesmo blockhash") não está implementada.

1. **Reenviar a mesma tx assinada a cada 2 s enquanto o blockhash vale** (`hunter_core/execution/meme/submit.py` `_confirm`, l. 212–228; mesma assinatura ⇒ sem risco de posição dupla). Versão de uma linha: `max_retries=3` na l. 200.
2. **Prioridade dinâmica com teto**: `getRecentPrioritizationFees` (p75) antes de montar a tx (`exits.py:212`, `entries.py:212`), piso 100 000 µL/CU (= 0,00004 SOL, 0,08 % da compra), teto `max_priority_fee_sol 0,002`.

Adicionais: baixar `compute_unit_limit` de 400 000 para o consumo real (a medir); slippage de **saída** maior que 1 % para `creator_dump`.

## 4. T4.45 em produção

| recusa | ordens | moedas | o que era | destino em 10 min (SOL real −50 %) | teria pago |
|---|---|---|---|---|---|
| `creator_flow_unknown` | 77 | 35 | **34 sem base** (`creator_initial_tokens` NULL): moedas vistas primeiro pelo board `trenches_ws` — o PumpPortal **não entregou o frame `create`** (perde ~7 % das criações: 1 909 de 2 125 moedas do board na janela ficam sem base). 1 com base 0. **0 falhas de leitura** | **29 de 35** | 3 (GPILL 4,3×, MEMEFIRM 1,9×, LOTAD 1,3×) |
| `creator_net_seller` | 64 | 28 | **todas pela cadeia**: saldo 0 contra base > 0 (leitura 0,2–0,4 s) | **21 de 28** | 5 (SWARM 1,8×, CoC, TAFFY, FCAT, Jeet) |

**Perda evitada pelos 64:** de −0,11 SOL (saindo no primeiro tique como a mesa faz) a −0,36 (segurando 10 min); com o ritmo real (1 posição por vez) **−0,04 a −0,18 SOL** — a ordem de grandeza do estágio 1 inteiro. O check funciona.

**Dois buracos medidos:** (a) sem base a cadeia **não é consultada** — uma ATA existente com saldo 0 já decide "vendeu" sem base nenhuma; (b) `creator_net_seller` **não está no cooldown determinístico** e a fita (`creator_sold = false` = "não vi venda", com 4–38 s de atraso) **tem precedência sobre a cadeia**: a COVER foi recusada pela cadeia às 19:46:56 e comprada às 19:47:20 (−0,0041). Duas linhas em `creator_flow.py:104` e `refusal_cooldown.py:33`.

## 5. Para decidir a renovação (números, não recomendação)

**O que o 1b mostra em 15 h de mesa:**

| taxa | valor |
|---|---|
| compras / h de mesa | 7 em 15 h (0,47/h); 12 compras em 35 h desde 16/09 21:31 |
| entradas depois de queda ≥ 50 % do SOL real (90 s) | **6 de 7** |
| criador vendeu (antes ou até 60 s depois) | **4 de 7** (COVER antes; PS, HALFIN, soly depois) → `creator_dump` em 4 de 6 fills |
| `time_stop` (30 min sem sair do lugar) | 2 de 6 — as duas com base 0 (dev não comprou) |
| envios que não pousaram | 2 de 15 (13 %) + 1 morto na simulação |
| custo fixo por ida e volta | 0,0027–0,0032 SOL (5,4–6,5 %); rent = 1/3 |
| resultado | +0,0078 SOL, **−0,0261 sem a PS**; acumulado −0,0371 |
| papel `operator/5`, mesmas 7 moedas | **−0,0071**; conjuntos com "progresso subindo" (flow_v2/3, /5, /2): +0,20 / +0,10 / +0,09 em 48–62 apostas |

**O que renovar significa** (mesma porta, mesmo executor): escopo restante 0,152 → **3 compras** de 0,05; ao ritmo de 0,47/h acabam em ~6 h de mesa. Esperança pela taxa medida (11 fills, −0,0034/fill): **≈ −0,010 SOL**; custo fixo garantido 3 × 0,0028 = 0,0084. Com o desenho atual a porta escolhe **a curva que acabou de esvaziar** (7/7) — é a célula de −0,305 R da KB-0118. Renovar o escopo como está compra 3 amostras dessa célula.

**Renovar depois de duas mudanças baratas** (sem deploy a 1.ª; um patch pequeno a 2.ª):

1. **`operator/5`: religar `progress_or_mcap_rising`** (parâmetro, desligado em 16/09 16:15 — KB-0099). Na foto de 15 s mais próxima do fill, `progress_rising` era `f` ou nulo nas **7** — nenhuma entraria. Os três conjuntos de papel que exigem isso foram os três positivos da janela.
2. **Reenvio da mesma tx assinada + prioridade dinâmica** (§3) — o que transforma 13 % de envios perdidos em ~0 e tira a sorte da equação (a PS não se repete).

E as duas de dado, para o T4.45 fechar o buraco (§4): cadeia mesmo sem base; `creator_net_seller` no cooldown e cadeia acima da fita.

## Ligações

[[03-TRADING/Meme/Balanco-2026-09-17-estagio-1]] · [[11-KNOWLEDGE/KB-0118-nao-entrar-depois-da-queda|KB-0118]] · [[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] · [[11-KNOWLEDGE/KB-0117-o-progresso-da-serie-de-15s-esta-atrasado|KB-0117]] · [[06-DECISIONS/2026-09-12-teste-pequeno-meme-real]] · T4.45 (`.claude/state/notes-T4.45.md`) · R54 (`.claude/state/notes-R54.md`) · R56 (`.claude/state/notes-R56.md`)
