**RESUMO**

Concordo com testar **10/20/40 simultaneamente**, como família pré-registrada. Corrigiria a refutação: **diferença não significativa é inconclusão; não demonstra que o parâmetro seja irrelevante.**

**ARQUIVOS**

Nenhum criado ou modificado. Parecer como `quant-engineer`, em modo OPINIÃO.

**TESTES**

Não executados; análise documental, leitura do código e consulta às fontes.

**MUST-FIX**

1. **Dependência entre variantes:** compartilhar mercados e minutos favorece a comparação pareada. O erro seria tratar os resultados como três amostras independentes: um único movimento generalizado poderia parecer dezenas de confirmações. Preserve essa dependência na inferência.

2. **Reentrada:** use **três `strategy_version_id` distintos**, todos em `cohort=prospective`, conforme o [contrato de versionamento](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:11). O estado é isolado pela tripla versão/mercado/coorte em [slots.py:95](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/slots.py:95). Mudar apenas parâmetros sob a mesma tripla faria uma variante bloquear outra.

   Com versões distintas, não há contaminação desse estado. Entretanto, cada janela altera quando a condição fica falsa e, portanto, o próprio rearme — [episodes.py:57](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:57). Você compara **três políticas completas de entrada/reentrada**. Seus trades não serão necessariamente pareáveis um a um.

3. **“Dispersão da ordem do erro”:** proponho expectancy líquida em R por entrada como métrica primária. Reamostre **blocos temporais comuns às três variantes, carregando todos os mercados juntos**; em cada réplica, recalcule `ΣR/n` e os três contrastes pareados. Agrupe pela data de entrada, espere maturação do horizonte e reporte censura separadamente. Blocos devem acomodar a dependência temporal; 4 h de holding não garantem independência após 4 h.

   Construa **ICs simultâneos de 95%**, por bootstrap max‑t, para as três diferenças. Métodos conjuntos permitem considerar a dependência e controlar multiplicidade. [Romano–Wolf](https://doi.org/10.1111/j.1468-0262.2005.00615.x).

   Pré-registre uma margem economicamente relevante `δ`:

   - Todos os ICs dentro de `[-δ,+δ]`: equivalência prática nessa população.
   - Algum IC inteiramente além de `±δ`: diferença relevante sustentada.
   - Demais casos: inconclusivo.

   **Cenário de falha da refutação original:** poucos dias geram ICs largos; concluir “parâmetro irrelevante” descartaria diferenças que a amostra simplesmente não consegue resolver.

**NICE-TO-HAVE**

Reporte frequência de entradas, sobreposição, tempo acompanhado e exclusões por variante. Expectancy maior com pouquíssimas oportunidades não responde, sozinha, qual política é mais útil.

**O QUE EU FARIA DIFERENTE**

- Chamaria de **família pré-especificada**: 10/20/40 ainda são escolhas experimentais, não comprimentos medidos pelo mercado.
- Fixaria início comum, regra de encerramento e confirmação futura; registraria todas as tentativas que influenciaram a seleção, inclusive mudanças posteriores.
- Usaria expectancy com inferência ajustada, evitando “expectancy deflacionada” sem definição. Sharpe exige uma série de retornos e convenção de capital; o Lab declara não possuir carteira em [SHADOW-LAB.md:5](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:5).
- Nomearia precisamente **rompimento de fechamentos**, como implementado em [momentum_v1.py:167](/C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:167).
- Acrescentaria à nota bibliográfica que Hudson–Urquhart encontraram desempenho negativo fora da amostra para os dois mercados de Bitcoin na avaliação das regras vencedoras. A significância corrigida citada não equivale a validação prospectiva universal. [Artigo, §5](https://link.springer.com/article/10.1007/s10479-019-03357-1).

**CONCORDO COM**

Publicar a família inteira, preservar os resultados desfavoráveis e não escolher vencedor quando a evidência for inconclusiva.

**OBSIDIAN**

- **Nota “Rompimento de canal e data snooping” — proposta:** registrar comparação dependente, multiplicidade e equivalência prática.
- **Strategy Backlog:** acrescentar a candidata 10/20/40, ainda sem ativação.
- **Strategy Performance:** documentar bootstrap conjunto, margem `δ` e os três resultados possíveis.