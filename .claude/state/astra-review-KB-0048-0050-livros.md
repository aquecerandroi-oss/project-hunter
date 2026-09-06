**RESUMO**

As notas têm boas propostas, mas precisam de correções antes de virarem protocolo:

- **KB-0050:** a conversão para R está dimensionalmente correta; a equivalência com um piso fixo de ATR é apenas nominal. `confidence` constante e `constant_uncalibrated_v1` estão confirmados.
- **KB-0049:** condicionar aos filtros e retirar somente o rompimento é defensável como diagnóstico incremental, mas o nulo ainda não está suficientemente especificado.
- **KB-0048:** “quase a mesma coisa” exagera a relação entre VR e ER. A auditoria simples de sobrevivência é executável; não constitui uma auditoria histórica completa.

Atuei como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Leitura estática com `Get-Content`/`rg`, consulta às fontes públicas e contas sintéticas em memória. Não executei pytest, SQL ou replay; não confirmei populações reais.

Saídas das verificações aritméticas:

```text
nominal_c=0.4444444444444444444444444444
ATR=0.29 P_entry=100.0600 cost_proxy_R=0.4042828282828282828282828283 old_floor_accept=False
ATR=0.30 P_entry=100.0600 cost_proxy_R=0.3923921568627450980392156863 old_floor_accept=True
```

Contraprova sintética de redundância, com variância populacional e retornos agregados sobrepostos:

```text
ER_both=1
VR2_alternating=0
VR2_grouped=1.894736842105263
```

**MUST-FIX**

**1. KB-0050: separar conversão de unidades, aproximação nominal e filtro efetivo.**

A [KB-0050:62](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo.md:62) está correta **se** `custo_total_bps` significa o custo por unidade expresso em bps de `P_entry`:

\[
D_R=\frac{D}{P_{\rm entry}-stop}
=\frac{b}{10000\,[(P_{\rm entry}-stop)/P_{\rm entry}]}.
\]

Mas `b = spread + 2·slippage + 2·fee = 20 bps` é uma aproximação: o código aplica spread/slippage aos preços de cada ponta, cobra fee sobre cada preço e desconta funding separadamente. [pricing.py:9](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:9), [pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74)

Para o piso, sejam `C` o fechamento de referência, `a=ATR/C`, `k=1,5` e `g=P_entry/C−1`. Como `stop=C−k·ATR`:

\[
\frac{P_{\rm entry}-stop}{P_{\rm entry}}
=\frac{g+ka}{1+g}.
\]

Com `b` fixo, o teto `D_R≤c` equivale a:

\[
a\geq\frac{(1+g)b/(10000c)-g}{k}.
\]

Portanto, **não equivale a um piso constante de ATR quando `g` varia**. Os níveis partem do fechamento; a entrada usa outra abertura acrescida de custos. [momentum_v1.py:217](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:217), [walker.py:44](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:44)

**Cenário de falha:** com referência e próxima abertura em 100, ATR `0,29`, entrada `100,06` e stop `99,565`, o piso atual rejeita `atr_pct=0,0029`. Entretanto, o proxy de custo efetivo é `0,404283 R`, abaixo do teto nominal `0,444444 R`. A “reparametrização sem mudar comportamento” da [KB-0050:84](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo.md:84) aceitaria essa entrada.

Eu manteria **`custo_R_nominal_referencia`** como tradução exata do parâmetro atual, usando `b/(10000·k·atr_pct)`. Um filtro baseado no R efetivo seria outra hipótese, inclusive porque `P_entry` ainda não é conhecido na decisão.

**2. KB-0049: definir precisamente o contraste e a distribuição nula.**

Condicionar a mercado, horário, `rvol`, faixa de ATR e retorno positivo, **sem exigir rompimento**, é defensável para perguntar:

> Dentro dessa população elegível, selecionar rompimentos melhora o resultado sob esta política de saída?

Isso não testa “entrada sem informação nenhuma”: os próprios filtros preservados podem carregar informação. Também **não exigir rompimento** difere de **exigir ausência de rompimento**; a nota deve escolher explicitamente. [KB-0049:82](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos.md:82), [KB-0049:95](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos.md:95)

Há quatro problemas concretos:

- **Invalidação dependente do rompimento.** Sem rompimento, a referência pode estar abaixo de `B`. O walker invalida quando um fechamento posterior fica abaixo desse nível, mesmo sem cruzamento de cima para baixo. [walker.py:136](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:136)  
  **Falha:** controles encerram no primeiro fechamento de 15m porque continuam abaixo de `B`; o resultado é vendido como poder preditivo isolado da entrada. O contraste inclui a interação entre entrada e invalidação. Isso é aceitável se declarado; para isolar a entrada, acrescentaria uma comparação com saídas independentes do rompimento.

- **Deriva e mudança de regime.** Mesmo mercado e hora UTC não equilibram as datas dentro do experimento.  
  **Falha:** sinais concentram-se numa semana de alta e controles numa semana de queda; o contraste mistura seleção temporal, regime e rompimento. Fixaria blocos de calendário e, quando pertinente, estados observáveis antes da decisão. Blocos para calcular incerteza, sozinhos, não corrigem esse desequilíbrio.

- **Réplicas e estatística indefinidas.** A [KB-0049:64](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos.md:64) descreve `200` controles por sinal, mas não distingue distribuição de outcomes individuais de distribuição da média do experimento.  
  **Falha:** tratar `200×N` outcomes como observações independentes produz precisão fictícia. Reutilizar datas entre réplicas Monte Carlo não é, por si, viés; ignorar dependência dentro delas é o problema. É preciso definir estatística, ponderação, reposição, blocos conjuntos entre mercados e tratamento de candidatos insuficientes. Se a pretensão for reproduzir a estratégia completa, também precisa reproduzir ocupação e rearme dos episódios. [episodes.py:62](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:62)

- **Elegibilidade histórica não vem apenas dos candles.** Avaliações sem sinal retornam sem persistir uma observação individual, e o universo atual é sobrescrito. [decide.py:155](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:155), [universe_repo.py:169](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:169)  
  **Falha:** controles reconstruídos com dados recuperados posteriormente são apresentados como oportunidades disponíveis ao vivo. Exigir proveniência histórica ou rotular como **replay reconstruído**, publicando cobertura, `no_entry`, censura e funding indisponível.

Chamaria inicialmente de **benchmark aleatório condicionado**, não de teste de permutação validado. O sorteio não demonstra automaticamente a intercambialidade necessária para interpretar um p-valor.

Também corrigiria “zero é o nulo errado”: zero continua relevante para perguntar se a expectancy líquida é positiva; o benchmark responde outra pergunta. Superar um controle de `−0,30 R` com `−0,08 R` não demonstra rentabilidade.

**3. KB-0048: retirar a quase equivalência entre VR e ER.**

A afirmação da [KB-0048:40](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro.md:40) é forte demais.

ER mede deslocamento líquido relativo ao caminho absoluto. VR mede como a variância cresce com o horizonte; para retornos aditivos estacionários:

\[
VR(q)=1+2\sum_{j=1}^{q-1}(1-j/q)\rho_j.
\]

São propriedades diferentes. A literatura de VR trata explicitamente testes de passeio aleatório e autocorrelação, inclusive suas limitações amostrais. [Lo e MacKinlay](https://www.nber.org/papers/t0066)

**Contraprova calculada:** vinte log-retornos positivos alternando `1,2,1,2,…`, em unidades comuns, produzem preços monotônicos: `ER=1`, mas cada retorno agregado de duas barras é igual, logo `VR(2)=0`. Reordenando os mesmos retornos em dez `1` seguidos de dez `2`, permanece `ER=1`, mas `VR(2)=1,894737` pela convenção declarada.

**Cenário de falha:** descartar VR como duplicata de ER elimina uma medida de dependência serial que a ER não identifica.

Concordo em medir correlação antes de abrir braços. Porém, `|ρ|≥0,8` deve ser uma **regra pragmática de priorização**, não prova de redundância. E correlação alta com `VR(2)` não elimina automaticamente informação de `VR(4)`.

**4. KB-0050: previsão contínua é avaliável sem dimensionamento.**

“Só tem uso onde existe dimensionamento” e “não é falsificável em sombra” extrapolam na [KB-0050:52](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo.md:52) e [KB-0050:96](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo.md:96).

**Cenário de falha:** registrar um score durante meses e adiar toda avaliação até M4, embora já fosse possível verificar prospectivamente se ele ordena outcomes.

Um score não vinculante não altera outcomes, mas pode ter sua **capacidade preditiva** testada: associação com `R_net`, médias por faixas previamente definidas ou calibração para um evento explícito. Uma função de ER não vira probabilidade por receber o nome `confidence`. É preciso declarar alvo, horizonte e método; sizing continua sendo uma pergunta posterior.

**5. KB-0048: D-CHAN-c não é hoje uma consulta direta ao envelope descrito.**

A [KB-0048:94](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro.md:94) pede a fração com `return_4h>0` no envelope. A lista produzida pela momentum inclui `return_15m`, mas não `return_4h`; a montagem posterior acrescenta proveniência, não essa feature. [momentum_v1.py:240](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:240), [record.py:138](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:138)

**Cenário de falha:** uma consulta retorna tudo ausente e essa ausência é interpretada como indisponibilidade do M2 ou exceção à redundância.

O diagnóstico precisa de reconstrução com candles e corte explícito, ou de snapshots históricos cuja associação temporal seja comprovada. A implicação matemática continua correta quando os fechamentos estão alinhados.

**6. Fontes: corrigir atribuições que podem orientar decisões indevidas.**

| Trecho | Correção necessária |
|---|---|
| [KB-0050:23](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo.md:23), reforçado na linha 116 | Carver distingue sistemas contínuos sem stops separados de sistemas discretos nos quais usa stops. **Falha:** transformar essa distinção em argumento geral a favor de remover o nosso stop. [Texto do autor](https://qoppac.blogspot.com/2020/12/) |
| [KB-0048:16](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro.md:16) | “Pede momentum/reversão” deve virar hipótese; “a forma mais comum” precisa de evidência específica. **Falha:** converter um diagnóstico estatístico em autorização de estratégia lucrativa. A [prévia consultada](https://www.oreilly.com/library/view/algorithmic-trading-winning/9781118746912/) não fundamenta esse superlativo. |
| [KB-0049:30](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos.md:30) | A editora confirma mais de 6.400 regras e o estudo do S&P 500; o resumo público do capítulo de resultados não expõe a conclusão estatística. Marcar “quase nada sobrevive” como pendente de fonte primária específica. **Falha:** registrar resultado lembrado como diretamente verificado e usá-lo como evidência contra toda AT. [Editora](https://www.wiley-vch.de/de/fachgebiete/finanzen-wirtschaft-recht/evidence-based-technical-analysis-978-0-470-00874-4), [capítulo 9](https://onlinelibrary.wiley.com/doi/abs/10.1002/9781118268315.ch9) |

O rótulo `evidencia: estudo revisado` da KB-0049 também mistura o livro com os trabalhos estatísticos que fundamentam o método.

**NICE-TO-HAVE**

- O limite de Carver já pode sair de “memória, a confirmar”: ele publica a heurística de gastar no máximo **um terço do retorno esperado antes dos custos**, expressa também em unidades de Sharpe. Isso não significa `c=1/3 R`, pois R é risco inicial, não retorno esperado. [Carver](https://qoppac.blogspot.com/2020/04/how-fast-should-we-trade.html?m=0)
- Especificar VR: log-retornos ou diferenças, sobreposição, correção amostral e variância zero. Vinte retornos são uma amostra curta para interpretar `VR>1` como evidência.
- Reality Check não é apenas uma correção baseada na quantidade de tentativas: compara o melhor modelo com um benchmark usando a distribuição conjunta. O registro é necessário, mas não suficiente para executar o procedimento. [White, 2000](https://users.ssc.wisc.edu/~behansen/718/White2000.pdf)
- Trocar “cair no corpo da distribuição” por critério previamente definido; ausência de rejeição não demonstra equivalência.

**O QUE EU FARIA DIFERENTE**

Primeiro fecharia três diagnósticos pequenos: custo nominal versus efetivo, VR/ER com estimador explícito e sobrevivência por estado atual. Para o D-NULL, escreveria antes uma especificação de população, estatística, calendário, invalidação e censura. Só depois escolheria `K`.

Manteria a previsão contínua não vinculante, mas com uma pergunta preditiva prospectiva desde o início.

**CONCORDO COM**

**Confidence está corretamente declarado.** O padrão é `0,5`, copiado do parâmetro para a decisão e persistido; o envelope declara `constant_uncalibrated_v1`. É constante por parametrização, não uma probabilidade calibrada. Não consultei o banco para confirmar os valores das versões ativadas. [momentum_v1.py:91](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:91), [momentum_v1.py:285](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:285), [persist.py:53](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:53), [envelope.py:122](C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:122)

**D-CHAN-b é executável no escopo proposto.** Pode partir dos sinais, associar outcomes e classificar os mercados pelo `is_monitored` atual, sem filtrar previamente os excluídos. O refresh marca deslistagem por atualização; há retenção de coleta para acompanhamentos abertos; o resumo atual não filtra pelo universo presente. [universe_repo.py:106](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:106), [universe.py:209](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:209), [lab_summary.py:92](C:/dev/project-hunter/apps/api/hunter_api/repositories/lab_summary.py:92)

Essa consulta responde **“quais mercados com sinais estão fora hoje?”**. Não identifica todos que saíram e voltaram, nem prova ausência de viés anterior à coleta. Separaria outcomes encerrados, censurados e ainda abertos. Sua ressalva de que nenhuma saída observada deixa a pergunta aberta está correta.

Também concordo em não calcular uma eficiência walk-forward fictícia sem processo de otimização em amostra, preservar janela futura e distinguir pesquisa por entrada de performance de carteira. O resumo público de Pardo sustenta essa finalidade da validação fora da amostra. [Pardo, capítulo 11](https://onlinelibrary.wiley.com/doi/abs/10.1002/9781119196969.ch11)

**OBSIDIAN**

- **KB-0048 — O teste antes da regra:** corrigir VR versus ER, a execução de D-CHAN-c e delimitar a auditoria de sobrevivência.
- **KB-0049 — Walk-forward e nulo:** especificar benchmark condicionado, estatística, dependência, calendário e proveniência.
- **KB-0050 — Previsão contínua e custos:** separar custo nominal/efetivo, restaurar avaliação preditiva em sombra e qualificar Carver.
- **Strategy Backlog / Registro de Tentativas:** refletir que mudar para um teto efetivo pode mudar a população; manter diagnósticos distintos de braços.
- **Revisões da Astra:** registrar esta revisão, incluindo os contraexemplos sintéticos e os limites das fontes verificadas.