# Notas T3.90 — dispersão BTC × alts (`dispersion_24h_v1`) como quarta regra do envelope (H-P18)

Escritas pelo orquestrador em 12/09/2026 ~04:05 BRT: o agente quant morreu no limite semanal do Opus
enquanto redigia esta nota ("Now the notes file"), com todo o código, docs e o EXP-0029 já em disco.
O que está abaixo é o que EU verifiquei antes de commitar — não é o relato do agente.

## Entregue (em disco, verificado)
- Migração `0020_market_dispersion` + `infra/migrations/ddl/dispersion.py`: tabela global `market_dispersion`
  (uma linha imutável por minuto fechado, versão `dispersion_24h_v1`, sem RLS), modelo `MarketDispersion`.
- Série: `packages/indicators/hunter_indicators/dispersion/` (spec + series; mediana do retorno de 24 h das
  16 alts do universo com ≥ 90 d menos o retorno de 24 h do `BTCUSDT`, no fechamento da barra).
- Produtor: `services/scanner-worker/hunter_scanner_worker/dispersion{,_job,_repo}.py` registrado em `main.py`
  (ao lado do job de breadth; `breadth.py`/`breadth_job.py` ajustados para compartilhar o padrão).
- Porta: `services/strategy-worker/hunter_strategy_worker/dispersion_{gate,policy}.py` + `gate_policy.py`,
  `context.py`, `record.py`, `variant.py`: cláusula `{"dispersion": {"min","max","version"}}`, `version`
  obrigatória, faixa meia-aberta no topo (`min <= v < max`), limites COM SINAL (gramática própria — o
  `partition("-")` da breadth quebraria com negativo), recusas `dispersion_gate:<2 casas>` e
  `dispersion_unavailable`.
- Backfill auditado: `infra/scripts/backfill_dispersion.py --days 90 [--plan] [--apply --reason …]` (só
  `--apply` escreve; exige `--reason`; vai para `audit_logs`) + `dispersion_windows.py`.
- Docs: `ACTIVATION.md` (regra `--policy dispersion=-0.05-0.00`, seis avisos), `PIPELINE.md` §4b item 16,
  `DATABASE.md`, `ARCHITECTURE.md`; EXP-0029 pré-registrado ANTES do backfill (campos `‹backfill›` a
  preencher pelo orquestrador com data/hora da leitura; faixas dos braços já fixadas: v20 braço A, v21 braço B).

## Verificação (saída real, 12/09 03:50–04:05 BRT, ambiente restaurado com `uv sync --all-packages`)
- `ruff check` (arquivos das duas tarefas): All checks passed.
- `pyright services/strategy-worker services/scanner-worker services/meme-worker packages/indicators/hunter_indicators/dispersion packages/core/hunter_core/db/models packages/core/hunter_core/settings.py infra/scripts/{backfill_dispersion,dispersion_windows,partition_retention}.py infra/migrations/ddl`: 9 errors, todos `reportPrivateUsage` pré-existentes em `tests/test_replay_*.py` — nenhum em arquivo novo.
- `pytest` unit (dispersion series/spec, scanner dispersion_job, strategy dispersion_gate/policy, meme features/tracker, backfill_dispersion, seed_dry_run): **133 passed**.
- `test_migrations.py` (cadeia até 0021): **132 passed**; `test_schema_privileges.py`: **55 passed**;
  `test_schema_seed_and_partitions.py`: **25 passed**; `services/meme-worker/tests/test_persistence.py`: **10 passed**.
- `check_file_size.py`: 0 over budget. `obsidian_lint.py`: base limpa.

## Próximos passos (orquestrador)
1. Deploy: `MEME=1 MEME_ENABLED=true STRATEGY_SHARDS=4 MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh update` (migra 0020 + 0021).
2. VPS: `bash infra/vps/compose.sh ops python infra/scripts/backfill_dispersion.py --days 90` (relatório) → `--plan` → `--apply --reason "EXP-0029"`; preencher os `‹backfill›` do EXP-0029 com a leitura.
3. Derivar v20/v21 (`derive_variant.py --policy dispersion=…`) e rodar o lote do dia (replay 90 d × 16 mercados) — a candidata do dia.
