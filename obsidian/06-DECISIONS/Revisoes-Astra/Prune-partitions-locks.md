---
tags: [astra, revisao, infra, particoes, disco]
date: 2026-09-27
updated: 2026-09-27
status: fechada
owner: sexta-feira
decided_on: 2026-09-27
by: Astra + database-architect
---

# Revisão da Astra — podador de partições sem travar a ingestão (27/09/2026)

**Tarefa:** pré-requisito sem apagar dado do plano de disco ([[2026-09-27-retencao-de-dados-e-backup]]): `prune_partitions.py` fazia todos os `DETACH`/`DROP` numa transação só, sem `lock_timeout` — um `DETACH` durante o `pg_dump` de 80 min travaria os INSERTs de memes.

**Resultado:** uma transação por partição com `lock_timeout 3s`/`statement_timeout 60s`, partição travada pulada pelo nome (sai 75, tenta amanhã), recusa quando há `pg_dump` conectado (`pg_stat_activity.application_name`, provado com o binário real), um `system_events` por execução; crons escritos (não instalados) fora da janela do dump.

**Astra — aceito:** "≤ 3 s" era falso (timeout por aquisição → ~6 s no pior caso); garantia real contra a corrida checagem × DDL documentada + teste com o binário real; `--max-batches` é teto de volume, outbox movida para 00:47. **Rejeitado:** relatório parcial quando a consulta de dump perde a conexão (sai 1 com traceback, basta).

**Achado colateral:** `create_partitions.py:217` nunca reconhece `LockNotAvailableError` pelo dialeto asyncpg (o `orig` é wrapper) — o "sai 75" do README nunca acontece; tarefa separada.

Bruto: `.claude/state/astra-review-prune-locks.md`. Relacionado: [[2026-09-27]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
