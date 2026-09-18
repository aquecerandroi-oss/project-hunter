# T4.60 — o freio de perda diária conta o que a tesouraria pôs na carteira

**Data:** 2026-09-18. **Motivo:** defeito com dinheiro real às 13:12 BRT. A posição YOU perdeu
0,0395 SOL (comprou 0,0516, vendeu 0,0121, saída pelo trailing, −0,77 R). Às 13:12:06 a tesouraria
(T4.54) trocou 5,75 USDC → 0,0516 SOL porque a carteira caiu abaixo do piso. O heartbeat seguinte
publicou `daily_loss_sol = 0` (`equity_sol 0,732 > day_start_sol_equity 0,686`): o freio
(`MEME_DAILY_LOSS_CAP_SOL` 0,15, check 18 `daily_loss`, e o `assess` do kill switch) era
`day_start_equity − equity`, **cego** a entradas da tesouraria. Com a tesouraria ligada, o teto
nunca dispararia — cada perda era reposta em USDC.

## O que mudou

- `packages/risk-core/hunter_risk_meme/inputs.py`: `MemeWalletState.treasury_inflow_today_sol`
  (`Decimal ≥ 0`, padrão 0) e `daily_loss_sol = max(0, day_start + inflow − equity)`. O motor
  continua puro: o número entra como argumento. `assess`, `daily_loss_check` e `sizing` (folga do
  teto diário) herdam a fórmula sem mudança.
- `services/meme-executor/hunter_meme_executor/treasury_db.py`: `sol_inflow_since(session, since)`
  — `Σ coalesce(sol_out_filled, sol_out_quoted)` das linhas `status ∈ {submitted, confirmed}` com
  `requested_at ≥ since` (índice `ix_meme_treasury_swaps_requested_at`). Uma linha `submitted`
  ainda não tem `sol_out_filled`; contar o cotado superestima a entrada ⇒ superestima a perda ⇒
  lado fechado.
- **Novo** `services/meme-executor/hunter_meme_executor/treasury_inflow.py`:
  - `TreasuryInflowReader`: um SELECT por tique do kill switch, cache de 10 s, releitura imediata
    quando `day_start_utc` muda; **falha mantém o último valor conhecido (nunca zero)**, conta
    `read_failures` e nomeia `last_error`; antes da primeira leitura o valor é `None`.
  - `treasury_inflow_once(ctx, now)`: chamado em `main.kill_switch_once` **depois** de
    `treasury_once` (uma troca que acabou de pousar entra na conta no mesmo tique).
  - `ensure_anchor(ctx, now, equity)` (movido de `entries.py`, que estava em 348/350 linhas):
    relê o influxo nos dois ramos; âncora nova = `max(0, equity − influxo_hoje)` — um *top-up* às
    00:05 não vira "perda" quando a primeira candidata ancora o dia às 09:00; com influxo ilegível
    **não** ancora e devolve `None`; a âncora de ontem nunca é devolvida como a de hoje.
- `context.py`: `ExecutorContext.treasury_inflow` (default_factory, sem sessão no construtor).
- `entries.py`: `anchor = await ensure_anchor(...)`; `anchor is None or inflow is None` ⇒ recusa
  `day_anchor_unavailable` com `treasury_inflow_*` no `admission`; `wallet_from(...,
  treasury_inflow_today_sol=inflow)`.
- `admission.py`: `wallet_from` aceita `treasury_inflow_today_sol` (padrão 0 para quem não passa).
- `heartbeat.py`: `daily_loss_fields(anchor, equity, inflow)` (puro, testável) publica
  `day_start_utc`, `day_start_sol_equity`, `equity_sol`, `treasury_inflow_today_sol` e
  `daily_loss_sol = day_start + inflow − equity`; influxo desconhecido ⇒ `daily_loss_sol` vazio,
  nunca `0`. Mais `treasury_inflow_read_at`/`_read_failures`/`_error` (`describe()`). A API
  (`meme_live.py`) já lê `daily_loss_sol` do heartbeat, então `/meme/mesa` herda o número certo
  sem mudança.
- Docs: `docs/RISK_ENGINE_MEME.md` §2 (tabela `MemeWalletState`), §4 (check 18), §7 (fórmula +
  parágrafo T4.60) e §16.3 (tesouraria × freio).

## Testes

- `packages/risk-core/tests/unit/meme/test_treasury_inflow.py` (5): caso YOU (0,0395, não 0);
  ganho com influxo não vira perda negativa; o teto 0,15 dispara com três *top-ups* de 0,0516 só
  quando o influxo é contado (`assess` ⇒ `TRADING_DISABLED`, latched); check 18 registrado com
  `value = 0,15` mesmo com a recusa de check 1 primeiro; influxo negativo é recusado.
- `services/meme-executor/tests/test_treasury_inflow.py` (12): leitor (soma desde a meia-noite
  SP; cache 10 s; virada de dia força releitura; falha mantém o último valor; falha antes da
  primeira leitura ⇒ `None`), âncora (top-up antes da primeira âncora não é contado duas vezes;
  influxo ilegível ⇒ sem âncora; mesmo dia só sobe o pico **e** lê o influxo; âncora de ontem
  nunca é a de hoje) e heartbeat (caso YOU; teto 0,15; sem âncora/equity ⇒ vazio).

## Residuais (não feitos aqui)

- `peak_sol_equity` (drawdown) continua bruto: um *top-up* sobe o pico. O drawdown não é check nem
  gatilho hoje; documentado em §7.
- A âncora do dia ainda só é escrita na primeira admissão do dia (não no tique); o heartbeat mostra
  a âncora de ontem até lá (comportamento anterior, inalterado).
- Nenhuma migração: a leitura usa `meme_treasury_swaps` como está (`0051`).
