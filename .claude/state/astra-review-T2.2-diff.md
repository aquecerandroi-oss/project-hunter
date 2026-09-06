## RESUMO

**DONE_WITH_CONCERNS — eu corrigiria os cinco pontos abaixo antes de reportar DONE.** Há caminhos de look-ahead pelo checkpoint e pelo candle sem timestamp, cobertura de trades presumida, ATR antigo publicado como fresco e dependência da precisão Decimal ambiente.

Revisão estática no papel de `quant-engineer`, limitada aos arquivos indicados e à documentação de contexto.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei pytest, lint ou typecheck nesta revisão. Os **177 passed** e demais verificações são resultados informados por você, não reproduzidos por mim. Os cenários abaixo foram identificados por inspeção; não os apresento como testes executados.

## MUST-FIX

**1. P1 — Checkpoint posterior ao corte contamina uma avaliação passada.**

`advance_from_context` preserva o checkpoint quando não encontra barras posteriores a ele; não verifica se a última barra do checkpoint fechou até `ctx.as_of`. `AtrPercent` verifica somente se o checkpoint ficou **atrás**, nunca se está **à frente**. [atr.py:270](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:270), [trend.py:77](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:77).

**Cenário:** processar até 12:30 e depois reavaliar um evento de 12:15 com o estado atual. O ATR incorpora a barra 12:15–12:30 e pode sair como `ok` no vetor de 12:15. Momentum e breakout também leem esse estado. [trend.py:125](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:125), [trend.py:205](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:205).

**Correção:** rejeitar estado posterior ao corte ou exigir checkpoint histórico compatível. Ignorar barras antigas preserva idempotência, mas não autoriza usar estado futuro em uma leitura passada.

**2. P1 — Gap recente permite ATR antigo com qualidade `ok`; falta a dependência do checkpoint.**

Quando `bars_15m` não consegue produzir nenhuma barra, `advance_from_context` devolve o checkpoint antigo com motivo. O engine descarta esse motivo. `AtrPercent` também retorna o número como `ok` quando a janela está indisponível. [windows.py:127](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:127), [atr.py:263](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:263), [engine.py:92](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:92), [trend.py:76](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:76).

**Cenário:** checkpoint aquecido até 04:00; contexto até 04:40 com o minuto 04:20 ausente. Até a âncora 04:30 restam apenas nove minutos contíguos, então não há barra agregada. Entretanto, os últimos 16 minutos estão completos e o feed está fresco: `momentum_15m` consegue dividir o retorno atual pelo ATR de 04:00 e publicar `ok`. [trend.py:91](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:91), [trend.py:140](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:140), [quality.py:112](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:112).

**Correção:** representar a validade e o timestamp do checkpoint como dependência compartilhada de ATR, momentum, aceleração e breakout. Hoje todos declaram apenas candles; `_inherit` não consegue transmitir uma falha do estado. [trend.py:52](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:52), [trend.py:115](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:115), [trend.py:156](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:156), [trend.py:195](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:195).

**3. P1 — O trade mais antigo não prova cobertura contínua até `as_of`.**

O loader transforma o timestamp do primeiro trade em `covers_from`. A seleção verifica somente o início, e a política declara o tape disponível como `ok`, independentemente da idade. [hotstate.py:204](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:204), [windows.py:168](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:168), [quality.py:169](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:169).

**Cenário:** interrupção na coleta deixa no payload trades antigos, mas nenhum da janela atual. Como existe um trade anterior ao início, `TradeVelocity` publica zero `ok`, embora tenham ocorrido trades durante a interrupção. Após reconectar, um trade novo também não prova que o intervalo perdido foi recuperado. [micro.py:189](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:189).

**Correção:** exigir evidência de cobertura contínua até o fim da janela, incluindo interrupções/perdas. Sem essa informação, `insufficient_coverage`. **Concordo com zero para janela comprovadamente vazia; discordo de inferir essa prova apenas dos trades presentes.**

**4. P1 — Candle em formação sem `event_ts` atravessa o corte.**

O construtor estrito aceita timestamp ausente; o builder também aceita explicitamente `event_ts is None`. Depois a política mantém o valor como `degraded/unknown_age`. [context.py:157](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:157), [context.py:245](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:245), [quality.py:134](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:134).

**Cenário:** parcial de 12:00 atualizado às 12:00:50, sem timestamp de atualização, entra numa avaliação de 12:00:20. A janela atravessa o corte corretamente, mas o preço contém informação dos próximos 30 segundos. Degradar não elimina o vazamento.

**Correção:** parcial sem timestamp causal deve ser rejeitado no construtor estrito e descartado/indisponível no builder. O teste atual chega a exigir que um parcial sem timestamp seja mantido. [test_context.py:125](C:/dev/project-hunter/packages/indicators/tests/unit/test_context.py:125).

**5. P2 — Duas somas de quantidades dependem do contexto Decimal ambiente.**

`bid_qty + ask_qty` e `buys + sells` ficam fora de `localcontext(CONTEXT)`. Entrar no contexto fixo apenas para a divisão não recupera dígitos perdidos na soma. [micro.py:108](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:108), [micro.py:159](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:159).

**Cenário:** quantidades `1.234` e `2.345`, sob precisão ambiente 2, produzem total `3.6`; sob precisão 28, `3.579`. A mesma amostra e versão geram pressão e imbalance diferentes.

**Correção:** incluir toda a aritmética no contexto fixo; testar invariância sob precisões ambientes diferentes.

## NICE-TO-HAVE

- **Identidade da política:** `FreshnessPolicy(book_max_age_s=60)` conserva `quality_v1`. Um book de 45 segundos muda de degradado para válido sem mudar a identidade publicada. Persistiria os parâmetros efetivos ou exigiria identidade distinta para overrides. [quality.py:63](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:63), [engine.py:106](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:106), [test_vector.py:214](C:/dev/project-hunter/packages/indicators/tests/unit/test_vector.py:214).
- **Fronteiras numéricas:** `_decimal` aceita float via `str` e não rejeita explicitamente `NaN`/infinito. Os tipos locais de book/trade são dataclasses sem validação própria. Eu acrescentaria testes de rejeição desses valores e de timestamps ingênuos nos insumos. [hotstate.py:101](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:101), [context.py:83](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:83).

## O QUE EU FARIA DIFERENTE

Centralizaria a validação temporal e a qualidade do checkpoint, para todas as calculadoras consumirem a mesma decisão. O engine já centraliza seu avanço; falta preservar o resultado dessa validação na proveniência. [engine.py:92](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:92).

## CONCORDO COM

Respostas diretas às oito perguntas:

1. **`tail_minutes`:** manter um número histórico completo como `degraded` é coerente **se ele significa “última janela observada”** e seu término permanece explícito. Não equivale à janela terminada no fechamento esperado por `as_of`; nesse contrato estrito, falta dado e deve ser indisponível. Atenção: com atraso de exatamente 60 segundos, a política atual ainda marca `ok`. [windows.py:95](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:95), [quality.py:113](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:113).

2. **Trades `(start, end]`:** concordo com as fronteiras e com zero sob cobertura comprovada. A prova de cobertura atual precisa do ajuste do must-fix 3. [windows.py:174](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:174).

3. **ATR:** gate de 16 barras, seed, suavização, duplicata, barra anterior e divisão pelo fechamento correspondente estão coerentes. O caminho por `bars_15m` busca somente buckets completos; **`advance`/`bootstrap` isoladamente não verificam `close_time` nem recebem `as_of`**, portanto essa garantia depende da entrada. [atr.py:178](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:178), [atr.py:215](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:215), [atr.py:237](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:237), [atr.py:242](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:242), [windows.py:124](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:124).

4. **ATR atrasado:** aceito mantê-lo degradado como última leitura conhecida, com timestamp próprio e qualidade herdada pelas dependentes. Não aceito o caminho que o publica `ok` após falha de agregação — must-fix 2.

5. **`inputs`:** a lacuna concreta é o checkpoint nas quatro features de tendência. Para preço, volume, book, trades e derivativos, não encontrei outra dependência numérica faltante nas definições revisadas. [price.py:56](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:56), [volume.py:57](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:57), [micro.py:182](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:182), [deriv.py:97](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:97).

6. **Hash sem `description`:** aceito. Prosa não precisa invalidar identidade numérica; alteração de fórmula continua exigindo nova versão. O hash inclui chave, versão, categoria, entradas e parâmetros. [definitions.py:73](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/definitions.py:73).

7. **Look-ahead:** ainda não cobre o suficiente. O helper usa sempre `EMPTY_STATE`, portanto não exercita checkpoint futuro. Com apenas 400 minutos, a invariância dos extremos de 24 h também não exercita um valor disponível. Acrescentaria esses casos, parcial sem timestamp e gap com checkpoint aquecido. [test_no_lookahead.py:31](C:/dev/project-hunter/packages/indicators/tests/unit/test_no_lookahead.py:31), [test_no_lookahead.py:58](C:/dev/project-hunter/packages/indicators/tests/unit/test_no_lookahead.py:58), [price.py:119](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:119).

8. **Decimal/UTC/dado fabricado:** os problemas concretos são a soma sob contexto ambiente e o zero por cobertura presumida. `as_of` passa por `ensure_utc`; o loader também aplica essa função aos timestamps que decodifica. A aceitação de float na fronteira merece endurecimento, conforme nice-to-have. [context.py:182](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:182), [hotstate.py:110](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:110).

## OBSIDIAN

- **Features (Feature Engine)** — registrar validade temporal do checkpoint, dependências stateful e semântica das janelas atrasadas.
- **Market Collector** — documentar que presença de trades antigos não comprova cobertura contínua da coleta.
- **Revisões Astra — T2.2** — registrar os cinco achados e os cenários de regressão; nenhuma página foi alterada nesta revisão.