**RESUMO**

Como `quant-engineer`, minha opinião é **DONE_WITH_CONCERNS**: o desenho é implementável, mas eu fecharia os pontos abaixo antes de congelar sua identidade. Distingo o contrato vigente das mudanças que estou recomendando.

1. **PESOS — prefiro v3, com os testes ajustados em tarefa complementar.**

   Não aceitaria a escolha entre deploy quebrado e suíte permanentemente vermelha. A comparação inclui o JSON inteiro: mudar somente `components_frozen` faz uma v2 existente divergir. [seed_weights.py:53](/C:/dev/project-hunter/infra/scripts/seed_weights.py:53).

   A ausência de scores anteriores explica por que uma ratificação controlada poderia ser segura semanticamente; **não resolve a incompatibilidade operacional**. Tampouco temos nesta revisão evidência dos bancos implantados.

   Recomendo preservar v2 integralmente e publicar v3 congelada. O orquestrador deve atribuir a atualização dos testes do core a uma tarefa com esse escopo: ajustar a lista esperada e substituir a v3 fictícia por uma versão externa ao catálogo. Esses acoplamentos estão em [test_schema_seed_and_partitions.py:887](/C:/dev/project-hunter/packages/core/tests/integration/test_schema_seed_and_partitions.py:887) e [test_schema_seed_and_partitions.py:947](/C:/dev/project-hunter/packages/core/tests/integration/test_schema_seed_and_partitions.py:947).

   **Falha concreta:** banco inicializado com v2/false recebe o release v2/true e o seed aborta. Uma nota mandando apagar a linha transfere a correção para uma operação manual e potencialmente destrutiva. Não recomendo isso.

2. **COMPONENTES versus LACUNAS — aceito denominador do perfil implementado, explicitamente congelado.**

   Separe `inputs_expected` do **perfil executável** e `inputs_not_implemented` do escopo originalmente desejado. Não determine o denominador procurando quais chaves chegaram naquele vetor: isso faria uma ausência operacional desaparecer da cobertura.

   Aceito Liquidity baseada somente em spread neste perfil, com nome explicativo como “componente de liquidez baseado em spread”. Sua confiança mede cobertura dessa definição limitada; não comprova profundidade nem capacidade de execução. O contrato original inclui três fontes, portanto essa redução precisa constar expressamente da definição versionada. [PIPELINE.md:108](/C:/dev/project-hunter/docs/PIPELINE.md:108).

   **Ressalva sobre DOWN:** MAD inverso mede *estreitamento relativo*, não liquidez absoluta. Pela transformação existente, spread na mediana produz zero, mesmo que seja pequeno. [severity.py:118](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/severity.py:118).

   **Falha concreta:** spread cai de 2% para 1% e recebe forte contribuição por melhora relativa; isso não permite explicar “mercado líquido”. Preserve valor bruto, referência e limitação.

3. **AGREGAÇÃO — eu usaria denominador fixo também dentro do componente.**

   A decisão conjunta proíbe redistribuição, mas não especifica a agregação interna. Portanto, não chamaria sua média de violação textual inequívoca; **ela introduz, matematicamente, uma redistribuição entre inputs**. [M2.md:53](/C:/dev/project-hunter/docs/plans/M2.md:53).

   Minha proposta para `N` inputs esperados do perfil:

   `component_score = Σ severidades_disponíveis / N`

   `component_confidence = Σ maturidades_disponíveis / N`

   A segunda expressão equivale à sua média de maturidade multiplicada pela cobertura. Ausência fica registrada como indisponível, com contribuição aritmética nula; não vira uma observação bruta igual a zero.

   **Falha concreta:** severidades `[100, 0]` dão 50. Perdendo o segundo input, a média dos disponíveis sobe para 100 apenas porque faltou informação. Reduzir confidence não desfaz a subida do score nem uma possível promoção de status. Com denominador fixo, continua 50.

4. **DEGRADADO — concordo, por dependência.**

   Exclua `quality=degraded` da evidência elegível; preserve valor e motivo apenas na explicação. A T2.3 distingue número disponível para exibição de avaliação elegível. [evaluation.py:72](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/evaluation.py:72), [evaluation.py:210](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/evaluation.py:210).

   Não transforme book degradado em veto automático a retornos saudáveis: a herança de qualidade da T2.2 é por dependência efetivamente usada. [engine.py:85](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/engine.py:85).

   Sem evidência de mercado elegível, não produza novo score. O último permanece para exibição com seu timestamp original e carimbo de atraso; não o apresente como avaliação atual. Essa apresentação já está prevista em [M2.md:17](/C:/dev/project-hunter/docs/plans/M2.md:17).

5. **DIREÇÃO E CIRCULARIDADE — duas passadas, sim; sinal do MAD como LONG/SHORT, não.**

   O `direction` de `evaluate_deviation` significa **acima/abaixo da mediana**. [severity.py:136](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/severity.py:136).

   Cada input precisa declarar separadamente sua regra de direção econômica. Volume, velocidade, spread e aumento de OI isolado não devem votar automaticamente LONG. Pressão compradora/vendedora complementar também não deve virar duas evidências independentes.

   **Falha concreta:** retorno atual −1%, mediana −3%: desvio positivo não significa preço subindo. Converter `UP` diretamente em LONG atribui direção errada.

   Aceito calcular direção sem Regime e avaliar compatibilidade depois. Use contribuições com o mesmo orçamento interno da agregação; empate exato produz NEUTRAL.

   Quanto à confiança, **aceito seu piso 0,5 como hipótese versionada**, sem alegar calibração. Defina:

   `A = |Σ contribuições_direcionais_assinadas| / Σ módulos`

   Quando o denominador for zero: `A=0`, direção NEUTRAL e motivo `no_directional_evidence`. A cobertura ponderada deve incorporar maturidade, não somente disponibilidade, sem multiplicar a cobertura interna duas vezes. Regime não participa do consenso que produziu sua própria direção de entrada. A dependência de confidence em qualidade, disponibilidade e concordância está em [PIPELINE.md:116](/C:/dev/project-hunter/docs/PIPELINE.md:116).

6. **EARLY-MOVEMENT — concordo: penalidade e status são efeitos distintos previstos.**

   `−10` altera pontuação; EXTENDED altera classificação e precedência. Ambos estão expressos na decisão conjunta. [M2.md:53](/C:/dev/project-hunter/docs/plans/M2.md:53), [M2.md:55](/C:/dev/project-hunter/docs/plans/M2.md:55).

   Use o estágio publicado, e leia a magnitude do perfil, mesmo sendo 10 hoje. [seed_reference.py:190](/C:/dev/project-hunter/infra/scripts/seed_reference.py:190).

   Preserve também **a direção publicada do estágio**, separada da direção calculada para a oportunidade. A T2.3 distingue essas direções durante a histerese. [stage/model.py:154](/C:/dev/project-hunter/packages/indicators/hunter_indicators/stage/model.py:154).

   **Cenário a testar:** EARLY/LONG ainda publicado enquanto a direção da oportunidade virou SHORT. O contrato atual mantém o fator por estágio; a explicação não pode chamar isso de “EARLY confirmado para SHORT”. Condicionar o bônus ao alinhamento seria outra mudança de contrato.

7. **ANOMALY abaixo de 40 — o contrato literal expira; sua alternativa é uma mudança que considero razoável.**

   A precedência de ANOMALY não suspende a expiração terminal. O contrato vigente exige 15 minutos válidos abaixo de 40, sem exceção por anomalia ativa. [M2.md:55](/C:/dev/project-hunter/docs/plans/M2.md:55).

   Recomendo formalizar uma regra de **sustentação do episódio**: anomalia ativa, elegível e com severidade ≥60 interrompe a sequência de expiração por score. Não basta `status=active`, pois uma anomalia pode permanecer ativa e inelegível. [analysis.py:112](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:112).

   **Falha concreta do desenho literal com reabertura automática:** score 30 e anomalia 70 contínuos geram episódios sucessivos para a mesma condição. Contudo, “recuperação posterior” não define expressamente que essa condição inalterada autoriza reabrir; não trate a reabertura como já resolvida.

   Minha preferência é sua segunda opção, **registrada como revisão do contrato antes da implementação**. Feche junto o caso EXTENDED abaixo de 40, para não deixar a mesma ambiguidade no outro estado que precede WATCHING.

8. **EXPIRAÇÃO COMPROVADA — zerar, sim; 15 leituras não bastam para provar continuidade.**

   Zere `since` e contagem quando a qualidade necessária se perder ou não houver score válido. Pausar e somar contradiz a continuidade exigida. [DATABASE.md:1199](/C:/dev/project-hunter/docs/DATABASE.md:1199). A T2.3 já zera ambos ao receber avaliação inelegível. [lifecycle.py:257](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:257).

   Aceito tempo **e** contagem como guardas complementares. Porém, derivar “15 leituras” de “15 minutos” exige fixar uma política de amostragem por minuto; quantidade e duração são unidades distintas.

   **Falha concreta:** 14 leituras rápidas, silêncio prolongado e uma leitura após 15 minutos satisfazem as duas condições sem comprovar o intervalo. A limitação equivalente está documentada em [.claude/state/notes-T2.3.md:408](/C:/dev/project-hunter/.claude/state/notes-T2.3.md:408).

   Exija observações distintas e crescentes, tratamento explícito dos minutos sem evidência pelo watchdog e estado recuperável. No restart, um intervalo não comprovado interrompe a sequência. Com amostras pontuais em `t0, t1, …, t15`, completar quinze minutos normalmente exige **16 pontos**, não quinze.

9. **REGIME v0 — concordâncias e ajustes em (a)–(f).**

   **(a)** Aceito configuração imutável no código, `classifier_version` e parâmetros completos no envelope. O precedente da T2.3 versiona os limiares e os serializa. [detectors.py:45](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:45), [detectors.py:105](/C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:105). Se houver overrides, a identidade precisa incorporar o conteúdo; `regime_v0` sozinho não basta.

   **(b)** Aceito calcular retorno de 1 dia internamente a partir das candles fornecidas: isso está expressamente permitido pelo [brief:9](/C:/dev/project-hunter/.claude/state/brief-T2.4-regime-opportunity.md:9). Declare-o como estatística interna versionada, sem fingir que pertence ao registry. Retornos devem usar o mesmo corte, candles finais disponíveis na decisão e unidades compatíveis com ATR. Aceito 2/4 como hipóteses iniciais, não limiares empiricamente validados.

   Falta fechar também a volatilidade: **`volatility_1h` não está na v1**, além de `return_1d`. [.claude/state/notes-T2.2.md:237](/C:/dev/project-hunter/.claude/state/notes-T2.2.md:237). Defina estimador, frequência das amostras históricas, janelas, cobertura, denominador zero e limiares HIGH/LOW; “mediana de 30 dias” sozinha não torna o cálculo reproduzível.

   **(c)** Confirmo UNKNOWN durante o warm-up de 30 dias, mesmo com tendência calculável. Preserve a tendência parcial apenas como evidência explicativa. [enums.py:228](/C:/dev/project-hunter/packages/core/hunter_core/domain/enums.py:228).

   **(d)** Aceito a ordem proposta **como projeção analítica versionada**, mas discordo de justificá-la como automaticamente mais conservadora para o Risk Engine. Os presets usam `BTC_BEAR_LONG=0,5` e `HIGH_VOLATILITY=0,7`. [seed_reference.py:107](/C:/dev/project-hunter/infra/scripts/seed_reference.py:107).

   **Falha concreta:** BTC bearish com alta volatilidade vira HIGH_VOLATILITY; pelo contrato de lookup, um LONG recebe 0,7 em vez de 0,5. Só um multiplicador é aplicado. [RISK_ENGINE.md:41](/C:/dev/project-hunter/docs/RISK_ENGINE.md:41). Preserve `{trend, volatility}` e registre essa incompatibilidade para o contrato de consumo de risco; mudar apenas a ordem não resolve todas as direções.

   **(e)** Aceito UNKNOWN imediato por falta de evidência obrigatória; sair de UNKNOWN exige três observações válidas distintas. Defina se a histerese acompanha o par completo — minha preferência — para que mudanças ocultas pela projeção principal não alterem a compatibilidade sem confirmação.

   **(f)** Prefiro breadth como confirmação, sem veto, neste v0. Cobertura abaixo de 80% significa confirmação indisponível; não mercado bearish. Cobertura e concordância são campos diferentes. Congele a fórmula de confidence e preserve composição, exclusões e denominador do universo, conforme [M2.md:57](/C:/dev/project-hunter/docs/plans/M2.md:57).

   Há ainda uma correção de escopo: o banco representa regimes **GLOBAL/BTC**, não uma linha por mercado arbitrário; o índice é por `scope`. Avaliações por mercado podem alimentar breadth, mas não cabem diretamente nessa tabela. [enums.py:220](/C:/dev/project-hunter/packages/core/hunter_core/domain/enums.py:220), [analysis.py:133](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:133).

10. **HISTÓRICO — concordo, acrescentando mudanças semânticas.**

    A regra base coincide com [M2.md:58](/C:/dev/project-hunter/docs/plans/M2.md:58). Eu acrescentaria mudança de **direção da oportunidade**, do **par publicado de regime** e da **direção publicada do estágio**.

    **Falha concreta:** LONG→SHORT com mesmo score, status, estágio e qualidade fica invisível por até cinco minutos. Mudança do regime pode também alterar a explicação sem superar três pontos.

    “Qualquer versão” deve incluir scorer/componentes, direção/confidence, classificador de regime, detectores e templates, além das versões citadas. Aceito `history_v1` no código, congelada e registrada.

    Não dispararia por qualquer `baseline_id` novo ou por toda oscilação de confidence: isso pode anular a amostragem. Compare sempre contra o último registro efetivamente persistido; reentrega não produz nova amostra nem avança seu timestamp.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Revisão estática; não executei testes nem consultei bancos. Os cenários acima são critérios propostos de teste, não resultados observados.

**MUST-FIX**

Antes de implementar, fechar especialmente:

- **Item 1:** upgrade de banco com v2 existente, sem reparo manual destrutivo.
- **Itens 3 e 5:** ausência não elevar contribuição; desvio positivo não fabricar LONG.
- **Itens 7 e 8:** contrato de sustentação/reabertura e continuidade comprovada.
- **Item 9:** fórmula completa de volatilidade, causalidade, escopos e consumo do regime pelo risco.
- **Item 10:** registrar inversões de direção mesmo com score estável.

**NICE-TO-HAVE**

Exibir separadamente cobertura do perfil implementado, lacunas do produto e concordância direcional.

**O QUE EU FARIA DIFERENTE**

Congelaria uma tabela por input com transformação, direção, orçamento fixo, elegibilidade e motivo de ausência. Publicaria v3 junto da adaptação dos testes de seed.

**CONCORDO COM**

Funções puras, duas passadas para direção/regime, exclusão de degradados, estágio publicado, Early-Movement assinado, UNKNOWN imediato por cegueira e histórico relativo ao último persistido.

**OBSIDIAN**

- **Features (Feature Engine)** — atualizar catálogo entregue e separar lacunas do build de indisponibilidade operacional.
- **Anomalies (Anomaly Engine)** — registrar que direção do desvio não equivale a LONG/SHORT e contagem não comprova continuidade.
- **Diálogo Claude ⇄ Astra — M2** — registrar as decisões sobre agregação, sustentação de episódios e projeção do regime.
- **Revisões Astra — T2.4** — criar nota vinculada com estes dez pontos e seus cenários de aceite.
- **Data Flow** — esclarecer avaliações por mercado versus regimes persistidos GLOBAL/BTC.