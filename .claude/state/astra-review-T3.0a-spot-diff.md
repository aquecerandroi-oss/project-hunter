## RESUMO

**Eu corrigiria dois pontos antes de entregar como componente isolado: o orçamento de heartbeat do WS e o limite final dos candles.** Não exigiria livro local nem unificação HTTP nesta tarefa.

## ARQUIVOS

Revisão em modo OPINIÃO, como `exchange-integration-specialist`. Nenhum arquivo criado ou modificado; nenhum commit.

## TESTES

`git diff --check -- packages/exchange-adapters` → saída vazia, código **0**.

Não executei pytest, ruff, pyright ou file-size nesta rodada. Os **370 testes** são o resultado informado por você, não uma verificação minha.

## MUST-FIX

**1. PING automático ultrapassa a reserva do throttle.**

O SPOT reserva apenas um slot para PONG e usa `default_connect` — [ws.py:81](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/ws.py:81), [ws.py:135](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/ws.py:135). Esse conector chama `websockets.connect(url)` sem configurar heartbeat — [connection.py:49](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:49).

**Cenário:** quatro controles + PING automático da biblioteca + PONG respondendo à Binance na mesma janela = **seis mensagens**, acima de cinco. A biblioteca habilita PING periódico por padrão; a Binance contabiliza PING, PONG e controles. [websockets](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html), [Binance](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#websocket-limits).

**Correção:** conector próprio SPOT com `ping_interval=None`, preservando respostas automáticas aos pings do servidor, e teste dessa configuração. O teste atual exercita somente `send()` — [test_spot_ws_client.py:304](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_spot_ws_client.py:304).

**2. `fetch_candles()` não garante `[start, end)`.**

Envia `endTime=end_ms` e acrescenta as respostas sem filtrar o intervalo — [rest.py:196](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/rest.py:196), [rest.py:203](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/rest.py:203).

**Cenário:** consulta histórica `[12:00, 12:30)` inclui a barra aberta às 12:30 pelo limite inclusivo da API. Como `is_final` usa o horário atual do servidor, essa barra pode chegar finalizada e contaminar uma janela histórica de volume.

**Correção:** enviar `endTime=end_ms-1` e garantir `start <= open_time < end` na saída. Testar explicitamente a fronteira.

O teste de paginação também precisa realmente paginar: sua primeira página tem três linhas, mas o cliente encerra quando recebe menos de 1000; a segunda página nunca é consultada — [test_spot_rest_client.py:241](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_spot_rest_client.py:241), [rest.py:212](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/rest.py:212).

## NICE-TO-HAVE

`fee_for()` promete arredondar sempre para cima, mas usa `ROUND_HALF_UP`, que também arredonda para baixo. Alinhar documentação e política; não considero essa diferença subcentavo bloqueadora do adaptador — [fees.py:89](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/fees.py:89), [fees.py:99](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/fees.py:99).

## O QUE EU FARIA DIFERENTE

**(1) Timestamp:** aceito `ts=received_at` como fallback documentado dentro deste escopo — [streams.py:192](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/streams.py:192), [streams.py:244](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/streams.py:244). Porém, **igualdade dos campos não é um discriminador inequívoco** de proveniência. Na integração, declarar essa capacidade explicitamente. Não substituir por horário de `aggTrade` ou `serverTime`: nenhum deles informa quando aquele livro foi produzido. Recepção também não prova ausência de atraso anterior no socket.

**(2) Sequência:** sim, pode descartar um frame legítimo repetido quando não houve mudança no livro. Isso não perde uma atualização, mas `sequence == previous` deveria ser contabilizado como duplicata, sem warning de regressão — hoje ambos seguem o mesmo caminho em [ws.py:306](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/ws.py:306). Manteria a deduplicação; saltos crescentes são aceitáveis para snapshots completos do top 20. Não exigiria contiguidade.

**(3) Depth20 + REST100:** aceitável para simulação MARKET com profundidade limitada. O REST disponibiliza esse snapshot — [rest.py:244](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/rest.py:244). O cuidado obrigatório na T3.4 é:

- REST obtido na decisão serve ao risco; o fill exige livro elegível **após a latência**.
- Não combinar top 20 novo com níveis 21–100 antigos.
- Não extrapolar quantidade além dos níveis observados nem repor consumo pela reentrega do mesmo snapshot.

Essas condições já constam do contrato de execução — [M3.md:138](C:/dev/project-hunter/docs/plans/M3.md:138). Não são motivo para exigir livro local agora.

## CONCORDO COM

**(4)** Aceito a duplicação HTTP temporária. A cobrança por tentativa e o tratamento explícito de 429/418 estão presentes — [http.py:124](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/http.py:124). Unificação posterior, com testes dos dois adaptadores.

**(5)** Após os dois MUST-FIX, considero adequada a entrega isolada. A integração continua bloqueada pela identidade incompleta nos eventos, corretamente registrada — [identity.py:23](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance_spot/identity.py:23).

## OBSIDIAN

- **Exchange Adapters** — registrar T3.0a, os dois ajustes e o bloqueio de integração.
- **WebSockets** — documentar PING/PONG no orçamento SPOT e distinguir duplicata de regressão.
- **Paper Trading** — explicitar disponibilidade após latência, profundidade limitada e consumo por snapshot.
- **Revisoes-Astra/Index** — vincular esta revisão e a posterior comprovação das correções.