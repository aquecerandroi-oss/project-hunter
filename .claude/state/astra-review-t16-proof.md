**Meu veredito é “parcial”.** Está provado que o pipeline recebe dado real, persiste e inicia recuperação automática. Ainda não está provado que sustenta os 200 mercados continuamente e conclui a recuperação sem intervenção. Correções despachadas precisam de uma nova execução operacional para fechar o aceite.

Não alterei arquivos nem li `.env`.

**Must-fix para o aceite — defeitos e provas pendentes**

1. **Fechar a prova de recuperação integral.** O registro termina com **376 gaps abertos**, apenas 45 mercados com vela de 16:46 e sem linha para 16:47. Isso prova recuperação iniciada, não concluída. Também houve um minuto com 194 velas: “200 mercados, todo minuto” excede a evidência. [t16-proof.md:484](C:/dev/project-hunter/.claude/state/t16-proof.md:484), [t16-proof.md:338](C:/dev/project-hunter/.claude/state/t16-proof.md:338).

   **Cenário:** corte de alguns minutos, restauração e acompanhamento até preencher cada par esperado `(mercado, minuto)`, sem duplicatas, dentro de um prazo de recuperação definido antes do teste. Registrar os mercados esperados por instante: houve troca de universo durante o restart. Contagem de gaps não equivale a contagem de minutos ausentes; “399 = 2 × 200” precisa de reconciliação. [t16-proof.md:428](C:/dev/project-hunter/.claude/state/t16-proof.md:428), [t16-proof.md:478](C:/dev/project-hunter/.claude/state/t16-proof.md:478).

2. **Repetir o apagão com falha que sobreviva ao restart.** Segundo o próprio relatório, o bloqueio desapareceu quando o container reiniciou. Portanto, não foi provada recuperação depois de uma indisponibilidade externa prolongada, atravessando vários reinícios. [t16-proof.md:443](C:/dev/project-hunter/.claude/state/t16-proof.md:443).

   **Cenário:** manter o bloqueio em um gateway/proxy separado do worker por 10–15 minutos; depois liberar. Exigir retorno automático, tentativas controladas e recuperação completa das velas.

3. **Resolver a semântica do `/ready` durante reconexão.** Há algo além da chave contraditória: o próprio HTTP volta de 503 para **200 durante o bloqueio**. O código permite até 120 segundos de tolerância em `connecting/reconnecting`; isso explica a possibilidade, mas não demonstra ingestão disponível. [t16-netcut.log:14](C:/dev/project-hunter/.claude/state/t16-netcut.log:14), [supervision.py:60](C:/dev/project-hunter/services/market-worker/hunter_market_worker/supervision.py:60).

   **Cenário:** interromper dados, deixar o watchdog reconectar e verificar que o simples início de uma tentativa não restabelece prontidão. Eu exigiria progresso recente nas conexões necessárias para voltar a declarar ingestão pronta.

4. **Revalidar Postgres e acrescentar Redis, incluindo indisponibilidade longa.** A prova do Postgres termina com restart manual para restaurar serviço. No código consultado, o heartbeat também aguarda escrita/publicação Redis sem tratamento local; é um caminho concreto a exercitar, não uma falha operacional já demonstrada. [t16-proof.md:554](C:/dev/project-hunter/.claude/state/t16-proof.md:554), [heartbeat.py:167](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:167).

   **Cenários locais:** parar/iniciar cada dependência; pausar/despausar para simular conexão pendurada; iniciar o worker com dependência indisponível. Usar 30 segundos e vários minutos: a fila de persistência tem idade máxima padrão de 60 segundos, portanto é necessário atravessar esse limite e conferir perdas, sinalização e backfill. [queues.py:118](C:/dev/project-hunter/services/market-worker/hunter_market_worker/queues.py:118), [queues.py:159](C:/dev/project-hunter/services/market-worker/hunter_market_worker/queues.py:159).

5. **Provar capacidade sustentada e recuperação após morte abrupta.** A amostra com CPU saturada, dados expirados e mercados indisponíveis não sustenta aceite do conjunto de dados em tempo real. [t16-proof.md:259](C:/dev/project-hunter/.claude/state/t16-proof.md:259).

   **Cenários:** rodar pelo menos 24–48 horas, atravessando virada UTC e refreshes, medindo idade por componente/mercado, memória, atraso do event loop, descartes e idade do gap mais antigo. Acrescentar morte abrupta durante persistência/backfill, por exemplo OOM controlado em stack descartável. A saída fatal supervisionada prova restart, mas não substitui interrupção sem oportunidade de limpeza. [t16-proof.md:448](C:/dev/project-hunter/.claude/state/t16-proof.md:448).

6. **Investigar um risco adicional de falsa recuperação.** O recovery avança `gap_start` até a primeira vela recebida, assumindo que o histórico anterior não existe. Uma resposta parcial sem as primeiras velas pode, portanto, reduzir a obrigação de cobertura indevidamente. [recovery.py:138](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:138).

   **Cenário:** simular REST retornando apenas o sufixo de um intervalo conhecido de mercado antigo. Exigir que o prefixo continue pendente; estreitar o intervalo precisa de evidência de início de negociação, não apenas ausência na resposta.

**Nice-to-have e próximos cenários**

| Cenário local | O que acrescenta |
|---|---|
| Silenciar uma conexão WS e manter a outra ativa, usando proxy separado por conexão | Verifica se tráfego saudável mascara falha parcial. O teste registrado cortou ambas. [t16-proof.md:456](C:/dev/project-hunter/.claude/state/t16-proof.md:456) |
| Simular REST 429, 5xx, timeout e resposta vazia/parcial | Verifica contenção de tentativas e retomada do backfill sem provocar limites na Binance real. |
| Interromper somente REST, mantendo WS; depois inverter | Separa continuidade de ingestão e capacidade de recuperação. |
| HTTP autenticado de ponta a ponta | Fecha a lacuna entre chamada direta ao serviço e endpoint funcionando para usuário autenticado. [t16-proof.md:199](C:/dev/project-hunter/.claude/state/t16-proof.md:199) |
| Stack descartável com partição futura ausente ou armazenamento esgotado | Exercita falhas que aparecem com tempo de operação, não apenas perda de conectividade. |

Se esses comportamentos forem requisitos explícitos de T1.6, deixam de ser nice-to-have.

**O que faria diferente**

Eu definiria antecipadamente limites de frescor, prazo de recuperação e perdas aceitáveis por tipo de dado. Separaria bootstrap de regime estável e identificaria a imagem exata de cada execução.

Também mediria cobertura por mercado/minuto e compararia uma amostra de OHLCV com REST. `count(*) = 200` sozinho não prova identidade dos mercados nem correção dos valores. E proteção da vela final contra descarte **nessa fila** não equivale a garantia de entrega ponta a ponta. [event_queue.py:44](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:44).

**Severidades: o que concordo e o que ajustaria**

- **CRITICAL-1:** concordo como bloqueador total de T1.6: impedia carregar qualquer universo. [t16-proof.md:40](C:/dev/project-hunter/.claude/state/t16-proof.md:40).
- **HIGH-1:** concordo pelo impacto medido no dado entregue, não pelo percentual de CPU isoladamente. Atribuir a causa exata exige profiling.
- **HIGH-1b:** classificaria isoladamente como **MEDIUM**, pois a degradação já aparece em métricas e na API; o descarte explícito é que fica invisível. Manteria HIGH se quantificar perda for requisito operacional indispensável. [t16-proof.md:296](C:/dev/project-hunter/.claude/state/t16-proof.md:296).
- **HIGH-2 e HIGH-3:** concordo, especialmente pela cascata e necessidade de intervenção demonstradas.
- **MEDIUM-1:** concordo. Separaria dele o retorno HTTP 200 sem recuperação comprovada da ingestão.
- **Backfill lento:** MEDIUM apenas se converge dentro do prazo aceito. Se o backlog cresce continuamente ou excede o prazo necessário ao produto, vira HIGH e bloqueia aceite.

Concordo com o valor da prova real: ela encontrou defeitos que testes simulados não capturaram e demonstrou degradação visível ao consumidor. O aceite **parcial** preserva esses resultados sem transformar recuperação iniciada e execução curta em garantia de operação 24/7.