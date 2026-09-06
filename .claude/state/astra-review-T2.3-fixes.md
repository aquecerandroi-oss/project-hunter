**RESUMO**

**DONE_WITH_CONCERNS: encontrei um must-fix na histerese.** O par `(estágio, direção)` protege a inversão de lado, mas pode impedir indefinidamente a retirada de um estágio que perdeu sustentação. Reproduzi esse caso. Os cinco arquivos de testes passaram: **117 passed in 19.09s**.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisão como `quant-engineer`, em modo OPINIÃO.

**TESTES**

Executei, com bytecode, cache do pytest e sincronização do uv desativados:

```text
uv run pytest packages/indicators/tests/unit/test_baselines_collect.py packages/indicators/tests/unit/test_baselines_compute.py packages/indicators/tests/unit/test_stage.py packages/indicators/tests/unit/test_anomaly_lifecycle.py packages/indicators/tests/unit/test_baselines_sql.py -q

117 passed in 19.09s
```

Também executei reproduções em memória via `uv run python -`, usando os helpers dos testes. Não executei integração com Postgres.

**MUST-FIX**

**1. (c) Alternância de direção pode prender um estágio superior já injustificado.**

Cenário reproduzido:

- Publicar `DEVELOPING LONG` com duas observações de `r = 2`.
- Depois, fornecer somente `r = 0,005`, com todas as confirmações de EARLY válidas, alternando retorno positivo/negativo e fluxo alinhado.
- Todo candidato passa a ser EARLY, mas cada mudança de lado reinicia a contagem em 1. O publicado permanece `DEVELOPING LONG`.

Saída real, início da sequência:

```text
initial: DEVELOPING long
2 r= 0.005 candidate= EARLY long published= DEVELOPING long count= 1
3 r= 0.005 candidate= EARLY short published= DEVELOPING long count= 1
4 r= 0.005 candidate= EARLY long published= DEVELOPING long count= 1
```

A mesma saída persistiu até a sexta observação subsequente. A causa é a igualdade do **par inteiro** para incrementar a contagem, preservando o publicado quando ela não chega a 2: [classifier.py:186](C:/dev/project-hunter/packages/indicators/hunter_indicators/stage/classifier.py:186). Repetir a alternância mantém essa condição indefinidamente.

**Correção recomendada:** separar a retirada de uma afirmação sem sustentação da confirmação de sua substituta. Após duas observações que não sustentam o estágio publicado, permitir sua retirada para `NONE`; publicar o novo par somente quando confirmado. Isso preserva a proteção de direção sem perpetuar DEVELOPING/EXTENDED antigos. A política precisa ser explicitada e coberta por regressão antes de integrar.

**NICE-TO-HAVE**

**(a) A proteção cobre os produtores atuais de cálculo, mas não toda a porta de escrita.**

`compute_revision` valida antes de calcular cobertura; o coletor e o bootstrap passam por ele. Portanto, com `expected_size > 0`, esses caminhos não devolvem revisão com tamanho excedente ou cobertura acima de 1. A semiabertura **rejeita**, não filtra, observações fora da janela: [compute.py:128](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/compute.py:128), [collect.py:159](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/collect.py:159), [bootstrap.py:220](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/bootstrap.py:220).

Entretanto, `BaselineRevision` aceita construção direta sem validar contagens, e `insert_revisions` serializa esse objeto diretamente. Reproduzi:

```text
direct revision accepted: 421 420 1.002381 insert compiled= True
```

Referências: [revision.py:130](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/revision.py:130), [sql.py:110](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/sql.py:110). O banco continua protegido pelos CHECKs, mas rejeitaria a escrita: [analysis_baselines.py:96](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis_baselines.py:96).

Não encontrei produtor operacional atual explorando esse desvio; por isso, classifico como endurecimento da interface, não segundo bloqueio. Validaria também `expected_size > 0` explicitamente antes da divisão.

**(b) PRIMEIRA significa primeira leitura válida recebida, não necessariamente a cronologicamente mais antiga.**

O slot só é ocupado por uma leitura aceita; rejeições anteriores não o ocupam: [collect.py:113](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/collect.py:113).

Nenhuma das políticas é automaticamente imparcial:

- **Primeira:** depende da ordem de chegada e do instante em que a qualidade se torna válida.
- **Última:** representa outro ponto do minuto e exige esperar seu encerramento para saber qual foi a última.

Usar a última de 14:03:59 numa decisão de 14:03:10 seria look-ahead. Usá-la numa baseline publicada posteriormente, respeitando os cortes causais, não seria. Da mesma forma, truncar uma primeira leitura de 14:03:40 para 14:03:00 não prova que ela estava disponível às 14:03:10: [collect.py:66](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/collect.py:66).

Manteria a primeira válida, mas corrigiria a justificativa: **replay equivalente exige preservar a seleção/ordem original**. Escolher a última numa nova revisão também não reescreve uma baseline imutável já referenciada.

**(d) Cinco leituras mais cinco minutos não comprovam continuidade.**

Reproduzi leituras baixas nos minutos `0, 1, 2, 3, 60`: a quinta resolveu a anomalia, apesar do intervalo de 57 minutos. O código conta leituras e tempo total, sem limitar o intervalo entre elas: [lifecycle.py:274](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:274).

Isso satisfaz a política literal proposta, mas exige documentar sua limitação. A continuidade depende de o watchdog entregar `no_data` nos intervalos ausentes, zerando a sequência: [lifecycle.py:253](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:253).

Baixa cadência pode impedir resolução antes da expiração. Considero aceitável terminar como **expired**, desde que o watchdog funcione: a expiração tem precedência, mas só acontece quando `advance` é chamado. Sem chamadas, quatro horas não constituem um timer autônomo: [lifecycle.py:241](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:241).

**O QUE EU FARIA DIFERENTE**

Corrigiria primeiro a retenção patológica do estágio. Depois, acrescentaria testes de integração do SQL e testes de chegada fora de ordem no coletor e de lacunas no lifecycle. Evitaria apresentar “primeira leitura” como garantia suficiente de causalidade ou “cinco leituras” como prova de cinco minutos contínuos.

**CONCORDO COM**

- **(e)** `feature_version` precisa distinguir as populações solicitadas. `algo_version` é redundante sob o `WHERE` atual, mas não causa erro; o prefixo do `ORDER BY` acompanha o `DISTINCT ON`: [sql.py:75](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/sql.py:75).
- Separar direção observada de direção publicada e persistir ambas resolve a ambiguidade do estado: [model.py:142](C:/dev/project-hunter/packages/indicators/hunter_indicators/stage/model.py:142).
- `_atr_reason` distingue warm-up de degradação conforme a política declarada: [classifier.py:59](C:/dev/project-hunter/packages/indicators/hunter_indicators/stage/classifier.py:59).

**OBSIDIAN**

- **Features (Feature Engine)** — registrar janela semiaberta, primeira leitura válida recebida e limites da garantia de replay.
- **Anomalies (Anomaly Engine)** — registrar dependência do watchdog, resolução por contagem e risco de estágio preso por alternância de direção.
- **Revisoes-Astra/Index** — vincular esta revisão da T2.3, com o cenário reproduzido e os 117 testes aprovados.