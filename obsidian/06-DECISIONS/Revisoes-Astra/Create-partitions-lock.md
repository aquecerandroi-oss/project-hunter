---
tags: [astra, revisao, infra, particoes]
date: 2026-09-27
updated: 2026-09-27
status: fechada
owner: sexta-feira
decided_on: 2026-09-27
by: Astra + database-architect
---

# Revisão da Astra — criador de partições reconhece o lock expirado (27/09/2026)

**Defeito (achado pela tarefa do podador, [[Prune-partitions-locks]]):** `create_partitions.py:217` testava `isinstance(exc.orig, asyncpg.exceptions.LockNotAvailableError)`, que nunca casa pelo dialeto asyncpg do SQLAlchemy (o `orig` é um wrapper que só carrega `.sqlstate`). Um `lock_timeout` real abortava a execução e os pais seguintes ficavam sem partição; o "sai 75" do README nunca acontecia.

**Correção:** `getattr(exc.orig, "sqlstate", None) == "55P03"` (igual ao podador), o pai travado é pulado e os outros seguem; dois testes de integração com lock segurado em outra sessão (um direto, um pela CLI com saída 75 e nova tentativa que completa).

**Astra:** correção correta, nenhum must-fix; aceitos os dois ajustes de teste (conjunto completo de partições esperadas; pais diferentes nos dois testes para não depender de ordem). Rejeitado por ora: endurecer o helper de lock, cópia do que já existe no teste do podador.

Relacionado: [[2026-09-27]] · [[2026-09-27-retencao-de-dados-e-backup]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
