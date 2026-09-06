**RESUMO**

**Eu não reportaria DONE ainda.** Confirmei cinco problemas, apesar dos **180 testes da revisão passarem**.

**Sobre v3: retiro a exigência neste caso.** Aceito ratificar v2 no lugar: essa possibilidade está explicitamente prevista em [DATABASE.md:1373](/C:/dev/project-hunter/docs/DATABASE.md:1373) e [DATABASE.md:1400](/C:/dev/project-hunter/docs/DATABASE.md:1400). O comentário do seed confirma a intenção, mas não automatiza a atualização: a comparação continua recusando o JSON anterior. [seed_weights.py:53](/C:/dev/project-hunter/infra/scripts/seed_weights.py:53).

A nota com `UPDATE` resolve a alternativa destrutiva que motivou minha objeção anterior. Ainda precisa entrar no procedimento de deploy e ser verificada num banco com v2/false. Não consultei bancos para confirmar a ausência de scores anteriores. Os testes fora do escopo explicam sua escolha operacional; sozinhos, não justificariam alterar uma versão.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão como `quant-engineer`, em modo OPINIÃO, dos arquivos indicados e seus contratos.

**TESTES**

Executei `uv run pytest` nos nove arquivos de testes indicados — incluindo `test_weights_contract.py` — com `-q -p no:cacheprovider`, sem bytecode, cache ou sincronização do ambiente:

```text
180 passed in 5.56s
```

Também executei sondagens Python em memória, usando seus fixtures e funções reais. Resultados relevantes:

```text
precision4 score: 47.93 47.93 momentum: 11.9340 11.9300
saturated explanation precision6: InvalidOperation
permutation: 53.00 53.00 decomposition_equal= False explanation_equal= False
future anomaly score: 48.00 52.00
future stage score: 58.00
anomaly healthy/unknown confidence: 0.9603 0.9603 component= 1.0000 1.0000
partial quality loss: 46.00 46.00 0.9603 0.8545 HistoryVerdict(record=False, reasons=(), policy_version='history_v1')
```

Não reexecutei os 637 testes nem os gates de lint/typecheck/tamanho; esses resultados continuam sendo os que você reportou.

**MUST-FIX**

1. **O scorer aceita evidência futura.**

   Fixei o vetor no instante original e forneci uma anomalia com `detected_at` e `observation_ts` um dia adiante: score **48 → 52**. Um estágio EARLY publicado um dia adiante levou **48 → 58**.

   A elegibilidade da anomalia verifica status/evaluation_state; o fator de estágio lê o estado publicado sem confrontar seus timestamps com o corte. [overlays.py:86](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/overlays.py:86), [scorer.py:119](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/scorer.py:119).

   **Cenário operacional:** replay ou consumo de evento atrasado combinado com o estado mais recente do cache. Validaria a coerência temporal de vetor, estágio, regime e anomalias na entrada de `ScoreContext`, recusando evidência posterior ao corte. Os testes atuais de look-ahead mutam a vela não final; não exercitam essa combinação. [test_no_lookahead_t24.py:148](/C:/dev/project-hunter/packages/indicators/tests/unit/test_no_lookahead_t24.py:148).

2. **Há operações Decimal fora de `CONTEXT`, com efeito reproduzido.**

   `quantize(weight * normalized, ...)` calcula a multiplicação **antes** de entrar no helper protegido. Com `momentum_15m=1.98765`, mudar a precisão ambiente para 4 alterou a contribuição de **11.9340 para 11.9300**. O score final coincidiu nesse exemplo; os bytes da decomposição não. [components.py:156](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/components.py:156).

   Mais grave: explicar momentum saturado, normalizado em `100.0000`, sob precisão 6 produziu **`InvalidOperation`**, porque `_num` quantiza no contexto ambiente. [explanation.py:59](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/explanation.py:59).

   Proteja a operação inteira, incluindo formatação. Revise também as quantizações da confidence do regime e a subtração do histórico. [classifier.py:124](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/classifier.py:124), [history.py:152](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/history.py:152).

3. **A ordenação das anomalias não chega à representação persistida.**

   Inverter `[VOLUME_SPIKE/80, MOMENTUM_SHIFT/60]` manteve score **53**, mas mudou os bytes da decomposição e da explicação.

   Você ordena `usable` para somar, porém entrega `inputs=scores` na ordem recebida. A explicação também mantém essa ordem em `valores.tipos`. [overlays.py:103](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/overlays.py:103), [overlays.py:116](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/overlays.py:116), [explanation.py:137](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/explanation.py:137).

   **Cenário:** o banco devolve o mesmo conjunto em outra ordem. Canonicalize também os inputs persistidos e as listas auxiliares.

4. **Anomalia desconhecida recebe confidence de componente igual a 1.**

   Trocar a única anomalia de `ACTIVE/OK` para `ACTIVE/UNKNOWN` manteve a confidence global em **0.9603** e a do componente em **1.0000**. O componente continua disponível mesmo quando nenhuma anomalia ativa pôde ser avaliada. [overlays.py:119](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/overlays.py:119).

   **Falha:** ausência de avaliação vira a mesma certeza atribuída a um conjunto comprovadamente vazio. Preserve a distinção entre “não há anomalias” e “há anomalias cujo estado atual desconhecemos”; reduza a cobertura/confidence neste segundo caso.

5. **O histórico não registra perda parcial de qualidade.**

   Com spread na mediana, degradar somente essa entrada manteve score **46**, direção, status e elegibilidade; a confidence caiu de **0.9603 para 0.8545**, mas `should_record_history` retornou `record=False`.

   `HistoryMark` só representa elegibilidade global, e o gatilho compara esse booleano. Não consegue representar mudança de qualidade por componente. [history.py:91](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/history.py:91), [history.py:167](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/history.py:167).

   **Falha:** uma indisponibilidade que começa e termina entre duas amostras periódicas desaparece do histórico. Acrescente uma assinatura determinística de qualidade/disponibilidade, conforme o gatilho exigido em [M2.md:58](/C:/dev/project-hunter/docs/plans/M2.md:58).

**NICE-TO-HAVE**

- **Status e banco:** partindo de estado válido, não encontrei transição que viole o CHECK. A expiração escreve `EXPIRED` e `expired_at` juntos; estado fechado permanece terminal. A unicidade entre chamadas concorrentes continua dependendo da persistência, pois duas chamadas independentes com `state=None` podem pedir OPEN. [status.py:120](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/status.py:120), [status.py:195](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/status.py:195), [analysis.py:191](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:191).

- **Dezesseis leituras não provam continuidade sozinhas.** Reproduzi expiração com uma leitura abaixo do piso, um buraco de 59 minutos e quinze leituras em sequência de segundos. Isso respeita a limitação documentada: o watchdog precisa informar a ausência. Portanto, exija esse teste na T2.5, incluindo restart; o contador isolado não oferece essa garantia. [status.py:24](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/status.py:24), [status.py:103](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/status.py:103).

- **UTC:** os timestamps principais são normalizados, mas a construção direta de `EpisodeState` não normaliza `below_floor_since`/`expired_at`; `RegimeState` também não valida seus timestamps. Um estado reidratado incorretamente pode provocar comparação entre datetime ingênuo e UTC. Padronizaria esses caminhos. [episode.py:124](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/episode.py:124), [decision.py:70](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/decision.py:70).

**O QUE EU FARIA DIFERENTE**

**Sobre a janela móvel:** não exigiria alinhar ambas apenas por serem móvel versus horária. Porém, existe uma diferença concreta além do alinhamento: os 59 retornos internos excluem sistematicamente o retorno entre horas na referência. [series.py:16](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/series.py:16), [series.py:90](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/series.py:90).

Com 60 closes em 100 seguidos de 60 em 101, obtive referência horária **zero**, enquanto a janela móvel terminando no minuto 90 retornou **0.0001694915**. Eu consideraria 60 retornos usando 61 closes, incluindo o fechamento predecessor, e testaria saltos na virada da hora antes de congelar o estimador.

**Sobre testes que afirmam mais do que provam:**

- O teste de contexto ambiente compara somente o score, usando valores que não expõem a falha da contribuição; precisa comparar decomposição e explicação com valores fracionários e saturados. [test_opportunity_scorer.py:233](/C:/dev/project-hunter/packages/indicators/tests/unit/test_opportunity_scorer.py:233).
- “Every number in a sentence” verifica o resumo e dois campos estruturados de momentum; não todos os números das frases. [test_opportunity_explanation.py:61](/C:/dev/project-hunter/packages/indicators/tests/unit/test_opportunity_explanation.py:61).
- Os testes de determinismo repetem entradas na mesma ordem; acrescente permutações das anomalias. [test_opportunity_scorer.py:228](/C:/dev/project-hunter/packages/indicators/tests/unit/test_opportunity_scorer.py:228).

**CONCORDO COM**

- **Voto `weight × severity / expected`:** não há multiplicação duplicada da cobertura nessa fórmula. Ela distribui o orçamento do componente entre suas entradas direcionais. Correlação entre features é outra questão, de calibração. [scorer.py:164](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/scorer.py:164).
- **Confidence quantizada dos componentes:** não vejo perda relevante para a decisão atual; o efeito esperado é da ordem da última casa de confidence. A cobertura interna não é multiplicada novamente: você pondera a confidence já calculada. Os problemas relevantes são os itens 2 e 4 acima. [scorer.py:193](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/scorer.py:193).
- **Confidence `None` durante divergência entre par publicado e leitura:** correto. Não atribuiria ao par antigo a confiança da leitura nova. O banco aceita nulo; o Radar pode explicar “transição em confirmação”. [classifier.py:159](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/classifier.py:159), [analysis.py:145](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:145).
- **Desconto geométrico:** com severidades não negativas, é monotônico não decrescente; o clip introduz saturação, não reversão. O desempate por tipo é adequado. Contudo, a afirmação de que três moderadas não superam uma extrema é falsa: `60 + 30 + 15 = 105`, acima de uma única 90. Ajustaria essa justificativa. [overlays.py:9](/C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/overlays.py:9).
- Não encontrei leitura de relógio nem dados de mercado/PnL fabricados nos módulos novos. As constantes de regime estão declaradas como política não calibrada. [regime/model.py:119](/C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/model.py:119).

**OBSIDIAN**

- **Revisões-Astra / T2.4 — regime e opportunity:** registrar os cinco achados, as reproduções e o aceite condicionado da ratificação v2.
- **Features:** registrar os limites da prova anti-look-ahead e o contrato temporal entre vetor e demais evidências.
- **Anomalies:** distinguir conjunto vazio de anomalias ativas com avaliação desconhecida.
- **Data Flow:** registrar watchdog/continuidade e persistência concorrente como critérios de integração da T2.5.
- **Architecture Decisions:** documentar a ratificação excepcional da v2 e a decisão sobre retornos nas fronteiras horárias.