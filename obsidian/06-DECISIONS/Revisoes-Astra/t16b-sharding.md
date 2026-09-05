---
tags: [astra, revisao]
updated: 2026-09-05
fonte: .claude/state/astra-review-t16b-sharding.md
---

# Revisão da Astra — t16b-sharding

Parte da [[Mente da Sexta-feira]]. Índice: [[Index|todas as revisões]]. Diálogos relacionados: [[Dialogos/M1|M1]], [[Dialogos/M2|M2]].

**Minha escolha: sharding explícito no Compose, 6 shards como dimensionamento inicial conservador, universo global versionado e trabalho por símbolo no shard proprietário.** A proposta de heartbeat precisa de correções antes de ser segura.

Li os arquivos solicitados e os auxiliares necessários. Não li `.env`, não modifiquei arquivos e não fiz commit.

1. **Sharding obrigatório e quantidade**

   **Concordo para esta arquitetura e para o tráfego assumido.** Usando a corrida de 50 mercados, o transporte custa aproximadamente `0,951 × (0,1315 + 0,1162) × 4 ≈ 0,94 core` a 200 mercados. Isso já ultrapassa 70%, antes da aplicação. Os números estão no [perfil:18](C:/dev/project-hunter/.claude/state/t16b-profile.md:18).

   A ressalva: proporcionalidade a **bytes** não garante proporcionalidade a **número de mercados**. A extrapolação é uma boa premissa de planejamento, não uma prova de impossibilidade para qualquer implementação de transporte. Não apostaria T1.6b numa reescrita desse transporte.

   **Projetaria 6 shards; avaliaria reduzir para 4 após medição.** Uma extrapolação conservadora, retirando apenas Pydantic e JSON da corrida de 50, dá aproximadamente `0,951 × (1 − 0,1083 − 0,0552) × 4 = 3,18 cores`: cinco shards perfeitamente equilibrados já seriam necessários abaixo de 70%. Eliminar O(n), normalizações e overhead de agendamento pode melhorar bastante; hash por símbolo pode piorar o equilíbrio. Portanto, seis é orçamento inicial, não resultado medido.

   **Must-fix:** não subtrair percentuais cumulativos sobrepostos nem projetar capacidade pela corrida saturada de 200. O consumidor faminto voltará a consumir CPU quando for agendado; os 0,18% não representam seu custo real ([perfil:68](C:/dev/project-hunter/.claude/state/t16b-profile.md:68)).

   Também corrigiria justiça de agendamento: `await put()` normalmente não suspende quando há espaço, e há criação de task por evento em duas camadas ([event_queue.py:44](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:44), [event_queue.py:120](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:120), [streaming.py:34](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:34)). Usaria processamento em lotes limitados com oportunidades explícitas de execução do consumidor.

2. **Compose e identidade dos shards**

   **Escolho (a): serviços explícitos `market-worker-0..N-1`, configuração comum reutilizada e `MARKET_SHARD` fixo.** O Compose atual já concentra o worker numa definição própria, adequada para essa expansão ([docker-compose.yml:90](C:/dev/project-hunter/infra/docker/docker-compose.yml:90)).

   Concordo com `crc32(symbol.upper().encode("ascii")) % N == i`, aplicado **depois** da seleção global. Manteria `MARKET_UNIVERSE_SIZE=200` em todos. Acrescentaria a validação de `N > 0` e `0 <= i < N` junto das configurações do worker ([settings.py:93](C:/dev/project-hunter/packages/core/hunter_core/settings.py:93)).

   Não derivaria propriedade do hostname: identidade operacional e índice de partição precisam ser contratos distintos. Hoje o runtime usa `hostname:pid` como identidade, sem qualquer contrato de ordinal ([runtime.py:62](C:/dev/project-hunter/packages/core/hunter_core/runtime.py:62)).

   **Must-fix e falhas concretas:**

   - **Índice duplicado:** dois containers coletam/publicam os mesmos símbolos. Exigiria exclusividade de `(exchange, geração, i)` com token de proprietário.
   - **Valores diferentes de N:** aparecem sobreposições e buracos. Todos devem validar uma configuração global de geração/N.
   - **Mudança de N durante rollout:** o módulo redistribui muitos símbolos. Nesta tarefa, manteria N fixo; redimensionamento exige transição coordenada.
   - **Concentração de tráfego:** 33 símbolos podem custar mais que 45. Aprovação depende do shard mais ocupado, não da média.

   Sharding também exige CPU disponível no host: seis processos disputando um único core não resolvem a meta.

3. **Heartbeat canônico agregado**

   **Concordo com preservar a chave canônica; não considero correto o read–compute–write concorrente descrito.**

   **Cenário de corrida:** A lê todos saudáveis e pausa. B observa um shard expirado e publica `disconnected`. A retoma e sobrescreve com `connected`, renovando o TTL de uma conclusão antiga.

   **Faria diferente:** cada shard atualiza seu hash com TTL atomicamente; qualquer shard pode executar um **script Lua curto que lê os N hashes esperados, valida e escreve o agregado com TTL na mesma execução**. Evita snapshot antigo sobrescrevendo decisão nova sem introduzir líder só para agregar. Usaria geração, identidade de execução e sequência para rejeitar amostras de proprietários antigos.

   Regras obrigatórias:

   - **Shard ausente/expirado é falha**, nunca simplesmente excluído do cálculo do pior estado.
   - Usaria uma janela de frescor explícita, por exemplo 15 s, mantendo TTL de 30 s. Assim, morte logo após heartbeat tem uma janela conhecida de detecção.
   - Shard esperado sem símbolos é `idle` válido; shard não inicializado não é equivalente. Hoje essa distinção já aparece no heartbeat ([heartbeat.py:206](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:206)).
   - `subscriptions` soma assinaturas; `markets_monitored` conta símbolos. Não são intercambiáveis ([heartbeat.py:76](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:76), [heartbeat.py:162](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:162)).
   - `last_event_at=max` serve para “último evento em algum shard”; **não prova saúde de todos**. Frescor/progresso de cada shard precisa entrar separadamente no veredito.
   - Somar `reconnects/dropped_events` dos hashes vivos perde histórico quando um shard expira ou reinicia. Para totais operacionais, manteria contadores por processo e agregaria seus incrementos no monitoramento; não chamaria a soma transitória de total durável.
   - Gaps de shard ausente ficam desconhecidos; não equivalem a zero.

   **Partição:** shard sem acesso ao Redis expira mesmo que ainda receba WS; o agregado deve degradar. Se todos perderem Redis, a chave canônica também deve expirar. Não publicaria agregado calculado de cache local.

   **Relógio:** usaria tempo do Redis para frescor dos heartbeats e relógio monotônico para silêncio local. Timestamp de evento precisa de validação própria: a API transforma timestamp mais de 2 s no futuro em `unavailable` ([system_status.py:279](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:279)).

   **Outro must-fix:** agregar também a publicação em `rt:system`. Hoje cada heartbeat publica status local nesse canal; mantê-lo assim faria a UI alternar entre shards ([heartbeat.py:90](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:90)).

   Sem tocar em apps, há dois limites existentes:

   - `/market-status` usa a chave canônica, mas mercados monitorados e gaps vêm do **Postgres** ([system_status.py:251](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:251), [system_status.py:302](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:302)).
   - Novos hashes `hb:market:binance:{i}` também aparecerão no scanner genérico `hb:*`. Se essa duplicação operacional for indesejada, usaria um namespace interno fora de `hb:*` ([system_status.py:214](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:214)).

4. **Distribuição das tarefas**

   | Tarefa | Minha escolha | Falha concreta e tratamento |
   |---|---|---|
   | `run_universe` | **Líder global**, seguidores carregam snapshot e filtram. | Líder morre durante refresh: conservar versão ativa e eleger substituto. Hoje o refresh altera monitoramento global, portanto não deve receber universo reduzido ([universe.py:132](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:132)). |
   | `run_funding` | **Por shard**, símbolos próprios. | Shard morre após buscar settlement e antes de persistir: no retorno, retomar watermark persistido, com escrita idempotente. A consulta atual já parte do máximo persistido por mercado ([funding.py:37](C:/dev/project-hunter/services/market-worker/hunter_market_worker/funding.py:37)). |
   | `oi_poll_loop` | **Por shard**, símbolos próprios. | Shard morto perde amostra histórica daquele instante; não inventar recuperação com OI atual. Distribuir chamadas ao longo da janela, preservando bucket lógico ([sampling.py:285](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:285)). |
   | `snapshot_loop` | **Por shard**, símbolos próprios. | Shard morto perde snapshots locais. Não preencher retrospectivamente com estado atual. O caminho já lê hot state dos símbolos recebidos e verifica frescor ([sampling.py:184](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:184), [sampling.py:217](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:217)). |
   | `run_recovery` | **Por shard**, mercados próprios. | Shard morto adia recuperação; gaps persistidos continuam disponíveis. Dois proprietários simultâneos podem duplicar REST: o lock atual só ocorre **depois** do fetch ([recovery.py:186](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:186)). Incluir gaps pendentes de símbolos removidos, não apenas os atualmente monitorados. |
   | `assert_writable_partitions` | **Em todos**, sem eleição; é verificação global localmente executada. | Follower inicia quando falta partição e não pode confiar numa verificação antiga do líder. A função consulta existência; não cria partições ([partitions.py:69](C:/dev/project-hunter/services/market-worker/hunter_market_worker/partitions.py:69), [partitions.py:158](C:/dev/project-hunter/services/market-worker/hunter_market_worker/partitions.py:158)). |

   **Must-fix de rate limit:** concordo que o bucket já é distribuído e recebe Redis na fábrica ([config.py:72](C:/dev/project-hunter/services/market-worker/hunter_market_worker/config.py:72)). Porém, **o cooldown por IP não é distribuído** ([rate_limit.py:114](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:114)).

   Falha: shard A recebe `Retry-After`; B continua chamando outro bucket pelo mesmo IP. Compartilharia o prazo de bloqueio no Redis, sem acrescentar shard à chave do orçamento. Também revisaria o orçamento global de recovery: o limite atual de 50 gaps por ciclo vira até `50 × N` ao replicar ([recovery.py:38](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:38)). Bucket compartilhado limita gasto, mas não garante justiça entre recovery e OI/funding.

5. **Refresh e divergência de universo**

   **Escolho líder + snapshot global versionado + notificação.** Não escolheria REST independente por shard.

   **Must-fix:** `SETNX` e TTL, sozinhos, não protegem contra líder antigo retomando após uma pausa. Usaria aquisição atômica com expiração, renovação/liberação condicionadas ao token e proteção contra escritor antigo **no recurso que recebe a escrita**, inclusive Postgres.

   O evento atual contém apenas `added/removed/total` e sai depois da transação de atualização ([universe.py:148](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:148)). Logo:

   - Follower reiniciado precisa carregar **snapshot completo**, não esperar próximo diff.
   - Líder pode morrer depois do commit e antes da publicação. Faria reconciliação periódica da versão persistida.
   - Cada shard precisa receber a notificação: não compartilhar um consumer group que distribua cada evento a apenas um deles.

   **Divergência por segundos:** com N fixo e hash estável, um símbolo que permanece no universo mantém seu dono. Isso evita migração desnecessária. Entretanto, não elimina buracos: a nova lista pode incluir um símbolo antes de seu dono aplicar a assinatura.

   Para tornar a transição inofensiva à cobertura, prepararia a versão nova mantendo assinaturas antigas; cada dono adiciona seus novos símbolos e confirma prontidão. Só então ativaria o novo universo global e removeria os antigos. Se um shard falhar, manteria a versão anterior e sinalizaria transição pendente. Delistagem real é exceção: deve aparecer como indisponibilidade, não como cobertura artificial.

6. **Readiness por shard**

   **Concordo:** cada `/ready` avalia seu conjunto atribuído, além de Redis, banco, persistência e partições. O healthcheck local na porta 8001 já está definido ([docker-compose.yml:117](C:/dev/project-hunter/infra/docker/docker-compose.yml:117)); o runtime combina dependências e checks adicionais ([runtime.py:117](C:/dev/project-hunter/packages/core/hunter_core/runtime.py:117)).

   **Must-fix:** a readiness atual não verifica “meus símbolos estão ok”. Ela considera estado da conexão e um único `last_data`; um evento recente pode manter a ingestão pronta enquanto vários mercados estão sem dados ([supervision.py:43](C:/dev/project-hunter/services/market-worker/hunter_market_worker/supervision.py:43), [supervision.py:60](C:/dev/project-hunter/services/market-worker/hunter_market_worker/supervision.py:60)).

   Acrescentaria cobertura/frescor por símbolo e campos exigidos, calculados periodicamente, com denominador da versão global atribuída. Não exigiria eventos recentes de canais naturalmente esparsos, como liquidações.

   Shard legitimamente vazio pode estar pronto **após inicializar e validar propriedade**. Erro de configuração produzindo lista vazia não pode virar `idle` saudável. A cobertura global deve ser `Σ mercados_ok / 200`, não média simples das porcentagens dos shards.

7. **Métricas de saturação**

   **Exporia as duas, mas não chamaria idade do último frame de atraso do consumidor.** Leitor atualizado e consumidor atrasado é justamente o cenário desta tarefa.

   | Métrica | Tipo | Cálculo |
   |---|---|---|
   | `market_ws_queue_depth` | Gauge | `len(queue)` no scrape ou amostragem periódica. Já existe `__len__` ([event_queue.py:82](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:82)). |
   | `market_ws_receive_event_age_seconds` | Gauge | `agora − último E válido`, por conexão/rota. Mede idade do último evento recebido, incluindo silêncio. |
   | `market_event_lag_seconds` | Gauge | `agora − E` do evento mais antigo aguardando processamento, incluindo o evento em execução quando aplicável. Mede atraso pendente. |
   | `market_event_loop_lag_seconds` | Gauge | Atraso de uma task periódica em relação ao prazo monotônico esperado. Expõe starvation diretamente. |

   Usaria labels limitados a exchange, shard e, quando aplicável, conexão/rota; sem label por evento.

   No caminho quente, apenas guardaria o inteiro `E` já decodificado e metadados mínimos necessários. Conversão para segundos e atualização Prometheus ficam fora dele. O acesso à cabeça da fila é O(1). **Custo literalmente zero para preservar informação nova não existe**, mas não exige JSON adicional, datetime ou histograma por frame.

   **Must-fix:** não reutilizar `_frame_ts` como se fosse sempre `E`: hoje ele prefere `event.ts` e até `close_time`, que pode ser futuro numa candle parcial ([ws.py:250](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:250)). Relógio adiantado deve sinalizar skew, não produzir lag zero “saudável”.

8. **O que eu não faria**

   - Não aumentaria a fila para esconder saturação nem aceitaria descarte O(1) como solução para “zero descartes”. A política atual descarta explicitamente quando cheia ([event_queue.py:47](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:47)).
   - Não prometeria perda zero sob qualquer falha apenas com sharding/backpressure. Há descarte por idade também na persistência ([persist.py:194](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:194)). Backpressure limita memória; não garante retenção ilimitada nem recuperação de todos os tipos de evento.
   - Não removeria Pydantic dos contratos públicos indiscriminadamente. Otimizaria a representação interna preservando validação necessária, precisão e semântica. O custo concentrado em dezenas de `BookLevel` por snapshot justifica começar ali ([streams.py:194](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:194)).
   - Não reduziria canais, profundidade ou frequência para declarar a mesma meta atingida.
   - Não implementaria autoscaling, rebalanceamento dinâmico ou failover automático de propriedade nesta tarefa.
   - Não aceitaria apenas CPU média e heartbeat verde como prova. Exigiria **200 mercados no denominador, cobertura ≥95%, cada shard abaixo de 70%, filas/lag estáveis e zero incremento dos contadores de descarte**, incluindo refresh, recovery e reconexões. Dimensionaria também conexões ao banco: cada processo tem pool configurado separadamente ([settings.py:51](C:/dev/project-hunter/packages/core/hunter_core/settings.py:51)).