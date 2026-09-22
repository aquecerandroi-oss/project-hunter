**RESUMO**

**Concordo com manter o P0 do R65 e recomendar não abrir a frente pós-graduação agora. Não aprovaria o veredito quantitativo como definitivo:** encontrei problemas de implementação além das limitações já declaradas.

Sobre suas perguntas:

- **(i)** Sim: “não é melhor”, “distribuição pior”, “board não enviesado” e “há poder a sério” excedem a evidência.
- **(ii)** O ruído permite pesquisa **indicativa**, mas não valida o PnL nem os gatilhos. Os problemas encontrados abaixo também precisam ser corrigidos; apenas acrescentar “indicativa” não basta.
- **(iii)** Entrada condicionada à sobrevivência por uma hora e horizontes de horas/dias continuam sem teste.
- **(iv)** Minha ressalva número 1 seria: **“Este estudo não identifica a diferença de rentabilidade executável entre curva e pós-graduação: observa uma amostra incompleta do board e simula saídas sobre preços esparsos.”**

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `quant-engineer`, em modo OPINIÃO.

**TESTES**

Não executei testes da aplicação, scripts geradores nem consultas à VPS. Conferi código, arquivos de resultados e documentação oficial.

Conferências somente de leitura com `Get-Content`, `ConvertFrom-Json`, `Where-Object` e `Group-Object`:

```text
Entradas simuladas: 4288
Entradas com market cap >= 29470 SOL: 466
Operações da regra de 300 s com hold > 390 s: 721
Saídas fim_da_serie: 295
PnL agregado dessas 295: +0,098010768 SOL
```

**MUST-FIX**

**1. A tabela de taxas está truncada; não representa o FeeConfig completo.**

[metrics.py:16](C:/dev/project-hunter/.claude/state/r66/metrics.py:16) contém dez faixas e estaciona em **0,80% a partir de 24.560 SOL**. A fixture registra **25 faixas**, chegando a 0,30% ([test_pumpfun_fee_config.py:137](C:/dev/project-hunter/packages/exchange-adapters/tests/unit/test_pumpfun_fee_config.py:137)). A [tabela oficial](https://pump.fun/docs/fees) confirma 0,75% a partir de 29.470 SOL e reduções posteriores.

**Cenário concreto:** uma entrada a 100.000 SOL recebe 0,80% no script quando a tabela prevê 0,30%. Há **466 entradas simuladas** acima do primeiro limiar omitido. Isso afeta custos, PnL e contrastes por market cap.

Corrigir e recalcular antes de publicar percentis e resultados finais. Além disso, **2 × mediana da taxa de entrada** é uma aproximação de giro, não a mediana do custo efetivo de entrada e saída. O próprio simulador recalcula a faixa na saída ([sim.py:46](C:/dev/project-hunter/.claude/state/r66/sim.py:46)).

**2. A simulação incorpora lacunas grandes e liquidações retrospectivas.**

O laço aceita qualquer observação posterior, sem limitar a lacuna, e verifica alvo/trailing antes da expiração ([sim.py:61](C:/dev/project-hunter/.claude/state/r66/sim.py:61)). **721 operações duram mais de 390 segundos**, apesar do horizonte de 300 segundos.

Quando a série termina, vende retrospectivamente na última marca ([sim.py:76](C:/dev/project-hunter/.claude/state/r66/sim.py:76)): são **295 operações**.

**Cenário concreto:** última observação aos 120 s, próxima aos 900 s; o script atribui uma saída aos 900 s à regra de 300 s. Se não houver próxima leitura, atribui venda aos 120 s, embora naquele instante ainda não fosse possível saber que seria a última.

Separar saídas observadas, lacunas e censura; apresentar sensibilidade. Esses resultados não reproduzem simplesmente “monitorização a cada 60 s”.

**3. Os 4.400 pares de “+1 minuto” não estão garantidos.**

[value_at:141](C:/dev/project-hunter/.claude/state/r66/load.py:141) procura a leitura mais próxima com tolerância de 90 s, incluindo a própria entrada.

**Cenário concreto:** token com uma única leitura em `t0`. Ela está a 60 s do alvo e é aceita como retorno de +1 minuto, produzindo **zero artificial** e cobertura fictícia.

Exigir observação posterior distinta e publicar os intervalos efetivamente medidos. Isso explica por que cobertura integral em +1 minuto pode coexistir com entradas sem qualquer saída simulável.

**4. “Não enviesado” e a superioridade relativa não foram demonstrados.**

A validação compara somente a entrada com o trade mais próximo, inclusive posterior, até 30 s de distância ([stats.py:65](C:/dev/project-hunter/.claude/state/r66/stats.py:65)). Mediana da razão igual a 1,002 significa **concordância central nessa subamostra**, não ausência de viés nos retornos, extremos ou saídas. O intervalo p10–p90 também é **−14,8% a +21,2%**, não “±15%” como limite conhecido.

**Cenário concreto:** preço executável constante, board alternando entre 100 e 120. A mediana agregada pode parecer correta, mas a simulação registra alvos e trailing artificiais. Erro no preço de entrada também pode criar associação entre “market cap menor” e retorno posterior maior.

Consequentemente:

- “Mediana observada de −79,9% entre os 2.714 pares disponíveis” é defensável.
- “A distribuição pós-graduação é pior que a curva” exige comparação compatível de população, período e execução.
- “Nenhum corte examinado teve média positiva neste modelo” é defensável; “nenhum corte funciona” não é.

**5. A afirmação de ausência de antecipação também precisa de correção.**

O câmbio usa todos os registros do mesmo minuto; na ausência deles, usa a mediana de toda a amostra ([load.py:71](C:/dev/project-hunter/.claude/state/r66/load.py:71), [load.py:114](C:/dev/project-hunter/.claude/state/r66/load.py:114)).

**Cenário concreto:** decisão às 12:00:02 incorpora registros das 12:00:58; um minuto sem câmbio recebe informação de dias seguintes. Isso pode alterar faixas e gatilhos próximos dos limiares.

Usar referência disponível até a decisão, com frescor limitado, ou declarar essa conversão como reconstrução retrospectiva e medir sua sensibilidade.

**NICE-TO-HAVE**

Há duas correções editoriais objetivas:

- O melhor tercil isolado apresentado é **volume acumulado alto: −0,001169 SOL/op**, melhor que −0,002647 de idade alta ([stats.txt:11](C:/dev/project-hunter/.claude/state/r66/stats.txt:11)).
- São **17 linhas incluindo o universo completo**, com cinco cortes simples, dez pares e um corte triplo; não 17 cortes de uma ou duas variáveis ([best.py:24](C:/dev/project-hunter/.claude/state/r66/best.py:24)).

Retiraria “há poder a sério”. São muitos mints, mas apenas oito datas. Permutar dentro do dia não elimina dependência intradiária; bootstrap por dia não cria regimes adicionais. E o contraste de snipers tem IC por dia atravessando zero, embora passe pelo procedimento de p-valores ([stats.txt:21](C:/dev/project-hunter/.claude/state/r66/stats.txt:21)).

**O QUE EU FARIA DIFERENTE**

Escreveria o veredito assim:

> **O R66 não fornece evidência suficiente para justificar abrir uma frente de entradas pós-graduação. A suposta grande economia de taxas não se sustenta; os resultados exploratórios disponíveis são desfavoráveis, mas os números finais precisam de correção nas faixas de taxas, cobertura e tratamento de saídas. Recomendo manter o P0 do R65 — recuperar rent das ATAs elegíveis — e não priorizar essa implementação agora. Isso não demonstra superioridade da curva nem exclui outras estratégias pós-graduação.**

Como hipótese não testada, deixaria **uma nota**, sem abrir implementação: entrar **a partir de +1 h**, condicionado a liquidez e atividade observáveis naquele instante, e acompanhar horas/dias. A seleção precisa ocorrer em +1 h; escolher retrospectivamente sobreviventes e atribuir-lhes entrada na graduação introduziria antecipação. “Continuar no board” também não equivale a sobreviver economicamente.

**CONCORDO COM**

A decisão de não priorizar essa frente pode permanecer mesmo com expectativa estatística inconclusiva: falta evidência favorável e existe trabalho adicional de execução. O adaptador declara exclusivamente venda ([pumpswap/__init__.py:1](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpswap/__init__.py:1)), e o contrato recusa compra por `pumpswap_buy_not_allowed` ([RISK_ENGINE_MEME.md:97](C:/dev/project-hunter/docs/RISK_ENGINE_MEME.md:97)).

Também concordo em retirar +4 h, declarar seleção retrospectiva e preservar a recuperação de rent como melhoria independente. Substituiria “a única economia real” por **“a recuperação de rent identificada no R65 não exige mudar de praça”**.

**OBSIDIAN**

- **Revisoes-Astra/R66 — veredito final:** registrar recomendação, limites inferenciais e correções necessárias antes da publicação.
- **Meme — o que uma “estratégia” é aqui:** distinguir resultado exploratório desfavorável de rejeição geral do pós-graduação.
- **KB-0147 — custo e prejuízo:** vincular recuperação de rent à elegibilidade das contas e incorporar a comparação de custos após recálculo.
- **Hipóteses do plantão:** registrar entrada condicionada em +1 h como hipótese não testada, sem prioridade de implementação.