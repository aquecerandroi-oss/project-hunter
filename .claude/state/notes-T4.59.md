# T4.59 — tolerância da compra configurável e taxa da compra que pousou com erro

**Data:** 2026-09-18. **Motivo:** mesa real a 0,28 SOL por compra, janela de progresso 2–100 %.
Duas compras morreram com `Custom 6002 = TooMuchSolRequired`: EMRLD (54,8 %, `failed
onchain_error 6002` **depois** do envio — a taxa de rede foi paga por nada) e TIME (52,3 %,
`simulation_failed 6002`). A compra usava fixo `MemeLimits.max_slippage_pct = 0.01` (1 %); a T4.55
só tinha tornado configurável a tolerância das vendas.

## O que mudou

- `services/meme-executor/hunter_meme_executor/send_tuning.py`: `MEME_BUY_MAX_SLIPPAGE_PCT`
  (por cento, padrão `1`, faixa `(0, 20]`; ausente/ilegível/fora da faixa ⇒ padrão, nunca recusa o
  boot). `SendTuning.buy_max_slippage_pct` + `buy_slippage_bps()`. O teto de 20 % é mais apertado
  que o das vendas (50 %) porque na compra a tolerância é dinheiro que pode sair a mais
  (`sol_final × (1 + pct)`).
- `send_path.py`: `build_entry_buy(cfg, read, global_account, ...)` — a compra do laço de entradas,
  com `max_slippage_bps = cfg.send.buy_slippage_bps()`; `entries.py` passou a chamá-la (o arquivo
  estava em 348/350 linhas). Simulação pré-envio e check 20 intocados.
- `heartbeat.py`: `policy_fields(limits, send=None)` publica `buy_max_slippage_pct` no blob
  `policy` (`heartbeat_fields` passa `cfg.send`).
- **Taxa de uma compra que pousou com erro — não era registrada.** O submitter grava
  `fill = NULL` em todo `failed`; `wallet_fills` devolve `()` para `meta.err`; o painel
  (`meme_live_wallet._ORDERS_FEES_TODAY`) soma `fill ->> 'network_fee_lamports'` só onde
  `fill IS NOT NULL`. Agora `send_path.record_failed_onchain_fee` (chamado por
  `record_send_result`, `main.reconcile_once` e `exits._reconcile_sell`) lê a transação por
  `getTransaction` quando o resultado é `failed` + `onchain_error:…` + assinatura, e grava no
  `fill` da ordem `{failed_onchain: true, network_fee_lamports, err, reason, signature, slot}`
  (`repo.record_failed_fill`: `UPDATE … WHERE status = 'failed' AND fill IS NULL`). Falha de
  simulação/preflight/blockhash expirado não pagaram nada e continuam sem `fill`. Todo leitor de
  `fill` como negócio exige `status = confirmed` **e** `FillRecord`; nenhum lê `fill IS NOT NULL`
  (verificado em executor, API e web).
- Docs: `docs/RISK_ENGINE_MEME.md` §3 (linha `max_slippage_pct`) e §6 (parágrafo + tabela das três
  tolerâncias + parágrafo da taxa paga); `docs/ACTIVATION.md` tabela de variáveis da T4.55;
  `docs/DATABASE.md` §40.2 (`fill` de uma linha `failed`).

## A linha do `.env`

```
MEME_BUY_MAX_SLIPPAGE_PCT=3
```

(3 % cobre o que EMRLD/TIME viram; o padrão sem a linha continua 1 %. Acima de 20 % cai no padrão.)

## Testes

`services/meme-executor/tests/test_buy_slippage.py` (29): parser (ausente / válido / fora da faixa /
teto mais apertado que o das vendas), `build_entry_buy` entrega os bps configurados a `build_buy`
(monkeypatch) e uma compra real a 3 % com `max_slippage_bps` no intent, `policy_fields` publica o
campo, `failed_onchain_fill` puro, `record_send_result` grava a taxa só em `failed`+`onchain_error`
+assinatura (nunca em simulação/preflight/expirado/unconfirmed/confirmed/replay), RPC ilegível não
inventa fill, reconcile grava a taxa também.

## Ressalvas

- O check 19 (`slippage_cap`) continua julgando o `max_slippage_pct` do perfil (1 %), e o
  `max_sol_cost_sol` do sizing é calculado com esse 1 %, enquanto a instrução usa o configurado.
  Com `MEME_BUY_MAX_SLIPPAGE_PCT=20` e `MEME_MAX_SOL_PER_TRADE=0.28`, a carteira pode pagar até
  0,336 SOL numa compra — o `intent` grava o `max_sol_cost_sol` real e a contagem do escopo
  (`scope.py`) usa esse número, mas a `MemeDecision` persistida diz 0,2828. Fechar isso exige o
  limite do perfil ler o env (risk-core), fora do escopo desta tarefa.
- `record_failed_fill` (SQL) só tem teste de forma (statement/params); não rodei a suíte de
  integração com Postgres.
