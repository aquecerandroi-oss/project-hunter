# Prova T3.5 — 30 minutos do `execution-worker` no stack local (2026-09-07)

**Comando:** `docker compose -f infra/docker/docker-compose.yml up -d execution-worker` +
`docker compose ... run -d --name t35-proof --entrypoint python execution-worker
services/execution-worker/proof/run_proof.py --minutes 30 --slug ever-t35-proof2`.
**Imagem:** `hunter-api:dev`, construída do worktree desta tarefa.
**Janela:** `2026-09-07T06:57:09Z → 07:27:10Z` (30 min exatos, `Exited (0)`).
**Carteira:** aberta pelo próprio roteiro como `hunter_worker` (§19.6),
`portfolio_id = 01a07aa8-0c9d-7b57-bb59-9f4900e8b079`, R$100.000 a 5,00 → **20.000,0000000000 USDT**.

**A fonte de mercado é rotulada.** O roteiro escreve nas **chaves spot reais**
(`mkt:proof:spot:PRFUSDT:book` e `:trades`, no msgpack exato que o `market-worker` grava) com
`exchange = "proof"`: nada que ele escreveu pode ser lido como Binance. O `avgPriceMins` do mercado
é **0** — o caso "use o último preço" da própria Binance (T3.0a §5) — porque ninguém coleta
`avgPrice` ainda (notes-T3.5 §5.2). O worker leu tudo pelo `RedisSpotMarketData`, sem nenhum atalho
de teste no caminho.

## 1. Linha do tempo, como aconteceu

| Instante (UTC) | Quem | O quê |
|---|---|---|
| 06:57:09 | roteiro | carteira aberta: carteira + trava + âncora + 1º ponto da curva + auditoria, um commit |
| 06:57:55 | roteiro | **uma ordem manual** pela admissão compartilhada: `approved`, `qty = 18,518`, `binding_constraint = risk_per_trade`, reserva `held` |
| 06:57:56 | worker | `entry_deferred reason=book_before_latency` — o livro na mão era **anterior** à decisão; nada escrito, tentativa **não** gasta |
| 06:57:57 | worker | fill: `18,518 @ 100,01`, taxa `0,018518 PRF`, posição `18,499482`, stop `97,5` armado, reserva → `consumed` |
| 06:58:01 | worker | 1º ponto da curva `1m`: equity `19.997,96302` |
| 07:02:09 | roteiro | **gap sintético**: a fita passa a imprimir `95,00` (o stop é `97,5`; nenhum preço intermediário é negociado) |
| 07:02:1x | worker | 1ª tentativa de saída: `pending_degraded` (`book_before_latency`) — ordem escrita, **fill nenhum**, intenção segue `open` e degradada |
| 07:02:1x | worker | 2ª tentativa, **identidade própria**: `18,499 @ 95,00`, taxa `1,75740500 USDT` |
| 07:06:28 | operador | `docker kill` + recriação do contêiner — o worker volta e continua sem nada em memória |
| 07:27:10 | roteiro | fim: 30 pontos de curva, 3 ordens, 2 fills, 1 trade, `latch = ACTIVE`, `Exited (0)` |

## 2. O que a prova **encontrou** (e que virou correção)

Duas coisas, as duas em `services/execution-worker/**`, as duas com o comportamento anterior
observado antes da correção:

1. **A primeira rodada (06:47–06:57) recusou a entrada em definitivo.**
   `orders.status = rejected, reason = book_before_latency`: a decisão saiu às 06:48:23,857 e o
   livro mais novo no hot state era o de 06:48:22 — o *anterior* a ela. A tentativa única foi gasta
   numa foto que o contrato nem sequer autoriza usar. **Correção:** a entrada só é tentada contra um
   livro **elegível**; enquanto não é, a proposta é adiada (nada escrito, nada gasto) e, se o livro
   nunca chegar, a reserva expira em 30 s e é liberada com o motivo. Na segunda rodada o mesmo
   evento aparece como `entry_deferred` e o fill acontece 1,2 s depois.
2. **`trade_from_the_future` em prints que chegaram durante o próprio ciclo.** O `now` era tomado no
   topo do laço e a fita era lida depois; um print que aterrissava no meio virava defeito e o lote
   inteiro saía `unavailable` — um stop adiado um ciclo pela nossa contabilidade.
   **Correção:** o instante da avaliação é recarimbado **depois** da leitura da fita
   (`run_protection_cycle(..., clock=...)`); sem `clock` (nos testes) ele continua sendo exatamente
   o `now` dado. **Durante os 30 minutos da rodada final não houve nenhum
   `protection_tape_unavailable`.**

## 3. Reconciliação — os números, exatos

Ledger, lido do banco ao fim (`orders`, `fills`, `trades`):

```
 side | purpose |  status   |      qty      |  filled_qty   | avg_fill_price |       reason
 buy  | entry   | filled    | 18.5180000000 | 18.5180000000 | 100.0100000000 |
 sell | stop    | submitted | 18.4994820000 |  0.0000000000 |                | book_before_latency
 sell | stop    | filled    | 18.4994820000 | 18.4990000000 |  95.0000000000 |

      qty      |     price      |     fee      | fee_asset |  slippage_bps
 18.5180000000 | 100.0100000000 | 0.0185180000 | PRF       |   1.0000000000
 18.4990000000 |  95.0000000000 | 1.7574050000 | USDT      | 256.4102564100

      qty      |  entry_price   |  exit_price   |      pnl       |     fees     | exit_reason
 18.4990000000 | 100.0100000000 | 95.0000000000 | -96.2893801800 | 3.6093901800 | stop
```

A conta que fecha, sem tolerância:

- **caixa** = `20.000 + 1.757,405 − 1.851,98518 − 1,75740500` = **19.903,662415**
  (creditado + vendido − comprado − taxas em moeda de cotação; a taxa em ativo-base **não** debita
  caixa, ela reduziu a quantidade recebida);
- **pó** = `18,499482 − 18,499` = **0,000482** unidades, abaixo do `min_qty = 0,001` → invendável,
  vale `0,000482 × 95` = **0,04579**;
- **patrimônio** = `19.903,662415 + 0,04579` = **19.903,708205**, que é **exatamente** o número no
  `hb:execution:paper` e no último ponto da curva;
- **resultado do trade** = bruto `18,499 × (95 − 100,01)` = `−92,679990`, menos os custos
  `1,85198518` (taxa da entrada em equivalente-cotação) `+ 1,75740500` (taxa da saída) = `3,60939018`
  → **−96,28938018**, que é o `pnl` gravado. Cada custo contado **uma** vez.
- **pior que o plano, publicado:** stop planejado `97,5`, execução `95,00` →
  `slippage_vs_plan_bps = 256,4102564100`. Nada puxa o preço de volta ao stop.

## 4. Estado final e supervisão

```
portfolio_equity_snapshots:  1m → 30 pontos (06:58:01 → 07:27:36), equity 19.997,96302 → 19.903,708205
                             1h →  1 ponto (a abertura; nenhuma virada de dia em 30 min)
outbox_events (key=carteira): executions.completed 3 · positions.updated 2 · proposals.decided 1
audit_logs:                  portfolio.opened 1 · proposal.admitted 1 · proposal.reservation_consumed 1
                             execution.entry_filled 1 · execution.exit_pending 1 · execution.exit_filled 1
                             portfolio.equity_point.stale_marks 1
participation_consumptions:  reserved 1.851,80 · executed 1.851,98518 (o bruto real, não o reservado)
positions:                   qty 0,000482 · status closing · realized_pnl −92,679990
portfolio_exit_intents:      state blocked_residual · filled_qty 18,499
portfolios.kill_switch_state: ACTIVE  (a queda foi de 0,48 %, abaixo do aviso de 1 %)
```

`GET /ready` ao fim — **200**, os sete checks verdes:

```
{"database": true, "redis": true, "paper_schema": true, "kill_switch_legible": true,
 "mtm_fresh": true, "protection_prompt": true, "outbox_not_lagging": true}
```

`hb:execution:paper` ao fim:

```
equity 19903.70820500000000000000 · kill_switch ACTIVE · open_positions 1 · pending_requests 0
degraded_protections 0 · protection_delay_s 0.0 · errors 0 · paper_autonomy false
last_mtm 07:27:36 · last_protection 07:27:38 · last_kill_switch_read 07:27:36
```

**Exceções: 0.** `grep -icE "traceback|execution_cycle_failed|\[error"` nos logs do contêiner durante
toda a rodada → **0**. Avisos: 4 (`mtm_marks_stale` / `equity_point_stale_marks`, dois pontos em
trinta, cada um gravado com `marks_stale = true` e auditado). Os 38
`protection_tape_unavailable reason=stale_trade` do log **começam às 07:27:19**, depois de o roteiro
parar de alimentar a fita: sem fita, o veredito é `unavailable` — que é exatamente o comportamento
certo, e não um fill inventado.

## 5. O que esta prova **não** prova

- **`kill_switch.changed` não foi exercitado aqui**: a queda de 0,48 % não move a trava. A publicação
  pelo worker (e o cancelamento das pendentes sob BLOQUEADO, e a saída de proteção continuando
  durante o bloqueio) está provada em
  `services/execution-worker/tests/test_mtm_and_kill_switch.py`, com o bloqueio produzido por um MTM
  **real**, nunca escrevendo a coluna à mão.
- **O `kill -9` de 07:06:28 aconteceu depois da saída**, não entre a escrita e o ACK. As fronteiras
  de crash com estado meio escrito estão nos testes de integração
  (`test_restart_recovery.py`), que reconstroem a intenção e as tentativas aplicadas só do Postgres.
- **A ordem manual entrou pela admissão compartilhada chamada pelo operador**, não pela rota da API:
  `trade_proposals` ainda não tem coluna para a geometria do pedido, então um pedido arquivado pela
  API não pode ser decidido a partir da linha (notes-T3.5 §5.1). Este é o bloqueante da T3.8.
- **Nenhuma ativação de produção.** `ENABLE_LIVE_TRADING=false` nos dois composes, e o processo
  recusa subir se for `true`.

## 6. Sujeira deixada no stack local, de propósito

O contêiner `docker-execution-worker-1` ficou **de pé** (é serviço novo do compose) e o banco local
tem a organização `ever-t35-proof2` com a carteira da prova, o mercado `proof:PRFUSDT` e as linhas
acima. O contêiner `t35-proof` saiu com 0 e pode ser removido (`docker rm t35-proof`). Nada disso
tocou a VPS.
