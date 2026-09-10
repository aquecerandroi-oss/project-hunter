---
tags: [experimento, amplitude, breadth, elegibilidade, populacao, mean-reversion, pre-registro]
updated: 2026-09-10
status: rascunho
owner: quant-engineer
exp: EXP-0027
strategy: "mean_reversion (+ momentum, se a população permitir)"
version: "a derivar de mean_reversion v10 — nenhuma variante existe"
result: pendente
evaluable: 0
days: 0
last_eval: "—"
---

# EXP-0027 — a amplitude do universo como **célula**: `breadth_5m` em tercis fixados antes de olhar

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0027** é a
> próxima vaga livre lida em 2026-09-10 (BRT); se outra tarefa tomar o número antes, renumerar.
> Nada aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`).
>
> **Escrito ANTES de qualquer derivação, ativação ou replay.** Em 2026-09-10 ~09:20 BRT
> (12:20 UTC) o código da regra está pronto e testado localmente; **a série `market_breadth` não
> tem uma única linha em lugar nenhum**, nenhuma variante existe, nenhuma coorte foi replayada.
> Tudo abaixo é desenho e previsão — não medida. As duas medidas reais deste documento estão na
> seção "O limite que decide tudo" e vieram de consultas **somente leitura** na VPS.

## De onde veio a hipótese (H-P8)

`.claude/state/notes-D-P9.md` §4 / KB-0083, sobre a pior hora da família
(09/09, 21:00Z, −34,02 R em 39 decisões, 0 % de acerto):

- o estouro tem minuto e nome: **19:08 BRT / 22:08Z**, quando **194 dos 200 perpétuos monitorados
  caíram no mesmo minuto** (média −3,71 %, mediana −1,76 %, LABUSDT −35,8 %) e repicaram no minuto
  seguinte. Ali saíram 15 das 39 apostas (−14,77 R, 43 % da hora);
- o **BTC não explica**: no mesmo minuto ele caiu −0,204 % (amplitude 0,246 %);
- e a hora inteira já estava rotulada `BTC_BEAR` com **58–76 % do universo caindo** antes do
  estouro — ou seja, o estado era observável *antes* das decisões, não só depois.

> **Hipótese (congelada):** a fração de perpétuos monitorados que caiu nos 5 minutos completos
> antes do fechamento da barra (`breadth_5m`) **separa a expectancy** das decisões de reversão à
> média: comprar reversão com 70 % do universo caindo não é a mesma aposta que comprar reversão com
> 30 %.

**Isto é uma hipótese sobre um minuto.** Um minuto. Escolher o estado que estava presente no pior
minuto do mês e depois "confirmar" que ele é ruim é exatamente o erro que este documento existe
para não cometer — a mesma armadilha que a EXP-0023 registrou para a hora 12 UTC (melhor-de-24 com
n ≤ 16). Daí as duas decisões de desenho abaixo.

## Célula, nunca filtro — e por que a regra de elegibilidade existe mesmo assim

A leitura primária deste experimento é **por célula**: as decisões do **pai sem portão** são
cortadas em tercis de `breadth_5m` e se compara a expectancy das três células. Nenhuma versão
filtrada é necessária para responder à pergunta.

A regra `breadth` (`--policy breadth=<min>-<max>`, T3.77) entra por um motivo diferente e menor:
**se** uma célula sobreviver ao critério de sucesso, a única forma honesta de testá-la para a
frente é uma versão que declare a faixa *antes* e deixe o mesmo maquinário que decide na faixa viva
decidir o replay. Derivar a variante **antes** de olhar a célula seria pré-registrar um palpite;
derivar depois, com a faixa que a célula deu, é o passo 2 e está no fim deste documento.

## O limite que decide tudo: **esta série não tem passado**

Duas medidas de 2026-09-10 (VPS, `repeatable read read only`):

| medida | valor |
|---|---|
| universo monitorado (perpétuas ativas, binance) | **200** |
| dias dos últimos 90 com ≥ 80 % do universo tendo ≥ 1 200 velas de 1 min | **4 de 91** |

Detalhe: até **28/08** só **16** dos 200 mercados têm velas de 1 min (8 % de cobertura — são os 16
mercados que a T3.7c backfillou); 29/08 salta para 150 e só **05/09 (81 %), 07/09 (81 %), 08/09
(85 %) e 09/09 (93 %)** passam o piso. 06/09 fica em 79 % e fica de fora por 2 pontos.

Consequências, e elas mudam o experimento inteiro:

1. **Um backfill de 90 dias produziria 87 dias de `insufficient_coverage`.** Não é desperdício
   inofensivo: seriam 125 mil linhas dizendo "não deu para olhar", e qualquer coorte de replay
   cortada por elas mediria a cobertura do backfill de velas, não a amplitude do mercado. O CLI
   (`infra/scripts/backfill_breadth.py`) existe, é **dry-run por padrão** e imprime exatamente esta
   tabela antes de qualquer escrita — **não foi rodado na VPS**.
2. **O replay dentro da amostra não é o instrumento aqui**, ao contrário da EXP-0023. No máximo
   ele cobre 4 dias, e 4 dias de calendário é a mesma armadilha que a T3.53 já matou para as
   células de hora-do-dia. **A leitura que vale é prospectiva**, e ela começa no dia em que o
   produtor de minuto sobe.
3. **Portanto o primeiro entregável deste EXP não é uma variante, é uma série.** Subir
   `hunter_scanner_worker.breadth`, deixar acumular, e só cortar quando houver dias suficientes.

## Os tercis, fixados numa janela anterior (e não na janela que vai ser lida)

**Regra de corte, congelada agora:** os dois limiares de tercil de `breadth_5m` são calculados
sobre as linhas `usable` dos **primeiros 7 dias de calendário completos** da série (a "janela de
calibração"), sobre **todos os minutos**, não só os de decisão — e nunca são recalculados. A
janela de calibração é **descartada** da leitura: as células são medidas sobre as decisões
**posteriores** a ela.

Por que assim, e não pelos tercis da própria amostra lida: tercis recalculados sobre a amostra
garantem células de tamanho igual e fazem o corte depender do que se quer medir — o limiar viraria
função do período, e duas leituras sucessivas não seriam comparáveis. Limiar fixo deixa as células
desbalanceadas de propósito; **o desbalanceamento é informação** (um mês em que 70 % dos minutos
caem na célula alta é um mês diferente, e isso tem de aparecer).

Faixa provisória, a substituir pelos números medidos: `baixa = [0, t1)`, `média = [t1, t2)`,
`alta = [t2, 1]`. A faixa do portão que o T3.77 já sabe escrever — `0.10-0.60` — é a **célula
média provisória** e existe hoje só como exemplo executável nos testes e na ACTIVATION §7c;
**não é uma previsão**.

## Previsões registradas antes da corrida (para poderem estar erradas)

1. **Distribuição.** `breadth_5m` não é simétrica em torno de 0,5: em janela calma a mediana deve
   ficar entre 0,40 e 0,60, e a cauda alta (> 0,90) deve ser rara — 194/200 = 0,97 é evento de
   minuto, não de regime. Previsão: **menos de 1 % dos minutos acima de 0,90**.
2. **Direção do efeito.** A hipótese diz que a `mean_reversion` **compradora** vai pior na célula
   alta. Previsão: Δ da célula alta contra a média **negativo**, com a maior parte do dano
   concentrada em poucos minutos (o padrão do KB-0083), o que faz o IC de blocos de dia ser largo
   mesmo com o sinal presente.
3. **Autocorrelação com o regime.** `breadth_5m` alto e `regime_hourly_v1 = BTC_BEAR` devem
   coincidir com frequência. **Se a célula alta for só o `BTC_BEAR` com outro nome, a hipótese não
   acrescenta nada** — e é isso que o braço de controle abaixo testa.
4. **População.** Com o piso de 80 % de cobertura e o produtor no ar, `breadth_unavailable` deve
   ficar **abaixo de 5 %** dos minutos. Acima disso, o problema é a cobertura de velas do universo,
   não a estratégia, e o EXP para até isso ser resolvido.

## Critério de sucesso (pré-registrado; nada aqui se move depois de olhar)

Mesma régua da EXP-0023/T3.59 e da T3.76, aplicada por **célula** contra a célula média:

1. **K1 — população:** `n ≥ 30` decisões terminais **e** ≥ 15 dias de calendário distintos na
   célula. Abaixo disso a célula é **inconclusiva**, nunca negativa, e nada mais é lido dela;
2. **efeito:** |Δ| da expectancy da célula contra a célula média **≥ 0,05 R** por decisão;
3. **estabilidade:** IC 95 % do Δ por **blocos de dia** (10 000 reamostragens,
   `.claude/state/exp-drafts/t342-blocos/blocos.py`, sem alterar uma linha do estimador)
   **inteiramente do mesmo lado de zero**;
4. **K5 — eixo declarado:** se `r_multiple` faltar por `funding_schedule_unknown`, a leitura sai em
   `r_ex_funding` e a tabela **declara o eixo** (PIPELINE §4b item 13). Nenhum agregado de eixo
   misto reivindica o eixo mais forte.

**Cláusula de falsificação (o controle):** a mesma leitura é repetida com as decisões cortadas por
`regime_hourly_v1` em vez de `breadth_5m`. Se o corte por regime produzir um Δ **igual ou maior**,
`breadth_5m` não é um estado novo — é o regime horário reamostrado por minuto, e o veredito do
experimento é `descartar` mesmo que os três itens passem.

E mesmo o sucesso **não** promove nada: uma célula que sobreviva autoriza **um** passo — derivar
uma variante `research_only` com a faixa daquela célula (`--policy breadth=<min>-<max>`) e começar
uma coorte prospectiva com a sua própria porta de K1, semanas depois. Nenhum braço deste EXP toca
carteira.

## Não-antecipação (o que está provado e o que custa)

A série dobra, para o minuto `T`, apenas velas com `open_time + 1 min <= T` — seis velas, de
`T−6min` a `T−1min` — e um mercado sem as seis não é contado
(`packages/indicators/tests/unit/test_breadth_series.py`, inclusive a prova de que mudar a vela que
**abre** no corte não move o número). O portão lê a linha cujo `end_time` é **exatamente** o
`source_bar_close`: sem tolerância, sem "a mais recente antes"
(`services/strategy-worker/tests/test_breadth_gate.py`). O custo declarado disso é que um produtor
atrasado **emudece** a versão com `breadth_unavailable` em vez de deixá-la decidir com um valor
velho — e a fração `breadth_unavailable` é, por isso, um número de saúde do produtor que a
previsão 4 acima transforma numa porta.

## Como parear

**Por (mercado, barra), sobre as barras elegíveis compartilhadas — nunca por decisão** (PIPELINE
§4b item 11, notas T3.52d §4.2). Para a leitura por célula o pareamento nem se aplica (é o mesmo
pai, cortado); ele volta a valer no passo 2, quando existir uma filha com portão. **K4 não é
mensurável em braço com portão** (PIPELINE §4b item 12): a leitura honesta é a do pai.

## Passos (nenhum executado)

1. commit + deploy do código da T3.77 e da migração `0019_market_breadth`;
2. subir o produtor de minuto (`hunter_scanner_worker.breadth`) e **esperar**: sem série não há
   experimento, e o backfill de 90 dias não substitui isso (4 dias úteis de 91);
3. depois de 7 dias completos, fixar os dois limiares de tercil e **escrever os números aqui**;
4. depois de mais ~21 dias, cortar as decisões do pai por célula, com o controle por regime ao lado;
5. veredito por célula; se alguma sobreviver, `derive_variant.py … --policy breadth=<min>-<max>
   --dry-run` e uma coorte prospectiva nova;
6. ≤ 10 linhas em português para o Everton.

## Registro de conferência (preencher depois da corrida, append-only)

| data | célula | faixa | n | dias | expectancy R | Δ vs média | IC 95 % (blocos de dia) | eixo | veredito |
|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — | — |
