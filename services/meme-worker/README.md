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
| `lab` (T4.6) | 60 s | o Lab de papel: porta da EXP-M1 sobre o minuto fechado → `meme_proposals`; fill na 1.ª fotografia posterior à decisão → `meme_paper_bets`; marca, saídas e `sell_now` a cada fotografia nova, venda na fotografia seguinte; `lab_*` no heartbeat `hb:meme:radar`. Atrás de `MEME_LAB_ENABLED` (padrão ligado) |

## O que ele **não** mede, e por quê

Quatro colunas são `NULL` com motivo em **toda** linha desta fatia — e isso é o
produto, não uma lacuna escondida (MUST-FIX 1 da revisão da Astra: ausência de
feed lida como "ninguém comprou" foi o erro mais grave do desenho original):

- `unique_buyers`, `buy_sell_ratio` → `no_trade_feed` (o canal de trades do
  PumpPortal é pago; o decodificador on-chain é a T4.2b);
- `top10_share`, `creator_sold` → `no_holders_reader`.

`curve_progress_pct` usa `1 − real/initial` com denominador **observado** (a
primeira leitura com `real_sol_reserves = 0`), nunca a constante de 793,1 M que
circula em blog; sem essa observação o valor é `NULL` com `denominator_unknown`.

## Testes

```bash
timeout 290 uv run pytest services/meme-worker/tests/test_tracker.py services/meme-worker/tests/test_features.py -q
timeout 290 uv run pytest services/meme-worker/tests/test_paper_engine.py services/meme-worker/tests/test_proposals.py -q   # o Lab, puro
timeout 290 uv run pytest services/meme-worker/tests/test_persistence.py -q       # testcontainers (coletor)
timeout 590 uv run pytest services/meme-worker/tests/test_lab_persistence.py -q   # testcontainers (Lab: fill, saídas, look-ahead, vistas, grants)
```

Os dois primeiros rodam offline sobre as **fixtures gravadas da T4.1**
(`packages/exchange-adapters/tests/fixtures/pumpfun/`), pelo normalizador real.
O terceiro sobe um Postgres, aplica as migrações até o head e prova o que só
existe no banco: upsert idempotente que preenche buraco e nunca apaga valor,
roteamento de partição, `mcap_sol` gerado, os CHECKs bicondicionais de motivo e o
marcador que a retenção precisa declarar.
