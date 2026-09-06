**RESUMO**

Eu manteria **valor incremental da invalidação em primeiro lugar**, seguido de alvo assimétrico, saída por tempo e filtro de eficiência de Kaufman. São perguntas testáveis sobre caminhos de preço, sem precisar inventar uma carteira.

Suas três afirmações precisam de ajustes: **(1) correta nos parâmetros padrão, mas “Donchian” exige qualificação; (2) correta sobre o acompanhamento, exagerada no “nunca sabemos”; (3) não é literalmente triple-barrier puro, nem há sobreposição dentro de todo episódio.**

Atuei como `quant-engineer`. As propostas abaixo são adaptações nossas, não estratégias cuja eficácia os livros comprovam para cripto em 15 minutos.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Fiz leitura estática com `Get-Content`/`rg` e consultei fontes dos autores e prévias autorizadas. **Não executei testes, SQL ou replay**; portanto, não confirmei cobertura atual das velas nem frequência empírica de sobreposição.

**MUST-FIX**

**1. Descrever corretamente o que a `momentum_v1` já faz.**

Os padrões são: 15 minutos, 20 fechamentos anteriores, stop/alvo principal a 1,5 ATR, alvos informativos a 3/4,5 ATR e horizonte de 14.400 segundos. [momentum_v1.py:74](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:74)

Mas há três qualificações:

- É **rompimento da máxima dos fechamentos**, excluindo a barra atual, não da máxima dos *highs*. Chamaria de “rompimento de canal de fechamentos, inspirado em Donchian”. [indicators.py:141](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:141)
- Também exige retorno positivo, volume relativo e faixa de ATR%; não é apenas rompimento. [momentum_v1.py:180](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:180)
- A simetria existe **ao redor do fechamento de referência**. A entrada ocorre em outra abertura, acrescida dos custos assumidos; o horizonte começa na abertura de entrada. [momentum_v1.py:216](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:216), [walker.py:42](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:42), [progress.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/progress.py:74)

**Cenário de erro:** referência 100, ATR 2, stop 97, alvo 103 e entrada 101: o potencial bruto é 2/4 = **0,5 R**, não 1 R. E 20 barras de 15 minutos não replicam os rompimentos de 20/55 dias dos Turtles. [Regras publicadas pelo autor de *The Complete TurtleTrader*](https://www.turtletrader.com/rules/)

**2. Distinguir alvo informativo, toque posterior e resultado realizável sob uma política.**

Confirmado: `record.py:137` monta os três preços; a gravação em `agent_signals.targets` acontece em `persist.py:59`. O plano de acompanhamento recebe somente `target1`. [record.py:137](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:137), [persist.py:59](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:59), [record.py:111](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:111)

O walker encerra no primeiro alvo e para de consumir barras quando terminal. Logo, **os outcomes atuais não fornecem uma taxa sistemática de chegada aos alvos 2/3 depois dessa saída**. [walker.py:73](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:73), [walker.py:157](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:157), [walker.py:170](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:170)

“Nunca sabemos” é forte demais: um gap favorável pode registrar `exit_observed` acima desses níveis; além disso, velas posteriores permitem investigação, se preservadas. [walker.py:90](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:90)

**Cenário de erro:** depois do alvo 1, o preço toca o stop e só então chega a 3 ATR. Contar apenas a máxima até quatro horas atribuiria sucesso a um braço que já teria parado no stop. É preciso refazer o caminho desde a entrada, com todas as saídas concorrentes.

**3. Corrigir “literalmente triple-barrier” e localizar a dependência.**

Stop, alvo e horizonte correspondem à estrutura de três barreiras discutida por López de Prado. Entretanto, aqui existe **uma saída adicional por invalidação**, observada no fechamento de 15 minutos e paga na abertura seguinte. Portanto: **modelo de três barreiras acrescido de invalidação e convenções de execução por OHLC**. [López de Prado, capítulos 3–4](https://www.oreilly.com/library/view/advances-in-financial/9781119482086/c03.xhtml), [walker.py:75](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:75), [walker.py:136](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:136)

A máquina de episódios impede outro acompanhamento aberto no mesmo `(strategy_version_id, market_id, cohort)`. Mercados, versões e coortes diferentes podem coexistir. [episodes.py:3](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:3), [episodes.py:62](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:62)

**Cenário de erro:** tratar cem altcoins reagindo ao mesmo movimento do BTC como cem réplicas independentes estreita artificialmente a incerteza. Sobreposição temporal, isoladamente, não prova dependência; tampouco ausência de sobreposição garante independência. O contrato já exige blocos temporais mantendo mercados simultâneos juntos. [SHADOW-LAB.md:19](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:19)

**4. Retirar a promessa incremental do gate `return_4h > 0` para esta entrada.**

Com preços e corte temporal idênticos:

`C_t > max(C_t−1 … C_t−20)` implica `C_t > C_t−16`.

Dezesseis barras de 15 minutos são quatro horas. Portanto, **esse gate já está implicado pelo rompimento**. A definição do retorno é justamente `close_t / close_t−N − 1`. [indicators.py:147](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:147), [price.py:38](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:38)

**Cenário de erro:** o filtro exclui sinais porque a feature está indisponível ou atrasada; publicamos isso como benefício da confirmação de tendência. A candidata consta como T-001 e merece correção explícita. [Registro de Tentativas.md:36](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:36>)

**NICE-TO-HAVE**

Eu aproveitaria **quatro ideias**, nesta ordem. “Testável hoje” significa **com os tipos de dados disponíveis, mediante replay implementado e cobertura verificada**, não que os experimentos já estejam prontos ou executados.

| Ideia e fonte | Experimento concreto | Armadilha provável |
|---|---|---|
| **1. Falha de rompimento — Grimes** | Preservar entradas, stop, alvo e quatro horas; comparar `INV-A/B/C/E`: invalidação atual, nenhuma, dois fechamentos e buffer de 0,25 ATR₀. Já está especificado na [KB-0006:64](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo.md:64). A ligação com [Grimes](https://www.adamhgrimes.com/fundamental-trading-patterns/) é a falha estrutural; esses parâmetros são nossos. | Dizer que perdas em `invalidated` são o custo de invalidar. A continuação pode perder ainda mais. Também não confundir saída do LONG com entrada contrária do *failure test*. |
| **2. Distribuição de R e alvo assimétrico — Van Tharp** | Três braços com alvo efetivo a 1,5/3/4,5 ATR₀ da referência, mantendo stop, invalidação e horizonte. Comparar diferença líquida pareada, cauda e duração. [Van Tharp](https://vantharp.com/wp-content/uploads/2018/06/A_Short_Lesson_on_R_and_R-multiple.pdf) fundamenta a análise em R; não prova que alvo maior melhora este sistema. | Chamar 3 ATR de “3 R”; escolher pelo payoff nominal ou somente pelos vencedores. O R efetivo usa `entrada − stop`. [pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74) |
| **3. Saída por tempo — Grimes** | Comparar horizontes de 1/2/4 horas, sem alterar as outras saídas. Os horizontes menores cabem no acompanhamento máximo atual. O mecanismo já usa `entry_bar_open + horizon_s`. [progress.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/progress.py:74). [Grimes discute time stops](https://adamhgrimes.com/trade-exits/). | Analisar só quem sobreviveu até uma hora, ou transformar a duração média dos vencedores no prazo “ótimo”. O denominador primário deve continuar sendo a população de entradas. |
| **4. Eficiência direcional — Kaufman** | Calcular `ER20 = abs(C_t−C_t−20) / Σ abs(ΔC)` em fechamentos finais de 15 minutos. Primeiro diagnóstico; depois, por exemplo, braço `ER20 ≥ 0,30`, limiar proposto e não validado. Exige cálculo adicional sobre velas, sem novo tipo de coleta. [Fórmula do próprio Kaufman](https://kaufmansignals.com/matching-the-markets-to-the-strategy/). | Confundir trajetória pouco ruidosa com baixa volatilidade; escolher janela/limiar nos outcomes e apresentar como confirmação. ER também pode selecionar movimentos já exauridos. Denominador zero é indisponibilidade. |

**O QUE EU FARIA DIFERENTE**

**Primeiro executaria INV-A/B/C/E, sem renomear a candidata como descoberta desta rodada.** A prioridade já existe no backlog. Seu mérito é identificar o efeito de uma regra nossa com entradas pareadas; não há evidência suficiente para antecipar qual braço ganha. [Strategy Backlog.md:47](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:47>)

O protocolo inicial seria:

1. Reproduzir o braço atual contra os registros persistidos.
2. Ramificar **as mesmas entradas** nos quatro braços, acompanhando cada caminho até sua saída.
3. Medir `ΔR_net`, cobertura por braço, cauda e exposição adicional; manter o denominador de risco inicial.
4. Confirmar apenas em janela futura reservada, com multiplicidade e dependência temporal tratadas.

Isso preserva a distinção já documentada: **efeito da saída condicionado às entradas da base ≠ performance da estratégia completa**, porque a duração altera o rearme e as entradas subsequentes. [KB-0006:90](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo.md:90), [KB-0006:106](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo.md:106)

Quanto aos demais livros, eu separaria assim:

| Autor/família | Aproveitamento e limite |
|---|---|
| **Schwager/Turtles; Clenow** | Regras objetivas de entrada e saída rendem hipóteses. Uma saída móvel pode ser estudada por unidade com OHLC e lógica adicional. Já diversificação, pirâmides e resultado do sistema completo exigem exposição, capital e carteira. Entrevistas ou resultados históricos não validam nossa adaptação. [Turtles](https://www.turtletrader.com/rules/), [Clenow](https://www.followingthetrend.com/the-book/) |
| **Van Tharp; Carver** | Expectancy por entrada é pertinente. Dimensionamento por risco, volatilidade-alvo, combinação de previsões e crescimento composto não são respondidos pela média de R do Lab. Trocar escala de exposição por um filtro binário muda a hipótese. [Van Tharp](https://vantharp.com/wp-content/uploads/2018/06/A_Short_Lesson_on_R_and_R-multiple.pdf), [Carver](https://qoppac.blogspot.com/p/systematic-trading-start-here.html) |
| **Ernest Chan** | Regras univariadas objetivas podem ser adaptadas. Pairs trading e reversão transversal exigem pernas conjuntas, hedge e custos combinados; entradas LONG já registradas não avaliam isso. Não chamar qualquer retorno à média de arbitragem estatística. [Conteúdo de *Algorithmic Trading*](https://www.oreilly.com/library/view/algorithmic-trading-winning/9781118746912/OEBPS/9781118746912_epub_bm_04.htm) |
| **Pardo; Aronson; López de Prado** | Entram como **protocolo**, não três candidatas de alpha: validação temporal, regras falsificáveis, controle da busca e tratamento de dependência. Armadilhas: escolher a janela pelo resultado; omitir tentativas; separar aleatoriamente observações dependentes. Purga de intervalos não torna toda a amostra independente. [Pardo](https://onlinelibrary.wiley.com/doi/10.1002/9781119196969.ch1), [Aronson](https://uat.store.wiley.com/en-us/evidence-based-technical-analysis-applying-the-scientific-method-and-statistical-inference-to-trading-signals-p-9781118268315), [López de Prado](https://www.oreilly.com/library/view/advances-in-financial/9781119482086/c04.xhtml) |
| **Weinstein/Minervini/O’Neil** | Aceitaria apenas uma regra de preço/volume explicitamente formalizada como adaptação. Não colocaria “Stage Analysis”, “VCP” ou “CAN SLIM” como experimentos completos sobre estas entradas. A armadilha é reduzir um método a um indicador e conservar o nome e a evidência do método original. |
| **Douglas** | Disciplina de execução do protocolo; não proponho hipótese de retorno de preço em seu nome. A armadilha é atribuir resultado de um algoritmo à psicologia humana sem observar decisões humanas. |

**Ausência de carteira não impede calcular um contrafactual por unidade. Impede concluir sobre alocação, margem, capacidade, crescimento ou drawdown de capital.** Essa fronteira está expressa no contrato do Lab. [SHADOW-LAB.md:5](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:5)

**CONCORDO COM**

- Investigar a continuação além do alvo 1 tem valor; precisa ser um acompanhamento contrafactual separado.
- Livros devem produzir regras falsificáveis, com transferência de mercado e horizonte declarada.
- Replay exploratório não confirma a hipótese que nasceu da própria amostra. O registro já exige essa separação. [Registro de Tentativas.md:51](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Registro de Tentativas.md:51>)

**OBSIDIAN**

- **Conhecimento — índice:** acrescentar a rodada de livros, distinguindo inspiração, hipótese operacional e protocolo.
- **Strategy Backlog:** preservar invalidação como prioridade; corrigir a redundância de `return_4h > 0`; detalhar alvo, tempo e ER.
- **Registro de Tentativas:** registrar novas propostas sem contá-las como avaliadas; acrescentar a correção de T-001.
- **KB-0006 — Valor incremental da invalidação:** ligar Grimes como referência conceitual, preservando autoria e protocolo existentes.
- **Strategies / EXP-0001-momentum-v1:** esclarecer canal de fechamentos, simetria na referência, alvos informativos e limites da sobreposição.