# Revisão de código — T2.5b (`bd1d4d8`) e T2.5-adapter (`4bb2865`)

Veredito: **APPROVE_WITH_NITS** (code-reviewer, 2026-09-06). Testes reexecutados: scanner-worker 62, exchange-adapters 274 (+3 skipped), market-worker 237; ruff/pyright/file-size limpos. Os 11 must-fix da Astra conferidos no código, não só na mensagem.

## Pendente para a próxima tarefa que tocar `services/scanner-worker/**` (T2.5c ou T2.5d)

1. **MEDIUM — `baseline_runner.py:97-118` / `replay.py:201-277`.** O atalho "sem candles" (`REASON_NO_CANDLES`) existe em `run_bootstrap` e é o que os testes exercitam, mas `main.py` liga `baseline_loop`, que monta o `BootstrapJob` por `prepare_job` e chama `run_slice` sem checar `job.candles`. Um mercado sem candle persistida (listagem nova, scanner subindo antes do market-worker) ocupa o único slot de bootstrap por ~13 s de parede calculando 10.080 cortes vazios e termina com `history_incomplete` em vez de `no_persisted_candles`. Corrigir fazendo o loop checar `job.candles` antes do `run_slice` **ou** fazendo `run_bootstrap` ser o caminho realmente chamado (eliminar a duplicação). Teste do `baseline_loop` costurado (bootstrap + refresh + falha isolada + agendamento), hoje só as peças isoladas têm teste (a própria nota §21-b declara).
2. **LOW — `publish.py:112`** `float(state.score)` só para o ZADD de `radar:scores` (ranking, não dinheiro); deixar comentário para revisor futuro.
