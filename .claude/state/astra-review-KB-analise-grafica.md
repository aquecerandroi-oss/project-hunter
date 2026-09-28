**RESUMO**

**Revisaria a nota antes de curá-la.** Os números centrais conferidos batem com as fontes; os problemas estão principalmente nas generalizações, no ranking chamado “líquido de custo” e na descrição do contexto do Lab.

Manteria **C1 → C2 → C3 como prioridade provisória de pesquisa**, com condições abaixo. Nenhuma delas tem vantagem demonstrada no nosso mercado.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhuma hipótese registrada, ativação ou commit.

**TESTES**

Não executei testes: revisão documental e leitura estática do código, sem consultar preços ou desfechos do banco. As referências `*.txt` abaixo pertencem a `.claude/state/kb167-fontes/`.

**MUST-FIX**

1. **O resumo e o ranking são mais negativos e universais que as fontes permitem.**

   Em [KB-0167:29](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0167-analise-grafica-o-que-sobra-depois-do-custo.md:29), “evidência séria em um lugar”, “no intradiário […] não paga” e “confirmação por volume quase não acrescenta” ultrapassam os desenhos examinados.

   Há contrapontos dentro das próprias fontes:

   - Hudson & Urquhart também encontram resistência a custos na família de **osciladores**, inclusive os valores já transcritos na nota; `hu.txt:145`. Isso precisa acompanhar a evidência negativa sobre RSI/Bollinger de Gerritsen, não desaparecer no ranking.
   - Schulmeister relata resultados brutos favoráveis no intradiário e diz expressamente não haver tendência clara de queda da rentabilidade nesse horizonte, embora o trecho mais recente seja pior. Não sustenta “todos os efeitos encolhem” da linha 256. [Resumo do artigo](https://onlinelibrary.wiley.com/doi/10.1016/j.rfe.2008.10.001).
   - Lo testa uma definição particular de tendência do volume; Gerritsen testa OBV. Isso não esgota “confirmação por volume”.

   **Correção:** “Entre os estudos consultados, a evidência mais favorável à viabilidade após custos concentra-se em regras diárias de tendência; a transferência ao nosso intradiário não está demonstrada.”

   **Cenário de falha:** a base transforma ausência de validação local em refutação de famílias inteiras e descarta candidatas por uma conclusão que os estudos não testaram.

2. **“Líquida de custo” mistura resultados diferentes, e o intervalo intradiário está mal classificado.**

   [KB-0167:145](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0167-analise-grafica-o-que-sobra-depois-do-custo.md:145) chama **3–16 bps** de efeitos intradiários. Os valores próximos de 16 vêm da família suporte/resistência de Hudson & Urquhart, em **dados diários**. Os 3/7/10 de Shen são **custos de equilíbrio das estratégias**, não coeficientes ou tamanhos genéricos de previsibilidade (`hu.txt:79`, `hu.txt:145`; `suw.txt:524`).

   Na linha 159, Detzel entra na coluna de evidência líquida, mas o **resumo aberto não informa custos**: informa previsão fora da amostra e ganhos de alfa/Sharpe. [Resumo de Detzel et al.](https://onlinelibrary.wiley.com/doi/abs/10.1111/fima.12310).

   Separaria:

   - resultado bruto;
   - custo de equilíbrio, com sua base;
   - resultado líquido sob custos explícitos;
   - resultado líquido fora da amostra.

   Também não se deve interpretar as tabelas 6 e 8 de Hudson como se demonstrassem que **as mesmas regras** sobrevivem simultaneamente ao custo e à correção estatística: as porcentagens publicadas separadamente não dão essa interseção.

   **Cenário de falha:** aprovar ou rejeitar uma candidata comparando custo por operação com ida e volta, ou atribuir robustez líquida e corrigida a uma interseção não verificada.

3. **Corbet está numericamente bem citado, mas a síntese omite uma mudança de sinal importante.**

   Os valores da [linha 122](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0167-analise-grafica-o-que-sobra-depois-do-custo.md:122) conferem: média compra−venda **−0,1245%**, com **11 das 16 diferenças negativas significativas**. Entretanto, o mesmo parágrafo da fonte informa:

   - **sem banda: +0,0138%;**
   - **com banda de 1%: −0,2627%.**

   Fonte: `corbet.txt:219–227`. Logo, “rompimentos de minutos invertidos” não caracteriza igualmente todas as especificações. Isso enfraquece o apoio direcional apresentado para C2 na linha 218.

   Sobre a VMA: **0,072% está realmente escrito** (`corbet.txt:183`). É correto desconfiar da interpretação econômica; o tamanho, sozinho, não demonstra erro de escala. É necessário esclarecer unidade, seleção das observações e alinhamento entre sinal e retorno. “Uso só o sinal” também não resolve eventual problema de alinhamento.

   **Cenário de falha:** importar uma direção média dominada pela banda para `breakout_15m`, cuja regra não é a mesma, e tratar isso como evidência de que comprar sem rompimento será melhor.

4. **A descrição do dado precisa distinguir configuração, disponibilidade e horizonte real.**

   A [linha 177](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0167-analise-grafica-o-que-sobra-depois-do-custo.md:177) está desatualizada: **1.560 minutos é o piso**, não uma janela fixa universal. O contexto é dimensionado por versão, limitado pelo teto; os padrões são piso **1.560** e teto **6.000**. Ver [context_budget.py:310](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/context_budget.py:310) e [config.py:299](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/config.py:299).

   A retenção padrão de **90 dias** confere em [settings.py:123](C:/dev/project-hunter/packages/core/hunter_core/settings.py:123), usada pela política em [partition_retention.py:50](C:/dev/project-hunter/infra/scripts/partition_retention.py:50). Isso **não comprova cobertura completa** desses dias.

   O backfill realmente recusa outro timeframe: [backfill.py:199](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill.py:199). A descrição da coleta padrão em 1 minuto está coerente; não a apresentaria como inventário verificado de tudo que existe no banco.

   Há ainda um erro na linha 198: `volume_anomaly_v1` decide em **5 minutos**, enquanto `momentum_v1` decide em **15 minutos** — [volume_anomaly_v1.py:66](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:66), [momentum_v1.py:74](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:74).

   **Cenário de falha:** planejar C1 como simples aumento da janela, ignorando o orçamento por versão, ou construir uma população incorreta supondo que ambas as estratégias decidem na mesma grade.

5. **C3 atribui aos artigos uma previsão que eles não estimaram.**

   Na [linha 233](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0167-analise-grafica-o-que-sobra-depois-do-custo.md:233), Chung & Bellotti vira argumento para falha **depois do rompimento**. O estudo estima a probabilidade de novo *bounce* ao alcançar uma região, condicionada aos anteriores (`cb.txt:274–305`). Isso não identifica o retorno após selecionar apenas os casos que **já romperam**.

   Osler sustenta agrupamento de ordens e aceleração ao cruzar certos níveis, mas não demonstra que **mais barras próximas do nível** produzam mais continuação (`osler03.txt:12–17`).

   Além disso, a família “support-resistance” de Hudson não representa todas as formas de suporte/resistência: o próprio artigo separa essa família de “channel breakout” (`hu.txt:377`, `hu.txt:408`).

   **Cenário de falha:** registrar uma previsão como derivada da literatura quando ela mudou o evento condicionado e a definição da variável. C3 pode permanecer exploratória, mas com essa extrapolação explícita.

**NICE-TO-HAVE**

- **Auditoria numérica:** não encontrei erro de transcrição nos principais números abaixo:

  | Trecho da nota | Conferência |
  |---|---|
  | Sullivan, linhas 98–102 | Confere com `stw.txt:614`, `:829`, `:860`, `:883`, `:927`. |
  | Lo, linhas 103–105 | Confere com `lmw.txt:918–946`. |
  | Hudson, linhas 106–112 | Confere com `t6.txt`, `t8.txt`, `t9.txt`. |
  | Gerritsen, linhas 113–115 | Confere com `gerr.txt:176–192`. |
  | Grobys, linhas 116–117 | Confere com `grobys.txt:193–200`, `:244–249`. |
  | Shen, linhas 118–121 | Confere com `suw.txt:297`, `:369–370`, `:524–529`. |
  | Osler, linhas 68–70 | Percentuais conferem com `osler.txt:466–467`; mecanismo com `osler03.txt:12–17`. |
  | Park & Irwin | A distinção entre versões está correta: `pi4.txt:40–42`; declínio em futuros em `pi05.txt:31–34`; contagens de 2007 no [resumo publicado](https://ideas.repec.org/a/bla/jecsur/v21y2007i4p786-826.html). |

- **Lo:** a leitura geral é correta, mas padronização **não significa ausência de diferença de média condicional**. Ela permite comparar e agregar ações em escala comum; as médias condicionais aparecem diferentes nas tabelas (`lmw.txt:785–799`, `:1696`). A razão para não concluir lucro é a ausência de estratégia executável com custos, não simplesmente a padronização.

- **Sullivan:** ao mencionar que o atraso elimina a significância pelo Sharpe, acrescentaria que o melhor resultado pelo critério de retorno **continua significativo** (`stw.txt:818–831`). A redação atual é literalmente defensável, mas seleciona apenas a metade desfavorável.

- **Períodos:** Gerritsen usa preços desde julho de 2010, mas avalia estratégias a partir de fevereiro de 2011, após aquecimento (`gerr.txt:163`, `:195`). Em Shen, explicitaria a janela principal da Bitstamp, distinta das outras corretoras (`suw.txt:1025`).

- **Causalidade diária:** a definição de C1 está correta ao excluir o dia corrente. Acrescentaria cobertura integral, dias de calendário e disponibilidade no instante da decisão. `is_final` isoladamente não garante continuidade; a agregação existente recusa minutos faltantes em [aggregate.py:128](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:128).

- A nota diz que as candidatas já estão em **Proximas Hipoteses**, nas linhas 21 e 188, mas não encontrei essa seção no arquivo lido. Corrigir a referência ou acrescentá-las posteriormente apenas como candidatas.

**O QUE EU FARIA DIFERENTE**

**Ranking da evidência:** manteria tendência diária na frente, mas abandonaria a ordenação rígida das demais. “Resultado negativo após custo”, “resultado bruto”, “estatística sem estratégia” e “não encontrei estudo” são estados diferentes; não formam uma escala única de qualidade. Osciladores precisam aparecer como evidência **mista**.

**Ranking das candidatas e colisões:**

| Candidata | Minha avaliação |
|---|---|
| **C1 — primeira, condicional** | Não é automaticamente H-008 ou H-024 renomeada: mede um estado diário aplicado a sinais intradiários. Mas mudar a janela não prova informação nova. Deve entrar junto de `_low`, ATR% e `return_4h`, com análise por estratégia, coorte futura e nível líquido positivo. H-008 continua aberta por estudo inválido; H-023 não matou `_low`; H-024 testa outra política e horizonte. Fontes: `Fila de Hipoteses.md:115`, `:279`, `:284`; `KB-0163:83–89`. |
| **C2 — segunda, em espera** | H-021 morreu por falta de dado, não por refutação econômica. O contraste entre componentes difere da conjunção da H-022, mas deve herdar as guardas de cobertura, progresso e identidade com `mcap_slope_15m` do desenho, além da coorte nova. Se a H-022 falhar por instrumento, C2 também fica bloqueada; se falhar economicamente, retirar um critério precisa de justificativa própria, não de escolha do pedaço vencedor. Fontes: `Fila de Hipoteses.md:261–265`; `exp-m26-grafico-moedas-maduras.md:396`. |
| **C3 — última** | Não é `breakout_strength_20` renomeada, mas “barras próximas” não equivale a visitas independentes ao nível. Separaria aproximação prolongada de rejeições distintas e chamaria a medida de geometria anterior ao rompimento. Não há apoio líquido direto. |

**Nenhuma é, por definição, uma das variáveis esgotadas disfarçada.** O risco é empírico: C1 reproduzir `_low`/tendência; C2 reproduzir progresso ou “já está subindo”; C3 apenas renomear a geometria do rompimento. As regras exigem demonstrar a diferença relevante, não apenas trocar o nome ou o comprimento da janela.

Também deixaria explícito que estudar sinais históricos de versões aposentadas **não autoriza reativá-las** para obter uma coorte nova; a lista de aposentadas está em `Proximas Hipoteses.md:111`.

**Eu colocaria a revisão de prontidão da `sweep_reclaim_v1` à frente de desenvolver C3.** Há implementação e protocolo existentes — [sweep_reclaim_v1.py:139](C:/dev/project-hunter/packages/core/hunter_core/strategies/sweep_reclaim_v1.py:139), `EXP-0017-sweep-reclaim.md:92`. Mas recomendaria verificar os aceites pendentes antes de propor ativação. O próprio EXP declara que mede forma de barra, **não caça a stops** (`:251`); Osler fornece motivação, não validação.

**CONCORDO COM**

- A crítica à alavancagem de Shen: sob custo proporcional ao nocional, **ganho e custo crescem juntos**; alavancagem não muda o sinal do resultado líquido. O artigo realmente faz o argumento contestado (`suw.txt:524–549`). A nota deve apresentar isso como crítica à comparação econômica dos autores.
- A separação entre informação estatística e estratégia lucrativa.
- A ressalva sobre transferência de mercado e horizonte.
- Coorte futura, teste incremental de C1, espera pela H-022 e nenhuma hipótese registrada nesta leitura.

**OBSIDIAN**

- **KB-0167 — Análise gráfica: o que sobra depois do custo:** corrigir generalizações, categorias de custo, contrapontos de Corbet e descrição do contexto.
- **Proximas Hipoteses:** registrar somente candidatas, com dependências e bloqueios explícitos.
- **Dicionario de Variaveis:** documentar a possível medida diária, cobertura e disponibilidade, sem atribuir vantagem.
- **EXP-0017 — Sweep reclaim:** atualizar prontidão e pendências antes de qualquer proposta de ativação.
- **Revisões Astra — KB-0167:** guardar o parecer e a decisão sobre cada divergência.