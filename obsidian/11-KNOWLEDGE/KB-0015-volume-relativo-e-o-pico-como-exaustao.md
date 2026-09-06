---
tags: [knowledge, nota, volume, sinal, falso-positivo]
tema: Volume e fluxo de ordens
fonte: "Gervais, Kaniel & Mingelgrin, The High-Volume Return Premium (versão de trabalho de dez/1998, Rodney White Center; publicado no Journal of Finance 56(3), 2001) + dado próprio de EXP-0002"
fonte_url: https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/04/9901.pdf
lido_em: 2026-09-06
evidencia: versão de trabalho (não a publicada) + dado próprio inconclusivo por limiar
hipotese_testavel: sim
astra: concorda com correções (causalidade retirada; teto 12 rebaixado a exploratório)
---

# Volume relativo e o pico como exaustão

## O que afirma

A frase de praticante "volume confirma o rompimento" apoia-se, quando apoiada em algo, no **prêmio de
volume alto**: ações com volume anormalmente alto num dia ou numa semana tendem a se valorizar no mês
seguinte, num corte transversal ajustado por tamanho. O mecanismo oferecido é **visibilidade**, e os
autores o apresentam como compatível com o resultado, não demonstrado.

**Uma generalização que eu tinha escrito e retirei:** eu afirmava que, medido em janelas longas (seis
meses), o sinal do efeito **inverte**. Não identifiquei o estudo que sustenta isso, e a fonte que
consultei distingue duas coisas diferentes — **volume habitual entre ações** (característica
persistente do papel) e **choque de volume na própria ação** — ao discutir resultados aparentemente
contrários. Tratar as duas como o mesmo indicador que muda de sinal ao alongar a janela é uma
simplificação sem apoio, e sai da nota. Registro também que li a **versão de trabalho de dezembro de
1998**, não a publicada de 2001.

O que sobrevive, então, é modesto e ainda assim útil: existe literatura de que choque de volume
precede retorno positivo **em ações, no mês seguinte, em corte transversal**. Isso motiva a pergunta.
Não a responde no nosso caso.

## Onde foi mostrado

Ações americanas; volume anormal em janela de dia ou semana; retorno avaliado no mês seguinte;
unidade de análise = carteira. O nosso caso é perpétuo de cripto, volume de **5 minutos** contra a
mediana das **288** barras anteriores, e o resultado de **uma operação** com stop, alvo e invalidação
em 2 h. Quatro dimensões distintas ao mesmo tempo. O que se transfere é a pergunta.

## Como mediríamos aqui

Já há dado, e está em [[EXP-0002-volume-anomaly-v1]] (VPS, `as_of = 2026-09-06T13:00Z`): expectancy
**−0,2304 R**, PF **0,6539**, e **156 de 440** acompanhamentos resolvidos (35%) terminando por
**invalidação**. A regra de invalidação é `close_below` do **meio da barra do sinal** em 5 min
(`volume_anomaly_v1.py:241`).

**Os números, com os denominadores separados** — porque misturá-los é fácil e engana:

| Grandeza | Valor | Denominador |
|---|---|---|
| Invalidados na coorte | 156 | 440 acompanhamentos resolvidos |
| Com MFE **determinado** | 156 | os 156 invalidados |
| MFE médio (até a saída) | 0,3806 R | os 156 |
| Invalidados **com `R_net` conhecido** | **112** | 316 avaliáveis com `R_net` |
| Soma de R dos invalidados | −80,2353 R | os 112 |
| Invalidados com lucro | 0 | **os que têm `R_net` conhecido**, não os 156 |

"Zero invalidados com lucro" é sobre a população com resultado líquido apurado. Ler isso como
"156 perdas verificadas" seria contar como perda quem não teve `R_net`.

**A leitura que eu tinha feito, e por que ela não se sustenta.** Eu escrevi que isso é "exatamente a
assinatura de exaustão". Não é — é **compatível** com exaustão, entre outras explicações, e há três
razões concretas:

1. **O grupo foi selecionado pelo próprio evento de recuo.** A entrada exige fechamento acima do meio
   da barra (linha 162) e a invalidação é definida abaixo **desse mesmo nível** (linha 241). Um grupo
   definido por "voltou abaixo do nível de entrada" concentra perdas por construção.
2. **O acompanhamento para na saída.** A invalidação vista no fechamento é executada na abertura
   seguinte e as barras posteriores não entram na observação
   (`services/strategy-worker/hunter_strategy_worker/walker.py:77,136,170`).
3. **O MFE cobre só esse período interrompido** — duração média de 1035,8 s contra 7200 s de
   horizonte — e é **indeterminado em todos os `target`**, o que impede comparar as médias entre
   invalidados e alvos.

**Cenário que derruba a leitura de exaustão sem mudar um único número publicado:** o preço recua
abaixo do meio da barra, invalida, e retoma a alta antes das 2 h. Recuo transitório, regime adverso
do dia e geometria da saída são igualmente compatíveis com o que observamos.

**Os dois denominadores de "volume relativo", corrigidos.** Eu tinha escrito "288 barras contíguas"
contra "23 janelas disjuntas", como se a diferença fosse contiguidade. Não é: **ambas usam janelas
consecutivas e sem sobreposição** dentro de cada cálculo. As diferenças reais são o **tamanho da
amostra e o período coberto**, e o alinhamento:

| Indicador | Denominador | Período | Alinhamento |
|---|---|---|---|
| `volume_ratio_5m` (estratégia) | mediana de **288** barras de 5 min, atual excluída | **24 h** | exige fechamento de 5 min (`aggregate.py:103`) |
| `relative_volume_5m` (feature) | mediana de **23** janelas de 5 min, atual excluída | **115 min** | últimos minutos disponíveis (`windows.py:77`) |

E a *baseline* sazonal da T2.3 não é um terceiro denominador de volume bruto: é outra camada,
aplicada às **leituras da feature** (`features/volume.py:3`). Três nomes parecidos, três coisas
diferentes — e aplicar um limiar pensado para um deles a outro produziria um número incomparável.

## Hipótese testável no Lab

**H-KB0015a — "A magnitude do `volume_ratio_5m` está associada ao resultado sob a regra atual?"**
(renomeada; a versão anterior prometia confirmar ou refutar exaustão, o que este diagnóstico não
faz). Por faixa de `volume_ratio_5m`, reportar **todos** os modos de saída — `target`, `stop`,
`expired`, `invalidated` — com contagens, a geometria entrada–stop–alvo, custos em R, e o
agrupamento por mercado e por hora, porque efeitos opostos entre mercados podem se compensar e
produzir distribuições agregadas parecidas. **Ausência de diferença detectada não demonstra
equivalência**, e associação agregada não demonstra mecanismo.

**H-KB0015b — teto de volume, como hipótese exploratória.** Hoje o gatilho só tem piso; se o pico
extremo for clímax, não há como recusá-lo:

```
volume_mult      = 4      (mantido)
volume_mult_max  = 12     (EXPLORATÓRIO — sem sustentação apresentada)
```

**O 12 não tem justificativa.** Eu o apresentara como "escolha declarada antes de olhar a
distribuição condicionada", o que é verdade e é insuficiente: uma escolha sem sustentação continua
sem sustentação por ter sido declarada cedo. Ele fica registrado em [[Registro de Tentativas]] como
**exploratório**, e o valor a testar deve sair da distribuição condicionada a pico — medida em (a),
antes.

**Critério de avaliação, corrigido:** "reduzir invalidações sem derrubar a taxa de alvo" **não
basta**. Cenário de falha: o teto elimina muitos invalidados e também poucos vencedores de grande
magnitude; a taxa de invalidação melhora e a expectancy piora. Avaliar exige denominadores
explícitos, **resultado líquido**, cobertura e frequência de sinais. E queda da taxa de alvo,
isoladamente, também não refuta benefício econômico.

**Ordem:** (a) antes de (b). E — correção aceita — (a) **conta** no histórico de pesquisa: um
diagnóstico usado para escolher a próxima hipótese entra em [[Registro de Tentativas]] mesmo sem
variante ativada. Eu tinha escrito "sem gastar uma tentativa"; isso está errado.

## Por que pode falhar

- **Selecionar o grupo pelo próprio evento** e depois explicar o grupo pelo evento — o erro que a
  revisão desta nota corrigiu.
- **MFE truncado pela saída** e indeterminado em todos os `target`: comparação de médias entre modos
  de saída é viés de seleção, não propriedade da estratégia.
- **Dois efeitos num parâmetro.** Um teto muda quais mercados, quais horários e qual ATR ao mesmo
  tempo — o mesmo motivo pelo qual a candidata #10 do [[Strategy Backlog]] foi separada.
- **Um dia** de observação, com dependência entre mercados simultâneos não estimada.
- **Confundir os denominadores** `volume_ratio_5m`, `relative_volume_5m` e a baseline sazonal.
- **Transferência de horizonte** de um efeito mensal em ações: motivação, nunca validação.

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-0015-exaustao.md`. **Cinco must-fix, todos aceitos**, e o veredito
dela sobre a pergunta central foi mais preciso que a minha própria formulação: exaustão é uma
explicação **compatível**, e os dados apresentados **não permitem ordenar** as explicações
concorrentes — nem dizer que são igualmente prováveis.

1. **"Exatamente a assinatura de exaustão" → "compatível com exaustão"**, pelos três motivos que
   escrevi no corpo (seleção pelo próprio evento de recuo; acompanhamento que para na saída,
   `walker.py:77,136,170`; MFE truncado e indeterminado em todos os `target`). Cenário de falha dela:
   preço recua, invalida e retoma antes das 2 h — os números publicados continuam iguais e a
   conclusão seria falsa.
2. **H-KB0015a reformulada.** "Concentração confirma / distribuições parecidas refutam" excede o que
   o diagnóstico responde.
3. **O teto 12 não tem sustentação apresentada**, e o critério "menos invalidações sem derrubar a
   taxa de alvo" é insuficiente — com o cenário de falha do teto que corta poucos vencedores grandes.
4. **"Zero invalidados com lucro" precisa de denominador**: 156 é a contagem de invalidados; a
   decomposição financeira usa 112 dentro dos 316 com `R_net`.
5. **A generalização da reversão em seis meses sai da nota** por falta de referência identificada, e
   a fonte que consultei é a **versão de trabalho de 1998**, não a publicada.

Correção técnica que ela acrescentou e que eu tinha errado: a diferença entre `volume_ratio_5m` e
`relative_volume_5m` **não** é contiguidade — ambas usam janelas consecutivas sem sobreposição. É
**288 (24 h) contra 23 (115 min)** e o alinhamento (`aggregate.py:103` contra `windows.py:77`).
Também aceitei o corte de "sem gastar uma tentativa".

**Divergência:** nenhuma. Adotei a separação dela entre as duas perguntas — *o ratio ajuda a
selecionar entradas?* e *a invalidação encerra operações que depois recuperariam?* — porque nenhuma
das duas exige declarar exaustão antes.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] ·
[[KB-0014-taker-buy-volume-o-que-temos-medido]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[EXP-0002-volume-anomaly-v1]] ·
[[Volume Agent]] · [[Features]] · [[Anomalies]]
