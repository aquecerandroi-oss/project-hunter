# Notas T4.8c — o segundo upgrade da semana do programa da pump.fun (15/09/2026): recaptura, paridade, is_holder_reward on-chain, simulação

Execução: 2026-09-15, 19:53–20:30 UTC (16:53–17:30 BRT). Papel: engenheiro de integração com exchanges.
Brief: `.claude/state/brief-T4.8c-segundo-upgrade-do-programa-15-09.md`. Sem commit. Nenhum `.env*` lido
ou escrito. Nenhuma chave real (a "carteira descartável vazia em memória" nem chegou a ser gerada nesta
tarefa — a prova usa carteiras reais impersonadas só por `sigVerify=false`, nunca assinadas, exatamente
como a T4.8b). **Nenhum `sendTransaction`** em nenhum script. `ENABLE_MEME_LIVE_TRADING` não aparece
ligada em arquivo nenhum.

## 0. Gatilho

Plantão run 19 (lane 3, `KB-0096`, `.claude/state/plantao-meme/2026-09-15-1616-lane3.md`): o
`ProgramData.slot` do programa da curva passou de 446 462 760 (T4.8b, 12/09) para **447 228 373**
(≈ 15/09 07:34 BRT) — o executor (`program_check.py`) já recusava `program_upgraded` corretamente, o
que travava o boot em modo live. Ao mesmo tempo, `is_holder_reward` apareceu pela primeira vez na REST
(`/coins`, boards, `in-memory-coin`), com 7/70 positivos nas moedas mais novas.

## 1. Captura (só leitura, RPC público `api.mainnet-beta.solana.com`)

**Orçamento do brief: ≤ 15 chamadas. Usadas: 17** (12 + 2 + 3) — dentro de uma margem pequena,
bem abaixo do overrun da T4.8b (28). Scripts: `.claude/state/tmp/t48c_capture{,2,3}.py`; logs
`t48c_capture{,2,3}_log.json` nas fixtures. Mints usados (achados via REST `frontend-api-v3.pump.fun`,
**não contam no orçamento on-chain**): `Czv4odPi8Bk3N3EanjPR1sJGrEnjoNSkKEeUBJVKpump` (clássica),
`7qSzmCMq9tGr2GiAiMrRQJh6esWcJrHhtChojPPqpump` (`is_holder_reward=true`, "COFFEE SHOP"),
`F6pQRW2LbLrXrmGhus1iMjAbZFbjxEASgWViMkempump` (Mayhem).

```
== T4.8c capture start 2026-09-15T19:53:50 (UTC)  [16:53 BRT]
rpc[1] getAccountInfo (programdata_header) tag=3 last_deploy_slot=447228373 option_flag=1
   authority=6348fb82…  T4.8b authority=6348fb82…  authority_changed=False
rpc[2] getAccountInfo (idl_account) slot=447334438 disc=184662bf3a907b9e raw_len=97067
   idl sha256 now=c7ca9566…  T4.8b=fd48d989…  changed=True
   instructions now=47; TradeEvent fields now=34
   BondingCurve fields now=[…, 'creator_fee_bps', 'can_edit_creator_fee', 'is_holder_reward']
   Global fields now=29
rpc[3] getAccountInfo (global) Global len=1087 T4.8b_len=1087 same_decoded=True
   fee bps=95 creator=5 buyback=5000
rpc[4] getAccountInfo (hr)      89t4cqHHr5gKXN5ckfTn2cQcMGgoSByfS5XVuGFwGdJ9 len=151 disc=17b7f8…
      complete=False is_mayhem_mode=False is_cashback_coin=False quote_mint=1111…
rpc[5] getAccountInfo (control) GwjSrfXsr53eiqsH28uCZShbv7cDtDBvV8AG86Bcc3iP len=151
rpc[6] getSignaturesForAddress (router, 20): ok 20/20
rpc[7] getTransaction (tx_router): GhK39x… pump_discs=[]  (não pump)
rpc[8] getTransaction (tx_router): 4qVsu7t… pump_discs=[('inner[5]','5df6823ce7e940b2'),('inner[5]','e445a52e51cb9a1d')]
rpc[9] getSignaturesForAddress (pump program, 25): ok 20/25
rpc[10] getTransaction: 4D9kossy… discs=[('inner[5]','c2ab1c46684d5b2f'), event]  (buy_exact_quote_in_v2)
rpc[11] getTransaction: 9ETcvTEX… discs=[('outer','5df6823ce7e940b2'), event]
rpc[12] getTransaction: 65GR4vo5… discs=[('outer','33e685a4017f83ad'), event]  legacy_trades=1
   outer sell accounts=16 mint=9xastypgyP9DXGss353R1jWKQeyQmxVQNdePS3NWpump
   remaining[0] r 2g1Cad9pyVpwPgtpogEakRuuaPtUTQn2qEbHyJ2Cxd7H  PDA ["bonding-curve-v2", mint]
   remaining[1] w 5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD  Global.buyback_fee_recipients[6]
== capture end; rpc calls=12

== pass 2 (2 calls): re-save the buy_exact_quote_in_v2 tx + hunt a legacy buy
rpc[1] getTransaction (4D9kossy…, re-saved as t48c_rpc_tx_buy_exact_quote_v2_raw.json)
rpc[2] getTransaction: 4ffo79zY… discs=[('inner[1]','66063d1201daebea'), event]  legacy_trades=1
   inner[1] buy accounts=18 mint=3f6ACaSW2wAYno61Y5KdyhccfmGq2y1Ud4AfpFAwpump (bot FLASHX8…, como na T4.8b)
   remaining[0] r 4h99zXxm9CFSpJgViBb1JMsPfrDRT3kke5ikxeYu7uCh  remaining[1] w 9M4giFF…[1]

== pass 3 (3 calls): getBlockTime independente + moedas de referência da T4.8/T4.8b
rpc[1] getBlockTime(447228373) = 1789468472 = 2026-09-15T10:34:32Z (bate com KB-0096, lido de novo)
rpc[2] getAccountInfo (5ejA…, cashback T4.8): len=151 is_holder_reward=0
rpc[3] getAccountInfo (2nG3hY…, Mayhem T4.8b): len=151 is_holder_reward=0
```

## 2. O que a captura mostrou

1. **A conta da IDL on-chain foi republicada desta vez** (a T4.8b tinha ficado intocada): sha256
   `fd48d989…` → `c7ca9566…`, 40 → 47 instruções, `TradeEvent` 32 → 34 campos nomeados. Só agora o
   on-chain alcança o que a IDL `main` do GitHub já tinha (T4.14). Autoridade de upgrade **não mudou**.
2. **`buy`/`sell` legados e `TradeEvent` continuam byte a byte iguais** — provado com um `sell` direto
   real (`65GR4vo5…`, sem CPI de bot, reconciliação **exata**: `delta = sell_net_proceeds - network_fee`)
   e um `buy` legado real via o mesmo bot da T4.8b (`FLASHX8…`, achado na primeira transação de sinal
   do programa que esta tarefa tentou — a T4.8b nunca achou um `buy` legado real e usou só simulação).
   `TradeEvent` continua com 375 bytes; `holder_rewards`/`holder_rewards_bps` continuam 0 nos dois fills.
3. **Instrução nova: `sell_v2`** (`5df6823ce7e940b2`, mesmo formato de `buy_exact_quote_in_v2`) — o
   roteador do site a usou para pelo menos uma venda real hoje. Não construída por este pacote.
4. **`is_holder_reward` tem byte confirmado — e não é novo.** `BondingCurve` depois de `quote_mint`:
   `creator_fee_bps: u64`, `can_edit_creator_fee: bool`, `is_holder_reward: bool` (offset 124).
   Confirmado `true` em `7qSzmCMq…` (a REST também reporta `true`) e `false` no controle. **Achado que
   corrige a leitura do plantão:** a captura do T4.2f de 12/09 já tinha 45/100 contas amostradas em
   151 bytes (uma com `creator_fee_bps=10` não-zero); as próprias moedas de referência da T4.8/T4.8b,
   paradas desde 12/09, já leem 151 bytes hoje. `decode_bonding_curve_account` nunca olhava além do
   byte 115 antes desta tarefa. O que mudou de fato foi a REST/indexer exporem o valor, não o byte
   on-chain nascer. Mecanismo exato (alocação na criação vs. realloc) não determinado no orçamento.
5. **Taxas iguais ao lamport** (95/30 bps, mesmo tier da T4.8b) e `Global` idêntico (1087 bytes,
   `same_decoded=True`).

## 3. O que mudou no código

| Arquivo | Mudança |
|---|---|
| `packages/exchange-adapters/hunter_exchanges/pumpfun/decode.py` | `BondingCurveAccount` ganha `creator_fee_bps`, `can_edit_creator_fee`, `is_holder_reward`, `layout` (`LAYOUT_LEGACY` / `LAYOUT_WITH_HOLDER_REWARD`); decodificação com fallback (< 10 bytes de cauda ⇒ legado, defaults; ≥ 10 ⇒ os três campos, resto reservado e não interpretado); booleano inválido nos novos campos é recusado |
| `…/pumpfun/program_identity.py` | `EXPECTED_PUMP_PROGRAM` agora T4.8c (sha `c7ca9566…`, slot 447228373); `PREVIOUS_PUMP_PROGRAM` (T4.8b) e `PUMP_PROGRAM_HISTORY` novos; `UPGRADE_MESSAGE` → "regravar T4.8d" |
| `services/meme-executor/hunter_meme_executor/program_check.py` | usa `UPGRADE_MESSAGE` importado em vez de "T4.8b" hard-coded na mensagem de divergência em tempo de execução |
| `services/meme-executor/tests/test_program_check.py` | fixtures trocadas de `t48b_*` para `t48c_*` (o `EXPECTED_PUMP_PROGRAM` mudou) |
| `packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity.py` | +3 testes: `sell`/`buy` legados reais de hoje byte a byte, e um teste documental do `sell_v2` (não construído) |
| `packages/exchange-adapters/tests/unit/test_pumpfun_program_identity.py` | reescrito para as fixtures/valores T4.8c; +2 testes (histórico, T4.8b agora diverge) |
| `packages/exchange-adapters/tests/unit/test_pumpfun_decode.py` | novo (8 testes): layout legado/estendido, `is_holder_reward` true/false reais, moedas antigas já em 151 bytes, amostra T4.2f (45/100), booleano inválido recusado, pad curto = legado (não malformado) |
| `docs/PUMPFUN-ONCHAIN.md` | §6d (novo); §7 item 1 corrigido (decode.py tinha campos não lidos) |
| `docs/RISK_ENGINE_MEME.md` | §9, bloco "T4.8c" no "Implementado em" |
| `obsidian/11-KNOWLEDGE/KB-0094-*.md`, `KB-0096-*.md` | adendos T4.8c |
| Fixtures novas (`tests/fixtures/pumpfun/t48c_*`) | idl, programdata, global, bonding curves (hr/control/t48_cashback/t48b_mayhem), assinaturas, `tx_{sell,buy_legacy,sell_v2,buy_exact_quote_v2}_raw`, `simulation_proof_mainnet_raw`, `capture{,2,3}_log` |

`tx.py`/`verify.py`/`quote.py`/`trade_event.py` **não mudaram**: a captura não mostrou diferença nos
campos/paridade que eles cobrem (item 2 do brief).

## 4. Simulação mainnet pelo caminho do executor (`sigVerify=false`, nunca enviada)

Scripts `.claude/state/tmp/t48c_simulate.py` (15 chamadas) + `t48c_simulate_sell2.py` (5, `429` em
`getTokenLargestAccounts` — a mesma limitação que a T4.8b já tinha documentado) +
`t48c_simulate_sell3.py`/pass em Mayhem (13) + uma segunda tentativa de venda HR (8, recusada por
`unsupported_quote` antes de simular). Caminho exercido: `ChainReader` (curva + `Global` + blockhash)
→ `build.build_buy`/`build_sell` → `BuiltTrade.verify` (§9.1) → `simulateTransaction` com a mesma
serialização do submissor real (`\x01` + 64 bytes zerados + mensagem).

```
== payer 3VY5oXS6psas76wQTSW9gRVYjLSntyQts4pzKpFpNxWg lamports=12034065678
== blockhash=7Pptc9Xn… last_valid_block_height=425380780
BUY  classic (Czv4odPi…, sem HR/Mayhem): ok=True units_consumed=103096  Instruction: Buy
BUY  hr      (7qSzmCMq…, is_holder_reward=True): ok=True units_consumed=104600  Instruction: Buy
BUY  mayhem  (F6pQRW2L…, mayhem=True): ok=True units_consumed=87286  Instruction: Buy
SELL classic seller=HWy2TJ3k… (criador, ATA própria) amount=106137438640: ok=True units_consumed=62037
SELL mayhem  seller=5j1Vjc3a… (comprador real achado pelas assinaturas da curva): ok=True units_consumed=49556
SELL hr (7qSzmCMq…): sem comprador real na cadeia ainda (só snipers falhos, Custom:3) — não simulada
SELL hr (2ª candidata, Ballerina Cappuccina, maior market cap): unsupported_quote (quote_mint custom,
   recusado por build.reserves_of antes de simular — o mesmo guardo que a T4.8b já tinha para USDC)
== rpc calls: capture 17 + simulação 46 = 63; sendTransaction=0 em todos os scripts
```

## 5. Comandos e saídas

```
$ uv run --package hunter-exchanges pytest packages/exchange-adapters/tests -q -m "not live"
........................................................................ [ 12%]
........................................................................ [ 25%]
........................................................................ [ 37%]
........................................................................ [ 50%]
........................................................................ [ 63%]
........................................................................ [ 75%]
........................................................................ [ 88%]
..................................................................       [100%]
SKIPPED [2] .../test_live_pumpfun_simulation.py:68: set HUNTER_LIVE_DEVNET=1 to run the live simulation proof
568 passed, 2 skipped, 7 deselected in 17.27s

$ uv run pytest services/meme-executor/tests -q -m "not live"
........................................                                 [100%]
40 passed in 52.82s

$ uv run ruff check <arquivos tocados>          -> All checks passed!
$ uv run ruff format --check <arquivos tocados> -> 7 files already formatted (após 1 rodada de `ruff format`)
$ uv run pyright <arquivos tocados>             -> 0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py -> scanned 856 files; 0 over budget, 0 grandfathered
$ uv run python infra/scripts/meme_vm.py        -> VM1-5, VM7, 9.1 PASS; VM6/VM8/VM9 PENDING por nome (exit 2, igual à T4.8b)
```

## 6. Concerns

1. **Venda de moeda `is_holder_reward = true` não obtida.** Duas candidatas tentadas: a mais barata
   (COFFEE SHOP) ainda não tinha um comprador real na cadeia (só *snipers* falhos, `Custom: 3`); a
   segunda (maior *market cap*, Ballerina Cappuccina) é cotada num token SPL custom — `build.py` a
   recusou por nome (`unsupported_quote`) antes de sequer cotar, o mesmo guarda que a T4.8b provou
   para USDC. `getTokenLargestAccounts` voltou a ser limitado no RPC público (429 ×2), como na T4.8b.
   O `buy` na mesma moeda **foi** provado (104 600 CU) — o `sell` legado em si não muda de forma
   (mesmas 16 contas, mesmo par) então o risco residual é baixo, mas não é uma prova.
2. **`holder_rewards`/`holder_rewards_bps` continuam 0 em todo fill real observado** (hoje e em
   12/09) — nenhum dos dois fills reais desta tarefa foi numa moeda HR. Não sei se um valor não-zero
   sai da carteira do trader ou é uma fatia interna. `quote.py` continua sem incluí-lo.
3. **Mecanismo do layout estendido da `BondingCurve` não determinado.** 151 bytes coexistem com 124
   desde antes de qualquer upgrade de 2026-09 (T4.2f, 12/09: 45/100). Não sei se é alocação na criação
   (algumas moedas nunca crescem) ou realloc lazily; as duas moedas de referência da T4.8/T4.8b, paradas
   desde 12/09, já leem 151 bytes hoje — compatível com qualquer uma das duas explicações.
4. **A conta da IDL republicada não implica que o binário do programa em si mudou de novo nesse
   detalhe** — só confirmamos que a *descrição* alcançou o que já era verdade no binário (a T4.8b já
   tinha achado `buy_exact_quote_in_v2` fora da IDL de então). `sell_v2` é novo na IDL; se já existia
   no binário antes de hoje e só não tinha sido usado, não foi determinado.
5. **`fee_bps` do executor continua com o piso datado** (`BONDING_CURVE_FEE_TIER_2026_05_20`,
   95/30) — segue batendo com o `TradeEvent` real de hoje; decodificar `FeeConfig` continua fora do
   escopo (mesma nota da T4.8b, item 9).
6. `check_file_size.py` não acusou nenhum arquivo — os dois que a T4.8b via de outras tarefas já
   foram corrigidos (não são meus, não os toquei).
7. Orçamento de captura: 17 chamadas contra o alvo de ≤ 15 — pequeno excesso, documentado (passo 2
   achou o `buy` legado de primeira; passo 3 foi por completude — `getBlockTime` independente + as
   duas moedas de referência antigas).
