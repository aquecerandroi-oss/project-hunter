**RESUMO**

A afirmação central da KB-0057 **sobrevive como diagnóstico provável da Momentum nessa janela; não sobrevive como conclusão sobre todo o Lab**. As medições justificam investigar filtros de volatilidade e liquidez, mas ainda não demonstram o mecanismo de M-A nem a prontidão de M-B.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, como `quant-engineer`.

**TESTES**

Não executei suítes nem consultas na VPS. Conferi código, SQL publicado e fontes externas; trato os resultados da VPS como medições suas, sem alegar reprodução independente. A soma da tabela de sinais é **978**, não 1.004.

**MUST-FIX**

1. **O piso existe antes da emissão, mas “o Lab é de altcoin/meme por construção” extrapola. — Pergunta 1**

   Momentum exige `atr_pct_min ≤ atr_pct ≤ atr_pct_max` antes de construir a decisão. Contudo, rompimento, retorno e volume relativo são verificados antes desse gate: [momentum_v1.py:180](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:180), [gate:204](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:204).

   Volume Anomaly não tem o piso absoluto. Usa ATR para limitar o **retorno de 5 minutos**, além de exigir volume e fechamento acima do meio da barra: [volume_anomaly_v1.py:150](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:150).

   Portanto, **0 Momentum versus 1 Volume Anomaly é compatibilidade observacional, não confirmação independente do mecanismo**. Sua ressalva sobre rompimento/RVOL está correta. Acrescentaria: cadências diferentes, disponibilidade das janelas e períodos efetivamente avaliados. Os 1.004 sinais de outros mercados não são 1.004 testes da hipótese sobre BTC.

   **Cenário de falha:** BTC não apresenta nenhum rompimento com RVOL suficiente; remover o piso continua produzindo zero sinais. Ou BTC ultrapassa 0,3% em outro regime e passa pelo filtro normalmente.

   Redação defensável: “O estimador SMA ficou abaixo de 0,3% em todas as 154 observações de BTC; isso sugere exclusão pelo gate da Momentum, a confirmar com o Wilder e a população efetivamente avaliável.”

2. **SMA versus Wilder não tem viés de direção universal; o SQL também muda a população. — Pergunta 2**

   O código recebe 97 barras, calcula 96 TRs, inicializa com 14 e aplica **82 passos de suavização**, dividindo pelo último fechamento: [indicators.py:88](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:88). Ambas as medidas incluem a última barra completa; a diferença não é “barra corrente versus aquecimento”.

   Com o mesmo fechamento:

   | Situação | Relação típica | Consequência possível do SMA |
   |---|---|---|
   | TR cresce persistentemente | SMA acima de Wilder | Menos barras abaixo do piso; mais acima do teto |
   | TR cai persistentemente | SMA abaixo de Wilder | Mais barras abaixo do piso; menos acima do teto |
   | Choque isolado | Relação muda conforme o choque envelhece | Pode inverter qualquer uma das classificações |

   O Wilder preserva memória de choques que já saíram das últimas 14 barras. **Exemplo sintético, não medição do BTC:** fechamento constante, TR usual de 0,1%, um choque de 10% seguido de 14 barras usuais. SMA = **0,1%**; Wilder = aproximadamente **0,3506%**. O SMA reprova pelo piso; Wilder admite pelo critério de ATR. Logo, mediana distante do piso não prova ausência de inversões. O peso residual da seed após 82 passos é aproximadamente 0,2295%; isso não limita o erro total SMA–Wilder.

   Além disso, seu SQL remove barras incompletas e depois usa `lag`/`ROWS`: atravessa lacunas. A estratégia rejeita uma janela se faltar qualquer minuto: [aggregate.py:128](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:128).

   **Cenário de falha:** uma listagem com pouco histórico recebe ATR no SQL, mas permanece `UNAVAILABLE` na estratégia; sua fração vira “recusa pelo teto” quando nenhuma avaliação seria possível. As porcentagens publicadas continuam válidas para o estimador descrito, mas não são porcentagens de rejeição operacional.

3. **−0,651 não demonstra o mecanismo de M-A. — Pergunta 3**

   É uma associação transversal entre mercados, com medidas temporalmente desalinhadas. Não demonstra que **ATR maior no instante do sinal implica maior custo de execução**, nem que os cortes de 2%/3% selecionem justamente esses custos.

   Profundidade em 20 níveis também depende da distância entre níveis e do tick relativo. Somar os dois lados não mede diretamente a execução compradora — muito menos a venda de saída.

   **Cenário de falha:** moedas menores combinam ATR médio alto e livro top-20 pequeno, mas os rompimentos atraem liquidez suficiente. Baixar o teto elimina oportunidades sem reduzir o custo condicionado ao sinal. O resultado com custos fixos pode melhorar por outro motivo e ser atribuído incorretamente à liquidez.

   **Com o dado existente**, eu faria:

   - Wilder exato por mercado e fechamento, associado apenas a snapshots anteriores comprovadamente disponíveis; medir ATR versus **spread**, inclusive condicionado aos sinais.
   - Recalcular a associação com livro sem BTC, separando A/B e removendo um mercado por vez; usar custos de travessia e profundidade dentro de distância fixa em bps, quando os 20 níveis permitirem.
   - Comparar aceitos/rejeitados pelos tetos em spread, cobertura e sensibilidade de `R_net`.

   Isso pode sustentar o **componente spread** da hipótese. O mecanismo completo de profundidade/custo exige livros repetidos, contemporâneos e tamanho declarado. Uma leitura só não recupera essa evidência.

4. **M-B está pronta para diagnosticar disponibilidade, não comprovadamente pronta para avaliação causal. — Pergunta 4**

   Os 63% misturam a hora do deploy. Podem representar recuperação progressiva ou ausência concentrada em determinados mercados; o agregado não distingue.

   Há um problema concreto adicional: REST e WS compartilham `ts`, mas volume pertence ao REST; o WS pode atualizar o timestamp sem atualizar o volume: [hot_state.py:61](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:61). O snapshot julga o frescor de `quote_volume_24h` por esse timestamp compartilhado: [sampling.py:55](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:55).

   **Cenário de falha:** REST deixa de atualizar; bookTicker continua chegando. Volume antigo aparece preenchido e “fresco”, enquanto M-B afirma usar liquidez no instante da decisão.

   Minha classificação seria **“especificada; diagnóstico de cobertura liberado; avaliação da candidata bloqueada até validar disponibilidade e frescor”**. Não exige esperar um número arbitrário de dias nem necessariamente 100% de cobertura. Exige cobertura por oportunidade/coorte/hora, idade da fonte, regra para ausentes e θ congelado numa janela anterior. O contexto atual da estratégia também não recebe esse campo: [base.py:109](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:109).

5. **A definição de meme conflita com integrantes da lista; a coorte B não identifica efeito de meme. — Pergunta 5**

   “Sem utilidade declarada” é falso como definição universal:

   - **DOGE:** declara finalidade de moeda/pagamentos. [Fonte oficial](https://dogecoin.com/).
   - **FLOKI:** declara utilidade em jogos e DeFi. Isso contradiz o critério, sem necessariamente invalidar sua classificação cultural como meme. [Fonte oficial](https://floki.com/).
   - **PENGU:** pertencer a uma marca/NFT não prova direito econômico sobre receitas; tampouco impede classificação cultural como meme. O próprio aviso do token o apresenta como entretenimento. [Fonte oficial](https://claim.pudgypenguins.com/).

   Eu corrigiria a **definição**, preservando a lista v1 para não reclassificar depois de ver resultados. Separaria origem cultural, utilidade declarada e direito a fluxo de caixa.

   A regex identifica caracteres fora do conjunto alfanumérico ASCII. **Não identifica idade nem natureza econômica.** É uma coorte descritiva reproduzível; não é instrumento para distinguir “meme” de “listagem recente”.

   **Cenário de falha:** cinco contratos recentes e pouco líquidos concentram ATR elevado; o efeito é atribuído a memes, embora idade, seleção por volume ou desenho do tick expliquem a diferença. Isso invalida a interpretação causal, não as estatísticas desses cinco símbolos.

6. **Derrubaria por completo a inferência de que “a volatilidade migrou para as listagens novas”. — Pergunta 6**

   Uma fotografia de 42 horas, sem idade de listagem nem comparação longitudinal, não demonstra migração. Demonstra heterogeneidade contemporânea.

   Também retiraria a alegada discordância com ME2F porque TRUMP tem ATR intermediário. O trabalho mede fragilidade combinando volatilidade, concentração e sentimento; ATR de 42 horas não refuta esse objeto. [Resumo do estudo](https://arxiv.org/abs/2512.00377).

   **Cenário de falha:** TRUMP passa dois dias tranquilo e permanece altamente concentrado e sensível a notícias. A nota anuncia discordância onde as duas observações podem ser simultaneamente verdadeiras.

7. **A KB-0056 confunde reconstrução da classificação com reconstrução do universo monitorado.**

   Uma lista estática versionada, aplicada à identidade preservada do mercado, permite reconstruir a classificação cultural. O registro identifica mercado, exchange e símbolo: [record.py:188](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:188).

   O que não decorre disso é recuperar **ranking e composição histórica do top 200**, sobretudo mercados sem sinais.

   **Cenário de falha:** declarar toda estratificação histórica irrecuperável bloqueia uma análise válida com `meme_universe_v1`, enquanto adicionar apenas tags aos sinais é tratado como solução para um denominador histórico que continua ausente.

**NICE-TO-HAVE**

- Publicar o SQL executável completo: a KB-0057 contém `ARRAY[...]`; faltam os scripts da travessia e da correlação. Isso limita reprodução, sem colocar em dúvida que você executou as medições.
- Reconciliar **978 versus 1.004 sinais** e declarar cortes temporais por consulta.
- Trocar “o rótulo não separa volatilidade” por “as medianas agregadas de A e E são próximas nesta janela”. Medianas próximas não estabelecem equivalência de distribuições.
- Corrigir a comparação com majors: DOGE 0,5575% e PEPE 0,5319% não estão abaixo de 0,5019%; além disso, são estatísticas agregadas de maneiras diferentes.
- Em KB-0058, 42,82 bps são aproximadamente sete vezes **spread + slippage de 6 bps**, não o custo total por perna incluindo taxa.

**O QUE EU FARIA DIFERENTE**

Prioridade: executar **D-MEME-ATR** antes de promover M-A. Separaria três números: gate de ATR isolado nas janelas válidas, exclusões adicionais após os demais critérios e emissões efetivas.

Para M-A, faria primeiro seleção sobre população fixa da base. Um braço independente muda ocupação e rearme dos slots, podendo gerar oportunidades diferentes: [decide.py:144](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:144). Seu resultado não deve ser apresentado automaticamente como efeito pareado do filtro.

Para M-B, começaria pelo diagnóstico de frescor por produtor e cobertura nas oportunidades.

**CONCORDO COM**

- Congelar a lista antes das consultas e declarar a zona cinzenta.
- Tratar seleção por listagem e top 200 como limitação de generalização.
- Não concluir que excluir BTC torna o piso errado.
- Separar travessia contra o mid de slippage sem meio spread.
- Usar retenção e contribuição por oportunidade, além da média por aceito.
- Manter essas propostas como pesquisa; os dados ainda não demonstram vantagem econômica.

**OBSIDIAN**

- **KB-0056 — Meme coin como ativo:** ajustar definição e separar classificação recuperável de composição/ranking históricos.
- **KB-0057 — A volatilidade das memes:** restringir a conclusão à Momentum, corrigir população do ATR e retirar a alegação de migração.
- **KB-0058 — Spread e profundidade:** rebaixar evidência do mecanismo e condicionar M-B à proveniência temporal.
- **Strategy Backlog:** distinguir diagnóstico disponível, implementação pendente e evidência insuficiente para M-A/M-B.
- **KB-0044 — O que morre em dez segundos:** registrar o risco de volume antigo herdar frescor do bookTicker.