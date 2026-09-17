# Revisão adversarial T4.46 — `5bbae3ab` (somente leitura)

Escopo: venda cheia fecha a ATA do token (aluguel de volta), rótulo de aluguel nos fills,
`wallet_fills` aceita `jsonParsed`, allowlist do `verify.py`. Código que **assina e envia
transação real de mainnet** (estágio 1, ≤ 0,05 SOL por operação).

Contratos lidos antes: `docs/RISK_ENGINE.md` (v2.5), `docs/RISK_ENGINE_MEME.md` (v0.1),
`docs/PIPELINE.md` §7–§8, `docs/ARCHITECTURE.md` §6, `.claude/state/notes-T4.46.md`.

## 1. Segurança do `CloseAccount`

**Só na venda cheia.** `build.py:232-237`:
`closes_ata = close_ata_on_full_sell and wallet_token_balance is not None and token_amount > 0
and token_amount == wallet_token_balance`. O chamador (`exits.py:206`) faz
`tokens = min(position.tokens, account.amount)`, então:

- `position.tokens >= account.amount` → `tokens == account.amount` → fecha (correto: a ATA fica em 0);
- `position.tokens < account.amount` (carteira tem mais do que a posição) → `tokens < account.amount`
  → **não** fecha. Conservador, correto.
- `wallet_token_balance=None` (leitura de cadeia falhou) → nunca fecha.

**Só a ATA da própria carteira, carteira como dono e destino.** `close_ata.py:22-31` deriva
`associated_token_address(owner, mint, token_program)` e monta
`[ata(w), owner(w), owner(w, signer)]` — destino e autoridade são o mesmo `owner`, que é
`ctx.signer.pubkey`. O verificador repete a derivação de forma independente a partir do
`intent` (`verify.py:139-143`) e recusa por nome se destino ou autoridade divergirem
(`close_account_destination_not_wallet`, testado em `test_build_and_fills.py:347`).

**Reversão atômica.** Não existe "fill parcial" on-chain: o `sell` do pump.fun move exatamente
`amount` ou a transação inteira falha (guarda `min_sol_output`). Se, no instante do
`CloseAccount`, o saldo da ATA não for zero, o SPL Token devolve `NonNativeHasBalance` e **toda a
transação reverte** — Solana é atômica por transação; nada da venda é aplicado, só a taxa de rede
é queimada. Confirmado no caminho: `submit.py` simula **sempre** antes de assinar
(`simulate_transaction(..., replace_blockhash=True)`), então o caso mais provável nem chega a ser
enviado: vira `failed:simulation_failed:...`.

**Modo de falha a nomear (posição travada):** se alguém transferir tokens do mesmo mint para a
nossa ATA entre a leitura de saldo (`exits.py:221`) e a aterrissagem, a venda reverte inteira. A
posição **não** fecha, `set_exit_intent` grava `failed` + `next_attempt_at` com backoff, e só a
próxima tentativa relê o saldo. Como a releitura seguinte veria `account.amount > position.tokens`
→ `tokens < account.amount` → **sem close**, o ataque não é persistente: custa um atraso de saída
(1 tentativa + backoff), não uma posição travada para sempre. Ainda assim: numa saída por stop,
atrasar uma tentativa numa meme coin é dinheiro.
**Sem o allowlist do `verify.py` (o desvio de escopo que o autor assumiu) a posição travaria de
verdade, para sempre** — o autor está certo ao reportar isso; a mudança é necessária, não opcional.

**Ordem `sell` → `close`.** Correta e **imposta por bytes**: `build_trade_message` (`tx.py:302-312`)
produz `[cu limit, cu price, (create ATA), trade, (close ATA), (tip)]` e `verify_trade_message`
reconstrói a mensagem inteira e compara `serialize_message(expected) != message_bytes`
(`verify.py:255`). Uma mensagem com `close` antes do `trade` é recusada
(`instruction_order_differs`).

**Mas: "ambos os venues" é falso.** O `CloseAccount` da ATA do token **só existe no caminho da
bonding curve**. O caminho migrado (PumpSwap) passa por `pumpswap_exit.handle_migrated_position`
→ `pumpswap_build.build_pumpswap_sell:184` → `pumpswap/tx.py:181-195`, que fecha **apenas a ATA
de WSOL** (o unwrap, pré-existente na T4.29a) e nunca a ATA do mint base. Nenhum dos dois arquivos
foi tocado neste commit.

→ `packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:181` — BAIXA — "o aluguel volta na
venda cheia" só vale para a curva — cenário: a moeda migra, a saída roda pelo PumpSwap, ~0,0015 SOL
de aluguel por moeda ficam estacionados para sempre e o contador `ata_closed` do heartbeat nunca
sobe para essas saídas, dando à mesa a impressão de que o recurso está quebrado.

## 2. Allowlist do `verify.py`

**Program ids adicionados: exatamente dois** — `TOKEN_PROGRAM_ID` e `TOKEN_2022_PROGRAM_ID`
(`verify.py:37-38, 173`). O programa ATA (`ASSOCIATED_TOKEN_PROGRAM_ID`) e o System **já estavam**
na lista desde antes (criação de ATA na compra e tip Jito). Nada mais foi aberto.

**O discriminador É checado**, não só o program id: `verify.py:137-138`
`if ix.data != CLOSE_ACCOUNT_DISCRIMINATOR: raise UnverifiedTransaction("token_instruction_not_close_account")`,
com `CLOSE_ACCOUNT_DISCRIMINATOR = bytes([9])` — igualdade **exata** do campo `data` inteiro (1 byte),
então nem `Transfer` (3), `TransferChecked` (12), `Approve` (4), `SetAuthority` (6) nem `Burn` (8)
passam, e um `CloseAccount` com bytes extras também não. Além disso `_close_ata` exige:
`intent.side == "sell"` (um `CloseAccount` numa compra é `close_account_not_a_sell`),
`ix.program_id == intent.token_program`, `len(ix.accounts) == 3`, `accounts[0] == ATA derivada`,
`accounts[1] == accounts[2] == intent.user`. E há uma **segunda linha de defesa**: a reconstrução
byte a byte (`verify.py:240-256`) — os flags de escrita/assinatura, que `_close_ata` não inspeciona
diretamente, estão no cabeçalho da mensagem compilada e qualquer divergência cai em
`message_bytes_differ`. `more_than_one_close_account_instruction` impede duas.

Conclusão: **não**, o allowlist ampliado não deixa passar instrução Token maliciosa ou errada.

O que o verificador **não pode** saber é se a venda é cheia (ele não lê a cadeia). Isso fica só na
guarda do builder.

→ `packages/exchange-adapters/hunter_exchanges/pumpfun/verify.py:130` — BAIXA — verify aceita
`CloseAccount` em venda parcial — cenário: uma regressão futura em `build.py:232` (trocar `==` por
`>=`, ou passar `position.tokens` em vez de `account.amount`) produz uma venda parcial com close;
verify aprova, a simulação reprova, e a saída entra em loop de backoff até alguém olhar o log. É
contido pela simulação, mas o nome da recusa não aponta a causa.

**Lacuna de teste:** não há caso que prove `token_instruction_not_close_account` (um `Transfer`
disfarçado) nem `close_account_not_a_sell`. O código trata os dois; a tabela de casos não os cobre.

→ `services/meme-executor/tests/test_build_and_fills.py:347` — BAIXA — cenário: alguém "simplifica"
a checagem para `ix.data[:1] == b"\x09"` ou remove a checagem de `side`, e a suíte continua verde.

## 3. Contabilidade do aluguel

`unexplained_lamports == 0` na fixture real do R43: **sim, para a COMPRA**
(`test_build_and_fills.py:386-397`: `buy_total_lamports == 52_659_524`, `ata_rent == 1_513_840`,
`account_rent == 1_346_200`, `unexplained == 0`; era 2 860 040 antes). A álgebra fecha nos dois
lados (`fills.py:80-86`). **Para a VENDA com close não existe fixture real de mainnet** — a nota §4
é honesta ("sell real confirma 'sem close hoje'") e o rótulo do refund só é provado contra um
`CloseAccount` sintético. A primeira venda cheia real é o primeiro teste.

**O aluguel entra no PnL — e isso é intencional e simétrico, com duas assimetrias reais.**
`exits.py:329` → `fill.sell_net_lamports`, que em `fills.py:70-71` devolve `payer_delta_lamports`
(o delta real da carteira, que **inclui** o refund); `repo_positions.py:207` faz
`pnl = received − spent`, e `spent` vem de `entries.py:313` → `buy_total_lamports`, que **inclui**
o aluguel pago. Ida e volta: efeito líquido zero — melhor do que antes, quando o aluguel era perda
permanente. Duas assimetrias sobram:

1. → `services/meme-executor/hunter_meme_executor/fills.py:70` — MÉDIA — o refund de aluguel é lido
   como PnL quando a compra não pagou aluguel — cenário: a ATA da moeda sobreviveu a uma posição
   anterior (venda parcial / `blocked_residual` / pó). Uma nova posição na mesma moeda compra com
   `create_ata_idempotent` que não cobra nada, vende cheia, fecha a ATA e credita ~1 513 840
   lamports (0,0015 SOL) ao PnL **dessa** posição. Numa operação de 0,05 SOL isso é +3% de retorno
   fabricado, e `R = pnl / initial_risk_sol` (`repo_positions.py:217`) leva o erro direto para a
   métrica que a mesa usa para julgar a hipótese. Nenhum teste cobre esse caso.
2. → `services/meme-executor/hunter_meme_executor/entries.py:313` — BAIXA — o aluguel único do PDA
   `user_volume_accumulator` (1 346 200 lamports) é cobrado da **primeira** compra da carteira e
   nunca é devolvido — cenário: a primeira posição da carteira nasce com −0,00135 SOL de custo que
   não é trading (−2,7% numa operação de 0,05 SOL) e o relatório da mesa lê isso como uma entrada
   ruim. Está **nomeado** em `ata_rent_lamports`/`account_rent_lamports` no JSON (`fills.py:111-112`),
   mas nenhuma leitura do desk subtrai.

Onde a mesa lê: `meme_positions.pnl_sol` / `.r_multiple` (`repo_positions.py:207-217`) e o payload
`fill.as_json()` gravado em `meme_live_orders.fill` / `positions.exit`. O rótulo está lá
(`ata_rent_refund_lamports`, `ata_rent_lamports`, `account_rent_lamports`) — essa é a parte boa —
mas **o número agregado que a mesa lê já vem somado**, não separado.

Nota menor: `rent.py:117` soma **todo** `createAccount` financiado pela carteira que não seja o PDA
do acumulador dentro de `ata_rent`. Na fixture R43 são exatamente dois e o rótulo está correto;
numa transação futura que financie outra conta (vault de criador etc.) o rótulo chamaria de
"aluguel da ATA" algo que o nosso `CloseAccount` não recupera. Só rótulo — o PnL usa `payer_delta`.

## 4. Risco de regressão

- **Compra:** sem mudança de comportamento. `build_trade_message` ganhou um parâmetro opcional que
  só `build_sell` preenche (`tx.py:297,310-311`); `build_buy` não foi tocado. Único delta
  observável: uma instrução Token numa compra agora é recusada como `close_account_not_a_sell` em
  vez de `program_not_allowed` — mesma recusa, nome diferente.
- **Venda parcial:** sem mudança. `closes_ata` é `False` e a mensagem é byte a byte a de antes.
- **Checagem de tamanho:** intocada. `max_slippage_bps`, `quote_sell`, os portões de
  `hunter_core.execution.meme.gates` e o teto de SOL por operação não aparecem no diff.
- **Simulação:** intocada (`submit.py`, fora do diff). Continua sempre antes de assinar, e é ela
  que converte o pior caso do close num `failed`, não num envio.
- **RPC por tick:** **nenhuma chamada nova**. `ctx.chain.token_account` já era chamado em `_sell`
  antes do commit; o diff só passa `account.amount` adiante. `rent_labels` e `ata_close_refund`
  trabalham sobre o payload de `getTransaction` já obtido — CPU pura, varredura das
  `innerInstructions` da mesma transação. Sem novo timeout a orçar.
- **Compute units:** `CloseAccount` custa ~3k CU contra um teto de 400 000 (`config.py:81`).
  Sem risco de estouro.
- **Idempotência/restart:** intocadas. `client_order_id` continua
  `order_key(proposal_id, side, attempt)`, o guarda de replay é `existing.signatures`
  (`submit.py`), e `_reconcile_sell` continua sendo o caminho de um `submitted_unconfirmed`.
- **Flag:** `_close_ata_on_full_sell(os.environ)` é lida direto do ambiente dentro de `_sell`
  (`exits.py:222`), fora do snapshot de `config.py`/`gates_reload`. → BAIXA — a mesa não consegue
  ver no heartbeat se o recurso está ligado; só vê `ata_closed` subindo (ou não).

## 5. Veredito

**SAFE_TO_DEPLOY.** O caminho que assina é conservador nos dois níveis (builder + verificador), o
discriminador é checado byte a byte, a simulação continua antes da assinatura, o pior caso é uma
reversão atômica que custa a taxa de rede e uma tentativa de saída, e nenhuma chamada de RPC nova
entra no tick. Nenhum achado justifica bloquear dinheiro real no estágio 1.

Duas correções para a fila (não bloqueiam):

1. `services/meme-executor/hunter_meme_executor/fills.py:70` — separar o refund de aluguel do PnL
   de trading (ex.: `close_position(sol_received_lamports=payer_delta − ata_rent_refund)` com o
   aluguel gravado à parte), ou pelo menos um teste que fixe o caso "ATA pré-existente".
2. `packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:181` — estender o fecho da ATA do
   token ao caminho migrado, ou documentar em `docs/PUMPFUN.md` que o aluguel só volta na curva.

## 6. `trade_event._event_payloads` (o achado que o autor deixou aberto)

`packages/exchange-adapters/hunter_exchanges/pumpfun/trade_event.py:254` —
`keys[index] != program_id`, com `keys` vindo cru de `message.accountKeys`. Sob `jsonParsed` cada
chave é `{"pubkey": ...}` e a comparação nunca bate → nenhum `TradeEvent` decodifica.

**Não é risco de produção hoje.** Verifiquei os clientes RPC do repo: `tx_rpc.py:184`
(`getTransaction`, o que o submitter e o executor usam) pede `"encoding": "json"`, e
`rpc_wallet.py:80` idem. `jsonParsed` não é pedido em lugar nenhum do código de produção — só nas
fixtures de investigação do R43. Sob `encoding: json` as `accountKeys` são strings e o caminho
funciona.

É uma **armadilha latente**: quem trocar o encoding para `jsonParsed` (por exemplo para ler
`preTokenBalances` com mais conforto) faz todo fill virar `unknown` **silenciosamente** — sem
exceção, sem log de erro, só uma razão nomeada no fundo do `raw`. O teste
`test_json_parsed_payload_now_names_the_program_not_the_wallet` fixa o comportamento atual em vez
de escondê-lo, o que é a escolha certa. Recomendação: extrair o `_key()` de `wallet_fills.py:117`
para um módulo comum e usá-lo também em `trade_event._event_payloads` — mudança de uma linha, e
fecha a armadilha antes de alguém cair nela.

## 7. Comandos executados (leitura apenas)

```
uv run pytest packages/exchange-adapters/tests/unit/test_wallet_fills_r43.py \
  packages/exchange-adapters/tests/unit/test_pumpfun_tx_parity.py \
  services/meme-executor/tests/test_build_and_fills.py -q -m "not live"
→ 37 passed in 1.92s

uv run pytest packages/exchange-adapters/tests services/meme-executor/tests \
  -q -m "not live" -k "not persistence"
→ 871 passed, 2 skipped, 39 deselected in 19.04s
```

Nada foi editado no código, nada tocou a VPS nem `.env*`, nada foi commitado.
