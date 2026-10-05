**RESUMO**

**REQUEST_CHANGES.** A retenção e o lock atacam o mecanismo descrito em *Scanner-lag-2026-10-01*, seção 7, mas ainda há caminhos que recriam divergência entre memória e banco. Encontrei cinco bloqueadores concretos.

Assumi o papel de `code-reviewer`. O gatilho original dos incidentes continua sendo hipótese, conforme a revisão anterior.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisei os arquivos indicados e seus chamadores, incluindo `main.py`, persistência, writers, consumidores e modelos.

**TESTES**

Executei, com sincronização de dependências e caches de Python/pytest desabilitados:

```text
uv run pytest services/scanner-worker/tests/test_flush_lane.py services/scanner-worker/tests/test_batch_retention.py services/scanner-worker/tests/test_commit_alarm.py -q

20 passed in 11.38s
```

Também executei quatro sondas com dependências simuladas, via `uv run python -`, inteiramente em memória:

```text
resync_order: ['evaluate', 'resync_failed', 'evaluate', 'EVALUATED_WITH_INVALIDATED_MEMORY'] invalidated_still_pending= True
invalidation_empty_retry: first=False second=True invalidated=set() retained_reference= True
blocked_ack: flushed_new_candle_ack=True evaluations=0
universe_rehydrate: speculative_OPEN_id_cleared_during_database_await=True
```

Essas sondas confirmam o fluxo de controle; **não substituem Postgres real**. Não executei `test_flush_retry.py`, Docker, gates completos nem validação em produção.

**MUST-FIX**

1. **HIGH — Resolver invalidações antes de qualquer nova mutação.**  
   [runners.py:93](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:93) avalia primeiro; o resync aparece somente depois de um flush bem-sucedido, na linha 100. O watchdog também faz flush sem resync imediato ([runners.py:263](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:263)).

   **Cenário:** `EXPIRE(X)` é descartado por baseline sumida; o reload falha uma vez. No próximo ciclo, com uma baseline válida, a memória livre abre Y enquanto X continua aberto no banco. O flush viola o índice único e, como o resync depende de sucesso desse flush, a recuperação fica impedida pelo próprio conflito.

   Há outra lacuna: se `_drop_invalidated` esvazia o lote e a transação falha, o próximo `flush()` retorna pelo atalho vazio, sem registrar os mercados em `lane.invalidated` ([flush_lane.py:92](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/flush_lane.py:92)). **`referenced_by` e `baseline_ids` sobrevivem, mas isso não garante que sejam consultados novamente.**

   **Correção:** preservar a obrigação de resync independentemente do sucesso/emptiness do lote e impedir avaliação/watchdog dos mercados afetados até concluí-la.

2. **HIGH — A reidratação do universo continua fora da exclusão mútua.**  
   [runners.py:307](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:307) disponibiliza o estado novo antes dos awaits de checkpoint e reidratação. [rehydrate.py:64](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/rehydrate.py:64) agora apaga episódio e ID quando a consulta não encontra episódio.

   **Cenário:** entra um mercado sem episódio persistido; durante o await do reload, a avaliação coleta `OPEN(Y)`. O reload retorna vazio e apaga Y da memória, embora sua linha permaneça no lote. A avaliação seguinte coleta `OPEN(Z)`: duas oportunidades abertas para o mesmo mercado.

   **Correção:** tornar entrada/remoção/reidratação parte do mesmo protocolo de exclusão, ou somente disponibilizar o estado após terminar sua carga. Zerar o episódio é correto para um estado isolado; aqui falta esse isolamento.

3. **HIGH — O regime pode envenenar permanentemente a lane. Must-fix agora.**  
   [runners.py:222](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:222) publica `scanner.regime_id` e `engine.row_id` antes do flush da linha 238. O próximo ciclo sem mudança apenas atualiza esse ID. Oportunidades possuem FK para `market_regimes` ([analysis.py:212](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:212)).

   **Cenário:** a abertura do regime R sofre rollback; a memória conserva R. Uma avaliação coleta uma oportunidade referenciando R inexistente. Agora essa oportunidade fica retida e impede todos os commits da lane. Mesmo uma mudança posterior de regime não cria retroativamente R.

   **Correção:** reter e concluir a transição do regime, incluindo estado do classificador e evento, antes de expor sua identidade às avaliações. Apenas mover a atribuição do ID não resolve todo o estado especulativo.

4. **HIGH — Listas separadas não preservam a ordem entre watchdog e avaliação.**  
   [persist.py:174](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:174) escreve todas as oportunidades e **depois** todos os `episode_touches`. Estes sobrescrevem status, contador e timestamp sem proteção contra atualização antiga ([writers.py:283](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:283)).

   **Cenário:** o watchdog coleta um touch de X em estado `NORMAL`; seu flush falha. Antes da próxima tentativa, chega observação fresca que muda X para `HOT`. O flush grava a oportunidade `HOT` e depois aplica o touch antigo, deixando status `NORMAL` e timestamp anterior, enquanto evento e memória descrevem `HOT`.

   **Correção:** preservar a ordem dessas mutações ou impedir que touches antigos sobrescrevam avaliações posteriores. A ordem de append dentro de cada lista não resolve a ordem entre listas.

5. **HIGH — O bloqueio admite ACKs novos sem avaliar seus efeitos e continua crescendo.**  
   [runners.py:87](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:87) pula a avaliação quando bloqueado, mas as linhas 96–97 continuam transferindo novos ACKs para o lote. O consumidor continua acumulando-os ([main.py:273](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:273)).

   **Cenário:** o lote contém snapshots de T0; durante o bloqueio chegam velas de T1. Quando o banco recupera, o flush de T0 também confirma os ACKs de T1, sem avaliação correspondente. Uma queda antes da avaliação seguinte elimina a possibilidade de reentrega dessas mensagens. Se a falha persistir, a lista de ACKs cresce indefinidamente.

   **Correção:** manter ACKs vinculados ao trabalho correspondente e aplicar contrapressão ao consumo pendente. O limite atual interrompe novas avaliações, mas não limita todo o lote.

**NICE-TO-HAVE**

- O teste de resync falho só produz a primeira transição; não tenta abrir Y durante a recuperação, deixando passar o bloqueador 1 ([test_flush_lane.py:261](C:/dev/project-hunter/services/scanner-worker/tests/test_flush_lane.py:261)). Acrescentar os cenários acima às regressões.
- A integração nova cobre rollback de **anomalias**, não oportunidades nem falha pós-commit ([test_flush_retry.py:39](C:/dev/project-hunter/services/scanner-worker/tests/test_flush_retry.py:39)).
- A afirmação “falhas do watchdog alimentam `cycle.failed`” vale para falhas de flush. Exceções da própria varredura ainda apenas geram log no `except` externo ([runners.py:271](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:271)).
- Documentar 60 segundos como limiar verificado **na próxima falha observada**, pois o bloqueio é acionado em `_failed`, não por temporizador independente ([flush_lane.py:108](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/flush_lane.py:108)).

**O QUE EU FARIA DIFERENTE**

Manteria o lock amplo nesta correção. Primeiro concluiria recuperação pendente e trabalho retido; depois permitiria novas transições. Isso simplifica tanto a precedência quanto o vínculo dos ACKs.

**Prefiro pausar a descartar após N tentativas.** Descartar pode perder exatamente o fechamento que evita a próxima violação única. Bissecção merece outro desenho: separar linhas arbitrariamente pode separar fechamento, abertura, histórico e evento do mesmo mercado.

O bloqueio com retries permite recuperação automática de falha transitória ([flush_lane.py:100](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/flush_lane.py:100)). Para veneno determinístico, será necessária intervenção. Reiniciar abandona o lote em memória; portanto, precisa ser apresentado como recuperação com possível perda de trabalho, não como preservação integral.

**CONCORDO COM**

- **Decisões 1 e 2:** avaliação e watchdog recebem a mesma lane em produção ([main.py:139](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:139)); seus acessos ao lote estão sob o lock. Não encontrei append direto em `lane.batch` fora dele nesses caminhos. A lacuna está nas outras mutações de estado e na ordem efetiva das escritas.
- **Decisão 3:** pausar também interrompe `features.updated`, publicado dentro da avaliação ([evaluation_cycle.py:43](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/evaluation_cycle.py:43)). Aceito esse custo como contenção, após corrigir ACKs e recuperação.
- **Decisão 4 — idempotência:** para repetir o mesmo conteúdo, snapshots usam chave `(market_id, ts)`; anomalias e oportunidades usam `id`; histórico ignora conflito `(opportunity_id, ts)`; outbox ignora conflito `event_id`. Conferido em [writers.py:137](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:137), [writers.py:217](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:217), [writers.py:252](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:252), [writers.py:298](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:298) e [outbox_store.py:138](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:138). **Isso não prova segurança de um lote que recebe mutações novas entre tentativas**, especialmente o caso dos touches.
- Os callbacks atuais promovem minuto e atribuem history mark ([collect.py:56](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:56)). Repetir a sequência congelada converge. Já falhas individuais de ACK são capturadas dentro de `_ack_all`: normalmente **não** provocam retry do lote; dependem da reentrega pelo Redis ([persist.py:204](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:204)).
- **Decisões 5–8:** metadados de invalidação permanecem, zerar episódio ausente é semanticamente correto e falhas de flush do watchdog entram no alarme. As condições que tornam essas garantias suficientes ainda faltam nos bloqueadores acima; o regime precisa entrar na correção.

**OBSIDIAN**

- **Scanner-lag-2026-10-01** — registrar os cinco caminhos restantes e distinguir retenção de linhas, recuperação de estado e ACKs.
- **Revisão da Astra — cura da causa raiz do scanner, 05/10/2026** — registrar `REQUEST_CHANGES`, os 20 testes e as quatro sondas, com a limitação de ausência de Postgres real.
- **Workers** — documentar quais mutações pertencem ao dono único e o comportamento operacional durante bloqueio.
- **Open Bugs** — registrar regime com ID não persistido, corrida de reidratação e inversão entre touches e avaliações.