## (1) MUST-FIX — each with a concrete failure scenario

**Revisão provisória:** não consegui ler os arquivos solicitados: a política do ambiente bloqueou até `Get-Content`. Portanto, não posso citar linhas do repositório, avaliar `market.py`/`base.py` nem afirmar que os pontos abaixo estão ausentes do M1. São critérios de aprovação baseados no seu resumo; nenhum arquivo foi modificado.

1. **Validar o roteamento atual dos WebSockets.** A documentação distingue `/public` para depth e `/market` para trades e mark price. **Falha:** conectar tudo no endpoint antigo deixa o book funcionando enquanto outros streams ficam silenciosos. Exigir teste de recebimento por tipo de stream, além do ACK de assinatura. [Binance — Connect, linhas 158–172](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect).

2. **Definir explicitamente snapshot parcial versus delta.** **Falha:** aplicar cada top-20 como delta preserva níveis que saíram da janela e inventa liquidez; descartar mensagens intermediárias de diff book corrompe a reconstrução. O contrato deve identificar a semântica, a profundidade disponível e a validade. Para diff book, exigir bootstrap REST+buffer e continuidade `pu == u_anterior`. [Binance — reconstrução, linhas 158–169](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly).

3. **Separar “último dado recebido” de “última escrita no Redis”.** **Falha:** o coalescer republica um preço congelado a cada 250 ms e renova o TTL; a página continua verde durante uma desconexão. Preservar timestamps da origem e recepção, atualizar frescor somente com dados novos e expor qualidade por componente.

4. **Definir recuperação por classe de dado e impedir regressão temporal.** **Falha:** após reconectar, um backfill REST atrasado sobrescreve estado WS recente; ou um snapshot atual faz desaparecer o registro de uma lacuna histórica. Separar recuperação do estado atual de reparação histórica, usar cursores duráveis e registrar intervalos irrecuperáveis.

5. **Limitar buffers e definir comportamento quando o banco para.** **Falha:** Postgres indisponível por 30 minutos provoca crescimento ilimitado da fila até OOM; o restart perde tudo. Exigir limites em bytes/itens/idade, política de descarte ou armazenamento durável e métricas de perda. Para dados históricos, “último valor vence” não é garantia de entrega.

6. **Tornar persistência e retomada idempotentes.** **Falha:** o commit termina, mas o worker cai antes de confirmar o lote; o replay duplica candles/trades. Usar chaves naturais adequadas, checkpoint consistente com o commit e proteção para que candle parcial não sobrescreva candle fechado.

7. **Incluir prova operacional no aceite.** **Falha:** a tarefa WS morre, mas o processo principal continua vivo; Docker mostra “running” indefinidamente. Exigir supervisão de tarefas, progresso por stream, shutdown com prazo e teste superior a 24 horas, incluindo indisponibilidade de Redis/Postgres e reconexão.

## (2) NICE-TO-HAVE

- Capturas pequenas de mensagens reais para testes de parsing, duplicação, reordenação e mudanças de schema.
- Histórico das revisões do universo: membros, ranking, motivo de entrada/saída e instante de vigência.
- Métricas de atraso p50/p95/p99, tamanho de filas, bytes por segundo e tempo de recuperação.
- Página de mercado mostrando separadamente idade do book, preço, mark price e histórico; um único indicador de conexão é insuficiente.
- Teste de carga reproduzível com períodos de alta atividade e consumidor lento.

## (3) O QUE EU FARIA DIFERENTE

| Escolha | Minha proposta |
|---|---|
| **depth20 a 250 ms versus diff book** | Manteria top-20 no M1 para visualização e métricas limitadas à profundidade observada. Não o usaria para prometer replay completo ou execução além dos níveis disponíveis. A documentação lista cadência de 250 ms, mas o schema explicita apenas sufixos `100ms`/`500ms`: validaria `@depth20` e não presumiria que `@depth20@250ms` é aceito. [Binance — Partial Book Depth](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public). |
| **Universo por volume de 24 h** | Usaria volume na moeda de cotação, filtros de contrato/status e moedas comparáveis. Acrescentaria histerese: como ponto inicial, revisão a cada 5 minutos e permanência mínima de 30 minutos. Novos membros passam por bootstrap antes de ficarem prontos. |
| **TTLs** | TTL controla retenção, não validade. Começaria com retenção de 60 segundos para estado rápido, preservando metadados de indisponibilidade por mais tempo. A validade expira antes e é calculada pelos timestamps. |
| **Coalescing de 250 ms** | Aplicaria somente à publicação de estado materializado. Deltas precisam ser processados antes; trades destinados ao histórico não podem ser simplesmente substituídos. Mediria o atraso adicional introduzido pelo temporizador. |
| **Persistência em lote** | Flush por tempo, quantidade **ou bytes**, o que ocorrer primeiro. Ponto inicial: 1 segundo ou 1.000 registros, ajustado por medição. Separaria candles fechados, eventos e amostras de book por necessidade de retenção. |
| **Recovery** | Máquina de estados por símbolo/componente: `BOOTSTRAPPING → LIVE → STALE/RECOVERING`. Snapshot parcial recupera estado atual; diff exige reconstrução; candles exigem backfill paginado e deduplicado. Recuperação tem orçamento REST próprio. |
| **Staleness** | Como valores iniciais para book a 250 ms: aviso após 1 segundo sem atualização e indisponível após 3 segundos. Calibraria por comportamento observado. Trades, mark price e candles precisam de regras próprias; silêncio de trades não prova desconexão. |
| **Uma conexão por 200 símbolos** | Usaria 200 como ponto inicial, condicionado a streams, rota, bytes/s e atraso do consumidor. Separaria `/public` e `/market`, com distribuição estável dos símbolos. O limite documentado é por **streams**, não símbolos: 1.024 por conexão. [Binance — Connect](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect). |

## (4) RISCOS que o plano ignora

**Não posso confirmar omissões sem ler o plano. Estes são os riscos a verificar:**

- **Rate limits e bans:** uma reconexão coletiva dispara snapshots e backfills simultaneamente. Centralizar orçamento por IP, consumir os headers de peso e interromper retries agressivos em `429`; insistência pode resultar em `418`. [Binance — limites, linhas 244–254](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info).
- **Clock skew:** um ajuste do relógio produz idade negativa e classifica dados antigos como recentes. Usar relógio monotônico para intervalos locais, UTC para registro e medir desvio em relação à exchange.
- **Renomes, redenominações e delistings:** concatenar séries pelo ticker pode misturar instrumentos economicamente diferentes. Preservar identidade interna, histórico de metadados e transições explícitas; não fazer stitching automático.
- **Reconexão de 24 horas:** conexões criadas juntas podem cair juntas. Rotacionar antecipadamente com jitter, sobreposição limitada e deduplicação. A validade de 24 horas é documentada. [Binance — Connect, linha 175](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect).
- **Crescimento de memória:** além das filas, conferir mapas de símbolos removidos, tarefas órfãs, buffers de bootstrap, históricos de erro e clientes WS lentos.
- **Perda do Redis:** reconstruir a partir de fontes apropriadas e marcar estado como indisponível durante o bootstrap. Um cursor existente apenas no Redis não permite retomada durável.
- **Amplificação de escrita no Postgres:** persistir uma amostra por símbolo a cada 250 ms para 200 símbolos gera **69,12 milhões de registros/dia**, antes de índices e WAL. Batch reduz overhead transacional, mas não esse volume. Definir amostragem, retenção e orçamento de disco antes do aceite.
- **Viés de pesquisa:** selecionar hoje os maiores volumes e aplicar essa seleção ao passado introduz informação futura. Guardar o universo efetivamente conhecido em cada instante é necessário para avaliar resultados posteriormente.

## (5) CONCORDO COM

- Começar com dados públicos reais e paper trading, mantendo o M1 focado na confiabilidade da ingestão.
- Combinar REST para descoberta/bootstrap com WS para atualização contínua.
- Separar Redis para consulta rápida e Postgres para histórico durável.
- Tornar staleness e gaps visíveis nas páginas de mercados.
- Usar top-20 como simplificação inicial, desde que a cobertura limitada esteja explícita.
- Tratar operação contínua como requisito do milestone, com recuperação verificável.

Para concluir a revisão solicitada com achados atribuídos a arquivos e linhas, preciso do conteúdo dos sete arquivos nesta conversa ou de acesso de leitura funcional.

A política automática do ambiente rejeitou a leitura local com a razão `blocked by policy`; não há mecanismo de aprovação disponível nesta sessão.