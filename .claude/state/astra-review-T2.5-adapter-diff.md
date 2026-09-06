**RESUMO**

**Aceito o fechamento do achado 3; não aceito o fechamento do achado 1.** A agregação por pior estado resolve o mascaramento entre keys corretamente sinalizadas, mas ainda falta preservar a ruptura até a retomada.

Revisão como `exchange-integration-specialist`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes; os cenários abaixo são deduções do código.

O comando solicitado retornou `fatal: cannot change to '/c/dev/project-hunter': No such file or directory`. Executei o equivalente no PowerShell:

`git -C C:/dev/project-hunter diff -- packages/exchange-adapters services/market-worker`

Resultado: exit code `0`; diff de 12 arquivos.

**MUST-FIX**

1. **Pergunta 1: ainda existe uma janela antes de sinalizar a ruptura.**

   A atribuição no início do laço não ocorre imediatamente após a queda. No tratamento da conexão estabelecida, primeiro acontece `await self._close_quietly(...)`; somente depois vem `state.ws_state = "reconnecting"`. A rotação limpa também aguarda fechamento antes de voltar ao início do laço. Fontes: [connection.py:207](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:207), [connection.py:209](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:209), [connection.py:216](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:216).

   **Cenário:** socket falha, fila está drenada e `__aexit__` demora dois segundos. Durante esse fechamento, o housekeeping ainda lê `connected` e pode avançar a cobertura sobre a interrupção.

   **Falta:** marcar a ruptura antes do primeiro await de fechamento, tanto no erro quanto na rotação.

2. **Congelar durante a queda não impede declarar continuidade depois dela.**

   Quando `caught_up` fica falso, o tracker apenas registra o log e congela o limite. Quando volta a verdadeiro, avança para `moment - 0.5s`, mantendo o `session_since` anterior. Fontes: [coverage.py:220](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:220), [coverage.py:224](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:224), [coverage.py:233](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:233).

   **Cenário:** sessão começa às 12:00, conexão cai às 12:01 e retorna às 12:02, sem incremento de drops. Depois da retomada, publica aproximadamente `[12:00, 12:01:59.5]`, incluindo a lacuna inteira.

   **Falta:** uma ruptura de conexão deve invalidar a sessão anterior; a retomada confirmada deve estabelecer um novo início conservador. Backlog sem perda pode apenas congelar e depois continuar a mesma sessão.

3. **Uma reconexão inteira pode escapar entre duas leituras.**

   O housekeeping consulta somente o estado atual quando `coverage.due()` permite. Uma rotação ou restart rápido pode passar por `connected → reconnecting → connected` entre essas leituras. Fontes: [streaming.py:58](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:58), [connection.py:175](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:175), [ws.py:229](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:229).

   **Cenário:** rotação e handshake terminam entre stamps, sem backlog nem drops. O tracker nunca observa indisponibilidade e preserva uma sessão que atravessa a ruptura.

   **Falta:** um marcador persistente de ruptura consultado pelo housekeeping. Pode ser uma geração apropriada ou outro marcador; não precisa depender da entrega de eventos.

**NICE-TO-HAVE**

Corrigir os comentários que dizem que ambos os sinais usam `getattr` e que a geração é registrada junto da quebra: o consumidor chama `connection_state()` diretamente e o log mostrado não inclui geração. Fontes: [coverage.py:46](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:46), [coverage.py:60](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:60), [streaming.py:69](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:69), [coverage.py:221](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:221).

**O QUE EU FARIA DIFERENTE**

Separaria três fatos: ruptura persistente, prontidão agregada e fila drenada. A ruptura invalida a sessão; prontidão e drenagem permitem estabelecer uma nova. Testaria fechamento bloqueado, reconexão entre stamps e retomada sem atravessar a lacuna.

**CONCORDO COM**

- **Achado 3 fechado:** `enqueued` conta append, `evicted` cobre os dois ramos de remoção, e `delivered` avança imediatamente antes do yield. A igualdade deixa de produzir backlog permanente após eviction. Fontes: [event_queue.py:102](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:102), [event_queue.py:115](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:115), [event_queue.py:126](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:126), [event_queue.py:207](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:207).
- **Pergunta 2:** sim, uma key saudável não mascara outra cujo estado já esteja marcado como indisponível. O agregado usa o pior estado. Isso não resolve os três cenários acima. Fonte: [ws.py:191](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:191).
- **Pergunta 3:** sim, aceito `connection_generation()` fora de `ExchangeAdapterExtras`, com acesso opcional. O protocolo permanece sem esse requisito e a fachada delega os novos métodos. Fontes: [base.py:152](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/base.py:152), [binance/__init__.py:95](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/__init__.py:95).
- O congelamento usa o último limite já descontado da margem, como solicitado. Fonte: [coverage.py:224](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:224).

**OBSIDIAN**

- **Market Collector** — distinguir congelamento por backlog de ruptura que exige nova sessão.
- **Exchange Adapters** — documentar o balanço `enqueued = delivered + evicted` e as capacidades opcionais.
- **WebSockets** — registrar a janela de fechamento e a necessidade de preservar rupturas entre leituras.
- **Revisões-Astra / T2.5 — cobertura** — registrar achado 3 fechado e achado 1 ainda bloqueado pelos cenários acima.