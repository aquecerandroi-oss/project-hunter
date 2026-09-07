# Brief T3.0e — banda de saída do universo spot (D12) e as séries de descarte por venue

**Owner:** exchange-integration-specialist. **Revisor depois:** code-reviewer. **Não commitar.** **Regra operacional: nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min; suítes com testcontainers um arquivo por invocação; Astra indisponível até 2026-09-12.** Base: `main` em `be4e907`. Outros agentes editam `services/execution-worker/**`, `packages/core/hunter_core/{admission,strategies,db}/**`, `infra/migrations/**`, `services/strategy-worker/**`, `tests/integration/paper/**`, `apps/**` — **não toque**. Se precisar de coluna nova para a contagem durável, **não** crie migração: use o que existe (`markets`/`market_universe*`/Redis durável com prova de restart) e registre a alternativa; se nada servir, pare e relate.

## Leia antes
`.claude/state/decisions-delegated-2026-09-07.md` §D12 (a regra decidida; a admissão **não** muda), `.claude/state/review-T3.0c-T3.0d.md` (item `market_dropped_events_total`, e os "Depois"), `.claude/state/notes-T3.0c.md` (ressalva 3: logs sem `market_type`; §6), `services/market-worker/hunter_market_worker/{spot_universe,universe,universe_repo,heartbeat}.py`, `packages/core/hunter_core/observability.py` (padrão `market_spot_*`), `docs/PIPELINE.md` §1d.

## Entregar
1. **Banda só na saída (D12)**: admissão inalterada (≥ 50 M USDT/24h inclusivo, `TRADING`, quote USDT, fora da blocklist, ticker legível). Permanência: par admitido só sai com `< 40 M` em **3 refreshes consecutivos**, contagem **durável** (sobrevive a restart do shard 0); ticker ilegível conta como observação abaixo; perder `TRADING`/quote/blocklist sai na hora. Testes: `PROMUSDT` oscilando 49/51 M não sai; 3 leituras < 40 M sai; 2 abaixo + 1 acima zera a contagem; restart entre a 2ª e a 3ª leitura mantém a contagem; par com < 50 M **nunca** entra. Evento de universo com o motivo da saída (`below_band_3x`, `not_trading`, ...).
2. **`market_spot_dropped_events_total{exchange}`** separado de `market_dropped_events_total` (mesmo padrão de `market_spot_ingestion_gaps`); o laço spot incrementa só o seu. Teste.
3. **`market_type` nos logs** `market_backfill_planned`, `market_persist_flush_failed` e nos demais logs de ingestão que a ressalva 3 lista; teste com `structlog.testing.capture_logs`.
4. `docs/PIPELINE.md` §1d: a banda, a série nova, e a atualização do checklist para ligar spot (`market_spot_dropped_events_total` no lugar do contador compartilhado).

## Provar
`services/market-worker/tests` por arquivo (`test_spot_universe`, `test_spot_ingest`, `test_universe*`, `test_heartbeat*`, novos), `ruff check`/`format --check`/`pyright` em `services/market-worker packages/core/hunter_core/observability.py`, `check_file_size.py`. Nada em `.env*`. Relatório em português no formato estendido com saída real; `.claude/state/notes-T3.0e.md`.
