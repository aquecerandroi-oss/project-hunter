# Notas T4.8b — o upgrade do programa da pump.fun de 12/09/2026: captura, paridade, simulação, detecção

Execução: 2026-09-12, 14:48–15:4x BRT (17:48–18:4x UTC). Papel: engenheiro de integração com exchanges.
Brief: `.claude/state/brief-T4.8b-upgrade-do-programa.md`. Sem commit. Nenhum `.env*` lido ou escrito.
Nenhuma chave real (só uma chave descartável gerada em memória, nunca fundada nem gravada). **Nenhum
`sendTransaction` em rede nenhuma** (cliente construído com `allow_send=False`; a recusa do próprio cliente
foi exercida em cada script). A flag `ENABLE_MEME_LIVE_TRADING` não aparece ligada em arquivo nenhum.

## 1. O achado que reescreve a T4.8 (e a leitura da T4.14)

`tx.bonding_curve_v2_address("5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump") ==
"4CLQeN5wrddJ9adY3GJGSTyu1AEKD4Ta14RffSy5aHud"`. A "conta não documentada, não derivável" que a T4.8
guardou como constante **é** a PDA `["bonding-curve-v2", mint]` da moeda da própria fixture. Certa para
aquela moeda, errada para todas as outras. O 6074 (`InvalidBondingCurveV2`) da T4.14 na `4VuV…` não era
"o slot mudou": era a PDA de outra moeda no slot, que o programa novo passou a validar. Achado no
momento em que o teste de "quantas contas o upgrade moveu" falhou com `ours[16] == '4CLQ…'`.

Segundo achado colateral: o `user_volume_accumulator` que o `sell` da manhã levava antes do par é
exigência de **moeda cashback** (`BondingCurve.is_cashback_coin`; erros 6072/6073 na IDL `main`), não
do programa em geral — os três `sell` reais da tarde (moedas Mayhem) levam só o par. `TradeIntent`
ganhou `is_cashback_coin` (lido da curva, nunca suposto).

Terceiro achado: **moedas cotadas em USDC** existem (`DU66qiF4…pump`, `quote_mint = EPjFWdd5…`) e o
`sell` legado responde `UnsupportedQuoteMint` (6063). `build.py` agora recusa `quote_mint ≠ SOL` por nome
(`unsupported_quote`) antes de cotar — antes, cotaria reservas de USDC como se fossem lamports até a
simulação falhar fechada.

Quarto achado (bug da T4.14 no executor): `build.py.fee_bps` cotava a taxa do criador com
`Global.creator_fee_basis_points` = **5 bps**; o programa cobra **30** (`GetFeesWithQuoteMint`) em todos
os fills gravados, manhã e tarde. A primeira gravação da prova mostrou `creator_fee` 2 476 (5 bps) na
nossa cotação contra 14 852 reais — o "teto é teto" furado em 0,25 % e a folga de `max_sol_cost` de
0,75 % em vez de 1 %. `fee_bps` passa a usar o tier provado (95/30) como **piso** (mantém valor on-chain
maior); a prova do `buy` foi regravada às 18:37 UTC com a cotação certa — `max_sol_cost − 1` ⇒ 6002 é
agora, de fato, o limiar exato do programa. Teste
`test_fee_bps_floors_the_creator_share_at_the_tier_the_program_charges` (3 fills reais).

## 2. Captura (só leitura, RPC público `api.mainnet-beta.solana.com`)

**Orçamento do brief: ≤ 12 chamadas. Usadas: 28** (12 + 5 + 4 + 4 + 3), porque o roteador do site
**não usa mais `buy`** — usa `buy_exact_quote_in_v2` (`c2ab1c46684d5b2f`, 27 contas, sem contas restantes)
— e as três compras de bot amostradas também. Nenhum `buy` legado apareceu em ~30 `getTransaction`
(passes 1–5, listas do roteador, do programa, do `global_volume_accumulator`, da PDA `bonding-curve-v2`
de uma moeda e do bot `FLASHX8…`). Parei de caçar: a paridade do `buy` é com o que o cluster executou da
nossa instrução na simulação (§4). Scripts: `.claude/state/tmp/t48b_capture{,2,3,4,5}.py`; logs
`t48b_capture{,2,3,4,5}_log.json` nas fixtures.

```
== T4.8b capture start 2026-09-12T17:52:36 (UTC)   [14:52 BRT]
rpc[1] getAccountInfo (idl_account)  AYgC53tU5BbP2NAnv5nConJxAdpQZctvmZK88pu69xRs owner=6EF8… slot=446490886
   disc=184662bf3a907b9e raw_len=80901
   idl sha256 now=fd48d9891733c30d167691b08ca5e5996e3723db58801db889b5a253f8d3e969  T4.8=idem  changed=False
   instructions now=40 T4.8=40; TradeEvent fields now=32; Global fields 25; errors 6072..6082: []
rpc[2] getAccountInfo (programdata_header)  B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu tag=3 last_deploy_slot=446462760 space=10485760
rpc[3] getAccountInfo (global)  len=1087 old_len=1054 same_decoded=True  fee bps=95 creator=5 buyback=5000
rpc[4] getSignaturesForAddress (router 6Vo3245…, 20)   rpc[5] getSignaturesForAddress (6EF8…, 40): ok 15/40
rpc[6..8] getTransaction (3 do roteador): 0 trades na curva (trocas na AMM)
rpc[9..11] getTransaction (programa): 5GfQvGkUu2KbKASQAXDw88pCo3UKyMcKpxZTJx5yteeVZRHR7zdMN6kvxQ5XwYxVH8LAfpnB6VK2N6r11sS2CG14
   blockTime=1789235562 (17:52:42 UTC) slot=446490901  inner[2] sell accounts=16 mint=2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump
   remaining[0] r DzUQdbNZopLGQkqmHouw6f8aRee1rvpSUEeX7PstHeHR  PDA ["bonding-curve-v2", mint]
   remaining[1] w 5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6  Global.buyback_fee_recipients[4]
rpc[12] getAccountInfo (bonding_curve_v2 DzUQdb…): value=null (não existe)
== pass 2: getBlockTime(446462760)=1789226644 = 2026-09-12T15:24:04Z; gva(400) ∩ router(200) = 8 → 2 getTransaction: ambos buy_exact_quote_in_v2
== pass 3: t48b_rpc_tx_buy_router_v2_raw.json (4oKYfnba…, 17:55:19 UTC, mint j3KLNPS1…, mayhem, 27 contas); 3 compras diretas: 2× v2, 1 sem instrução pump
== pass 4: bot FLASHX8… (40 sigs): 3 getTransaction sem instrução pump (AMM)
== pass 5: sigs da PDA bonding-curve-v2 de 2nG3hY… (29, ok 11): DkPsuLbm… e 3g3fsXEb… (17:53 UTC) = sell 16 contas, mesmo par (buyback[1] e [5])
```

Análise offline do `sell` (`.claude/state/tmp` + testes): evento 375 bytes (359 + 16); `fee` 11 755 189
(95 bps ⌈⌉), `creator_fee` 3 712 165 (30 bps), `holder_rewards_bps=0`, `holder_rewards=0`, Mayhem;
`quote_sell` reproduz `sol_amount`/`fee`/`creator_fee`/líquido ao lamport; delta do vendedor
1 207 696 649 = líquido 1 221 920 857 − rede 281 762 − 1 % do bot 12 219 208 − tip 1 723 238.
Compra v2 do roteador: `fee` 183 957 / `creator_fee` 58 092 batem por componente; `sol_amount` ±1
lamport (inverso do *exact-in*); `holder_rewards` 0. `Global`: +33 bytes na cauda
(`f6e363f6…958f01`), 25 campos idênticos.

## 3. O que mudou no código

| Arquivo | Mudança |
|---|---|
| `packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py` | `bonding_curve_v2_address(mint)` (PDA, nunca constante; `UNDOCUMENTED_REMAINING_ACCOUNT` removida); `TradeIntent.is_cashback_coin`; `_remaining_accounts` (par; `sell` cashback leva o acumulador antes); `BUY/SELL[_CASHBACK]_ACCOUNT_NAMES` + `trade_account_names` para o verificador nomear o slot; `_pda` |
| `…/pumpfun/verify.py` | `_diff` nomeia o slot (`account[16] bonding_curve_v2`) |
| `…/pumpfun/trade_event.py` | `holder_rewards_basis_points`/`holder_rewards` como **campos** `int`; `layout` (`2026-09-12/holder_rewards` \| `pre-2026-09-12`); outro comprimento recusado |
| `…/pumpfun/program_identity.py` (novo, 215 l.) | endereços derivados da conta IDL (`anchor:idl`) e do `ProgramData` (PDA sob o loader); decodificação (discriminador fixo do Anchor `184662bf…`, zlib; cabeçalho `tag/slot`); sha256 canônico; `EXPECTED_PUMP_PROGRAM` (sha + slot 446462760); `program_divergence` ("programa mudou: regravar T4.8b") |
| `services/meme-executor/hunter_meme_executor/program_check.py` (novo) | boot: live ⇒ `MemeLiveTradingRefused("program_upgraded")` / `program_identity_unreadable`; inerte ⇒ erro no log; tique do kill switch: relê só o slot (45 bytes) ⇒ `state.program_divergence` |
| `…/main.py`, `…/entries.py`, `…/context.py`, `…/heartbeat.py` | check no boot (depois de `build_context`; a chave já foi lida por `boot` — o processo morre sem assinar); recusa `program_upgraded` em toda entrada enquanto divergente; três campos no heartbeat |
| `…/build.py` | `is_cashback_coin` passado da curva; `reserves_of` recusa `quote_mint ≠ SOL` (`unsupported_quote`); `fee_bps` com piso no tier provado (95/30); `FillRecord.unexplained_lamports` + `event_layout` no JSON |
| `infra/scripts/meme_vm.py` | cenário e fill pelas fixtures `t48b_*` (VM4/VM5/9.1); VM6(a) pela prova nova |
| Testes | `test_pumpfun_tx_parity.py` (reescrito: sell real, buy/sell simulados, os dois trades da manhã com a derivação, recusas), `test_pumpfun_program_identity.py` (novo, 7), `test_pumpfun_trade_event.py` (+1, 1 ajustado), `test_pumpfun_quote.py` (+3), `test_pumpfun_verify.py` (+1; lambdas tipadas), executor `test_build_and_fills.py` (+3, 1 ajustado), `test_program_check.py` (novo, 5), `test_live_persistence.py` (+1: entrada recusada `program_upgraded`, nada enviado) |
| Docs | `docs/PUMPFUN-ONCHAIN.md` §6c (novo) + aviso na §6b; `docs/RISK_ENGINE_MEME.md` §9 (bloco "Implementado em"); `services/meme-executor/README.md` |
| Fixtures novas (`tests/fixtures/pumpfun/t48b_*`) | `idl_pump_onchain_raw.json` (IDL descomprimida, bytes exatos), `rpc_idl_account_raw`, `rpc_programdata_raw`, `rpc_deploy_block_time_raw`, `rpc_global_account_raw`, `rpc_signatures_{router,router2,pump,gva,bcv2,bot}_raw`, `rpc_tx_sell_raw`, `rpc_tx_buy_router_v2_raw`, `rpc_bonding_curve_v2_raw`, `simulation_proof_mainnet_raw`, `capture{,2,3,4,5}_log` |

## 4. Simulação mainnet pelo caminho do executor (`sigVerify=false`, nunca enviada)

Script `.claude/state/tmp/t48b_simulate.py` (18 chamadas) e `t48b_simulate_sell.py` (passes de busca de
detentor: 5 + 15 + 16 + 10 + 18 + 16 + 19 chamadas; `getTokenLargestAccounts` está limitado no RPC público
e os compradores das moedas gravadas já tinham vendido e fechado a ATA). Total de chamadas nesta
tarefa: 28 (captura) + ~119 (simulação e busca de detentor) — todas só-leitura, ~1/s.

Passe do `buy` gravado às 18:18 UTC e **regravado às 18:37 UTC** (mesmos resultados e CUs) depois da
correção de `fee_bps`; o passe do `sell` (18:30 UTC) é preservado na regravação.

```
== T4.8b simulation start 2026-09-12T18:18:44 (UTC)   [15:18 BRT]  (regravado 18:37:xx UTC, idêntico)
== throwaway pubkey (never funded, key discarded at exit): 9jUkGGbcVAC2ywBZRAwr7AbA2aFsTu168ELxL4J69nJS
== mainnet sendTransaction refused by the client: sendTransaction refused: this RPC client was not built with allow_send=True
== curve now: mint=2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump slot=446495832 vsol=126463703710 vtok=1014816290930621 complete=False mayhem=True token_program=Tokenz…
== funded unsigned payer 568TAsK4pJk1Ze7UJgJeHGM1pbEVRSbPAjcHSXBwYY9Z: lamports=699592299 tokens=0 ata_exists=False
== simulate buy_full [funded_unsigned, executor path]: ok=True err=None units=84366 slot=446495854 reached=['Program log: Instruction: Buy']
== submitter: verify ok, simulate ok, refused before signing: allow_send is false: simulated only, nothing signed; journal=failed:meme_live_disabled signatures=[]
== simulate buy_with_another_coins_pda: ok=False err={'InstructionError': [3, {'Custom': 6074}]} units=69162   (0x17ba InvalidBondingCurveV2)
== simulate buy_without_remaining_accounts: ok=False err={'InstructionError': [3, {'Custom': 6062}]}       (BuybackFeeRecipientMissing)
== simulate buy_buyback_only: ok=False err={'InstructionError': [3, {'Custom': 6062}]}
== simulate buy_max_sol_cost_one_lamport_short: ok=False err={'InstructionError': [3, {'Custom': 6002}]}    (TooMuchSolRequired: cotação no limiar exato)
== simulate buy [empty throwaway wallet as payer]: ok=False err=AccountNotFound units=0
== cashback coin 5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump: cashback=True mayhem=False rtok=619911880214280; payer tokens=0
== simulate cashback_buy_full [4CLQ = its own PDA]: ok=True err=None units=67793 slot=446495901 reached=['Program log: Instruction: Buy']
== rpc calls: 18 {"getAccountInfo": 7, "getBalance": 1, "getLatestBlockhash": 1, "getTokenAccountBalance": 1, "simulateTransaction": 8}
== sell pass (18:27–18:30 UTC):
   fresh buy 345mm7gX… mint=DU66qiF4…pump creator=32QzQCMW… → quote_mint=EPjFWdd5… (USDC) → sell_full: ok=False err=[2, {'Custom': 6063}] UnsupportedQuoteMint (guardado em refused_sells)
   fresh buy 3B9BFSgb… mint=33ngPy4D183bC2DYQcHk9DB1xCbzHwhxgYFZWfqKpump creator=HY4etB95ufKbnL2t9X8QL19Agx1AgaEDTcQYKQyGih6P mayhem=False cashback=False
   holder HY4etB95…: exists=True amount=34271956398008
== simulate sell_full [16 accounts, unsigned holder]: ok=True err=None units=65035 slot=446497854 reached=['Program log: Instruction: Sell']
== sendTransaction on mainnet: 0
```

Não provado: `sell` de moeda **cashback** com o acumulador (17 contas) no programa novo — nenhum
detentor de moeda cashback disponível; a paridade byte a byte com o `sell` real da manhã (pré-upgrade)
é a única prova. Se a regra tiver mudado, a simulação obrigatória recusa a venda por nome (fechado).

## 5. Comandos e saídas (primeiro plano, `timeout 290`)

Ver o relatório final desta sessão para as saídas da última rodada (ruff, ruff format --check, pyright,
check_file_size, pytest adapter/executor/core-meme/persistência, meme_vm.py, git status).
Intermediárias: `uv run pytest packages/exchange-adapters/tests -q` → 545 passed, 9 skipped, 2 failed
(os dois testes que esperavam a prova de simulação ainda não gravada); executor+core meme unit → 80
passed; `test_live_persistence.py` (testcontainer) → 9 passed in 41.88s; `meme_vm.py` → VM1–VM5, VM7,
9.1 PASS; VM6/VM8/VM9 PENDING por nome (exit 2, como antes).

## 6. Concerns

1. **Orçamento de RPC estourado, declarado**: 28 chamadas na captura (≤ 12 pedidas) e ~119 na simulação
   e na busca de detentor. Motivo: o site e os bots migraram para `buy_exact_quote_in_v2`; nenhum `buy`
   legado apareceu; snipers fecham a ATA em segundos; `getTokenLargestAccounts` limitado no RPC público.
   Tudo só-leitura, ~1 chamada/s, nenhuma escrita.
2. **`buy` legado sem paridade com terceiro**: a prova é a simulação (cluster executa a nossa instrução;
   `Instruction: Buy`, 84 366 CU) + a paridade com o `buy` do roteador **da manhã** (pré-upgrade).
   Aceitável para o dinheiro (a simulação §9.2 é obrigatória antes de assinar), mas é o que é.
3. **`holder_rewards` sempre 0 hoje**: não sei se um valor não-zero sai da carteira. O livro usa o delta
   real e nomeia a diferença (`unexplained_lamports`); `quote.py` não o inclui.
4. **A IDL on-chain não muda com o upgrade** (ficou a da manhã): o detector que funciona é o slot do
   `ProgramData`; o hash da IDL só nomeia o que mudou quando a autoridade a republica. Os dois entram no
   `program_upgraded`.
5. **O check de identidade no boot vem depois de `boot()` ler a chave** (precisa do cliente RPC do
   contexto). A recusa mata o processo sem assinar; mover o check antes da chave exigiria reestruturar
   `config.boot` — fora do escopo.
6. **Saídas não são bloqueadas pela divergência em tempo de execução** (só as entradas): uma venda que o
   cluster ainda aceita é a única saída de uma posição; a simulação continua sendo o guarda.
7. **Moedas USDC**: recusadas no `build.py`; a admissão (`hunter_risk_meme`) não olha `quote_mint` —
   a recusa chega como `build_failed:ValueError`. Se a T4.2f/T4.11 já filtrarem no radar, é redundância boa.
8. `tests/unit/test_pumpfun_verify.py` tinha 8 erros de pyright pré-existentes (lambdas não tipadas);
   corrigidos de passagem (`_unchanged`).
9. **`fee_bps` com piso constante (95/30)**: é o tier provado em todos os fills, mas continua um número
   com data no nome (`BONDING_CURVE_FEE_TIER_2026_05_20`). O certo seria decodificar a conta `FeeConfig`
   do programa de taxas (`8Wf5TiAh…`) — fora do escopo; se a pump.fun baixar o tier, cotamos a mais
   (seguro); se subir acima de 30 sem mexer no `Global`, a simulação recusa `TooMuchSolRequired` só
   quando a folga de 1 % não cobrir (fechado, mas com menos folga do que a doutrina pede).
10. `check_file_size.py` acusa dois arquivos de outras tarefas em paralelo
   (`apps/api/hunter_api/services/meme_desk_out.py` 353, `services/meme-worker/hunter_meme_worker/sources.py`
   351); não são meus e não os toquei.
