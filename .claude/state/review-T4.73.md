# Revisão de risco — T4.73 (commit `8fc9dcbe`, troca spot genérica pela Jupiter, chave real)

**Veredito: BLOQUEIO para `--apply`** (achados 1, 2 e 3); **dry-run liberado** (não assina, não
simula, não envia). Com 1–4 corrigidos e re-revisados: APROVADO COM RESSALVAS. Somente leitura;
nada editado no código, nenhum `.env` lido, nenhum comando git de escrita. Revisor: guardião do
motor de risco, 2026-09-19.

Lido: `git show 8fc9dcbe --stat`, `spot_verify.py`, `meme_spot_swap{,_rules,_plan,_send,_db,_kill}.py`,
os 4 arquivos de teste, `0056` + `ddl/meme_spot_swaps.py`, fixture `quote_sol_to_wif_real.json`,
`signer.py`, `chain.py:145`, `tx_rpc.py:197-250`, `treasury_send.py` (comparação),
`treasury_rules.classify_submitted`, `.claude/state/review-T4.54.md`, `.claude/state/notes-T4.73.md`,
`docs/RISK_ENGINE_MEME.md` §16.4.

Nota de honestidade: o achado 1 faz a perna de **compra** do `--apply` ser sempre recusada, então
hoje **nenhum SOL sai** por este script — o bloqueio é porque (a) o round trip não roda, (b) a
correção mexe no caminho que assina, e (c) a perna de venda tem o invariante vazio abaixo de 0,01 SOL.

## Achados

### 1. `infra/scripts/meme_spot_swap_send.py:108-135` — ALTA — o "invariante pós-simulação" não lê a simulação

`sol_before`/`sol_after` são **duas leituras ao vivo** de `chain.wallet(wallet).lamports` (linhas 108
e 116, nada mudou entre elas) e `token_after=other_before` é literalmente o valor anterior (linhas 121
e 130). `simulation.accounts` (que `tx_rpc.py:233` devolve e `treasury_send.py:178` lê via
`simulated_balances`) é **descartado**; só `simulation.ok` é olhado. Reprodução com os valores que
`run_apply_leg` passa (fixture real: 0,02 SOL → `otherAmountThreshold` 10 402 273):
```
uv run python <scratch>/adv_spot_send.py
buy  0.02 SOL, threshold 10402273 -> simulation_token_short      # compra SEMPRE recusada
sell back, min_sol_out 19_900_000 -> simulation_sol_short        # venda > 0,01 SOL recusada
sell back, min_sol_out  9_000_000 -> None                        # venda ≤ 0,01 SOL: invariante VAZIO
```
Cenário: Everton roda o round trip de 0,02 SOL → `buy leg: refused filled=0`, linha `refused
simulation_token_short`, nada acontece. Alguém "corrige" removendo o check ou trocando o sinal →
assina sem invariante nenhum. E qualquer venda cujo mínimo seja ≤ 0,01 SOL passa hoje sem conferir
nada. `docs/RISK_ENGINE_MEME.md:1730-1731` afirma o contrário ("simula com `accounts=[…]` e aplica o
mesmo invariante da tesouraria").
Correção: ler `simulation.accounts[0]["lamports"]` e `accounts[1]["data"]["parsed"]["info"]["tokenAmount"]["amount"]`
(como `treasury_send.simulated_balances`) e passar esses como `sol_after`/`token_after`; recusar
`simulation_accounts_unreadable` se vierem `None`; teste com fake de RPC cobrindo aceito e recusado.

### 2. `infra/scripts/meme_spot_swap_send.py:144-158` — ALTA — confirmação que estoura vira `confirmed`

O laço faz 20 × 1 s; se sair com `verdict == "pending"` (RPC lenta, tx ainda não vista), a linha 151
só trata `"failed"` → cai em `mark_confirmed` com `filled = 0` (linha 154, ATA ainda sem saldo) e
`--round-trip` chama a venda com `amount_atoms=0` (`meme_spot_swap.py:192`) → `GET /quote` com
`amount=0` → exceção HTTP → (achado 3) rollback. Cenário: tx pousa aos 25 s (blockhash vale ~60 s):
banco diz `confirmed`/`sol_out_filled = 0`, a moeda fica na carteira sem ficha, e o traceback é o
único registro. Correção: `pending` após o laço → deixar a linha em `submitted`, imprimir a
assinatura, retornar `("submitted", 0)` e **nunca** disparar a perna de volta; reconciliar manualmente.

### 3. `infra/scripts/meme_spot_swap.py:147` — MÉDIA — uma única transação de banco envolve assinar, enviar e confirmar as duas pernas

`async with engine.connect() as conn, conn.begin():` abrange `insert_row`/`mark_submitted`/
`mark_confirmed` das duas pernas e até 2 × 20 s de espera. Qualquer exceção depois de
`send_transaction` (linha 142 de `_send.py`; `get_signature_statuses` com erro HTTP, Jupiter 4xx na
cotação de volta, Ctrl-C) desfaz **todas** as linhas: swap na cadeia, zero linhas em
`meme_treasury_swaps`, assinatura só no stdout. `treasury_send` grava por passo. Correção: conexão em
autocommit (ou `await conn.commit()` logo após cada `mark_*`), e o `try/except` em volta da
confirmação registrando `mark_failed`/`submitted` antes de propagar.

### 4. `infra/scripts/meme_spot_swap_rules.py:85-88` — MÉDIA — `--i-know` remove o teto por completo; não há teto absoluto

`classify_amount_cap` devolve `None` para qualquer valor com `i_know=True`; nada em `_apply` confere
saldo/piso da carteira. Cenário: `--from SOL --amount 0.7 --i-know --apply` (erro de digitação em
"0.07") assina uma compra de 0,7 dos 0,76 SOL — o verificador aceita porque `in_amount` bate com o
pedido. Correção: teto absoluto que `--i-know` não levanta (sugiro 0,10 SOL-equivalente,
`amount_above_hard_cap`), e recusar se `wallet_sol − amount − 0,01 < MEME_WALLET_SOL_FLOOR`.

### 5. `infra/scripts/meme_spot_swap.py:181-195` — BAIXA — perna de volta sem teto de impacto e sem reler o interruptor

A venda usa `run_apply_leg` direto, sem `build_plan` → `classify_impact_cap` não roda; com `--hold-s`
longo o kill switch lido na linha 148 fica velho. É saída (sempre permitida pela doutrina) e a perda
está limitada ao que a compra pagou (≤ 0,05), por isso BAIXA. Correção: rodar
`classify_impact_cap(quote.price_impact_pct)` dentro de `run_apply_leg` para a venda também e logar
o estado do interruptor antes da segunda perna.

### 6. `services/meme-executor/hunter_meme_executor/spot_verify.py:153-157` — BAIXA — `Create ATA` com mint via lookup table pula a checagem de endereço

`if mint is not None and …`: se o índice do mint (pos. 3) ou da ATA (pos. 1) estiver atrás de ALT,
`_key` devolve `None` e o `ata_address_mismatch` não roda. Limite real: o programa ATA deriva o
endereço on-chain e o dono é a carteira (linha 146), então o pior caso é a carteira pagar ~0,002 SOL
de aluguel por uma ATA de um mint arbitrário, ≤ `MAX_ATA_CREATES` vezes. Correção: recusar
`ata_account_via_lookup_table` quando `mint is None` ou `_key(message, ix, 1) is None`, como `_route`
faz nas linhas 268-270.

### 7. `infra/scripts/meme_spot_swap.py:167` — nota — `plan.verify_reason` ignorado no `--apply`

Só `amount_cap_refusal`/`impact_refusal` recusam; o veredito do verificador do `build_plan` é
descartado. Não assina nada porque `run_apply_leg:101-107` verifica de novo a tx que realmente
assina — o custo é um segundo `POST /swap` e uma linha `quoted → refused`. Correção de uma linha:
`if plan.verify_reason: raise Refused(plan.verify_reason)`.

## O que foi conferido e está certo (evidência)

1. **Verificador instrução a instrução** (`spot_verify.py`): 1 signatário e fee payer = carteira
   (`:287-290`); blockhash zerado recusado (`:291`); program id via ALT recusado (`:305`); programa
   desconhecido recusado por nome (`:320`). ComputeBudget só limit/price, sem contas, uma vez cada,
   `limit × price ≤ MAX_PRIORITY_FEE_LAMPORTS` (`:121-134`, `:323-326`). System: **só**
   `Transfer(carteira → ATA WSOL própria, == in_amount)`, uma vez, e só quando a entrada é SOL
   (`:206-227`, `:315-318`) — `CreateAccount`/`Assign`/transferência para terceiro caem em
   `system_instruction_not_allowed`/`system_transfer_destination_not_wsol_ata`. Token/Token-2022:
   só `CloseAccount` (conta = ATA WSOL, destino = carteira, dono = carteira, uma vez), `SyncNative` e
   `InitializeAccount*` na ATA WSOL própria (`:163-203`); `Transfer`(3), `Approve`(4),
   `SetAuthority`(6), `Burn`(8), `TransferChecked`(12) → `token_instruction_not_allowed:<n>`.
   `JUP6`: exatamente uma `route`/`shared_accounts_route`, autoridade = carteira, origem/destino =
   ATAs próprias dos mints pedidos, `destination_token_account` opcional = placeholder `JUP6`,
   `platform_fee_bps == 0` e conta de taxa = placeholder, `in_amount == pedido`,
   `quoted_out ≥ quote.out_amount`, `slippage_bps ≤ teto`; contas do usuário via ALT → recusa
   (`:230-281`). Contas de DEX dentro da `JUP6` (via ALT) **não são inspecionadas** — mesma confiança
   no programa on-chain da Jupiter que a T4.54b aceitou.
2. **Mínimo on-chain**: a tx não carrega `otherAmountThreshold` literalmente; o programa deriva
   `quoted_out × (1 − slippage_bps/10⁴)` dos dois campos verificados em `:249-257`. Slippage padrão
   50 bps (`meme_spot_swap.py:86`). Impacto: `priceImpactPct` é fração (fixture real
   `0.000618…` = 0,06 %) comparado a `1/100` (`_rules.py:92-101`). Correto.
3. **Token-2022 fecha antes de assinar**: ATAs da rota derivadas com `TOKEN_PROGRAM_ID`
   (`spot_verify.py:260-265`) → `route_source/destination_mismatch`; em `run_apply_leg` a verificação
   (`_send.py:104`) precede `signer.sign` (`:140`). Desembrulho na volta: `CloseAccount` só com
   destino = carteira (`spot_verify.py:180`).
4. **Dry-run não toca a cadeia**: `_dry_run` só faz `getAccount` (decimais), `GET /quote`,
   `POST /swap` (tx não assinada) e verificação local; **não** chama `simulateTransaction` nem
   `sendTransaction`; `SolanaTxRpcClient(args.rpc)` sem `allow_send` → `SendDisabled`
   (`tx_rpc.py:239-240`).
5. **Segredo**: `MemeSigner.from_environment(os.environ)` só em `_apply` (`meme_spot_swap.py:151`),
   depois do interruptor; lido e removido do ambiente uma vez (`signer.py:106-116`); objeto sem
   atributo com a string, `repr` = chave pública; `Settings` não nomeia a variável (grep vazio);
   `main` só captura `Refused` e imprime `refused: <motivo>`; tracebacks Python não renderizam
   locais. Linha do banco: `reason`, quantias, impacto, bps, `signature`, `input_mint`/`output_mint`,
   saldos SOL (`_db.py:34-52`); `system_events.data` = assinatura + mints (`_send.py:159-166`).
6. **Kill switch ao vivo**: `meme_live_kill_switch` (scope `wallet`, latched sem release →
   `TRADING_DISABLED`), `meme:kill` no Redis (erro → `EMERGENCY`), `SYSTEM_KILL_SWITCH`,
   `MEME_KILL_FILE`; mais restritivo; `--apply` exige **exatamente** `ACTIVE` (`_kill.py:46-67`,
   `meme_spot_swap.py:148-150`). `apply_requires_a_sol_leg` antes de abrir banco (`:142-143`).
7. **Migração 0056**: duas colunas `text` anuláveis + um CHECK `(input_mint IS NULL) = (output_mint
   IS NULL)` (aditivo, satisfeito por toda linha existente); downgrade recusa com `RAISE EXCEPTION`
   enquanto houver par gravado, depois `DROP … IF EXISTS`; nenhuma instrução de RLS/grant/policy.
   `test_migration_0056.py` não foi rodado (Postgres via testcontainers — mesma lacuna das notas).

## Comandos executados
```
timeout 590 uv run pytest infra/scripts/tests services/meme-executor/tests/test_spot_verify.py -q -p no:cacheprovider -k "spot"
20 passed, 321 deselected in 3.00s

uv run python <scratch>/adv_spot_send.py     # check_buy_with_sol/check_sell_for_sol com os valores de run_apply_leg
buy  0.02 SOL, threshold 10402273 -> simulation_token_short
sell back, min_sol_out 19_900_000 -> simulation_sol_short
sell back, min_sol_out  9_000_000 -> None
```
Observação: `run_apply_leg` não tem **nenhum** teste (o docstring de `test_meme_spot_swap.py:1-8`
admite); os achados 1 e 2 seriam pegos por um fake de `ChainReader`/RPC.

## Dry-run que o Everton roda primeiro (na VPS, sem chave)
```bash
bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
    --from SOL --to EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --amount 0.02 \
    --round-trip --reason "T4.73 prova SOL->WIF" \
    --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4
```
A saída **tem** de mostrar, nos dois blocos (`quote So111… -> EKpQ…` e `round-trip sell-back:`):
`in=0.02 (20000000 atoms)`; `out~=` e `threshold=` com `threshold ≈ out × 0,995`; `route=` com
rótulos de DEX conhecidos; `price_impact_pct=` < `0.01`; `amount_cap: ok`; `impact_cap: ok`;
**`verify: OK`** (qualquer `verify: REFUSED …` ou `verify_unavailable:…` = parar; em especial
`route_instruction_unknown:…` significa que a Jupiter devolveu um layout de rota novo e o verificador
não o cobre); `round_trip_cost_fraction=` abaixo de ~0,015; e a última linha
`dry-run: nothing written (add --apply)`. Só depois das correções 1–4 e de uma nova revisão do diff
de `meme_spot_swap_send.py` é que o `--apply` de 0,02 SOL faz sentido.
