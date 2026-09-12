# Notas T4.16b — o rastreador não solta uma moeda com aposta aberta (12/09/2026, 17:0x–18:0x BRT)

A agente (backend-specialist) entregou o código e os testes e foi cortada pelo limite semanal no passo do pyright
("Now let's run pyright"); não escreveu estas notas nem os docs. O orquestrador verificou o disco e fechou:

- `ruff check`/`ruff format --check`: limpos. `pyright services/meme-worker`: 3 erros → 0 (`_tracked_from_row(row: RowMapping)`
  + import `sqlalchemy.engine.RowMapping`; `_iso` → `iso_or_none` público em `source_stats.py`, importado por `sources.py`).
- `pytest services/meme-worker/tests -m "not integration"`: **205 passed**. Testcontainers `test_lab_persistence.py` +
  `test_tracker.py` + `test_tracker_priority.py`: **38 passed em 150 s**. `check_file_size`: 0 acima (848 arquivos).
- Arquivos: M `collect.py`, `lab.py`, `lab_bets.py`, `lab_repo_bets.py`, `main.py`, `repo.py`, `sources.py`, `tracker.py`,
  `tests/test_lab_persistence.py`, `tests/test_tracker.py`, `tests/test_tracker_priority.py`; novos `lab_pins.py`,
  `lab_point_read.py`, `source_stats.py`, `tracker_pins.py`, `tracker_types.py`, `warmup.py`.
- Docs: `docs/plans/T4-MEME-RADAR.md` §T4.16b, `docs/RISK_ENGINE_MEME.md` §10 item 8 (escritos pelo orquestrador).
- Item 4 do brief (reclassificar as 5 apostas) já tinha sido feito na VPS às 16:5x BRT (`--reason tracker_evicted_open_bet`).
- Prova na VPS após o deploy: heartbeat `tracked_pinned` ≥ apostas abertas, `tracked_capped_60s`, 0 reinícios.
