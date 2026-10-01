**RESUMO**

`APPROVE_WITH_NITS` como mitigação, em revisão estática como `code-reviewer`. Nenhum novo must-fix identificado.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados, preservando o modo somente leitura. Não validei `EXPLAIN` nem desempenho real.

**MUST-FIX**

Nenhum neste diff.

**NICE-TO-HAVE**

- Acrescentar teste com **dois IDs ativos do mesmo par**: a deduplicação é por ID, portanto esse lote continua falhando na unicidade; a ordenação não resolve esse caso ([writers.py:218](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:218)).
- Verificar retorno `0/1`, `metadata.state.reason` e `resolved_at` nos testes; hoje o caso principal verifica apenas parte desses efeitos ([test_anomaly_supersede.py:114](C:/dev/project-hunter/services/scanner-worker/tests/test_anomaly_supersede.py:114)).

**O QUE EU FARIA DIFERENTE**

Mediria o plano antes de afirmar ganho: há **um UPDATE adicional por flush com ativos**, inclusive atualizações de episódios existentes. O predicado permite usar o índice parcial; uso efetivo e custo não foram demonstrados ([writers.py:163](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:163), [writers.py:194](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:194)).

**CONCORDO COM**

- `unnest` com arrays alinhados e cast para `anomaly_type`; guarda temporal impede que **esta expiração** produza `resolved_at < detected_at`; `metadata.state` acompanha o fechamento ([writers.py:154](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:154)).
- `rowcount` é compatível com esse UPDATE: o adaptador asyncpg instalado extrai a contagem de `UPDATE n` ([asyncpg.py:551](C:/dev/project-hunter/.venv/Lib/site-packages/sqlalchemy/dialects/postgresql/asyncpg.py:551)).
- Fechamentos antes de aberturas e transação compartilhada com oportunidades/outbox ([writers.py:218](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:218), [persist.py:166](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:166)).
- Não inventar evento de fechamento: o fluxo existente anuncia OPEN/UPDATE. `Opportunity.anomaly_ids` recebe os IDs da memória; referências históricas permanecem válidas porque a linha antiga não é apagada ([collect.py:91](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:91), [collect.py:141](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:141)).

**OBSIDIAN**

- **Scanner-lag-2026-10-01** — registrar aprovação limitada à mitigação, caso de duas ativas e custo ainda não medido.
- **Anomalies** — documentar expiração por `superseded`, distinta de resolução pelo detector.