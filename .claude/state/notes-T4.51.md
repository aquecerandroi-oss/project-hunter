# T4.51 — o saldo da carteira envelhece pelo relógio, não pela última ordem

**Data:** 2026-09-17. **Escopo:** `services/meme-executor` (novo `wallet_refresh.py`, `config.py`,
`main.py`, `heartbeat.py`) e `services/meme-executor/tests` (novo `test_wallet_refresh.py`,
extensão de `test_live_persistence.py`).

## 1. A causa

`state.wallet_lamports`/`state.wallet_read_at` só eram escritos dentro de
`entries.handle_candidate` (T4.8), linha 152 — ou seja, só quando havia uma proposta viva para
admitir naquele tique de 1 s. `exits.py` nunca lê a carteira. Com a mesa quieta (toda posição
fechada, como a DOPEY às 09:29Z), nada mais chamava esse trecho: o heartbeat continuou publicando
`wallet_sol_balance = equity_sol = 0,645172518` de quando a DOPEY ainda estava aberta, até as
13:03Z registradas no defeito, enquanto a RPC pública dizia 0,672509616 SOL às 13:4xZ. `equity_sol`
e `daily_loss_sol` são recalculados a cada heartbeat a partir desse mesmo `state.wallet_lamports` —
então os dois herdavam a mesma estagnação. As checagens do motor de risco
(`wallet_over_max_sol`, `daily_loss_cap_reached`) continuam corretas porque fazem sua própria
leitura fresca da RPC a cada `handle_candidate`; o que estava estagnado era só o número publicado
para `/meme/mesa` e para o próprio heartbeat.

## 2. A mudança

`wallet_refresh.py` (novo, 65 linhas): `wallet_refresh_once(ctx)` — sem `ctx.signer` (processo
inerte/sem chave), não lê nada; com signer, chama `ctx.chain.wallet(pubkey)` em thread, com prazo
duro `MEME_WALLET_REFRESH_TIMEOUT_S` (padrão 1,5 s, `config.wallet_read_timeout_s`, mesmo padrão do
`risk_read.py` da T4.45). **Sucesso** grava `wallet_lamports`/`wallet_read_at`; **qualquer falha**
(timeout ou erro de RPC) não toca nenhum dos dois — mantém o último valor conhecido, conta
`rpc_errors` e loga `meme_executor_wallet_refresh_failed`. Nunca um segundo escritor concorrente:
é a mesma dupla de campos que `handle_candidate` já escreve, o mais recente vence (mesmo padrão de
`program_check_once`/`check_program_at_boot` para `program_last_deploy_slot`).

`main.py`: `kill_switch_once` (chamado a cada `kill_switch_poll_s`, 10 s por padrão, com ou sem
evento) agora também chama `wallet_refresh_once(ctx)`, ao lado do `gates_reload_once` e do
`program_check_once` — ambos já rodam nesse mesmo tique incondicional.

`heartbeat.py`: novo campo `wallet_balance_stale_s` = segundos desde `wallet_read_at` até `now`,
sempre publicado (não só numa falha) — é a forma de a mesa ver o número envelhecendo em vez de
inferir por ausência de mudança.

`config.py`: novo campo `wallet_read_timeout_s` (env `MEME_WALLET_REFRESH_TIMEOUT_S`, padrão 1,5 s,
`max(0.1, …)` como os demais tempos-limite do arquivo).

## 3. Cadência

Antes: o saldo publicado só mudava quando havia uma proposta a admitir — no cenário do defeito,
mais de 3 h de atraso (09:29Z → 13:03Z, e o heartbeat ainda estaria parado se nenhuma ordem tivesse
vindo). Depois: no máximo `kill_switch_poll_s` (10 s) de atraso, mesa quieta ou não, e a leitura tem
teto de 1,5 s — nunca compete com o tique de entradas (1 s) nem com o de saídas.
`equity_sol`/`daily_loss_sol` seguem consistentes automaticamente, porque já eram recalculados a
cada heartbeat a partir de `state.wallet_lamports` — bastava esse campo parar de ficar velho.

## 4. Testes e resultados reais

Novo `services/meme-executor/tests/test_wallet_refresh.py` (unitário, sem Docker, 4 casos):
sem signer não lê a cadeia; leitura boa publica o saldo fresco; leitura que falha mantém o saldo
anterior e conta o erro (inclusive quando a leitura que falhou "veria" 0 se fosse confiada); leitura
que estoura o prazo (0,2 s de atraso simulado contra teto de 0,01 s) é tratada como falha e nunca
toca o estado depois do prazo.

Extensão de `test_live_persistence.py` (integração, Postgres real) com dois casos que reproduzem o
cenário exato do defeito (mesa sem candidato nenhum): `wallet_refresh_once` sozinho atualiza
`wallet_sol_balance`/`equity_sol` do heartbeat para 0,672509616 SOL sem nenhuma ordem; e uma falha
de RPC simulada depois de um saldo bom mantém 0,645172518 publicado (nunca cai para o 0 que a
cadeia falsa "responderia") e `wallet_balance_stale_s` cresce.

```
uv run pytest services/meme-executor/tests/test_wallet_refresh.py -q -p no:cacheprovider
....                                                                     [100%]
4 passed in 0.96s

uv run pytest services/meme-executor/tests -q -p no:cacheprovider -m "not live"
........................................................................ [ 37%]
........................................................................ [ 74%]
..................................................                       [100%]
194 passed in 116.11s (0:01:56)

uv run ruff check <arquivos tocados>          → All checks passed!
uv run ruff format --check <arquivos tocados> → 6 files already formatted
uv run python infra/scripts/check_file_size.py → scanned 924 files; 0 over budget, 0 grandfathered
uv run pyright <arquivos de produção tocados>  → 0 errors, 0 warnings, 0 informations
```

## 5. Limites honestos

- Não toquei `packages/core/hunter_core/universe.py` nem
  `services/meme-worker/hunter_meme_worker/repo_boards.py` (fora de escopo, outra tarefa em curso).
- `wallet_balance_stale_s` é sempre publicado (não só numa falha) — decisão deliberada: um heartbeat
  antigo por qualquer motivo (processo reiniciado antes desta tarefa, `wallet_refresh_once` nunca
  chamado) fica visível pelo próprio número, não só pela ausência de uma falha registrada.
- Não medi em produção. O que vai medir: `wallet_balance_stale_s` e `wallet_read_at` no próximo
  heartbeat real, e `rpc_errors` se a RPC pública/própria começar a falhar mais.
