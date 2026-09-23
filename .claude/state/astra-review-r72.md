## RESUMO

**Não aprovaria ainda o R72 para confirmar ou refutar H-009.** Usar reservas posteriores ao gatilho para executar uma ordem com latência **não é, por si só, antecipação**. Porém, encontrei problemas no relógio de execução, na ordenação da reconstrução, nos custos e no braço de comparação que precisam ser corrigidos antes do veredito.

Revisão como `quant-engineer`, em modo OPINIÃO. Não alterei arquivos.

## ARQUIVOS

Principais revisados:

- [sim.py](C:/dev/project-hunter/.claude/state/r72/sim.py:1): 205 linhas.
- [swings.py](C:/dev/project-hunter/.claude/state/r72/swings.py:1): 78 linhas.
- [load.py](C:/dev/project-hunter/.claude/state/r72/load.py:1): 269 linhas.

Também conferi o carregador R64, o pré-registro H-009, a decomposição R65 e a origem de `sol_spent_lamports` no executor.

## TESTES

Executei verificações **em memória**, com dados sintéticos e leitura agregada dos CSVs locais:

```text
@'<script via stdin>'@ | uv run --no-sync --offline python -B -
```

Saídas relevantes, com código de saída 0:

```text
REAL aggregate only: n= 89 sources= {'tape+photos': 76, 'photos': 13}
eligible= 76 upper_median_gap= 45.0
REAL eligible gaps>30: 44

REAL current params:
{('3', '0.35', 1800): 13,
 ('1.3', '0.2', 300): 2,
 ('1.15', '0.1', 300): 74}

SYNTHETIC time_stop trigger_seconds= [200.0]
final= 9790 actual_asof301_net= 979

SYNTHETIC deadline sale trigger10 fill11.6 dip40.5:
rebuys= 0 abandoned= True

REAL slot-order timestamp regressions within300:
55 positions affected= 32

exact simplified effective cycle cost= 0.0221756775
```

São reproduções pontuais, **não uma suíte pytest nem uma reavaliação estatística das 12 células**. Não executei lint/typecheck.

## MUST-FIX

**1. Separar horário das reservas, horário do fill e fechamento aos 300 s.**

**1(a):** `_fill_index` é conceitualmente correto se a ordem é irrevogavelmente decidida em `t`, executada em `t+1,6`, e as reservas usadas são o último estado conhecido da cadeia até esse instante. Consultar o futuro para determinar **o resultado da execução** é permitido; usá-lo para escolher **a decisão anterior** não é. O problema está em tratar `points[j][0]` como horário da execução. [sim.py:62](C:/dev/project-hunter/.claude/state/r72/sim.py:62)

O prazo de recompra começa no timestamp desse ponto, que pode anteceder o fill real em até 1,6 s. **Cenário reproduzido:** venda disparada em 10 s, execução em 11,6 s, nenhum negócio intermediário; queda em 40,5 s. Ela está dentro dos 30 s após a execução, mas o simulador abandona. Isso **prejudica** o giro. [sim.py:114](C:/dev/project-hunter/.claude/state/r72/sim.py:114), [sim.py:121](C:/dev/project-hunter/.claude/state/r72/sim.py:121)

Mais grave: ambos os braços liquidam no **último ponto da janela**, em vez de disparar um evento temporal aos 300 s. Além disso, o corte da fita em 300 s impede observar o pouso posterior. **Cenário reproduzido:** último ponto em 200 s; drenagem em 301 s. O simulador vende pelo estado dos 200 s e recebe 9.790 lamports; uma venda aos 300 s com pouso aos 301,6 s receberia 979 no exemplo. [sim.py:139](C:/dev/project-hunter/.claude/state/r72/sim.py:139), [sim.py:179](C:/dev/project-hunter/.claude/state/r72/sim.py:179), [load.py:220](C:/dev/project-hunter/.claude/state/r72/load.py:220)

**Correção:** relógio explícito de execução; gatilhos até 300 s, fita disponível até o último fill; ausência de cobertura produz censura, não liquidação retroativa.

**2. A reconstrução mistura ordem da cadeia com horário de observação e depois reordena estados prontos.**

As reservas são reconstruídas por `slot`, usando fotos com `observed_at`; depois os estados resultantes são ordenados por timestamp. Isso pode recolocar uma foto antiga **depois** de um estado mais avançado da cadeia. [load.py:190](C:/dev/project-hunter/.claude/state/r72/load.py:190), [load.py:207](C:/dev/project-hunter/.claude/state/r72/load.py:207), [load.py:215](C:/dev/project-hunter/.claude/state/r72/load.py:215)

**Cenário reproduzido:** foto do slot 101 observada em 10 s; trade do slot 102 em 2 s. O resultado foi:

```text
(segundo, reserva SOL, reserva tokens)
(0, 1000000, 1000000)
(2, 2100000, 450000)
(10, 2000000, 500000)
```

Em 10 s, o caminho volta ao estado do slot 101, fabricando uma queda posterior ao trade. Além disso, o estado reconstruído em 2 s depende de uma foto só observada em 10 s: ele pode servir à reconstrução retrospectiva da cadeia, mas **não prova disponibilidade da informação para a decisão em 2 s**.

Encontrei 55 regressões de timestamps na sequência ordenada por slot, envolvendo 32 posições dentro da janela. Isso não prova 55 decisões erradas, mas demonstra que o conflito existe nos dados.

**Correção:** preservar separadamente ordem da cadeia e disponibilidade da observação; fotos atrasadas não podem fazer a trajetória voltar de slot nem corrigir retroativamente informações acessíveis à política.

**3. Há subcotação nas novas pernas e duplicação na entrada.**

**Pergunta 2 — marca versus transação:** não há dupla cobrança dos 1,25% da marca na venda simulada: `_leg_sell` recalcula o produto **bruto**, depois desconta `c/2`. Entretanto, com `c=2,23%`, a venda paga somente **1,115%**, abaixo dos próprios 1,25% assumidos pelo estudo, antes de rede. A recompra também usa 1,115%. [load.py:51](C:/dev/project-hunter/.claude/state/r72/load.py:51), [sim.py:71](C:/dev/project-hunter/.claude/state/r72/sim.py:71)

**Cenário:** produto bruto de 1 SOL. O simulador entrega 0,98885 SOL; a taxa declarada de curva permite 0,9875 SOL antes da rede. São **0,00135 SOL a mais por venda**, favorecendo giros.

Os 2,23% do R65 são custo histórico agregado dividido pelo tamanho de referência; não são automaticamente duas alíquotas contratuais iguais sobre cada novo notional. A própria decomposição distingue curva, criador e rede. [KB-0147:20](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista.md:20>)

Na entrada ocorre o oposto: `spent` vem de `sol_spent_lamports`, persistido como `fill.buy_total_lamports`, que já inclui taxas e, quando conhecido, rent. `per_sol` subtrai esse total **e acrescenta outra taxa de entrada**. [load.py:114](C:/dev/project-hunter/.claude/state/r72/load.py:114), [entries.py:309](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/entries.py:309), [fills.py:58](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/fills.py:58), [sim.py:195](C:/dev/project-hunter/.claude/state/r72/sim.py:195)

**Cenário:** uma compra com taxa já debitada recebe novo desconto de 1,115% ao calcular PnL. Isso piora artificialmente o resultado absoluto. O desconto adicional comum **cancela na diferença pareada** entre os braços, mas não torna a contabilidade correta. O rent também precisa de tratamento explícito para sustentar a premissa “sem aluguel”.

**Sobre o equilíbrio analítico:** concordo com

\[
q'/q=\frac{1-c}{1-X},\qquad X>c
\]

**somente** se `c` representa perda multiplicativa efetiva do ciclo, `X` é queda do preço executável e ignoramos impacto/taxas fixas.

Com duas pernas de `c/2`, a expressão simplificada exata é:

\[
q'/q=\frac{(1-c/2)^2}{1-X},\qquad
X>c-\frac{c^2}{4}.
\]

Para `c=2,23%`, o limiar é **2,21756775%**. No simulador, porém, `X` mede queda da liquidação de um lote finito e as compras/vendas usam curvas não lineares: essa fórmula é aproximação, não identidade do código. [sim.py:50](C:/dev/project-hunter/.claude/state/r72/sim.py:50), [sim.py:120](C:/dev/project-hunter/.claude/state/r72/sim.py:120)

**4. Fixar o comparador declarado.**

`simulate_current` usa `P["target_x"]` e `P["trailing"]` por padrão. Nos dados, 13 posições carregam 3×/35% e duas carregam 1,3×/20%. O horizonte, entretanto, continua 300 s: forma-se um comparador híbrido entre parâmetros históricos e janela atual. [sim.py:155](C:/dev/project-hunter/.claude/state/r72/sim.py:155), [sim.py:163](C:/dev/project-hunter/.claude/state/r72/sim.py:163)

**Cenário:** uma posição antiga alcança 1,16× e depois cai. A regra declarada de 1,15× sairia por alvo; a chamada padrão espera 3×. A vantagem atribuída ao giro passa a depender do comparador errado.

Passar explicitamente `target_x=Decimal("1.15")`, `trailing=Decimal("0.10")` e `seconds=300` resolve essa parte.

**5. Não chamar cobertura insuficiente de “resolvida”, nem usá-la para refutação por falta de giros.**

`resolvable` exige apenas alguma fita e três pontos na janela; não exige continuidade, nem usa seu argumento `seconds`. `source` considera trades de todo o caminho, inclusive posteriores à janela. [load.py:175](C:/dev/project-hunter/.claude/state/r72/load.py:175), [load.py:241](C:/dev/project-hunter/.claude/state/r72/load.py:241)

**Cenário:** três fotos nos primeiros cinco minutos e um único trade posterior bastam para classificar o caminho como resolvível. Uma queda e recuperação inteiras dentro de um intervalo sem observações desaparecem, permitindo uma falsa refutação pelo critério “mediana < 2”.

**Pergunta 5:** 45 s de maior intervalo mediano **não invalida automaticamente todo evento de N=30 s**. Ausência de trades pode ser inatividade verdadeira. Mas, sem prova de completude, também pode ser perda de coleta. Os dados atuais não permitem tratar esses casos como equivalentes.

Eu declararia:

> “Das 89 posições, 13 foram excluídas por terem apenas fotos. Nas 76 restantes, 44 apresentaram algum intervalo sem pontos superior a 30 s; a mediana superior do maior intervalo foi 45 s. Presença de fita não comprova continuidade. As células N=30 s são exploratórias; ausência de oscilação nos trechos sem cobertura comprovada não constitui evidência de ausência nem sustenta, isoladamente, a refutação de H-009.”

O mesmo cuidado vale para N=60/120 conforme os intervalos individuais.

## NICE-TO-HAVE

- **1(b), salto `i=j+1`: correto sob uma ordem pendente irrevogável.** Os pontos pulados determinam o fill, mas não devem disparar outra operação enquanto a anterior está pendente. Se a política pretende cancelar ordens ou manter proteções ativas durante a pendência, falta modelar isso. Não é antecipação inerente ao salto. [sim.py:112](C:/dev/project-hunter/.claude/state/r72/sim.py:112), [sim.py:126](C:/dev/project-hunter/.claude/state/r72/sim.py:126)

- **1(c), `drain`: não contamina as decisões atuais.** É calculado depois de `out["final"]`. Porém, examina até o fim da janela, inclusive depois de uma eventual revenda daquele lote. Mede “teria drenado se segurasse”, não necessariamente perda sofrida pela política. Renomearia ou limitaria ao período efetivamente exposto. [sim.py:143](C:/dev/project-hunter/.claude/state/r72/sim.py:143)

- **1(d), reset no abort: não inventa recuperação.** No exemplo `100 → 90 → [timeout] 80 → 71 → 79`, ele conta a queda local 80→71 e a recuperação 71→79. Esses movimentos existem, embora permaneçam abaixo da máxima original. É uma segmentação por episódios, não um retorno à máxima global. Em queda monotônica, esse reset sozinho não produz `swing`. Documentaria também que N começa no primeiro cruzamento da queda, não no fundo posterior. [swings.py:43](C:/dev/project-hunter/.claude/state/r72/swings.py:43), [swings.py:49](C:/dev/project-hunter/.claude/state/r72/swings.py:49)

- **A guarda não certifica ausência de antecipação.** Ela verifica índices e limite temporal do fill; não controla quais dados formaram o sinal. Uma decisão baseada no máximo futuro poderia passar por ela. O braço `cheat` tampouco é um teste suficiente: comparar performances não prova causalidade. Usaria invariância dos sinais ao alterar o sufixo futuro. [sim.py:42](C:/dev/project-hunter/.claude/state/r72/sim.py:42), [sim.py:184](C:/dev/project-hunter/.claude/state/r72/sim.py:184)

## O QUE EU FARIA DIFERENTE

**Pergunta 4 — interpretação da política.** A implementação é uma leitura plausível: vende X% acima da marca da última compra e recompra X% abaixo da referência da venda. Mas “desceu comprou, subiu vendeu” não determina sozinho essas âncoras, nem determina abandono definitivo após N segundos. Essa última condição é uma variante adicional. [sim.py:87](C:/dev/project-hunter/.claude/state/r72/sim.py:87)

Há duas diferenças que precisam ficar explícitas:

- O censo mede recuperação a partir do **mínimo móvel**; o simulador vende a partir da **marca da compra**. Uma compra em 95, seguida de queda a 70 e recuperação a 74, pode completar um swing de 5% no censo, mas não uma venda da política. Portanto, número de oscilações não equivale a número de giros capturáveis. O comentário de `swings.py` dizendo que é o mesmo código usado pelo simulador não corresponde às implementações. [swings.py:6](C:/dev/project-hunter/.claude/state/r72/swings.py:6), [swings.py:54](C:/dev/project-hunter/.claude/state/r72/swings.py:54), [sim.py:110](C:/dev/project-hunter/.claude/state/r72/sim.py:110)
- A referência da queda usa sempre **o lote original**, mesmo depois de recompras que alteraram a quantidade. Para significar literalmente “valor do lote vendido”, deveria congelar a quantidade efetivamente vendida. Com impacto não linear, as duas referências não são idênticas. [sim.py:115](C:/dev/project-hunter/.claude/state/r72/sim.py:115), [sim.py:120](C:/dev/project-hunter/.claude/state/r72/sim.py:120)

Eu manteria a variante atual identificada pelo nome e pré-registraria qualquer interpretação alternativa antes de comparar resultados.

**Pergunta 3 — vieses favoráveis e possibilidade de inverter um negativo.**

Além dos custos subcotados, há execução sempre bem-sucedida, latência constante sem cauda e nenhuma restrição explícita de slippage nas pernas. Isso tende a favorecer uma política com mais operações. [sim.py:28](C:/dev/project-hunter/.claude/state/r72/sim.py:28), [sim.py:71](C:/dev/project-hunter/.claude/state/r72/sim.py:71)

Sobre impacto: concordo em tratá-lo como uma limitação otimista, mas **não como um limite superior matematicamente demonstrado**. A foto ressincronizada contém nossas operações reais, enquanto o caminho pula nossos trades; a interação pode alterar gatilhos em ambas as direções. Essa limitação já está registrada no R65. [load.py:175](C:/dev/project-hunter/.claude/state/r72/load.py:175), [load.py:207](C:/dev/project-hunter/.claude/state/r72/load.py:207), [KB-0147:44](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista.md:44>)

**Corrigir um viés estritamente favorável não resgata um resultado negativo, mantendo as operações fixas.** Mas os problemas encontrados não têm todos essa direção: cobertura pode esconder giros, o relógio pode rejeitar recompras válidas e a ordenação pode criar ou apagar sinais. Eles podem mudar o veredito; **não medi se mudariam este**.

## CONCORDO COM

- Comparar políticas sobre as mesmas entradas, com diferenças pareadas e bootstrap por mint, conforme H-009. [Fila de Hipóteses:118](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:118>)
- Separar marca de decisão e fluxo de caixa realizado, desde que as taxas sejam reconciliadas.
- Usar lamports inteiros e `Decimal` nas operações monetárias principais; os três módulos respeitam o limite de 350 linhas. [sim.py:50](C:/dev/project-hunter/.claude/state/r72/sim.py:50), [load.py:51](C:/dev/project-hunter/.claude/state/r72/load.py:51)
- Excluir e contar as posições somente com fotos; falta qualificar a continuidade das restantes.

## OBSIDIAN

Nenhuma página foi modificada. Deveriam ser atualizadas:

- **Fila de Hipóteses — H-009:** manter aberta até corrigir relógio, reconstrução, custos e comparador; explicitar censura por cobertura.
- **KB-0147 — Custo é o prejuízo:** distinguir custo histórico normalizado de alíquota aplicável por nova perna.
- **KB-0149 — O que a mesa real ensinou:** registrar a diferença entre ordem da cadeia, disponibilidade da observação e horário de execução.
- **Revisões-Astra — R72/H-009** *(nova nota)*: preservar os cenários reproduzidos e os critérios para reavaliar o estudo.