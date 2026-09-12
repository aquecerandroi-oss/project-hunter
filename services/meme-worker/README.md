# meme-worker — o radar da pump.fun (`HUNTER_ROLE=meme`)

Coletor de memecoins: descobre mints pelo WebSocket do PumpPortal, acompanha o
estado da bonding curve dentro do orçamento medido de **60 requisições/60 s** do
`frontend-api-v3.pump.fun`, reconcilia os maiores contra um RPC Solana e escreve
**uma linha de feature por minuto fechado** por mint rastreado.

**Só monitoramento.** Nada aqui vira ordem: nenhum módulo importa
`packages/risk-core`, `hunter_core.execution` ou o caminho de execução, e
`hunter_app` tem `SELECT` e nada mais nas cinco tabelas
(`docs/plans/T4-MEME-RADAR.md` §0, `docs/DATABASE.md` §33).

## Como subir

```bash
# local, container no ar e coletor desligado (o padrão)
docker compose -f infra/docker/docker-compose.yml --profile meme up -d meme-worker

# local, coletando
MEME_ENABLED=true docker compose -f infra/docker/docker-compose.yml --profile meme up -d meme-worker

# VPS
MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update
```

Dois interruptores de propósito: o **perfil** decide se o container existe,
`MEME_ENABLED` decide se ele coleta. Desligado, o processo serve `/health`,
`/ready` e `/metrics` e responde `radar: "disabled"` no readiness — um coletor
desligado tem de ser visivelmente desligado. Runbook completo em
`docs/DEPLOYMENT.md` §3.6.

## Os cinco loops (`main.py`, um `TaskGroup`)

| Loop | Cadência | O que faz |
|---|---|---|
| `discovery` | stream | consome `subscribeNewToken`/`subscribeMigration` (os dois canais grátis), faz upsert em `meme_tokens` e escreve uma lacuna a cada reconexão |
| `poll` | 60 s | gasta o orçamento REST no conjunto rastreado — tier jovem primeiro, menos recentemente consultado primeiro — e grava `meme_curve_snapshots` |
| `reconcile` | 300 s | lê o top-K por market cap direto da cadeia; as duas leituras ficam, distinguidas por `source` |
| `fold` | 5 s (escreve no fechamento do minuto) | uma linha de `meme_features_1m` por mint rastreado, com NULL **e motivo** onde a fonte grátis não responde |
| `retention` | 1 h | poda `meme_tokens` em lotes, atrás de `SET LOCAL app.meme_retention = 'on'` |
| `board-{new,graduating,graduated,movers}` (T4.2c) | stream | consome `/ws/trenches` por board (snapshot + deltas por versão, backoff do site), grava `meme_board_observations` por minuto fechado com o intervalo de exposição (censura na reconexão) e alimenta o tracker com os mints `pump`/SOL de `new`/`graduating` |
| `trades` (T4.2c) | 10 s | a fita `swap-api` (900/60 s): aposta aberta > `graduating` > `new` > resto, intervalos 10/10/20/60 s, cursor até a alta-marca por mint → `meme_trades` (`source='swap_api'`, dedupe pela PK) |
| `risk` (T4.2c) | 60 s | `GET /in-memory-coin/{mint}` (≤ 1/mint/5 min, apostas abertas e `graduating`) → `meme_risk_snapshots` (jsonb cru + colunas extraídas) |
| `heartbeat` (T4.2c) | 15 s | `tracked`, `budget_used_60s`, `gaps_60s`, `ws_malformed_60s`, `last_snapshot_observed_at`, `lag_s`, `trenches_connected`, `trenches_patches_60s`, `swap_api_used_60s` e o JSON `sources` em `hb:meme:radar` |
| `lab` (T4.6) | 60 s | o Lab de papel: porta da EXP-M1 sobre o minuto fechado → `meme_proposals`; fill na 1.ª fotografia posterior à decisão → `meme_paper_bets`; marca, saídas e `sell_now` a cada fotografia nova, venda na fotografia seguinte; `lab_*` no heartbeat `hb:meme:radar`. Atrás de `MEME_LAB_ENABLED` (padrão ligado) |

## O que ele mede desde a T4.2c, e o que continua `NULL` com motivo

As colunas de holders (`holders`, `top10_share`, `dev_share`, `snipers`, com
`holders_observed_at`/`holders_source`) vêm do board do site ou da leitura de
risco; as da fita (`buys_1m`, `sells_1m`, `unique_buyers`, `buy_sell_ratio`,
`net_sol_flow_1m`, `curve_volume_1m_sol`, `creator_sold`, `creator_net_seller`)
do `swap-api`. **Todas obedecem a uma regra só** (`features_tape.py`): só entra
no minuto `T` o que tinha chegado (`received_at <= T`) — um trade do minuto
recebido depois do fecho está em minuto nenhum.

`NULL` com motivo continua sendo o produto (MUST-FIX 1 da Astra): `no_trade_feed`
até a primeira leitura da fita de um mint, `no_holders_reader` até um board ou
uma leitura de risco falar dele, `no_sells` numa razão compra/venda sem vendas,
`rate_limited`/`unsupported_quote` quando a fonte recusou.

`curve_progress_pct` usa `1 − real/initial` com denominador **observado** (a
primeira leitura com `real_sol_reserves = 0`), nunca a constante de 793,1 M que
circula em blog; sem essa observação o valor é `NULL` com `denominator_unknown`.

## Testes

```bash
timeout 290 uv run pytest services/meme-worker/tests/test_tracker.py services/meme-worker/tests/test_features.py -q
timeout 290 uv run pytest services/meme-worker/tests/test_paper_engine.py services/meme-worker/tests/test_proposals.py -q   # o Lab, puro
timeout 290 uv run pytest services/meme-worker/tests/test_tracker_priority.py services/meme-worker/tests/test_features_tape.py services/meme-worker/tests/test_boards.py services/meme-worker/tests/test_trades.py services/meme-worker/tests/test_sources.py -q   # T4.2c, puro (fixtures reais)
timeout 590 uv run pytest services/meme-worker/tests/test_boards_trades_persistence.py -q   # testcontainers (T4.2c: boards, fita, risco, fold com as três fontes)
timeout 290 uv run pytest services/meme-worker/tests/test_persistence.py -q       # testcontainers (coletor)
timeout 590 uv run pytest services/meme-worker/tests/test_lab_persistence.py -q   # testcontainers (Lab: fill, saídas, look-ahead, vistas, grants)
```

Os dois primeiros rodam offline sobre as **fixtures gravadas da T4.1**
(`packages/exchange-adapters/tests/fixtures/pumpfun/`), pelo normalizador real.
O terceiro sobe um Postgres, aplica as migrações até o head e prova o que só
existe no banco: upsert idempotente que preenche buraco e nunca apaga valor,
roteamento de partição, `mcap_sol` gerado, os CHECKs bicondicionais de motivo e o
marcador que a retenção precisa declarar.
