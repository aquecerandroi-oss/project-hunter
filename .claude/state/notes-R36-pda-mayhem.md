# R36 — a conta da curva em moedas Mayhem: o que o executor lê e compra (2026-09-16)

**Resposta direta: o executor está seguro — sim.** Ele deriva o PDA `["bonding-curve", mint]` na
leitura e na instrução, e o campo `meme_tokens.bonding_curve` **nunca** entra no caminho de execução.
O achado lateral do R33 (KB-0115 §7) está invertido: quem mente é a linha, não o PDA.

## 1. O que o código faz (leitura)

- `services/meme-executor/hunter_meme_executor/chain.py:103` — `ChainReader.curve(mint)` chama
  `get_account(bonding_curve_address(mint))`, o PDA derivado. Não há parâmetro de endereço.
- `packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py:214,243` —
  `build_buy_instruction`/`build_sell_instruction` derivam `curve = bonding_curve_address(intent.mint)`
  e a ATA da curva a partir dele; o *remaining account* `["bonding-curve-v2", mint]` (`tx.py:132`)
  também é derivado por mint. Nenhum endereço vem de banco.
- `services/meme-executor/hunter_meme_executor/build.py:241` — só o **flag** `is_mayhem_mode` lido da
  conta decide o `fee_recipient` (lista reservada vs. normal). Nada de endereço de curva.
- Não existe `pumpfun/pdas.py` (o brief citou esse caminho): a derivação mora em `tx.py`.

## 2. O que o banco tem (VPS, SELECT apenas, 16/09/2026)

7 dias: 135 905 `meme_tokens`, 112 108 com `bonding_curve`, 34 846 com `mayhem_state`.

| stored `bonding_curve` | linhas (7 d) | mayhem_enabled |
| --- | --- | --- |
| `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s` (um único valor, repetido) | **13 615** | 13 615 (100 %) |
| qualquer outro valor | 98 493 | — |

`GROUP BY bonding_curve HAVING count(*) > 1` devolve **exatamente uma** linha: esse endereço. Ou
seja, **13 615 mints divergentes**, todos Mayhem, e nenhuma outra duplicata em 7 dias.

Amostra de 200 mints (100 Mayhem + 100 não-Mayhem) com o helper rodado localmente
(`bonding_curve_address`): 43/100 Mayhem divergem, 0/100 não-Mayhem divergem, 57/100 Mayhem batem.
Nenhum divergente é `["bonding-curve-v2", mint]`, `["mayhem-state", mint]` nem o vault ATA do mint.

## 3. Por que a linha está errada e o PDA está certo

`BwWK17cb…` **é** `mayhem_pdas().sol_vault` = PDA `["sol-vault"]` do programa
`MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e` — uma conta compartilhada por todas as moedas Mayhem.
Leitura na mainnet (`api.mainnet-beta.solana.com`, `getAccountInfo`, 16/09):

- `BwWK17cb…` → owner `11111111111111111111111111111111` (System Program), **0 byte de dado**,
  54 320,006 SOL. Não é curva de ninguém.
- mint `3aYHwMeoXeEqtLnap1TByBfmh2CHnVexX9pqMUHFpump` → PDA derivado
  `Ck72XTyTQYsksoHeHBB48eyY5hmHNcwESXJKEeSCSrHQ`, owner `6EF8rrec…` (pump.fun), 153 bytes de dado,
  decodifica como `BondingCurve` viva: `is_mayhem_mode=true`, `complete=false`,
  `virtual_sol_reserves=26 430 445 402`.

Origem provável da contaminação: o frame de `create` do PumpPortal (`normalize.py:135`,
`bondingCurveKey`) traz o sol-vault do Mayhem em vez da curva; `discovery.py:85` grava como veio.

## 4. O que aconteceria se "corrigíssemos" para usar `meme_tokens.bonding_curve`

Provado por mutação (monkeypatch de `bonding_curve_address` para o vault): a leitura
levanta `MalformedMessage: account owner '111…1' is not the pump.fun bonding curve program`. Em
produção esse erro sobe de `_read_chain` e é engolido pelo `except Exception` de
`entries.handle_candidate:147` → contador `rpc_errors` + log `meme_live_rpc_unreachable`, **sem
refusal nomeado**, e o candidato volta a ser tentado para sempre. Se a conta *decodificasse* (não
decodifica: 0 byte), a compra iria para uma conta de 54 mil SOL de outro programa — a simulação
falharia com `AccountNotInitialized`/`ConstraintSeeds`, mas o erro seria opaco. Conclusão: **não
mudar**; se algum dia for preciso usar o campo, validar `owner == 6EF8rrec…` + discriminador
`17b7f83760d8ac60`, não confiar na linha.

## 5. Mayhem é recusada antes de montar transação?

Sim, em duas camadas, ambas antes de qualquer byte assinado:

1. seleção de candidatas — `exclude_mayhem` (ligado por padrão) recusa `mayhem_curve` /
   `mayhem_unknown` (`packages/indicators/hunter_indicators/meme/rules_criteria.py:53`), lendo os
   flags do banco;
2. admissão — `mayhem_policy_check` (`packages/risk-core/hunter_risk_meme/checks.py:278`): com
   `curve.is_mayhem_mode=true` (flag da conta lida agora) e `MemeContext.mayhem_agent_state_known`
   que o executor **nunca** liga (`admission.context_from` não passa o campo; default `False`),
   o check sai `UNAVAILABLE`/`mayhem_state_unknown`; `evaluate.py:75` exige `all(c.passed)`, então
   `approved=False` e `entries.py` recusa **antes** de `build_buy`.

Ordem confirmada em `entries.handle_candidate`: `_read_chain` → `admit` → `if not decision.approved:
_refuse(...)` → só então `build_buy`.

## 6. Efeito colateral no radar (não é dinheiro, mas é ruído)

`services/meme-worker/hunter_meme_worker/collect.py:260` passa `tracked.bonding_curve` cru para
`get_curve_state` — para os 13 615 mints Mayhem isso lê o sol-vault e falha fechado
(`meme_chain_read_failed`, contador `meme_polls_total{outcome=error}`), gastando orçamento de RPC no
top-K. A cobertura de dados não se perde porque o caminho em lote (`rpc_curves.curve_addresses`)
deriva o PDA: nos últimos 2 dias, mints Mayhem com o vault gravado têm snapshot `solana_rpc` em
7 061/7 123 (99,1 %), contra 10 930/10 997 (99,4 %) dos demais Mayhem. Correção sugerida (fora desta
tarefa): `reconcile_once` derivar o PDA em vez de usar a coluna, ou validar o dono antes.

## 7. Teste de regressão

`services/meme-executor/tests/test_mayhem_curve_account.py` (7 casos): pina que o endereço gravado é
o sol-vault compartilhado, que `ChainReader.curve` lê o PDA por mint e **nunca** pede o vault, e que
uma curva Mayhem chega ao motor com o flag e é recusada por nome (`mayhem_state_unknown`). A corrida
mutante acima faz 4 dos 7 falharem.
