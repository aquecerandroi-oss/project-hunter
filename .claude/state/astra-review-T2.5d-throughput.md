**RESUMO**

**Aprovo a direção, com ajustes antes de implementar.** Papel adotado: `backend-specialist`; modo OPINIÃO.

| Pergunta | Minha escolha |
|---|---|
| **1 — Guard antecipado** | Manter `consume()` com guard por mensagem; usar guard pipelinado somente em `consume_batches()`. |
| **2 — Timestamp** | **MAIOR** para o campo atual; medir atraso de fila separadamente, antes da coalescência. |
| **3 — hiredis** | **`redis[hiredis]>=5.2`**, com atualização do lock e verificação na imagem final. |
| **4 — Bootstrap** | **Remover `run_bootstrap` e migrar seus testes para o caminho real**, mantendo o replay orçamentado no loop. |

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes nem benchmarks. Esta revisão usa leitura do código, dos registros da T2.5c e da documentação oficial.

**MUST-FIX**

**1. Não tratar “primeira ocorrência entregue” como “evento processado”.**

A equivalência proposta não existe quando o handler falha ou devolve `PendingAck`: hoje o scanner continua sem marcar o evento como processado. Portanto, uma segunda ocorrência ainda pode ser entregue: [consumers.py:152](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/consumers.py:152).

**Cenário:** chegam duas ocorrências de E; a primeira falha transitoriamente. Hoje a segunda pode executar com sucesso imediatamente. No desenho proposto, ela já foi ACKada; sobra apenas a primeira, aguardando recuperação.

Minha solução mais simples: **`consume_batches()` entrega todas as entradas ainda não processadas, inclusive repetições de `event_id`**. O scanner coalesce por mercado e `ack_many()` recebe todas as entradas concluídas. Isso dispensa um mapa oculto entre representante e duplicatas.

ACK direto continua adequado para entradas cujo evento **já estava marcado como processado**, como acontece hoje: [consume.py:209](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:209).

**2. Preservar `consume()`; antecipar o guard tem outras diferenças observáveis.**

Além da duplicação dentro do lote:

- **A concorrência não depende de `XAUTOCLAIM`.** Duas entradas com IDs de stream distintos e o mesmo `event_id` podem chegar a consumidores diferentes por `XREADGROUP` normal. B consulta antecipadamente; A conclui; B entrega algo que uma consulta posterior teria filtrado. O Redis distribui entradas, sem conhecer o `event_id` do envelope. [Documentação de consumer groups](https://redis.io/docs/latest/commands/xreadgroup/).
- **A janela UTC pode mudar entre yields.** E foi marcado em D−1; o lote começa às 23:59 de D, mas E seria examinado depois de 00:00 de D+1. O guard antecipado encontra E; o atual já não consulta D−1. Isso decorre da janela calculada a cada chamada: [consume.py:134](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:134).

A corrida já é possível hoje; antecipar amplia a janela. **Não justificaria alterar todos os consumidores para acelerar três streams específicos.** Manteria assinatura, default e guard atuais de `consume()`.

**3. `ack_many()` precisa concluir todas as notificações absorvidas, não apenas os representantes.**

**Cenário:** 500 eventos distintos do mesmo mercado viram um `touch`; somente o representante entra em `ack_many`. Restam 499 pendências, posteriormente recuperadas, recriando trabalho.

Separe conceitualmente:

- entradas concluídas: todos os IDs de stream e `event_id` absorvidos;
- chamadas de `touch`: uma por mercado;
- eventos já processados: somente ACK;
- falhas: continuam pendentes.

O ACK atual marca o `event_id` antes de confirmar a entrada: [consume.py:240](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:240). Preserve essa ordem e calcule a chave diária **no ACK**, não na leitura.

**4. Não usar o maior timestamp como prova de que a fila inteira cumpriu o p99.**

**Escolho MAIOR para `input_ts`.** Isso preserva o comportamento de `touch()` e o significado declarado do histograma: idade do input mais recente que disparou a observação. [state.py:129](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/state.py:129), [metrics.py:29](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/metrics.py:29).

**Cenário:** um lote contém um tick de dez minutos atrás e outro recente do mesmo mercado. O máximo esconde o primeiro. Um fechamento recente também pode substituir o timestamp do tick, independentemente do lote.

Exigiria **atraso por stream medido antes da coalescência**, usando os timestamps de todas as entradas válidas, além de lag/PEL. Se o requisito escolhido for “input mais antigo ainda não atendido → conclusão”, mantenha um campo mínimo separado ao longo de **todo o período dirty**; trocar apenas `max` por `min` dentro do lote não resolve, porque `touch()` continua tomando o máximo entre chamadas.

O timestamp da notificação tampouco prova a idade da evidência: o handler apenas marca o mercado para leitura do hot state: [main.py:176](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:176).

**5. Definir isolamento de envelope inválido no novo lote.**

**Cenário:** 499 entradas válidas e uma inválida. Se a lista inteira for decodificada antes do primeiro yield e uma exceção abortar tudo, nenhuma das válidas progride naquela leitura; recuperar o mesmo conjunto pode repetir o bloqueio.

Hoje a decodificação ocorre por entrada, permitindo progresso das anteriores: [consume.py:207](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:207).

No novo caminho, permita progresso das válidas, registre a falha e mantenha a inválida pendente, com recuperação que não monopolize o consumidor. Teste isso tanto em leitura nova quanto em `XAUTOCLAIM`.

**6. O atalho sem candles precisa fechar o job pelo caminho operacional completo.**

**Escolho remover `run_bootstrap`**, migrando seus testes de orquestração para `baseline_loop`. O wrapper chama `run_slice()` sem orçamento; o loop passa orçamento e pressão: [replay_io.py:132](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay_io.py:132), [baseline_runner.py:260](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:260).

Remover o wrapper **não basta**: após `_start_job`, o ramo vazio precisa:

- produzir `REASON_NO_CANDLES`, preservando `gaps` e `requested`;
- registrar tentativa incompleta e backoff;
- atualizar `baseline_note` e progresso;
- liberar `job`, `entry` e `requested`, sem chamar replay.

O fechamento normal já atualiza motivo e progresso; o ledger deriva o backoff de `complete=False`: [baseline_runner.py:138](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:138), [ledger.py:154](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/ledger.py:154).

**Cenário:** somente limpar o slot, sem registrar corretamente a tentativa, permite escolher repetidamente o mercado vazio. O teste essencial deve demonstrar que o próximo mercado progride e que o primeiro fica com o motivo correto.

**NICE-TO-HAVE**

- Usaria **dois `SMISMEMBER` no pipeline**, um por dia, em vez de `2*N SISMEMBER`; e **um `XACK` com todos os IDs**, em vez de N comandos. Mantém os round trips e reduz comandos/respostas. [SMISMEMBER](https://redis.io/docs/latest/commands/smismember/), [XACK](https://redis.io/docs/latest/commands/xack/).
- O contador de coalescência deve contar notificações válidas absorvidas menos representantes, separado de duplicatas já processadas e entradas inválidas. Acrescente `stream` como label.

**O QUE EU FARIA DIFERENTE**

**Lote 500 e bloqueio:** aceito como ponto inicial. `COUNT=500` é teto, não espera até completar 500; com a fila drenada, haverá lotes menores. `BLOCK` atua quando não há entradas disponíveis. [XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/).

Concordo que os `touch` são baratos, mas **não afirmaria ainda que leitura→ACK ficará sempre abaixo de 30 s**: esse intervalo inclui decodificação, guard, escalonamento e Redis. Mediria a duração completa sob carga. Os 2 s de bloqueio continuam abaixo do socket timeout de 5 s: [config.py:64](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/config.py:64), [redis.py:56](C:/dev/project-hunter/packages/core/hunter_core/redis.py:56).

**hiredis:** escolheria o extra oficial, deixando a compatibilidade declarada pelo `redis-py`. O lock atual fixa **Redis 8.1.0**, apesar do mínimo `>=5.2`: [uv.lock:1385](C:/dev/project-hunter/uv.lock:1385). Evitaria atualizar Redis incidentalmente ao adicionar o extra.

O Docker usa Python 3.12 Bookworm e instalação congelada; portanto, manifest e lock precisam acompanhar a mudança: [Dockerfile.api-workers:15](C:/dev/project-hunter/infra/docker/Dockerfile.api-workers:15), [Dockerfile.api-workers:40](C:/dev/project-hunter/infra/docker/Dockerfile.api-workers:40). Há wheels CPython 3.12 manylinux publicados, mas confirmaria o artefato resolvido e o parser efetivamente ativo na imagem final. [Redis-py](https://redis.io/docs/latest/develop/clients/redis-py/), [hiredis no PyPI](https://pypi.org/project/hiredis/).

Mediria em etapas: **base → lote → lote+hiredis**, com carga comparável. Os 16–21 ms ainda não são custo demonstrado exclusivamente do parser: [notes-T2.5.md:981](C:/dev/project-hunter/.claude/state/notes-T2.5.md:981).

**CONCORDO COM**

Consumo em lote, coalescência restrita às notificações, preservação do ACK diferido dos candles, ausência de `XGROUP SETID` e prova dentro do contêiner. Essa separação corresponde ao contrato atual dos handlers: [main.py:176](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:176), [main.py:194](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:194).

**OBSIDIAN**

- **Workers** — registrar consumo em lote, fronteiras de ACK e caminho único de bootstrap.
- **Data Flow** — distinguir entrada entregue, processada e absorvida por coalescência.
- **Features** — documentar timestamp mais recente versus idade da fila e do trabalho pendente.
- **Infrastructure** — registrar extra hiredis, parser ativo e comparação medida.
- **Revisoes-Astra/T2.5d — desenho** — registrar as quatro escolhas e os cenários de regressão acima.