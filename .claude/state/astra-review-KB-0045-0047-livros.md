**RESUMO**

**O exemplo de 0,5 R está correto. A redundância de `return_4h > 0` também, desde que use os mesmos preços e corte temporal. Já a previsão de que o canal raramente decidiria a saída em quatro horas não está demonstrada: o raciocínio precisa ser corrigido.**

Revisei como `quant-engineer`, em modo OPINIÃO. Manteria as três ideias, corrigindo principalmente a interação canal–invalidação, a definição dos diagnósticos e as atribuições bibliográficas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Leitura estática com `Get-Content`/`rg`, consulta às fontes abertas e verificações aritméticas em PowerShell. Não executei pytest, SQL ou replay; não medi frequência real de saídas.

Saída real das contas com `Decimal`, incluindo o contraexemplo explicado abaixo:

```text
risk=4,0; gain=2,0; payoff=0,5; intervals=16
channel_min=100; next_close=99,95; channel_exit=True; invalidated=False; below_stop=False
```

**MUST-FIX**

**1. KB-0045: retirar a previsão de raridade baseada somente nas 16 barras.**

O problema está na [KB-0045:95](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao.md:95). O mínimo dos dez fechamentos pode **já estar acima do stop na entrada**; não precisa esperar uma subida para chegar lá. Além disso, há outra saída concorrente: a invalidação fixa no máximo dos vinte fechamentos anteriores, definida em [momentum_v1.py:282](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:282).

A restrição correta é esta, chamando esse máximo anterior de `B`:

- Nos primeiros nove fechamentos posteriores ao sinal, o canal ainda contém algum fechamento anterior ao rompimento, portanto seu mínimo é `≤ B`.
- Romper esse mínimo também satisfaz `close < B`: a invalidação já pediria saída.
- No décimo fechamento, a janela passa a conter apenas o fechamento do sinal e os nove seguintes. O canal pode então acrescentar uma saída própria.

As duas regras seriam observadas na mesma cadência; a invalidação atual compara o fechamento com seu nível e sai na abertura seguinte. [walker.py:136](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:136), [walker.py:77](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:77)

**Contraexemplo sintético:** `B=99,90`, referência `100`, ATR `2`, stop `97`, alvo `103`. Os nove fechamentos seguintes são `100,10 … 100,90`; o décimo é `99,95`. Nesse instante:

- canal anterior: mínimo `100`;
- `99,95 < 100`: canal dispara;
- `99,95 > 99,90`: invalidação não dispara;
- com mínimas acima de `97` e máximas abaixo de `103`, stop e alvo tampouco dispararam.

Isso acontece **150 minutos após o sinal**, dentro das quatro horas. Não prova que seja frequente; prova que a justificativa apresentada não determina a frequência.

**Cenário de falha:** rebaixar a candidata por uma suposta irrelevância estrutural que não existe. Eu escreveria: “a invalidação torna o canal redundante nos nove primeiros fechamentos; sua contribuição posterior precisa ser medida”.

**2. KB-0045: separar efeito do pacote e contribuição do canal.**

O braço proposto remove o alvo e adiciona o canal. Compará-lo apenas à base mede o **efeito conjunto**. Não identifica quanto veio de cada mudança. [KB-0045:64](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao.md:64)

Para essa atribuição, usaria três políticas sobre entradas congeladas: atual; sem alvo; sem alvo com canal. Stop, invalidação e horizonte permanecem iguais.

**Cenário de falha:** o pacote melhora porque removeu o alvo, enquanto o canal piorou o resultado; a nota atribui a melhora ao canal. Contar poucas saídas por canal também não basta para refutar seu valor: poucas saídas podem ter efeito grande.

E intervalo cobrindo zero significa **inconclusivo**, não refutação. Isso precisa mudar na [KB-0045:81](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao.md:81).

**3. KB-0046: corrigir a direção do deslocamento e distinguir preços de custos.**

A frase “os dois lados na mesma direção” está errada. [KB-0046:49](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde.md:49)

Com referência `F`, distância `a=1,5·ATR` e `δ=P_entry−F`:

```text
risco = a + δ
ganho potencial nominal = a − δ
payoff nominal = (a − δ)/(a + δ)
```

Entrada maior **aumenta o denominador e reduz o numerador**. O exemplo continua certo: `(103−101)/(101−97)=0,5`.

Também é preciso distinguir:

- `P_entry` incorpora meio spread e slippage; taxa é descontada separadamente. [pricing.py:47](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47), [pricing.py:79](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:79)
- Os **14,362/44,068 bps** registrados na KB-0041 medem **open bruto versus referência**, conforme seu SQL; não a distribuição de `P_entry−referência`. [KB-0041:67](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:67), [KB-0041:77](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio.md:77)

**Cenário de falha:** implementar o diagnóstico com o open bruto ou chamar 0,5 R de resultado líquido. A conta apresentada é o potencial nominal, antes das fricções de saída, taxas e funding.

**4. KB-0047: corrigir “20 fechamentos idênticos” para 21 e delimitar a reconstrução histórica.**

`ER(20)` usa **20 diferenças e 21 fechamentos**. O denominador é zero quando esses 21 fechamentos são iguais. [KB-0047:20](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0047-razao-de-eficiencia-de-kaufman.md:20), [KB-0047:73](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0047-razao-de-eficiencia-de-kaufman.md:73)

**Cenário de falha:** os vinte fechamentos anteriores são `100`, o atual é `101`. A ER correta é `1`; verificar apenas os vinte anteriores produziria `unavailable`. Num rompimento válido da mesma janela, denominador zero é impossível.

O diagnóstico também pede a distribuição nas barras históricas `not_triggered`. Porém, nesse caminho o worker avança o checkpoint e retorna antes de persistir um sinal; registra contadores agregados, não um histórico individual dessas avaliações. [decide.py:123](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:123), [decide.py:155](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:155)

**Cenário de falha:** preencher retrospectivamente uma lacuna com candles recuperados depois e apresentar o resultado como avaliação observada naquele instante. O próprio envelope alerta que corte por tempo de mercado não prova disponibilidade na decisão. [record.py:53](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:53)

Eu qualificaria essa população como **replay reconstruído**, sujeito à cobertura e proveniência, ou faria a coleta prospectiva.

**5. KB-0047: definir o denominador de `ΔR_net` para um filtro.**

O contraste da [KB-0047:75](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0047-razao-de-eficiencia-de-kaufman.md:75) deixa ambíguo se compara média por entrada aceita ou contribuição por oportunidade da base.

**Cenário sintético:** a base tem cem entradas com média `0,10 R`; o filtro aceita dez com média `0,20 R`. Melhorou a média por entrada aceita, mas a soma caiu de `10 R` para `2 R`. São resultados diferentes, nenhum representa automaticamente performance de carteira.

Definiria ambos e a taxa de retenção. Se o teste rodar como estratégia independente, também não presumiria entradas pareadas: o rearme depende do estado `not_triggered` e da ocupação do slot. [episodes.py:57](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:57)

**6. Fontes: substituir “o livro ensina” pelo material realmente consultado.**

**Cenário de falha comum:** uma sessão futura registra o livro como lido e trata uma adaptação nossa como regra documentada pelo autor.

| Nota | O que a fonte aberta permite afirmar |
|---|---|
| **KB-0045** | A página de Covel sustenta rompimentos 20/55 e dimensionamento por `N`/ATR. Ela não documenta ali todo o pacote numérico de saídas. Os itens “de memória” devem continuar separados, **incluindo a ausência de alvo fixo**, enquanto não houver referência específica verificada. Schwager não deve aparecer como fonte diretamente consultada. [Página de Covel](https://www.turtletrader.com/rules/) |
| **KB-0046** | O PDF **abriu nesta revisão** e sustenta risco inicial, R-múltiplos, expectancy e importância do sizing. É material do instituto sobre seu simulador, não prova de leitura de *Trade Your Way to Financial Freedom*. A oposição absoluta “não é a entrada, é o sizing” deve virar uma atribuição qualificada; o próprio texto reconhece o papel do sistema de entrada/saída. [PDF do instituto](https://vantharp.com/wp-content/uploads/2018/06/A_Short_Lesson_on_R_and_R-multiple.pdf) |
| **KB-0047** | Há fonte melhor: **artigo do próprio Kaufman**, com fórmula, distinção ruído/volatilidade e comparação ilustrativa de mercados e resultados de tendência. Sustenta a inspiração, mas não valida `ER(20)` como filtro intradiário nosso. Atribuir isso ao artigo evita fingir leitura do livro. [Artigo de Kaufman](https://kaufmansignals.com/matching-the-markets-to-the-strategy/) |

*Expectunity* também tem definição aberta no [glossário do Van Tharp Institute](https://vantharpinstitute.com/glossary/).

Não identifiquei reprodução extensa nas notas. O problema principal é **rastreabilidade da atribuição**, não necessidade de remover fórmulas ou sínteses próprias.

**NICE-TO-HAVE**

- Trocar “nosso R nominal não é 1” por **“o payoff nominal no alvo não é necessariamente 1 R”**. Uma unidade de risco continua sendo 1 R.
- Retirar a alegação de descoberta inédita: o contrato já contém o mesmo exemplo `100/97/103/101 → 0,5 R`. [SHADOW-LAB.md:13](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:13)
- Na KB-0045, trocar “censura por horizonte” por **expiração por horizonte**: o walker produz `EXPIRED`; censura é outro estado. [walker.py:75](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:75), [progress.py:136](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/progress.py:136)
- Trocar “nunca acompanhados” por **“não usados como barreiras pelo acompanhamento atual”**. Isso delimita a afirmação ao código examinado, sem alegar toda a história do projeto.
- Registrar a presente ressalva na segunda opinião: minha revisão anterior priorizou invalidação, mas não demonstrou raridade do canal. [.claude/state/astra-review-KB-rodada6-curadoria-livros.md:3](C:/dev/project-hunter/.claude/state/astra-review-KB-rodada6-curadoria-livros.md:3)

**O QUE EU FARIA DIFERENTE**

| Nota | O que retiraria |
|---|---|
| **KB-0045** | “Metade do sistema já está rodando”, a previsão de raridade sem medição e a causalidade “o resultado vem de…” sem decomposição empírica. Manteria semelhança da entrada, diferenças e teste das saídas concorrentes. |
| **KB-0046** | A novidade “ninguém tinha escrito”, a exclusividade do sizing e “três vezes por ano não paga o aluguel”. Manteria a fórmula do payoff e o diagnóstico com preços claramente definidos. |
| **KB-0047** | “Não diz nada sobre o caminho” — o rompimento impõe restrições, embora não determine a ER — e “um caminho retilíneo já andou tudo”, que presume exaustão. Manteria exaustão como risco hipotético. |

Minha sequência seria diagnóstico de payoff, diagnóstico de ER com proveniência explícita e comparação das saídas sobre entradas congeladas. Mediria contribuição incremental antes de mudar a prioridade por expectativa narrativa.

**CONCORDO COM**

A conferência dos pontos de código ficou assim:

| Afirmação | Resultado |
|---|---|
| `risk = entry − stop` | **Exata**, em [pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74). |
| Canal de vinte fechamentos anteriores | **Correta**: fatia exclui o atual; condição exige superá-la. [indicators.py:147](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:147), [momentum_v1.py:180](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:180). |
| Parâmetros 15m, ATR14/97, stop/alvo 1,5, alvos 3/4,5, filtros e horizonte | **Corretos nos padrões**. [momentum_v1.py:74](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:74). Os níveis partem da referência. [momentum_v1.py:217](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:217). |
| Alvos 2/3 persistidos, sem acompanhamento próprio | **Correta no fluxo atual**: grava todos em sinais/outcomes, reconstrói somente o primeiro como barreira. [persist.py:59](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:59), [persist.py:79](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:79), [tracking_repo.py:102](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/tracking_repo.py:102). |
| Dezesseis barras em quatro horas | **Correta como duração equivalente e até 16 fechamentos de avaliação**. Não são necessariamente 16 candles UTC inteiramente posteriores à entrada, pois ela ocorre numa abertura de 1m posterior à decisão. Horizonte começa nessa entrada. [plan.py:48](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/plan.py:48), [progress.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/progress.py:74). |
| Rompimento implica `return_4h > 0` | **Correta com preços positivos e mesmo corte**: `Cₜ₋₁₆` pertence aos vinte anteriores, logo `Cₜ > Cₜ₋₁₆` e `Cₜ/Cₜ₋₁₆−1 > 0`. [indicators.py:150](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:150). Uma feature atrasada ou `_live` não satisfaz automaticamente essa equivalência. [price.py:38](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/price.py:38). |

Concordo também que a ER acrescenta uma descrição da trajetória que o rompimento não determina, que 3 ATR não significa 3 R e que nenhuma dessas fontes valida diretamente a adaptação para cripto em 15 minutos.

**OBSIDIAN**

- **KB-0045 — Os Turtles:** corrigir a concorrência com invalidação e separar efeito de remover alvo do efeito do canal.
- **KB-0046 — R-múltiplos:** corrigir os sinais algébricos, distinguir open/P_entry e substituir alegação de novidade.
- **KB-0047 — Razão de eficiência:** corrigir 21 fechamentos, proveniência de `not_triggered` e denominadores do teste.
- **Strategy Backlog / Registro de Tentativas:** refletir protocolos corrigidos, sem apresentar raridade ou vantagem como resultados medidos.
- **Revisões da Astra — rodada 6:** registrar esta revisão e a ressalva ao argumento de raridade atribuído à priorização anterior.