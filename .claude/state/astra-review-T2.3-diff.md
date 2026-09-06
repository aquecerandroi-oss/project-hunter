**RESUMO**

**Não aprovaria a T2.3 ainda.** Concordo com o desenho e com várias correções, mas encontrei sete problemas concretos na implementação. Confirmei os principais com probes em memória, sem modificar arquivos.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit. Revisão no papel de `quant-engineer`.

**TESTES**

Não reexecutei a suíte nem os gates; os **403 passed** são o resultado informado por você.

Executei três probes via `.venv/Scripts/python.exe -B -`, alimentados por stdin, usando funções reais e fixtures existentes. Todos terminaram com código 0. Trechos reais:

```text
terminal + old event: open 2026-09-08 10:00:00+00:00
append retry availability: stored= 2026-09-08 09:01:00+00:00 returned= 2026-09-08 10:01:00+00:00 equal= False
missing baseline after EARLY: EARLY NONE False
1500 ring vector equality: False
same final candles two computations: NONE DEVELOPING -> DEVELOPING DEVELOPING
version mismatch accepted: True detector_feature_version= 1 baseline_feature_version= 2
same minute 60 distinct seconds sample_size: 60
```

O probe SQL usou o `FakeConnection` existente: comprova o comportamento do adaptador diante da resposta de conflito, não concorrência real no PostgreSQL.

**MUST-FIX**

1. **Evento antigo abre outro episódio depois de um estado terminal.**

   `advance()` transforma estado fechado em `open_state=None` e decide abrir **antes** da guarda temporal. Cenário: abre às 10h, expira às 14h e recebe novamente a avaliação das 10h; retorna `OPEN`, com `detected_at=10h`. Reproduzido.

   A guarda deve comparar com o último timestamp do estado recebido, inclusive `resolved/expired`, antes de decidir uma nova abertura. [lifecycle.py:198](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:198), [lifecycle.py:205](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:205).

2. **As transições misturam números atuais com proveniência antiga.**

   Nos ramos abaixo de hold e RESOLVE, mudam `severity`, `current_value` e `deviation`, mas permanecem `baseline`, `baseline_ids`, `confidence` e versões anteriores. `_updated()` troca a baseline, porém também deixa as versões anteriores.

   Cenário: muda o bucket horário ou a revisão selecionada; a nova avaliação fica abaixo do hold. O estado passa a guardar um desvio calculado contra B, acompanhado da baseline A. No probe, a avaliação tinha baseline `2`, mas o estado retornou baseline `1` junto do novo `current_value=2.5`. O replay dessa explicação fica inconsistente.

   Atualize o conjunto completo de evidências de toda avaliação válida, preservando separadamente os campos do episódio. [lifecycle.py:172](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:172), [lifecycle.py:238](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:238).

3. **`append()` recupera o ID persistido, mas devolve a revisão da tentativa.**

   A releitura encontra a linha completa, aproveita apenas seu ID e depois monta `StoredBaseline(..., revision=revision)` com o argumento recebido.

   Cenário: publicação original às 09:01; retry idêntico às 10:01. O fingerprint permanece igual, mas o retorno anuncia disponibilidade às 10:01. Uma projeção histórica das 09:30 construída desse retorno rejeita uma baseline que realmente já existia. Também diverge do store em memória, que devolve o objeto existente.

   No conflito, devolva a revisão reconstruída da linha persistida. [sql.py:155](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/sql.py:155), [sql.py:173](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/sql.py:173), [store.py:131](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/store.py:131).

4. **A identidade temporal prometida ainda é horário de recomputação.**

   O estágio usa `vector.ts`, mas o engine preenche esse campo com `ctx.as_of`. Duas computações dos mesmos candles finais, separadas por um segundo, publicaram DEVELOPING no probe. Portanto, comparar timestamps crescentes não garante duas observações distintas. [stage.py:266](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:266), [features/engine.py:114](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:114).

   A mesma fragilidade chega à população: o collector usa `vector.ts`, e `_check_inputs` deduplica o timestamp exato, não o minuto. Aceitou 60 observações em 60 segundos do mesmo minuto. Repetindo isso em três dias, é possível ultrapassar o gate sem 120 minutos observados. [collect.py:68](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/collect.py:68), [compute.py:118](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/compute.py:118).

   Separe identidade da observação e instante de processamento. Para a população `PER_MINUTE`, valide explicitamente a unicidade por minuto.

5. **A invalidação de estágio não cobre os insumos externos de `StageInputs`.**

   `_required_keys()` examina somente features do vetor. Cenário reproduzido: EARLY publicado perde `trade_velocity_baseline`; o candidato vira NONE, mas continua publicando EARLY, com `invalidated=False`, esperando a histerese. Perder o histórico externo necessário ao EXTENDED por exhaustion sofre a mesma omissão. [stage.py:163](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:163), [stage.py:182](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:182), [stage.py:305](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:305).

   Além disso, o envelope não inclui a mediana externa nem os quatro volumes usados: registra as confirmações, mas não toda a evidência necessária para recalculá-las. Persista esses insumos e sua proveniência; inclua sua indisponibilidade na invalidação imediata. [stage.py:85](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:85), [stage.py:137](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:137).

6. **O bootstrap não reproduz o recorte do ring de 1.500 entradas.**

   `bisect_left(cut − 1500 min)` junto de `bisect_right(cut)` inclui **1.501 fechamentos** numa série contínua com timestamps exatos. Com gaps, selecionar por duração também difere de selecionar as últimas 1.500 entradas.

   No probe com 1.600 candles, o bootstrap começou em 01:39 e o ring em 01:40; `canonical_bytes()` divergiu. O checkpoint ATR coincidiu nesse cenário — não estou afirmando divergência numérica nele. [bootstrap.py:130](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/bootstrap.py:130).

   O loader marca truncamento pela quantidade de entradas retornadas; os testes de equivalência usam apenas 400 candles e não atravessam essa fronteira. Reproduza a seleção real do ring e teste rolagem, gaps e checkpoint. [features/hotstate.py:154](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:154), [test_baselines_bootstrap.py:79](/C:/dev/project-hunter/packages/indicators/tests/unit/test_baselines_bootstrap.py:79).

7. **A projeção valida causalidade, mas não compatibilidade de versões.**

   Sua construção aceita uma revisão com feature v2/algoritmo incompatível; `resolve()` verifica somente bucket e gate. O detector não rejeita essa incompatibilidade.

   Cenário: cache ou `load_ids()` fornece a revisão de outro perfil. No probe, um detector feature v1 produziu avaliação elegível contra baseline feature v2, continuando a declarar v1 no resultado. Esse é justamente o caminho alternativo ao SELECT que a validação da projeção deveria proteger. [projection.py:95](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/projection.py:95), [projection.py:152](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/projection.py:152), [evaluation.py:181](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/evaluation.py:181).

   Vincule a projeção a um perfil explícito de versões e valide as entradas contra ele.

**NICE-TO-HAVE**

- **`item.type == "Decimal"` funciona hoje, mas é frágil.** `Decimal | None` cairia em `int(...)`: pode levantar ou truncar um valor Decimal. Prefiro conversores explícitos, com rejeição de tipos não suportados, ou resolução das anotações com tratamento explícito de opcionais. Não é falha atual do perfil existente. [stage.py:75](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:75).

- **Severidade degradada no envelope é aceitável como diagnóstico**, desde que os consumidores respeitem `evaluation_state`. Acrescentaria `eligible` à serialização e um teste de contrato do scorer. Hoje a propriedade bloqueia a utilização, mas não aparece em `as_wire()`. [evaluation.py:72](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/evaluation.py:72), [evaluation.py:92](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/evaluation.py:92).

- **Falta testar candle final disponível somente depois do corte.** O teste atual cobre alteração de candle em formação; `build_context()` filtra finais pelo fechamento, sem considerar `event_ts`. Para replay de decisão histórica, prove disponibilidade até a decisão. Para bootstrap publicado hoje, usar backfill conhecido hoje é legítimo; isso não prova equivalência com o que o live sabia ontem. [test_no_lookahead_t23.py:100](/C:/dev/project-hunter/packages/indicators/tests/unit/test_no_lookahead_t23.py:100), [features/context.py:278](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:278).

- Testaria também silêncio entre duas leituras abaixo do hold: o teste atual resolve com leituras apenas nos minutos 1 e 6. A continuidade depende de o watchdog realmente inserir `no_data` durante a ausência. [test_anomaly_lifecycle.py:136](/C:/dev/project-hunter/packages/indicators/tests/unit/test_anomaly_lifecycle.py:136), [lifecycle.py:238](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:238).

**O QUE EU FARIA DIFERENTE**

Manteria a arquitetura e corrigiria as fronteiras: identidade temporal explícita; evidência atualizada como um conjunto; retorno SQL fiel à linha persistida; projeção vinculada a versões; insumos externos do estágio incluídos no envelope. Depois acrescentaria regressões dos cenários acima e uma prova de equivalência passando pelo loader real.

**CONCORDO COM**

- **Ponto 1:** sim, corte duplo e versões entram no `WHERE` antes da escolha por `DISTINCT ON`. O fingerprint inclui mercado, feature, hora, versões, sampling, source, janela e observações: não encontrei colisão lógica entre mercados/features produzidos por essa função. O problema concreto do retry é o item 3 acima. Manteria o `RuntimeError` quando não há linha: impede devolver identidade inexistente. [sql.py:58](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/sql.py:58), [compute.py:84](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/compute.py:84), [sql.py:168](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/sql.py:168).

- **Ponto 2:** timestamps diferentes não cabem na mesma projeção atual. Prefiro agrupar por corte e manter a guarda. Apenas aceitar timestamps diferentes em `resolve()` seria incorreto: a revisão já foi selecionada para outro corte. Suporte heterogêneo exigiria seleção causal por entrada. [projection.py:143](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/projection.py:143).

- **Ponto 3:** levantar por janela/hora errada é correto. **Gaps não provocam essas exceções**; reduzem população e cobertura. A correção necessária é distinguir minuto de timestamp exato. [compute.py:119](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/compute.py:119), [compute.py:160](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/compute.py:160).

- **Ponto 4:** para estado ativo e timestamp crescente, expiração precede inelegibilidade; `active+unknown` expira quando chamado, e severidade stale não substitui a válida. Concordo com guardar severidade corrente no RESOLVE; um pico teria de ser campo separado. O defeito está na proveniência incompleta, não nessa escolha. [lifecycle.py:210](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:210), [lifecycle.py:223](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:223).

- **Ponto 6:** concordo: guardar `candidate` com contagem zero faz a próxima confirmação começar em **1**. Sem ATR não existe candidato calculável; descartá-lo é coerente. A omissão está nos insumos externos, descrita acima. [stage.py:232](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:232), [stage.py:284](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:284), [stage.py:308](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:308).

- **Pontos 9–10:** `bisect_right` inclui corretamente o candle que fecha exatamente no corte; a borda inferior está errada para o ring. Não encontrei IO/relógio nos detectores e no classificador, nem aritmética Decimal fora de `CONTEXT` nas fórmulas examinadas. Concordo com MAD cru, unilateralidade e quantização antes do uso; isso não elimina os problemas temporais e de replay acima. [bootstrap.py:130](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/bootstrap.py:130), [severity.py:109](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/severity.py:109), [stage.py:297](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage.py:297), [revision.py:67](/C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/revision.py:67).

**OBSIDIAN**

- **Revisões Astra — T2.3** — registrar os sete achados, reproduções e critérios de fechamento.
- **Anomalies (Anomaly Engine)** — documentar guarda temporal também em estados terminais e atualização atômica da evidência.
- **Features (Feature Engine)** — distinguir identidade da observação, processamento e disponibilidade histórica; registrar o contrato do ring.
- **Diálogo Claude ⇄ Astra — M2** — registrar que a implementação ainda não comprova identidade temporal nem equivalência bootstrap/live na rolagem.