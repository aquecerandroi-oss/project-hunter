**RESUMO**

**Concordo com a direção, mas não considero o achado 1 fechado com o desenho atual.** O contador identifica tentativas de reconexão; falta distinguir **ruptura, retomada e pertencimento do evento à sessão**. Os contadores de fila fecham a janela `popleft → yield`, mas precisam contabilizar descartes.

Revisão como `exchange-integration-specialist`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes. Os cenários abaixo são deduções do fluxo de código, não resultados de execução.

**MUST-FIX**

**1. Propostas 1 e 3 / pergunta (i): concordo com os caminhos cobertos; discordo do momento e da suficiência da detecção.**

O callback junto de `state.reconnects += 1` alcança retries, reconexão por erro/ociosidade e rotação proativa. `_start_group` para uma key reutilizada cobre o restart externo ao laço. Fontes: [connection.py:135](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:135), [connection.py:166](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:166), [ws.py:186](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:186).

Não encontrei outro caminho de **reconexão corretiva silenciosa** no `SubscriptionController`: falha de envio, timeout e rejeição de SUBSCRIBE convergem para restart; falha no catch-up entra no tratamento do runner. Fontes: [subscriptions.py:194](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:194), [subscriptions.py:207](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:207), [subscriptions.py:230](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscriptions.py:230), [connection.py:160](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:160).

**Cenário que continua escapando:** socket cai, fila esvazia e nenhum evento novo chega. O runner espera fechamento/backoff **antes** de incrementar o contador na próxima tentativa. Depois disso, `observe_generation()` também depende de chegar um evento. Durante esse intervalo, `enqueued == delivered` e `_in_flight == 0`; o housekeeping pode continuar avançando a cobertura. Hoje ele não verifica estado da conexão. Fontes: [connection.py:194](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:194), [streaming.py:58](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:58).

**Correção necessária:** invalidar a continuidade quando a ruptura é reconhecida, antes dos awaits de fechamento/backoff, e fazer a publicação verificar essa invalidade **mesmo sem eventos**. A geração pode continuar existindo, mas não substitui o estado “sessão interrompida”.

**2. Proposta 3 / pergunta (iii): discordo de usar o `received_at` do próximo evento sem provar sua origem. Trocar por “agora” sozinho também não resolve.**

**Cenário:** há um evento recebido às 12:00:00 aguardando entrega. A conexão rompe às 12:00:01; a geração muda. Às 12:00:02, o consumidor recebe aquele evento antigo, lê a geração atual e abre a sessão em 12:00:00. A lacuna volta a ficar dentro do intervalo declarado.

Isso é possível porque a fila preserva eventos durante o restart, e `get()` descarta a connection key antes da entrega. Fontes: [ws.py:195](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:195), [event_queue.py:105](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:105).

Existe ainda o caso de **outra key saudável** entregar um evento enquanto a key rompida continua reconectando: a fila é compartilhada entre leitores. Esse evento também não prova retomada da exchange inteira. Fonte: [event_queue.py:119](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:119).

**Minha preferência:** `received_at` é válido se pertencer comprovadamente à sessão retomada e não anteceder a recuperação das conexões/subscrições exigidas. Sem essa informação, prefiro o instante conservador em que a retomada foi confirmada. **O instante de detectar mudança de geração não é necessariamente esse instante.**

**3. Propostas 2 e 4 / pergunta (ii): concordo para o item retirado; discordo da igualdade sem contabilizar descartes.**

Incrementar `delivered` **imediatamente antes do `yield`, sem await entre ambos**, fecha a janela identificada: enquanto `get_task` retirou o item mas o gerador não o entregou, `enqueued > delivered`. Incrementar depois do `yield` atrasaria a contagem até a próxima retomada do gerador. Fonte: [event_queue.py:153](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:153).

Mantenha também `_in_flight`: entregue não significa escrito. O consumidor atual chama `writing()` antes de aguardar `handle_event()` e `written()` no encerramento desse processamento. Fonte: [streaming.py:86](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:86).

**Cenário bloqueante:** enfileira A, descarta A por overflow, enfileira B e entrega B. Resultado: `enqueued=2`, `delivered=1`, fila vazia. A diferença nunca desaparece, mesmo depois de horas saudáveis. A fila realmente remove itens previamente aceitos nos dois caminhos de eviction. Fonte: [event_queue.py:82](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:82).

**Correção:** contar separadamente os itens **enfileirados e depois descartados**:

`caught_up = enqueued == delivered + evicted`

O descarte do evento entrante antes do append não entra em `evicted`; continua sendo perda que rompe cobertura. Esse caminho existe em [event_queue.py:65](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:65). Não confundir “pendências resolvidas” com “todos os eventos entregues”.

Quanto ao item 4, guardaria **o último `covered_until` seguro**, já descontada a margem, e congelaria nele. Se `_last_caught_up_at` guardar o relógio bruto, o primeiro stamp com backlog pode ganhar indevidamente os 0,5 s antes retidos. Reinício/ruptura deve invalidar essa referência; sem referência segura na sessão atual, não publicar intervalo.

**4. Proposta 5: concordo com a compatibilidade do consumidor, mas “fakes continuam exatamente como hoje” precisa de ressalva.**

`ExchangeAdapterExtras` é `runtime_checkable`; adicionar métodos altera sua conformidade estrutural. Há testes que exigem `isinstance(fake, ExchangeAdapterExtras)` e o equivalente para Binance. Fontes: [base.py:152](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/base.py:152), [test_fake_adapter.py:54](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_fake_adapter.py:54), [test_binance_adapter.py:55](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_binance_adapter.py:55).

Atualize os implementadores desse contrato ou use um protocolo separado para cobertura. E exponha os métodos também na fachada `BinanceAdapter`: o worker recebe essa fachada, cujos métodos delegam ao cliente WS. Caso contrário, o `getattr` cai silenciosamente no comportamento antigo. Fonte: [binance/__init__.py:76](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/__init__.py:76).

**NICE-TO-HAVE**

Testes determinísticos, controlando a ordem das tasks, para:

- Reconexão sem eventos durante o backoff.
- Evento antigo entregue após mudança de geração.
- Evento de key saudável enquanto outra permanece caída.
- Item retirado antes do `yield`, escrita pendente e eviction seguida de drenagem.

**O QUE EU FARIA DIFERENTE**

Separaria explicitamente **ruptura → indisponibilidade → retomada confirmada**. Usaria geração para invalidar a sessão, progresso para provar drenagem e `_in_flight` para provar conclusão da escrita. Só então avançaria o limite temporal, preservando a margem.

**CONCORDO COM**

**Pergunta (iv): aceito a quebra exchange-wide.** Não exigiria cobertura persistida por símbolo/key nesta correção. O tracker atual já mantém uma sessão por exchange e a invalida integralmente. Fonte: [coverage.py:93](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:93).

Mas **quebra global exige retomada global**: um evento de uma key saudável não pode reabilitar as demais. Pode ser necessário controlar prontidão por key dentro do adaptador, mantendo o contrato externo agregado.

Concordo também com excluir o primeiro connect de uma key nova da contagem de **reconexões**; isso não dispensa comprovar que suas subscrições ficaram prontas.

**OBSIDIAN**

- **Market Collector** — registrar ruptura, retomada confirmada e congelamento no último limite seguro.
- **Exchange Adapters** — documentar geração, progresso de entrega e contabilização separada de eviction.
- **WebSockets** — distinguir tentativa de reconexão de retomada das subscrições.
- **Revisões-Astra / T2.5 — cobertura** — registrar concordâncias numeradas, cenários restantes e testes de fechamento.