# Revisão de risco — T4.54 (commit `02d97530`, tesouraria USDC → SOL pela Jupiter)

**Veredito: BLOCK** (não ligar `MEME_TREASURY_ENABLED=true` antes das correções A, B e D). Com A–E
corrigidas e a prova ao vivo da §6 feita: SAFE_WITH_FIXES. Somente leitura; nada editado, VPS/.env
intocados. Revisor: guardião do motor de risco, 2026-09-18.

Lido: `git show 02d97530 --stat`, `packages/exchange-adapters/hunter_exchanges/jupiter/*`,
`services/meme-executor/hunter_meme_executor/treasury*.py`, `config.py`/`context.py`/`main.py`/
`heartbeat.py` (diff), `infra/migrations/ddl/meme_treasury_swaps.py`, `0051`, ORM
`meme_treasury.py`, `.claude/state/notes-T4.54.md`, `docs/RISK_ENGINE_MEME.md` §16, e o caminho
confiável `pumpfun/verify.py` + `hunter_core/execution/meme/submit.py` + `pumpfun/tx_rpc.py`.

## 1. Verificação antes de assinar

- Lista branca (`treasury_rules.py:44-53`): `JUP6LkbZ…`, Token, Token-2022, Associated Token,
  System, ComputeBudget.
- O verificador (`treasury_rules.py:130-149`) percorre **todas** as instruções de topo do v0 e só
  olha o `program_id`. Contas atrás de *address lookup tables* **não são resolvidas** (nenhuma RPC);
  um `program_id_index` fora das chaves estáticas é recusado (`program_via_lookup_table`). Isso
  **não** quebra rotas legítimas: o runtime da Solana exige que o program id de toda instrução seja
  chave estática (sanitize do `MessageV0`), e os programas de DEX de uma rota Jupiter aparecem
  apenas como *contas* da instrução `JUP6` (CPI), quase sempre via ALT — e essas contas **não são
  inspecionadas**. Logo: swaps roteados por Raydium/Orca/Meteora passam; a confiança está inteira no
  programa on-chain da Jupiter (que só faz CPI para adaptadores conhecidos). Aceitável, desde que a
  instrução `JUP6` seja verificada (não é — ver A).
- Único signatário e fee payer = carteira: sim (`:138-141`, `num_required_signatures == 1` e
  `static_account_keys[0] == wallet`). Tx para outro `userPublicKey` cai em `fee_payer_not_wallet`.
- Blockhash zerado recusado (`:142`); blockhash velho só cai na simulação (`replaceRecentBlockhash=false`).

**A — `treasury_rules.py:44-53,144-149` — ALTA — a lista branca não bounda valor.** Ao contrário de
`pumpfun/verify.py:94-143` (System só gorjeta Jito com teto, Token só `CloseAccount` na própria ATA,
`amount`/`max_sol_cost` iguais ao intento, teto de CU), aqui nenhum dado de instrução é decodificado.
Cenário: resposta de `POST /v6/swap` adulterada (API comprometida, DNS/TLS no meio, proxy) devolve
`SystemProgram.Transfer(carteira → X, 0,68 SOL)` + `Token.Transfer(ATA USDC → X, 21,33 USDC)` ou uma
`route` com `in_amount` = saldo inteiro e `slippage_bps = 10000`; o verificador aceita, a simulação
passa (é válida), assina e envia. Prova (scratchpad, 3 testes adversariais, **todos aceitos**):
```
timeout 120 uv run pytest <scratch>/test_adv_treasury.py -q
3 passed in 1.30s   # System transfer, SPL transfer e route com in_amount 1000x passam
```
Correção mínima (uma das duas, de preferência as duas):
1. Instrução a instrução, como `verify.py`: ComputeBudget só `SetComputeUnitLimit`/`Price` com
   teto (`compute_unit_price_micro_lamports`); ATA só `CreateIdempotent` da ATA WSOL da própria
   carteira; Token só `CloseAccount`(9) com conta = ATA WSOL própria, destino e autoridade =
   carteira, e `SyncNative`(17); **System proibido** (USDC → SOL não precisa de wrap); `JUP6`
   exatamente uma, decodificar `route`/`sharedAccountsRoute` (`in_amount`, `quoted_out_amount`,
   `slippage_bps`) e exigir `in_amount == usdc_atoms`, `quoted_out_amount >= quote.out_amount`,
   `slippage_bps <= cfg.treasury_max_slippage_bps`; qualquer outra coisa → recusa nomeada.
2. Invariante pós-simulação: `simulateTransaction` com `accounts: {addresses: [carteira, ATA USDC],
   encoding: jsonParsed}` e recusar se `USDC_depois < USDC_antes − usdc_in` ou
   `SOL_depois < SOL_antes + other_amount_threshold − 0,01 SOL` (`tx_rpc.py:190` precisa aceitar
   `accounts`). É o invariante `equity = cash + Σ posições` aplicado antes da assinatura.

## 2. Limites de quantidade

- `usdc_atoms` vem do sizing puro (`size_first_pass`/`size_to_target`, `treasury.py:114-139`), com
  teto por troca e **teto diário lido do Postgres** (`treasury_db.py:64`), não de memória — reinício
  não zera o dia. OK.
- **B — `treasury.py:122-139,189-190`, `models.py:192` — MÉDIA — a cotação não é validada contra o
  pedido.** `quote.in_amount`, `input_mint`, `output_mint`, `slippage_bps` nunca são comparados ao
  que foi pedido; `other_amount_threshold` é parseado e ignorado (grep: zero usos). Cenário: quote
  com `inAmount = 21330000` a um pedido de 5 USDC → a tx consome tudo, `meme_treasury_swaps.usdc_in`
  grava 5, teto diário fica errado. O slippage on-chain é o que a Jupiter puser na instrução — só A
  garante. Correção em `_quote`: `in_amount == amount`, mints iguais aos pedidos,
  `slippage_bps == cfg`, `other_amount_threshold >= out_amount × (1 − bps/10000)` (com arredondamento),
  senão `quote_mismatch`.
- Impacto de preço: teto fixo 1 % (`MAX_PRICE_IMPACT_PCT`), mas a **unidade** de `priceImpactPct`
  (fração vs. percentual) não foi confirmada offline. Se for percentual, 0.01 vira 0,01 % → recusa
  tudo (fechado, feature morta). Confirmar na prova ao vivo.
- `config.py:130` diz que o slippage é "checked against the built transaction's own tolerance" —
  falso hoje; só vale depois de A.

## 3. Modos de falha

- **Confirmação estoura (`treasury.py:256-260`)**: linha vai a `failed` com assinatura; nada
  reenvia. Próximo tique: `wallet_refresh` relê o SOL; `last_attempt_at` conta **qualquer** linha
  (DB) → `min_interval` 600 s segura o duplo swap. OK para duplicação.
- **C — `treasury_db.py:34-37` + `treasury.py:256-260` — MÉDIA — teto diário só soma `confirmed`.**
  `confirm_timeout_s` = 30 s < validade do blockhash (~60–90 s): um swap que pousa aos 45 s fica
  `failed` e **não conta**; linha `submitted` órfã (crash entre `send` e `mark_*`) idem; não existe
  reconcile (o caminho confiável tem `reconcile_once`, `main.py:102`). Cenário: 3 estouros em 30 min
  com swaps que pousaram → 75 USDC gastos com cap 50 (hoje limitado pelo saldo, 21,33). Correção:
  `_USDC_24H` soma `status IN ('submitted','confirmed') OR (status='failed' AND signature IS NOT
  NULL)`; reconciliar `submitted`/`failed`-com-assinatura via `get_signature_statuses`/
  `get_transaction` no tique seguinte antes de qualquer nova tentativa.
- Jupiter devolve tx para outro `userPublicKey` → `fee_payer_not_wallet`, OK.
  Simulação falha/ilegível → `refused`, nada assinado (`:229-237`), OK.
  Kill switch travado → `kill_switch_latched` antes de ler qualquer coisa (`:75`), OK.
- **E — `treasury.py:125-131`, `config.py:322-333` — MÉDIA — alvo desacoplado de `wallet_max_sol`.**
  Efetivo hoje 0,72 (`min(0.80, max_total_sol 0.72)`); target padrão 0,60 cabe, mas
  `MEME_TREASURY_SOL_TARGET=1.0` empurra a carteira acima de 0,72 → `wallet_over_max_sol` recusa
  toda entrada até intervenção manual. Correção: `target_efetivo = min(cfg.treasury_sol_target,
  limits.wallet_max_sol − limits.max_sol_per_trade)` e recusar se `wallet_sol + out_amount >
  wallet_max_sol`.
- **D — `treasury.py:60-66` + `main.py:86-91` — MÉDIA — banco lido ANTES de `enabled`.** Duas
  queries em `meme_treasury_swaps` a cada 10 s mesmo com a flag desligada; `forever` re-levanta
  qualquer exceção e o TaskGroup derruba o executor inteiro. Cenário: deploy do código antes da
  0051 aplicada (ou erro transitório de DB) → `meme_executor_loop_failed` a cada boot, mesa parada,
  **com a tesouraria desligada**. Correção: `if not cfg.treasury_enabled: return` como primeira
  linha; envolver o restante em `try/except Exception` que loga e incrementa `rpc_errors`.
- Durante `_confirm` (até ~30 × (RPC + 1 s)) o tique do kill switch não roda: kill file/estado
  ficam sem releitura por até ~60 s (viola "relê a cada 10 s"). BAIXA — mover a confirmação para
  fora do tique ou reduzir para `min(confirm_timeout_s, 20)` com reconcile (C).

## 4. Raio de explosão

- Por tique com a flag ligada e SOL < piso: 2 queries, 1 RPC (`token_account`), 1–2 `GET /quote`
  (httpx 5 s), e só com tentativa 1 `POST /swap` + simulate + send + até 30 statuses + 1
  `wallet`. Sem backoff quando a Jupiter/RPC falha antes de inserir linha (`quote_failed`,
  `usdc_balance_unreadable`, `nothing_to_swap`): repete a cada 10 s indefinidamente. BAIXA.
- Flag desligada: **não é zero** — item D (2 queries/10 s e um caminho de crash novo). `entries.py`/
  `exits.py`/`wake.py` intocados; `JupiterClient` só abre socket ao usar.
- `quote-api.jup.ag/v6` (`client.py:29`) foi descontinuado pela Jupiter (migração para
  `api.jup.ag/swap/v1` com chave / `lite-api.jup.ag/swap/v1`) — não confirmado offline; se estiver
  fora, falha fechada (`quote_failed`) e a feature nunca troca. 3xx não seguido → `MalformedMessage`.
- Migração 0051: `down_revision` 0050, downgrade recusa com linha existente e só então `DROP` —
  reversível enquanto vazia; grants SELECT/INSERT/UPDATE ao worker, sem DELETE; ORM espelha colunas
  e CHECKs (`alembic check` verde nas notas). OK.

## 5. Correções, por prioridade (file:line)

| # | Sev | Onde | O quê |
|---|-----|------|-------|
| A | ALTA | `treasury_rules.py:44-53,144-149` | verificar instrução a instrução (System fora; Token só Close/SyncNative na ATA WSOL própria; `JUP6` decodificada: in_amount/quoted_out/slippage) **e/ou** invariante de saldos pós-simulação |
| B | MÉDIA | `treasury.py:142-154`, `models.py:192` | validar quote: mints, `in_amount == amount`, `slippage_bps == cfg`, `other_amount_threshold` coerente |
| C | MÉDIA | `treasury_db.py:34-37`, `treasury.py:256-260` | cap diário soma `submitted`+`failed` com assinatura; reconcile antes de nova tentativa |
| D | MÉDIA | `treasury.py:60-66` | `enabled` antes do banco; nunca levantar do tique do kill switch |
| E | MÉDIA | `treasury.py:125-131`, `config.py:322-333` | alvo ≤ `wallet_max_sol − max_sol_per_trade`; recusar swap que ultrapasse o teto |
| F | BAIXA | `client.py:29` | confirmar endpoint vivo e unidade de `priceImpactPct` |

## 6. Prova ao vivo mínima (antes de confiar)

1. Sem chave: `GET /v6/quote?inputMint=USDC&outputMint=WSOL&amount=1000000&slippageBps=50` e
   `POST /v6/swap` com `userPublicKey=ARsuJEagSE2p…` → gravar as duas respostas como fixtures reais;
   `decode_versioned_transaction` + `verify_swap_transaction` **têm de passar** e o log deve listar
   os programas de topo (esperado: ComputeBudget ×2, ATA, JUP6, Token). Conferir a unidade de
   `priceImpactPct`.
2. `simulateTransaction` da tx real (sem assinar) com `accounts` da carteira e da ATA USDC:
   USDC cai exatamente 1,000000 e SOL sobe ≥ `otherAmountThreshold`.
3. Primeira troca real só depois de A–E: `.env` com `MEME_TREASURY_ENABLED=true`,
   `MEME_TREASURY_MAX_USDC_PER_SWAP=1`, `MEME_TREASURY_MAX_USDC_PER_DAY=1`,
   `MEME_TREASURY_SOL_FLOOR=0.70`, `MEME_TREASURY_SOL_TARGET=0.72` (força um swap de ~1 USDC com o
   saldo atual de 0,68 sem ultrapassar o teto 0,72); conferir a assinatura no Solscan, a linha
   `confirmed` em `meme_treasury_swaps` com `sol_out_filled > 0`, o `hb:meme:executor.treasury`, e
   que `hb.wallet_sol <= wallet_max_sol`; depois voltar aos valores padrão.

## Comandos executados
```
timeout 290 uv run pytest packages/exchange-adapters/tests/unit/test_jupiter_client.py \
  packages/exchange-adapters/tests/unit/test_jupiter_versioned_tx.py \
  services/meme-executor/tests/test_treasury_config.py \
  services/meme-executor/tests/test_treasury_rules.py -q -m "not live"
49 passed in 1.36s
uv run python -c "b58encode(bytes(32)) == '1'*32"  -> True   (constante _ZERO_BLOCKHASH_B58 correta)
timeout 120 uv run pytest <scratchpad>/test_adv_treasury.py -q  -> 3 passed (3 txs hostis ACEITAS)
```
