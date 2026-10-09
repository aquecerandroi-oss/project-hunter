**RESUMO**

**REQUEST_CHANGES:** há campos zumbis após reinício com laços desligados e uma lacuna comprovada no teste de cancelamento. Não encontrei colisão de nomes nem corrupção da conexão Redis no caminho analisado.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisão dos três arquivos solicitados e das dependências de heartbeat, configuração e leitores da API.

**TESTES**

Execução com sincronização do ambiente, bytecode e cache do pytest desabilitados:

```text
uv run pytest services/meme-worker/tests/test_cycle_metrics.py -q
22 passed in 8.40s
```

Prova adicional por `uv run python -`, exclusivamente em memória:

```text
ORIGINAL: cancelamento dentro da publicacao propagou; failed_total=0
MUTANTE SOMENTE EM MEMORIA: _publish captura BaseException (engole CancelledError)
22 passed in 5.69s
```

Não executei integração com Redis real nem os gates completos de lint/typecheck.

**MUST-FIX**

1. **HIGH — reinício não invalida métricas de laços desligados.**  
   `announce` está dentro de `if config.chain_curves_enabled` e `if lab is not None`; com o radar inteiro desligado, a função estaciona antes dessas publicações. [main.py:183](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:183), [main.py:249](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:249), [main.py:313](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:313).

   **Cenário:** processo A publica p95; processo B sobe antes dos 30 segundos com Lab/cadeia desligados. B não sobrescreve os campos novos, mas o runtime renova o hash a cada 10 segundos. Os valores de A podem permanecer indefinidamente junto de `ts` recente. O UUID antigo identifica uma geração, mas sozinho não comprova que ela pertence ao processo atual. [runtime.py:42](/C:/dev/project-hunter/packages/core/hunter_core/runtime.py:42), [runtime.py:101](/C:/dev/project-hunter/packages/core/hunter_core/runtime.py:101).

   **Correção:** publicar a geração/estado dos dois medidores também quando desligados, antes dos desvios de configuração, e testar reinício sobre hash previamente preenchido. Considerar também falha do `announce`: hoje ela é absorvida, deixando os campos anteriores até uma publicação posterior bem-sucedida. [cycle_metrics.py:149](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:149).

2. **MEDIUM — a suíte aceita engolir `CancelledError` durante a publicação.**  
   Comprovei: trocar apenas `except Exception` por `except BaseException`, em memória, mantém **22 testes verdes**. O teste existente cancela após uma publicação que não suspende; não força o cancelamento dentro do publisher. [test_cycle_metrics.py:250](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:250).

   **Cenário:** essa regressão faria o wrapper consumir o cancelamento de shutdown enquanto aguarda Redis; o `forever` poderia continuar e atrasar o encerramento do `TaskGroup`.

   **Correção:** publisher sinaliza entrada com `Event` e fica bloqueado; o teste cancela nesse ponto e exige `CancelledError`, sem incremento de `publish_failed_total`. Cobrir `timed_step` e `announce`.

**NICE-TO-HAVE**

- **LOW — `started_at` não valida UTC.** `record` rejeita datas ingênuas/offset não zero, mas o construtor aceita esses mesmos valores e os publica em `cycle_since`. Cenário: caller fornece `datetime` sem timezone e produz proveniência temporal ambígua. O caminho atual de produção usa `utcnow`, portanto não bloqueia este diff. [cycle_metrics.py:101](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:101), [cycle_metrics.py:113](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:113).
- **LOW — teste do orçamento é pouco discriminante.** Solicita 50 ms, mas tolera até 2 segundos: uma regressão que fixe o timeout em 1 segundo ainda passa. [test_cycle_metrics.py:288](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:288).

**O QUE EU FARIA DIFERENTE**

Fecharia o contrato de boot e acrescentaria os testes acima, mantendo a estrutura atual. O teste de `announce` hoje verifica um dicionário publicado, sem simular hash antigo nem executar os caminhos condicionais de `main`; por isso não detecta o primeiro achado. [test_cycle_metrics.py:296](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:296).

**CONCORDO COM**

- **Laço:** preserva resultado e exceções do passo; mede antes de publicar e mantém o sono posterior. A cadência passa a incluir o custo da instrumentação/publicação. Há também dois `announce` sequenciais no boot, que podem atrasar a criação das tarefas seguintes. [cycle_metrics.py:187](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:187), [collect.py:341](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:341), [main.py:256](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:256). O orçamento de 1 segundo é cooperativo, não garantia rígida sob bloqueio do event loop.
- **Cancelamento atual:** propaga. `CancelledError` deriva de `BaseException`; o `except Exception` não o captura. O timeout próprio vira `TimeoutError`, tratado como falha de publicação. A prova direta confirmou o cancelamento externo. [cycle_metrics.py:154](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:154), [documentação Python](https://docs.python.org/3.12/library/asyncio-task.html#task-cancellation).
- **Redis:** compartilha cliente/pool, não uma conexão simultaneamente emprestada às duas tarefas. No redis-py inspecionado, cancelamento durante envio/leitura fecha a conexão; o cliente a devolve ao pool no `finally`. Não encontrei caminho que entregue ao heartbeat a resposta pendente do `HSET`. O comando pode já ter sido aplicado no servidor quando ocorre o cancelamento. [redis.py:98](/C:/dev/project-hunter/packages/core/hunter_core/redis.py:98), [client.py:924](/C:/dev/project-hunter/.venv/Lib/site-packages/redis/asyncio/client.py:924), [connection.py:1315](/C:/dev/project-hunter/.venv/Lib/site-packages/redis/asyncio/connection.py:1315), [fonte oficial](https://redis.readthedocs.io/en/stable/_modules/redis/asyncio/connection.html).
- **Campos/API:** não há colisão. `chain_cycle_s` continua separado dos novos `chain_cycle_ms_*`; os campos de `lab_heartbeat` também são distintos. Os leitores existentes consultam nomes explícitos e não passam a consumir automaticamente essas métricas. [sources.py:326](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/sources.py:326), [lab_heartbeat.py:46](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_heartbeat.py:46), [meme_sources.py:207](/C:/dev/project-hunter/apps/api/hunter_api/services/meme_sources.py:207), [meme_lab_goal.py:154](/C:/dev/project-hunter/apps/api/hunter_api/services/meme_lab_goal.py:154).
- **Instância:** configuração e Compose pressupõem uma instância `radar`; isso não equivale a exclusão distribuída que impeça iniciar outro processo. [config.py:39](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/config.py:39), [__main__.py:17](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/__main__.py:17), [docker-compose.yml:637](/C:/dev/project-hunter/infra/docker/docker-compose.yml:637).
- **Cálculo:** nearest-rank correto, `deque(maxlen=window)`, duração inteira monotônica e throttle por laço. Remover `maxlen` ou publicar antes de registrar seria detectado pelos testes existentes. [cycle_metrics.py:102](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:102), [lab_heartbeat.py:32](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_heartbeat.py:32), [test_cycle_metrics.py:60](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:60), [test_cycle_metrics.py:161](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:161). Não há cálculo monetário nem `print` nos três arquivos; contagens verificadas: **209/337/316 linhas**, abaixo de 350.

**OBSIDIAN**

- **Revisão da Astra — tempo de ciclo da cadeia e do Lab:** registrar esta rodada, reabrindo a correção de proveniência e acrescentando a mutação que escapou dos testes.
- **Meme — o que uma “estratégia” é aqui:** corrigir a afirmação de limpeza no boot para contemplar laços desligados e falha de publicação.
- **EXP-M26 — gráfico em moedas maduras:** registrar que métricas de geração anterior não servem como evidência da guarda §6.8.