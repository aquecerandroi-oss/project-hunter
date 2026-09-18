# Notas T4.52b-1 — adaptador WS de RPC Solana + fixtures gravadas

Data: 2026-09-18. Escopo: `packages/exchange-adapters/hunter_exchanges/pumpfun/` (`rpc_ws.py`,
`rpc_ws_models.py`, `models.py`, `trade_event.py`) e `infra/scripts/research/2026-09-18-t452b-ws-probe.py`.

## 1. API do `SolanaWsClient` (`rpc_ws.py`)

Uma conexão, N assinaturas do chamador, cada `subscribe_*` devolve um **id lógico** estável
(nunca o `subscription` do servidor, que é reatribuído a cada conexão):

- `await client.subscribe_logs(mentions=[pda], commitment="confirmed")` — cada notificação vira
  `LogsNotification(subscription_id, slot, signature, err, logs, received_at)`.
- `await client.subscribe_account(pda, commitment="confirmed", encoding="base64")` —
  `AccountNotification(subscription_id, slot, data_base64, encoding, owner, lamports, received_at)`.
- `await client.subscribe_slot()` — `SlotNotification(subscription_id, slot, parent, root, received_at)`.
- `await client.unsubscribe(logical_id)` — `True`/`False`.
- `async for notif in client.listen():` — iterador único; conecta, resina o conjunto inteiro em
  cada reconexão, backoff+jitter (mesma disciplina do `ws.py`), idle timeout (60 s), contadores em
  `client.state`: `messages`, `reconnects`, `dropped` (notificação de assinatura não rastreada),
  `malformed`.

**Achado central da tarefa (bug corrigido antes de fechar):** resinar (`_resubscribe_all`) não
pode ser `await`ado *antes* do laço de leitura começar — a resposta do `subscribe` só chega
através desse mesmo laço, então isso trava para sempre numa reconexão. Corrigido rodando o
resinar como `asyncio.create_task` concorrente ao laço; e o mapeamento id-lógico↔id-do-servidor é
gravado **de forma síncrona** dentro de `_resolve_response` (no próprio turno do laço de leitura),
nunca depois, senão uma notificação que chega logo em seguida pode ser descartada por chegar
"antes" do registro (corrida real, pego pelo teste de reconexão com `websockets.serve`).

`trade_event.py` ganhou `trade_events_from_logs(lines)` (decodifica `TradeEvent` de uma lista de
logs, sem filtrar por `program_id` — a assinatura já filtrou por PDA) e
`normalized_curve_trade(event, slot=, signature=, received_at=)` → `NormalizedCurveTrade`
(`models.py`): `lamports` cru (`Decimal`, não convertido — trilha de auditoria), reservas
pós-trade em SOL/tokens (`Decimal`, unidades humanas), `creator`, `mayhem`, `block_time` (do
`TradeEvent.timestamp`), `received_at`.

## 2. Cobertura e lag medidos (`infra/scripts/research/2026-09-18-t452b-ws-probe.py`)

Rodado ao vivo contra o endpoint público `wss://api.mainnet-beta.solana.com`, 5 mints mais
recentes do `frontend-api-v3.pump.fun`, 120 s cada:

- **`confirmed`**: lag `recebido − slot_estimado` (via `slotSubscribe`, `slot×0,4s`) — `logs`
  p50=0,58 s p95=0,61 s; `account` p50=0,53 s p95=0,58 s. Cobertura: todo slot com trade via
  `logsSubscribe` também apareceu como mudança em `accountSubscribe` (overlap 100% nas amostras).
- **`processed`**: `logs` p50=0,42 s p95=0,44 s; `account` p50=0,41 s p95=0,44 s — mais rápido que
  `confirmed` por ~150-170 ms nesta medição (menor que a faixa 0,5-1,5 s do plano, mas o método
  mede lag *relativo* ao próprio `slotSubscribe`, que não tem parâmetro de commitment).
- Sem 429/418 do endpoint público nas duas rodadas; nenhum reconnect.
- Fixtures gravadas (rodada `confirmed`, a que fica no repo): `t452b_ws_logs_notifications_raw.jsonl`
  (13 linhas, 8 com `TradeEvent` decodificável), `t452b_ws_account_notifications_raw.jsonl` (8
  linhas), `t452b_ws_slot_notifications_raw.jsonl` (452 linhas) — todas bem abaixo do teto de 2 MB.

## 3. O que a T4.52b-2 consome

`MintEventState`/`EventBook` vão querer: (a) `NormalizedCurveTrade` por evento de
`logsSubscribe` (via `trade_events_from_logs` + `normalized_curve_trade`) para a deque de trades
de 60 s e o fluxo do criador; (b) `AccountNotification.data_base64`/`owner` direto em
`decode_bonding_curve_account` para o estado por slot; (c) `SlotNotification.slot` como âncora de
lag (`event_slot_lag`). O cliente não sabe nada de pump.fun (fica em `rpc_ws.py`/`rpc_ws_models.py`
puros) — toda semântica de curva entra via `trade_event.py`/`decode.py`, como já era.

## Testes

`packages/exchange-adapters/tests/unit/test_pumpfun_rpc_ws.py` (12 casos: fixtures →
`NormalizedCurveTrade`/`decode_bonding_curve_account`, notificação de assinatura desconhecida,
frames malformados, id matching entre 3 assinaturas concorrentes, reconexão real com
`websockets.serve` que derruba uma vez) + 5 casos novos em `test_pumpfun_trade_event.py`
(`trade_events_from_logs`, `normalized_curve_trade`, fixture real R43). `749 passed, 2 skipped`
em `packages/exchange-adapters/tests -m "not live"`; ruff/pyright limpos; todos os arquivos
tocados ≤ 350 linhas (`rpc_ws.py` 348, `rpc_ws_models.py` 213, `trade_event.py` 346, `models.py`
315).
