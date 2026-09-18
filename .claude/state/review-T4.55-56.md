# Revisão de risco — T4.55 (`f7fd9d44`) e T4.56 (`ba9f958f`)

Revisor: guardião do risk-engine. Somente leitura; nada editado no código, VPS ou `.env`.
Data: 2026-09-18. Testes dos dois commits rodados localmente: 63 passed
(`test_meme_submit_resend.py`, `test_priority_fee.py`, `test_send_tuning.py`,
`test_creator_precedence.py`, `test_creator_flow.py`).

## 1. Reenvio (T4.55)

- **Mesmos bytes, sem re-assinatura.** `submit.py:141-143` assina uma vez e serializa;
  `submit.py:166` passa exatamente esse `transaction` como `resend`; `confirm.py:85-93`
  só chama `send_transaction(transaction)` — nenhum rebuild, nenhum blockhash novo.
  Assinatura idêntica ⇒ a rede deduplica ⇒ double-fill impossível. `submit.py:108-110`
  ainda faz replay se o journal já tem assinatura (restart nunca assina de novo).
- **Expiração:** `getBlockHeight` (`tx_rpc.py:151-152`) contra `lastValidBlockHeight` de
  `getLatestBlockhash` (`tx_rpc.py:149`) — mesma unidade, ambos `confirmed`. Correto.
- **Teto de 30 s é macio.** `confirm.py:64-66` só confere o prazo depois do
  `getSignatureStatuses`; entre um poll e o próximo há até 3 chamadas HTTP com
  timeout de 15 s cada (`tx_rpc.py:84,91`): pior caso ≈ 30 + 15 + 15 + 1 + 15 ≈ 76 s
  antes de devolver `confirmation_timeout`. Não re-assina, não gasta dinheiro; só
  atrasa o laço (roda em `to_thread`, `entries.py:296`/`exits.py:267`, então saídas
  de outras posições seguem). BAIXO.
- **`confirmation_timeout` → `submitted_unconfirmed` com assinatura** (`submit.py:288-292`);
  `reconcile_once` (30 s, `main.py:104-128`) usa `getSignatureStatuses` com
  `searchTransactionHistory: true` (`tx_rpc.py:180`) — tx que aterrissa aos 31 s é
  encontrada e liquidada. Correto.
- **MÉDIO — corrida status→altura vira `failed` para uma tx que aterrissou.**
  `confirm.py:55` lê o status (None), `confirm.py:68/79` lê a altura *depois*; se a tx
  confirmou no último bloco válido entre as duas chamadas, `height > last_valid` ⇒
  `Settled("failed","blockhash_expired_never_landed")` (`confirm.py:69`) ⇒ `_fail`
  (`submit.py:174`) ⇒ status `failed`, e `unconfirmed_orders` (`repo.py:144`) nunca
  revisita `failed`. Cenário: compra de 0,28 SOL incluída no bloco `last_valid`;
  a carteira fica com os tokens e nenhuma posição/stop; para uma venda, a posição
  continua aberta, o próximo tick tenta vender de novo e cai em
  `reconciliation_mismatch:no_tokens_on_chain`. Reproduzido no scratchpad
  (`test_confirm_race.py`): `outcome: failed blockhash_expired_never_landed` sem
  reconsulta do status. O mesmo ordenamento já existia em `reconcile`
  (`submit.py:216→226`), mas lá a leitura vem 30-60 s depois, quando a confirmação
  já assentou; o laço novo faz essa checagem a cada 2 s exatamente na fronteira.
  **Fix:** em `confirm.py:68-69`, ao ver `height > last_valid`, reconsultar
  `get_signature_statuses` uma vez e só então decidir `failed`; ou devolver
  `unconfirmed:blockhash_expired_unverified` e deixar o `reconcile` (que lê com
  histórico) dar o veredito. Idem em `submit.py:233-234`.

## 2. Priority fee (T4.55)

- **Aritmética do teto:** `cap_micro_lamports` (`priority_fee.py:57-61`) =
  0,002 × 10⁹ × 10⁶ / 400 000 = **5 000 000 µL/CU**, não 5 000 (µL = 10⁻⁶ lamport).
  Piso 100 000 µL/CU × 400 000 CU = 4·10¹⁰ µL = 40 000 lamports = **0,00004 SOL**,
  não 0,04. Executado com os defaults: `floor → 0.00004 SOL`, `p75 2 000 000 → 0.0008`,
  `cap → 0.002`.
- **Quem vence:** `choose_priority_fee` (`priority_fee.py:121-125`) faz
  `min(max(p75, floor), cap)`; com piso mal configurado acima do teto o teto vence
  (`floor>cap -> cap 5000000 0.002`). Pior caso por tx aterrissada = 0,002 SOL =
  0,71 % de 0,28 SOL. Reenvios não somam: mesma assinatura, a tx aterrissa ≤ 1 vez.
- **Check 20** (`checks_wallet.py:84-112`) recebe o valor escolhido
  (`entries.py:183`: `fee.fee_sol(compute_unit_limit)`) e recusa `> max_priority_fee_sol`
  (0,002) ou `> 5 %` da compra. Continua limitando. BAIXO: `MEME_PRIORITY_FEE_MAX_SOL`
  (env) e `limits.max_priority_fee_sol` são dois números; se o env subir, compras são
  recusadas por nome (fecha), mas vendas (sem admissão) pagam até o env.

## 3. Slippage de saída (T4.55)

- Só vendas: `exits.py:213` e `pumpswap_exit.py:121` usam `cfg.send.exit_slippage_bps(reason)`;
  a compra segue `cfg.limits.max_slippage_pct` (`entries.py:217`, 1 %). Nenhum
  caminho de compra lê `send.exit_*`.
- `min_sol_output` sai de `quote_sell(reserves_of(read))` (`build.py:221-229`) com o
  `read` do próprio tick (`exits.py:110`). Fresco.
- `PANIC_EXIT_REASONS = {creator_dump, rug_signal}` (`send_tuning.py:268`) bate com os
  nomes de `hunter_risk_meme/exits.py:70-89`; `sell_now`, `target`, `trailing`,
  `time_stop`, `migrated`, `curve_complete`, `emergency_auto_close` ficam em 5 %.
  Env limitado a (0, 50] (`send_tuning.py:353-356`).

## 4. T4.56

- **`chain_net_sol = ""` (leitura falhou):** `read_creator_flow` devolve `flow=None`
  (`admission_context.py:102-109`); `resolve_creator_flow` (`creator_flow.py:203-210`)
  cai em `tape_sold is False → +1` e o check 10 **passa**. Cenário: COVER de novo +
  timeout de 1,5 s no RPC no mesmo tick ⇒ compra de 0,28 SOL numa moeda que o criador
  já despejou. É exatamente o residual que o autor nomeou; antes da T4.56 a fita
  `false` passava sem nem ler a cadeia, então não é regressão, mas com 0,28 SOL/trade
  vale fechar. **Fix (MÉDIO):** quando `needs_chain_creator_flow(token)` era verdadeiro
  e a leitura falhou, resolver `net_sol=None` (⇒ `creator_flow_unknown`, que **não**
  entra na carência e é retentado no próximo tick), em vez de aceitar o `false` da fita.
- **Memória local ao processo:** restart perde os 30 min; a carência de 120 s em
  Postgres (`refusal_cooldown.py:48`, `creator_net_seller` incluído) cobre o reinício
  curto; depois disso `needs_chain_creator_flow` volta a ser verdadeiro para fita
  `false` (`creator_flow.py:137`) e a ATA vazia recusa de novo. Cobre, salvo o caso
  acima (leitura falha). Bounded: TTL 30 min + 4096 mints (`creator_flow.py:84-93`).
- **RPC extra por admissão:** uma leitura, `asyncio.timeout(risk_read_timeout_s=1.5)`
  (`admission_context.py:98-104`); sem leitura quando já há memória ou fita `true`.
  A thread pode continuar até o timeout httpx de 15 s, mas a decisão não espera. OK.

## 5. Veredito

- **T4.55 (`f7fd9d44`): SAFE_WITH_FIX** — corrigir a corrida status→altura em
  `confirm.py:68-69` (e `submit.py:233-234`) antes de contar com
  `blockhash_expired_never_landed` como final. Teto de fee está correto (0,002 SOL
  máximo, piso 0,00004 SOL); slippage só em vendas.
- **T4.56 (`ba9f958f`): SAFE_TO_DEPLOY** com concern MÉDIO: fechar o caso
  leitura-falha + fita `false` em `creator_flow.py:203-210` / `admission_context.py:143-153`.
