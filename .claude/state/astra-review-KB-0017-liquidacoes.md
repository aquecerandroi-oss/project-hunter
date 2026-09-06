**RESUMO**

**Sua conclusão sobre a amostragem incompleta está correta, mas “a maior” precisa virar “a mais recente” nos dois streams. A H-KB0017, como escrita, não identifica quanto foi perdido.** Há também uma descoberta relevante: o projeto já possui coleta de `forceOrder`, embora o detector permaneça desarmado.

**1. O contrato da Binance**

A documentação oficial consultada diz que tanto `<symbol>@forceOrder` quanto `!forceOrder@arr` publicam **a última ordem de liquidação por símbolo dentro de 1000 ms**; sem liquidação no intervalo, não publicam evento. O limite do agregado é **por símbolo**, não uma ordem para o mercado inteiro. [Binance — Liquidation Order Streams e All Market Liquidation Order Streams](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market#liquidation-order-streams).

A consequência precisa ser formulada com cuidado:

- Múltiplas ordens na mesma janela implicam omissão.
- Maior concentração temporal favorece omissões.
- **A fração do notional omitido não necessariamente cresce de forma monotônica com a intensidade.** Ela também depende dos tamanhos e da ordem de chegada.

Exemplo hipotético: numa janela, duas ordens de 99 e 1 deixam observar apenas 1%; noutra, dez ordens pequenas seguidas de uma enorme podem deixar observar quase tudo. O contrato não fornece uma curva de subestimação por intensidade.

**2. O detector**

**Sim, está desarmado.** A declaração associa `LIQUIDATION_CLUSTER` a `liquidation_pressure_1h` e ao motivo `feature_not_implemented` em [detectors.py:185](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:185). A construção aplica `enabled=False` em [detectors.py:237](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:237).

Há uma distinção de contrato: na avaliação, o motivo externo é `detector_disabled`; `feature_not_implemented` vai como detalhe em [evaluation.py:154](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/evaluation.py:154). O `MarketContext` não contém uma entrada de liquidações em [context.py:188](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:188).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes nem consultei o banco; esta foi uma revisão estática e documental. Não afirmo cobertura operacional da coleta.

A busca no código retornou:

```text
135: detector = detector_for(AnomalyType.LIQUIDATION_CLUSTER)
136: assert detector.enabled is False
137: assert detector.disabled_reason == "feature_not_implemented"
```

Fonte: [test_anomaly_detectors.py:134](C:/dev/project-hunter/packages/indicators/tests/unit/test_anomaly_detectors.py:134). Teste existente, apenas inspecionado.

**MUST-FIX**

**1. Substituir a promessa de medir a perda: ela não é identificável com esses dados.**

O item 2 da [KB-0017:79](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0017-liquidacoes-o-fluxo-forcado-que-nao-observamos.md:79) confunde volume agressor excedente com liquidações ausentes.

Mesmo no cenário favorável em que todas as execuções relevantes estejam incluídas no volume agressor:

```text
A = L + U
A − S = (L − S) + U
```

`A` é volume agressor observado; `L`, liquidações executadas; `U`, demais execuções agressoras; `S`, liquidações executadas observadas no snapshot. O residual mistura **liquidações omitidas e fluxo voluntário**. Subtrair uma baseline continua deixando a variação desconhecida de `U`.

**Cenário de falha, hipotético:** mesmos `A=100` e `S=10` comportam tanto `L=10, U=90` — nenhuma perda — quanto `L=90, U=10` — perda de 80. Mesmas velas e snapshots, perdas radicalmente diferentes. Não identificam nem a ordem de grandeza.

**2. Corrigir “maior” e retirar a garantia irrestrita de limite inferior.**

A regra incorreta aparece na [KB-0017:24](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0017-liquidacoes-o-fluxo-forcado-que-nao-observamos.md:24) e na proveniência proposta na linha 77.

Além disso, o parser atual usa `q × p` em [streams.py:293](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:293). A Binance distingue quantidade original (`q`), quantidade executada acumulada (`z`), preço da ordem (`p`) e preço médio (`ap`). [Binance — campos do snapshot](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market#all-market-liquidation-order-streams).

**Cenário de falha:** ordem original de 10 unidades a 100, executada parcialmente em 1 unidade a 100. O parser produz notional 1000; a execução foi 100. Logo, **a soma atual não é necessariamente um limite inferior do executado**.

Para essa interpretação, seria necessário preservar a semântica das execuções, controlar duplicações/atualizações acumuladas e alinhar o período. Não basta trocar o rótulo.

**3. Corrigir a premissa de coleta futura.**

“Se alguém um dia coletar” na [KB-0017:63](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0017-liquidacoes-o-fluxo-forcado-que-nao-observamos.md:63) está desatualizado em relação ao código:

- `LIQUIDATIONS` integra os canais do worker em [ingest.py:62](C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:62), usados na assinatura em [streaming.py:45](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:45).
- O adapter mapeia esse canal para `forceOrder` em [streams.py:57](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:57).
- A persistência grava quantidade, preço, notional e `source="ws"` em [persist_rows.py:217](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:217).

**Cenário de falha:** planejar um coletor duplicado e deixar sem auditoria a série já produzida pelo caminho existente. O próximo trabalho deveria começar pela semântica e cobertura desse caminho; sua operação efetiva ainda precisa ser medida.

**4. Retirar o critério “subestimação explode ⇒ série inútil”.**

Esse salto está na [KB-0017:91](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0017-liquidacoes-o-fluxo-forcado-que-nao-observamos.md:91).

**Cenário de falha:** uma série inadequada para estimar volume total pode conservar informação sobre presença e persistência de atividade forçada. Descartá-la pela perda de volume eliminaria uma possível variável útil. Inversamente, subestimação estável não demonstra utilidade.

**NICE-TO-HAVE**

Eu cortaria ou restringiria estas afirmações:

- **“Principal razão”** para agressor não significar informado: a nota não mede a importância relativa de liquidações frente a outras motivações.
- **“Deixaram de empurrar dados em tempo real”**: descrever diretamente o contrato atual; a transição histórica requer referência datada.
- **“Custos deixam de valer” e “entrada mais irrealista”**: reformular como hipóteses de fragilidade sob estresse, ainda não medidas.
- **“A literatura autoriza… nada preditivo por evento”**: restringir a “este preprint não valida um alarme por evento”. Um resultado negativo limitado não prova impossibilidade geral.
- **“Variância do fluxo taker”**: especificar que o estudo trabalha com resíduos do log da razão taker buy/sell, não diretamente com volume bruto. [Preprint, dados e métodos](https://arxiv.org/html/2607.27070v1#S2).

**O QUE EU FARIA DIFERENTE**

**3. Mediria observabilidade e utilidade incremental, sem chamar nenhuma delas de perda do snapshot:**

| Medida | Interpretação defensável |
|---|---|
| Tempo conectado e assinado, atrasos, reconexões e descartes locais | Qualidade do coletor |
| Fração de intervalos com snapshots e persistência das sequências | Atividade observada; não contagem total de liquidações |
| Quantidades executadas observadas, por lado, após corrigir a semântica | Intensidade da amostra recebida |
| Associação com retornos, volatilidade, spread e profundidade | Contexto de estresse; não identificação causal |
| Ganho em janela futura sobre uma baseline de preço/volume | Utilidade incremental para um objetivo previamente definido |

Uma conexão saudável não demonstra ausência de perdas na origem. Silêncio durante desconexão deve permanecer desconhecido.

Para medir **a fração realmente perdida**, precisaria de uma referência independente, comprovadamente completa, do mesmo mercado e período. Outro distribuidor do mesmo `forceOrder` não resolve. Sem essa referência, simulações podem mostrar sensibilidade a hipóteses, mas não estimar empiricamente a perda real.

**CONCORDO COM**

Manter o detector desarmado; declarar a amostragem; não apresentar snapshots como total do mercado; separar pesquisa de ativação. Também concordo com a leitura limitada do preprint: o resultado populacional não valida um alarme individual. [Preprint, §4.6](https://arxiv.org/html/2607.27070v1#S4.SS6).

**OBSIDIAN**

- **Liquidações: o fluxo forçado que não observamos** — corrigir seleção, coleta existente e semântica; substituir a mensuração não identificável.
- **Exchange Adapters / Market Collector** — registrar a distinção entre notional original da ordem e executado, além da cobertura operacional pendente.
- **Anomalies** — esclarecer `disabled_reason` versus motivo retornado pela avaliação.
- **Strategy Backlog** — reformular H-KB0017 como auditoria de observabilidade e estudo de utilidade incremental.
- **Open Bugs** — registrar `q × p` interpretado como executado, com o cenário de execução parcial.