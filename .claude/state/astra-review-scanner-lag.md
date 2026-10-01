**RESUMO**

**Concordo com A+B como mecanismo dominante do incidente; o primeiro gatilho continua desconhecido.** Não atribuiria agora o lag a `history_v2` ou à necessidade de sharding. A expiração automática proposta pode destravar, mas **não é segura isoladamente**.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `backend-specialist`, somente leitura.

**TESTES**

Não executados. Conferi código e memória compartilhada; as medições da VPS são as fornecidas por você, sem nova validação remota.

**MUST-FIX**

1. **A: divergência entre memória e banco confirmada no código.** IDs e fechamento avançam antes do commit em [collect.py:85](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:85) e [watchdog.py:115](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/watchdog.py:115). A exceção descarta o lote em [runners.py:121](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:121). Cenário: fechamento de X perdido → abertura de Y → conflito, porque o upsert trata apenas `id`, não a unicidade parcial ([writers.py:150](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:150)). **Outro gatilho possível**, além de falha de DB/watchdog: a invalidação de baseline remove as linhas de anomalia depois de a memória avançar ([persist.py:133](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:133)).

2. **B: amplificação confirmada, com correção na descrição.** ACK ocorre depois da transação ([persist.py:166](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:166)); cada reentrega incrementa o contador de handles ([consumers.py:156](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/consumers.py:156)). O reclaim precede cada leitura nova, mas termina em **cursor zero OU página vazia** ([consume.py:190](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:190)). Portanto, ~1.700 páginas é cenário possível, não contagem demonstrada. Os ~88× sustentam a espiral; a parcela exata dos 98% de CPU exige perfil.

3. **O `superseded` irrestrito tem dois furos concretos.** Um lote atrasado de X pode expirar Y mais recente; e, se X fechado estiver no lote junto de Y ativo, excluir todos os IDs do lote da reparação deixa a execução dependente da ordem das escritas. Hoje há deduplicação por ID, sem proteção temporal ([writers.py:153](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:153)). Reter o lote e continuar acrescentando avaliações também não resolve isso.

**NICE-TO-HAVE**

Evidência adicional que pediria **antes de reiniciar**:

- Para 2–3 conflitos: X ativo no DB e Y do INSERT rejeitado, com `detected_at`, `metadata.state.observation_ts`, status e motivo; incluir linhas fechadas recentes do mesmo par. O SQL rejeitado já pode provar X≠Y sem acessar memória.
- Duas amostras de `XPENDING` dos mesmos IDs, separadas por 60 s: consumidor, idle e número de entregas; junto de deltas de handles e produção.
- Perfil curto de CPU e logs retidos de `scanner_watchdog_failed`/`scanner_baseline_vanished_before_write`.

Ressalva: **`max(detected_at)` parado não prova ausência de UPDATE**; o upsert preserva essa coluna ([writers.py:161](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:161)). Os máximos apresentados demonstram paralisação importante, mas não “nenhuma escrita em todo o scanner”.

**O QUE EU FARIA DIFERENTE**

**Conserto mínimo candidato: dois arquivos de produção + um de testes**, sem prometer resolver toda recuperação histórica:

- `runners.py`: serializar avaliação/watchdog **desde a mutação até o commit**; preservar lote e ACKs durante retry com backoff, sem novas transições sobre ele. Falha permanente precisa interromper progresso, não descartar silenciosamente.
- `writers.py`: fechamento explícito antes de abertura; reconciliação apenas de X comprovadamente anterior a Y, na mesma transação, preservando evidência de `superseded_by`. Lote antigo não pode ressuscitar estado terminal nem substituir episódio mais novo.
- Testes com Postgres real: rollback→retry, X fechado/Y aberto nas duas ordens, lote atrasado, concorrência e repetição.

**Prefiro retenção + serialização; reconciliação é complementar para o estado já divergente.** Só reter não cura o lote atualmente envenenado. A invalidação de baseline também precisa estar coberta; se exigir mais arquivos, rejeito sacrificar correção para cumprir o teto.

RLS não é o obstáculo: anomalias/oportunidades são globais ([DATABASE.md:22](C:/dev/project-hunter/docs/DATABASE.md:22)). Preserve referências históricas a X; as oportunidades novas devem apontar para Y, como já são montadas em [collect.py:136](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:136). Atualize também `metadata.state`, não só colunas ([rows.py:107](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/rows.py:107)). Retry com os mesmos eventos é deduplicado; regenerar IDs não é ([outbox_store.py:138](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:138)).

**CONCORDO COM**

- **Sem sharding agora.** Primeiro restabelecer commits e medir CPU/lag sem reprocessamento. Depois, limitar páginas de reclaim por rodada, preservando cursor e intercalando mensagens novas.
- **Restart isolado: mitigação plausível, não cura garantida.** Todas as ativas são carregadas, independentemente da idade; porém uma fechada com observação mais recente pode vencer na reidratação ([repo.py:177](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/repo.py:177)). E os caminhos de divergência permanecem. O boot das 14:49Z não prova sozinho que houve cura seguida de recaída.
- Pendências ainda retidas podem ser reentregues; trimadas não recuperam payload pelo stream ([Redis](https://redis.io/docs/latest/commands/xautoclaim/)). **Reentrega não reconstrói automaticamente os snapshots perdidos**: o handler marca mercado dirty e a avaliação lê hot state ([main.py:265](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:265), [scanner.py:136](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:136)). Aceite operacional: commits avançando, PEL diminuindo e ausência de novos conflitos.

**OBSIDIAN**

- **Late-delay-do-Lab-diagnostico-2026-10-01** — acrescentar diagnóstico do scanner, distinguindo mecanismo sustentado de gatilho desconhecido.
- **Open Bugs** — registrar divergência pré-commit, amplificação do reclaim e limites do restart.
- **Anomalies / Workers** — documentar recuperação transacional e ausência de recomposição histórica automática.