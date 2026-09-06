---
tags: [knowledge, nota, livros, metodo, filtros]
tema: meta-rotulagem e relógio de amostragem
fonte: Marcos López de Prado, *Advances in Financial Machine Learning* — meta-rotulagem e barras alternativas (volume/dólar)
fonte_url: https://en.wikipedia.org/wiki/Meta-Labeling
lido_em: 2026-09-06
evidencia: anedótico
hipotese_testavel: sim
astra: concorda
---

# Meta-rotulagem: o formato de todo filtro que a gente já propôs

## O que afirma

**Meta-rotulagem** separa duas decisões que quase todo sistema mistura: *para que lado* e *se vale a
pena agir*. Um modelo primário dá o lado; um segundo modelo é treinado tendo como **alvo** o
resultado do primeiro — esse alvo é o *meta-rótulo* — e decide se aquele sinal específico deve ser
tomado. A consequência de método é a que interessa: o segundo modelo é um **classificador binário**,
então precisão, revocação e taxa de retenção passam a ser leituras necessárias — **ao lado da
expectancy, nunca no lugar dela.** Um filtro com 90% de precisão pode ter expectancy negativa: nove
ganhos de +0,1 R e uma perda de −2 R dão exatamente isso (exemplo da Astra). Classificação e
resultado financeiro têm de coexistir.

**Barras alternativas:** amostrar o mercado pelo relógio (uma barra a cada 15 minutos) produz séries
com propriedades estatísticas ruins, porque a atividade não é uniforme no tempo. Amostrar por volume
negociado ou por valor negociado ("dollar bars") produz retornos mais bem comportados.

Ressalvas de fonte, e são duas. **O livro não foi lido nesta rodada** — li descrições abertas do
método. E os ganhos numéricos que fontes secundárias reportam para meta-rotulagem em exemplos
específicos **não foram verificados por mim nem pela Astra**, então saíram desta nota inteiramente:
não entram como evidência, não entram como expectativa, e não entram nem como contraexemplo.

## Onde foi mostrado

Séries financeiras genéricas, em contexto de aprendizado de máquina, com exemplos do autor e
reimplementações de terceiros. Nada específico a perpétuos de cripto em 15 minutos, e nada que
estabeleça tamanho de efeito transferível.

## Como mediríamos aqui

**A contribuição desta nota é de vocabulário, e ela reorganiza metade do backlog.** Olhe a fila:

| Candidata | Estratégia-base | O que é |
|---|---|---|
| #6 gate de tendência `return_4h > 0` | `momentum_v1` | filtro binário (e redundante — [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]]) |
| #7 impulso recente excessivo | `momentum_v1` | filtro binário |
| #8 proximidade da máxima de 24 h | `momentum_v1` | filtro binário |
| #11 desequilíbrio agressor | **`volume_anomaly_v1`** | filtro binário |
| #12 teto de volume (`volume_ratio_5m`) | **`volume_anomaly_v1`** | filtro binário |
| `ER-A` da [[KB-0047-razao-de-eficiencia-de-kaufman]] | `momentum_v1` | filtro binário |

Duas correções da Astra estão embutidas nessa tabela. **Primeira: elas são filtros binários, e isso
não as torna meta-rótulos.** O meta-rótulo é o *alvo* do modelo secundário; o filtro é a *decisão*.
Chamar a coluna inteira de "meta-rótulo" trocaria o alvo pela regra. **Segunda: elas não são todas
sobre a `momentum_v1`** — a #11 é explicitamente sobre a `volume_anomaly_v1`
([[KB-0014-taker-buy-volume-o-que-temos-medido]]), e a #12 é um teto sobre `volume_ratio_5m`, que é
a estratégia de 5 minutos (`volume_anomaly_v1.py:64`). Avaliar as duas contra a população da
`momentum_v1` compararia populações, cadências e gatilhos diferentes, e atribuiria ao filtro uma
diferença entre estratégias.

O que continua valendo é a forma: **decisão binária sobre os sinais de uma estratégia-base
declarada**. Isso tem três consequências práticas, e nenhuma delas é sobre aprendizado de máquina.

1. **As leituras necessárias aumentam.** Um filtro não é avaliado só por "melhorou a expectancy": é
   avaliado por **taxa de retenção**, pelo desempenho na população aceita **e** pela contribuição
   sobre a população da base — os dois denominadores que a Astra exigiu na
   [[KB-0047-razao-de-eficiencia-de-kaufman]], com o cenário dos 100 × 0,10 R contra 10 × 0,20 R. E
   a expectancy **continua** sendo uma delas.
2. **A amostra necessária é maior do que parece.** Um segundo classificador precisa de outcomes
   **rotulados**, e a [[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] mostra
   que a população pode estar concentrada em poucos blocos de tempo. Ajustar qualquer coisa com
   aprendizado sobre isso hoje seria ajustar ruído.
3. **A multiplicidade é a mesma.** Seis filtros testados sobre a mesma população são seis tentativas,
   e a página que cuida disso é o [[Registro de Tentativas]].

### O relógio de amostragem, e por que ele não é uma variante

Trocar barras de 15 minutos por barras de volume **não é reparametrizar a `momentum_v1`: é outra
estratégia**. Muda a janela do rompimento, muda a janela do ATR, muda a janela do volume relativo,
muda a cadência das decisões e muda a máquina de rearme dos slots. Não existe braço que isole "o
efeito do relógio" mantendo o resto igual, porque o resto é definido em unidades do relógio.

Além disso, esbarra numa limitação de dado: o nosso denominador de volume tem problemas conhecidos
([[KB-0018-volume-relatado-e-o-denominador-que-usamos]]) e `quote_volume` é *nullable*, o que torna
"barras de dólar" mal definidas em parte do universo.

Fica registrada como ideia, **bloqueada**, com o motivo escrito — para que ninguém a reproponha
achando que é um parâmetro.

## Hipótese testável no Lab

**`C-META` — convenção de relatório, não tentativa nova.** Toda candidata de filtro passa a declarar
a **estratégia-base**, a **população avaliável** e a **cobertura**, e só então publicar quatro
números. Com `B` = entradas encerradas avaliáveis da base, `A ⊆ B` = aceitas pelo filtro, `μ` =
média de `R_net`:

```
retencao               q = |A| / |B|
delta_por_aceito       μ_A − μ_B
delta_por_oportunidade q·μ_A − μ_B  ( = − Σ R_net dos rejeitados / |B| )
precisao_positiva      nº(R_net > 0 em A)/|A|, publicada ao lado da mesma taxa em B
```

A Astra conferiu a álgebra: rejeitar equivale a contribuição zero, **sem reinvestimento**, e no
exemplo sintético dá `0,1 × 0,20 − 0,10 = −0,08 R` por oportunidade apesar de `+0,10 R` por aceito.

**Requisitos que faltavam e sem os quais os números mentem:** população **maturada**; cobertura das
features; `R_net` **conhecido** — `r_multiple` pode ser nulo por funding indeterminado
(`settle.py:5`); mesma coorte; e tratamento explícito de denominador vazio. **Cenário de falha:** o
`SUM` ignora outcomes nulos enquanto o denominador conta todos os sinais, e o delta sai parecendo
completo sobre resultados parcialmente desconhecidos.

**E uma ressalva que eu tinha subestimado:** se o filtro rodar como **braço independente** em vez de
replay, declarar o despareamento não basta — ele **deixa de ser** efeito de seleção sobre `B`, porque
ocupação e rearme de slots alteram as oportunidades futuras (`episodes.py:57`). Nesse caso os quatro
números descrevem duas estratégias diferentes, não um filtro.

Regra editorial: **nenhum filtro é reportado só pelo primeiro número**, e retenção **não é
revocação** — revocação é a parcela dos positivos da base que o filtro preservou.

**Refutação:** não é falsificável — é convenção. O que ela impede é uma classe inteira de conclusão
falsa (o filtro que "melhora a média" cortando 90% da amostra).

## Por que pode falhar

1. **Convenção não é resultado.** `C-META` não descobre nada; ela só impede um erro. Contá-la como
   entrega da rodada seria inflar o saldo.
2. **Meta-rotulagem de verdade exige modelo**, e modelo exige amostra que não temos. O que esta nota
   propõe é o **formato**, não o classificador. Propor o classificador agora seria propor algo
   inavaliável.
3. **Os quatro números não são independentes**, e ler os quatro sem correção de multiplicidade é
   quatro chances de encontrar significância onde não há.
4. **O rearme dos slots quebra o pareamento, e não é só uma ressalva.** Se o filtro rodar como
   estratégia independente em vez de replay, as entradas **não** são as mesmas: uma barra recusada
   por filtro não é uma barra `not_triggered`, e a máquina de episódios trata as duas de forma
   diferente (`episodes.py:57`). Nesse regime o `delta_por_oportunidade` **não** mede seleção sobre
   `B`; mede a diferença entre duas estratégias.
5. **Barras alternativas podem ser uma boa ideia que nunca conseguiremos avaliar de graça** — e
   admitir isso é melhor que abrir um braço que muda cinco coisas ao mesmo tempo.

## Segunda opinião (Astra)

Na curadoria, colocou López de Prado junto de Pardo e Aronson na categoria **protocolo**, com a
advertência que atravessa esta nota inteira: "purga de intervalos **não** torna toda a amostra
independente". Foi ela também quem exigiu, na revisão da
[[KB-0047-razao-de-eficiencia-de-kaufman]], os dois denominadores que aqui viraram convenção — o
cenário sintético dos 100 sinais a 0,10 R contra 10 a 0,20 R é dela, e é a razão de existir do
`C-META`.

E foi ela quem estabeleceu a fronteira que impede esta nota de virar promessa: **nenhuma dessas
fontes valida a adaptação para cripto em 15 minutos**; o que elas dão é forma, não expectativa de
retorno.

Na revisão da nota, corrigiu quatro coisas: **filtro não é meta-rótulo** (o meta-rótulo é o alvo do
modelo secundário); a #11 e a #12 são sobre a **`volume_anomaly_v1`**, não sobre a `momentum_v1`, e
avaliá-las contra a população errada atribuiria ao filtro uma diferença entre estratégias; a oposição
"precisão em vez de expectancy" está errada e se contradiz com os próprios deltas (nove ganhos de
+0,1 R e uma perda de −2 R dão 90% de precisão com expectancy negativa); e faltavam os requisitos de
população maturada, `R_net` conhecido e denominador vazio. **Confirmou que a álgebra do
`delta_por_oportunidade` está certa** e a reescreveu na forma fechada `q·μ_A − μ_B`.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] ·
[[KB-0047-razao-de-eficiencia-de-kaufman]] ·
[[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0018-volume-relatado-e-o-denominador-que-usamos]]
