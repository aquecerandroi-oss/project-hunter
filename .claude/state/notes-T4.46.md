# T4.46 — a venda cheia fecha a conta do token (aluguel volta); fills rotulam aluguel de ATA/PDA

Escopo dado: `packages/exchange-adapters/hunter_exchanges/pumpfun/{tx.py,wallet_fills.py}`,
`services/meme-executor/hunter_meme_executor/{build.py,exits.py,exit_common.py}` (exits só),
testes, docs. `exit_common.py` não precisou de mudança (o contador vive em `ExecutorState`).

## 1. `build.py`/`tx.py` — `CloseAccount` na venda cheia

`tx.build_close_ata_instruction(owner, mint, token_program)` — `CloseAccount` (índice 9, igual
em SPL Token e Token-2022) na ATA do próprio `owner`, espelhando
`pumpswap.tx.build_close_wsol_instruction`. `build_trade_message` ganhou o parâmetro `close_ata`
(ordem `[cu limit, cu price, (create ATA), trade, (close ATA), (tip)]`).

`build_sell` ganhou `wallet_token_balance: int | None` e `close_ata_on_full_sell: bool = True`:
fecha quando `token_amount == wallet_token_balance` (venda cheia, positiva); nunca em venda
parcial (fecharia uma conta com saldo — o programa recusaria on-chain, então nem tentamos) nem
sem saldo conhecido (`wallet_token_balance=None`, o chamador não leu a cadeia). `exits.py` passa
`account.amount` (o saldo real lido antes de montar a venda) e lê a env `MEME_CLOSE_ATA_ON_FULL_SELL`
(default ligado) via `parse_flag` de `hunter_core.execution.meme.gates`.

**Desvio de escopo, necessário:** `verify.py` (não estava na minha lista) precisou de um allowlist
novo — sem ele, `verify_trade_message` recusa `program_not_allowed` em **toda** venda cheia, para
sempre (a venda nunca decodifica, o retry roda com backoff eternamente e a posição trava). Toquei
o mínimo: `_classify` aceita um `CloseAccount` do `token_program` do `intent` só numa venda, só na
própria ATA, só com `owner == destination == wallet`; a reconstrução do rebuild inclui
`close_ata` quando visto. `VerifiedTrade` ganhou `closes_user_ata`. Sem essa mudança o recurso
inteiro é uma bomba: constrói, nunca verifica, nunca vende. Reporto isto como concern explícito.

Contador: `ExecutorState.ata_closed` (`context.py`) incrementado em `_close()` quando
`fill.ata_rent_refund_lamports` é positivo (o fechamento *confirmado* na cadeia, não a intenção);
exposto em `heartbeat_fields` como `ata_closed`. Ambos os arquivos não estavam na minha lista
("exits only" para o pacote do executor) — mudança de uma linha cada, sem tocar nada do T4.45.

## 2. `wallet_fills.py` — aluguel rotulado, `jsonParsed` aceito

`_account_keys` aceita `{"pubkey": ...}` (o bug do R43 §5: uma chave `jsonParsed` virava
`str(dict)`, o programa Pump nunca era achado, `_from_balances` caía em `no_known_venue`).

`rent_funded_by`/`rent_labels`/`ata_close_refund_lamports` (movidos de
`test_wallet_fills_r43.py` para produção, ampliados): leem tanto `jsonParsed` (`parsed.info`)
quanto o `encoding: json` que os clientes RPC deste repo realmente pedem — decodificando os bytes
crus do System Program (`u32 index=0, u64 lamports, u64 space, pubkey owner`, confirmado byte a
byte contra a fixture real do R43). Isso importa: **o watcher e o executor usam `encoding: json`
em produção**, nunca `jsonParsed` — sem o caminho raw, o rótulo nunca apareceria fora de um teste.
Confirmado rodando contra os três fixtures reais: `rent_labels` devolve `(1 513 840, 1 346 200)`
nos dois encodings da mesma compra.

`WalletFill.sol_received_lamports` soma `raw["ata_rent_refund_lamports"]` quando presente.

**Achado lateral não corrigido (fora do escopo, nomeado para não passar despercebido):**
`trade_event._event_payloads` (não é um dos meus arquivos) tem o mesmo bug de comparação de chave
`jsonParsed` — `keys[index] != program_id` nunca bate quando `keys[index]` é um dict. Resultado:
mesmo depois do meu fix, `wallet_fills_from_transaction` num payload `jsonParsed` real ainda cai
em `unknown` (a razão melhora de `no_known_venue` para `no_trade_event_for_wallet` — o programa
Pump agora é visto — mas o evento não decodifica). Coberto por
`test_json_parsed_payload_now_names_the_program_not_the_wallet`, que fixa o comportamento atual
em vez de escondê-lo.

## 3. Arquivos novos (só para caber no orçamento de 350 linhas)

`build.py` (414), `wallet_fills.py` (536) e `tx.py` (366) passaram do teto depois das mudanças.
Extraí, sem mudar comportamento:

- `hunter_exchanges/pumpfun/rent.py` — `rent_funded_by`/`rent_labels`/`ata_close_refund` puros
  (recebem `keys` do chamador, sem reler `getTransaction`).
- `hunter_exchanges/pumpfun/wallet_balance.py` — a leitura de saldo (`from_balances`, §2 do
  docstring de `wallet_fills.py`), incluindo `PUMPSWAP_PROGRAM_ID`/`WSOL_MINT`/`Side`/`Venue`
  (reexportados por `wallet_fills.py`, nenhuma API pública mudou).
- `hunter_exchanges/pumpfun/close_ata.py` — `CLOSE_ACCOUNT_DISCRIMINATOR` +
  `build_close_ata_instruction` (reexportados por `tx.py`).
- `hunter_meme_executor/fills.py` — `FillRecord` + `decode_fills` (reexportados por `build.py`).

`infra/scripts/check_file_size.py --root .`: `scanned 923 files; 0 over budget, 0 grandfathered`.

## 4. Testes

Reais (R43): buy rotula `(1 513 840, 1 346 200)` nos dois encodings; `unexplained_lamports == 0`
em `build.py` para o buy real; sell real confirma "sem close hoje" (`ata_close_refund is None`).
Sintético: um `CloseAccount` construído à mão confirma o rótulo do refund e sua entrada em
`sol_received_lamports`. Builder: venda cheia fecha e verifica; venda parcial nunca fecha; flag
`close_ata_on_full_sell=False` nunca fecha; saldo desconhecido nunca fecha; `CloseAccount` para
outra carteira é recusado por nome (`close_account_destination_not_wallet`).

## 5. Comandos

```
uv run ruff check packages/exchange-adapters services/meme-executor          # All checks passed!
uv run ruff format --check packages/exchange-adapters services/meme-executor # 181 files already formatted
uv run pyright <11 arquivos>                                                  # 0 errors
uv run python infra/scripts/check_file_size.py --root .                      # 0 over budget
uv run pytest packages/exchange-adapters/tests services/meme-executor/tests \
       -q -m "not live" -k "not persistence"                                 # 871 passed, 2 skipped
```
