**RESUMO**

**DONE_WITH_CONCERNS.** A reescrita corrige a espera ilimitada atrás do dump, mas **não garante bloqueio total da ingestão ≤ 3 segundos**. O backup padrão deve ser detectado; os horários estão corretos nas noites normais, com uma exceção relevante na mudança para o horário de verão. Confirmei também o problema do `isinstance` no criador.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit ou cron instalado. Revisei os arquivos delimitados e, em `docs/DATABASE.md`, considerei apenas o parágrafo novo da §1.3.

**TESTES**

Executei sondas em memória com `.venv/Scripts/python.exe -B -`, sem conectar ao banco nem carregar `Settings`. Resultado real do tradutor de exceções instalado:

```text
SQLAlchemy 2.0.52
orig class: AsyncAdapt_asyncpg_dbapi.Error
isinstance(orig, asyncpg.LockNotAvailableError): False
orig.sqlstate: 55P03
```

A conversão com `ZoneInfo("Europe/Berlin")` confirmou:

| Noite | Criar UTC | Podar UTC | Outbox UTC | Dump UTC |
|---|---|---|---|---|
| Verão normal | 23:07 anterior | 23:27 anterior | 23:47 anterior | 01:17 |
| Inverno normal | 00:07 | 00:27 | 00:47 | 02:17 |
| Entrada no verão, 29/03/2026 | 00:07 | 00:27 | 00:47 | 01:17 |
| Entrada no inverno, 25/10/2026 | 23:07 anterior | 23:27 anterior | 23:47 anterior | 02:17 |

**Não executei pytest nem integração PostgreSQL nesta revisão.** Os cenários de concorrência abaixo são derivados do código e da implementação documentada do PostgreSQL, não reproduções medidas no banco.

**MUST-FIX**

1. **P1 — A promessa de bloqueio máximo de 3 segundos é falsa.**  
   Em [prune_partitions.py:202](C:/dev/project-hunter/infra/scripts/prune_partitions.py:202), `DETACH` e `DROP` compartilham a transação; os limites são definidos em [linha 98](C:/dev/project-hunter/infra/scripts/prune_partitions.py:98).

   **Cenário:** uma sessão segura `ACCESS SHARE` somente na pai por 2,5 s; outra segura a filha por mais tempo. O `DETACH` espera 2,5 s pela pai, consegue `ACCESS EXCLUSIVE` e depois espera até outros 3 s pela filha. Um `INSERT` que entrou atrás dele pode esperar aproximadamente **5,5 s**. Depois de adquirido, o lock também permanece durante execução, `DROP` e commit.

   `lock_timeout` vale **por aquisição**, enquanto `statement_timeout` vale por comando; nenhum deles é um orçamento de 3 s para toda a transação. [Documentação PostgreSQL](https://www.postgresql.org/docs/16/runtime-config-client.html#GUC-LOCK-TIMEOUT).

   **Correção:** retirar a garantia absoluta de [linha 31](C:/dev/project-hunter/infra/scripts/prune_partitions.py:31). Se ≤ 3 s for requisito obrigatório, a implementação precisa de um orçamento total compatível e teste com ingestão concorrente; os dois `SET LOCAL` atuais não o implementam.

2. **P2 — “Qualquer pg_dump” e “nada enquanto conectado” excedem a proteção implementada.**  
   O filtro compara exatamente `'pg_dump'` em [prune_partitions.py:112](C:/dev/project-hunter/infra/scripts/prune_partitions.py:112).

   **Cenário:** um dump manual usa `PGAPPNAME=backup-manual` dentro do container. Ele deixa de ser detectado, embora continue sendo `pg_dump`. Esse nome é um *fallback*, substituível por `PGAPPNAME` ou parâmetro de conexão. [Contrato libpq](https://www.postgresql.org/docs/16/libpq-connect.html#LIBPQ-CONNECT-FALLBACK-APPLICATION-NAME).

   Existe também uma corrida: o dump pode conectar entre a consulta em [linha 228](C:/dev/project-hunter/infra/scripts/prune_partitions.py:228) e o DDL em [linha 233](C:/dev/project-hunter/infra/scripts/prune_partitions.py:233).

   **Correção:** documentar a garantia real e fixar explicitamente o nome no backup administrado. Se a exigência for exclusão absoluta entre backup e poda, ambos precisam participar de uma mesma coordenação; consultar `pg_stat_activity` não oferece exclusão mútua.

3. **P2 — O teto de lotes não garante terminar antes do dump, especialmente na transição de verão.**  
   O comentário de [hunter-outbox:5](C:/dev/project-hunter/infra/vps/cron/hunter-outbox:5) atribui essa garantia a `--max-batches 1000`, mas o laço apenas conta lotes em [prune_outbox_events.py:146](C:/dev/project-hunter/infra/scripts/prune_outbox_events.py:146).

   **Cenário:** 1.000 lotes levando 6 s cada ultrapassam 100 minutos, contra 90 minutos disponíveis numa noite normal. Na entrada do horário de verão, a folga cai para **30 minutos**: uma execução de 40 minutos já cruza o backup. O teste em [test_vps_cron_files.py:63](C:/dev/project-hunter/infra/scripts/tests/test_vps_cron_files.py:63) verifica somente o minuto de início, sem duração nem transição de fuso.

   **Correção:** tratar 1.000 como teto de volume; corrigir a documentação e, se não sobrepor for obrigatório, implementar limite temporal/coordenação com o backup.

**NICE-TO-HAVE**

- Testar um `pg_dump` real, com e sem `PGAPPNAME`, além de dump iniciando entre duas partições. Hoje o teste configura o nome artificialmente em [test_prune_partitions_integration.py:203](C:/dev/project-hunter/infra/scripts/tests/test_prune_partitions_integration.py:203).
- Cobrir sucesso, erro misto, dry-run sem evento e contagem **exatamente igual a um** evento. O teste atual consulta apenas o último evento em [linha 232](C:/dev/project-hunter/infra/scripts/tests/test_prune_partitions_integration.py:232).
- Tratar falhas gerais com relatório parcial: uma exceção na consulta de dump pode escapar do tratamento por partição e impedir `record_run`, chamado somente após `prune` retornar. [prune_partitions.py:228](C:/dev/project-hunter/infra/scripts/prune_partitions.py:228), [linha 306](C:/dev/project-hunter/infra/scripts/prune_partitions.py:306), [linha 317](C:/dev/project-hunter/infra/scripts/prune_partitions.py:317).

**O QUE EU FARIA DIFERENTE**

Manteria a transação por partição e o tratamento por SQLSTATE, mas escreveria o contrato como “espera por aquisição limitada a 3 s”, até existir prova de um limite total.

**Sobre `--max-batches 1000`: aceitável como teto inicial de volume**, equivalente a até 5 milhões de linhas, pelo lote de 5.000 em [outbox_store.py:55](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:55). Sua adequação operacional depende da duração medida e da evolução do backlog; não constitui prazo de conclusão.

**Confirmo o bug preexistente do criador:** [create_partitions.py:217](C:/dev/project-hunter/infra/scripts/create_partitions.py:217) não reconhece o wrapper do dialeto. Num lock timeout real, ele relança, interrompe os grupos restantes e não chega ao caminho esperado de saída 75. Corrigiria em tarefa separada usando `.sqlstate == "55P03"` e teste de integração. Não é regressão deste diff.

**CONCORDO COM**

- **Detecção do backup padrão:** no código atual, a chamada está em [backup_postgres.sh:122](C:/dev/project-hunter/infra/vps/backup_postgres.sh:122), usando `-U hunter -d hunter`; o DSN administrativo aponta ao mesmo banco em [docker-compose.prod.yml:47](C:/dev/project-hunter/infra/vps/docker-compose.prod.yml:47). Não encontrei configuração explícita de `PGAPPNAME` nos blocos revisados; isso não verifica o ambiente vivo da VPS.
- **Visibilidade e `datname`:** não vejo falha aqui. `application_name` fica disponível antes da restrição de visibilidade por papel no [código PostgreSQL](https://github.com/postgres/postgres/blob/REL_16_STABLE/src/backend/utils/adt/pgstatfuncs.c); `current_database()` é o filtro correto.
- **Horários e retenção:** criar às 01:07 e podar às 01:27 ficam do mesmo lado da meia-noite UTC nas duas estações. No verão, a expiração recém-atingida à meia-noite só será processada às 23:27Z: atraso de retenção, sem exclusão antecipada. O corte usa UTC em [partition_retention.py:97](C:/dev/project-hunter/infra/scripts/partition_retention.py:97).
- Transações independentes, rollback da partição problemática, prioridade de saída 1 sobre 75 e `flock` compartilhado entre criação/poda são boas escolhas. [prune_partitions.py:137](C:/dev/project-hunter/infra/scripts/prune_partitions.py:137), [hunter-partitions:12](C:/dev/project-hunter/infra/vps/cron/hunter-partitions:12).

**OBSIDIAN**

- **Decisão — retenção de dados e backup para o disco da VPS (27/09/2026):** registrar limites reais das guardas e pendências antes da instalação.
- **Deployment:** atualizar horários, exceções de DST e distinguir teto de volume de prazo.
- **Open Bugs:** registrar o tratamento incorreto de `55P03` em `create_partitions.py`.
- **Revisoes-Astra/Index:** vincular esta revisão e suas limitações de validação.