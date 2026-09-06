## RESUMO

**Concordo com a direção, mas ajustaria retomada, transição bootstrap→vivo e recuperação de lacunas antes de implementar.** Avaliei como `quant-engineer`, em modo OPINIÃO.

| Decisão | Minha recomendação |
|---|---|
| **1. Custo** | Replay cooperativo é aceitável como solução provisória; 50% não preserva a capacidade de um loop já saturado. |
| **2. Retomada** | Postgres como verdade, mas **não** `max(window_end)` por mercado. |
| **3. Cortes** | Fronteira do minuto correta; equivalência exige mesmas candles **e estado ATR compatível**. |
| **4. Backfill** | Continuar com dados válidos, sem esperar; falta garantir quem atende o pedido e quando ocorre a recomputação. |
| **5. Derivativos** | Carregar OI e manter settlement separado. Roster por mercado precisa de rearme e motivos de indisponibilidade operacional. |

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei testes ou benchmarks nesta revisão somente de leitura. Os tempos abaixo são projeções sobre os **50 ms/corte informados**, não medições desta rodada.

## MUST-FIX

**1. Retomada: transação atômica não significa população completa.**

O coletor produz revisões somente para buckets não vazios; uma revisão existente também pode estar abaixo do gate. Fontes: [collect.py:158](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/collect.py:158), [revision.py:179](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/revision.py:179).

**Cenário:** existem apenas duas horas de candles. O bootstrap grava algumas revisões com `window_end` recente. O backfill chega, mas o próximo processo encontra esse máximo e pula o mercado por 24 horas, deixando os outros buckets ausentes. Outro cenário: revisões da versão anterior fazem pular features da versão nova.

Escolheria **(a), corrigida**: reconciliar por `(mercado, feature, versão, algoritmo, sampling, hora UTC)`, verificando janela e cobertura. Mercado parcialmente processado continua pendente. Não usaria apenas o gate mínimo como prova de completude: 120/420 observações podem ser utilizáveis e ainda ter recuperação pendente.

Redis pode guardar tentativa, cursor e backoff; sua perda deve provocar reconciliação, não autorizar um “concluído”. A idade de 24 horas seria uma política de atualização, não prova de progresso.

**2. Refresh horário pode apagar operacionalmente o benefício do bootstrap.**

`revisions_for` publica revisões `LIVE`; a seleção escolhe primeiro o maior `available_at`, sem preferência por maturidade. Fontes: [baselines.py:324](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baselines.py:324), [sql.py:88](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/sql.py:88).

**Cenário:** bootstrap utilizável com 420 observações; na primeira hora viva entram 60 observações de um dia. Essa revisão mais recente passa a ser selecionada e falha no gate. O detector perde a baseline apesar do bootstrap bem-sucedido.

Antes de ligar o runner, definiria a transição. Minha preferência é formar a janela com observações históricas reproduzíveis e snapshots vivos, **uma observação por minuto, precedência explícita para o snapshot vivo**. Medianas/MADs prontas não podem ser combinadas para reconstruir a população.

Como solução provisória mais simples, o worker pode adiar a publicação da substituição imatura quando houver bootstrap utilizável, expondo esse atraso. Isso precisa ser uma política explícita; não basta recarregar o cache.

**3. O pedido de backfill ainda não tem atendimento demonstrado.**

Encontrei o produtor, mas nenhum consumidor do stream na busca em `services/**`; o conjunto de tarefas do market-worker agenda recovery, sem consumidor de backfill. O recovery encontra lacunas pelas próprias janelas de detecção. Fontes: [backfill.py:89](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/backfill.py:89), [main.py:85](C:/dev/project-hunter/services/market-worker/hunter_market_worker/main.py:85), [recovery.py:237](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:237).

**Cenário:** faltam candles históricas anteriores à janela ordinária de detecção. O scanner publica, ninguém transforma o pedido em trabalho, e todas as próximas passadas continuam incompletas.

Cabe à T2.5b publicar e reconciliar a chegada efetiva dos dados. **Atender o stream é dependência fora de `services/scanner-worker/**`**, a registrar como bloqueio da recuperação completa.

**4. Cinco minutos não é um limiar suficiente para lacunas históricas.**

Uma única candle ausente quebra janelas contíguas; `relative_volume_1h` requer 1.440 minutos. Fontes: [windows.py:90](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:90), [volume.py:69](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:69).

**Cenário:** falta um minuto no meio do dia anterior. A feature perde até aproximadamente um dia de observações, mas a regra “≥5 minutos” nunca pede reparo.

Detectaria todas as lacunas históricas, incluindo série vazia e cauda ausente, separando atraso recente de coleta. Há também um erro de fronteira a resolver: `BackfillRequester` documenta intervalo inclusivo, mas rejeita duração `<5 min`; cinco candles ausentes, de 10:00 a 10:04, têm diferença de quatro minutos e são recusadas. Fonte: [backfill.py:72](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/backfill.py:72).

Continuaria o bootstrap aproveitando observações aceitas, porém com **retentativa explícita após reparo**. Refresh de snapshots não recalcula automaticamente os minutos históricos.

**5. Corte equivalente não prova ATR equivalente nem igualdade dos dados recebidos.**

O replay começa com `EMPTY_STATE`; o vivo usa o checkpoint do mercado. Wilder preserva a origem da recursão. Fontes: [bootstrap.py:127](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/bootstrap.py:127), [scanner.py:150](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:150), [atr.py:171](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:171).

**Cenário:** replay começa oito dias atrás, mas o scanner vivo inicializou seu ATR hoje sobre o buffer recente. Mesmo com as mesmas candles finais atuais, origens diferentes podem produzir valores diferentes, especialmente após choques.

Exigiria teste de continuidade e uma origem/checkpoint compatível para afirmar equivalência exata. Não sobrescreveria o checkpoint vivo com o resultado de um replay antigo.

Há outra assimetria concreta: a qualidade permite uma candle de atraso de até 60 segundos. Assim, uma observação viva pode ser aceita antes de chegar a candle M−1, enquanto o replay posteriormente a inclui. Fonte: [quality.py:152](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/quality.py:152). Portanto, “mesma população” é condicional à presença das mesmas candles; timestamp truncado sozinho não garante isso.

**6. Histórico não vazio não significa detector operacional.**

`OPEN_INTEREST_SPIKE` usa `open_interest_change_1h`, que exige OI atual e referência próxima de uma hora atrás. Fontes: [detectors.py:169](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:169), [deriv.py:105](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:105).

**Cenário:** o histórico contém apenas uma amostra recente. Seu teste de presença arma o detector, mas a feature continua `warmup`. Inversamente, um roster criado uma vez na partida pode continuar desarmado depois da chegada dos dados.

Reconciliaria o roster por mercado e distinguiria **desarmado por capacidade ausente**, **warmup**, **fonte stale** e **baseline indisponível**. O avaliador já retorna motivos de indisponibilidade; aproveitaria isso para heartbeat, sem reduzir tudo a `enabled`. Fonte: [evaluation.py:145](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/evaluation.py:145).

## NICE-TO-HAVE

- Métricas separadas: cortes processados, mercados tentados/concluídos, buckets utilizáveis/esperados, rejeições e idade das revisões. ETA baseada na taxa efetivamente observada.
- Janela fixa **por trabalho de mercado**, evitando perseguir continuamente um `window_end` móvel durante as dezenas de horas de execução.
- Releitura periódica com sobreposição no histórico de OI: um cursor por maior timestamp pode perder inserções tardias anteriores ao cursor. A consulta atual filtra pelo timestamp da observação. Fonte: [repo.py:78](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/repo.py:78).
- Ajustar explicitamente a convenção de `load_candles`: hoje `until` é inclusivo sobre `open_time`, diferente do intervalo semiaberto proposto. Fonte: [repo.py:124](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/repo.py:124).

## O QUE EU FARIA DIFERENTE

**Custo:** 10.080 × 50 ms = **8,4 minutos de CPU por mercado**, ou **28 horas de CPU para 200**. Com 50% efetivos de execução, são aproximadamente **56 horas de parede**, antes de IO e demais custos. Num loop já saturado, reservar metade para bootstrap necessariamente prejudica o vivo.

Usaria orçamento por tempo verificado **a cada vetor**, fatias curtas e redução/pausa conforme atraso do loop e backlog. Um único gerador e um único coletor por mercado permanecem vivos entre fatias; recriar o gerador reiniciaria o ATR. Fonte: [bootstrap.py:127](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/bootstrap.py:127).

Testaria `asyncio.to_thread` como alternativa, sem prometer ganho pelo NumPy: há construção de listas Python no trecho apontado. Fonte: [windows.py:38](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:38). Para isolamento mais forte, consideraria um processo filho único, com entradas imutáveis e publicação pelo processo principal, caso exista CPU disponível. Nenhuma dessas opções substitui medir latência sob carga.

**Derivativos:** manteria settlement fora. Nove horas cobrem os horizontes propostos; as tolerâncias atuais são 6 minutos para OI 1h, 24 para OI 4h e 48 para funding 8h. Fonte: [deriv.py:179](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/deriv.py:179).

`funding_change_8h` pode continuar indisponível nesta entrega, com motivo operacional “histórico amostrado ausente”. Para recuperá-la futuramente, investigaria as observações de `funding_rate` nos snapshots duráveis, preservando timestamp e qualidade, sem preencher minutos ausentes nem transformar settlement em amostra.

## CONCORDO COM

- Não subamostrar; manter um coletor alimentado por todas as features.
- Postgres como verdade durável e transação curta por mercado, após o cálculo.
- Corte `M:00:00` e bucket `M.hour`: com as mesmas candles, volume relativo não depende dos segundos intraminuto; ATR depende das barras completas e do checkpoint. Fontes: [bootstrap.py:130](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/bootstrap.py:130), [windows.py:124](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:124).
- Prosseguir com dados válidos enquanto o reparo está pendente.
- `FUNDING_ANOMALY` depender de `funding_rate`, independentemente de `funding_change_8h`. Fonte: [detectors.py:176](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:176).

## OBSIDIAN

- **Features** — registrar condições de equivalência bootstrap/vivo, origem ATR e lacuna do histórico amostrado de funding.
- **Anomalies** — documentar retomada por bucket, transição bootstrap→live e estados operacionais dos detectores.
- **Workers** — registrar orçamento do replay e dependência do consumidor de backfill.
- **Revisões da Astra / T2.5b — desenho dos runners** — acrescentar esta revisão e os cenários exigidos para validação.