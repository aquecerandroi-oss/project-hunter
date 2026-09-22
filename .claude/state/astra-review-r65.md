**RESUMO**

**Eu recomendaria recuperar o rent; não mudaria o gate nem o `creator_dump` com esta evidência.** `buys_1m≤25` merece teste prospectivo em sombra. A análise é exploratória útil, mas há erros de apresentação e limitações concretas na reconstrução.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `quant-engineer`, em modo OPINIÃO.

**TESTES**

Conferências somente de leitura com `Import-Csv`, `ConvertFrom-Json` e somas em `Decimal`:

```text
87 operações; 76 mints
Mediana buys_1m: 27 nas 87; 26 nas 69 alvo/trailing
buys≤25: PnL real −0,041895684; com rent +0,014090996 SOL
Diferença não reconciliada: 0,002860040 SOL, em TAXCOIN
72 operações com parâmetros 0,07 / 1,15× / 300 s / trailing 10%
```

Não executei os scripts geradores nem testes da aplicação.

**MUST-FIX**

**A) Método: honesto como exploração, insuficiente como confirmação.** O bootstrap e a permutação tratam operações como independentes ([stats.py:43](C:/dev/project-hunter/.claude/state/r65/stats.py:43)). É necessário considerar dependência por mint e regime temporal: reamostrar mints inteiros e apresentar sensibilidade por dia, inclusive retirando um dia de cada vez. Com apenas seis dias, a inferência temporal continua frágil. Dependência positiva geralmente **reduz artificialmente o p e estreita o IC** quando ignorada; a direção não é garantida para estes contrastes.

O BH cobre 13 contrastes **em cada análise**, não toda a busca entre duas populações, Spearman, cortes e combinações ([stats.py:175](C:/dev/project-hunter/.claude/state/r65/stats.py:175), [stats.py:193](C:/dev/project-hunter/.claude/state/r65/stats.py:193)). Além disso, o teste compara **PnL**, não diretamente a probabilidade alvo/trailing. Selecionar somente esses dois desfechos condiciona a análise ao resultado. Cenário de falha: descobrir um filtro “bom” excluindo justamente os `creator_dump` que ele admitiria.

**B) Só rent agora; gate em sombra.** Ausência de significância não prova ausência de efeito, mas não sustenta promoção para dinheiro real.

Os oito flips também **não provam domínio do timing**: Cupsey muda de 18 para 36 compras/min e NARKY de 20 para 92, com mudanças grandes de idade e progresso ([metrics.txt:24](C:/dev/project-hunter/.claude/state/r65/metrics.txt:24), [metrics.txt:27](C:/dev/project-hunter/.claude/state/r65/metrics.txt:27)). Existem pares semelhantes; não são oito controles equivalentes.

Mais grave: **as 87 não representam uma única regra atual**. Há parâmetros históricos diferentes, e o contrafactual apenas filtra posições e reaproveita seu PnL realizado, sem ressimular saídas ([cf.py:42](C:/dev/project-hunter/.claude/state/r65/cf.py:42)). Cenário: atribuir ao gate atual um lucro produzido sob alvo 3× e horizonte 1.800 s.

**C) Não existe desconto percentual defensável.** Eu atribuiria **zero crédito de lucro esperado para decisão real**, sem afirmar que a expectativa verdadeira seja zero.

Apresentaria assim:

> “Filtro escolhido retrospectivamente: 41 operações perderam 0,04190 SOL realizados; supondo restituição integral do rent, o saldo seria +0,01409 SOL. Não é estimativa validada de lucro futuro.”

O corte 25 não é a mediana das 87. E “4/5 dias verdes” significa **quatro positivos, um negativo e um sem operação**, dentro dos seis dias ([cf.txt:9](C:/dev/project-hunter/.claude/state/r65/cf.txt:9)). O IC comum após escolher o vencedor não incorpora o viés dessa seleção.

**D) Nenhuma das duas conclusões causais.** `0/14` permite dizer apenas: **o indicador não sinalizava vendedor líquido na entrada**. Não absolve a entrada nem condena a saída.

O “segurar” calcula uma marca aos 300 s; não reproduz alvo, trailing e demais proteções ([cf.py:91](C:/dev/project-hunter/.claude/state/r65/cf.py:91)). PlanB saiu aos 514 s: nesse caso, 300 s é **antes** do gatilho ([cf.txt:27](C:/dev/project-hunter/.claude/state/r65/cf.txt:27)). Portanto, −0,0174 SOL não estima o efeito de simplesmente remover `creator_dump`.

**E) Há quatro armadilhas materiais:**

- **Ordem intrasslot:** assinatura não representa ordem de execução; trades posteriores à compra no mesmo slot são descartados. Isso pode mudar pico e primeiro toque de trailing ([load.py:147](C:/dev/project-hunter/.claude/state/r65/load.py:147), [load.py:168](C:/dev/project-hunter/.claude/state/r65/load.py:168)).
- **Contrafactual inconsistente:** exclui nossos trades, mas ressincroniza com fotos que incorporam nossas vendas reais. A trajetória “sem vender” passa a conter o efeito da venda ([load.py:168](C:/dev/project-hunter/.claude/state/r65/load.py:168), [load.py:198](C:/dev/project-hunter/.claude/state/r65/load.py:198)).
- **Marca velha vira “300 s”:** não há exigência de cobertura/frescor no horizonte. Uma moeda sem observações após desaparecer pode conservar uma marca favorável ([load.py:228](C:/dev/project-hunter/.claude/state/r65/load.py:228)).
- **Fotos não mostram a sequência dos toques.** Separar as 13 operações e testar sensibilidade é obrigatório. MFE futuro pode ser desfecho legítimo; usá-lo para selecionar retrospectivamente entradas não é validação prospectiva.

Também falta reconciliar **0,002860040 SOL** de TAXCOIN antes de chamar a decomposição de completa ([metrics.txt:101](C:/dev/project-hunter/.claude/state/r65/metrics.txt:101)).

**NICE-TO-HAVE**

Corrigir a economia do rent: 0,00130445/0,07 equivale a **1,86%**, não 1,3%. Rent recuperável é depósito imobilizado; fechar devolve lamports, mas o líquido depende das contas elegíveis e das taxas. Não prometer recuperação integral sem inventário. [Documentação Solana](https://solana.com/docs/tokens/basics).

**O QUE EU FARIA DIFERENTE**

Congelaria `≤25` como hipótese única, com controle simultâneo e parâmetros iguais. Percentil móvel seria outra estratégia. Três dias servem como triagem; passar sua regra não valida o gate. Usaria PnL líquido como desfecho principal, MFE como secundário, e admitiria resultado **inconclusivo**.

**CONCORDO COM**

Priorizar rent, divulgar o BH negativo e manter cautela com os três grandes vencedores do contrafactual. `p=0,64` significa ausência de diferença detectável entre mesas, não equivalência comprovada.

**OBSIDIAN**

- **Revisões Astra — R65:** registrar correções numéricas, mistura de parâmetros e limitações do replay.
- **Mesa `operator/6`:** separar comparação histórica de teste prospectivo do novo gate.
- **Meme — estratégias:** registrar `buys_1m≤25` como hipótese exploratória, sem promoção para dinheiro real.