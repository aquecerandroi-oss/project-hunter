## RESUMO

**REQUEST_CHANGES:** a geração nova resolve o reinício **com laços habilitados e anúncio bem-sucedido**, mas ainda deixa métricas zumbis quando um laço é desligado. Também falta um teste que cancele a publicação em andamento.

Revisão como `code-reviewer`, considerando a primeira rodada e a decisão de instrumentar antes do seed em [EXP-M26:530](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M26-grafico-em-moedas-maduras.md:530).

## ARQUIVOS

Nenhum arquivo criado ou modificado. Inspecionados os três arquivos pedidos, escritores/leitores do heartbeat, runtime, configuração de implantação e redis-py instalado.

## TESTES

**Não executei pytest, lint nem testes de mutação**, respeitando o modo estritamente sem escritas. As conclusões sobre cobertura abaixo são por inspeção, não resultados executados.

## MUST-FIX

**1. MEDIUM — métricas antigas sobrevivem ao boot com laço desligado.**

Os anúncios ficam dentro de `if config.chain_curves_enabled` e `if lab is not None`: [main.py:249](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:249), [main.py:313](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:313). Desabilitar o Lab publica seus campos tradicionais, mas não os campos novos de ciclo: [main.py:206](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:206), [lab_heartbeat.py:46](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_heartbeat.py:46).

**Cenário:** o processo A publica p95; reinicia em menos de 30 s como B, com cadeia ou Lab desligados. B não substitui aquele `cycle_run_id`, contador ou p95. O runtime continua renovando o TTL do hash inteiro, preservando-os indefinidamente: [runtime.py:101](/C:/dev/project-hunter/packages/core/hunter_core/runtime.py:101).

Um leitor iniciado depois desse boot não consegue concluir, apenas pelo UUID presente, que a geração pertence ao processo anterior. A mesma ambiguidade existe temporariamente se `announce` falhar e o primeiro ciclo ainda não terminar: [cycle_metrics.py:149](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:149).

**Correção:** anunciar estado vazio/habilitado/desabilitado dos dois medidores em todo boot, inclusive com radar inteiramente desligado; vincular a geração ao boot atual e exigir essa correspondência no consumidor. Testar com hash previamente preenchido. Não apagar o hash inteiro, pois há outros escritores.

**2. MEDIUM — o teste de cancelamento não protege o novo ponto vulnerável.**

O `publish` do teste não contém suspensão; registra o dicionário e retorna. Portanto, o cancelamento externo não chega durante `_publish`: [test_cycle_metrics.py:250](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:250).

**Cenário de regressão:** trocar `except Exception` por `except BaseException` em [cycle_metrics.py:156](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:156) engoliria o cancelamento recebido durante o HSET. O teste atual ainda pode passar porque cancela durante `step` ou `sleep`, fora desse bloco.

**Correção:** um publisher sinaliza “entrei” e fica suspenso; o teste espera esse sinal, cancela a tarefa e exige `CancelledError`, sem incrementar `publish_failed_total`. Cobrir também `announce`.

## NICE-TO-HAVE

- **UTC do início:** `record` recusa horário ingênuo ou offset diferente de zero, mas `started_at` não é validado. Um chamador pode publicar `cycle_since` sem UTC. Produção usa `utcnow`, portanto é endurecimento do contrato: [cycle_metrics.py:101](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:101), [cycle_metrics.py:113](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:113).
- **Precisão do overrun:** 60.000,4 ms arredonda para 60.000 e não conta excesso. Está coerente com a quantização atual, mas “maior que o período” deve ser entendido em milissegundos arredondados: [cycle_metrics.py:119](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:119), [cycle_metrics.py:192](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:192).
- **Teste do orçamento frouxo:** solicita 50 ms, mas aceita conclusão dentro de 2 s. Uma implementação que ignore o argumento e sempre use 1 s passaria: [test_cycle_metrics.py:288](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:288).

## O QUE EU FARIA DIFERENTE

**Comportamento e cancelamento.** O retorno e a exceção do passo permanecem preservados. Há custo adicional de medição, percentis/log e publicação; no boot também há dois `await announce`, que atrasam a criação das tarefas seguintes. A cadência fica aproximadamente `passo + instrumentação/publicação + sleep`: [cycle_metrics.py:187](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:187), [main.py:256](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:256), [main.py:315](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:315), [collect.py:341](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:341).

O **cancelamento externo propaga** na implementação atual: `CancelledError` deriva de `BaseException`; o timeout converte seu próprio cancelamento em `TimeoutError`, capturado fora do contexto. O orçamento de 1 s é cooperativo, não garantia rígida sob bloqueio do event loop. [Código: cycle_metrics.py:154](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:154); [documentação Python](https://docs.python.org/3.12/library/asyncio-task.html#timeouts).

**Redis compartilhado.** Compartilha-se cliente/pool; comandos concorrentes não utilizam simultaneamente a mesma conexão emprestada. No redis-py 8.1.0 fixado no [uv.lock:1449](/C:/dev/project-hunter/uv.lock:1449), cancelamento durante envio/leitura fecha aquela conexão com `disconnect(nowait=True)`; o cliente a libera no `finally`. Não encontrei corrupção do protocolo do heartbeat. Há reconexão posterior, e timeout não prova que o servidor deixou de aplicar o HSET. Referências: [connection.py:1204](/C:/dev/project-hunter/.venv/Lib/site-packages/redis/asyncio/connection.py:1204), [connection.py:1315](/C:/dev/project-hunter/.venv/Lib/site-packages/redis/asyncio/connection.py:1315), [client.py:973](/C:/dev/project-hunter/.venv/Lib/site-packages/redis/asyncio/client.py:973); [fonte oficial](https://redis.readthedocs.io/en/stable/_modules/redis/asyncio/connection.html).

**Instância única.** Há um serviço declarado no Compose e identidade fixa `radar`; isso expressa intenção operacional, não exclusão mútua. Não há trava de singleton no caminho inspecionado. Dois processos escreveriam alternadamente suas gerações na mesma chave. Não afirmo quantas instâncias existem na VPS: [docker-compose.yml:637](/C:/dev/project-hunter/infra/docker/docker-compose.yml:637), [__main__.py:17](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/__main__.py:17).

## CONCORDO COM

- **Sem colisão de campos encontrada.** `chain_cycle_s` continua separado das novas durações em ms; os campos tradicionais `lab_*` também são distintos. Os leitores examinados da API selecionam campos explicitamente e não expõem os novos percentis: [sources.py:326](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/sources.py:326), [cycle_metrics.py:131](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:131), [meme_sources.py:207](/C:/dev/project-hunter/apps/api/hunter_api/services/meme_sources.py:207), [meme_lab_goal.py:154](/C:/dev/project-hunter/apps/api/hunter_api/services/meme_lab_goal.py:154).
- **Percentil, anel e throttle corretos:** nearest-rank; `deque(maxlen=window)`; contadores acumulados independentes; throttle monotônico por wrapper. Suprimidos aparecem no próximo overrun elegível: [lab_heartbeat.py:31](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_heartbeat.py:31), [cycle_metrics.py:102](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:102), [cycle_metrics.py:193](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:193).
- **Dois testes detectam as mutações simples perguntadas:** publicar antes de medir falharia nas expectativas de duração/contador; retirar `maxlen` falharia no tamanho e máximo após expulsão do 900. A lacuna é engolir cancelamento durante publicação: [test_cycle_metrics.py:161](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:161), [test_cycle_metrics.py:60](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:60).

## OBSIDIAN

- **Meme — README:** corrigir a promessa de limpeza em todo boot; registrar desabilitação, geração e pressuposto de instância única.
- **Revisões Astra — meme-cycle-metrics:** acrescentar esta rodada, distinguindo cancelamento correto de cobertura insuficiente.
- **EXP-M26 — gráfico em moedas maduras:** manter coleta durável e validação de geração/cobertura como pendências antes do seed.

Nenhuma página foi alterada.