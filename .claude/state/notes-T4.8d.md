# Notas T4.8d — terceiro upgrade do programa da pump.fun (23/09/2026): a IDL não mudou, o bytecode mudou

Execução: 2026-09-23, 17:37–18:0x UTC (14:37–15:0x BRT). Papel: engenheiro de integração com exchanges.
Sem commit. Nenhum `.env*` lido ou escrito. Nenhuma chave (real ou descartável). **Nenhum
`sendTransaction`** em script nenhum — o cliente foi construído com `allow_send=False` em todos e a
asserção `assert not rpc.allow_send` está no topo de cada um. Nada escrito no VPS.

## 0. Gatilho

Executor de meme em *crash loop* no VPS (64 reinícios, ~1 h): `check_program_at_boot`
(`services/meme-executor/hunter_meme_executor/program_check.py:61`) levantava
`MemeLiveTradingRefused: program_upgraded: last_deploy_slot 449734335 != 447228373`. O guarda fez
exatamente o que devia: construímos `buy`/`sell` à mão contra um programa conhecido, logo uma troca de
*bytecode* tem de parar a negociação até alguém provar que o layout das instruções continua o mesmo.

## 1. Captura (só leitura, RPC público `api.mainnet-beta.solana.com`)

4 passes de captura + 5 de simulação; **~90 chamadas**, todas só-leitura, ~1/s, `sendTransaction=0`.
Scripts em `.claude/state/tmp/t48d_*.py`; saídas em `t48d_*_stdout.txt`. Artefactos brutos pedidos
pelo brief em `.claude/state/t48d/` (`idl_pump_onchain_449734335.json`, `capture_log.json`).

```
== T4.8d capture start 2026-09-23T17:37:58 (UTC)  [14:37 BRT]
rpc[1] getAccountInfo (programdata_header) tag=3 last_deploy_slot=449734335 option_flag=1
   authority=6348fb82…  T4.8c authority=6348fb82…  authority_changed=False
rpc[2] getAccountInfo (idl_account) slot=449773161 disc=184662bf3a907b9e raw_len=97067
   idl sha256 now=c7ca9566…  T4.8c=c7ca9566…  changed=False      <<< a IDL NÃO foi republicada
   instructions now=47 T4.8c=47
rpc[3] getBlockTime(449734335) = 1790174719 = 2026-09-23T14:45:19Z  [11:45:19 BRT]
rpc[4] getAccountInfo (global) len=1087 T4.8c_len=1087 same_decoded=True  fee bps=95 creator=5 buyback=5000
rpc[5] getSignaturesForAddress (pump program, 30): ok 27/30
rpc[6..8] getTransaction: 2 trades legados … mas ambos CPI do programa Mayhem (ver §3)
== pass 2: maxSupportedTransactionVersion=0 recusado (-32015) → v1; 2 trades legados NÃO-Mayhem
== pass 3/4: caça a um `sell` legado em moeda Mayhem (não encontrado na janela)
```

Verificação offline: `t48d_idl_pump_onchain` **não foi gravada** porque os bytes são idênticos aos da
T4.8c — `data[0]` em base64 é a mesma string, o zlib descomprime nos mesmos 97 067 bytes e o sha256 do
JSON canónico é o mesmo. O teste `test_the_t48d_deploy_did_not_republish_the_idl_account` afirma isso
estruturalmente, em vez de duplicar 97 KB de fixture.

## 2. Diff da IDL, instrução a instrução

**Diff vazio por construção**: a conta `anchor:idl` é byte a byte a da T4.8c. Não há uma única
instrução, conta, argumento, tipo ou evento diferente. Por isso a tabela abaixo é o que de facto
importa — o que foi comparado contra a **cadeia**, não contra a descrição:

| O que o nosso código depende | T4.8c (gravado) | T4.8d (programa novo) | Nosso builder/parser continua certo? |
|---|---|---|---|
| discriminador `buy` | `66063d1201daebea` | idem | **sim** |
| discriminador `sell` | `33e685a4017f83ad` | idem | **sim** |
| argumentos `buy` (`amount`, `max_sol_cost`) | 2×`u64`, 24 B (25 com `track_volume`) | idem (24 B nosso; o agente Mayhem passa 25) | **sim** |
| argumentos `sell` (`amount`, `min_sol_output`) | 2×`u64`, 24 B | idem | **sim** |
| nº de contas `buy` | 18 (16 IDL + par) | 18 | **sim** |
| nº de contas `sell` | 16 (14 IDL + par) | 16 | **sim** |
| ordem das contas `buy`/`sell` | ver `BUY/SELL_ACCOUNT_NAMES` | idêntica, slot a slot | **sim** |
| *writability* de cada conta | — | idêntica em ambos os trades reais | **sim** |
| `creator_vault` (T4.29) | `buy[9]` w, `sell[8]` w | idem | **sim** |
| `fee_config` (T4.48) | `buy[14]` r, `sell[12]` r | idem | **sim** |
| `fee_program` (T4.48) | `buy[15]` r, `sell[13]` r | idem | **sim** |
| `bonding_curve_v2` (remaining[0]) | PDA `["bonding-curve-v2", mint]` sob o pump, r | idem | **sim** |
| `buyback_fee_recipient` (remaining[1]) | um dos 8 do `Global`, w | idem | **sim** |
| `TradeEvent` — discriminador | `bddb7fd34ee661ee` | idem | **sim** |
| `TradeEvent` — layout/tamanho | 375 B (`2026-09-12/holder_rewards`) | 375 B (`sell`) / 374 B (`buy`, `ix_name` 1 B mais curto) | **sim** |
| `TradeEvent` — campos lidos em `fills.py` | 34 | idem, todos auto-consistentes (`quote_amount == sol_amount`, `quote_mint` = sentinela SOL, `timestamp` bate) | **sim** |
| `holder_rewards` / `_bps` | 0 | 0 | **sim** (continua reportado, não somado) |
| tier de taxas (`GetFeesWithQuoteMint`) | lp 0 / prot. 95 / criador 30 | idem (`AAAAAAAAAABfAAAAAAAAAB4AAAAAAAAA`) | **sim** |
| `Global` | 1087 B | 1087 B, `same_decoded=True` | **sim** |
| autoridade de upgrade | `6348fb82…` | idem | — |

Provas: `t48d_rpc_tx_buy_nonmayhem_raw.json` (moeda **Mayhem**, `buy` legado de terceiro, slot
449773177) e `t48d_rpc_tx_sell_nonmayhem_raw.json` (moeda clássica, `sell` legado, slot 449773176) —
ambos ≈ 2 h 53 depois do deploy. **0 diffs** em contas, flags e bytes contra
`build_buy_instruction`/`build_sell_instruction`. Teste: `test_pumpfun_tx_parity_t48d.py`.

## 3. A armadilha desta rodada (os dois primeiros trades que amostrei)

Os dois primeiros trades legados que a captura encontrou eram CPI do **programa Mayhem**
(`MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e`) para o seu próprio agente. Neles, três diferenças que
parecem mudança de layout e **não são**:

1. `fee = 0`, `fee_basis_points = 0`, `creator_fee = 0`, `buyback_fee = 0` — o agente Mayhem não paga
   taxa de protocolo (a doc oficial do Mayhem Mode diz o mesmo; achado pela Astra).
2. `global_volume_accumulator` marcado **writable** (o nosso builder marca `r`). É escolha do
   chamador no `message`; uma CPI não pode escalar privilégios, só manter/baixar.
3. No lugar de `bonding_curve_v2`, um endereço que **não** é a nossa PDA. Força bruta:
   é `find_program_address(["bonding-curve-v2", mint], MAYHEM_PROGRAM)` — as mesmas sementes derivadas
   sob **outro programa**. As duas contas não existem na cadeia (`value=null`), como a nossa.

Um `buy` normal na **mesma moeda Mayhem** (`6CF3Vioh…`) carrega a PDA derivada sob o *pump* e bate com
a nossa byte a byte. Conclusão: caminho do chamador, não do programa. O nosso builder nunca passa por
lá. Pinado em `test_the_mayhem_agents_own_trades_are_not_our_path` para a próxima regravação não
tropeçar nisto outra vez.

Quarto achado colateral: o programa Mayhem emite um evento próprio, `31487b2d6e40b085`, 303 B, na mesma
transação. O nosso extractor ignora-o nos dois caminhos (o estruturado filtra por `program_id`, o de
logs pelo discriminador do `TradeEvent`) — `trade_events_from_transaction` devolve exatamente 1 evento.
Também pinado em teste.

## 4. Simulação mainnet pelo caminho do executor (`sigVerify=false`, nunca enviada)

`ChainReader` → `build_buy`/`build_sell` → `BuiltTrade.verify` (§9.1) → `simulateTransaction` com a
mesma serialização do submissor real. Carteiras reais impersonadas só por `sigVerify=false`, nunca
assinadas; fundos de ninguém tocados.

```
BUY  clássica (Cqtq1i2m…, mayhem=False): ok=True units=89601  Instruction: Buy
BUY  Mayhem   (6CF3Vioh…, mayhem=True):  ok=True units=91801  Instruction: Buy
SELL clássica (Cqtq1i2m…, detentor real 4i2Ekmd2…): ok=True units=56042  Instruction: Sell
SELL Mayhem: NÃO PROVADA — ver concern 1
== sendTransaction em mainnet: 0
```

**O `Overflow` (6024) investigado e descartado como problema de layout.** A única venda Mayhem que
consegui montar era do cofre do próprio agente (`BwWK17cb…`) numa curva com `real_sol_reserves = 1`
lamport (drenada). Controlo que fecha a questão: o mesmo erro, no mesmo *compute*, com a **nossa** PDA
e com a **PDA do Mayhem** no lugar de `bonding_curve_v2`, em três tamanhos (0,01 %, 0,1 %, e os
755 493 416 085 que o agente vendeu com sucesso no mesmo slot). Se fosse conta errada, a divergência
seria 6074 (`InvalidBondingCurveV2`), não 6024. Gravado no `simulation_proof` e afirmado em teste.

## 5. O que mudou no código

| Arquivo | Mudança |
|---|---|
| `packages/exchange-adapters/hunter_exchanges/pumpfun/program_identity.py` | `EXPECTED_PUMP_PROGRAM` → T4.8d (**sha inalterado** `c7ca9566…`, slot 449734335, `captured_at` 2026-09-23T17:37:58Z); T4.8c desce para `PREVIOUS_PUMP_PROGRAM`; T4.8b vira `_T48B_PUMP_PROGRAM`, alcançável por `PUMP_PROGRAM_HISTORY` (agora 3 entradas); `UPGRADE_MESSAGE` → "regravar T4.8e"; docstring com a lição do deploy que não republica a IDL |
| `packages/exchange-adapters/tests/unit/test_pumpfun_program_identity.py` | reescrito para T4.8d; +1 teste (a IDL não foi republicada: base64 idêntico, mesmo sha, slot de contexto maior); histórico dos três deploys em ordem; `program_divergence` contra T4.8c menciona **só** o slot (não o `idl_sha256`) |
| `packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity_t48d.py` (novo) | 5 testes: `buy` real (Mayhem), `sell` real (clássica), `Global`+tier inalterados, a armadilha do agente Mayhem, e a prova de simulação |
| `services/meme-executor/tests/test_program_check.py` | fixtures `t48c_*` → `t48d_*` (o `EXPECTED_PUMP_PROGRAM` mudou) |
| `docs/RISK_ENGINE_MEME.md` §9 | bloco "T4.8d" no "Implementado em" |
| Fixtures novas (`tests/fixtures/pumpfun/t48d_*`) | `rpc_programdata_raw`, `rpc_idl_account_raw`, `rpc_deploy_block_time_raw`, `rpc_global_account_raw`, `rpc_signatures_pump_raw`, `rpc_tx_{buy_legacy,sell}_raw` (agente Mayhem), `rpc_tx_{buy,sell}_nonmayhem_raw`, `rpc_tx_sell_mayhem_raw` (é `sell_v2`, documental), `simulation_proof_mainnet_raw`, `capture{,2}_log` |

`tx.py`, `verify.py`, `quote.py`, `trade_event.py`, `decode.py`, `fills.py` e `build.py` **não mudaram**:
nada em que dependem mudou. Nenhuma linha de produção mudou além do pino da identidade.

## 6. Comandos e saídas

```
$ timeout 590 uv run pytest packages/exchange-adapters -q -p no:cacheprovider -m "not live"
747 passed, 12 skipped, 7 deselected in 5.32s
$ timeout 590 uv run pytest services/meme-executor -q -p no:cacheprovider -m "not live"
767 passed, 53 skipped in 7.02s
$ timeout 590 uv run pytest packages/exchange-adapters services/meme-executor -q -p no:cacheprovider -m "not live"
1514 passed, 65 skipped, 7 deselected in 11.74s
$ uv run ruff check <arquivos tocados>          -> All checks passed!
$ uv run ruff format --check <arquivos tocados> -> 4 files already formatted
$ uv run pyright <arquivos tocados>             -> 0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py -> scanned 1061 files; 0 over budget, 0 grandfathered
```

Numa das rodadas o Docker ficou alcançável e os testes de container correram (819 em vez de 767 no
executor). Um falhou — **alheio a esta tarefa**, ver concern 8:

```
$ timeout 590 uv run pytest services/meme-executor -q -p no:cacheprovider -m "not live"   [com Docker]
FAILED services/meme-executor/tests/test_live_persistence.py::test_the_kill_switch_from_redis_blocks_and_the_daily_latch_persists
E   AssertionError: every check recorded after the first refusal (T4.61c: 26 with ``conviction``)
E   assert 27 == 26
1 failed, 819 passed in 199.60s
```

Antes de mudar a constante, os 5 testes de paridade/simulação da T4.8d **já passavam** e os 6 de
identidade falhavam só por "a constante ainda diz T4.8c" — ou seja, o builder estava certo contra o
programa novo sem uma linha de mudança.

## 7. Checklist do operador (procedimento usado três vezes: T4.8b, T4.8c, T4.8d)

Quando o executor recusar `program_upgraded` no boot:

1. **Não desligue o guarda.** A mesa fica fechada até o passo 8. Entradas recusadas é o
   comportamento correto; saídas continuam guardadas pela simulação obrigatória da §9.2.
2. **Capture a identidade nova** (só leitura): `ProgramData` (slot + autoridade), conta `anchor:idl`,
   `getBlockTime(slot)`, `Global`. Base: `.claude/state/tmp/t48d_capture.py`. ~5 chamadas.
   Guarde o JSON bruto da IDL em `.claude/state/t48<n>/`.
3. **Compare a IDL com a gravada.** Se o sha **mudou**: faça o diff instrução a instrução
   (`buy`/`sell`: discriminador, argumentos, ordem e *writability* das contas, `creator_vault`,
   `fee_config`, `fee_program`; e o `TradeEvent`). Se **não** mudou (T4.8b e T4.8d), a IDL não prova
   nada — vá direto ao passo 4, que é a prova de verdade.
4. **Ache trades reais de terceiros que aterraram DEPOIS do slot do deploy** e reproduza-os byte a
   byte com o nosso builder (contas, flags e dados). Mínimo: um `buy` e um `sell` legados.
   - Filtre pelo **discriminador**, nunca pelo comprimento dos dados: `sell_v2` também tem 24 bytes.
   - **Descarte trades cujo programa externo seja o Mayhem (`MAyhSmzXz…`)**: é caminho do agente,
     sem taxa, com `global_volume_accumulator` writable e com a PDA `bonding-curve-v2` derivada sob o
     *programa Mayhem*. Não é o nosso caminho (§3).
   - `getTransaction` precisa de `maxSupportedTransactionVersion: 1` desde 23/09.
5. **Simule os nossos próprios bytes na mainnet** pelo caminho do executor (`sigVerify=false`,
   `allow_send=False`, nada assinado): `buy` e `sell`, clássica e Mayhem se houver detentor.
   Base: `.claude/state/tmp/t48d_simulate.py`. Um erro `Custom` só condena o layout se for
   6062/6072/6074; 6002/6024 são económicos — confirme repetindo com uma variante de conta.
6. **Peça a segunda opinião** (`bash infra/scripts/astra.sh ask t48<n> "…"`) **antes** de mexer na
   constante: é essa conclusão que reautoriza dinheiro real.
7. **Só então** mova `EXPECTED_PUMP_PROGRAM` (empurre o antigo para `PREVIOUS_PUMP_PROGRAM`, acrescente
   ao `PUMP_PROGRAM_HISTORY`, incremente `UPGRADE_MESSAGE` para a tarefa seguinte), aponte
   `services/meme-executor/tests/test_program_check.py` para as fixtures novas e escreva o teste que
   afirma a identidade nova e o histórico.
8. `uv run pytest packages/exchange-adapters services/meme-executor -q -m "not live"` + ruff + pyright
   + `check_file_size.py`; escreva `notes-T4.8<n>.md` e o bloco em `docs/RISK_ENGINE_MEME.md` §9.

**Se qualquer coisa de que o nosso código depende tiver mudado: pare no passo 4, não mexa na
constante, e reporte.** A mesa fica fechada até os builders serem corrigidos.

## 8. Segunda opinião (Astra)

`.claude/state/astra-review-t48d.md`. Resumo: **concorda** com mover o pino para
`(c7ca9566…, 449734335)` e com reabrir o escopo atual da mesa; reproduziu offline, por scripts
próprios, o sha idêntico das duas IDLs, a paridade `data_equal=True` / `diffs []` nos dois trades e a
derivação das duas PDAs sob o programa Mayhem. Concorda explicitamente com manter os **dois** campos no
detector ("a T4.8d é precisamente a regressão que deve impedir alguém de aceitar 'hash igual ⇒ programa
aprovado'").

Argumento dela que eu **não** tinha e que incorporei (e verifiquei antes de aceitar, correndo o grep
que o liquida): a lacuna da venda Mayhem **não cobre nenhuma entrada hoje permitida**, porque
`mayhem_policy_check` (`packages/risk-core/hunter_risk_meme/checks.py:290`) exige
`context.mayhem_policy_approved`, e nem esse campo nem `mayhem_agent_state_known` são alguma vez
ligados em código de produção (defaults `False` em `inputs.py:118`; `grep` em `services/` e `packages/`
fora de testes: **zero** ocorrências). Ela é explícita que este aceite **não** se estende a habilitar
Mayhem — concordo e registo isso aqui.

Correções dela que aceitei: os trades são de 17:38:03Z, **2 h 53** depois do deploy (eu tinha escrito
"~1 h"); `t48d_rpc_tx_sell_mayhem_raw.json` é `sell_v2`, não venda legada (eu já o sabia; fica
documental, sem paridade reivindicada). Ela também notou que o `buy` do agente Mayhem tem 25 bytes
(o byte opcional `track_volume`) — está afirmado em teste.

Findings dela que **não** tratei aqui, por estarem fora do escopo desta tarefa (ficam para o
orquestrador, ver concerns 3 e 4): o leitor de carteiras preso a `maxSupportedTransactionVersion: 0`, e
o facto de o bloqueio no boot matar também a reconciliação/saídas. Nenhum dos dois é motivo para
contornar o detector, e ela diz o mesmo.

## 9. Concerns

1. **`sell` legado numa moeda Mayhem não provado neste deploy.** Nenhum aterrou na janela amostrada
   (14 assinaturas boas examinadas; as vendas Mayhem que apareceram eram `sell_v2` ou do agente) e o
   único detentor que restava era o cofre do agente numa curva drenada. O que **está** provado do lado
   Mayhem: o `buy` legado real byte a byte + `buy` simulado ok (91 801 CU) — ou seja, a aceitação do
   *reserved fee recipient* e da PDA no programa novo. A venda Mayhem difere da clássica **apenas** no
   pubkey do `fee_recipient` (de `Global.mayhem_fee_recipients`, validado por `_validate_recipients`).
   Mitigação real: **Mayhem é recusado na admissão hoje** (§8) e a simulação obrigatória da §9.2
   recusa por nome antes de assinar. Não estender este aceite para habilitar Mayhem.
2. **A IDL não muda com todo upgrade** (2 dos 3 deploys não a republicaram). Quem regravar no futuro
   não pode concluir "sha igual ⇒ nada mudou". Está na docstring do módulo, no docstring do teste e no
   passo 3 da checklist.
3. **Fora de escopo, achado pela Astra:** `rpc_wallet.py:82` (e o consumidor em
   `services/meme-worker/hunter_meme_worker/wallets.py:177`) limita `getTransaction` a
   `maxSupportedTransactionVersion: 0`. Uma transação v1 de uma carteira acompanhada passa a devolver
   erro `-32015` e o coletor retorna sem avançar o cursor — a assinatura fica a bloquear as
   posteriores. **Eu bati nisto nesta tarefa** (pass 2 da captura morreu com esse erro) e uma das
   fixtures novas é `version: 1`. Não corrigi: fora do escopo (`hunter_exchanges/pumpfun/**` desta
   tarefa é o pumpfun on-chain, e a correção precisa de fixture v1 + teste do consumidor).
4. **Fora de escopo:** a recusa no boot em modo live mata o processo antes de subir reconciliação e
   saídas. Se houver posição aberta quando um upgrade cair, ela fica sem babysitter até alguém
   regravar. Não é motivo para enfraquecer o detector; é uma tarefa própria (deixar subir em modo
   "só saídas"). Não verifiquei se há posição aberta agora.
5. **`quote.py` não olha `real_sol_reserves`.** Cotou 1 420 177 lamports de saída numa curva com 1
   lamport de SOL real (§4). Fecha fechado (a simulação obrigatória recusa), mas a cotação mente ao
   sizing antes disso. Pré-existente, não introduzido aqui.
6. **Orçamento de RPC:** ~90 chamadas. Mais do que a T4.8c (63) porque as duas primeiras amostras
   eram do agente Mayhem e tive de recomeçar a caça, e porque persegui a venda Mayhem em quatro
   tentativas. Todas só-leitura.
8. **Falha pré-existente, não minha:** com o Docker de pé,
   `test_live_persistence.py::test_the_kill_switch_from_redis_blocks_and_the_daily_latch_persists`
   falha com `assert 27 == 26` (nº de checks de admissão gravados). `git diff --stat HEAD` nesse
   ficheiro e em `packages/risk-core` é **vazio** — ambos estão exatamente no HEAD; o commit
   `aab81473` (T4.78) acrescentou o check 28 `mint_cooldown_after_loss` sem atualizar essa asserção
   com o número fixo. Só aparece quando o Docker está alcançável, que é porque passou despercebida.
   Não toquei: o ficheiro é de outra tarefa. Para o orquestrador.
9. O brief apontava `docs/RISK_ENGINE_MEME.md` **§16** para a documentação do guarda; §16 é a
   tesouraria. O guarda está documentado na **§9** ("Implementado em"), que foi onde escrevi.
