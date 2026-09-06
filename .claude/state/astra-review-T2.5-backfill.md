**RESUMO**

O desenho é viável sem migração, mas eu corrigiria **ACK/reavaliação, concorrência na criação de gaps, planejamento parcial e orçamento temporal** antes de implementar.

Respostas diretas:

- **(i)** Prioridade por idade é defensável como preferência pela janela recente. Não exige coluna de origem, mas precisa dos ajustes abaixo para proteger a coleta.
- **(ii)** Grupo por shard funciona nessa topologia. Faltam considerar namespace por exchange, replay na troca de `n`, sobreposição de processos e perda por trimming.
- **(iii)** Além dos testes propostos, os mais importantes são concorrência, falhas entre commit e ACK, republicação do mesmo `event_id` após recusa e progresso de pedidos parcialmente planejados.

Revisão como `backend-specialist`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes; esta é uma revisão de desenho. Acrescentaria estes cenários ao aceite:

| Cenário | Resultado exigido |
|---|---|
| Recusa por mercado não monitorado → mercado volta → republicação uma hora depois, **mesmo `event_id`** | Pedido reavaliado e atendido |
| Commit dos gaps → queda antes do ACK → restart/reclaim | Nenhuma lacuna redundante |
| Dois pedidos sobrepostos e detecção periódica concorrentes | Cobertura planejada sem duplicação |
| Gap `failed` entre duas corridas novas | Fusão não atravessa seu cooldown |
| Mais de 12 corridas; pedido maior que sete dias | Cobertura restante explícita e progresso comprovado nas próximas passagens |
| Histórico lento; lacuna recente surge durante sua recuperação | Nova detecção não espera dez timeouts |
| Envelope inválido, além de payload inválido | Mensagem isolada; próxima mensagem válida processada; coletor continua |
| `initialized=True`, universo vazio; follower inicia antes do líder | Sem espera infinita por `changed`; recusa temporária não envenena republicação |
| Um minuto; fronteiras de graça; timestamps com segundos, sem timezone ou com offset | Contagem e normalização explicitamente definidas |
| Símbolo Unicode; `market_id` incompatível com símbolo/exchange | Roteamento correto; identidade inconsistente recusada |
| Bootstrap concorrente com publicação ao vivo | Outbox e consumidores mantêm progresso, com atraso medido |
| Histórico atravessando mês sem partição; REST vazio/parcial; coordenação Redis indisponível | Sem conclusão fictícia, sem perda do pedido por erro transitório |

**MUST-FIX**

**1. Item 5: ACK não pode bloquear a reavaliação que você está prometendo.**

O produtor mantém a identidade da janela na republicação; o TTL de uma hora só controla quando volta a publicar. Já `ack()` grava o `event_id`, e `consume()` consulta os conjuntos de hoje e ontem antes de entregar ao handler. Portanto, a republicação horária **não garante atendimento na hora seguinte**. Fontes: [backfill.py:88](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/backfill.py:88), [backfill.py:102](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/backfill.py:102), [consume.py:134](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:134), [consume.py:239](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:239).

**Falha concreta:** mercado recusado às 10h, volta às 10h15, republicação às 11h é descartada pela guarda antes da consulta ao universo.

Dentro das restrições, minha recomendação é:

- Recusa dependente do estado atual — mercado fora do universo, desconhecido naquele momento, janela ainda futura — recebe **`XACK` físico sem marcar a janela como processada**.
- Planejamento integral, duravelmente confirmado, pode usar a guarda normal após commit.
- Erro transitório de Postgres/Redis/relógio da exchange **não é recusa**: mantém pendência e retenta com backoff.

Concordo em não deixar uma recusa de negócio na PEL esperando o universo mudar. Discordo de “nunca retry” se isso incluir falhas de infraestrutura.

**2. Item 3: subtrair cobertura não resolve concorrência; fundir depois pode desfazer a subtração.**

O modelo tem índice de status/data, mas nenhuma unicidade por intervalo. A detecção atual consulta cobertura e depois insere gaps. Um segundo planejador acrescenta outro escritor a esse protocolo. Fontes: [market_data.py:134](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:134), [recovery.py:249](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:249).

**Falha concreta:** consumidor e recovery leem simultaneamente “minuto ausente, nenhum gap”; ambos inserem. A recuperação pode fazer REST redundante, pois busca antes do lock de atualização do gap. Fonte: [recovery.py:194](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:194).

Eu usaria **serialização transacional por mercado/timeframe, compartilhada pelos dois caminhos de criação**, por exemplo advisory lock transacional no Postgres. Reconsultar cobertura dentro dessa seção; nenhuma chamada REST segurando esse lock. Isso cabe em `services/market-worker/**`.

Outra falha: faltam 10:00 e 10:30, mas 10:01–10:29 está num gap `failed`. Subtrair esse gap e depois unir as duas corridas recria todo o intervalo, contornando o cooldown.

**Pode unir através de velas persistidas; não atravesse cobertura `open/failed`.** Essa cobertura deve permanecer uma barreira na fusão.

**3. Item 4: limite de linhas não é limite de tempo nem prioridade estrita.**

Hoje a lista é selecionada uma vez, processada sequencialmente e cada fetch admite 20 segundos. O laço só volta à detecção depois dessa execução. Fontes: [recovery.py:207](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:207), [recovery.py:276](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:276), [recovery.py:338](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:338).

**Falha concreta:** começa a fase histórica sem gaps recentes; surge uma lacuna recente; dez históricos lentos ocupam aproximadamente 200 segundos apenas em fetches antes da próxima detecção.

Eu manteria seus dois estratos, mas exigiria:

- Deadline monotônico para o trabalho histórico, respeitando a próxima detecção.
- Não iniciar outro histórico quando esse orçamento acabar; limitar o timeout ao tempo restante.
- Reavaliar a prioridade entre unidades de trabalho.
- Não fundir um trecho histórico com recente de modo que o `gap_end` recente promova todo o trecho antigo.

Há também uma inversão **dentro** do estrato recente: 50 bootstraps de quase um dia, com `detected_at` anterior, podem preceder uma lacuna de um minuto recém-detectada. Se “prioridade da coleta ao vivo” significa atender primeiro os minutos mais recentes, o desempate precisa refletir isso — por exemplo, `gap_end DESC`, seguido de menor extensão e desempates estáveis. Se significa somente “últimas 24h antes do histórico”, declare essa garantia mais limitada.

Finalmente, **10 gaps é orçamento por shard**, não global. E “100 de peso” não descreve todo o custo: cada `fetch_candles()` também consulta `server_time()`. O rate limiter compartilhado continua necessário, mas não fornece sozinho prioridade entre classes. Fontes: [rest.py:241](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/rest.py:241), [config.py:72](C:/dev/project-hunter/services/market-worker/hunter_market_worker/config.py:72).

**4. Item 3: truncamento precisa de contrato de progresso.**

**Falha concreta:** existem 13 corridas separadas por pelo menos 60 minutos; você registra 12 e marca o `event_id` inteiro como processado. A mesma solicitação republicada não pode planejar a corrida restante durante a janela da guarda. O mesmo problema aparece ao limitar um pedido maior a sete dias. A identidade representa o intervalo original, não a fração aceita: [backfill.py:102](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/backfill.py:102).

Eu trataria sete dias/12 linhas como **orçamento por passagem**, preservando explicitamente o restante. Planejamento parcial não recebe a marca definitiva da janela; uma republicação reconsulta cobertura e avança sobre o que falta. O teste precisa provar esse avanço sem depender de o produtor inventar outra identidade.

Quanto ao lado: **para a primeira passagem, prefiro os minutos mais recentes**, como você propôs. Isso não pode virar descarte permanente da parte antiga. O produtor contempla também a referência de trinta dias do regime: [backfill.py:139](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/backfill.py:139).

**5. Mensagem malformada precisa ser tratada antes do handler.**

O consumidor genérico desserializa o envelope **antes do `yield`**. Capturar validação somente dentro do handler não cobre JSON inválido, campo `data` ausente ou envelope inválido. Fontes: [consume.py:112](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:112), [consume.py:208](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:208).

**Falha concreta:** envelope inválido gera exceção na tarefa; integrada ao `TaskGroup`, ela pode derrubar o coletor inteiro e repetir o problema após restart. Fonte: [main.py:85](C:/dev/project-hunter/services/market-worker/hunter_market_worker/main.py:85).

Como você não pode alterar esse comportamento no core, precisa resolver a leitura/validação por mensagem localmente no market-worker, preservando ID físico para registrar a recusa e dar `XACK`. Reiniciar o gerador genericamente não basta: reencontra a mesma mensagem.

**NICE-TO-HAVE**

- **Partições históricas:** verificar os meses necessários e expor ausência com motivo. As guardas atuais cobrem agora e amanhã, não toda janela solicitada: [partitions.py:5](C:/dev/project-hunter/services/market-worker/hunter_market_worker/partitions.py:5).
- **Pressão do outbox:** medir antes de fixar dez chunks como vazão aceitável. Um chunk pode inserir 1.440 eventos; a prontidão usa limite de 500 pendentes, e o dispatcher ordena por criação. Há risco de o histórico atrasar eventos recentes mesmo com REST bem priorizado. Fontes: [outbox.py:23](C:/dev/project-hunter/services/market-worker/hunter_market_worker/outbox.py:23), [outbox_store.py:210](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:210).
- Acrescentar ao log `event_id`, exchange, shard, IDs dos gaps, intervalo original/efetivo e minutos adiados. `accepted` deve significar planejamento aceito, não recuperação concluída.

**O QUE EU FARIA DIFERENTE**

**Item 1 — manteria fan-out, com grupo `market-worker.backfill.{exchange}.{i}of{n}`.**

O grupo único é inadequado **se cada consumidor só pode atender sua própria fatia**. Não é intrinsecamente errado: funcionaria se qualquer consumidor apenas registrasse gaps globais e o recovery proprietário os drenasse. Não recomendo mudar sua topologia agora.

As armadilhas adicionais:

- Sem exchange no nome, futuros workers de exchanges distintas competiriam no mesmo grupo e poderiam descartar trabalho alheio. Hoje a fábrica só admite Binance: [config.py:25](C:/dev/project-hunter/services/market-worker/hunter_market_worker/config.py:25).
- Mudança de `n` cria grupos que começam em `0`, portanto **releem o histórico retido**. Não existe transferência automática da PEL antiga para os novos grupos: [produce.py:34](C:/dev/project-hunter/packages/core/hunter_core/events/produce.py:34), [consume.py:173](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:173).
- Deployment com topologias antigas e novas sobrepostas pode ter dois recuperadores do mesmo mercado. Planejamento idempotente não elimina automaticamente REST concorrente.
- Pending não protege a mensagem contra trimming. O stream está limitado a aproximadamente 5.000 entradas; shard atrasado pode perder solicitações antes de atendê-las. A republicação/reconciliação é parte necessária da recuperação. Fontes: [streams.py:48](C:/dev/project-hunter/packages/core/hunter_core/events/streams.py:48), [documentação Redis](https://redis.io/docs/latest/commands/xreadgroup/).

O custo de grupos/guardas é aceitável se dimensionado pelo volume real de pedidos. São conjuntos **por grupo e dia**, não uma única chave eterna: [consume.py:22](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:22). Limpeza de grupos antigos deve ser procedimento explícito, sem apagar pendências automaticamente.

**Item 3 — ajustaria o limite superior.**

Para reproduzir exatamente a janela inclusiva atual:

```text
detection_last = align_open_time(server_now) - DETECTION_GRACE
effective_end_exclusive = min(request_end, detection_last + 1 minuto)
last_minute = effective_end_exclusive - 1 minuto
```

Seu clamp direto em `detection_last`, seguido de `−1min`, é conservador, mas exclui um minuto adicional ao recovery. Fonte: [recovery.py:230](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:230).

Também validaria conjuntamente `market_id`, exchange, símbolo e tipo de mercado no banco; timestamps conscientes de timezone e alinhamento ao minuto precisam de política explícita antes de usar `expected_times()`, que avança a partir do início fornecido: [recovery.py:63](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:63).

**CONCORDO COM**

- **Item 2:** esperar `initialized`, não universo não vazio nem somente `changed`. `set([])` inicializa e pode retornar sem sinalizar mudança. Universo vazio válido não trava essa guarda; falhas contínuas antes do primeiro `set()` podem mantê-la aguardando. Fonte: [universe.py:99](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:99). O follower também pode inicializar com consulta vazia antes de o líder popular o banco; por isso a correção do ACK continua necessária: [universe_leader.py:125](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_leader.py:125).
- **Item 3:** conversão semiaberta→inclusiva, subtração de candles finais e chunks de 1.440 minutos são escolhas razoáveis. Uma página não é garantia de conclusão em 20 segundos; timeout continua sendo orçamento, não previsão.
- **Item 4:** não usar `detected_at` futuro. O campo participa efetivamente da reabertura de falhas: [recovery.py:80](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:80).
- **Item 6:** não é necessário outro evento para anunciar cada candle. O caminho atual enfileira somente candles **efetivamente inseridas**, na mesma transação; conflitos não republicam: [persist_rows.py:100](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:100). Isso não confirma sozinho conclusão da janela: ela deve ser reconciliada pela cobertura persistida.
- Métrica local está conforme o precedente, usando **`hunter_market_backfill_requests_total` e `registry=registry` de `hunter_core.observability`**: [metrics.py:20](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/metrics.py:20). Defina `duplicate` como planejamento sem trabalho novo, ou instrumente a leitura local: duplicatas filtradas pelo `consume()` genérico nunca chegam ao handler para serem contadas.

**OBSIDIAN**

- **Market Collector** — registrar planejamento de backfill, prioridades, limites e protocolo de concorrência.
- **Workers** — documentar grupos por exchange/shard, supervisão e retomada após recusa.
- **Data Flow** — descrever pedido → gaps → REST → candles/outbox, distinguindo planejamento de conclusão.
- **Features (Feature Engine)** — explicar progresso parcial do histórico e reavaliação após preenchimento.
- **Revisões da Astra — T2.5-backfill** — registrar os cenários desta revisão e as decisões adotadas; nenhuma página foi alterada nesta rodada.