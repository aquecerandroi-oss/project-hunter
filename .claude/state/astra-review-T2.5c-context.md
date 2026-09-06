## RESUMO

**Eu manteria a janela decodificada, mas não aprovaria “C + D1 garantem igualdade com Redis”.** O evento de fechamento não é um registro de todas as mutações da lista.

Minha recomendação para T2.5c: **manter 1500 linhas, ler a lista completa e reutilizar a decodificação das linhas cujo msgpack não mudou**. Isso cabe inteiramente em `services/scanner-worker/**`, ataca o custo identificado e permite provar equivalência sem depender da entrega de eventos. A latência resultante ainda precisa ser medida.

Papel adotado: `backend-specialist`; modo OPINIÃO.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei testes nem benchmarks. As conclusões abaixo vêm da leitura do código; os cenários descritos são casos propostos para reprodução.

## MUST-FIX

### 1. C + D1 não são suficientes

Há três contraexemplos concretos:

- **Evento atrasado:** o WS altera uma vela fora das 16 primeiras; o scanner avalia antes da persistência/publicação do fechamento. A leitura completa já enxerga a mudança; a janela incremental ainda não. A escrita no Redis antecede o enfileiramento durável em [ingest.py:179](C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:179).
- **REST primeiro, WS depois:** REST insere uma vela histórica no Postgres e seu evento é consumido. Depois, uma vela WS daquele minuto preenche um buraco ou substitui uma parcial no trecho invisível do Redis. O `INSERT … DO NOTHING` encontra a linha existente e **não produz outro evento**: somente as linhas retornadas pelo `INSERT` são anunciadas. Veja [recovery.py:159](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:159) e [persist_rows.py:133](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:133).
- **Parcial antiga:** uma atualização WS não final, com `event_ts`, pode entrar no caminho de reescrita completa. Ela não gera `market.candles.closed`. Isso já quebra a afirmação sobre a janela, mesmo quando aquela parcial não afeta o vetor do corte corrente. Veja [hot_state_candles.py:83](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state_candles.py:83) e [ingest.py:181](C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:181).

Portanto, **“só WS escreve” não implica “cada escrita relevante é anunciada”**.

Sobre expiração e remoção:

- O escritor de candles não atribui TTL; seus caminhos usam `LSET`, `LPUSH/LTRIM` ou `DELETE/RPUSH/LTRIM`. O truncamento normal é para 1500 entradas: [hot_state_candles.py:61](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state_candles.py:61), [hot_state_candles.py:99](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state_candles.py:99).
- Ausência de TTL não protege de políticas `allkeys-*`; políticas `volatile-*` selecionam chaves com expiração. Não consultei a configuração efetiva do Redis em execução. [Documentação oficial de eviction](https://redis.io/docs/latest/develop/reference/eviction/).
- **Contraexemplo à fusão:** cache com 1500 entradas; chave removida e recriada apenas com a parcial do mesmo minuto da cabeça. C aceita a sobreposição e preserva 1499 entradas que Redis perdeu.
- Uma resposta com **menos de 16 linhas é a lista completa** naquele instante: deve substituir a janela, inclusive quando vazia. Um `LTRIM` externo para 100 linhas, preservando as primeiras 16, continua invisível à leitura curta.

Também exigiria cabeça não regressiva e sobreposição efetiva, além da desigualdade. C mede avanço em **entradas**, não em minutos: vinte minutos sem novas velas podem deixar a mesma cabeça.

### 3. Memória: manteria 1500; 1440 tem um problema maior que o ATR

Pelos números fornecidos, reduzir 1500 para 1440 economiza somente **4%: aproximadamente 19,5 MB** nos 200 mercados.

Além da mudança de ancoragem, **1440 linhas incluindo uma parcial deixam 1439 finais**. `relative_volume_1h` pede `60 × (23 + 1) = 1440` minutos finais; essa folga foi deliberada no código: [volume.py:14](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:14), [volume.py:69](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:69). Portanto, a redução pode tornar a feature indisponível durante a formação da vela.

Sua observação sobre o ATR procede: o número de barras depende do trecho contíguo utilizável, e a reconstrução fria parte da barra completa mais antiga disponível. Os números 100/96 dependem também do alinhamento e das parciais: [windows.py:208](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:208), [atr.py:266](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:266).

**Não abro mão da identidade dos resultados.** Aceitaria aproximadamente 487,5 MB como orçamento candidato, condicionado à medição do processo inteiro: RSS, pico durante reconstrução, bootstrap, baselines e eventual armazenamento dos bytes. `tracemalloc` sozinho não fecha esse orçamento.

LRU seria uma segunda opção, removendo apenas o cache de candles. Com 200 mercados continuamente ativos e capacidade inferior a 200, porém, ele pode transformar cada passagem numa sequência de reconstruções. Não o escolheria antes de medir.

### 4. O teste precisa separar mutação de Redis de entrega do evento

O caso prioritário é:

> Cache quente → REST insere a vela histórica e seu evento é consumido → WS altera o Redis fora das 16 primeiras → scanner avalia sem novo evento.

Também acrescentaria:

| Caso | O que verifica |
|---|---|
| Escrita histórica seguida de avaliação **antes** do evento | Divergência transitória que a amostragem por minuto pode esconder |
| Parcial → outra parcial → final; cortes antes/depois de `event_ts` e `close_time` | Preservação do corte intraminuto |
| Chave vazia, recriada com a mesma cabeça, lista reduzida para 15, 16 e 100 entradas | Remoções que uma união preservaria indevidamente |
| 1499 → 1500 → 1501 entradas | Descarte exato da cauda e atualização de `truncated` |
| Evento recebido durante o `await` da reconstrução | Invalidação que não pode ser apagada ao instalar a resposta |
| Reinício com checkpoint, sem checkpoint e corte regressivo | Continuidade e reconstrução do ATR |

Compare também **janela completa e `truncated`**, não somente as duas saídas. Uma divergência em dados atualmente inutilizados pode não aparecer em `canonical_bytes()` ou `as_wire()`.

O oráculo deve receber o mesmo snapshot de entrada e o mesmo corte, com caches/checkpoints independentes. E o fake precisa simular remoção de listas: o atual `FakeHotState.delete` remove apenas strings, enquanto `expire` não faz nada — [builders.py:207](C:/dev/project-hunter/services/scanner-worker/tests/builders.py:207), [builders.py:219](C:/dev/project-hunter/services/scanner-worker/tests/builders.py:219).

## NICE-TO-HAVE

### 2. Ressincronização periódica: útil como reconciliação, insuficiente como garantia

Se mantiver a leitura curta, **D3 tem utilidade real diante dos contraexemplos acima**, mas nenhum N positivo estabelece identidade em todos os cortes.

Como ponto inicial experimental, defenderia **N = 5 minutos**, somente se for explicitamente aceitável haver divergência entre reconciliações. Com seu custo estimado:

`200 × 50 ms / 300 s ≈ 3,3% de um núcleo`, em média.

Esse cálculo não limita os picos. Use distribuição estável por exchange/símbolo e um orçamento global de reconstruções; hash sozinho não impede colisões de horários.

Distinga ainda:

- “no máximo uma reconstrução a cada N minutos” limita frequência;
- “no máximo N minutos sem reconstrução bem-sucedida” limita idade.

D1, sem refinamento, pode invalidar também em fechamentos normais, pois o minuto fechado frequentemente já está na cabeça ou atrás dela. Inclua essa concentração na virada do minuto no benchmark.

**Na alternativa de leitura completa com decode reutilizado, eu dispensaria D3 para consistência.**

## O QUE EU FARIA DIFERENTE

**Primeiro experimento:** um cache limitado ao snapshot corrente, indexando bytes msgpack por objeto decodificado. A cada `LRANGE 1500`:

1. Reutilizar objetos para bytes idênticos.
2. Decodificar somente linhas novas ou alteradas.
3. Reconstruir a sequência exatamente com as linhas recebidas.
4. Descartar entradas ausentes e calcular `truncated` pelo limite 1500.

Isso preserva remoções, reordenações, reescritas históricas e a precedência já aplicada pelo escritor. Mantém tráfego e comparação O(1500), mas elimina a reconstrução dos objetos inalterados. O loader atual separa leitura de decodificação, permitindo essa composição no scanner: [hotstate.py:76](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:76), [context.py:118](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/context.py:118).

### 5. Bootstrap: regra simples com suspensão e histerese

Preferiria **suspender novas fatias quando houver atraso**, mantendo o job intacto. Como parâmetros iniciais de teste: suspender com idade do sujo mais velho acima de 1 s; retomar abaixo de 0,5 s, com atraso do loop também recuperado. Esses valores são hipóteses de tuning, não prova do SLA.

A checagem deve ocorrer em cada fronteira cooperativa. Hoje uma chamada externa pode ter orçamento de 120 s, embora ceda internamente: [config.py:80](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/config.py:80), [replay.py:148](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay.py:148). Checar apenas no `baseline_loop` reagiria tarde.

Os 50 ms também não são teto rígido: o relógio é consultado depois de produzir um vetor. A prova deve considerar **uma unidade indivisível de trabalho excedendo a fatia**. Sob sobrecarga permanente, aceite e exponha a suspensão do bootstrap; não force progresso sacrificando a prioridade declarada.

### 6. Invalidação: `CandleWindow` com entrada explícita em `MarketState`

Usaria os dois, com responsabilidades distintas:

- `MarketState.note_closed_candle(candle)` marca sujo e encaminha a notificação.
- `CandleWindow` controla validade, substituição/fusão, limite, `truncated` e geração de invalidação.

O handler já decodifica a vela; pode encaminhá-la nesse ponto: [main.py:190](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:190). **Não inseriria o corpo do evento na janela Redis**, porque ele também pode vir do REST.

Na versão incremental, capture a geração antes do `await`; só limpe a invalidação se ela não mudou. Isso evita perder um evento recebido durante a leitura. A encapsulação protege contra esquecimento local, mas não resolve eventos que nunca chegam.

## CONCORDO COM

Manter finais e parciais na janela e aplicar novamente o corte em cada contexto. Esse é o comportamento do `build_context`: [context.py:286](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:286). Concordo também em tratar D2 como precaução, sem atribuir à cobertura do tape uma garantia sobre candles.

Para aceitar p99 ≤ 3 s, a prova precisa incluir publicação e filas. A métrica atual é observada dentro de `advance`, antes da publicação feita pelo runner: [scanner.py:182](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:182), [runners.py:80](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:80). E o teste de carga ainda reutiliza candles de um símbolo nos demais mercados: [test_load.py:62](C:/dev/project-hunter/services/scanner-worker/tests/test_load.py:62).

## OBSIDIAN

- **Features (Feature Engine)** — registrar a necessidade de 1440 velas finais, a folga das 1500 entradas e o contrato de equivalência do cache.
- **Market Collector** — documentar que eventos de fechamento representam inserções duráveis, não todas as mutações do hot state.
- **Workers** — registrar a política de contrapressão e a fronteira da medição tick→oportunidade.
- **Revisoes-Astra/T2.5c — desenho do scanner** — criar a revisão com os contraexemplos e a alternativa de reutilização do decode; decisão ainda pendente.