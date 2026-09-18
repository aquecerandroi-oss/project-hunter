**RESUMO**

**DONE_WITH_CONCERNS.** Como `database-architect`: não encontrei falha de correção no loop, cutoff ou transação por lote para uma única execução. O `COUNT` diário é aceitável, condicionado à medição de I/O. Há uma correção necessária na documentação sobre espaço em disco; o primeiro dreno merece acompanhamento operacional.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum acesso à VPS ou a `.env`.

**TESTES**

Não executados nesta revisão estritamente sem escrita.

Os testes cobrem término com lote curto/vazio, limite de lotes e validação do cutoff ([test_prune_outbox_events.py:55](C:/dev/project-hunter/infra/scripts/tests/test_prune_outbox_events.py:55)). A integração existente cobre retenção, preservação de pendentes e exclusão limitada por lote ([test_outbox_integration.py:599](C:/dev/project-hunter/packages/core/tests/integration/test_outbox_integration.py:599)); isso não comprova desempenho sobre 19,57 milhões de linhas.

**MUST-FIX**

1. **Corrigir a expectativa de recuperação física de disco.** O [README:263](C:/dev/project-hunter/infra/vps/README.md:263) sugere que o espaço volta após autovacuum/VACUUM, e [DATABASE.md:74](C:/dev/project-hunter/docs/DATABASE.md:74) promete estabilização em aproximadamente 13 GB. Normalmente, vacuum disponibiliza espaço **para reutilização interna**, sem reduzir o arquivo ou o `df`; a exceção são páginas inteiramente livres no final da relação. [Documentação PostgreSQL](https://www.postgresql.org/docs/16/routine-vacuuming.html#VACUUM-FOR-SPACE-RECOVERY).

   **Cenário:** com disco a 88%, o operador considera a emergência resolvida após apagar 7 milhões de linhas, mas o filesystem continua ocupado enquanto backups e outras tabelas crescem. A redação deve separar população lógica, espaço reutilizável e espaço livre no filesystem; “~13 GB” é estimativa, não resultado garantido. Concordo em evitar `VACUUM FULL` durante a operação.

**NICE-TO-HAVE**

- **Remover “never a Seq Scan” como garantia.** O [script:19](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:19) exagera: `ORDER BY id LIMIT` limita linhas retornadas, não linhas examinadas. A [consulta:339](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:339) filtra `dispatched_at` sem índice nessa coluna; a passagem final pode examinar toda a população sobrevivente. O teste verifica somente o plano da seleção com 60 mil linhas elegíveis, não o `DELETE` completo nem a distribuição após o dreno ([teste:678](C:/dev/project-hunter/packages/core/tests/integration/test_outbox_integration.py:678)). Eu mediria o plano completo antes de propor índice novo.

- **O `COUNT` é aceitável uma vez por dia**, fora do horário de maior carga, sem criar índice exclusivamente para ele. É uma varredura potencialmente pesada, não uma consulta barata por ser dry-run ([script:67](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:67)). Seu lock de leitura não impede DML normal; o risco principal é competição por I/O/cache. [Locks PostgreSQL](https://www.postgresql.org/docs/16/explicit-locking.html). A receita atual de cron nem executa esse COUNT: ele ocorre apenas com `--dry-run` ([script:184](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:184)).

- **04:37 não garante que o backup terminou.** O [README:251](C:/dev/project-hunter/infra/vps/README.md:251) separa horários, mas não sincroniza processos. Se o dump ainda estiver ativo, seu snapshot pode impedir a remoção das versões apagadas pelo vacuum, além da competição por I/O. Isso não corrompe o backup; pode atrasar a reutilização de espaço. [Vacuum e MVCC](https://www.postgresql.org/docs/16/routine-vacuuming.html).

- **Corrigir dois detalhes de diagnóstico:** `--max-batches=-1` vira ilimitado ([script:130](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:130)); e atingir o limite não prova que restam linhas — um lote final curto também pode receber essa mensagem ([script:192](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:192)). Rejeitaria negativos e escreveria “pode haver linhas restantes”.

**O QUE EU FARIA DIFERENTE**

Para os 7 milhões iniciais, começaria com uma fatia limitada, medindo duração, espaço livre, WAL, progresso do vacuum e atraso do dispatcher antes de ampliar.

Os lotes têm commits separados, mas o [loop:130](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:130) não tem pausa: **lote pequeno não limita a taxa nem o WAL total**. Commit também não significa reciclagem imediata do WAL. [Configuração de WAL](https://www.postgresql.org/docs/16/wal-configuration.html).

Acrescentaria exclusão mútua entre execuções e timeouts por sessão. O cron atual não impede sobreposição ([README:258](C:/dev/project-hunter/infra/vps/README.md:258)); dois pruners podem disputar as mesmas linhas.

Também explicitaria que **400 × 5.000 = 2 milhões por execução**: mantendo esse teto uma vez ao dia, a entrada informada de 2,1 milhões/dia supera a capacidade de poda. Serve como primeira fatia, mas não como configuração permanente para eliminar o backlog.

**CONCORDO COM**

- Cutoff calculado uma única vez, em UTC, preservando uma fronteira estável durante o dreno ([script:91](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:91), [script:146](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:146)).
- Uma transação por lote: o retorno só se completa após sair de `session.begin()`; falha no lote atual não desfaz os anteriores ([script:149](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:149)).
- Reutilizar `prune_dispatched`, mantendo pendentes fora do predicado de exclusão ([outbox_store.py:339](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:339)).
- Encerrar no primeiro lote curto para uma execução isolada e usar `compose.sh ops` com a imagem disponível ([compose.sh:250](C:/dev/project-hunter/infra/vps/compose.sh:250)).

**OBSIDIAN**

- **Deployment** — registrar cron da outbox, procedimento do primeiro dreno e diferença entre espaço reutilizável e espaço livre.
- **Workers** — atualizar o responsável operacional pela retenção da outbox.
- **Diario/2026-09-18** — registrar esta revisão; acrescentar resultados operacionais somente após medição real.