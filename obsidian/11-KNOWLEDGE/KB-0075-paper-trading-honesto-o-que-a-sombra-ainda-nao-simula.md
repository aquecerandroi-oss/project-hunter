---
tags: [knowledge, nota, risco, paper-trading, execucao, m4]
tema: dimensionamento e risco / paper trading honesto
fonte: nosso walker.py e pricing.py; docs/RISK_ENGINE.md e docs/PIPELINE.md §8; .claude/agents/risk-engine-guardian.md; notas das rodadas 5 e 7
fonte_url: —
lido_em: 2026-09-06
evidencia: leitura de código + leitura de contrato + medição própria citada
hipotese_testavel: sim
astra: concorda
---

# Paper trading honesto — o que a sombra ainda não simula, e por que os números dela não passam para o M4

## O que afirma

O Shadow Lab e o paper trading do M4 **não são o mesmo simulador**, e a diferença entre eles é grande
o bastante para que nenhum número do primeiro descreva o segundo.

O Lab resolve desfecho por dobra sobre velas de 1 min fechadas (`walker.py:1,118-126`): toque de
stop ou alvo decidido pelo `high`/`low` da vela, saída creditada no `open` da vela seguinte quando há
gap, e preenchimento **integral suposto**, nunca verificado. O contrato do M4 pede outra coisa — o
`risk-engine-guardian` a resume em uma frase: *paper fills walk the real book, apply taker fees,
latency and slippage; partial fills when depth is short*.

Sete diferenças, todas com consequência mensurável:

| # | O Lab hoje | O paper do M4, pelo contrato | Consequência |
|---|---|---|---|
| 1 | preenchimento **integral** por construção | preenchimento **parcial** quando o livro é raso | 35 dos 200 livros medidos não comportam 10.000 USDT ([[KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho]]) |
| 2 | custo fixo de 6 bps por perna + 4 de taxa | custo do **book walk** para o tamanho | 2,48 bps a 500 USDT, 9,36 a 10.000 — o custo é função do tamanho, e o Lab não tem tamanho |
| 3 | stop por `high`/`low` de vela de **negócios** | stop por **toque no mark** (`PIPELINE.md` §8) | instrumentos diferentes: taxa de toque diferente, e a diferença **não foi medida** |
| 4 | sem rejeição de ordem | rejeições, `min_notional`, `step_size` | posições pequenas podem ser **inexecutáveis** e hoje contam como executadas |
| 5 | sem fila, sem tipo de ordem | ordem agressiva explícita ([[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]]) | o Lab tem política de execução implícita que ninguém escreveu |
| 6 | funding tratado como transferência assinada na apuração | funding realizado por ciclo, com cadência real | a mediana de exposição é de 12 a 21 min: a maioria não atravessa ciclo |
| 7 | sem carteira: cada sinal vira acompanhamento | 6 slots, caixa finito, exposição agregada | **981 de 992 entradas chegaram com ≥ 6 acompanhamentos anteriores abertos** ([[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]]) |

A linha 7 é a que fecha a nota: **a diferença entre o Lab e o M4 não é de precisão de custo; é de
população.** **Ressalva obrigatória (correção da Astra):** esse número mede **demanda**, não taxa de
rejeição — a consulta conta acompanhamentos que uma carteira com teto nem teria aberto. Quantas
oportunidades o produto teria pegado só se sabe com **simulação sequencial**, com regra de desempate
declarada para as entradas do mesmo minuto. O que está estabelecido é a direção, não a razão.

## Onde foi mostrado

**No nosso código.** `walker.py` é explícito sobre o que faz: dobra pura sobre barras de 1 min
fechadas, com o comentário do próprio arquivo dizendo que credita o `open` quando o mercado abriu
além da barreira, porque "é o preço que o mercado de fato imprimiu naquele instante"
(`walker.py:91-94`). Isso é honesto quanto ao gap e **silencioso** quanto ao tamanho.

**Nas medições das rodadas 5 e 7**, todas citadas na tabela acima e nas notas correspondentes.

**Na literatura, o que existe e o que não existe.** Não encontrei fonte aberta que quantifique a
diferença paper→real em perpétuos de cripto. O que existe e é aplicável, já registrado:
seleção adversa após o preenchimento ([[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]],
de Hyperliquid, não Binance) e o custo do relógio entre referência e entrada
([[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]], medido por nós). **Nenhum
número de fonte externa sobre "paper contra real" entra nesta nota**, porque não achei nenhum que
tenha método declarado.

## Como mediríamos aqui

O que separa um paper honesto de um paper que engana é uma propriedade só: **o simulador tem de poder
recusar.** Um simulador que nunca recusa preenchimento, nunca preenche parcialmente e nunca rejeita
ordem produz uma distribuição de resultados que não é atingível — e a diferença aparece toda de uma
vez no primeiro dia de dinheiro real.

Quatro coisas concretas, em ordem de quanto mudam o número:

1. **Tamanho declarado** (`assumed_notional_usd`, item 19 da quinta rodada). Sem ele, nada acima é
   sequer formulável.
2. **Preenchimento parcial** contra o livro do instante, com o resto expirando ou virando ordem
   subsequente. Exige o carimbo de execução (item 20).
3. **Recusa por `min_notional` e arredondamento por `step_size`.** É a diferença entre "posição de
   500 USDT" e "posição que a exchange aceita".
4. **Stop no mesmo instrumento que o produto usa.** Se o M4 dispara stop no mark, o Lab que dispara
   no negócio está medindo outra estratégia.

## Hipótese testável no Lab

**Uma, e ela roda sem pré-requisito nenhum** — `D-PAPER-1` no [[Strategy Backlog]]:

> **Diferença entre instrumentos de stop.** Para os 292 desfechos `stop` e os 290 `target` já
> registrados, recomputar o desfecho usando o **mark price** em vez do `high`/`low` da vela de
> negócios, e publicar a matriz de concordância (mesmo desfecho / desfecho diferente / momento
> diferente). Dado necessário: `mark_price` histórico por minuto. **Temos parcialmente** —
> `market_snapshots` guarda `mark_price`, com a chave no **minuto alinhado** e a ressalva de
> look-ahead da terceira rodada ([[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]); a cobertura
> por minuto não foi medida e é a primeira coisa a medir.

O que refutaria a preocupação: concordância alta (digamos, acima de 95% dos desfechos idênticos) diria
que o instrumento não importa nesta escala. **Concordância alta não é o resultado esperado nem o
indesejado** — é só a informação que falta.

E uma **convenção**, `C-PAPER`: todo relatório do Lab passa a trazer, ao lado do resultado, a linha
*"população do Lab: N acompanhamentos; população que o Risk Engine teria admitido: M"*. Enquanto
`M ≪ N`, nenhum número do Lab é previsão sobre o produto. **`M` exige a simulação sequencial descrita
acima e ainda não foi calculado** — o que temos hoje é a demanda (981 de 992 entradas com ≥ 6
acompanhamentos abertos), que é um limite superior grosseiro da lotação, não `M`.

## Por que pode falhar

- **A tabela de sete diferenças compara o Lab com um contrato, não com uma implementação.** O paper
  do M4 não existe; pode acabar diferente do que a página diz.
- **A comparação de instrumentos de stop depende da cobertura de `market_snapshots` por minuto**, que
  é justamente o que a quinta rodada mediu como ruim (8 de 200 sinais com snapshot no próprio
  minuto). O diagnóstico pode ficar sem denominador.
- **A razão `M/N` não foi calculada.** O número de concorrência mede demanda, e convertê-lo em taxa
  de admissão exige simulação sequencial que não foi feita. Qualquer razão publicada antes disso é
  invenção.
- **Nada disto significa que o Lab esteja errado.** Ele mede o que se propôs a medir — se a regra de
  entrada e saída seleciona instantes com informação. O erro seria ler esse número como previsão de
  retorno de uma carteira, e é exatamente esse erro que esta nota tenta tornar impossível.

## Segunda opinião (Astra)

Revisões de 2026-09-06 (`.claude/state/astra-review-KB-sizing-risk-1.md` e `-2.md`).

**A correção que atinge esta nota** veio da primeira: o número de concorrência mede **demanda**, não
taxa de rejeição, e a razão `M/N` que eu tinha publicado (≈ 1/90) **não foi calculada** — exige
simulação sequencial com regra de desempate declarada. Corrigido acima e no `C-PAPER`.

**Concordou com o achado central da nota:** a diferença de preços que importa é **mark contra
negócios** — o contrato prevê stop no mark (`PIPELINE.md:189`) e o walker observa velas
(`walker.py:71`). É o que sustenta o `D-PAPER-1`.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]] ·
[[KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho]] ·
[[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]] ·
[[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0073-alavancagem-em-perpetuos-a-liquidacao-contra-o-nosso-stop]] ·
[[KB-0074-risco-operacional-as-regras-de-nao-operar-quando]]
