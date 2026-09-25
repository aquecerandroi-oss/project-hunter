# R78 — H-018 (recompra após ganho) + H-015 (SOL no slot de criação)

Início: 2026-09-25. Notas incrementais (tentativa anterior travou).

## 0. Plano
- A: H-018 — real (meme_live_positions + meme_proposals.rule_set_id) e papel (meme_paper_bets); mesmo operador / cruzado / ambos; bootstrap por mint 10k, permutação; contrafactual cooldown 300 s por mint após QUALQUER saída nos dois operadores; posições concorrentes op5×op6.
- B: H-015 — só se a população ≥ 150 decisões resolvidas; senão parar na cláusula de dado com contagem e ETA.

## 1. Dados (extraídos 25/09, antes de qualquer desfecho calculado)
- `r78/q_pop.sql` → `r78/cache/pop.csv` (1 645 linhas). Real: 148 posições fechadas (operator/5 112, operator/6 36; 17/09–25/09 14:43Z). Papel: `leg='single'`, rule sets `operator/*`, `flow_v2/*`, `recuo_v1/*` e toda aposta cuja porta é `fluxo_e_holders/*`. Excluídos (não são portas da mesa): absorb_v0 (absorcao_de_venda), refused_probe, hype_probe/moonshot (sonda_de_hype), organic, meme_paper_v0.
- Megawatt presente: op6 alvo 07:37:58Z +0,0160 → op5 entrada 07:38:03Z −0,0519 (recompra **cruzada**).
- Mesa real hoje: check 28 (T4.78) `mint_cooldown_after_loss_s` = 300, **por mint, todas as pistas/operadores**, só `pnl_sol < 0` (`services/meme-executor/hunter_meme_executor/repo_positions.py` `_RECENT_LOSS`; `packages/risk-core/hunter_risk_meme/checks_wallet.py`). Não existe guarda contra posição concorrente no mesmo mint entre operadores.

## 2. Desenho H-018 (congelado antes de calcular desfechos)
- r = pnl_sol ÷ SOL gasto (real: sol_spent_lamports/1e9; papel: entry.sol_spent). Perda ≥ 50 % = r ≤ −0,5.
- "Mesa" (desk) = rule set (`operator/5`, `operator/6`, cada braço de papel).
- Recompra após ganho (escopo S ∈ {mesmo, cruzado, qualquer}): posição q na mesma lane e mint com uma posição p anterior tal que pnl_p > 0 e exit_p ≤ entry_q ≤ exit_p + 300 s; S=mesmo exige rs_p = rs_q, S=cruzado rs_p ≠ rs_q, S=qualquer ambos. **Uma recompra por par (mint, saída anterior)**: para cada p lucrativa, só a primeira q do escopo; q contada uma vez só.
- Entradas com entry_q < exit_p (posição concorrente) **não** são recompra — vão para a seção de concorrência.
- Controle: primeiras entradas — S=mesmo: primeira posição de cada (rs, mint); S=qualquer/cruzado: primeira posição do mint na lane. Mesmo período = toda a janela da lane. Sensibilidade: controle só a partir da 1.ª recompra; controle sem os mints das recompras.
- Primário = S **qualquer** (variável do bloco: qualquer entrada da porta da mesa); linha primária da saída anterior: pnl > 0 (variável); sensibilidade: saída anterior com `exit_reason = target` (população do bloco).
- D = média(r | recompra) − média(r | controle); IC 95 % por bootstrap de mint (10 000; reamostra mints da união, todas as linhas do mint vão junto); p por permutação de rótulo (10 000, linha a linha — ignora o cluster, só descritivo).
- Veredito: n recompras < 20 → limite de dado (não julgar). IC sup > −0,01 → REFUTA. D ≤ −0,05 com IC sup < 0 **e** taxa de perda ≥ 50 % ≥ 2× → CONFIRMA. Senão NÃO CONFIRMA. Real e papel julgados separadamente.
- Contrafactual real: varredura cronológica; q bloqueada se existe posição **executada (não bloqueada)** p no mesmo mint com exit_p ≤ entry_q < exit_p + 300 s (qualquer operador, qualquer resultado). Cada bloqueada nomeada; Δ SOL = −Σ pnl bloqueadas. Parte incremental sobre o check 28 = bloqueadas cuja saída anterior foi ganho.
- Concorrência: pares (p,q) reais mesmo mint, rs diferentes, entry_p ≤ entry_q < exit_p.

### 2b. Emendas da revisão de desenho da Astra (`astra-review-R78-design.md`), aplicadas ANTES de calcular desfechos
1. **Saída imediatamente anterior** (must-fix 1): a saída p que conta é a **última** saída no escopo antes de entry_q (same: da mesma mesa; any/cross: de qualquer mesa). Ganho em t=10, perda em t=100, entrada em t=150 → não é recompra após ganho. q tem de ser a primeira entrada do escopo depois de exit_p.
2. **Mesma decisão de origem não é recompra** (must-fix 2): origem = (mint, `features_end_time` da proposta). Ex.: Megawatt recuo_v1 tem o `features_end_time` da decisão do op5 (07:38:03.411532) → excluído como recompra da sombra. As entradas da mesma origem de p são ignoradas ao procurar "a primeira depois de p".
3. **Primária = saída anterior por alvo E com lucro** (must-fix 3, leitura literal: a variável pede lucro, a população pede alvo). "Qualquer saída lucrativa" vira sensibilidade. (Desvio declarado em relação ao brief, que falava em "profitable exit"; os dois são publicados.)
4. **Contrafactual por dois replays** (must-fix 4): replay "só perda" (check 28, `pnl < 0`) × replay "qualquer saída"; incremento = diferença dos Δ, cada replay com estado próprio. Janela do replay exclusiva em 300 s (como o check 28, que libera quando `left ≤ 0`); a janela da variável é inclusiva (≤ 300 s, texto do bloco).
- Nice-to-have aceito: a sensibilidade "controle sem os mints recomprados" seleciona pelo futuro — fica descritiva, não causal. Contraste = descritivo; a economia do contrafactual é retrospectiva sobre entradas observadas.
- Testes: `r78/test_h018.py` 12 casos sintéticos (Megawatt cruzada; janela 300 s; perda intermediária; mesma origem; alvo × ganho; replays; concorrência; bootstrap).

### 2c. Emenda PÓS-EXECUÇÃO (declarada; não muda o rótulo — ver §3)
Primeira corrida (`r78/h018.txt` v0): 007 e BAGI, citados no brief, **não** saíam como recompra no real. Causa: a regra de origem (emenda 2) usava `features_end_time`, e o op6 do 007/BAGI tem o **mesmo** instante de fita do op5 — as duas propostas nasceram juntas (06:18:25.21 e 14:11:08.10). Trilha em `meme_proposals`: op5 decidido em 19 ms; op6 ficou `proposed` e só foi decidido **06:18:36.73** (11,5 s depois, 1,7 s depois da saída do op5 por alvo) e **14:12:00.84** (52,7 s depois, 1,8 s depois da saída do op5). Mecanismo (código): `services/meme-executor/hunter_meme_executor/auto_approve.py` `plan_auto_approvals` pula a proposta como `mint_busy` enquanto há posição aberta no mint, mas a deixa pendente até `AUTO_APPROVE_MAX_AGE_S = 60` s; no primeiro tick depois da saída ela é aprovada **sem reavaliar a fita** — recompra com dado velho. No real isso é uma compra nova da carteira, admitida depois da saída; a emenda 2 (feita para as sombras de papel) não se aplica. **Correção só na lane real: origem = instante de admissão (`decided_at`)**; papel continua por `features_end_time`. Publicadas as duas versões.

## 3. Resultados H-018 (saída real: `r78/h018.txt`; primeira corrida `r78/h018_v0.txt`; testes `r78/test_h018.py` 12/12)
Unidade r = pnl ÷ SOL gasto. Bootstrap por mint 10 000 (semente 78); p por permutação 10 000 (linha a linha, descritivo).

### 3.1 Real (148 posições, 132 mints, 17/09 00:31Z – 25/09 14:43Z)
| escopo | n recompras | média r | perda ≥ 50 % | controle (1.ª entradas) | D [IC 95 %] | p perm | razão ≥ 50 % | rótulo |
|---|---|---|---|---|---|---|---|---|
| **qualquer (primária)** | **10** (10 mints) | −0,187 | 0,100 | 132, −0,053, 0,053 | **−0,134 [−0,305, +0,003]** | 0,104 | 1,89 | **LIMITE DE DADO (10 < 20)** |
| mesma mesa | 4 | −0,065 | 0 | 142, −0,056 | −0,009 [−0,100, +0,165] | 0,94 | 0 | limite de dado |
| cruzada op5↔op6 | 6 | −0,268 | 0,167 | 132, −0,053 | −0,216 [−0,466, −0,031] | 0,041 | 3,14 | limite de dado |
- Sensibilidade "qualquer saída lucrativa" = idêntica à primária no real (todas as saídas lucrativas anteriores foram por alvo).
- s1 (controle desde a 1.ª recompra): D −0,151 [−0,318, −0,012]; s2 (sem os mints recomprados, descritivo): −0,114 [−0,286, +0,019].
- v0 (origem por `features_end_time`, antes da emenda 2c): n = 8, D −0,127 [−0,343, +0,038] — mesmo rótulo.
- As 10: Cupsey −0,0075, KODA **+0,0083**, ANT −0,0150, Paidichi −0,0094, TANK −0,0011, **Megawatt −0,0519**, CALLS −0,0103, 007 −0,0097, Calcios −0,0095, BAGI −0,0116. **9 de 10 perderam, Σ −0,1178 SOL.** 6 cruzadas (op5↔op6) e 4 na mesma mesa; as cruzadas entram 1–55 s depois do alvo, as da mesma mesa 137–174 s.
- Brief (25/09): CALLS, 007, Calcios, BAGI → Σ segunda entrada −0,0411 SOL ✔ (bate com o "−0,041" do brief).

### 3.2 Papel (1 497 apostas, 788 mints; operator/*, flow_v2/*, recuo_v1, portas fluxo_e_holders; origem = features_end_time)
| linha | n | D [IC 95 %] | razão ≥ 50 % | rótulo |
|---|---|---|---|---|
| **primária (alvo∧lucro), qualquer** | **5** | −0,060 [−0,458, +0,215] | 2,05 | **LIMITE DE DADO** |
| primária, mesma mesa | 6 | −0,078 [−0,439, +0,223] | 1,57 | limite de dado |
| primária, cruzada | 2 | +0,056 | — | limite de dado |
| sensib. lucro qualquer razão, qualquer | 36 (33 mints) | **+0,009 [−0,113, +0,124]**, p 0,91 | 0,57 | cláusula (a) dispara |
| sensib., mesma mesa | 62 (29 mints) | −0,019 [−0,173, +0,117] | 0,61 | (a) dispara |
| sensib., cruzada | 23 | +0,074 [−0,089, +0,220] | 0,44 | (a) dispara |
- Por que o papel quase não tem "alvo": os braços flow_v2/* saem por `line_broken`/`creator_dump` (não têm alvo 1,15×); só operator/*-papel e recuo_v1 saem por alvo.

### 3.3 Contrafactual real — pausa de 300 s por mint após QUALQUER saída, os dois operadores (dois replays)
- PnL realizado −0,4707 SOL (148). Replay "qualquer saída": **16 bloqueadas, Δ +0,0571**. Replay "só perda" (check 28 retroativo): 7 bloqueadas, Δ **−0,0596** (bloquearia NARKY +0,0142, BLEP +0,0039, Aura +0,0114, DVD +0,0204, TANK +0,0125 — 5 de 7 recompras após perda **ganharam** no real, ao contrário do papel do R64).
- **Incremento sobre a regra atual: Δ +0,1167 SOL, 9 bloqueadas a mais, 0 liberadas**: Cupsey −0,0075, KODA **+0,0083** (única vencedora morta), ANT −0,0150, Paidichi −0,0094, Megawatt −0,0519, CALLS −0,0103, 007 −0,0097, Calcios −0,0095, BAGI −0,0116.
- Economia retrospectiva sobre entradas observadas (não estima oportunidades novas); 1 vencedora morta de 9.

### 3.4 Concorrência e fila
- **Real: 0 posições concorrentes op5×op6 no mesmo mint** — estruturalmente impossível (`mint_busy` no auto_approve + `duplicate_position` na admissão).
- Papel (sombras op5/op6, sem essa guarda): 13 pares sobrepostos, Σ primeira −0,1089, Σ segunda −0,1423, total −0,2512 SOL (7 da mesma decisão).
- **Fila `mint_busy` (real): 5 entradas com proposta anterior à saída e admitida depois dela** (11,5–53,8 s velhas; 1,7–48,9 s depois da saída): ANT, 007, BAGI depois de **ganho** (todas perderam, Σ −0,0363); BLEP, Aura depois de perda (ganharam, +0,0153; hoje o check 28 as bloquearia).
- Ritmo: 10 recompras primárias em 8,6 dias (1,16/dia); 5 nos últimos 2 dias. **ETA para 20: ~4 dias (ritmo recente) a ~9 dias (ritmo médio)**, se a mesa real rodar sem mudança.

## 4. H-015 — desenho (congelado antes de resolver slots e de ver desfechos)
- **Dados:** `r78/q_h015_pop.sql` → `r78/cache/h015_pop.csv` (562 apostas fechadas com fita `meme_decision_tapes` na decisão; join `t.mint = p.mint AND t.as_of = p.features_end_time`; `series = meme_event_gate_v1`). Fitas existem desde 24/09 00:59Z (= deploy T4.89b; todas com `creation_bundle`). Nada do histórico do R76 (que terminou em 23/09).
- **População primária (literal "pista meme_event_gate_v1", reais e papel):** todas as portas dessa pista (inclui absorb_v0 — `absorcao_de_venda/1`), uma por mint = a primeira entrada (empate → real). **Sensibilidade:** só portas `fluxo_e_holders/*` (a porta da mesa, população de origem do R76). Contagem (`r78/h015_pop.py`): 395 mints (364 com `create_signature`); porta da mesa 179 (164). `reason`: null 312, `not_covered_from_birth` 51, `coverage_gap` 1; `early_slots` nunca vazio.
- **Variável:** `getTransaction(create_signature)` (Helius, dentro do contêiner `hunter-meme-worker-1`, chave só do env, nunca impressa) → slot real da criação. `sol_no_slot_de_criacao` = `sol_others` da entrada de `early_slots` com esse slot; se o slot não está em `early_slots` e é ≤ o maior slot listado → 0 (nenhuma troca de outra carteira nesse slot desde a assinatura); se é > o maior slot listado → não resolvida. **Resolvida** = slot obtido e `creation_bundle.reason ≠ coverage_gap`. Sensibilidade: só `reason = null`. Publicar a concordância `creation_slot` (inferido, `first_trade_seen`) × slot real.
- **Desfecho:** r = pnl ÷ SOL gasto **registrado** (real realizado; papel gravado). Desvio declarado: o bloco não cita custo nem simulador; o R76 simulou a 2,23 %. Secundário: despejo coordenado = ≥ 10 vendedoras distintas num mesmo slot com `block_time` em [entrada, entrada + 300 s], de `meme_trades`, sem a nossa carteira, como no R76.
- **Tercis por posto**: cortes q1/3 e q2/3; baixo ≤ q1/3, alto > q2/3; empates sempre juntos; tamanhos efetivos publicados; < 20 mints num extremo → sem contraste identificável. **D = média(alto) − média(baixo)**; previsão D ≤ −0,05 com IC 95 % (bootstrap por mint, 10 000) inteiramente < 0 **e** despejo alto ≥ 2× baixo.
- **Cláusulas:** limite de dado se < 150 resolvidas (antes de qualquer contraste). (a) literal "IC sup de D > −0,01" → pela **errata do R76** (mesma redação, mesma leitura, fixada agora): (a) sozinha = NÃO CONFIRMA; REFUTA só se IC inf de D > −0,01 (o intervalo exclui o efeito previsto), ou (b) pico, ou (c). (b) grade de cortes do "alto" nos quantis {0,50, 0,60, 0,667, 0,75, 0,85} (só partições distintas contam): patamar = a previsão (D ≤ −0,05) vale em q2/3 e em ≥ 1 vizinho; pico = vale em q2/3 e em nenhum vizinho; só julgado se a principal confirma. (c) teto "bloquear > q2/3": fração das vencedoras (r > 0) no tercil alto > 30 % → REFUTA.
- **Mesma errata aplicada à H-018** (fixada agora, antes de redigir o veredito): nas linhas de sensibilidade do papel onde "(a) literal dispara" o rótulo passa a NÃO CONFIRMA, salvo IC inf > −0,01. Não muda a primária (limite de dado).

### 4b. Resolução e emendas da Astra (`astra-review-R78-h015-design.md`), ANTES de ver desfechos
- `getTransaction(create_signature)`: **364 de 364 ok** (364 chamadas, 0 × 429, 0 erro; `r78/cache/slots.jsonl`). Resolvidas (`r78/h015_var.txt`): pista inteira 363 (228 slot em `early_slots`, 135 "ausente → 0"; 31 sem `create_signature`, 1 `coverage_gap`); só `reason` null 312; porta da mesa 163. Slot inferido (`first_trade_seen`) = real em 327 de 363; nos 36 restantes o slot inferido é **posterior** ao real e o `creation_bundle.sol` gravado mede o slot errado.
- **Astra must-fix 1 (aceito):** "ausente ≤ maior slot → 0" não prova zero — a assinatura WS abre DEPOIS do frame `create` (`event_gate_subscriptions.subscribe_at_create`; o próprio código diz "the create's own buy never reaches the logs subscription opened after it"), e `early_slots` guarda só compras, até 5 slots. Código confirma: nos 99 zeros com slot inferido = real, a assinatura viu **alguma** troca no slot S (não necessariamente todas); nos 36 com slot inferido > real, a cobertura de S é desconhecida. **Correção:** prova pela chain — `getTransactionsForAddress(mint, asc, signatures, succeeded, 100)` lista as transações do slot real; para cada uma, `getTransaction` dá pagador e Δ SOL. Zero só é zero se não houver outra transação no slot S (fora o create) com pagador ≠ criador que gaste SOL; senão a linha fica **não resolvida** (zero ambíguo). Também publicada a concordância fita × chain nos casos "match" (a fita pode subcontar compras de S anteriores à assinatura).
- **Astra must-fix 2 (aceito):** grade colapsada não vira "pico": sem vizinho de partição distinta → "patamar não avaliável" (impede confirmar, não refuta). Com q1/3 = 0 o baixo = zeros (empates juntos); < 20 num extremo → contraste não identificável.
- Astra "o que faria diferente" (primeira entrada antes de filtrar fechadas): verificado `r78/q_h015_open.sql` — **0 apostas abertas** na pista (papel e real): não ocorre.
- Nice-to-have aceito: composição por porta e lane em cada extremo.

### 4c. Prova de cobertura pela chain (`r78/gtfa_tpl.py`, `r78/cache/cov.jsonl`, `r78/h015_cov.txt`) — ainda sem desfechos
- `getTransactionsForAddress(mint, asc, signatures, succeeded, 100)` + `getTransaction` das transações do slot real: 363 mints; o create listado em 363/363 e sempre no **primeiro** slot listado; no máximo 31 outras transações no slot. 1.ª passada com `maxSupportedTransactionVersion: 0` perdeu 105 transações v1 (71 mints) → refeitas com `1` (Helius total desta etapa: 1 577 + 575 chamadas, 0 × 429).
- Zeros ("ausente → 0"): slot inferido = real → **97 zeros confirmados pela chain, 2 falsos** (compras de outra carteira no slot S antes da assinatura ficar ativa); slot inferido > real → **17 confirmados, 19 falsos**. **21 zeros ambíguos → não resolvidos** (emenda 4b). O `creation_bundle.sol` gravado mede o slot errado nesses 36.
- Casos "match" (228): a chain mostra compra de outra carteira no slot em 228/228 (coerente).
- **Resolvidas (v1): primária 342 · só reason null 309 · porta da mesa 154 · variável da chain 363** (v2 em §5: 344 · 311 · 154 · 363) — todas ≥ 150: a cláusula de dado **não** dispara; contraste corre.
- Classificador de compra na chain (suposição numérica declarada): pagador ≠ criador (`meme_tokens.creator`) e gasto além da taxa > 0,0025 SOL (acima do aluguel de ATA ≈ 0,00204); o valor da chain é aproximado (inclui aluguel/gorjeta). Na sensibilidade "variável da chain" os 21 ambíguos entram com o valor da chain.


## 5. Resultados H-015 — v2 (saída real `r78/h015.txt`; v1 preservada em `r78/h015_v1.txt`; testes `r78/test_h015.py` 9/9)
**v1 → v2 (emenda da Astra no veredito, `astra-review-R78-veredito.md` must-fix 1, aceita):** o classificador v1 (gasto do pagador > 0,0025 SOL) não provava ausência de compra (compra de 0,001 SOL com ATA existente lia 0; gasto sem compra lia compra) e ignorava compra alheia dentro do próprio `create`. **v2 = saldo de token** (`r78/tok_tpl.py`, `r78/h015_tok.py`): todas as transações do slot real, **incluindo o create**, relidas com `pre/postTokenBalances`; compra = dono ≠ curva ≠ criador com Δ token > 0 do mint; SOL = Δ lamports da curva repartido pelos tokens; curva = maior ganho de lamports no create (1.ª versão usava o maior Δ token e errava em 8 mints em que o criador comprou > 50 % da oferta — pego no teste de sanidade, `r78/h015_tok_check.txt`, e corrigido com teste). Helius: 1 578 chamadas, 0 × 429. Resultado: curva certa em 363/363; 0 compras alheias dentro do create; zeros provados **114**, ambíguos **19** (os 2 que o v1 via como compra não tinham Δ token); fita × chain nos 228 "match": **Spearman 0,998, mediana da diferença 0,0000 SOL**, chain > fita + 0,5 SOL em 24 (compras de S antes da assinatura ficar ativa). **Rótulos iguais aos da v1.**

Uma por mint (a primeira entrada), r = pnl ÷ SOL gasto registrado; tercis por posto (empates juntos); bootstrap 10 000 (uma linha por mint = por mint).
| linha | n | cortes q1/3 · q2/3 (SOL) | baixo / alto | r baixo | r alto | **D alto − baixo [IC 95 %]** | perda ≥ 50 % baixo → alto | despejo baixo → alto (Δ [IC]; razão) | vencedoras no alto |
|---|---|---|---|---|---|---|---|---|---|
| **primária** (pista inteira, fita, zeros provados) | 344 | 0 · 4,72 | 116 / 115 | +0,004 | −0,048 | **−0,052 [−0,143, +0,037]** | 1,7 % → 8,7 % | 4,3 % → 10,4 % (+0,061 [+0,000, +0,131]; 2,42×) | **38/104 = 36,5 %** |
| só `reason` null | 311 | 0 · 3,60 | 114 / 104 | +0,003 | −0,076 | −0,080 [−0,178, +0,017] | 1,8 % → 11,5 % | 4,4 % → 12,5 % (+0,081 [+0,008, +0,157]; 2,85×) | 35/97 = 36,1 % |
| porta da mesa | 154 | 0 · 1,68 | 59 / 51 | +0,008 | −0,078 | −0,086 [−0,245, +0,073] | 1,7 % → 11,8 % | 3,4 % → 23,5 % (+0,201 [+0,084, +0,333]; 6,94×) | 18/58 = 31,0 % |
| variável da chain | 363 | 0,009 · 4,80 | 121 / 121 | −0,004 | −0,052 | −0,048 [−0,141, +0,042] | 3,3 % → 9,1 % | 4,1 % → 10,7 % (+0,066 [+0,000, +0,132]; 2,60×) | 41/110 = 37,3 % |
- Grade do "alto" (primária; baixo fixo): q0,50 −0,070 · q0,60 −0,062 · **q2/3 −0,052** · q0,75 −0,068 · q0,85 −0,045 (5 partições distintas).
- Por tercil (primária): vitória 31,9 % · 25,7 % · 33,0 %; média +0,004 · **−0,055** · −0,048 (não monótona: o meio é o pior); perda ≥ 50 % 1,7 % → 7,1 % → 8,7 %; vitória ≥ +50 % 5,2 % → 6,2 % → 1,7 %.
- Composição: o alto tem mais absorb_v0/1 (31 vs 9) e recuo_v1 (19 vs 13); o baixo mais flow_v2/1 (25 vs 5). Reais: 10 baixo / 8 alto.
- Limitação: 71 de 344 mints sem nenhuma venda em `meme_trades` nos 300 s (cópia por polling) — a taxa de despejo é limite inferior.
- Só `reason` null perde 18 dos 19 zeros ambíguos: a reconciliação do `ledger` (1 %) já os marcava `not_covered_from_birth`.

### 5.1 Cláusula a cláusula (primária)
- **Dado:** 344 ≥ 150 → não dispara.
- **(a) literal** (IC sup de D > −0,01): **dispara** (+0,037) → pela errata do R76 sozinha = NÃO CONFIRMA; o intervalo **não** sustenta refutação (IC inf −0,143 < −0,01). (Pela letra original, sem a errata, (a) também daria REFUTA.)
- **(b) pico:** **não acionada** — só se julga quando a principal confirma; a grade pontual é compatível com patamar (D ≤ −0,05 em q0,60 e q0,75).
- **(c) teto do tercil alto mata > 30 % das vencedoras:** **dispara** — 36,5 % (38 de 104); 36,1 / 31,0 / 37,3 % nas sensibilidades (a porta da mesa por 1 pp).
- Previsão: D pontual −0,052 (bate −0,05) mas IC não inteiramente < 0; despejo 2,42× (bate ≥ 2×; IC da diferença toca 0 na primária, > 0 em só-reason-null e na porta da mesa).
- **Rótulo pela regra fixada em §4: REFUTA pela cláusula (c)**, nas quatro linhas.
- Leitura descritiva (redação pedida pela Astra): **nesta amostra**, as taxas de vitória dos extremos foram próximas (31,9 % e 33,0 %); houve mais perdas ≥ 50 % e menos ganhos ≥ 50 % no alto. Por isso o teto do tercil alto leva ~1/3 das vencedoras e (c) dispara. A média inconclusiva não demonstra efeito só nas caudas, e a composição de portas difere entre os extremos. Pista exploratória para coorte nova, não confirmação.

## 6. Vereditos, Astra e contabilidade
### Astra — rodada 2 do veredito (`astra-review-R78-veredito-2.md`)
- Concorda: H-015 = REFUTA por (c); H-018 = LIMITE DE DADO; §5.1 descritiva o bastante.
- Must-fix novo (sem ocorrência demonstrada): saldo líquido não distingue (i) compra + venda integral na mesma tx (falso zero) nem (ii) transferência gratuita (falsa compra). **Checado nos dados** (`r78/h015_tok_edge.txt`), sem chamada nova: (ii) **0 ocorrências** — todo ganho de token de não criador em tx do slot S vem com saída de token da curva; (i) as **20** tx do slot S dos 116 zeros provados foram inspecionadas: 18 não tocam a curva (pré-criação de ATAs, ≈ 0,00204 SOL por conta) e as 2 que tocam têm Δ token 0, Δ lamports 0 da curva e o pagador gasta só a taxa (+5 000 lamports no máximo) — um ida-e-volta pagaria ~1 % de taxa de protocolo em cada perna. **Cenário não ocorre na amostra; rótulos inalterados.** Discordância registrada: ela preferia "validar por instruções/eventos antes de gravar"; a prova por ocorrência cobre os 116 zeros usados, então gravei.

### Vereditos (gravados na Fila)
- **H-018: LIMITE DE DADO** (primária real n = 10, papel n = 5; < 20) — registrar e não julgar; **sem regra de mesa**. Descritivo: real D −0,134 [−0,305, +0,003], 9 de 10 perderam (−0,118 SOL). ETA 4–9 dias para 20 reais.
- **Regra, SE a H-018 confirmar na reabertura (não implementar agora):** estender o check 28 às saídas com ganho — limite novo `mint_cooldown_after_win_s` (env `MEME_MINT_COOLDOWN_AFTER_WIN_S`, 300 s), mesma forma do `mint_cooldown_after_loss_check` (`packages/risk-core/hunter_risk_meme/checks_wallet.py`), leitura por mint em `repo_positions` sem o filtro `pnl_sol < 0` para esse limite; escopo **por mint, todas as pistas, os dois operadores** (como o check 28), avaliado na admissão — o que também barra a aprovação vinda da fila `mint_busy`. Contrafactual retrospectivo: +0,117 SOL, 9 bloqueadas, 1 vencedora morta.
- **Achado fora do veredito (para a mesa/`risk-engine-guardian`):** a fila `mint_busy` do `auto_approve` aprova propostas de até 60 s **sem reler a fita** logo depois da saída do outro operador (ANT 53,8 s, 007 11,5 s, BAGI 52,7 s; as três perderam depois de um alvo).
- **H-015: REFUTA pela cláusula (c)** (36,5 % das vencedoras no tercil alto > 30 %), nas quatro linhas; (a) literal dispara (errata R76 → sozinha NÃO CONFIRMA; sem errata daria REFUTA); (b) não acionada. **Nenhum braço, nenhum parâmetro.**

### Helius (chave só no env do contêiner `hunter-meme-worker-1`, nunca impressa)
`getTransaction(create)` 364 · prova de cobertura 1 577 + 575 (`getTransactionsForAddress` 434 + `getTransaction`) · saldo de token 1 578 + 12 (piloto) + 12 (piloto cov) · **≈ 4 100 chamadas, 0 × 429, 0 erro**.

### Testes
`uv run --project C:/dev/project-hunter pytest .claude/state/r78/test_h018.py .claude/state/r78/test_h015.py -q -p no:cacheprovider` → 21 passed.
