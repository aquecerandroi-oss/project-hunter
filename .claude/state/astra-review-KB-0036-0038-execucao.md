**RESUMO**

As três notas têm diagnósticos úteis, mas **não aprovaria os textos como estão**. A KB-0036 extrapola a comparação para um critério de validação; a KB-0037 contém erros aritméticos e inferências não demonstradas; a KB-0038 tem a aritmética correta, mas precisa restringir as afirmações sobre tarifas e execução.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, no escopo de `quant-engineer`.

**TESTES**

Não executei suítes, SQL nem a coleta de livros. Conferi código, evidências coladas e a FAQ externa. Cálculos executados em PowerShell com `[decimal]`, usando `total = 12 + 2×fee` e `R = 51`:

```text
fee=4; fee_rt=8; total_rt=20; cost_R=0,39215686; delta_R=0,00000000
fee=4,5; fee_rt=9,0; total_rt=21,0; cost_R=0,41176471; delta_R=0,01960784
fee=5; fee_rt=10; total_rt=22; cost_R=0,43137255; delta_R=0,03921569
spread_delta_rt=0,3; spread_delta_per_side=0,15
p90_example_spread=5.9; delta_rt=3,9
book_missing_partitions=69,69; stated=68
```

**MUST-FIX**

**KB-0036 — O tamanho que a sombra nunca declara**

1. **Afirmações e evidência:** as contagens são incompatíveis. O agregado tem **68** livros insuficientes para 20 mil; os estratos somam **28+41=69** e **5+64=69**, embora sejam apresentados como a mesma amostra. Além disso, o trecho de script não contém coleta, filtros, quantis nem estratificação: não reproduz as tabelas. Corrigir a proveniência antes de rotular como “replicado”. **Cenário:** usar esses estratos para justificar um tamanho mistura populações ou instantes diferentes. [Tabela agregada:48](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:48), [estratos:55](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:55), [script:70](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:70).

2. **Comparabilidade:** você já declarou corretamente **mid versus negócio** e **snapshot versus fill**. O problema adicional é usar essa medição para concluir que “a hipótese de 6 bps está adequada”: o teste mede o **ask na decisão**, enquanto a entrada ocorre numa abertura posterior; tampouco mede o **bid na saída**. Os quantis ainda são condicionais aos livros que comportam o tamanho. **Cenário:** mediana e p90 dos casos completos passam, mas muitos sinais não cabem no livro ou enfrentam saída cara; o diagnóstico arquiva a dúvida indevidamente. Restringir o veredito ao custo estático observado e exigir cobertura explícita. [Critério:93](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:93), [refutação:107](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:107), [plan.py:94](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:94).

3. **Aritmética:** o núcleo do walk calcula corretamente `notional gasto / quantidade preenchida`. Os arredondamentos das medianas estão corretos; **68/200=34%** também. Mas “acima de 5 mil, mais da metade não cabe” contradiz a própria linha de 20 mil, com 34%. [Walk:72](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:72), [justificativa da grade:137](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:137).

4. **Recalibração:** **não propõe recalibrar na amostra descoberta**; a proibição está explícita. Acrescentar tamanho é uma proposta de contrato, não evidência de que o custo foi validado. [Nota:109](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:109).

5. **Cortaria inteiramente:** “o único parâmetro que decide se está certa”, a generalização de execução no toque para o top 20 e a justificativa falsa de censura acima de 5 mil. Tamanho importa, mas instante, lado e política de execução também; custo baixo não prova preenchimento inteiro no melhor nível. [Nota:26](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:26), [nota:61](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md:61).

**KB-0037 — O spread assumido contra o spread medido**

1. **Afirmações e evidência:** “monotônico” é falso: **3,245 → 3,265 → 3,780** e **2,390 → 3,390** são reversões. “Quase toda a dispersão é entre mercados” exige uma decomposição que a tabela não apresenta. E medianas menores nos mercados que sinalizaram não demonstram que o filtro de volume relativo **causou** isso, nem descrevem os instantes dos sinais. **Cenário:** adotar custo por decil acreditando que ele explica quase toda a variação ignora alargamentos dentro do mesmo mercado. [Conclusão:19](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:19), [tabela:73](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:73), [causalidade:94](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:94).

   Há também uma lacuna de reprodução: nenhum SQL colado delimita a janela temporal; a saída por decil contém `min_bps` e `max_bps` ausentes do `SELECT`; faltam consultas para os **535 minutos** e **8/200 sinais**. Isso não prova que os números sejam falsos, mas impede auditá-los como apresentados. **Cenário:** executar amanhã o mesmo SQL altera a população que continua identificada como aquela janela. [SQL:35](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:35), [SQL por decil:63](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:63), [cobertura:107](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:107).

2. **Comparabilidade:** não aparece um novo erro específico de VWAP. Porém, spread cotado **na decisão** não determina spread pago na entrada e na saída. O `EXEC-B` mede contexto; sozinho não mede erro realizado de ida e volta. [Proposta:121](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:121).

3. **Aritmética — dois reparos obrigatórios:**
   - **2 → 2,3 bps significa aproximadamente +0,30 bps por ida e volta**, ou +0,15 por lado. A linha 137 está errada; a seção de segunda opinião traz o valor correto. [Nota:135](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:135).
   - **p90 abaixo de 6 não garante erro máximo de 2 bps por ida e volta.** Duas pernas com spread de 5,9 custam aproximadamente **3,9 bps adicionais**, frente à hipótese de 2. Além disso, p90 não limita os 10% restantes. **Cenário:** o diagnóstico aprova uma distribuição que viola o orçamento declarado de 10% do custo total. [Critério:129](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:129).

4. **Recalibração:** **não**, a troca retrospectiva de 2 para 2,3 é explicitamente recusada. Mas “obrigaria a tratar como variável por mercado” também extrapola: p90 elevado pode decorrer de horários ou regimes, não necessariamente de diferenças persistentes entre mercados. [Nota:131](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0037-o-spread-assumido-contra-o-spread-medido.md:131).

5. **Cortaria inteiramente:** “quase toda”, “monotônico”, “isso não é sorte” e a garantia de erro máximo. Manteria a conclusão mais estreita: **a diferença entre as medianas tem pequena escala dentro do custo assumido**.

**KB-0038 — A taxa de 4 bps não é nem maker nem taker**

1. **Afirmações e evidência:** a FAQ confirma os exemplos de **2/5 bps** e o desconto de **10% em BNB**, mas declara que as tarifas dos exemplos são hipotéticas. Portanto, o título é amplo demais: **4 bps não corresponde aos exemplos escolhidos**, não necessariamente a nenhum perfil maker/taker. “Favorece a estratégia” vale **contra os cenários de 4,5/5**, não contra uma tarifa efetiva desconhecida. **Cenário:** transformar a comparação em correção obrigatória para uma conta cuja tarifa aplicável seja diferente. [Nota:16](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker.md:16), [FAQ oficial](https://www.binance.com/en/support/faq/detail/360033544231).

   “Inequivocamente taker nos dois lados” também excede o modelo: aplicar deslocamento adverso ao OHLC não identifica uma ordem nem sua condição maker/taker. **Cenário:** tratar o alvo sintético como execução taker comprovada para atribuir tarifa. Melhor: “cenário de execução agressiva, sem modelagem de fila maker”. [Nota:21](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker.md:21), [pricing.py:47](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47).

2. **Comparabilidade:** nenhuma comparação adicional de VWAP versus mid; o excesso aqui é inferir **tipo de execução** a partir do preço sintético.

3. **Aritmética:** **correta como aproximação com denominador fixo de 51 bps**: 39,22%, 41,18%, 43,14%; aumentos de **0,01961 R** e **0,03922 R**. Explicitar o exemplo sem gap: 51 bps não é o denominador de todo trade no piso. Para cada outcome, a mudança exata é:
   `ΔR = −Δfee × (E + X)/(E − S)`.
   É a cobrança implementada em [pricing.py:74](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74), aplicada à [tabela:51](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker.md:51).

4. **Recalibração:** **não**. O `EXEC-C` é sensibilidade legítima sobre população fixa. Isso continua válido enquanto não se escolhe a coluna favorável como resultado principal. [Proposta:65](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker.md:65).

5. **Cortaria inteiramente:** a comparação causal com “14 bps de mediana absoluta”. Movimento absoluto não informa se ajudou ou prejudicou o long; tampouco pode ser comparado diretamente com expectancy média em R. Basta o argumento exato: **aumentar somente a taxa reduz cada R, logo não elimina um resultado já negativo**. [Nota:88](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker.md:88).

**NICE-TO-HAVE**

Trocar “meia-corretagem do spread” por **meio spread**. Acrescentar carimbos UTC, método de quantil e denominadores completos. Revisar os resumos de “Segunda opinião”: algumas correções declaradas ainda contradizem o corpo das notas.

**O QUE EU FARIA DIFERENTE**

Manteria as três notas, com conclusões menores: custo estático por tamanho; distribuição do spread cotado; sensibilidade determinística às taxas. Os critérios de validação precisam medir exatamente o objeto que pretendem aprovar.

**CONCORDO COM**

Declarar tamanho, medir prospectivamente, preservar hipóteses congeladas e publicar sensibilidade com a coluna primária identificada. Nenhuma das três propõe diretamente recalibrar os parâmetros usando a amostra descoberta.

**OBSIDIAN**

- **O tamanho que a sombra nunca declara** — reconciliar amostras, completar reprodução e restringir o critério de adequação.
- **O spread assumido contra o spread medido** — corrigir 0,30 bps, remover a garantia do p90 e as inferências não demonstradas.
- **A taxa de 4 bps não é nem maker nem taker** — restringir título e viés aos cenários comparados; explicitar o denominador.
- **Revisões da Astra** — registrar esta revisão e substituir a concordância irrestrita por pendências concretas.