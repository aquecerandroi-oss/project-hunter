# R56 — Balanço do estágio 1b (7 compras desde a liberação do `max_trades`) + falhas de envio + T4.45 em produção

Medido em **18/09/2026 09:02 BRT** (12:02 UTC, `date -u` conferido na VPS). Janela: **13:42 BRT 17/09 → 09:02 BRT 18/09** (`meme_gates.json` mtime 18:42:56 CEST = 16:42:56Z = 13:42 BRT). Banco `hunter-postgres-1`, só SELECT. SQL no scratchpad (`q0…q14.sql`), resumida no fim. Horários em Brasília (UTC−3).

> **Correção de relógio.** O diário de 18/09 e o brief desta tarefa listam as compras como "soly 14:38, PS 15:00, COVER 16:47, === 16:48, HALFIN 00:40, Punch 02:18, FAMILY 05:39". **Estão 3 h adiantados** (é UTC−6). Os `block_time` das fills são 20:38:38Z, 21:00:03Z, 22:47:20Z, 22:48:21Z, 06:40:40Z, 08:18:12Z, 11:38:35Z → **17:38, 18:00, 19:47, 19:48, 03:40, 05:18, 08:38 BRT**. A primeira compra veio **3 h 56 min** depois da liberação, não 56 min. As horas de saída da PS no brief (18:00:04 → 18:02:02) já estavam certas.

## 0. Totais

| | compras | fills | vitórias | SOL líquido | R | custos pagos (taxa+rede+rent) |
|---|---|---|---|---|---|---|
| estágio 1 (16/09 21:31 → 17/09 06:29, R54) | 5 | 5 | 0 | **−0,0449** | −0,87 | ≈ 0,0140 |
| **estágio 1b (17/09 17:38 → 18/09 08:38)** | 7 | 6 | **1** | **+0,0078** | **+0,15** | **0,0169** (taxas 0,0078 + rent 0,0091) |
| acumulado (12 compras, 11 fills) | 12 | 11 | 1 | **−0,0371** | −0,72 | ≈ 0,031 |

`meme_live_positions` fechadas desde sempre: 11, soma `pnl_sol` −0,03716, soma `r_multiple` −0,717 (bate com 5 + 6). Escopo (`admission.small_test` da FAMILY): `trades_done 11`, `used_sol 0,5678`, **restante 0,1522 de 0,72** (3 compras de 0,05). Carteira lida na admissão da FAMILY: **0,68026 SOL** (`wallet_cap`). Kill switch: `ACTIVE`, dia 18/09 aberto com 0,68583.

**Sem a PS o estágio 1b é −0,0261 SOL (−0,51 R).** O estágio 1b inteiro é uma aposta.

## 1. As 7 compras — uma a uma

Parâmetros iguais nas 6 (`params`): `size_sol 0.05`, `target_x 3`, `trailing_pct 35` (desarmado), `max_hold_s 1800`, `decided_by executor:auto_stage1`. Rent da ATA **não devolvido** em nenhuma (`closes_ata: false` nas 6 intenções de venda → `MEME_CLOSE_ATA_ON_FULL_SELL` continua OFF).

| moeda | fill BRT | prog. na cota → na admissão (fill) | real SOL: máx. 90 s antes → no fill | criador vendeu **antes**? | saída | +s | marca máx. | SOL | R | custos |
|---|---|---|---|---|---|---|---|---|---|---|
| soly | 17/09 17:38:38 | 31,4 % (−20 s) → **2,9 %** | **11,4 → 0,65 (−94 %)** | não (cadeia: saldo = 10 M = inicial); a curva foi drenada por terceiros entre a cota e o fill; criador vendeu 0,29 SOL a +39 s; fita `creator_sold=t` a +82 s | creator_dump (fita 1 min) | +86 | −4,4 % | −0,0039 | −0,08 | 0,00275 |
| **PS** | 18:00:03 | 34,0 → 33,4 % (vinha de **67,6 % a −60 s**) | 29,9 → 10,05 (−66 %) | não (cadeia: 34,2 M = inicial); **vendeu 100 % a +54 s** (`creator_sold_seen_at` 18:00:57, fração 1,0) | creator_dump, **3.ª tentativa** | +117 | **+70,8 %** | **+0,0339** | **+0,66** | 0,00323 |
| COVER | 19:47:20 | 5,3 → 5,2 % (vinha de **91 % a −57 s**) | **61,9 → 1,7 (−97 %)** | **SIM: vendeu 200 M tokens = 20,1 SOL às 19:46:28** (52 s antes). Ordem anterior às 19:46:56 **recusada** `creator_net_seller` pela cadeia; 23 s depois a fita de 1 min dizia `creator_sold = f` (a venda entrou na fita com 37,7 s de atraso) → cadeia não consultada → admitida | creator_dump (fita, 15 s) | +45 | −5,3 % | −0,0041 | −0,08 | 0,00275 |
| === | 19:48:21 | 36,6 % (−21 s) → **15,2 %** | 12,2 → 4,1 (−66 %) | base 0 (criador não comprou) → sem leitura; fita `f` | time_stop | +1804 | −7,1 % | −0,0126 | −0,24 | 0,00264 |
| HALFIN | 18/09 03:40:40 | 34,0 → 33,2 % (vinha de **55,9 % a −53 s**) | 21,1 → 10,25 (−51 %) | não (cadeia: 24,1 M = inicial); **vendeu 0,99 SOL a +24 s**, visto na cadeia a +31 s, venda enviada a +33 s | creator_dump (cadeia) | +33 | +4,6 % | −0,0026 | −0,05 | 0,00277 |
| Punch | 05:18:12 | 7,1 → 7,0 % (vinha de **86 % a −49 s**) | **52,4 → 1,6 (−97 %)** | base 0 → sem leitura; fita `f` | time_stop | +1804 | −4,2 % | −0,0029 | −0,06 | 0,00274 |
| FAMILY | 08:38:35 (**não pousou**) | 31,5 % (vinha de 47 % a −76 s) | 16,05 → 13,1 (−18 %) | não (cadeia: 67 M = inicial) | — | — | — | 0 (rede não cobra tx que não pousa) | — | 0 |

**Entrada depois da queda (KB-0118 / R54): 7 de 7.** Em **6 de 7** a curva tinha perdido **≥ 50 % do SOL real nos 90 s anteriores ao fill**; em 3 (soly, COVER, Punch) perdeu **94–97 %**. Duas quedas aconteceram **entre a cota da proposta e o fill** (soly 31 → 2,9 % em 20 s; === 37 → 15 % em 21 s) e a admissão aprovou porque o check `curve_progress` só olha a janela 2–50 % no instante da leitura — não compara com a cota nem com o pico recente. Nas outras (COVER, Punch) o radar propôs uma moeda já esvaziada porque a fita de 60 s ainda mostrava os compradores de antes da queda. É exatamente a célula "queda > 50 % e fresca (≤ 60 s)" que a KB-0118 mediu como a única claramente ruim (**−0,305 R** em 73 apostas). As duas `time_stop` (===, Punch) nunca se recuperaram: real SOL máximo depois do fill 3,0 e 1,9 contra 4,1 e 1,6 na entrada.

Custos por ida e volta (fills): taxa 0,95 % + criador 0,30 % em cada perna + 0,000009 rede ×2 + **rent 0,0015 da ATA** = **0,0027–0,0032 SOL (5,4–6,5 % do tamanho)**. O rent é **um terço do custo** e está parado em 11 ATAs (≈ 0,0165 SOL recuperáveis fechando-as).

Papel × real nas mesmas 7 (`operator/5` em papel entrou nas **mesmas 7 moedas**, 5–24 s depois): papel **−0,0071 SOL (2 vitórias: PS +0,0105, HALFIN +0,0051)** × real +0,0078. A diferença é a PS: o papel saiu no `creator_dump` da fita às 18:01:13 (+0,0105); o real só conseguiu vender às 18:02:00 depois de duas falhas — e o preço subiu nesse minuto.

## 2. PS — por que ganhou, e o que as duas vendas falhadas custaram

**Entrada.** Proposta 17:59:57, cota 33,96 % (real SOL 10,05), fill 18:00:03 (6 s), 1 000 453 M tokens contra 984 797 M na cota (+1,6 %, o preço caiu entre a cota e o fill). Admissão: 25 checks, todos `passed`; **`creator_flow` lido da cadeia sob demanda** (`source: chain_ata_vs_initial`, saldo 34 199 203 = inicial, `net_sol +1`, 0,3 s); `bundled_share 0,070` e `top10 0,184` **com valor** (o retrato de risco existiu no instante da decisão — T4.45 parte A funcionando; `risk_read` não deixou marca própria no JSON, só os valores). Progresso vinha de 67,6 % a −60 s (a moeda tinha acabado de perder 2/3 do SOL real) e **voltou a subir**: 36,7 % a +6 s, 49,5 % a +55 s, 61 % a +177 s — com 83 compras × 81 vendas no minuto (fluxo −23 SOL a +6 s, +7,5 a +55 s). É o caso "queda que já parou" (KB-0118 §3, +0,566 R em n=17) — não é o mesmo desenho de soly/COVER/Punch.

**Criador.** Comprou 0,99 SOL na criação (34,2 M tokens). A leitura da ATA a +54 s (18:00:57) devolveu **saldo 0** → `creator_sold_fraction 1.0` → `creator_dump`. A fita (`meme_trades`) **não tem** a venda do criador (só a compra às 17:58:55): ou vendeu por outra rota ou transferiu os tokens — a cadeia decidiu certo mesmo assim.

**As três vendas** (`meme_live_orders`):

| tent. | recebida | simulada | enviada | desfecho | `min_sol_output` (líquido esperado) | preço no instante (µSOL/token) |
|---|---|---|---|---|---|---|
| 1 | 18:00:57,47 | 18:00:57,73 | ≈ 18:00:58 (`submitted_at` 18:01:27 é o retorno após 30 s de `confirm_timeout`) | **`blockhash_expired_never_landed`** (reconciliação 18:01:49: altura > `last_valid_block_height` 425 933 416) | 67,96 M (líq. 68,64 M = **+33 %**) | 69,6 |
| 2 | 18:01:54,34 | 18:01:54,48 | **não enviada** | **`onchain_error Custom 6003` na simulação** = `TooLittleSolReceived` ("slippage: Too little SOL received to sell the given amount of tokens", IDL do programa pump) — no segundo 18:01:54 a fita mostra 5 vendas seguidas (1,12 + 0,49 + 0,19 + 0,17 + 0,21 SOL) e o preço foi de 86,7 para 74,4 (−14 %) contra `max_slippage_bps 100` | 78,99 M | 86,5 → 74,4 |
| 3 | 18:02:00,71 | 18:02:00,90 | 18:02:02,22 | **confirmada** (slot 447 892 345, block_time 18:02:00) | 84,60 M | 86,5 |

Fill final: bruto 86,54 M, taxas 1,08 M, **líquido 85,44 M** (+0,0339). **As duas falhas não custaram: renderam.** Entre a decisão (18:00:57, líquido esperado 68,64 M) e o fill (18:02:00, 85,44 M) o preço subiu 24 % — **+0,0168 SOL** a favor. Pico da posição (`high_water_sol` 0,0880 às 18:01:44, preço 88,9): a venda ficou **2,9 % abaixo do pico**. Ou seja: a PS ganhou **porque** a primeira venda não pousou. Nada disso é repetível.

**Latência das 6 compras que pousaram** (recebida → liquidada): 1,5–2,3 s. As vendas confirmadas: 1,5–2,5 s. O caminho normal está rápido; o problema é o caso em que a tx não entra no bloco.

### 2.1 `blockhash_expired_never_landed` ×3 em 30 h — diagnóstico

Falhas de envio nas últimas 48 h (`meme_live_orders.status='failed'`): INMATE compra 17/09 04:15 (`Custom 6002`, slippage na compra), **PlanB venda 17/09 06:08 (`blockhash_expired`)**, **PS venda 17/09 18:00 (`blockhash_expired`)**, PS venda 18:01 (`6003`), **FAMILY compra 18/09 08:38 (`blockhash_expired`)**. Nos 15 envios do estágio 1b, **2 nunca pousaram (13 %)** e 1 morreu na simulação (20 % de tentativas perdidas).

O que o código faz hoje:

| ponto | arquivo:linha | valor |
|---|---|---|
| blockhash lido | `services/meme-executor/hunter_meme_executor/exits.py:200` (`ctx.chain.blockhash`) → `chain.py:143` `get_latest_blockhash(commitment="confirmed")` | **≈ 1 s antes** de assinar — não é "cedo demais" |
| `last_valid_block_height` | o que o RPC devolve (150 blocos ≈ 60 s) — gravado na ordem | não é "apertado demais" |
| priority fee | `config.py:81-82` `compute_unit_limit 400_000` × `compute_unit_price_micro_lamports 10_000` (`MEME_COMPUTE_UNIT_PRICE_MICRO_LAMPORTS`) → `config.py:146` = **4 000 lamports = 0,000004 SOL** (é o `fee_caps.value` de todas as admissões) | teto da doutrina `max_priority_fee_sol 0,002` → **500× de folga não usada** |
| envio | `packages/core/hunter_core/execution/meme/submit.py:200` `send_transaction(transaction, max_retries=0)` → `tx_rpc.py:224-229` `skipPreflight false`, `preflightCommitment confirmed`, **`maxRetries: 0`** | o nó RPC encaminha **uma vez** ao líder e nunca reenvia |
| confirmação | `submit.py:212-228` `_confirm`: só `getSignatureStatuses` a cada `poll_interval_s` por `confirm_timeout_s 30` (`config.py:80`); **não reenvia** a mesma tx assinada | a doutrina §9.4 regra 3 ("retentativa reusa o mesmo blockhash: mesma assinatura, a rede deduplica") **não está implementada** — a "retentativa" só existe depois de expirar (`exits.py:281` `BACKOFF_S`, blockhash novo, tentativa nova) |
| reconciliação | `submit.py:269-281`: sem status **e** altura > `last_valid` → `blockhash_expired_never_landed` | correto; só chega 50–60 s depois |

**Diagnóstico:** não é o blockhash — é **uma tx com 0,000004 SOL de prioridade, enviada uma única vez, que ninguém reenvia**. Nos três casos a rede estava exatamente no momento de disputa (PS: ~5 SOL/s de compras e vendas na mesma curva; FAMILY: 42 compras/23 vendas no minuto). Uma tx de prioridade mínima que o líder do slot descarta some sem erro — é o `never_landed`.

**Correções (mais barata primeiro):**

1. **Reenviar a mesma tx assinada enquanto o blockhash vale** — `submit.py:_confirm` (linhas 212–228): a cada poll (2 s) chamar de novo `self._rpc.send_transaction(transaction, max_retries=0)` com os **mesmos bytes** (mesma assinatura → idempotente, é a regra 3 da §9.4; `skipPreflight: true` no reenvio para não gastar 400 ms de simulação). Exige passar `transaction` para `_confirm` (hoje só recebe `pid, signature`). Zero risco de posição dupla: a assinatura é a mesma. Alternativa de uma linha: `max_retries=3` em `submit.py:200` (o nó reenvia por conta própria) — menos controle, mas sem mudar a máquina de estados.
2. **Prioridade dinâmica com teto** — antes do `build_sell`/`build_buy` (`exits.py:212`, `entries.py:212`): `getRecentPrioritizationFees([programa pump, bonding_curve do mint])`, usar o p75 dos últimos slots, com piso 10 000 e **teto = `max_priority_fee_sol` 0,002 / CU limit** (= 5 000 000 µL/CU com 400k). Só com o piso ×10 (100 000 µL/CU) a taxa vai a 0,00004 SOL — 0,08 % do tamanho, irrelevante contra os 5,4 % de custo fixo.
3. **Baixar `compute_unit_limit`** para o consumo real (buy_v2/sell_v2 gastam ~40–70 k CU; o `400_000` vem da doc oficial, `RISK_ENGINE_MEME.md` §9.2 item 5): com 120 k CU o mesmo lamport de prioridade compra 3,3× mais posição na fila. Precisa medir `computeUnitsConsumed` nas fills antes (não está no JSON de fill hoje).
4. Para vendas de saída (`creator_dump`): **slippage de saída maior** que 1 % (a venda 2 da PS morreu por 6003 com −14 % num segundo) — `max_slippage_pct` é um só para compra e venda (`cfg.limits.max_slippage_pct`, `exits.py:211`); uma venda de emergência a 1 % de tolerância numa curva que derrete é uma venda que não acontece.

## 3. T4.45 em produção: `creator_flow_unknown` 77 e `creator_net_seller` 64

Recusas de compra na janela (`meme_live_orders.status='refused'`): `creator_flow_unknown` **77**, `creator_net_seller` **64** (o brief dizia 63; entrou mais uma às 09:01), `progress_above_window` 40, `progress_below_window` 14, `top10_share_unknown` 7, `top10_share_above_cap` 4, `bundled_share_above_cap` 1, `marks_incomplete` 1. Propostas do `operator/5`: 208 `rejected`, 10 `expired`, 7 `filled`.

### 3.1 Os 77 `creator_flow_unknown` (35 moedas) — não foi falha de leitura: **a base nunca existiu**

| causa | ordens | moedas |
|---|---|---|
| `creator_initial_tokens` **NULL** e **nenhum** `creator_flow` no JSON (a leitura da cadeia não foi tentada — `creator_flow.py:104-107` `needs_chain_creator_flow` exige base > 0) | **76** | 34 |
| base **0** (dev não comprou) — idem, nada a derivar | 1 | 1 |
| `read_failed` (timeout/erro RPC) | **0** | 0 |

**Por que a base é NULL:** as 34 moedas têm `first_seen_source = 'trenches_ws'` (o board do site, 1–2 s depois da criação) — e a base só vem do frame `create` do PumpPortal (`normalize.py:165`). O upsert é `COALESCE(existente, novo)` (`repo_token_sql.py:85`), então se o frame do PumpPortal chegasse depois ele preencheria; **não chega**. Na janela: moedas vistas primeiro pelo `trenches_ws` **2 125** → **1 909 sem base** (90 %); vistas primeiro pelo PumpPortal 25 163 → 1 sem base. **1 494 das 1 911 sem base terminam em `pump`** (são moedas normais do pump.fun). Ou seja: o `subscribeNewToken` do PumpPortal **perde ~7 % das criações**, e são exatamente as que o board pega — e nessas o T4.45-B fica cego por desenho ("sem base nada é derivado"). Não é moeda anterior ao deploy: as 35 foram criadas entre 13:56 e 06:31 BRT.

Destino das 35 (fotos da curva, 10 min depois da 1.ª recusa): **29 perderam ≥ 50 % do SOL real** (a definição do R39), 23 estavam a < 0,7× o preço, **3** valiam ≥ 1,1× (GPILL 4,3×, MEMEFIRM 1,86×, LOTAD 1,27×), 9 tocaram ≥ 1,3× em algum momento. Uma compra de 0,05 em cada uma, segurada 10 min: **−0,48 SOL** (3 vitórias). A recusa por silêncio foi, na média, uma recusa boa — mas por sorte, não por juízo.

**Correção barata (dado):** com base NULL, ler a ATA do criador mesmo assim: `existe e saldo 0` ⇒ vendeu tudo (`−1`); `não existe` ⇒ nunca comprou ou vendeu e fechou — só este caso fica `unknown`. Uma linha em `needs_chain_creator_flow` + um ramo em `creator_flow_from_chain` (`creator_flow.py:110`). Melhor ainda: gravar a base a partir da **primeira leitura da ATA** quando a moeda tem < 10 s (o board vê com 1–2 s) — `boards.py:267` já constrói o `TokenRow` desse instante.

### 3.2 Os 64 `creator_net_seller` (28 moedas) — o check funcionou

Todas as 64 têm `creator_flow.source = chain_ata_vs_initial`, `net_sol −1`, **saldo 0** contra base > 0 (59 com a ATA ainda existindo, 5 com a ATA já fechada). Nenhuma veio da fita. Tempo da leitura: 0,2–0,4 s.

Destino das 28: **21 perderam ≥ 50 % do SOL real em 10 min** (75 %); 13 estavam a < 0,7× do preço no fim; **5 valiam ≥ 1,1×** (SWARM 1,83×, TAFFY 1,25×, CoC 1,27×, FCAT 1,21×, Jeet 1,15×); 10 tocaram ≥ 1,3× em algum momento (série mediana 276 s — os picos são curtos). **Estimativa da perda evitada:** 0,05 em cada uma das 28, saída como a mesa realmente faz nessas (creator_dump no primeiro tique, como soly/COVER: ≈ −0,004 cada) → **≈ −0,11 SOL**; segurando 10 min → **−0,36 SOL** (5 vitórias, 23 perdas). Com o ritmo real (1 posição por vez, cooldown, 2 h de janela morta) a mesa teria feito 10–15 delas: **−0,04 a −0,18 SOL evitados** — da ordem do que o estágio 1 inteiro perdeu.

**O buraco que a COVER mostrou:** a recusa `creator_net_seller` **não está** em `DETERMINISTIC_REFUSALS` (`refusal_cooldown.py:33-42`), então a mesa re-propôs a mesma moeda 23 s depois; a fita já tinha `creator_sold = false` (só quer dizer "nenhuma venda vista na janela" — a venda de 20 SOL entrou 37,7 s atrasada) e, como a fita tem precedência sobre a cadeia (`admission_context.py:16-19`, `creator_flow.py:104`), a cadeia não foi consultada. **Correção barata (2 linhas):** (a) `creator_net_seller` entra no cooldown determinístico (um criador que vendeu ≥ 98 % não "desvende"); (b) `needs_chain_creator_flow` também lê a cadeia quando `creator_sold is False` — 1 RPC de 0,3 s. Teria evitado a COVER (−0,0041) e o soly não (lá o criador ainda tinha tudo).

## 4. Laboratório de papel na mesma janela (13:42 → 09:02)

`meme_paper_bets`, `leg` ≠ runner, `entry_at` na janela:

| conjunto | apostas | vitórias | SOL | R soma | R médio | melhor | pior |
|---|---|---|---|---|---|---|---|
| **flow_v2/3** | 48 | 23 | **+0,2025** | +4,05 | +0,086 | +0,0704 | −0,0406 |
| flow_v2/5 | 51 | 22 | +0,1026 | +2,05 | +0,041 | +0,0704 | −0,0430 |
| flow_v2/2 | 62 | 27 | +0,0881 | +1,76 | +0,029 | +0,0704 | −0,0430 |
| flow_v2/6 | 10 | 3 | +0,0460 | +0,92 | +0,092 | +0,0670 | −0,0194 |
| flow_v2/7 | 8 | 2 | +0,0237 | +0,47 | +0,059 | +0,0670 | −0,0194 |
| hype_probe_v0/2 | 7 | 1 | −0,0043 | −0,43 | | | |
| **operator/5** | **7** | **2** | **−0,0071** | **−0,14** | −0,020 | +0,0105 | −0,0081 |
| flow_v2/8 (novo) | 25 | 8 | −0,0161 | −0,32 | −0,013 | +0,0670 | −0,0341 |
| moonshot_v0/1 e /2 | 9 | 1 | −0,0413 | −2,06 | | | |
| flow_v2/1 | 5 | 1 | −0,0972 | −1,94 | | | |

**O `operator/5` em papel entrou nas mesmas 7 moedas da mesa real** (soly, PS, COVER, ===, HALFIN, Punch, FAMILY — 5 a 24 s depois de cada fill): mesma porta, mesmas entradas, **−0,0071 em papel × +0,0078 real**. A diferença inteira é a PS (papel +0,0105 saindo às 18:01:13 pela fita; real +0,0339 saindo às 18:02:00 por acidente). Na FAMILY o papel perdeu −0,0081 (creator_dump a +4 min 40 s) — a compra real que não pousou **poupou 0,008**. Os conjuntos que exigem progresso subindo (flow_v2/2, /3, /5) continuam positivos; os que **não** exigem (operator/5, moonshot, flow_v2/1) continuam negativos. Mesmo desenho do R54.

## 5. Material de decisão — ver `obsidian/03-TRADING/Meme/Balanco-2026-09-18-estagio-1b.md` §5.

## SQL (scratchpad)

- `q0` esquema; `q1` `meme_live_positions ⋈ meme_tokens ⋈ meme_proposals ⋈ meme_rule_sets`, `entry_at ≥ 2026-09-17 16:42Z`; `q2` `meme_rule_set_param_history` 48 h + soma histórica; `q3` `meme_live_orders` da janela (status/reason/attempt/intent/fill); `q4/q5` `admission` JSON das 7 compras (`creator_flow`, `small_test`, checks); `q6` recusas `creator_flow_unknown`/`creator_net_seller` ⋈ `meme_tokens.creator_initial_tokens` ⋈ `admission->'creator_flow'`; `q7` `first_seen_source` × base; `q8` base por hora e `meme_ingest_gaps`; `q9` destino das 63 moedas em `meme_curve_snapshots` (preço = `virtual_sol/virtual_token`, real SOL mín., +10/+30 min) e vendas do criador em `meme_trades`; `q10` `meme_features_15s` −150…+90 s das 7; `q11` `meme_features_1m` (creator_sold), fotos da PS 20:59:40–21:03Z, fita da PS 21:00:40–21:02:10Z; `q12` `meme_paper_bets` por conjunto e as do `operator/5`; ordens falhas 48 h; kill switch; `q13` COVER: vendas do criador, ordens, fold de 1 min; `q14` real SOL máx./mín. 90 s antes e máx. 30 min depois das 7.
- Erro `6003`: `packages/exchange-adapters/tests/fixtures/pumpfun/idl_pump_onchain_raw.json` (`TooLittleSolReceived`).

## Caveats

1. 6 fills, 1 vitória que depende de duas falhas de envio; 7 apostas de papel do `operator/5`. Nenhuma taxa aqui é estimável com IC.
2. "Destino" das moedas recusadas = fotos de 15 s até onde a série vai (mediana 209–276 s; o radar larga a moeda); "+10 min" é a última foto ≤ 10 min. Preço em curvas de progresso baixo subestima a morte (a curva só pode cair até o preço inicial) — por isso a métrica principal é o SOL real.
3. `meme_trades` não tem todas as vendas de criador (PS: nenhuma; COVER: com 37,7 s de atraso); a cadeia (`creator_sold_seen_at`, `creator_flow`) é a fonte que decidiu.
4. A perda evitada pelos 64 `creator_net_seller` supõe que a mesa teria comprado e saído como nas reais; o ritmo real (1 aberta por vez) limita a 10–15 apostas.
5. O CU consumido não está gravado nas fills — a correção 3 da §2.1 precisa de medição antes.
6. Diário de 18/09 e o brief têm as horas das compras 3 h adiantadas (§0).
